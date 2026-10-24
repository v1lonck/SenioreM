"""Окно загрузки: название, что умеет программа, прогресс.
При первом запуске докачивает речевую модель (~45 МБ), затем загружает её в память."""
import math
import shutil
import time
import urllib.request
import zipfile

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt,
                            QThread, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

import config
from theme import ACCENT, BG, ERROR, LINE, TEXT, button, label, set_role

MIN_SHOW_SECONDS = 2.6

FEATURES = [
    ("01", "Звук и громкость", "«Сеньор, громкость десять»"),
    ("02", "Программы и сайты", "«Сеньор, открой браузер»"),
    ("03", "Поиск в интернете", "«Сеньор, найди погоду»"),
    ("04", "Музыка, время, скриншоты", "«Сеньор, который час»"),
]


class Loader(QThread):
    progress = Signal(float, str)
    loaded = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            path = config.model_dir()
            if not config.model_ready(path):
                self._download()
                path = config.model_dir()
            self.progress.emit(0.86, "Загружаю распознавание речи")
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            model = Model(str(path))
            self.progress.emit(0.95, "Готовлю голос")
            try:
                import edge_tts  # noqa: F401  — прогрев импорта
                import sounddevice  # noqa: F401
            except Exception:  # noqa: BLE001
                pass
            self.progress.emit(1.0, "Готово")
            self.loaded.emit(model)
        except OSError:
            self.failed.emit("Не удалось скачать речевую модель. Проверьте интернет и нажмите «Повторить».")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка загрузки: {e}")

    def _download(self):
        root = config.local_dir()
        zpath = root / "model.zip.part"
        self.progress.emit(0.02, "Первый запуск — скачиваю речевую модель")
        req = urllib.request.Request(config.MODEL_URL, headers={"User-Agent": "SenioreM"})
        with urllib.request.urlopen(req, timeout=30) as r, open(zpath, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0) or 45_000_000
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                frac = min(1.0, done / total)
                self.progress.emit(0.02 + 0.76 * frac,
                                   f"Первый запуск — скачиваю речевую модель · "
                                   f"{done / 1e6:.0f} из {total / 1e6:.0f} МБ")

        self.progress.emit(0.80, "Распаковываю")
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


class Mark(QWidget):
    """Знак программы: кольцо и «дышащая» точка."""

    def __init__(self, size=150):
        super().__init__()
        self.setFixedSize(size, size)
        self._t = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def _tick(self):
        self._t += 0.016
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = self.width() / 2 - 4
        b = (math.sin(self._t * 2.2) + 1) / 2
        p.setPen(QPen(QColor(ACCENT), 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R * 0.82, R * 0.82)
        halo = QColor(TEXT)
        halo.setAlphaF(0.06 + 0.08 * b)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        r = R * (0.30 + 0.04 * b)
        p.drawEllipse(c, r * 1.6, r * 1.6)
        p.setBrush(QColor(TEXT))
        p.drawEllipse(c, r, r)


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
    done = Signal(object)      # загруженная модель или None
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("SenioreM")
        self.setFixedSize(860, 520)
        self._started = time.monotonic()
        self._loader = None

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
        status_row = QHBoxLayout()
        self.status = label("Запускаю", 13, role="muted")
        self.pct = label("0 %", 13, role="faint")
        status_row.addWidget(self.status, 1)
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
        skip.clicked.connect(lambda: self._finish(None))
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

    def _on_progress(self, frac, text):
        self.bar.target = frac
        self.status.setText(text)

    def _on_failed(self, msg):
        self.status.setText(msg)
        set_role(self.status, "error")
        self.bar.color = ERROR
        self.actions.show()

    def _on_loaded(self, model):
        wait = max(0.0, MIN_SHOW_SECONDS - (time.monotonic() - self._started))
        QTimer.singleShot(int(wait * 1000), lambda: self._finish(model))

    def _finish(self, model):
        self.bar.target = 1.0
        self.done.emit(model)
        self._fade(0.0, 260, self.close)

    def _cancel(self):
        self.cancelled.emit()
        self.close()
