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


def _deg(t):
    t = round(t)
    return f"{'плюс ' if t > 0 else ('минус ' if t < 0 else '')}{abs(t)}"


def weather_phrase(appearance, day="now"):
    d = weather(appearance)
    city = d.get("_city") or "вашем городе"
    if day == "now":
        c = d["current"]
        return (f"В городе {city} сейчас {_deg(c['temperature_2m'])} градусов, "
                f"{WEATHER.get(int(c['weather_code']), '').strip()}. Ощущается как "
                f"{_deg(c['apparent_temperature'])}, ветер {round(c['wind_speed_10m'])} м/с.")
    i = 1 if day == "tomorrow" else 0
    dl = d["daily"]
    word = "Завтра" if i else "Сегодня"
    rain = dl.get("precipitation_probability_max", [None] * 3)[i]
    tail = f" Вероятность осадков {rain} процентов." if rain is not None else ""
    return (f"{word} в городе {city} от {_deg(dl['temperature_2m_min'][i])} до "
            f"{_deg(dl['temperature_2m_max'][i])} градусов, "
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
    return f"Курс {name} по ЦБ — {rub} рублей {kop} копеек."


# ------------------------------------------------------------------ поиск
def web_search(query, n=4):
    """Короткие выдержки из поиска DuckDuckGo: [(заголовок, текст)]."""
    def fetch():
        page = _get("https://html.duckduckgo.com/html/?kl=ru-ru&q=" + urllib.parse.quote(query),
                    timeout=10, raw=True)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', page, flags=re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, flags=re.S)
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()  # noqa: E731
        out = []
        for t, sn in zip(titles, snippets):
            if "ad_domain" in t:
                continue
            out.append((clean(t), clean(sn)))
        return out[:n]
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
            parts.append(weather_phrase(appearance, "now"))
            parts.append(weather_phrase(appearance, "today"))
            parts.append(weather_phrase(appearance, "tomorrow"))
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
    snip = re.split(r"(?<=[.!?])\s", snip)
    return " ".join(snip[:2]) if snip else title
