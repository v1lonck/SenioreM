"""Выполнение команд в Windows. Возвращает (что сказать, действие для окна)."""
import ctypes
import datetime
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
             "открывать программы и сайты, искать в интернете, управлять музыкой, "
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
    try:
        _endpoint().SetMute(1 if on else 0, None)
    except Exception:
        _tap(VK["mute"])


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
        "youtube": (lambda: webbrowser.open("https://www.youtube.com"), "Открываю ютуб."),
        "paint": (lambda: _open("mspaint.exe"), "Открываю пейнт."),
    }
    fn, reply = table[app]
    fn()
    return reply


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
            name = intent.get("name") or ""
            if name:
                webbrowser.open(cfg.get("search_url", "https://www.google.com/search?q=")
                                + urllib.parse.quote(name))
                return f"Не знаю такой программы, ищу «{name}» в интернете.", ""
            return "Что открыть?", ""
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
        if a == "empty":
            return "", ""
        return "Не расслышал команду. Повторите, пожалуйста.", ""
    except Exception as e:  # noqa: BLE001
        return f"Не получилось выполнить команду. {e}", ""
