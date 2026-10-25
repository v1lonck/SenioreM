"""Компаньон над панелью задач: ваш персонаж (набор картинок — например, из shimeji-архива),
который оживает и «говорит» вместе с помощником.

Персонажи добавляются в профиле → «Компаньон» → «Добавить персонажа» (архив .zip или папка).
Из архива берутся только картинки (.png, .webp, .gif) — программы и скрипты не запускаются.
Кадры, похожие на основную позу, становятся «живыми»: персонаж меняет их, моргает и
улыбается, а когда помощник говорит — быстро переключает выражения и подпрыгивает."""
import json
import math
import os
import random
import re
import shutil
import time
import zipfile

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QRadialGradient)
from PySide6.QtWidgets import QWidget

import theme as T

IMG_EXT = (".png", ".webp", ".gif")
SKIP_NAMES = ("icon", "thumbs", "preview", "logo", "banner")
GENERIC_DIRS = {"img", "image", "images", "sprites", "sprite", "frames", "shime", "png", "conf",
                "assets", "data", "res"}
MAX_H = 360            # высота хранимых кадров


def _c(hex_, a=255):
    c = QColor(hex_)
    c.setAlpha(int(a))
    return c


# ------------------------------------------------------------------ хранилище персонажей
def packs_dir():
    import config
    d = config.data_dir() / "companions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_packs():
    """[(id, имя)] — добавленные персонажи."""
    out = []
    for d in sorted(packs_dir().iterdir()):
        meta = d / "meta.json"
        if meta.is_file():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                out.append((d.name, m.get("name") or d.name))
            except (OSError, ValueError):
                continue
    return out


def figures():
    return [("pack:" + pid, name, "Ваш персонаж") for pid, name in list_packs()] + \
        [("none", "Нет", "Без компаньона")]


def norm_kind(kind):
    kind = kind or "none"
    if kind.startswith("pack:") and (packs_dir() / kind[5:] / "meta.json").is_file():
        return kind
    return "none"


def delete_pack(pid):
    _PACKS.pop(pid, None)
    shutil.rmtree(packs_dir() / pid, ignore_errors=True)


def _natural(name):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def _pack_name(dirpath, fallback):
    parts = [p for p in re.split(r"[\\/]", dirpath) if p]
    for p in reversed(parts):
        if p.lower() not in GENERIC_DIRS:
            name = re.sub(r"(?i)^shimeji[-_ ]*|[-_ ]*shimeji$", "", p).replace("_", " ").strip()
            return name or p
    return fallback


def _iou(a, b):
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 0.0


def _build_pack(images, name):
    """images — [(имя, байты)] кадров одного персонажа. -> id или None."""
    import io
    from PIL import Image
    frames = []
    for _fname, data in sorted(images, key=lambda x: _natural(os.path.basename(x[0]))):
        try:
            im = Image.open(io.BytesIO(data))
            im.seek(0)
            im = im.convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        alpha = im.getchannel("A")
        bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
        if not bbox:
            continue
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if bw * bh < im.width * im.height * 0.01:
            continue                                   # почти пустой кадр
        frames.append((im, bbox))
    if not frames:
        return None
    w0, h0 = frames[0][0].size
    frames = [(im if im.size == (w0, h0) else im.resize((w0, h0)), bb) for im, bb in frames]

    def mask(im):
        a = im.getchannel("A").resize((32, 32))
        return [1 if v > 60 else 0 for v in a.getdata()]

    def boxy(im, bb):
        """Кадр — прямоугольное окошко с текстом, а не персонаж."""
        crop = im.crop(bb).getchannel("A")
        full = sum(1 for v in crop.getdata() if v > 200)
        return full > crop.width * crop.height * 0.93

    def tone(im):
        """Цвета по зонам 12×12 на белом фоне: перевёрнутые и другие позы сильно отличаются."""
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return list(bg.convert("RGB").resize((12, 12)).getdata())

    base = mask(frames[0][0])
    base_tone = tone(frames[0][0])

    def similar(im):
        if _iou(mask(im), base) < 0.8:
            return False
        diff = sum(abs(x[k] - y[k]) for x, y in zip(tone(im), base_tone) for k in range(3)) / 432
        return diff < 23.5

    idle = [i for i, (im, bb) in enumerate(frames) if similar(im) and not boxy(im, bb)][:30] or [0]
    x1 = min(frames[i][1][0] for i in idle)
    y1 = min(frames[i][1][1] for i in idle)
    x2 = max(frames[i][1][2] for i in idle)
    y2 = max(frames[i][1][3] for i in idle)
    pad = 4
    box = (max(0, x1 - pad), max(0, y1 - pad), min(w0, x2 + pad), min(h0, y2 + pad))
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().encode("ascii", "ignore").decode()).strip("-")
    pid = (slug or "pack") + "-" + format(int(time.time() * 1000) % 100000, "05d")
    out = packs_dir() / pid
    out.mkdir(parents=True, exist_ok=True)
    scale = min(1.0, MAX_H / max(1, box[3] - box[1]))
    size = (1, 1)
    for k, i in enumerate(idle):
        im = frames[i][0].crop(box)
        if scale < 1.0:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                           Image.LANCZOS)
        im.save(out / f"idle_{k:02d}.png")
        size = im.size
    (out / "meta.json").write_text(json.dumps({"name": name, "frames": len(idle), "w": size[0],
                                               "h": size[1]}, ensure_ascii=False), encoding="utf-8")
    return pid


