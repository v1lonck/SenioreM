"""Режим администратора.

Окно «Разрешить этому приложению вносить изменения?» (контроль учётных записей Windows)
показывается на защищённом рабочем столе — нажать «Да» в нём не может ни одна программа,
так устроена защита Windows. Поэтому делаем, как принято: один раз, с вашего согласия,
создаём в Планировщике заданий задачу «запускать SenioreM с наивысшими правами».
После этого SenioreM сам работает от администратора, а программы, которые он запускает
(VPN, обход блокировок, игры), открываются уже без этого окна."""
import ctypes
import os
import subprocess
import sys
import time

TASK = "SenioreM Admin"
NO_WINDOW = 0x08000000


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _flag():
    import config
    return config.data_dir() / "admin_mode"


def enabled():
    return _flag().is_file()


def _exe_cmd():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --elevated'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --elevated'


def task_exists():
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True,
                           creationflags=NO_WINDOW, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


class _SEI(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong), ("hwnd", ctypes.c_void_p),
                ("lpVerb", ctypes.c_wchar_p), ("lpFile", ctypes.c_wchar_p),
                ("lpParameters", ctypes.c_wchar_p), ("lpDirectory", ctypes.c_wchar_p),
                ("nShow", ctypes.c_int), ("hInstApp", ctypes.c_void_p), ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
                ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p), ("hProcess", ctypes.c_void_p)]


def run_as_admin(exe, params="", wait=True, show=0):
    """Запуск с правами администратора (Windows спросит разрешение, если SenioreM сам не админ).
    -> True, если запуск состоялся (пользователь не отказался)."""
    sei = _SEI()
    sei.cbSize = ctypes.sizeof(_SEI)
    sei.fMask = 0x00000040 | 0x00000400         # NOCLOSEPROCESS | FLAG_NO_UI
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = show
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return False
    if wait and sei.hProcess:
        ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 30000)
        ctypes.windll.kernel32.CloseHandle(sei.hProcess)
    return True


def _self_args(flag):
    """Как запустить сам SenioreM с флагом (собранный .exe или скрипт)."""
    if getattr(sys, "frozen", False):
        return sys.executable, flag
    return sys.executable, f'"{os.path.abspath(sys.argv[0])}" {flag}'


def create_task():
    """Вызывается в процессе с правами администратора (--setup-admin)."""
    if getattr(sys, "frozen", False):
        tr = f'"{sys.executable}" --elevated'
    else:
        tr = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --elevated'
    user = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/TR", tr, "/SC", "ONCE", "/ST", "00:00",
                        "/RL", "HIGHEST", "/IT", "/RU", user, "/F"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=30)
    if r.returncode != 0:      # без /RU — для текущего пользователя
        r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/TR", tr, "/SC", "ONCE",
                            "/ST", "00:00", "/RL", "HIGHEST", "/F"],
                           capture_output=True, creationflags=NO_WINDOW, timeout=30)
    return r.returncode == 0


def delete_task():
    subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True,
                   creationflags=NO_WINDOW, timeout=30)


def enable():
    """Создаёт задачу (Windows один раз спросит разрешение). -> (успех, сообщение)."""
    if is_admin():
        ok = create_task()
    else:
        # запускаем сам SenioreM с правами администратора — он и создаст задачу
        exe, params = _self_args("--setup-admin")
        started = run_as_admin(exe, params, wait=True, show=0)
        ok = started and task_exists()
        if not started:
            return False, "Разрешение не дано — права администратора не включены."
    if not ok:
        return False, "Windows не дала создать задачу. Попробуйте ещё раз."
    _flag().write_text("1", encoding="utf-8")
    return True, "Готово. SenioreM перезапустится с правами администратора."


def disable():
    try:
        _flag().unlink()
    except OSError:
        pass
    try:
        if is_admin():
            delete_task()
        elif task_exists():
            exe, params = _self_args("--remove-admin")
            run_as_admin(exe, params, wait=False, show=0)
    except Exception:  # noqa: BLE001
        pass


def handle_cli():
    """Служебные запуски: --setup-admin / --remove-admin. -> код выхода или None."""
    if "--setup-admin" in sys.argv:
        return 0 if create_task() else 1
    if "--remove-admin" in sys.argv:
        delete_task()
        return 0
    return None


def relaunch():
    """Перезапуск через задачу — уже с правами администратора и без окна разрешения."""
    try:
        r = subprocess.run(["schtasks", "/Run", "/TN", TASK], capture_output=True,
                           creationflags=NO_WINDOW, timeout=15)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def maybe_restart_elevated():
    """При запуске: если включён режим администратора, а мы запущены обычно — перезапускаемся
    через задачу. -> True, если текущий процесс должен завершиться."""
    if sys.platform != "win32" or "--elevated" in sys.argv or is_admin() or not enabled():
        return False
    if relaunch():
        time.sleep(0.3)
        return True
    return False
