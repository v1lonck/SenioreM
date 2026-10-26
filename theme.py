"""Общая тема интерфейса: цвета, шрифты, стили, мелкие фабрики виджетов."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QPainter, QPalette, QPen,
                           QLinearGradient, QPixmap, QRadialGradient)
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
    ("space", "Космос", "Туманность и планета"),
    ("galaxy", "Галактика", "Вращается спиральная галактика"),
    ("warp", "Гиперпрыжок", "Полёт сквозь звёзды"),
    ("aurora", "Северное сияние", "Сияние над горами"),
    ("grid", "Ретро", "Неоновое солнце и сетка 80-х"),
    ("waves", "Волны", "Светящиеся волны"),
    ("glow", "Свечение", "Спокойный фон без анимации"),
    ("oled", "Чёрный", "Минимум нагрузки"),
    ("glass", "Стекло", "Виден рабочий стол"),
    ("custom", "Свой фон", "Ваша картинка или GIF"),
]
BG_ALIASES = {"stars": "space", "particles": "space", "solid": "glow"}
THEMES = [
    ("Джарвис", "#38BDF8", "space", "digital", "jarvis"),
    ("Галактика", "#A78BFA", "galaxy", "analog", "hologram"),
    ("Гиперпрыжок", "#60A5FA", "warp", "digital", "jarvis"),
    ("Сияние", "#34D399", "aurora", "digital", "siri"),
    ("Ретро", "#F472B6", "grid", "digital", "equalizer"),
    ("OLED", "#CBD5E1", "oled", "digital", "sphere"),
]
ANIMATED = ("space", "galaxy", "warp", "aurora", "waves", "grid")
# медленные фоны не нужно перерисовывать часто — экономим процессор
BG_FRAME_MS = {"custom": 33, "space": 80, "galaxy": 90, "aurora": 80, "waves": 55, "grid": 50, "warp": 42}


def bg_style():
    st = APPEARANCE.get("background", "space")
    return BG_ALIASES.get(st, st)


APPEARANCE = {"accent": "#38BDF8", "background": "space", "glass": 0.55, "panels": 0.72,
              "widgets": {"clock": True, "weather": True, "system": True, "volume": True,
                          "history": True, "notes": False, "tips": True},
              "clock_style": "digital", "city": "", "orb_style": "jarvis", "eco": False}
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
    BG = "#000000" if APPEARANCE.get("background") == "oled" else _mix("#090B10", ACCENT, 0.035)
    SURFACE = _mix("#141822", ACCENT, 0.05)
    LINE = _mix("#222836", ACCENT, 0.14)
    MUTED = _mix("#8A93A6", ACCENT, 0.08)
    FAINT = _mix("#535C6E", ACCENT, 0.08)


def on_theme_change(callback):
    _listeners.append(callback)


QSS_KEYS = {"accent", "background", "glass", "panels", "hover"}
BACKDROP_KEYS = {"accent", "background", "glass", "custom_bg", "custom_dim", "eco"}


def set_appearance(app=None, **changes):
    """Меняет оформление и сразу применяет его ко всей программе."""
    for k, v in changes.items():
        if k == "widgets":
            APPEARANCE["widgets"].update(v)
        else:
            APPEARANCE[k] = v
    _recompute()
    save_appearance()
    keys = set(changes)
    # перестраиваем стиль всей программы только когда это нужно (иначе переключение «лагает»)
    if app is not None and keys & QSS_KEYS:
        app.setStyleSheet(build_qss())
        _apply_palette(app)
    if app is not None and keys & BACKDROP_KEYS:
        for w in app.allWidgets():
            if isinstance(w, Backdrop):
                w.invalidate()
    for cb in list(_listeners):
        try:
            cb()
        except Exception:  # noqa: BLE001
            pass


# Шрифты на выбор: встроенные в программу (assets/fonts) и стандартные шрифты Windows с русскими буквами
FONT_CHOICES = [
    ("", "Стандартный", "Segoe UI — как в Windows"),
    ("Manrope", "Manrope", "Современный и чёткий"),
    ("Montserrat", "Montserrat", "Широкий, «дизайнерский»"),
    ("Inter", "Inter", "Строгий, для интерфейсов"),
    ("Nunito", "Nunito", "Мягкий, округлый"),
    ("Rubik", "Rubik", "Плотный, слегка скруглённый"),
    ("Golos Text", "Golos", "Спокойный, очень читаемый"),
    ("Jost", "Jost", "Геометрический, лёгкий"),
    ("Exo 2", "Exo 2", "Технологичный, «игровой»"),
    ("Comfortaa", "Comfortaa", "Круглый и дружелюбный"),
    ("Unbounded", "Unbounded", "Крупный, жирный, яркий"),
    ("Oswald", "Oswald", "Узкий и высокий"),
    ("Play", "Play", "Как в играх и на табло"),
    ("Caveat", "Caveat", "Рукописный"),
    ("Bahnschrift", "Bahnschrift", "Технический (есть в Windows)"),
    ("Trebuchet MS", "Trebuchet", "Классический гуманистический"),
    ("Georgia", "Georgia", "С засечками, книжный"),
    ("Consolas", "Consolas", "Моноширинный, как в коде"),
    ("Comic Sans MS", "Comic Sans", "Шуточный"),
]
_FONTS_LOADED = [False]


def load_bundled_fonts():
    """Подключаем шрифты, которые идут вместе с программой (assets/fonts)."""
    if _FONTS_LOADED[0]:
        return
    _FONTS_LOADED[0] = True
    import os
    import config
    d = os.path.join(str(config.resource_path("assets")), "fonts")
    try:
        names = os.listdir(d)
    except OSError:
        return
    for n in names:
        if n.lower().endswith((".ttf", ".otf")):
            QFontDatabase.addApplicationFont(os.path.join(d, n))


def available_fonts():
    fams = set(QFontDatabase.families())
    return [(f, t, d) for f, t, d in FONT_CHOICES if not f or f in fams]


def pick_fonts():
    global FAMILY, DISPLAY
    load_bundled_fonts()
    fams = set(QFontDatabase.families())
    for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if f in fams:
            FAMILY = f
            break
    DISPLAY = "Segoe UI Variable Display" if "Segoe UI Variable Display" in fams else FAMILY
    chosen = APPEARANCE.get("font") or ""
    if chosen and chosen in fams:
        FAMILY = DISPLAY = chosen


def set_font(app, family):
    """Меняет шрифт всех надписей сразу, без перезапуска."""
    old = {FAMILY, DISPLAY}
    APPEARANCE["font"] = family or ""
    save_appearance()
    pick_fonts()
    if app is None:
        return
    app.setFont(font(15))
    for w in app.allWidgets():
        f = w.font()
        if f.family() in old or not family:
            f.setFamily(FAMILY)
            w.setFont(f)
        w.update()
    for cb in list(_listeners):
        try:
            cb()
        except Exception:  # noqa: BLE001
            pass


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
QFrame[role="bubble_me"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_SOFT}, stop:1 {A});
    border-radius: 16px; border-bottom-right-radius: 4px;
}}
QFrame[role="bubble_bot"] {{
    background: {rgba(_mix(SURFACE, "#FFFFFF", 0.04), 0.92)}; border: 1px solid {LINE};
    border-radius: 16px; border-top-left-radius: 4px;
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
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px;
    border-radius: 8px; }}
QMenu {{
    background: {rgba(_mix(SURFACE, "#FFFFFF", 0.03), 0.97)}; color: {TEXT};
    border: 1px solid {rgba(_mix(LINE, A, 0.3), 0.95)}; border-radius: 12px; padding: 6px;
}}
QMenu::item {{ padding: 8px 26px 8px 14px; border-radius: 8px; margin: 1px 0; }}
QMenu::item:selected {{ background: {rgba(A, 0.22)}; color: #FFFFFF; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}
""" + hover_qss(A)


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
    if role in ("primary", "ghost", "secondary", "nav", "danger", "dangerfill"):
        HoverFX.attach(b)
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
    from icons import ChromeButton
    mn = ChromeButton("minimize", "Свернуть")
    mn.clicked.connect(getattr(win, "smooth_minimize", win.showMinimized))
    cl = ChromeButton("close", "Закрыть")
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


