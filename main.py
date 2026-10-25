"""SenioreM — голосовой помощник для Windows."""
import datetime
import math
import os
import sys
import threading
import time
import traceback
import webbrowser

from PySide6.QtCore import QLockFile, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QIcon, QKeySequence,
                           QLinearGradient, QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QColorDialog, QGridLayout, QHBoxLayout,
                               QPushButton, QSlider,
                               QLineEdit, QMessageBox, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import actions
import asr
import live
import ai
import commands
import config
import theme as T
import sites
import widgets
import tts
from auth import AuthError, AuthStore, Mailer
from splash import Splash
from settings import (NAME_PRESETS, WAKE_REPLY_PRESETS, Settings, greeting, personalize,
                      set_autostart)
from theme import (Backdrop, Clickable, ConfirmDialog,
                   LogoMark, PlayButton, Toggle,
                   apply_app_theme, button, card, field, font, hline, label, set_role,
                   switch_page, window_controls)
from voice import Chime, Listener, Speaker


class AIBridge(QObject):
    progress = Signal(float, str)
    done = Signal(str)
    answer = Signal(str)


class Bridge(QObject):
    """Передаёт результаты из фоновых потоков в интерфейс."""
    mail_done = Signal(str, str)        # email, ошибка ('' если ок)
    action_done = Signal(str, str)      # ответ, действие окна
    volume = Signal(int)                # текущая громкость системы
    recognized = Signal(str)            # текст, уточнённый точным распознаванием


# ================================================================== вход
class FormBase(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(432)
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(0)

    def head(self, eyebrow, title, body=""):
        self.col.addWidget(label(eyebrow, 11, QFont.DemiBold, "accent", spacing=2.2))
        self.col.addSpacing(14)
        self.col.addWidget(label(title, 36, QFont.Light, display=True))
        if body:
            self.col.addSpacing(10)
            self.body = label(body, 15, role="muted", wrap=True)
            self.col.addWidget(self.body)
        self.col.addSpacing(40)

    def add_field(self, caption, edit):
        self.col.addWidget(label(caption, 12, QFont.DemiBold, "muted", spacing=0.6))
        self.col.addSpacing(2)
        self.col.addWidget(edit)
        self.col.addSpacing(26)
        return edit

    def add_error(self):
        self.error = label("", 13, role="error", wrap=True)
        self.error.setMinimumHeight(20)
        self.col.addWidget(self.error)
        self.col.addSpacing(14)

    def show_error(self, text):
        self.error.setText(text)


class RegisterForm(FormBase):
    def __init__(self, by_email=False):
        super().__init__()
        if by_email:
            self.head("РЕГИСТРАЦИЯ", "Создать аккаунт",
                      "Подтвердим почту одноразовым кодом — это займёт минуту.")
            self.email = self.add_field("Почта", field("you@mail.ru"))
        else:
            self.head("РЕГИСТРАЦИЯ", "Создать аккаунт",
                      "Придумайте логин и пароль — это займёт несколько секунд.")
            self.email = self.add_field("Логин", field("например: kirill"))
        self.pw = self.add_field("Пароль", field("минимум 6 символов", True))
        self.pw2 = self.add_field("Повторите пароль", field("", True))
        self.add_error()
        self.submit = button("Получить код" if by_email else "Создать аккаунт")
        self.col.addWidget(self.submit)
        self.col.addSpacing(18)
        self.to_login = button("Уже есть аккаунт?  Войти", "link", 14, QFont.Normal)
        self.col.addWidget(self.to_login, 0, Qt.AlignLeft)
        self.email.returnPressed.connect(self.pw.setFocus)
        self.pw.returnPressed.connect(self.pw2.setFocus)
        self.pw2.returnPressed.connect(self.submit.click)


class LoginForm(FormBase):
    def __init__(self, by_email=False):
        super().__init__()
        self.head("ВХОД", "С возвращением", "Войдите в свой аккаунт SenioreM.")
        self.email = self.add_field("Почта" if by_email else "Логин",
                                    field("you@mail.ru" if by_email else "ваш логин"))
        self.pw = self.add_field("Пароль", field("", True))
        self.add_error()
        self.submit = button("Войти")
        self.col.addWidget(self.submit)
        self.col.addSpacing(18)
        self.to_register = button("Нет аккаунта?  Создать", "link", 14, QFont.Normal)
        self.col.addWidget(self.to_register, 0, Qt.AlignLeft)
        self.email.returnPressed.connect(self.pw.setFocus)
        self.pw.returnPressed.connect(self.submit.click)


class _CodeBox(QLineEdit):
    def __init__(self, owner, idx):
        super().__init__()
        self.owner, self.idx = owner, idx
        self.setProperty("role", "code")
        self.setFixedSize(54, 66)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(font(26, QFont.Medium))
        self.setContextMenuPolicy(Qt.NoContextMenu)

    def keyPressEvent(self, e):
        k, t = e.key(), e.text()
        if e.matches(QKeySequence.Paste):
            self.owner.paste(self.idx)
        elif t and t.isdigit():
            self.owner.type_digit(self.idx, t)
        elif k == Qt.Key_Backspace:
            self.owner.backspace(self.idx)
        elif k == Qt.Key_Left:
            self.owner.focus(self.idx - 1)
        elif k == Qt.Key_Right:
            self.owner.focus(self.idx + 1)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.owner.submit.emit()


class CodeInput(QWidget):
    completed = Signal()
    submit = Signal()

    def __init__(self, n=6):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.boxes = [_CodeBox(self, i) for i in range(n)]
        for b in self.boxes:
            row.addWidget(b)
        row.addStretch(1)

    def focus(self, i):
        if 0 <= i < len(self.boxes):
            self.boxes[i].setFocus()
            self.boxes[i].selectAll()

    def value(self):
        return "".join(b.text() for b in self.boxes)

    def clear(self):
        for b in self.boxes:
            b.clear()
        self.focus(0)

    def type_digit(self, i, d):
        self.boxes[i].setText(d)
        if i < len(self.boxes) - 1:
            self.focus(i + 1)
        if len(self.value()) == len(self.boxes):
            self.completed.emit()

    def backspace(self, i):
        if self.boxes[i].text():
            self.boxes[i].clear()
        elif i > 0:
            self.boxes[i - 1].clear()
            self.focus(i - 1)

    def paste(self, i):
        digits = [c for c in QGuiApplication.clipboard().text() if c.isdigit()]
        for j, d in enumerate(digits[: len(self.boxes) - i]):
            self.boxes[i + j].setText(d)
        self.focus(min(i + len(digits), len(self.boxes) - 1))
        if len(self.value()) == len(self.boxes):
            self.completed.emit()


class VerifyForm(FormBase):
    def __init__(self):
        super().__init__()
        self.head("ПОДТВЕРЖДЕНИЕ", "Введите код", " ")
        self.code = CodeInput()
        self.col.addWidget(self.code)
        self.col.addSpacing(18)
        self.note = label("", 13, role="accent", wrap=True)
        self.note.hide()
        self.col.addWidget(self.note)
        self.add_error()
        self.submit = button("Подтвердить")
        self.col.addWidget(self.submit)
        self.col.addSpacing(18)
        links = QHBoxLayout()
        links.setSpacing(28)
        self.resend = button("Отправить ещё раз", "link", 14, QFont.Normal)
        self.back = button("Изменить почту", "link", 14, QFont.Normal)
        links.addWidget(self.resend)
        links.addWidget(self.back)
        links.addStretch(1)
        self.col.addLayout(links)
        self.code.completed.connect(self.submit.click)
        self.code.submit.connect(self.submit.click)


class AuthScreen(Backdrop):
    """Слева — логотип, название и возможности; справа — форма в карточке."""

    def __init__(self, win, by_email=False):
        super().__init__(glows=((0.25, 0.42, 0.55), (0.80, 0.80, 0.40)))
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 24, 40)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addLayout(window_controls(win))
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(0)
        root.addLayout(body, 1)

        # ---- бренд
        brand = QVBoxLayout()
        brand.setContentsMargins(72, 0, 48, 0)
        brand.setSpacing(0)
        brand.addStretch(1)
        brand.addWidget(LogoMark(150), 0, Qt.AlignLeft)
        brand.addSpacing(18)
        brand.addWidget(label("ГОЛОСОВОЙ ПОМОЩНИК ДЛЯ WINDOWS", 11, QFont.DemiBold, "accent",
                              spacing=2.2))
        brand.addSpacing(10)
        brand.addWidget(label("SenioreM", 88, QFont.Light, display=True, spacing=-2))
        brand.addSpacing(10)
        brand.addWidget(label("Скажите «Сеньор» — остальное он сделает сам.",
                              21, QFont.Light, "muted", display=True))
        brand.addSpacing(40)
        feats = QGridLayout()
        feats.setHorizontalSpacing(14)
        feats.setVerticalSpacing(14)
        items = [
            ("♪", "Звук и музыка", "«Сеньор, громкость десять»"),
            ("◎", "Сайты и программы", "«Сеньор, открой яндекс музыку»"),
            ("✕", "Закрыть что угодно", "«Сеньор, закрой телеграм»"),
            ("⌕", "Поиск и ответы", "«Сеньор, который час»"),
        ]
        for i, (ico, title, ex) in enumerate(items):
            c, lay = card((18, 16, 18, 16), 4)
            c.setMinimumWidth(270)
            head = QHBoxLayout()
            head.setSpacing(10)
            badge = label(ico, 15, QFont.DemiBold, "accent")
            badge.setFixedWidth(20)
            head.addWidget(badge)
            head.addWidget(label(title, 15, QFont.DemiBold), 1)
            lay.addLayout(head)
            lay.addWidget(label(ex, 13, role="muted"))
            feats.addWidget(c, i // 2, i % 2)
        brand.addLayout(feats)
        brand.addStretch(1)
        body.addLayout(brand, 11)

        # ---- формы
        right = QVBoxLayout()
        right.addStretch(1)
        self.form_card, fl = card((44, 40, 44, 36))
        self.form_card.setFixedWidth(520)
        self.stack = QStackedWidget()
        self.register = RegisterForm(by_email)
        self.login = LoginForm(by_email)
        self.verify = VerifyForm()
        for f in (self.register, self.login, self.verify):
            self.stack.addWidget(f)
        fl.addWidget(self.stack)
        right.addWidget(self.form_card, 0, Qt.AlignHCenter)
        right.addStretch(1)
        body.addLayout(right, 9)

    def show_form(self, form):
        switch_page(self.stack, form, 180)
        form.show_error("")


# ================================================================== главный экран
class Orb(QWidget):
    """Круг-индикатор. Когда вы говорите — пульсирует, расходится волнами и синеет."""

    def __init__(self, size=340):
        super().__init__()
        self.setFixedSize(size, size)
        self.state = "loading"
        self._level = 0.0
        self._target = 0.0
        self._heat = 0.0          # 0 — спокойный, 1 — ярко-синий
        self._t = 0.0
        self._ripples = []        # [радиус 0..1, прозрачность]
        self._last_ripple = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)

    def push_level(self, v):
        self._target = max(self._target, v)
        if v > 0.10 and self._t - self._last_ripple > 0.22:
            self._ripples.append([0.0, min(1.0, 0.35 + v)])
            self._last_ripple = self._t

    def _tick(self):
        self._t += 0.016
        self._level += (self._target - self._level) * 0.25
        self._target *= 0.85
        active = self.state in ("armed", "busy") or self._level > 0.06
        goal = 1.0 if active else (0.55 if self.state == "speaking" else 0.0)
        self._heat += (goal - self._heat) * 0.08
        for r in self._ripples:
            r[0] += 0.012
            r[1] *= 0.965
        self._ripples = [r for r in self._ripples if r[0] < 1.0 and r[1] > 0.02]
        if self.state == "speaking" and self._t - self._last_ripple > 0.55:
            self._ripples.append([0.0, 0.45])
            self._last_ripple = self._t
        self.update()

    @staticmethod
    def _mix(a, b, t):
        a, b = QColor(a), QColor(b)
        return QColor(int(a.red() + (b.red() - a.red()) * t),
                      int(a.green() + (b.green() - a.green()) * t),
                      int(a.blue() + (b.blue() - a.blue()) * t))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 4
        breathe = (math.sin(self._t * 2.2) + 1) / 2
        lvl = min(1.0, self._level)

        if self.state == "error":
            core = QColor(T.ERROR)
        elif self.state == "speaking":
            core = self._mix(T.ACCENT_SOFT, "#FFFFFF", breathe * 0.6)
        else:
            core = self._mix(T._mix(T.LINE, "#FFFFFF", 0.08), T.ACCENT, self._heat)

        # свечение позади
        g = QRadialGradient(c, R)
        glow = QColor(core)
        glow.setAlpha(int(40 + 70 * self._heat + 60 * lvl))
        g.setColorAt(0.0, glow)
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)

        # расходящиеся волны
        for rad, alpha in self._ripples:
            col = QColor(core)
            col.setAlphaF(max(0.0, alpha * (1 - rad)))
            p.setPen(QPen(col, 2.0))
            p.setBrush(Qt.NoBrush)
            rr = R * (0.30 + 0.66 * rad)
            p.drawEllipse(c, rr, rr)

        # внешнее кольцо
        ring = self._mix(T.LINE, T.ACCENT, self._heat)
        ring.setAlphaF(0.55 + 0.35 * breathe * self._heat)
        p.setPen(QPen(ring, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R * 0.86, R * 0.86)

        # ядро
        base = R * 0.27
        if self.state in ("speaking", "busy", "loading"):
            r = base + R * 0.06 * breathe
        else:
            r = base + R * 0.03 * breathe + R * 0.42 * lvl
        cg = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.4), r * 1.6)
        cg.setColorAt(0.0, self._mix(core, "#FFFFFF", 0.45))
        cg.setColorAt(1.0, core)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(c, r, r)


