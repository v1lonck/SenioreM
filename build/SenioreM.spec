# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller build/SenioreM.spec --noconfirm --clean   (запускать из корня проекта)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821

datas = [(os.path.join(ROOT, "assets"), "assets")]
if os.path.exists(os.path.join(ROOT, "config.json")):      # почта, вшитая при сборке
    datas.append((os.path.join(ROOT, "config.json"), "."))

binaries = []
hiddenimports = ["pyttsx3.drivers", "pyttsx3.drivers.sapi5"]
d, b, h = collect_all("vosk")
datas += d
binaries += b
hiddenimports += h
for pkg in ("comtypes", "pycaw", "edge_tts"):
    hiddenimports += collect_submodules(pkg, filter=lambda n: ".test" not in n)

# Всё, что программе не нужно, — не тащим (меньше размер, быстрее скачивание).
excludes = [
    "tkinter", "unittest", "pydoc", "doctest", "lib2to3", "numpy",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf",
    "PySide6.QtSvg", "PySide6.QtOpenGL", "PySide6.QtMultimedia", "PySide6.QtSql",
    "PySide6.QtWebEngineCore", "PySide6.QtDBus", "PySide6.QtConcurrent",
]

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SenioreM",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SenioreM", upx=False)  # noqa: F821
