"""Окно загрузки: название, что умеет программа, прогресс.
При первом запуске докачивает речевую модель (~45 МБ), затем загружает её в память."""
import os
import shutil
import time
import urllib.error
import urllib.request
import zipfile

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt,
                            QThread, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

import config
import theme as T
from theme import button, label, set_role

MIN_SHOW_SECONDS = 1.2

FEATURES = [
    ("01", "Звук и громкость", "«Сеньор, громкость десять»"),
    ("02", "Игры и программы", "«Сеньор, открой доту»"),
    ("03", "Разговор с ИИ", "«Сеньор, расскажи анекдот»"),
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
        # папку для загрузок выбрали в установщике — переносим туда уже скачанное
        try:
            err = config.apply_pending_move(lambda t: self.progress.emit(0.02, t))
            if err:
                _log(err)
        except Exception:  # noqa: BLE001
            _log(traceback.format_exc())
        # голос качаем параллельно с речевой моделью — первый запуск заметно быстрее
        voice_thread = None
        if not tts.voice_ready():
            import threading

            def get_voice():
                try:
                    tts.download_voice()
                except Exception:  # noqa: BLE001
                    _log("Голос не скачался:\n" + traceback.format_exc())
            voice_thread = threading.Thread(target=get_voice, daemon=True)
            voice_thread.start()
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
        if voice_thread is not None and voice_thread.is_alive():
            self.progress.emit(0.6, "Первый запуск — докачиваю голос помощника")
            voice_thread.join(600)
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
                    url = asset["browser_download_url"]
                    # только с GitHub этого же проекта
                    if not url.startswith(f"https://github.com/{self.repo}/releases/download/"):
                        return
                    self.found.emit(latest.lstrip("vV"), url)
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
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    self.progress.emit(min(1.0, done / total),
                                       f"Скачиваю обновление · {done / 1e6:.0f} из {total / 1e6:.0f} МБ")
            if not self._verify(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
                self.failed.emit("Обновление скачалось с ошибкой (не совпала контрольная сумма). "
                                 "Попробуйте позже.")
                return
            self.ready.emit(path)
        except Exception:  # noqa: BLE001
            self.failed.emit("Не удалось скачать обновление. Попробуйте позже.")

    def _verify(self, path):
        """Сверяем SHA-256 установщика с суммой, опубликованной в том же релизе."""
        import hashlib
        try:
            req = urllib.request.Request(self.url + ".sha256", headers={"User-Agent": "SenioreM"})
            with urllib.request.urlopen(req, timeout=20) as r:
                want = r.read().decode("ascii", "ignore").strip().lower()[:64]
        except urllib.error.HTTPError as e:
            return e.code == 404          # у старых версий суммы нет — не блокируем
        except Exception:  # noqa: BLE001
            return False
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest() == want


class Mark(QWidget):
    """Иконка программы с ровным неподвижным свечением (без пульсации — она «мигала»,
    когда компьютер занят загрузкой)."""

    def __init__(self, size=150):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = QPointF(self.width() / 2, self.height() / 2)
        glow = QColor(T.ACCENT)
        glow.setAlphaF(0.09)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, self.width() * 0.5, self.width() * 0.5)
        side = self.width() * 0.84
        T.draw_logo(p, QRectF(c.x() - side / 2, c.y() - side / 2, side, side))


class ProgressLine(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(3)
        self.target = 0.0
        self.value = 0.0
        self.color = T.ACCENT
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
        p.setBrush(QColor(T.LINE))
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
        from icons import ChromeButton
        close = ChromeButton("close", "Закрыть")
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
        self.features = QWidget()
        grid = QGridLayout(self.features)
        grid.setContentsMargins(0, 0, 0, 0)
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
        root.addWidget(self.features)

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
        # первый запуск: куда скачивать речь, голос и ИИ
        self.store_row = QWidget()
        sr = QVBoxLayout(self.store_row)
        sr.setContentsMargins(0, 0, 24, 16)
        sr.setSpacing(8)
        self.store_lbl = label("", 15, QFont.DemiBold, wrap=True)
        sr.addWidget(self.store_lbl)
        self.store_err = label("", 12, role="error", wrap=True)
        self.store_err.hide()
        sr.addWidget(self.store_err)
        sb = QHBoxLayout()
        sb.setSpacing(14)
        sb.addStretch(1)
        other = button("Выбрать другую папку…", "ghost", 14, QFont.Normal)
        other.clicked.connect(self._pick_storage)
        sb.addWidget(other)
        here = button("Скачать сюда", "primary", 14)
        here.setFixedWidth(190)
        here.clicked.connect(self._storage_ok)
        sb.addWidget(here)
        sr.addLayout(sb)
        self.store_row.hide()
        root.addWidget(self.store_row)
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
        p.setPen(QPen(QColor(T.LINE), 1))
        p.setBrush(QColor(T.BG))
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

    # ---------- папка для загрузок (первый запуск) ----------
    def _show_storage(self, path, err=""):
        self._store_path = str(path)
        free = config.free_gb(path)
        self.store_lbl.setText(
            f"Распознавание речи, голос и ИИ (около {config.STORAGE_NEED_GB:.1f} ГБ) скачаются в папку\n"
            f"{path}   ·   свободно {free:.0f} ГБ")
        self.store_err.setText(err)
        self.store_err.setVisible(bool(err))
        self.features.hide()                # освобождаем место под выбор папки
        self.store_row.show()
        self.status.setText("Выберите, куда скачивать — потом это можно поменять в профиле → «Запуск»")

    def _pick_storage(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Куда скачивать распознавание речи, голос и ИИ",
                                             self._store_path)
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.basename(d).lower() != "seniorem":
            d = os.path.join(d, "SenioreM")
        err = config.check_storage_path(d)
        if not err and config.free_gb(d) < config.STORAGE_NEED_GB:
            err = f"На этом диске меньше {config.STORAGE_NEED_GB:.1f} ГБ свободного места."
        self._show_storage(d if not err else self._store_path, err)

    def _storage_ok(self):
        err = config.set_storage(self._store_path)
        if err:
            self._show_storage(self._store_path, err)
            return
        self.store_row.hide()
        self.features.show()
        self.start()

    def start(self):
        if not config.storage_chosen() and not config.model_ready(config.model_dir()):
            self._show_storage(config.local_dir())
            if not self._checker.isRunning() and not self._checker.isFinished():
                self._checker.start()
            return
        self.actions.hide()
        set_role(self.status, "muted")
        self.bar.color = T.ACCENT
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
        self.bar.color = T.ACCENT
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
        self._mark("ставлю обновление — программа закроется и откроется снова")
        self.status.setText("Устанавливаю обновление — через несколько секунд SenioreM откроется снова")
        try:
            import ai
            ai.ENGINE.stop()
        except Exception:  # noqa: BLE001
            pass
        import updater
        updater.run(path)   # установщик заменит файлы и SenioreM откроется снова

    def _update_failed(self, msg):
        self._updating = False
        self._hold = False
        self.status.setText(msg)
        kind, model = self._pending
        if kind == "loaded":
            QTimer.singleShot(1500, lambda: self._on_loaded(model))

    def _mark(self, text):
        config.startup_mark("загрузка: " + text)

    def _on_progress(self, frac, text):
        if text != getattr(self, "_last_mark", ""):
            self._last_mark = text
            self._mark(text)
        if self._updating:
            return
        self.bar.target = frac
        self.status.setText(text)

    def _on_failed(self, msg):
        self._mark("ОШИБКА: " + msg)
        if self._updating:
            return
        self.status.setText(msg)
        set_role(self.status, "error")
        self.bar.color = T.ERROR
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
        self._mark("закрыто крестиком на окне загрузки")
        self.cancelled.emit()
        self.close()
