"""Выполнение команд в Windows. Возвращает (что сказать, действие для окна)."""
import ctypes
import datetime
import re
import os
import subprocess
import sys
import urllib.parse
import webbrowser
from pathlib import Path

IS_WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WIN else 0

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница",
            "суббота", "воскресенье"]

HELP_TEXT = ("Я умею менять громкость и яркость, включать и выключать звук, "
             "открывать и закрывать программы и сайты, искать в интернете, управлять музыкой, "
             "говорить время и дату, делать скриншот и блокировать компьютер.")


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def pct(n):
    return f"{n} {plural(n, 'процент', 'процента', 'процентов')}"


# ---------------- клавиши ----------------
VK = {"vol_down": 0xAE, "vol_up": 0xAF, "mute": 0xAD, "next": 0xB0,
      "prev": 0xB1, "play_pause": 0xB3, "lwin": 0x5B, "snapshot": 0x2C}


def _key(vk, down=True):
    flags = 0x0001 | (0 if down else 0x0002)  # EXTENDEDKEY | KEYUP
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def _tap(vk):
    _key(vk, True)
    _key(vk, False)


# ---------------- громкость ----------------
def _endpoint():
    import comtypes
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetSpeakers()
    ev = getattr(dev, "EndpointVolume", None)  # новые версии pycaw
    if ev is not None:
        return ev
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def get_volume():
    try:
        return round(_endpoint().GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return None


def set_volume(n):
    n = max(0, min(100, int(n)))
    try:
        ev = _endpoint()
        ev.SetMasterVolumeLevelScalar(n / 100.0, None)
        if n > 0 and ev.GetMute():
            ev.SetMute(0, None)
        return n
    except Exception:
        # Запасной путь: мультимедийные клавиши (шаг — 2%).
        for _ in range(50):
            _tap(VK["vol_down"])
        for _ in range(round(n / 2)):
            _tap(VK["vol_up"])
        return n


def set_mute(on):
    """Включить/выключить звук. Проверяем результат: если не сработало — мультимедийная клавиша."""
    try:
        ev = _endpoint()
        ev.SetMute(1 if on else 0, None)
        if not on and ev.GetMasterVolumeLevelScalar() < 0.05:
            ev.SetMasterVolumeLevelScalar(0.3, None)   # звук «включён», но на нуле
        if bool(ev.GetMute()) != bool(on):
            _tap(VK["mute"])
    except Exception:
        _tap(VK["mute"])


def is_muted():
    try:
        return bool(_endpoint().GetMute())
    except Exception:
        return False


# ---------------- яркость ----------------
def _ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def get_brightness():
    out = _ps("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness"
              " | Select-Object -First 1).CurrentBrightness")
    return int(out.split()[0])


def set_brightness(n):
    n = max(0, min(100, int(n)))
    _ps("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods"
        f" | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={n}}}"
        " | Out-Null")
    return n


# ---------------- программы ----------------
def _open(target):
    os.startfile(target)  # type: ignore[attr-defined]


def open_app(app, cfg):
    home = Path.home()
    table = {
        "browser": (lambda: webbrowser.open(cfg.get("home_url", "https://www.google.com")), "Открываю браузер."),
        "notepad": (lambda: _open("notepad.exe"), "Открываю блокнот."),
        "calc": (lambda: _open("calc.exe"), "Открываю калькулятор."),
        "explorer": (lambda: _open(str(home)), "Открываю проводник."),
        "downloads": (lambda: _open(str(home / "Downloads")), "Открываю загрузки."),
        "documents": (lambda: _open(str(home / "Documents")), "Открываю документы."),
        "settings": (lambda: _open("ms-settings:"), "Открываю параметры."),
        "taskmgr": (lambda: _open("taskmgr.exe"), "Открываю диспетчер задач."),
        "paint": (lambda: _open("mspaint.exe"), "Открываю пейнт."),
    }
    fn, reply = table[app]
    fn()
    return reply



def _start(hit, why):
    """Запустить найденную программу — или показать её, если она уже открыта."""
    import sites
    title, target = hit
    try:
        import procs
        state = procs.bring_up(title, target)
    except Exception:  # noqa: BLE001
        state = None
    if state == "minimized":
        return f"{title} уже открыта — разворачиваю."
    if state == "open":
        return f"{title} уже открыта — переключаю на неё."
    return f"{sites.launch(target, title, why)} {title}."


def open_by_name(name, cfg):
    """Порядок: приложение из меню «Пуск» -> скачанная программа или папка (Загрузки,
    Рабочий стол, Документы) -> сайт -> первый результат поиска.
    Если сказано «сайт …» — открываем именно сайт."""
    import sites
    name = (name or "").strip()
    if not name:
        return "Что открыть?"
    pretty = sites.clean(name)
    site = sites.find_site(name)
    if site and not site[1] and "сайт" not in name:
        # известный сайт (ютуб, вк…): приложение — только при точном совпадении названия
        prog = sites.find_program(name, threshold=0.95)
        if prog:
            return _start(prog, f"открой {name}")
        webbrowser.open(site[0])
        return f"Открываю {pretty}."
    if "сайт" not in name:
        prog = sites.find_program(name)
        if prog:
            return _start(prog, f"открой {name}")
        local = sites.find_local(name)
        if local:
            return _start(local, f"открой {name}")
    site = sites.find_site(name)
    if site:
        webbrowser.open(site[0])
        return f"Открываю {pretty}."
    if "сайт" not in name:
        # похоже звучит, но сказано неточно: «саунпат» -> Soundpad
        loose = sites.find_program(name, threshold=0.72)
        if loose:
            return _start(loose, f"открой {name} (похоже на {loose[0]})")
    if "сайт" in name or len(pretty.split()) >= 3:
        webbrowser.open("https://duckduckgo.com/?q=" + urllib.parse.quote(pretty))
        return f"Ищу {pretty} в интернете."
    return (f"Не нашёл «{pretty}» на компьютере. Если программа только что установлена — скажите "
            f"«обнови список программ», а чтобы найти в интернете — «найди {pretty}».")


def _looks_like_game(name):
    """Название латиницей или с цифрой — скорее игра/программа, чем сайт: в браузер не идём."""
    return bool(re.search(r"[a-z]", name)) or bool(re.search(r"\d", name))


# ---------------- закрытие программ ----------------
CLOSE_TARGETS = {
    "browser": (["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe",
                 "brave.exe", "vivaldi.exe"], "браузер"),
    "notepad": (["notepad.exe"], "блокнот"),
    "calc": (["calculatorapp.exe", "calculator.exe", "calc.exe"], "калькулятор"),
    "settings": (["systemsettings.exe"], "параметры"),
    "taskmgr": (["taskmgr.exe"], "диспетчер задач"),
    "paint": (["mspaint.exe"], "пейнт"),
}
# Эти программы при закрытии прячутся в трей — их завершаем принудительно.
TRAY_APPS = {"telegram.exe", "discord.exe", "steam.exe", "spotify.exe", "viber.exe",
             "skype.exe", "whatsapp.exe", "zoom.exe", "ayugram.exe"}
# Системные процессы трогать нельзя.
PROTECTED = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "dwm.exe",
             "system", "smss.exe", "lsass.exe", "services.exe", "wininit.exe",
             "senioreM.exe".lower(), "python.exe", "pythonw.exe", "searchhost.exe",
             "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe",
             "runtimebroker.exe", "applicationframehost.exe", "sihost.exe", "ctfmon.exe"}
