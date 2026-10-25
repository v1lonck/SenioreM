"""Сколько раз скачали SenioreM — по данным релизов на GitHub (без своего сервера)."""
import json
import time
import urllib.request


def _cache():
    import config
    return config.data_dir() / "downloads.json"


def cached():
    try:
        d = json.loads(_cache().read_text(encoding="utf-8"))
        return int(d["count"]), float(d.get("at", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return None, 0.0


def fetch(repo):
    """Сумма скачиваний установщика по всем релизам. -> число или None."""
    if not repo:
        return None
    total, page = 0, 1
    while page <= 5:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "SenioreM"})
        with urllib.request.urlopen(req, timeout=10) as r:
            rel = json.loads(r.read().decode("utf-8"))
        if not rel:
            break
        for x in rel:
            if x.get("draft") or x.get("tag_name") == "ci-screens":
                continue
            for a in x.get("assets") or []:
                if a.get("name", "").lower().endswith(".exe"):
                    total += int(a.get("download_count") or 0)
        if len(rel) < 100:
            break
        page += 1
    try:
        _cache().write_text(json.dumps({"count": total, "at": time.time()}), encoding="utf-8")
    except OSError:
        pass
    return total


def get(repo, max_age=1800):
    """Свежее число (из кэша, если ему меньше max_age секунд)."""
    n, at = cached()
    if n is not None and time.time() - at < max_age:
        return n
    try:
        return fetch(repo)
    except Exception:  # noqa: BLE001
        return n


def phrase(n):
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        w = "скачивание"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = "скачивания"
    else:
        w = "скачиваний"
    return f"{n:,}".replace(",", " ") + " " + w
