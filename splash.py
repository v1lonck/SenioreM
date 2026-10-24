"""Окно загрузки: название, что умеет программа, прогресс.
При первом запуске докачивает речевую модель (~45 МБ), затем загружает её в память."""
import math
import shutil
import time
import urllib.request
import zipfile

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt,
                            QThread, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

import config
from theme import ACCENT, BG, ERROR, LINE, TEXT, button, label, set_role

MIN_SHOW_SECONDS = 1.2

FEATURES = [
    ("01", "Звук и громкость", "«Сеньор, громкость десять»"),
    ("02", "Открыть и закрыть программы", "«Сеньор, закрой телеграм»"),
    ("03", "Поиск в интернете", "«Сеньор, найди погоду»"),
    ("04", "Музыка, время, скриншоты", "«Сеньор, который час»"),
]


def _is_ascii(p) -> bool:
    try:
        str(p).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def load_model(path):
    """Движок распознавания не открывает пути с русскими буквами (например, если
    имя пользователя Windows на кириллице). Поэтому грузим модель по относительному
    пути, а если не вышло — копируем её в папку с латинским путём."""
    import os
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    if _is_ascii(path):
        return Model(str(path))
    old = os.getcwd()
    try:
        os.chdir(path)
        return Model(".")
    except Exception:  # noqa: BLE001
        pass
    finally:
        os.chdir(old)
    root = os.environ.get("ProgramData") or "C:\\ProgramData"
    safe = config.Path(root) / "SenioreM" / "model"
    if not config.model_ready(safe):
        shutil.rmtree(safe, ignore_errors=True)
        safe.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(path, safe)
    return Model(str(safe))


def _log(text):
    try:
        with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


class Loader(QThread):
    """Готовит всё, что нужно для работы: распознавание речи и голос."""
    progress = Signal(float, str)
    loaded = Signal(object)      # {"model": vosk.Model | None, "voice": PiperVoice | None}
    failed = Signal(str)

    redownload = False   # после неудачной загрузки модель скачивается заново

    def run(self):
        import traceback

        import tts
        result = {"model": None, "voice": None}
        # ---- 1. распознавание речи
        try:
            path = config.model_dir()
            if Loader.redownload and path.parent == config.local_dir():
                shutil.rmtree(path, ignore_errors=True)
                Loader.redownload = False
            if not config.model_ready(path):
                self._download_model()
                path = config.model_dir()
        except Exception:  # noqa: BLE001
            _log(traceback.format_exc())
            self.failed.emit("Не удалось скачать распознавание речи. Проверьте интернет и нажмите "
                             "«Повторить».")
            return
        # ---- 2. голос (если не скачается — будет голос Windows)
        if not tts.voice_ready():
            try:
                self.progress.emit(0.46, "Первый запуск — скачиваю голос помощника")
                tts.download_voice(lambda d, t: self.progress.emit(
                    0.46 + 0.34 * min(1.0, d / max(t, 1)),
                    f"Первый запуск — скачиваю голос помощника · {d / 1e6:.0f} из {t / 1e6:.0f} МБ"))
            except Exception:  # noqa: BLE001
                _log("Голос не скачался:\n" + traceback.format_exc())
        # ---- 3. загрузка в память
        self.progress.emit(0.84, "Загружаю распознавание речи")
        try:
            result["model"] = load_model(path)
        except Exception:  # noqa: BLE001
            _log(f"model path: {path}\n" + traceback.format_exc())
            Loader.redownload = True
            self.failed.emit("Не удалось загрузить речевую модель. Нажмите «Повторить» — "
                             "она скачается заново.")
            return
        self.progress.emit(0.93, "Готовлю голос")
        if tts.voice_ready():
            try:
                result["voice"] = tts.load_voice()
            except Exception:  # noqa: BLE001
                _log("Голос не загрузился:\n" + traceback.format_exc())
        try:
            import sounddevice  # noqa: F401  — прогрев импорта
        except Exception:  # noqa: BLE001
            pass
        self.progress.emit(1.0, "Готово")
        self.loaded.emit(result)

    def _download_model(self):
        import tts
        root = config.local_dir()
        zpath = root / "model.zip"
        self.progress.emit(0.02, "Первый запуск — скачиваю распознавание речи")
        tts.download(config.model_urls(), zpath, lambda d, t: self.progress.emit(
            0.02 + 0.38 * min(1.0, d / max(t, 1)),
            f"Первый запуск — скачиваю распознавание речи · {d / 1e6:.0f} из {t / 1e6:.0f} МБ"),
            expect=45_000_000)
        self.progress.emit(0.42, "Распаковываю")
        tmp = root / "_unpack"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        inner = next((p for p in tmp.iterdir() if p.is_dir()), tmp)
        target = root / "model"
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(inner), str(target))
        shutil.rmtree(tmp, ignore_errors=True)
        zpath.unlink(missing_ok=True)
        if not config.model_ready(target):
            raise RuntimeError("архив модели повреждён")


