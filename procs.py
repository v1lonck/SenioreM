"""Запущенные программы: найти окно по названию, развернуть, переключиться, закрыть.

Главная идея — сопоставлять не по заголовку окна (он у каждой программы свой), а по
папке, из которой запущен процесс: у osu! это …\\osulazer, у игры из Steam —
…\\steamapps\\common\\<игра>, у Discord — …\\Local\\Discord."""
import ctypes
import os
import re
import subprocess
import time

NO_WINDOW = 0x08000000
SW_RESTORE, SW_SHOW = 9, 5

# процессы, которые никогда не считаем «программой пользователя»
SYSTEM = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "dwm.exe", "system",
          "smss.exe", "lsass.exe", "services.exe", "wininit.exe", "seniorem.exe", "python.exe",
          "pythonw.exe", "searchhost.exe", "startmenuexperiencehost.exe",
          "shellexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe", "sihost.exe",
          "ctfmon.exe", "llama-server.exe", "lockapp.exe", "systemsettingsbroker.exe"}
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe",
            "vivaldi.exe", "yandex.exe"}
# Папки, которые слишком общие, чтобы считать «папкой программы»
_GENERIC = None


def _generic_dirs():
    global _GENERIC
    if _GENERIC is None:
        env = os.environ
        home = env.get("USERPROFILE", "")
        win = env.get("SystemRoot", r"C:\Windows")
        dirs = {home, os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
                os.path.join(home, "Documents"), os.path.join(home, "OneDrive", "Desktop"),
                env.get("LOCALAPPDATA", ""), env.get("APPDATA", ""),
                os.path.join(env.get("LOCALAPPDATA", ""), "Programs"),
                env.get("ProgramFiles", ""), env.get("ProgramFiles(x86)", ""),
                env.get("ProgramW6432", ""), env.get("ProgramData", ""), win,
                os.path.join(win, "System32"), os.path.join(win, "SysWOW64"),
                os.environ.get("SystemDrive", "C:") + "\\"}
        _GENERIC = {os.path.normcase(os.path.normpath(d)) for d in dirs if d}
    return _GENERIC


def _nc(p):
    return os.path.normcase(os.path.normpath(p)) if p else ""


# ------------------------------------------------------------------ окна
class Win:
    __slots__ = ("hwnd", "pid", "title", "exe", "path")

    def __init__(self, hwnd, pid, title, exe, path):
        self.hwnd, self.pid, self.title, self.exe, self.path = hwnd, pid, title, exe, path

    def __repr__(self):
        return f"Win({self.exe!r}, {self.title[:40]!r})"


def _cloaked(hwnd):
    try:
        v = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), 4)
        return v.value != 0
    except Exception:  # noqa: BLE001
        return False


def windows():
    """Главные окна программ, сверху вниз (как на экране)."""
    import psutil
    u = ctypes.windll.user32
    me = os.getpid()
    info = {}
    out = []
    hwnd = u.GetTopWindow(None)
    while hwnd:
        if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4) and not _cloaked(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                pid = ctypes.c_ulong()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                pid = pid.value
                if pid != me:
                    if pid not in info:
                        try:
                            pr = psutil.Process(pid)
                            info[pid] = ((pr.name() or "").lower(), pr.exe() or "")
                        except Exception:  # noqa: BLE001
                            info[pid] = ("", "")
                    exe, path = info[pid]
                    if exe not in SYSTEM:
                        out.append(Win(hwnd, pid, buf.value, exe, path))
        hwnd = u.GetWindow(hwnd, 2)
    return out


def processes():
    """[(pid, имя.exe, путь)] всех процессов (кроме системных)."""
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (p.info["name"] or "").lower()
            if name and name not in SYSTEM and p.info["pid"] != os.getpid():
                out.append((p.info["pid"], name, p.info["exe"] or ""))
        except Exception:  # noqa: BLE001
            pass
    return out


def is_minimized(hwnd):
    return bool(ctypes.windll.user32.IsIconic(hwnd))


def activate(hwnd):
    """Развернуть (если свёрнуто) и вывести окно на передний план."""
    u = ctypes.windll.user32
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)
    else:
        u.ShowWindow(hwnd, SW_SHOW)
    # Windows разрешает менять активное окно только «активной» программе: нажатие Alt
    # снимает это ограничение (известный приём), затем подключаемся к потоку окна.
    try:
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
    except Exception:  # noqa: BLE001
        pass
    fg = u.GetForegroundWindow()
    cur = ctypes.windll.kernel32.GetCurrentThreadId()
    other = u.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if other and other != cur:
        attached = bool(u.AttachThreadInput(cur, other, True))
    try:
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(cur, other, False)


def close_window(hwnd):
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)        # WM_CLOSE


