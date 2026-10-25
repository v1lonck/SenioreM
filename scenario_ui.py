"""Раздел профиля «Сценарии»: свои фразы («игровой режим», «я дома») и VPN."""
import copy
import os
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout,
                               QWidget)

import scenarios
import sites
import theme as T
from theme import Toggle, button, card, field, label

STEP_BUTTONS = (("game", "+ Игра"), ("app", "+ Программа"), ("site", "+ Сайт"), ("command", "+ Команда"),
                ("vpn", "+ VPN"), ("click", "+ Нажать кнопку"), ("file", "+ Файл или скрипт"),
                ("wait", "+ Пауза"))


class _Bridge(QObject):
    tested = Signal(str, str)


# ------------------------------------------------------------------ выбор программы
class AppPicker(QDialog):
    """Окно выбора программы: поиск по названию среди всех программ, игр и скачанных папок."""

    def __init__(self, parent=None, title="Выберите программу"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(620, 640)
        self.setStyleSheet(f"QDialog {{ background: {T.BG}; }}")
        self.result_value = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(12)
        lay.addWidget(label(title, 20, QFont.DemiBold))
        lay.addWidget(label("Начните вводить название — по-русски или как пишется.", 13,
                            role="muted"))
        self.q = field("Поиск: стим, дискорд, запрет, hiddify…")
        self.q.textChanged.connect(self._fill)
        lay.addWidget(self.q)
        self.list = QListWidget()
        self.list.setStyleSheet(
            f"QListWidget {{ background: {T.SURFACE}; border: 1px solid {T.LINE}; border-radius: 12px;"
            f" padding: 6px; color: {T.TEXT}; font-size: 14px; }}"
            f"QListWidget::item {{ padding: 9px 10px; border-radius: 8px; }}"
            f"QListWidget::item:selected {{ background: {T.rgba(T.ACCENT, 0.25)}; }}"
            f"QListWidget::item:hover {{ background: {T.rgba('#FFFFFF', 0.06)}; }}")
        self.list.itemDoubleClicked.connect(lambda _i: self._ok())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        browse = button("Файл на компьютере…", "ghost", 13, QFont.Normal)
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        row.addStretch(1)
        cancel = button("Отмена", "ghost", 14, QFont.Normal)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = button("Выбрать", "primary", 14)
        ok.clicked.connect(self._ok)
        row.addWidget(ok)
        lay.addLayout(row)
        self.items = sites.all_targets()
        self._fill()
        self.q.setFocus()

    def _fill(self):
        self.list.clear()
        q = sites._norm(self.q.text())
        rows = self.items
        if q:
            keys = {k for k in sites._keys(q) if k}
            scored = []
            for name, tgt, src in self.items:
                n = sites._norm(name)
                sc = 1.0 if q in n else max((sites._score(k, n) for k in keys), default=0)
                if sc >= 0.6:
                    scored.append((-sc, name.lower(), (name, tgt, src)))
            rows = [x[2] for x in sorted(scored)]
        for name, tgt, src in rows[:400]:
            it = QListWidgetItem(f"{name}    ·  {src}")
            it.setData(Qt.UserRole, (name, list(tgt)))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите программу или скрипт", "",
                                              "Программы и скрипты (*.exe *.bat *.cmd *.lnk);;Все файлы (*)")
        if path:
            path = os.path.normpath(path)
            self.result_value = (os.path.splitext(os.path.basename(path))[0], ["path", path])
            self.accept()

    def _ok(self):
        it = self.list.currentItem()
        if it is None:
            return
        self.result_value = it.data(Qt.UserRole)
        self.accept()


def ask_text(parent, title, prompt, default=""):
    text, ok = QInputDialog.getText(parent, title, prompt, text=default)
    return text.strip() if ok else None


