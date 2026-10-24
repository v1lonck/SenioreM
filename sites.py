"""Как открыть то, что назвали голосом: сайт по русскому названию, установленную
программу из меню «Пуск» или, в крайнем случае, первый результат поиска."""
import os
import re
from pathlib import Path

# (основы слов, адрес, сначала искать программу на компьютере)
SITES = [
    (("яндекс", "музык"), "https://music.yandex.ru", False),
    (("яндекс", "карт"), "https://yandex.ru/maps", False),
    (("яндекс", "почт"), "https://mail.yandex.ru", False),
    (("яндекс", "диск"), "https://disk.yandex.ru", False),
    (("яндекс", "маркет"), "https://market.yandex.ru", False),
    (("яндекс", "переводч"), "https://translate.yandex.ru", False),
    (("яндекс", "погод"), "https://yandex.ru/pogoda", False),
    (("яндекс", "еда"), "https://eda.yandex.ru", False),
    (("яндекс", "лавк"), "https://lavka.yandex.ru", False),
    (("яндекс", "браузер"), "https://browser.yandex.ru", True),
    (("яндекс",), "https://ya.ru", False),
    (("гугл", "переводч"), "https://translate.google.com", False),
    (("гугл", "диск"), "https://drive.google.com", False),
    (("гугл", "карт"), "https://maps.google.com", False),
    (("гугл", "почт"), "https://mail.google.com", False),
    (("гугл", "документ"), "https://docs.google.com", False),
    (("гугл", "таблиц"), "https://sheets.google.com", False),
    (("джимейл",), "https://mail.google.com", False),
    (("гугл",), "https://www.google.com", False),
    (("ютуб", "музык"), "https://music.youtube.com", False),
    (("ютуб",), "https://www.youtube.com", False),
    (("ютюб",), "https://www.youtube.com", False),
    (("рутуб",), "https://rutube.ru", False),
    (("вк", "музык"), "https://vk.com/audio", False),
    (("вконтакт",), "https://vk.com", False),
    (("вк",), "https://vk.com", False),
    (("одноклассник",), "https://ok.ru", False),
    (("телеграм",), "https://web.telegram.org", True),
    (("дискорд",), "https://discord.com/app", True),
    (("стим",), "https://store.steampowered.com", True),
    (("спотифай",), "https://open.spotify.com", True),
    (("вотсап",), "https://web.whatsapp.com", True),
    (("ватсап",), "https://web.whatsapp.com", True),
    (("твич",), "https://www.twitch.tv", False),
    (("тикток",), "https://www.tiktok.com", False),
    (("тик", "ток"), "https://www.tiktok.com", False),
    (("инстаграм",), "https://www.instagram.com", False),
    (("фейсбук",), "https://www.facebook.com", False),
    (("твиттер",), "https://x.com", False),
    (("википеди",), "https://ru.wikipedia.org", False),
    (("авито",), "https://www.avito.ru", False),
    (("озон",), "https://www.ozon.ru", False),
    (("вайлдбер",), "https://www.wildberries.ru", False),
    (("валдбер",), "https://www.wildberries.ru", False),
    (("вайлдбер",), "https://www.wildberries.ru", False),
    (("госуслуг",), "https://www.gosuslugi.ru", False),
    (("сбер",), "https://online.sberbank.ru", False),
    (("тинькофф",), "https://www.tbank.ru", False),
    (("т", "банк"), "https://www.tbank.ru", False),
    (("алиэкспресс",), "https://aliexpress.ru", False),
    (("али", "экспресс"), "https://aliexpress.ru", False),
    (("гитхаб",), "https://github.com", False),
    (("чат", "гпт"), "https://chatgpt.com", False),
    (("клод",), "https://claude.ai", False),
    (("нетфликс",), "https://www.netflix.com", False),
    (("кинопоиск",), "https://www.kinopoisk.ru", False),
    (("иви",), "https://www.ivi.ru", False),
    (("окко",), "https://okko.tv", False),
    (("мейл",), "https://e.mail.ru", False),
    (("дзен",), "https://dzen.ru", False),
    (("хабр",), "https://habr.com", False),
    (("пинтерест",), "https://www.pinterest.com", False),
    (("амазон",), "https://www.amazon.com", False),
    (("новост",), "https://dzen.ru/news", False),
    (("погод",), "https://yandex.ru/pogoda", False),
    (("карт",), "https://yandex.ru/maps", False),
    (("переводч",), "https://translate.yandex.ru", False),
]
SITES.sort(key=lambda s: -len(s[0]))

