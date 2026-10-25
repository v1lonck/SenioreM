"""Компаньон над панелью задач: милая фигурка, которая «говорит» вместе с помощником.
Все фигуры нарисованы кодом (оригинальные), цвета подстраиваются под тему."""
import math
import random

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import QWidget

import theme as T

FIGURES = [
    ("aki", "Аки", "Серебряные волосы"),
    ("mia", "Мия", "Кошачьи наушники"),
    ("rei", "Рэй", "Очки и бомбер"),
    ("cat", "Котик", "Пушистый кот"),
    ("fox", "Лисичка", "Рыжая лиса"),
    ("robot", "Робот", "Экран вместо лица"),
    ("none", "Нет", "Без компаньона"),
]
IMAGE_KINDS = ("aki", "mia", "rei")       # нарисованы заранее: assets/companions/<имя>_e*_m*.png
KIND_ALIASES = {"girl": "aki", "slime": "mia", "ghost": "rei"}
ASPECT = 820 / 400                         # высота / ширина картинки персонажа


def norm_kind(kind):
    return KIND_ALIASES.get(kind, kind)


def tall(kind):
    return norm_kind(kind) in IMAGE_KINDS


_FRAMES = {}


def _frames(kind, height):
    """9 кадров (глаза × рот), уменьшенных заранее до нужной высоты — рисовать их почти бесплатно."""
    key = (kind, int(height))
    if key not in _FRAMES:
        from PySide6.QtGui import QPixmap
        import config
        out = {}
        for e in range(3):
            for m in range(3):
                pix = QPixmap(str(config.resource_path(f"assets/companions/{kind}_e{e}_m{m}.png")))
                if not pix.isNull():
                    pix = pix.scaledToHeight(int(height), Qt.SmoothTransformation)
                out[(e, m)] = pix
        if len(_FRAMES) > 12:
            _FRAMES.clear()
        _FRAMES[key] = out
    return _FRAMES[key]


def _c(hex_, a=255):
    c = QColor(hex_)
    c.setAlpha(int(a))
    return c