# ------------------------------------------------------------------ раздел
class ScenariosPage(QWidget):
    def __init__(self, profile):
        super().__init__()
        self.profile = profile
        self.settings = None
        self.data = []
        self._bridge = _Bridge()
        self._bridge.tested.connect(self._tested)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(0, 0, 16, 0)
        self.lay.setSpacing(0)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        profile._title(self.lay, "Сценарии",
                       "Своя фраза — и SenioreM делает всё сразу. Например, «игровой режим» "
                       "открывает Steam, Discord и обход блокировок, а «я дома» — Яндекс Музыку.")
        # ---- VPN
        self._build_vpn()
        self.lay.addSpacing(22)
        self._build_games()
        self.lay.addSpacing(26)
        self.lay.addWidget(label("ВАШИ СЦЕНАРИИ", 12, QFont.DemiBold, "muted", spacing=0.6))
        self.lay.addSpacing(10)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(16)
        self.lay.addLayout(self.list_box)
        self.lay.addSpacing(14)
        add = button("+ Новый сценарий", "ghost", 14)
        add.setFixedWidth(240)
        add.clicked.connect(self._add_scenario)
        self.lay.addWidget(add, 0, Qt.AlignLeft)
        self.lay.addStretch(1)

    # ---------- VPN
    def _build_vpn(self):
        box, bl = card((22, 18, 22, 18), 8)
        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("VPN по команде «включи впн»", 16, QFont.DemiBold))
        self.vpn_name = label("", 13, role="muted", wrap=True)
        col.addWidget(self.vpn_name)
        top.addLayout(col, 1)
        pick = button("Выбрать VPN…", "ghost", 13)
        pick.clicked.connect(self._pick_vpn)
        top.addWidget(pick, 0, Qt.AlignVCenter)
        bl.addLayout(top)
        bl.addSpacing(8)

        def trow(title, sub, key):
            r = QHBoxLayout()
            c = QVBoxLayout()
            c.setSpacing(2)
            c.addWidget(label(title, 14, QFont.DemiBold))
            if sub:
                c.addWidget(label(sub, 12, role="muted", wrap=True))
            r.addLayout(c, 1)
            t = Toggle()
            t.toggled.connect(lambda v, k=key: self._set_vpn(**{k: bool(v)}))
            r.addWidget(t, 0, Qt.AlignVCenter)
            bl.addLayout(r)
            bl.addSpacing(6)
            return t
        self.t_vpn_admin = trow("От имени администратора", "Многим VPN это нужно для работы.", "admin")
        self.t_vpn_click = trow("Сразу нажимать «Подключить»",
                                "SenioreM найдёт кнопку подключения и нажмёт её сам.", "click")
        self.f_vpn_button = field("Текст кнопки, если не «Подключить» (например: Connect, ВКЛ)")
        self.f_vpn_button.editingFinished.connect(
            lambda: self._set_vpn(button=self.f_vpn_button.text().strip()))
        bl.addWidget(self.f_vpn_button)
        bl.addSpacing(4)
        bl.addWidget(label("Скажите: «Сеньор, включи впн» или «выключи впн». Чтобы SenioreM мог нажимать "
                           "кнопки в VPN от администратора, включите «Работать с правами "
                           "администратора» в разделе «Запуск».", 12, role="faint", wrap=True))
        self.lay.addWidget(box)

    def _build_games(self):
        box, bl = card((22, 18, 22, 18), 8)
        head = QHBoxLayout()
        self.games_title = label("Ваши игры", 16, QFont.DemiBold)
        head.addWidget(self.games_title, 1)
        bl.addLayout(head)
        bl.addWidget(label("Нажмите, чтобы запустить. Голосом: «Сеньор, открой …». Добавить игру в "
                           "сценарий — кнопка «+ Игра» в сценарии.", 12, role="muted", wrap=True))
        bl.addSpacing(6)
        self.games_grid = QGridLayout()
        self.games_grid.setHorizontalSpacing(8)
        self.games_grid.setVerticalSpacing(8)
        bl.addLayout(self.games_grid)
        self.lay.addWidget(box)

    def _fill_games(self):
        while self.games_grid.count():
            it = self.games_grid.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        found = sites.games()
        self.games_title.setText(f"Ваши игры · {len(found)}" if found else "Ваши игры")
        if not found:
            self.games_grid.addWidget(label("Игры не найдены. Если игра установлена — нажмите "
                                            "«Обновить список» в разделе «Программы и игры».", 13,
                                            role="faint", wrap=True), 0, 0)
            return
        for k, (name, tgt, src) in enumerate(found[:60]):
            b = button(name if len(name) <= 26 else name[:25] + "…", "ghost", 13, QFont.Normal)
            b.setToolTip(f"{name} · {src}")
            b.clicked.connect(lambda _=False, n=name, t=tgt: self._run_game(n, t))
            self.games_grid.addWidget(b, k // 3, k % 3)

    def _run_game(self, name, tgt):
        def work():
            try:
                import actions
                actions._start((name, tuple(tgt)), "игры в настройках")
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=work, daemon=True).start()
        self.profile._flash(f"Запускаю {name}")

    def _vpn(self):
        return dict(self.settings["vpn"] or {}) if self.settings is not None else {}

    def _set_vpn(self, **changes):
        if self.settings is None or getattr(self, "_loading", False):
            return
        v = self._vpn()
        v.update(changes)
        self.settings.set("vpn", v)
        self._refresh_vpn()
        self.profile._flash()

    def _pick_vpn(self):
        dlg = AppPicker(self, "Какой VPN включать")
        vpns = [x for x in dlg.items if scenarios.is_vpn(x[0]) or
                (x[1][0] in ("path", "lnk") and scenarios.is_vpn(os.path.basename(x[1][1])))]
        dlg.items = vpns
        dlg._fill()
        if not vpns:
            dlg.list.addItem("VPN на компьютере не найден — выберите файл кнопкой «Файл на компьютере…»")
        if dlg.exec() and dlg.result_value:
            name, tgt = dlg.result_value
            self._set_vpn(app={"name": name, "target": tgt})

    def _refresh_vpn(self):
        v = self._vpn()
        self._loading = True
        if v.get("app"):
            self.vpn_name.setText(f"Включаю: {v['app']['name']}")
        else:
            name, _t = (None, None)
            try:
                name, _t = scenarios.pick_vpn({})
            except Exception:  # noqa: BLE001
                pass
            self.vpn_name.setText(f"Последний открытый: {name}" if name else
                                  "VPN не выбран — нажмите «Выбрать VPN…» или откройте VPN голосом один раз.")
        self.t_vpn_admin.setChecked(bool(v.get("admin", True)))
        self.t_vpn_click.setChecked(bool(v.get("click", True)))
        self.f_vpn_button.setText(v.get("button", ""))
        self._loading = False

    # ---------- сценарии
    def load(self, settings):
        self.settings = settings
        self.data = copy.deepcopy(scenarios.get(settings))
        self._refresh_vpn()
        self._fill_games()
        self._render()

    def _save(self):
        if self.settings is not None:
            self.settings.set("scenarios", copy.deepcopy(self.data))
            self.profile._flash()

    def _render(self):
        while self.list_box.count():
            it = self.list_box.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for i, sc in enumerate(self.data):
            self.list_box.addWidget(self._card(i, sc))

    def _card(self, i, sc):
        box, bl = card((22, 18, 22, 18), 8)
        head = QHBoxLayout()
        name = field("Название")
        name.setText(sc.get("name", ""))
        name.setFont(T.font(16, QFont.DemiBold))
        name.editingFinished.connect(lambda i=i, w=name: self._set(i, name=w.text().strip() or "Сценарий"))
        head.addWidget(name, 1)
        test = button("▶  Проверить", "ghost", 13)
        test.clicked.connect(lambda _=False, i=i: self._test(i))
        head.addWidget(test)
        rm = button("Удалить", "link", 13, QFont.Normal)
        rm.clicked.connect(lambda _=False, i=i: self._remove(i))
        head.addWidget(rm)
        bl.addLayout(head)
        bl.addWidget(label("Фразы (через запятую):", 12, role="muted"))
        ph = field("например: игровой режим, давай поиграем")
        ph.setText(", ".join(sc.get("phrases") or []))
        ph.editingFinished.connect(lambda i=i, w=ph: self._set(
            i, phrases=[x.strip() for x in w.text().split(",") if x.strip()]))
        bl.addWidget(ph)
        bl.addSpacing(6)
        steps = sc.get("steps") or []
        if not steps:
            bl.addWidget(label("Пока ничего не делает — добавьте шаги кнопками ниже.", 13,
                               role="faint"))
        for j, st in enumerate(steps):
            bl.addWidget(self._step_row(i, j, st))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for k, (kind, title) in enumerate(STEP_BUTTONS):
            b = button(title, "ghost", 12, QFont.Normal)
            b.clicked.connect(lambda _=False, i=i, kind=kind: self._add_step(i, kind))
            grid.addWidget(b, k // 4, k % 4)
        bl.addSpacing(6)
        bl.addLayout(grid)
        st = label("", 12, role="accent", wrap=True)
        st.setObjectName(f"status{i}")
        bl.addWidget(st)
        box.setProperty("scenario_index", i)
        box._status = st
        return box

    def _describe(self, st):
        k = st.get("type")
        if k == "app":
            return f"Открыть «{st.get('name', '?')}»"
        if k == "file":
            return f"Запустить «{st.get('name') or os.path.basename(st.get('path', ''))}»"
        if k == "site":
            return f"Сайт {st.get('url', '')}"
        if k == "command":
            return f"Команда «{st.get('text', '')}»"
        if k == "click":
            return f"Нажать кнопку «{st.get('text', '')}»"
        if k == "vpn":
            return "Включить VPN и подключиться"
        if k == "wait":
            return f"Подождать {st.get('seconds', 2)} с"
        return k

    def _step_row(self, i, j, st):
        row = QFrame()
        row.setProperty("role", "option")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 10, 8)
        rl.addWidget(label(f"{j + 1}.", 13, QFont.DemiBold, "accent"))
        rl.addWidget(label(self._describe(st), 14), 1)
        if st.get("type") in ("app", "file"):
            rl.addWidget(label("от админа", 12, role="muted"))
            t = Toggle(bool(st.get("admin")))
            t.toggled.connect(lambda v, i=i, j=j: self._set_step(i, j, admin=bool(v)))
            rl.addWidget(t)
        up = button("↑", "link", 14, QFont.Normal)
        up.setFixedWidth(28)
        up.clicked.connect(lambda _=False, i=i, j=j: self._move(i, j, -1))
        rl.addWidget(up)
        x = button("✕", "link", 14, QFont.Normal)
        x.setFixedWidth(28)
        x.clicked.connect(lambda _=False, i=i, j=j: self._del_step(i, j))
        rl.addWidget(x)
        return row

    # ---------- изменения
    def _set(self, i, **changes):
        self.data[i].update(changes)
        self._save()

    def _set_step(self, i, j, **changes):
        self.data[i]["steps"][j].update(changes)
        self._save()

    def _move(self, i, j, d):
        steps = self.data[i]["steps"]
        k = j + d
        if 0 <= k < len(steps):
            steps[j], steps[k] = steps[k], steps[j]
            self._save()
            self._render()

    def _del_step(self, i, j):
        del self.data[i]["steps"][j]
        self._save()
        self._render()

    def _remove(self, i):
        del self.data[i]
        self._save()
        self._render()

    def _add_scenario(self):
        self.data.append({"id": scenarios.new_id(), "name": "Новый сценарий", "phrases": [],
                          "steps": []})
        self._save()
        self._render()

    def _add_step(self, i, kind):
        st = None
        if kind == "game":
            dlg = AppPicker(self, "Выберите игру")
            dlg.items = sites.games()
            dlg._fill()
            if dlg.exec() and dlg.result_value:
                name, tgt = dlg.result_value
                st = {"type": "app", "name": name, "target": tgt, "admin": False}
        elif kind == "app":
            dlg = AppPicker(self)
            if dlg.exec() and dlg.result_value:
                name, tgt = dlg.result_value
                bat = tgt[0] == "path" and tgt[1].lower().endswith((".bat", ".cmd"))
                st = {"type": "app", "name": name, "target": tgt,
                      "admin": bat or scenarios.is_vpn(name) or "zapret" in name.lower()}
        elif kind == "file":
            path, _ = QFileDialog.getOpenFileName(self, "Файл или скрипт", "",
                                                  "Программы и скрипты (*.exe *.bat *.cmd *.lnk);;Все файлы (*)")
            if path:
                path = os.path.normpath(path)
                st = {"type": "file", "name": os.path.basename(path), "path": path,
                      "admin": path.lower().endswith((".bat", ".cmd"))}
        elif kind == "site":
            url = ask_text(self, "Сайт", "Адрес сайта (например, music.yandex.ru):")
            if url:
                if not url.startswith("http"):
                    url = "https://" + url
                st = {"type": "site", "url": url}
        elif kind == "command":
            text = ask_text(self, "Команда", "Что сказать SenioreM (например: громкость 30, "
                                             "открой телеграм, включи на ютубе лофи):")
            if text:
                st = {"type": "command", "text": text}
        elif kind == "click":
            text = ask_text(self, "Нажать кнопку", "Текст на кнопке в последнем открытом окне "
                                                   "(например: Подключить, Играть):")
            if text:
                st = {"type": "click", "text": text, "wait": 15}
        elif kind == "vpn":
            st = {"type": "vpn"}
        elif kind == "wait":
            sec = ask_text(self, "Пауза", "Сколько секунд подождать:", "3")
            if sec:
                try:
                    st = {"type": "wait", "seconds": max(1, min(60, float(sec.replace(",", "."))))}
                except ValueError:
                    pass
        if st:
            self.data[i].setdefault("steps", []).append(st)
            self._save()
            self._render()

    def _test(self, i):
        sc = copy.deepcopy(self.data[i])
        vcfg = self._vpn()
        self._status(i, "Выполняю…")

        def work():
            try:
                res = scenarios.run({"action": "scenario", "scenario": sc, "vpn": vcfg}, {})
            except Exception as e:  # noqa: BLE001
                res = f"Ошибка: {e}"
            self._bridge.tested.emit(str(i), res)
        threading.Thread(target=work, daemon=True).start()

    def _status(self, i, text):
        for k in range(self.list_box.count()):
            w = self.list_box.itemAt(k).widget()
            if w is not None and w.property("scenario_index") == i:
                w._status.setText(text)

    def _tested(self, i, text):
        self._status(int(i), text)