ALIASES = {
    "телеграм": "telegram", "телеграмм": "telegram", "дискорд": "discord", "ютуб": "youtube",
    "спотифай": "spotify", "вотсап": "whatsapp", "ватсап": "whatsapp", "ворд": "word",
    "эксель": "excel", "хром": "chrome", "гугл хром": "chrome", "эдж": "edge",
    "файрфокс": "firefox", "фаерфокс": "firefox", "опера": "opera", "стим": "steam",
    "зум": "zoom", "вайбер": "viber", "скайп": "skype", "фотошоп": "photoshop",
    "яндекс": "yandex", "яндекс браузер": "yandex", "вк": "vk", "вконтакте": "vk",
    "обс": "obs", "майнкрафт": "minecraft", "кс": "counter strike", "контра": "counter strike", "дота": "dota", "аюграм": "ayugram",
    "пауэрпоинт": "powerpoint", "повер поинт": "powerpoint", "аутлук": "outlook",
    "вижуал студио": "visual studio", "вс код": "visual studio code", "эпик": "epic games",
    "эпик геймс": "epic games", "юнити": "unity", "блендер": "blender", "торрент": "torrent",
    "утоппент": "utorrent", "ватсапп": "whatsapp", "лаунчер": "launcher", "роблокс": "roblox",
    "фортнайт": "fortnite", "валорант": "valorant", "батл нет": "battle.net",
    "тим спик": "teamspeak", "энидеск": "anydesk", "тимвьюер": "teamviewer",
    "осу": "osu", "оса": "osu", "яндекс музыка": "yandex music", "яндекс музыку": "yandex music",
    "кап кат": "capcut", "капкат": "capcut", "нотпад": "notepad", "гит": "git",
}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n",
                     "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y",
                     "", "e", "yu", "ya"]))
FILLER = {"сайт", "сайте", "страницу", "мне", "пожалуйста", "приложение", "программу", "ка"}


def translit(text):
    return "".join(TRANSLIT.get(c, c) for c in text)


def clean(name: str) -> str:
    return " ".join(w for w in name.lower().replace("ё", "е").split() if w not in FILLER)


def _base(word):
    """Грубо убираем падежные окончания: «музыку» -> «музык», «телеграмме» -> «телеграм»."""
    for end in ("ами", "ями", "ому", "ему", "ой", "ей", "ую", "юю", "ах", "ях", "ом", "ем",
                "у", "ю", "е", "ы", "и", "а", "я"):
        if len(word) > len(end) + 2 and word.endswith(end):
            return word[: -len(end)]
    return word


def find_site(name: str):
    """-> (url, prefer_app) или None."""
    words = clean(name).split()
    if not words:
        return None
    joined = "".join(words)
    m = re.fullmatch(r"([a-zа-я0-9-]+(?:\s*(?:точка|\.)\s*[a-zа-я0-9-]+)+)", " ".join(words))
    if m and ("точка" in joined or "." in joined):
        dom = re.sub(r"\s*(точка|\.)\s*", ".", m.group(1))
        dom = translit(dom) if re.search("[а-я]", dom.split(".")[-1]) else dom
        dom = dom.replace(".ru", ".ru").replace(".kom", ".com")
        return "https://" + dom, False
    for stems, url, prefer_app in SITES:
        if all(any(w.startswith(s) or _base(w).startswith(s) for w in words) for s in stems):
            if len(stems) == 1 and len(stems[0]) <= 2 and stems[0] not in words:
                continue  # «вк», «т» — только целым словом
            return url, prefer_app
    return None


# ---------------- установленные программы ----------------
import threading
import time
from difflib import SequenceMatcher

