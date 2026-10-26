"""Чат с помощником: пишете вопрос — он отвечает сообщением (и голосом, если включено).
Можно прикреплять фото (кнопкой, Ctrl+V, перетаскиванием, снимком экрана), выбирать, какой ИИ
отвечает, и просить нарисовать картинку («нарисуй кота в космосе»)."""
import datetime
import os
import re
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import theme as T
from theme import Backdrop, LogoMark, Toggle, button, field, font, label, window_controls

SUGGESTIONS = ["Кто такой Павел Дуров?", "Какая погода завтра?", "Курс доллара",
               "Расскажи анекдот", "Нарисуй кота в космосе", "Открой ютуб"]
# какой ИИ отвечает: ключ, название, что умеет (подсказка под выбором)
AI_CHOICES = [
    ("auto", "Авто", "Сам выбирает: на простое — быстрый, на сложное — умный"),
    ("fast", "Быстрый", "DeepSeek V4 Flash · мгновенные короткие ответы"),
    ("smart", "Умный", "DeepSeek V4 Pro · подробные ответы, рассуждения, разбор фото"),
    ("code", "Код", "DeepSeek V4 Pro · пишет и объясняет программы"),
    ("draw", "Картинки", "FLUX · рисует картинку по вашему описанию"),
]
DRAW_RX = re.compile(r"^(нарисуй|нарисуйте|сгенерируй|сгенерировать|создай картинку|создай изображение|"
                     r"сделай картинку|сделай изображение|изобрази|покажи картинку|сгенерь)\s*"
                     r"(мне\s+)?(картинку|изображение|фото|арт)?\s*(с\s+|про\s+)?(?P<p>.+)$", re.I)
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def images_dir():
    import config
    d = config.data_dir() / "chat_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_image(src_path=None, qimage=None):
    """Картинку — в папку чата (уменьшенную до 1600 px). -> путь."""
    from PySide6.QtGui import QImage
    img = qimage if qimage is not None else QImage(src_path)
    if (img is None or img.isNull()) and src_path:
        img = _pil_qimage(src_path)
    if img is None or img.isNull():
        raise ValueError("не картинка")
    if max(img.width(), img.height()) > 1600:
        img = img.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    stem = images_dir() / f"img_{int(time.time() * 1000)}"
    out = f"{stem}.jpg"
    if not img.save(out, "JPG", 90):            # нет модуля JPEG — PNG есть всегда
        out = f"{stem}.png"
        if not img.save(out, "PNG"):
            raise OSError("не удалось сохранить картинку")
    return out


def _pil_qimage(path):
    """Запасной способ открыть картинку — через Pillow (если Qt не знает формат)."""
    try:
        from PIL import Image
        from PySide6.QtGui import QImage
        im = Image.open(path).convert("RGBA")
        data = im.tobytes("raw", "RGBA")
        q = QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888)
        return q.copy()
    except Exception:  # noqa: BLE001
        return None


def load_pixmap(path, side):
    pix = QPixmap(path)
    if pix.isNull() and path and os.path.isfile(path):
        q = _pil_qimage(path)
        if q is not None and not q.isNull():
            pix = QPixmap.fromImage(q)
    if pix.isNull():
        return None
    return pix.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class Thumb(QLabel):
    """Картинка в сообщении: нажатие открывает её в полном размере."""

    def __init__(self, path, side=300):
        super().__init__()
        self.path = path
        pix = load_pixmap(path, side)
        if pix is not None:
            self.setPixmap(pix)
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Открыть в полном размере")
        else:
            self.setText("Картинка не найдена")
            self.setFont(font(12))
            self.setProperty("role", "faint")

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._open()

    def _open(self):
        try:
            if os.path.isfile(self.path):
                os.startfile(self.path)          # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def contextMenuEvent(self, e):
        if not os.path.isfile(self.path):
            return
        m = _menu(self)
        m.addAction("Открыть", self._open)
        m.addAction("Копировать картинку", self._copy)
        m.addAction("Сохранить как…", self._save_as)
        m.addSeparator()
        m.addAction("Показать в папке", self._reveal)
        m.exec(e.globalPos())

    def _copy(self):
        from PySide6.QtGui import QImage
        img = QImage(self.path)
        if img.isNull():
            q = _pil_qimage(self.path)
            img = q if q is not None else img
        QGuiApplication.clipboard().setImage(img)

    def _save_as(self):
        import shutil
        ext = os.path.splitext(self.path)[1] or ".jpg"
        dst, _ = QFileDialog.getSaveFileName(self, "Сохранить картинку",
                                             os.path.join(os.path.expanduser("~"), "Pictures",
                                                          "SenioreM" + ext),
                                             f"Картинка (*{ext})")
        if dst:
            try:
                shutil.copyfile(self.path, dst)
            except OSError:
                pass

    def _reveal(self):
        import subprocess
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.path)])
        except OSError:
            pass


