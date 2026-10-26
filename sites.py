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
    (("телег",), "https://web.telegram.org", True),
    (("тг",), "https://web.telegram.org", True),
    (("дс",), "https://discord.com/app", True),
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
    "осу": "osu", "оса": "osu", "озу": "osu", "оза": "osu", "осю": "osu", "ozu": "osu", "запрет": "zapret", "запрета": "zapret",
    "тг": "telegram", "телега": "telegram", "телегу": "telegram", "дс": "discord",
    "дискордик": "discord", "ютубчик": "youtube", "хромчик": "chrome", "стимчик": "steam",
    "вкшку": "vk", "вкшка": "vk", "ворлд оф танкс": "world of tanks", "танки": "world of tanks",
    "доту": "dota", "кску": "counter strike", "контру": "counter strike", "впн": "vpn",
    "блюстакс": "bluestacks", "саундпад": "soundpad", "саунпад": "soundpad", "саунд пад": "soundpad",
    "соундпад": "soundpad", "амонг ас": "among us", "геншин": "genshin", "яндекс музыка": "yandex music", "яндекс музыку": "yandex music",
    "ведьмак": "witcher", "ведьмака": "witcher", "гта": "grand theft auto",
    "гта5": "grand theft auto v", "гта 5": "grand theft auto v", "гта пять": "grand theft auto v",
    "гтав": "grand theft auto v", "gta5": "grand theft auto v", "gta 5": "grand theft auto v",
    "гта 4": "grand theft auto iv", "гта сан андреас": "san andreas", "самп": "samp",
    "обход": "zapret", "обход дискорда": "zapret", "обход блокировок": "zapret",
    "обход дс": "zapret", "обход ютуба": "zapret", "запрет дискорд": "zapret", "пабг": "pubg",
    "пубг": "pubg", "кс го": "counter strike", "майн": "minecraft", "симс": "sims",
    "фифа": "fifa", "кап кат": "capcut", "капкат": "capcut", "нотпад": "notepad", "гит": "git",
    # точное распознавание иногда пишет короткие названия латиницей
    "ks": "counter strike", "cs": "counter strike", "cs2": "counter strike", "cs 2": "counter strike",
    "ks2": "counter strike", "ks 2": "counter strike", "csgo": "counter strike", "cs go": "counter strike",
    "ks go": "counter strike", "кс2": "counter strike", "кс 2": "counter strike", "кс два": "counter strike",
    "ксго": "counter strike", "контр страйк": "counter strike", "каунтер страйк": "counter strike",
    "dota": "dota", "dota 2": "dota", "gta": "grand theft auto", "ds": "discord", "tg": "telegram",
}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n",
                     "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y",
                     "", "e", "yu", "ya"]))
FILLER = {"сайт", "сайте", "страницу", "мне", "пожалуйста", "приложение", "программу", "ка",
          "игру", "игра", "игрушку", "поиграть", "в", "во"}


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


_REV = None


def _ru_words(words):
    """Латинские названия -> русские: «youtube» -> «ютуб», «telegram» -> «телеграм»."""
    global _REV
    if _REV is None:
        _REV = {}
        for ru, en in ALIASES.items():
            _REV.setdefault(en.replace(" ", ""), ru)
        _REV.update({"youtube": "ютуб", "ютуб": "ютуб", "vk": "вк", "vkontakte": "вконтакте",
                     "google": "гугл", "twitch": "твич", "tiktok": "тикток", "instagram": "инстаграм",
                     "github": "гитхаб", "wikipedia": "википедия", "netflix": "нетфликс",
                     "rutube": "рутуб", "gmail": "джимейл", "chatgpt": "чат гпт", "avito": "авито",
                     "ozon": "озон", "wildberries": "вайлдберриз", "pinterest": "пинтерест",
                     "twitter": "твиттер", "facebook": "фейсбук", "kinopoisk": "кинопоиск"})
    out = []
    for w in words:
        key = re.sub(r"[^a-z0-9]", "", w.lower())
        out.append(_REV.get(key, w) if key else w)
    return " ".join(out).split()


def find_site(name: str):
    """-> (url, prefer_app) или None."""
    words = clean(name).split()
    if not words:
        return None
    if re.search("[a-z]", " ".join(words)):
        words = _ru_words(words)
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


# ---------------- установленные и скачанные программы ----------------
import subprocess
import threading
import time
from difflib import SequenceMatcher

