"""Аватары: готовые (цветной круг и значок) или своя картинка."""
import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap

PRESETS = [
    ("cat", "🐱", "#F59E0B", "#B45309"), ("fox", "🦊", "#FB923C", "#C2410C"),
    ("panda", "🐼", "#94A3B8", "#334155"), ("bear", "🐻", "#D97706", "#78350F"),
    ("owl", "🦉", "#A78BFA", "#5B21B6"), ("bunny", "🐰", "#F9A8D4", "#BE185D"),
    ("penguin", "🐧", "#38BDF8", "#0C4A6E"), ("frog", "🐸", "#4ADE80", "#166534"),
    ("tiger", "🐯", "#FBBF24", "#B45309"), ("lion", "🦁", "#FCD34D", "#92400E"),
    ("koala", "🐨", "#CBD5E1", "#475569"), ("dog", "🐶", "#FDBA74", "#9A3412"),
    ("unicorn", "🦄", "#F0ABFC", "#7E22CE"), ("dragon", "🐉", "#34D399", "#065F46"),
    ("wolf", "🐺", "#94A3B8", "#1E293B"), ("butterfly", "🦋", "#60A5FA", "#1E3A8A"),
    ("ninja", "🥷", "#64748B", "#0F172A"), ("mage", "🧙", "#818CF8", "#312E81"),
    ("elf", "🧝", "#86EFAC", "#14532D"), ("vampire", "🧛", "#F87171", "#7F1D1D"),
    ("hero", "🦸", "#60A5FA", "#B91C1C"), ("astronaut", "🧑‍🚀", "#93C5FD", "#1E3A8A"),
    ("robot", "🤖", "#7DD3FC", "#0369A1"), ("alien", "👽", "#86EFAC", "#14532D"),
    ("invader", "👾", "#C084FC", "#581C87"), ("ghost", "👻", "#E2E8F0", "#64748B"),
    ("rocket", "🚀", "#FDA4AF", "#1E1B4B"), ("planet", "🪐", "#FDE68A", "#7C2D12"),
    ("moon", "🌙", "#FEF08A", "#1E1B4B"), ("star", "⭐", "#FDE047", "#A16207"),
    ("fire", "🔥", "#FB923C", "#7F1D1D"), ("lightning", "⚡", "#FDE047", "#1E293B"),
    ("sakura", "🌸", "#FBCFE8", "#9D174D"), ("leaf", "🍀", "#86EFAC", "#14532D"),
    ("snow", "❄️", "#BAE6FD", "#0C4A6E"), ("wave", "🌊", "#67E8F9", "#164E63"),
    ("game", "🎮", "#A5B4FC", "#1E1B4B"), ("headphones", "🎧", "#F472B6", "#1F2937"),
    ("guitar", "🎸", "#FCA5A5", "#7F1D1D"), ("crown", "👑", "#FDE047", "#713F12"),
    ("diamond", "💎", "#67E8F9", "#1E3A8A"), ("sword", "⚔️", "#CBD5E1", "#1E293B"),
    ("pumpkin", "🎃", "#FDBA74", "#431407"), ("pizza", "🍕", "#FCD34D", "#9A3412"),
    ("ball", "🏀", "#FDBA74", "#7C2D12"), ("skate", "🛹", "#A3E635", "#365314"),
]


def _circle(pix_src, size):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(path)
    p.drawPixmap(QRectF(0, 0, size, size), pix_src, QRectF(pix_src.rect()))
    p.end()
    return pix


def render_preset(pid, size):
    item = next((x for x in PRESETS if x[0] == pid), PRESETS[0])
    _pid, glyph, c1, c2 = item
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(0, 0, size, size))
    hl = QLinearGradient(0, 0, 0, size)
    hl.setColorAt(0, QColor(255, 255, 255, 60))
    hl.setColorAt(0.5, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(hl))
    p.drawEllipse(QRectF(0, 0, size, size))
    f = QFont("Segoe UI Emoji")
    f.setPixelSize(int(size * 0.56))
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, size * 0.02, size, size), Qt.AlignCenter, glyph)
    p.end()
    return pix