STATE_TEXT = {
    "loading": "ЗАГРУЖАЮ РАСПОЗНАВАНИЕ…",
    "idle": "СКАЖИТЕ «СЕНЬОР»",
    "armed": "СЛУШАЮ",
    "busy": "ВЫПОЛНЯЮ",
    "speaking": "ГОВОРЮ",
    "error": "",
}

TIPS = [
    ("Звук", ["громкость 30", "громче / тише", "выключи звук"]),
    ("Сайты", ["открой яндекс музыку", "открой ютуб", "открой госуслуги"]),
    ("Программы", ["открой телеграм", "вруби запрет", "закрой браузер"]),
    ("Поиск", ["найди погоду в Москве", "который час", "какое сегодня число"]),
    ("Музыка", ["пауза", "следующий трек", "предыдущий трек"]),
    ("Система", ["сделай скриншот", "яркость 70", "заблокируй компьютер"]),
]


class HistoryList(QWidget):
    def __init__(self, limit=7):
        super().__init__()
        self.limit = limit
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)

    def set_items(self, items):
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not items:
            self.lay.addWidget(label("Здесь появятся ваши команды.", 14, role="faint", wrap=True))
            return
        for h in items[: self.limit]:
            row = QHBoxLayout()
            row.setSpacing(12)
            t = label(datetime.datetime.fromtimestamp(h.get("t", 0)).strftime("%H:%M"),
                      12, QFont.DemiBold, "faint")
            t.setFixedWidth(40)
            t.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            col = QVBoxLayout()
            col.setSpacing(2)
            cmd = h.get("cmd", "")
            col.addWidget(label(cmd[:1].upper() + cmd[1:], 14, QFont.DemiBold, wrap=True))
            if h.get("reply"):
                col.addWidget(label(h["reply"], 12, role="muted", wrap=True))
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(12)
            wl.addWidget(t, 0, Qt.AlignTop)
            wl.addLayout(col, 1)
            self.lay.addWidget(w)


class VolumeMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.value = 0.0
        self.target = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30)

    def _tick(self):
        if abs(self.target - self.value) > 0.002:
            self.value += (self.target - self.value) * 0.2
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.LINE))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 6), 3, 3)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor(T.ACCENT))
        g.setColorAt(1, QColor(T.ACCENT_SOFT))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 0, max(6, self.width() * self.value), 6), 3, 3)


