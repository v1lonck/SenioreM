"""Разбор фраз на русском в команды. Без внешних зависимостей."""
import re
from difflib import SequenceMatcher

UNITS = {
    "ноль": 0, "нуль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
    "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
    "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
}
TENS = {
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
}
HUNDREDS = {"сто": 100}
SPECIAL = {
    "половину": 50, "половина": 50, "максимум": 100, "максимальную": 100,
    "полную": 100, "минимум": 0, "минимальную": 0,
}

WAKE_DEFAULT = ("сеньор", "сеньер", "синьор", "сеньора", "сеньору", "сеньоры",
                "синьора", "сенор", "синьер", "сеньёр")

APPS = [
    (("браузер", "интернет", "гугл"), "browser"),
    (("блокнот",), "notepad"),
    (("калькулятор",), "calc"),
    (("проводник", "мой компьютер", "этот компьютер"), "explorer"),
    (("загрузки",), "downloads"),
    (("документы",), "documents"),
    (("настройки", "параметры"), "settings"),
    (("диспетчер",), "taskmgr"),
    (("ютуб", "youtube", "ютюб"), "youtube"),
    (("пейнт", "паинт", "пэйнт", "paint", "рисовалк"), "paint"),
]


def normalize(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s%]", " ", text)
    return " ".join(text.split())


def tokens(text: str) -> list:
    return normalize(text).split()


def parse_number(words):
    """'пятьдесят пять' -> 55, '10' -> 10, 'половину' -> 50. Нет числа -> None."""
    total = None
    for w in words:
        d = w.rstrip("%")
        if d.isdigit():
            if total is None:
                return int(d)
            break
        if w in HUNDREDS:
            v = HUNDREDS[w]
        elif w in TENS:
            v = TENS[w]
        elif w in UNITS:
            v = UNITS[w]
        elif w in SPECIAL and total is None:
            return SPECIAL[w]
        else:
            if total is not None:
                break
            continue
        total = (total or 0) + v
    return total


def find_wake(words, extra=()) -> int:
    """Индекс слова-обращения («сеньор») или -1."""
    targets = set(WAKE_DEFAULT) | {normalize(w) for w in extra if w}
    for i, w in enumerate(words):
        if w in targets:
            return i
        if (len(w) >= 5 and w[0] in "сш"
                and SequenceMatcher(None, w, "сеньор").ratio() >= 0.75):
            return i
    return -1


def _has(t, *subs):
    return any(s in t for s in subs)


def _after(words, stems):
    """Слова после первого слова, начинающегося с одного из stems."""
    for i, w in enumerate(words):
        if any(w.startswith(s) for s in stems):
            return words[i + 1:]
    return []


def _clamp(n):
    return max(0, min(100, int(n)))


def parse(text: str) -> dict:
    t = normalize(text)
    w = t.split()
    if not w:
        return {"action": "empty"}

    if _has(t, "стоп", "хватит", "замолчи", "помолчи", "отмена"):
        return {"action": "stop"}

    if _has(t, "закройся", "выключись", "заверши работу", "закрой программу",
            "выход из программы") or t == "выход":
        return {"action": "quit"}

    verb_search = ("найди", "найти", "поищи", "загугли", "погугли", "ищи")
    if any(x in verb_search for x in w):
        q = _after(w, verb_search)
        if q and q[0] in ("в", "во") and len(q) > 1 and q[1] in ("интернете", "гугле", "сети"):
            q = q[2:]
        return {"action": "search", "query": " ".join(q)}

    if any(x.startswith(("откро", "открой", "открыть", "запусти", "запустить")) for x in w):
        for keys, app in APPS:
            if _has(t, *keys):
                return {"action": "open", "app": app}
        return {"action": "open", "app": None, "name": " ".join(_after(w, ("откр", "запуст")))}

    if _has(t, "выключи звук", "отключи звук", "без звука", "убери звук", "мьют"):
        return {"action": "mute", "on": True}
    if _has(t, "включи звук", "верни звук"):
        return {"action": "mute", "on": False}

    if _has(t, "громкост") or (_has(t, "звук") and parse_number(w) is not None):
        n = parse_number(_after(w, ("громкост", "звук")))
        if n is None:
            n = parse_number(w)
        if _has(t, "на всю", "на максимум", "максимал"):
            n = 100
        if _has(t, "увелич", "прибав", "подними", "повыс", "добав"):
            return {"action": "volume_delta", "delta": _clamp(n if n is not None else 10)}
        if _has(t, "уменьш", "убав", "опусти", "пониз", "сбавь"):
            return {"action": "volume_delta", "delta": -_clamp(n if n is not None else 10)}
        if n is not None:
            return {"action": "volume_set", "value": _clamp(n)}
        return {"action": "volume_get"}

    if _has(t, "громче"):
        n = parse_number(w)
        return {"action": "volume_delta", "delta": _clamp(n if n is not None else 10)}
    if _has(t, "тише"):
        n = parse_number(w)
        return {"action": "volume_delta", "delta": -_clamp(n if n is not None else 10)}

    if _has(t, "яркост"):
        n = parse_number(_after(w, ("яркост",)))
        if n is None:
            n = parse_number(w)
        if _has(t, "увелич", "прибав", "подними", "повыс"):
            return {"action": "brightness_delta", "delta": _clamp(n if n is not None else 10)}
        if _has(t, "уменьш", "убав", "опусти", "пониз"):
            return {"action": "brightness_delta", "delta": -_clamp(n if n is not None else 10)}
        if n is not None:
            return {"action": "brightness_set", "value": _clamp(n)}
        return {"action": "brightness_get"}
    if _has(t, "ярче"):
        return {"action": "brightness_delta", "delta": 10}
    if _has(t, "темнее"):
        return {"action": "brightness_delta", "delta": -10}

    if _has(t, "пауз", "продолж", "воспроизвед", "играй"):
        return {"action": "media", "key": "play_pause"}
    if _has(t, "следующ"):
        return {"action": "media", "key": "next"}
    if _has(t, "предыдущ"):
        return {"action": "media", "key": "prev"}

    if _has(t, "сверни"):
        return {"action": "window", "mode": "minimize"}
    if _has(t, "разверни", "покажись", "вернись", "покажи окно"):
        return {"action": "window", "mode": "restore"}

    if _has(t, "заблокируй", "блокировк"):
        return {"action": "lock"}
    if _has(t, "скриншот", "снимок экрана"):
        return {"action": "screenshot"}

    if _has(t, "который час", "сколько времени", "время", "который сейчас час"):
        return {"action": "time"}
    if _has(t, "какое сегодня число", "какое число", "какой сегодня день",
            "какая дата", "дата", "какой день"):
        return {"action": "date"}

    if _has(t, "что ты умеешь", "помощь", "команды", "что умеешь"):
        return {"action": "help"}
    if _has(t, "привет", "здравствуй", "добрый"):
        return {"action": "greet"}
    if _has(t, "спасибо", "благодарю"):
        return {"action": "thanks"}

    return {"action": "unknown", "text": t}
