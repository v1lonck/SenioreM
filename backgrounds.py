"""Анимированные фоны: космос, галактика, гиперпрыжок, северное сияние, ретро-сетка, волны.

Тяжёлые части (туманности, галактика, планета) рисуются один раз в картинку, а каждый
кадр только сдвигается/поворачивается и поверх добавляются мерцающие звёзды — так фон
выглядит богато и почти не нагружает компьютер."""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)

import theme as T


def _accent_set():
    a = QColor(T.ACCENT)
    h, s, v, _ = a.getHsv()
    h = h if h >= 0 else 225
    return (QColor.fromHsv(h, max(120, s), 255),
            QColor.fromHsv((h + 45) % 360, 170, 235),
            QColor.fromHsv((h + 300) % 360, 160, 230),
            QColor.fromHsv((h + 190) % 360, 120, 220))


def _c(col, alpha):
    c = QColor(col)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


def _cache(bd, key, make):
    store = bd.__dict__.setdefault("_bg_cache", {})
    if key not in store:
        if len(store) > 8:
            store.clear()
        store[key] = make()
    return store[key]


# ------------------------------------------------------------------ общие слои
def _stars(bd, n, seed):
    def make():
        rnd = random.Random(seed)
        out = []
        for _ in range(n):
            depth = rnd.random() ** 2.2
            out.append((rnd.random(), rnd.random(), 0.35 + 1.6 * depth, rnd.uniform(0, 6.28),
                        rnd.uniform(0.5, 2.2), depth, rnd.random()))
        return out
    return _cache(bd, ("stars", n, seed), make)


def _nebula(bd, w, h):
    """Туманность: много мягких цветных облаков (рисуем в 1/6 размера и растягиваем)."""
    def make():
        sw, sh = max(8, w // 6), max(8, h // 6)
        pix = QPixmap(sw, sh)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        rnd = random.Random(11)
        cols = _accent_set()
        # главная «река» туманности по диагонали
        for i in range(70):
            u = rnd.random()
            x = sw * (0.05 + 0.95 * u) + rnd.gauss(0, sw * 0.08)
            y = sh * (0.85 - 0.7 * u) + rnd.gauss(0, sh * 0.12)
            r = max(sw, sh) * rnd.uniform(0.05, 0.22)
            col = cols[rnd.choice((0, 0, 1, 2, 2, 3))]
            g = QRadialGradient(QPointF(x, y), r)
            g.setColorAt(0, _c(col, rnd.uniform(14, 34)))
            g.setColorAt(1, _c(col, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), r, r)
        # тёмные пылевые прожилки
        p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        for i in range(26):
            u = rnd.random()
            x = sw * u + rnd.gauss(0, sw * 0.05)
            y = sh * (0.8 - 0.6 * u) + rnd.gauss(0, sh * 0.06)
            r = max(sw, sh) * rnd.uniform(0.02, 0.07)
            g = QRadialGradient(QPointF(x, y), r)
            g.setColorAt(0, QColor(0, 0, 0, 90))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), r, r)
        p.end()
        return pix
    return _cache(bd, ("nebula", w, h, T.ACCENT), make)


def _planet(bd, d):
    def make():
        size = int(d * 1.5)
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(size / 2, size / 2)
        r = d / 2
        cols = _accent_set()
        # атмосфера
        g = QRadialGradient(c, r * 1.45)
        g.setColorAt(0.62, _c(cols[0], 0))
        g.setColorAt(0.70, _c(cols[0], 70))
        g.setColorAt(1.0, _c(cols[0], 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r * 1.45, r * 1.45)
        # тело планеты: освещена сверху-слева
        body = QRadialGradient(QPointF(c.x() - r * 0.45, c.y() - r * 0.5), r * 1.7)
        body.setColorAt(0.0, QColor(cols[0]).lighter(115))
        body.setColorAt(0.35, QColor(cols[0]).darker(170))
        body.setColorAt(0.75, QColor("#05060C"))
        body.setColorAt(1.0, QColor("#020308"))
        p.setBrush(QBrush(body))
        p.drawEllipse(c, r, r)
        # полосы облаков
        p.save()
        path = QPainterPath()
        path.addEllipse(c, r, r)
        p.setClipPath(path)
        rnd = random.Random(5)
        for i in range(9):
            y = c.y() - r + (i + 0.5) * (2 * r / 9) + rnd.uniform(-4, 4)
            col = _c(cols[1] if i % 2 else cols[3], 22)
            p.setPen(QPen(col, r * rnd.uniform(0.04, 0.1)))
            p.drawLine(QPointF(c.x() - r, y), QPointF(c.x() + r, y + rnd.uniform(-8, 8)))
        p.restore()
        # тонкий светлый край
        rim = QPen(_c("#FFFFFF", 60), 1.5)
        p.setPen(rim)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 70 * 16, 110 * 16)
        p.end()
        return pix
    return _cache(bd, ("planet", d, T.ACCENT), make)