def install_russian(app):
    """Стандартные меню Qt (правый клик в поле ввода и т. п.) — по-русски."""
    import os
    from PySide6.QtCore import QLibraryInfo, QTranslator
    try:
        import PySide6
        dirs = [QLibraryInfo.path(QLibraryInfo.TranslationsPath),
                os.path.join(os.path.dirname(PySide6.__file__), "translations")]
    except Exception:  # noqa: BLE001
        return
    for d in dirs:
        tr = QTranslator(app)
        if tr.load("qtbase_ru", d):
            app.installTranslator(tr)
            app._ru_translator = tr
            return


def apply_app_theme(app):
    load_appearance()
    try:
        install_russian(app)
    except Exception:  # noqa: BLE001
        pass
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


_FOCUS_UNTIL = 0.0


def mark_focus(seconds=1.5):
    """Идёт разговор: фон замирает на это время, чтобы круг двигался идеально плавно."""
    global _FOCUS_UNTIL
    import time as _time
    _FOCUS_UNTIL = _time.monotonic() + seconds


def focused():
    import time as _time
    return _time.monotonic() < _FOCUS_UNTIL


class Backdrop(QWidget):
    """Фон экрана. Кадр фона рисуется один раз в картинку и только копируется при перерисовке
    (например, когда двигается круг) — поэтому анимация фона не мешает плавности."""

    FPS_MS = 50

    def __init__(self, glows=((0.22, 0.30, 0.55), (0.85, 0.85, 0.45))):
        super().__init__()
        self.glows = glows
        self._dots = None
        self._static = None
        self._frame = None
        self._frame_key = None
        self._t = 0.0
        import time as _time
        self._clock = _time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.FPS_MS)

    def invalidate(self):
        self._dots = None
        self._static = None
        self._frame = None
        self.__dict__.pop("_bg_cache", None)
        self.update()

    def resizeEvent(self, e):
        self.invalidate()
        super().resizeEvent(e)

    def hideEvent(self, e):
        self._frame = None                   # не держим картинку фона в памяти
        super().hideEvent(e)

    def _tick(self):
        import time as _time
        now = _time.monotonic()
        dt, self._clock = min(0.2, now - self._clock), now
        if APPEARANCE.get("eco"):
            return
        if focused():
            if not getattr(self, "_was_focused", False):
                self._was_focused = True
                self.update()                 # перерисуем кадр без падающих звёзд
            return
        if getattr(self, "_was_focused", False):
            self._was_focused = False
        style = bg_style()
        ms = BG_FRAME_MS.get(style, 70)
        if self._timer.interval() != ms:
            self._timer.setInterval(ms)
        w = self.window()
        moving = style in ANIMATED
        if style == "custom":
            import backgrounds
            moving = backgrounds.CUSTOM.animated()
        if moving and self.isVisible() and \
                not (w is not None and (w.isMinimized() or not w.isVisible())):
            self._t += dt
            self.update()

    def _custom_tick(self):
        if bg_style() != "custom":
            return 0
        import backgrounds
        return id(backgrounds.CUSTOM.current())

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

    def _paint_bg(self, p, w, h):
        style = bg_style()
        if style == "glass":
            p.fillRect(QRectF(0, 0, w, h), qcolor(BG, 255 * (1 - float(APPEARANCE.get("glass", 0.55)))))
        else:
            p.fillRect(QRectF(0, 0, w, h), QColor(BG))
        if style == "oled":
            return
        import backgrounds
        fn = backgrounds.PAINTERS.get(style)
        if fn is not None:
            fn(self, p, w, h, self._t + 40.0)
            return
        if self._static is None or self._static.size() != self.size():
            self._static = self._render_blobs(w, h, 0.0)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(QRectF(0, 0, w, h), self._static, QRectF(self._static.rect()))
        if self._dots is None or self._dots.size() != self.size():
            self._dots = self._render_dots()
        p.drawPixmap(0, 0, self._dots)

    def paintEvent(self, e):
        w, h = max(1, self.width()), max(1, self.height())
        dpr = self.devicePixelRatioF()
        key = (w, h, dpr, self._t, bg_style(), ACCENT, BG, APPEARANCE.get("glass"), focused(),
               APPEARANCE.get("custom_bg"), APPEARANCE.get("custom_dim"), self._custom_tick())
        if self._frame is None or self._frame_key != key:
            pix = QPixmap(int(w * dpr), int(h * dpr))
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.transparent)
            q = QPainter(pix)
            try:
                self._paint_bg(q, w, h)
            finally:
                q.end()
            self._frame, self._frame_key = pix, key
        p = QPainter(self)
        p.setClipRect(e.rect())
        p.drawPixmap(0, 0, self._frame)



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
    """Иконка программы (буква S) с ровным свечением."""

    def __init__(self, size=120, glow=True):
        super().__init__()
        self.setFixedSize(size, size)
        self.glow = glow
        self._t = 0.0
        import config
        path = config.resource_path("assets/icon.png")
        self._pix = QPixmap(str(path)) if path.exists() else QPixmap()


    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width()
        c = QPointF(w / 2, w / 2)
        if self.glow:
            g = QRadialGradient(c, w * 0.5)          # ровное свечение, без пульсации
            g.setColorAt(0.45, qcolor(ACCENT, 85))
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
        self.setProperty("nohover", True)
        HoverFX.attach(self)                 # только звук нажатия
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


