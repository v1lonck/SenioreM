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
    packs = list_packs()
    built = [("pack:" + pid, name, "Встроенный") for pid, name in packs if pid.startswith("builtin-")]
    own = [("pack:" + pid, name, "Ваш персонаж") for pid, name in packs if not pid.startswith("builtin-")]
    return built + own + [("none", "Нет", "Без компаньона")]


def _removed_file():
    return packs_dir() / ".removed_builtin.json"


def install_builtin(restore=False):
    """Встроенные персонажи (Аля, Аки, Мия, Рэй, котёнок, лисёнок) — копируем из программы в папку персонажей.
    Удалённые пользователем не возвращаем, пока он сам не нажмёт «Вернуть встроенных»."""
    import config
    src = config.resource_path("assets/companions")
    if not src.is_dir():
        return []
    try:
        removed = set(json.loads(_removed_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        removed = set()
    if restore:
        removed = set()
        try:
            _removed_file().unlink()
        except OSError:
            pass
    added = []
    for d in sorted(src.iterdir()):
        meta = d / "meta.json"
        if not meta.is_file() or d.name in removed:
            continue
        try:
            ver = json.loads(meta.read_text(encoding="utf-8")).get("builtin", 0)
            dst = packs_dir() / d.name
            have = 0
            if (dst / "meta.json").is_file():
                have = json.loads((dst / "meta.json").read_text(encoding="utf-8")).get("builtin", 0)
            if have >= ver:
                continue
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(d, dst)
            _PACKS.pop(d.name, None)
            added.append(d.name)
        except (OSError, ValueError):
            continue
    return added


def norm_kind(kind):
    kind = kind or "none"
    if kind.startswith("pack:") and (packs_dir() / kind[5:] / "meta.json").is_file():
        return kind
    return "none"


def delete_pack(pid):
    _PACKS.pop(pid, None)
    if pid.startswith("builtin-"):
        try:
            removed = set(json.loads(_removed_file().read_text(encoding="utf-8")))
        except (OSError, ValueError):
            removed = set()
        removed.add(pid)
        _removed_file().write_text(json.dumps(sorted(removed)), encoding="utf-8")
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
    """images — [(имя, байты)] кадров одного персонажа. -> id или None.
    Сохраняем все пригодные кадры и отмечаем позы: стоит (idle), сидит (sit), лежит (lie)."""
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
        bbox = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        if not bbox:
            continue
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if bw * bh < im.width * im.height * 0.01:
            continue                                   # почти пустой кадр
        frames.append((im, bbox))
    if not frames:
        return None
    w0, h0 = frames[0][0].size
    fixed = []
    for im, bb in frames:
        if im.size != (w0, h0):
            im = im.resize((w0, h0))
            bb = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox() or bb
        fixed.append((im, bb))
    frames = fixed

    def mask(im):
        a = im.getchannel("A").resize((32, 32))
        return [1 if v > 60 else 0 for v in a.getdata()]

    def boxy(im, bb):
        """Кадр — прямоугольное окошко с текстом, а не персонаж."""
        crop = im.crop(bb).getchannel("A")
        full = sum(1 for v in crop.getdata() if v > 200)
        return full > crop.width * crop.height * 0.93

    def tone(im):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return list(bg.convert("RGB").resize((12, 12)).getdata())

    frames = [(im, bb) for im, bb in frames if not boxy(im, bb)][:120]
    if not frames:
        return None
    base = mask(frames[0][0])
    base_tone = tone(frames[0][0])

    def similar(im):
        if _iou(mask(im), base) < 0.8:
            return False
        diff = sum(abs(x[k] - y[k]) for x, y in zip(tone(im), base_tone) for k in range(3)) / 432
        return diff < 23.5

    idle = [i for i, (im, _bb) in enumerate(frames) if similar(im)][:30] or [0]
    ix1 = min(frames[i][1][0] for i in idle)
    iy1 = min(frames[i][1][1] for i in idle)
    ix2 = max(frames[i][1][2] for i in idle)
    iy2 = max(frames[i][1][3] for i in idle)
    ih, iw = max(1, iy2 - iy1), max(1, ix2 - ix1)
    base_aspect = iw / ih
    tags = []
    for i, (im, bb) in enumerate(frames):
        t = []
        if i in idle:
            t.append("idle")
        else:
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            rh, ra = h / ih, (w / max(1, h)) / base_aspect
            low = bb[3] >= iy2 - ih * 0.12              # стоит на «полу», а не в прыжке
            if low and ra >= 1.4 and rh <= 0.75:
                t.append("lie")
            elif low and 0.55 <= rh <= 0.88 and 0.8 <= ra <= 1.6:
                t.append("sit")
        tags.append(t)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().encode("ascii", "ignore").decode()).strip("-")
    pid = (slug or "pack") + "-" + format(int(time.time() * 1000) % 100000, "05d")
    out = packs_dir() / pid
    out.mkdir(parents=True, exist_ok=True)
    sc = min(1.0, MAX_H / ih)
    meta_frames = []
    for k, (im, bb) in enumerate(frames):
        x1, y1 = max(0, bb[0] - 2), max(0, bb[1] - 2)
        x2, y2 = min(w0, bb[2] + 2), min(h0, bb[3] + 2)
        crop = im.crop((x1, y1, x2, y2))
        if sc < 1.0:
            crop = crop.resize((max(1, int(crop.width * sc)), max(1, int(crop.height * sc))),
                               Image.LANCZOS)
        fname = f"f_{k:03d}.png"
        crop.save(out / fname)
        meta_frames.append({"f": fname, "x": x1 * sc, "y": y1 * sc, "tags": tags[k]})
    meta = {"v": 2, "name": name, "frames": meta_frames, "idle_h": ih * sc, "idle_w": iw * sc,
            "cx": (ix1 + ix2) / 2 * sc, "bottom": iy2 * sc}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
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


def _looks_like_pack(path):
    """Архив с кадрами персонажа (shimeji: img/shime1.png…, или sprites/0000.webp…)."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(IMG_EXT)]
    except (OSError, zipfile.BadZipFile):
        return False
    if len(names) < 3:
        return False
    hits = sum(1 for n in names if re.search(r"(^|/)(sprites|img|frames)/", n.lower())
               or re.search(r"shime\d+\.png$", n.lower()) or re.search(r"/\d{2,4}\.(png|webp|gif)$", n.lower()))
    return hits >= 3


def auto_import():
    """Сам находит архивы с персонажами в «Загрузках» и на рабочем столе и добавляет их.
    -> [(id, имя)] новых персонажей."""
    env = os.environ
    home = env.get("USERPROFILE", "")
    roots = [os.path.join(home, "Downloads"), os.path.join(home, "Desktop"),
             os.path.join(home, "OneDrive", "Desktop"), os.path.join(home, "Documents")]
    if env.get("OneDrive"):
        roots.append(os.path.join(env["OneDrive"], "Desktop"))
    done_file = packs_dir() / "imported.json"
    try:
        done = set(json.loads(done_file.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        done = set()
    found = []
    for root in dict.fromkeys(roots):
        try:
            for e in os.scandir(root):
                if e.is_file() and e.name.lower().endswith(".zip") and e.stat().st_size < 150_000_000:
                    key = f"{e.name}|{e.stat().st_size}"
                    if key not in done and _looks_like_pack(e.path):
                        found.append((e.path, key))
        except OSError:
            continue
    if not found:
        return []
    # персонажи старого формата (только одна поза) — заменяем на новые из тех же архивов
    for pid, _n in list_packs():
        try:
            m = json.loads((packs_dir() / pid / "meta.json").read_text(encoding="utf-8"))
            if m.get("v") != 2:
                delete_pack(pid)
        except (OSError, ValueError):
            continue
    added = []
    for path, key in found:
        try:
            added += import_path(path)
        except Exception:  # noqa: BLE001
            pass
        done.add(key)
    try:
        done_file.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return added


def rename_pack(pid, name):
    meta = packs_dir() / pid / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["name"] = name
    meta.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


class Pack:
    """Кадры персонажа с позами. Все кадры выравниваются по «полу» основной позы."""

    def __init__(self, pid):
        d = packs_dir() / pid
        self.pid = pid
        self.meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        self.name = self.meta.get("name", pid)
        self.frames, self.pos, self.tags = [], [], []
        if self.meta.get("v") == 2:
            for fr in self.meta["frames"]:
                pix = QPixmap(str(d / fr["f"]))
                if pix.isNull():
                    continue
                self.frames.append(pix)
                self.pos.append((fr["x"], fr["y"]))
                self.tags.append(set(fr.get("tags", [])))
            self.idle_h = self.meta.get("idle_h", 100)
            self.idle_w = self.meta.get("idle_w", 100)
            self.cx = self.meta.get("cx", 50)
            self.bottom = self.meta.get("bottom", 100)
        else:                                       # старый формат (только основная поза)
            for k in range(int(self.meta.get("frames", 1))):
                pix = QPixmap(str(d / f"idle_{k:02d}.png"))
                if not pix.isNull():
                    self.frames.append(pix)
                    self.pos.append((0, 0))
                    self.tags.append({"idle"})
            self.idle_w, self.idle_h = self.meta.get("w", 100), self.meta.get("h", 100)
            self.cx, self.bottom = self.idle_w / 2, self.idle_h
        self.aspect = self.idle_h / max(1, self.idle_w)
        self._scaled = {}

    def pose_frames(self, pose, talk=False):
        """Кадры позы. talk=True — с открытым ртом (если такие отмечены), иначе — без них."""
        out = [i for i, t in enumerate(self.tags) if pose in t]
        if not out:
            pose = "idle"
            out = [i for i, t in enumerate(self.tags) if "idle" in t] or [0]
        talking = [i for i in out if "talk" in self.tags[i]]
        quiet = [i for i in out if "talk" not in self.tags[i]]
        if talk:
            return talking or out
        return quiet or out

    def seq(self, pose):
        """Сколько секунд на кадр, если позу нужно проигрывать по порядку (болтает ногами, Zzz)."""
        return (self.meta.get("seq") or {}).get(pose)

    def has(self, pose):
        return any(pose in t for t in self.tags)

    def scaled(self, i, scale):
        key = (i, round(scale, 3))
        if key not in self._scaled:
            if len(self._scaled) > 96:
                self._scaled.clear()
            pix = self.frames[i]
            self._scaled[key] = pix.scaled(max(1, int(pix.width() * scale)),
                                           max(1, int(pix.height() * scale)),
                                           Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return self._scaled[key]

    def set_tags(self, i, tags):
        """Поменять позу кадра (из окна «Позы») и сохранить."""
        self.tags[i] = set(tags)
        if self.meta.get("v") == 2:
            self.meta["frames"][i]["tags"] = sorted(tags)
            (packs_dir() / self.pid / "meta.json").write_text(
                json.dumps(self.meta, ensure_ascii=False), encoding="utf-8")


def frame_pixmap(kind, i):
    p = get_pack(kind)
    return p.frames[i] if p and 0 <= i < len(p.frames) else None


_PACKS = {}


def get_pack(kind):
    if not kind or not kind.startswith("pack:"):
        return None
    pid = kind[5:]
    if pid not in _PACKS:
        try:
            p = Pack(pid)
        except (OSError, ValueError, KeyError):
            return None
        if not p.frames:
            return None
        _PACKS[pid] = p
    return _PACKS[pid]


def aspect(kind):
    p = get_pack(kind)
    return p.aspect if p else 1.0


# ------------------------------------------------------------------ анимация
POSES = (("auto", "Сам меняет"), ("stand", "Стоит"), ("sit", "Сидит"), ("lie", "Лежит"))


class FigurePainter:
    def __init__(self):
        self.t = 0.0
        self.speaking = False
        self.listening = False
        self.animated = True
        self.pose = "auto"            # stand | sit | lie | auto
        self._cur_pose = "idle"
        self._pose_left = 30.0
        self.frame = 0
        self._next = 1.5
        self._jump = 0.0

    def _want_pose(self, pack, dt):
        if self.pose == "sit":
            return "sit"
        if self.pose == "lie":
            return "lie"
        if self.pose == "stand" or not self.animated or pack is None:
            return "idle"
        # «сам меняет»: в основном стоит, иногда садится или ложится отдохнуть
        self._pose_left -= dt
        if self._pose_left <= 0:
            options = [p for p in ("sit", "lie") if pack.has(p)]
            if self._cur_pose == "idle" and options and random.random() < 0.6:
                self._cur_pose = random.choice(options)
                self._pose_left = random.uniform(12, 30)
            else:
                self._cur_pose = "idle"
                self._pose_left = random.uniform(25, 60)
        return "idle" if self.speaking and self._cur_pose == "lie" else self._cur_pose

    def tick(self, dt, pack=None):
        self.t += dt
        self._next -= dt
        pose = self._want_pose(pack, dt)
        frames = pack.pose_frames(pose) if pack else [0]
        if self.speaking:
            talk = pack.pose_frames(pose, talk=True) if pack else [0]
            both = list(dict.fromkeys(frames[:1] + talk))
            if self.frame not in both:
                self.frame = talk[0]
                self._next = 0.2
            if self._next <= 0:
                if len(both) > 1:
                    self.frame = random.choice([i for i in both if i != self.frame])
                self._next = random.uniform(0.14, 0.28)
            self._jump = abs(math.sin(self.t * 7.5)) * (0.4 if pose != "idle" else 1.0)
        else:
            self._jump *= 0.8
            step = pack.seq(pose) if pack else None
            if self.frame not in frames:
                self.frame = frames[0]
                self._next = step or 0.6
            if not self.animated:
                self.frame = frames[0]
            elif step:                                  # по порядку: болтает ногами, «Zzz»
                if self._next <= 0:
                    k = frames.index(self.frame) if self.frame in frames else -1
                    self.frame = frames[(k + 1) % len(frames)]
                    self._next = step
            elif self._next <= 0:
                if self.frame != frames[0] or len(frames) == 1 or random.random() < 0.45:
                    self.frame = frames[0]
                    self._next = random.uniform(2.0, 4.5)
                else:
                    self.frame = random.choice(frames[1:])
                    self._next = random.uniform(0.35, 1.4)

    def paint(self, p, rect, kind):
        pack = get_pack(kind)
        if pack is None:
            return
        if self.frame >= len(pack.frames):
            self.frame = 0
        h = min(rect.height() - 6, rect.width() * pack.aspect)
        scale = h / max(1, pack.idle_h)
        pix = pack.scaled(self.frame, scale)
        fx, fy = pack.pos[self.frame]
        feet = QPointF(rect.center().x(), rect.bottom() - 6)
        x = feet.x() + (fx - pack.cx) * scale
        y = feet.y() - (pack.bottom - fy) * scale
        if x + pix.width() > rect.right() + 4:          # лёжа персонаж шире — не вылезаем за край
            x = rect.right() + 4 - pix.width()
        w = pack.idle_w * scale
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QRadialGradient(QPointF(feet.x(), feet.y() + 2), w * 0.55)
        g.setColorAt(0, _c("#000000", 70))
        g.setColorAt(1, _c("#000000", 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(feet.x(), feet.y() + 2), w * 0.5, 7)
        p.translate(feet)
        if self.animated:
            p.scale(1.0, 1.0 + 0.008 * math.sin(self.t * 2.0))       # «дыхание»
        p.translate(0, -h * 0.05 * self._jump)                         # подпрыгивает, когда говорит
        p.translate(-feet.x(), -feet.y())
        p.drawPixmap(QPointF(x, y), pix)
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

    def configure(self, kind, animated, size, pose="auto"):
        self.kind = norm_kind(kind)
        self.painter.animated = animated
        self.painter.pose = pose or "auto"
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
        self.painter.tick(0.04, get_pack(self.kind))
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
            self.painter.tick(0.04, get_pack(self.kind))
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
        i0 = pack.pose_frames("idle")[0]
        fr = pack.scaled(i0, fh / max(1, pack.idle_h))
        p.drawPixmap(QPointF((w - fr.width()) / 2, h * 0.05), fr)
    else:
        p.setPen(QPen(_c("#FFFFFF", 90), 3))
        p.drawEllipse(QPointF(w / 2, h * 0.4), 26, 26)
        p.drawLine(QPointF(w / 2 - 18, h * 0.4 + 18), QPointF(w / 2 + 18, h * 0.4 - 18))
    p.end()
    return pix


# ------------------------------------------------------------------ окно «Позы»
class PoseDialog:
    """Сетка всех кадров персонажа: отмечаете, какие кадры — «стоит», «сидит», «лежит»."""

    def __new__(cls, parent, kind):
        from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                                       QScrollArea, QVBoxLayout, QWidget)
        from theme import button, label
        pack = get_pack(kind)
        dlg = QDialog(parent)
        dlg.setWindowTitle("Позы персонажа")
        dlg.resize(820, 640)
        dlg.setStyleSheet(f"QDialog {{ background: {T.BG}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.addWidget(label("Позы персонажа", 20))
        lay.addWidget(label("Выберите позу сверху и нажимайте на кадры, которые к ней относятся. "
                            "Синяя рамка — кадр в этой позе.", 13, role="muted", wrap=True))
        state = {"pose": "idle"}
        names = {"idle": "Стоит", "sit": "Сидит", "lie": "Лежит"}
        top = QHBoxLayout()
        pose_btns = {}
        for key, title in names.items():
            b = button(title, "ghost", 14)
            b.setCheckable(True)
            top.addWidget(b)
            pose_btns[key] = b
        top.addStretch(1)
        lay.addLayout(top)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(8)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        cells = []

        def refresh():
            for k, b in pose_btns.items():
                b.setChecked(k == state["pose"])
            for i, cell in cells:
                on = state["pose"] in pack.tags[i]
                cell.setStyleSheet(f"QPushButton {{ background: {T.SURFACE}; border-radius: 10px; "
                                   f"border: {'3px solid ' + T.ACCENT if on else '1px solid ' + T.LINE}; }}")

        def toggle(i):
            t = set(pack.tags[i])
            t ^= {state["pose"]}
            pack.set_tags(i, t)
            refresh()

        if pack is not None:
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QIcon
            for i, pix in enumerate(pack.frames):
                b = QPushButton()
                b.setFixedSize(112, 112)
                b.setIcon(QIcon(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                b.setIconSize(QSize(96, 96))
                b.clicked.connect(lambda _=False, i=i: toggle(i))
                grid.addWidget(b, i // 6, i % 6)
                cells.append((i, b))
        for key, b in pose_btns.items():
            b.clicked.connect(lambda _=False, k=key: (state.update(pose=k), refresh()))
        ok = button("Готово", "primary", 14)
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok, 0, Qt.AlignRight)
        refresh()
        return dlg
