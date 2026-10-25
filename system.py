"""Автозапуск программ и удаление: «убери роблокс из автозапуска», «что у меня в автозапуске»,
«удали это» (выделенное — в корзину), «удали программу …»."""
import os
import re
import struct
import subprocess
import sys
import time

NO_WINDOW = 0x08000000
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN32 = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
UWP = (r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel"
       r"\SystemAppData")


def parse(text):
    import commands
    t = commands.normalize(text)
    m = re.search(r"(выключи|убери|отключи|удали|исключи|запрети)\s+(.+?)\s+(из|с|со)\s+"
                  r"(автозапуск\w*|автозагрузк\w*|запуска windows|загрузки)", t)
    if m:
        return {"action": "startup_off", "name": m.group(2)}
    m = re.search(r"(выключи|убери|отключи|удали|исключи)\s+(из|с|со)\s+(автозапуск\w*|автозагрузк\w*)"
                  r"\s+(.+)$", t) or \
        re.search(r"(выключи|убери|отключи)\s+(автозапуск\w*|автозагрузк\w*)\s+(у\s+)?(.+)$", t)
    if m:
        return {"action": "startup_off", "name": m.group(4)}
    if re.search(r"(что|какие программы)\s+(у меня\s+)?(в|при)\s+(автозапуск|автозагрузк|запуске)", t) \
            or t in ("покажи автозапуск", "автозапуск", "покажи автозагрузку"):
        return {"action": "startup_list"}
    if re.fullmatch(r"(удали|удалить|сотри|в корзину)\s*(это|этот файл|эту папку|выделенное|файл|"
                    r"выбранное|его|ее|их|это в корзину)?", t):
        return {"action": "delete_selected"}
    m = re.search(r"(удали|удалить|снеси|деинсталлируй)\s+(программу|игру|приложение)?\s*(.+?)"
                  r"(\s+с компьютера|\s+с компа)?$", t)
    if m and (m.group(2) or m.group(4)):
        return {"action": "uninstall", "name": m.group(3)}
    return None


# ------------------------------------------------------------------ автозапуск
def _entries():
    """[(имя, команда, где)] — всё, что запускается вместе с Windows."""
    import winreg
    out = []
    for root, path, where in ((winreg.HKEY_CURRENT_USER, RUN, "hkcu"),
                              (winreg.HKEY_LOCAL_MACHINE, RUN, "hklm"),
                              (winreg.HKEY_LOCAL_MACHINE, RUN32, "hklm32")):
        try:
            with winreg.OpenKey(root, path) as k:
                for i in range(winreg.QueryInfoKey(k)[1]):
                    name, val, _ = winreg.EnumValue(k, i)
                    out.append((name, str(val), where))
        except OSError:
            continue
    # приложения из Microsoft Store (например, Roblox из Store) — у них свои «задачи запуска»
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UWP) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                pkg = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(k, pkg) as pk:
                        for j in range(winreg.QueryInfoKey(pk)[0]):
                            task = winreg.EnumKey(pk, j)
                            try:
                                with winreg.OpenKey(pk, task) as tk:
                                    winreg.QueryValueEx(tk, "State")
                                nice = pkg.split("_")[0].split(".")[-1]
                                out.append((nice, pkg + "\\" + task, "uwp"))
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        pass
    for folder, where in ((os.path.join(os.environ.get("APPDATA", ""),
                                        r"Microsoft\Windows\Start Menu\Programs\Startup"), "folder"),
                          (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                        r"Microsoft\Windows\Start Menu\Programs\StartUp"), "cfolder")):
        try:
            for f in os.listdir(folder):
                if f.lower() != "desktop.ini":
                    out.append((f, os.path.join(folder, f), where))
        except OSError:
            continue
    return out


def _disabled(name, where):
    import winreg
    if where == "uwp":
        return False
    root = winreg.HKEY_CURRENT_USER if where in ("hkcu", "folder") else winreg.HKEY_LOCAL_MACHINE
    sub = {"hkcu": "Run", "hklm": "Run", "hklm32": "Run32", "folder": "StartupFolder",
           "cfolder": "StartupFolder"}[where]
    try:
        with winreg.OpenKey(root, APPROVED + "\\" + sub) as k:
            v = winreg.QueryValueEx(k, name)[0]
            return bool(v) and v[0] in (1, 3)
    except OSError:
        return False


def _match(name, entries):
    import sites
    keys = {k.replace(" ", "") for k in sites.keys_for(name) if len(k.replace(" ", "")) >= 3}
    hits = []
    for ename, cmd, where in entries:
        base = os.path.splitext(ename)[0]
        exe = os.path.splitext(os.path.basename(re.sub(r'^"|".*$', "", cmd.split(" -")[0]).strip()))[0]
        cand = [sites._norm(sites._latinize(base)), sites._norm(sites._latinize(exe))]
        sc = 0.0
        for k in keys:
            lk = sites._norm(sites._latinize(k)).replace(" ", "")
            for c in cand:
                c2 = c.replace(" ", "")
                if not c2:
                    continue
                if lk == c2 or c2.startswith(lk) or (len(lk) >= 4 and lk in c2):
                    sc = max(sc, 1.0)
                else:
                    sc = max(sc, sites._score(lk, c2))
        if sc >= 0.85:
            hits.append((ename, cmd, where))
    return hits