_apps = []            # [(нормализованное имя, исходное имя, ("lnk"|"app"|"path", значение))]
_apps_time = 0.0
_apps_lock = threading.Lock()
_local = []           # папки и программы в Загрузках, на Рабочем столе, в Документах
_local_time = 0.0
SKIP = ("uninstall", "удал", "readme", "help", "справк", "website", "веб сайт", "seniorem",
        "documentation", "release notes", "changelog", "license", "лиценз", "unins")
NO_WINDOW = 0x08000000

# Папки Windows, которые встречаются в AppID приложений меню «Пуск»
KNOWN_FOLDERS = {
    "{6D809377-6AF0-444B-8957-A3773F02200E}": "ProgramW6432",       # Program Files
    "{905E63B6-C1BF-494E-B29C-65B732D3D21A}": "ProgramFiles",
    "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}": "ProgramFiles(x86)",
    "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}": "LOCALAPPDATA",
    "{3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}": "APPDATA",
    "{5E6C858F-0E22-4760-9AFE-EA3317B67173}": "USERPROFILE",
    "{F38BF404-1D43-42F2-9305-67DE0B28FC23}": "SystemRoot",
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": "SYSTEM32",
    "{D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27}": "SYSWOW64",
}


def _norm(name: str) -> str:
    name = name.lower().replace("ё", "е")
    name = re.sub(r"\(.*?\)", " ", name)
    return " ".join(re.sub(r"[^a-zа-я0-9]+", " ", name).split())


def _env_path(var):
    if var == "SYSTEM32":
        return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if var == "SYSWOW64":
        return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64")
    return os.environ.get(var, "")


def _appid_ok(appid: str) -> bool:
    """AppID вида «{GUID}\\путь\\program.exe» или «C:\\…\\program.exe» — проверяем, что файл есть.
    Битые записи (программу удалили) пропускаем — иначе Windows показывает ошибку."""
    if "!" in appid:                      # приложение из Microsoft Store
        return True
    m = re.match(r"^(\{[0-9A-Fa-f-]{36}\})\\(.+)$", appid)
    if m:
        base = _env_path(KNOWN_FOLDERS.get(m.group(1).upper(), ""))
        return bool(base) and os.path.exists(os.path.join(base, m.group(2)))
    if re.match(r"^[A-Za-z]:\\", appid):
        return os.path.exists(appid)
    return True                           # обычный идентификатор приложения


_shell = None


def _lnk_info(path: str):
    """-> (цель, аргументы) ярлыка."""
    global _shell
    try:
        if _shell is None:
            import comtypes.client
            _shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
        sc = _shell.CreateShortcut(path)
        return str(sc.TargetPath or ""), str(sc.Arguments or "")
    except Exception:  # noqa: BLE001
        return "", ""


def _lnk_target(path: str) -> str:
    return _lnk_info(path)[0]


# Ярлыки Android-приложений из эмуляторов (BlueStacks создаёт «Telegram», «Roblox»…):
# их не путаем с настоящими программами — только если прямо сказали «в блюстаксе».
EMU_MARKERS = ("bluestacks", "hd-player", "hd-runapp", "memu", "nox.exe", "noxvm", "ldplayer",
               "dnplayer", "mumu", "gameloop", "androidemulator", "launchapp")
EMU_TAG = "bluestacks"


def _is_emulated(name: str, target) -> bool:
    if any(m in name.lower() for m in ("bluestacks", "memu", "nox", "ldplayer", "mumu", "gameloop")):
        return False                         # это сам эмулятор
    kind, value = target
    text = value
    if kind == "lnk" and value.lower().endswith(".lnk"):
        text = " ".join((value,) + _lnk_info(value))
    low = text.lower()
    return any(m in low for m in EMU_MARKERS)


def _lnk_ok(path: str) -> bool:
    if not path.lower().endswith(".lnk"):
        return True
    target = _lnk_target(path)
    if not target:                        # «объявленные» ярлыки установщиков — цели не видно
        return True
    if target.lower().startswith(("http:", "https:", "steam:", "com.epicgames")):
        return True
    return os.path.exists(target)


