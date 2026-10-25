"""Уборка: старая история, кэш голоса и журналы не копятся бесконечно.
Запускается в фоне при входе и раз в сутки."""
import os
import time

CHAT_KEEP = 150                 # сообщений в чате
CHAT_DAYS = 30                  # и не старше месяца
HISTORY_KEEP = 100              # последних команд
HISTORY_DAYS = 60
VOICE_CACHE_FILES = 400         # готовые фразы голоса
VOICE_CACHE_MB = 150
LOG_MAX_KB = 1024               # журналы больше — обрезаем до последних 256 КБ


def trim_settings(settings):
    """Чистит историю чата и команд. -> сколько записей удалено."""
    now = time.time()
    removed = 0
    chat = list(settings["chat"] or [])
    keep = [m for m in chat if now - float(m.get("t", now)) < CHAT_DAYS * 86400][-CHAT_KEEP:]
    if len(keep) != len(chat):
        removed += len(chat) - len(keep)
        settings.data["chat"] = keep
    hist = list(settings["history"] or [])
    keep_h = [h for h in hist if now - float(h.get("t", now)) < HISTORY_DAYS * 86400][:HISTORY_KEEP]
    if len(keep_h) != len(hist):
        removed += len(hist) - len(keep_h)
        settings.data["history"] = keep_h
    if removed:
        settings.save()
    return removed


def trim_voice_cache():
    import config
    d = config.local_dir() / "voice_cache"
    if not d.is_dir():
        return 0
    files = []
    for e in os.scandir(d):
        if e.is_file():
            st = e.stat()
            files.append((st.st_atime, st.st_size, e.path))
    files.sort(reverse=True)                 # самые свежие — первыми
    total, removed = 0, 0
    for i, (_t, size, path) in enumerate(files):
        total += size
        old_tmp = path.endswith(".part") or ".once" in os.path.basename(path)
        if old_tmp or i >= VOICE_CACHE_FILES or total > VOICE_CACHE_MB * 1024 * 1024:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def trim_logs():
    import config
    paths = [config.data_dir() / n for n in ("error.log", "launches.log")]
    paths.append(config.local_dir() / "ai" / "server.log")
    for p in paths:
        try:
            if p.is_file() and p.stat().st_size > LOG_MAX_KB * 1024:
                with open(p, "rb") as f:
                    f.seek(-256 * 1024, os.SEEK_END)
                    tail = f.read()
                cut = tail.find(b"\n")
                with open(p, "wb") as f:
                    f.write(tail[cut + 1:] if cut >= 0 else tail)
        except OSError:
            pass


def run(settings=None):
    import config
    config.low_priority_thread()
    out = {}
    try:
        if settings is not None:
            out["history"] = trim_settings(settings)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["voice_cache"] = trim_voice_cache()
    except Exception:  # noqa: BLE001
        pass
    trim_logs()
    return out
