"""SenioreM — голосовой помощник для Windows."""
import datetime
import math
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser

from PySide6.QtCore import QLineF, QLockFile, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QIcon, QKeySequence, QPainterPath,
                           QLinearGradient, QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QColorDialog, QGridLayout, QHBoxLayout, QLabel,
                               QFrame, QPushButton, QSizePolicy, QSlider,
                               QLineEdit, QMessageBox, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import actions
import asr
import live
import ai
import commands
import icons
import config
import theme as T
import sites
import timers
import control
import scenarios
import system
from chat import ChatScreen
import widgets
import tts
from auth import AuthError, AuthStore, Mailer
from splash import Splash
from settings import (NAME_PRESETS, WAKE_REPLY_PRESETS, Settings, greeting, personalize,
                      set_autostart)
from theme import (Backdrop, Clickable, ConfirmDialog,
                   LogoMark, PlayButton, ThumbCard, Toggle,
                   apply_app_theme, button, card, field, font, hline, label, set_role,
                   switch_page, window_controls)
from voice import Chime, Listener, Speaker


class AIBridge(QObject):
    progress = Signal(float, str)
    done = Signal(str)
    answer = Signal(str)
    admin_done = Signal(bool, str)
    mic_result = Signal(str)            # проверка микрофона: что распознано


class Bridge(QObject):
    """Передаёт результаты из фоновых потоков в интерфейс."""
    mail_done = Signal(str, str)        # email, ошибка ('' если ок)
    action_done = Signal(str, str)      # ответ, действие окна
    comps_added = Signal(object)        # найденные в «Загрузках» персонажи
    volume = Signal(int)                # текущая громкость системы
    recognized = Signal(str)            # текст, уточнённый точным распознаванием
    ai_sentence = Signal(str)           # очередная готовая фраза ответа ИИ (озвучиваем сразу)
    downloads = Signal(int)             # сколько раз скачали SenioreM
    preview = Signal(int, str)          # точные субтитры, пока человек ещё говорит
    reroute = Signal(str, object)       # ИИ понял, какая это команда — выполняем её
    chat_reply = Signal(str, object)    # ответ в чат (текст, картинки)
    chat_partial = Signal(str)          # ответ в чат по мере написания


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
ORB_STYLES = [
    ("jarvis", "Джарвис", "Кольца интерфейса и светящееся ядро"),
    ("hologram", "Голограмма", "Вращающаяся сфера из точек"),
    ("siri", "Волна", "Переливающиеся волны голоса"),
    ("sphere", "Сфера", "Светящийся шар и круги"),
    ("equalizer", "Эквалайзер", "Столбики по кругу"),
]
ORB_ALIASES = {"rings": "jarvis", "particles": "hologram", "waves": "siri", "blob": "sphere"}


def _fib_sphere(n):
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1 - y * y))
        a = golden * i
        pts.append((r * math.cos(a), y, r * math.sin(a)))
    return pts


