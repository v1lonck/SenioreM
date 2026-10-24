"""Общая тема интерфейса: цвета, шрифты, стили, мелкие фабрики виджетов."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

# ------------------------------------------------------------------ тема
BG = "#0F0F0E"
SURFACE = "#1A1918"
LINE = "#2C2A28"
TEXT = "#EEEBE5"
MUTED = "#8E8981"
FAINT = "#57534E"
ACCENT = "#E2A857"
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
QPushButton[role="primary"]:pressed {{ background: #D6D2CB; }}
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
