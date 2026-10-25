"""Личные настройки пользователя (у каждого аккаунта свои)."""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

DEFAULTS = {
    "name": "",                     # как зовут — для приветствия
    "address": "",                  # обращение в ответах: «господин», «босс»…
    "wake_reply": "Слушаю вас",     # что сказать на «Сеньор»
    "speak_wake_reply": True,
    "chime": True,
    "voice_speed": "normal",
    "mic_sensitivity": "normal",
    "assistant_name": "Сеньор",
    "speak_replies": True,
    "listen_seconds": 8,
    "wake_words": "",               # дополнительные слова-обращения
    "autostart": False,
    "ai_enabled": False,
    "ai_mode": "smart",             # smart | fast | api
    "ai_api_url": "",
    "ai_api_key": "",
    "ai_api_model": "",
    "history": [],
}

NAME_PRESETS = ["Сеньор", "Компьютер", "Помощник", "Макс", "Шеф", "Друг"]
NAME_VARIANTS = {
    "сеньор": ["сеньор", "сеньер", "синьор", "сеньора"],
    "компьютер": ["компьютер", "компьютера"],
    "помощник": ["помощник", "помощника"],
}

WAKE_REPLY_PRESETS = ["Слушаю вас", "Да, господин", "Чем могу помочь?", "На связи", "Да?"]


class Settings:
    def __init__(self, directory: Path, email: str):
        self.email = email
        d = Path(directory) / "profiles"
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / (hashlib.sha1(email.encode()).hexdigest()[:16] + ".json")
        self.data = dict(DEFAULTS)
        self.data["history"] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def set(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---------- история ----------
    def add_history(self, command, reply):
        h = list(self.data.get("history") or [])
        h.insert(0, {"t": int(time.time()), "cmd": command, "reply": reply})
        self.data["history"] = h[:100]
        self.save()

    def clear_history(self):
        self.set("history", [])

    @property
    def wake_words(self):
        name = (self["assistant_name"] or "Сеньор").strip().lower().replace("ё", "е")
        words = list(NAME_VARIANTS.get(name, [name]))
        extra = self["wake_words"] or ""
        if extra.strip().lower().replace(" ", "") == "сеньор,сеньер,синьор":
            extra = ""   # старое значение по умолчанию
        words += [w.strip().lower() for w in re.split(r"[,;\n]", extra) if w.strip()]
        return words

    @property
    def name(self):
        return (self["assistant_name"] or "Сеньор").strip() or "Сеньор"


def personalize(reply: str, address: str) -> str:
    """«Готово. Громкость 10 процентов.» + «господин» -> «Готово, господин. Громкость…»."""
    address = (address or "").strip()
    if not reply or not address:
        return reply
    m = re.search(r"[.!?]", reply)
    if not m:
        return f"{reply}, {address}"
    return f"{reply[:m.start()]}, {address}{reply[m.start():]}"


def greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "Доброе утро"
    if 12 <= hour < 18:
        return "Добрый день"
    if 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


# ---------- автозапуск ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(on: bool) -> bool:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "SenioreM", 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(k, "SenioreM")
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
