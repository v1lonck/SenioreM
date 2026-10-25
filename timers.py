"""Таймеры, напоминания и выключение компьютера по времени.
Плашки с обратным отсчётом появляются в правом верхнем углу экрана поверх всех окон."""
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import wave

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import theme as T
from theme import font

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ------------------------------------------------------------------ разбор времени
UNIT_SEC = (("сек", 1), ("мин", 60), ("час", 3600), ("сут", 86400), ("ден", 86400), ("дн", 86400))


def parse_duration(text):
    """«5 минут», «полчаса», «полтора часа», «1 час 20 минут», «через минуту» -> секунды."""
    import commands
    t = commands.normalize(text)
    t = t.replace("пол часа", "полчаса").replace("пол минуты", "полминуты")
    total = 0
    if "полтора часа" in t:
        total += 5400
        t = t.replace("полтора часа", " ")
    if "полторы минуты" in t:
        total += 90
        t = t.replace("полторы минуты", " ")
    if "полчаса" in t:
        total += 1800
        t = t.replace("полчаса", " ")
    if "полминуты" in t:
        total += 30
        t = t.replace("полминуты", " ")
    words = t.split()
    i = 0
    while i < len(words):
        w = words[i]
        unit = next((sec for stem, sec in UNIT_SEC if w.startswith(stem)), None)
        if unit:
            j = i - 1
            nums = []
            while j >= 0 and (commands.parse_number([words[j]]) is not None):
                nums.insert(0, words[j])
                j -= 1
            n = commands.parse_number(nums) if nums else 1
            total += (n or 1) * unit
        i += 1
    return total


def human(sec):
    """3725 -> «1 час 2 минуты 5 секунд»."""
    from speechtext import plural
    sec = int(round(sec))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} {plural(h, 'час', 'часа', 'часов')}")
    if m:
        parts.append(f"{m} {plural(m, 'минуту', 'минуты', 'минут')}")
    if s and not h:
        parts.append(f"{s} {plural(s, 'секунду', 'секунды', 'секунд')}")
    return " ".join(parts) or "0 секунд"


def clock(sec):
    sec = max(0, int(math.ceil(sec)))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ------------------------------------------------------------------ звуки
RATE = 44100


def _marimba(freq, dur, amp=0.3):
    """Мягкая «маримба»: основной тон + быстро гаснущий обертон."""
    import numpy as np
    t = np.arange(int(RATE * dur)) / RATE
    env = np.minimum(1.0, t / 0.004) * np.exp(-t / 0.45)
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 4.0 * t) * np.exp(-t / 0.05)
            + 0.15 * np.sin(2 * np.pi * freq * 2.0 * t))
    return amp * env * tone


def _mix_into(buf, sig, at):
    s0 = int(at * RATE)
    n = min(len(sig), len(buf) - s0)
    if n > 0:
        buf[s0:s0 + n] += sig[:n]


def _write_wav(path, buf):
    import numpy as np
    peak = float(np.max(np.abs(buf))) or 1.0
    data = (buf / max(1.0, peak) * 32000).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def _bell_path():
    """Короткий приятный сигнал окончания таймера (три ноты вверх)."""
    import numpy as np
    path = os.path.join(tempfile.gettempdir(), "seniorem_bell_v2.wav")
    if os.path.exists(path):
        return path
    buf = np.zeros(int(RATE * 2.4))
    for i, (at, f) in enumerate(((0.0, 659.25), (0.16, 830.6), (0.32, 987.8), (0.9, 659.25),
                                 (1.06, 830.6), (1.22, 987.8))):
        _mix_into(buf, _marimba(f, 1.1, 0.28), at)
    _write_wav(path, buf)
    return path