def avatars_dir():
    import config
    d = config.data_dir() / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_custom(path, login):
    """Своя картинка -> квадрат 256×256 в папке программы. -> значение для настроек."""
    from PySide6.QtGui import QImage
    img = QImage(path)
    if img.isNull():
        raise ValueError("Не получилось открыть картинку.")
    side = min(img.width(), img.height())
    img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    img = img.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    import hashlib
    name = hashlib.sha1(login.encode()).hexdigest()[:12] + ".png"
    out = avatars_dir() / name
    img.save(str(out))
    return "file:" + str(out)


def render(value, size, letter="?"):
    """Аватар по значению из настроек: preset:<id> / file:<путь> / пусто (буква)."""
    value = value or ""
    if value.startswith("preset:"):
        return render_preset(value[7:], size)
    if value.startswith("file:") and os.path.isfile(value[5:]):
        src = QPixmap(value[5:])
        if not src.isNull():
            return _circle(src, size)
    return None


def apply(widget, value, letter, size):
    """Поставить аватар на кнопку/надпись. Нет аватара — первая буква, как раньше."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QPushButton
    pix = render(value, size * 2)
    if pix is not None:
        pix.setDevicePixelRatio(2.0)
    if isinstance(widget, QPushButton):
        if pix is None:
            widget.setIcon(QIcon())
            widget.setText(letter)
        else:
            widget.setText("")
            widget.setIcon(QIcon(pix))
            widget.setIconSize(QSize(size, size))
    else:
        if pix is None:
            widget.setPixmap(QPixmap())
            widget.setText(letter)
        else:
            widget.setText("")
            widget.setPixmap(pix)


class AvatarDialog:
    """Окно «Изменить аватар»: сетка готовых + «Добавить свой». -> значение или None."""

    @staticmethod
    def ask(parent, current, login):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFont, QIcon
        from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QHBoxLayout, QPushButton,
                                       QScrollArea, QVBoxLayout, QWidget)
        import theme as T
        dlg = QDialog(parent)
        dlg.setWindowTitle("Аватар")
        dlg.setModal(True)
        dlg.resize(640, 620)
        dlg.setStyleSheet(f"QDialog {{ background: {T.BG}; }}")
        out = {"v": None}
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(12)
        lay.addWidget(T.label("Выберите аватар", 20, QFont.DemiBold))
        lay.addWidget(T.label("Нажмите на понравившийся или добавьте свою картинку.", 13,
                              role="muted"))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        grid = QGridLayout(inner)
        grid.setSpacing(10)
        cols = 6

        def pick(v):
            out["v"] = v
            dlg.accept()

        for i, (pid, *_rest) in enumerate(PRESETS):
            b = QPushButton()
            b.setFixedSize(84, 84)
            b.setCursor(Qt.PointingHandCursor)
            pix = render_preset(pid, 136)
            pix.setDevicePixelRatio(2.0)
            b.setIcon(QIcon(pix))
            b.setIconSize(QSize(68, 68))
            sel = current == "preset:" + pid
            b.setStyleSheet(
                f"QPushButton {{ background: {T.rgba('#FFFFFF', 0.04)}; border-radius: 42px;"
                f" border: 2px solid {T.ACCENT if sel else 'transparent'}; }}"
                f"QPushButton:hover {{ background: {T.rgba(T.ACCENT, 0.18)}; }}")
            b.clicked.connect(lambda _=False, v="preset:" + pid: pick(v))
            grid.addWidget(b, i // cols, i % cols)
        area.setWidget(inner)
        lay.addWidget(area, 1)
        row = QHBoxLayout()
        own = T.button("Добавить свой аватар…", "primary", 14)

        def browse():
            path, _ = QFileDialog.getOpenFileName(dlg, "Картинка для аватара", "",
                                                  "Картинки (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
            if path:
                try:
                    pick(save_custom(path, login))
                except ValueError:
                    pass
        own.clicked.connect(browse)
        row.addWidget(own)
        letter = T.button("Без картинки (буква)", "ghost", 13, QFont.Normal)
        letter.clicked.connect(lambda: pick(""))
        row.addWidget(letter)
        row.addStretch(1)
        cancel = T.button("Отмена", "ghost", 14, QFont.Normal)
        cancel.clicked.connect(dlg.reject)
        row.addWidget(cancel)
        lay.addLayout(row)
        if dlg.exec() != QDialog.Accepted:
            return None
        return out["v"]
