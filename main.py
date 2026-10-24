"""SenioreM — голосовой помощник для Windows."""
import datetime
import math
import os
import sys
import threading
import traceback
import webbrowser

from PySide6.QtCore import QLockFile, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QIcon, QKeySequence,
                           QLinearGradient, QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QGridLayout, QHBoxLayout,
                               QLineEdit, QMessageBox, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import actions
import commands
import config
from auth import AuthError, AuthStore, Mailer
from splash import Splash
from settings import WAKE_REPLY_PRESETS, Settings, greeting, personalize, set_autostart
from theme import (ACCENT, ERROR, FAINT, LINE, TEXT, Backdrop, LogoMark, Toggle,
                   apply_app_theme, button, card, field, font, hline, label, set_role,
                   window_controls)
from voice import VOICES, Chime, Listener, Speaker


class Bridge(QObject):
    """Передаёт результаты из фоновых потоков в интерфейс."""
    mail_done = Signal(str, str)        # email, ошибка ('' если ок)
    action_done = Signal(str, str)      # ответ, действие окна
    volume = Signal(int)                # текущая громкость системы


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
        self.stack.setCurrentWidget(form)
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
            core = QColor(ERROR)
        elif self.state == "speaking":
            core = self._mix("#9DB8FF", "#FFFFFF", breathe * 0.6)
        else:
            core = self._mix("#323A4B", ACCENT, self._heat)

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
        ring = self._mix(LINE, ACCENT, self._heat)
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
    ("Программы", ["открой телеграм", "закрой браузер", "закрой окно"]),
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
        p.setBrush(QColor(LINE))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 6), 3, 3)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor("#3D6BFF"))
        g.setColorAt(1, QColor("#8FB0FF"))
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
        self.speaker.speaking.connect(self._on_speaking)
        self.arm_timer = QTimer(self)
        self.arm_timer.setSingleShot(True)
        self.arm_timer.timeout.connect(self._disarm)
        self._last_cmd = ""

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

        # ---- три колонки
        body = QHBoxLayout()
        body.setSpacing(28)
        root.addLayout(body, 1)

        left, ll = card((26, 24, 26, 24))
        left.setFixedWidth(340)
        self.hello = label("", 26, QFont.Light, display=True, wrap=True)
        ll.addWidget(self.hello)
        ll.addSpacing(4)
        self.today = label("", 13, role="muted")
        ll.addWidget(self.today)
        ll.addSpacing(22)
        ll.addWidget(hline())
        ll.addSpacing(18)
        hh = QHBoxLayout()
        hh.addWidget(label("ПОСЛЕДНИЕ КОМАНДЫ", 11, QFont.DemiBold, "accent", spacing=1.8))
        hh.addStretch(1)
        more = button("Вся история", "link", 12, QFont.Normal)
        more.clicked.connect(lambda: self.win.open_profile("history"))
        hh.addWidget(more)
        ll.addLayout(hh)
        ll.addSpacing(14)
        self.history = HistoryList(7)
        ll.addWidget(self.history)
        ll.addStretch(1)
        ll.addWidget(hline())
        ll.addSpacing(16)
        vh = QHBoxLayout()
        vh.addWidget(label("Громкость", 13, QFont.DemiBold))
        vh.addStretch(1)
        self.vol_lbl = label("—", 13, role="muted")
        vh.addWidget(self.vol_lbl)
        ll.addLayout(vh)
        ll.addSpacing(10)
        self.vol = VolumeMeter()
        ll.addWidget(self.vol)
        body.addWidget(left)

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
        self.input = field("Напишите команду и нажмите Enter…")
        self.input.setFont(font(15))
        self.input.setAlignment(Qt.AlignCenter)
        self.input.setFixedWidth(500)
        self.input.returnPressed.connect(self._typed)
        center.addWidget(self.input, 0, Qt.AlignHCenter)
        body.addLayout(center, 1)

        right, rl = card((26, 24, 26, 24))
        right.setFixedWidth(340)
        rl.addWidget(label("ЧТО МОЖНО СКАЗАТЬ", 11, QFont.DemiBold, "accent", spacing=1.8))
        rl.addSpacing(6)
        rl.addWidget(label("Начинайте с «Сеньор». Нажмите на пример, чтобы выполнить.",
                           12, role="muted", wrap=True))
        rl.addSpacing(16)
        for title, examples in TIPS:
            rl.addWidget(label(title, 13, QFont.DemiBold))
            rl.addSpacing(6)
            for ex in examples:
                b = button(f"«{ex}»", "link", 13, QFont.Normal)
                b.clicked.connect(lambda _=False, e=ex: self.execute(e))
                rl.addWidget(b, 0, Qt.AlignLeft)
            rl.addSpacing(12)
        rl.addStretch(1)
        body.addWidget(right)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._vol_timer = QTimer(self)
        self._vol_timer.timeout.connect(self._poll_volume)

    # ---------- жизненный цикл ----------
    def start(self, email, settings):
        self.settings = settings
        name = settings["name"] or ""
        self.avatar.setText((name or email or "?")[:1].upper())
        self.history.set_items(settings["history"])
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
            self.hello.setText(f"{hello},\n{who}" if who else f"{hello}!")
            self.today.setText(f"Сегодня {actions.WEEKDAYS[now.weekday()]}, "
                               f"{now.day} {actions.MONTHS[now.month - 1]}")

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
            self._set_state("idle")
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
        if not flag and self.armed:
            self.arm_timer.start(self._listen_ms())
        self._rest_state()

    def _listen_ms(self):
        try:
            return int(self.settings["listen_seconds"]) * 1000
        except (TypeError, ValueError):
            return 8000

    # ---------- речь ----------
    def _show_heard(self, text, faint):
        self.heard.setText(text)
        self.heard.setStyleSheet(f"color: {FAINT if faint else TEXT};")

    def _on_partial(self, text):
        if self.orb.state in ("idle", "armed") and text:
            self._show_heard(text, True)

    def _on_final(self, text):
        words = commands.tokens(text)
        i = commands.find_wake(words, self.settings.wake_words if self.settings else [])
        if i >= 0:
            rest = words[i + 1:]
            if rest:
                self._disarm(silent=True)
                self.execute(" ".join(rest))
            else:
                self._arm()
        elif self.armed:
            self._disarm(silent=True)
            self.execute(text)
        else:
            self._show_heard("", True)

    def _arm(self):
        self.armed = True
        s = self.settings
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
        self.armed = False
        self.arm_timer.stop()
        if not silent:
            self._rest_state()

    def _typed(self):
        text = self.input.text().strip()
        self.input.clear()
        if text:
            self.execute(text)

    # ---------- выполнение ----------
    def execute(self, text):
        intent = commands.parse(text)
        shown = commands.normalize(text)
        self._last_cmd = shown
        self._show_heard(shown[:1].upper() + shown[1:], False)
        if intent["action"] == "stop":
            self.speaker.interrupt()
            self.reply.setText("")
            self._rest_state()
            return
        self._set_state("busy")

        def work():
            reply, ui = actions.run(intent, self.cfg)
            self.bridge.action_done.emit(reply, ui)

        threading.Thread(target=work, daemon=True).start()

    def _on_action_done(self, reply, ui):
        if self.settings is not None:
            reply = personalize(reply, self.settings["address"])
            if self._last_cmd:
                self.settings.add_history(self._last_cmd, reply)
                self.history.set_items(self.settings["history"])
        self.reply.setText(reply)
        self._rest_state()
        if reply:
            self.speaker.say(reply)
        if "громк" in self._last_cmd or "звук" in self._last_cmd or "тише" in self._last_cmd \
                or "громче" in self._last_cmd:
            QTimer.singleShot(300, self._poll_volume)
        if ui == "minimize":
            QTimer.singleShot(300, self.win.showMinimized)
        elif ui == "restore":
            self.win.showFullScreen()
            self.win.raise_()
            self.win.activateWindow()
        elif ui == "quit":
            QTimer.singleShot(1800, self.win.close)


