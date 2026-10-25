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
        t.timeout.connect(self.update)
        t.start(50)

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
        w, h = self.width(), self.height()
        sec = now.second + now.microsecond / 1e6
        # бегущая дуга секунд
        d = min(h - 8, 136)
        r = QRectF(w - d - 4, (h - d) / 2, d, d)
        p.setPen(QPen(T.qcolor(T.LINE), 3))
        p.drawEllipse(r)
        pen = QPen(QColor(T.ACCENT), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-sec / 60 * 360 * 16))
        ang = math.radians(90 - sec / 60 * 360)
        cx, cy, rad = r.center().x(), r.center().y(), d / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT_SOFT))
        p.drawEllipse(QPointF(cx + rad * math.cos(ang), cy - rad * math.sin(ang)), 5, 5)
        p.setPen(QColor(T.TEXT))
        p.setFont(font(15, QFont.DemiBold))
        p.drawText(r, Qt.AlignCenter, f"{now.second:02d}")
        # время крупно
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#FFFFFF"))
        g.setColorAt(1, QColor(T.ACCENT_SOFT))
        p.setPen(QPen(QBrush(g), 1))
        f = font(76, QFont.Light, display=True, spacing=-2)
        p.setFont(f)
        colon = ":" if now.microsecond < 500_000 else " "
        p.drawText(QRectF(0, 0, w - d - 12, h), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{now:%H}{colon}{now:%M}")

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

    def set_city(self, city):
        if city != self.city or self.last is None:
            self.city = city
            self.refresh()

    def refresh(self):
        city = self.city

        def work():
            try:
                self.bridge.done.emit(fetch_weather(city))
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


class SystemCard(QWidget):
    def __init__(self):
        super().__init__()
        self.frame, lay = card((24, 20, 24, 22), 0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        lay.addWidget(caption("КОМПЬЮТЕР"))
        lay.addSpacing(12)
        self.rows = {}
        for key, title in (("cpu", "Процессор"), ("ram", "Память"), ("bat", "Батарея")):
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 10)
            wl.setSpacing(6)
            head = QHBoxLayout()
            head.addWidget(label(title, 13, QFont.DemiBold))
            head.addStretch(1)
            val = label("—", 13, role="muted")
            head.addWidget(val)
            wl.addLayout(head)
            bar = Bar()
            wl.addWidget(bar)
            lay.addWidget(w)
            self.rows[key] = (w, val, bar)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def refresh(self):
        if not self.isVisible():
            return
        try:
            import psutil
        except Exception:  # noqa: BLE001
            return
        cpu = psutil.cpu_percent(None)
        mem = psutil.virtual_memory()
        self._set("cpu", cpu / 100, f"{cpu:.0f}%")
        self._set("ram", mem.percent / 100,
                  f"{mem.used / 1e9:.1f} из {mem.total / 1e9:.0f} ГБ")
        bat = None
        try:
            bat = psutil.sensors_battery()
        except Exception:  # noqa: BLE001
            pass
        w, _v, _b = self.rows["bat"]
        if bat is None:
            w.hide()
        else:
            w.show()
            self._set("bat", bat.percent / 100,
                      f"{bat.percent:.0f}%{' · заряжается' if bat.power_plugged else ''}")

    def _set(self, key, frac, text):
        _w, val, bar = self.rows[key]
        val.setText(text)
        bar.target = max(0.0, min(1.0, frac))


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