class HomeScreen(Backdrop):
    logout_requested = Signal()
    profile_requested = Signal()

    def __init__(self, win, cfg, speaker: Speaker, model=None):
        super().__init__(glows=((0.5, 0.42, 0.42), (0.08, 0.95, 0.35), (0.95, 0.10, 0.30)))
        self.win, self.cfg, self.speaker, self.model = win, cfg, speaker, model
        self.settings = None
        self.listener = None
        self._old_listeners = []
        self.armed = False
        self.speaking = False
        self.mic = "loading"
        self.chime = Chime()
        self.bridge = Bridge()
        self.bridge.action_done.connect(self._on_action_done)
        self.bridge.volume.connect(self._on_volume)
        self.bridge.recognized.connect(lambda t: self.execute(t))
        self.speaker.speaking.connect(self._on_speaking)
        self.arm_timer = QTimer(self)
        self.arm_timer.setSingleShot(True)
        self.arm_timer.timeout.connect(self._disarm)
        self._last_cmd = ""
        self._continue = False
        self._voice_cmd = False

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 30)
        root.setSpacing(0)

        # ---- верхняя панель
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(LogoMark(34, glow=False))
        top.addWidget(label("SenioreM", 18, QFont.DemiBold))
        top.addStretch(1)
        self.clock = label("", 14, role="muted")
        top.addWidget(self.clock)
        top.addSpacing(18)
        self.avatar = button("", "avatar", 15, QFont.DemiBold)
        self.avatar.setToolTip("Профиль и настройки")
        self.avatar.clicked.connect(self.profile_requested.emit)
        top.addWidget(self.avatar)
        top.addSpacing(10)
        top.addLayout(window_controls(win))
        root.addLayout(top)
        root.addSpacing(18)

        # ---- три колонки: виджеты слева и справа, круг — в центре
        body = QHBoxLayout()
        body.setSpacing(28)
        root.addLayout(body, 1)

        def column():
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setFixedWidth(356)
            inner = QWidget()
            lay = QVBoxLayout(inner)
            lay.setContentsMargins(0, 0, 10, 0)
            lay.setSpacing(16)
            area.setWidget(inner)
            return area, lay

        left_area, left = column()
        right_area, right = column()

        self.w_clock = widgets.ClockCard()
        self.w_weather = widgets.WeatherCard()
        self.w_system = widgets.SystemCard()

        self.w_volume, vl = card((24, 18, 24, 20))
        vh = QHBoxLayout()
        vh.addWidget(widgets.caption("ГРОМКОСТЬ"))
        vh.addStretch(1)
        self.vol_lbl = label("—", 13, role="muted")
        vh.addWidget(self.vol_lbl)
        vl.addLayout(vh)
        vl.addSpacing(12)
        self.vol = VolumeMeter()
        vl.addWidget(self.vol)

        self.w_history, hl = card((24, 20, 24, 20))
        hh = QHBoxLayout()
        hh.addWidget(widgets.caption("ПОСЛЕДНИЕ КОМАНДЫ"))
        hh.addStretch(1)
        more = button("Вся история", "link", 12, QFont.Normal)
        more.clicked.connect(lambda: self.win.open_profile("history"))
        hh.addWidget(more)
        hl.addLayout(hh)
        hl.addSpacing(14)
        self.history = HistoryList(6)
        hl.addWidget(self.history)

        self.w_notes = widgets.NotesCard()
        self.w_notes.changed.connect(self._notes_changed)
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._save_notes)

        self.w_tips, rl = card((24, 20, 24, 20))
        rl.addWidget(widgets.caption("ЧТО МОЖНО СКАЗАТЬ"))
        rl.addSpacing(6)
        self.tips_hint = label("Начинайте с «Сеньор». Нажмите на пример, чтобы выполнить.",
                               12, role="muted", wrap=True)
        rl.addWidget(self.tips_hint)
        rl.addSpacing(14)
        for title, examples in TIPS:
            rl.addWidget(label(title, 13, QFont.DemiBold))
            rl.addSpacing(4)
            for ex in examples:
                b = button(f"«{ex}»", "link", 13, QFont.Normal)
                b.clicked.connect(lambda _=False, e=ex: self.execute(e, typed=True))
                rl.addWidget(b, 0, Qt.AlignLeft)
            rl.addSpacing(10)

        self.cards = {"clock": self.w_clock, "weather": self.w_weather, "system": self.w_system,
                      "volume": self.w_volume, "history": self.w_history, "notes": self.w_notes,
                      "tips": self.w_tips}
        for w in (self.w_clock, self.w_weather, self.w_system, self.w_volume):
            left.addWidget(w)
        left.addStretch(1)
        for w in (self.w_history, self.w_notes, self.w_tips):
            right.addWidget(w)
        right.addStretch(1)

        center = QVBoxLayout()
        center.setSpacing(0)
        center.addStretch(2)
        self.orb = Orb(340)
        center.addWidget(self.orb, 0, Qt.AlignHCenter)
        center.addSpacing(26)
        self.state_lbl = label("", 12, QFont.DemiBold, "muted", spacing=2.6)
        self.state_lbl.setAlignment(Qt.AlignCenter)
        center.addWidget(self.state_lbl)
        center.addSpacing(16)
        self.heard = label("", 34, QFont.Light, display=True, wrap=True)
        self.heard.setAlignment(Qt.AlignCenter)
        self.heard.setMinimumHeight(48)
        center.addWidget(self.heard)
        center.addSpacing(8)
        self.reply = label("", 18, role="muted", wrap=True)
        self.reply.setAlignment(Qt.AlignCenter)
        self.reply.setMinimumHeight(28)
        center.addWidget(self.reply)
        center.addStretch(3)
        self.bg_status = label("", 12, role="faint")
        self.bg_status.setAlignment(Qt.AlignCenter)
        center.addWidget(self.bg_status)
        center.addSpacing(10)
        self.input = field("Напишите команду и нажмите Enter…")
        self.input.setFont(font(15))
        self.input.setAlignment(Qt.AlignCenter)
        self.input.setFixedWidth(500)
        self.input.returnPressed.connect(self._typed)
        center.addWidget(self.input, 0, Qt.AlignHCenter)

        body.addWidget(left_area)
        body.addLayout(center, 1)
        body.addWidget(right_area)
        self.apply_widgets()
        self._ai_warmed = False
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._bg_status)
        self._status_timer.start(1000)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._vol_timer = QTimer(self)
        self._vol_timer.timeout.connect(self._poll_volume)

    # ---------- жизненный цикл ----------
    def start(self, email, settings):
        self.settings = settings
        sites.warm()   # список установленных программ — заранее, в фоне
        self.tips_hint.setText(f"Начинайте с «{settings.name}». Нажмите на пример, "
                               "чтобы выполнить.")
        name = settings["name"] or ""
        self.avatar.setText((name or email or "?")[:1].upper())
        self.history.set_items(settings["history"])
        self.w_notes.set_text(settings["notes"] or "")
        self._tick_clock()
        self.heard.setText("")
        self.reply.setText("")
        if self.listener is None:
            self.mic = "loading"
            self.listener = Listener(self.model)
            self.listener.level.connect(self.orb.push_level)
            self.listener.partial.connect(self._on_partial)
            self.listener.final.connect(self._on_final)
            self.listener.failed.connect(self._on_failed)
            self.listener.ready.connect(self._on_ready)
            self.listener.start()
        self._rest_state()
        self._poll_volume()
        self._vol_timer.start(2000)

    def stop(self):
        self._vol_timer.stop()
        if self.listener is not None:
            lst = self.listener
            for sig in (lst.level, lst.partial, lst.final, lst.failed, lst.ready):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
            lst.stop()
            self._old_listeners.append(lst)
            self.listener = None
        self.armed = False

    def _tick_clock(self):
        now = datetime.datetime.now()
        self.clock.setText(f"{now:%H:%M}  ·  {actions.WEEKDAYS[now.weekday()]}, "
                           f"{now.day} {actions.MONTHS[now.month - 1]}")
        if self.settings is not None:
            who = self.settings["name"] or self.settings["address"]
            hello = greeting(now.hour)
            self.w_clock.tick(f"{hello}, {who}" if who else f"{hello}!")

    def apply_widgets(self):
        """Показывает виджеты, выбранные в профиле → «Оформление»."""
        flags = T.APPEARANCE.get("widgets", {})
        for key, w in self.cards.items():
            w.setVisible(bool(flags.get(key, True)))
        self.w_clock.face.set_style(T.APPEARANCE.get("clock_style", "digital"))
        self.clock.setVisible(not flags.get("clock", True))
        if flags.get("weather", True):
            self.w_weather.set_city(T.APPEARANCE.get("city", ""), T.APPEARANCE.get("city_lat"),
                                    T.APPEARANCE.get("city_lon"))

    def _bg_status(self):
        """Строка состояния фоновых загрузок (распознавание, ИИ) под центром экрана."""
        parts = []
        if asr.DOWNLOADS.active:
            parts.append(f"Точное распознавание: {round(asr.DOWNLOADS.frac * 100)}%")
        if ai.DOWNLOADS.active:
            parts.append(f"ИИ-собеседник: {round(ai.DOWNLOADS.frac * 100)}%")
        if parts:
            self.bg_status.setText("Скачиваю в фоне — " + "  ·  ".join(parts) +
                                   "  ·  команды уже работают")
        elif ai.DOWNLOADS.error:
            self.bg_status.setText(ai.DOWNLOADS.error)
        else:
            self.bg_status.setText("")
        if ai.DOWNLOADS.done_kind and not self._ai_warmed:
            self._ai_warmed = True
            kind = ai.DOWNLOADS.done_kind
            threading.Thread(target=lambda: MainWindow._warm_ai(kind), daemon=True).start()

    def _notes_changed(self, _text):
        self._notes_timer.start(800)

    def _save_notes(self):
        if self.settings is not None:
            self.settings.set("notes", self.w_notes.edit.toPlainText())

    def _poll_volume(self):
        def work():
            v = actions.get_volume()
            self.bridge.volume.emit(-1 if v is None else v)
        threading.Thread(target=work, daemon=True).start()

    def _on_volume(self, v):
        if v < 0:
            self.vol_lbl.setText("—")
            return
        self.vol_lbl.setText(f"{v} %")
        self.vol.target = v / 100

    # ---------- состояния ----------
    def _set_state(self, s, text=None):
        self.orb.state = s
        self.state_lbl.setText(text if text is not None else STATE_TEXT.get(s, ""))
        set_role(self.state_lbl, "error" if s == "error" else ("accent" if s == "armed" else "muted"))

    def _rest_state(self):
        if self.speaking:
            self._set_state("speaking")
        elif self.armed:
            self._set_state("armed")
        elif self.mic == "ok":
            name = self.settings.name if self.settings else "Сеньор"
            self._set_state("idle", f"СКАЖИТЕ «{name.upper()}»")
        elif self.mic == "loading":
            self._set_state("loading")
        else:
            self._set_state("error", "МИКРОФОН НЕДОСТУПЕН — МОЖНО ПИСАТЬ КОМАНДЫ")

    def _on_ready(self):
        self.mic = "ok"
        self._rest_state()

    def _on_failed(self, msg):
        self.mic = "error"
        if self.listener is not None:
            self._old_listeners.append(self.listener)
            self.listener = None
        self._rest_state()
        self.reply.setText(msg)

    def _on_speaking(self, flag):
        self.speaking = flag
        if self.listener:
            self.listener.set_paused(flag)
        if not flag:
            if self._continue:
                self._continue = False
                self._arm(quiet=True)       # как у Алисы: ответил — и снова слушает
            elif self.armed:
                self.arm_timer.start(self._listen_ms())
        self._rest_state()

    def _followup_ms(self):
        """Сколько слушать после ответа (0 — сразу перестать)."""
        if self.settings is None:
            return 10000
        try:
            return max(0, int(self.settings["followup_seconds"])) * 1000
        except (TypeError, ValueError):
            return 10000

    def _listen_ms(self):
        try:
            return int(self.settings["listen_seconds"]) * 1000
        except (TypeError, ValueError):
            return 10000

    # ---------- речь ----------
    def _show_heard(self, text, faint):
        self.heard.setText(text)
        self.heard.setStyleSheet(f"color: {T.FAINT if faint else T.TEXT};")

    def _on_partial(self, text):
        if self.orb.state in ("idle", "armed") and text:
            self._show_heard(text, True)
            if self.armed:
                self.arm_timer.start(getattr(self, "_arm_ms", self._listen_ms()))  # не перебиваем

    def _on_final(self, text, confs=None, audio=None):
        words = commands.tokens(text)
        if confs is not None and len(confs) != len(words):
            confs = None
        wake = self.settings.wake_words if self.settings else None
        i = commands.find_wake(words, wake, confs)
        if i >= 0:
            rest = words[i + 1:]
            if rest:
                self._disarm(silent=True)
                self._voice_command(" ".join(rest), audio, strip_wake=True)
            elif not self.armed:
                self._arm()
        elif self.armed:
            self._disarm(silent=True)
            self._voice_command(text, audio, strip_wake=False)
        else:
            self._show_heard("", True)

    def _voice_command(self, vosk_text, audio, strip_wake):
        """Команду после обращения уточняем точным распознаванием (Whisper), если оно готово."""
        if not audio or not asr.RECOGNIZER.available:
            self.execute(vosk_text)
            return
        self._set_state("busy", "РАСПОЗНАЮ…")
        wake = self.settings.wake_words if self.settings else None

        def work():
            text = ""
            try:
                text = asr.RECOGNIZER.transcribe(audio)
            except Exception:  # noqa: BLE001
                pass
            if text and strip_wake:
                w = commands.tokens(text)
                j = commands.find_wake(w, wake, max_pos=2)
                if j < 0 and w and commands.find_wake(w[:1] + ["x"], None) == 0:
                    j = 0
                if j >= 0:
                    w = w[j + 1:]
                text = " ".join(w)
            self.bridge.recognized.emit(text.strip() or vosk_text)

        threading.Thread(target=work, daemon=True).start()

    def _arm(self, quiet=False):
        self.armed = True
        s = self.settings
        if quiet:                       # продолжение разговора — без звука и приветствия
            self._arm_ms = self._followup_ms()
            self.arm_timer.start(self._arm_ms)
            self._rest_state()
            return
        self._arm_ms = self._listen_ms()
        if s is None or s["chime"]:
            self.chime.play()
        self._show_heard("", True)
        reply = (s["wake_reply"] if s else "") or ""
        if s is not None and s["speak_wake_reply"] and reply.strip():
            self.reply.setText(reply)
            QTimer.singleShot(250 if s["chime"] else 0, lambda: self.speaker.say(reply, force=True))
        else:
            self.arm_timer.start(self._listen_ms())
        self._rest_state()

    def _disarm(self, silent=False):
        was = self.armed
        self.armed = False
        self.arm_timer.stop()
        if not silent:
            self._rest_state()
            if was and not self.speaking and self.settings is not None:
                self._show_heard("", True)

    def _typed(self):
        text = self.input.text().strip()
        self.input.clear()
        if text:
            self.execute(text, typed=True)

    # ---------- выполнение ----------
    def execute(self, text, typed=False):
        intent = commands.parse(text)
        intent["typed"] = typed
        self._continue = False
        self._voice_cmd = not typed
        shown = commands.normalize(text)
        self._last_cmd = shown
        self._show_heard(shown[:1].upper() + shown[1:], False)
        if intent["action"] == "stop":
            self.speaker.interrupt()
            self.reply.setText("")
            self._disarm()
            return
        s = self.settings
        ai_on = s is not None and s["ai_enabled"]
        use_ai = ai_on and intent["action"] in ("ask", "unknown", "forget")
        self._set_state("busy", "ДУМАЮ…" if use_ai and intent["action"] != "forget" else None)

        local_ai = use_ai and (s["ai_mode"] or "smart") != "api"
        if local_ai and not ai.local_ready(s["ai_mode"] or "smart"):
            if intent["action"] == "unknown":
                use_ai = False
            elif intent["action"] == "ask":
                use_ai = False     # пока ИИ скачивается — ответ по поиску в интернете

        def work():
            ui = ""
            if intent["action"] == "weather":
                try:
                    reply = live.weather_phrase(T.APPEARANCE, intent.get("day", "now"))
                except Exception:  # noqa: BLE001
                    reply = "Не получилось узнать погоду. Проверьте интернет."
                self.bridge.action_done.emit(reply, "")
                return
            if intent["action"] == "rates":
                try:
                    reply = live.rate_phrase(intent.get("cur", "USD"))
                except Exception:  # noqa: BLE001
                    reply = "Не получилось узнать курс. Проверьте интернет."
                self.bridge.action_done.emit(reply, "")
                return
            if intent["action"] == "ask" and not use_ai:
                # ИИ выключен или ещё скачивается — отвечаем по поиску в интернете
                reply = live.quick_answer(intent.get("text", text))
                self.bridge.action_done.emit(reply, "")
                return
            if use_ai and intent["action"] == "forget":
                ai.ENGINE.forget()
                reply = "Хорошо, начнём разговор заново."
            elif use_ai:
                reply = actions.try_launch(intent.get("text", "")) \
                    if intent["action"] == "unknown" else None
                if reply is None:
                    try:
                        ctx = live.build_context(text, T.APPEARANCE)
                        reply = ai.ENGINE.ask(text, s, ctx)
                        ui = "ai"
                    except ai.AIError as e:
                        reply = str(e)
            else:
                reply, ui = actions.run(intent, self.cfg)
            if intent["action"] != "mute" and actions.is_muted():
                ui += "|muted"
            self.bridge.action_done.emit(reply, ui)

        threading.Thread(target=work, daemon=True).start()

    def _on_action_done(self, reply, ui):
        muted = ui.endswith("|muted")
        ui = ui.replace("|muted", "")
        from_ai = ui == "ai"
        if from_ai:
            ui = ""
        if self.settings is not None:
            if not from_ai:
                reply = personalize(reply, self.settings["address"])
            if self._last_cmd:
                self.settings.add_history(self._last_cmd, reply)
                self.history.set_items(self.settings["history"])
        self.reply.setFont(font(16 if len(reply) > 140 else 18))
        self.reply.setText(reply + ("\nЗвук на компьютере выключен — скажите или напишите "
                                    "«включи звук»." if muted and reply else ""))
        dialog = (self._voice_cmd and ui not in ("quit", "minimize")
                  and self._followup_ms() > 0)
        if reply and self.speaker.enabled:
            self._continue = dialog           # снова слушаем, когда договорит
            self.speaker.say(reply, cache=not from_ai)
        elif dialog:
            self._arm(quiet=True)
        self._rest_state()
        if "громк" in self._last_cmd or "звук" in self._last_cmd or "тише" in self._last_cmd \
                or "громче" in self._last_cmd:
            QTimer.singleShot(300, self._poll_volume)
        if ui == "minimize":
            QTimer.singleShot(300, self.win.smooth_minimize)
        elif ui == "restore":
            self.win.smooth_restore()
        elif ui == "quit":
            QTimer.singleShot(1800, self.win.force_close)