def _shortcut_dirs():
    env = os.environ
    dirs = []
    for root, sub in ((env.get("APPDATA"), r"Microsoft\Windows\Start Menu\Programs"),
                      (env.get("ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                      (env.get("USERPROFILE"), "Desktop"),
                      (env.get("USERPROFILE"), r"OneDrive\Desktop"),
                      (env.get("OneDrive"), "Desktop"),
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
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                           capture_output=True, timeout=20, creationflags=NO_WINDOW)
        data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
        if isinstance(data, dict):
            data = [data]
        return [(d["Name"], ("app", d["AppID"])) for d in data if d.get("Name") and d.get("AppID")]
    except Exception:  # noqa: BLE001
        return []


_apps_full = []       # [(норм. имя, имя, цель, источник)]


def refresh_apps(force=False):
    """Все программы и игры компьютера. Сначала мгновенно из кэша, затем свежий список."""
    global _apps, _apps_time, _apps_full
    with _apps_lock:
        if not force and _apps and time.time() - _apps_time < 600:
            return _apps
        if not _apps and not force:
            cached = _load_index()
            if cached:
                _apps_full = cached
                _apps = [(n, o, t) for n, o, t, _s in cached]
                _feed_vocab()
                _apps_time = time.time() - 540     # обновим в фоне через минуту
                return _apps
        items = {}
        sources = ([(n, t, "Ярлык") for n, t in _scan_shortcuts()] + _scan_steam() + _scan_epic()
                   + _scan_gog() + [(n, t, "Пуск") for n, t in _scan_start_apps()]
                   + _scan_uninstall())
        for name, target, src in sources:
            n = _norm(name)
            if not n or any(k in n for k in SKIP):
                continue
            if _is_emulated(name, target):
                n, name, src = f"{n} {EMU_TAG}", f"{name} (BlueStacks)", "Эмулятор"
            if n in items:
                continue
            if target[0] == "lnk":
                ok = _lnk_ok(target[1])
            elif target[0] == "app":
                ok = _appid_ok(target[1])
            else:
                ok = True
            if ok:
                items[n] = (n, name, target, src)
        _apps_full = list(items.values())
        _apps = [(n, o, t) for n, o, t, _s in _apps_full]
        _apps_time = time.time()
        _save_index(_apps_full)
        _feed_vocab()
        return _apps


# ---------------- игры: Steam, Epic Games, GOG и все установленные программы ----------------
def _reg_value(root, path, name):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:  # noqa: BLE001
        return None


def _steam_root():
    import winreg
    for root, path, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
        v = _reg_value(root, path, name)
        if v and os.path.isdir(v):
            return os.path.normpath(v)
    for v in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        if os.path.isdir(v):
            return v
    return None


STEAM_SKIP = ("redistributable", "steamworks common", "proton", "steam linux runtime",
              "directx", "vcredist", "dedicated server")


def _scan_steam():
    out = []
    try:
        root = _steam_root()
        if not root:
            return out
        libs = {os.path.join(root, "steamapps")}
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            with open(vdf, encoding="utf-8", errors="ignore") as f:
                for p in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                    libs.add(os.path.join(p.replace("\\\\", "\\"), "steamapps"))
        for lib in libs:
            if not os.path.isdir(lib):
                continue
            for fn in os.listdir(lib):
                if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
                    continue
                try:
                    with open(os.path.join(lib, fn), encoding="utf-8", errors="ignore") as f:
                        txt = f.read()
                    appid = re.search(r'"appid"\s+"(\d+)"', txt).group(1)
                    name = re.search(r'"name"\s+"([^"]+)"', txt).group(1)
                except Exception:  # noqa: BLE001
                    continue
                if any(k in name.lower() for k in STEAM_SKIP):
                    continue
                out.append((name, ("url", f"steam://rungameid/{appid}"), "Steam"))
    except Exception:  # noqa: BLE001
        pass
    return out


def _scan_epic():
    import json
    out = []
    d = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     r"Epic\EpicGamesLauncher\Data\Manifests")
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".item"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8", errors="ignore") as f:
                m = json.load(f)
            name = m.get("DisplayName")
            ns, item, app = m.get("CatalogNamespace"), m.get("CatalogItemId"), m.get("AppName")
            if name and ns and item and app:
                out.append((name, ("url", f"com.epicgames.launcher://apps/{ns}%3A{item}%3A{app}"
                                          f"?action=launch&silent=true"), "Epic Games"))
        except Exception:  # noqa: BLE001
            continue
    return out


def _scan_gog():
    out = []
    try:
        import winreg
        base = r"SOFTWARE\WOW6432Node\GOG.com\Games"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                sub = winreg.EnumKey(k, i)
                name = _reg_value(winreg.HKEY_LOCAL_MACHINE, base + "\\" + sub, "gameName")
                exe = _reg_value(winreg.HKEY_LOCAL_MACHINE, base + "\\" + sub, "exe")
                if name and exe and os.path.isfile(exe):
                    out.append((name, ("path", exe), "GOG"))
    except Exception:  # noqa: BLE001
        pass
    return out


UNINSTALL_SKIP = ("redistributable", "runtime", "driver", "update for", "security update",
                  "sdk", "hotfix", "service pack", "language pack", "языковой", "обновление",
                  "microsoft visual c++", ".net", "directx", "vcredist", "webview2", "helper",
                  "uninstall", "удален", "plugin", "plug-in", "codec", "bonjour")


def _scan_uninstall():
    out = []
    try:
        import winreg
    except ImportError:
        return out
    roots = ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"))
    for root, base in roots:
        try:
            k = winreg.OpenKey(root, base)
        except OSError:
            continue
        with k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                try:
                    sub = base + "\\" + winreg.EnumKey(k, i)
                    name = _reg_value(root, sub, "DisplayName")
                    if not name or _reg_value(root, sub, "SystemComponent") == 1:
                        continue
                    if any(x in name.lower() for x in UNINSTALL_SKIP):
                        continue
                    icon = (_reg_value(root, sub, "DisplayIcon") or "").split(",")[0].strip('" ')
                    loc = (_reg_value(root, sub, "InstallLocation") or "").strip('" ')
                    if icon.lower().endswith(".exe") and os.path.isfile(icon) and \
                            "unins" not in os.path.basename(icon).lower():
                        out.append((name, ("path", icon), "Программа"))
                    elif loc and os.path.isdir(loc):
                        out.append((name, ("path", loc), "Программа"))
                except Exception:  # noqa: BLE001
                    continue
    return out


def _feed_vocab():
    """Подсказываем распознаванию речи названия своих программ и игр (сначала игры)."""
    try:
        import asr
        rank = {"Steam": 0, "Epic Games": 0, "GOG": 0, "Ярлык": 1, "Пуск": 2, "Программа": 3}
        items = sorted((x for x in _apps_full if x[3] != "Эмулятор"),
                       key=lambda x: (rank.get(x[3], 4), len(x[1])))
        asr.set_vocab([x[1] for x in items if re.search("[A-Za-z]", x[1])])
    except Exception:  # noqa: BLE001
        pass


def _index_file():
    import config
    return config.data_dir() / "apps_index2.json"


def _save_index(items):
    import json
    try:
        data = [{"n": n, "name": o, "kind": t[0], "value": t[1], "src": src}
                for n, o, t, src in items]
        with open(_index_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def _load_index():
    import json
    try:
        with open(_index_file(), encoding="utf-8") as f:
            return [(d["n"], d["name"], (d["kind"], d["value"]), d.get("src", ""))
                    for d in json.load(f)]
    except Exception:  # noqa: BLE001
        return []


GAME_WORDS = ("roblox", "minecraft", "osu", "genshin", "valorant", "league of legends", "fortnite",
              "dota", "counter strike", "cs2", "grand theft auto", "gta", "apex", "overwatch", "pubg",
              "warface", "world of tanks", "world of warships", "war thunder", "rust", "terraria",
              "stardew", "among us", "fall guys", "rocket league", "hearthstone", "starcraft", "diablo",
              "call of duty", "battlefield", "the sims", "sims", "fifa", "ea sports fc", "nba 2k",
              "honkai", "zenless", "wuthering", "standoff", "brawl", "clash", "tlauncher", "lunar client",
              "badlion", "garry", "team fortress", "left 4 dead", "half life", "portal", "witcher",
              "cyberpunk", "elden ring", "dark souls", "skyrim", "fallout", "minecraft launcher",
              "geometry dash", "hollow knight", "dead by daylight", "rainbow six", "escape from tarkov",
              "lethal company", "phasmophobia", "palworld", "helldivers", "deadlock", "marvel rivals",
              "the finals", "naraka", "lost ark", "path of exile", "warframe", "destiny", "halo",
              "forza", "need for speed", "assassin", "far cry", "red dead", "mortal kombat", "tekken",
              "street fighter", "osu lazer", "chess", "мир танков", "калибр", "танки")
GAME_PATHS = ("steamapps", "epic games", "riot games", "ubisoft", "battle net", "battle.net",
              "rockstar games", "\\games\\", "\\игры\\", "gog galaxy", "ea games", "electronic arts",
              "wargaming", "lesta", "mihoyo", "hoyoplay", "roblox", "minecraft", "osulazer", "xboxgames")


def is_game(name, target, src=""):
    """Похоже ли на игру: из Steam/Epic/GOG, известное название или лежит в папке игр."""
    if src in ("Steam", "Epic Games", "GOG"):
        return True
    n = " " + _norm(name) + " "
    if any((" " + w + " ") in n or (len(w) >= 6 and w in n) for w in GAME_WORDS):
        return True
    val = (target[1] if target else "").lower().replace("/", "\\")
    if target and target[0] == "url" and ("steam://" in val or "epicgames" in val):
        return True
    return any(p in val for p in GAME_PATHS)


def games():
    """[(имя, цель, источник)] — только игры."""
    return [x for x in all_targets() if x[2] not in ("Папка", "Файл") and is_game(*x)]


def all_targets():
    """[(имя, цель, источник)] — программы, игры и скачанные папки/файлы, для выбора в настройках."""
    out = [(o, t, src) for _n, o, t, src in _apps_full if src != "Эмулятор"]
    seen = {o.lower() for o, _t, _s in out}
    try:
        for _n, o, t in refresh_local():
            if o.lower() not in seen:
                seen.add(o.lower())
                out.append((o, t, "Папка" if os.path.isdir(t[1]) else "Файл"))
    except Exception:  # noqa: BLE001
        pass
    return sorted(out, key=lambda x: x[0].lower())


def all_apps():
    """[(имя, источник)] — для списка в профиле."""
    return sorted(((o, src) for _n, o, _t, src in _apps_full), key=lambda x: x[0].lower())


# ---- фонетическое сравнение: «хартстоун» ~ «Hearthstone», «террария» ~ «Terraria»
NUM_WORDS = {"один": "1", "одна": "1", "два": "2", "две": "2", "три": "3", "четыре": "4",
             "пять": "5", "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10"}
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8"}


def _latinize(s: str) -> str:
    s = s.lower()
    if re.search("[а-я]", s):
        s = " ".join(NUM_WORDS.get(w, w) for w in s.split())
        s = translit(s)
    s = " ".join(ROMAN.get(w, w) for w in s.split())
    return s


def _skel(s: str) -> str:
    s = _latinize(s)
    for a, b in (("sch", "sh"), ("ph", "f"), ("th", "t"), ("ck", "k"), ("qu", "kv"), ("dzh", "j"),
                 ("kh", "h"), ("c", "k"), ("q", "k"), ("x", "ks"), ("w", "v"), ("z", "s"),
                 ("y", "i"), ("e", "i"), ("o", "a"), ("u", "a")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]", "", s)
    if not s:
        return ""
    out = s[0]
    for ch in s[1:]:
        if ch in "aeiou":
            continue
        if ch != out[-1]:
            out += ch
    return out


# ---- скачанные программы и папки (например, «запрет» — zapret-discord-youtube)
LAUNCHER_HINTS = ("general", "start", "run", "launch", "запуск", "service")


def _local_roots():
    env = os.environ
    home = env.get("USERPROFILE", "")
    roots = []
    for p in (os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"),
              os.path.join(env.get("OneDrive", ""), "Desktop") if env.get("OneDrive") else "",
              os.path.join(home, "Downloads"), os.path.join(home, "Documents"),
              os.path.join(home, "OneDrive", "Documents"), home,
              os.environ.get("SystemDrive", "C:") + "\\",
              os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "Games")):
        if p and os.path.isdir(p) and p not in roots:
            roots.append(p)
    return roots


def _scan_local():
    out, seen = [], set()
    skip_dirs = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
                 "appdata", "system volume information", "node_modules", ".git", "users"}
    for root in _local_roots():
        depth0 = root.rstrip("\\/").count(os.sep)
        shallow = root in (os.environ.get("USERPROFILE", ""),
                           os.environ.get("SystemDrive", "C:") + "\\")
        max_depth = 1 if shallow else 3
        for cur, dirs, files in os.walk(root):
            depth = cur.rstrip("\\/").count(os.sep) - depth0
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith(".")]
            if depth >= max_depth:
                dirs[:] = []
            for d in dirs:
                p = os.path.join(cur, d)
                if p not in seen:
                    seen.add(p)
                    out.append((d, ("path", p)))
            for f in files:
                if f.lower().endswith((".exe", ".bat", ".cmd", ".lnk")):
                    p = os.path.join(cur, f)
                    if p not in seen:
                        seen.add(p)
                        out.append((os.path.splitext(f)[0], ("path", p)))
    return out