def _menu(parent):
    """Контекстное меню в стиле программы (по-русски, со скруглениями)."""
    from PySide6.QtWidgets import QMenu
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    m.setFont(font(14))
    return m


class BubbleText(QLabel):
    """Текст сообщения: выделяется мышью, правый клик — своё меню «Копировать»."""

    def contextMenuEvent(self, e):
        m = _menu(self)
        sel = self.selectedText()
        if sel:
            m.addAction("Копировать выделенное", lambda: QGuiApplication.clipboard().setText(sel))
        plain = self.text()
        if self.textFormat() == Qt.MarkdownText:
            from PySide6.QtGui import QTextDocument
            doc = QTextDocument()
            doc.setMarkdown(plain)
            plain = doc.toPlainText()
        m.addAction("Копировать сообщение", lambda: QGuiApplication.clipboard().setText(plain))
        codes = re.findall(r"```[^\n]*\n(.*?)```", self.text(), re.S)
        if codes:
            m.addAction("Копировать код", lambda: QGuiApplication.clipboard().setText("\n\n".join(codes).strip()))
        m.exec(e.globalPos())


class Typing(QWidget):
    """Три прыгающие точки — «помощник печатает» (и подпись, если ждать долго: «рисую…»)."""

    def __init__(self, text=""):
        super().__init__()
        self.text = text
        self.setFixedSize(60 + (len(text) * 8 + 10 if text else 0), 26)
        self._t = 0.0
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(33)

    def _tick(self):
        self._t += 0.033
        self.update()

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i in range(3):
            k = max(0.0, math.sin(self._t * 6 - i * 0.7))
            c = QColor(T.ACCENT_SOFT)
            c.setAlphaF(0.45 + 0.55 * k)
            p.setBrush(c)
            p.drawEllipse(QPointF(14 + i * 16, 13 - 4 * k), 4.5, 4.5)
        if self.text:
            p.setPen(QColor(T.MUTED))
            p.setFont(font(13))
            p.drawText(QRectF(60, 0, self.width() - 60, 26), Qt.AlignVCenter, self.text)


class LimitBar(QWidget):
    """Тонкая полоска: сколько облачного ИИ осталось на сегодня."""

    def __init__(self):
        super().__init__()
        self.frac = 0.0
        self.setFixedSize(150, 6)

    def set_frac(self, f):
        self.frac = max(0.0, min(1.0, f))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(r, 3, 3)
        if self.frac > 0:
            c = QColor(T.ACCENT) if self.frac > 0.2 else QColor("#F2A33A") if self.frac > 0.05 \
                else QColor("#E5484D")
            p.setBrush(c)
            p.drawRoundedRect(QRectF(0, 0, max(6.0, r.width() * self.frac), r.height()), 3, 3)


