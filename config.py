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
    # Подтверждение почты кодом. Пока выключено: регистрация по логину и паролю.
    "email_verification": False,
    # Если почта не настроена или здесь true — код показывается прямо в окне.
    "test_mode_show_code": False,
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


def model_urls():
    """Зеркало в релизах GitHub (быстрее и доступнее), затем официальный сайт Vosk."""
    repo = load_config().get("update_repo") or ""
    urls = [f"https://github.com/{repo}/releases/download/models/{MODEL_NAME}.zip"] if repo else []
    return urls + [MODEL_URL]


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


_LOCAL = None
STORAGE_ITEMS = ("model", "voice", "whisper-small", "ai", "voice_cache")   # что скачивает программа
STORAGE_NEED_GB = 3.5           # речь, голос, точное распознавание и ИИ вместе — с запасом


def _storage_file() -> Path:
    return data_dir() / "storage.json"


def storage_chosen() -> bool:
    """Выбирал ли пользователь папку для загрузок (или она уже используется)."""
    return _storage_file().is_file()


def check_storage_path(path) -> str:
    """-> "" если папка подходит, иначе — понятная причина."""
    d = Path(path)
    if not str(path).strip():
        return "Папка не выбрана."
    if not _ascii(d):
        return ("В пути есть русские буквы или другие не латинские символы — движок распознавания "
                "речи такие пути не понимает. Выберите папку вроде D:\\SenioreM.")
    if not _writable(d):
        return "В эту папку нельзя записывать. Выберите другую."
    return ""


def set_storage(path) -> str:
    """Запомнить папку для загрузок. -> "" или причина, почему нельзя."""
    global _LOCAL
    err = check_storage_path(path)
    if err:
        return err
    _storage_file().write_text(json.dumps({"path": str(Path(path))}, ensure_ascii=False),
                               encoding="utf-8")
    _LOCAL = None
    return ""


def free_gb(path) -> float:
    import shutil
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free / 1e9
    except OSError:
        return 0.0


def folder_size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def move_storage(new, progress=None) -> str:
    """Перенести всё скачанное в новую папку и переключиться на неё. -> "" или ошибка."""
    import shutil
    old = local_dir()
    new = Path(new)
    err = check_storage_path(new)
    if err:
        return err
    if old.resolve() == new.resolve():
        return set_storage(new)
    need = sum(folder_size(old / n) for n in STORAGE_ITEMS if (old / n).exists())
    if free_gb(new) * 1e9 < need * 1.05:
        return f"На диске мало места: нужно {need / 1e9:.1f} ГБ."
    items = [n for n in STORAGE_ITEMS if (old / n).exists()]
    for i, name in enumerate(items):
        if progress:
            progress(i / max(1, len(items)), f"Переношу {name}")
        dst = new / name
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.move(str(old / name), str(dst))
    return set_storage(new)


def apply_pending_move(progress=None) -> str:
    """Папку выбрали в установщике: переносим туда уже скачанное (один раз). -> "" или ошибка."""
    import shutil
    global _LOCAL
    data = _read_json(_storage_file()) if _storage_file().is_file() else {}
    if not data.get("pending_move"):
        return ""
    new = Path(data.get("path", ""))
    err = check_storage_path(new)
    old = default_storage()
    if not err and old.resolve() != new.resolve():
        try:
            for name in STORAGE_ITEMS:
                if (old / name).exists() and not (new / name).exists():
                    if progress:
                        progress(f"Переношу скачанное в {new}")
                    shutil.move(str(old / name), str(new / name))
        except OSError as e:
            err = f"Не получилось перенести файлы: {e}"
    data.pop("pending_move", None)
    if err:
        _storage_file().unlink(missing_ok=True)          # остаёмся в прежней папке
    else:
        _storage_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _LOCAL = None
    return err


def local_dir() -> Path:
    """Папка для всего, что программа скачивает (речь, голос, ИИ). Можно выбрать самому
    (storage.json). Движок распознавания не понимает русские буквы в пути (например, имя
    пользователя Windows на кириллице), поэтому по умолчанию — первая папка с латинским путём."""
    global _LOCAL
    if _LOCAL is not None:
        return _LOCAL
    chosen = _read_json(_storage_file()).get("path") if _storage_file().is_file() else None
    if chosen and _ascii(chosen) and _writable(Path(chosen)):
        _LOCAL = Path(chosen)
        return _LOCAL
    candidates = []
    for env in ("LOCALAPPDATA", "ProgramData", "PUBLIC"):
        v = os.environ.get(env)
        if v:
            candidates.append(Path(v) / "SenioreM")
    candidates.append(Path(os.environ.get("SystemDrive", "C:") + "\\") / "SenioreM")
    for d in candidates:
        if _ascii(d) and _writable(d):
            _LOCAL = d
            return d
    d = candidates[0] if candidates else Path.home() / "SenioreM"
    d.mkdir(parents=True, exist_ok=True)
    _LOCAL = d
    return d


def default_storage() -> Path:
    """Куда программа положит загрузки, если ничего не выбирать."""
    global _LOCAL
    keep = _LOCAL
    _LOCAL = None
    f = _storage_file()
    saved = f.read_text(encoding="utf-8") if f.is_file() else None
    try:
        if saved is not None:
            f.unlink()
        return local_dir()
    finally:
        if saved is not None:
            f.write_text(saved, encoding="utf-8")
        _LOCAL = keep


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


_T0 = __import__("time").time()


def startup_mark(stage):
    """Журнал запуска: какой этап и через сколько секунд (startup.log) — видно, где долго
    и на чём программа закрылась."""
    import time
    try:
        with open(data_dir() / "startup.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} +{time.time() - _T0:5.1f}s  pid {os.getpid()}  {stage}\n")
    except OSError:
        pass


def low_priority_thread():
    """Фоновая работа (поиск программ, загрузка моделей, уборка) — с низким приоритетом,
    чтобы компьютер не «тормозил», пока SenioreM запускается."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetThreadPriority(k32.GetCurrentThread(), -2)       # THREAD_PRIORITY_LOWEST
    except Exception:  # noqa: BLE001
        pass


def voice_log(text):
    """Журнал слуха (voice.log): что услышано и почему не выполнено — чтобы разобраться,
    если помощник «не слышит». Не больше ~300 КБ."""
    import time
    try:
        p = data_dir() / "voice.log"
        if p.exists() and p.stat().st_size > 300_000:
            p.replace(data_dir() / "voice.old.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass
