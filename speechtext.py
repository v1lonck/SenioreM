"""Подготовка текста к озвучке: числа словами, время, проценты, сокращения, латиница.
Без этого синтезатор «спотыкается» на цифрах, кавычках и английских словах."""
import re

UNITS = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
UNITS_F = {1: "одна", 2: "две"}
TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
        "восемьдесят", "девяносто"]
HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
            "восемьсот", "девятьсот"]


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _triad(n, feminine=False):
    words = []
    h, rest = divmod(n, 100)
    if h:
        words.append(HUNDREDS[h])
    if rest >= 20:
        t, u = divmod(rest, 10)
        words.append(TENS[t])
        if u:
            words.append(UNITS_F[u] if feminine and u in UNITS_F else UNITS[u])
    elif rest:
        words.append(UNITS_F[rest] if feminine and rest in UNITS_F else UNITS[rest])
    return words


def number_words(n: int, feminine=False) -> str:
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + number_words(-n, feminine)
    if n >= 10 ** 9:
        return " ".join(UNITS[int(d)] for d in str(n))
    words = []
    mil, rest = divmod(n, 1_000_000)
    th, rest = divmod(rest, 1000)
    if mil:
        words += _triad(mil) + [plural(mil, "миллион", "миллиона", "миллионов")]
    if th:
        words += ([] if th == 1 else _triad(th, feminine=True)) + \
            [plural(th, "тысяча", "тысячи", "тысяч")]
    words += _triad(rest, feminine)
    return " ".join(w for w in words if w)


