"""Управление открытыми программами и играми голосом:
«нажми пробел», «нажми на да», «кликни», «включи первое видео», «включи на ютубе котиков»,
«перемотай вперёд», «на весь экран».

Как это работает:
* клавиши отправляются в окно, которое было открыто перед SenioreM (игра, браузер);
* «нажми на <текст>» ищет кнопку с таким текстом через специальные возможности Windows
  (UI Automation), а если это игра и кнопок там нет — распознаёт текст на экране встроенным
  в Windows распознаванием (OCR) и нажимает мышкой в это место;
* YouTube: адрес открытой страницы читается из браузера, список видео берётся с сайта."""
import ctypes
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

NO_WINDOW = 0x08000000

KEYS = {
    "пробел": 0x20, "space": 0x20, "спейс": 0x20, "энтер": 0x0D, "enter": 0x0D, "ввод": 0x0D,
    "интер": 0x0D, "эскейп": 0x1B, "escape": 0x1B, "esc": 0x1B, "эскейт": 0x1B, "таб": 0x09,
    "tab": 0x09, "шифт": 0x10, "shift": 0x10, "контрл": 0x11, "ctrl": 0x11, "контрол": 0x11,
    "альт": 0x12, "alt": 0x12, "бэкспейс": 0x08, "backspace": 0x08, "удалить": 0x2E, "делит": 0x2E,
    "delete": 0x2E, "вверх": 0x26, "вниз": 0x28, "влево": 0x25, "вправо": 0x27,
    "стрелку вверх": 0x26, "стрелку вниз": 0x28, "стрелку влево": 0x25, "стрелку вправо": 0x27,
    "стрелка вверх": 0x26, "стрелка вниз": 0x28, "стрелка влево": 0x25, "стрелка вправо": 0x27,
    "home": 0x24, "end": 0x23, "пейдж ап": 0x21, "пейдж даун": 0x22,
}
# буквы, как их произносят: «нажми вэ», «нажми дабл ю», «нажми е»
LETTER_NAMES = {
    "а": "A", "эй": "A", "би": "B", "бэ": "B", "си": "C", "ди": "D", "дэ": "D", "и": "E", "е": "E",
    "эф": "F", "джи": "G", "эйч": "H", "ай": "I", "джей": "J", "кей": "K", "ка": "K", "эл": "L",
    "эм": "M", "эн": "N", "о": "O", "пи": "P", "пэ": "P", "кью": "Q", "ар": "R", "эр": "R", "эс": "S",
    "ти": "T", "тэ": "T", "ю": "U", "у": "U", "ви": "V", "вэ": "V", "дабл ю": "W", "дабл": "W",
    "икс": "X", "уай": "Y", "игрек": "Y", "зет": "Z", "зэт": "Z",
    # одна русская буква, похожая на латинскую
    "с": "C", "к": "K", "м": "M", "т": "T", "р": "R", "х": "X", "з": "Z", "в": "V", "д": "D",
    "ф": "F", "г": "G", "л": "L", "п": "P", "н": "N", "б": "B", "ш": "W", "ж": "J", "й": "Q",
}
NUM_WORDS = {"один": 1, "одну": 1, "раз": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
             "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "ноль": 0}
ORDINALS = {"первое": 1, "первый": 1, "1": 1, "второе": 2, "второй": 2, "2": 2, "третье": 3,
            "третий": 3, "3": 3, "четвертое": 4, "четвертый": 4, "4": 4, "пятое": 5, "пятый": 5,
            "5": 5, "шестое": 6, "седьмое": 7, "восьмое": 8, "девятое": 9, "десятое": 10,
            "первую": 1, "первая": 1, "вторую": 2, "вторая": 2, "третью": 3, "третья": 3,
            "четвертую": 4, "четвертая": 4, "пятую": 5, "пятая": 5, "шестую": 6, "шестой": 6,
            "седьмую": 7, "восьмую": 8, "девятую": 9, "десятую": 10}
YT_KEYS = {"forward": ("L", "Перематываю вперёд."), "back": ("J", "Перематываю назад."),
           "full": ("F", "Готово."), "subs": ("C", "Готово."), "mute": ("M", "Готово."),
           "next": ("SHIFT+N", "Следующее видео."), "prev": ("SHIFT+P", "Предыдущее видео."),
           "pause": ("K", "Готово."), "theatre": ("T", "Готово.")}


# ------------------------------------------------------------------ разбор фраз
def _norm(text):
    import commands
    return commands.normalize(text)


# ------------------------------------------------------------------ меню игр
# «запусти катку», «запусти напы», «найди матч»: нажимаем кнопки в меню открытой игры
# (по надписям на экране). Только меню — играть за вас SenioreM не будет.
GAME_MODES = [
    (r"нап(ы|арник\w*)|wingman|вингман", ["Напарники", "Wingman"]),
    (r"мм(ку|ка)?|соревновательн\w*|компетитив\w*|competitive|ранкед|рейтинг\w*", ["Соревновательный",
                                                                              "Competitive", "Рейтинговый",
                                                                              "Ranked"]),
    (r"премьер\w*|premier", ["Премьер", "Premier"]),
    (r"бой насмерть|дм|дезматч|deathmatch", ["Бой насмерть", "Deathmatch"]),
    (r"обычн\w*|казуал\w*|casual", ["Обычный", "Casual"]),
    (r"арен\w*|arena", ["Арена", "Arena"]),
    (r"дуэл\w*|1 на 1|один на один", ["Дуэль", "1v1", "Duel"]),
    (r"трен\w*|практик\w*|practice", ["Тренировка", "Practice"]),
]
GAME_PLAY = ["Играть", "Play", "В бой", "Начать игру", "Найти игру", "Найти матч", "Find Match", "Start",
             "Начать"]
GAME_GO = ["Найти", "Поиск", "Go", "Start", "Начать", "Find", "Принять", "Accept", "Готов", "Ready",
           "Подтвердить", "В бой"]
GAME_ACCEPT = ["Принять", "Accept", "Готов", "Ready"]
GAME_CANCEL = ["Отмена", "Отменить", "Cancel", "Остановить поиск", "Отменить поиск", "Stop Search",
               "Cancel Search", "Прекратить поиск", "Выйти из очереди", "Leave Queue", "Stop",
               "Прекратить", "Выйти из поиска"]


def _wait_and_click(win, texts, timeout=3.0, min_score=0.8):
    """Фокусируемся на окне один раз и опрашиваем экран, пока нужная кнопка не появится
    (нажимаем сразу, как только видна). Быстрее фиксированных пауз и надёжнее."""
    _focus(win)
    try:
        rect = _rect(win.hwnd)
    except Exception:  # noqa: BLE001
        return None
    end = time.time() + timeout
    while True:
        try:
            words = ocr_words(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        except Exception:  # noqa: BLE001
            words = []
        for t in texts:
            hit = find_ocr(rect, t, min_score=min_score, words=words)
            if hit:
                click_at(hit[0], hit[1])
                return hit[2]
        if time.time() >= end:
            return None
        time.sleep(0.15)


# ------------------------------------------------------------------ движение в игре голосом
# Это просто нажатия клавиш по вашей команде (как обычная клавиатура): «иди вперёд 3 секунды»,
# «прыгни», «беги влево». Сам по себе SenioreM в игре ничего не делает.
MOVE_KEYS = {"вперед": 0x57, "прямо": 0x57, "назад": 0x53, "влево": 0x41, "налево": 0x41,
             "вправо": 0x44, "направо": 0x44}
NUM_WORDS = {"одну": 1, "один": 1, "одна": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5,
             "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "пару": 2, "полсекунды": 0.5}
_HELD = set()
_HOLD_LOCK = __import__("threading").Lock()


def _num(word, default):
    if not word:
        return default
    word = word.strip()
    try:
        return float(word.replace(",", "."))
    except ValueError:
        return NUM_WORDS.get(word, default)


def parse_move(t):
    t = t.replace("ё", "е")
    m = re.match(r"^(прыгни|прыгай|прыжок|подпрыгни)(\s+(\S+)\s+раз\w*)?$", t)
    if m:
        return {"action": "game_move", "kind": "jump", "times": int(_num(m.group(3), 1))}
    m = re.match(r"^(иди|беги|двигайся|шагай|ходи|топай|отойди|пройди)\s+(вперед|прямо|назад|влево|налево|"
                 r"вправо|направо)(\s+(на\s+)?(\S+)?\s*(секунд\w*|сек|с))?$", t)
    if m:
        sec = _num(m.group(5), 2) if m.group(3) else 2
        return {"action": "game_move", "kind": "move", "key": MOVE_KEYS[m.group(2)],
                "seconds": max(0.2, min(float(sec), 20)), "run": m.group(1) == "беги"}
    if re.match(r"^(стой|остановись|замри|хватит идти|не иди)$", t):
        return {"action": "game_move", "kind": "halt"}
    return None


def release_all():
    with _HOLD_LOCK:
        keys = list(_HELD)
        _HELD.clear()
    for k in keys:
        try:
            _send(k, up=True)
        except Exception:  # noqa: BLE001
            pass


def game_move(intent):
    kind = intent["kind"]
    if kind == "halt":
        release_all()
        return "Стою."
    win = _target_window()
    if win is not None:
        _focus(win)
    if kind == "jump":
        press([0x20], intent.get("times", 1))
        return ""
    key, sec = intent["key"], intent["seconds"]
    keys = [0x10, key] if intent.get("run") else [key]

    def hold():
        with _HOLD_LOCK:
            _HELD.update(keys)
        for k in keys:
            _send(k)
        end = time.time() + sec
        while time.time() < end:
            with _HOLD_LOCK:
                if key not in _HELD:          # сказали «стоп»/«стой»
                    return
            time.sleep(0.05)
        release_all()
    __import__("threading").Thread(target=hold, daemon=True).start()
    return ""


def parse_game(t):
    if re.match(r"^(прими|принять|прими игру|прими матч|прими катку|accept)$", t):
        return {"action": "game_accept"}
    if re.match(r"^(отмен\w+|останов\w+|прекрат\w+|выйди из)\s+(подбор\w*\s*матч\w*|подбор\w*|"
                r"поиск\w*\s*(матч\w*|игр\w*)?|матч\w*|катк\w*|очеред\w*)$", t):
        return {"action": "game_cancel"}
    m = re.match(r"^(запусти|запустить|начни|найди|ищи|поищи|го|давай|кинь|ставь|поставь)\s+"
                 r"(поиск\s+)?(катку|катки|матч|игру в поиск|поиск игры|поиск матча|игру)?\s*(в\s+|на\s+)?(.*)$", t)
    if not m:
        return None
    what, rest = m.group(3), (m.group(5) or "").strip()
    for rx, labels in GAME_MODES:
        if rest and re.fullmatch(rf"({rx})", rest):
            return {"action": "game_play", "mode": labels}
    if what in ("катку", "катки", "матч", "поиск игры", "поиск матча", "игру в поиск") and not rest:
        return {"action": "game_play", "mode": None}
    return None


def game_play(mode):
    """Меню открытой игры: «Играть» → режим → «Найти/Начать». Нажимаем каждую кнопку сразу,
    как только она появилась (не ждём фиксированных пауз)."""
    win = _target_window()
    if win is None:
        return "Не вижу открытой игры — откройте окно игры."
    steps = []
    hit = _wait_and_click(win, GAME_PLAY, timeout=2.5)
    if hit:
        steps.append(hit)
    if mode:
        hit = _wait_and_click(win, mode, timeout=3.5)
        if not hit:
            got = _ai_pick(win, "режим игры " + mode[0])
            if got:
                click_at(got[0], got[1])
                hit = got[2]
        if not hit:
            return (f"Не нашёл в меню режим «{mode[0]}». Откройте главное меню игры и повторите."
                    if not steps else f"Нажал «{steps[0]}», но не нашёл режим «{mode[0]}».")
        steps.append(hit)
    hit = _wait_and_click(win, GAME_GO, timeout=3.5)
    if hit:
        steps.append(hit)
    if not steps:
        return "Не нашёл в игре кнопку «Играть». Откройте главное меню игры и повторите."
    return "Готово: " + " → ".join(f"«{s}»" for s in steps) + "."


def game_cancel():
    """Отменить подбор/поиск матча в открытой игре."""
    win = _target_window()
    if win is None:
        return "Не вижу открытой игры."
    hit = _wait_and_click(win, GAME_CANCEL, timeout=2.5)
    if not hit:
        got = _ai_pick(win, "отменить поиск матча или выйти из очереди")
        if got:
            click_at(got[0], got[1])
            hit = got[2]
    return f"Отменил: «{hit}»." if hit else "Не нашёл кнопку отмены поиска в этом окне."


def parse(text):
    """-> intent или None (если это не команда управления)."""
    t = _norm(text)
    if not t:
        return None
    g = parse_game(t) or parse_move(t)
    if g:
        return g
    # --- «зайди в юту», «перейди на ютуб» — это сайт, а не кнопка в игре
    m = re.match(r"^(зайди|зайти|перейди|заходи|открой)\s+(в|на)\s+(.+)$", t)
    if m:
        import sites
        site = sites.find_site(m.group(3))
        if site and len(m.group(3).split()) <= 2:
            return {"action": "open", "app": None, "name": m.group(3)}
    # --- YouTube: найти/включить ролик, самый популярный/новый/старый, у любого автора
    yt = _parse_yt_find(t)
    if yt:
        return yt
    m = re.search(r"\b(включи|открой|запусти|поставь|покажи|давай)\s+(\w+)\s+(видео|ролик|видос)\w*", t)
    if m and m.group(2) in ORDINALS:
        return {"action": "yt_nth", "n": ORDINALS[m.group(2)]}
    verb = q = None
    m = re.search(r"\b(включи|поставь|найди|открой|покажи|запусти)\s+(на|в)\s+(ютуб\w*|youtube)\s+(.+)$", t)
    if m:
        verb, q = m.group(1), m.group(4)
    else:
        m = re.search(r"\b(включи|поставь|найди|покажи|запусти)\s+(.+?)\s+(на|в)\s+(ютуб\w*|youtube)$", t)
        if m:
            verb, q = m.group(1), m.group(2)
    if q:
        q = re.sub(r"^(видео|ролик|видос)\s+(про\s+)?", "", q).strip()
        if q:
            return {"action": "yt_play", "query": q, "search_only": verb == "найди"}
    if re.search(r"(видео|ролик|видос|ютуб)", t) or _yt_hint(t):
        if re.search(r"перемота\w* (вперед|дальше)|вперед на|промотай", t):
            return {"action": "yt_key", "key": "forward"}
        if re.search(r"перемота\w* назад|назад на", t):
            return {"action": "yt_key", "key": "back"}
        if re.search(r"на весь экран|полный экран|во весь экран", t):
            return {"action": "yt_key", "key": "full"}
        if re.search(r"субтитр", t):
            return {"action": "yt_key", "key": "subs"}
        if re.search(r"следующ", t):
            return {"action": "yt_key", "key": "next"}
        if re.search(r"предыдущ", t):
            return {"action": "yt_key", "key": "prev"}
    if re.search(r"^(перемотай|промотай) (вперед|дальше)", t):
        return {"action": "yt_key", "key": "forward"}
    if re.search(r"^перемотай назад", t):
        return {"action": "yt_key", "key": "back"}
    if re.search(r"^(сделай )?(на весь экран|во весь экран|полноэкранный)", t):
        return {"action": "yt_key", "key": "full"}
    # --- вкладки браузера
    hit = parse_tabs(t)
    if hit:
        return hit
    # --- игры и лаунчеры: «найди игру … и зайди», «выбери первую игру», «играть»
    hit = parse_app(t)
    if hit:
        return hit
    # --- клавиши и клики
    m = re.match(r"^(нажми|нажать|жми|кликни|клик|тыкни|ткни|щелкни|нажмите|выбери)\b\s*(.*)$", t)
    if not m:
        return None
    verb, rest = m.group(1), m.group(2).strip()
    times = 1
    tm = re.search(r"\s(\d+|два|две|три|четыре|пять|десять)\s+раз\w*$", " " + rest)
    if tm:
        times = int(tm.group(1)) if tm.group(1).isdigit() else NUM_WORDS.get(tm.group(1), 1)
        rest = rest[: tm.start()].strip() if tm.start() > 0 else ""
        rest = re.sub(r"\s(\d+|два|две|три|четыре|пять|десять)\s+раз\w*$", "", " " + rest).strip()
    rest = re.sub(r"^(на|по)\s+", "", rest)
    if rest in ("", "мышкой", "мышью", "левой", "левой кнопкой", "мышку"):
        return {"action": "mouse_click", "button": "left", "times": times}
    if rest in ("правой", "правой кнопкой", "правой кнопкой мыши"):
        return {"action": "mouse_click", "button": "right", "times": times}
    key = key_for(re.sub(r"^(кнопку|клавишу|клавиша|кнопка)\s+", "", rest))
    if key and not rest.startswith(("кнопку ", "кнопка ")):
        return {"action": "press_key", "keys": key, "times": times, "name": rest}
    target = re.sub(r"^(кнопку|кнопка|ссылку|пункт|надпись|слово)\s+", "", rest)
    om = re.match(r"^(\w+)\s+(видео|ролик|видос)", target)
    if om and om.group(1) in ORDINALS:
        return {"action": "yt_nth", "n": ORDINALS[om.group(1)]}
    return {"action": "click_text", "text": target}


TAB_NUM = {"одну": 1, "одна": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
           "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "пару": 2}


def parse_tabs(t):
    """«закрой эту вкладку», «закрой первые 5 вкладок», «закрой все вкладки», «закрой вкладку ютуб»."""
    m = re.match(r"^(закрой|убери|закрыть)\s+(сайт\s+)?(.+)$", t)
    if m and not re.search(r"вклад[ко]", t):
        import sites
        name = m.group(3)
        site = sites.find_site(name)
        if site and (not site[1] or not sites.find_program(name, threshold=0.8)):
            return {"action": "tabs", "mode": "by_name", "name": name}   # «закрой ютуб» — вкладку
    if not re.search(r"вклад[ко]|таб[ыа]?\b|вкладочк", t) or not re.search(
            r"закр|убери|удали|выключи|верни|открой заново|восстанови|переключи|следующ|предыдущ", t):
        return None
    if re.search(r"(верни|открой заново|восстанови)", t):
        return {"action": "tabs", "mode": "reopen"}
    if re.search(r"следующ", t):
        return {"action": "tabs", "mode": "next"}
    if re.search(r"предыдущ", t):
        return {"action": "tabs", "mode": "prev"}
    if re.search(r"\bвсе\b|\bвсё\b", t) and not re.search(r"кроме|остальн", t):
        return {"action": "tabs", "mode": "all"}
    if re.search(r"остальн|кроме (этой|текущей)", t):
        return {"action": "tabs", "mode": "others"}
    m = re.search(r"(\d+|" + "|".join(TAB_NUM) + r")", t)
    n = None
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else TAB_NUM[m.group(1)]
    if re.search(r"последн", t):
        return {"action": "tabs", "mode": "last", "n": n or 1}
    if re.search(r"перв", t):
        return {"action": "tabs", "mode": "first", "n": n or 1}
    if n:
        return {"action": "tabs", "mode": "current", "n": n}
    m = re.search(r"вкладк\w*\s+(с\s+|со\s+|где\s+)?(.+)$", t)
    if m and not re.fullmatch(r"(эту|текущую|ее|её|открытую|активную)", m.group(2).strip()):
        name = re.sub(r"^(сайтом|сайт|страницей)\s+", "", m.group(2).strip())
        return {"action": "tabs", "mode": "by_name", "name": name}
    return {"action": "tabs", "mode": "current", "n": 1}


def tabs(intent):
    win = _browser_window(prefer_youtube=False)
    if win is None:
        return "Не вижу открытого браузера."
    _focus(win)
    mode, n = intent.get("mode"), max(1, min(50, int(intent.get("n") or 1)))
    W, TAB, SH, CTRL = ord("W"), 0x09, 0x10, 0x11
    if mode == "reopen":
        press([CTRL, SH, ord("T")])
        return "Вернул закрытую вкладку."
    if mode == "next":
        press([CTRL, TAB])
        return "Следующая вкладка."
    if mode == "prev":
        press([CTRL, SH, TAB])
        return "Предыдущая вкладка."
    if mode == "all":
        press([CTRL, SH, W])                    # закрыть окно браузера со всеми вкладками
        return "Закрыл все вкладки."
    if mode == "others":
        # закрываем всё справа и слева от текущей: справа — переходом на последнюю
        title = win.title
        closed = 0
        for _ in range(60):
            press([CTRL, ord("9")])             # последняя вкладка
            time.sleep(0.15)
            import procs
            cur = procs.foreground()
            if cur is None or cur.title == title:
                break
            press([CTRL, W])
            closed += 1
            time.sleep(0.12)
        for _ in range(60):
            press([CTRL, ord("1")])             # первая вкладка
            time.sleep(0.15)
            import procs
            cur = procs.foreground()
            if cur is None or cur.title == title:
                break
            press([CTRL, W])
            closed += 1
            time.sleep(0.12)
        return f"Оставил только текущую вкладку, закрыл {closed}."
    if mode in ("first", "last"):
        press([CTRL, ord("1" if mode == "first" else "9")])
        time.sleep(0.15)
        for _ in range(n):
            if mode == "last":
                press([CTRL, ord("9")])
                time.sleep(0.08)
            press([CTRL, W])
            time.sleep(0.12)
        word = "первую" if mode == "first" else "последнюю"
        return (f"Закрыл {word} вкладку." if n == 1 else
                f"Закрыл {'первые' if mode == 'first' else 'последние'} {n} вкладок.")
    if mode == "by_name":
        name = intent.get("name", "")
        import procs
        import sites
        keys = {sites._norm(sites._latinize(k)) for k in sites.keys_for(name)} | {sites._norm(name)}
        first = None
        for step in range(40):
            cur = procs.foreground()
            raw = cur.title if cur else ""
            title = sites._norm(sites._latinize(raw))
            if any(k and k in title for k in keys):
                press([CTRL, W])
                return f"Закрыл вкладку «{raw[:40]}»."
            if step and raw == first:
                break                               # прошли все вкладки по кругу
            first = first if first is not None else raw
            press([CTRL, TAB])
            time.sleep(0.18)
        return f"Не нашёл вкладку «{name}»."
    for _ in range(n):
        press([CTRL, W])
        time.sleep(0.12)
    return "Закрыл вкладку." if n == 1 else f"Закрыл {n} вкладок."


ITEM_WORDS = r"(игру|игра|карточку|результат|пункт|вариант|ссылку|сервер|мод|режим|уровень|карту|" \
             r"персонажа|скин|предмет|плейс|плейсы|место|файл|папку|элемент|строку|кнопку)"
ENTER_WORDS = r"(зайди|войди|запусти|играй|поиграем|открой|включи|начни|присоединись|подключись)"
PLACE_WORDS = ("тут", "здесь", "в окне", "в игре", "в роблоксе", "в роблокс", "в стиме", "в steam",
               "в приложении", "в лаунчере", "в программе", "на экране", "в магазине")


def parse_app(t):
    # «выбери первую игру», «открой вторую карточку», «зайди в третий сервер»
    m = re.match(r"^(выбери|открой|нажми на|нажми|зайди в|зайди на|запусти|кликни на|кликни|включи|"
                 r"войди в|давай)\s+(\w+)\s+" + ITEM_WORDS + r"\b(.*)$", t)
    if m and m.group(2) in ORDINALS:
        play = bool(re.search(r"\bи\s+" + ENTER_WORDS, m.group(4) or "")) or m.group(1).startswith(
            ("зайди", "войди", "запусти"))
        return {"action": "nth_item", "n": ORDINALS[m.group(2)], "play": play}
    # «найди игру доорс и зайди», «найди в роблоксе брукхейвен»
    m = re.match(r"^(найди|поищи|ищи|отыщи|набери в поиске|введи в поиск)\s+(.+)$", t)
    if m:
        rest = m.group(2)
        play = False
        em = re.search(r"\s+и\s+" + ENTER_WORDS + r"(\s+в\s+(нее|неё|него|нее))?.*$", rest)
        if em:
            play = True
            rest = rest[:em.start()]
        local = any(p in " " + rest + " " for p in [" " + x + " " for x in PLACE_WORDS]) or \
            re.match(r"^(игру|игра|сервер|карту|мод|режим|плейс)\s+", rest) or play or \
            m.group(1) in ("набери в поиске", "введи в поиск")
        if local:
            for x in PLACE_WORDS:
                rest = rest.replace(" " + x, "").replace(x + " ", "")
            rest = re.sub(r"^(игру|игра|сервер|карту|мод|режим|плейс)\s+", "", rest).strip()
            if rest:
                return {"action": "app_search", "query": rest, "play": play}
    # «зайди в доорс», «войди в игру брукхейвен»
    m = re.match(r"^(зайди|войди|заходи)\s+(в|на)\s+(игру\s+|сервер\s+|режим\s+)?(.+)$", t)
    if m and m.group(4) not in ("нее", "неё", "него", "игру", "нее"):
        return {"action": "enter_item", "text": m.group(4)}
    if re.fullmatch(r"(играть|нажми играть|нажми на играть|начни игру|играем|погнали играть|"
                    r"нажми плей|плей|присоединиться|зайди в игру|войди в игру|запусти игру)", t):
        return {"action": "click_play"}
    return None


YT_SORTS = (
    ("popular", r"(сам\w*\s+)?(популярн\w*|просматриваем\w*|топов\w*)|больше всего просмотров|"
                r"с наибольшим числом просмотров|самый топ"),
    ("oldest", r"(сам\w*\s+)?(старое|старый|старая|старые|старых|первое|первый|первые|ранние|раннее)"
               r"(?!\s+(видео|ролик\w*|видос\w*)\s*$)"),
    ("newest", r"(сам\w*\s+)?(новое|новый|новая|новые|новых|новенькое|последнее|последний|последние|"
               r"свежее|свежий|свежие)"),
)


def _parse_yt_find(t):
    """«найди ролик а4», «найди ролик выживание 24 часа в лесу», «включи самый популярный ролик а4»,
    «найди самое старое видео а4». Когда YouTube уже открыт — «найди …» тоже ищет на YouTube."""
    m = re.match(r"^(найди|поищи|покажи|ищи|включи|поставь|запусти|открой|врубай|давай)\s+(.+)$", t)
    if not m:
        return None
    verb, rest = m.group(1), m.group(2)
    has_video = re.search(r"\b(ролик\w*|видео\w*|видос\w*|клип\w*|ютуб\w*|youtube)\b", rest)
    if not has_video and not (verb in ("найди", "поищи", "ищи") and _yt_hint(t)):
        return None
    if re.match(r"^(\w+)\s+(видео|ролик|видос)\w*$", rest) and rest.split()[0] in ORDINALS:
        return None                                    # «включи первое видео» — отдельная команда
    sort = None
    for key, rx in YT_SORTS:
        if re.search(rf"(^|\s)({rx})(\s|$)", rest):
            sort = key
            rest = re.sub(rf"(^|\s)({rx})(?=\s|$)", " ", rest)
            break
    q = re.sub(r"\b(ролик\w*|видео\w*|видос\w*|клип\w*)\b", " ", rest)
    q = re.sub(r"\b(на|в)\s+(ютуб\w*|youtube)\b|\b(ютуб\w*|youtube)\b", " ", q)
    q = re.sub(r"^\s*(про|о|об|с|у|от|канала|блогера|автора)\s+", " ", q.strip() + " ")
    q = re.sub(r"\s+(у|от|канала)\s*$", " ", q)
    q = " ".join(q.split())
    if not q:
        return None
    play = verb in ("включи", "поставь", "запусти", "врубай", "давай") or (verb == "открой" and has_video)
    return {"action": "yt_find", "query": q, "sort": sort, "play": play}


def _yt_hint(t):
    """Открыт ли сейчас YouTube (тогда «следующее», «на весь экран» — про видео)."""
    try:
        import procs
        w = procs.foreground()
        return bool(w and "youtube" in (w.title or "").lower())
    except Exception:  # noqa: BLE001
        return False


def key_for(name):
    """«пробел» -> [0x20]; «контрл с» -> [0x11, 0x53]; «w» -> [0x57]; «ф5» -> [0x74]."""
    name = name.strip().lower()
    if not name:
        return None
    if name in KEYS:
        return [KEYS[name]]
    m = re.fullmatch(r"(f|ф|эф)\s*(\d{1,2})", name)
    if m and 1 <= int(m.group(2)) <= 12:
        return [0x70 + int(m.group(2)) - 1]
    if re.fullmatch(r"[a-z0-9]", name):
        return [ord(name.upper())]
    if name in LETTER_NAMES:
        return [ord(LETTER_NAMES[name])]
    parts = name.replace("+", " плюс ").split()
    if len(parts) >= 2 and ("плюс" in parts or parts[0] in KEYS):
        out = []
        for part in [x for x in parts if x != "плюс"]:
            k = key_for(part)
            if not k:
                return None
            out += k
        return out
    return None


# ------------------------------------------------------------------ ввод
def _target_window():
    """Окно, в котором выполняем команду: то, что человек сейчас видит на экране (активное),
    и только не свёрнутое. В свёрнутых окнах ничего не нажимаем."""
    import procs
    return procs.active_window()


def _focus(win):
    import procs
    if win is not None:
        procs.activate(win.hwnd)
        time.sleep(0.25)


def _send(vk, up=False):
    u = ctypes.windll.user32
    scan = u.MapVirtualKeyW(vk, 0)
    ext = vk in (0x25, 0x26, 0x27, 0x28, 0x2E, 0x24, 0x23, 0x21, 0x22)
    flags = (0x0002 if up else 0) | (0x0001 if ext else 0)
    u.keybd_event(vk, scan, flags, 0)


def press(keys, times=1):
    for _ in range(max(1, min(times, 30))):
        for k in keys:
            _send(k)
            time.sleep(0.02)
        time.sleep(0.04)
        for k in reversed(keys):
            _send(k, up=True)
            time.sleep(0.02)
        time.sleep(0.08)


def click_at(x, y, button="left", times=1):
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
    for _ in range(max(1, times)):
        u.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        u.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)


def type_text(text):
    """Печатает текст (любые буквы) — через Unicode-ввод."""
    for ch in text:
        code = ord(ch)
        _unicode(code, False)
        _unicode(code, True)
        time.sleep(0.004)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _unicode(code, up):
    inp = _INPUT()
    inp.type = 1
    inp.ki = _KEYBDINPUT(0, code, 0x0004 | (0x0002 if up else 0), 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ------------------------------------------------------------------ поиск текста на экране
def _rect(hwnd):
    import ctypes.wintypes as wt
    r = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _similar(a, b):
    import sites
    a, b = sites._norm(a), sites._norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b.startswith(a + " ") or b.startswith(a):
        return 0.9 if len(a) >= 3 or len(b) <= 4 else 0.75
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


_uia = None


def _uia_client():
    global _uia
    if _uia is None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        _uia = comtypes.client.CreateObject(CUIAutomation._reg_clsid_, interface=IUIAutomation)
    return _uia


CLICKABLE = {50000, 50005, 50011, 50007, 50019, 50002, 50013, 50020, 50003, 50006, 50021, 50031}


def find_uia(hwnd, text, limit_s=2.5, min_score=0.78):
    """Элемент окна с похожей надписью (кнопка, ссылка, пункт меню). -> (x, y, имя) или None."""
    import comtypes
    try:
        comtypes.CoInitialize()
    except Exception:  # noqa: BLE001
        pass
    uia = _uia_client()
    root = uia.ElementFromHandle(hwnd)
    arr = root.FindAll(4, uia.CreateTrueCondition())        # TreeScope_Descendants
    best, best_sc = None, 0.0
    t0 = time.time()
    n = min(arr.Length, 4000)
    for i in range(n):
        if time.time() - t0 > limit_s:
            break
        try:
            el = arr.GetElement(i)
            name = el.CurrentName or ""
            if not name or len(name) > 80 or el.CurrentControlType not in CLICKABLE:
                continue
            sc = _similar(text, name)
            if sc > best_sc:
                if el.CurrentIsOffscreen:
                    continue
                r = el.CurrentBoundingRectangle
                if r.right - r.left < 2 or r.bottom - r.top < 2:
                    continue
                best, best_sc = ((r.left + r.right) / 2, (r.top + r.bottom) / 2, name), sc
        except Exception:  # noqa: BLE001
            continue
    return best if best_sc >= min_score else None


OCR_PS = r"""
param([string]$img, [int]$x, [int]$y, [int]$w, [int]$h)
Add-Type -Name D -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[W.D]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Drawing
if ($w -gt 0) {
  $bmp = New-Object System.Drawing.Bitmap([int]$w, [int]$h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
  $bmp.Save($img, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($img)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res = @()
$langs = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
[Console]::Error.WriteLine("ocr langs: " + ($langs | ForEach-Object { $_.LanguageTag }) -join ",")
$engines = @()
foreach ($lang in $langs) { $e = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang); if ($e) { $engines += $e } }
if ($engines.Count -eq 0) { $e = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); if ($e) { $engines += $e } }
[Console]::Error.WriteLine("engines: " + $engines.Count + " bitmap: " + ($sb -ne $null))
foreach ($eng in $engines) {
  if ($eng -eq $null) { continue }
  $r = Await ($eng.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
  foreach ($l in $r.Lines) { foreach ($wd in $l.Words) {
    $res += [pscustomobject]@{t=$wd.Text; x=$wd.BoundingRect.X; y=$wd.BoundingRect.Y; w=$wd.BoundingRect.Width; h=$wd.BoundingRect.Height; line=$l.Text}
  } }
}
$stream.Dispose()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$res | ConvertTo-Json -Compress
"""


OCR_ERR = ""


def ocr_words(left, top, width, height):
    """Слова на экране в прямоугольнике: [{t, x, y, w, h, line}] (координаты экрана)."""
    d = tempfile.gettempdir()
    script = os.path.join(d, "seniorem_ocr.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(OCR_PS)
    img = os.path.join(d, "seniorem_ocr.png")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                        img, str(left), str(top), str(width), str(height)],
                       capture_output=True, timeout=25, creationflags=NO_WINDOW)
    out = r.stdout.decode("utf-8", "ignore").strip()
    global OCR_ERR
    OCR_ERR = r.stderr.decode("utf-8", "ignore").strip()[:900]
    if not out:
        return []
    data = json.loads(out)
    if isinstance(data, dict):
        data = [data]
    for w in data:
        w["x"] += left
        w["y"] += top
    return data


def ocr_file(path):
    """Текст на картинке (файл): строки по порядку."""
    import shutil
    d = tempfile.gettempdir()
    script = os.path.join(d, "seniorem_ocr.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(OCR_PS)
    img = os.path.join(d, "seniorem_ocr_file" + os.path.splitext(path)[1].lower())
    shutil.copyfile(path, img)                 # латинский путь — WinRT не любит необычные пути
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                        img, "0", "0", "0", "0"],
                       capture_output=True, timeout=40, creationflags=NO_WINDOW)
    out = r.stdout.decode("utf-8", "ignore").strip()
    if not out:
        return ""
    data = json.loads(out)
    if isinstance(data, dict):
        data = [data]
    lines = []
    for w in data:
        ln = (w.get("line") or "").strip()
        if ln and ln not in lines:
            lines.append(ln)
    return "\n".join(lines)


def find_ocr(rect, text, min_score=0.72, words=None):
    left, top, right, bottom = rect
    if words is None:
        words = ocr_words(left, top, right - left, bottom - top)
    if not words:
        return None
    import sites
    target = sites._norm(text).split()
    if not target:
        return None
    best, best_sc = None, 0.0
    for i, w in enumerate(words):
        # фраза из нескольких слов: берём подряд идущие слова той же строки
        group = [w]
        j = i + 1
        while len(group) < len(target) and j < len(words) and words[j].get("line") == w.get("line"):
            group.append(words[j])
            j += 1
        phrase = " ".join(g["t"] for g in group)
        sc = _similar(" ".join(target), phrase)
        if sc > best_sc:
            x1 = min(g["x"] for g in group)
            y1 = min(g["y"] for g in group)
            x2 = max(g["x"] + g["w"] for g in group)
            y2 = max(g["y"] + g["h"] for g in group)
            best, best_sc = ((x1 + x2) / 2, (y1 + y2) / 2, phrase), sc
    return best if best_sc >= min_score else None


def click_in(win, texts, min_score=0.85):
    """Нажать в окне первую найденную кнопку из списка надписей. -> надпись или None.
    Сначала читаем то, что ВИДНО на экране (игры и лаунчеры рисуют кнопки сами, а в их
    «невидимом» описании бывают скрытые кнопки), и только потом — описание окна."""
    _focus(win)
    hit = None
    rect = None
    try:
        rect = _rect(win.hwnd)
        words = ocr_words(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        for t in texts:
            hit = find_ocr(rect, t, min_score=min_score, words=words)
            if hit:
                break
    except Exception:  # noqa: BLE001
        hit = None
    if hit is None:
        for t in texts:
            try:
                hit = find_uia(win.hwnd, t, limit_s=1.5, min_score=min_score)
            except Exception:  # noqa: BLE001
                hit = None
            # кнопка должна быть внутри окна на экране, а не спрятанной
            if hit and rect and not (rect[0] <= hit[0] <= rect[2] and rect[1] <= hit[1] <= rect[3]):
                hit = None
            if hit:
                break
    if hit is None:
        return None
    x, y, name = hit
    _focus(win)
    click_at(x, y)
    return name


def click_text(text):
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    _focus(win)
    hit = None
    try:
        hit = find_ocr(_rect(win.hwnd), text)          # сначала — то, что видно на экране
    except Exception:  # noqa: BLE001
        hit = None
    if hit is None:
        try:
            hit = find_uia(win.hwnd, text)
            r = _rect(win.hwnd)
            if hit and not (r[0] <= hit[0] <= r[2] and r[1] <= hit[1] <= r[3]):
                hit = None
        except Exception:  # noqa: BLE001
            hit = None
    if hit is None:
        hit = _ai_pick(win, text)            # точной надписи нет — ИИ выбирает по смыслу
    if hit is None:
        return f"Не нашёл «{text}» в окне «{win.title[:40]}»."
    x, y, name = hit
    _focus(win)
    click_at(x, y)
    return f"Нажал «{name}»."


# ИИ выбирает, на что нажать, по смыслу («нажми выйти» → «Выход из аккаунта»). Задаёт main.py.
AI_PICK = None


def _ai_pick(win, text):
    if AI_PICK is None:
        return None
    try:
        rect, words = _window_words(win)
        lines = [ln for ln in _lines(words) if 1 <= len(ln["text"]) <= 60][:120]
        if not lines:
            return None
        k = AI_PICK(text, [ln["text"] for ln in lines])
        if k is None or not (0 <= k < len(lines)):
            return None
        ln = lines[k]
        return ln["x"], ln["y"], ln["text"]
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ YouTube
BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe",
                "vivaldi.exe", "yandex.exe"}


def _browser_window(prefer_youtube=True):
    import procs
    wins = [w for w in procs.windows() if w.exe in BROWSER_EXES]
    if prefer_youtube:
        for w in wins:
            if "youtube" in w.title.lower():
                return w
    return wins[0] if wins else None


def browser_url(win):
    """Адрес открытой страницы из адресной строки браузера."""
    try:
        uia = _uia_client()
        root = uia.ElementFromHandle(win.hwnd)
        cond = uia.CreatePropertyCondition(30003, 50004)        # ControlType = Edit
        arr = root.FindAll(4, cond)
        for i in range(min(arr.Length, 12)):
            el = arr.GetElement(i)
            try:
                v = el.GetCurrentPropertyValue(30045) or ""     # Value
            except Exception:  # noqa: BLE001
                v = ""
            if v and ("." in v or v.startswith("http")) and " " not in v.strip():
                return v if v.startswith("http") else "https://" + v
    except Exception:  # noqa: BLE001
        pass
    return ""


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36", "Accept-Language": "ru-RU,ru;q=0.9",
        "Cookie": "CONSENT=YES+1; SOCS=CAI"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", "ignore")


def video_ids(page_url):
    """Видео на странице YouTube по порядку."""
    html = _fetch(page_url)
    ids = []
    for m in re.finditer(r'"(?:videoRenderer|gridVideoRenderer|compactVideoRenderer|'
                         r'richItemRenderer|lockupViewModel)".{0,400}?"(?:videoId|contentId)":"([\w-]{11})"',
                         html):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:
        for m in re.finditer(r'"videoId":"([\w-]{11})"', html):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


YT_SP = {"popular": "CAM%253D", "newest": "CAI%253D"}       # сортировка поиска YouTube


def search_url(query, sort=None):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    if sort in YT_SP:
        url += "&sp=" + YT_SP[sort]
    return url


def _yt_channel(query):
    """Канал по имени («а4» -> https://www.youtube.com/@A4) или ""."""
    try:
        html = _fetch(search_url(query) + "&sp=EgIQAg%253D%253D")       # только каналы
    except Exception:  # noqa: BLE001
        return ""
    m = re.search(r'"canonicalBaseUrl":"(/@[^"]+)"', html)
    return "https://www.youtube.com" + urllib.parse.unquote(m.group(1)) if m else ""


def _yt_open(url):
    """Открыть адрес: в уже открытом YouTube — в той же вкладке, иначе в браузере."""
    import webbrowser
    win = _browser_window()
    if win is not None and "youtube" in (win.title or "").lower():
        _navigate(win, url)
        return win
    webbrowser.open(url)
    return None


SORT_CHIPS = {"popular": ["Популярное", "Популярные", "Popular"],
              "oldest": ["Старые", "Сначала старые", "Oldest"],
              "newest": ["Новые", "Latest", "Последние"]}
SORT_WORDS = {"popular": "самые популярные", "oldest": "самые старые", "newest": "самые новые"}


def yt_find(query, sort=None, play=False):
    """Найти или включить ролик. sort: popular / newest / oldest."""
    if play:
        ids = video_ids(search_url(query, "popular" if sort == "oldest" else sort))
        if sort == "oldest":
            ch = _yt_channel(query)
            if ch:                                     # самое старое у автора: открываем канал
                return yt_find(query, "oldest", play=False) + " Скажите «включи первое видео»."
        if not ids:
            _yt_open(search_url(query, sort))
            return f"Открыл поиск на YouTube: {query}."
        _yt_open(f"https://www.youtube.com/watch?v={ids[0]}")
        return f"Включаю{' самое популярное' if sort == 'popular' else (' самое новое' if sort == 'newest' else '')}: {query}."
    # у конкретного автора (короткое имя) самые популярные/старые/новые — на его канале
    if sort and len(query.split()) <= 3:
        ch = _yt_channel(query)
        if ch:
            win = _yt_open(ch + "/videos")
            time.sleep(4.0)
            win = win or _browser_window()
            clicked = None
            if win is not None:
                try:
                    clicked = click_in(win, SORT_CHIPS[sort], min_score=0.85)
                except Exception:  # noqa: BLE001
                    clicked = None
            name = ch.rsplit("/@", 1)[-1]
            if clicked or sort == "newest":
                return f"Открыл канал {name}: {SORT_WORDS[sort]} видео."
            return (f"Открыл видео канала {name}. Нажмите «{SORT_CHIPS[sort][0]}» вверху списка — "
                    f"или скажите «нажми {SORT_CHIPS[sort][0].lower()}».")
    _yt_open(search_url(query, sort))
    return f"Ищу на YouTube{' ' + SORT_WORDS[sort] if sort else ''}: {query}."


def _navigate(win, url):
    """Открыть адрес в той же вкладке браузера."""
    _focus(win)
    press([0x11, 0x4C])            # Ctrl+L — адресная строка
    time.sleep(0.15)
    type_text(url)
    time.sleep(0.05)
    press([0x0D])


def yt_nth(n):
    win = _browser_window()
    url = browser_url(win) if win else ""
    if not url or "youtube.com" not in url:
        if win is None or "youtube" not in (win.title or "").lower():
            return "Сначала откройте YouTube — например, скажите «открой ютуб»."
        url = "https://www.youtube.com/"
    ids = video_ids(url)
    if len(ids) < n:
        return "Не получилось найти видео на этой странице."
    _navigate(win, f"https://www.youtube.com/watch?v={ids[n - 1]}")
    return "Включаю." if n == 1 else f"Включаю {n}-е видео."


def yt_play(query, search_only=False):
    import webbrowser
    if search_only:
        webbrowser.open(search_url(query))
        return f"Ищу на YouTube: {query}."
    ids = video_ids(search_url(query))
    if not ids:
        webbrowser.open(search_url(query))
        return f"Открыл поиск на YouTube: {query}."
    url = f"https://www.youtube.com/watch?v={ids[0]}"
    win = _browser_window()
    if win is not None and "youtube" in (win.title or "").lower():
        _navigate(win, url)
    else:
        webbrowser.open(url)
    return f"Включаю на YouTube: {query}."


def yt_key(name):
    keys, reply = YT_KEYS[name]
    win = _browser_window()
    if win is None:
        return "Не вижу открытого видео."
    _focus(win)
    seq = [0x10, ord("N")] if keys == "SHIFT+N" else ([0x10, ord("P")] if keys == "SHIFT+P" else [ord(keys)])
    press(seq)
    return reply


# ------------------------------------------------------------------ вход
# ------------------------------------------------------------------ игры и лаунчеры
PLAY_WORDS = ["Играть", "Play", "Join", "Присоединиться", "Start", "Начать", "Запустить", "Launch",
              "Войти", "Continue", "Продолжить", "Начать игру", "Play now"]
SEARCH_WORDS = ["Search", "Поиск", "Найти", "Искать", "Search experiences", "Поиск игр"]
NOISE = re.compile(r"(rating|рейтинг|%|^\d+$|^ad$|^\W+$|online|онлайн|playing|играют|friends|друзья|"
                   r"^home$|^charts$|^avatar$|^chat$|^more$|^главная$|recommended|continue|"
                   r"рекоменд|продолжить|see all|все$|^search$|^поиск$|add friends)", re.I)


def _window_words(win):
    rect = _rect(win.hwnd)
    return rect, ocr_words(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])


def _lines(words):
    """Слова -> строки текста с координатами центра."""
    lines = {}
    for w in words:
        key = (w.get("line"), round(w["y"] / 12))
        lines.setdefault(key, []).append(w)
    out = []
    for (text, _), ws in lines.items():
        x1 = min(w["x"] for w in ws)
        y1 = min(w["y"] for w in ws)
        x2 = max(w["x"] + w["w"] for w in ws)
        y2 = max(w["y"] + w["h"] for w in ws)
        out.append({"text": text or " ".join(w["t"] for w in ws), "x": (x1 + x2) / 2,
                    "y": (y1 + y2) / 2, "x1": x1, "h": y2 - y1})
    return out


def _items(win):
    """Похожие на названия игр/карточек строки в порядке чтения (слева направо, сверху вниз)."""
    rect, words = _window_words(win)
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    lines = [ln for ln in _lines(words)
             if ln["y"] > top + h * 0.12 and ln["x1"] > left + w * 0.05
             and len(re.sub(r"[^\wА-Яа-я]", "", ln["text"])) >= 3 and not NOISE.search(ln["text"].strip())]
    # начинаем после заголовка раздела «Рекомендуем / Recommended / Результаты»
    heads = [ln for ln in _lines(words) if re.search(r"recommended|рекоменд|results|результат|"
                                                      r"популярн|popular|for you|для вас", ln["text"], re.I)]
    if heads:
        y0 = min(hd["y"] for hd in heads)
        lines = [ln for ln in lines if ln["y"] > y0 + 10] or lines
    rows = []
    for ln in sorted(lines, key=lambda z: z["y"]):
        if rows and abs(rows[-1][0]["y"] - ln["y"]) < 14:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    rows = [r for r in rows if len(r) <= 8]          # длинные ряды — это ники друзей, меню
    ordered = [ln for r in rows for ln in sorted(r, key=lambda z: z["x"])]
    return ordered


def nth_item(n, play=False):
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    _focus(win)
    items = _items(win)
    if len(items) < n:
        return f"Не нашёл {n}-й вариант в окне «{win.title[:30]}»."
    it = items[n - 1]
    click_at(it["x"], it["y"])
    name = it["text"][:40]
    if play:
        time.sleep(3.0)
        played = click_in(win, PLAY_WORDS, min_score=0.85)
        return f"Открыл «{name}»" + (" и нажал «Играть»." if played else ". Кнопку «Играть» не нашёл.")
    return f"Открыл «{name}»."


def _find_search_box(win):
    """Поле поиска: сначала через UI Automation, потом по надписи «Search/Поиск» на экране."""
    try:
        uia = _uia_client()
        root = uia.ElementFromHandle(win.hwnd)
        arr = root.FindAll(4, uia.CreatePropertyCondition(30003, 50004))     # Edit
        rect = _rect(win.hwnd)
        best = None
        for i in range(min(arr.Length, 30)):
            el = arr.GetElement(i)
            r = el.CurrentBoundingRectangle
            if r.right - r.left < 40:
                continue
            name = (el.CurrentName or "").lower()
            score = 2 if ("search" in name or "поиск" in name or "найти" in name) else 1
            if r.top < rect[1] + (rect[3] - rect[1]) * 0.3:
                score += 1
            if best is None or score > best[0]:
                best = (score, (r.left + r.right) / 2, (r.top + r.bottom) / 2)
        if best:
            return best[1], best[2]
    except Exception:  # noqa: BLE001
        pass
    try:
        hit = click_target_ocr(win, SEARCH_WORDS)
        if hit:
            return hit[0], hit[1]
    except Exception:  # noqa: BLE001
        pass
    return None


def click_target_ocr(win, texts, min_score=0.85):
    rect, words = _window_words(win)
    for t in texts:
        hit = find_ocr(rect, t, min_score=min_score, words=words)
        if hit:
            return hit
    return None


def app_search(query, play=False):
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    _focus(win)
    box = _find_search_box(win)
    if box is None:
        press([0x11, 0x46])                 # Ctrl+F — поиск во многих программах
        time.sleep(0.3)
    else:
        click_at(*box)
        time.sleep(0.25)
    press([0x11, 0x41])                     # выделить старый текст
    type_text(query)
    time.sleep(0.1)
    press([0x0D])
    if not play:
        return f"Ищу «{query}»."
    time.sleep(3.5)
    # первый результат, похожий на запрос (ниже поля поиска)
    rect, words = _window_words(win)
    sy = box[1] if box else rect[1] + 80
    best, best_sc = None, 0.0
    for ln in _lines(words):
        if ln["y"] <= sy + 20:
            continue
        sc = _similar(query, ln["text"])
        if sc > best_sc:
            best, best_sc = ln, sc
    if best is None or best_sc < 0.55:
        items = _items(win)
        best = items[0] if items else None
    if best is None:
        return f"Нашёл «{query}», но не понял, куда нажать."
    click_at(best["x"], best["y"])
    time.sleep(3.0)
    played = click_in(win, PLAY_WORDS, min_score=0.85)
    return f"Нашёл «{best['text'][:40]}»" + (" и нажал «Играть»." if played else ". Открыл страницу.")


def enter_item(text):
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    name = click_in(win, [text], min_score=0.7)
    if not name:
        return app_search(text, play=True)
    time.sleep(3.0)
    played = click_in(win, PLAY_WORDS, min_score=0.85)
    return f"Открыл «{name}»" + (" и нажал «Играть»." if played else ".")


def click_play():
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    name = click_in(win, PLAY_WORDS, min_score=0.85)
    return f"Нажал «{name}»." if name else "Не нашёл кнопку «Играть» в этом окне."


def run(intent):
    a = intent["action"]
    if a == "tabs":
        return tabs(intent)
    if a == "nth_item":
        return nth_item(intent["n"], intent.get("play"))
    if a == "app_search":
        return app_search(intent["query"], intent.get("play"))
    if a == "enter_item":
        return enter_item(intent["text"])
    if a == "click_play":
        return click_play()
    if a == "game_play":
        return game_play(intent.get("mode"))
    if a == "game_cancel":
        return game_cancel()
    if a == "game_move":
        return game_move(intent)
    if a == "game_accept":
        win = _target_window()
        if win is None:
            return "Не вижу открытой игры."
        hit = click_in(win, GAME_ACCEPT, min_score=0.8)
        return f"Нажал «{hit}»." if hit else "Не вижу кнопки «Принять»."
    if a == "press_key":
        win = _target_window()
        if win is None:
            return "Не вижу открытых окон."
        _focus(win)
        press(intent["keys"], intent.get("times", 1))
        return "Нажал." if intent.get("times", 1) == 1 else f"Нажал {intent['times']} раза."
    if a == "mouse_click":
        win = _target_window()
        _focus(win)
        import ctypes.wintypes as wt
        pt = wt.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        click_at(pt.x, pt.y, intent.get("button", "left"), intent.get("times", 1))
        return "Кликнул."
    if a == "click_text":
        return click_text(intent["text"])
    if a == "yt_nth":
        return yt_nth(intent["n"])
    if a == "yt_play":
        return yt_play(intent["query"], intent.get("search_only"))
    if a == "yt_find":
        return yt_find(intent["query"], intent.get("sort"), intent.get("play"))
    if a == "yt_key":
        return yt_key(intent["key"])
    return ""


ACTIONS = ("press_key", "mouse_click", "click_text", "yt_nth", "yt_play", "yt_find", "yt_key", "nth_item", "tabs",
           "app_search", "enter_item", "click_play", "game_play", "game_accept",
           "game_move", "game_cancel")