def _version_tuple(v):
    out = []
    for part in str(v).lstrip("vV").split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


class UpdateChecker(QThread):
    """Проверяет на GitHub, нет ли версии новее установленной."""
    found = Signal(str, str)  # версия, ссылка на установщик

    def __init__(self, cfg):
        super().__init__()
        self.repo = cfg.get("update_repo") or ""
        self.version = cfg.get("version") or "0.0.0"

    def run(self):
        if not self.repo or self.version == "0.0.0":
            return
        try:
            import json
            req = urllib.request.Request(
                f"https://api.github.com/repos/{self.repo}/releases/latest",
                headers={"User-Agent": "SenioreM", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.load(r)
            latest = data.get("tag_name", "")
            if _version_tuple(latest) <= _version_tuple(self.version):
                return
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith("setup.exe"):
                    self.found.emit(latest.lstrip("vV"), asset["browser_download_url"])
                    return
        except Exception:  # noqa: BLE001 — нет интернета и т.п.: просто запускаемся
            pass


class Updater(QThread):
    progress = Signal(float, str)
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, url, version):
        super().__init__()
        self.url, self.version = url, version

    def run(self):
        import tempfile
        path = f"{tempfile.gettempdir()}\\SenioreM-Setup-{self.version}.exe"
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "SenioreM"})
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0) or 35_000_000
                done = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    self.progress.emit(min(1.0, done / total),
                                       f"Скачиваю обновление · {done / 1e6:.0f} из {total / 1e6:.0f} МБ")
            self.ready.emit(path)
        except Exception:  # noqa: BLE001
            self.failed.emit("Не удалось скачать обновление. Попробуйте позже.")


class Mark(QWidget):
    """Иконка программы с мягко «дышащим» свечением."""

    def __init__(self, size=150):
        super().__init__()
        self.setFixedSize(size, size)
        self._t = 0.0
        path = config.resource_path("assets/icon.png")
        self._pix = QPixmap(str(path)) if path.exists() else QPixmap()
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def _tick(self):
        self._t += 0.016
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = QPointF(self.width() / 2, self.height() / 2)
        b = (math.sin(self._t * 2.2) + 1) / 2
        glow = QColor(ACCENT)
        glow.setAlphaF(0.05 + 0.07 * b)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, self.width() * 0.5, self.width() * 0.5)
        if not self._pix.isNull():
            side = self.width() * 0.84
            p.drawPixmap(QRectF(c.x() - side / 2, c.y() - side / 2, side, side), self._pix,
                         QRectF(self._pix.rect()))
        else:
            p.setBrush(QColor(TEXT))
            p.drawEllipse(c, self.width() * 0.2, self.width() * 0.2)


