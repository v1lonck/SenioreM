"""Чат с помощником: пишете вопрос — он отвечает сообщением (и голосом, если включено).
Можно прикреплять фото (кнопкой, Ctrl+V, перетаскиванием, снимком экрана), выбирать ИИ
и просить нарисовать картинку («нарисуй кота в космосе»)."""
import datetime
import os
import re
import time

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import theme as T
from theme import Backdrop, LogoMark, Toggle, button, field, font, label, window_controls

SUGGESTIONS = ["Кто такой Павел Дуров?", "Какая погода завтра?", "Курс доллара",
               "Расскажи анекдот", "Нарисуй кота в космосе", "Открой ютуб"]
AI_CHOICES = [("auto", "ИИ: сам выбирает"), ("fast", "ИИ: быстрый"), ("smart", "ИИ: умный"),
              ("local", "ИИ: на компьютере")]
DRAW_RX = re.compile(r"^(нарисуй|нарисуйте|сгенерируй|сгенерировать|создай картинку|создай изображение|"
                     r"сделай картинку|сделай изображение|изобрази|покажи картинку|сгенерь)\s*"
                     r"(мне\s+)?(картинку|изображение|фото|арт)?\s*(с\s+|про\s+)?(?P<p>.+)$", re.I)
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def save_image(src_path=None, qimage=None):
    """Картинку — в папку чата (уменьшенную до 1600 px). -> путь."""
    import config
    d = config.data_dir() / "chat_images"
    d.mkdir(parents=True, exist_ok=True)
    out = str(d / f"img_{int(time.time() * 1000)}.jpg")
    from PySide6.QtGui import QImage
    img = qimage if qimage is not None else QImage(src_path)
    if img.isNull():
        raise ValueError("не картинка")
    if max(img.width(), img.height()) > 1600:
        img = img.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    img.save(out, "JPG", 90)
    return out


