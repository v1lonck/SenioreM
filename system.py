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
    hit = parse_settings(t)
    if hit:
        return hit
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
    if a == "sysinfo":
        return sysinfo(intent["what"])
    if a == "settings_page":
        return settings_page(intent["uri"], intent["title"])
    return ""


ACTIONS = ("startup_off", "startup_list", "delete_selected", "uninstall", "sysinfo", "settings_page")


# ------------------------------------------------------------------ настройки и характеристики
SETTINGS_PAGES = [
    (("звук",), "ms-settings:sound", "звука"),
    (("микрофон",), "ms-settings:privacy-microphone", "микрофона"),
    (("монитор", "экран", "дисплей", "разрешени"), "ms-settings:display", "экрана"),
    (("блютуз", "bluetooth", "блютус"), "ms-settings:bluetooth", "Bluetooth"),
    (("вайфай", "wi fi", "wifi", "вай фай"), "ms-settings:network-wifi", "Wi-Fi"),
    (("интернет", "сеть", "сети"), "ms-settings:network-status", "сети"),
    (("обновлени",), "ms-settings:windowsupdate", "обновлений"),
    (("мыш",), "ms-settings:mousetouchpad", "мыши"),
    (("клавиатур",), "ms-settings:typing", "клавиатуры"),
    (("автозагрузк", "автозапуск"), "ms-settings:startupapps", "автозагрузки"),
    (("приложени", "программ"), "ms-settings:appsfeatures", "приложений"),
    (("батаре", "питани", "электропитани"), "ms-settings:powersleep", "питания"),
    (("фон", "обои"), "ms-settings:personalization-background", "фона"),
    (("тем", "персонализац", "цвет"), "ms-settings:personalization", "персонализации"),
    (("уведомлени",), "ms-settings:notifications", "уведомлений"),
    (("время", "дат"), "ms-settings:dateandtime", "даты и времени"),
    (("язык", "раскладк"), "ms-settings:regionlanguage", "языка"),
    (("камер",), "ms-settings:privacy-webcam", "камеры"),
    (("принтер",), "ms-settings:printers", "принтеров"),
    (("памят", "хранилищ", "диск"), "ms-settings:storagesense", "памяти"),
    (("игров", "game bar"), "ms-settings:gaming-gamebar", "игрового режима"),
    (("конфиденциальн", "приватн"), "ms-settings:privacy", "конфиденциальности"),
    (("учетн", "аккаунт"), "ms-settings:yourinfo", "учётной записи"),
    (("о системе", "характеристик", "систем"), "ms-settings:about", "системы"),
]
TOOLS = [
    (("диспетчер устройств",), "devmgmt.msc", "диспетчер устройств"),
    (("панель управления",), "control", "панель управления"),
    (("сведения о системе",), "msinfo32", "сведения о системе"),
    (("управление дисками",), "diskmgmt.msc", "управление дисками"),
    (("службы",), "services.msc", "службы"),
    (("редактор реестра", "реестр"), "regedit", "редактор реестра"),
    (("средство диагностики directx", "dxdiag"), "dxdiag", "диагностику DirectX"),
]


def parse_settings(t):
    """«какой у меня монитор», «характеристики компа», «открой настройки звука»…"""
    if re.search(r"(какой|какая|какие|что за|покажи|скажи|узнай).{0,12}(монитор|экран|дисплей)|"
                 r"(характеристик\w*|параметры|частот\w*|герц\w*|разрешени\w*).{0,6}(монитор|экран)", t):
        return {"action": "sysinfo", "what": "monitor"}
    if re.search(r"(характеристик\w*|параметры|железо|конфигурац\w*).{0,10}(компьютер|пк|ноутбук|систем)|"
                 r"что (у меня )?за (компьютер|пк|ноутбук|железо)|какое у меня железо", t):
        return {"action": "sysinfo", "what": "pc"}
    m = re.search(r"(какой|какая|сколько).{0,10}(процессор|видеокарт\w*|оперативк\w*|оперативной памяти|"
                  r"озу|ram|виндовс|windows|систем\w*)", t)
    if m:
        word = m.group(2)
        what = ("cpu" if "процессор" in word else "gpu" if "видео" in word else
                "os" if word.startswith(("виндовс", "windows", "систем")) else "ram")
        return {"action": "sysinfo", "what": what}
    if re.search(r"^(открой|покажи|зайди в|перейди в|включи)\s+", t):
        for keys, cmd, title in TOOLS:
            if any(k in t for k in keys):
                return {"action": "settings_page", "uri": cmd, "title": title}
        if re.search(r"(настройк|параметр)", t):
            for keys, uri, title in SETTINGS_PAGES:
                if any(k in t for k in keys):
                    return {"action": "settings_page", "uri": uri, "title": "настройки " + title}
    return None