class ProgressLine(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(3)
        self.target = 0.0
        self.value = 0.0
        self.color = ACCENT
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def _tick(self):
        self.value += (self.target - self.value) * 0.10
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(LINE))
        p.drawRoundedRect(QRectF(0, 0, w, h), 1.5, 1.5)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(0, 0, max(h, w * self.value), h), 1.5, 1.5)


class Splash(QWidget):
    done = Signal(object)      # {"model": ..., "voice": ...}
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("SenioreM")
        self.setFixedSize(860, 520)
        self._started = time.monotonic()
        self._loader = None
        self._hold = False          # ждём решения про обновление
        self._updating = False
        self._pending = ("none", None)
        self._checker = UpdateChecker(config.load_config())
        self._checker.found.connect(self._on_update_found)

        root = QVBoxLayout(self)
        root.setContentsMargins(56, 40, 32, 44)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.addStretch(1)
        close = button("✕", "chrome", 14, QFont.Normal)
        close.clicked.connect(self._cancel)
        top.addWidget(close)
        root.addLayout(top)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label("ГОЛОСОВОЙ ПОМОЩНИК ДЛЯ WINDOWS", 11, QFont.DemiBold, "accent", spacing=2.2))
        col.addSpacing(12)
        col.addWidget(label("SenioreM", 72, QFont.Light, display=True, spacing=-1.5))
        col.addSpacing(8)
        col.addWidget(label("Скажите «Сеньор» — остальное он сделает сам.", 18, QFont.Light,
                            "muted", display=True))
        head.addLayout(col, 1)
        head.addWidget(Mark(150), 0, Qt.AlignVCenter)
        head.addSpacing(24)
        root.addLayout(head)

        root.addSpacing(40)
        grid = QGridLayout()
        grid.setHorizontalSpacing(40)
        grid.setVerticalSpacing(22)
        for i, (num, title, example) in enumerate(FEATURES):
            cell = QHBoxLayout()
            cell.setSpacing(14)
            n = label(num, 12, QFont.DemiBold, "accent")
            n.setAlignment(Qt.AlignTop)
            cell.addWidget(n, 0, Qt.AlignTop)
            txt = QVBoxLayout()
            txt.setSpacing(3)
            txt.addWidget(label(title, 15, QFont.DemiBold))
            txt.addWidget(label(example, 13, role="faint"))
            cell.addLayout(txt, 1)
            grid.addLayout(cell, i // 2, i % 2)
        root.addLayout(grid)

        root.addStretch(1)
        self.update_row = QWidget()
        ur = QHBoxLayout(self.update_row)
        ur.setContentsMargins(0, 0, 24, 16)
        ur.setSpacing(20)
        self.update_lbl = label("", 14, QFont.DemiBold, "accent")
        ur.addWidget(self.update_lbl, 1)
        self.update_btn = button("Обновить", "primary", 14)
        self.update_btn.setFixedWidth(150)
        self.update_btn.clicked.connect(self._do_update)
        later = button("Позже", "link", 14, QFont.Normal)
        later.clicked.connect(self._skip_update)
        ur.addWidget(later)
        ur.addWidget(self.update_btn)
        self.update_row.hide()
        root.addWidget(self.update_row)
        status_row = QHBoxLayout()
        self.status = label("Запускаю", 13, role="muted")
        self.pct = label("0 %", 13, role="faint")
        status_row.addWidget(self.status, 1)
        ver = config.load_config().get("version", "")
        if ver and ver != "0.0.0":
            status_row.addWidget(label(f"версия {ver}", 12, role="faint"))
            status_row.addSpacing(16)
        status_row.addWidget(self.pct)
        status_row.addSpacing(24)
        root.addLayout(status_row)
        root.addSpacing(12)
        bar_row = QHBoxLayout()
        self.bar = ProgressLine()
        bar_row.addWidget(self.bar)
        bar_row.addSpacing(24)
        root.addLayout(bar_row)

        self.actions = QWidget()
        act = QHBoxLayout(self.actions)
        act.setContentsMargins(0, 18, 0, 0)
        act.setSpacing(24)
        retry = button("Повторить", "primary", 14)
        retry.setFixedWidth(160)
        retry.clicked.connect(self.start)
        skip = button("Продолжить без голоса", "link", 14, QFont.Normal)
        skip.clicked.connect(lambda: self._finish({"model": None, "voice": None}, force=True))
        act.addWidget(retry)
        act.addWidget(skip)
        act.addStretch(1)
        self.actions.hide()
        root.addWidget(self.actions)

        pct_timer = QTimer(self)
        pct_timer.timeout.connect(lambda: self.pct.setText(f"{round(self.bar.value * 100)} %"))
        pct_timer.start(50)

    # ---------- отрисовка панели ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(LINE), 1))
        p.setBrush(QColor(BG))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)

    def mousePressEvent(self, e):  # окно можно перетаскивать
        if e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    # ---------- жизненный цикл ----------
    def show_animated(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.setWindowOpacity(0.0)
        self.show()
        self._fade(1.0, 280)

    def _fade(self, to, ms, then=None):
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(ms)
        self._anim.setEndValue(to)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if then:
            self._anim.finished.connect(then)
        self._anim.start()

    def start(self):
        self.actions.hide()
        set_role(self.status, "muted")
        self.bar.color = ACCENT
        self.status.setText("Запускаю")
        self._loader = Loader()
        self._loader.progress.connect(self._on_progress)
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._loader.start()
        if not self._checker.isRunning() and not self._checker.isFinished():
            self._checker.start()

    # ---------- обновление ----------
    def _on_update_found(self, version, url):
        if not self.isVisible():
            return
        self._update = (version, url)
        self._hold = True
        self.update_lbl.setText(f"Доступна новая версия {version}")
        self.update_row.show()

    def _skip_update(self):
        self.update_row.hide()
        self._hold = False
        kind, model = self._pending
        if kind == "loaded":
            self._on_loaded(model)

    def _do_update(self):
        version, url = self._update
        self._updating = True
        self.update_row.hide()
        self.actions.hide()
        set_role(self.status, "muted")
        self.bar.color = ACCENT
        self.bar.value = self.bar.target = 0.0
        self._updater = Updater(url, version)
        self._updater.progress.connect(self._on_progress_update)
        self._updater.ready.connect(self._run_installer)
        self._updater.failed.connect(self._update_failed)
        self._updater.start()

    def _on_progress_update(self, frac, text):
        self.bar.target = frac
        self.status.setText(text)

    def _run_installer(self, path):
        import os
        import subprocess
        self.status.setText("Устанавливаю обновление — через несколько секунд SenioreM откроется снова")
        subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                          "/CLOSEAPPLICATIONS"])
        QTimer.singleShot(600, lambda: os._exit(0))

    def _update_failed(self, msg):
        self._updating = False
        self._hold = False
        self.status.setText(msg)
        kind, model = self._pending
        if kind == "loaded":
            QTimer.singleShot(1500, lambda: self._on_loaded(model))

    def _on_progress(self, frac, text):
        if self._updating:
            return
        self.bar.target = frac
        self.status.setText(text)

    def _on_failed(self, msg):
        if self._updating:
            return
        self.status.setText(msg)
        set_role(self.status, "error")
        self.bar.color = ERROR
        self.actions.show()

    def _on_loaded(self, model):
        self._pending = ("loaded", model)
        if self._hold or self._updating:
            return
        wait = max(0.0, MIN_SHOW_SECONDS - (time.monotonic() - self._started))
        QTimer.singleShot(int(wait * 1000), lambda: self._finish(model))

    def _finish(self, model, force=False):
        if getattr(self, "_finished", False):
            return
        if not force and (self._hold or self._updating):
            return
        self._finished = True
        self.bar.target = 1.0
        self.done.emit(model)
        self._fade(0.0, 260, self.close)

    def _cancel(self):
        self.cancelled.emit()
        self.close()