def alarm_samples():
    """Мелодия будильника: мягкое арпеджио, постепенно громче (~24 с, потом по кругу)."""
    import numpy as np
    buf = np.zeros(int(RATE * 24))
    phrase = (523.25, 659.25, 783.99, 1046.5, 783.99, 659.25, 783.99, 1046.5)
    at = 0.0
    k = 0
    while at < 23:
        vol = 0.22 + 0.6 * min(1.0, at / 18)          # сначала тихо — будит мягко
        for i, f in enumerate(phrase):
            _mix_into(buf, _marimba(f * (1.0 if k % 2 == 0 else 1.122), 1.0, vol), at + i * 0.2)
        # мягкий «пэд» под мелодией
        t = np.arange(int(RATE * 1.6)) / RATE
        pad = 0.06 * vol * np.sin(np.pi * t / 1.6) * (np.sin(2 * np.pi * 261.6 * t)
                                                       + np.sin(2 * np.pi * 392.0 * t))
        _mix_into(buf, pad, at)
        at += 2.6
        k += 1
    peak = float(np.max(np.abs(buf))) or 1.0
    return (buf / peak * 0.85).astype(np.float32)


def play_bell():
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.PlaySound(_bell_path(), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:  # noqa: BLE001
        pass


class AlarmSound:
    """Звонок будильника по кругу — отдельным каналом, чтобы голос помощника его не обрывал."""

    def __init__(self):
        self.playing = False
        self._path = None

    def start(self):
        if self.playing:
            return
        self.playing = True
        try:
            import sounddevice as sd
            sd.play(alarm_samples(), RATE, loop=True)
            self._mode = "sd"
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            import winsound
            import numpy as np
            path = os.path.join(tempfile.gettempdir(), "seniorem_alarm_v1.wav")
            if not os.path.exists(path):
                _write_wav(path, alarm_samples().astype(np.float64))
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            self._mode = "ws"
        except Exception:  # noqa: BLE001
            self.playing = False

    def stop(self):
        if not self.playing:
            return
        self.playing = False
        try:
            if getattr(self, "_mode", "") == "sd":
                import sounddevice as sd
                sd.stop()
            else:
                import winsound
                winsound.PlaySound(None, 0)
        except Exception:  # noqa: BLE001
            pass


ALARM = AlarmSound()


# ------------------------------------------------------------------ плашка
KINDS = {"timer": "Таймер", "remind": "Напоминание", "shutdown": "Выключение",
         "restart": "Перезагрузка", "sleep": "Спящий режим", "alarm": "Будильник"}


def draw_icon(p, kind, c, r, color):
    """Векторные значки (эмодзи в Windows выглядят по-разному — рисуем сами)."""
    p.save()
    pen = QPen(color, r * 0.13, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    x, y = c.x(), c.y()
    if kind == "timer":
        p.drawEllipse(QPointF(x, y + r * 0.08), r * 0.62, r * 0.62)
        p.drawLine(QPointF(x, y + r * 0.08), QPointF(x, y - r * 0.3))
        p.drawLine(QPointF(x, y + r * 0.08), QPointF(x + r * 0.28, y + r * 0.2))
        p.drawLine(QPointF(x - r * 0.18, y - r * 0.78), QPointF(x + r * 0.18, y - r * 0.78))
    elif kind in ("remind", "alarm"):
        path = QPainterPath()
        path.moveTo(x - r * 0.55, y + r * 0.35)
        path.cubicTo(x - r * 0.45, y + r * 0.2, x - r * 0.5, y - r * 0.15, x - r * 0.45, y - r * 0.3)
        path.cubicTo(x - r * 0.38, y - r * 0.68, x + r * 0.38, y - r * 0.68, x + r * 0.45, y - r * 0.3)
        path.cubicTo(x + r * 0.5, y - r * 0.15, x + r * 0.45, y + r * 0.2, x + r * 0.55, y + r * 0.35)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(x - r * 0.14, y + r * 0.56), QPointF(x + r * 0.14, y + r * 0.56))
        if kind == "alarm":
            p.drawArc(QRectF(x - r * 1.0, y - r * 0.95, r * 0.7, r * 0.7), 100 * 16, 70 * 16)
            p.drawArc(QRectF(x + r * 0.3, y - r * 0.95, r * 0.7, r * 0.7), 10 * 16, 70 * 16)
    elif kind in ("shutdown",):
        p.drawArc(QRectF(x - r * 0.6, y - r * 0.55, r * 1.2, r * 1.2), 125 * 16, -250 * 16)
        p.drawLine(QPointF(x, y - r * 0.7), QPointF(x, y - r * 0.05))
    elif kind == "restart":
        p.drawArc(QRectF(x - r * 0.6, y - r * 0.6, r * 1.2, r * 1.2), 70 * 16, 290 * 16)
        p.drawLine(QPointF(x + r * 0.2, y - r * 0.62), QPointF(x + r * 0.42, y - r * 0.85))
        p.drawLine(QPointF(x + r * 0.2, y - r * 0.62), QPointF(x + r * 0.46, y - r * 0.45))
    else:                                     # сон — месяц
        path = QPainterPath()
        path.addEllipse(QPointF(x, y), r * 0.6, r * 0.6)
        cut = QPainterPath()
        cut.addEllipse(QPointF(x + r * 0.32, y - r * 0.22), r * 0.5, r * 0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path.subtracted(cut))
    p.restore()


class Toast(QWidget):
    """Плашка в правом верхнем углу: кольцо прогресса со значком, название, обратный отсчёт.
    У будильника после звонка — большие кнопки «Стоп» и «Ещё 5 минут»."""
    cancel_clicked = Signal()
    closed = Signal()
    stop_clicked = Signal()
    snooze_clicked = Signal()

    W, H = 420, 124
    M = 14                                    # поле под мягкую тень

    def __init__(self, item):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.item = item
        self.done = False
        self._hover = ""
        self._t = 0.0
        self._h = self.H
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    @property
    def is_alarm(self):
        return self.item.get("kind") == "alarm"

    def _tick(self):
        self._t += 0.05
        if self.done or int(self._t * 20) % 4 == 0:
            self.update()

    def finish(self):
        self.done = True
        if self.is_alarm:
            self._h = self.H + 58              # место под кнопки
            self.setFixedSize(self.W, self._h)
        else:
            QTimer.singleShot(15000, self.dismiss)
        self.update()

    def _pos_for(self, index):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        return self.pos().__class__(geo.right() - self.W - 8, geo.top() + 8 + index * (self.H - 6))

    def show_at(self, index):
        target = self._pos_for(index)
        self.setWindowOpacity(0.0)
        self.move(target.x() + 60, target.y())
        self.show()
        self._a1 = QPropertyAnimation(self, b"windowOpacity", self)
        self._a1.setDuration(280)
        self._a1.setEndValue(1.0)
        self._a1.start()
        self._a2 = QPropertyAnimation(self, b"pos", self)
        self._a2.setDuration(420)
        self._a2.setEndValue(target)
        self._a2.setEasingCurve(QEasingCurve.OutBack)
        self._a2.start()

    def move_to(self, index):
        self._a3 = QPropertyAnimation(self, b"pos", self)
        self._a3.setDuration(260)
        self._a3.setEndValue(self._pos_for(index))
        self._a3.setEasingCurve(QEasingCurve.OutCubic)
        self._a3.start()

    def dismiss(self):
        if not self.isVisible():
            return
        self._a4 = QPropertyAnimation(self, b"windowOpacity", self)
        self._a4.setDuration(220)
        self._a4.setEndValue(0.0)
        self._a4.finished.connect(lambda: (self.close(), self.closed.emit()))
        self._a4.start()

    # ---- геометрия
    def _card(self):
        m = self.M
        return QRectF(m, m, self.W - 2 * m, self.height() - 2 * m)

    def _x_rect(self):
        r = self._card()
        return QRectF(r.right() - 34, r.top() + 10, 24, 24)

    def _btn_rects(self):
        r = self._card()
        y = r.bottom() - 52
        w = (r.width() - 36 - 10) / 2
        return QRectF(r.left() + 18, y, w, 38), QRectF(r.left() + 28 + w, y, w, 38)

    def _hit(self, pos):
        if self._x_rect().contains(pos):
            return "x"
        if self.done and self.is_alarm:
            stop, snooze = self._btn_rects()
            if stop.contains(pos):
                return "stop"
            if snooze.contains(pos):
                return "snooze"
        return ""

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = ""
        self.update()

    def mousePressEvent(self, e):
        h = self._hit(e.position())
        if h == "stop":
            self.stop_clicked.emit()
        elif h == "snooze":
            self.snooze_clicked.emit()
        elif h == "x":
            if self.done:
                if self.is_alarm:
                    self.stop_clicked.emit()
                else:
                    self.dismiss()
            else:
                self.cancel_clicked.emit()
        elif self.done and not self.is_alarm:
            self.dismiss()

    # ---- рисование
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._card()
        acc = QColor(T.ACCENT)
        pulse = 0.5 + 0.5 * math.sin(self._t * 5) if self.done else 0.0
        # мягкая тень
        for i in range(self.M, 0, -2):
            sh = QPainterPath()
            sh.addRoundedRect(r.adjusted(-i, -i + 4, i, i + 4), 22 + i, 22 + i)
            p.fillPath(sh, QColor(0, 0, 0, int(10 * (1 - i / self.M) + 2)))
        if self.done:                          # свечение при срабатывании
            for i in range(8, 0, -2):
                gl = QPainterPath()
                gl.addRoundedRect(r.adjusted(-i, -i, i, i), 22 + i, 22 + i)
                p.fillPath(gl, T.qcolor(T.ACCENT, int((8 - i) * 6 * pulse)))
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, T.qcolor(T._mix("#11141C", T.ACCENT, 0.22), 250))
        g.setColorAt(0.55, T.qcolor("#10131A", 250))
        g.setColorAt(1, T.qcolor(T._mix("#10131A", T.ACCENT, 0.08), 250))
        p.fillPath(path, QBrush(g))
        # блик сверху
        hl = QLinearGradient(0, r.top(), 0, r.top() + 40)
        hl.setColorAt(0, QColor(255, 255, 255, 18))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(hl))
        p.setPen(QPen(T.qcolor(T.ACCENT, 90 + int(140 * pulse)), 1.3))
        p.drawPath(path)

        kind = self.item.get("kind", "timer")
        title = KINDS.get(kind, "Таймер")
        remain = max(0.0, self.item["end"] - time.time())
        total = max(1.0, self.item["end"] - self.item["start"])
        frac = 1.0 if self.done else 1 - remain / total
        # кольцо прогресса со значком
        c = QPointF(r.left() + 52, r.top() + 50)
        rad = 30
        p.setPen(QPen(QColor(255, 255, 255, 22), 5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, rad, rad)
        ring = QPen(acc, 5, Qt.SolidLine, Qt.RoundCap)
        p.setPen(ring)
        p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), 90 * 16, int(-360 * 16 * frac))
        icon_col = QColor(T.ACCENT_SOFT) if not self.done else QColor("#FFFFFF")
        if self.done:
            p.save()
            p.translate(c)
            p.rotate(12 * math.sin(self._t * 22) if self.is_alarm or kind == "remind" else 0)
            p.translate(-c.x(), -c.y())
            draw_icon(p, kind, c, 20, icon_col)
            p.restore()
        else:
            draw_icon(p, kind, c, 20, icon_col)

        left = r.left() + 100
        width = r.right() - 44 - left
        label = self.item.get("label") or ""
        p.setPen(QColor(T.ACCENT_SOFT))
        p.setFont(font(11, QFont.DemiBold, spacing=1.4))
        head = title.upper()
        if self.done:
            head = {"alarm": "ПОРА ВСТАВАТЬ", "remind": "НАПОМИНАНИЕ"}.get(kind, "ВРЕМЯ ВЫШЛО")
        p.drawText(QRectF(left, r.top() + 16, width, 16), Qt.AlignLeft | Qt.AlignVCenter, head)
        p.setPen(QColor("#FFFFFF"))
        if self.done:
            big = self.item.get("at_text") or (label if label else title)
            if kind == "alarm":
                big = self.item.get("at_text") or time.strftime("%H:%M")
            p.setFont(font(28 if kind == "alarm" else 19, QFont.DemiBold, display=kind == "alarm"))
            fm = p.fontMetrics()
            p.drawText(QRectF(left, r.top() + 34, width, 40), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(big, Qt.ElideRight, int(width)))
            sub = label if kind == "alarm" and label else ("Нажмите, чтобы закрыть" if kind != "alarm" else "")
            if sub:
                p.setPen(QColor(255, 255, 255, 150))
                p.setFont(font(12))
                p.drawText(QRectF(left, r.top() + 74, width, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(sub, Qt.ElideRight, int(width)))
        else:
            p.setFont(font(32, QFont.Light, display=True))
            txt = clock(remain)
            p.drawText(QRectF(left, r.top() + 32, width, 44), Qt.AlignLeft | Qt.AlignVCenter, txt)
            sub = label or (f"в {self.item['at_text']}" if self.item.get("at_text") else "")
            if kind == "alarm" and self.item.get("at_text"):
                sub = f"Зазвонит в {self.item['at_text']}" + (f" · {label}" if label else "")
            if sub:
                p.setPen(QColor(255, 255, 255, 150))
                p.setFont(font(12))
                p.drawText(QRectF(left, r.top() + 76, width, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(sub, Qt.ElideRight, int(width)))
        # кнопки будильника
        if self.done and self.is_alarm:
            stop, snooze = self._btn_rects()
            for rect, text, primary in ((stop, "Стоп", True), (snooze, "Ещё 5 минут", False)):
                hov = self._hover == ("stop" if primary else "snooze")
                bp = QPainterPath()
                bp.addRoundedRect(rect, 12, 12)
                if primary:
                    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
                    bg.setColorAt(0, QColor(T.ACCENT).lighter(115 if hov else 100))
                    bg.setColorAt(1, QColor(T.ACCENT_SOFT))
                    p.fillPath(bp, QBrush(bg))
                    p.setPen(QColor("#0A0C10"))
                else:
                    p.fillPath(bp, QColor(255, 255, 255, 34 if hov else 18))
                    p.setPen(QPen(QColor(255, 255, 255, 60), 1))
                    p.drawPath(bp)
                    p.setPen(QColor("#FFFFFF"))
                p.setFont(font(14, QFont.DemiBold))
                p.drawText(rect, Qt.AlignCenter, text)
        # крестик
        xr = self._x_rect()
        if self._hover == "x":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawEllipse(xr)
        p.setPen(QPen(QColor(255, 255, 255, 200 if self._hover == "x" else 110), 1.6, Qt.SolidLine,
                      Qt.RoundCap))
        m = 8
        p.drawLine(QPointF(xr.left() + m, xr.top() + m), QPointF(xr.right() - m, xr.bottom() - m))
        p.drawLine(QPointF(xr.right() - m, xr.top() + m), QPointF(xr.left() + m, xr.bottom() - m))


# ------------------------------------------------------------------ менеджер
class TimerManager(QObject):
    finished = Signal(str)        # текст, который нужно сказать вслух

    def __init__(self):
        super().__init__()
        self.items = []
        self._next_id = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(250)
        self.toasts = []

    def add(self, kind, seconds, label="", at_text=""):
        now = time.time()
        if kind == "alarm" and not at_text:
            at_text = time.strftime("%H:%M", time.localtime(now + seconds))
        item = {"id": self._next_id, "kind": kind, "start": now, "end": now + seconds,
                "label": label, "seconds": seconds, "at_text": at_text}
        self._next_id += 1
        self.items.append(item)
        if kind in ("shutdown", "restart"):
            # дублируем средствами Windows — сработает, даже если SenioreM закроют
            flag = "/s" if kind == "shutdown" else "/r"
            try:
                subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=NO_WINDOW)
                subprocess.run(["shutdown", flag, "/t", str(int(seconds))], capture_output=True,
                               creationflags=NO_WINDOW)
            except Exception:  # noqa: BLE001
                pass
        toast = Toast(item)
        toast.cancel_clicked.connect(lambda i=item["id"]: self.cancel(i))
        toast.stop_clicked.connect(self.stop_alarm)
        toast.snooze_clicked.connect(self.snooze)
        toast.closed.connect(lambda tt=toast: self._remove_toast(tt))
        self.toasts.append(toast)
        toast.show_at(len(self.toasts) - 1)
        return item

    def _remove_toast(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        for i, tt in enumerate(self.toasts):
            tt.move_to(i)

    def _toast_for(self, item_id):
        return next((tt for tt in self.toasts if tt.item["id"] == item_id), None)

    def cancel(self, item_id=None, kinds=None):
        """Отменяет таймер по номеру или все таймеры нужных видов. -> сколько отменено."""
        n = 0
        for item in list(self.items):
            if (item_id is not None and item["id"] == item_id) or \
                    (item_id is None and (kinds is None or item["kind"] in kinds)):
                self.items.remove(item)
                n += 1
                if item["kind"] in ("shutdown", "restart"):
                    try:
                        subprocess.run(["shutdown", "/a"], capture_output=True,
                                       creationflags=NO_WINDOW)
                    except Exception:  # noqa: BLE001
                        pass
                tt = self._toast_for(item["id"])
                if tt:
                    tt.dismiss()
        return n

    def stop_alarm(self):
        """Выключить звенящий будильник. -> был ли звонок."""
        was = ALARM.playing or any(tt.done and tt.is_alarm for tt in self.toasts)
        ALARM.stop()
        for tt in list(self.toasts):
            if tt.done and tt.is_alarm:
                tt.dismiss()
        return was

    def snooze(self, minutes=5):
        label = next((tt.item.get("label", "") for tt in self.toasts if tt.done and tt.is_alarm), "")
        self.stop_alarm()
        self.add("alarm", minutes * 60, label)

    def nearest(self):
        return min(self.items, key=lambda i: i["end"]) if self.items else None

    def _check(self):
        now = time.time()
        for item in list(self.items):
            if now >= item["end"]:
                self.items.remove(item)
                tt = self._toast_for(item["id"])
                if tt:
                    tt.finish()
                if item["kind"] == "alarm":
                    ALARM.start()
                    QTimer.singleShot(10 * 60 * 1000, self.stop_alarm)     # не звенит вечно
                else:
                    play_bell()
                self._fire(item)

    def _fire(self, item):
        kind, label = item["kind"], item.get("label")
        if kind == "alarm":
            self.finished.emit(f"Будильник! Сейчас {item.get('at_text') or time.strftime('%H:%M')}."
                               + (f" {label}." if label else "") + " Скажите «стоп», чтобы выключить.")
        elif kind == "timer":
            self.finished.emit(f"Таймер на {human(item['seconds'])} закончился."
                               + (f" {label}." if label else ""))
        elif kind == "remind":
            self.finished.emit(f"Напоминаю: {label}." if label else "Напоминаю!")
        elif kind == "sleep":
            self.finished.emit("Перевожу компьютер в спящий режим.")
            QTimer.singleShot(2500, lambda: subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NO_WINDOW))
        elif kind in ("shutdown", "restart"):
            self.finished.emit("Выключаю компьютер." if kind == "shutdown" else "Перезагружаю компьютер.")


MANAGER = None


def manager():
    global MANAGER
    if MANAGER is None:
        MANAGER = TimerManager()
    return MANAGER


def parse(text):
    """Команды таймеров. -> intent или None."""
    import commands
    t = commands.normalize(text)
    if re.search(r"(выключи|выключить|останови|отключи|стоп|хватит|тихо)\b.*будильник|"
                 r"будильник.*(выключи|стоп|хватит)|^(я )?(встал|встаю|проснулся|проснулась)", t):
        return {"action": "timer_alarm_stop"}
    if re.search(r"отложи|еще (5|пять) минут|ещё (5|пять) минут|дай поспать", t) and \
            (ALARM.playing or "будильник" in t):
        return {"action": "timer_snooze"}
    if re.search(r"отмени|отменить|убери|сбрось|удали", t) and "будильник" in t:
        return {"action": "timer_cancel", "kinds": ("alarm",)}
    if re.search(r"будильник|разбуди|подними меня|подъем в", t):
        return parse_alarm(t)
    if re.search(r"отмени|отменить|останови|убери|сбрось", t) and \
            re.search(r"таймер|выключени|перезагрузк|напоминани|сон|все", t):
        kinds = None
        if "выключ" in t or "перезагруз" in t:
            kinds = ("shutdown", "restart")
        elif "напомин" in t:
            kinds = ("remind",)
        elif "таймер" in t and "все" not in t:
            kinds = ("timer",)
        elif "сон" in t:
            kinds = ("sleep",)
        return {"action": "timer_cancel", "kinds": kinds}
    if re.search(r"сколько (еще|осталось)|сколько времени осталось", t) and \
            re.search(r"таймер|осталось|выключени", t):
        return {"action": "timer_left"}
    if re.match(r"^(напомни|напомнить)", t):
        words = t.split()
        if "через" in words:
            k = words.index("через")
            j = k + 1
            dur = []
            while j < len(words) and (commands.parse_number([words[j]]) is not None or
                                      any(words[j].startswith(st) for st, _ in UNIT_SEC) or
                                      words[j] in ("пол", "полчаса", "полтора", "полторы",
                                                   "полминуты", "час", "и")):
                dur.append(words[j])
                j += 1
            sec = parse_duration(" ".join(dur))
            skip = {"напомни", "напомнить", "мне", "что", "чтобы", "о", "том", "про", "нужно", "надо"}
            label = " ".join(x for x in words[1:k] + words[j:] if x not in skip)
            if sec:
                return {"action": "timer_add", "kind": "remind", "seconds": sec, "label": label}
        return {"action": "chat", "reply": "Скажите, через сколько напомнить. Например: "
                                           "«напомни через 10 минут позвонить маме»."}
    kind = None
    if re.search(r"(выключи|выключить|выключение|выруби)\s+(компьютер|комп|пк|ноутбук)|"
                 r"выключение компьютера|выключи все", t):
        kind = "shutdown"
    elif re.search(r"(перезагрузи|перезагрузить|перезагрузка)\s*(компьютер|комп|пк|ноутбук)?", t):
        kind = "restart"
    elif re.search(r"(спящий режим|в сон|усыпи|режим сна)", t):
        kind = "sleep"
    elif re.search(r"таймер|засеки|засечь|отсчет", t):
        kind = "timer"
    if not kind:
        return None
    sec = parse_duration(t)
    if kind == "timer" and not sec:
        return {"action": "chat", "reply": "На сколько поставить таймер? Например: «таймер на 5 минут»."}
    if kind in ("shutdown", "restart", "sleep") and not sec:
        sec = 60                      # без времени — через минуту, чтобы можно было отменить
    label = ""
    if kind == "timer":
        m = re.search(r"\bдля ([а-я ]+)$", t)
        if m:
            label = m.group(1).strip()
    return {"action": "timer_add", "kind": kind, "seconds": sec, "label": label}


DAYPART = {"утра": "am", "утром": "am", "ночи": "night", "вечера": "pm", "вечером": "pm",
           "дня": "pm", "днем": "pm"}


def _num(w):
    import commands
    if w.isdigit():
        return int(w)
    return commands.parse_number([w])


def parse_alarm(t):
    """«будильник на 7 утра», «разбуди в 7 30», «будильник через 20 минут», «на семь тридцать»."""
    import datetime
    words = t.split()
    if "через" in words:
        sec = parse_duration(" ".join(words[words.index("через") + 1:]))
        if sec:
            return {"action": "timer_add", "kind": "alarm", "seconds": sec, "label": ""}
    hour = minute = None
    part = None
    for i, w in enumerate(words):
        if w in DAYPART:
            part = DAYPART[w]
    for i, w in enumerate(words):
        if w in ("на", "в", "к", "во") or hour is None and w.isdigit():
            j = i + 1 if w in ("на", "в", "к", "во") else i
            if j < len(words):
                h = _num(words[j])
                if h is not None and 0 <= h <= 24:
                    hour = h
                    minute = 0
                    if j + 1 < len(words):
                        mm = _num(words[j + 1])
                        if mm is not None and 0 <= mm < 60 and words[j + 1] not in DAYPART:
                            minute = mm
                            if j + 2 < len(words) and words[j + 2].isdigit() is False:
                                m2 = _num(words[j + 2]) if words[j + 1] in (
                                    "двадцать", "тридцать", "сорок", "пятьдесят") else None
                                if m2 is not None and m2 < 10:
                                    minute += m2
                    break
    if hour is None:
        return {"action": "chat", "reply": "На какое время поставить будильник? Например: "
                                           "«будильник на 7 утра» или «разбуди меня в 6:45»."}
    if part == "pm" and hour < 12:
        hour += 12
    if part == "night" and hour == 12:
        hour = 0
    now = datetime.datetime.now()
    at = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if at <= now:
        at += datetime.timedelta(days=1)
    sec = int((at - now).total_seconds())
    return {"action": "timer_add", "kind": "alarm", "seconds": sec, "label": "",
            "at_text": at.strftime("%H:%M")}
