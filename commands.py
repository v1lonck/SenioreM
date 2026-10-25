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
    (("браузер", "интернет"), "browser"),
    (("блокнот",), "notepad"),
    (("калькулятор",), "calc"),
    (("проводник", "мой компьютер", "этот компьютер"), "explorer"),
    (("загрузки",), "downloads"),
    (("документы",), "documents"),
    (("настройки", "параметры"), "settings"),
    (("диспетчер",), "taskmgr"),
    (("пейнт", "паинт", "пэйнт", "paint", "рисовалк"), "paint"),
]


SELF_WORDS = {"себя", "программу", "приложение", "сеньор", "сеньора", "сеньора",
              "работу", "эту программу", "помощника"}


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


def _same_start(a, b):
    group = ("сш", "еэ")
    return a[0] == b[0] or any(a[0] in g and b[0] in g for g in group)


def find_wake(words, names=None, confs=None, max_pos=1) -> int:
    """Индекс слова-обращения или -1. Чтобы помощник не срабатывал «просто так»:
    обращение должно стоять в начале фразы (первым или вторым словом), быть
    уверенно распознано, а слишком длинные фразы (разговор, фильм) игнорируются."""
    targets = [normalize(w) for w in (names or WAKE_DEFAULT) if normalize(w)]
    if not words or len(words) > 14:
        return -1
    for i, w in enumerate(words[: max_pos + 1]):
        conf = confs[i] if confs and i < len(confs) else 1.0
        if w in targets and conf >= 0.5:
            return i
        for t in targets:
            if (len(t) >= 4 and len(w) >= 4 and _same_start(w, t) and conf >= 0.65
                    and SequenceMatcher(None, w, t).ratio() >= 0.86):
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


# Разговорные и сленговые слова -> обычные
SLANG = {
    "вруби": "включи", "врубай": "включи", "врубить": "включи", "включай": "включи",
    "включить": "включи", "включите": "включи", "вкл": "включи",
    "выруби": "выключи", "вырубай": "выключи", "вырубить": "выключи", "выключай": "выключи",
    "выключить": "выключи", "выключите": "выключи", "выкл": "выключи",
    "запускай": "запусти", "запустите": "запусти", "запустить": "запусти",
    "открывай": "открой", "откройте": "открой", "открыть": "открой", "откроешь": "открой",
    "закрывай": "закрой", "закройте": "закрой", "закрыть": "закрой", "убей": "закрой",
    "кильни": "закрой", "прибей": "закрой", "вырубись": "выключись",
    "погромче": "громче", "погромчее": "громче", "потише": "тише", "потишее": "тише",
    "скрин": "скриншот", "скриншотни": "скриншот", "заскринь": "скриншот", "скринни": "скриншот",
    "скриншотик": "скриншот", "скрином": "скриншот",
    "скип": "следующий", "скипни": "следующий", "скипай": "следующий", "некст": "следующий",
    "щас": "сейчас", "ща": "сейчас", "че": "что", "чо": "что", "шо": "что",
    "спс": "спасибо", "пасиб": "спасибо", "пасибо": "спасибо", "сенкс": "спасибо",
    "здарова": "привет", "здорово": "привет", "хай": "привет", "ку": "привет",
    "салют": "привет", "приветик": "привет", "хеллоу": "привет", "хелло": "привет",
    "музон": "музыку", "музончик": "музыку", "песню": "музыку", "песенку": "музыку",
    "загугли": "найди", "погугли": "найди", "чекни": "найди", "глянь": "найди",
    "стопни": "пауза", "паузу": "пауза", "паузни": "пауза", "тормозни": "пауза",
    "плиз": "пожалуйста", "пж": "пожалуйста", "пожалуста": "пожалуйста",
}
AI_VERBS = {"расскажи", "объясни", "придумай", "напиши", "посоветуй", "спроси", "ответь",
            "переведи", "сочини", "подскажи", "почему", "зачем", "представь", "опиши",
            "порекомендуй", "сравни", "реши", "посчитай", "вычисли", "предложи"}
AI_PHRASES = ("что такое", "кто такой", "кто такая", "кто такие", "что значит", "как сделать",
              "как приготовить", "сколько будет", "что лучше", "как работает", "в чем разница",
              "что посмотреть", "во что поиграть", "что почитать", "как думаешь", "а ты знаешь",
              "ты знаешь", "скажи мне", "давай поговорим", "поговори со мной")
QUESTION_WORDS = {"кто", "что", "какой", "какая", "какое", "какие", "сколько", "когда", "где",
                  "куда", "откуда", "как", "почему", "зачем", "чем", "чей", "можно", "правда",
                  "а", "ли", "скажи", "есть"}
