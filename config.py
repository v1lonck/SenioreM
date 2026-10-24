"""Пути и настройки приложения."""
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "version": "0.0.0",        # подставляется при сборке
    "update_repo": "",         # owner/repo на GitHub, откуда брать обновления
    "smtp": {
        "host": "",
        "port": 465,
        "user": "",
        "password": "",
        "from_name": "SenioreM",
    },
    # Если почта не настроена или здесь true — код показывается прямо в окне.
    "test_mode_show_code": False,
    "voice": {
        # Нейроголос (нужен интернет). Без интернета — встроенный голос Windows.
        "edge_voice": "ru-RU-DmitryNeural",
        "rate": "+0%",
    },
    "wake_words": ["сеньор", "сеньер", "синьор"],
    "search_url": "https://www.google.com/search?q=",
    "home_url": "https://www.google.com",
}


def base_dir() -> Path:
    """Папка рядом с программой (там лежат config.json и model)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(rel: str) -> Path:
    """Файлы, упакованные внутрь сборки (иконка и т.п.)."""
    root = Path(getattr(sys, "_MEIPASS", base_dir()))
    return root / rel


def data_dir() -> Path:
    """Личные данные: аккаунты, сессия, журнал ошибок."""
    root = os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / "SenioreM"
    d.mkdir(parents=True, exist_ok=True)
    return d


MODEL_NAME = "vosk-model-small-ru-0.22"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def _ascii(p) -> bool:
    try:
        str(p).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".write_test"
        t.write_text("ok")
        t.unlink()
        return True
    except OSError:
        return False


def local_dir() -> Path:
    """Папка для речевой модели. Движок распознавания не понимает русские буквы
    в пути (например, имя пользователя Windows на кириллице), поэтому выбираем
    первую подходящую папку с латинским путём."""
    candidates = []
    for env in ("LOCALAPPDATA", "ProgramData", "PUBLIC"):
        v = os.environ.get(env)
        if v:
            candidates.append(Path(v) / "SenioreM")
    candidates.append(Path(os.environ.get("SystemDrive", "C:") + "\\") / "SenioreM")
    for d in candidates:
        if _ascii(d) and _writable(d):
            return d
    d = candidates[0] if candidates else Path.home() / "SenioreM"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_ready(path: Path) -> bool:
    return (path / "am" / "final.mdl").is_file()


def model_dir() -> Path:
    """Модель рядом с программой (если положили) или скачанная при первом запуске."""
    bundled = base_dir() / "model"
    if model_ready(bundled):
        return bundled
    return local_dir() / "model"


def _merge(defaults: dict, user: dict) -> dict:
    out = dict(defaults)
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_config() -> dict:
    """Настройки по умолчанию <- вшитые при сборке <- config.json рядом с программой."""
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg = _merge(cfg, _read_json(resource_path("config.json")))
    if base_dir() != resource_path("."):
        cfg = _merge(cfg, _read_json(base_dir() / "config.json"))
    return cfg
