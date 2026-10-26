"""Векторные значки (рисуются кодом, а не символами шрифта) — чёткие на любом масштабе экрана."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton

DPR = 3.0          # рисуем с запасом — значок остаётся чётким и на 150–200 % масштаба


def _pen(color, w):
    p = QPen(QColor(color), w)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def draw(p, name, rect, color, weight=1.6):
    """Рисует значок name в прямоугольнике rect (в логических пикселях)."""
    s = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y()
    u = s / 16.0                                       # «сетка» 16×16
    w = weight * u
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(_pen(color, w))
    p.setBrush(Qt.NoBrush)

    def pt(x, y):
        return QPointF(cx + (x - 8) * u, cy + (y - 8) * u)

    if name == "close":
        p.drawLine(pt(4, 4), pt(12, 12))
        p.drawLine(pt(12, 4), pt(4, 12))
    elif name == "minimize":
        p.drawLine(pt(3.5, 8.5), pt(12.5, 8.5))
    elif name == "back":
        p.drawLine(pt(13, 8), pt(3.5, 8))
        path = QPainterPath(pt(7.5, 4))
        path.lineTo(pt(3.5, 8))
        path.lineTo(pt(7.5, 12))
        p.drawPath(path)
    elif name == "up":
        p.drawLine(pt(8, 13), pt(8, 3.5))
        path = QPainterPath(pt(4, 7.5))
        path.lineTo(pt(8, 3.5))
        path.lineTo(pt(12, 7.5))
        p.drawPath(path)
    elif name == "download":
        p.drawLine(pt(8, 2.5), pt(8, 10))
        path = QPainterPath(pt(4.5, 7))
        path.lineTo(pt(8, 10.5))
        path.lineTo(pt(11.5, 7))
        p.drawPath(path)
        p.drawLine(pt(3, 13.5), pt(13, 13.5))
    elif name == "update":                             # стрелка вверх в круге
        p.drawEllipse(QRectF(pt(1.8, 1.8), pt(14.2, 14.2)))
        p.drawLine(pt(8, 11.5), pt(8, 4.8))
        path = QPainterPath(pt(5.2, 7.4))
        path.lineTo(pt(8, 4.6))
        path.lineTo(pt(10.8, 7.4))
        p.drawPath(path)
    elif name == "chat":
        path = QPainterPath()
        path.addRoundedRect(QRectF(pt(2, 2.5), pt(14, 11.5)), 3 * u, 3 * u)
        tail = QPainterPath(pt(5, 11.2))
        tail.lineTo(pt(4.2, 14.2))
        tail.lineTo(pt(8.2, 11.4))
        p.drawPath(path.united(tail))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        for x in (5.4, 8, 10.6):
            p.drawEllipse(pt(x, 7), 0.95 * u, 0.95 * u)
    elif name == "play":
        path = QPainterPath(pt(5, 3.5))
        path.lineTo(pt(12.5, 8))
        path.lineTo(pt(5, 12.5))
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    elif name == "clip":                               # скрепка
        path = QPainterPath(pt(11.5, 6.5))
        path.lineTo(pt(6.2, 11.8))
        path.cubicTo(pt(4.9, 13.1), pt(2.9, 13.1), pt(2.6, 11.4))
        path.cubicTo(pt(2.4, 10.4), pt(2.9, 9.7), pt(3.5, 9.1))
        path.lineTo(pt(9.6, 3.0))
        path.cubicTo(pt(10.6, 2.0), pt(12.5, 2.0), pt(13.2, 3.2))
        path.cubicTo(pt(13.8, 4.3), pt(13.4, 5.3), pt(12.6, 6.1))
        path.lineTo(pt(6.8, 11.9))
        p.drawPath(path)
    elif name == "screen":                             # монитор — снимок экрана
        p.drawRoundedRect(QRectF(pt(1.8, 2.8), pt(14.2, 11.2)), 1.6 * u, 1.6 * u)
        p.drawLine(pt(8, 11.2), pt(8, 13.6))
        p.drawLine(pt(5.2, 13.8), pt(10.8, 13.8))
    elif name == "image":                              # картинка
        p.drawRoundedRect(QRectF(pt(2, 2.5), pt(14, 13.5)), 2 * u, 2 * u)
        path = QPainterPath(pt(2.6, 12.0))
        path.lineTo(pt(6.4, 8.0))
        path.lineTo(pt(9.0, 10.6))
        path.lineTo(pt(10.8, 8.8))
        path.lineTo(pt(13.4, 11.6))
        p.drawPath(path)
        p.drawEllipse(pt(10.4, 5.6), 1.2 * u, 1.2 * u)
    elif name == "brush":                              # кисть — нарисовать
        p.drawLine(pt(13.5, 2.5), pt(7.2, 8.8))
        path = QPainterPath(pt(7.2, 8.8))
        path.cubicTo(pt(4.8, 8.4), pt(3.4, 10.4), pt(3.6, 12.4))
        path.cubicTo(pt(3.0, 13.2), pt(2.6, 13.4), pt(2.2, 13.6))
        path.cubicTo(pt(5.2, 14.4), pt(7.8, 12.6), pt(7.2, 8.8))
        p.drawPath(path)
    elif name == "check":
        path = QPainterPath(pt(3.5, 8.5))
        path.lineTo(pt(6.8, 11.8))
        path.lineTo(pt(12.5, 4.5))
        p.drawPath(path)
    p.restore()


def pixmap(name, size, color, weight=1.6):
    pix = QPixmap(int(size * DPR), int(size * DPR))
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(DPR)
    p = QPainter(pix)
    draw(p, name, QRectF(0, 0, size, size), color, weight)
    p.end()
    return pix


def icon(name, size=16, color="#E8ECF4", weight=1.6):
    return QIcon(pixmap(name, size, color, weight))


def set_icon(btn, name, size=16, color=None, weight=1.6):
    """Ставит значок на кнопку (цвет — как у текста кнопки, если не задан)."""
    import theme as T
    btn.setIcon(icon(name, size, color or T.TEXT, weight))
    btn.setIconSize(QSize(size, size))


class ChromeButton(QPushButton):
    """Кнопки окна «Свернуть» и «Закрыть»: рисуются вектором, при наведении — подсветка
    (у «Закрыть» — красная, как в Windows)."""

    def __init__(self, kind, tooltip=""):
        super().__init__()
        self.kind = kind
        self.setToolTip(tooltip)
        self.setFixedSize(42, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def sizeHint(self):
        return QSize(42, 36)

    def paintEvent(self, _):
        import theme as T
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover or self.isDown():
            bg = QColor("#E5484D") if self.kind == "close" else QColor(T.ACCENT)
            bg.setAlpha(235 if self.kind == "close" else 40)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 8, 8)
        col = "#FFFFFF" if (self._hover and self.kind == "close") else (T.TEXT if self._hover else T.MUTED)
        draw(p, self.kind, QRectF(r.center().x() - 7, r.center().y() - 7, 14, 14), col, 1.5)
        p.end()
