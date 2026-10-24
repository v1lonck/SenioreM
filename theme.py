"""Общая тема интерфейса: цвета, шрифты, стили, мелкие фабрики виджетов."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QPainter, QPalette, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

# ------------------------------------------------------------------ тема
BG = "#0B0D12"
SURFACE = "#161A23"
LINE = "#252B38"
TEXT = "#ECEFF5"
MUTED = "#8A93A6"
FAINT = "#535C6E"
ACCENT = "#5B8CFF"
ERROR = "#E58A7A"

FAMILY = "Segoe UI"
DISPLAY = "Segoe UI"


def pick_fonts():
    global FAMILY, DISPLAY
    fams = set(QFontDatabase.families())
    for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if f in fams:
            FAMILY = f
            break
    DISPLAY = "Segoe UI Variable Display" if "Segoe UI Variable Display" in fams else FAMILY


def font(size, weight=QFont.Normal, display=False, spacing=0.0):
    f = QFont(DISPLAY if display else FAMILY)
    f.setPixelSize(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


QSS = f"""
QWidget#root {{ background: {BG}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="faint"] {{ color: {FAINT}; }}
QLabel[role="error"] {{ color: {ERROR}; }}
QLabel[role="accent"] {{ color: {ACCENT}; }}
QLineEdit {{
    background: transparent; color: {TEXT};
    border: none; border-bottom: 1px solid {LINE};
    padding: 8px 0 10px 0;
    selection-background-color: {ACCENT}; selection-color: {BG};
}}
QLineEdit:focus {{ border-bottom: 1px solid {ACCENT}; }}
QLineEdit[role="code"] {{
    border: 1px solid {LINE}; border-radius: 12px; padding: 0;
}}
QLineEdit[role="code"]:focus {{ border: 1px solid {ACCENT}; }}
QPushButton[role="primary"] {{
    background: {TEXT}; color: {BG}; border: none; border-radius: 10px;
    padding: 0 22px; min-height: 50px;
}}
QPushButton[role="primary"]:hover {{ background: #FFFFFF; }}
QPushButton[role="primary"]:pressed {{ background: #D3D8E3; }}
QPushButton[role="primary"]:disabled {{ background: {LINE}; color: {FAINT}; }}
QPushButton[role="link"] {{
    background: transparent; border: none; color: {MUTED};
    padding: 4px 0; text-align: left;
}}
QPushButton[role="link"]:hover {{ color: {TEXT}; }}
QPushButton[role="link"]:disabled {{ color: {FAINT}; }}
QPushButton[role="chrome"] {{
    background: transparent; border: none; color: {MUTED};
    min-width: 40px; min-height: 40px; max-width: 40px; max-height: 40px; border-radius: 8px;
}}
QPushButton[role="chrome"]:hover {{ background: {SURFACE}; color: {TEXT}; }}
QWidget[role="vline"] {{ background: {LINE}; }}
QFrame[role="card"] {{
    background: rgba(22, 26, 35, 0.78); border: 1px solid {LINE}; border-radius: 18px;
}}
QFrame[role="chip"] {{
    background: rgba(91, 140, 255, 0.10); border: 1px solid rgba(91, 140, 255, 0.28);
    border-radius: 12px;
}}
QPushButton[role="ghost"] {{
    background: transparent; color: {TEXT}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 0 18px; min-height: 42px;
}}
QPushButton[role="ghost"]:hover {{ border-color: {ACCENT}; color: #FFFFFF; }}
QPushButton[role="ghost"]:checked {{ border-color: {ACCENT}; background: rgba(91, 140, 255, 0.14); }}
QPushButton[role="danger"] {{
    background: transparent; color: {ERROR}; border: 1px solid rgba(229, 138, 122, 0.4);
    border-radius: 10px; padding: 0 18px; min-height: 42px;
}}
QPushButton[role="danger"]:hover {{ background: rgba(229, 138, 122, 0.10); }}
QPushButton[role="nav"] {{
    background: transparent; color: {MUTED}; border: none; border-radius: 10px;
    padding: 0 16px; min-height: 44px; text-align: left;
}}
QPushButton[role="nav"]:hover {{ color: {TEXT}; background: rgba(255, 255, 255, 0.03); }}
QPushButton[role="nav"]:checked {{ color: #FFFFFF; background: rgba(91, 140, 255, 0.16); }}
QPushButton[role="avatar"] {{
    background: rgba(91, 140, 255, 0.18); color: {TEXT}; border: 1px solid rgba(91, 140, 255, 0.45);
    border-radius: 20px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
}}
QPushButton[role="avatar"]:hover {{ background: rgba(91, 140, 255, 0.32); }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""


def label(text="", size=15, weight=QFont.Normal, role=None, display=False,
          spacing=0.0, wrap=False):
    lb = QLabel(text)
    lb.setFont(font(size, weight, display, spacing))
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def button(text, role="primary", size=15, weight=QFont.DemiBold):
    b = QPushButton(text)
    b.setProperty("role", role)
    b.setFont(font(size, weight))
    b.setCursor(Qt.PointingHandCursor)
    return b


def field(placeholder="", password=False):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFont(font(17))
    if password:
        e.setEchoMode(QLineEdit.Password)
    return e


def set_role(widget, role):
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def window_controls(win):
    box = QHBoxLayout()
    box.setSpacing(4)
    mn = button("—", "chrome", 14, QFont.Normal)
    mn.setToolTip("Свернуть")
    mn.clicked.connect(win.showMinimized)
    cl = button("✕", "chrome", 14, QFont.Normal)
    cl.setToolTip("Закрыть")
    cl.clicked.connect(win.close)
    box.addWidget(mn)
    box.addWidget(cl)
    return box



def apply_app_theme(app):
    pick_fonts()
    app.setFont(font(15))
    pal = app.palette()
    for role, col in ((QPalette.Window, BG), (QPalette.Base, BG), (QPalette.Text, TEXT),
                      (QPalette.WindowText, TEXT), (QPalette.ButtonText, TEXT),
                      (QPalette.PlaceholderText, FAINT), (QPalette.Button, SURFACE)):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def card(margins=(24, 22, 24, 22), spacing=0):
    """Карточка: полупрозрачная панель со скруглёнными углами."""
    f = QFrame()
    f.setProperty("role", "card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


def hline():
    w = QWidget()
    w.setProperty("role", "vline")
    w.setAttribute(Qt.WA_StyledBackground, True)
    w.setFixedHeight(1)
    return w


class Backdrop(QWidget):
    """Фон экрана: тёмный, с мягким синим свечением и едва заметной сеткой точек."""

    def __init__(self, glows=((0.22, 0.30, 0.55), (0.85, 0.85, 0.45))):
        super().__init__()
        self.glows = glows

        self._cache = None

    def resizeEvent(self, e):
        self._cache = None
        super().resizeEvent(e)

    def _render(self):
        w, h = max(1, self.width()), max(1, self.height())
        pix = QPixmap(w, h)
        pix.fill(QColor(BG))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        for i, (gx, gy, gr) in enumerate(self.glows):
            g = QRadialGradient(QPointF(w * gx, h * gy), max(w, h) * gr)
            c = QColor(52, 92, 230, 46) if i % 2 == 0 else QColor(96, 70, 220, 32)
            g.setColorAt(0.0, c)
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(pix.rect(), QBrush(g))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 9))
        step = 28
        for y in range(step, h, step):
            for x in range(step, w, step):
                p.drawEllipse(QPointF(x, y), 0.9, 0.9)
        p.end()
        return pix

    def paintEvent(self, e):
        if self._cache is None or self._cache.size() != self.size():
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(e.rect(), self._cache, e.rect())


class LogoMark(QWidget):
    """Иконка программы (буква S) с мягким пульсирующим свечением."""

    def __init__(self, size=120, glow=True):
        super().__init__()
        self.setFixedSize(size, size)
        self.glow = glow
        self._t = 0.0
        import config
        path = config.resource_path("assets/icon.png")
        self._pix = QPixmap(str(path)) if path.exists() else QPixmap()
        if glow:
            t = QTimer(self)
            t.timeout.connect(self._tick)
            t.start(33)

    def _tick(self):
        self._t += 0.033
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width()
        c = QPointF(w / 2, w / 2)
        if self.glow:
            b = (math.sin(self._t * 2.0) + 1) / 2
            g = QRadialGradient(c, w * 0.5)
            g.setColorAt(0.45, QColor(70, 120, 255, int(60 + 50 * b)))
            g.setColorAt(1.0, QColor(70, 120, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, w * 0.5, w * 0.5)
        side = w * (0.72 if self.glow else 1.0)
        if not self._pix.isNull():
            p.drawPixmap(QRectF(c.x() - side / 2, c.y() - side / 2, side, side), self._pix,
                         QRectF(self._pix.rect()))


class Toggle(QAbstractButton):
    """Переключатель-«таблетка»."""

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 1.0 if checked else 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._anim)
        self.toggled.connect(lambda _: self._timer.start(16))

    def _anim(self):
        target = 1.0 if self.isChecked() else 0.0
        self._pos += (target - self._pos) * 0.3
        if abs(target - self._pos) < 0.01:
            self._pos = target
            self._timer.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(LINE), QColor(ACCENT)
        col = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                     int(off.green() + (on.green() - off.green()) * self._pos),
                     int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(13 + 20 * self._pos, 13), 9.5, 9.5)


class Clickable(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)