def refresh_local(force=False):
    global _local, _local_time
    if not force and _local and time.time() - _local_time < 300:
        return _local
    items = []
    for name, target in _scan_local():
        n = _norm(name)
        if n and not any(k in n for k in SKIP):
            items.append((n, name, target))
    _local, _local_time = items, time.time()
    return _local


def warm(force=False):
    """Заранее собирает список программ и игр в фоне, чтобы «открой …» срабатывало мгновенно."""
    def work():
        import config
        config.low_priority_thread()
        refresh_apps()
        if force or time.time() - _apps_time > 500:
            refresh_apps(force=True)
        refresh_local()
    threading.Thread(target=work, daemon=True).start()


def _keys(text: str):
    n = clean(text)
    keys = {n, translit(n), _latinize(n), ALIASES.get(n, ""), ALIASES.get(_base(n), "")}
    if " " not in n and len(n) >= 4:
        keys |= {_base(n), translit(_base(n))}
    return {_norm(k) for k in keys if len(_norm(k)) >= 2}


def keys_for(name: str):
    """Ключи для поиска: вся фраза, а также каждое слово (для закрытия окон)."""
    n = clean(name)
    keys = _keys(n)
    for w in n.split():
        keys |= _keys(w)
    return keys


def _score(key: str, app: str) -> float:
    if key == app:
        return 1.0
    flat_k, flat_a = key.replace(" ", ""), app.replace(" ", "")
    if flat_k == flat_a:
        return 0.98
    words = app.split()
    if words and key == words[0]:
        return 0.92 - 0.01 * max(0, len(words) - 1)
    first = words[0] if words else flat_a
    if len(flat_k) >= 4 and flat_a.startswith(flat_k) and len(flat_k) >= 0.6 * len(first):
        # начало названия: «телеграм» ~ «telegram desktop»; но «роб» — это ещё не «roblox»
        return 0.9 - 0.01 * max(0, len(words) - 1)
    if key in words:                       # слово из середины названия — слабое совпадение
        return 0.78
    if len(flat_k) >= 5 and flat_k in flat_a:
        return 0.84 - 0.01 * max(0, len(words) - 1)
    best = SequenceMatcher(None, flat_k, flat_a).ratio()
    for w in words:
        if len(w) >= 3:
            best = max(best, SequenceMatcher(None, flat_k, w).ratio() - 0.04)
    # звучание: русская запись английского названия
    sk, sa = _skel(key), _skel(app)
    if len(sk) >= 3 and words and _skel(words[0]) == sk:
        best = max(best, 0.88 - 0.01 * max(0, len(words) - 1))   # совпало первое слово названия
    elif len(sk) >= 3 and any(_skel(w) == sk for w in words):
        best = max(best, 0.78)
    if len(sk) >= 4 and sa:
        if sk == sa:
            best = max(best, 0.9)
        elif sa.startswith(sk) and len(sk) >= 5:
            best = max(best, 0.86)
        else:
            best = max(best, SequenceMatcher(None, sk, sa).ratio() * 0.93)
    return best