# ---------------------------------------------------------------- наведение на кнопки
HOVER_STYLES = [
    ("glass", "Жидкое стекло", "Стеклянный блик пробегает по кнопке"),
    ("glow", "Свечение", "Мягкое свечение цветом темы"),
    ("neon", "Неон", "Яркая неоновая обводка"),
    ("fill", "Заливка", "Кнопка заливается цветом темы"),
    ("lift", "Парение", "Кнопка «приподнимается» с тенью"),
    ("classic", "Классика", "Только подсвеченная рамка"),
]


def click_feedback(w, hover=True):
    """Звук нажатия (и анимация наведения) для кнопки, созданной не через button()."""
    if not hover:
        w.setProperty("nohover", True)
    HoverFX.attach(w)


def hover_style():
    s = APPEARANCE.get("hover") or "glass"
    return s if s in dict((k, t) for k, t, _d in HOVER_STYLES) else "glass"


def hover_qss(A):
    st = hover_style()
    sel = ('QPushButton[role="ghost"]:hover, QPushButton[role="secondary"]:hover, '
           'QPushButton[role="nav"]:hover')
    opt = 'QFrame[role="option"]:hover'
    if st == "glass":
        # «жидкое стекло» как в iOS: полупрозрачная матовая кнопка, светлая кромка сверху,
        # при наведении — светлее, при нажатии — «вдавливается»
        rest = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.09), "
                "stop:1 rgba(255,255,255,0.03))")
        hov = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.20), "
               "stop:0.5 rgba(255,255,255,0.10), stop:1 rgba(255,255,255,0.07))")
        base = 'QPushButton[role="ghost"], QPushButton[role="secondary"]'
        return (f"{base} {{ background: {rest}; border: 1px solid rgba(255,255,255,0.13);"
                f" border-top: 1px solid rgba(255,255,255,0.26); border-radius: 12px; }}\n"
                f"{sel} {{ background: {hov}; color: #FFFFFF; border: 1px solid rgba(255,255,255,0.26);"
                f" border-top: 1px solid rgba(255,255,255,0.55); border-bottom: 1px solid rgba(255,255,255,0.12); }}\n"
                f'QPushButton[role="ghost"]:pressed, QPushButton[role="secondary"]:pressed {{ background: '
                f'rgba(255,255,255,0.22); border-top: 1px solid rgba(255,255,255,0.35); }}\n'
                f'QPushButton[role="ghost"]:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, '
                f'stop:0 {rgba(A, 0.34)}, stop:1 {rgba(A, 0.18)}); border: 1px solid {rgba(A, 0.7)};'
                f' border-top: 1px solid rgba(255,255,255,0.45); color: #FFFFFF; }}\n'
                f"{opt} {{ background: {hov}; border: 1px solid rgba(255,255,255,0.24);"
                f" border-top: 1px solid rgba(255,255,255,0.5); }}\n"
                f'QPushButton[role="primary"]:hover {{ border-top: 1px solid rgba(255,255,255,0.75); }}\n')
    if st == "glow":
        return (f"{sel} {{ background: {rgba(A, 0.12)}; color: #FFFFFF; border: 1px solid {A}; }}\n"
                f"{opt} {{ background: {rgba(A, 0.10)}; border: 1px solid {A}; }}\n")
    if st == "neon":
        return (f"{sel} {{ background: {rgba(A, 0.06)}; color: {_mix(A, '#FFFFFF', 0.55)};"
                f" border: 2px solid {_mix(A, '#FFFFFF', 0.25)}; }}\n"
                f"{opt} {{ border: 2px solid {_mix(A, '#FFFFFF', 0.25)}; }}\n")
    if st == "fill":
        return (f"{sel} {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {_mix(A, '#FFFFFF', 0.4)},"
                f" stop:1 {A}); color: #0A0C10; border: 1px solid {A}; }}\n"
                f"{opt} {{ background: {rgba(A, 0.22)}; border: 1px solid {A}; }}\n")
    if st == "lift":
        return (f"{sel} {{ background: rgba(255,255,255,0.07); color: #FFFFFF; border: 1px solid "
                f"{rgba(A, 0.6)}; }}\n{opt} {{ background: rgba(255,255,255,0.05); }}\n")
    return ""


