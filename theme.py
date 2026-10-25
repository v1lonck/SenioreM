"""Общая тема интерфейса: цвета, шрифты, стили, мелкие фабрики виджетов."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QPainter, QPalette, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

# ------------------------------------------------------------------ тема
# Цвета пересчитываются из выбранного акцента (set_appearance) — вся программа меняет цвет сразу.
BG = "#0B0D12"
SURFACE = "#161A23"
LINE = "#252B38"
TEXT = "#ECEFF5"
MUTED = "#8A93A6"
FAINT = "#535C6E"
ACCENT = "#5B8CFF"
ACCENT_SOFT = "#9DB8FF"
ERROR = "#E58A7A"

PRESETS = [
    ("Синий", "#5B8CFF"), ("Зелёный", "#34D399"), ("Изумруд", "#10B981"), ("Бирюза", "#22D3EE"),
    ("Фиолетовый", "#A78BFA"), ("Розовый", "#F472B6"), ("Красный", "#F87171"),
    ("Оранжевый", "#FB923C"), ("Золотой", "#FBBF24"), ("Серебро", "#CBD5E1"),
]
BACKGROUNDS = [
    ("aurora", "Северное сияние", "Живой фон, плавно переливается"),
    ("glow", "Свечение", "Мягкие пятна света"),
    ("solid", "Однотонный", "Спокойный тёмный фон"),
    ("glass", "Стекло", "Сквозь окно виден рабочий стол"),
]
APPEARANCE = {"accent": "#5B8CFF", "background": "aurora", "glass": 0.55, "panels": 0.72,
              "widgets": {"clock": True, "weather": True, "system": True, "volume": True,
                          "history": True, "notes": False, "tips": True},
              "clock_style": "digital", "city": ""}
_listeners = []

FAMILY = "Segoe UI"
DISPLAY = "Segoe UI"


def _mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t)).name()


def rgba(color, alpha):
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def qcolor(color, alpha=255):
    c = QColor(color)
    c.setAlpha(int(alpha))
    return c


def _appearance_file():
    import config
    return config.data_dir() / "appearance.json"


def load_appearance():
    import json
    try:
        with open(_appearance_file(), encoding="utf-8") as f:
            data = json.load(f)
        w = dict(APPEARANCE["widgets"])
        w.update(data.get("widgets", {}))
        APPEARANCE.update(data)
        APPEARANCE["widgets"] = w
    except (OSError, ValueError):
        pass
    _recompute()
    return APPEARANCE


def save_appearance():
    import json
    try:
        with open(_appearance_file(), "w", encoding="utf-8") as f:
            json.dump(APPEARANCE, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _recompute():
    global BG, SURFACE, LINE, ACCENT, ACCENT_SOFT, MUTED, FAINT
    ACCENT = QColor(APPEARANCE.get("accent") or "#5B8CFF").name()
    ACCENT_SOFT = _mix(ACCENT, "#FFFFFF", 0.45)
    BG = _mix("#090B10", ACCENT, 0.035)
    SURFACE = _mix("#141822", ACCENT, 0.05)
    LINE = _mix("#222836", ACCENT, 0.14)
    MUTED = _mix("#8A93A6", ACCENT, 0.08)
    FAINT = _mix("#535C6E", ACCENT, 0.08)


def on_theme_change(callback):
    _listeners.append(callback)


def set_appearance(app=None, **changes):
    """Меняет оформление и сразу применяет его ко всей программе."""
    for k, v in changes.items():
        if k == "widgets":
            APPEARANCE["widgets"].update(v)
        else:
            APPEARANCE[k] = v
    _recompute()
    save_appearance()
    if app is not None:
        app.setStyleSheet(build_qss())
        _apply_palette(app)
        for w in app.allWidgets():
            if isinstance(w, Backdrop):
                w.invalidate()
            w.update()
    for cb in list(_listeners):
        try:
            cb()
        except Exception:  # noqa: BLE001
            pass


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


def build_qss():
    A = ACCENT
    panel = float(APPEARANCE.get("panels", 0.72))
    glass = APPEARANCE.get("background") == "glass"
    if glass:
        panel = min(panel, 0.6)
    top = rgba(_mix(SURFACE, "#FFFFFF", 0.06), round(panel, 2))
    bottom = rgba(SURFACE, round(max(0.05, panel - 0.12), 2))
    return f"""
