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


# ------------------------------------------------------------------ звук окончания
def _bell_path():
    path = os.path.join(tempfile.gettempdir(), "seniorem_bell_v1.wav")
    if os.path.exists(path):
        return path
    rate = 44100
    total = int(rate * 2.2)
    buf = [0.0] * total
    for start, freq in ((0.0, 1046.5), (0.18, 1318.5), (0.36, 1568.0), (0.9, 1046.5),
                        (1.08, 1318.5), (1.26, 1568.0)):
        s0 = int(start * rate)
        for i in range(min(total - s0, int(rate * 0.9))):
            tt = i / rate
            env = min(1.0, tt / 0.005) * math.exp(-tt / 0.35)
            buf[s0 + i] += 0.12 * env * (math.sin(2 * math.pi * freq * tt) +
                                         0.3 * math.sin(2 * math.pi * freq * 2.01 * tt))
    frames = b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32767)) for x in buf)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return path


def play_bell():
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.PlaySound(_bell_path(), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ плашка
KINDS = {"timer": ("⏱", "Таймер"), "remind": ("🔔", "Напоминание"),
         "shutdown": ("⏻", "Выключение компьютера"), "restart": ("↻", "Перезагрузка"),
         "sleep": ("☾", "Спящий режим")}


class Toast(QWidget):
    """Плашка в правом верхнем углу: значок, название, большой обратный отсчёт, полоса."""
    cancel_clicked = Signal()
    closed = Signal()

    W, H = 380, 118

    def __init__(self, item):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.item = item
        self.done = False
        self._hover_x = False
        self._t = 0.0
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

    def _tick(self):
        self._t += 0.1
        self.update()

    def finish(self):
        self.done = True
        QTimer.singleShot(12000, self.dismiss)

    def show_at(self, index):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        x = geo.right() - self.W - 18
        y = geo.top() + 18 + index * (self.H + 12)
        self.setWindowOpacity(0.0)
        self.move(x + 40, y)
        self.show()
        self._a1 = QPropertyAnimation(self, b"windowOpacity", self)
        self._a1.setDuration(260)
        self._a1.setEndValue(1.0)
        self._a1.start()
        self._a2 = QPropertyAnimation(self, b"pos", self)
        self._a2.setDuration(320)
        self._a2.setEndValue(self.pos().__class__(x, y))
        self._a2.setEasingCurve(QEasingCurve.OutCubic)
        self._a2.start()

    def move_to(self, index):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self._a3 = QPropertyAnimation(self, b"pos", self)
        self._a3.setDuration(220)
        self._a3.setEndValue(self.pos().__class__(geo.right() - self.W - 18,
                                                  geo.top() + 18 + index * (self.H + 12)))
        self._a3.start()

    def dismiss(self):
        if not self.isVisible():
            return
        self._a4 = QPropertyAnimation(self, b"windowOpacity", self)
        self._a4.setDuration(220)
        self._a4.setEndValue(0.0)
        self._a4.finished.connect(lambda: (self.close(), self.closed.emit()))
        self._a4.start()

    def _x_rect(self):
        return QRectF(self.W - 40, 12, 26, 26)

    def mouseMoveEvent(self, e):
        hx = self._x_rect().contains(e.position())
        if hx != self._hover_x:
            self._hover_x = hx
            self.update()

    def mousePressEvent(self, e):
        if self._x_rect().contains(e.position()):
            if self.done:
                self.dismiss()
            else:
                self.cancel_clicked.emit()
        elif self.done:
            self.dismiss()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(4, 4, self.W - 8, self.H - 8)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, T.qcolor(T._mix(T.SURFACE, T.ACCENT, 0.18), 245))
        g.setColorAt(1, T.qcolor(T.SURFACE, 245))
        p.fillPath(path, QBrush(g))
        border = QColor(T.ACCENT)
        if self.done:
            border.setAlphaF(0.5 + 0.5 * abs(math.sin(self._t * 3)))
        else:
            border.setAlphaF(0.55)
        p.setPen(QPen(border, 1.5))
        p.drawPath(path)
        # значок в круге
        icon, title = KINDS.get(self.item["kind"], ("⏱", "Таймер"))
        c = QPointF(r.left() + 42, r.top() + 44)
        p.setPen(Qt.NoPen)
        p.setBrush(T.qcolor(T.ACCENT, 50))
        p.drawEllipse(c, 26, 26)
        p.setPen(QColor(T.ACCENT_SOFT))
        p.setFont(font(22, QFont.DemiBold))
        p.drawText(QRectF(c.x() - 26, c.y() - 26, 52, 52), Qt.AlignCenter, icon)
        # тексты
        left = r.left() + 82
        p.setPen(QColor(T.MUTED))
        p.setFont(font(12, QFont.DemiBold, spacing=1.2))
        p.drawText(QRectF(left, r.top() + 14, r.width() - 130, 18), Qt.AlignLeft,
                   ("ГОТОВО" if self.done else title.upper()))
        label = self.item.get("label") or ""
        remain = max(0.0, self.item["end"] - time.time())
        p.setPen(QColor(T.TEXT))
        if self.done:
            p.setFont(font(20, QFont.DemiBold))
            p.drawText(QRectF(left, r.top() + 34, r.width() - 96, 30), Qt.AlignLeft | Qt.AlignVCenter,
                       label or f"{title} закончился")
        else:
            p.setFont(font(30, QFont.Light, display=True))
            p.drawText(QRectF(left, r.top() + 30, 150, 40), Qt.AlignLeft | Qt.AlignVCenter, clock(remain))
            if label:
                p.setPen(QColor(T.MUTED))
                p.setFont(font(13))
                fm = p.fontMetrics()
                p.drawText(QRectF(left + 132, r.top() + 34, r.width() - 222, 34),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(label, Qt.ElideRight, int(r.width() - 222)))
        # полоса прогресса
        total = max(1.0, self.item["end"] - self.item["start"])
        frac = 1.0 if self.done else 1 - remain / total
        bar = QRectF(left, r.bottom() - 26, r.width() - left - 18 + r.left(), 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.LINE))
        p.drawRoundedRect(bar, 2, 2)
        fill = QLinearGradient(bar.topLeft(), bar.topRight())
        fill.setColorAt(0, QColor(T.ACCENT))
        fill.setColorAt(1, QColor(T.ACCENT_SOFT))
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(4, bar.width() * frac), 4), 2, 2)
        # крестик
        xr = self._x_rect()
        if self._hover_x:
            p.setBrush(T.qcolor("#FFFFFF", 30))
            p.drawEllipse(xr)
        p.setPen(QPen(QColor(T.MUTED if not self._hover_x else T.TEXT), 1.6))
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

    def add(self, kind, seconds, label=""):
        now = time.time()
        item = {"id": self._next_id, "kind": kind, "start": now, "end": now + seconds,
                "label": label, "seconds": seconds}
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
                play_bell()
                self._fire(item)

    def _fire(self, item):
        kind, label = item["kind"], item.get("label")
        if kind == "timer":
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
