# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller build/SenioreM.spec --noconfirm --clean   (запускать из корня проекта)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821

datas = [(os.path.join(ROOT, "assets"), "assets")]
if os.path.exists(os.path.join(ROOT, "config.json")):      # версия и откуда брать обновления (без паролей)
    datas.append((os.path.join(ROOT, "config.json"), "."))

binaries = []
hiddenimports = []
for pkg in ("vosk", "piper", "onnxruntime", "faster_whisper", "ctranslate2", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
for pkg in ("comtypes", "pycaw"):
    hiddenimports += collect_submodules(pkg, filter=lambda n: ".test" not in n)

# Всё, что программе не нужно, — не тащим (меньше размер, быстрее скачивание).
excludes = [
    "tkinter", "pydoc", "doctest", "lib2to3", "edge_tts", "pyttsx3", "av", "torch",
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

# Сведения о программе в свойствах файла (издатель, описание, версия) — антивирусы меньше
# подозревают файлы, у которых они заполнены.
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,  # noqa: E402
                                                 StringTable, VarFileInfo, VarStruct, VSVersionInfo)
_ver = (os.environ.get("APP_VERSION") or "1.0").strip()
_nums = tuple((list(int(x) for x in _ver.split(".") if x.isdigit()) + [0, 0, 0, 0])[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_nums, prodvers=_nums, mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("041904B0", [
        StringStruct("CompanyName", "SenioreM"),
        StringStruct("FileDescription", "SenioreM — голосовой помощник"),
        StringStruct("FileVersion", _ver),
        StringStruct("InternalName", "SenioreM"),
        StringStruct("LegalCopyright", "© 2026 v1lonck"),
        StringStruct("OriginalFilename", "SenioreM.exe"),
        StringStruct("ProductName", "SenioreM"),
        StringStruct("ProductVersion", _ver)])]),
        VarFileInfo([VarStruct("Translation", [0x0419, 1200])])])
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SenioreM",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=False,
    upx=False,
    version=version_info,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SenioreM", upx=False)  # noqa: F821
