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
    "chime": False,                 # «писк» при обращении — по умолчанию выключен
    "chime_off_v2": False,
    "launches": 0,                  # сколько раз открывали (для одной просьбы оценить)
    "rate_asked": False,
    "joke_shutdown": False,         # после шутки-обиды мягко выключать ПК (по умолчанию нет)
    "talk_mode": "polite",          # polite (вежливый) | rude (дерзкий — может подкалывать и ругаться)
    "voice_speed": "normal",
    "voice_engine": "piper",        # piper (Руслан, бесплатно) | yandex (по ключу)
    "yandex_key": "",
    "yandex_voice": "filipp",
    "mic_sensitivity": "normal",
    "mic_device": "",               # выбранный микрофон ("" — по умолчанию в Windows)
    "assistant_name": "Сеньор",
    "speak_replies": True,
    "listen_seconds": 10,
    "dialog_mode": True,
    "followup_seconds": 10,         # сколько слушать после ответа; 0 — сразу выключаться
    "wake_words": "",               # дополнительные слова-обращения
    "stop_words": "стоп",           # чем остановить помощника, пока он говорит
    "autostart": False,
    "ai_enabled": True,
    "ai_auto_setup": False,         # ИИ уже настроен автоматически
    "ai_mode": "smart",             # smart | fast | api
    "cloud_switched": False,        # уже перевели на облачный сервер
    "ai_api_url": "",
    "ai_api_key": "",
    "ai_api_model": "",
    "notes": "",
    "chat": [],
    "chat_ai": "auto",            # какой ИИ в чате: auto / fast / smart / local
    "ai_day_limit": 1500000,      # лимиты токенов облачного ИИ (чтобы хватило надолго)
    "ai_month_limit": 20000000,
    "chat_speak": False,
    "companion": "none",            # фигура над панелью задач
    "companion_anim": True,
    "companion_size": 150,
    "companion_pose": "auto",       # stand | sit | lie | auto
    "avatar": "",                   # аватар: "preset:<id>" или путь к своей картинке
    "history": [],
    "scenarios": None,              # свои фразы и действия (None — сценарии по умолчанию)
    "vpn": {},                      # {"app": {"name", "target"}, "admin", "click", "button"}
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
        if self.data.get("listen_seconds") == 8:      # старое значение по умолчанию
            self.data["listen_seconds"] = 10
        if "followup_seconds" not in self.data or self.data.get("dialog_mode") is False:
            self.data["followup_seconds"] = 10 if self.data.get("dialog_mode", True) else 0
            self.data["dialog_mode"] = True

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
    def cloud_voice(self):
        if self["voice_engine"] == "yandex" and (self["yandex_key"] or "").strip():
            return {"key": self["yandex_key"].strip(), "voice": self["yandex_voice"] or "filipp"}
        return None

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