_VIG = {}


def _vignette(p, w, h, strength=170):
    key = (int(w), int(h), strength)
    if key not in _VIG:
        if len(_VIG) > 6:
            _VIG.clear()
        pix = QPixmap(max(1, int(w) // 4), max(1, int(h) // 4))
        pix.fill(Qt.transparent)
        q = QPainter(pix)
        g = QRadialGradient(QPointF(pix.width() / 2, pix.height() / 2), max(pix.width(), pix.height()) * 0.75)
        g.setColorAt(0.55, QColor(0, 0, 0, 0))
        g.setColorAt(1.0, QColor(0, 0, 0, strength))
        q.fillRect(pix.rect(), QBrush(g))
        q.end()
        _VIG[key] = pix
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(QRectF(0, 0, w, h), _VIG[key], QRectF(_VIG[key].rect()))
    p.restore()


def _draw_stars(p, bd, w, h, t, n=260, drift=0.006, seed=42):
    p.setPen(Qt.NoPen)
    tint = QColor(T.ACCENT_SOFT)
    for x, y, size, ph, spd, depth, hue in _stars(bd, n, seed):
        xx = ((x - t * drift * (0.2 + depth)) % 1.0) * w
        tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * spd + ph))
        col = QColor("#FFFFFF") if hue < 0.75 else tint
        col.setAlphaF(min(1.0, tw * (0.35 + 0.65 * depth)))
        p.setBrush(col)
        p.drawEllipse(QPointF(xx, y * h), size * 0.5, size * 0.5)
        if depth > 0.75:                       # яркие звёзды — с крестиком-сиянием
            col.setAlphaF(0.25 * tw)
            p.setPen(QPen(col, 0.8))
            L = size * 3.5 * tw
            p.drawLine(QPointF(xx - L, y * h), QPointF(xx + L, y * h))
            p.drawLine(QPointF(xx, y * h - L), QPointF(xx, y * h + L))
            p.setPen(Qt.NoPen)


