"""SenioreM — голосовой помощник для Windows."""
import math
import os
import sys
import threading
import traceback

from PySide6.QtCore import QLockFile, QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLineEdit, QMessageBox,
                               QStackedWidget, QVBoxLayout, QWidget)

import actions
import commands
import config
from auth import AuthError, AuthStore, Mailer
from splash import Splash
from voice import Chime, Listener, Speaker
from theme import (ACCENT, ERROR, FAINT, LINE, TEXT, apply_app_theme,
                   button, field, font, label, set_role, window_controls)


class Bridge(QObject):
    """Передаёт результаты из фоновых потоков в интерфейс."""
    mail_done = Signal(str, str)        # email, ошибка ('' если ок)
    action_done = Signal(str, str)      # ответ, действие окна


# ================================================================== вход
class FormBase(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(400)
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
    def __init__(self):
        super().__init__()
        self.head("РЕГИСТРАЦИЯ", "Создать аккаунт",
                  "Подтвердим почту одноразовым кодом — это займёт минуту.")
        self.email = self.add_field("Почта", field("you@mail.ru"))
        self.pw = self.add_field("Пароль", field("минимум 6 символов", True))
        self.pw2 = self.add_field("Повторите пароль", field("", True))
        self.add_error()
        self.submit = button("Получить код")
        self.col.addWidget(self.submit)
        self.col.addSpacing(18)
        self.to_login = button("Уже есть аккаунт?  Войти", "link", 14, QFont.Normal)
        self.col.addWidget(self.to_login, 0, Qt.AlignLeft)
        self.email.returnPressed.connect(self.pw.setFocus)
        self.pw.returnPressed.connect(self.pw2.setFocus)
        self.pw2.returnPressed.connect(self.submit.click)


class LoginForm(FormBase):
    def __init__(self):
        super().__init__()
        self.head("ВХОД", "С возвращением", "Войдите в свой аккаунт SenioreM.")
        self.email = self.add_field("Почта", field("you@mail.ru"))
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
        self.setFixedWidth(440)
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


class AuthScreen(QWidget):
    """Слева — бренд, справа — формы."""

    def __init__(self, win):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 24, 48)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addLayout(window_controls(win))
        root.addLayout(top)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        # бренд
        brand = QVBoxLayout()
        brand.setContentsMargins(56, 0, 40, 0)
        brand.addStretch(1)
        brand.addWidget(label("ГОЛОСОВОЙ ПОМОЩНИК", 11, QFont.DemiBold, "muted", spacing=2.2))
        brand.addSpacing(18)
        brand.addWidget(label("SenioreM", 96, QFont.Light, display=True, spacing=-2))
        brand.addSpacing(18)
        brand.addWidget(label("Скажите «Сеньор» —\nостальное он сделает сам.",
                              22, QFont.Light, "muted", display=True))
        brand.addSpacing(56)
        brand.addWidget(label("«Сеньор, громкость десять»", 15, role="faint"))
        brand.addSpacing(6)
        brand.addWidget(label("«Сеньор, открой браузер»", 15, role="faint"))
        brand.addSpacing(6)
        brand.addWidget(label("«Сеньор, который час»", 15, role="faint"))
        body.addLayout(brand, 1)

        line = QWidget()
        line.setProperty("role", "vline")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setFixedWidth(1)
        body.addWidget(line)

        # формы
        self.stack = QStackedWidget()
        self.register = RegisterForm()
        self.login = LoginForm()
        self.verify = VerifyForm()
        for f in (self.register, self.login, self.verify):
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.addStretch(1)
            hl.addWidget(f, 0, Qt.AlignHCenter)
            hl.addStretch(1)
            self.stack.addWidget(holder)
        body.addWidget(self.stack, 1)

    def show_form(self, form):
        self.stack.setCurrentWidget(form.parentWidget())
        form.show_error("")