# ================================================================== профиль
class ProfileScreen(Backdrop):
    back_requested = Signal()
    logout_requested = Signal()

    SECTIONS = [
        ("look", "Оформление"),
        ("city", "Город и погода"),
        ("name", "Имя помощника"),
        ("address", "Обращение"),
        ("voice", "Голос"),
        ("wake", "Активация"),
        ("history", "История"),
        ("apps", "Программы и игры"),
        ("ai", "ИИ-собеседник"),
        ("startup", "Запуск"),
        ("account", "Аккаунт"),
        ("about", "О программе"),
    ]

    def __init__(self, win, cfg, store: AuthStore, speaker: Speaker):
        super().__init__(glows=((0.15, 0.20, 0.45), (0.90, 0.90, 0.40)))
        self.win, self.cfg, self.store, self.speaker = win, cfg, store, speaker
        self.settings = None
        self.email = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 36)
        top = QHBoxLayout()
        back = button("←  Назад", "link", 15, QFont.Normal)
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addSpacing(18)
        top.addWidget(label("Профиль и настройки", 18, QFont.DemiBold))
        top.addStretch(1)
        self.saved = label("", 13, role="accent")
        top.addWidget(self.saved)
        top.addSpacing(16)
        top.addLayout(window_controls(win))
        root.addLayout(top)
        root.addSpacing(26)

        body = QHBoxLayout()
        body.setSpacing(28)
        root.addLayout(body, 1)

        # ---- навигация
        nav, nl = card((20, 24, 20, 20))
        nav.setFixedWidth(300)
        self.big_avatar = label("", 30, QFont.DemiBold)
        self.big_avatar.setAlignment(Qt.AlignCenter)
        self.big_avatar.setFixedSize(72, 72)
        self.big_avatar.setProperty("role", "bigavatar")
        nl.addWidget(self.big_avatar, 0, Qt.AlignLeft)
        nl.addSpacing(14)
        self.who = label("", 17, QFont.DemiBold, wrap=True)
        nl.addWidget(self.who)
        self.since = label("", 12, role="muted")
        nl.addWidget(self.since)
        nl.addSpacing(20)
        nl.addWidget(hline())
        nl.addSpacing(14)
        self.nav_buttons = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, title in self.SECTIONS:
            b = button(title, "nav", 15, QFont.Normal)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.show_section(k))
            group.addButton(b)
            nl.addWidget(b)
            self.nav_buttons[key] = b
        nl.addStretch(1)
        body.addWidget(nav)

        # ---- содержимое
        content, cl = card((40, 34, 40, 34))
        self.pages = QStackedWidget()
        cl.addWidget(self.pages)
        body.addWidget(content, 1)
        self.page_widgets = {}
        for key, _ in self.SECTIONS:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            getattr(self, f"_build_{key}")(lay)
            self.pages.addWidget(page)
            self.page_widgets[key] = page

        self.speaker.speaking.connect(self._on_speaking)
        self.speaker.problem.connect(lambda m: self.voice_status.setText(m))

        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(lambda: self.saved.setText(""))

    # ---------- помощники ----------
    @staticmethod
    def _title(lay, title, sub):
        lay.addWidget(label(title, 30, QFont.Light, display=True))
        lay.addSpacing(8)
        lay.addWidget(label(sub, 14, role="muted", wrap=True))
        lay.addSpacing(30)

    @staticmethod
    def _caption(lay, text):
        lay.addWidget(label(text, 12, QFont.DemiBold, "muted", spacing=0.6))
        lay.addSpacing(4)

    def _toggle_row(self, lay, title, sub, key):  # key=None — обработчик подключат отдельно
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(label(title, 15, QFont.DemiBold))
        if sub:
            col.addWidget(label(sub, 13, role="muted", wrap=True))
        row.addLayout(col, 1)
        t = Toggle()
        if key is not None:
            t.toggled.connect(lambda v, k=key: self._set(k, v))
        row.addWidget(t, 0, Qt.AlignVCenter)
        lay.addLayout(row)
        lay.addSpacing(22)
        return t

    def _flash(self, text="Сохранено ✓"):
        self.saved.setText(text)
        self._saved_timer.start(1600)

    def _set(self, key, value):
        if self.settings is None or self._loading:
            return
        self.settings.set(key, value)
        if key in ("voice_speed", "speak_replies", "voice_engine", "yandex_key", "yandex_voice"):
            self.speaker.configure(self.settings["voice_speed"], self.settings["speak_replies"],
                                   self.settings.cloud_voice)
        if key == "autostart":
            if not set_autostart(bool(value)):
                self._flash("Автозапуск работает только в установленной программе")
                return
        self._flash()
        self._refresh_preview()

    _loading = False

    # ---------- разделы ----------
    def _build_name(self, lay):
        self._title(lay, "Имя помощника", "Как вы будете к нему обращаться. Он реагирует только "
                                          "когда фраза начинается с его имени — на разговоры "
                                          "вокруг и фильмы он не отвечает.")
        self._caption(lay, "Выберите имя")
        row = QHBoxLayout()
        row.setSpacing(10)
        group = QButtonGroup(self)
        self.name_buttons = {}
        for nm in NAME_PRESETS:
            b = button(nm, "ghost", 15, QFont.Normal)
            b.setCheckable(True)
            b.setMinimumWidth(110)
            b.clicked.connect(lambda _=False, n=nm: self._pick_name(n))
            group.addButton(b)
            row.addWidget(b)
            self.name_buttons[nm] = b
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(26)
        self._caption(lay, "…или своё имя")
        self.f_ai_name = field("например: Командир")
        self.f_ai_name.textEdited.connect(self._typed_name)
        lay.addWidget(self.f_ai_name)
        lay.addSpacing(8)
        lay.addWidget(label("Лучше выбрать обычное русское слово — так помощник узнаёт его "
                            "надёжнее. Иностранные имена он может не расслышать.", 12,
                            role="faint", wrap=True))
        lay.addSpacing(26)
        ex, el = card((20, 16, 20, 16), 6)
        ex.setProperty("role", "chip")
        el.addWidget(label("КАК ЗВАТЬ", 11, QFont.DemiBold, "accent", spacing=1.6))
        self.name_example = label("", 15, wrap=True)
        el.addWidget(self.name_example)
        lay.addWidget(ex)
        lay.addStretch(1)

    def _pick_name(self, name):
        self.f_ai_name.setText("")
        self._set("assistant_name", name)
        self._refresh_name()

    def _typed_name(self, text):
        text = text.strip()
        for b in self.name_buttons.values():
            b.setChecked(False)
        if text:
            self._set("assistant_name", text)
            self._refresh_name()

    def _refresh_name(self):
        if self.settings is None:
            return
        n = self.settings.name
        for nm, b in self.name_buttons.items():
            b.setChecked(nm.lower() == n.lower())
        self.name_example.setText(f"«{n}, громкость десять»\n«{n}, открой телеграм»\n"
                                  f"«{n}» — и дождитесь ответа, потом скажите команду")

    def _build_address(self, lay):
        self._title(lay, "Обращение", "Как помощник будет к вам обращаться и что отвечать, "
                                      "когда вы скажете «Сеньор».")
        self._caption(lay, "Ваше имя (для приветствия)")
        self.f_name = field("например: Алексей")
        self.f_name.textEdited.connect(lambda v: self._set("name", v.strip()))
        lay.addWidget(self.f_name)
        lay.addSpacing(24)
        self._caption(lay, "Как к вам обращаться в ответах")
        self.f_address = field("например: господин")
        self.f_address.textEdited.connect(lambda v: self._set("address", v.strip()))
        lay.addWidget(self.f_address)
        lay.addSpacing(24)
        self._caption(lay, "Ответ на «Сеньор»")
        self.f_wake = field("например: Да, господин")
        self.f_wake.textEdited.connect(lambda v: self._set("wake_reply", v.strip()))
        lay.addWidget(self.f_wake)
        lay.addSpacing(14)
        chips = QHBoxLayout()
        chips.setSpacing(10)
        for preset in WAKE_REPLY_PRESETS:
            b = button(preset, "ghost", 13, QFont.Normal)
            b.clicked.connect(lambda _=False, p=preset: self._pick_wake(p))
            chips.addWidget(b)
        chips.addStretch(1)
        lay.addLayout(chips)
        lay.addSpacing(30)
        prev, pl = card((20, 16, 20, 16), 6)
        prev.setProperty("role", "chip")
        pl.addWidget(label("КАК ЭТО ЗВУЧИТ", 11, QFont.DemiBold, "accent", spacing=1.6))
        self.preview = label("", 15, wrap=True)
        pl.addWidget(self.preview)
        lay.addWidget(prev)
        lay.addSpacing(16)
        listen = PlayButton("Прослушать")
        listen.clicked.connect(lambda: self._listen_preview(listen))
        lay.addWidget(listen, 0, Qt.AlignLeft)
        lay.addStretch(1)

    def _listen_preview(self, btn):
        self.speaker.interrupt()
        self._playing(btn)
        a, b = self._preview_lines()
        self.speaker.say(a + " " + b, force=True)

    def _pick_wake(self, text):
        self.f_wake.setText(text)
        self._set("wake_reply", text)

    def _preview_lines(self):
        s = self.settings
        wake = (s["wake_reply"] if s else "Слушаю вас") or "Слушаю вас"
        addr = s["address"] if s else ""
        if not wake.rstrip().endswith((".", "!", "?")):
            wake += "."
        return wake, personalize("Готово. Громкость 10 процентов.", addr)

    def _refresh_preview(self):
        if hasattr(self, "preview"):
            a, b = self._preview_lines()
            self.preview.setText(f"Вы: «Сеньор»  →  «{a}»\nВы: «Громкость десять»  →  «{b}»")

    def _build_voice(self, lay):
        self._title(lay, "Голос", "Бесплатный голос «Руслан» работает прямо на компьютере. "
                                  "Голоса Яндекса звучат как у Алисы — нужен ключ Yandex Cloud "
                                  "(стоит копейки) и интернет.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.engine_cards = {}
        for i, (key, title, desc) in enumerate((
                ("piper", "Руслан", "Бесплатно · без интернета"),
                ("yandex", "Голоса Яндекса", "Как у Алисы · по ключу API"))):
            c = Clickable()
            c.setProperty("role", "option")
            c.setCursor(Qt.PointingHandCursor)
            row = QHBoxLayout(c)
            row.setContentsMargins(18, 14, 16, 14)
            col = QVBoxLayout()
            col.setSpacing(3)
            col.addWidget(label(title, 16, QFont.DemiBold))
            col.addWidget(label(desc, 12, role="muted"))
            row.addLayout(col, 1)
            c.clicked.connect(lambda k=key: self._choose_engine(k))
            grid.addWidget(c, 0, i)
            self.engine_cards[key] = c
        lay.addLayout(grid)
        lay.addSpacing(16)

        # --- Яндекс: ключ и выбор голоса
        self.ya_box = QWidget()
        yl = QVBoxLayout(self.ya_box)
        yl.setContentsMargins(0, 0, 0, 0)
        yl.setSpacing(4)
        self._caption(yl, "API-ключ Yandex Cloud")
        krow = QHBoxLayout()
        self.f_ya_key = field("вставьте ключ сюда", True)
        self.f_ya_key.textEdited.connect(lambda v: self._set("yandex_key", v.strip()))
        krow.addWidget(self.f_ya_key, 1)
        how = button("Как получить ключ", "link", 13, QFont.Normal)
        how.clicked.connect(lambda: webbrowser.open(
            "https://yandex.cloud/ru/docs/iam/operations/authentication/manage-api-keys"))
        krow.addSpacing(14)
        krow.addWidget(how)
        yl.addLayout(krow)
        yl.addSpacing(14)
        self._caption(yl, "Голос")
        vg = QGridLayout()
        vg.setHorizontalSpacing(8)
        vg.setVerticalSpacing(8)
        group = QButtonGroup(self)
        self.ya_buttons = {}
        for i, (vid, title, desc) in enumerate(tts.YANDEX_VOICES):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setToolTip(desc)
            b.clicked.connect(lambda _=False, v=vid: self._choose_ya_voice(v))
            group.addButton(b)
            vg.addWidget(b, i // 5, i % 5)
            self.ya_buttons[vid] = b
        yl.addLayout(vg)
        yl.addSpacing(16)
        lay.addWidget(self.ya_box)

        prow = QHBoxLayout()
        self.voice_play = PlayButton("Послушать")
        self.voice_play.clicked.connect(lambda: self._demo_voice(self.voice_play))
        prow.addWidget(self.voice_play)
        prow.addStretch(1)
        lay.addLayout(prow)
        lay.addSpacing(22)
        self._caption(lay, "Скорость речи")
        speeds = QHBoxLayout()
        speeds.setSpacing(10)
        group = QButtonGroup(self)
        self.speed_buttons = {}
        for key, title in (("slow", "Медленнее"), ("normal", "Обычно"), ("fast", "Быстрее")):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(140)
            b.clicked.connect(lambda _=False, k=key: self._choose_speed(k))
            group.addButton(b)
            speeds.addWidget(b)
            self.speed_buttons[key] = b
        speeds.addStretch(1)
        lay.addLayout(speeds)
        lay.addSpacing(14)
        self.voice_status = label("", 13, role="muted", wrap=True)
        lay.addWidget(self.voice_status)
        lay.addSpacing(18)
        self.t_speak = self._toggle_row(lay, "Озвучивать ответы",
                                        "Если выключить, ответы будут только текстом на экране.",
                                        "speak_replies")
        lay.addStretch(1)

    def _choose_engine(self, key):
        self._set("voice_engine", key)
        self._refresh_voice()
        if key == "piper" or self.settings.cloud_voice:
            self._demo_voice(self.voice_play)

    def _choose_ya_voice(self, vid):
        self._set("yandex_voice", vid)
        self._refresh_voice()
        if self.settings.cloud_voice:
            self._demo_voice(self.voice_play)
        else:
            self.voice_status.setText("Сначала вставьте API-ключ Yandex Cloud.")

    def _refresh_voice(self):
        if self.settings is None:
            return
        eng = self.settings["voice_engine"] or "piper"
        for k, c in self.engine_cards.items():
            c.setProperty("selected", "true" if k == eng else "false")
            c.style().unpolish(c)
            c.style().polish(c)
        self.ya_box.setVisible(eng == "yandex")
        for v, b in self.ya_buttons.items():
            b.setChecked(v == (self.settings["yandex_voice"] or "filipp"))

    def _choose_speed(self, key):
        self._set("voice_speed", key)
        self._demo_voice(self.voice_play)

    def _playing(self, btn):
        """Отмечает кнопку, которая сейчас играет; остальные — в обычном виде."""
        old = getattr(self, "_play_btn", None)
        if old is not None and old is not btn:
            old.set_playing(False)
        self._play_btn = btn
        if btn is not None:
            btn.set_playing(True)

    def _on_speaking(self, flag):
        if not flag:
            self._playing(None)

    def _demo_voice(self, btn=None):
        addr = self.settings["address"] if self.settings else ""
        speed = self.settings["voice_speed"] if self.settings else "normal"
        self.voice_status.setText("")
        self.speaker.interrupt()
        self._playing(btn)
        self.speaker.say(personalize("Здравствуйте. Я SenioreM, ваш голосовой помощник.", addr),
                         force=True, speed=speed, cache=True,
                         cloud=self.settings.cloud_voice if self.settings else None)

    def _build_wake(self, lay):
        self._title(lay, "Активация", "Как вы обращаетесь к помощнику и как он даёт понять, "
                                      "что слушает.")
        self._caption(lay, "Дополнительные слова-обращения (через запятую, необязательно)")
        self.f_words = field("например: эй, слушай")
        self.f_words.textEdited.connect(lambda v: self._set("wake_words", v))
        lay.addWidget(self.f_words)
        lay.addSpacing(28)
        self.t_chime = self._toggle_row(lay, "Мягкий звук при обращении",
                                        "Короткий сигнал, когда помощник вас услышал.", "chime")
        self.t_wake_reply = self._toggle_row(lay, "Отвечать голосом на обращение",
                                             "Например: «Слушаю вас» — текст задаётся в разделе "
                                             "«Обращение».", "speak_wake_reply")
        lay.addWidget(label("Микрофон подстраивается сам: помощник слышит и обычную речь, и "
                            "тихий голос, и шёпот. Команды после обращения разбирает точное "
                            "распознавание Whisper — оно понимает даже названия игр.", 13,
                            role="muted", wrap=True))
        lay.addSpacing(26)
        self._caption(lay, "После ответа")
        lay.addWidget(label("Как у Алисы: после ответа помощник ещё немного слушает — можно "
                            "продолжать разговор без «Сеньор». Или сразу перестаёт слушать.", 13,
                            role="muted", wrap=True))
        lay.addSpacing(10)
        frow = QHBoxLayout()
        frow.setSpacing(10)
        fgroup = QButtonGroup(self)
        self.follow_buttons = {}
        for sec, title in ((0, "Сразу выключаться"), (5, "5 с"), (10, "10 с"), (20, "20 с"),
                           (30, "30 с"), (60, "1 мин")):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setMinimumWidth(80 if sec else 190)
            b.clicked.connect(lambda _=False, v=sec: self._set("followup_seconds", v))
            fgroup.addButton(b)
            frow.addWidget(b)
            self.follow_buttons[sec] = b
        frow.addStretch(1)
        lay.addLayout(frow)
        lay.addSpacing(26)
        self._caption(lay, "После «Сеньор» ждать команду")
        row = QHBoxLayout()
        row.setSpacing(10)
        group = QButtonGroup(self)
        self.listen_buttons = {}
        for sec in (5, 10, 15, 20):
            b = button(f"{sec} с", "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(80)
            b.clicked.connect(lambda _=False, s=sec: self._set("listen_seconds", s))
            group.addButton(b)
            row.addWidget(b)
            self.listen_buttons[sec] = b
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

    def _build_history(self, lay):
        self._title(lay, "История", "Последние 100 команд и ответов. Хранится только на этом компьютере.")
        self.full_history = HistoryList(100)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.full_history)
        lay.addWidget(scroll, 1)
        lay.addSpacing(16)
        clear = button("Очистить историю", "danger", 14, QFont.Normal)
        clear.setFixedWidth(220)
        clear.clicked.connect(self._clear_history)
        lay.addWidget(clear, 0, Qt.AlignLeft)

    def _clear_history(self):
        if self.settings is not None:
            self.settings.clear_history()
            self.full_history.set_items([])
            self.win.home.history.set_items([])
            self._flash("История очищена")

    def _build_ai(self, lay):
        self._title(lay, "ИИ-собеседник", "С помощником можно разговаривать и задавать любые "
                                          "вопросы: «расскажи анекдот», «что такое чёрная дыра», "
                                          "«придумай поздравление».")
        self.t_ai = self._toggle_row(lay, "Разговаривать и отвечать на вопросы",
                                     "Всё, что не похоже на команду, помощник обсудит с вами.",
                                     "ai_enabled")
        self._caption(lay, "Где работает ИИ")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.ai_cards = {}
        opts = [("smart", "Умный", "На компьютере · бесплатно · ~2 ГБ"),
                ("fast", "Быстрый", "Для слабых ПК · бесплатно · ~1 ГБ"),
                ("api", "Свой сервер", "OpenAI-совместимый API по ключу")]
        for i, (key, title, desc) in enumerate(opts):
            c = Clickable()
            c.setProperty("role", "option")
            c.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(c)
            cl.setContentsMargins(18, 14, 18, 14)
            cl.setSpacing(3)
            cl.addWidget(label(title, 16, QFont.DemiBold))
            cl.addWidget(label(desc, 12, role="muted", wrap=True))
            c.clicked.connect(lambda k=key: self._choose_ai(k))
            grid.addWidget(c, 0, i)
            self.ai_cards[key] = c
        lay.addLayout(grid)
        lay.addSpacing(18)

        # локальный режим: скачивание
        self.ai_local = QWidget()
        ll = QVBoxLayout(self.ai_local)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        self.ai_status = label("", 14, wrap=True)
        ll.addWidget(self.ai_status)
        self.ai_bar = VolumeMeter()
        self.ai_bar.hide()
        ll.addWidget(self.ai_bar)
        self.ai_download = button("Скачать", "ghost", 14)
        self.ai_download.setFixedWidth(220)
        self.ai_download.clicked.connect(self._download_ai)
        ll.addWidget(self.ai_download, 0, Qt.AlignLeft)
        ll.addWidget(label("Модель Qwen 2.5 работает прямо на вашем компьютере через llama.cpp: "
                           "бесплатно, без ключей и регистрации, разговоры никуда не отправляются. "
                           "Первый ответ после запуска — через несколько секунд.", 12,
                           role="faint", wrap=True))
        lay.addWidget(self.ai_local)

        # свой API
        self.ai_api = QWidget()
        al = QVBoxLayout(self.ai_api)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(4)
        self._caption(al, "Адрес API")
        self.f_api_url = field("например: https://api.groq.com/openai/v1")
        self.f_api_url.textEdited.connect(lambda v: self._set("ai_api_url", v.strip()))
        al.addWidget(self.f_api_url)
        al.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(18)
        kc = QVBoxLayout()
        self._caption(kc, "Ключ")
        self.f_api_key = field("ключ API", True)
        self.f_api_key.textEdited.connect(lambda v: self._set("ai_api_key", v.strip()))
        kc.addWidget(self.f_api_key)
        mc = QVBoxLayout()
        self._caption(mc, "Модель")
        self.f_api_model = field("например: llama-3.3-70b-versatile")
        self.f_api_model.textEdited.connect(lambda v: self._set("ai_api_model", v.strip()))
        mc.addWidget(self.f_api_model)
        row.addLayout(kc, 1)
        row.addLayout(mc, 1)
        al.addLayout(row)
        al.addSpacing(6)
        al.addWidget(label("Ключ хранится только на этом компьютере.", 12, role="faint"))
        lay.addWidget(self.ai_api)

        lay.addSpacing(22)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.ai_test = button("Проверить", "ghost", 14)
        self.ai_test.setFixedWidth(160)
        self.ai_test.clicked.connect(self._test_ai)
        row.addWidget(self.ai_test)
        forget = button("Забыть разговор", "ghost", 14, QFont.Normal)
        forget.setFixedWidth(190)
        forget.clicked.connect(lambda: (ai.ENGINE.forget(), self._flash("Разговор начат заново")))
        row.addWidget(forget)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(10)
        self.ai_answer = label("", 14, role="muted", wrap=True)
        lay.addWidget(self.ai_answer)
        lay.addStretch(1)

        self.ai_bridge = AIBridge()
        self.ai_bridge.progress.connect(self._ai_progress)
        self.ai_bridge.done.connect(self._ai_done)
        self.ai_bridge.answer.connect(self._ai_answer)

    def _choose_ai(self, key):
        self._set("ai_mode", key)
        self._refresh_ai()

    def _refresh_ai(self):
        if self.settings is None:
            return
        mode = self.settings["ai_mode"] or "smart"
        for k, c in self.ai_cards.items():
            c.setProperty("selected", "true" if k == mode else "false")
            c.style().unpolish(c)
            c.style().polish(c)
        self.ai_api.setVisible(mode == "api")
        self.ai_local.setVisible(mode != "api")
        if mode != "api" and ai.DOWNLOADS.active and not getattr(self, "_ai_downloading", False):
            self._ai_downloading = True
            self.ai_download.setEnabled(False)
            self.ai_bar.show()
            if not hasattr(self, "_ai_poll"):
                self._ai_poll = QTimer(self)
                self._ai_poll.timeout.connect(self._poll_ai_download)
            self._ai_poll.start(500)
        if mode != "api" and not getattr(self, "_ai_downloading", False):
            ready = ai.local_ready(mode)
            size = "~2 ГБ" if mode == "smart" else "~1 ГБ"
            self.ai_status.setText("✓ Модель скачана и готова к работе." if ready else
                                   f"Модель ещё не скачана ({size}, один раз).")
            set_role(self.ai_status, "accent" if ready else "muted")
            self.ai_download.setVisible(not ready)
            self.ai_bar.hide()

    def _download_ai(self):
        mode = self.settings["ai_mode"] or "smart"
        self._ai_downloading = True
        self.ai_download.setEnabled(False)
        self.ai_bar.show()
        self.ai_bar.value = self.ai_bar.target = 0.0
        ai.DOWNLOADS.start(mode)
        if not hasattr(self, "_ai_poll"):
            self._ai_poll = QTimer(self)
            self._ai_poll.timeout.connect(self._poll_ai_download)
        self._ai_poll.start(500)

    def _poll_ai_download(self):
        d = ai.DOWNLOADS
        if d.active:
            self._ai_progress(d.frac, d.text)
            return
        self._ai_poll.stop()
        self._ai_done(d.error)

    def _ai_progress(self, frac, text):
        self.ai_bar.target = frac
        self.ai_status.setText(f"{text} · {round(frac * 100)} %")

    def _ai_done(self, err):
        self._ai_downloading = False
        self.ai_download.setEnabled(True)
        self._refresh_ai()
        if err:
            self.ai_status.setText(err)
            set_role(self.ai_status, "error")
            self.ai_download.show()
        else:
            if not self.settings["ai_enabled"]:
                self.t_ai.setChecked(True)
            self._flash("ИИ готов")

    def _test_ai(self):
        self.ai_test.setEnabled(False)
        self.ai_answer.setText("Думаю…")
        s = self.settings

        def work():
            try:
                ans = ai.ENGINE.ask("Привет! Представься одной короткой фразой.", s)
            except ai.AIError as e:
                ans = str(e)
            self.ai_bridge.answer.emit(ans)

        threading.Thread(target=work, daemon=True).start()

    def _ai_answer(self, text):
        self.ai_test.setEnabled(True)
        self.ai_answer.setText(text)
        self.speaker.say(text, force=True, cache=False)

    # ---------- оформление ----------
    def _build_look(self, outer):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 16, 0)
        lay.setSpacing(0)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._title(lay, "Оформление", "Цвет, фон, прозрачность и виджеты главного экрана. "
                                       "Всё применяется сразу.")
        self._caption(lay, "Цвет")
        row = QHBoxLayout()
        row.setSpacing(10)
        group = QButtonGroup(self)
        self.swatches = {}
        for name, color in T.PRESETS:
            b = QPushButton()
            b.setProperty("role", "swatch")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(name)
            b.setStyleSheet(f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                            f"stop:0 {T._mix(color, '#FFFFFF', 0.35)}, stop:1 {color}); }}")
            b.clicked.connect(lambda _=False, c=color: self._set_look(accent=c))
            group.addButton(b)
            row.addWidget(b)
            self.swatches[color.lower()] = b
        custom = button("Свой цвет…", "ghost", 13, QFont.Normal)
        custom.clicked.connect(self._pick_color)
        row.addSpacing(8)
        row.addWidget(custom)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(26)

        self._caption(lay, "Фон")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.bg_cards = {}
        for i, (key, title, desc) in enumerate(T.BACKGROUNDS):
            c = Clickable()
            c.setProperty("role", "option")
            c.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(c)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(2)
            cl.addWidget(label(title, 15, QFont.DemiBold))
            cl.addWidget(label(desc, 12, role="muted", wrap=True))
            c.clicked.connect(lambda k=key: self._choose_bg(k))
            grid.addWidget(c, i // 2, i % 2)
            self.bg_cards[key] = c
        lay.addLayout(grid)
        lay.addSpacing(10)
        self.glass_note = label("", 13, role="accent", wrap=True)
        self.glass_note.hide()
        lay.addWidget(self.glass_note)
        self.restart_btn = button("Перезапустить сейчас", "ghost", 14)
        self.restart_btn.setFixedWidth(240)
        self.restart_btn.clicked.connect(self.win.restart)
        self.restart_btn.hide()
        lay.addWidget(self.restart_btn, 0, Qt.AlignLeft)
        lay.addSpacing(18)

        def slider(title, key, lo, hi):
            self._caption(lay, title)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setFixedWidth(420)
            sl.valueChanged.connect(lambda v, k=key: self._set_look(**{k: v / 100}))
            lay.addWidget(sl)
            lay.addSpacing(20)
            return sl
        self.s_glass = slider("Прозрачность окна (для «Стекла»)", "glass", 15, 85)
        self.s_panels = slider("Плотность панелей", "panels", 25, 95)

        self._caption(lay, "Виджеты на главном экране")
        lay.addSpacing(6)
        self.widget_toggles = {}
        for key, title, sub in (("clock", "Часы", "Крупное время, дата и приветствие"),
                                ("weather", "Погода", "Температура и осадки за окном"),
                                ("system", "Компьютер", "Загрузка процессора, памяти, батарея"),
                                ("volume", "Громкость", "Текущая громкость системы"),
                                ("history", "Последние команды", "Что вы просили недавно"),
                                ("notes", "Заметки", "Записи, которые всегда под рукой"),
                                ("tips", "Подсказки", "Примеры команд")):
            t = self._toggle_row(lay, title, sub, None)
            t.toggled.connect(lambda v, k=key: self._set_widget(k, v))
            self.widget_toggles[key] = t
        self._caption(lay, "Часы")
        crow = QHBoxLayout()
        crow.setSpacing(10)
        cgroup = QButtonGroup(self)
        self.clock_buttons = {}
        for key, title in (("digital", "Цифровые"), ("analog", "Стрелочные")):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(150)
            b.clicked.connect(lambda _=False, k=key: self._set_look(clock_style=k))
            cgroup.addButton(b)
            crow.addWidget(b)
            self.clock_buttons[key] = b
        crow.addStretch(1)
        lay.addLayout(crow)
        lay.addSpacing(22)
        self._caption(lay, "Город для погоды (пусто — определить автоматически)")
        self.f_city = field("например: Магадан")
        self.f_city.editingFinished.connect(lambda: self._set_look(
            city=self.f_city.text().strip(), city_lat=None, city_lon=None)
            if self.f_city.text().strip() != T.APPEARANCE.get("city", "") else None)
        lay.addWidget(self.f_city)
        lay.addStretch(1)

    def _refresh_look(self):
        a = T.APPEARANCE
        self._loading = True
        acc = (a.get("accent") or "").lower()
        for c, b in self.swatches.items():
            b.setChecked(c == acc)
        bg = a.get("background", "aurora")
        for k, c in self.bg_cards.items():
            c.setProperty("selected", "true" if k == bg else "false")
            c.style().unpolish(c)
            c.style().polish(c)
        self.s_glass.setValue(int(float(a.get("glass", 0.55)) * 100))
        self.s_panels.setValue(int(float(a.get("panels", 0.72)) * 100))
        for k, t in self.widget_toggles.items():
            t.setChecked(bool(a.get("widgets", {}).get(k, True)))
        for k, b in self.clock_buttons.items():
            b.setChecked(k == a.get("clock_style", "digital"))
        self.f_city.setText(a.get("city", ""))
        self._loading = False

    def _set_look(self, **changes):
        if self._loading:
            return
        T.set_appearance(QApplication.instance(), **changes)
        self.win.home.apply_widgets()
        self._refresh_look()

    def _set_widget(self, key, value):
        if not self._loading:
            self._set_look(widgets={key: bool(value)})

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(T.ACCENT), self, "Свой цвет")
        if c.isValid():
            self._set_look(accent=c.name())

    def _choose_bg(self, key):
        was_glass = self.win.glass
        self._set_look(background=key)
        need = (key == "glass") != was_glass
        self.glass_note.setVisible(need)
        self.restart_btn.setVisible(need)
        if need:
            self.glass_note.setText("Чтобы прозрачность окна включилась, программу нужно "
                                    "перезапустить." if key == "glass" else
                                    "Чтобы отключить прозрачность окна, перезапустите программу.")

    # ---------- город ----------
    def _build_city(self, lay):
        self._title(lay, "Город и погода", "Для погоды и ответов на вопросы вроде «сколько сейчас "
                                           "градусов» или «нужен ли зонт».")
        self._caption(lay, "Сейчас")
        self.city_now = label("", 20, QFont.DemiBold)
        lay.addWidget(self.city_now)
        lay.addSpacing(4)
        self.city_weather = label("", 14, role="muted", wrap=True)
        lay.addWidget(self.city_weather)
        lay.addSpacing(26)
        self._caption(lay, "Выбрать город")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.f_city_search = field("например: Магадан")
        self.f_city_search.returnPressed.connect(self._search_city)
        row.addWidget(self.f_city_search, 1)
        find = button("Найти", "ghost", 14)
        find.setFixedWidth(120)
        find.clicked.connect(self._search_city)
        row.addWidget(find)
        lay.addLayout(row)
        lay.addSpacing(12)
        self.city_results = QWidget()
        self.city_res_lay = QVBoxLayout(self.city_results)
        self.city_res_lay.setContentsMargins(0, 0, 0, 0)
        self.city_res_lay.setSpacing(8)
        lay.addWidget(self.city_results)
        lay.addSpacing(16)
        auto = button("Определять автоматически", "link", 14, QFont.Normal)
        auto.clicked.connect(lambda: self._choose_city(None))
        lay.addWidget(auto, 0, Qt.AlignLeft)
        lay.addStretch(1)
        self.city_bridge = AIBridge()          # переиспользуем сигналы: answer(str)
        self.city_bridge.answer.connect(lambda t: self.city_weather.setText(t))
        self.city_bridge.progress.connect(lambda _f, t: self._show_city_results(t))

    def _refresh_city(self):
        a = T.APPEARANCE
        self.city_now.setText(a.get("city") or "Определяется автоматически по интернету")
        self.city_weather.setText("Узнаю погоду…")

        def work():
            try:
                txt = live.weather_phrase(T.APPEARANCE, "now")
            except Exception:  # noqa: BLE001
                txt = "Нет связи с сервисом погоды — проверьте интернет."
            self.city_bridge.answer.emit(txt)
        threading.Thread(target=work, daemon=True).start()

    def _search_city(self):
        q = self.f_city_search.text().strip()
        if not q:
            return
        self._show_city_results("…")

        def work():
            try:
                res = live.search_cities(q)
                self._city_found = res
                self.city_bridge.progress.emit(0.0, "ok" if res else "none")
            except Exception:  # noqa: BLE001
                self.city_bridge.progress.emit(0.0, "error")
        threading.Thread(target=work, daemon=True).start()

    def _show_city_results(self, status):
        while self.city_res_lay.count():
            it = self.city_res_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if status == "…":
            self.city_res_lay.addWidget(label("Ищу…", 13, role="muted"))
            return
        if status != "ok":
            self.city_res_lay.addWidget(label("Город не найден." if status == "none" else
                                              "Нет связи с интернетом.", 13, role="error"))
            return
        for r in getattr(self, "_city_found", []):
            title = ", ".join(x for x in (r["name"], r["region"], r["country"]) if x)
            b = button(title, "ghost", 14, QFont.Normal)
            b.setStyleSheet("text-align: left; padding-left: 16px;")
            b.clicked.connect(lambda _=False, rr=r: self._choose_city(rr))
            self.city_res_lay.addWidget(b)

    def _choose_city(self, r):
        if r is None:
            self._set_look(city="", city_lat=None, city_lon=None)
        else:
            self._set_look(city=r["name"], city_lat=r["lat"], city_lon=r["lon"])
        while self.city_res_lay.count():
            it = self.city_res_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.f_city_search.clear()
        self._flash("Город сохранён")
        self._refresh_city()

    # ---------- программы и игры ----------
    def _build_apps(self, lay):
        self._title(lay, "Программы и игры", "Всё, что помощник умеет запускать голосом: "
                                             "игры Steam, Epic Games и GOG, программы, ярлыки "
                                             "рабочего стола и скачанные папки.")
        row = QHBoxLayout()
        self.apps_count = label("", 15, QFont.DemiBold)
        row.addWidget(self.apps_count)
        row.addStretch(1)
        self.apps_scan = button("Обновить список", "ghost", 14)
        self.apps_scan.setFixedWidth(200)
        self.apps_scan.clicked.connect(self._rescan_apps)
        row.addWidget(self.apps_scan)
        lay.addLayout(row)
        lay.addSpacing(12)
        self.apps_filter = field("Поиск по названию…")
        self.apps_filter.textChanged.connect(lambda _t: self._fill_apps())
        lay.addWidget(self.apps_filter)
        lay.addSpacing(14)
        self.apps_list = QWidget()
        self.apps_lay = QVBoxLayout(self.apps_list)
        self.apps_lay.setContentsMargins(0, 0, 0, 0)
        self.apps_lay.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.apps_list)
        lay.addWidget(scroll, 1)
        lay.addSpacing(8)
        lay.addWidget(label("Скажите: «Сеньор, открой …» и название — по-русски, как слышится. "
                            "Если игру только что поставили, нажмите «Обновить список» или "
                            "скажите «обнови список программ».", 12, role="faint", wrap=True))
        self._apps_timer = QTimer(self)
        self._apps_timer.timeout.connect(self._apps_poll)

    def _fill_apps(self):
        while self.apps_lay.count():
            it = self.apps_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = sites.all_apps()
        self.apps_count.setText(f"Знаю {len(items)} программ и игр")
        q = self.apps_filter.text().strip().lower()
        shown = 0
        for name, src in items:
            if q and q not in name.lower():
                continue
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(4, 4, 4, 4)
            rl.addWidget(label(name, 14), 1)
            rl.addWidget(label(src, 12, role="faint"))
            self.apps_lay.addWidget(r)
            shown += 1
            if shown >= 400:
                break
        self.apps_lay.addStretch(1)

    def _rescan_apps(self):
        self.apps_scan.setEnabled(False)
        self.apps_scan.setText("Ищу…")
        sites.warm(force=True)
        self._apps_t0 = sites._apps_time
        self._apps_timer.start(700)

    def _apps_poll(self):
        if sites._apps_time != self._apps_t0:
            self._apps_timer.stop()
            self.apps_scan.setEnabled(True)
            self.apps_scan.setText("Обновить список")
            self._fill_apps()

    def _build_startup(self, lay):
        self._title(lay, "Запуск", "Когда и как открывается SenioreM.")
        self.t_autostart = self._toggle_row(lay, "Запускать вместе с Windows",
                                            "Помощник будет готов сразу после включения компьютера.",
                                            "autostart")
        lay.addStretch(1)

    def _build_account(self, lay):
        self._title(lay, "Аккаунт", "Логин, пароль и выход.")
        self._caption(lay, "Логин")
        self.acc_email = label("", 17)
        lay.addWidget(self.acc_email)
        lay.addSpacing(30)
        lay.addWidget(label("Сменить пароль", 17, QFont.DemiBold))
        lay.addSpacing(12)
        pw = QHBoxLayout()
        pw.setSpacing(18)
        self.p_old = field("текущий пароль", True)
        self.p_new = field("новый пароль", True)
        self.p_new2 = field("повторите новый", True)
        for f in (self.p_old, self.p_new, self.p_new2):
            pw.addWidget(f)
        lay.addLayout(pw)
        lay.addSpacing(12)
        self.p_msg = label("", 13, role="error", wrap=True)
        lay.addWidget(self.p_msg)
        lay.addSpacing(8)
        change = button("Сохранить пароль", "ghost", 14)
        change.setFixedWidth(200)
        change.clicked.connect(self._change_password)
        lay.addWidget(change, 0, Qt.AlignLeft)
        lay.addStretch(1)
        out = button("Выйти из аккаунта", "danger", 14)
        out.setFixedWidth(220)
        out.clicked.connect(self.logout_requested.emit)
        lay.addWidget(out, 0, Qt.AlignLeft)

    def _change_password(self):
        try:
            self.store.change_password(self.email, self.p_old.text(), self.p_new.text(),
                                       self.p_new2.text())
        except AuthError as e:
            set_role(self.p_msg, "error")
            self.p_msg.setText(str(e))
            return
        for f in (self.p_old, self.p_new, self.p_new2):
            f.clear()
        set_role(self.p_msg, "accent")
        self.p_msg.setText("Пароль изменён.")

    def _build_about(self, lay):
        row = QHBoxLayout()
        row.addWidget(LogoMark(110))
        row.addSpacing(18)
        col = QVBoxLayout()
        col.addStretch(1)
        col.addWidget(label("SenioreM", 40, QFont.Light, display=True))
        ver = self.cfg.get("version", "0.0.0")
        col.addWidget(label(f"Версия {ver}", 14, role="muted"))
        col.addStretch(1)
        row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(26)
        lay.addWidget(label("Голосовой помощник для Windows. Распознавание речи работает без "
                            "интернета, ваши данные и история хранятся только на этом компьютере. "
                            "Обновления проверяются при каждом запуске.", 15, role="muted",
                            wrap=True))
        lay.addSpacing(24)
        repo = self.cfg.get("update_repo") or ""
        if repo:
            b = button("Страница программы на GitHub", "ghost", 14, QFont.Normal)
            b.setFixedWidth(300)
            b.clicked.connect(lambda: webbrowser.open(f"https://github.com/{repo}"))
            lay.addWidget(b, 0, Qt.AlignLeft)
        lay.addStretch(1)

    # ---------- показ ----------
    def load(self, email, settings):
        self.email, self.settings = email, settings
        self._loading = True
        name = settings["name"]
        self.big_avatar.setText((name or email or "?")[:1].upper())
        self.who.setText(name or email)
        created = self.store.created(email)
        self.since.setText(("с нами с " + datetime.datetime.fromtimestamp(created).strftime("%d.%m.%Y"))
                           if created else email)
        self.f_name.setText(name)
        self.f_address.setText(settings["address"])
        self.f_wake.setText(settings["wake_reply"])
        ww = settings["wake_words"] or ""
        self.f_words.setText("" if ww.replace(" ", "") == "сеньор,сеньер,синьор" else ww)
        custom = settings.name not in NAME_PRESETS
        self.f_ai_name.setText(settings.name if custom else "")
        self._refresh_name()
        for k, b in self.speed_buttons.items():
            b.setChecked(k == (settings["voice_speed"] or "normal"))
        self.voice_status.setText("")
        self.t_speak.setChecked(bool(settings["speak_replies"]))
        self.t_chime.setChecked(bool(settings["chime"]))
        self.t_wake_reply.setChecked(bool(settings["speak_wake_reply"]))
        self.t_autostart.setChecked(bool(settings["autostart"]))
        for sec, b in self.follow_buttons.items():
            b.setChecked(sec == int(settings["followup_seconds"]))
        self.f_ya_key.setText(settings["yandex_key"] or "")
        self._refresh_voice()
        for sec, b in self.listen_buttons.items():
            b.setChecked(sec == int(settings["listen_seconds"] or 10))
        self.acc_email.setText(email)
        self.t_ai.setChecked(bool(settings["ai_enabled"]))
        self.f_api_url.setText(settings["ai_api_url"] or "")
        self.f_api_key.setText(settings["ai_api_key"] or "")
        self.f_api_model.setText(settings["ai_api_model"] or "")
        self._refresh_ai()
        self.full_history.set_items(settings["history"])
        self._loading = False
        self._refresh_preview()

    def show_section(self, key):
        self.nav_buttons[key].setChecked(True)
        switch_page(self.pages, self.page_widgets[key], 180)
        if key == "look":
            self._refresh_look()
        if key == "city":
            self._refresh_city()
        if key == "apps":
            self._fill_apps()
        if key == "history" and self.settings is not None:
            self.full_history.set_items(self.settings["history"])