# ================================================================== профиль
class ProfileScreen(Backdrop):
    back_requested = Signal()
    logout_requested = Signal()

    SECTIONS = [
        ("address", "Обращение"),
        ("voice", "Голос"),
        ("wake", "Активация"),
        ("history", "История"),
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
        self.big_avatar.setStyleSheet(
            f"background: rgba(91,140,255,0.18); border: 1px solid rgba(91,140,255,0.5);"
            f"border-radius: 36px; color: {TEXT};")
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

    def _toggle_row(self, lay, title, sub, key):
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(label(title, 15, QFont.DemiBold))
        if sub:
            col.addWidget(label(sub, 13, role="muted", wrap=True))
        row.addLayout(col, 1)
        t = Toggle()
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
        if key in ("voice_id", "speak_replies"):
            self.speaker.configure(self.settings["voice_id"], self.settings["speak_replies"])
        if key == "autostart":
            if not set_autostart(bool(value)):
                self._flash("Автозапуск работает только в установленной программе")
                return
        self._flash()
        self._refresh_preview()

    _loading = False

    # ---------- разделы ----------
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
        listen = button("Прослушать", "ghost", 14)
        listen.setFixedWidth(170)
        listen.clicked.connect(lambda: self.speaker.say(self._preview_lines()[0] + " " +
                                                        self._preview_lines()[1], force=True))
        lay.addWidget(listen, 0, Qt.AlignLeft)
        lay.addStretch(1)

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
        self._title(lay, "Голос", "Каким голосом отвечает помощник. Нейроголоса звучат "
                                  "естественно и требуют интернета; без него включится голос Windows.")
        self.voice_buttons = {}
        group = QButtonGroup(self)
        for vid, (title, *_rest) in VOICES.items():
            row = QHBoxLayout()
            b = button(title, "ghost", 15, QFont.Normal)
            b.setCheckable(True)
            b.setMinimumWidth(360)
            b.clicked.connect(lambda _=False, v=vid: self._choose_voice(v))
            group.addButton(b)
            row.addWidget(b)
            play = button("▶  Послушать", "link", 13, QFont.Normal)
            play.clicked.connect(lambda _=False, v=vid: self._demo_voice(v))
            row.addSpacing(14)
            row.addWidget(play)
            row.addStretch(1)
            lay.addLayout(row)
            lay.addSpacing(10)
            self.voice_buttons[vid] = b
        lay.addSpacing(24)
        self.t_speak = self._toggle_row(lay, "Озвучивать ответы",
                                        "Если выключить, ответы будут только текстом на экране.",
                                        "speak_replies")
        lay.addStretch(1)

    def _choose_voice(self, vid):
        self._set("voice_id", vid)
        self._demo_voice(vid)

    def _demo_voice(self, vid):
        addr = self.settings["address"] if self.settings else ""
        self.speaker.interrupt()
        self.speaker.say(personalize("Здравствуйте. Я SenioreM, ваш голосовой помощник.", addr),
                         force=True, voice_id=vid)

    def _build_wake(self, lay):
        self._title(lay, "Активация", "Как вы обращаетесь к помощнику и как он даёт понять, "
                                      "что слушает.")
        self._caption(lay, "Слова-обращения (через запятую)")
        self.f_words = field("сеньор, сеньер, синьор")
        self.f_words.textEdited.connect(lambda v: self._set("wake_words", v))
        lay.addWidget(self.f_words)
        lay.addSpacing(28)
        self.t_chime = self._toggle_row(lay, "Мягкий звук при обращении",
                                        "Короткий сигнал, когда помощник вас услышал.", "chime")
        self.t_wake_reply = self._toggle_row(lay, "Отвечать голосом на обращение",
                                             "Например: «Слушаю вас» — текст задаётся в разделе "
                                             "«Обращение».", "speak_wake_reply")
        self._caption(lay, "Сколько секунд ждать команду после обращения")
        row = QHBoxLayout()
        row.setSpacing(10)
        group = QButtonGroup(self)
        self.listen_buttons = {}
        for sec in (5, 8, 12, 20):
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
        self.f_words.setText(settings["wake_words"])
        for vid, b in self.voice_buttons.items():
            b.setChecked(vid == settings["voice_id"])
        self.t_speak.setChecked(bool(settings["speak_replies"]))
        self.t_chime.setChecked(bool(settings["chime"]))
        self.t_wake_reply.setChecked(bool(settings["speak_wake_reply"]))
        self.t_autostart.setChecked(bool(settings["autostart"]))
        for sec, b in self.listen_buttons.items():
            b.setChecked(sec == int(settings["listen_seconds"] or 8))
        self.acc_email.setText(email)
        self.full_history.set_items(settings["history"])
        self._loading = False
        self._refresh_preview()

    def show_section(self, key):
        self.nav_buttons[key].setChecked(True)
        self.pages.setCurrentWidget(self.page_widgets[key])
        if key == "history" and self.settings is not None:
            self.full_history.set_items(self.settings["history"])


# ================================================================== окно
class MainWindow(QWidget):
    def __init__(self, cfg, model=None):
        super().__init__()
        self.cfg = cfg
        self.setObjectName("root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("SenioreM")
        icon = config.resource_path("assets/icon.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.store = AuthStore(config.data_dir())
        self.mailer = Mailer(cfg)
        self.speaker = Speaker(cfg.get("voice", {}))
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
        self.stack.setCurrentWidget(self.auth)
        self.auth.show_form(form)
        QTimer.singleShot(0, lambda: (form.email.setFocus() if hasattr(form, "email")
                                      else form.code.focus(0)))

    def _enter(self, email):
        self.email = email
        self.settings = Settings(config.data_dir(), email)
        s = self.settings
        self.speaker.configure(s["voice_id"], s["speak_replies"])
        self.speaker.prefetch([s["wake_reply"]] if s["wake_reply"] else [])
        self.stack.setCurrentWidget(self.home)
        self.home.start(email, s)
        if not self.greeted:
            self.greeted = True
            who = s["name"] or s["address"]
            hello = greeting(datetime.datetime.now().hour)
            self.speaker.say(f"{hello}{', ' + who if who else ''}. Я на связи — "
                             f"скажите «Сеньор» и команду.")

    def open_profile(self, section="address"):
        if self.settings is None:
            return
        self.profile.load(self.email, self.settings)
        self.profile.show_section(section)
        self.stack.setCurrentWidget(self.profile)

    def _back_home(self):
        self.stack.setCurrentWidget(self.home)
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

    def closeEvent(self, e):
        self.home.stop()
        self.speaker.shutdown()
        super().closeEvent(e)


# ================================================================== запуск
def _install_error_log():
    log = config.data_dir() / "error.log"

    def hook(t, v, tb):
        with open(log, "a", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(t, v, tb)) + "\n")
    sys.excepthook = hook


def main():
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
    if not lock.tryLock(100):
        QMessageBox.information(None, "SenioreM", "SenioreM уже запущен.")
        return 0

    cfg = config.load_config()
    holder = {}

    def open_main(model):
        win = MainWindow(cfg, model)
        holder["win"] = win
        win.showFullScreen()

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