def import_path(path):
    """Добавить персонажей из .zip или папки. -> [(id, имя)]."""
    groups = {}
    stem = os.path.splitext(os.path.basename(path.rstrip("\\/")))[0]
    if os.path.isdir(path):
        top = os.path.dirname(path.rstrip("\\/"))
        for root, _dirs, files in os.walk(path):
            for f in files:
                if f.lower().endswith(IMG_EXT) and not f.lower().startswith(SKIP_NAMES):
                    with open(os.path.join(root, f), "rb") as fh:
                        groups.setdefault(os.path.relpath(root, top), []).append((f, fh.read()))
    else:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                base = os.path.basename(info.filename)
                if info.is_dir() or not base.lower().endswith(IMG_EXT) or \
                        base.lower().startswith(SKIP_NAMES) or info.file_size > 8_000_000:
                    continue
                groups.setdefault(os.path.dirname(info.filename), []).append(
                    (base, z.read(info)))
    added = []
    for d, imgs in groups.items():
        if len(imgs) < 3 and len(groups) > 1:
            continue
        name = _pack_name(d, stem)
        if name.lower() in GENERIC_DIRS:
            name = stem
        name = re.sub(r"^[0-9a-f]{8}-", "", name)
        if re.fullmatch(r"[0-9a-z]{6,12}", name.lower()) and re.search(r"\d", name):
            name = f"Персонаж {len(list_packs()) + len(added) + 1}"   # имя архива — случайные буквы
        pid = _build_pack(imgs, name)
        if pid:
            added.append((pid, name))
    return added


def rename_pack(pid, name):
    meta = packs_dir() / pid / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["name"] = name
    meta.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


class Pack:
    def __init__(self, pid):
        d = packs_dir() / pid
        self.meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        self.name = self.meta.get("name", pid)
        self.frames = []
        for k in range(int(self.meta.get("frames", 1))):
            pix = QPixmap(str(d / f"idle_{k:02d}.png"))
            if not pix.isNull():
                self.frames.append(pix)
        self.aspect = self.meta.get("h", 1) / max(1, self.meta.get("w", 1))
        self._scaled = {}

    def frame(self, i, height):
        key = (i, int(height))
        if key not in self._scaled:
            if len(self._scaled) > 64:
                self._scaled.clear()
            self._scaled[key] = self.frames[i].scaledToHeight(max(1, int(height)),
                                                              Qt.SmoothTransformation)
        return self._scaled[key]


_PACKS = {}


def get_pack(kind):
    if not kind or not kind.startswith("pack:"):
        return None
    pid = kind[5:]
    if pid not in _PACKS:
        try:
            p = Pack(pid)
        except (OSError, ValueError):
            return None
        if not p.frames:
            return None
        _PACKS[pid] = p
    return _PACKS[pid]


def aspect(kind):
    p = get_pack(kind)
    return p.aspect if p else 1.0