def _shooting_star(p, w, h, t, period=7.0, seed=0):
    if T.focused():
        return                                 # во время разговора фон стоит — без «застывших» звёзд
    k = int(t // period)
    u = (t % period) / 1.1                     # пролёт длится ~1.1 с
    if u > 1.0:
        return
    rnd = random.Random(k * 31 + seed)
    x0, y0 = w * rnd.uniform(0.15, 0.95), h * rnd.uniform(0.0, 0.45)
    ang = math.radians(rnd.uniform(140, 165))
    dist = w * 0.35
    x, y = x0 + math.cos(ang) * dist * u, y0 + math.sin(ang) * dist * u
    tail = w * 0.12 * (1 - abs(0.5 - u))
    tx, ty = x - math.cos(ang) * tail, y - math.sin(ang) * tail
    g = QLinearGradient(QPointF(x, y), QPointF(tx, ty))
    alpha = 230 * math.sin(math.pi * u)
    g.setColorAt(0, _c("#FFFFFF", alpha))
    g.setColorAt(1, _c(T.ACCENT_SOFT, 0))
    p.setPen(QPen(QBrush(g), 2.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x, y), QPointF(tx, ty))


# ------------------------------------------------------------------ фоны
def paint_space(bd, p, w, h, t):
    """Глубокий космос: туманность, планета, мерцающие звёзды и падающие звёзды."""
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#03040A"))
    g.setColorAt(1, QColor(T._mix("#05060F", T.ACCENT, 0.06)))
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    neb = _nebula(bd, w, h)
    # медленный «наезд камеры»
    s = 1.08 + 0.04 * math.sin(t * 0.05)
    dx = w * 0.03 * math.sin(t * 0.03)
    dy = h * 0.02 * math.cos(t * 0.04)
    p.save()
    p.translate(w / 2 + dx, h / 2 + dy)
    p.scale(s, s)
    p.translate(-w / 2, -h / 2)
    p.drawPixmap(QRectF(0, 0, w, h), neb, QRectF(neb.rect()))
    p.restore()
    p.setRenderHint(QPainter.Antialiasing)
    _draw_stars(p, bd, w, h, t)
    d = min(w, h) * 0.55
    pl = _planet(bd, int(d))
    p.drawPixmap(QPointF(w - d * 0.95, h - d * 0.62), pl)
    _shooting_star(p, w, h, t, 8.0, 1)
    _shooting_star(p, w, h, t + 3.7, 11.0, 2)
    _vignette(p, w, h, 150)


def _galaxy(bd, size):
    def make():
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        c = size / 2
        cols = _accent_set()
        rnd = random.Random(3)
        # мягкое свечение диска
        g = QRadialGradient(QPointF(c, c), c)
        g.setColorAt(0, _c("#FFF4E0", 200))
        g.setColorAt(0.08, _c("#FFD9A8", 120))
        g.setColorAt(0.3, _c(cols[0], 40))
        g.setColorAt(1, _c(cols[0], 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(c, c), c, c)
        arms = 3
        for i in range(5200):
            arm = i % arms
            r = rnd.random() ** 0.75
            ang = arm * 2 * math.pi / arms + r * 4.6 + rnd.gauss(0, 0.32 * (1.1 - r))
            rr = r * c * 0.95
            x = c + math.cos(ang) * rr + rnd.gauss(0, c * 0.02)
            y = c + math.sin(ang) * rr + rnd.gauss(0, c * 0.02)
            if r < 0.15:
                col = _c("#FFE9C7", 160)
            else:
                col = _c(cols[rnd.choice((0, 0, 1, 2, 3))] if rnd.random() < 0.6 else QColor("#FFFFFF"),
                         60 + 140 * (1 - r) * rnd.random())
            p.setBrush(col)
            s = rnd.uniform(0.5, 1.6) * (1.3 - r * 0.6)
            p.drawEllipse(QPointF(x, y), s, s)
        # пыль на рукавах
        for i in range(260):
            arm = i % arms
            r = rnd.uniform(0.2, 0.9)
            ang = arm * 2 * math.pi / arms + r * 4.6 + 0.25
            x = c + math.cos(ang) * r * c * 0.95
            y = c + math.sin(ang) * r * c * 0.95
            rad = c * rnd.uniform(0.03, 0.08)
            gg = QRadialGradient(QPointF(x, y), rad)
            gg.setColorAt(0, _c(cols[rnd.choice((0, 2))], 30))
            gg.setColorAt(1, _c(cols[0], 0))
            p.setBrush(QBrush(gg))
            p.drawEllipse(QPointF(x, y), rad, rad)
        p.end()
        return pix
    return _cache(bd, ("galaxy", size, T.ACCENT), make)


def paint_galaxy(bd, p, w, h, t):
    p.fillRect(QRectF(0, 0, w, h), QColor("#020309"))
    p.setRenderHint(QPainter.Antialiasing)
    _draw_stars(p, bd, w, h, t, n=200, drift=0.002, seed=7)
    size = int(min(w, h) * 1.25)
    gal = _galaxy(bd, size)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.save()
    p.translate(w * 0.62, h * 0.52)
    p.rotate(-18)
    p.scale(1.0, 0.42)                         # диск наклонён к нам
    p.rotate(math.degrees(t * 0.025))
    p.drawPixmap(QPointF(-size / 2, -size / 2), gal)
    p.restore()
    _shooting_star(p, w, h, t, 9.0, 4)
    _vignette(p, w, h, 160)


def paint_warp(bd, p, w, h, t):
    """Полёт сквозь звёзды."""
    p.fillRect(QRectF(0, 0, w, h), QColor("#020308"))
    g = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.6)
    g.setColorAt(0, _c(T.ACCENT, 38))
    g.setColorAt(1, _c(T.ACCENT, 0))
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    p.setRenderHint(QPainter.Antialiasing)
    stars = _cache(bd, ("warp",), lambda: [(random.Random(i).uniform(-1, 1),
                                            random.Random(i + 999).uniform(-1, 1),
                                            random.Random(i + 77).random()) for i in range(320)])
    cx, cy = w / 2, h / 2
    f = min(w, h) * 0.5
    speed = 0.07
    tint = QColor(T.ACCENT_SOFT)
    for sx, sy, z0 in stars:
        z = 1.0 - ((z0 + t * speed) % 1.0)              # 1 — далеко, 0 — рядом
        z = max(0.03, z)
        z2 = min(1.0, z + 0.018 + 0.02 * z)
        x1, y1 = cx + sx / z * f, cy + sy / z * f
        x2, y2 = cx + sx / z2 * f, cy + sy / z2 * f
        if not (-50 < x1 < w + 50 and -50 < y1 < h + 50):
            continue
        a = min(1.0, (1 - z) * 1.4)
        col = QColor("#FFFFFF") if z0 > 0.3 else QColor(tint)
        col.setAlphaF(a)
        p.setPen(QPen(col, 0.5 + 1.2 * (1 - z), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x2, y2), QPointF(x1, y1))
    _vignette(p, w, h, 140)


def paint_aurora(bd, p, w, h, t):
    """Северное сияние: занавеси света над тёмными горами и звёздами."""
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor("#02040B"))
    g.setColorAt(1, QColor(T._mix("#04070F", T.ACCENT, 0.08)))
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    p.setRenderHint(QPainter.Antialiasing)
    _draw_stars(p, bd, w, h * 0.7, t, n=160, drift=0.0015, seed=9)
    cols = _accent_set()
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for k in range(3):
        col = cols[(k * 2) % 4] if k else cols[0]
        base_y = h * (0.3 + 0.08 * k)
        path = QPainterPath()
        pts = []
        for i in range(41):
            u = i / 40
            y = base_y + h * 0.07 * math.sin(u * 5 + t * (0.25 + 0.07 * k) + k * 2) \
                + h * 0.035 * math.sin(u * 13 - t * 0.4 + k)
            pts.append((w * u, y))
        path.moveTo(pts[0][0], pts[0][1] - h * 0.22)
        for x, y in pts:
            path.lineTo(x, y - h * 0.22)
        for x, y in reversed(pts):
            path.lineTo(x, y)
        path.closeSubpath()
        gg = QLinearGradient(0, base_y - h * 0.24, 0, base_y + h * 0.05)
        gg.setColorAt(0, _c(col, 0))
        gg.setColorAt(0.75, _c(col, 46 - 8 * k))
        gg.setColorAt(1, _c(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gg))
        p.drawPath(path)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    # горы
    rnd = random.Random(2)
    for layer, (shade, top) in enumerate(((0.10, 0.74), (0.05, 0.82))):
        path = QPainterPath()
        path.moveTo(0, h)
        x = 0.0
        y = h * top
        path.lineTo(0, y)
        while x < w:
            x += w * rnd.uniform(0.04, 0.09)
            y = h * (top + rnd.uniform(-0.07, 0.05))
            path.lineTo(x, y)
        path.lineTo(w, h)
        path.closeSubpath()
        p.setBrush(QColor(T._mix("#03050A", T.ACCENT, shade)))
        p.drawPath(path)
    _vignette(p, w, h, 120)


