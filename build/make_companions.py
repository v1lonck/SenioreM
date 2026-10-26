"""Рисует встроенных персонажей SenioreM в assets/companions (запускать: python build/make_companions.py).
Все персонажи — оригинальные, нарисованы кодом."""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent / "assets" / "companions"

import draw_girl  # noqa: E402
import draw_pets  # noqa: E402

VERSION = 2


def Image_h(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.height


def save(pid, name, frames, seq):
    d = OUT / pid
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    metas = []
    boxes = []
    for k, (im, tags) in enumerate(frames):
        bb = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
        x1, y1, x2, y2 = max(0, bb[0] - 2), max(0, bb[1] - 2), min(im.width, bb[2] + 2), min(im.height, bb[3] + 2)
        im.crop((x1, y1, x2, y2)).save(d / f"f_{k:03d}.png", optimize=True)
        metas.append({"f": f"f_{k:03d}.png", "x": x1, "y": y1, "tags": tags})
        if "idle" in tags:
            boxes.append((x1, y1, x2, y2))
    ix1, iy1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    ix2, iy2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    # сидит на краю: ноги свисают ниже «пола» — запоминаем, насколько (окно опускается на панель задач)
    hang = max([m["y"] + Image_h(d / m["f"]) - iy2 for m in metas if "sit" in m["tags"]] + [0])
    meta = {"v": 2, "name": name, "builtin": VERSION, "frames": metas, "idle_h": iy2 - iy1,
            "idle_w": ix2 - ix1, "cx": (ix1 + ix2) / 2, "bottom": iy2, "seq": seq,
            "hang": max(0, hang - 8)}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(pid, len(frames), "кадров")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save("builtin-alya", "Аля", draw_girl.frames(), {"lie": 0.22})
    save("builtin-cat", draw_pets.CAT["name"], draw_pets.frames(draw_pets.CAT), {"lie": 0.9})
    save("builtin-fox", draw_pets.FOX["name"], draw_pets.frames(draw_pets.FOX), {"lie": 0.9})