_apps = []            # [(нормализованное имя, исходное имя, ("lnk", путь) | ("app", AppID))]
_apps_time = 0.0
_apps_lock = threading.Lock()
SKIP = ("uninstall", "удал", "readme", "help", "справк", "website", "веб-сайт", "seniorem",
        "documentation", "release notes", "changelog", "license", "лиценз")


def _norm(name: str) -> str:
    name = name.lower().replace("ё", "е")
    name = re.sub(r"\(.*?\)", " ", name)
    return " ".join(re.sub(r"[^a-zа-я0-9]+", " ", name).split())


def _shortcut_dirs():
    env = os.environ
    dirs = []
    for root, sub in ((env.get("APPDATA"), r"Microsoft\Windows\Start Menu\Programs"),
                      (env.get("ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                      (env.get("USERPROFILE"), "Desktop"),
                      (env.get("USERPROFILE"), r"OneDrive\Desktop"),
                      (env.get("PUBLIC"), "Desktop")):
        if root:
            d = Path(root) / sub
            if d.is_dir():
                dirs.append(d)
    return dirs


def _scan_shortcuts():
    out = []
    for d in _shortcut_dirs():
        for p in d.rglob("*"):
            if p.suffix.lower() in (".lnk", ".url", ".appref-ms"):
                out.append((p.stem, ("lnk", str(p))))
    return out


def _scan_start_apps():
    """Все приложения меню «Пуск», включая приложения из Microsoft Store."""
    import json
    import subprocess
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                           capture_output=True, timeout=20, creationflags=0x08000000)
        data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
        if isinstance(data, dict):
            data = [data]
        return [(d["Name"], ("app", d["AppID"])) for d in data if d.get("Name") and d.get("AppID")]
    except Exception:  # noqa: BLE001
        return []


def refresh_apps(force=False):
    global _apps, _apps_time
    with _apps_lock:
        if not force and _apps and time.time() - _apps_time < 600:
            return _apps
        items = {}
        for name, target in _scan_start_apps() + _scan_shortcuts():
            n = _norm(name)
            if not n or any(k in n for k in SKIP):
                continue
            items.setdefault(n, (n, name, target))
        _apps = list(items.values())
        _apps_time = time.time()
        return _apps


def warm():
    """Заранее собирает список программ в фоне, чтобы «открой …» срабатывало мгновенно."""
    threading.Thread(target=refresh_apps, daemon=True).start()


def keys_for(name: str):
    n = clean(name)
    keys = {n, translit(n), ALIASES.get(n, ""), ALIASES.get(_base(n), "")}
    for w in n.split():
        keys |= {ALIASES.get(w, ""), ALIASES.get(_base(w), "")}
        if len(w) >= 4:
            keys |= {_base(w), translit(_base(w))}
    return {_norm(k) for k in keys if len(_norm(k)) >= 2}


def _score(key: str, app: str) -> float:
    if key == app:
        return 1.0
    flat_k, flat_a = key.replace(" ", ""), app.replace(" ", "")
    if flat_k == flat_a:
        return 0.98
    words = app.split()
    if key in words or (len(flat_k) >= 3 and flat_a.startswith(flat_k)):
        return 0.92 - 0.01 * max(0, len(words) - 1)
    if len(flat_k) >= 4 and flat_k in flat_a:
        return 0.85 - 0.01 * max(0, len(words) - 1)
    best = SequenceMatcher(None, flat_k, flat_a).ratio()
    for w in words:
        if len(w) >= 3:
            best = max(best, SequenceMatcher(None, flat_k, w).ratio() - 0.04)
    return best


def find_program(name: str):
    """-> (исходное имя, ("lnk", путь) | ("app", AppID)) или None."""
    keys = keys_for(name)
    if not keys:
        return None
    best, best_score = None, 0.0
    for n, orig, target in refresh_apps():
        sc = max(_score(k, n) for k in keys)
        if sc > best_score:
            best, best_score = (orig, target), sc
    return best if best_score >= 0.8 else None


def launch(target):
    kind, value = target
    if kind == "app":
        os.startfile("shell:AppsFolder\\" + value)  # type: ignore[attr-defined]
    else:
        os.startfile(value)  # type: ignore[attr-defined]