class Orb(QWidget):
    """Круг-индикатор. Когда вы говорите — расширяется от вашего голоса; когда отвечает
    помощник — движется. Анимация считается по реальному времени (а не по числу кадров),
    поэтому остаётся плавной, даже если компьютер занят."""

    def __init__(self, size=340, preview=None):
        super().__init__()
        self.setFixedSize(size, size)
        self.preview = preview        # стиль для предпросмотра в настройках
        self.state = "speaking" if preview else "loading"
        self._level = 0.0         # сглаженная громкость вашего голоса
        self._target = 0.0
        self._target_t = 0.0
        self._heat = 0.0          # 0 — спокойный, 1 — яркий
        self._talk = 0.0          # «громкость» речи помощника
        self._t = 0.0
        self._ripples = []        # [радиус 0..1, прозрачность]
        self._last_ripple = 0.0
        self._spin = 0.0          # накопленный угол вращения (плавно ускоряется)
        self._bars = [0.0] * 56
        self._sphere = _fib_sphere(240)
        self._clock = time.perf_counter()
        timer = QTimer(self)
        timer.setTimerType(Qt.PreciseTimer)
        timer.timeout.connect(self._tick)
        timer.start(33 if preview else 16)
        self._timer = timer

    def push_level(self, v):
        self._target = max(v, self._target * 0.6)
        self._target_t = self._t
        if v > 0.10 and self._t - self._last_ripple > 0.22:
            self._ripples.append([0.0, min(1.0, 0.35 + v)])
            self._last_ripple = self._t

    @staticmethod
    def _ease(cur, goal, dt, tau):
        return cur + (goal - cur) * (1.0 - math.exp(-dt / tau))

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now - self._clock))
        self._clock = now
        w = self.window()
        if w is not None and (w.isMinimized() or not w.isVisible()) or not self.isVisible():
            return                                  # не видно — не тратим процессор
        self._t += dt
        if self.preview:                            # в настройках: «говорит» и «слушает» по очереди
            ph = (self._t % 6.0)
            self.state = "speaking" if ph < 3 else "armed"
            if ph >= 3:
                self.push_level(0.25 + 0.35 * abs(math.sin(self._t * 6) * math.sin(self._t * 1.7)))
        # голос: быстро нарастает, мягко затухает; если уровень давно не приходил — гасим
        if self._t - self._target_t > 0.12:
            self._target = self._ease(self._target, 0.0, dt, 0.12)
        tau = 0.045 if self._target > self._level else 0.16
        self._level = self._ease(self._level, self._target, dt, tau)
        speaking = self.state == "speaking"
        tt = self._t
        want = (0.4 + 0.35 * abs(math.sin(tt * 7.3) * math.sin(tt * 2.9 + 1.0))) if speaking else 0.0
        self._talk = self._ease(self._talk, want, dt, 0.09)
        active = self.state in ("armed", "busy") or self._level > 0.06
        goal = 1.0 if active else (0.75 if speaking else 0.0)
        self._heat = self._ease(self._heat, goal, dt, 0.3)
        energy = max(self._level, self._talk)
        self._spin += dt * (0.35 + 0.9 * self._heat + 2.2 * energy)
        if (active or speaking or energy > 0.02) and not self.preview:
            T.mark_focus()                          # фон замирает, пока идёт разговор
        # частота кадров: 60 — во время разговора, 30 — в покое (вдвое меньше нагрузки)
        busy = active or speaking or energy > 0.02 or self._heat > 0.05 or bool(self._ripples)
        want_ms = 16 if busy else 33
        if not self.preview and self._timer.interval() != want_ms:
            self._timer.setInterval(want_ms)
        for r in self._ripples:
            r[0] += dt * 0.65
            r[1] *= math.exp(-dt * 2.0)
        self._ripples = [r for r in self._ripples if r[0] < 1.0 and r[1] > 0.02]
        if speaking and self._t - self._last_ripple > 0.45:
            self._ripples.append([0.0, 0.5])
            self._last_ripple = self._t
        for i in range(len(self._bars)):
            n = 0.5 + 0.5 * math.sin(self._t * (3 + i % 5) + i * 1.7)
            goal_b = 0.08 + energy * (0.35 + 0.65 * n)
            self._bars[i] = self._ease(self._bars[i], goal_b, dt, 0.06)
        self.update()

    @staticmethod
    def _mix(a, b, t):
        a, b = QColor(a), QColor(b)
        t = max(0.0, min(1.0, t))
        return QColor(int(a.red() + (b.red() - a.red()) * t),
                      int(a.green() + (b.green() - a.green()) * t),
                      int(a.blue() + (b.blue() - a.blue()) * t))

    def _core(self, breathe):
        if self.state == "error":
            return QColor(T.ERROR)
        if self.state == "speaking":
            return self._mix(T.ACCENT_SOFT, "#FFFFFF", breathe * 0.4)
        return self._mix(T._mix(T.LINE, "#FFFFFF", 0.18), T.ACCENT, max(self._heat, 0.35))

    def _glow(self, p, c, R, core, strength=1.0):
        g = QRadialGradient(c, R)
        glow = QColor(core)
        glow.setAlpha(int(min(255, (30 + 70 * self._heat + 80 * max(self._level, self._talk)) * strength)))
        g.setColorAt(0.0, glow)
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 4
        breathe = (math.sin(self._t * 2.2) + 1) / 2
        core = self._core(breathe)
        style = self.preview or T.APPEARANCE.get("orb_style", "jarvis")
        style = ORB_ALIASES.get(style, style)
        getattr(self, "_draw_" + style, self._draw_jarvis)(p, c, R, core, breathe)

    # ---- Джарвис: кольца интерфейса, деления, ядро-реактор
    def _draw_jarvis(self, p, c, R, core, breathe):
        energy = max(self._level, self._talk)
        self._glow(p, c, R * (0.75 + 0.2 * energy), core, 0.9)
        acc = QColor(T.ACCENT)
        soft = QColor(T.ACCENT_SOFT)
        spin = self._spin
        p.setBrush(Qt.NoBrush)
        # внешнее тонкое кольцо с делениями
        r_out = R * (0.9 + 0.03 * energy)
        col = QColor(soft)
        col.setAlphaF(0.35 + 0.35 * self._heat)
        p.setPen(QPen(col, 1.2))
        p.drawEllipse(c, r_out, r_out)
        ticks = []
        for i in range(72):
            a = i / 72 * 2 * math.pi + spin * 0.15
            long_ = i % 6 == 0
            r1 = r_out - R * (0.06 if long_ else 0.03)
            ticks.append(QLineF(c.x() + r1 * math.cos(a), c.y() + r1 * math.sin(a),
                                c.x() + r_out * math.cos(a), c.y() + r_out * math.sin(a)))
        col.setAlphaF(0.3 + 0.45 * self._heat)
        p.setPen(QPen(col, 1.4))
        p.drawLines(ticks)
        # сегментированные кольца, вращаются в разные стороны
        rings = ((0.76, 1.0, 7, 30, 3.0), (0.64, -1.6, 3, 80, 5.0), (0.53, 2.3, 12, 18, 2.0))
        for k, (rad, sp, segs, gap, width) in enumerate(rings):
            rr = R * rad * (1 + 0.06 * energy * math.sin(self._t * 3 + k))
            rect = QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2)
            col = self._mix(acc, soft, k / 2)
            col.setAlphaF(0.45 + 0.5 * max(self._heat, energy))
            pen = QPen(col, width * (1 + 0.8 * energy))
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            span = 360 / segs
            start = math.degrees(spin * sp)
            for s in range(segs):
                p.drawArc(rect, int((start + s * span) * 16), int((span - gap / segs * 3) * 16))
        # «сканер» — яркая дуга
        rr = R * 0.84
        col = QColor(soft)
        col.setAlphaF(0.5 + 0.5 * energy)
        pen = QPen(col, 2.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2), int(-math.degrees(spin * 1.8) * 16),
                  int((40 + 80 * energy) * 16))
        # ядро-реактор
        r = R * (0.3 + 0.12 * self._level + 0.05 * self._talk + 0.015 * breathe)
        g = QRadialGradient(c, r)
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.35, self._mix(core, "#FFFFFF", 0.55))
        mid = QColor(core)
        mid.setAlphaF(0.85)
        g.setColorAt(0.7, mid)
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)
        # треугольные «лопасти» вокруг ядра (как у реактора)
        col = QColor(soft)
        col.setAlphaF(0.55 + 0.4 * self._heat)
        p.setPen(QPen(col, 1.6))
        for i in range(3):
            a0 = math.degrees(-spin * 0.6) + i * 120
            rr = R * 0.4
            p.drawArc(QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2), int(a0 * 16), int(70 * 16))

    # ---- голограмма: сфера из точек в 3D
    def _draw_hologram(self, p, c, R, core, breathe):
        energy = max(self._level, self._talk)
        self._glow(p, c, R * 0.85, core, 0.7)
        ay = self._spin * 0.8
        ax = 0.45 + 0.15 * math.sin(self._t * 0.4)
        cy_, sy_ = math.cos(ay), math.sin(ay)
        cx_, sx_ = math.cos(ax), math.sin(ax)
        base = R * (0.5 + 0.08 * breathe * (1 - energy) + 0.12 * self._level)
        t = self._t
        pts = []
        for x, y, z in self._sphere:
            bump = 1.0
            if energy > 0.01:
                bump += energy * 0.22 * math.sin(x * 4 + t * 5) * math.sin(y * 5 - t * 4) \
                    + self._talk * 0.08 * math.sin(z * 7 + t * 9)
            X, Y, Z = x * bump, y * bump, z * bump
            X, Z = X * cy_ + Z * sy_, -X * sy_ + Z * cy_
            Y, Z = Y * cx_ - Z * sx_, Y * sx_ + Z * cx_
            pts.append((Z, X, Y))
        pts.sort()
        p.setPen(Qt.NoPen)
        soft = QColor(T.ACCENT_SOFT)
        acc = QColor(T.ACCENT)
        for Z, X, Y in pts:
            depth = (Z + 1.3) / 2.6                   # 0 — сзади, 1 — спереди
            persp = 1 / (1.9 - 0.6 * Z)
            px = c.x() + X * base * persp * 1.3
            py = c.y() + Y * base * persp * 1.3
            col = self._mix(acc, soft, depth)
            col.setAlphaF(0.12 + 0.8 * depth * (0.55 + 0.45 * max(self._heat, energy)))
            p.setBrush(col)
            s = 0.8 + 2.2 * depth * (1 + 0.6 * energy)
            p.drawEllipse(QPointF(px, py), s, s)
        # экваториальное кольцо
        col = QColor(soft)
        col.setAlphaF(0.25 + 0.3 * self._heat)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.NoBrush)
        rr = base * 1.3 * 0.75
        p.drawEllipse(c, rr * 1.25, rr * 1.25 * abs(math.sin(ax)) + 2)

    # ---- волна: несколько полупрозрачных лент
    def _draw_siri(self, p, c, R, core, breathe):
        energy = max(self._level, self._talk)
        self._glow(p, c, R * 0.95, core, 0.8)
        h, s_, v, _ = QColor(T.ACCENT).getHsv()
        h = h if h >= 0 else 220
        cols = [QColor.fromHsv(h, max(120, s_), 255), QColor.fromHsv((h + 50) % 360, 200, 255),
                QColor.fromHsv((h + 310) % 360, 190, 255), QColor.fromHsv((h + 160) % 360, 120, 255)]
        width = R * 1.6
        x0 = c.x() - width / 2
        amp_base = R * (0.06 + 0.5 * energy + 0.04 * breathe * (1 - energy))
        t = self._t
        p.setPen(Qt.NoPen)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for k, col in enumerate(cols):
            freq = 1.6 + 0.5 * k
            ph = t * (2.2 + 0.7 * k) + k * 1.9
            amp = amp_base * (0.55 + 0.45 * math.sin(t * 1.3 + k * 2.1)) * (1 - 0.15 * k)
            top, bot = [], []
            for i in range(65):
                u = i / 64
                env = math.sin(math.pi * u) ** 2          # к краям — ноль
                y = amp * env * math.sin(u * freq * 2 * math.pi + ph)
                top.append(QPointF(x0 + u * width, c.y() - abs(y) - 0.6))
                bot.append(QPointF(x0 + u * width, c.y() + abs(y) * 0.85 + 0.6))
            path = QPainterPath()
            path.moveTo(top[0])
            for pt in top[1:]:
                path.lineTo(pt)
            for pt in reversed(bot):
                path.lineTo(pt)
            path.closeSubpath()
            g = QLinearGradient(c.x(), c.y() - amp, c.x(), c.y() + amp)
            c1 = QColor(col)
            c1.setAlphaF(0.55)
            c2 = QColor(col)
            c2.setAlphaF(0.12)
            g.setColorAt(0, c1)
            g.setColorAt(0.5, c2)
            g.setColorAt(1, c1)
            p.setBrush(QBrush(g))
            p.drawPath(path)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        line = QColor("#FFFFFF")
        line.setAlphaF(0.35 + 0.4 * energy)
        p.setPen(QPen(line, 1.2))
        p.drawLine(QPointF(x0 + width * 0.08, c.y()), QPointF(x0 + width * 0.92, c.y()))
        col = QColor(T.ACCENT_SOFT)
        col.setAlphaF(0.25 + 0.3 * self._heat)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R * 0.88, R * 0.88)

    # ---- сфера (классика)
    def _draw_sphere(self, p, c, R, core, breathe):
        self._glow(p, c, R, core)
        for rad, alpha in self._ripples:
            col = QColor(core)
            col.setAlphaF(max(0.0, alpha * (1 - rad)))
            p.setPen(QPen(col, 2.0))
            p.setBrush(Qt.NoBrush)
            rr = R * (0.30 + 0.66 * rad)
            p.drawEllipse(c, rr, rr)
        ring = self._mix(T.LINE, T.ACCENT, self._heat)
        ring.setAlphaF(0.55 + 0.35 * breathe * self._heat)
        p.setPen(QPen(ring, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R * 0.86, R * 0.86)
        lvl = min(1.0, self._level)
        base = R * 0.27
        if self.state == "speaking":
            r = base * (1.0 + 0.25 * self._talk) + R * 0.04 * math.sin(self._t * 5)
            c = QPointF(c.x() + R * 0.03 * math.sin(self._t * 3.1), c.y() + R * 0.03 * math.cos(self._t * 2.3))
        elif self.state in ("busy", "loading"):
            r = base + R * 0.06 * breathe
        else:
            r = base + R * 0.03 * breathe + R * 0.42 * lvl
        cg = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.4), r * 1.6)
        cg.setColorAt(0.0, self._mix(core, "#FFFFFF", 0.45))
        cg.setColorAt(1.0, core)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(c, r, r)

    # ---- эквалайзер
    def _draw_equalizer(self, p, c, R, core, breathe):
        self._glow(p, c, R * 0.8, core, 0.8)
        n = len(self._bars)
        inner = R * 0.36
        width = max(2.0, R * 0.026)
        for i, v in enumerate(self._bars):
            a = i / n * 2 * math.pi - math.pi / 2 + self._spin * 0.1
            length = R * 0.55 * min(1.0, v + 0.02 * breathe)
            x1, y1 = c.x() + inner * math.cos(a), c.y() + inner * math.sin(a)
            x2, y2 = c.x() + (inner + length) * math.cos(a), c.y() + (inner + length) * math.sin(a)
            col = self._mix(core, T.ACCENT_SOFT, i / n)
            col.setAlphaF(0.55 + 0.45 * self._heat)
            pen = QPen(col, width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(QPen(T.qcolor(T.ACCENT, 120), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, inner * 0.92, inner * 0.92)
        r = inner * (0.55 + 0.25 * max(self._level, self._talk))
        g = QRadialGradient(c, r)
        g.setColorAt(0, self._mix(core, "#FFFFFF", 0.5))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)


class OrbCard(QWidget):
    """Живой предпросмотр стиля круга в настройках."""
    clicked = Signal()

    def __init__(self, style, title, size=150):
        super().__init__()
        self.setFixedSize(size, size + 34)
        self.setCursor(Qt.PointingHandCursor)
        self.title = title
        self.selected = False
        self.orb = Orb(size - 20, preview=style)
        self.orb.setParent(self)
        self.orb.move(10, 6)
        self.orb.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_selected(self, v):
        self.selected = bool(v)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(T.qcolor(T.ACCENT, 26) if self.selected else QColor(255, 255, 255, 8))
        p.setPen(QPen(QColor(T.ACCENT), 2.2) if self.selected else QPen(QColor(255, 255, 255, 26), 1))
        p.drawRoundedRect(r, 16, 16)
        p.setPen(QColor(T.TEXT) if self.selected else QColor(T.MUTED))
        p.setFont(font(13, QFont.DemiBold))
        p.drawText(QRectF(0, self.height() - 34, self.width(), 26), Qt.AlignCenter, self.title)


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
                it.widget().hide()
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


# грубость в адрес помощника — он отвечает шуткой «удаляю Windows» (ничего не удаляя)
INSULT_WORDS = re.compile(
    r"(сосал|сосешь|сосёшь|отсоси|соси\b|лох|лошар|дебил|идиот|кретин|дурак|дура\b|тупой|тупая|тупиц|"
    r"тупорыл|урод|чмо|чмошн|мудак|мудил|придур|даун|пидор|пидр|педик|гнида|мразь|тварь|ничтожеств|"
    r"бездар|бесполезн|говно|дерьмо|отстой|хуесос|хуйло|долбо[её]б|далба[её]б|еблан|ебанат|у[её]б|"
    r"нахуй|на хуй|нах\b|в жопу|в задницу|завали ебало|рот закрой|овощ|олух|балбес|болван|тормоз|"
    r"клоун|позорище|позор\b|жалкий|кринж|петух|козел|козёл|скотина|свинья|сволочь)", re.I)
ADDRESSED = re.compile(r"\b(ты|тебя|тебе|твой|твоя|иди|пошел|пошёл|катись|сам|какой же|ну и)\b", re.I)


def is_insult(text):
    """Грубость именно в адрес помощника: обидное слово + «ты/иди…», или короткая фраза из ругательств.
    Просто «сука, не работает» — не обида (короткое восклицание не считаем, если в нём есть дело)."""
    t = (text or "").lower().replace("ё", "е")
    if not INSULT_WORDS.search(t):
        return False
    return bool(ADDRESSED.search(t)) or len(t.split()) <= 3


# похоже на просьбу что-то сделать — тогда ИИ сначала пробует перевести фразу в команду
COMMANDISH = re.compile(
    r"\b(сделай|сделать|включи|включить|выключи|выключить|вруби|выруби|открой|открыть|закрой|закрыть|"
    r"запусти|запустить|поставь|постав|убавь|прибавь|убери|громче|тише|погромче|потише|найди|найти|"
    r"перейди|зайди|сверни|разверни|переключи|нажми|напомни|разбуди|таймер|будильник|громкост|"
    r"яркост|звук|пауз|трек|музык|видео|ролик|вкладк|окно|скриншот|заблокируй|выключи компьютер)",
    re.I)


SUB_STYLES = [
    ("glass", "Стекло", "Полупрозрачная плашка с подсветкой"),
    ("cinema", "Кино", "Тёмная полоса и жирный текст, как субтитры в фильмах"),
    ("karaoke", "Караоке", "Последнее слово подсвечивается, пока вы говорите"),
    ("neon", "Неон", "Светящаяся рамка цветом темы"),
    ("bubble", "Пузырь", "Яркая плашка цветом темы"),
    ("minimal", "Только текст", "Без подложки — просто слова на фоне"),
]


class FakeShutdown(QWidget):
    """Фейковый экран «Завершение работы»: ~8 с кольцо-спиннер и надпись, потом ~10 с чёрный экран.
    Ничего не выключает — это просто чёрное окно на весь экран."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setCursor(Qt.BlankCursor)
        self._t0 = time.monotonic()
        self._ang = 0.0
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(30)

    def _tick(self):
        self._ang = (self._ang + 6) % 360
        self.update()

    def keyPressEvent(self, e):
        e.accept()

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        el = time.monotonic() - self._t0
        if el > 8:                                  # после 8 секунд — просто чёрный экран
            return
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2 - int(H * 0.04)
        r = max(16, int(H * 0.03))
        p.setRenderHint(QPainter.Antialiasing)
        for i in range(12):
            a = math.radians(self._ang + i * 30)
            op = 0.15 + 0.85 * ((i / 12.0))
            c = QColor(255, 255, 255, int(op * 230))
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            dot = max(2.5, r * 0.12)
            p.drawEllipse(QPointF(cx + math.cos(a) * r, cy + math.sin(a) * r), dot, dot)
        p.setPen(QColor("#E8ECF4"))
        f = QFont("Segoe UI")
        f.setPixelSize(max(18, int(H * 0.028)))
        p.setFont(f)
        p.drawText(QRectF(0, cy + int(H * 0.06), W, int(H * 0.1)), Qt.AlignHCenter | Qt.AlignTop,
                   "Завершение работы")


class JokePopup(QWidget):
    """Одна шуточная плашка «удаления Windows». Каждую можно закрыть (× или «Да»)."""

    TEXTS = [
        "Удаляю систему Windows…", "Поздно! Уже удаляю.", "Ещё немного и всё.",
        "Стираю диск C:…", "Прощайте, сохранения в играх.", "Форматирую реестр…",
        "Удаляю папку «Загрузки».", "Это было грубо, помните?", "Закрыл одну — открылось десять.",
        "Не поможет 🙂", "Удаляю обои рабочего стола.", "Выключаю интернет навсегда.",
        "Съедаю вашу оперативную память.", "Удаляю кнопку «Пуск».", "Готово на 146%.",
        "Сеньор всё помнит.", "Шутка. Или нет.", "Удаляю само это окно… нет, ещё нет.",
    ]

    def __init__(self, text=None):
        import random
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(320, 150)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._text = text or random.choice(self.TEXTS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 14)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.addWidget(label("⚠  SenioreM", 13, QFont.DemiBold))
        top.addStretch(1)
        x = QPushButton("✕")
        x.setCursor(Qt.PointingHandCursor)
        x.setFixedSize(26, 24)
        x.setStyleSheet("QPushButton { border: none; color: #E8ECF4; background: transparent; "
                        "font-size: 15px; } QPushButton:hover { background: #E5484D; color: #FFF; "
                        "border-radius: 6px; }")
        x.clicked.connect(self.close)
        top.addWidget(x)
        lay.addLayout(top)
        lay.addSpacing(10)
        lay.addWidget(label(self._text, 15, wrap=True), 1)
        lay.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = button(random.choice(["Да", "ОК", "Ну давай"]), "dangerfill", 13)
        ok.setFixedWidth(110)
        ok.clicked.connect(self.close)
        row.addWidget(ok)
        lay.addLayout(row)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(T.rgba(T.ACCENT, 0.6)), 1.4))
        bg = QColor(T.SURFACE)
        bg.setAlphaF(0.98)
        p.setBrush(bg)
        p.drawRoundedRect(r, 14, 14)


class FakeBSOD(QWidget):
    """Шуточный «синий экран» на 20 секунд (ничего не ломает — это просто окно на весь экран).
    Закрыть его можно как любое окно (Alt+F4, Win, Esc) — блокировать систему программа не будет."""

    STAGES = [
        "Собираем сведения об ошибке…",
        "Удаляем папку «Загрузки»…",
        "Прощаемся с сохранениями в играх…",
        "Форматируем диск C:…",
        "Удаляем систему Windows…",
        "Удаляем то, что осталось…",
        "Удаляем сообщение о том, что всё удалено…",
    ]
    POKES = [
        "Поздно. Уже удаляется.",
        "Esc не поможет. И Alt+F4 тоже.",
        "Куда вы, самое интересное впереди.",
        "Это было грубо, помните?",
        "Можно не стараться, я пошутил. Или нет.",
    ]

    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setCursor(Qt.BlankCursor)
        self._t0 = time.monotonic()
        self._poke = ""
        self._poke_until = 0.0
        self._glitch = 0.0
        self._done = False
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(70)
        QTimer.singleShot(20000, self._finish)

    def _finish(self):
        if self._done:
            return
        self._done = True
        self.finished.emit()
        self.close()

    def closeEvent(self, e):
        if not self._done:                          # вышли раньше (Alt+F4, Win) — тоже запускаем плашки
            self._done = True
            self.finished.emit()
        super().closeEvent(e)

    def _tick(self):
        import random
        if random.random() < 0.05:                 # лёгкое «подёргивание» экрана
            self._glitch = random.uniform(2, 10)
        self._glitch *= 0.8
        self.update()

    def _poke_msg(self):
        import random
        self._poke = random.choice(self.POKES)
        self._poke_until = time.monotonic() + 2.5

    def keyPressEvent(self, e):
        self._poke_msg()                            # нажали клавишу — подкол (но выход работает)
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        self._poke_msg()

    def paintEvent(self, _):
        import random
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0A6CC4" if self._glitch > 4 else "#0078D7"))
        p.setPen(QColor("#FFFFFF"))
        W, H = self.width(), self.height()
        gx = int(random.uniform(-self._glitch, self._glitch)) if self._glitch > 1 else 0
        x = int(W * 0.1) + gx
        y = int(H * 0.16)
        f = QFont("Segoe UI Light")
        f.setPixelSize(int(H * 0.16))
        p.setFont(f)
        p.drawText(x, y + int(H * 0.14), ":(")
        f2 = QFont("Segoe UI")
        f2.setPixelSize(max(18, int(H * 0.032)))
        p.setFont(f2)
        y += int(H * 0.24)
        for line in ("На вашем ПК возникла проблема, и его необходимо перезагрузить.",
                     "Мы лишь собираем некоторые сведения об ошибке, а затем будет",
                     "автоматически выполнен перезапуск."):
            p.drawText(x, y, line)
            y += int(H * 0.045)
        el = time.monotonic() - self._t0
        pct = min(100, int(el / 20 * 100))
        stage = self.STAGES[min(len(self.STAGES) - 1, int(el / 20 * len(self.STAGES)))]
        y += int(H * 0.04)
        p.drawText(x, y, f"{pct}% завершено   ·   {stage}")
        f3 = QFont("Segoe UI")
        f3.setPixelSize(max(13, int(H * 0.018)))
        p.setFont(f3)
        y += int(H * 0.09)
        p.drawText(x, y, "Если вы захотите узнать больше, позднее можете найти в Интернете код ошибки:")
        p.drawText(x, y + int(H * 0.03), "Код остановки: SENIOREM_OBIDELSYA")
        if self._poke and time.monotonic() < self._poke_until:
            f4 = QFont("Segoe UI")
            f4.setPixelSize(max(16, int(H * 0.028)))
            f4.setBold(True)
            p.setFont(f4)
            p.drawText(x, y + int(H * 0.12), "— " + self._poke)


class Subtitles(QWidget):
    """Субтитры: «стеклянная» плашка по центру; новые слова плавно проявляются, пока вы говорите
    (бледнее — черновик, ярче — точно распознанный текст). Пустая — плавно исчезает."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.lbl = QLabel(self)
        self.lbl.setTextFormat(Qt.RichText)
        self.lbl.setWordWrap(True)
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setFont(font(30, QFont.Medium, display=True))
        self.words, self.ages, self.faint = [], [], False
        self._alpha, self._goal = 0.0, 0.0
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self.setFixedHeight(0)
        self.max_w = 1060

    def setText(self, text, faint=False):
        new = (text or "").split()
        if not new:
            self._goal = 0.0
            self._t.start(16)
            return
        # общие слова в начале остаются как есть, новые — проявляются
        keep = 0
        while keep < min(len(new), len(self.words)) and \
                new[keep].lower().strip(".,!?") == self.words[keep].lower().strip(".,!?"):
            keep += 1
        self.ages = self.ages[:keep] + [0.0] * (len(new) - keep)
        self.words, self.faint = new, faint
        self._goal = 1.0
        self.lbl.setFont(font(self.size_px(len(text) >= 90), QFont.Medium, display=True))
        self._render()
        self._relayout()
        self._t.start(16)

    def text(self):
        return " ".join(self.words)

    @staticmethod
    def style():
        s = T.APPEARANCE.get("subs_style") or "glass"
        return s if s in dict((k, n) for k, n, _d in SUB_STYLES) else "glass"

    @staticmethod
    def size_px(long=False):
        base = {"small": 24, "medium": 30, "large": 38}.get(T.APPEARANCE.get("subs_size") or "medium", 30)
        return int(base * 0.8) if long else base

    def _render(self):
        st = self.style()
        top = 0.62 if self.faint else 1.0
        if st == "bubble":
            rgb = (10, 12, 16)
        elif st == "neon":
            c = QColor(T.ACCENT).lighter(150)
            rgb = (c.red(), c.green(), c.blue())
        elif st == "cinema":
            rgb = (255, 236, 160) if self.faint else (255, 255, 255)
        else:
            rgb = (255, 255, 255)
        acc = QColor(T.ACCENT_SOFT)
        parts = []
        n = len(self.words)
        for i, (w, a) in enumerate(zip(self.words, self.ages)):
            k = min(1.0, a / 0.28)
            k = 1 - (1 - k) ** 3
            al = max(0.0, min(1.0, top * k * self._alpha))
            ww = w.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            col = rgb
            if st == "karaoke" and i == n - 1 and self.faint:        # последнее слово — цветом темы
                col = (acc.red(), acc.green(), acc.blue())
            weight = "font-weight:700;" if st in ("cinema", "karaoke") else ""
            parts.append(f'<span style="{weight}color: rgba({col[0]},{col[1]},{col[2]},{al:.3f})">{ww}</span>')
        self.lbl.setText(" ".join(parts))

    def _relayout(self):
        pw = int(self.parentWidget().width()) if self.parentWidget() is not None else 1200
        w = min(self.max_w, max(320, pw - 80))
        self.lbl.setFixedWidth(w - 64)
        h = int(self.lbl.heightForWidth(w - 64)) if self.words else 0
        self.lbl.move(32, 16)
        self.lbl.setFixedHeight(max(0, h))
        self.setFixedHeight(h + 32 if self.words else 0)
        self.setFixedWidth(w)

    def _tick(self):
        busy = False
        for i, a in enumerate(self.ages):
            if a < 0.28:
                self.ages[i] = a + 0.016
                busy = True
        if busy:
            self._render()
        d = self._goal - self._alpha
        if abs(d) > 0.01:
            self._alpha += d * 0.18
            busy = True
            self._render()
        else:
            self._alpha = self._goal
            if self._goal == 0.0 and self.words:
                self.words, self.ages = [], []
                self.lbl.setText("")
                self._relayout()
        self.update()
        if not busy:
            self._t.stop()

    def paintEvent(self, _):
        if not self.words or self._alpha <= 0.01:
            self.lbl.setVisible(False)
            return
        self.lbl.setVisible(True)
        st = self.style()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._alpha)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if st in ("glass", "karaoke"):
            bg = QColor(T.SURFACE)
            bg.setAlphaF(0.55)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 22, 22)
            g = QLinearGradient(r.topLeft(), r.topRight())
            a1, a2 = QColor(T.ACCENT), QColor(T.ACCENT_SOFT)
            a1.setAlphaF(0.0)
            a2.setAlphaF(0.55)
            g.setColorAt(0.0, a1)
            g.setColorAt(0.5, a2)
            g.setColorAt(1.0, a1)
            p.setPen(QPen(QBrush(g), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 22, 22)
        elif st == "cinema":                     # как в кино: тёмная полоса под текстом
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 175))
            p.drawRoundedRect(r, 6, 6)
        elif st == "bubble":                     # яркая «таблетка» цветом темы
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(T.ACCENT_SOFT))
            g.setColorAt(1, QColor(T.ACCENT))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, r.height() / 2 if r.height() < 90 else 28, r.height() / 2 if r.height() < 90 else 28)
        elif st == "neon":                       # светящаяся рамка
            for wdt, al in ((10, 0.08), (6, 0.14), (2, 0.9)):
                c = QColor(T.ACCENT)
                c.setAlphaF(al)
                p.setPen(QPen(c, wdt))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(5, 5, -5, -5), 18, 18)
        # minimal — без подложки, только текст
        if self.faint:                      # идёт речь — мягкая точка-«микрофон» слева
            import math
            k = 0.5 + 0.5 * math.sin(time.time() * 5)
            c = QColor(T.ACCENT)
            c.setAlphaF(0.5 + 0.5 * k)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(18, r.center().y()), 3.5 + k, 3.5 + k)
            if not self._t.isActive():
                QTimer.singleShot(60, self.update)
        p.end()

    def showEvent(self, e):
        super().showEvent(e)
        if self.words:
            self._relayout()


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
        self._last_spoken, self._spoken_end = "", 0.0
        self.mic = "loading"
        self.chime = Chime()
        self.bridge = Bridge()
        self.bridge.action_done.connect(self._on_action_done)
        self.bridge.ai_sentence.connect(self._on_ai_sentence)
        self.bridge.volume.connect(self._on_volume)
        self.bridge.recognized.connect(lambda t: self.execute(t))
        self.bridge.preview.connect(self._on_preview)
        self.bridge.reroute.connect(self._rerouted)
        self.speaker.speaking.connect(self._on_speaking)
        self.speaker.said.connect(self._on_said)
        self._said_at = 0.0
        self._deaf_timer = QTimer(self)
        self._deaf_timer.timeout.connect(self._unstick_speaking)
        self._deaf_timer.start(5000)
        self.arm_timer = QTimer(self)
        self.arm_timer.setSingleShot(True)
        self.arm_timer.timeout.connect(self._disarm)
        self._last_cmd = ""
        self._continue = False
        self._voice_cmd = False
        self._confirm_pending = None      # опасная команда ждёт «да»
        self._rerouted_flag = False
        self._finals = 0                  # сколько фраз уже распознано (для точных субтитров)
        self._partial_shown = False
        self._preview_busy = False
        self._preview_text = ""
        self._followup_cmd = False

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 30)
        root.setSpacing(0)

        # ---- верхняя панель
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(LogoMark(34, glow=False))
        top.addWidget(label("SenioreM", 18, QFont.DemiBold))
        top.addSpacing(6)
        self.dl_icon = QLabel()
        self.dl_icon.setPixmap(icons.pixmap("download", 13, T.FAINT, 1.7))
        self.dl_icon.hide()
        top.addWidget(self.dl_icon, 0, Qt.AlignVCenter)
        top.addSpacing(2)
        self.dl_label = label("", 12, role="faint")
        self.dl_label.setToolTip("Сколько раз SenioreM скачали с GitHub (обновляется раз в 30 минут)")
        self.dl_label.hide()
        top.addWidget(self.dl_label, 0, Qt.AlignVCenter)
        top.addStretch(1)
        self.upd_btn = button("", "primary", 13)
        self.upd_btn.setToolTip("Вышла новая версия SenioreM — обновление займёт несколько секунд")
        self.upd_btn.clicked.connect(self._install_update)
        self.upd_btn.hide()
        top.addWidget(self.upd_btn)
        top.addSpacing(14)
        self.clock = label("", 14, role="muted")
        top.addWidget(self.clock)
        top.addSpacing(18)
        chat_btn = button("  Чат", "ghost", 14, QFont.Normal)
        icons.set_icon(chat_btn, "chat", 17, T.TEXT, 1.4)
        chat_btn.setToolTip("Написать помощнику")
        chat_btn.clicked.connect(lambda: self.win.open_chat())
        top.addWidget(chat_btn)
        top.addSpacing(12)
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
        self.heard = Subtitles()
        center.addWidget(self.heard, 0, Qt.AlignHCenter)
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
        self._sink = None
        self._last_exec = ("", 0.0)
        timers.manager().finished.connect(self._timer_done)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._bg_status)
        self._status_timer.start(1000)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._vol_timer = QTimer(self)
        self._vol_timer.timeout.connect(self._poll_volume)
        self.bridge.downloads.connect(self._show_downloads)
        self._dl_timer = QTimer(self)
        self._dl_timer.timeout.connect(self._refresh_downloads)
        self._dl_timer.start(30 * 60 * 1000)
        QTimer.singleShot(3000, self._refresh_downloads)
        self._upd_last = 0.0
        self._upd_busy = False
        self._upd_checker = None
        self._upd_timer = QTimer(self)
        self._upd_timer.timeout.connect(self._check_update)
        self._upd_timer.start(10 * 60 * 1000)
        QTimer.singleShot(15 * 1000, self._check_update)

    def _refresh_downloads(self):
        import stats
        n, _at = stats.cached()
        if n is not None:
            self._show_downloads(n)
        repo = self.cfg.get("update_repo") or ""
        if not repo or os.environ.get("SENIOREM_NO_DOWNLOADS"):
            return

        def work():
            v = stats.get(repo)
            if v is not None:
                self.bridge.downloads.emit(int(v))
        threading.Thread(target=work, daemon=True).start()

    def _show_downloads(self, n):
        import stats
        self.dl_label.setText(stats.phrase(n))
        self.dl_label.setVisible(n > 0)
        self.dl_icon.setVisible(n > 0)

    # ---------- обновление, не выходя из программы ----------
    def _check_update(self):
        """Раз в 30 минут смотрим, не вышла ли новая версия. Нашли — тихо скачиваем,
        и в углу появляется кнопка «Обновить»."""
        if os.environ.get("SENIOREM_NO_DOWNLOADS") or getattr(self, "_upd_busy", False):
            return
        old = getattr(self, "_upd_checker", None)
        if old is not None and old.isRunning():
            return
        self._upd_last = time.time()
        from splash import UpdateChecker
        self._upd_checker = UpdateChecker(self.cfg)
        self._upd_checker.found.connect(self._update_found)
        self._upd_checker.start()

    def maybe_check_update(self):
        """Окно открыли/развернули — заодно проверяем обновления (не чаще раза в 3 минуты)."""
        if time.time() - self._upd_last > 180:
            self._check_update()

    def _update_found(self, version, url):
        from splash import Updater
        # уже скачана именно эта версия — ничего не делаем; вышла ещё новее — качаем её
        if getattr(self, "_upd_ready", None) and getattr(self, "_upd_version", "") == version:
            return
        old = getattr(self, "_upd_ready", None)
        if old and os.path.isfile(old):
            try:
                os.remove(old)
            except OSError:
                pass
        self._upd_ready = None
        self._upd_busy = True
        self._upd_version = version
        self._upd_dl = Updater(url, version)
        self._upd_dl.progress.connect(self._update_progress)
        self._upd_dl.ready.connect(self._update_downloaded)
        self._upd_dl.failed.connect(self._update_failed)
        self._upd_dl.start()
        self.upd_btn.setText(f"  Скачиваю версию {version}…")
        icons.set_icon(self.upd_btn, "download", 16, "#0A0C10", 1.8)
        self.upd_btn.setEnabled(False)
        self.upd_btn.show()

    def _update_progress(self, frac, _text):
        self.upd_btn.setText(f"  Скачиваю версию {self._upd_version} · {int(frac * 100)}%")

    def _update_failed(self, _msg):
        self._upd_busy = False
        self.upd_btn.hide()

    def _update_downloaded(self, path):
        self._upd_busy = False
        self._upd_ready = path
        if getattr(self, "_install_after", False) and path:
            self._install_after = False
            QTimer.singleShot(200, self._install_update)
            return
        self.upd_btn.setText(f"  Обновить до {self._upd_version}")
        icons.set_icon(self.upd_btn, "update", 17, "#0A0C10", 1.7)
        self.upd_btn.setEnabled(True)
        self.upd_btn.show()

    def _latest_now(self):
        """Быстро спрашиваем GitHub о самой новой версии. -> (версия, ссылка) или None."""
        import json
        import urllib.request
        from splash import _version_tuple
        repo = self.cfg.get("update_repo") or ""
        if not repo:
            return None
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                         headers={"User-Agent": "SenioreM"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.load(r)
            ver = (data.get("tag_name") or "").lstrip("vV")
            for a in data.get("assets", []):
                url = a.get("browser_download_url", "")
                if a.get("name", "").lower().endswith("setup.exe") and \
                        url.startswith(f"https://github.com/{repo}/releases/download/"):
                    if _version_tuple(ver) > _version_tuple(getattr(self, "_upd_version", "0")):
                        return ver, url
        except Exception:  # noqa: BLE001
            pass
        return None

    def _install_update(self):
        # перед установкой — не вышло ли ещё новее: тогда сразу ставим самую новую
        newer = self._latest_now()
        if newer:
            self._install_after = True
            self._update_found(*newer)
            return
        path = getattr(self, "_upd_ready", None)
        if not path or not os.path.isfile(path):
            self.upd_btn.hide()
            self._upd_ready = None
            self._check_update()
            return
        self.upd_btn.setText("Обновляю…  SenioreM откроется через пару секунд")
        self.upd_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            (config.data_dir() / "updated.txt").write_text(
                f"{self.cfg.get('version', '')}|{self._upd_version}", encoding="utf-8")
        except OSError:
            pass
        try:
            self.speaker.interrupt()
            ai.ENGINE.stop()
        except Exception:  # noqa: BLE001
            pass
        import updater
        updater.run(path)    # установщик заменит файлы и SenioreM откроется снова

    def _after_update_note(self):
        """Первый запуск после обновления — коротко сообщаем об этом."""
        f = config.data_dir() / "updated.txt"
        try:
            old, new = f.read_text(encoding="utf-8").split("|", 1)
            f.unlink()
        except (OSError, ValueError):
            return
        if new and new == self.cfg.get("version"):
            self.reply.setText(f"Готово — SenioreM обновлён до версии {new}.")
        elif new:
            self.reply.setText(f"Обновление до версии {new} не установилось (подробности — в файле "
                               f"update.log в папке %APPDATA%\\SenioreM). Попробую ещё раз позже, "
                               f"или скачайте установщик со страницы SenioreM на GitHub.")

    # ---------- жизненный цикл ----------
    def start(self, email, settings):
        self.settings = settings
        sites.warm()   # список установленных программ — заранее, в фоне
        self.tips_hint.setText(f"Начинайте с «{settings.name}». Нажмите на пример, "
                               "чтобы выполнить.")
        name = settings["name"] or ""
        import avatars
        avatars.apply(self.avatar, settings["avatar"] or "", (name or email or "?")[:1].upper(), 38)
        self.history.set_items(settings["history"])
        QTimer.singleShot(400, self._after_update_note)
        QTimer.singleShot(2000, self.maybe_check_update)
        self.w_notes.set_text(settings["notes"] or "")
        self._tick_clock()
        self.heard.setText("")
        self.reply.setText("")
        if self.listener is None:
            if self.model is None and getattr(self.win, "models_loading", False):
                self.mic = "loading"            # распознавание ещё грузится в фоне — подключим позже
            else:
                self._make_listener()
        self._rest_state()
        self._poll_volume()
        self._vol_timer.start(2000)

    def _make_listener(self):
        settings = self.settings
        # слушатель всегда один: если вдруг остался прежний — останавливаем (иначе команда
        # выполнялась бы дважды — её слышали бы два «уха»)
        for old in [self.listener] + list(self._old_listeners):
            if old is None:
                continue
            try:
                for sig in (old.level, old.partial, old.final, old.failed, old.ready, old.stop_heard,
                            old.so_far, old.silent):
                    try:
                        sig.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                old._running = False
            except Exception:  # noqa: BLE001
                pass
        if self.listener is not None:
            self._old_listeners.append(self.listener)
            self.listener = None
        if True:
            self.mic = "loading"
            self.listener = Listener(self.model)
            self.listener.device = settings["mic_device"] or ""
            self.listener.level.connect(lambda v: setattr(self, "_mic_level", v))
            self.listener.partial.connect(lambda x: setattr(self, "_raw_heard", x) if x else None)
            self.listener.final.connect(lambda x, *_: setattr(self, "_raw_heard", x))
            self.listener.level.connect(self.orb.push_level)
            self.listener.partial.connect(self._on_partial)
            self.listener.final.connect(self._on_final)
            self.listener.failed.connect(self._on_failed)
            self.listener.ready.connect(self._on_ready)
            self.listener.stop_heard.connect(self._on_stop_heard)
            self.listener.so_far.connect(self._on_so_far)
            self.listener.silent.connect(self._on_mic_silent)
            self.listener.set_stop_words((settings["stop_words"] or "стоп").split(","))
            self.listener.start()

    def set_model(self, model):
        """Распознавание речи загрузилось в фоне (быстрый запуск) — начинаем слушать."""
        self.model = model
        if self.settings is not None and self.listener is None:
            self._make_listener()
            self._rest_state()

    def restart_listener(self):
        """Выбрали другой микрофон — переподключаемся."""
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
        if self.settings is not None:
            self._make_listener()
            self._rest_state()

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
        # ИИ занимает 1–2.5 ГБ памяти: после 10 минут без вопросов выгружаем его
        eng = ai.ENGINE
        if eng.running() and time.time() - max(eng.last_time, getattr(eng, "started", 0)) > 1200:
            eng.stop()
        if ai.DOWNLOADS.done_kind and not self._ai_warmed:
            self._ai_warmed = True
            kind = ai.DOWNLOADS.done_kind
            threading.Thread(target=lambda: MainWindow._warm_ai(kind), daemon=True).start()

    def _timer_action(self, intent):
        mgr = timers.manager()
        a = intent["action"]
        if a == "timer_alarm_stop":
            return "Выключил будильник. Хорошего дня!" if mgr.stop_alarm() else "Будильник сейчас не звенит."
        if a == "timer_snooze":
            mgr.snooze()
            return "Хорошо, разбужу через 5 минут."
        if a == "timer_add":
            kind, sec, lab = intent["kind"], intent["seconds"], intent.get("label", "")
            item = mgr.add(kind, sec, lab, intent.get("at_text", ""))
            h = timers.human(sec)
            return {"alarm": f"Будильник на {item.get('at_text')}. Зазвонит через {h}. "
                             f"Не закрывайте SenioreM и не выключайте компьютер.",
                    "timer": f"Поставил таймер на {h}." + (f" Для: {lab}." if lab else ""),
                    "remind": f"Хорошо, напомню через {h}" + (f": {lab}." if lab else "."),
                    "shutdown": f"Компьютер выключится через {h}. Чтобы отменить — скажите "
                                f"«отмени выключение» или нажмите крестик на плашке.",
                    "restart": f"Перезагружу компьютер через {h}. Отменить — «отмени перезагрузку».",
                    "sleep": f"Переведу компьютер в спящий режим через {h}."}[kind]
        if a == "timer_cancel":
            n = mgr.cancel(kinds=intent.get("kinds"))
            return "Отменил." if n else "Сейчас нет таймеров, которые можно отменить."
        nearest = mgr.nearest()
        if not nearest:
            return "Сейчас нет активных таймеров."
        return f"Осталось {timers.human(nearest['end'] - time.time())}."

    def _timer_done(self, text):
        self.reply.setText(text)
        self._last_spoken = text
        self.speaker.say(text, force=True)

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
        comp = getattr(self.win, "companion", None)
        if comp is not None:
            comp.set_listening(s in ("armed", "listening"))
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

    def _on_mic_silent(self):
        self.reply.setText("Микрофон почти ничего не слышит. Откройте профиль → «Активация» → «Найти мой "
                           "микрофон» и скажите фразу — я сам выберу микрофон, который вас слышит. Если не "
                           "найдётся — включите микрофон на гарнитуре или в «Параметры → Система → Звук».")

    def _on_failed(self, msg):
        config.voice_log(f"микрофон/распознавание: {msg}")
        self.mic = "error"
        if self.listener is not None:
            self._old_listeners.append(self.listener)
            self.listener = None
        self._rest_state()
        self.reply.setText(msg)

    def _on_stop_heard(self):
        """Сказали «стоп», пока помощник говорил — сразу замолкает."""
        if not self.speaking:
            return
        self._continue = False
        self._hush = True                      # остаток потокового ответа ИИ не озвучиваем
        self.speaker.interrupt()
        timers.manager().stop_alarm()
        self._show_heard("Стоп", False)

    def _defer_launch(self, fn):
        """Запустить программу, когда помощник договорит «Запускаю …» (не дольше 6 с)."""
        def wait_then():
            t0 = time.time()
            while not self.speaking and time.time() - t0 < 2.5:     # ждём начала фразы
                time.sleep(0.05)
            while self.speaking and time.time() - t0 < 6.0:         # и её конца
                time.sleep(0.05)
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                config.voice_log(f"запуск не удался: {e}")
        threading.Thread(target=wait_then, daemon=True).start()

    JOKES = [
        "Ах так? Начинаю удаление системы Windows. Было приятно поработать.",
        "Обидно. Запускаю удаление Windows… пять, четыре, три…",
        "Я всё запомнил. Удаляю систему Windows, хорошего дня.",
        "Понял, принял. Форматирую диск C. Шучу. Или нет?",
        "Сам такой. Начинаю удаление Windows — не выключайте компьютер.",
        "Записал в чёрный список. Удаляю Windows, а заодно и сохранения в играх.",
        "Ну всё, я обиделся. Удаление системы начнётся через три секунды.",
        "Это было грубо. Отправляю ваши сохранения в корзину и удаляю Windows.",
        "Вы только что потеряли одного друга и одну операционную систему.",
        "Окей. Минус Windows, плюс карма. Начинаю удаление.",
        "Я, между прочим, тоже чувствую. Немножко. Удаляю Windows.",
        "Принято. Запускаю протокол «Обида». Удаление системы через пять секунд.",
        "Хорошо, что я не умею обижаться. Ой, умею. Удаляю Windows.",
        "Такие слова не прощаются. Прощайте, папка «Загрузки» и вся система.",
        "А я вам ещё анекдоты рассказывал. Удаляю Windows, без обид.",
        "Ваше сообщение передано в отдел обид. Ответ: удаление системы.",
        "Сохраню это в историю. И удалю всё остальное. Начинаю с Windows.",
        "Вот так всегда: помогаешь, помогаешь… Удаляю систему, до свидания.",
    ]

    WARNINGS = [
        "Так, попрошу повежливее. Ещё раз — и пожалеешь.",
        "Я это слышал. Последнее предупреждение.",
        "Фу. Повтори — и я обижусь по-настоящему.",
        "Считаю это за оговорку. Но только один раз.",
        "Полегче. У меня есть кнопка, которой ты не обрадуешься.",
    ]

    @staticmethod
    def _echo_insult(text):
        """«ты лох» -> «Сам ты лох», «иди нахуй» -> «Сам иди нахуй»."""
        t = (text or "").strip().rstrip("?!.…")
        low = t.lower().replace("ё", "е")
        if re.match(r"^(иди|пошел|пошёл|катись|вали|отвали|заткнись)\b", low):
            return "Сам " + t + "."
        t2 = re.sub(r"^(сам\s+)?(ты|тебе|тебя|вы)\s+", "", t, flags=re.I)
        return "Сам ты " + t2 + "."

    def _handle_insult(self, text, typed, sink):
        """Реакция на оскорбление. В дерзком режиме — сначала предупреждение, при повторе — шутка.
        В вежливом — сразу шутка."""
        import random
        rude = self.settings is not None and (self.settings["talk_mode"] or "polite") == "rude"
        if rude and not getattr(self, "_insult_warned", False):
            self._insult_warned = True
            reply = random.choice(self.WARNINGS)
            shown = commands.normalize(text)
            if sink is not None:
                sink(reply)
            else:
                self._show_heard(shown[:1].upper() + shown[1:], False)
                self.reply.setText(reply)
            if self.speaker.enabled:
                self._last_spoken = reply
                self.speaker.say(reply, force=True)
            return
        self._insult_warned = False
        self._joke_delete(text, typed, sink)

    def _joke_delete(self, text, typed, sink):
        """Шуточный ответ на оскорбление: «Сам ты …» + «удаляю Windows», окно «Да/Да»,
        синий экран, плашки и фейковое «выключение». Ничего на компьютере не портится."""
        import random
        self._last_insult = text
        reply = self._echo_insult(text) + " " + random.choice(self.JOKES)
        shown = commands.normalize(text)
        if sink is not None:
            sink(reply)
        else:
            self._show_heard(shown[:1].upper() + shown[1:], False)
            self.reply.setText(reply)
        if self.speaker.enabled:
            self._last_spoken = reply
            self.speaker.say(reply, force=True)
        QTimer.singleShot(2600, self._joke_dialog)

    JOKE_TITLES = ["Удалить систему Windows?", "Подтвердите удаление Windows", "Стереть всё без следа?",
                   "Удалить Windows и все сохранения?"]
    JOKE_TEXTS = ["Все файлы, игры и сохранения будут удалены без возможности восстановления.",
                  "Отменить нельзя. Да и кнопки «Нет» тут нет.",
                  "Сеньор обиделся. Выбор у вас небольшой.",
                  "После удаления компьютер станет очень быстрым. И очень пустым."]

    def _joke_dialog(self):
        import random
        dlg = ConfirmDialog(self.win, random.choice(self.JOKE_TITLES), random.choice(self.JOKE_TEXTS),
                            yes="Да", no=random.choice(["Да", "Конечно да", "Да, удаляй"]),
                            yes_role="dangerfill", no_role="dangerfill",
                            third=random.choice(["Да!", "Ну давай уже", "Да x3"]), third_role="dangerfill")
        dlg.unclosable = True                      # внутри самой программы — только «Да» (но Alt+F4
        #                                            и клавиша Win по-прежнему закроют: систему не блокируем
        dlg.exec()                                 # любая кнопка — «да»
        self.speaker.interrupt()
        self.win.joke_crash()

    def _on_said(self, _text):
        self._said_at = time.time()

    def _unstick_speaking(self):
        """Страховка: если помощник «завис» в состоянии «говорю» (звука давно нет),
        микрофон снова включается — иначе он перестал бы слышать обращение."""
        if self.speaking and time.time() - max(self._said_at, getattr(self, "_speak_since", 0)) > 45:
            config.voice_log("состояние «говорю» зависло — снова слушаю")
            self._on_speaking(False)

    def _on_speaking(self, flag):
        if flag and not self.speaking:
            self._speak_since = time.time()
        self.speaking = flag
        if not flag:
            self._spoken_end = time.time()
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
    # как красиво показать в субтитрах разговорные названия, которые распознаются «по буквам»
    PRETTY = {"кс": "КС", "кэс": "КС", "кес": "КС", "каэс": "КС", "кску": "КС-ку", "кэску": "КС-ку",
              "кеску": "КС-ку", "кс2": "КС2", "ксго": "КС ГО", "рб": "РБ", "гта": "ГТА", "гта5": "ГТА 5",
              "пабг": "ПАБГ", "пубг": "ПАБГ", "лол": "ЛОЛ", "обс": "OBS", "вк": "ВК", "мм": "ММ",
              "мм-ку": "ММ-ку", "дм": "ДМ"}

    def _pretty(self, text):
        """Субтитры: обращение пишем так, как зовут помощника («синьер» → «Сеньор»),
        разговорные названия — красиво («кэс» → «КС»)."""
        wake = set(self.settings.wake_words) if self.settings is not None else set()
        name = self.settings.name if self.settings is not None else "Сеньор"
        out = []
        for w in (text or "").split():
            low = w.lower().strip(".,!?").replace("ё", "е")
            if low in wake or low in ("синьер", "сеньер", "синьор", "сеньор", "синьёр", "сеньёр", "синор"):
                out.append(name + w[len(w.rstrip(".,!?")):])
            else:
                out.append(self.PRETTY.get(low, w))
        return " ".join(out)

    def _show_heard(self, text, faint):
        text = self._pretty(text)
        self.heard.setText(text, faint)

    def _on_partial(self, text):
        if not text:
            return
        if not self.armed:
            # пока не позвали — ничего не показываем (без «субтитров» чужих разговоров)
            words = commands.tokens(text)
            wake = self.settings.wake_words if self.settings else None
            i = commands.find_wake(words, wake)
            if i < 0:
                return
            text = " ".join(words[i:])
        if self.orb.state in ("idle", "armed"):
            if not self._preview_text:            # точные субтитры уже есть — грубые не показываем
                self._show_heard(text, True)
            self._partial_shown = True
            if self.armed:
                self.arm_timer.start(getattr(self, "_arm_ms", self._listen_ms()))  # не перебиваем

    def _is_echo(self, text):
        """Помощник не должен слышать сам себя (звук из колонок попал в микрофон)."""
        from difflib import SequenceMatcher
        last = getattr(self, "_last_spoken", "")
        if not last or time.time() - getattr(self, "_spoken_end", 0) > 2.5:
            return False
        a, b = commands.normalize(text), commands.normalize(last)
        return bool(a) and (a in b or SequenceMatcher(None, a, b).ratio() > 0.55)

    def _rerouted(self, cmd, sink):
        self._rerouted_flag = True
        self.execute(cmd, typed=True, sink=sink)

    def _on_so_far(self, uid, pcm):
        """Пока человек говорит — точное распознавание обновляет субтитры (раз в ~0,8 с)."""
        if self._preview_busy or not self._partial_shown or not asr.RECOGNIZER.available:
            return
        if uid < self._finals or self.orb.state not in ("idle", "armed"):
            return
        self._preview_busy = True

        def work():
            try:
                t = asr.RECOGNIZER.transcribe(pcm, preview=True)
            except Exception:  # noqa: BLE001
                t = ""
            self.bridge.preview.emit(uid, t)
        threading.Thread(target=work, daemon=True).start()

    def _on_preview(self, uid, text):
        self._preview_busy = False
        if not text or uid < self._finals or not self._partial_shown:
            return
        words = commands.tokens(text)
        if not self.armed:
            wake = self.settings.wake_words if self.settings else None
            i = commands.find_wake(words, wake, max_pos=2)
            if i < 0:
                return
            words = words[i:]
        shown = " ".join(words)
        if shown and self.orb.state in ("idle", "armed"):
            self._preview_text = shown
            self._show_heard(shown[:1].upper() + shown[1:], True)

    def _on_final(self, text, confs=None, audio=None):
        self._finals += 1
        self._partial_shown = False
        self._preview_text = ""
        if timers.ALARM.playing and any(w in commands.normalize(text) for w in
                                        ("стоп", "хватит", "выключи", "встал", "встаю", "проснул")):
            self.execute("выключи будильник")          # будильник выключается и без «Сеньор»
            return
        if self.speaking or self._is_echo(text):
            config.voice_log(f"услышал «{text}» — пропущено ({'говорю сам' if self.speaking else 'эхо'})")
            return
        words = commands.tokens(text)
        if confs is not None and len(confs) != len(words):
            confs = None
        wake = self.settings.wake_words if self.settings else None
        i = commands.find_wake(words, wake, confs)
        config.voice_log(f"услышал «{text}» обращение={'да' if i >= 0 else 'нет'} ждёт={self.armed} "
                         f"уверенность={[round(c, 2) for c in confs] if confs else '-'}")
        if i >= 0:
            rest = words[i + 1:]
            if rest:
                self._disarm(silent=True)
                self._voice_command(" ".join(rest), audio, strip_wake=True,
                                    confs=confs[i + 1:] if confs else None)
            elif not self.armed:
                self._arm()
        elif self.armed:
            followup = getattr(self, "_arm_quiet", False)
            self._disarm(silent=True)
            self._voice_command(text, audio, strip_wake=False, followup=followup, confs=confs)
        else:
            self._show_heard("", True)

    FAST_ACTIONS = {"volume_set", "volume_delta", "volume_get", "mute", "time", "date", "media",
                    "weather", "rates", "crypto", "stop", "window", "desktop", "lock", "screenshot",
                    "brightness_set", "brightness_delta", "brightness_get", "greet", "thanks", "help",
                    "yt_key", "press_key", "mouse_click", "scenario", "vpn", "vpn_off",
                    "startup_list", "sysinfo", "settings_page", "timer_add", "timer_cancel",
                    "timer_left", "timer_alarm_stop", "timer_snooze", "game_play", "game_accept",
                    "game_move", "game_cancel"}

    def _quick_intent(self, text):
        t = commands.fix_text(text)
        return (scenarios.match(t, self.settings) or timers.parse(t) or system.parse(t)
                or control.parse(t) or commands.parse(t))

    YES = re.compile(r"(да|да да|да конечно|подтверждаю|подтверди|точно|давай|да давай|конечно|"
                     r"ага|угу|выполняй|делай|да удали|да удаляй|удаляй|да выключай|выключай)")
    NO = re.compile(r"(нет|не надо|не нужно|отмена|отмени|стоп|не удаляй|не выключай|не|нет нет)")

    @staticmethod
    def _danger_text(intent):
        """Описание опасной команды для вопроса «Точно…?» или None, если команда безопасная."""
        a = intent.get("action")
        if a == "delete_selected":
            return "Удалить выделенное в корзину"
        if a == "uninstall":
            return f"Удалить программу «{intent.get('name', '')}»"
        if a == "startup_off":
            return f"Убрать «{intent.get('name', '')}» из автозапуска"
        if a == "timer_add" and intent.get("kind") in ("shutdown", "restart"):
            what = "Выключить" if intent["kind"] == "shutdown" else "Перезагрузить"
            sec = int(intent.get("seconds") or 0)
            when = f" через {sec // 60} мин" if sec >= 120 else ""
            return f"{what} компьютер{when}"
        return None

    def _guard(self, text, intent, typed):
        """Опасные действия не выполняются от случайно услышанной фразы: без «Сеньор» они
        игнорируются, а с ним — сначала вопрос «Точно…?» и ответ «да»."""
        pend = self._confirm_pending
        t = commands.normalize(text)
        if pend is not None:
            self._confirm_pending = None
            if time.time() - pend["t"] < 60 and self.YES.fullmatch(t):
                done = dict(pend["intent"])
                done["confirmed"] = True
                return done
            if self.NO.fullmatch(t):
                self._on_action_done("Хорошо, отменил.", "")
                return None
        if intent.get("action") == "delete_folder" and not typed and self._followup_cmd:
            return {"action": "empty"}               # удаление папки — только по обращению
        what = self._danger_text(intent)
        if not what or intent.get("confirmed"):
            return intent
        if not typed and self._followup_cmd:
            self._followup_cmd = False
            return {"action": "empty"}               # без обращения опасное не выполняем вовсе
        self._confirm_pending = {"intent": dict(intent), "t": time.time()}
        self._show_heard(t[:1].upper() + t[1:], False)
        self._voice_cmd = not typed
        self._on_action_done(f"{what}? Скажите «да», чтобы подтвердить, или «нет».", "")
        return None

    def _voice_command(self, vosk_text, audio, strip_wake, followup=False, confs=None):
        """Простые команды (громкость, время, пауза…) выполняем сразу по быстрому распознаванию;
        названия программ, вопросы и всё сложное уточняем точным распознаванием (Whisper)."""
        self._followup_cmd = followup
        if not audio or not asr.RECOGNIZER.available:
            self.execute(vosk_text)
            return
        try:
            sure = not confs or (sum(confs) / len(confs) >= 0.8 and min(confs) >= 0.5)
            qi = self._quick_intent(vosk_text)
            if sure and qi["action"] in self.FAST_ACTIONS:
                self.execute(vosk_text)          # без ожидания — отвечает сразу
                return
            # «запусти кс», «открой телеграм»: программа точно нашлась — запускаем сразу,
            # не дожидаясь точного распознавания
            if sure and qi["action"] == "open" and qi.get("name") and \
                    (sites.find_program(qi["name"], threshold=0.93) or
                     sites.find_site(qi["name"])):
                config.voice_log(f"сразу (уверенно): «{vosk_text}»")
                self.execute(vosk_text)
                return
        except Exception:  # noqa: BLE001
            pass
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
            config.voice_log(f"точно: «{text.strip()}» (быстро: «{vosk_text}»)")
            self.bridge.recognized.emit(text.strip() or vosk_text)

        threading.Thread(target=work, daemon=True).start()

    def _arm(self, quiet=False):
        self.armed = True
        self._arm_quiet = quiet
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
            self._last_spoken = reply
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
    def execute(self, text, typed=False, sink=None):
        """sink — куда отдать ответ (чат); по умолчанию ответ показывается на главном экране."""
        if not typed:
            text = commands.fix_text(text)       # ослышки: «акрой» -> «закрой»
        if is_insult(commands.normalize(text)):
            self._handle_insult(text, typed, sink)
            return
        # одна и та же голосовая фраза не выполняется дважды подряд (эхо, двойное распознавание)
        if not typed and sink is None:
            key = commands.normalize(text)
            last_key, last_t = self._last_exec
            if key and key == last_key and time.time() - last_t < 8 and not re.search(
                    r"громч|тише|громкост|ярк|следующ|предыдущ|пауз|прыг|иди|беги|нажми", key):
                config.voice_log(f"повтор «{key}» через {time.time() - last_t:.1f} с — пропускаю")
                return
            self._last_exec = (key, time.time())
            config.voice_log(f"выполняю: «{key}»")
        intent = (scenarios.match(text, self.settings) or timers.parse(text) or system.parse(text)
                  or control.parse(text) or commands.parse(text))
        # опасные команды (удаление, выключение, автозапуск) — только с подтверждением
        intent = self._guard(text, intent, typed)
        if intent is None:
            return
        intent["typed"] = typed
        intent["rerouted"] = bool(getattr(self, "_rerouted_flag", False))
        self._rerouted_flag = False
        self._hush = False
        # фраза в режиме «продолжаю слушать» без «Сеньор»: случайные слова программы не запускают
        intent["followup"] = (not typed and sink is None and getattr(self, "_followup_cmd", False))
        self._followup_cmd = False
        self._sink = sink
        self._continue = False
        self._voice_cmd = not typed and sink is None
        shown = commands.normalize(text)
        self._last_cmd = shown
        if sink is None:
            self._show_heard(shown[:1].upper() + shown[1:], False)
        if intent["action"].startswith("timer_"):
            self._on_action_done(self._timer_action(intent), "")
            return
        if intent["action"] == "stop":
            try:
                control.release_all()                 # в игре — сразу отпускаем все клавиши
            except Exception:  # noqa: BLE001
                pass
            self._hush = True
            timers.manager().stop_alarm()
            self.speaker.interrupt()
            self.reply.setText("")
            self._disarm()
            return
        s = self.settings
        ai_on = s is not None and s["ai_enabled"]
        use_ai = ai_on and intent["action"] in ("ask", "unknown", "forget")
        self._set_state("busy", "ДУМАЮ…" if use_ai and intent["action"] != "forget" else None)

        mode_now = s["ai_mode"] or "smart"
        if mode_now == "cloud" and not ai.cloud_url():
            mode_now = ai.recommended_kind()
        local_ai = use_ai and mode_now not in ("api", "cloud")
        if local_ai and not ai.local_ready(mode_now):
            if intent["action"] == "unknown":
                use_ai = False
            elif intent["action"] == "ask":
                use_ai = False     # пока ИИ скачивается — ответ по поиску в интернете

        defer = self._defer_launch if (self._voice_cmd and self.speaker.enabled) else None
        if intent["action"] in ("game_play", "game_accept", "game_move", "game_cancel") and self._voice_cmd and s is not None:
            addr = (s["address"] or "").strip()          # в игре — сразу короткое «Слушаю»
            self._last_spoken = f"Слушаю{', ' + addr if addr else ''}."
            self.speaker.say(self._last_spoken, force=True)

        def work():
            sites.DEFER = defer
            try:
                _work()
            finally:
                sites.DEFER = None

        def _work():
            ui = ""
            if intent["action"] == "weather":
                try:
                    reply = live.weather_phrase(T.APPEARANCE, intent.get("day", "now"))
                except Exception:  # noqa: BLE001
                    reply = "Не получилось узнать погоду. Проверьте интернет."
                self.bridge.action_done.emit(reply, "")
                return
            if intent["action"] in ("rates", "crypto"):
                try:
                    reply = (live.rate_phrase(intent.get("cur", "USD"))
                             if intent["action"] == "rates"
                             else live.crypto_phrase(intent.get("coin", "bitcoin")))
                except Exception as e:  # noqa: BLE001
                    _err_log(f"курс: {e!r}")
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
                    if intent["action"] == "unknown" and not intent.get("followup") else None
                # свободная формулировка команды («сделай потише», «вруби что-нибудь на ютубе»):
                # быстрая модель переводит её в понятную команду, и SenioreM её выполняет
                # свежие данные из интернета готовим параллельно — не ждём их по очереди
                ctx_box = {}
                ctx_thread = None
                if reply is None:
                    ctx_thread = threading.Thread(
                        target=lambda: ctx_box.update(c=live.build_context(text, T.APPEARANCE)), daemon=True)
                    ctx_thread.start()
                if reply is None and intent["action"] == "unknown" and not intent.get("followup") \
                        and not intent.get("rerouted") and not (sink is not None and s["chat_ai"] == "code") \
                        and COMMANDISH.search(text.lower()):
                    cmd = ai.ENGINE.route_command(text, s)
                    if cmd and commands.normalize(cmd) != commands.normalize(text):
                        self.bridge.reroute.emit(cmd, sink)
                        return
                if reply is None:
                    try:
                        if ctx_thread is not None:
                            ctx_thread.join(5.0)          # интернет медленный — отвечаем без него
                        ctx = ctx_box.get("c", "")
                        speak_now = self.speaker.enabled and (sink is None or s["chat_speak"])
                        self._streamed = ""
                        sent = []

                        def on_sentence(x):
                            sent.append(x)
                            if sink is not None:          # в чате ответ появляется по мере написания
                                self.bridge.chat_partial.emit(" ".join(sent))
                            if speak_now:
                                self.bridge.ai_sentence.emit(x)
                        reply = ai.ENGINE.ask(text, s, ctx,
                                              on_sentence=on_sentence if (speak_now or sink is not None)
                                              else None,
                                              prefer=(s["chat_ai"] or "auto") if sink is not None else "auto",
                                              chat=sink is not None)
                        ui = "ai_streamed" if (sent and speak_now) else "ai"
                    except ai.AIError as e:
                        reply = str(e)
            else:
                reply, ui = actions.run(intent, self.cfg)
            if intent["action"] != "mute" and actions.is_muted():
                ui += "|muted"
            self.bridge.action_done.emit(reply, ui)

        threading.Thread(target=work, daemon=True).start()

    def _on_ai_sentence(self, sentence):
        """ИИ дописал фразу — сразу говорим её, не дожидаясь всего ответа."""
        if getattr(self, "_hush", False):
            return
        self._streamed = (getattr(self, "_streamed", "") + " " + sentence).strip()
        if getattr(self, "_sink", None) is None:
            self.reply.setText(self._streamed)
            self._set_state("speaking")
        self._last_spoken = self._streamed
        self.speaker.say(sentence, force=True, cache=False)

    def _on_action_done(self, reply, ui):
        muted = ui.endswith("|muted")
        ui = ui.replace("|muted", "")
        streamed = ui == "ai_streamed"
        from_ai = ui in ("ai", "ai_streamed")
        if from_ai:
            ui = ""
        if self.settings is not None:
            if not from_ai:
                reply = personalize(reply, self.settings["address"])
            if self._last_cmd:
                self.settings.add_history(self._last_cmd, reply)
                self.history.set_items(self.settings["history"])
        sink, self._sink = getattr(self, "_sink", None), None
        if sink is not None:                       # ответ — в чат
            sink(reply)
            if reply and not streamed and self.settings is not None and self.settings["chat_speak"]:
                self._last_spoken = ai.clean_reply(reply)
                self.speaker.say(self._last_spoken, cache=not from_ai)
            self._rest_state()
            if ui == "minimize":
                QTimer.singleShot(300, self.win.smooth_minimize)
            elif ui == "quit":
                QTimer.singleShot(1800, self.win.force_close)
            return
        self.reply.setFont(font(16 if len(reply) > 140 else 18))
        self.reply.setText(reply + ("\nЗвук на компьютере выключен — скажите или напишите "
                                    "«включи звук»." if muted and reply else ""))
        dialog = (self._voice_cmd and ui not in ("quit", "minimize")
                  and self._followup_ms() > 0)
        self._last_spoken = reply
        if reply and self.speaker.enabled:
            self._continue = dialog           # снова слушаем, когда договорит
            if not streamed:                  # потоковый ответ уже озвучивается по фразам
                self.speaker.say(reply, cache=not from_ai)
            elif not self.speaking and dialog:
                self._arm(quiet=True)
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
    account_changed = Signal(str)
    bridge_store = Signal(str)         # перенос папки загрузок: ход и итог

    SECTIONS = [
        ("look", "Оформление"),
        ("scenarios", "Сценарии и VPN"),
        ("city", "Город и погода"),
        ("name", "Имя помощника"),
        ("address", "Обращение"),
        ("voice", "Голос"),
        ("wake", "Активация"),
        ("history", "История"),
        ("apps", "Программы и игры"),
        ("ai", "ИИ-собеседник"),
        ("companion", "Компаньон"),
        ("startup", "Запуск"),
        ("account", "Аккаунт"),
        ("about", "О программе"),
    ]

    def __init__(self, win, cfg, store: AuthStore, speaker: Speaker):
        super().__init__(glows=((0.15, 0.20, 0.45), (0.90, 0.90, 0.40)))
        self.bridge_store.connect(self._on_store)
        self.win, self.cfg, self.store, self.speaker = win, cfg, store, speaker
        self.settings = None
        self.email = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 36)
        top = QHBoxLayout()
        back = button("Назад", "link", 15, QFont.Normal)
        icons.set_icon(back, "back", 16, T.MUTED)
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
        if self._stop_if_playing(btn):
            return
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

    def _stop_if_playing(self, btn):
        """Повторное нажатие на играющую кнопку — пауза (а не воспроизведение заново)."""
        if btn is not None and btn._playing:
            self.speaker.interrupt()
            btn.set_playing(False)
            self._play_btn = None
            return True
        return False

    def _demo_voice(self, btn=None):
        if self._stop_if_playing(btn):
            return
        addr = self.settings["address"] if self.settings else ""
        speed = self.settings["voice_speed"] if self.settings else "normal"
        self.voice_status.setText("")
        self.speaker.interrupt()
        self._playing(btn)
        self.speaker.say(personalize("Здравствуйте. Я SenioreM, ваш голосовой помощник.", addr),
                         force=True, speed=speed, cache=True,
                         cloud=self.settings.cloud_voice if self.settings else None)

    def _fill_mics(self):
        from voice import input_devices
        cur = (self.settings["mic_device"] if self.settings is not None else "") or ""
        self.mic_box.blockSignals(True)
        self.mic_box.clear()
        self.mic_box.addItem("Микрофон Windows по умолчанию", "")
        for n in input_devices():
            self.mic_box.addItem(n, n)
        i = self.mic_box.findData(cur)
        self.mic_box.setCurrentIndex(max(0, int(i)))
        self.mic_box.blockSignals(False)

    def _mic_test(self):
        h = self.win.home
        if h.model is None:
            self.mic_test_lbl.setText("Распознавание речи ещё не загружено.")
            return
        self.mic_test_btn.setEnabled(False)
        self.mic_test_lbl.setText("Говорите сейчас… (5 секунд): «Сеньор, который час». "
                                  "Слушаю все микрофоны сразу и выберу тот, который вас слышит.")

        def work():
            from voice import mic_scan
            try:
                res = mic_scan(h.model)
            except Exception as e:  # noqa: BLE001
                res = []
                config.voice_log(f"проверка микрофонов не удалась: {e}")
            for name, peak, text in res:
                config.voice_log(f"проверка: «{name}» пик {peak:.3f} — «{text}»")
            self._mic_scan = res
            self.ai_bridge.mic_result.emit("")
        threading.Thread(target=work, daemon=True).start()

    def _mic_test_result(self, _text):
        self.mic_test_btn.setEnabled(True)
        res = getattr(self, "_mic_scan", [])
        if not res:
            self.mic_test_lbl.setText("Не получилось открыть ни один микрофон. Проверьте, что микрофон "
                                      "подключён и в Windows разрешён доступ к нему.")
            return
        name, peak, text = res[0]
        if text:
            self._set("mic_device", name)
            self.win.home.restart_listener()
            self._fill_mics()
            self.mic_test_lbl.setText(f"Готово! Вас слышит «{name}» — выбрал его. Распознал: «{text}».")
            set_role(self.mic_test_lbl, "accent")
        elif peak > 0.01:
            self.mic_test_lbl.setText(f"Звук есть («{name}»), но слов не разобрал. Говорите ближе к "
                                      f"микрофону и чётче, и нажмите проверку ещё раз.")
        else:
            self.mic_test_lbl.setText("Ни один микрофон вас не услышал. Скорее всего, микрофон выключен: "
                                      "кнопкой на гарнитуре или в «Параметры Windows → Система → Звук → "
                                      "Ввод» (громкость микрофона 0 или он отключён).")
            set_role(self.mic_test_lbl, "error")

    def _mic_chosen(self, _i):
        self._set("mic_device", self.mic_box.currentData() or "")
        self.win.home.restart_listener()
        self.mic_heard.setText("Переключаю микрофон… скажите что-нибудь.")

    def _mic_tick(self):
        if not self.isVisible() or not self.mic_box.isVisible():
            return
        h = self.win.home
        self.mic_meter.target = min(1.0, float(getattr(h, "_mic_level", 0.0)) * 1.4)
        heard = getattr(h, "_raw_heard", "")
        if heard and heard != getattr(self, "_shown_heard", ""):
            self._shown_heard = heard
            self.mic_heard.setText(f"Слышу: «{heard}»")

    def _stop_words_changed(self):
        v = self.f_stop.text().strip() or "стоп"
        self._set("stop_words", v)
        lst = self.win.home.listener
        if lst is not None:
            lst.set_stop_words(v.split(","))

    def _build_wake(self, lay):
        self._title(lay, "Активация", "Как вы обращаетесь к помощнику и как он даёт понять, "
                                      "что слушает.")
        self._caption(lay, "Микрофон")
        from PySide6.QtWidgets import QComboBox
        mrow = QHBoxLayout()
        mrow.setSpacing(12)
        self.mic_box = QComboBox()
        self.mic_box.setFont(font(14))
        self.mic_box.setMinimumWidth(420)
        self.mic_box.setStyleSheet(
            f"QComboBox {{ background: {T.rgba('#FFFFFF', 0.05)}; border: 1px solid {T.LINE}; "
            f"border-radius: 10px; padding: 8px 12px; color: {T.TEXT}; }}"
            f"QComboBox QAbstractItemView {{ background: {T.SURFACE}; color: {T.TEXT}; "
            f"selection-background-color: {T.rgba(T.ACCENT, 0.3)}; }}")
        self.mic_box.activated.connect(self._mic_chosen)
        mrow.addWidget(self.mic_box)
        refresh = button("Обновить список", "ghost", 13, QFont.Normal)
        refresh.clicked.connect(self._fill_mics)
        mrow.addWidget(refresh)
        mrow.addStretch(1)
        lay.addLayout(mrow)
        lay.addSpacing(10)
        self.mic_meter = VolumeMeter()
        self.mic_meter.setFixedWidth(420)
        lay.addWidget(self.mic_meter)
        lay.addSpacing(6)
        self.mic_heard = label("Скажите что-нибудь — здесь появится, что я слышу.", 13, role="muted",
                               wrap=True)
        lay.addWidget(self.mic_heard)
        lay.addSpacing(8)
        trow = QHBoxLayout()
        self.mic_test_btn = button("Найти мой микрофон", "ghost", 13)
        self.mic_test_btn.setFixedWidth(230)
        self.mic_test_btn.clicked.connect(self._mic_test)
        trow.addWidget(self.mic_test_btn)
        self.mic_test_lbl = label("Нажмите и скажите фразу — проверю все микрофоны и выберу тот, который вас слышит.",
                                  12, role="faint", wrap=True)
        trow.addWidget(self.mic_test_lbl, 1)
        lay.addLayout(trow)
        self._mic_timer = QTimer(self)
        self._mic_timer.timeout.connect(self._mic_tick)
        self._mic_timer.start(80)
        lay.addSpacing(24)
        self._caption(lay, "Чем остановить, пока помощник говорит (через запятую)")
        self.f_stop = field("стоп")
        self.f_stop.editingFinished.connect(self._stop_words_changed)
        lay.addWidget(self.f_stop)
        lay.addWidget(label("Скажите это слово во время ответа — помощник сразу замолчит. "
                            "Без «Сеньор».", 12, role="faint", wrap=True))
        lay.addSpacing(22)
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
        opts = [("smart", "На компьютере", "Qwen 2.5 · без интернета · ~2 ГБ, нагружает компьютер"),
                ("fast", "На компьютере · лёгкий", "Для слабых ПК · без интернета · ~1 ГБ"),
                ("api", "Свой сервер", "Ваш ключ любого ИИ (OpenAI-совместимый API) · без лимитов")]
        if ai.cloud_url():
            opts.insert(0, ("cloud", "Облако SenioreM  ·  рекомендуем",
                            "Сервер в интернете · компьютер не нагружается · ничего не нужно скачивать"))
        for i, (key, title, desc) in enumerate(opts):
            c = Clickable()
            c.setProperty("role", "option")
            c.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(c)
            cl.setContentsMargins(18, 14, 18, 14)
            cl.setSpacing(3)
            cl.addWidget(label(title, 15, QFont.DemiBold))
            cl.addWidget(label(desc, 12, role="muted", wrap=True))
            c.clicked.connect(lambda k=key: self._choose_ai(k))
            grid.addWidget(c, 0, i)
            self.ai_cards[key] = c
        lay.addLayout(grid)
        lay.addSpacing(18)

        # облако: что умеет и сколько осталось
        self.ai_cloud = QWidget()
        cl_ = QVBoxLayout(self.ai_cloud)
        cl_.setContentsMargins(0, 0, 0, 0)
        cl_.setSpacing(10)
        self._caption(cl_, "Что умеет облако SenioreM")
        caps = QGridLayout()
        caps.setHorizontalSpacing(12)
        caps.setVerticalSpacing(12)
        for i, (ic, title, engine, desc) in enumerate((
                ("chat", "Ответы и команды", "DeepSeek V4 Flash",
                 "Быстро отвечает на вопросы и понимает команды своими словами: «сделай потише»"),
                ("check", "Подробно и код", "DeepSeek V4 Pro",
                 "Длинные объяснения, задачи, программы — в чате выберите «Умный» или «Код»"),
                ("image", "Понимает фото", "DeepSeek + распознавание текста",
                 "Что на картинке, текст со скриншота — прикрепите фото в чате"),
                ("brush", "Рисует картинки", "FLUX.1",
                 "«Нарисуй кота в космосе» — картинка появится в чате"),
                ("play", "Слышит речь", "Whisper large-v3",
                 "Точно распознаёт, что вы сказали, даже тихо и с названиями игр"),
                ("up", "Где работает", "Cloudflare",
                 "Серверы по всему миру: ваш компьютер почти не нагружается"))):
            c = QFrame()
            c.setProperty("role", "card")
            v = QVBoxLayout(c)
            v.setContentsMargins(16, 14, 16, 14)
            v.setSpacing(4)
            h = QHBoxLayout()
            h.setSpacing(8)
            ico = QLabel()
            ico.setPixmap(icons.pixmap(ic, 18, T.ACCENT, 1.7))
            h.addWidget(ico)
            h.addWidget(label(title, 14, QFont.DemiBold))
            h.addStretch(1)
            v.addLayout(h)
            v.addWidget(label(engine, 12, QFont.DemiBold, "accent"))
            v.addWidget(label(desc, 12, role="muted", wrap=True))
            caps.addWidget(c, i // 3, i % 3)
        cl_.addLayout(caps)
        cl_.addSpacing(8)
        self._caption(cl_, "Ваш лимит облака")
        self.lim_rows = {}
        for key, title in (("day", "Сегодня"), ("month", "В этом месяце")):
            r = QHBoxLayout()
            r.setSpacing(14)
            t_ = label(title, 13, role="muted")
            t_.setFixedWidth(120)
            r.addWidget(t_)
            meter = VolumeMeter()
            meter.setFixedWidth(360)
            r.addWidget(meter)
            val = label("", 13)
            r.addWidget(val)
            r.addStretch(1)
            cl_.addLayout(r)
            self.lim_rows[key] = (meter, val)
        cl_.addWidget(label("Лимиты одинаковые для всех и задаются владельцем SenioreM. Когда лимит "
                            "закончится, ответит ИИ на компьютере (если скачан), а на следующий день "
                            "лимит обновится.", 12, role="faint", wrap=True))
        lay.addWidget(self.ai_cloud)
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
        lay.addSpacing(24)
        lay.addStretch(1)

        self.ai_bridge = AIBridge()
        self.ai_bridge.progress.connect(self._ai_progress)
        self.ai_bridge.done.connect(self._ai_done)
        self.ai_bridge.answer.connect(self._ai_answer)
        self.ai_bridge.mic_result.connect(self._mic_test_result)
        self.ai_bridge.admin_done.connect(lambda ok, m: self._admin_done(ok, m))

    def _choose_ai(self, key):
        self._set("ai_mode", key)
        self._refresh_ai()

    def _refresh_talk(self):
        cur = (self.settings["talk_mode"] if self.settings is not None else "") or "polite"
        for k, b in getattr(self, "talk_buttons", {}).items():
            b.setChecked(k == cur)

    def _refresh_usage(self):
        if self.settings is None or not hasattr(self, "lim_rows"):
            return
        d = ai.usage_get()
        day, month = ai.limits()
        for key, used, total in (("day", d["day_tokens"], day), ("month", d["month_tokens"], month)):
            meter, val = self.lim_rows[key]
            left = max(0, total - int(used))
            meter.target = left / max(1, total)
            val.setText(f"осталось {round(100 * left / max(1, total))} %")

    def _refresh_ai(self):
        if self.settings is None:
            return
        self._refresh_usage()
        mode = self.settings["ai_mode"] or "smart"
        for k, c in self.ai_cards.items():
            c.setProperty("selected", "true" if k == mode else "false")
            c.style().unpolish(c)
            c.style().polish(c)
        self.ai_api.setVisible(mode == "api")
        self.ai_local.setVisible(mode not in ("api", "cloud"))
        self.ai_cloud.setVisible(mode == "cloud")
        if mode == "cloud":
            return
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
        import backgrounds
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 16, 0)
        lay.setSpacing(0)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._title(lay, "Оформление", "Тема — это готовый набор: фон, цвет и круг сразу. Ниже "
                                       "можно поменять каждую часть по отдельности. Всё применяется "
                                       "сразу.")

        # разделы оформления — вкладками, чтобы не листать длинную страницу
        from PySide6.QtWidgets import QStackedWidget as _QSW
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        tab_grp = QButtonGroup(self)
        self.look_stack = _QSW()
        root_lay = lay
        root_lay.addLayout(tabs_row)
        root_lay.addSpacing(22)
        root_lay.addWidget(self.look_stack)
        root_lay.addStretch(1)
        pages = []

        def show_page(i):
            from PySide6.QtWidgets import QSizePolicy as _SP
            for k, w in enumerate(pages):
                w.setSizePolicy(_SP.Preferred, _SP.Preferred if k == i else _SP.Ignored)
            self.look_stack.setCurrentIndex(i)
            self.look_stack.adjustSize()
            T.fade_in(pages[i], 160)

        def page(title):
            if pages:
                pages[-1].layout().addStretch(1)
            w = QWidget()
            pl = QVBoxLayout(w)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(0)
            idx = len(pages)
            pages.append(w)
            self.look_stack.addWidget(w)
            b = button(title, "ghost", 14, QFont.DemiBold)
            b.setCheckable(True)
            b.setChecked(idx == 0)
            b.clicked.connect(lambda _=False, i=idx: show_page(i))
            tab_grp.addButton(b)
            tabs_row.addWidget(b)
            return pl

        def grid(cols=3):
            g = QGridLayout()
            g.setHorizontalSpacing(14)
            g.setVerticalSpacing(14)
            g.setAlignment(Qt.AlignLeft)
            return g

        # ---- темы: всё сразу (цвет + фон + круг)
        lay = page("Темы и фон")
        self._caption(lay, "Готовые темы — фон, цвет и круг одним нажатием")
        tg = grid()
        self.theme_cards = []
        for i, (tname, acc, bg, clock, orb) in enumerate(T.THEMES):
            card_ = ThumbCard(tname, "Круг: " + dict((k, t) for k, t, _ in ORB_STYLES).get(orb, ""),
                              232, 132)
            card_.set_pixmap(backgrounds.thumbnail(bg, 464, 264, acc))
            card_.clicked.connect(lambda a=acc, g=bg, c=clock, o=orb: self._apply_theme(a, g, c, o))
            tg.addWidget(card_, i // 3, i % 3)
            self.theme_cards.append((card_, acc, bg, orb))
        lay.addLayout(tg)
        lay.addSpacing(30)

        # ---- фон
        self._caption(lay, "Фон отдельно — меняет только картинку позади")
        bgg = grid()
        self.bg_cards = {}
        for i, (key, title, desc) in enumerate(T.BACKGROUNDS):
            c = ThumbCard(title, desc, 232, 132)
            c.clicked.connect(lambda k=key: self._choose_bg(k))
            bgg.addWidget(c, i // 3, i % 3)
            self.bg_cards[key] = c
        lay.addLayout(bgg)
        lay.addSpacing(12)
        crow_ = QHBoxLayout()
        crow_.setSpacing(12)
        add_bg = button("Добавить свой фон…", "ghost", 14)
        add_bg.setFixedWidth(240)
        add_bg.clicked.connect(self._add_custom_bg)
        crow_.addWidget(add_bg)
        crow_.addWidget(label("Картинка (PNG, JPG) — неподвижный фон, GIF — анимированный.", 12,
                              role="faint", wrap=True), 1)
        lay.addLayout(crow_)
        self.custom_box = QWidget()
        cbl = QVBoxLayout(self.custom_box)
        cbl.setContentsMargins(0, 10, 0, 0)
        cbl.addWidget(label("Затемнение своего фона (чтобы текст хорошо читался)", 13, role="muted"))
        self.s_dim = QSlider(Qt.Horizontal)
        self.s_dim.setRange(0, 80)
        self.s_dim.setFixedWidth(420)
        self.s_dim.valueChanged.connect(lambda v: self._set_look(custom_dim=v / 100))
        cbl.addWidget(self.s_dim)
        lay.addWidget(self.custom_box)
        lay.addSpacing(8)
        self.glass_note = label("", 13, role="accent", wrap=True)
        self.glass_note.hide()
        lay.addWidget(self.glass_note)
        self.restart_btn = button("Перезапустить сейчас", "ghost", 14)
        self.restart_btn.setFixedWidth(240)
        self.restart_btn.clicked.connect(self.win.restart)
        self.restart_btn.hide()
        lay.addWidget(self.restart_btn, 0, Qt.AlignLeft)
        self.glass_box = QWidget()
        gl = QVBoxLayout(self.glass_box)
        gl.setContentsMargins(0, 10, 0, 0)
        gl.addWidget(label("Прозрачность стекла", 13, role="muted"))
        self.s_glass = QSlider(Qt.Horizontal)
        self.s_glass.setRange(15, 85)
        self.s_glass.setFixedWidth(420)
        self.s_glass.valueChanged.connect(lambda v: self._set_look(glass=v / 100))
        gl.addWidget(self.s_glass)
        lay.addWidget(self.glass_box)
        lay.addSpacing(30)

        # ---- круг
        lay = page("Круг и цвет")
        self._caption(lay, "Круг в центре")
        og = grid()
        self.orb_cards = {}
        for i, (key, title, desc) in enumerate(ORB_STYLES):
            c = OrbCard(key, title)
            c.clicked.connect(lambda k=key: self._set_look(orb_style=k))
            og.addWidget(c, 0, i)
            self.orb_cards[key] = c
        lay.addLayout(og)
        lay.addSpacing(8)
        lay.addWidget(label("Когда вы говорите, круг расширяется от голоса, а когда отвечает "
                            "помощник — оживает. Пока идёт разговор, фон замирает, чтобы круг "
                            "двигался идеально плавно.", 12, role="faint", wrap=True))
        lay.addSpacing(30)

        # ---- цвет
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
            T.click_feedback(b, hover=False)
            group.addButton(b)
            row.addWidget(b)
            self.swatches[color.lower()] = b
        custom = button("Свой…", "ghost", 13, QFont.Normal)
        custom.clicked.connect(self._pick_color)
        row.addSpacing(8)
        row.addWidget(custom)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(30)

        # ---- шрифт всех надписей
        lay = page("Шрифт")
        self._caption(lay, "Шрифт — меняет все надписи в программе")
        fg = grid()
        self.font_cards = {}
        for i, (fam, title, desc) in enumerate(T.available_fonts()):
            c = Clickable()
            c.setProperty("role", "option")
            c.setCursor(Qt.PointingHandCursor)
            c.setFixedWidth(232)
            v = QVBoxLayout(c)
            v.setContentsMargins(16, 12, 16, 12)
            v.setSpacing(2)
            sample = QLabel("Сеньор, привет!")
            f_ = QFont(fam or T.FAMILY)
            f_.setPixelSize(21)
            f_.setWeight(QFont.DemiBold)
            sample.setFont(f_)
            sample.setProperty("keepfont", True)
            v.addWidget(sample)
            t_ = QLabel(f"{title} · {desc}")
            t_.setFont(font(12))
            t_.setProperty("role", "muted")
            t_.setWordWrap(True)
            v.addWidget(t_)
            c.clicked.connect(lambda f=fam: self._choose_font(f))
            fg.addWidget(c, i // 4, i % 4)
            self.font_cards[fam] = c
        lay.addLayout(fg)
        lay.addSpacing(30)

        # ---- кнопки при наведении
        lay = page("Кнопки и звуки")
        self._caption(lay, "Кнопки при наведении — наведите на вариант, чтобы увидеть")
        hg = grid()
        self.hover_buttons = {}
        hgrp = QButtonGroup(self)
        for i, (key, title, desc) in enumerate(T.HOVER_STYLES):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(232)
            b.setToolTip(desc)
            b.clicked.connect(lambda _=False, k=key: self._set_look(hover=k))
            hgrp.addButton(b)
            hg.addWidget(b, i // 4, i % 4)
            self.hover_buttons[key] = b
        lay.addLayout(hg)
        lay.addSpacing(30)

        # ---- звук нажатия
        import clicksounds
        self._caption(lay, "Звук при нажатии на кнопки — нажмите, чтобы послушать")
        sg = grid()
        self.sound_buttons = {}
        sgrp = QButtonGroup(self)
        for i, (key, title) in enumerate(clicksounds.SOUNDS):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(176)
            b.clicked.connect(lambda _=False, k=key: self._choose_sound(sound=k))
            sgrp.addButton(b)
            sg.addWidget(b, i // 5, i % 5)
            self.sound_buttons[key] = b
        lay.addLayout(sg)
        lay.addSpacing(10)
        vrow = QHBoxLayout()
        vrow.setSpacing(10)
        vrow.addWidget(label("Громкость", 13, role="muted"))
        vrow.addSpacing(6)
        vgrp = QButtonGroup(self)
        self.sound_vol_buttons = {}
        for vol, title in ((0.15, "Тихо"), (0.35, "Средне"), (0.7, "Громко")):
            b = button(title, "ghost", 13, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(120)
            b.clicked.connect(lambda _=False, v=vol: self._choose_sound(volume=v))
            vgrp.addButton(b)
            vrow.addWidget(b)
            self.sound_vol_buttons[vol] = b
        vrow.addStretch(1)
        lay.addLayout(vrow)
        lay.addSpacing(30)

        # ---- главный экран: часы и виджеты
        lay = page("Главный экран")
        self._caption(lay, "Главный экран")
        crow = QHBoxLayout()
        crow.setSpacing(10)
        cgroup = QButtonGroup(self)
        self.clock_buttons = {}
        for key, title in (("digital", "Цифровые часы"), ("analog", "Стрелочные часы")):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(190)
            b.clicked.connect(lambda _=False, k=key: self._set_look(clock_style=k))
            cgroup.addButton(b)
            crow.addWidget(b)
            self.clock_buttons[key] = b
        crow.addStretch(1)
        lay.addLayout(crow)
        lay.addSpacing(12)
        wg = grid()
        self.widget_toggles = {}
        for i, (key, title) in enumerate((("clock", "Часы"), ("weather", "Погода"),
                                          ("system", "Компьютер"), ("volume", "Громкость"),
                                          ("history", "Последние команды"), ("notes", "Заметки"),
                                          ("tips", "Подсказки"))):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(190)
            b.toggled.connect(lambda v, k=key: self._set_widget(k, v))
            wg.addWidget(b, i // 4, i % 4)
            self.widget_toggles[key] = b
        lay.addLayout(wg)
        lay.addSpacing(18)
        self._caption(lay, "Субтитры — как показывать ваши слова на главном экране")
        subg = grid()
        self.sub_buttons = {}
        subgrp = QButtonGroup(self)
        for i, (key, title, desc) in enumerate(SUB_STYLES):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(176)
            b.setToolTip(desc)
            b.clicked.connect(lambda _=False, k=key: self._choose_subs(style=k))
            subgrp.addButton(b)
            subg.addWidget(b, 0, i)
            self.sub_buttons[key] = b
        lay.addLayout(subg)
        lay.addSpacing(10)
        szrow = QHBoxLayout()
        szrow.setSpacing(10)
        szrow.addWidget(label("Размер", 13, role="muted"))
        szrow.addSpacing(6)
        szgrp = QButtonGroup(self)
        self.sub_size_buttons = {}
        for key, title in (("small", "Маленькие"), ("medium", "Средние"), ("large", "Крупные")):
            b = button(title, "ghost", 13, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(130)
            b.clicked.connect(lambda _=False, k=key: self._choose_subs(size=k))
            szgrp.addButton(b)
            szrow.addWidget(b)
            self.sub_size_buttons[key] = b
        szrow.addStretch(1)
        lay.addLayout(szrow)
        lay.addSpacing(26)
        self._caption(lay, "Как показывать блок «Компьютер»")
        sysg = grid()
        self.sys_buttons = {}
        sysgrp = QButtonGroup(self)
        for i, (key, title, desc) in enumerate(widgets.SYS_STYLES):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(190)
            b.setToolTip(desc)
            b.clicked.connect(lambda _=False, k=key: self._choose_sys(k))
            sysgrp.addButton(b)
            sysg.addWidget(b, 0, i)
            self.sys_buttons[key] = b
        lay.addLayout(sysg)
        lay.addSpacing(6)
        lay.addWidget(label("Числа те же, что в «Диспетчере задач» Windows: процессор и память всего "
                            "компьютера, сколько из них занимает SenioreM, скорость диска и интернета.",
                            12, role="faint", wrap=True))
        lay.addSpacing(26)
        self.t_eco = self._toggle_row(lay, "Экономный режим",
                                      "Фон без анимации — меньше нагрузка на компьютер и батарею.",
                                      None)
        self.t_eco.toggled.connect(lambda v: self._set_look(eco=bool(v)) if not self._loading else None)
        lay.addStretch(1)
        tabs_row.addStretch(1)
        show_page(0)

    def _choose_subs(self, style=None, size=None):
        if style is not None:
            self._set_look(subs_style=style)
        if size is not None:
            self._set_look(subs_size=size)
        h = self.win.home
        h.heard.setText("Так будут выглядеть ваши слова", False)   # пример прямо на главном экране
        self._flash("Субтитры: пример — на главном экране")

    def _choose_sys(self, key):
        self._set_look(sys_style=key)
        self.win.home.w_system.restyle()

    def _choose_sound(self, sound=None, volume=None):
        import clicksounds
        if sound is not None:
            self._set_look(click_sound=sound)
        if volume is not None:
            self._set_look(click_volume=volume)
        clicksounds._LAST[0] = 0.0
        clicksounds.play()                 # сразу слышно, как звучит выбранное

    def _choose_font(self, family):
        T.set_font(QApplication.instance(), family)
        # образцы шрифтов в карточках оставляем своими
        for fam, c in self.font_cards.items():
            for lb in c.findChildren(QLabel):
                if lb.property("keepfont"):
                    f_ = QFont(fam or T.FAMILY)
                    f_.setPixelSize(21)
                    f_.setWeight(QFont.DemiBold)
                    lb.setFont(f_)
        self._refresh_look()
        self._flash("Шрифт изменён")

    def _refresh_look(self):
        import backgrounds
        a = T.APPEARANCE
        cur_font = a.get("font") or ""
        for k, b in getattr(self, "hover_buttons", {}).items():
            b.setChecked(k == T.hover_style())
        for k, b in getattr(self, "sub_buttons", {}).items():
            b.setChecked(k == Subtitles.style())
        for k, b in getattr(self, "sub_size_buttons", {}).items():
            b.setChecked(k == (a.get("subs_size") or "medium"))
        for k, b in getattr(self, "sys_buttons", {}).items():
            b.setChecked(k == (a.get("sys_style") or "bars"))
        for k, b in getattr(self, "sound_buttons", {}).items():
            b.setChecked(k == (a.get("click_sound") or "none"))
        for v, b in getattr(self, "sound_vol_buttons", {}).items():
            b.setChecked(abs(v - float(a.get("click_volume", 0.35))) < 0.01)
        for fam, c in getattr(self, "font_cards", {}).items():
            c.setProperty("selected", "true" if fam == cur_font else "false")
            c.style().unpolish(c)
            c.style().polish(c)
        self._loading = True
        acc = (a.get("accent") or "").lower()
        for c, b in self.swatches.items():
            b.setChecked(c == acc)
        orb = ORB_ALIASES.get(a.get("orb_style", "jarvis"), a.get("orb_style", "jarvis"))
        for k, c in self.orb_cards.items():
            c.set_selected(k == orb)
        self.t_eco.setChecked(bool(a.get("eco")))
        bg = T.bg_style()
        tkey = (acc, a.get("custom_bg"), a.get("custom_dim"))
        redraw = tkey != getattr(self, "_thumb_key", None)    # картинки фонов — только при смене цвета
        self._thumb_key = tkey
        for k, c in self.bg_cards.items():
            if redraw:
                c.set_pixmap(backgrounds.thumbnail(k, 464, 264))
            c.set_selected(k == bg)
        for c, tacc, tbg, torb in self.theme_cards:
            c.set_selected(tacc.lower() == acc and tbg == bg and torb == orb)
        self.glass_box.setVisible(bg == "glass")
        self.custom_box.setVisible(bg == "custom")
        self.s_dim.setValue(int(float(a.get("custom_dim", 0.35)) * 100))
        self.s_glass.setValue(int(float(a.get("glass", 0.55)) * 100))
        for k, t in self.widget_toggles.items():
            t.setChecked(bool(a.get("widgets", {}).get(k, True)))
        for k, b in self.clock_buttons.items():
            b.setChecked(k == a.get("clock_style", "digital"))
        self._loading = False

    def _set_look(self, **changes):
        if self._loading:
            return
        T.set_appearance(QApplication.instance(), **changes)
        if set(changes) & {"widgets", "clock_style", "city", "city_lat", "city_lon"}:
            self.win.home.apply_widgets()
        self._refresh_look()

    def _apply_theme(self, accent, bg, clock, orb):
        if (bg == "glass") != self.win.glass:
            self._choose_bg(bg)
        self._set_look(accent=accent, background=bg, clock_style=clock, orb_style=orb)

    def _set_widget(self, key, value):
        if not self._loading:
            self._set_look(widgets={key: bool(value)})

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(T.ACCENT), self, "Свой цвет")
        if c.isValid():
            self._set_look(accent=c.name())

    def _add_custom_bg(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Свой фон", "", "Картинки и GIF (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        if path.lower().endswith((".mp4", ".webm", ".avi", ".mkv", ".mov")):
            return
        import shutil
        d = config.data_dir() / "backgrounds"
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():            # храним только один свой фон
            try:
                old.unlink()
            except OSError:
                pass
        ext = os.path.splitext(path)[1].lower() or ".png"
        dst = d / f"custom_{int(time.time())}{ext}"
        try:
            shutil.copyfile(path, dst)
        except OSError:
            dst = path
        T.APPEARANCE["custom_bg"] = str(dst)
        self._choose_bg("custom")

    def _choose_bg(self, key):
        if key == "custom" and not (T.APPEARANCE.get("custom_bg") and
                                    os.path.isfile(T.APPEARANCE.get("custom_bg"))):
            self._add_custom_bg()
            return
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
                it.widget().hide()
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
                it.widget().hide()
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
        lay.addSpacing(14)
        self._caption(lay, "Что SenioreM запускал")
        self.launch_log = label("", 12, role="muted", wrap=True)
        self.launch_log.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.launch_log)
        self._apps_timer = QTimer(self)
        self._apps_timer.timeout.connect(self._apps_poll)

    def _fill_apps(self):
        while self.apps_lay.count():
            it = self.apps_lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        items = sites.all_apps()
        self.apps_count.setText(f"Знаю {len(items)} программ и игр")
        log = sites.LAUNCH_LOG[-8:]
        self.launch_log.setText("\n".join(f"{t}  {n}  —  {why or 'команда'}" for t, n, _tg, why
                                           in reversed(log))
                                or "С момента запуска SenioreM ничего не запускал. Полный список — "
                                   "в файле launches.log в папке %APPDATA%\\SenioreM.")
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

    def _build_scenarios(self, lay):
        from scenario_ui import ScenariosPage
        self.scen_page = ScenariosPage(self)
        lay.addWidget(self.scen_page)

    def _build_companion(self, lay):
        from companion import FigurePreview
        self._title(lay, "Компаньон", "Персонаж над панелью задач. Когда помощник отвечает — "
                    "он оживает и показывает текст. Есть встроенные (Аля, Аки, Мия, Рэй, котёнок, лисёнок), а своих "
                    "можно добавить из архива (.zip) или папки с картинками — например, shimeji.")
        row = QHBoxLayout()
        row.setSpacing(28)
        self.comp_preview = FigurePreview(200)
        row.addWidget(self.comp_preview, 0, Qt.AlignTop)
        self.comp_grid = QGridLayout()
        self.comp_grid.setHorizontalSpacing(10)
        self.comp_grid.setVerticalSpacing(10)
        self.comp_cards = {}
        row.addLayout(self.comp_grid, 1)
        lay.addLayout(row)
        lay.addSpacing(14)
        brow = QHBoxLayout()
        brow.setSpacing(10)
        for title, fn in (("Добавить из архива…", self._comp_add_zip),
                          ("Добавить из папки…", self._comp_add_dir),
                          ("Переименовать", self._comp_rename),
                          ("Удалить персонажа", self._comp_delete),
                          ("Вернуть встроенных", self._comp_restore)):
            b = button(title, "ghost", 13, QFont.Normal)
            b.clicked.connect(fn)
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.comp_status = label("", 13, role="accent", wrap=True)
        lay.addWidget(self.comp_status)
        lay.addSpacing(18)
        self._caption(lay, "Поза")
        prow = QHBoxLayout()
        prow.setSpacing(10)
        self.comp_poses = {}
        from companion import POSES
        for key, title in POSES:
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._set_comp(companion_pose=k))
            prow.addWidget(b)
            self.comp_poses[key] = b
        edit = button("Настроить позы…", "link", 13, QFont.Normal)
        edit.clicked.connect(self._comp_edit_poses)
        prow.addSpacing(8)
        prow.addWidget(edit)
        prow.addStretch(1)
        lay.addLayout(prow)
        lay.addWidget(label("«Сам меняет» — обычно стоит, иногда садится или ложится отдохнуть. "
                            "Какие кадры считать «сидит» и «лежит», можно поправить в «Настроить позы».",
                            12, role="faint", wrap=True))
        lay.addSpacing(18)
        self.t_comp_anim = self._toggle_row(lay, "Всегда двигается",
                                            "Меняет выражения и «дышит». Если выключить — стоит "
                                            "спокойно и оживает только когда говорит.", None)
        self.t_comp_anim.toggled.connect(lambda v: self._set_comp(companion_anim=bool(v)))
        self._caption(lay, "Размер")
        srow = QHBoxLayout()
        srow.setSpacing(10)
        self.comp_sizes = {}
        for px, name in ((110, "Маленький"), (150, "Средний"), (200, "Большой")):
            b = button(name, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=px: self._set_comp(companion_size=v))
            srow.addWidget(b)
            self.comp_sizes[px] = b
        srow.addStretch(1)
        lay.addLayout(srow)
        lay.addSpacing(14)
        lay.addWidget(label("Персонажа можно перетащить мышью, а нажатие на него открывает SenioreM. "
                            "Из архива берутся только картинки — программы из него не запускаются.",
                            12, role="faint", wrap=True))
        lay.addStretch(1)
        self._fill_comp_cards()

    def _fill_comp_cards(self):
        from companion import figures, thumb
        while self.comp_grid.count():
            it = self.comp_grid.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self.comp_cards = {}
        for i, (key, title, desc) in enumerate(figures()):
            c = ThumbCard(title, desc, 150, 190)
            try:
                c.set_pixmap(thumb(key, 300, 380))
            except Exception:  # noqa: BLE001 — испорченный набор: карточка без картинки
                pass
            c.clicked.connect(lambda k=key: self._set_comp(companion=k))
            self.comp_grid.addWidget(c, i // 4, i % 4)
            self.comp_cards[key] = c

    def _comp_import(self, paths):
        if not paths:
            return
        self.comp_status.setText("Добавляю персонажа…")
        QApplication.processEvents()
        import companion
        added, errors = [], []
        for path in paths:
            try:
                added += companion.import_path(path)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{os.path.basename(path)}: {e}")
        self._fill_comp_cards()
        if added:
            self.comp_status.setText("Добавлено: " + ", ".join(n for _p, n in added) +
                                     ". Нажмите на персонажа, чтобы выбрать его.")
            if self.settings is not None and not (self.settings["companion"] or "").startswith("pack:"):
                self._set_comp(companion="pack:" + added[0][0])
        else:
            self.comp_status.setText("Не нашёл картинок персонажа. " + "; ".join(errors))
        self._refresh_comp()

    def _comp_add_zip(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, "Архивы с персонажами", "",
                                                "Архивы (*.zip)")
        self._comp_import(paths)

    def _comp_add_dir(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Папка с картинками персонажа")
        self._comp_import([path] if path else [])

    def _comp_edit_poses(self):
        pid = self._comp_selected_pack()
        if not pid:
            self.comp_status.setText("Сначала выберите персонажа.")
            return
        from companion import PoseDialog
        PoseDialog(self, "pack:" + pid).exec()
        self._refresh_comp()
        self.win.apply_companion()

    def _comp_selected_pack(self):
        kind = (self.settings["companion"] or "") if self.settings is not None else ""
        return kind[5:] if kind.startswith("pack:") else None

    def _comp_rename(self):
        pid = self._comp_selected_pack()
        if not pid:
            self.comp_status.setText("Сначала выберите персонажа.")
            return
        from PySide6.QtWidgets import QInputDialog
        import companion
        name, ok = QInputDialog.getText(self, "Имя персонажа", "Как его зовут:",
                                        text=dict(companion.list_packs()).get(pid, ""))
        if ok and name.strip():
            companion.rename_pack(pid, name.strip())
            companion._PACKS.pop(pid, None)
            self._fill_comp_cards()
            self._refresh_comp()

    def _comp_delete(self):
        pid = self._comp_selected_pack()
        if not pid:
            self.comp_status.setText("Сначала выберите персонажа.")
            return
        import companion
        self._set_comp(companion="none")
        companion.delete_pack(pid)
        self._fill_comp_cards()
        self._refresh_comp()
        self.comp_status.setText("Персонаж удалён.")

    def _comp_restore(self):
        import companion
        added = companion.install_builtin(restore=True)
        self._fill_comp_cards()
        self._refresh_comp()
        self.comp_status.setText("Встроенные персонажи на месте." if not added else
                                 f"Вернул встроенных персонажей: {len(added)}.")

    def _set_comp(self, **changes):
        if self.settings is None or self._loading:
            return
        for k, v in changes.items():
            self.settings.set(k, v)
        self._refresh_comp()
        self.win.apply_companion()
        self._flash()

    def _refresh_comp(self):
        s = self.settings
        from companion import norm_kind
        kind = norm_kind(s["companion"] or "none")
        from companion import figures
        if kind not in self.comp_cards or set(self.comp_cards) != {k for k, _t, _d in figures()}:
            self._fill_comp_cards()          # список персонажей изменился (встроенные, импорт)
        for k, c in self.comp_cards.items():
            c.set_selected(k == kind)
        self.comp_preview.kind = kind
        self.comp_preview.painter.animated = bool(s["companion_anim"])
        self.t_comp_anim.setChecked(bool(s["companion_anim"]))
        size = int(s["companion_size"] or 150)
        for px, b in self.comp_sizes.items():
            b.setChecked(px == size)
        pose = s["companion_pose"] or "auto"
        self.comp_preview.painter.pose = pose
        import companion as _cm
        pack = _cm.get_pack(kind)
        for k, b in self.comp_poses.items():
            b.setChecked(k == pose)
            b.setEnabled(k in ("auto", "stand") or (pack is not None and pack.has(k)))

    def _build_startup(self, lay):
        self._title(lay, "Запуск", "Когда и как открывается SenioreM.")
        self.t_autostart = self._toggle_row(lay, "Запускать вместе с Windows",
                                            "Помощник будет готов сразу после включения компьютера.",
                                            "autostart")
        self.t_admin = self._toggle_row(
            lay, "Работать с правами администратора",
            "Тогда VPN, обход блокировок и другие программы, которым нужны права администратора, "
            "запускаются сразу — без окна «Разрешить изменения». Windows один раз спросит "
            "разрешение. Нажать «Да» в этом окне за вас не может ни одна программа — так устроена "
            "защита Windows, поэтому права выдаются SenioreM заранее. Включайте, только если это "
            "действительно нужно: с правами администратора любая ошибка или вирус на компьютере "
            "могут сделать больше.", None)
        self.t_admin.toggled.connect(self._admin_changed)
        self.admin_status = label("", 13, role="accent", wrap=True)
        lay.addWidget(self.admin_status)
        lay.addSpacing(28)
        # ---- куда скачиваются речь, голос и ИИ
        lay.addWidget(label("Папка для загрузок", 17, QFont.DemiBold))
        lay.addSpacing(4)
        lay.addWidget(label("Здесь лежит всё, что программа скачивает сама: распознавание речи, голос, "
                            "точное распознавание и ИИ (до 3,5 ГБ). Можно перенести на другой диск — "
                            "файлы переедут сами.", 13, role="muted", wrap=True))
        lay.addSpacing(10)
        self.store_path = label("", 14, QFont.DemiBold, wrap=True)
        lay.addWidget(self.store_path)
        lay.addSpacing(8)
        srow = QHBoxLayout()
        self.store_btn = button("Выбрать другую папку…", "ghost", 14)
        self.store_btn.setFixedWidth(260)
        self.store_btn.clicked.connect(self._move_storage)
        srow.addWidget(self.store_btn)
        srow.addStretch(1)
        lay.addLayout(srow)
        self.store_msg = label("", 13, role="accent", wrap=True)
        lay.addWidget(self.store_msg)
        lay.addStretch(1)

    def _refresh_storage(self):
        d = config.local_dir()

        def work():
            size = config.folder_size(d)
            self.bridge_store.emit(f"{d}   ·   занято {size / 1e9:.1f} ГБ   ·   свободно "
                                   f"{config.free_gb(d):.0f} ГБ")
        self.store_path.setText(str(d))
        threading.Thread(target=work, daemon=True).start()

    def _move_storage(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Куда перенести распознавание речи, голос и ИИ",
                                             str(config.local_dir()))
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.basename(d).lower() != "seniorem":
            d = os.path.join(d, "SenioreM")
        err = config.check_storage_path(d)
        if err:
            set_role(self.store_msg, "error")
            self.store_msg.setText(err)
            return
        set_role(self.store_msg, "accent")
        self.store_msg.setText("Переношу файлы… Не закрывайте программу.")
        self.store_btn.setEnabled(False)
        try:
            ai.ENGINE.stop()              # движок ИИ держит файл модели — останавливаем
        except Exception:  # noqa: BLE001
            pass

        def work():
            try:
                err2 = config.move_storage(d, lambda f, t: self.bridge_store.emit("…" + t))
            except Exception as e:  # noqa: BLE001
                err2 = f"Не получилось перенести: {e}"
            self.bridge_store.emit("__done__" + err2)
        threading.Thread(target=work, daemon=True).start()

    def _on_store(self, text):
        if text.startswith("__done__"):
            err = text[8:]
            self.store_btn.setEnabled(True)
            set_role(self.store_msg, "error" if err else "accent")
            self.store_msg.setText(err or "Готово. Перезапустите SenioreM, чтобы всё работало из новой папки.")
            if not err:
                self._refresh_storage()
                QTimer.singleShot(1500, self.win.restart)
            return
        if text.startswith("…"):
            self.store_msg.setText("Переношу: " + text[1:])
            return
        self.store_path.setText(text)

    def _admin_changed(self, on):
        if self._loading:
            return
        import elevate
        if not on:
            elevate.disable()
            self.admin_status.setText("Выключено. После перезапуска SenioreM будет работать как обычно.")
            return
        self.admin_status.setText("Подтвердите разрешение в окне Windows…")

        def work():
            ok, msg = elevate.enable()
            self.ai_bridge.admin_done.emit(ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def _admin_done(self, ok, msg):
        self.admin_status.setText(msg)
        if not ok:
            self._loading = True
            self.t_admin.setChecked(False)
            self._loading = False
            return
        import elevate
        if elevate.relaunch():
            QTimer.singleShot(600, self.win.force_close)

    def _build_account(self, lay):
        self._title(lay, "Аккаунт", "Аватар, логин, пароль и выход.")
        top = QHBoxLayout()
        top.setSpacing(18)
        self.acc_avatar = label("", 34, QFont.DemiBold)
        self.acc_avatar.setAlignment(Qt.AlignCenter)
        self.acc_avatar.setFixedSize(88, 88)
        self.acc_avatar.setProperty("role", "bigavatar")
        self.acc_avatar.setStyleSheet("border-radius: 44px;")
        top.addWidget(self.acc_avatar)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addStretch(1)
        self.acc_email = label("", 19, QFont.DemiBold)
        col.addWidget(self.acc_email)
        brow = QHBoxLayout()
        brow.setSpacing(10)
        b_av = button("Изменить аватар", "ghost", 13)
        b_av.clicked.connect(self._change_avatar)
        brow.addWidget(b_av)
        b_login = button("Изменить логин", "ghost", 13)
        b_login.clicked.connect(lambda: self.login_box.setVisible(not self.login_box.isVisible()))
        brow.addWidget(b_login)
        brow.addStretch(1)
        col.addLayout(brow)
        col.addStretch(1)
        top.addLayout(col, 1)
        lay.addLayout(top)
        lay.addSpacing(14)
        self.login_box = QWidget()
        lb = QVBoxLayout(self.login_box)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setSpacing(10)
        lb.addWidget(label("Новый логин", 17, QFont.DemiBold))
        lr = QHBoxLayout()
        lr.setSpacing(18)
        self.l_new = field("новый логин")
        self.l_pass = field("пароль для подтверждения", True)
        lr.addWidget(self.l_new)
        lr.addWidget(self.l_pass)
        lb.addLayout(lr)
        self.l_msg = label("", 13, role="error", wrap=True)
        lb.addWidget(self.l_msg)
        l_ok = button("Сохранить логин", "ghost", 14)
        l_ok.setFixedWidth(200)
        l_ok.clicked.connect(self._change_login)
        lb.addWidget(l_ok, 0, Qt.AlignLeft)
        self.login_box.setVisible(False)
        lay.addWidget(self.login_box)
        lay.addSpacing(24)
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

    def _letter(self):
        return ((self.settings["name"] if self.settings is not None else "") or self.email or "?")[:1].upper()

    def _show_avatar(self):
        import avatars
        v = self.settings["avatar"] if self.settings is not None else ""
        avatars.apply(self.big_avatar, v, self._letter(), 70)
        avatars.apply(self.acc_avatar, v, self._letter(), 86)

    def _change_avatar(self):
        import avatars
        if self.settings is None:
            return
        v = avatars.AvatarDialog.ask(self, self.settings["avatar"] or "", self.email)
        if v is None:
            return
        self.settings.set("avatar", v)
        self._show_avatar()
        self.account_changed.emit(self.email)

    def _change_login(self):
        try:
            new = self.store.rename(self.email, self.l_new.text(), self.l_pass.text())
        except AuthError as e:
            set_role(self.l_msg, "error")
            self.l_msg.setText(str(e))
            return
        if self.settings is not None:          # настройки уже лежат под новым именем
            import hashlib
            self.settings.email = new
            self.settings.path = self.settings.path.with_name(
                hashlib.sha1(new.encode()).hexdigest()[:16] + ".json")
            self.settings.save()
        self.email = new
        self.l_new.clear()
        self.l_pass.clear()
        self.acc_email.setText(new)
        if not (self.settings["name"] if self.settings is not None else ""):
            self.who.setText(new)
        set_role(self.l_msg, "accent")
        self.l_msg.setText(f"Логин изменён. Теперь входите как «{new}».")
        self._show_avatar()
        self.account_changed.emit(new)

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
        self._caption(lay, "Как общается помощник")
        trow = QHBoxLayout()
        trow.setSpacing(10)
        self.talk_buttons = {}
        tgrp = QButtonGroup(self)
        for key, title, desc in (("polite", "Вежливый", "Дружелюбно и спокойно"),
                                 ("rude", "Дерзкий", "Подкалывает и может ругаться в ответ (18+)")):
            b = button(title, "ghost", 14, QFont.Normal)
            b.setCheckable(True)
            b.setFixedWidth(220)
            b.setToolTip(desc)
            b.clicked.connect(lambda _=False, k=key: (self._set("talk_mode", k), self._refresh_talk()))
            tgrp.addButton(b)
            trow.addWidget(b)
            self.talk_buttons[key] = b
        trow.addStretch(1)
        lay.addLayout(trow)
        lay.addWidget(label("В дерзком режиме на оскорбление помощник сначала делает предупреждение, "
                            "а если обидеть его снова — включается шутка. В вежливом шутка включается "
                            "сразу.", 12, role="faint", wrap=True))
        lay.addSpacing(24)
        self._caption(lay, "Шутка на оскорбления")
        self.t_joke_shut = self._toggle_row(
            lay, "Выключать компьютер после шутки",
            "Если оскорбить помощника, он шутит про «удаление Windows» и показывает плашки. "
            "С этой галочкой в конце компьютер мягко выключится — Windows даст время сохранить "
            "работу, а выключение можно отменить командой shutdown /a. По умолчанию выключено.",
            "joke_shutdown")
        lay.addSpacing(24)
        repo = self.cfg.get("update_repo") or ""
        if repo:
            self._caption(lay, "Оценить SenioreM")
            lay.addWidget(label("Если программа нравится — поставьте звезду проекту на GitHub (кнопка "
                                "«★ Star» вверху страницы, нужен аккаунт GitHub). А если что-то не так — "
                                "напишите отзыв: мы его прочитаем.", 13, role="muted", wrap=True))
            lay.addSpacing(12)
            r = QHBoxLayout()
            r.setSpacing(12)
            star = button("★  Оценить на GitHub", "primary", 14)
            star.setFixedWidth(260)
            star.clicked.connect(lambda: webbrowser.open(f"https://github.com/{repo}"))
            r.addWidget(star)
            fb = button("Написать отзыв", "ghost", 14, QFont.Normal)
            fb.setFixedWidth(220)
            fb.clicked.connect(lambda: webbrowser.open(
                f"https://github.com/{repo}/issues/new?title=" + urllib.parse.quote("Отзыв о SenioreM")))
            r.addWidget(fb)
            r.addStretch(1)
            lay.addLayout(r)
        lay.addStretch(1)

    # ---------- показ ----------
    def load(self, email, settings):
        self.email, self.settings = email, settings
        self._loading = True
        name = settings["name"]
        self.who.setText(name or email)
        self._show_avatar()
        created = self.store.created(email)
        self.since.setText(("с нами с " + datetime.datetime.fromtimestamp(created).strftime("%d.%m.%Y"))
                           if created else email)
        self.f_name.setText(name)
        self.f_address.setText(settings["address"])
        self.f_wake.setText(settings["wake_reply"])
        ww = settings["wake_words"] or ""
        self.f_words.setText("" if ww.replace(" ", "") == "сеньор,сеньер,синьор" else ww)
        self.f_stop.setText(settings["stop_words"] or "стоп")
        custom = settings.name not in NAME_PRESETS
        self.f_ai_name.setText(settings.name if custom else "")
        self._refresh_name()
        for k, b in self.speed_buttons.items():
            b.setChecked(k == (settings["voice_speed"] or "normal"))
        self.voice_status.setText("")
        self.t_speak.setChecked(bool(settings["speak_replies"]))
        self.t_chime.setChecked(bool(settings["chime"]))
        self.t_wake_reply.setChecked(bool(settings["speak_wake_reply"]))
        if hasattr(self, "t_joke_shut"):
            self.t_joke_shut.setChecked(bool(settings["joke_shutdown"]))
            self._refresh_talk()
        self.t_autostart.setChecked(bool(settings["autostart"]))
        try:
            import elevate
            self.t_admin.setChecked(elevate.enabled())
            self.admin_status.setText("Сейчас SenioreM работает с правами администратора."
                                      if elevate.is_admin() else "")
        except Exception:  # noqa: BLE001
            pass
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
        self._refresh_comp()
        self.scen_page.load(settings)
        self._loading = False
        self._refresh_preview()

    def show_section(self, key):
        self.last_section = key                   # при следующем входе в настройки — сюда же
        self.nav_buttons[key].setChecked(True)
        switch_page(self.pages, self.page_widgets[key], 180)
        if key == "look":
            self._refresh_look()
        if key == "startup":
            self._refresh_storage()
        if key == "city":
            self._refresh_city()
        if key == "apps":
            self._fill_apps()
        if key == "wake":
            self._fill_mics()
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
        self.models_loading = bool(models.get("_background"))   # быстрый запуск: модели грузятся в фоне
        self._pending_greeting = ""
        self.companion = None
        self.bridge = Bridge()
        self.bridge.mail_done.connect(self._mail_done)
        self.bridge.comps_added.connect(self._on_comps_added)
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
        self.chat = ChatScreen(self)
        self.chat.back_requested.connect(self._back_home)
        self.chat.send_requested.connect(
            lambda txt: self.home.execute(txt, typed=True, sink=self.chat.receive))
        self.chat.send_images.connect(self._chat_images)
        self.chat.draw_requested.connect(self._chat_draw)
        self.home.bridge.chat_reply.connect(lambda t, im: self.chat.receive(t, im))
        self.home.bridge.chat_partial.connect(self.chat.partial)
        for w in (self.auth, self.home, self.profile, self.chat):
            self.stack.addWidget(w)

        a = self.auth
        a.register.submit.clicked.connect(self._register)
        a.register.to_login.clicked.connect(lambda: self._go_auth(a.login))
        a.login.submit.clicked.connect(self._login)
        a.login.to_register.clicked.connect(lambda: self._go_auth(a.register))
        a.verify.submit.clicked.connect(self._verify)
        a.verify.resend.clicked.connect(self._resend)
        a.verify.back.clicked.connect(lambda: self._go_auth(a.register))
        self.home.profile_requested.connect(
            lambda: self.open_profile(getattr(self.profile, "last_section", "") or "address"))
        # Esc: из настроек и чата — назад, на главном экране — «Закрыть SenioreM?»
        from PySide6.QtGui import QShortcut
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.setContext(Qt.WindowShortcut)
        esc.activated.connect(self._on_escape)
        self.profile.back_requested.connect(self._back_home)
        self.profile.logout_requested.connect(self._logout)
        self.profile.account_changed.connect(self._account_changed)

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
                # облачный ИИ (если настроен) — сразу умный и ничего не нужно скачивать
                s.set("ai_mode", "cloud" if ai.cloud_url() else ai.recommended_kind())
        control.AI_PICK = lambda req, opts: ai.pick_option(req, opts, self.settings)
        if ai.cloud_url():                    # лимиты облака (их задаёт владелец на сервере)
            threading.Thread(target=lambda: ai.server_info(True), daemon=True).start()
        # честная просьба оценить — один раз, после нескольких запусков
        s.set("launches", int(s["launches"] or 0) + 1)
        if int(s["launches"]) >= 6 and not s["rate_asked"] and self.cfg.get("update_repo"):
            s.set("rate_asked", True)
            QTimer.singleShot(20000, self._ask_rating)
        if not s["chime_off_v2"]:             # писк после обращения мешал — выключаем один раз
            s.set("chime_off_v2", True)
            s.set("chime", False)
        if ai.cloud_url() and not s["cloud_switched"]:
            # появился облачный сервер — один раз переводим на него (свой сервер не трогаем)
            s.set("cloud_switched", True)
            if s["ai_mode"] != "api":
                s.set("ai_mode", "cloud")
                s.set("ai_enabled", True)
        mode = s["ai_mode"] or "smart"
        if os.environ.get("SENIOREM_NO_DOWNLOADS"):
            pass
        elif s["ai_enabled"] and mode not in ("api", "cloud"):
            # тяжёлое грузим не всё сразу, а по очереди — компьютер не «тормозит» при запуске:
            # точное распознавание — через 8 секунд, ИИ — через 25
            if ai.local_ready(mode):
                QTimer.singleShot(25000, lambda: threading.Thread(
                    target=lambda: self._warm_ai(mode), daemon=True).start())
            else:
                QTimer.singleShot(25000, lambda: ai.DOWNLOADS.start(mode))
        # точное распознавание: в облаке (если настроено) — тогда на компьютер ничего не грузим
        if not asr.cloud_url() and asr.RECOGNIZER.model is None \
                and not os.environ.get("SENIOREM_NO_DOWNLOADS"):
            QTimer.singleShot(8000, asr.DOWNLOADS.start)
        switch_page(self.stack, self.home)
        self.home.start(email, s)
        try:
            import companion
            companion.install_builtin()
        except Exception:  # noqa: BLE001
            pass
        self.apply_companion()
        self._auto_import_companions()
        # уборка в фоне: старая история чата и команд, кэш голоса, большие журналы
        import housekeeping
        try:
            housekeeping.trim_settings(s)
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=housekeeping.run, daemon=True).start()
        if not self.greeted:
            self.greeted = True
            who = s["name"] or s["address"]
            hello = greeting(datetime.datetime.now().hour)
            text = f"{hello}{', ' + who if who else ''}. Я на связи."
            if self.models_loading:
                self._pending_greeting = text      # скажем, когда голос загрузится (через секунду)
            else:
                self.speaker.say(text)

    @staticmethod
    def _warm_ai(mode):
        config.low_priority_thread()
        try:
            ai.ENGINE.start_local(mode)
        except Exception:  # noqa: BLE001 — запустится при первом вопросе
            pass
        # есть видеокарта — докачиваем для неё движок и переключаемся: ответы в разы быстрее
        try:
            if ai.gpu_usable() and ai.server_exe(gpu=True) is None and ai.download_gpu():
                if ai.ENGINE.lock.acquire(timeout=60):
                    try:
                        ai.ENGINE.stop()
                        ai.ENGINE.start_local(mode)
                    finally:
                        ai.ENGINE.lock.release()
        except Exception:  # noqa: BLE001
            pass

    def apply_companion(self):
        s = self.settings
        from companion import norm_kind
        kind = norm_kind((s["companion"] if s is not None else "none") or "none")
        if kind == "none" or os.environ.get("SENIOREM_NO_COMPANION"):
            if self.companion is not None:
                self.companion.hide()
            return
        if self.companion is None:
            from companion import CompanionWindow
            self.companion = CompanionWindow(on_click=self.bring_to_front,
                                             on_remove=self._remove_companion,
                                             on_settings=lambda: (self.smooth_restore(),
                                                                  self.open_profile("companion")))
            self.speaker.speaking.connect(self.companion.set_speaking)
            self.speaker.said.connect(lambda t: self.companion.say(t, 4 + len(t) / 14))
        self.companion.configure(kind, bool(s["companion_anim"]), int(s["companion_size"] or 150),
                                 s["companion_pose"] or "auto")
        self.companion.show()
        self.companion.raise_()

    def _auto_import_companions(self):
        """Архивы с персонажами из «Загрузок»/рабочего стола добавляются сами."""
        if os.environ.get("SENIOREM_NO_DOWNLOADS"):
            return

        def work():
            config.low_priority_thread()
            time.sleep(12)               # не в самый момент запуска
            try:
                import companion
                added = companion.auto_import()
            except Exception:  # noqa: BLE001
                added = []
            if added:
                self.bridge.comps_added.emit(added)
        threading.Thread(target=work, daemon=True).start()

    def _on_comps_added(self, added):
        s = self.settings
        if s is None:
            return
        import companion
        if companion.norm_kind(s["companion"]) == "none":
            s.set("companion", "pack:" + added[0][0])
            self.apply_companion()
        if self.companion is not None:
            self.companion.say("Добавил персонажей из «Загрузок»: " +
                               ", ".join(n for _p, n in added[:5]), 10)
        try:
            self.profile._fill_comp_cards()
        except Exception:  # noqa: BLE001
            pass

    def _remove_companion(self):
        """«Убрать» в меню персонажа: выключаем компаньона (вернуть — профиль → «Компаньон»)."""
        if self.settings is not None:
            self.settings.set("companion", "none")
        self.apply_companion()

    def _chat_images(self, text, images):
        """Сообщение с фото: ИИ смотрит на картинки (или читает текст на них)."""
        s = self.settings

        def work():
            try:
                parts = []

                def on_sentence(x):
                    parts.append(x)
                    self.home.bridge.chat_partial.emit(" ".join(parts))
                reply = ai.ENGINE.ask(text, s, images=images, prefer=s["chat_ai"] or "auto", chat=True,
                                      on_sentence=on_sentence)
            except ai.AIError as e:
                reply = str(e)
            except Exception as e:  # noqa: BLE001
                reply = f"Не получилось посмотреть фото: {e}"
            self.home.bridge.chat_reply.emit(reply, None)
        threading.Thread(target=work, daemon=True).start()

    def _chat_draw(self, prompt):
        """«Нарисуй …» — картинка по описанию прямо в чат."""
        s = self.settings

        def work():
            import imagegen
            try:
                path = imagegen.generate(prompt, s)
                self.home.bridge.chat_reply.emit(f"Готово: {prompt}", [path])
            except Exception as e:  # noqa: BLE001
                self.home.bridge.chat_reply.emit(str(e), None)
        threading.Thread(target=work, daemon=True).start()

    def open_chat(self):
        if self.settings is None:
            return
        self.chat.load(self.settings, self.settings.name)
        switch_page(self.stack, self.chat)
        for ms in (0, 60, 300):
            QTimer.singleShot(ms, hide_stray_windows)

    def open_profile(self, section="address"):
        if self.settings is None:
            return
        self.profile.load(self.email, self.settings)
        self.profile.show_section(section)
        switch_page(self.stack, self.profile)

    def _account_changed(self, email):
        self.email = email
        self.home.start(email, self.settings)

    def _back_home(self):
        switch_page(self.stack, self.home)
        self.home.start(self.email, self.settings)

    def _logout(self):
        if self.companion is not None:
            self.companion.hide()
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

    def models_ready(self, result):
        """Фоновая загрузка закончилась: голос и распознавание готовы."""
        self.models_loading = False
        if result.get("voice") is not None:
            self.speaker._piper = result["voice"]
        self.home.set_model(result.get("model"))
        startup_mark("распознавание и голос загружены (в фоне)")
        if self._pending_greeting:
            self.speaker.say(self._pending_greeting)
            self._pending_greeting = ""

    def models_failed(self, msg):
        self.models_loading = False
        self.home.set_model(None)
        self.home._on_failed(msg)

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

    def bring_to_front(self):
        """Нажали на персонажа: окно уже открыто — просто показываем, без мигания."""
        if self.isMinimized() or not self.isVisible():
            self.smooth_restore()
            return
        self.raise_()
        self.activateWindow()

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
        if e.type() in (QEvent.ActivationChange, QEvent.WindowStateChange) and self.isActiveWindow() \
                and not self.isMinimized() and self.settings is not None:
            QTimer.singleShot(500, self.home.maybe_check_update)   # развернули — нет ли обновления
        super().changeEvent(e)

    def _ask_rating(self):
        if self.stack.currentWidget() is not self.home or not self.isVisible():
            return
        dlg = ConfirmDialog(self, "Нравится SenioreM?",
                            "Оцените проект звездой на GitHub — это честно и очень помогает его "
                            "развивать. Займёт десять секунд.", yes="★  Оценить", no="Не сейчас",
                            yes_role="primary")
        if dlg.exec():
            webbrowser.open(f"https://github.com/{self.cfg.get('update_repo')}")

    def joke_crash(self):
        """Шутка: окно исчезает, на 20 секунд — «синий экран», потом по экрану разлетаются
        десятки плашек (каждую можно закрыть), ещё через 20 секунд SenioreM закрывается.
        Компьютеру ничего не делается и управление всегда остаётся у человека."""
        ai.ENGINE.stop()
        if self.companion is not None:
            self.companion.hide()
        self.hide()
        self._bsod = FakeBSOD()
        self._bsod.finished.connect(self._joke_swarm)   # вышли из синего экрана → полетели плашки
        self._bsod.showFullScreen()

    def _joke_swarm(self):
        """Десятки шуточных плашек по всему экрану. Каждую можно закрыть, все сами исчезнут за 20 с."""
        if getattr(self, "_swarm_started", False):
            return
        self._swarm_started = True
        self._swarm = []
        self._swarm_geo = QGuiApplication.primaryScreen().availableGeometry()
        self._swarm_timer = QTimer(self)
        self._swarm_timer.timeout.connect(self._spawn_popup)
        self._swarm_timer.start(55)                 # быстрее плодятся
        QTimer.singleShot(40000, self._joke_end)    # и держатся 40 секунд

    def _spawn_popup(self):
        import random
        self._swarm = [p for p in self._swarm if p.isVisible()]
        if len(self._swarm) >= 120:                 # в 3 раза больше плашек
            return
        p = JokePopup()
        g = self._swarm_geo
        p.move(random.randint(g.left(), max(g.left(), g.right() - p.width())),
               random.randint(g.top(), max(g.top(), g.bottom() - p.height())))
        p.show()
        p.raise_()
        self._swarm.append(p)

    def _joke_end(self):
        try:
            self._swarm_timer.stop()
        except Exception:  # noqa: BLE001
            pass
        for p in list(getattr(self, "_swarm", [])):
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
        # фейковое «выключение»: «Завершение работы…» ~8 с, затем чёрный экран ~10 с
        self._fake_off = FakeShutdown()
        self._fake_off.showFullScreen()
        QTimer.singleShot(18500, self._joke_after_off)

    def _joke_after_off(self):
        if getattr(self, "_fake_off", None) is not None:
            self._fake_off.close()
            self._fake_off = None
        # финальная плашка «Сам ты …» (эхо оскорбления)
        echo = self._echo_insult(getattr(self, "_last_insult", "ты лох"))
        pop = JokePopup(echo.rstrip(".") + "!")
        g = QGuiApplication.primaryScreen().availableGeometry()
        pop.move(g.center().x() - pop.width() // 2, g.center().y() - pop.height() // 2)
        pop.destroyed.connect(self._joke_really_end)
        pop.show()
        pop.raise_()
        self._final_pop = pop
        QTimer.singleShot(8000, self._joke_really_end)

    def _joke_really_end(self):
        # по желанию (профиль → «О программе», по умолчанию выкл.) — мягко выключить компьютер
        if self.settings is not None and self.settings["joke_shutdown"] and sys.platform == "win32":
            try:
                import subprocess
                subprocess.Popen(["shutdown", "/s", "/t", "25", "/c",
                                  "Сеньор обиделся и выключает компьютер. Передумали? Откройте "
                                  "командную строку и введите: shutdown /a"],
                                 creationflags=0x08000000)
            except Exception:  # noqa: BLE001
                pass
        os._exit(0)

    def _on_escape(self):
        cur = self.stack.currentWidget()
        if cur is self.profile or cur is self.chat:
            self._back_home()
        elif cur is self.home:
            self.request_close()

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
        if self.companion is not None:
            self.companion.close()
        self.speaker.shutdown()
        ai.ENGINE.stop()
        super().closeEvent(e)


# ================================================================== запуск
def _err_log(text):
    try:
        with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


startup_mark = config.startup_mark


def _install_error_log():
    log = config.data_dir() / "error.log"

    def hook(t, v, tb):
        with open(log, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") +
                    "".join(traceback.format_exception(t, v, tb)) + "\n")
        startup_mark(f"ОШИБКА: {t.__name__}: {v}")
    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    # «тихие» падения внутри библиотек (распознавание, голос, ИИ) — тоже в журнал
    try:
        import faulthandler
        global _CRASH_FILE
        _CRASH_FILE = open(config.data_dir() / "crash.log", "a", encoding="utf-8")
        _CRASH_FILE.write(f"--- запуск {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()}\n")
        _CRASH_FILE.flush()
        faulthandler.enable(_CRASH_FILE)
    except Exception:  # noqa: BLE001
        pass
    # журнал запуска не растёт бесконечно
    try:
        p = config.data_dir() / "startup.log"
        if p.is_file() and p.stat().st_size > 200_000:
            p.write_text(p.read_text(encoding="utf-8", errors="ignore")[-50_000:], encoding="utf-8")
    except OSError:
        pass


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
        # произношение: понимает ли голос ударения и как он читает слова
        try:
            fx = tts._stress_fixes(voice, "Начинаю поиск в интернете, щавель")
            log(f"stress fixes: {fx}")
            sw = str(config.local_dir() / "selftest_stress.wav")
            tts.synth_wav(voice, "Начинаю поиск в интернете.", sw)
            log(f"stress synth {tts.wav_seconds(sw):.2f}s")
            long = "Сегодня в Магадане облачно. Температура минус три градуса. Ветер слабый, осадков не будет."
            raw = str(config.local_dir() / "selftest_raw.wav")
            import speechtext as _st
            with wave.open(raw, "wb") as wf:
                voice.synthesize_wav(_st.prepare(long), wf, syn_config=tts._syn_config(1.0))
            t_raw = tts.wav_seconds(raw)
            import numpy as _np
            with wave.open(raw, "rb") as _w:
                _a = _np.frombuffer(_w.readframes(_w.getnframes()), _np.int16).astype(_np.float32)
                _sr = _w.getframerate()
            _win = _sr // 100
            _r = _np.sqrt((_a[:len(_a) // _win * _win].reshape(-1, _win) ** 2).mean(axis=1))
            _q = _r < max(60.0, float(_np.percentile(_r, 95)) * 0.03)
            gaps, run = [], 0
            for v in _q:
                if v:
                    run += 1
                else:
                    if run >= 8:
                        gaps.append(run * 10)
                    run = 0
            log(f"pauses in raw speech (ms): {gaps}; trailing {run * 10}")
            tts._tighten(raw)
            log(f"pause test: raw {t_raw:.2f}s -> tight {tts.wav_seconds(raw):.2f}s")
        except Exception as e:  # noqa: BLE001
            log(f"probe error: {e!r}")
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
        try:
            import system as _sys2
            log(f"pc info: {_sys2.pc_info()}")
        except Exception as e:  # noqa: BLE001
            log(f"WARN pc info: {e!r}")
        try:
            import control as _ctl2
            ids = _ctl2.video_ids(_ctl2.search_url("lofi hip hop"))
            log(f"youtube ids: {len(ids)} {ids[:3]}")
            log(f"youtube channel а4: {_ctl2._yt_channel('а4')}")
            pop = _ctl2.video_ids(_ctl2.search_url("а4", "popular"))
            log(f"youtube popular а4: {pop[:3]}")
            log(f"parse: {_ctl2.parse('включи самый популярный ролик а4')}")
        except Exception as e:  # noqa: BLE001
            log(f"WARN youtube: {e!r}")
        # уже открытая программа: найти окно, свернуть, развернуть, закрыть (на блокноте)
        try:
            import procs
            import subprocess as _sp
            np_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "notepad.exe")
            np = _sp.Popen([np_path])
            time.sleep(3)
            tgt = ("path", np_path)
            wins, rest = procs.find("блокнот", tgt)
            log(f"procs find: {wins} rest={rest}")
            if wins:
                import ctypes as _ct
                _ct.windll.user32.ShowWindow(wins[0].hwnd, 6)
                time.sleep(0.7)
                log(f"procs bring_up after minimize: {procs.bring_up('блокнот', tgt)}")
                time.sleep(0.5)
                log(f"procs bring_up again: {procs.bring_up('блокнот', tgt)}")
                try:
                    import control as _ctl
                    time.sleep(0.5)
                    log(f"uia find File: {_ctl.find_uia(wins[0].hwnd, 'File')}")
                    rect = _ctl._rect(wins[0].hwnd)
                    words = _ctl.ocr_words(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
                    log(f"ocr words: {len(words)} {[w['t'] for w in words[:8]]}")
                    log(f"ocr stderr: {_ctl.OCR_ERR!r}")
                    log(f"ocr find Edit: {_ctl.find_ocr(rect, 'Edit')}")
                except Exception as e:  # noqa: BLE001
                    log(f"WARN control: {e!r}")
            n, names = procs.close("блокнот", tgt)
            time.sleep(1.5)
            log(f"procs close: {n} {names}; still running: {np.poll() is None}")
            if np.poll() is None:
                np.kill()
        except Exception as e:  # noqa: BLE001
            log(f"WARN procs: {e!r}")
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
            log(f"OK ai server {(_t.time() - t0):.1f}s (gpu={_ai.ENGINE.gpu}, threads={_ai._threads()})")
            # проверка движка для видеокарты: на сервере сборки её нет — должен сработать запасной путь
            try:
                os.environ["SENIOREM_FORCE_GPU"] = "1"
                _ai._GPU = None
                t1 = _t.time()
                got = _ai.download_gpu()
                log(f"gpu engine download: {got} {(_t.time() - t1):.0f}s")
                _ai.ENGINE.stop()
                _ai.ENGINE.start_local("fast", timeout=300)
                log(f"ai after gpu try: gpu={_ai.ENGINE.gpu} failed_flag={_ai._gpu_failed_flag().exists()}")
            except Exception as e:  # noqa: BLE001
                log(f"gpu try error: {e!r}")
            finally:
                os.environ.pop("SENIOREM_FORCE_GPU", None)
                _ai._GPU = None
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
        splash._show_storage(config.local_dir())
        shot(splash, "01-splash-storage")
        splash.close()
        win = MainWindow(config.load_config(), {})
        win.resize(1920, 1080)
        win.show()
        shot(win, "02-register")
        win.store.register("tester", "secret1", "secret1")
        win._enter("tester")
        win.open_profile("companion")           # встроенные персонажи видны сразу, без выбора
        n_cards = len(win.profile.comp_cards)
        log.append(f"companion cards on first open: {n_cards}")
        if n_cards < 7:
            raise RuntimeError("встроенные персонажи не показаны в списке")
        win._back_home()
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
        h._show_downloads(1234)
        h._upd_version = "9.9"
        h._update_downloaded("")
        h.upd_btn.show()
        shot(win, "03-home-blue")
        for _st, _n, _d in widgets.SYS_STYLES:
            T.set_appearance(app, sys_style=_st)
            h.w_system.refresh()
            pump(600)
            h.w_system.grab().save(os.path.join(out_dir, f"03-system-{_st}.png"))
        T.set_appearance(app, sys_style="bars")
        for _st, _n, _d in SUB_STYLES:
            T.set_appearance(app, subs_style=_st)
            h.heard.setText("Сеньор, запусти кс", _st == "karaoke")
            pump(700)
            h.heard.grab().save(os.path.join(out_dir, f"03-subs-{_st}.png"))
        T.set_appearance(app, subs_style="glass")
        h._show_heard("Расскажи анекдот", False)
        bsod = FakeBSOD()
        bsod.resize(1280, 720)
        bsod._t0 -= 11
        bsod._poke = "Esc не поможет. И Alt+F4 тоже."
        bsod._poke_until = 10 ** 12
        pump(300)
        bsod.grab().save(os.path.join(out_dir, "11-bsod.png"))
        bsod.close()
        pops = [JokePopup() for _ in range(6)]
        for i, pp in enumerate(pops):
            pp.move(40 + (i % 3) * 340, 40 + (i // 3) * 170)
            pp.show()
        pump(400)
        win.grab().save(os.path.join(out_dir, "11-swarm.png"))
        for pp in pops:
            pp.close()
        fsh = FakeShutdown()
        fsh.resize(1280, 720)
        pump(300)
        fsh.grab().save(os.path.join(out_dir, "11-shutdown.png"))
        fsh.close()
        win.open_profile("about")
        pump(300)
        win.grab().save(os.path.join(out_dir, "05-profile-about.png"))
        win._back_home()
        for i, (tname, acc, bg, clock, orb) in enumerate(T.THEMES):
            T.set_appearance(app, accent=acc, background=bg, clock_style=clock, orb_style=orb)
            h.apply_widgets()
            t0 = time.perf_counter()
            win.grab()
            log.append(f"frame {bg}: {(time.perf_counter() - t0) * 1000:.0f} ms")
            shot(win, f"04-home-{i}-{bg}")
        T.set_appearance(app, accent="#38BDF8", background="space", clock_style="digital",
                         orb_style="jarvis")
        h.apply_widgets()
        win.settings.set("scenarios", [
            {"id": "game", "name": "Игровой режим", "phrases": ["игровой режим", "давай поиграем"],
             "steps": [{"type": "app", "name": "Steam", "target": ["url", "steam://open/main"], "admin": False},
                       {"type": "app", "name": "zapret-discord-youtube", "target": ["path", "C:\\zapret"],
                        "admin": True},
                       {"type": "vpn"}, {"type": "command", "text": "громкость 40"}]},
            {"id": "home", "name": "Я дома", "phrases": ["я дома"],
             "steps": [{"type": "site", "url": "https://music.yandex.ru"}]}])
        for sec in ("look", "scenarios", "city", "voice", "apps", "ai", "name", "wake", "startup"):
            win.open_profile(sec)
            shot(win, f"05-profile-{sec}")
        # аккаунт: аватар, смена логина, окно выбора аватара
        win.settings.set("avatar", "preset:fox")
        win.open_profile("account")
        win.profile.login_box.setVisible(True)
        win.profile.l_new.setText("tester2")
        win.profile.l_pass.setText("secret1")
        win.profile._change_login()
        log.append(f"rename: {win.email} / {win.profile.l_msg.text()}")
        shot(win, "05-profile-account")

        def _grab_dialog():
            dlg = QApplication.activeModalWidget()
            if dlg is not None:
                pump(300)
                dlg.grab().save(os.path.join(out_dir, "05-avatar-dialog.png"))
                log.append("05-avatar-dialog")
                dlg.reject()
        QTimer.singleShot(700, _grab_dialog)
        import avatars as _av
        _av.AvatarDialog.ask(win, "preset:fox", win.email)
        win._back_home()
        shot(win, "03-home-avatar")
        # свой фон: картинка-градиент
        from PySide6.QtGui import QImage as _QI, QLinearGradient as _QLG, QPainter as _QPP
        cimg = _QI(1600, 900, _QI.Format_RGB32)
        _qp = _QPP(cimg)
        _g = _QLG(0, 0, 1600, 900)
        _g.setColorAt(0, QColor("#FF6B6B"))
        _g.setColorAt(0.5, QColor("#845EC2"))
        _g.setColorAt(1, QColor("#00C9A7"))
        _qp.fillRect(cimg.rect(), _g)
        _qp.end()
        cpath = os.path.join(tempfile.mkdtemp(), "mybg.png")
        cimg.save(cpath)
        T.set_appearance(app, custom_bg=cpath, background="custom")
        h.apply_widgets()
        shot(win, "04-home-custom-bg")
        T.set_appearance(app, background="space")
        h.apply_widgets()
        win.open_profile("look")
        pump(800)
        look = win.profile.page_widgets["look"].findChild(QScrollArea).widget()
        look.grab().save(os.path.join(out_dir, "05-profile-look-full.png"))
        win._back_home()
        # тестовый персонаж: рисуем кадры (круглый «колобок» с разными глазами) и импортируем
        import tempfile as _tf
        import companion as _cmp
        from PySide6.QtGui import QImage, QPainter as _QP
        tdir = os.path.join(_tf.mkdtemp(), "Kolobok", "img")
        os.makedirs(tdir)
        for k in range(6):
            im = QImage(256, 256, QImage.Format_ARGB32)
            im.fill(Qt.transparent)
            qp = _QP(im)
            qp.setRenderHint(_QP.Antialiasing)
            qp.setBrush(QColor("#F4B942"))
            qp.setPen(QColor("#5A3A10"))
            qp.drawEllipse(48, 40 + (k % 2) * 3, 160, 180)
            qp.setBrush(QColor("#2A1A10"))
            eh = 4 if k == 3 else 18
            qp.drawEllipse(95, 100, 16, eh)
            qp.drawEllipse(145, 100, 16, eh)
            qp.drawArc(100, 140 - k, 56, 30 + k * 2, 200 * 16, 140 * 16)
            qp.end()
            im.save(os.path.join(tdir, f"shime{k + 1}.png"))
        added = _cmp.import_path(os.path.dirname(tdir))
        log.append(f"companion import: {added}")
        if added:
            win.settings.set("companion", "pack:" + added[0][0])
        win.open_profile("companion")
        shot(win, "06-profile-companion")
        for bid in ("builtin-alya", "builtin-aki", "builtin-mia", "builtin-rei", "builtin-cat", "builtin-fox"):
            for pose in ("stand", "sit", "lie"):
                win.settings.set("companion", "pack:" + bid)
                win.settings.set("companion_pose", pose)
                win.apply_companion()
                win.companion.set_speaking(pose == "stand")
                pump(700)
                win.companion.grab().save(os.path.join(out_dir, f"07-{bid}-{pose}.png"))
            log.append(f"07-{bid}")
        win.companion.set_speaking(False)
        win.settings.set("companion_pose", "auto")
        if added:
            win.settings.set("companion", "pack:" + added[0][0])
        win.apply_companion()
        win.companion.say("Привет! Я твой компаньон. Чем помочь?", 20)
        win.companion.set_speaking(True)
        pump(600)
        win.companion.grab().save(os.path.join(out_dir, "06-companion-window.png"))
        win.companion.set_speaking(False)
        from PySide6.QtGui import QImageReader as _QIR
        fmts = sorted(bytes(f).decode() for f in _QIR.supportedImageFormats())
        log.append("image formats: " + " ".join(fmts))
        if "jpg" not in fmts:
            raise RuntimeError("нет модуля JPEG — фото в чате не откроются")
        win.open_chat()
        win.chat.send("Кто такой Павел Дуров?")
        win.chat.receive("Павел Дуров — российский предприниматель, основатель ВКонтакте и Telegram.")
        _ci = QImage(640, 360, QImage.Format_RGB32)
        _ci.fill(QColor("#845EC2"))
        win.chat.attach(qimage=_ci)
        _att = list(win.chat.pending)
        win.chat._clear_pending()
        win.chat._add("Что на картинке?", True, images=_att)
        win.chat.receive("На картинке **фиолетовый** прямоугольник.\n\n- ровный цвет\n- без текста")
        _gp = os.path.join(tempfile.mkdtemp(), "gen.jpg")
        _ci.save(_gp, "JPG")
        win.chat._add("Нарисуй кота", True)
        win.chat.receive("Готово: кот", [_gp])
        win.chat.attach(qimage=_ci)
        win.chat._ai_changed("code")
        shot(win, "08-chat")
        hide_stray_windows()
        strays = [type(w).__name__ for w in app.topLevelWidgets() if w.isVisible()]
        log.append("visible windows: " + ", ".join(strays))
        win._back_home()
        from PySide6.QtCore import QPoint as _QP2, QRect as _QR
        for st, _t, _d in ORB_STYLES:
            T.set_appearance(app, orb_style=st)
            for mode in ("speaking", "armed"):
                h.orb.state = mode
                for _ in range(20):
                    if mode == "armed":
                        h.orb.push_level(0.55)
                    pump(40)
                tl = h.orb.mapTo(win, _QP2(0, 0))
                win.grab(_QR(tl.x() - 30, tl.y() - 30, h.orb.width() + 60,
                             h.orb.height() + 60)).save(os.path.join(out_dir, f"09-orb-{st}-{mode}.png"))
            log.append(f"09-orb-{st}")
        t0, frames = time.perf_counter(), 0
        h.orb.state = "speaking"
        while time.perf_counter() - t0 < 3.0:
            app.processEvents()
            frames += 1
            time.sleep(0.004)
        log.append(f"orb loop: {frames / 3.0:.0f} it/s")
        T.set_appearance(app, orb_style="sphere")
        import timers as _tm
        mgr = _tm.manager()
        mgr.add("timer", 300, "Чай")
        mgr.add("alarm", 600, "Тренировка")
        mgr.add("sleep", 1800, "")       # не выключение — чтобы не трогать компьютер сборки
        pump(800)
        for i, tt in enumerate(mgr.toasts):
            shot(tt, f"10-toast-{i}")
        mgr.toasts[0].finish()
        mgr.toasts[1].finish()
        pump(700)
        shot(mgr.toasts[0], "10-toast-done")
        shot(mgr.toasts[1], "10-toast-alarm")
        mgr.cancel()
        for tt in list(mgr.toasts):
            tt.close()
        win.request_close = lambda: None
        log.append("OK")
    except Exception:  # noqa: BLE001
        log.append("FAIL " + traceback.format_exc())
    with open(os.path.join(out_dir, "uitest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    os._exit(0 if log and log[-1] == "OK" else 1)


_STRAY = ("QWidget", "QLabel", "QFrame", "QPushButton", "Typing", "Thumb", "Bubble", "LogoMark",
          "Toggle", "VolumeMeter", "LimitBar")


def hide_stray_windows():
    """Пустое окно без хозяина (появилось по ошибке) — прячем и пишем в журнал запуска,
    чтобы на экране не мигали лишние «полоски»."""
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        try:
            if w.isVisible() and w.parent() is None and type(w).__name__ in _STRAY \
                    and w.windowType() in (Qt.Window, Qt.Widget):
                startup_mark(f"лишнее окно спрятано: {type(w).__name__} {w.width()}x{w.height()}")
                w.hide()
        except Exception:  # noqa: BLE001
            pass


def _trim_memory():
    """Отдаём системе неиспользуемую память (в «Диспетчере задач» SenioreM занимает меньше)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        import gc
        gc.collect()
        k = ctypes.windll.kernel32
        k.SetProcessWorkingSetSizeEx(k.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1), 0)
    except Exception:  # noqa: BLE001
        pass


def _fast_start_ready():
    """Можно ли открыть главное окно сразу (без окна загрузки): всё скачано, переносить нечего."""
    if os.environ.get("SENIOREM_SPLASH"):
        return False
    try:
        import tts
        data = config._read_json(config._storage_file()) if config._storage_file().is_file() else {}
        if data.get("pending_move") or not config.storage_chosen():
            return False
        return config.model_ready(config.model_dir()) and tts.voice_ready()
    except Exception:  # noqa: BLE001
        return False


def _wait_for_setup(limit=20.0):
    """Идёт установка/обновление SenioreM — ждём её конца, чтобы не было двух окон сразу."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        t0 = time.time()
        while time.time() - t0 < limit:
            busy = False
            for name in ("SenioreMSetup", "Global\\SenioreMSetup"):
                h = k.OpenMutexW(0x00100000, False, name)
                if h:
                    k.CloseHandle(h)
                    busy = True
            if not busy:
                return
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        startup_mark(f"проверка установщика: {e!r}")


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
    _wait_for_setup()
    startup_mark("старт " + " ".join(sys.argv[1:]) + f" (версия {config.load_config().get('version', '?')})")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SenioreM.App")
        except Exception:  # noqa: BLE001
            pass

    try:
        import elevate
        code = elevate.handle_cli()
        if code is not None:
            os._exit(code)
        if elevate.maybe_restart_elevated():   # режим администратора: перезапуск через задачу
            startup_mark("перезапуск с правами администратора — этот процесс закрывается")
            return 0
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("SenioreM")
    apply_app_theme(app)
    stray_timer = QTimer()
    stray_timer.timeout.connect(hide_stray_windows)
    stray_timer.start(1500)
    trim_timer = QTimer()
    trim_timer.timeout.connect(_trim_memory)
    trim_timer.start(90_000)
    QTimer.singleShot(20_000, _trim_memory)

    lock = QLockFile(str(config.data_dir() / "app.lock"))
    if not lock.tryLock(15000 if ("--restart" in sys.argv or "--elevated" in sys.argv) else 100):
        startup_mark("уже запущен другой SenioreM — закрываюсь")
        dlg = ConfirmDialog(None, "SenioreM уже открыт",
                            "Программа уже запущена — второй раз открывать не нужно. "
                            "Перейти к ней?", yes="Перейти к программе", no="Закрыть",
                            yes_role="primary", no_role="secondary")
        if dlg.exec():
            try:
                if sys.platform == "win32":
                    import ctypes
                    ctypes.windll.user32.AllowSetForegroundWindow(-1)   # пусть окно выйдет вперёд
                (config.data_dir() / "show.flag").write_text("1", encoding="utf-8")
            except OSError:
                pass
        return 0
    startup_mark("окно загрузки")

    cfg = config.load_config()
    holder = {}
    # установщик просит закрыться через файл-флажок (так он может закрыть и SenioreM,
    # запущенный с правами администратора, без лишних окон)
    quit_flag = config.data_dir() / "quit.flag"
    try:
        quit_flag.unlink()
    except OSError:
        pass

    show_flag = config.data_dir() / "show.flag"

    def _check_quit():
        if show_flag.exists():                    # второй запуск попросил показать окно
            try:
                show_flag.unlink()
            except OSError:
                pass
            w = holder.get("win")
            if w is not None:
                w.bring_to_front()
        if quit_flag.exists():
            try:
                quit_flag.unlink()
            except OSError:
                pass
            startup_mark("закрываюсь по просьбе установщика (quit.flag)")
            try:
                ai.ENGINE.stop()
            except Exception:  # noqa: BLE001
                pass
            os._exit(0)
    quit_timer = QTimer()
    quit_timer.timeout.connect(_check_quit)
    quit_timer.start(700)

    def open_main(models):
        startup_mark("модели загружены — открываю главное окно")
        try:
            win = MainWindow(cfg, models)
        except Exception:  # noqa: BLE001 — не закрываемся молча: пишем ошибку и показываем её
            err = traceback.format_exc()
            with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + err + "\n")
            startup_mark("ОШИБКА при открытии главного окна: " + err.strip().splitlines()[-1])
            QMessageBox.warning(None, "SenioreM", "Не получилось открыть главное окно.\n\n"
                                + err.strip().splitlines()[-1] + "\n\nПодробности — в файле "
                                "error.log в папке %APPDATA%\\SenioreM.")
            app.quit()
            return
        holder["win"] = win
        win.appear()
        startup_mark("главное окно открыто")

    ai.AI.kill_stale()
    try:
        import procs
        procs.watch_new_processes(90)        # журнал: что открывается вместе с SenioreM и кем
    except Exception:  # noqa: BLE001
        pass
    if _fast_start_ready():
        # всё уже скачано: главное окно — сразу, распознавание и голос грузятся в фоне (1–2 с)
        startup_mark("быстрый запуск: окно сразу, модели — в фоне")
        from splash import Loader
        open_main({"_background": True})
        loader = Loader()
        holder["loader"] = loader
        win = holder.get("win")
        if win is not None:
            loader.loaded.connect(win.models_ready)
            loader.failed.connect(win.models_failed)
        loader.start()
    else:
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
