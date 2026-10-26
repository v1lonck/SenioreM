"""Убирает из готовой сборки лишние файлы Qt, чтобы установщик был меньше."""
import shutil
import sys
from pathlib import Path

dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/SenioreM")


def size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


before = size(dist)
qt = next(dist.rglob("PySide6"), None)
removed = []
if qt and qt.is_dir():
    for rel in ("translations", "qml", "resources"):
        t = qt / rel
        if t.exists():
            shutil.rmtree(t)
            removed.append(rel)
    patterns = ["opengl32sw.dll", "Qt6Pdf*.dll", "Qt6Qml*.dll", "Qt6Quick*.dll",
                "Qt6VirtualKeyboard*.dll", "Qt6Network*.dll", "Qt6Svg*.dll",
                "Qt6OpenGL*.dll", "Qt6Multimedia*.dll", "Qt6WebEngine*"]
    for pat in patterns:
        for f in qt.rglob(pat):
            f.unlink()
            removed.append(f.name)
    plugins = qt / "plugins"
    keep_plugins = {"platforms", "styles", "imageformats"}
    if plugins.exists():
        for d in plugins.iterdir():
            if d.is_dir() and d.name not in keep_plugins:
                shutil.rmtree(d)
                removed.append(f"plugins/{d.name}")
        fmt = plugins / "imageformats"
        if fmt.exists():
            for f in fmt.iterdir():
                # оставляем ICO, JPEG, GIF, WebP — фото в чате, сгенерированные картинки, свои фоны
                if not any(k in f.name for k in ("qico", "qjpeg", "qgif", "qwebp")):
                    f.unlink()
                    removed.append(f"imageformats/{f.name}")

after = size(dist)
print(f"Удалено: {len(removed)} элементов")
print(f"Размер сборки: {before / 1e6:.1f} МБ -> {after / 1e6:.1f} МБ")