class Thumb(QLabel):
    """Картинка в сообщении: нажатие открывает её в полном размере."""

    def __init__(self, path, side=300):
        super().__init__()
        self.path = path
        pix = QPixmap(path)
        if not pix.isNull():
            self.setPixmap(pix.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.setText("(картинка удалена)")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Открыть в полном размере")

    def mousePressEvent(self, e):
        try:
            os.startfile(self.path)          # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


class Typing(QWidget):
    """Три прыгающие точки — «помощник печатает»."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(60, 26)
        self._t = 0.0
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(60)

    def _tick(self):
        self._t += 0.06
        self.update()

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i in range(3):
            y = 13 - 4 * max(0.0, math.sin(self._t * 6 - i * 0.7))
            c = QColor(T.ACCENT_SOFT)
            c.setAlphaF(0.5 + 0.5 * max(0.0, math.sin(self._t * 6 - i * 0.7)))
            p.setBrush(c)
            p.drawEllipse(QPointF(14 + i * 16, y), 4.5, 4.5)


class Bubble(QWidget):
    def __init__(self, text, mine, when="", images=None):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        box = QFrame()
        box.setProperty("role", "bubble_me" if mine else "bubble_bot")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 11, 16, 10)
        bl.setSpacing(4)
        for pth in images or []:
            bl.addWidget(Thumb(pth))
        self.text = QLabel(text)
        self.text.setVisible(bool(text))
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text.setFont(font(15))
        self.text.setMaximumWidth(620)
        if mine:
            self.text.setStyleSheet("color: #0A0C10;")
        bl.addWidget(self.text)
        if when:
            t = label(when, 11, role="faint")
            if mine:
                t.setStyleSheet("color: rgba(10,12,16,0.55);")
            t.setAlignment(Qt.AlignRight)
            bl.addWidget(t)
        box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        if mine:
            row.addStretch(1)
            row.addWidget(box)
        else:
            row.addWidget(LogoMark(34, glow=False), 0, Qt.AlignTop)
            row.addWidget(box)
            row.addStretch(1)


class ChatScreen(Backdrop):
    back_requested = Signal()
    send_requested = Signal(str)
    send_images = Signal(str, object)     # текст и картинки — ИИ посмотрит на них
    draw_requested = Signal(str)          # «нарисуй …»

    def __init__(self, win):
        super().__init__(glows=((0.2, 0.2, 0.5), (0.9, 0.9, 0.45)))
        self.win = win
        self.settings = None
        self._typing = None
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 28)
        top = QHBoxLayout()
        back = button("Назад", "link", 15, QFont.Normal)
        import icons
        icons.set_icon(back, "back", 16, T.MUTED)
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addSpacing(18)
        self.title = label("Чат", 18, QFont.DemiBold)
        top.addWidget(self.title)
        top.addSpacing(18)
        self.ai_box = QComboBox()
        for key, title in AI_CHOICES:
            self.ai_box.addItem(title, key)
        self.ai_box.setToolTip("Какой ИИ отвечает в чате")
        self.ai_box.setFont(font(13))
        self.ai_box.setStyleSheet(
            f"QComboBox {{ background: {T.rgba('#FFFFFF', 0.05)}; border: 1px solid {T.LINE}; "
            f"border-radius: 10px; padding: 6px 12px; color: {T.TEXT}; }}"
            f"QComboBox QAbstractItemView {{ background: {T.SURFACE}; color: {T.TEXT}; "
            f"selection-background-color: {T.rgba(T.ACCENT, 0.3)}; }}")
        self.ai_box.currentIndexChanged.connect(self._ai_changed)
        top.addWidget(self.ai_box)
        top.addSpacing(12)
        self.usage = label("", 12, role="faint")
        self.usage.setToolTip("Сколько токенов облачного ИИ потрачено (лимиты — в профиле → «ИИ-собеседник»)")
        top.addWidget(self.usage)
        top.addStretch(1)
        top.addWidget(label("Озвучивать ответы", 13, role="muted"))
        top.addSpacing(10)
        self.t_speak = Toggle(False)
        self.t_speak.toggled.connect(self._speak_changed)
        top.addWidget(self.t_speak)
        top.addSpacing(18)
        clear = button("Очистить", "link", 13, QFont.Normal)
        clear.clicked.connect(self.clear)
        top.addWidget(clear)
        top.addSpacing(16)
        top.addLayout(window_controls(win))
        root.addLayout(top)
        root.addSpacing(16)

        body = QHBoxLayout()
        body.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list = QWidget()
        self.lay = QVBoxLayout(self.list)
        self.lay.setContentsMargins(4, 4, 14, 4)
        self.lay.setSpacing(14)
        self.lay.addStretch(1)
        self.scroll.setWidget(self.list)
        self.scroll.setMinimumWidth(820)
        self.scroll.setMaximumWidth(980)
        col.addWidget(self.scroll, 1)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        for sgt in SUGGESTIONS:
            b = button(sgt, "ghost", 13, QFont.Normal)
            b.clicked.connect(lambda _=False, q=sgt: self.send(q))
            self.chips.addWidget(b)
        self.chips.addStretch(1)
        col.addLayout(self.chips)

        # прикреплённые картинки (до отправки)
        self.pending = []
        self._pend_widgets = []
        self.pend_row = QHBoxLayout()
        self.pend_row.setSpacing(8)
        self.pend_box = QWidget()
        self.pend_box.setLayout(self.pend_row)
        self.pend_box.hide()
        col.addWidget(self.pend_box)

        inrow = QHBoxLayout()
        inrow.setSpacing(10)
        import icons as _ic
        for name, tip, fn in (("clip", "Прикрепить фото (или перетащите его сюда, или Ctrl+V)", self._pick_files),
                              ("screen", "Прикрепить снимок экрана", self._snap_screen),
                              ("brush", "Нарисовать картинку по описанию", self._draw_hint)):
            b = QPushButton()
            b.setProperty("role", "ghost")
            b.setFixedSize(46, 46)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            _ic.set_icon(b, name, 20, T.TEXT, 1.5)
            b.clicked.connect(fn)
            inrow.addWidget(b)
        self.input = field("Напишите сообщение… (фото — скрепка, Ctrl+V или перетащите)")
        self.input.setFont(font(16))
        self.input.returnPressed.connect(lambda: self.send(self.input.text()))
        self.input.installEventFilter(self)
        inrow.addWidget(self.input, 1)
        sendb = button("Отправить", "primary", 14)
        sendb.setFixedWidth(150)
        sendb.clicked.connect(lambda: self.send(self.input.text()))
        inrow.addWidget(sendb)
        col.addLayout(inrow)
        body.addLayout(col, 6)
        body.addStretch(1)
        root.addLayout(body, 1)
        self.setAcceptDrops(True)

    # ---------- данные ----------
    def load(self, settings, name):
        self.settings = None                      # чтобы переключатель не сохранял при загрузке
        self.t_speak.setChecked(bool(settings["chat_speak"]))
        self.settings = settings
        self.title.setText(f"Чат · {name}")
        self._clear_widgets()
        for m in (settings["chat"] or [])[-60:]:
            self._add(m.get("text", ""), m["me"], m.get("t", 0), save=False, images=m.get("img"))
        want = settings["chat_ai"] or "auto"
        for i in range(self.ai_box.count()):
            if self.ai_box.itemData(i) == want:
                self.ai_box.blockSignals(True)
                self.ai_box.setCurrentIndex(i)
                self.ai_box.blockSignals(False)
        self.refresh_usage()
        if not settings["chat"]:
            self._add(f"Привет! Я {name}. Спросите что угодно: кто такой Павел Дуров, какая "
                      f"погода завтра, курс доллара — или попросите что-то сделать на компьютере.",
                      False, save=False)
        QTimer.singleShot(50, self._scroll_down)
        self.input.setFocus()

    def _speak_changed(self, v):
        if self.settings is not None:
            self.settings.set("chat_speak", bool(v))

    def _clear_widgets(self):
        while self.lay.count() > 1:
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def clear(self):
        if self.settings is not None:
            self.settings.set("chat", [])
        self._clear_widgets()
        try:
            import ai
            ai.ENGINE.forget()
        except Exception:  # noqa: BLE001
            pass

    def _add(self, text, me, ts=0, save=True, images=None):
        ts = ts or datetime.datetime.now().timestamp()
        when = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
        images = [p for p in (images or []) if p]
        self.lay.insertWidget(self.lay.count() - 1, Bubble(text, me, when, images))
        if save and self.settings is not None:
            hist = list(self.settings["chat"] or [])
            item = {"text": text, "me": me, "t": int(ts)}
            if images:
                item["img"] = images
            hist.append(item)
            self.settings.set("chat", hist[-150:])
        QTimer.singleShot(30, self._scroll_down)

    def _scroll_down(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- отправка ----------
    def send(self, text):
        text = (text or "").strip()
        images = list(self.pending)
        if (not text and not images) or self._typing is not None:
            return
        self.input.clear()
        self._clear_pending()
        self._add(text, True, images=images)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(LogoMark(34, glow=False), 0, Qt.AlignTop)
        box = QFrame()
        box.setProperty("role", "bubble_bot")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.addWidget(Typing())
        rl.addWidget(box)
        rl.addStretch(1)
        self._typing = row
        self.lay.insertWidget(self.lay.count() - 1, row)
        QTimer.singleShot(30, self._scroll_down)
        m = DRAW_RX.match(text) if not images else None
        if m and m.group("p").strip():
            self.draw_requested.emit(m.group("p").strip())
        elif images:
            self.send_images.emit(text, images)
        else:
            self.send_requested.emit(text)

    def receive(self, reply, images=None):
        if self._typing is not None:
            self._typing.hide()
            self._typing.deleteLater()
            self._typing = None
        self._add(reply or ("" if images else "…"), False, images=images)
        self.refresh_usage()

    # ---------- выбор ИИ и расход токенов ----------
    def _ai_changed(self, _i):
        if self.settings is not None:
            self.settings.set("chat_ai", self.ai_box.currentData())

    def refresh_usage(self):
        try:
            import ai
            d = ai.usage_get()
            self.usage.setText(f"сегодня {ai.fmt_tokens(d['day_tokens'])} · за месяц "
                               f"{ai.fmt_tokens(d['month_tokens'])} токенов" if d["month_tokens"] else "")
        except Exception:  # noqa: BLE001
            self.usage.setText("")

    # ---------- картинки ----------
    def attach(self, path=None, qimage=None):
        if len(self.pending) >= 4:
            return
        try:
            p = save_image(path, qimage)
        except Exception:  # noqa: BLE001
            return
        self.pending.append(p)
        t = QWidget()
        tl = QHBoxLayout(t)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        tl.addWidget(Thumb(p, 72))
        x = QPushButton("×")
        x.setFixedSize(22, 22)
        x.setCursor(Qt.PointingHandCursor)
        x.setToolTip("Убрать")
        x.setStyleSheet(f"QPushButton {{ border: none; border-radius: 11px; color: {T.TEXT}; "
                        f"background: {T.rgba('#FFFFFF', 0.12)}; }}")
        x.clicked.connect(lambda _=False, w=t, pp=p: self._unattach(w, pp))
        tl.addWidget(x, 0, Qt.AlignTop)
        self.pend_row.addWidget(t)
        self._pend_widgets.append(t)
        self.pend_box.show()
        self.input.setFocus()

    def _unattach(self, w, p):
        if p in self.pending:
            self.pending.remove(p)
        if w in self._pend_widgets:
            self._pend_widgets.remove(w)
        w.hide()
        w.deleteLater()
        self.pend_box.setVisible(bool(self.pending))

    def _clear_pending(self):
        self.pending = []
        for w in self._pend_widgets:
            w.hide()
            w.deleteLater()
        self._pend_widgets = []
        self.pend_box.hide()

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Фото для помощника", "",
                                                "Картинки (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        for p in paths[:4]:
            self.attach(p)

    def _snap_screen(self):
        """Снимок экрана без окна SenioreM: прячем окно на мгновение."""
        w = self.window()
        w.hide()

        def grab():
            try:
                scr = QGuiApplication.primaryScreen()
                pix = scr.grabWindow(0)
                self.attach(qimage=pix.toImage())
            finally:
                w.show()
                w.raise_()
                w.activateWindow()
        QTimer.singleShot(450, grab)

    def _draw_hint(self):
        self.input.setText("Нарисуй ")
        self.input.setFocus()
        self.input.end(False)

    def eventFilter(self, obj, e):
        # Ctrl+V с картинкой в буфере — прикрепляем её
        if obj is self.input and e.type() == QEvent.KeyPress and e.key() == Qt.Key_V and \
                e.modifiers() & Qt.ControlModifier:
            cb = QGuiApplication.clipboard()
            md = cb.mimeData()
            if md is not None and md.hasImage():
                self.attach(qimage=cb.image())
                return True
            if md is not None and md.hasUrls():
                files = [u.toLocalFile() for u in md.urls() if u.toLocalFile().lower().endswith(IMG_EXT)]
                if files:
                    for f in files[:4]:
                        self.attach(f)
                    return True
        return super().eventFilter(obj, e)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasImage() or (md.hasUrls() and any(u.toLocalFile().lower().endswith(IMG_EXT)
                                                   for u in md.urls())):
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                if u.toLocalFile().lower().endswith(IMG_EXT):
                    self.attach(u.toLocalFile())
        elif md.hasImage():
            self.attach(qimage=md.imageData())
        e.acceptProposedAction()