ALIASES = {
    "телеграм": "telegram", "телеграмм": "telegram", "дискорд": "discord", "ютуб": "youtube",
    "спотифай": "spotify", "вотсап": "whatsapp", "ватсап": "whatsapp", "ворд": "word",
    "эксель": "excel", "хром": "chrome", "гугл хром": "chrome", "эдж": "edge",
    "файрфокс": "firefox", "фаерфокс": "firefox", "опера": "opera", "стим": "steam",
    "зум": "zoom", "вайбер": "viber", "скайп": "skype", "фотошоп": "photoshop",
    "яндекс": "yandex", "вк": "vk", "вконтакте": "vk", "обс": "obs", "майнкрафт": "minecraft",
    "кс": "cs2", "дота": "dota", "аюграм": "ayugram", "пауэрпоинт": "powerpnt",
    "повер поинт": "powerpnt",
}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n",
                     "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y",
                     "", "e", "yu", "ya"]))


def _translit(text):
    return "".join(TRANSLIT.get(c, c) for c in text)


def _windows():
    """Видимые окна верхнего уровня в порядке «сверху вниз»: (hwnd, pid, заголовок)."""
    u = ctypes.windll.user32
    out = []
    hwnd = u.GetTopWindow(None)
    while hwnd:
        if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):  # GW_OWNER: только главные
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                pid = ctypes.c_ulong()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append((hwnd, pid.value, buf.value))
        hwnd = u.GetWindow(hwnd, 2)  # GW_HWNDNEXT
    return out


def _proc_names():
    import psutil
    names = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            names[p.info["pid"]] = (p.info["name"] or "").lower()
        except Exception:  # noqa: BLE001
            pass
    return names


def _taskkill(args):
    subprocess.run(["taskkill", *args], capture_output=True, creationflags=NO_WINDOW, timeout=10)