# ================================================================== главный экран
class Orb(QWidget):
    def __init__(self, size=300):
        super().__init__()
        self.setFixedSize(size, size)
        self.state = "loading"
        self._level = 0.0
        self._target = 0.0
        self._t = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)

    def push_level(self, v):
        self._target = max(self._target, v)

    def _tick(self):
        self._t += 0.016
        self._level += (self._target - self._level) * 0.22
        self._target *= 0.86
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 6
        breathe = (math.sin(self._t * 2.4) + 1) / 2

        colors = {"idle": "#3B3936", "armed": ACCENT, "busy": ACCENT,
                  "speaking": TEXT, "error": ERROR, "loading": "#3B3936"}
        col = QColor(colors.get(self.state, "#3B3936"))

        ring = QColor(ACCENT if self.state == "armed" else LINE)
        if self.state == "armed":
            ring.setAlphaF(0.35 + 0.35 * breathe)
        p.setPen(QPen(ring, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R, R)

        base = R * 0.28
        if self.state in ("speaking", "busy", "loading"):
            r = base + R * 0.07 * breathe
        else:
            r = base + R * 0.5 * min(1.0, self._level)

        halo = QColor(col)
        halo.setAlphaF(0.08 + 0.14 * min(1.0, self._level + (0.4 * breathe if self.state == "speaking" else 0)))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(c, r * 1.55, r * 1.55)
        p.setBrush(col)
        p.drawEllipse(c, r, r)


STATE_TEXT = {
    "loading": "ЗАГРУЖАЮ РАСПОЗНАВАНИЕ…",
    "idle": "СКАЖИТЕ «СЕНЬОР»",
    "armed": "СЛУШАЮ",
    "busy": "ВЫПОЛНЯЮ",
    "speaking": "ГОВОРЮ",
    "error": "",
}


class HomeScreen(QWidget):
    logout_requested = Signal()

    def __init__(self, win, cfg, speaker: Speaker, model=None):
        super().__init__()
        self.win, self.cfg, self.speaker = win, cfg, speaker
        self.model = model
        self.listener = None
        self._old_listeners = []
        self.armed = False
        self.speaking = False
        self.mic = "loading"   # loading | ok | error
        self.chime = Chime()
        self.bridge = Bridge()
        self.bridge.action_done.connect(self._on_action_done)
        self.speaker.speaking.connect(self._on_speaking)
        self.arm_timer = QTimer(self)
        self.arm_timer.setSingleShot(True)
        self.arm_timer.timeout.connect(self._disarm)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 24, 24, 40)

        top = QHBoxLayout()
        top.addWidget(label("SenioreM", 17, QFont.DemiBold))
        top.addStretch(1)
        self.user_lbl = label("", 13, role="muted")
        top.addWidget(self.user_lbl)
        top.addSpacing(20)
        out = button("Выйти", "link", 13, QFont.Normal)
        out.clicked.connect(self.logout_requested.emit)
        top.addWidget(out)
        top.addSpacing(16)
        top.addLayout(window_controls(win))
        root.addLayout(top)

        root.addStretch(3)
        self.orb = Orb(300)
        root.addWidget(self.orb, 0, Qt.AlignHCenter)
        root.addSpacing(36)
        self.state_lbl = label("", 11, QFont.DemiBold, "muted", spacing=2.4)
        self.state_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self.state_lbl)
        root.addSpacing(18)
        self.heard = label("", 34, QFont.Light, display=True, wrap=True)
        self.heard.setAlignment(Qt.AlignCenter)
        self.heard.setMinimumHeight(48)
        root.addWidget(self.heard)
        root.addSpacing(10)
        self.reply = label("", 18, role="muted", wrap=True)
        self.reply.setAlignment(Qt.AlignCenter)
        self.reply.setMinimumHeight(28)
        root.addWidget(self.reply)
        root.addStretch(4)

        hints = label("громкость 30   ·   громче   ·   выключи звук   ·   открой браузер   ·   закрой телеграм   ·   "
                      "найди погоду   ·   который час   ·   пауза   ·   сверни",
                      13, role="faint")
        hints.setAlignment(Qt.AlignCenter)
        root.addWidget(hints)
        root.addSpacing(18)
        self.input = field("…или напишите команду и нажмите Enter")
        self.input.setFont(font(15))
        self.input.setAlignment(Qt.AlignCenter)
        self.input.setFixedWidth(480)
        self.input.returnPressed.connect(self._typed)
        root.addWidget(self.input, 0, Qt.AlignHCenter)

    # ---------- жизненный цикл ----------
    def start(self, email):
        self.user_lbl.setText(email)
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

    def stop(self):
        if self.listener is not None:
            lst = self.listener
            for sig in (lst.level, lst.partial, lst.final, lst.failed, lst.ready):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
            lst.stop()
            self._old_listeners.append(lst)  # держим ссылку, пока поток не закончится
            self.listener = None
        self.armed = False

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
        self._rest_state()

    # ---------- речь ----------
    def _show_heard(self, text, faint):
        self.heard.setText(text)
        self.heard.setStyleSheet(f"color: {FAINT if faint else TEXT};")

    def _on_partial(self, text):
        if self.orb.state in ("idle", "armed") and text:
            self._show_heard(text, True)

    def _on_final(self, text):
        words = commands.tokens(text)
        i = commands.find_wake(words, self.cfg.get("wake_words", []))
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
        self.chime.play()
        self._show_heard("", True)
        self._rest_state()
        self.arm_timer.start(8000)

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
        self.reply.setText(reply)
        self._rest_state()
        if reply:
            self.speaker.say(reply)
        if ui == "minimize":
            QTimer.singleShot(300, self.win.showMinimized)
        elif ui == "restore":
            self.win.showFullScreen()
            self.win.raise_()
            self.win.activateWindow()
        elif ui == "quit":
            QTimer.singleShot(1800, self.win.close)


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
        self.greeted = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.auth = AuthScreen(self)
        self.home = HomeScreen(self, cfg, self.speaker, model)
        self.stack.addWidget(self.auth)
        self.stack.addWidget(self.home)

        a = self.auth
        a.register.submit.clicked.connect(self._register)
        a.register.to_login.clicked.connect(lambda: self._go_auth(a.login))
        a.login.submit.clicked.connect(self._login)
        a.login.to_register.clicked.connect(lambda: self._go_auth(a.register))
        a.verify.submit.clicked.connect(self._verify)
        a.verify.resend.clicked.connect(self._resend)
        a.verify.back.clicked.connect(lambda: self._go_auth(a.register))
        self.home.logout_requested.connect(self._logout)

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
        self.stack.setCurrentWidget(self.home)
        self.home.start(email)
        if not self.greeted:
            self.greeted = True
            self.speaker.say("Здравствуйте. Я на связи — скажите «Сеньор» и команду.")

    def _logout(self):
        self.home.stop()
        self.speaker.interrupt()
        self.store.logout()
        f = self.auth.login
        f.pw.clear()
        self._go_auth(f)

    # ---------- регистрация ----------
    def _register(self):
        f = self.auth.register
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
            form = self.auth.verify if self.stack.currentWidget() is self.auth and \
                self.auth.stack.currentWidget() is self.auth.verify.parentWidget() else self.auth.register
            form.show_error(err)
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