def _best(keys, items, threshold=0.8):
    best, best_score = None, 0.0
    emu_ok = any(EMU_TAG in k or "эмулятор" in k for k in keys)
    for n, orig, target in items:
        if not emu_ok and n.endswith(" " + EMU_TAG):
            continue
        sc = max(_score(k, n) for k in keys)
        if target[0] == "path" and os.path.isdir(target[1]):
            sc -= 0.02                       # папка — только если нет ярлыка/игры с тем же именем
        if sc > best_score:
            best, best_score = (orig, target), sc
    return best if best_score >= threshold else None


def _phrases(name: str):
    """Сначала вся фраза («яндекс музыку»), потом первое слово («запрет дискорд и ютуб» -> «запрет»)."""
    n = clean(name)
    out = [n]
    words = n.split()
    if len(words) > 1:
        out.append(words[0])
    return out


def find_program(name: str, threshold=0.8):
    """-> (имя, цель) из меню «Пуск» или None."""
    for ph in _phrases(name):
        keys = _keys(ph)
        if keys:
            hit = _best(keys, refresh_apps(), threshold)
            if hit:
                return hit
    return None


def find_local(name: str, threshold=0.84):
    """-> (имя, ("path", путь)) из Загрузок, Рабочего стола, Документов или None."""
    for ph in _phrases(name):
        keys = {k for k in _keys(ph) if len(k.replace(" ", "")) >= 3}
        if keys:
            hit = _best(keys, refresh_local(), threshold=threshold)
            if hit:
                return hit
    return None


