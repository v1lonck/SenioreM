"""Виджеты главного экрана: часы, погода, система, громкость, заметки.
Включаются и выключаются в профиле → «Оформление»."""
import datetime
import json
import math
import threading
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

import theme as T
from theme import card, font, label

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря"]


def caption(text):
    return label(text, 11, QFont.DemiBold, "accent", spacing=1.8)


# ------------------------------------------------------------------ часы
class ClockFace(QWidget):
    """Цифровые часы с бегущей секундной дугой или классические стрелочные."""

    def __init__(self):
        super().__init__()
        self.style_name = "digital"
        self.setMinimumHeight(150)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(100)

    def _tick(self):
        w = self.window()
        if self.isVisible() and not (w and w.isMinimized()):
            self.update()

    def set_style(self, name):
        self.style_name = name
        self.setMinimumHeight(220 if name == "analog" else 150)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = datetime.datetime.now()
        if self.style_name == "analog":
            self._analog(p, now)
        else:
            self._digital(p, now)

    def _digital(self, p, now):
        from PySide6.QtGui import QFontMetrics
        w, h = self.width(), self.height()
        sec = now.second + now.microsecond / 1e6
        # бегущая дуга секунд справа
        d = min(h - 16, 96)
        r = QRectF(w - d - 4, (h - d) / 2, d, d)
        p.setPen(QPen(T.qcolor(T.LINE), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
        pen = QPen(QColor(T.ACCENT), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-sec / 60 * 360 * 16))
        ang = math.radians(90 - sec / 60 * 360)
        cx, cy, rad = r.center().x(), r.center().y(), d / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT_SOFT))
        p.drawEllipse(QPointF(cx + rad * math.cos(ang), cy - rad * math.sin(ang)), 4.5, 4.5)
        p.setPen(QColor(T.TEXT))
        p.setFont(font(14, QFont.DemiBold))
        p.drawText(r, Qt.AlignCenter, f"{now.second:02d}")
        # время — крупно, размер подбираем под ширину
        area = QRectF(0, 0, w - d - 18, h)
        size = 80
        while size > 30:
            f = font(size, QFont.Light, display=True, spacing=-1.5)
            if QFontMetrics(f).horizontalAdvance("00:00") <= area.width():
                break
            size -= 2
        p.setFont(f)
        g = QLinearGradient(0, h * 0.2, 0, h * 0.8)
        g.setColorAt(0, QColor("#FFFFFF"))
        g.setColorAt(1, QColor(T.ACCENT_SOFT))
        hh, mm = f"{now:%H}", f"{now:%M}"
        fm = QFontMetrics(f)
        x = area.left()
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(QRectF(x, 0, area.width(), h), Qt.AlignVCenter | Qt.AlignLeft, hh)
        x += fm.horizontalAdvance(hh)
        blink = 255 if now.microsecond < 500_000 else 90
        p.setPen(T.qcolor(T.ACCENT_SOFT, blink))
        p.drawText(QRectF(x, 0, area.width(), h), Qt.AlignVCenter | Qt.AlignLeft, ":")
        x += fm.horizontalAdvance(":")
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(QRectF(x, 0, area.width(), h), Qt.AlignVCenter | Qt.AlignLeft, mm)

    def _analog(self, p, now):
        w, h = self.width(), self.height()
        d = min(w, h) - 10
        c = QPointF(w / 2, h / 2)
        R = d / 2
        g = QLinearGradient(0, c.y() - R, 0, c.y() + R)
        g.setColorAt(0, T.qcolor(T._mix(T.SURFACE, "#FFFFFF", 0.08), 220))
        g.setColorAt(1, T.qcolor(T.SURFACE, 160))
        p.setPen(QPen(T.qcolor(T.ACCENT, 120), 2))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)
        for i in range(60):
            a = math.radians(i * 6)
            long_ = i % 5 == 0
            r1 = R - (14 if long_ else 7)
            p.setPen(QPen(QColor(T.TEXT if long_ else T.FAINT), 2.4 if long_ else 1))
            p.drawLine(QPointF(c.x() + r1 * math.sin(a), c.y() - r1 * math.cos(a)),
                       QPointF(c.x() + (R - 4) * math.sin(a), c.y() - (R - 4) * math.cos(a)))
        sec = now.second + now.microsecond / 1e6
        mins = now.minute + sec / 60
        hrs = now.hour % 12 + mins / 60

        def hand(angle_deg, length, width, color):
            a = math.radians(angle_deg)
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(c, QPointF(c.x() + length * math.sin(a), c.y() - length * math.cos(a)))

        hand(hrs * 30, R * 0.5, 6, T.TEXT)
        hand(mins * 6, R * 0.75, 4, T.TEXT)
        hand(sec * 6, R * 0.85, 2, T.ACCENT)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT))
        p.drawEllipse(c, 6, 6)