# ------------------------------------------------------------------ откуда запускается программа
def _steam_dir(appid):
    import sites
    root = sites._steam_root() if os.name == "nt" else None
    if not root:
        return ""
    libs = {os.path.join(root, "steamapps")}
    vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="ignore") as f:
            for p in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                libs.add(os.path.join(p.replace("\\\\", "\\"), "steamapps"))
    except OSError:
        pass
    for lib in libs:
        mf = os.path.join(lib, f"appmanifest_{appid}.acf")
        try:
            with open(mf, encoding="utf-8", errors="ignore") as f:
                m = re.search(r'"installdir"\s+"([^"]+)"', f.read())
            if m:
                return os.path.join(lib, "common", m.group(1))
        except OSError:
            continue
    return ""


def _epic_dir(app_name):
    import json
    d = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     r"Epic\EpicGamesLauncher\Data\Manifests")
    try:
        for fn in os.listdir(d):
            if fn.endswith(".item"):
                with open(os.path.join(d, fn), encoding="utf-8", errors="ignore") as f:
                    m = json.load(f)
                if m.get("AppName") == app_name:
                    return m.get("InstallLocation") or ""
    except Exception:  # noqa: BLE001
        pass
    return ""


def _appid_path(appid):
    import sites
    m = re.match(r"^(\{[0-9A-Fa-f-]{36}\})\\(.+)$", appid)
    if m:
        base = sites._env_path(sites.KNOWN_FOLDERS.get(m.group(1).upper(), ""))
        return os.path.join(base, m.group(2)) if base else ""
    if re.match(r"^[A-Za-z]:\\", appid):
        return appid
    return ""


def locate(target):
    """Цель запуска из индекса -> (папки_программы, точные_exe, пакет_Store)."""
    import sites
    kind, value = target
    dirs, exes, package = set(), set(), ""

    def add_exe(path):
        if not path:
            return
        path = _nc(path)
        if path.endswith(".exe"):
            exes.add(path)
            folder = os.path.dirname(path)
        else:
            folder = path
        if folder and folder not in _generic_dirs() and folder.count(os.sep) >= 2:
            dirs.add(folder)

    if kind == "url":
        m = re.match(r"steam://rungameid/(\d+)", value)
        if m:
            d = _steam_dir(m.group(1))
            if d:
                dirs.add(_nc(d))
        m = re.search(r"%3A([^?%]+)\?action=launch", value)
        if m:
            d = _epic_dir(m.group(1))
            if d:
                dirs.add(_nc(d))
    elif kind == "lnk":
        t = sites._lnk_target(value)
        if t.lower().startswith("steam://"):
            return locate(("url", t))
        add_exe(t)
    elif kind == "app":
        if "!" in value:
            package = value.split("!")[0].split("_")[0].lower()
        else:
            add_exe(_appid_path(value))
    elif kind == "path":
        add_exe(value)
    return dirs, exes, package


def _matches(path, dirs, exes, package):
    p = _nc(path)
    if not p:
        return False
    if p in exes:
        return True
    if any(p.startswith(d + os.sep) for d in dirs):
        return True
    if package and ("\\windowsapps\\" + package + "_") in p:
        return True
    return False


def _name_keys(name):
    import sites
    return {k.replace(" ", "") for k in sites.keys_for(name) if len(k.replace(" ", "")) >= 3}


def _exe_stem(exe):
    return re.sub(r"[^a-z0-9а-я]", "", exe.lower().replace(".exe", ""))


def _fuzzy_proc(keys, exe):
    """Имя процесса похоже на сказанное: «озу» -> osu!.exe, «телеграм» -> telegram.exe."""
    import sites
    stem = _exe_stem(exe)
    if len(stem) < 3:
        return False
    return any(k == stem or (len(k) >= 4 and stem.startswith(k)) or sites._score(k, stem) >= 0.9
               for k in keys)


def _title_match(keys, title):
    """Заголовок окна похож на сказанное: «Soundpad» ~ «саундпад», «osu!» ~ «озу»."""
    import sites
    t = sites._norm(sites._latinize(title)) if title else ""
    if not t:
        return False
    flat = t.replace(" ", "")
    words = [w for w in t.split() if len(w) >= 3]
    for k in keys:
        lk = sites._norm(sites._latinize(k)).replace(" ", "")
        if len(lk) < 3:
            continue
        if flat.startswith(lk) or any(sites._score(lk, w) >= 0.88 for w in words[:4]):
            return True
    return False


def foreground():
    """Окно программы, которое было активным до SenioreM (верхнее чужое окно)."""
    for w in windows():
        if w.exe not in ("seniorem.exe",):
            return w
    return None