EXE_SKIP = ("unins", "crash", "report", "redist", "vcredist", "dxsetup", "setup", "install",
            "update", "helper", "service", "cef", "subprocess", "error", "benchmark", "dotnet",
            "vc_redist", "ue4prereq", "easyanticheat", "be_service", "uninstall")


def _acronym(name):
    """«Grand Theft Auto V» -> «gtav», «gta5»."""
    words = _norm(_latinize(name)).split()
    if len(words) < 2:
        return set()
    base = "".join(w[0] for w in words if not w.isdigit() and w not in ROMAN)
    tail = "".join(ROMAN.get(w, w) for w in words if w.isdigit() or w in ROMAN)
    out = {base}
    if tail:
        out |= {base + tail, base[:-1] + tail if len(base) > 2 else base + tail}
        out.add("".join(w[0] for w in words[:-1]) + ROMAN.get(words[-1], words[-1]))
    return out


def _pick_launcher(folder: str):
    """В папке программы выбираем, что запускать: лаунчер игры, .exe с похожим именем
    или главный .bat. Ищем и в подпапках (bin, Binaries, x64)."""
    try:
        files = os.listdir(folder)
    except OSError:
        return None
    name = os.path.basename(folder.rstrip("\\/"))
    key = _norm(name).split(" ")[0]
    keys = {key} | _acronym(name)
    exes = [f for f in files if f.lower().endswith(".exe")
            and not any(x in f.lower() for x in EXE_SKIP)]
    # «PlayGTAV.exe», «Launcher.exe», «GameLauncher.exe»
    for f in exes:
        low = f.lower()
        if low.startswith("play") or "launcher" in low:
            return os.path.join(folder, f)
    for f in exes:
        nf = _norm(f).replace(" ", "")
        if any(k and (k in nf) for k in keys):
            return os.path.join(folder, f)
    bats = [f for f in files if f.lower().endswith((".bat", ".cmd"))]
    for hint in LAUNCHER_HINTS:
        for f in sorted(bats, key=len):
            if _norm(f).startswith(hint):
                return os.path.join(folder, f)
    if len(exes) == 1:
        return os.path.join(folder, exes[0])
    if exes:                                       # несколько — берём самый большой (это игра)
        try:
            return max((os.path.join(folder, f) for f in exes), key=os.path.getsize)
        except OSError:
            pass
    for sub in ("bin", "Bin", "binaries", "Binaries", "x64", "bin64", "Game", "game"):
        p = os.path.join(folder, sub)
        if os.path.isdir(p):
            hit = _pick_launcher(p)
            if hit:
                return hit
    return None


