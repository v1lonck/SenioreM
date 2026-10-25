"""Живые данные из интернета: погода в вашем городе, курсы валют, поиск свежей информации.
Всё бесплатно и без ключей: Open-Meteo (погода), ЦБ РФ (курсы), DuckDuckGo (поиск)."""
import datetime
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SenioreM"}
_cache = {}
_lock = threading.Lock()

WEATHER = {0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман",
           48: "изморозь", 51: "морось", 53: "морось", 55: "сильная морось",
           61: "небольшой дождь", 63: "дождь", 65: "ливень", 66: "ледяной дождь",
           67: "ледяной дождь", 71: "небольшой снег", 73: "снег", 75: "сильный снег",
           77: "снежная крупа", 80: "ливень", 81: "ливень", 82: "сильный ливень",
           85: "снегопад", 86: "сильный снегопад", 95: "гроза", 96: "гроза с градом",
           99: "гроза с градом"}


def _get(url, timeout=10, raw=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data.decode("utf-8", "ignore") if raw else json.loads(data)


def _cached(key, ttl, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


# ------------------------------------------------------------------ город
def search_cities(name, count=6):
    """-> [{name, region, country, lat, lon}] — для выбора города в настройках."""
    data = _get("https://geocoding-api.open-meteo.com/v1/search?language=ru&count=%d&name=%s"
                % (count, urllib.parse.quote(name.strip())))
    out = []
    for r in data.get("results") or []:
        out.append({"name": r.get("name", ""), "region": r.get("admin1", ""),
                    "country": r.get("country", ""), "lat": r["latitude"], "lon": r["longitude"]})
    return out


def location(appearance):
    """Город из настроек (с координатами) или определённый по интернет-адресу."""
    city = (appearance.get("city") or "").strip()
    lat, lon = appearance.get("city_lat"), appearance.get("city_lon")
    if city and lat is not None and lon is not None:
        return city, lat, lon
    if city:
        found = _cached("geo:" + city.lower(), 86400, lambda: search_cities(city, 1))
        if found:
            return found[0]["name"], found[0]["lat"], found[0]["lon"]
    ip = _cached("ip", 3600, lambda: _get("https://ipwho.is/?lang=ru"))
    return ip.get("city", ""), ip["latitude"], ip["longitude"]


# ------------------------------------------------------------------ погода
def weather(appearance):
    city, lat, lon = location(appearance)

    def fetch():
        return _get("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                    "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,"
                    "relative_humidity_2m,precipitation"
                    "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
                    "precipitation_probability_max&forecast_days=3"
                    "&wind_speed_unit=ms&timezone=auto" % (lat, lon))
    data = _cached(f"wx:{lat:.2f},{lon:.2f}", 600, fetch)
    data["_city"] = city
    return data


def _deg(t, word=False):
    t = round(t)
    sign = "плюс " if t > 0 else ("минус " if t < 0 else "")
    if not word:
        return f"{sign}{abs(t)}"
    from speechtext import plural
    return f"{sign}{abs(t)} {plural(abs(t), 'градус', 'градуса', 'градусов')}"


def weather_phrase(appearance, day="now"):
    d = weather(appearance)
    city = d.get("_city") or "вашем городе"
    if day == "now":
        c = d["current"]
        return (f"В городе {city} сейчас {_deg(c['temperature_2m'], True)}, "
                f"{WEATHER.get(int(c['weather_code']), '').strip()}. Ощущается как "
                f"{_deg(c['apparent_temperature'])}, ветер {round(c['wind_speed_10m'])} м/с.")
    i = 1 if day == "tomorrow" else 0
    dl = d["daily"]
    word = "Завтра" if i else "Сегодня"
    rain = dl.get("precipitation_probability_max", [None] * 3)[i]
    from speechtext import plural
    tail = (f" Вероятность осадков {rain} {plural(rain, 'процент', 'процента', 'процентов')}."
            if rain is not None else "")
    return (f"{word} в городе {city} от {_deg(dl['temperature_2m_min'][i])} до "
            f"{_deg(dl['temperature_2m_max'][i], True)}, "
            f"{WEATHER.get(int(dl['weather_code'][i]), '')}.{tail}")


# ------------------------------------------------------------------ курсы валют
CURRENCIES = {"USD": ("доллар", "доллара"), "EUR": ("евро", "евро"), "CNY": ("юань", "юаня"),
              "GBP": ("фунт", "фунта"), "KZT": ("тенге", "тенге"), "BYN": ("белорусский рубль",
                                                                         "белорусского рубля"),
              "TRY": ("лира", "лиры"), "JPY": ("иена", "иены")}


def rates():
    return _cached("cbr", 1800, lambda: _get("https://www.cbr-xml-daily.ru/daily_json.js"))


def rate_phrase(code="USD"):
    data = rates()
    v = data["Valute"].get(code)
    if not v:
        return "Не нашёл такую валюту."
    per = v["Value"] / v["Nominal"]
    name = CURRENCIES.get(code, (code, code))[1]
    rub, kop = int(per), round((per - int(per)) * 100)
    from speechtext import plural
    return (f"Курс {name} по ЦБ — {rub} {plural(rub, 'рубль', 'рубля', 'рублей')} "
            f"{kop} {plural(kop, 'копейка', 'копейки', 'копеек')}.")


# ------------------------------------------------------------------ поиск
def _ddg(query, n):
    page = _get("https://html.duckduckgo.com/html/?kl=ru-ru&q=" + urllib.parse.quote(query),
                timeout=8, raw=True)
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', page, flags=re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', page, flags=re.S)
    return [(_clean(t), _clean(sn)) for t, sn in zip(titles, snippets)][:n]


def _clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    s = s.replace("\u0301", "").replace("\u0300", "")        # значки ударения
    s = re.sub(r"\s*\((?:англ|лат|нем|фр|исп|итал|произносится)[^()]*(?:\([^()]*\)[^()]*)*\)", "", s)
    s = re.sub(r"\s*\[[^\]]*\]", "", s)                       # транскрипции и сноски
    return re.sub(r"\s{2,}", " ", s).strip()


def _wiki(query, n):
    """Википедия: определения, факты, люди, места."""
    data = _get("https://ru.wikipedia.org/w/api.php?action=query&list=search&format=json"
                "&utf8=1&srlimit=%d&srsearch=%s" % (n, urllib.parse.quote(query)), timeout=8)
    hits = data.get("query", {}).get("search", [])
    out = []
    if hits:
        title = hits[0]["title"]
        ext = _get("https://ru.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1"
                   "&explaintext=1&exsentences=3&format=json&utf8=1&titles="
                   + urllib.parse.quote(title), timeout=8)
        for page in ext.get("query", {}).get("pages", {}).values():
            if page.get("extract"):
                out.append((_clean(title), _clean(page["extract"])))
    for h in hits[1:n]:
        out.append((h["title"], _clean(h.get("snippet", ""))))
    return out


def _news(query, n):
    """Свежие новости (Google News RSS)."""
    page = _get("https://news.google.com/rss/search?hl=ru&gl=RU&ceid=RU:ru&q="
                + urllib.parse.quote(query), timeout=8, raw=True)
    items = re.findall(r"<item>(.*?)</item>", page, flags=re.S)
    out = []
    for it in items[:n]:
        title = _clean(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.findall(r"<title>(.*?)</title>", it, re.S) or [""])[0]))
        date = (re.findall(r"<pubDate>(.*?)</pubDate>", it, re.S) or [""])[0][:16]
        if title:
            out.append((date, title))
    return out