LATIN = [("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("th", "т"), ("ph", "ф"),
         ("kh", "х"), ("ts", "ц"), ("oo", "у"), ("ee", "и"), ("ea", "и"), ("ou", "ау"),
         ("ck", "к"), ("qu", "кв"), ("x", "кс"), ("j", "дж"), ("w", "в"), ("q", "к"),
         ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
         ("h", "х"), ("i", "и"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"),
         ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("y", "и"),
         ("z", "з")]
KNOWN_LATIN = {
    "the": "зе", "of": "оф", "and": "энд", "hearthstone": "хартстоун", "witcher": "ведьмак",
    "seniorem": "сеньорем", "telegram": "телеграм", "youtube": "ютуб", "discord": "дискорд",
    "steam": "стим", "google": "гугл", "windows": "виндоус", "chrome": "хром", "osu": "осу",
    "yandex": "яндекс", "spotify": "спотифай", "minecraft": "майнкрафт", "vk": "вэ ка",
    "ok": "окей", "wi-fi": "вай фай", "wifi": "вай фай", "ai": "эй ай", "pc": "пэ ка",
    "dota": "дота", "counter-strike": "каунтер страйк", "twitch": "твич", "zoom": "зум",
    "word": "ворд", "excel": "эксель", "photoshop": "фотошоп", "github": "гитхаб",
}
ABBR = {
    "т.е.": "то есть", "т.д.": "так далее", "т.п.": "тому подобное", "т.к.": "так как",
    "др.": "другие", "г.": "года", "руб.": "рублей", "млн": "миллионов", "млрд": "миллиардов",
    "тыс.": "тысяч", "км": "километров", "кг": "килограммов", "ИИ": "и и", "ПК": "пэ ка",
    "США": "сэ шэ а", "РФ": "эр эф",
}
SYMBOLS = {"№": " номер ", "°C": " градусов", "°": " градусов", "&": " и ", "+": " плюс ",
           "=": " равно "}
LETTERS = {"a": "эй", "b": "би", "c": "си", "d": "ди", "e": "и", "f": "эф", "g": "джи",
           "h": "эйч", "i": "ай", "j": "джей", "k": "кей", "l": "эл", "m": "эм", "n": "эн",
           "o": "оу", "p": "пи", "q": "кью", "r": "ар", "s": "эс", "t": "ти", "u": "ю",
           "v": "ви", "w": "дабл ю", "x": "экс", "y": "уай", "z": "зед"}


def _latin_word(m):
    w = m.group(0)
    low = w.lower()
    if low in KNOWN_LATIN:
        return KNOWN_LATIN[low]
    if w.isupper() and len(w) <= 4:          # аббревиатура: CPU -> си пи ю
        return " ".join(LETTERS.get(c, c) for c in low)
    if len(low) > 4 and low.endswith("e") and low[-2] not in "aeiouy":
        low = low[:-1]                       # немая e на конце: stone -> стон
    out, i = "", 0
    while i < len(low):
        for a, b in LATIN:
            if low.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            out += low[i]
            i += 1
    return out


# буква «ё», которую часто не пишут: без неё голос говорит «еще», «ее»
YO = {w.replace("ё", "е"): w for w in """
ещё её моё твоё своё неё нём чём причём о_чём всё-таки идёт пойдёт придёт найдёт начнёт ждёт живёт
берёт даёт зовёт поёт ведёт несёт растёт уснёт пьёт льёт бьёт жёлтый жёлтая жёлтое зелёный зелёная
зелёное тёплый тёплая тёплое тёплые лёгкий лёгкая лёгкое чёрный чёрная чёрное тёмный тёмная тёмное
твёрдый счёт отчёт учёт расчёт полёт самолёт вертолёт звёзды звёзд пёс лёд мёд сёстры шёл пришёл ушёл
нашёл пошёл зашёл подошёл прошёл учёный учёные включён подключён отключён сохранён решён завершён
определён четвёртый четвёртая четвёртое трёх трём четырёх вперёд приём объём подъём днём дождём
огнём путём ещё-то клёво щёки ёлка ёж ёжик тётя дядёк орёл озёра озёрный слёзы тёща шёпот шёпотом
расчёска пчёлы свёкла бельё жильё питьё ружьё копьё сырьё
""".split()}
_VSE_YO = re.compile(r"\b([Вв])се(?=\s*[.!?…]|\s*$|\s+(?:равно|готово|хорошо|понятно|в порядке|ещё|еще|"
                     r"сделал|сделано|верно|отлично|нормально|будет|получилось|ясно|просто|время|"
                     r"правильно|сказал|работает|закрыто|открыто|включено|выключено)\b)")


def restore_yo(t: str) -> str:
    t = _VSE_YO.sub(lambda m: m.group(1) + "сё", t)
    t = re.sub(r"\b(вот|это|и)\s+все\b(?=\s*[.!?,]|$)", r"\1 всё", t, flags=re.I)

    def rep(m):
        w = m.group(0)
        low = w.lower()
        if low in YO:
            r = YO[low]
            return r[0].upper() + r[1:] if w[0].isupper() else r
        return w
    return re.sub(r"[А-Яа-яЁё-]+", rep, t)


# ударения, которые голос ставит неправильно (дополняется по проверке в сборке).
# Знак «+» перед ударной гласной; в текст для голоса идёт как U+0301 после гласной.
STRESS = {w.replace("+", ""): w for w in """
""".split()}
_ACUTE = "\u0301"


def add_stress(t: str) -> str:
    def rep(m):
        w = m.group(0)
        low = w.lower()
        mark = STRESS.get(low)
        if not mark:
            return w
        i = mark.index("+")
        return w[:i + 1] + _ACUTE + w[i + 1:]
    return re.sub(r"[А-Яа-яЁё]+", rep, t)


def prepare(text: str, accents=False) -> str:
    t = text or ""
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    t = re.sub(r"[«»\"“”„*_#`~|<>\[\]{}]", "", t)
    t = t.replace("…", ".").replace("—", ", ").replace("–", ", ").replace(" - ", ", ")
    for k, v in SYMBOLS.items():
        t = t.replace(k, v)
    for k, v in ABBR.items():
        t = re.sub(rf"(?<![\w]){re.escape(k)}(?![\w])", v, t)
    # время 12:05 -> «двенадцать ноль пять»
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: number_words(int(m.group(1))) + " " +
               ("ноль " + UNITS[int(m.group(2))] if m.group(2).startswith("0") and m.group(2) != "00"
                else ("ровно" if m.group(2) == "00" else number_words(int(m.group(2))))), t)
    # проценты
    t = re.sub(r"(\d+)\s*%", lambda m: number_words(int(m.group(1))) + " " +
               plural(int(m.group(1)), "процент", "процента", "процентов"), t)
    t = re.sub(r"(\d+)\s+(процент\w*)", lambda m: number_words(int(m.group(1))) + " " +
               plural(int(m.group(1)), "процент", "процента", "процентов"), t)
    # десятичные: 3,5 / 3.5
    t = re.sub(r"(\d+)[.,](\d+)", lambda m: number_words(int(m.group(1))) + " целых " +
               number_words(int(m.group(2))), t)
    t = re.sub(r"\d+", lambda m: number_words(int(m.group(0))), t)
    t = re.sub(r"[A-Za-z][A-Za-z'\-]*", _latin_word, t)
    t = restore_yo(t)
    if accents:
        t = add_stress(t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"([,.!?]){2,}", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    if t and t[-1] not in ".!?":
        t += "."
    if t:
        t = t[0].upper() + t[1:]
    return t