class ClockCard(QWidget):
    def __init__(self):
        super().__init__()
        self.frame, lay = card((24, 20, 24, 22))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.hello = label("", 22, QFont.Light, display=True, wrap=True)
        lay.addWidget(self.hello)
        self.face = ClockFace()
        lay.addWidget(self.face)
        self.date = label("", 14, role="muted")
        lay.addWidget(self.date)

    def tick(self, hello):
        now = datetime.datetime.now()
        self.hello.setText(hello)
        self.date.setText(f"{WEEKDAYS[now.weekday()].capitalize()}, {now.day} "
                          f"{MONTHS[now.month - 1]} {now.year}")


# ------------------------------------------------------------------ погода
WEATHER = {0: ("Ясно", "☀"), 1: ("Почти ясно", "🌤"), 2: ("Переменная облачность", "⛅"),
           3: ("Пасмурно", "☁"), 45: ("Туман", "🌫"), 48: ("Изморозь", "🌫"),
           51: ("Морось", "🌦"), 53: ("Морось", "🌦"), 55: ("Сильная морось", "🌧"),
           61: ("Небольшой дождь", "🌦"), 63: ("Дождь", "🌧"), 65: ("Ливень", "🌧"),
           66: ("Ледяной дождь", "🌧"), 67: ("Ледяной дождь", "🌧"),
           71: ("Небольшой снег", "🌨"), 73: ("Снег", "🌨"), 75: ("Сильный снег", "❄"),
           77: ("Снежная крупа", "🌨"), 80: ("Ливень", "🌦"), 81: ("Ливень", "🌧"),
           82: ("Сильный ливень", "⛈"), 85: ("Снегопад", "🌨"), 86: ("Сильный снегопад", "❄"),
           95: ("Гроза", "⛈"), 96: ("Гроза с градом", "⛈"), 99: ("Гроза с градом", "⛈")}


def _get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "SenioreM"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_weather(city=""):
    """-> dict(city, temp, feels, wind, humidity, code). Город — из настроек или по IP."""
    if city:
        geo = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&name="
                        + urllib.parse.quote(city))
        res = (geo.get("results") or [None])[0]
        if not res:
            raise RuntimeError(f"город «{city}» не найден")
        lat, lon, name = res["latitude"], res["longitude"], res.get("name", city)
    else:
        ip = _get_json("https://ipwho.is/?lang=ru")
        lat, lon, name = ip["latitude"], ip["longitude"], ip.get("city", "")
    data = _get_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                     "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,"
                     "relative_humidity_2m&wind_speed_unit=ms&timezone=auto" % (lat, lon))
    cur = data["current"]
    return {"city": name, "temp": cur["temperature_2m"], "feels": cur["apparent_temperature"],
            "wind": cur["wind_speed_10m"], "humidity": cur["relative_humidity_2m"],
            "code": cur["weather_code"]}


class _WeatherBridge(QObject):
    done = Signal(object)