# ------------------------------------------------------------------ анимация
class FigurePainter:
    def __init__(self):
        self.t = 0.0
        self.speaking = False
        self.listening = False
        self.animated = True
        self.frame = 0
        self._next = 1.5
        self._jump = 0.0

    def tick(self, dt, n_frames=1):
        self.t += dt
        self._next -= dt
        if self.speaking:
            if self._next <= 0:
                if n_frames > 1:
                    self.frame = random.choice([i for i in range(n_frames) if i != self.frame])
                self._next = random.uniform(0.16, 0.32)
            self._jump = abs(math.sin(self.t * 7.5))
        else:
            self._jump *= 0.8
            if not self.animated:
                self.frame = 0
            elif self._next <= 0:
                # чаще основная поза, иногда другие выражения
                if self.frame != 0 or n_frames == 1 or random.random() < 0.45:
                    self.frame = 0
                    self._next = random.uniform(2.0, 4.5)
                else:
                    self.frame = random.randrange(1, n_frames)
                    self._next = random.uniform(0.35, 1.4)
        if self.frame >= n_frames:
            self.frame = 0

    def paint(self, p, rect, kind):
        pack = get_pack(kind)
        if pack is None:
            return
        if self.frame >= len(pack.frames):
            self.frame = 0
        h = min(rect.height() - 6, rect.width() * pack.aspect)
        pix = pack.frame(self.frame, h)
        w = pix.width()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        feet = QPointF(rect.center().x(), rect.bottom())
        g = QRadialGradient(QPointF(feet.x(), feet.y() - 4), w * 0.45)
        g.setColorAt(0, _c("#000000", 70))
        g.setColorAt(1, _c("#000000", 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(feet.x(), feet.y() - 4), w * 0.42, 7)
        p.translate(feet)
        if self.animated:
            p.scale(1.0, 1.0 + 0.008 * math.sin(self.t * 2.0))       # «дыхание»
        p.translate(0, -h * 0.05 * self._jump)                         # подпрыгивает, когда говорит
        p.translate(-feet.x(), -feet.y())
        p.drawPixmap(QPointF(feet.x() - w / 2, feet.y() - h - 6), pix)
        p.restore()


# ------------------------------------------------------------------ окно над панелью задач
class CompanionWindow(QWidget):
    def __init__(self, on_click=None, on_remove=None, on_settings=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.on_remove, self.on_settings = on_remove, on_settings
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.painter = FigurePainter()
        self.kind = "none"
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
        self.fig_h = int(self.size_px * 1.6)
        self.fig_w = int(self.fig_h / max(0.3, aspect(self.kind))) + 8
        self.setFixedSize(self.fig_w + int(self.size_px * 1.7), self.fig_h + 14)
        self.place()

    def place(self):
        if self._custom_pos is not None:
            self.move(self._custom_pos)
            return
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 12, geo.bottom() - self.height() + 4)

    def say(self, text, seconds=6.0):
        self.text = text[:90] + ("…" if len(text) > 90 else "")
        self._text_until = time.time() + seconds

    def set_speaking(self, flag):
        self.painter.speaking = flag

    def set_listening(self, flag):
        self.painter.listening = flag

    def _tick(self):
        pack = get_pack(self.kind)
        self.painter.tick(0.04, len(pack.frames) if pack else 1)
        if self.text and time.time() > self._text_until and not self.painter.speaking:
            self.text = ""
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
            x = max(4, fig.left() - bw + self.fig_w * 0.3)
            y = max(4, fig.top() + self.fig_h * 0.05)
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

    def contextMenuEvent(self, e):
        """Правый клик по персонажу: убрать, сменить, открыть SenioreM."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {T.SURFACE}; color: {T.TEXT}; border: 1px solid {T.LINE}; "
            f"border-radius: 10px; padding: 6px; font-size: 14px; }}"
            f"QMenu::item {{ padding: 8px 22px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background: {T.rgba(T.ACCENT, 0.25)}; }}"
            f"QMenu::separator {{ height: 1px; background: {T.LINE}; margin: 4px 8px; }}")
        a_open = menu.addAction("Открыть SenioreM")
        a_set = menu.addAction("Сменить персонажа…")
        a_home = menu.addAction("Вернуть на место")
        menu.addSeparator()
        a_rm = menu.addAction("Убрать")
        act = menu.exec(e.globalPos())
        if act is a_open and self.on_click:
            self.on_click()
        elif act is a_set and self.on_settings:
            self.on_settings()
        elif act is a_home:
            self._custom_pos = None
            self.place()
        elif act is a_rm:
            self.hide()
            if self.on_remove:
                self.on_remove()

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
        if e.button() != Qt.LeftButton:
            return
        if self._moved:
            self._custom_pos = QPoint(self.pos())
        elif self.on_click:
            self.on_click()
        self._drag = None


class FigurePreview(QWidget):
    """Живой предпросмотр персонажа в настройках."""

    def __init__(self, size=180):
        super().__init__()
        self.setFixedSize(size, int(size * 1.4))
        self.painter = FigurePainter()
        self.kind = "none"
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

    def _tick(self):
        if self.isVisible():
            pack = get_pack(self.kind)
            self.painter.tick(0.04, len(pack.frames) if pack else 1)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if get_pack(self.kind) is None:
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(14))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Персонаж не выбран.\nДобавьте своего кнопкой ниже.")
            return
        self.painter.paint(p, QRectF(self.rect()).adjusted(6, 6, -6, -4), self.kind)


def thumb(kind, w, h):
    """Карточка-портрет для выбора персонажа в настройках."""
    pix = QPixmap(w, h)
    pix.fill(QColor("#0B0E15"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    g = QRadialGradient(QPointF(w / 2, h * 0.4), max(w, h) * 0.8)
    g.setColorAt(0, _c(T.ACCENT, 70))
    g.setColorAt(1, _c(T.ACCENT, 0))
    p.fillRect(pix.rect(), QBrush(g))
    pack = get_pack(kind)
    if pack is not None:
        fh = min(h * 0.74, w * 0.9 * pack.aspect)
        fr = pack.frame(0, fh)
        p.drawPixmap(QPointF((w - fr.width()) / 2, h * 0.05), fr)
    else:
        p.setPen(QPen(_c("#FFFFFF", 90), 3))
        p.drawEllipse(QPointF(w / 2, h * 0.4), 26, 26)
        p.drawLine(QPointF(w / 2 - 18, h * 0.4 + 18), QPointF(w / 2 + 18, h * 0.4 - 18))
    p.end()
    return pix
