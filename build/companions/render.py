"""Рендер SVG-персонажей (Аки, Мия, Рэй) во встроенные наборы кадров через Chromium (Playwright).
Запуск: python build/companions/render.py [--preview]"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import characters  # noqa: E402
import poses  # noqa: E402

NAMES = {"aki": "Аки", "mia": "Мия", "rei": "Рэй"}
SCALE = 0.62          # 820 px * 0.62 ≈ 500 px в высоту — с запасом для «Большого» размера


def frames_for(fn):
    """[(svg, теги)] — стоит (моргает, говорит), сидит (моргает, говорит), лежит (болтает ногами)."""
    out = []
    P = lambda e=0, m=0: fn(eyes=e, mouth=m)  # noqa: E731
    out += [(poses.stand(P(0, 0)), ["idle"]), (poses.stand(P(1, 0)), ["idle"]),
            (poses.stand(P(2, 0)), ["idle"]), (poses.stand(P(0, 1)), ["idle", "talk"]),
            (poses.stand(P(0, 2)), ["idle", "talk"]), (poses.stand(P(1, 2)), ["idle", "talk"])]
    out += [(poses.sit(P(0, 0)), ["sit"]), (poses.sit(P(2, 0)), ["sit"]),
            (poses.sit(P(0, 1)), ["sit", "talk"]), (poses.sit(P(0, 2)), ["sit", "talk"])]
    for k in range(8):
        e = 2 if k == 5 else 0
        out.append((poses.lie(P(e, 0), swing=k / 4.0), ["lie"]))
    return out


def render(names=None, preview=False):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    import make_companions as mk
    names = names or list(NAMES)
    result = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": poses.W, "height": poses.H}, device_scale_factor=1.0)
        for name in names:
            imgs = []
            for svg, tags in frames_for(characters.CHARACTERS[name]):
                pg.set_content("<html><body style='margin:0;background:transparent'>" + svg
                               + "</body></html>")
                png = pg.locator("svg").screenshot(omit_background=True)
                im = Image.open(io.BytesIO(png)).convert("RGBA")
                im = im.resize((int(im.width * SCALE), int(im.height * SCALE)), Image.LANCZOS)
                imgs.append((im, tags))
            result[name] = imgs
            if not preview:
                mk.save(f"builtin-{name}", NAMES[name], imgs, {"lie": 0.22})
        br.close()
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in NAMES]
    res = render(args or None, preview="--preview" in sys.argv)
    if "--preview" in sys.argv:
        from PIL import Image
        out = sys.argv[sys.argv.index("--preview") + 1] if len(sys.argv) > sys.argv.index("--preview") + 1 \
            else "preview.png"
        rows = []
        for name, imgs in res.items():
            pick = [imgs[0], imgs[4], imgs[6], imgs[10], imgs[12]]
            w = sum(i.width for i, _ in pick)
            row = Image.new("RGBA", (w, pick[0][0].height), (40, 44, 60, 255))
            x = 0
            for im, _ in pick:
                row.alpha_composite(im, (x, 0))
                x += im.width
            rows.append(row)
        sheet = Image.new("RGBA", (max(r.width for r in rows), sum(r.height for r in rows)), (40, 44, 60, 255))
        y = 0
        for r in rows:
            sheet.alpha_composite(r, (0, y))
            y += r.height
        sheet.thumbnail((1800, 1400))
        sheet.save(out)