NEWSY = re.compile(r"новост|сегодня|вчера|случилось|происходит|сч[её]т|матч|выиграл|победил|"
                   r"выбор|курс|цена|стоит|вышел|вышла|релиз|когда выйдет|последн|недавно|"
                   r"на этой неделе|\b20[2-3]\d\b")


def web_search(query, n=4):
    """Выдержки из интернета: [(заголовок, текст)]. Несколько источников по очереди."""
    def fetch():
        out = []
        for fn in ((_news, _ddg, _wiki) if NEWSY.search(query.lower()) else (_ddg, _wiki, _news)):
            try:
                out += fn(query, n)
            except Exception:  # noqa: BLE001 — источник недоступен, берём следующий
                continue
            if len(out) >= 2:
                break
        return out[:n + 1]
    return _cached("q:" + query.lower(), 900, fetch)


FRESH = re.compile(
    r"новост|курс|сегодня|сейчас|вчера|завтра|последн|сч[её]т|матч|выиграл|победил|цена|стоит|"
    r"сколько стоит|кто сейчас|президент|премьер|вышел|вышла|релиз|когда выйдет|случилось|"
    r"происходит|обновлени|акци|биткоин|bitcoin|нефть|золото|рейтинг|чемпион|турнир|выбор|"
    r"\b20[2-3]\d\b|актуальн|свеж|недавно|в этом году|на этой неделе")
WEATHERY = re.compile(r"погод|градус|температур|холодно|тепло|дожд|снег|ветер|зонт|одеться|оденься")


def build_context(question, appearance):
    """Свежие данные для ИИ: время, погода у вас, курсы и выдержки из интернета."""
    parts = []
    now = datetime.datetime.now()
    parts.append(f"Сейчас {now:%d.%m.%Y}, {now:%H:%M}.")
    q = question.lower()
    try:
        city, _lat, _lon = location(appearance)
        if city:
            parts.append(f"Пользователь находится в городе {city}.")
        if WEATHERY.search(q) or "погод" in q:
            d = weather(appearance)
            c = d["current"]
            parts.append(f"ТЕМПЕРАТУРА НА УЛИЦЕ СЕЙЧАС: {_deg(c['temperature_2m'], True)} "
                         f"({WEATHER.get(int(c['weather_code']), '')}, ветер "
                         f"{round(c['wind_speed_10m'])} м/с).")
            if "завтра" in q:
                parts.append(weather_phrase(appearance, "tomorrow"))
            elif re.search(r"сегодня|вечер|днем|днём|ночью|будет", q):
                parts.append(weather_phrase(appearance, "today"))
    except Exception:  # noqa: BLE001
        pass
    if re.search(r"курс|доллар|евро|юан|валют|рубл", q):
        try:
            parts += [rate_phrase(c) for c in ("USD", "EUR", "CNY")]
        except Exception:  # noqa: BLE001
            pass
    if FRESH.search(q) and not (WEATHERY.search(q) and len(q.split()) < 8):
        try:
            for title, snip in web_search(question):
                parts.append(f"— {title}: {snip}")
        except Exception:  # noqa: BLE001
            pass
    text = "\n".join(parts)
    return text[:1800]


def quick_answer(question):
    """Ответ без ИИ: первая выдержка из поиска."""
    try:
        res = web_search(question, 2)
    except Exception:  # noqa: BLE001
        return "Не получилось поискать в интернете. Проверьте подключение."
    if not res:
        return "Ничего не нашёл. Попробуйте спросить иначе."
    title, snip = res[0]
    if re.match(r"^\w{3}, \d", title):            # новость: (дата, заголовок)
        return "Вот что пишут: " + "; ".join(t for _d, t in res[:2]) + "."
    parts = re.split(r"(?<=[.!?])\s", snip)
    return " ".join(parts[:2]) if snip else title