LAUNCH_LOG = []          # последние запуски: (время, что, цель, почему)


def log_launch(name, target, why=""):
    import datetime
    item = (datetime.datetime.now().strftime("%d.%m %H:%M:%S"), name, f"{target[0]}: {target[1]}", why)
    LAUNCH_LOG.append(item)
    del LAUNCH_LOG[:-30]
    try:
        import config
        with open(config.data_dir() / "launches.log", "a", encoding="utf-8") as f:
            f.write(" | ".join(item) + "\n")
    except Exception:  # noqa: BLE001
        pass


def launch(target, name="", why=""):
    """Запуск без блокировки программы (ошибки Windows не «замораживают» помощника)."""
    kind, value = target
    log_launch(name or value, target, why)
    if kind == "app":
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + value], creationflags=NO_WINDOW)
        return "Запускаю"
    if kind in ("lnk", "url"):
        os.startfile(value)  # type: ignore[attr-defined]
        return "Запускаю"
    path = value
    if os.path.isdir(path):
        launcher = _pick_launcher(path)
        if launcher is None:
            os.startfile(path)  # type: ignore[attr-defined]
            return "Открываю папку"
        path = launcher
    if path.lower().endswith((".bat", ".cmd")):
        # такие скрипты (например, запрет) обычно требуют прав администратора
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", path, None, os.path.dirname(path), 1)
    else:
        os.startfile(path)  # type: ignore[attr-defined]
    return "Запускаю"