class FigurePainter:
    """Рисует фигуру в квадрате 200×200 (масштабируется)."""

    def __init__(self):
        self.t = 0.0
        self.speaking = False
        self.listening = False
        self.animated = True
        self._blink = 0.0
        self._next_blink = 2.0
        self.mouth = 0.0

    def tick(self, dt):
        self.t += dt
        want = (0.25 + 0.75 * abs(math.sin(self.t * 13) * math.sin(self.t * 4.7 + 1))
                if self.speaking else 0.0)
        self.mouth += (want - self.mouth) * 0.5
        if self.animated or self.speaking:
            self._next_blink -= dt
            if self._next_blink <= 0:
                self._blink = 1.0
                self._next_blink = random.uniform(2.5, 5.5)
            self._blink = max(0.0, self._blink - dt * 7)

    def eye_open(self):
        return 1.0 - math.sin(min(1.0, self._blink) * math.pi)

    def bob(self):
        if not self.animated:
            return 0.0
        return 4 * math.sin(self.t * 2.0) + (2 * math.sin(self.t * 9) if self.speaking else 0)

    def sway(self):
        return 3 * math.sin(self.t * 1.3) if self.animated else 0.0

    # ------------------------------------------------------------------ общий рисунок
    def paint(self, p, rect, kind):
        kind = norm_kind(kind)
        if kind in IMAGE_KINDS:
            self._paint_image(p, rect, kind)
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        s = min(rect.width(), rect.height()) / 200.0
        p.translate(rect.center().x() - 100 * s, rect.center().y() - 100 * s)
        p.scale(s, s)
        # тень
        g = QRadialGradient(QPointF(100, 192), 60)
        g.setColorAt(0, _c("#000000", 90))
        g.setColorAt(1, _c("#000000", 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(100, 192), 62, 10)
        p.translate(0, self.bob())
        p.translate(100, 190)
        p.rotate(self.sway() * 0.6)
        p.translate(-100, -190)
        getattr(self, "_" + kind, self._cat)(p)
        p.restore()

    def _paint_image(self, p, rect, kind):
        h = min(rect.height(), rect.width() * ASPECT)
        frames = _frames(kind, h)
        op = self.eye_open()
        e = 0 if op > 0.7 else (1 if op > 0.25 else 2)
        m = 0 if self.mouth < 0.18 else (1 if self.mouth < 0.55 else 2)
        pix = frames.get((e, m))
        if pix is None or pix.isNull():
            return
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = pix.width() / pix.devicePixelRatio()
        x = rect.center().x() - w / 2
        y = rect.bottom() - h
        feet = QPointF(rect.center().x(), rect.bottom())
        # дыхание и лёгкое покачивание вокруг ступней
        breath = 1 + (0.006 * math.sin(self.t * 2.0) if self.animated else 0)
        p.translate(feet)
        p.rotate(self.sway() * 0.35)
        p.scale(1.0, breath)
        if self.speaking:
            p.translate(0, -1.2 * abs(math.sin(self.t * 7)))
        p.translate(-feet.x(), -feet.y())
        p.drawPixmap(QPointF(x, y), pix)
        p.restore()

    def _eyes(self, p, lx, rx, y, w, h, iris, glossy=True):
        op = self.eye_open()
        for x in (lx, rx):
            if op < 0.15:
                p.setPen(QPen(_c("#3A2A2A"), 3, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(QRectF(x - w, y - 4, w * 2, 10), 200 * 16, 140 * 16)
                continue
            hh = h * op
            p.setPen(Qt.NoPen)
            p.setBrush(_c("#FFFFFF"))
            p.drawEllipse(QPointF(x, y), w, hh)
            g = QLinearGradient(x, y - hh, x, y + hh)
            g.setColorAt(0, QColor(iris).darker(160))
            g.setColorAt(1, QColor(iris).lighter(130))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y + hh * 0.08), w * 0.78, hh * 0.86)
            p.setBrush(_c("#1A1020"))
            p.drawEllipse(QPointF(x, y + hh * 0.12), w * 0.38, hh * 0.45)
            if glossy:
                p.setBrush(_c("#FFFFFF", 235))
                p.drawEllipse(QPointF(x - w * 0.32, y - hh * 0.32), w * 0.26, hh * 0.22)
                p.drawEllipse(QPointF(x + w * 0.3, y + hh * 0.35), w * 0.12, hh * 0.1)
            if self.listening:
                p.setBrush(_c("#FFFFFF", 200))
                p.drawEllipse(QPointF(x + w * 0.35, y - hh * 0.45), w * 0.1, w * 0.1)

    def _mouth(self, p, x, y, w, color="#7A2E3A", closed="#5A2A2A"):
        m = self.mouth
        if m > 0.06:
            p.setPen(Qt.NoPen)
            p.setBrush(_c(color))
            p.drawEllipse(QPointF(x, y + 2), w * (0.55 + 0.25 * m), 2 + 9 * m)
            p.setBrush(_c("#F08A9A"))
            p.drawEllipse(QPointF(x, y + 4 + 5 * m), w * 0.35, 1.5 + 3 * m)
        else:
            p.setPen(QPen(_c(closed), 2.6, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(x - w * 0.5, y - 5, w, 8), 200 * 16, 140 * 16)

    # ------------------------------------------------------------------ девушка
    def _girl(self, p):
        hair = QColor(T._mix(T.ACCENT, "#FFFFFF", 0.35))
        hair_d = hair.darker(130)
        dress = QColor(T.ACCENT)
        skin = _c("#FFE6D8")
        # волосы сзади
        back = QPainterPath()
        back.moveTo(38, 92)
        back.cubicTo(30, 20, 170, 20, 162, 92)
        back.cubicTo(172, 150, 160, 178, 150, 186)
        back.lineTo(50, 186)
        back.cubicTo(40, 178, 28, 150, 38, 92)
        p.setPen(Qt.NoPen)
        g = QLinearGradient(0, 30, 0, 186)
        g.setColorAt(0, hair)
        g.setColorAt(1, hair_d)
        p.setBrush(QBrush(g))
        p.drawPath(back)
        # тело (платье с воротничком)
        body = QPainterPath()
        body.moveTo(66, 150)
        body.cubicTo(60, 170, 52, 190, 50, 196)
        body.lineTo(150, 196)
        body.cubicTo(148, 190, 140, 170, 134, 150)
        body.closeSubpath()
        bg = QLinearGradient(0, 150, 0, 196)
        bg.setColorAt(0, dress.lighter(115))
        bg.setColorAt(1, dress.darker(120))
        p.setBrush(QBrush(bg))
        p.drawPath(body)
        p.setBrush(_c("#FFFFFF"))
        collar = QPolygonF([QPointF(84, 150), QPointF(100, 166), QPointF(116, 150), QPointF(100, 156)])
        p.drawPolygon(collar)
        p.setBrush(_c("#E5484D"))
        p.drawEllipse(QPointF(100, 162), 5, 4)
        # шея и голова
        p.setBrush(skin)
        p.drawRoundedRect(QRectF(92, 138, 16, 16), 4, 4)
        p.drawEllipse(QPointF(100, 98), 58, 56)
        # чёлка
        bang = QPainterPath()
        bang.moveTo(40, 96)
        bang.cubicTo(36, 36, 164, 36, 160, 96)
        bang.cubicTo(150, 76, 140, 70, 132, 66)
        bang.cubicTo(130, 82, 122, 86, 116, 88)
        bang.cubicTo(116, 74, 108, 66, 100, 62)
        bang.cubicTo(96, 76, 86, 86, 78, 88)
        bang.cubicTo(78, 78, 72, 70, 66, 66)
        bang.cubicTo(58, 74, 48, 82, 40, 96)
        hg = QLinearGradient(0, 40, 0, 96)
        hg.setColorAt(0, hair.lighter(110))
        hg.setColorAt(1, hair)
        p.setBrush(QBrush(hg))
        p.drawPath(bang)
        # блик на волосах
        p.setPen(QPen(_c("#FFFFFF", 110), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(60, 46, 80, 40), 40 * 16, 100 * 16)
        p.setPen(Qt.NoPen)
        # боковые пряди
        for sx in (1, -1):
            lock = QPainterPath()
            x0 = 100 - sx * 56
            lock.moveTo(x0, 90)
            lock.cubicTo(x0 - sx * 6, 120, x0 - sx * 2, 150, x0 + sx * 6, 168)
            lock.cubicTo(x0 + sx * 12, 150, x0 + sx * 10, 120, x0 + sx * 12, 96)
            p.setBrush(hair)
            p.drawPath(lock)
        # заколка-звёздочка
        p.setBrush(_c("#FFD166"))
        star = QPolygonF()
        for k in range(10):
            r = 8 if k % 2 == 0 else 3.5
            a = -math.pi / 2 + k * math.pi / 5
            star.append(QPointF(140 + r * math.cos(a), 62 + r * math.sin(a)))
        p.drawPolygon(star)
        # лицо
        self._eyes(p, 78, 122, 106, 12, 15, T.ACCENT)
        p.setBrush(_c("#FF8FA3", 90))
        p.drawEllipse(QPointF(68, 124), 9, 5)
        p.drawEllipse(QPointF(132, 124), 9, 5)
        self._mouth(p, 100, 128, 14)

    # ------------------------------------------------------------------ кот
    def _cat(self, p):
        fur = _c("#C9CED8")
        fur_d = _c("#9AA1AE")
        p.setPen(Qt.NoPen)
        # хвост
        tail = QPainterPath()
        tw = 10 * math.sin(self.t * 2.5) if self.animated else 0
        tail.moveTo(150, 180)
        tail.cubicTo(185, 170, 180 + tw, 120, 168 + tw, 110)
        p.setPen(QPen(fur_d, 12, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(tail)
        p.setPen(Qt.NoPen)
        # тело
        p.setBrush(fur_d)
        p.drawEllipse(QPointF(100, 172), 52, 26)
        # уши
        for sx in (1, -1):
            ear = QPolygonF([QPointF(100 - sx * 50, 80), QPointF(100 - sx * 42, 26),
                             QPointF(100 - sx * 12, 58)])
            p.setBrush(fur)
            p.drawPolygon(ear)
            inner = QPolygonF([QPointF(100 - sx * 44, 74), QPointF(100 - sx * 40, 40),
                               QPointF(100 - sx * 22, 60)])
            p.setBrush(_c("#F5B7C4"))
            p.drawPolygon(inner)
        hg = QRadialGradient(QPointF(90, 80), 80)
        hg.setColorAt(0, fur.lighter(115))
        hg.setColorAt(1, fur)
        p.setBrush(QBrush(hg))
        p.drawEllipse(QPointF(100, 104), 60, 52)
        p.setBrush(_c("#FFFFFF", 200))
        p.drawEllipse(QPointF(100, 128), 26, 18)
        self._eyes(p, 76, 124, 100, 11, 13, "#7BC67B")
        p.setBrush(_c("#F28AA0"))
        p.drawPolygon(QPolygonF([QPointF(94, 118), QPointF(106, 118), QPointF(100, 124)]))
        self._mouth(p, 100, 130, 12, closed="#6B5B5B")
        p.setPen(QPen(_c("#6B7280", 160), 1.4))
        for sx in (1, -1):
            for dy in (-3, 3):
                p.drawLine(QPointF(100 + sx * 22, 124 + dy), QPointF(100 + sx * 54, 120 + dy * 2.5))

    # ------------------------------------------------------------------ лиса
    def _fox(self, p):
        orange = _c("#F28C38")
        p.setPen(Qt.NoPen)
        tw = 8 * math.sin(self.t * 2.2) if self.animated else 0
        tail = QPainterPath()
        tail.moveTo(140, 186)
        tail.cubicTo(200, 180, 190 + tw, 110, 160 + tw, 120)
        tail.cubicTo(170, 150, 150, 170, 130, 176)
        p.setBrush(orange)
        p.drawPath(tail)
        p.setBrush(_c("#FFFFFF"))
        p.drawEllipse(QPointF(170 + tw * 0.9, 124), 10, 8)
        p.setBrush(orange.darker(110))
        p.drawEllipse(QPointF(100, 172), 46, 26)
        for sx in (1, -1):
            ear = QPolygonF([QPointF(100 - sx * 54, 86), QPointF(100 - sx * 48, 22),
                             QPointF(100 - sx * 14, 56)])
            p.setBrush(orange)
            p.drawPolygon(ear)
            p.setBrush(_c("#3A2A2A"))
            p.drawPolygon(QPolygonF([QPointF(100 - sx * 49, 34), QPointF(100 - sx * 48, 22),
                                     QPointF(100 - sx * 40, 34)]))
        face = QPainterPath()
        face.moveTo(40, 92)
        face.cubicTo(40, 40, 160, 40, 160, 92)
        face.cubicTo(160, 126, 130, 146, 100, 150)
        face.cubicTo(70, 146, 40, 126, 40, 92)
        p.setBrush(orange)
        p.drawPath(face)
        cheeks = QPainterPath()
        cheeks.moveTo(48, 104)
        cheeks.cubicTo(70, 110, 88, 120, 100, 150)
        cheeks.cubicTo(112, 120, 130, 110, 152, 104)
        cheeks.cubicTo(150, 130, 126, 148, 100, 150)
        cheeks.cubicTo(74, 148, 50, 130, 48, 104)
        p.setBrush(_c("#FFF4EA"))
        p.drawPath(cheeks)
        self._eyes(p, 78, 122, 96, 10, 12, "#8B5A2B")
        p.setBrush(_c("#2A1E1E"))
        p.drawEllipse(QPointF(100, 132), 7, 5)
        self._mouth(p, 100, 140, 10, closed="#5A3A2A")

    # ------------------------------------------------------------------ робот
    def _robot(self, p):
        p.setPen(Qt.NoPen)
        metal = QLinearGradient(0, 40, 0, 160)
        metal.setColorAt(0, _c("#E6EAF2"))
        metal.setColorAt(1, _c("#A9B1C2"))
        # антенна
        p.setPen(QPen(_c("#8A93A6"), 4))
        p.drawLine(QPointF(100, 40), QPointF(100, 22))
        p.setPen(Qt.NoPen)
        blink = 0.5 + 0.5 * math.sin(self.t * 4)
        p.setBrush(_c(T.ACCENT, 140 + 115 * blink))
        p.drawEllipse(QPointF(100, 18), 7, 7)
        # тело
        p.setBrush(QBrush(metal))
        p.drawRoundedRect(QRectF(62, 150, 76, 44), 12, 12)
        p.setBrush(_c(T.ACCENT, 200))
        p.drawEllipse(QPointF(100, 172), 7, 7)
        # голова
        p.setBrush(QBrush(metal))
        p.drawRoundedRect(QRectF(40, 40, 120, 106), 30, 30)
        for sx in (1, -1):
            p.setBrush(_c("#8A93A6"))
            p.drawRoundedRect(QRectF(100 - sx * 66 - 7, 80, 14, 30), 6, 6)
        # экран
        p.setBrush(_c("#10131C"))
        p.drawRoundedRect(QRectF(54, 58, 92, 72), 20, 20)
        op = self.eye_open()
        glow = _c(T.ACCENT)
        p.setBrush(glow)
        for x in (80, 120):
            p.drawRoundedRect(QRectF(x - 9, 84 - 9 * op, 18, max(3, 18 * op)), 6, 6)
        # «рот» — эквалайзер
        p.setBrush(_c(T.ACCENT_SOFT))
        for i in range(5):
            hgt = 3 + (14 * self.mouth * abs(math.sin(self.t * 12 + i * 1.3)) if self.mouth > 0.05 else 0)
            p.drawRoundedRect(QRectF(82 + i * 8, 114 - hgt / 2, 5, hgt), 2, 2)

    # ------------------------------------------------------------------ слайм
    def _slime(self, p):
        col = QColor(T.ACCENT)
        wob = (math.sin(self.t * 3) * 6) if self.animated or self.speaking else 0
        path = QPainterPath()
        path.moveTo(30, 188)
        path.cubicTo(20, 120, 50 - wob, 50 + wob, 100, 50 - wob)
        path.cubicTo(150 + wob, 50 + wob, 180, 120, 170, 188)
        path.closeSubpath()
        g = QRadialGradient(QPointF(80, 90), 120)
        g.setColorAt(0, col.lighter(150))
        g.setColorAt(1, col.darker(110))
        p.setPen(QPen(col.darker(140), 2))
        c2 = QColor(col)
        p.setBrush(QBrush(g))
        p.setOpacity(0.92)
        p.drawPath(path)
        p.setOpacity(1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(_c("#FFFFFF", 150))
        p.drawEllipse(QPointF(70, 80), 14, 8)
        p.drawEllipse(QPointF(58, 96), 5, 4)
        self._eyes(p, 80, 120, 124, 11, 13, c2.darker(200).name())
        self._mouth(p, 100, 146, 14, color="#3A1F3A", closed="#3A1F3A")

    # ------------------------------------------------------------------ привидение
    def _ghost(self, p):
        float_y = 6 * math.sin(self.t * 1.6) if self.animated else 0
        p.translate(0, float_y - 6)
        path = QPainterPath()
        path.moveTo(40, 100)
        path.cubicTo(40, 30, 160, 30, 160, 100)
        path.lineTo(160, 176)
        ph = self.t * 4 if self.animated else 0
        for k in range(6):
            x1 = 160 - (k + 0.5) * 20
            x2 = 160 - (k + 1) * 20
            path.quadTo(QPointF(x1, 196 + 6 * math.sin(ph + k)), QPointF(x2, 178))
        path.closeSubpath()
        g = QLinearGradient(0, 30, 0, 190)
        g.setColorAt(0, _c("#FFFFFF", 245))
        g.setColorAt(1, _c(T._mix("#FFFFFF", T.ACCENT, 0.25), 225))
        p.setPen(QPen(_c(T.ACCENT, 90), 2))
        p.setBrush(QBrush(g))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        self._eyes(p, 80, 120, 96, 10, 13, "#3A3A55", glossy=True)
        p.setBrush(_c("#FF9EB5", 110))
        p.drawEllipse(QPointF(68, 116), 8, 4)
        p.drawEllipse(QPointF(132, 116), 8, 4)
        self._mouth(p, 100, 120, 12, color="#3A3A55", closed="#3A3A55")


# ------------------------------------------------------------------ окно над панелью задач
class CompanionWindow(QWidget):
    def __init__(self, on_click=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.painter = FigurePainter()
        self.kind = "aki"
        self.size_px = 150
        self.fig_w = self.fig_h = 150
        self.on_click = on_click
        self.text = ""
        self._text_until = 0.0
        self._drag = None
        self._moved = False
        self._custom_pos = None
        self.setToolTip("SenioreM — нажмите, чтобы открыть")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def configure(self, kind, animated, size):
        self.kind = norm_kind(kind)
        self.painter.animated = animated
        self.size_px = int(size)
        if tall(self.kind):                 # персонаж в полный рост
            self.fig_h = int(self.size_px * 2.0)
            self.fig_w = int(self.fig_h / ASPECT) + 8
            w, h = self.fig_w + int(self.size_px * 1.6), self.fig_h + 10
        else:
            self.fig_w = self.fig_h = self.size_px
            w, h = int(self.size_px * 2.1), int(self.size_px * 1.55)
        self.setFixedSize(w, h)
        self.place()

    def place(self):
        if self._custom_pos is not None:
            self.move(self._custom_pos)
            return
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 12, geo.bottom() - self.height() + 4)

    def say(self, text, seconds=6.0):
        import time
        self.text = text[:90] + ("…" if len(text) > 90 else "")
        self._text_until = time.time() + seconds

    def set_speaking(self, flag):
        self.painter.speaking = flag

    def set_listening(self, flag):
        self.painter.listening = flag

    def _tick(self):
        import time
        self.painter.tick(0.04)
        if self.text and time.time() > self._text_until and not self.painter.speaking:
            self.text = ""
        if self.painter.animated or self.painter.speaking or self.painter._blink > 0 or self.text:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fig = QRectF(self.width() - self.fig_w - 6, self.height() - self.fig_h - 4,
                     self.fig_w, self.fig_h)
        self.painter.paint(p, fig, self.kind)
        if self.text:
            p.setFont(T.font(13))
            fm = p.fontMetrics()
            maxw = int(self.width() - self.fig_w * 0.55)
            br = fm.boundingRect(0, 0, maxw - 24, 200, Qt.TextWordWrap, self.text)
            bw, bh = br.width() + 24, br.height() + 16
            if tall(self.kind):
                x = max(4, fig.left() - bw + self.fig_w * 0.3)
                y = max(4, fig.top() + self.fig_h * 0.06)
            else:
                x = max(4, fig.left() - bw + self.size_px * 0.35)
                y = max(4, fig.top() - bh * 0.15)
            r = QRectF(x, y, bw, bh)
            path = QPainterPath()
            path.addRoundedRect(r, 12, 12)
            tail = QPolygonF([QPointF(r.right() - 26, r.bottom() - 2), QPointF(r.right() - 6, r.bottom() + 12),
                              QPointF(r.right() - 12, r.bottom() - 2)])
            path.addPolygon(tail)
            p.setPen(QPen(_c(T.ACCENT, 160), 1.2))
            p.setBrush(_c(T.SURFACE, 240))
            p.drawPath(path.simplified())
            p.setPen(QColor(T.TEXT))
            p.drawText(r.adjusted(12, 8, -12, -8), Qt.TextWordWrap, self.text)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            pos = e.globalPosition().toPoint() - self._drag
            if (pos - self.pos()).manhattanLength() > 3:
                self._moved = True
                self.move(pos)

    def mouseReleaseEvent(self, e):
        if self._moved:
            self._custom_pos = QPoint(self.pos())
        elif self.on_click:
            self.on_click()
        self._drag = None


class FigurePreview(QWidget):
    """Живой предпросмотр фигуры в настройках."""

    def __init__(self, size=180):
        super().__init__()
        self.setFixedSize(size, int(size * 1.7))
        self.painter = FigurePainter()
        self.kind = "aki"
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

    def _tick(self):
        if self.isVisible():
            self.painter.tick(0.04)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if self.kind == "none":
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(14))
            p.drawText(self.rect(), Qt.AlignCenter, "Без компаньона")
            return
        r = QRectF(self.rect())
        if not tall(self.kind):
            r = QRectF(0, r.height() - r.width() - 10, r.width(), r.width())
        self.painter.paint(p, r, self.kind)


def thumb(kind, w, h):
    """Карточка-портрет для выбора персонажа в настройках."""
    from PySide6.QtGui import QPixmap
    kind = norm_kind(kind)
    pix = QPixmap(w, h)
    pix.fill(QColor("#0B0E15"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    g = QRadialGradient(QPointF(w / 2, h * 0.35), max(w, h) * 0.8)
    g.setColorAt(0, _c(T.ACCENT, 70))
    g.setColorAt(1, _c(T.ACCENT, 0))
    p.fillRect(pix.rect(), QBrush(g))
    if kind in IMAGE_KINDS:
        fr = _frames(kind, h * 1.9).get((0, 0))
        if fr is not None and not fr.isNull():
            p.drawPixmap(QPointF((w - fr.width()) / 2, h * 0.02 - fr.height() * 0.02), fr)
    elif kind == "none":
        p.setPen(QPen(_c("#FFFFFF", 90), 3))
        p.drawEllipse(QPointF(w / 2, h * 0.42), 26, 26)
        p.drawLine(QPointF(w / 2 - 18, h * 0.42 + 18), QPointF(w / 2 + 18, h * 0.42 - 18))
    else:
        fp = FigurePainter()
        fp.animated = False
        fp.paint(p, QRectF(w * 0.08, h * 0.04, w * 0.84, w * 0.84), kind)
    p.end()
    return pix