SOUND_WORDS = {"звук", "звуки", "звука", "громкость", "динамики", "колонки"}
MUSIC_WORDS = {"музыку", "музыка", "трек", "песня", "плеер", "проигрыватель"}
SMALL_TALK = [
    (("ты тут", "ты здесь", "ты где", "алло", "ау", "ты меня слышишь", "слышишь меня"),
     "Да, я здесь и слушаю."),
    (("как дела", "как ты", "как жизнь", "как поживаешь", "как настроение"),
     "Отлично! Готов помогать."),
    (("кто ты", "ты кто", "как тебя зовут", "что ты такое"),
     "Я SenioreM, ваш голосовой помощник."),
    (("что делаешь", "чем занят", "че делаешь"), "Слушаю вас и жду команду."),
    (("молодец", "красава", "красавчик", "умница", "ты лучший", "крутой", "хорош"),
     "Спасибо! Стараюсь."),
    (("пока", "до свидания", "спокойной ночи", "до завтра"), "До встречи!"),
    (("скучно", "мне скучно"), "Могу включить музыку или открыть ютуб — только скажите."),
]


def parse(text: str) -> dict:
    t = normalize(text)
    w = [SLANG.get(x, x) for x in t.split()]
    w = [x for x in w if x not in ("пожалуйста", "ка", "плз")]
    t = " ".join(w)
    if not w:
        return {"action": "empty"}

    if t in ("забудь", "забудь все", "новый разговор", "начнем сначала", "сбрось разговор"):
        return {"action": "forget"}
    if w[0] in AI_VERBS or any(t.startswith(p + " ") for p in AI_PHRASES):
        return {"action": "ask", "text": text.strip()}

    if (("погод" in t or _has(t, "сколько градусов", "какая температура", "холодно ли",
                                "тепло ли", "будет ли дождь", "будет дождь", "будет ли снег",
                                "нужен ли зонт", "брать ли зонт"))
            and not w[0].startswith(("откр", "найд", "запуст"))):
        day = "tomorrow" if "завтра" in t else ("today" if _has(t, "сегодня", "днем", "вечером",
                                                                  "будет") else "now")
        return {"action": "weather", "day": day}

    cur = None
    for code, stems in (("USD", ("доллар",)), ("EUR", ("евро",)), ("CNY", ("юан",)),
                        ("GBP", ("фунт",)), ("KZT", ("тенге",)), ("BYN", ("белорусск",)),
                        ("TRY", ("лир",)), ("JPY", ("иен", "йен"))):
        if any(st in t for st in stems):
            cur = code
            break
    if cur and (_has(t, "курс", "стоит", "почем", "рубл", "сколько") or len(w) <= 2):
        return {"action": "rates", "cur": cur}
    for code, stems in (("bitcoin", ("биткоин", "биткойн", "bitcoin")),
                        ("ethereum", ("эфир", "эфириум", "ethereum")),
                        ("toncoin", ("тонкоин", "toncoin")),
                        ("tether", ("тезер", "usdt"))):
        if any(st in t for st in stems) and (_has(t, "курс", "стоит", "почем", "сколько")
                                               or len(w) <= 2):
            return {"action": "crypto", "coin": code}

    if _has(t, "обнови список", "обнови программы", "обнови игры", "найди новые игры",
            "найди новые программы", "просканируй", "выучи программы", "выучи игры"):
        return {"action": "rescan"}

    for phrases, reply in SMALL_TALK:
        if any(t == p or t.startswith(p + " ") or t.endswith(" " + p) for p in phrases):
            return {"action": "chat", "reply": reply}

    # «включи» / «выключи» без уточнения — про звук
    if w == ["включи"] or t in ("верни звук", "звук", "включи обратно"):
        return {"action": "mute", "on": False}
    if w == ["выключи"]:
        return {"action": "mute", "on": True}
    if w[0] in ("включи", "выключи") and len(w) > 1 and w[1] not in ("звук", "звуки", "громкость"):
        rest = [x for x in w[1:] if x not in ("мне", "нам")]
        if set(rest) & MUSIC_WORDS:
            return {"action": "media", "key": "play_pause"}
        if w[0] == "выключи" and rest and rest[0] in ("компьютер", "комп", "пк", "микрофон"):
            pass  # такие вещи не трогаем — дальше ответит «не понял»
        elif rest and not (set(rest) & SOUND_WORDS):
            if w[0] == "включи":
                return {"action": "open", "app": None, "name": " ".join(rest)}
            return {"action": "close", "app": None, "name": " ".join(rest)}

    if _has(t, "стоп", "хватит", "замолчи", "помолчи", "отмена"):
        return {"action": "stop"}

    if _has(t, "закройся", "выключись", "выход из программы") or t == "выход":
        return {"action": "quit"}

    verb_close = ("закрой", "закрыть", "закрою", "заверши", "завершить")
    if any(x in verb_close for x in w):
        rest = [x for x in _after(w, verb_close) if x not in ("пожалуйста", "мне", "ка")]
        if not rest or " ".join(rest) in SELF_WORDS:
            return {"action": "quit"}
        name = " ".join(rest)
        for keys, app in APPS:
            if _has(name, *keys):
                return {"action": "close", "app": app, "name": name}
        return {"action": "close", "app": None, "name": name}

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

    if _has(t, "на всю", "на полную", "на максимум", "максимальная громкость"):
        return {"action": "volume_set", "value": 100}

    if _has(t, "который час", "сколько времени", "время", "который сейчас час",
            "сколько сейчас", "что по времени"):
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

    if w[0] in QUESTION_WORDS or text.strip().endswith("?"):
        return {"action": "ask", "text": text.strip()}
    return {"action": "unknown", "text": t}
