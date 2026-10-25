"""Чат с помощником: пишете вопрос — он отвечает сообщением (и голосом, если включено)."""
import datetime

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

import theme as T
from theme import Backdrop, LogoMark, Toggle, button, field, font, label, window_controls

SUGGESTIONS = ["Кто такой Павел Дуров?", "Какая погода завтра?", "Курс доллара",
               "Расскажи анекдот", "Поставь таймер на 5 минут", "Открой ютуб"]


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
    def __init__(self, text, mine, when=""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        box = QFrame()
        box.setProperty("role", "bubble_me" if mine else "bubble_bot")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 11, 16, 10)
        bl.setSpacing(4)
        self.text = QLabel(text)
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

        inrow = QHBoxLayout()
        inrow.setSpacing(12)
        self.input = field("Напишите сообщение…")
        self.input.setFont(font(16))
        self.input.returnPressed.connect(lambda: self.send(self.input.text()))
        inrow.addWidget(self.input, 1)
        sendb = button("Отправить", "primary", 14)
        sendb.setFixedWidth(150)
        sendb.clicked.connect(lambda: self.send(self.input.text()))
        inrow.addWidget(sendb)
        col.addLayout(inrow)
        body.addLayout(col, 6)
        body.addStretch(1)
        root.addLayout(body, 1)

    # ---------- данные ----------
    def load(self, settings, name):
        self.settings = None                      # чтобы переключатель не сохранял при загрузке
        self.t_speak.setChecked(bool(settings["chat_speak"]))
        self.settings = settings
        self.title.setText(f"Чат · {name}")
        self._clear_widgets()
        for m in (settings["chat"] or [])[-60:]:
            self._add(m["text"], m["me"], m.get("t", 0), save=False)
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

    def _add(self, text, me, ts=0, save=True):
        ts = ts or datetime.datetime.now().timestamp()
        when = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
        self.lay.insertWidget(self.lay.count() - 1, Bubble(text, me, when))
        if save and self.settings is not None:
            hist = list(self.settings["chat"] or [])
            hist.append({"text": text, "me": me, "t": int(ts)})
            self.settings.set("chat", hist[-150:])
        QTimer.singleShot(30, self._scroll_down)

    def _scroll_down(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- отправка ----------
    def send(self, text):
        text = (text or "").strip()
        if not text or self._typing is not None:
            return
        self.input.clear()
        self._add(text, True)
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
        self.send_requested.emit(text)

    def receive(self, reply):
        if self._typing is not None:
            self._typing.hide()
            self._typing.deleteLater()
            self._typing = None
        self._add(reply or "…", False)
