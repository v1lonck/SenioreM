"""Установка обновления: запускаем установщик через маленький сценарий, который после установки
обязательно откроет SenioreM снова (даже если установщик не справился — откроется прежняя версия)."""
import os
import subprocess
import sys

import config

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200
BREAKAWAY = 0x01000000


def run(installer):
    """Запускает установку и сразу закрывает программу (её файлы должны освободиться)."""
    log = config.data_dir() / "update.log"
    app = sys.executable if getattr(sys, "frozen", False) else ""
    bat = config.data_dir() / "update.cmd"
    lines = ["@echo off", "chcp 65001 >nul",
             f'"{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS '
             f'/nosplash=1 /LOG="{log}"',
             "ping -n 5 127.0.0.1 >nul"]
    if app:
        lines.append(f'tasklist /FI "IMAGENAME eq SenioreM.exe" 2>nul | find /I "SenioreM.exe" >nul '
                     f'|| start "" "{app}"')
    lines.append('del "%~f0"')
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    args = [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"), "/c", str(bat)]
    try:
        subprocess.Popen(args, creationflags=NO_WINDOW | NEW_GROUP | BREAKAWAY, close_fds=True)
    except OSError:
        try:
            subprocess.Popen(args, creationflags=NO_WINDOW | NEW_GROUP, close_fds=True)
        except OSError:
            subprocess.Popen([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                              "/CLOSEAPPLICATIONS", "/nosplash=1"])
    os._exit(0)
