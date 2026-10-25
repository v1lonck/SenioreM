"""Рендер SVG-персонажей в PNG-кадры (глаза × рот) через Chromium (Playwright).
Запуск: python build/companions/render.py [имя ...]  → assets/companions/<имя>_e<0..2>_m<0..2>.png"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import characters  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "companions"


def main(names=None, preview=False):
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    chars = characters.CHARACTERS
    names = names or list(chars)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 400, "height": 820}, device_scale_factor=1.5)
        for name in names:
            for e in range(3):
                for m in range(3):
                    if preview and (e, m) not in ((0, 0), (0, 2), (2, 0)):
                        continue
                    svg = chars[name](eyes=e, mouth=m)
                    pg.set_content("<html><body style='margin:0;background:transparent'>" + svg
                                   + "</body></html>")
                    pg.locator("svg").screenshot(path=str(OUT / f"{name}_e{e}_m{m}.png"),
                                                 omit_background=True)
        br.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(args or None, preview="--preview" in sys.argv)