def _seg_qss():
    A = T.ACCENT
    return (f"QPushButton {{ background: transparent; color: {T.MUTED}; border: none; border-radius: 9px;"
            f" padding: 0 14px; min-height: 32px; }}"
            f"QPushButton:hover {{ color: {T.TEXT}; background: {T.rgba('#FFFFFF', 0.05)}; }}"
            f"QPushButton:checked {{ color: #FFFFFF; background: {T.rgba(A, 0.30)}; }}")


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
        bl.setSpacing(6)
        for pth in images or []:
            bl.addWidget(Thumb(pth))
        self.text = BubbleText()
        if not mine and any(m in text for m in ("**", "```", "\n- ", "\n1. ", "`", "\n#")):
            self.text.setTextFormat(Qt.MarkdownText)   # ответ ИИ с разметкой: списки, код, жирный
        else:
            self.text.setTextFormat(Qt.PlainText)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        self.text.setWordWrap(True)
        self.text.setOpenExternalLinks(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.text.setFont(font(15))
        self.text.setMaximumWidth(640)
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
        self._loaded_key = None
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 22, 24, 22)

        # ---- верх: назад · заголовок · озвучивать · очистить · окно
        top = QHBoxLayout()
        back = button("Назад", "link", 15, QFont.Normal)
        import icons
        icons.set_icon(back, "back", 16, T.MUTED)
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addSpacing(18)
        self.title = label("Чат", 18, QFont.DemiBold)
        top.addWidget(self.title)
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
        root.addSpacing(10)

        body = QHBoxLayout()
        body.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(12)

        # ---- какой ИИ отвечает + сколько осталось
        bar = QFrame()
        bar.setProperty("role", "card")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 16, 8)
        bl.setSpacing(4)
        self.ai_group = QButtonGroup(self)
        self.ai_group.setExclusive(True)
        self.ai_buttons = {}
        for key, title, desc in AI_CHOICES:
            b = QPushButton(title)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFont(font(13, QFont.DemiBold))
            b.setToolTip(desc)
            b.setStyleSheet(_seg_qss())
            T.click_feedback(b)
            b.clicked.connect(lambda _=False, k=key: self._ai_changed(k))
            self.ai_group.addButton(b)
            self.ai_buttons[key] = b
            bl.addWidget(b)
        bl.addSpacing(14)
        self.ai_desc = label("", 12, role="muted")
        bl.addWidget(self.ai_desc, 1)
        lim = QVBoxLayout()
        lim.setSpacing(5)
        self.limit_lbl = label("", 11, role="faint")
        self.limit_lbl.setAlignment(Qt.AlignRight)
        lim.addWidget(self.limit_lbl)
        self.limit_bar = LimitBar()
        lim.addWidget(self.limit_bar, 0, Qt.AlignRight)
        self.limit_box = QWidget()
        self.limit_box.setLayout(lim)
        self.limit_box.setToolTip("Сколько облачного ИИ осталось на сегодня. Лимиты одинаковые для всех "
                                  "и задаются владельцем SenioreM.")
        bl.addWidget(self.limit_box)
        bar.setMaximumWidth(980)
        col.addWidget(bar)

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
        self.pend_box = QWidget()
        self.pend_row = QHBoxLayout(self.pend_box)
        self.pend_row.setContentsMargins(0, 0, 0, 0)
        self.pend_row.setSpacing(8)
        self.pend_row.addStretch(1)
        self.pend_box.hide()
        col.addWidget(self.pend_box)

        # ---- ввод: фото · экран · нарисовать · поле · отправить
        inrow = QHBoxLayout()
        inrow.setSpacing(8)
        for name, text, tip, fn in (
                ("image", "Фото", "Прикрепить фото с компьютера (можно и перетащить его сюда или Ctrl+V)",
                 self._pick_files),
                ("screen", "Экран", "Прикрепить снимок экрана — ИИ посмотрит, что у вас открыто",
                 self._snap_screen),
                ("brush", "Нарисовать", "Нарисовать картинку по описанию", self._draw_hint)):
            b = button("  " + text, "ghost", 13, QFont.Normal)
            b.setFixedHeight(46)
            b.setToolTip(tip)
            icons.set_icon(b, name, 18, T.TEXT, 1.5)
            b.clicked.connect(fn)
            inrow.addWidget(b)
        inrow.addSpacing(4)
        self.input = field("Напишите сообщение…")
        self.input.setFont(font(16))
        self.input.returnPressed.connect(lambda: self.send(self.input.text()))
        self.input.installEventFilter(self)
        inrow.addWidget(self.input, 1)
        sendb = button("Отправить", "primary", 14)
        sendb.setFixedWidth(140)
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
        hist = (settings["chat"] or [])[-40:]
        key = (id(settings), len(settings["chat"] or []), hist[-1].get("t") if hist else 0)
        if key != self._loaded_key:               # история та же — не перестраиваем (быстрое открытие)
            self._loaded_key = key
            self.list.setUpdatesEnabled(False)
            self._clear_widgets()
            for m in hist:
                self._add(m.get("text", ""), m["me"], m.get("t", 0), save=False, images=m.get("img"))
            if not hist:
                self._add(f"Привет! Я {name}. Спросите что угодно, пришлите фото или попросите "
                          f"нарисовать картинку. Вверху можно выбрать, какой ИИ отвечает.",
                          False, save=False)
            self.list.setUpdatesEnabled(True)
        self._show_ai(settings["chat_ai"] or "auto")
        self.refresh_usage()
        QTimer.singleShot(0, self._scroll_down)
        QTimer.singleShot(120, self._scroll_down)
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
        self._loaded_key = None
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
            self._loaded_key = (id(self.settings), len(self.settings["chat"] or []), int(ts))
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
        mode = (self.settings["chat_ai"] if self.settings is not None else "") or "auto"
        m = DRAW_RX.match(text) if not images else None
        draw = (m.group("p").strip() if m and m.group("p").strip() else
                (text if mode == "draw" and not images else ""))
        self._show_typing("рисую…" if draw else ("смотрю фото…" if images else ""))
        if draw:
            self.draw_requested.emit(draw)
        elif images:
            self.send_images.emit(text, images)
        else:
            self.send_requested.emit(text)

    def _show_typing(self, text=""):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(LogoMark(34, glow=False), 0, Qt.AlignTop)
        box = QFrame()
        box.setProperty("role", "bubble_bot")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.addWidget(Typing(text))
        rl.addWidget(box)
        rl.addStretch(1)
        self._typing = row
        self.lay.insertWidget(self.lay.count() - 1, row)
        QTimer.singleShot(30, self._scroll_down)

    def partial(self, text):
        """Ответ пишется — показываем уже готовую часть вместо «печатает…»."""
        if self._typing is None or not text:
            return
        lbl = getattr(self._typing, "_partial_lbl", None)
        if lbl is None:
            box = self._typing.findChild(QFrame)
            if box is None:
                return
            lay = box.layout()
            while lay.count():
                it = lay.takeAt(0)
                if it.widget():
                    it.widget().hide()
                    it.widget().deleteLater()
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setFont(font(15))
            lbl.setMaximumWidth(640)
            lbl.setTextFormat(Qt.PlainText)
            lay.setContentsMargins(16, 11, 16, 10)
            lay.addWidget(lbl)
            self._typing._partial_lbl = lbl
        lbl.setText(text + " ▍")
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() - bar.value() < 120:
            QTimer.singleShot(20, self._scroll_down)

    def receive(self, reply, images=None):
        if self._typing is not None:
            self._typing.hide()
            self._typing.deleteLater()
            self._typing = None
        self._add(reply or ("" if images else "…"), False, images=images)
        self.refresh_usage()

    # ---------- выбор ИИ и лимит ----------
    def _ai_changed(self, key):
        if self.settings is not None:
            self.settings.set("chat_ai", key)
        self._show_ai(key)

    def _show_ai(self, key):
        if key not in self.ai_buttons:
            key = "auto"
        self.ai_buttons[key].setChecked(True)
        desc = dict((k, d) for k, _t, d in AI_CHOICES)[key]
        mode = (self.settings["ai_mode"] if self.settings is not None else "") or "smart"
        if mode not in ("cloud", "api") and key != "draw":
            desc = "ИИ на этом компьютере (облако выключено в профиле → «ИИ-собеседник»)"
        elif mode == "api" and key != "draw":
            desc = desc.split("·", 1)[-1].strip() + " · ваш сервер"
        self.ai_desc.setText(desc)

    def refresh_usage(self):
        try:
            import ai
            if not ai.limited(self.settings):
                self.limit_box.hide()
                return
            d = ai.usage_get()
            day, _month = ai.limits()
            left = max(0, day - int(d["day_tokens"]))
            self.limit_lbl.setText(f"осталось сегодня {round(100 * left / max(1, day))} %")
            self.limit_bar.set_frac(left / max(1, day))
            self.limit_box.show()
        except Exception:  # noqa: BLE001
            self.limit_box.hide()

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
        self.pend_row.insertWidget(self.pend_row.count() - 1, t)
        self._pend_widgets.append(t)
        self.pend_box.show()
        self.input.setFocus()
        if not self.input.text():
            self.input.setPlaceholderText("Что сделать с фото? (например: «что тут написано?»)")

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
        self.input.setPlaceholderText("Напишите сообщение…")

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Фото для помощника", os.path.expanduser("~"),
                                                "Картинки (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        for p in paths[:4]:
            self.attach(p)

    def _snap_screen(self):
        """Снимок экрана без окна SenioreM: окно на мгновение становится прозрачным
        (не прячем его — так не сбивается полноэкранный режим)."""
        w = self.window()
        if getattr(self, "_snapping", False):
            return
        self._snapping = True
        old = w.windowOpacity()
        w.setWindowOpacity(0.0)

        def grab():
            try:
                scr = w.screen() or QGuiApplication.primaryScreen()
                pix = scr.grabWindow(0)
                if not pix.isNull():
                    self.attach(qimage=pix.toImage())
            except Exception:  # noqa: BLE001
                pass
            finally:
                w.setWindowOpacity(old or 1.0)
                self._snapping = False
        QTimer.singleShot(350, grab)

    def _draw_hint(self):
        self._ai_changed("draw")
        self.input.setPlaceholderText("Опишите картинку: например, «кот-космонавт на Луне»")
        self.input.setFocus()

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