class WeatherCard(QWidget):
    def __init__(self):
        super().__init__()
        self.city = ""
        self.last = None
        self.frame, lay = card((24, 20, 24, 20))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        head = QHBoxLayout()
        head.addWidget(caption("ПОГОДА"))
        head.addStretch(1)
        self.place = label("", 12, role="muted")
        head.addWidget(self.place)
        lay.addLayout(head)
        lay.addSpacing(6)
        row = QHBoxLayout()
        self.icon = label("", 46)
        row.addWidget(self.icon)
        row.addSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.temp = label("…", 40, QFont.Light, display=True)
        col.addWidget(self.temp)
        self.desc = label("Загружаю…", 13, role="muted", wrap=True)
        col.addWidget(self.desc)
        row.addLayout(col, 1)
        lay.addLayout(row)
        lay.addSpacing(6)
        self.details = label("", 12, role="faint", wrap=True)
        lay.addWidget(self.details)
        self.bridge = _WeatherBridge()
        self.bridge.done.connect(self._show)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(20 * 60 * 1000)

    def set_city(self, city, lat=None, lon=None):
        key = (city, lat, lon)
        if key != getattr(self, "_key", None) or self.last is None:
            self._key = key
            self.city = city
            self.refresh()

    def refresh(self):
        def work():
            try:
                import live
                d = live.weather(T.APPEARANCE)
                c = d["current"]
                self.bridge.done.emit({"city": d.get("_city", ""), "temp": c["temperature_2m"],
                                       "feels": c["apparent_temperature"],
                                       "wind": c["wind_speed_10m"],
                                       "humidity": c["relative_humidity_2m"],
                                       "code": c["weather_code"]})
            except Exception as e:  # noqa: BLE001
                self.bridge.done.emit({"error": str(e)})

        threading.Thread(target=work, daemon=True).start()

    def _show(self, d):
        if "error" in d:
            self.desc.setText("Нет данных о погоде")
            self.details.setText("Проверьте интернет или укажите город в профиле → «Оформление».")
            return
        self.last = d
        text, icon = WEATHER.get(int(d["code"]), ("", "🌡"))
        self.icon.setText(icon)
        t = round(d["temp"])
        self.temp.setText(f"{'+' if t > 0 else ''}{t}°")
        self.desc.setText(text)
        self.place.setText(d["city"])
        self.details.setText(f"Ощущается {round(d['feels'])}°  ·  ветер {round(d['wind'])} м/с  ·  "
                             f"влажность {round(d['humidity'])}%")

    def summary(self):
        if not self.last:
            return None
        text, _ = WEATHER.get(int(self.last["code"]), ("", ""))
        t = round(self.last["temp"])
        return f"Сейчас {t} градусов, {text.lower()}."


# ------------------------------------------------------------------ система
class Bar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.value = 0.0
        self.target = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

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


SYS_STYLES = [
    ("bars", "Полоски", "Подписи и полоски загрузки"),
    ("rings", "Кольца", "Круглые индикаторы, как на панели приборов"),
    ("graph", "Графики", "Как менялась нагрузка за последние минуты"),
    ("numbers", "Крупные цифры", "Только главное, крупно"),
]
GIB = 1024 ** 3


def _load_color(frac):
    """Цвет по нагрузке: спокойный цвет темы → жёлтый → красный."""
    if frac < 0.6:
        return QColor(T.ACCENT)
    if frac < 0.85:
        return QColor("#F2A33A")
    return QColor("#E5484D")


def _fmt_mb(b):
    return f"{b / GIB:.1f} ГБ" if b >= GIB else f"{b / 1024 ** 2:.0f} МБ"


def _fmt_rate(bps, bits=False):
    v = bps * 8 / 1e6 if bits else bps / 1024 ** 2
    unit = "Мбит/с" if bits else "МБ/с"
    return f"{v:.1f} {unit}" if v < 10 else f"{v:.0f} {unit}"