# ================================================================== окно
class MainWindow(QWidget):
    def __init__(self, cfg, models=None):
        models = models or {}
        model = models.get("model")
        super().__init__()
        self.cfg = cfg
        self.setObjectName("root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.glass = T.APPEARANCE.get("background") == "glass"
        if self.glass:
            self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("SenioreM")
        icon = config.resource_path("assets/icon.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.store = AuthStore(config.data_dir())
        self.mailer = Mailer(cfg)
        self.speaker = Speaker(models.get("voice"))
        self.speaker.start()
        self.bridge = Bridge()
        self.bridge.mail_done.connect(self._mail_done)
        self.pending_email = ""
        self.email = ""
        self.settings = None
        self.greeted = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.by_email = bool(cfg.get("email_verification"))
        self.auth = AuthScreen(self, self.by_email)
        self.home = HomeScreen(self, cfg, self.speaker, model)
        self.profile = ProfileScreen(self, cfg, self.store, self.speaker)
        for w in (self.auth, self.home, self.profile):
            self.stack.addWidget(w)

        a = self.auth
        a.register.submit.clicked.connect(self._register)
        a.register.to_login.clicked.connect(lambda: self._go_auth(a.login))
        a.login.submit.clicked.connect(self._login)
        a.login.to_register.clicked.connect(lambda: self._go_auth(a.register))
        a.verify.submit.clicked.connect(self._verify)
        a.verify.resend.clicked.connect(self._resend)
        a.verify.back.clicked.connect(lambda: self._go_auth(a.register))
        self.home.profile_requested.connect(lambda: self.open_profile("address"))
        self.profile.back_requested.connect(self._back_home)
        self.profile.logout_requested.connect(self._logout)

        self.resend_timer = QTimer(self)
        self.resend_timer.timeout.connect(self._tick_resend)

        email = self.store.session_email()
        if email:
            self._enter(email)
        else:
            self._go_auth(a.login if self.store.has_users else a.register)

    # ---------- навигация ----------
    def _go_auth(self, form):
        switch_page(self.stack, self.auth)
        self.auth.show_form(form)
        QTimer.singleShot(0, lambda: (form.email.setFocus() if hasattr(form, "email")
                                      else form.code.focus(0)))

    def _enter(self, email):
        self.email = email
        self.settings = Settings(config.data_dir(), email)
        s = self.settings
        self.speaker.configure(s["voice_speed"], s["speak_replies"], s.cloud_voice)
        self.speaker.prefetch([s["wake_reply"]] if s["wake_reply"] else [])
        if not s["ai_auto_setup"]:            # ИИ включаем сразу, без похода в профиль
            s.set("ai_auto_setup", True)
            s.set("ai_enabled", True)
            if s["ai_mode"] != "api":
                s.set("ai_mode", ai.recommended_kind())
        mode = s["ai_mode"] or "smart"
        if os.environ.get("SENIOREM_NO_DOWNLOADS"):
            pass
        elif s["ai_enabled"] and mode != "api":
            if ai.local_ready(mode):
                threading.Thread(target=lambda: self._warm_ai(mode), daemon=True).start()
            else:
                ai.DOWNLOADS.start(mode)
        if not asr.RECOGNIZER.available and not os.environ.get("SENIOREM_NO_DOWNLOADS"):
            asr.DOWNLOADS.start()
        switch_page(self.stack, self.home)
        self.home.start(email, s)
        if not self.greeted:
            self.greeted = True
            who = s["name"] or s["address"]
            hello = greeting(datetime.datetime.now().hour)
            self.speaker.say(f"{hello}{', ' + who if who else ''}. Я на связи — "
                             f"скажите «{s.name}» и команду.")

    @staticmethod
    def _warm_ai(mode):
        try:
            ai.ENGINE.start_local(mode)
        except Exception:  # noqa: BLE001 — запустится при первом вопросе
            pass

    def open_profile(self, section="address"):
        if self.settings is None:
            return
        self.profile.load(self.email, self.settings)
        self.profile.show_section(section)
        switch_page(self.stack, self.profile)

    def _back_home(self):
        switch_page(self.stack, self.home)
        self.home.start(self.email, self.settings)

    def _logout(self):
        self.home.stop()
        self.speaker.interrupt()
        self.store.logout()
        self.settings = None
        f = self.auth.login
        f.pw.clear()
        self._go_auth(f)

    # ---------- регистрация ----------
    def _register(self):
        f = self.auth.register
        if not self.by_email:
            try:
                name = self.store.register(f.email.text(), f.pw.text(), f.pw2.text())
            except AuthError as e:
                f.show_error(str(e))
                return
            f.pw.clear()
            f.pw2.clear()
            self._enter(name)
            return
        try:
            code = self.store.start_registration(f.email.text(), f.pw.text(), f.pw2.text())
        except AuthError as e:
            f.show_error(str(e))
            return
        self.pending_email = self.store.normalize_email(f.email.text())
        self._deliver(code, f.submit)

    def _deliver(self, code, btn):
        email = self.pending_email
        test_mode = self.cfg.get("test_mode_show_code") or not self.mailer.configured
        if test_mode:
            self._show_verify(email, code)
            return
        btn.setEnabled(False)
        old = btn.text()
        btn.setText("Отправляю…")

        def work():
            err = ""
            try:
                self.mailer.send_code(email, code)
            except AuthError as e:
                err = str(e)
            except Exception as e:  # noqa: BLE001
                err = f"Не удалось отправить письмо: {e}"
            self.bridge.mail_done.emit(email, err)

        self._sending_btn = (btn, old)
        threading.Thread(target=work, daemon=True).start()

    def _mail_done(self, email, err):
        btn, old = self._sending_btn
        btn.setEnabled(True)
        btn.setText(old)
        if err:
            on_verify = self.auth.stack.currentWidget() is self.auth.verify
            (self.auth.verify if on_verify else self.auth.register).show_error(err)
            return
        self._show_verify(email, None)

    def _show_verify(self, email, test_code):
        v = self.auth.verify
        v.body.setText(f"Мы отправили 6 цифр на {email}.\nКод действует 10 минут.")
        if test_code:
            v.note.setText(f"Тестовый режим — почта отправителя не настроена.\nВаш код: {test_code}")
            v.note.show()
        else:
            v.note.hide()
        self.auth.show_form(v)
        v.code.clear()
        self._tick_resend()
        self.resend_timer.start(1000)

    def _tick_resend(self):
        wait = self.store.resend_wait(self.pending_email)
        b = self.auth.verify.resend
        if wait:
            b.setEnabled(False)
            b.setText(f"Отправить ещё раз · {wait} с")
        else:
            b.setEnabled(True)
            b.setText("Отправить ещё раз")
            self.resend_timer.stop()

    def _resend(self):
        v = self.auth.verify
        try:
            code = self.store.new_code(self.pending_email)
        except AuthError as e:
            v.show_error(str(e))
            return
        v.show_error("")
        self._deliver(code, v.resend)

    def _verify(self):
        v = self.auth.verify
        try:
            email = self.store.verify(self.pending_email, v.code.value())
        except AuthError as e:
            v.show_error(str(e))
            if "Неверный" in str(e):
                v.code.clear()
            return
        self.resend_timer.stop()
        r = self.auth.register
        r.pw.clear()
        r.pw2.clear()
        self._enter(email)

    # ---------- вход ----------
    def _login(self):
        f = self.auth.login
        try:
            email = self.store.login(f.email.text(), f.pw.text())
        except AuthError as e:
            f.show_error(str(e))
            return
        f.pw.clear()
        self._enter(email)

    # ---------- плавные появление и сворачивание ----------
    def _animate_opacity(self, start, end, ms, then=None):
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(ms)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if then:
            anim.finished.connect(then)
        self._win_anim = anim
        anim.start()

    def appear(self):
        self.setWindowOpacity(0.0)
        self.showFullScreen()
        if self.glass:
            T.enable_glass(self)
        self._animate_opacity(0.0, 1.0, 320)

    def restart(self):
        """Перезапуск программы (например, чтобы включить прозрачное окно)."""
        import subprocess
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--restart"]
        else:
            args = [sys.executable, os.path.abspath(sys.argv[0]), "--restart"]
        subprocess.Popen(args, close_fds=True)
        self.force_close()

    def smooth_minimize(self):
        self._animate_opacity(self.windowOpacity(), 0.0, 180, self.showMinimized)

    def smooth_restore(self):
        self.setWindowOpacity(0.0)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._animate_opacity(0.0, 1.0, 260)

    def changeEvent(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.WindowStateChange and not self.isMinimized() \
                and e.oldState() & Qt.WindowMinimized:
            self.setWindowOpacity(0.0)
            QTimer.singleShot(0, lambda: self._animate_opacity(0.0, 1.0, 260))
        super().changeEvent(e)

    def request_close(self):
        dlg = ConfirmDialog(self, "Закрыть SenioreM?",
                            "Помощник перестанет слушать команды, пока вы снова его не откроете.",
                            yes="Да, закрыть", no="Вернуться")
        if dlg.exec() == ConfirmDialog.Accepted:
            self.force_close()

    def force_close(self):
        ai.ENGINE.stop()
        self._close_ok = True
        self.close()

    def closeEvent(self, e):
        if not getattr(self, "_close_ok", False):
            e.ignore()
            QTimer.singleShot(0, self.request_close)
            return
        self.home.stop()
        self.speaker.shutdown()
        ai.ENGINE.stop()
        super().closeEvent(e)


# ================================================================== запуск
def _install_error_log():
    log = config.data_dir() / "error.log"

    def hook(t, v, tb):
        with open(log, "a", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(t, v, tb)) + "\n")
    sys.excepthook = hook


def run_selftest(out_path):
    """Проверка сборки без окна: модели, распознавание, голос. Используется в GitHub Actions."""
    import json
    import wave
    lines, ok = [], True

    def log(msg):
        lines.append(msg)

    try:
        import tts
        for mod in ("vosk", "sounddevice", "piper", "onnxruntime", "comtypes", "pycaw.pycaw",
                    "psutil", "PySide6.QtWidgets"):
            try:
                __import__(mod)
                log(f"OK import {mod}")
            except Exception as e:  # noqa: BLE001
                ok = False
                log(f"FAIL import {mod}: {e!r}")
        path = config.model_dir()
        if not config.model_ready(path):
            from splash import Loader
            Loader()._download_model()
            path = config.model_dir()
        from splash import load_model
        model = load_model(path)
        log(f"OK vosk model: {path}")
        if not tts.voice_ready():
            tts.download_voice()
        voice = tts.load_voice()
        log("OK piper voice loaded")
        wav = str(config.local_dir() / "selftest.wav")
        tts.synth_wav(voice, "Сеньор, громкость десять процентов.", wav)
        _ = sites  # модуль поиска программ подключён
        secs = tts.wav_seconds(wav)
        log(f"OK synth {secs:.2f}s")
        if secs < 0.5:
            ok = False
            log("FAIL synth too short")
        from vosk import KaldiRecognizer
        with wave.open(wav, "rb") as w:
            rec = KaldiRecognizer(model, w.getframerate())
            while True:
                data = w.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
        heard = json.loads(rec.FinalResult()).get("text", "")
        log(f"heard: {heard!r}")
        words = commands.tokens(heard)
        i = commands.find_wake(words)
        intent = commands.parse(" ".join(words[i + 1:]) if i >= 0 else heard)
        log(f"intent: {intent}")
        # живые данные из интернета
        for name, fn in (("weather", lambda: live.weather_phrase({"city": "Магадан"}, "now")),
                         ("tomorrow", lambda: live.weather_phrase({"city": "Магадан"}, "tomorrow")),
                         ("rate", lambda: live.rate_phrase("USD")),
                         ("search", lambda: live.quick_answer("столица Австралии")),
                         ("news", lambda: live.quick_answer("последние новости сегодня"))):
            try:
                log(f"live {name}: {fn()}")
            except Exception as e:  # noqa: BLE001
                log(f"WARN live {name}: {e!r}")
        # точное распознавание (Whisper) той же фразы
        import asr as _asr
        t0 = time.time()
        _asr.download()
        _asr.RECOGNIZER.load()
        log(f"OK whisper loaded {(time.time() - t0):.0f}s")
        with wave.open(wav, "rb") as w:
            pcm, rate = w.readframes(w.getnframes()), w.getframerate()
        t0 = time.time()
        wtext = _asr.RECOGNIZER.transcribe(pcm, rate)
        log(f"whisper ({(time.time() - t0):.1f}s): {wtext!r}")
        if not wtext:
            ok = False
            log("FAIL whisper empty")
        for speed in ("slow", "fast"):
            tts.synth_wav(voice, "Проверка скорости.", wav, speed)
        log("OK speeds")
        if os.environ.get("SENIOREM_SELFTEST_AI"):
            import time as _t
            import ai as _ai
            t0 = _t.time()
            _ai.download_local("fast")
            log(f"OK ai download {(_t.time() - t0):.0f}s")

            class _S(dict):
                name = "Сеньор"
            s = _S(address="", ai_mode="fast")
            t0 = _t.time()
            _ai.ENGINE.start_local("fast", timeout=300)
            log(f"OK ai server {(_t.time() - t0):.1f}s")
            t0 = _t.time()
            ans = _ai.ENGINE.ask("Привет! Какого цвета небо днём? Ответь одной фразой.", s)
            log(f"ai answer ({(_t.time() - t0):.1f}s): {ans}")
            try:
                ctx = live.build_context("Сколько сейчас градусов на улице и какой курс доллара?",
                                         {"city": "Магадан"})
                t0 = _t.time()
                ans2 = _ai.ENGINE.ask("Сколько сейчас градусов на улице и какой курс доллара?",
                                      s, ctx)
                log(f"ai live ({(_t.time() - t0):.1f}s): {ans2}")
            except Exception as e:  # noqa: BLE001
                log(f"WARN ai live: {e!r}")
            if not ans or len(ans) < 3:
                ok = False
                log("FAIL ai empty answer")
            _ai.ENGINE.stop()
    except Exception:  # noqa: BLE001
        ok = False
        log("FAIL " + traceback.format_exc())
    log("RESULT " + ("PASS" if ok else "FAIL"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os._exit(0 if ok else 1)


def run_uitest(out_dir):
    """Снимки экранов для проверки дизайна (запускается в сборке на GitHub)."""
    import tempfile
    os.environ["SENIOREM_NO_DOWNLOADS"] = "1"
    os.makedirs(out_dir, exist_ok=True)
    os.environ["APPDATA"] = tempfile.mkdtemp()
    app = QApplication(sys.argv)
    apply_app_theme(app)
    log = []

    def pump(ms=400):
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)

    def shot(widget, name):
        pump(500)
        widget.grab().save(os.path.join(out_dir, name + ".png"))
        log.append(name)

    try:
        splash = Splash()
        splash.show()
        splash._on_progress(0.62, "Загружаю распознавание речи")
        pump(900)
        shot(splash, "01-splash")
        splash.close()
        win = MainWindow(config.load_config(), {})
        win.resize(1920, 1080)
        win.show()
        shot(win, "02-register")
        win.store.register("tester", "secret1", "secret1")
        win._enter("tester")
        h = win.home
        h.settings.set("address", "господин")
        h.settings.add_history("громкость десять", "Готово, господин. Громкость 10 процентов.")
        h.settings.add_history("открой осу", "Запускаю osu!.")
        h.history.set_items(h.settings["history"])
        h._show_heard("Расскажи анекдот", False)
        h.reply.setText("Почему программисты путают Хэллоуин и Рождество? Потому что Oct 31 = Dec 25.")
        h.orb.state = "armed"
        h.orb.push_level(0.5)
        pump(2500)
        shot(win, "03-home-blue")
        for i, (acc, bg) in enumerate((("#34D399", "aurora"), ("#A78BFA", "glow"),
                                      ("#FB923C", "solid"))):
            T.set_appearance(app, accent=acc, background=bg,
                             widgets={"notes": True}, clock_style="analog" if i == 1 else "digital")
            h.apply_widgets()
            shot(win, f"04-home-{i}-{bg}")
        T.set_appearance(app, accent="#5B8CFF", background="aurora", clock_style="digital")
        h.apply_widgets()
        for sec in ("look", "city", "voice", "apps", "ai", "name", "wake"):
            win.open_profile(sec)
            shot(win, f"05-profile-{sec}")
        win.request_close = lambda: None
        log.append("OK")
    except Exception:  # noqa: BLE001
        log.append("FAIL " + traceback.format_exc())
    with open(os.path.join(out_dir, "uitest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    os._exit(0 if log and log[-1] == "OK" else 1)


def main():
    if "--uitest" in sys.argv:
        i = sys.argv.index("--uitest")
        run_uitest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "screens")
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        run_selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "selftest.txt")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    _install_error_log()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SenioreM.App")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("SenioreM")
    apply_app_theme(app)

    lock = QLockFile(str(config.data_dir() / "app.lock"))
    if not lock.tryLock(15000 if "--restart" in sys.argv else 100):
        QMessageBox.information(None, "SenioreM", "SenioreM уже запущен.")
        return 0

    cfg = config.load_config()
    holder = {}

    def open_main(models):
        win = MainWindow(cfg, models)
        holder["win"] = win
        win.appear()

    ai.AI.kill_stale()
    splash = Splash()
    splash.done.connect(open_main)
    splash.cancelled.connect(lambda: os._exit(0))  # мгновенно, даже если идёт загрузка
    splash.show_animated()
    splash.start()

    code = app.exec()
    lock.unlock()
    os._exit(code)  # не ждём фоновые потоки (озвучка, распознавание)


if __name__ == "__main__":
    sys.exit(main())