def _approved_bytes(on):
    ft = int((time.time() + 11644473600) * 10_000_000)
    return struct.pack("<I", 2 if on else 3) + (b"\x00" * 8 if on else struct.pack("<Q", ft))


def startup_off(name):
    if sys.platform != "win32":
        return "Это работает только в Windows."
    entries = _entries()
    hits = _match(name, entries)
    if not hits:
        names = ", ".join(sorted({os.path.splitext(e[0])[0] for e in entries})[:12])
        return (f"Не нашёл «{name}» в автозапуске." + (f" Там сейчас: {names}." if names else ""))
    import winreg
    done, need_admin = [], []
    for ename, _cmd, where in hits:
        if where == "uwp":
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UWP + "\\" + _cmd, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "State", 0, winreg.REG_DWORD, 1)     # выключено пользователем
                done.append(ename)
            except OSError:
                pass
            continue
        sub = {"hkcu": "Run", "hklm": "Run", "hklm32": "Run32", "folder": "StartupFolder",
               "cfolder": "StartupFolder"}[where]
        root = winreg.HKEY_CURRENT_USER if where in ("hkcu", "folder") else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.CreateKeyEx(root, APPROVED + "\\" + sub, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, ename, 0, winreg.REG_BINARY, _approved_bytes(False))
            done.append(os.path.splitext(ename)[0])
        except OSError:
            need_admin.append((ename, sub))
    if need_admin:
        # программы «для всех пользователей» — нужны права администратора (Windows спросит)
        import elevate
        data = _approved_bytes(False).hex()
        cmds = " & ".join(
            f'reg add "HKLM\\{APPROVED}\\{sub}" /v "{ename}" /t REG_BINARY /d {data} /f'
            for ename, sub in need_admin)
        if elevate.run_as_admin("cmd.exe", f'/c {cmds}'):
            done += [os.path.splitext(e)[0] for e, _ in need_admin]
    if not done:
        return "Не получилось — нужны права администратора."
    return f"Убрал из автозапуска: {', '.join(dict.fromkeys(done))}. Сработает при следующем включении компьютера."


def startup_list():
    if sys.platform != "win32":
        return "Это работает только в Windows."
    on = sorted({os.path.splitext(n)[0] for n, _c, w in _entries() if not _disabled(n, w)})
    if not on:
        return "В автозапуске ничего нет."
    return "Вместе с Windows запускаются: " + ", ".join(on[:15]) + "."


# ------------------------------------------------------------------ удаление
def delete_selected():
    """Удалить выделенное в Проводнике (или в другой программе) — клавиша Delete, в корзину."""
    import control
    import procs
    w = procs.foreground()
    if w is None:
        return "Не вижу открытых окон."
    control._focus(w)
    control.press([0x2E])
    return "Удалил в корзину." if w.exe == "explorer.exe" else "Нажал «Удалить»."


def uninstall(name):
    """Открывает удаление программы (сам удалитель программы спросит подтверждение)."""
    import winreg
    import sites
    best, best_sc = None, 0.0
    keys = {k for k in sites.keys_for(name) if len(k.replace(" ", "")) >= 3}
    for root, base in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            k = winreg.OpenKey(root, base)
        except OSError:
            continue
        with k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                try:
                    sub = base + "\\" + winreg.EnumKey(k, i)
                    disp = sites._reg_value(root, sub, "DisplayName")
                    cmd = sites._reg_value(root, sub, "UninstallString")
                    if not disp or not cmd or sites._reg_value(root, sub, "SystemComponent") == 1:
                        continue
                    sc = max(sites._score(sites._norm(kk), sites._norm(disp)) for kk in keys)
                    if sc > best_sc:
                        best, best_sc = (disp, cmd), sc
                except Exception:  # noqa: BLE001
                    continue
    if best is None or best_sc < 0.85:
        # игра из Steam
        hit = sites.find_program(name, threshold=0.85)
        if hit and hit[1][0] == "url" and "rungameid" in hit[1][1]:
            os.startfile(hit[1][1].replace("rungameid", "uninstall"))   # type: ignore[attr-defined]
            return f"Открываю удаление {hit[0]} в Steam — подтвердите там."
        os.startfile("ms-settings:appsfeatures")                       # type: ignore[attr-defined]
        return f"Не нашёл «{name}» среди установленных программ. Открыл список программ Windows."
    disp, cmd = best
    try:
        subprocess.Popen(cmd, shell=True, creationflags=NO_WINDOW)
    except Exception:  # noqa: BLE001
        os.startfile("ms-settings:appsfeatures")                       # type: ignore[attr-defined]
    return f"Открываю удаление «{disp}». Подтвердите в окне удаления."


def run(intent):
    a = intent["action"]
    if a == "startup_off":
        return startup_off(intent["name"])
    if a == "startup_list":
        return startup_list()
    if a == "delete_selected":
        return delete_selected()
    if a == "uninstall":
        return uninstall(intent["name"])
    return ""


ACTIONS = ("startup_off", "startup_list", "delete_selected", "uninstall")