def _close_pids(pids, names):
    done = set()
    for pid in pids:
        exe = names.get(pid, "")
        if not exe or exe in PROTECTED or pid == os.getpid() or exe in done:
            continue
        done.add(exe)
        _taskkill(["/IM", exe, "/T", "/F"] if exe in TRAY_APPS else ["/IM", exe])
    return done


CURRENT_WORDS = {"окно", "это", "это окно", "текущее окно", "активное окно", "его", "ее", "её",
                 "игру", "эту игру", "программу", "эту программу", "приложение", "это приложение",
                 "текущую программу", "текущее", "текущую игру", "вкладку"}


def close_app(intent):
    me = os.getpid()
    names = _proc_names()
    app, name = intent.get("app"), (intent.get("name") or "").strip()

    if app in ("explorer", "downloads", "documents"):
        _ps("$s = New-Object -ComObject Shell.Application; "
            "@($s.Windows()) | ForEach-Object { try { $_.Quit() } catch {} }")
        return "Закрыл окна проводника."

    if app in CLOSE_TARGETS:
        exes, title = CLOSE_TARGETS[app]
        pids = [pid for pid, exe in names.items() if exe in exes]
        if not pids:
            return f"{title.capitalize()} сейчас не открыт."
        _close_pids(pids, names)
        return f"Закрыл {title}."

    if name in CURRENT_WORDS:
        import procs
        w = procs.foreground()
        if w is None:
            return "Открытых окон нет."
        procs.close_window(w.hwnd)
        procs.force_later([w])
        return f"Закрыл «{w.title[:40]}»."

    import sites
    # 1) по списку программ: «закрой озу» -> osu! -> процессы из папки osu!
    try:
        import procs
        hit = sites.find_program(name, threshold=0.85)
        n, exes = procs.close(name, hit[1] if hit else None)
        if n:
            return f"Закрыл {hit[0] if hit else name}."
    except Exception as e:  # noqa: BLE001
        _log_err(f"close {name}: {e!r}")
    keys = sites.keys_for(name) | {name, _translit(name), ALIASES.get(name, "")}
    if app == "youtube":
        keys = {"youtube"}
    if "word" in keys:
        keys.add("winword")
    keys = {k.replace(" ", "") for k in keys if len(k.replace(" ", "")) >= 2}
    found = False
    # 1) окна, в заголовке которых есть название (закрываем мягко)
    for hwnd, pid, title in _windows():
        t = title.lower().replace(" ", "")
        if pid != me and names.get(pid, "") not in PROTECTED and any(k in t for k in keys):
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            found = True
    # 2) процессы с таким именем (на случай программ в трее)
    pids = [pid for pid, exe in names.items()
            if any(exe.replace(".exe", "").startswith(k) for k in keys)]
    if pids:
        found = bool(_close_pids(pids, names)) or found
    return f"Закрыл {name}." if found else f"Не нашёл открытую программу «{name}»."

def app_window(intent):
    """«Сверни осу», «разверни телеграм», «переключись на дискорд»."""
    import procs
    import sites
    name = (intent.get("name") or "").strip()
    hit = sites.find_program(name, threshold=0.85)
    wins, _ = procs.find(name, hit[1] if hit else None)
    title = hit[0] if hit else name
    if not wins:
        if intent.get("mode") == "show" and hit:
            return _start(hit, f"разверни {name}")
        return f"{title} сейчас не открыта."
    if intent.get("mode") == "min":
        for w in wins:
            ctypes.windll.user32.ShowWindow(w.hwnd, 6)      # SW_MINIMIZE
        return f"Свернул {title}."
    procs.activate(wins[0].hwnd)
    return f"Показываю {title}."


def try_launch(text):
    """Одно-два слова, ТОЧНО совпавшие с названием программы («осу», «запрет»), — запускаем.
    Случайные слова из разговора программы не запускают."""
    if not text or len(text.split()) > 2 or len(text.replace(" ", "")) < 3:
        return None
    import sites
    hit = sites.find_program(text, threshold=0.97) or sites.find_local(text, threshold=0.97)
    if hit:
        return _start(hit, f"название без «открой»: {text}")
    return None


def _log_err(text):
    try:
        import config
        with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:  # noqa: BLE001
        pass