QWidget#root {{ background: {"transparent" if glass else BG}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="faint"] {{ color: {FAINT}; }}
QLabel[role="error"] {{ color: {ERROR}; }}
QLabel[role="accent"] {{ color: {A}; }}
QLineEdit, QPlainTextEdit {{
    background: transparent; color: {TEXT};
    border: none; border-bottom: 1px solid {LINE};
    padding: 8px 0 10px 0;
    selection-background-color: {A}; selection-color: {BG};
}}
QPlainTextEdit {{ border: 1px solid {LINE}; border-radius: 10px; padding: 8px; }}
QLineEdit:focus {{ border-bottom: 1px solid {A}; }}
QPlainTextEdit:focus {{ border: 1px solid {A}; }}
QLineEdit[role="code"] {{
    border: 1px solid {LINE}; border-radius: 12px; padding: 0;
}}
QLineEdit[role="code"]:focus {{ border: 1px solid {A}; }}
QPushButton[role="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_SOFT}, stop:1 {A});
    color: #0A0C10; border: none; border-radius: 10px;
    padding: 0 22px; min-height: 50px;
}}
QPushButton[role="primary"]:hover {{ background: {ACCENT_SOFT}; }}
QPushButton[role="primary"]:pressed {{ background: {A}; }}
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
QPushButton[role="chrome"]:hover {{ background: {rgba(A, 0.14)}; color: {TEXT}; }}
QWidget[role="vline"] {{ background: {LINE}; }}
QFrame[role="card"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bottom});
    border: 1px solid {rgba(_mix(LINE, A, 0.25), 0.9)};
    border-top: 1px solid {rgba(_mix(LINE, "#FFFFFF", 0.25), 0.9)};
    border-radius: 18px;
}}
QFrame[role="chip"] {{
    background: {rgba(A, 0.10)}; border: 1px solid {rgba(A, 0.28)}; border-radius: 12px;
}}
QPushButton[role="ghost"] {{
    background: {rgba("#FFFFFF", 0.02)}; color: {TEXT}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 0 18px; min-height: 42px;
}}
QPushButton[role="ghost"]:hover {{ border-color: {A}; color: #FFFFFF; }}
QPushButton[role="ghost"]:checked {{ border-color: {A}; background: {rgba(A, 0.16)}; }}
QPushButton[role="swatch"] {{ border: 2px solid transparent; border-radius: 19px;
    min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px; }}
QPushButton[role="swatch"]:checked {{ border: 2px solid #FFFFFF; }}
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
QPushButton[role="nav"]:checked {{ color: #FFFFFF; background: {rgba(A, 0.18)}; }}
QPushButton[role="avatar"] {{
    background: {rgba(A, 0.20)}; color: {TEXT}; border: 1px solid {rgba(A, 0.5)};
    border-radius: 20px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
}}
QPushButton[role="avatar"]:hover {{ background: {rgba(A, 0.34)}; }}
QLabel[role="bigavatar"] {{
    background: {rgba(A, 0.20)}; border: 1px solid {rgba(A, 0.5)}; border-radius: 36px; color: {TEXT};
}}
QFrame[role="modal"] {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 20px;
}}
QFrame[role="option"] {{
    background: rgba(255, 255, 255, 0.02); border: 1px solid {LINE}; border-radius: 14px;
}}
QFrame[role="option"]:hover {{ border-color: {rgba(A, 0.5)}; }}
QFrame[role="option"][selected="true"] {{
    background: {rgba(A, 0.13)}; border: 1px solid {A};
}}
QPushButton[role="dangerfill"] {{
    background: #E5484D; color: #FFFFFF; border: none; border-radius: 10px;
    padding: 0 22px; min-height: 46px;
}}
QPushButton[role="dangerfill"]:hover {{ background: #F05A5F; }}
QPushButton[role="dangerfill"]:pressed {{ background: #C93C41; }}
QPushButton[role="secondary"] {{
    background: rgba(255, 255, 255, 0.06); color: {TEXT}; border: 1px solid {LINE};
    border-radius: 10px; padding: 0 22px; min-height: 46px;
}}
QPushButton[role="secondary"]:hover {{ background: rgba(255, 255, 255, 0.10); }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {A}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px; }}
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
    mn.clicked.connect(getattr(win, "smooth_minimize", win.showMinimized))
    cl = button("✕", "chrome", 14, QFont.Normal)
    cl.setToolTip("Закрыть")
    cl.clicked.connect(getattr(win, "request_close", win.close))
    box.addWidget(mn)
    box.addWidget(cl)
    return box



def _apply_palette(app):
    pal = app.palette()
    for role, col in ((QPalette.Window, BG), (QPalette.Base, BG), (QPalette.Text, TEXT),
                      (QPalette.WindowText, TEXT), (QPalette.ButtonText, TEXT),
                      (QPalette.PlaceholderText, FAINT), (QPalette.Button, SURFACE),
                      (QPalette.Highlight, ACCENT)):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)


def apply_app_theme(app):
    load_appearance()
    pick_fonts()
    app.setFont(font(15))
    _apply_palette(app)
    app.setStyleSheet(build_qss())


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
    """Фон экрана. Стили: «Северное сияние» (живой), «Свечение», «Однотонный», «Стекло»."""

    def __init__(self, glows=((0.22, 0.30, 0.55), (0.85, 0.85, 0.45))):
        super().__init__()
        self.glows = glows
        self._dots = None
        self._static = None
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(70)

    def invalidate(self):
        self._dots = None
        self._static = None
        self.update()

    def resizeEvent(self, e):
        self.invalidate()
        super().resizeEvent(e)

    def _tick(self):
        if APPEARANCE.get("background") == "aurora" and self.isVisible():
            self._t += 0.07
            self.update()

    def _render_dots(self):
        w, h = max(1, self.width()), max(1, self.height())
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        step = 28
        for y in range(step, h, step):
            for x in range(step, w, step):
                p.drawEllipse(QPointF(x, y), 0.9, 0.9)
        p.end()
        return pix

    def _glow_colors(self):
        a = QColor(ACCENT)
        h, s_, v, _ = a.getHsv()
        b = QColor.fromHsv((h + 40) % 360 if h >= 0 else 220, max(80, s_), max(160, v))
        c = QColor.fromHsv((h + 320) % 360 if h >= 0 else 260, max(80, s_), max(140, v))
        return a, b, c

    def _render_blobs(self, w, h, t):
        """Пятна света рисуем в маленьком разрешении и растягиваем — это почти бесплатно."""
        sw, sh = max(1, w // 8), max(1, h // 8)
        pix = QPixmap(sw, sh)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        cols = self._glow_colors()
        blobs = [(0.25 + 0.12 * math.sin(t * 0.21), 0.35 + 0.10 * math.cos(t * 0.17), 0.55, 0, 60),
                 (0.78 + 0.10 * math.cos(t * 0.13), 0.70 + 0.12 * math.sin(t * 0.19), 0.48, 1, 45),
                 (0.55 + 0.18 * math.sin(t * 0.09 + 1), 0.15 + 0.08 * math.cos(t * 0.11), 0.40, 2, 38),
                 (0.10 + 0.08 * math.cos(t * 0.15), 0.90 + 0.05 * math.sin(t * 0.12), 0.35, 1, 30)]
        for x, y, r, ci, alpha in blobs:
            g = QRadialGradient(QPointF(sw * x, sh * y), max(sw, sh) * r)
            c = QColor(cols[ci])
            c.setAlpha(alpha)
            g.setColorAt(0.0, c)
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(pix.rect(), QBrush(g))
        p.end()
        return pix

    def paintEvent(self, e):
        style = APPEARANCE.get("background", "aurora")
        w, h = self.width(), self.height()
        p = QPainter(self)
        if style == "glass":
            p.fillRect(self.rect(), qcolor(BG, 255 * (1 - float(APPEARANCE.get("glass", 0.55)))))
        else:
            p.fillRect(self.rect(), QColor(BG))
        if style == "aurora":
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(self.rect(), self._render_blobs(w, h, self._t))
        elif style in ("glow", "glass"):
            if self._static is None or self._static.size() != self.size():
                self._static = self._render_blobs(w, h, 0.0)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(self.rect(), self._static)
        if self._dots is None or self._dots.size() != self.size():
            self._dots = self._render_dots()
        p.drawPixmap(0, 0, self._dots)


def enable_glass(widget):
    """Размытие рабочего стола за окном (Windows 10/11)."""
    import sys
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import POINTER, Structure, byref, c_int, c_size_t, c_uint, pointer, sizeof

        class ACCENTPOLICY(Structure):
            _fields_ = [("AccentState", c_int), ("AccentFlags", c_int),
                        ("GradientColor", c_uint), ("AnimationId", c_int)]

        class WINCOMPATTRDATA(Structure):
            _fields_ = [("Attribute", c_int), ("Data", POINTER(ACCENTPOLICY)),
                        ("SizeOfData", c_size_t)]

        hwnd = int(widget.winId())
        bg = QColor(BG)
        tint = (int(40) << 24) | (bg.blue() << 16) | (bg.green() << 8) | bg.red()
        accent = ACCENTPOLICY(4, 2, tint, 0)            # 4 = акриловое размытие
        data = WINCOMPATTRDATA(19, pointer(accent), sizeof(accent))
        if not ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, byref(data)):
            accent = ACCENTPOLICY(3, 0, 0, 0)           # 3 = обычное размытие
            data = WINCOMPATTRDATA(19, pointer(accent), sizeof(accent))
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
        return True
    except Exception:  # noqa: BLE001
        return False


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
            g.setColorAt(0.45, qcolor(ACCENT, int(60 + 50 * b)))
            g.setColorAt(1.0, qcolor(ACCENT, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, w * 0.5, w * 0.5)
        side = w * (0.72 if self.glow else 1.0)
        draw_logo(p, QRectF(c.x() - side / 2, c.y() - side / 2, side, side))


def draw_logo(p, r):
    """Значок программы в цвете темы: скруглённый квадрат, кольца-волны и буква S."""
    from PySide6.QtGui import QLinearGradient, QPainterPath
    side = r.width()
    path = QPainterPath()
    path.addRoundedRect(r, side * 0.235, side * 0.235)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0.0, QColor(_mix(ACCENT, "#000000", 0.62)))
    g.setColorAt(1.0, QColor(_mix(ACCENT, "#000000", 0.05)))
    p.setRenderHint(QPainter.Antialiasing)
    p.fillPath(path, QBrush(g))
    hl = QRadialGradient(QPointF(r.left() + side * 0.25, r.top() + side * 0.1), side * 0.7)
    hl.setColorAt(0.0, QColor(255, 255, 255, 45))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(hl))
    p.setBrush(Qt.NoBrush)
    for rr, a in ((0.43, 40), (0.36, 26)):
        p.setPen(QPen(QColor(255, 255, 255, a), max(1.0, side * 0.008)))
        p.drawEllipse(r.center(), side * rr, side * rr)
    p.setPen(QPen(QColor(255, 255, 255, 50), max(1.0, side * 0.004)))
    p.drawPath(path)
    f = QFont(DISPLAY)
    f.setPixelSize(max(6, int(side * 0.62)))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(QColor(0, 0, 0, 70))
    p.drawText(r.translated(0, side * 0.02), Qt.AlignCenter, "S")
    p.setPen(QColor("#FFFFFF"))
    p.drawText(r, Qt.AlignCenter, "S")


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


class PlayButton(QAbstractButton):
    """Аккуратная круглая кнопка «прослушать» с нарисованным треугольником."""

    def __init__(self, text="Прослушать", size=34):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self._text = text
        self._d = size
        self._hover = False
        self._playing = False
        f = font(14, QFont.DemiBold)
        self.setFont(f)
        from PySide6.QtGui import QFontMetrics
        w = size + (12 + QFontMetrics(f).horizontalAdvance(text) if text else 0)
        self.setFixedSize(w + 6, size + 4)

    def set_playing(self, flag):
        self._playing = flag
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = self._d
        c = QPointF(2 + d / 2, 2 + d / 2)
        bg = QColor(ACCENT)
        bg.setAlpha(255 if (self._hover or self._playing) else 210)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(c, d / 2, d / 2)
        p.setBrush(QColor("#FFFFFF"))
        if self._playing:
            w = d * 0.09
            for dx in (-d * 0.11, d * 0.11):
                p.drawRoundedRect(QRectF(c.x() + dx - w / 2, c.y() - d * 0.17, w, d * 0.34), 1.5, 1.5)
        else:
            from PySide6.QtGui import QPolygonF
            r = d * 0.2
            tri = QPolygonF([QPointF(c.x() - r * 0.7, c.y() - r), QPointF(c.x() - r * 0.7, c.y() + r),
                             QPointF(c.x() + r * 1.05, c.y())])
            p.drawPolygon(tri)
        if self._text:
            p.setPen(QColor(TEXT if self._hover else ACCENT_SOFT))
            p.setFont(self.font())
            p.drawText(QRectF(d + 14, 0, self.width() - d - 14, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self._text)


class ConfirmDialog(QDialog):
    """Тёмное окно подтверждения поверх затемнённой программы."""

    def __init__(self, parent, title, text, yes="Да, закрыть", no="Вернуться"):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        if parent is not None:
            self.setGeometry(parent.frameGeometry())
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        box = QFrame()
        box.setProperty("role", "modal")
        box.setFixedWidth(460)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(36, 32, 36, 30)
        lay.setSpacing(0)
        lay.addWidget(LogoMark(56, glow=False), 0, Qt.AlignLeft)
        lay.addSpacing(18)
        lay.addWidget(label(title, 24, QFont.Light, display=True))
        lay.addSpacing(8)
        lay.addWidget(label(text, 15, role="muted", wrap=True))
        lay.addSpacing(28)
        row = QHBoxLayout()
        row.setSpacing(12)
        back = button(no, "secondary", 15)
        back.clicked.connect(self.reject)
        ok = button(yes, "dangerfill", 15)
        ok.clicked.connect(self.accept)
        row.addWidget(back, 1)
        row.addWidget(ok, 1)
        lay.addLayout(row)
        outer.addWidget(box, 0, Qt.AlignHCenter)
        outer.addStretch(1)
        back.setFocus()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(4, 6, 10, 175))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)


def fade_in(widget, ms=220):
    """Мягкое появление виджета (страницы, раздела)."""
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation
    from PySide6.QtWidgets import QGraphicsOpacityEffect
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0.0)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))  # без эффекта — быстрее
    widget._fade_anim = anim
    anim.start()


def switch_page(stack, widget, ms=220):
    if stack.currentWidget() is widget:
        return
    stack.setCurrentWidget(widget)
    fade_in(widget, ms)