def paint_waves(bd, p, w, h, t):
    p.fillRect(QRectF(0, 0, w, h), QColor(T.BG))
    p.setRenderHint(QPainter.Antialiasing)
    cols = _accent_set()
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for i in range(5):
        path = QPainterPath()
        amp = h * (0.06 + 0.02 * i)
        base = h * (0.58 + 0.05 * i)
        path.moveTo(0, h)
        for k in range(0, 97):
            x = w * k / 96
            y = base + amp * math.sin(k / 96 * 6.28 * (1.1 + 0.2 * i) + t * (0.35 + 0.08 * i) + i) \
                + amp * 0.35 * math.sin(k / 96 * 6.28 * 3 - t * 0.5)
            path.lineTo(x, y)
        path.lineTo(w, h)
        path.closeSubpath()
        g = QLinearGradient(0, base - amp, 0, h)
        g.setColorAt(0, _c(cols[i % 4], 42 - 5 * i))
        g.setColorAt(1, _c(cols[i % 4], 0))
        p.setPen(QPen(_c(cols[i % 4], 90 - 12 * i), 1.4))
        p.setBrush(QBrush(g))
        p.drawPath(path)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)


def paint_grid(bd, p, w, h, t):
    """Ретро-сетка 80-х: солнце, горизонт и бегущие линии."""
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor("#05030D"))
    g.setColorAt(0.58, QColor(T._mix("#12061F", T.ACCENT, 0.25)))
    g.setColorAt(1, QColor("#04020A"))
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    p.setRenderHint(QPainter.Antialiasing)
    _draw_stars(p, bd, w, h * 0.62, t, n=110, drift=0.001, seed=3)
    horizon = h * 0.68
    cols = _accent_set()
    r = h * 0.14
    sun_c = QPointF(w / 2, horizon - r * 0.35)
    sg = QLinearGradient(0, sun_c.y() - r, 0, sun_c.y() + r)
    sg.setColorAt(0, QColor("#FFD36E"))
    sg.setColorAt(1, QColor(cols[2]))
    p.save()
    clip = QPainterPath()
    clip.addRect(QRectF(0, 0, w, horizon))
    p.setClipPath(clip)
    glow = QRadialGradient(sun_c, r * 2.2)
    glow.setColorAt(0, _c(cols[2], 90))
    glow.setColorAt(1, _c(cols[2], 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(sun_c, r * 2.2, r * 2.2)
    p.setBrush(QBrush(sg))
    p.drawEllipse(sun_c, r, r)
    p.setBrush(QColor("#05030D"))
    for i in range(6):                        # прорези в солнце
        yy = sun_c.y() + r * (0.1 + i * 0.15)
        p.drawRect(QRectF(sun_c.x() - r, yy, 2 * r, 2 + i * 1.6))
    p.restore()
    col = QColor(cols[0])
    for i in range(1, 22):
        z = (i - (t * 0.9) % 1.0) / 21
        y = horizon + (h - horizon) * (z ** 2.2)
        col.setAlphaF(0.08 + 0.5 * z)
        p.setPen(QPen(col, 1.0 + 1.4 * z))
        p.drawLine(QPointF(0, y), QPointF(w, y))
    for k in range(-16, 17):
        col.setAlphaF(0.35)
        p.setPen(QPen(col, 1.1))
        p.drawLine(QPointF(w / 2 + k * w * 0.012, horizon), QPointF(w / 2 + k * w * 0.11, h))
    p.setPen(QPen(_c(cols[2], 200), 2))
    p.drawLine(QPointF(0, horizon), QPointF(w, horizon))


PAINTERS = {"space": paint_space, "galaxy": paint_galaxy, "warp": paint_warp,
            "aurora": paint_aurora, "waves": paint_waves, "grid": paint_grid}


# ------------------------------------------------------------------ свой фон
class _Custom:
    """Своя картинка (PNG/JPG — статичная) или GIF/WebP (анимированная) из APPEARANCE["custom_bg"]."""

    def __init__(self):
        self.path = None
        self.movie = None
        self.image = None
        self.frame = None
        self.next_at = 0.0
        self._scaled = None

    def _load(self, path):
        from PySide6.QtGui import QImage, QMovie
        self.path, self.movie, self.image, self.frame, self._scaled = path, None, None, None, None
        if not path:
            return
        import os
        if not os.path.isfile(path):
            return
        if path.lower().endswith((".gif", ".webp", ".apng")):
            m = QMovie(path)
            m.setCacheMode(QMovie.CacheNone)
            if m.isValid() and m.frameCount() != 1 and m.jumpToFrame(0):
                self.movie = m
                self.frame = m.currentImage()
                return
        img = QImage(path)
        if not img.isNull():
            if img.width() > 3840:
                img = img.scaledToWidth(3840, Qt.SmoothTransformation)
            self.image = img

    def ensure(self):
        p = T.APPEARANCE.get("custom_bg") or ""
        if p != self.path:
            self._load(p)

    def animated(self):
        self.ensure()
        return self.movie is not None

    def current(self):
        """Текущий кадр (QImage) с учётом времени кадров GIF."""
        import time
        self.ensure()
        if self.movie is None:
            return self.image
        now = time.monotonic()
        if now >= self.next_at:
            m = self.movie
            if not m.jumpToNextFrame():
                m.jumpToFrame(0)
            self.frame = m.currentImage()
            delay = m.nextFrameDelay()
            self.next_at = now + max(0.02, (delay if delay > 0 else 80) / 1000.0)
        return self.frame


CUSTOM = _Custom()


def _cover(img, w, h):
    """Прямоугольник-источник, чтобы картинка заполнила экран без искажений (обрезка краёв)."""
    iw, ih = img.width(), img.height()
    if iw <= 0 or ih <= 0:
        return QRectF(0, 0, 1, 1)
    k = max(w / iw, h / ih)
    sw, sh = w / k, h / k
    return QRectF((iw - sw) / 2, (ih - sh) / 2, sw, sh)


def paint_custom(self, p, w, h, t):
    img = CUSTOM.current()
    if img is None or img.isNull():
        p.fillRect(QRectF(0, 0, w, h), QColor("#06070C"))
        return
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(0, 0, w, h), img, _cover(img, w, h))
    dim = float(T.APPEARANCE.get("custom_dim", 0.35))     # затемнение — чтобы текст читался
    p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, int(255 * max(0.0, min(0.85, dim)))))