class HoverFX:
    """Анимация при наведении: плавное свечение/тень, у «жидкого стекла» — пробегающий блик."""
    _filter = None

    @classmethod
    def attach(cls, w):
        from PySide6.QtCore import QObject

        if cls._filter is None:
            class _F(QObject):
                def eventFilter(self, obj, e):
                    from PySide6.QtCore import QEvent
                    t = e.type()
                    if t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
                        try:
                            import clicksounds
                            clicksounds.play()
                        except Exception:  # noqa: BLE001
                            pass
                    elif obj.property("nohover"):
                        return False
                    elif t == QEvent.Enter:
                        HoverFX._go(obj, True)
                    elif t == QEvent.Leave:
                        HoverFX._go(obj, False)
                    return False
            cls._filter = _F()
        w.installEventFilter(cls._filter)

    @staticmethod
    def _go(w, on):
        from PySide6.QtCore import QEasingCurve, QVariantAnimation
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtWidgets import QPushButton
        st = hover_style()
        if st in ("classic", "neon", "fill") or not w.isEnabled() or not isinstance(w, QPushButton):
            return                         # у карточек и простых стилей — только плавная подсветка цветом
        eff = w.graphicsEffect()
        if on and not isinstance(eff, QGraphicsDropShadowEffect):
            if eff is not None:
                return                       # у виджета уже свой эффект — не мешаем
            eff = QGraphicsDropShadowEffect(w)
            eff.setBlurRadius(0)
            eff.setOffset(0, 0)
            eff.setColor(QColor(0, 0, 0, 0))
            w.setGraphicsEffect(eff)
        if not isinstance(eff, QGraphicsDropShadowEffect):
            return
        old = getattr(w, "_hover_anim", None)
        start = old.currentValue() if old is not None else (0.0 if on else 1.0)
        if old is not None:
            old.stop()
        anim = QVariantAnimation(w)
        anim.setStartValue(float(start or 0.0))
        anim.setEndValue(1.0 if on else 0.0)
        anim.setDuration(260 if on else 320)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def step(v, w=w, eff=eff, st=st):
            v = float(v)
            if st == "lift":
                c = QColor(0, 0, 0, int(150 * v))
                eff.setOffset(0, 6 * v)
                eff.setBlurRadius(22 * v)
            else:
                c = QColor("#FFFFFF" if st == "glass" else ACCENT)
                c.setAlpha(int((70 if st == "glass" else 190) * v))
                eff.setOffset(0, 2 * v if st == "glass" else 0)
                eff.setBlurRadius((22 if st == "glass" else 34) * v)
            eff.setColor(c)

        def done(w=w, on=on):
            if not on:
                try:
                    w.setGraphicsEffect(None)
                except RuntimeError:
                    pass
        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        w._hover_anim = anim
        anim.start()


