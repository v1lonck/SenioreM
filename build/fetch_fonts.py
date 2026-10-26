"""Перед сборкой: скачивает свободные шрифты (Google Fonts, лицензия OFL) с русскими буквами
и делает из них обычные начертания 400 / 600 / 700 -> assets/fonts. Ошибка — не повод
ломать сборку: тогда в программе будут только шрифты Windows."""
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts"
DIRS = ["manrope", "montserrat", "inter", "nunito", "rubik", "golostext", "jost", "exo2",
        "comfortaa", "unbounded", "oswald", "play", "caveat"]
WEIGHTS = {400: "Regular", 600: "SemiBold", 700: "Bold"}
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def get(url, api=False):
    h = {"User-Agent": "SenioreM-build"}
    if api and TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        return r.read()


def set_names(font, family, style):
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
            name.removeNames(nameID=rec.nameID)
    ps = (family + "-" + style).replace(" ", "")
    for nid, val in ((1, family), (2, style), (3, ps), (4, f"{family} {style}"), (6, ps)):
        name.setName(val, nid, 3, 1, 0x409)
        name.setName(val, nid, 1, 0, 0)
    os2 = font["OS/2"]
    sel = os2.fsSelection & ~0b1100001          # сбросить italic/bold/regular
    if style == "Bold":
        sel |= 0b100000
    elif style == "Regular":
        sel |= 0b1000000
    os2.fsSelection = sel
    if "head" in font:
        font["head"].macStyle = 1 if style == "Bold" else 0


def family_of(font):
    n = font["name"]
    return (n.getDebugName(16) or n.getDebugName(1) or "").strip()


def main():
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0
    for d in DIRS:
        try:
            items = json.loads(get(f"https://api.github.com/repos/google/fonts/contents/ofl/{d}", api=True))
            ttfs = [it for it in items if it["name"].lower().endswith(".ttf") and "italic" not in it["name"].lower()]
            for it in items:
                if it["name"] == "OFL.txt":
                    (OUT / f"OFL-{d}.txt").write_bytes(get(it["download_url"]))
            for it in ttfs:
                raw = get(it["download_url"])
                font = TTFont(io.BytesIO(raw))
                fam = family_of(font)
                if "fvar" in font:
                    axes = {a.axisTag: a for a in font["fvar"].axes}
                    for w, style in WEIGHTS.items():
                        f2 = TTFont(io.BytesIO(raw))
                        loc = {}
                        for tag, a in axes.items():
                            loc[tag] = max(a.minValue, min(a.maxValue, w)) if tag == "wght" else a.defaultValue
                        inst = instancer.instantiateVariableFont(f2, loc)
                        if "wght" in axes:
                            inst["OS/2"].usWeightClass = int(loc["wght"])
                        set_names(inst, fam, style)
                        inst.save(str(OUT / f"{fam.replace(' ', '')}-{style}.ttf"))
                        made += 1
                else:
                    (OUT / it["name"]).write_bytes(raw)
                    made += 1
            print(f"{d}: ок ({fam})")
        except Exception as e:  # noqa: BLE001
            print(f"::warning::шрифт {d} не получен: {e}")
    total = sum(f.stat().st_size for f in OUT.glob("*.ttf"))
    print(f"Шрифтов: {made}, {total / 1e6:.1f} МБ")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"::warning::шрифты не скачаны: {e}")
    sys.exit(0)