def custom_thumb(w, h):
    pix = QPixmap(w, h)
    pix.fill(QColor("#06070C"))
    p = QPainter(pix)
    CUSTOM.ensure()
    img = CUSTOM.frame if CUSTOM.movie is not None else CUSTOM.image
    if img is not None and not img.isNull():
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, w, h), img, _cover(img, w, h))
    else:
        p.setPen(QColor(255, 255, 255, 120))
        f = p.font()
        f.setPixelSize(int(h * 0.28))
        p.setFont(f)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "+")
    p.end()
    return pix


class _Holder:
    """Хранилище кэша для миниатюр (вместо настоящего фона)."""


_THUMBS = {}


def thumbnail(key, w, h, accent=None):
    """Миниатюра фона для настроек (кадр анимации)."""
    if key == "custom":
        return custom_thumb(w, h)
    ck = (key, w, h, accent or T.ACCENT)
    if ck in _THUMBS:
        return _THUMBS[ck]
    old = (T.ACCENT, T.ACCENT_SOFT)
    if accent:
        T.ACCENT, T.ACCENT_SOFT = accent, T._mix(accent, "#FFFFFF", 0.45)
    try:
        pix = QPixmap(w, h)
        pix.fill(QColor("#06070C"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        fn = PAINTERS.get(key)
        if fn is not None:
            fn(_Holder(), p, w, h, 47.0)
        elif key == "oled":
            p.fillRect(pix.rect(), QColor("#000000"))
        else:
            base = QColor(T._mix("#090B10", T.ACCENT, 0.05))
            p.fillRect(pix.rect(), base)
            cols = _accent_set()
            for x, y, r, col, a in ((0.25, 0.3, 0.6, cols[0], 70), (0.8, 0.75, 0.5, cols[1], 55),
                                    (0.6, 0.1, 0.4, cols[2], 45)):
                g = QRadialGradient(QPointF(w * x, h * y), max(w, h) * r)
                g.setColorAt(0, _c(col, a))
                g.setColorAt(1, _c(col, 0))
                p.fillRect(pix.rect(), QBrush(g))
            if key == "glass":                  # «окна рабочего стола» сквозь стекло
                p.setPen(Qt.NoPen)
                for rx, ry, rw, rh in ((0.08, 0.15, 0.4, 0.45), (0.55, 0.35, 0.38, 0.5)):
                    p.setBrush(QColor(255, 255, 255, 22))
                    p.drawRoundedRect(QRectF(w * rx, h * ry, w * rw, h * rh), 6, 6)
                p.fillRect(pix.rect(), QColor(255, 255, 255, 18))
        p.end()
    finally:
        T.ACCENT, T.ACCENT_SOFT = old
    _THUMBS[ck] = pix
    return pix


PAINTERS["custom"] = paint_custom