INFO_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name })
$vc = Get-CimInstance Win32_VideoController | Where-Object { $_.CurrentHorizontalResolution } | Select-Object -First 1
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$os = (Get-CimInstance Win32_OperatingSystem).Caption
$mons = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID | ForEach-Object {
  ($_.UserFriendlyName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join '' })
$disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { "{0} ({1} ГБ)" -f $_.Model, [math]::Round($_.Size / 1GB) })
[Console]::OutputEncoding = [Text.Encoding]::UTF8
@{cpu=$cpu; gpus=$gpus; ram=$ram; os=$os; monitors=$mons; disks=$disks;
  w=$vc.CurrentHorizontalResolution; h=$vc.CurrentVerticalResolution; hz=$vc.CurrentRefreshRate} | ConvertTo-Json -Compress
"""


def pc_info():
    import json
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", INFO_PS],
                       capture_output=True, timeout=30, creationflags=NO_WINDOW)
    return json.loads(r.stdout.decode("utf-8", "ignore") or "{}")


def _clean(name):
    return re.sub(r"\((R|TM)\)|\(r\)|\(tm\)|CPU|\s+@.*$|\s+Processor", "", name or "", flags=re.I).strip()


def sysinfo(what):
    try:
        info = pc_info()
    except Exception:  # noqa: BLE001
        info = {}
    gpus = [g for g in (info.get("gpus") or []) if g and "basic" not in g.lower()]
    if what == "monitor":
        os.startfile("ms-settings:display-advanced")            # type: ignore[attr-defined]
        mons = [m for m in (info.get("monitors") or []) if m]
        res = (f"{info.get('w')}×{info.get('h')}, {info.get('hz')} Гц" if info.get("w") else "")
        if mons:
            return (f"{'Мониторы' if len(mons) > 1 else 'Монитор'}: {', '.join(mons)}"
                    + (f". Сейчас {res}" if res else "") + ". Открыл дополнительные параметры дисплея.")
        return (f"Сейчас экран {res}. " if res else "") + "Открыл дополнительные параметры дисплея."
    parts = {
        "cpu": f"процессор {_clean(info.get('cpu'))}" if info.get("cpu") else "",
        "gpu": f"видеокарта {', '.join(gpus)}" if gpus else "",
        "ram": f"оперативной памяти {info.get('ram')} ГБ" if info.get("ram") else "",
        "os": info.get("os") or "",
    }
    if what in parts and parts[what]:
        reply = parts[what][:1].upper() + parts[what][1:] + "."
        if what in ("cpu", "ram", "os"):
            os.startfile("ms-settings:about")                     # type: ignore[attr-defined]
        return reply
    os.startfile("ms-settings:about")                             # type: ignore[attr-defined]
    got = [p for p in (parts["cpu"], parts["gpu"], parts["ram"], parts["os"]) if p]
    if not got:
        return "Открыл характеристики компьютера."
    return "У вас " + ", ".join(got) + ". Открыл характеристики компьютера."


def settings_page(uri, title):
    try:
        if uri.startswith("ms-settings:"):
            os.startfile(uri)                                     # type: ignore[attr-defined]
        else:
            subprocess.Popen(uri, shell=True, creationflags=NO_WINDOW)
        return f"Открываю {title}."
    except Exception as e:  # noqa: BLE001
        return f"Не получилось открыть {title}: {e}"