class Clickable(QFrame):
    clicked = Signal()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        HoverFX.attach(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ThumbCard(QWidget):
    """Карточка с картинкой (фон, тема): скругления, подпись и рамка выбора."""
    clicked = Signal()

    def __init__(self, title, sub="", w=232, h=150):
        super().__init__()
        click_feedback(self, hover=False)
        self.title, self.sub = title, sub
        self.pix = None
        self.selected = False
        self._hover = False
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)

    def set_pixmap(self, pix):
        self.pix = pix
        self.update()

    def set_selected(self, v):
        self.selected = bool(v)
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _):
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.save()
        p.setClipPath(path)
        if self.pix is not None:
            p.drawPixmap(r, self.pix, QRectF(self.pix.rect()))
        else:
            p.fillRect(r, QColor(SURFACE))
        g = QLinearGradient(0, r.bottom() - 62, 0, r.bottom())
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0, 190))
        p.fillRect(QRectF(r.left(), r.bottom() - 62, r.width(), 62), QBrush(g))
        p.restore()
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.DemiBold))
        p.drawText(QRectF(r.left() + 14, r.bottom() - 46, r.width() - 28, 22),
                   Qt.AlignLeft | Qt.AlignVCenter, self.title)
        if self.sub:
            p.setPen(QColor(255, 255, 255, 170))
            p.setFont(font(11))
            p.drawText(QRectF(r.left() + 14, r.bottom() - 25, r.width() - 28, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, self.sub)
        if self.selected:
            p.setPen(QPen(QColor(ACCENT), 2.6))
        elif self._hover:
            p.setPen(QPen(qcolor(ACCENT, 140), 1.6))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if self.selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawEllipse(QPointF(r.right() - 18, r.top() + 18), 10, 10)
            p.setPen(QPen(QColor("#0A0C10"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            c = QPointF(r.right() - 18, r.top() + 18)
            p.drawPolyline([QPointF(c.x() - 4.5, c.y()), QPointF(c.x() - 1.2, c.y() + 3.2),
                            QPointF(c.x() + 4.5, c.y() - 3.5)])


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