class _SysData:
    """Считает нагрузку так же, как «Диспетчер задач» Windows."""

    def __init__(self):
        self.ok = True
        try:
            import psutil
            self.ps = psutil
            psutil.cpu_percent(None)
            self.me = psutil.Process()
            self.me.cpu_percent(None)
            self.ncpu = psutil.cpu_count() or 1
            self._io = (psutil.disk_io_counters(), psutil.net_io_counters(), time_now())
        except Exception:  # noqa: BLE001
            self.ok = False
        self._kids = {}
        self._uss_t, self._uss = 0.0, 0
        self.hist = {"cpu": [], "ram": [], "app": []}

    def read(self):
        ps = self.ps
        d = {}
        d["cpu"] = ps.cpu_percent(None) / 100
        m = ps.virtual_memory()
        used = m.total - m.available                    # как «Используется» в Диспетчере задач
        d["ram"] = used / max(1, m.total)
        d["ram_used"], d["ram_total"] = used, m.total
        # SenioreM вместе с ИИ на компьютере (если запущен): процессор и память
        cpu = self.me.cpu_percent(None)
        procs = [self.me]
        try:
            for ch in self.me.children(recursive=True):
                if ch.pid not in self._kids:
                    self._kids[ch.pid] = ch
                    ch.cpu_percent(None)
                else:
                    cpu += self._kids[ch.pid].cpu_percent(None)
                procs.append(self._kids[ch.pid])
        except Exception:  # noqa: BLE001
            pass
        d["app_cpu"] = cpu / self.ncpu / 100
        now = time_now()
        if now - self._uss_t > 6:                       # «Память» как в Диспетчере задач (частный набор)
            self._uss_t = now
            tot = 0
            for pr in procs:
                try:
                    tot += pr.memory_full_info().uss
                except Exception:  # noqa: BLE001
                    try:
                        tot += pr.memory_info().rss
                    except Exception:  # noqa: BLE001
                        pass
            self._uss = tot
        d["app_mem"] = self._uss
        d["app"] = self._uss / max(1, m.total)
        try:
            dio, nio, t0 = self._io
            dio2, nio2 = ps.disk_io_counters(), ps.net_io_counters()
            dt = max(0.5, now - t0)
            d["disk"] = ((dio2.read_bytes + dio2.write_bytes) - (dio.read_bytes + dio.write_bytes)) / dt
            d["net"] = ((nio2.bytes_recv + nio2.bytes_sent) - (nio.bytes_recv + nio.bytes_sent)) / dt
            self._io = (dio2, nio2, now)
        except Exception:  # noqa: BLE001
            d["disk"] = d["net"] = 0.0
        try:
            b = ps.sensors_battery()
            d["bat"] = (b.percent, b.power_plugged) if b is not None else None
        except Exception:  # noqa: BLE001
            d["bat"] = None
        for k in ("cpu", "ram", "app"):
            h = self.hist[k]
            h.append(d["app_cpu"] if k == "app" else d[k])
            del h[:-60]
        return d


def time_now():
    import time
    return time.monotonic()