def find(name="", target=None):
    """Окна и процессы программы. -> (окна [Win], pids без окон {pid: exe})."""
    dirs, exes, package = locate(target) if target else (set(), set(), "")
    keys = _name_keys(name) if name else set()
    wins = []
    for w in windows():
        if w.exe in BROWSERS and not (dirs or exes):
            continue        # вкладка «osu! — YouTube» в браузере — это не osu!
        if (dirs or exes or package) and _matches(w.path, dirs, exes, package):
            wins.append(w)
        elif keys and _fuzzy_proc(keys, w.exe):
            wins.append(w)
        elif keys and w.exe not in BROWSERS and _title_match(keys, w.title):
            wins.append(w)
    win_pids = {w.pid for w in wins}
    rest = {}
    for pid, exe, path in processes():
        if pid in win_pids:
            continue
        if (dirs or exes or package) and _matches(path, dirs, exes, package):
            rest[pid] = exe
        elif keys and exe not in BROWSERS and _fuzzy_proc(keys, exe):
            rest[pid] = exe
    return wins, rest


def bring_up(name, target):
    """Если программа уже открыта — показать её. -> текст ответа или None (не открыта)."""
    try:
        wins, _rest = find(name, target)
    except Exception:  # noqa: BLE001
        return None
    if not wins:
        return None            # не запущена или спрятана в трей — пусть запускается обычно
    w = wins[0]
    was_min = is_minimized(w.hwnd)
    activate(w.hwnd)
    return "minimized" if was_min else "open"


def force_later(wins, wait=3.0):
    """Окно не закрылось за несколько секунд (игры часто игнорируют «закрыть») — завершаем."""
    def later():
        time.sleep(wait)
        u = ctypes.windll.user32
        for w in wins:
            if u.IsWindow(w.hwnd) and u.IsWindowVisible(w.hwnd):
                try:
                    subprocess.run(["taskkill", "/PID", str(w.pid), "/T", "/F"], capture_output=True,
                                   creationflags=NO_WINDOW, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
    import threading
    threading.Thread(target=later, daemon=True).start()


def close(name, target=None):
    """Закрыть программу. -> (сколько закрыто окон/процессов, имена exe)."""
    wins, rest = find(name, target)
    names = set()
    for w in wins:
        close_window(w.hwnd)
        names.add(w.exe)
    tray = {"telegram.exe", "discord.exe", "steam.exe", "spotify.exe", "viber.exe", "skype.exe",
            "whatsapp.exe", "zoom.exe", "ayugram.exe"}
    for pid, exe in rest.items():
        if exe in names and exe not in tray:
            continue        # у программы уже закрываем окно — дочерние процессы закроются сами
        # программа без окон (в трее/фоне) обычную просьбу закрыться не слышит — завершаем
        args = ["/PID", str(pid), "/T"] + (["/F"] if exe in tray or not wins else [])
        try:
            subprocess.run(["taskkill", *args], capture_output=True, creationflags=NO_WINDOW,
                           timeout=10)
            names.add(exe)
        except Exception:  # noqa: BLE001
            pass
    if wins:
        force_later(wins)
    return len(wins) + len(rest), names


# ------------------------------------------------------------------ кто запускает программы
WATCH_IGNORE = {"conhost.exe", "svchost.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
                "backgroundtaskhost.exe", "runtimebroker.exe", "dllhost.exe", "wmiprvse.exe",
                "powershell.exe", "taskhostw.exe", "audiodg.exe", "smartscreen.exe", "consent.exe",
                "llama-server.exe", "werfault.exe", "compattelrunner.exe", "sppsvc.exe"}


def watch_new_processes(seconds=90):
    """Первые полторы минуты после запуска SenioreM записываем все новые программы и кто их
    запустил. Так видно, открывает ли что-то SenioreM или программа запускается сама."""
    import threading

    def work():
        try:
            import psutil
            import sites
            me = os.getpid()
            seen = {p.pid for p in psutil.process_iter()}
            end = time.time() + seconds
            while time.time() < end:
                time.sleep(0.4)
                for p in psutil.process_iter(["pid", "name", "ppid"]):
                    if p.info["pid"] in seen:
                        continue
                    seen.add(p.info["pid"])
                    name = (p.info["name"] or "").lower()
                    if not name or name in WATCH_IGNORE or name in SYSTEM:
                        continue
                    chain, mine = [], False
                    try:
                        cur = p
                        for _ in range(5):
                            par = cur.parent()
                            if par is None:
                                break
                            if par.pid == me:
                                mine = True
                            chain.append((par.name() or "?"))
                            cur = par
                    except Exception:  # noqa: BLE001
                        pass
                    who = " → ".join(chain[:3]) or "неизвестно"
                    why = ("ЗАПУСТИЛ SenioreM" if mine else "открылась сама") + f" (родитель: {who})"
                    sites.log_launch(p.info["name"], ("process", name), "при старте: " + why)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()