# ---------------- главный вход ----------------
def run(intent: dict, cfg: dict):
    """-> (reply_text, ui_action) ; ui_action: '', 'minimize', 'restore', 'quit'."""
    a = intent.get("action")
    try:
        if a == "volume_set":
            n = set_volume(intent["value"])
            return f"Готово. Громкость {pct(n)}.", ""
        if a == "volume_delta":
            cur = get_volume()
            if cur is None:
                cur = 50
            n = set_volume(cur + intent["delta"])
            return f"Громкость {pct(n)}.", ""
        if a == "volume_get":
            cur = get_volume()
            return (f"Сейчас громкость {pct(cur)}." if cur is not None
                    else "Не удалось узнать громкость."), ""
        if a == "mute":
            set_mute(intent["on"])
            return ("Звук выключен." if intent["on"] else "Звук включён."), ""

        if a in ("brightness_set", "brightness_delta", "brightness_get"):
            try:
                if a == "brightness_get":
                    return f"Яркость {pct(get_brightness())}.", ""
                if a == "brightness_set":
                    n = set_brightness(intent["value"])
                else:
                    n = set_brightness(get_brightness() + intent["delta"])
                return f"Готово. Яркость {pct(n)}.", ""
            except Exception:
                return "Этот монитор не даёт менять яркость программно.", ""

        if a == "open":
            if intent.get("app"):
                return open_app(intent["app"], cfg), ""
            return open_by_name(intent.get("name") or "", cfg), ""
        if a == "rescan":
            import sites
            sites.refresh_apps(force=True)
            sites.refresh_local(force=True)
            return f"Готово. Я знаю {len(sites.all_apps())} программ и игр.", ""
        if a == "close":
            return close_app(intent), ""
        if a == "app_window":
            return app_window(intent), ""
        import control
        if a in control.ACTIONS:
            return control.run(intent), ""
        if a == "desktop":
            try:
                import comtypes
                import comtypes.client
                comtypes.CoInitialize()
                shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
                if intent.get("mode") == "min":
                    shell.MinimizeAll()
                    return "Свернул все окна.", "minimize"
                shell.UndoMinimizeALL()
                return "Вернул окна.", ""
            except Exception:  # noqa: BLE001
                pass
            if intent.get("mode") == "min":
                _key(VK["lwin"], True)
                _tap(0x4D)                      # Win+M — свернуть все окна
                _key(VK["lwin"], False)
                return "Свернул все окна.", "minimize"
            _key(VK["lwin"], True)
            _key(0x10, True)
            _tap(0x4D)                          # Win+Shift+M — вернуть окна
            _key(0x10, False)
            _key(VK["lwin"], False)
            return "Вернул окна.", ""
        if a == "search":
            q = intent.get("query") or ""
            if not q:
                return "Что найти? Скажите, например: сеньор, найди погоду.", ""
            webbrowser.open(cfg.get("search_url", "https://www.google.com/search?q=")
                            + urllib.parse.quote(q))
            return f"Ищу: {q}.", ""

        if a == "media":
            _tap(VK[intent["key"]])
            return {"play_pause": "Готово.", "next": "Следующий трек.",
                    "prev": "Предыдущий трек."}[intent["key"]], ""
        if a == "window":
            if intent["mode"] == "minimize":
                return "Сворачиваюсь. Я продолжаю слушать.", "minimize"
            return "Я здесь.", "restore"
        if a == "lock":
            ctypes.windll.user32.LockWorkStation()
            return "Блокирую компьютер.", ""
        if a == "screenshot":
            _key(VK["lwin"], True)
            _tap(VK["snapshot"])
            _key(VK["lwin"], False)
            return "Скриншот сохранён в папку «Снимки экрана».", ""

        now = datetime.datetime.now()
        if a == "time":
            return f"Сейчас {now.hour}:{now.minute:02d}.", ""
        if a == "date":
            return f"Сегодня {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS[now.month - 1]}.", ""
        if a == "help":
            return HELP_TEXT, ""
        if a == "greet":
            return "Здравствуйте! Чем помочь?", ""
        if a == "thanks":
            return "Всегда пожалуйста.", ""
        if a == "quit":
            return "До встречи.", "quit"
        if a == "chat":
            return intent.get("reply", ""), ""
        if a in ("ask", "forget"):
            return ("Чтобы я мог разговаривать и отвечать на вопросы, включите "
                    "ИИ-собеседника: профиль → «ИИ-собеседник»."), ""
        if a == "empty":
            return "", ""
        # Неизвестная короткая фраза — может, это название программы («запрет», «осу»)
        launched = None if intent.get("followup") else try_launch(intent.get("text", ""))
        if launched:
            return launched, ""
        if intent.get("typed"):
            return ("Не понял команду. Попробуйте написать иначе — например, «открой телеграм» "
                    "или «громкость 30»."), ""
        return "Не расслышал команду. Повторите, пожалуйста.", ""
    except Exception as e:  # noqa: BLE001
        return f"Не получилось выполнить команду. {e}", ""