class SysView(QWidget):
    """Рисует нагрузку выбранным видом: полоски, кольца, графики или крупные цифры."""

    def __init__(self):
        super().__init__()
        self.d = None
        self.hist = None
        self.anim = {"cpu": 0.0, "ram": 0.0, "app": 0.0, "app_cpu": 0.0}
        self.t = QTimer(self)
        self.t.timeout.connect(self._tick)

    def style(self):
        s = T.APPEARANCE.get("sys_style") or "bars"
        return s if s in dict((k, n) for k, n, _ in SYS_STYLES) else "bars"

    def set_data(self, d, hist):
        self.d, self.hist = d, hist
        self.setFixedHeight({"bars": 186, "rings": 150, "graph": 196, "numbers": 150}[self.style()]
                            + (24 if d.get("bat") else 0))
        self.t.start(30)

    def _tick(self):
        busy = False
        for k in self.anim:
            goal = float(self.d.get(k, 0.0)) if self.d else 0.0
            if abs(goal - self.anim[k]) > 0.002:
                self.anim[k] += (goal - self.anim[k]) * 0.18
                busy = True
        self.update()
        if not busy:
            self.t.stop()

    # ---- общие куски
    def _text(self, p, x, y, w, h, s, size, weight=QFont.Normal, color=None, align=Qt.AlignLeft):
        p.setFont(font(size, weight))
        p.setPen(QColor(color or T.TEXT))
        p.drawText(QRectF(x, y, w, h), int(align | Qt.AlignVCenter), s)

    def _bar(self, p, x, y, w, frac):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.LINE))
        p.drawRoundedRect(QRectF(x, y, w, 6), 3, 3)
        c = _load_color(frac)
        g = QLinearGradient(x, 0, x + w, 0)
        g.setColorAt(0, c)
        g.setColorAt(1, QColor(c).lighter(130))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(x, y, max(6.0, w * max(0.0, min(1.0, frac))), 6), 3, 3)

    def _ring(self, p, cx, cy, r, frac, big, small):
        pen = QPen(QColor(T.LINE), 7)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawArc(rect, 225 * 16, -270 * 16)
        pen.setColor(_load_color(frac))
        p.setPen(pen)
        p.drawArc(rect, 225 * 16, int(-270 * 16 * max(0.0, min(1.0, frac))))
        self._text(p, cx - r, cy - 13, 2 * r, 22, big, 16, QFont.DemiBold, align=Qt.AlignHCenter)
        self._text(p, cx - r - 10, cy + r - 4, 2 * r + 20, 18, small, 11, color=T.MUTED, align=Qt.AlignHCenter)

    def _spark(self, p, x, y, w, h, hist, frac):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(QRectF(x, y, w, h), 8, 8)
        if len(hist) < 2:
            return
        from PySide6.QtGui import QPainterPath
        n = 60
        step = w / (n - 1)
        pts = [QPointF(x + w - (len(hist) - 1 - i) * step, y + h - 3 - (h - 6) * max(0.0, min(1.0, v)))
               for i, v in enumerate(hist)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        area = QPainterPath(path)
        area.lineTo(pts[-1].x(), y + h)
        area.lineTo(pts[0].x(), y + h)
        area.closeSubpath()
        c = _load_color(frac)
        g = QLinearGradient(0, y, 0, y + h)
        top = QColor(c)
        top.setAlpha(90)
        bot = QColor(c)
        bot.setAlpha(0)
        g.setColorAt(0, top)
        g.setColorAt(1, bot)
        p.setBrush(QBrush(g))
        p.drawPath(area)
        pen = QPen(c, 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def paintEvent(self, _):
        if not self.d:
            return
        d, a = self.d, self.anim
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        st = self.style()
        ram_txt = f"{d['ram_used'] / GIB:.1f} из {d['ram_total'] / GIB:.1f} ГБ"
        app_txt = f"{d['app_cpu'] * 100:.1f}% · {_fmt_mb(d['app_mem'])}"
        io_txt = f"Диск {_fmt_rate(d['disk'])}   ·   Сеть {_fmt_rate(d['net'], True)}"
        y = 0.0
        if st == "bars":
            for title, frac, val in (("Процессор", a["cpu"], f"{d['cpu'] * 100:.0f}%"),
                                     ("Память", a["ram"], f"{d['ram'] * 100:.0f}%  ·  {ram_txt}"),
                                     ("SenioreM", a["app_cpu"], app_txt)):
                self._text(p, 0, y, W, 20, title, 13, QFont.DemiBold)
                self._text(p, 0, y, W, 20, val, 12, color=T.MUTED, align=Qt.AlignRight)
                self._bar(p, 0, y + 26, W, frac)
                y += 46
            self._text(p, 0, y + 2, W, 18, io_txt, 12, color=T.MUTED)
            y += 26
        elif st == "rings":
            r = min(38.0, (W - 40) / 6)
            for i, (frac, big, small) in enumerate((
                    (a["cpu"], f"{d['cpu'] * 100:.0f}%", "процессор"),
                    (a["ram"], f"{d['ram'] * 100:.0f}%", "память"),
                    (a["app_cpu"], f"{d['app_cpu'] * 100:.0f}%", "SenioreM"))):
                cx = W * (i * 2 + 1) / 6
                self._ring(p, cx, 46, r, frac, big, small)
            self._text(p, 0, 106, W, 18, f"Память: {ram_txt}  ·  SenioreM: {_fmt_mb(d['app_mem'])}", 11,
                       color=T.MUTED, align=Qt.AlignHCenter)
            self._text(p, 0, 126, W, 18, io_txt, 11, color=T.MUTED, align=Qt.AlignHCenter)
            y = 150
        elif st == "graph":
            hist = self.hist or {}
            for title, key, val in (("Процессор", "cpu", f"{d['cpu'] * 100:.0f}%"),
                                    ("Память", "ram", f"{d['ram'] * 100:.0f}%  ·  {ram_txt}")):
                self._text(p, 0, y, W, 18, title, 12, QFont.DemiBold)
                self._text(p, 0, y, W, 18, val, 12, color=T.MUTED, align=Qt.AlignRight)
                self._spark(p, 0, y + 22, W, 46, hist.get(key, []), a[key])
                y += 76
            self._text(p, 0, y, W, 18, f"SenioreM: {app_txt}", 12, color=T.MUTED)
            self._text(p, 0, y + 20, W, 18, io_txt, 12, color=T.MUTED)
            y += 44
        else:
            cells = ((f"{d['cpu'] * 100:.0f}%", "процессор"), (f"{d['ram'] * 100:.0f}%", "память"),
                     (_fmt_mb(d["app_mem"]), "SenioreM"), (_fmt_rate(d["net"], True), "сеть"))
            for i, (big, small) in enumerate(cells):
                cx, cy = (i % 2) * W / 2, (i // 2) * 72
                self._text(p, cx, cy, W / 2, 38, big, 28, QFont.DemiBold,
                           color=_load_color(d["cpu"] if i == 0 else d["ram"] if i == 1 else 0).name())
                self._text(p, cx, cy + 36, W / 2, 18, small, 12, color=T.MUTED)
            y = 150
        if d.get("bat"):
            pct, plug = d["bat"]
            self._text(p, 0, y, W, 18, f"Батарея {pct:.0f}%" + (" · заряжается" if plug else ""), 12,
                       color=T.MUTED)
        p.end()


class SystemCard(QWidget):
    """Блок «Компьютер»: нагрузка процессора, памяти и самого SenioreM — те же числа,
    что и в «Диспетчере задач». Вид меняется в профиле → «Оформление»."""

    def __init__(self):
        super().__init__()
        self.frame, lay = card((24, 20, 24, 20), 0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        lay.addWidget(caption("КОМПЬЮТЕР"))
        lay.addSpacing(12)
        self.view = SysView()
        lay.addWidget(self.view)
        self.data = _SysData()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        QTimer.singleShot(300, self.refresh)

    def refresh(self):
        if not self.isVisible() or not self.data.ok:
            return
        try:
            d = self.data.read()
        except Exception:  # noqa: BLE001
            return
        self.view.set_data(d, self.data.hist)

    def restyle(self):
        if self.view.d:
            self.view.set_data(self.view.d, self.data.hist)


# ------------------------------------------------------------------ заметки
class NotesCard(QWidget):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.frame, lay = card((24, 20, 24, 20))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        lay.addWidget(caption("ЗАМЕТКИ"))
        lay.addSpacing(10)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Список дел, мысли, номера телефонов…")
        self.edit.setFont(font(14))
        self.edit.setMinimumHeight(120)
        self.edit.textChanged.connect(lambda: self.changed.emit(self.edit.toPlainText()))
        lay.addWidget(self.edit)

    def set_text(self, text):
        if text != self.edit.toPlainText():
            self.edit.blockSignals(True)
            self.edit.setPlainText(text or "")
            self.edit.blockSignals(False)
