"""Рисует иконку программы, иконку установщика и картинки мастера установки."""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # рисуем крупно, потом уменьшаем


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def radial(size, center, radius, inner, outer, power=1.0):
    w, h = size
    img = Image.new("RGBA", size)
    px = img.load()
    cx, cy = center
    for y in range(h):
        for x in range(w):
            d = min(1.0, math.hypot(x - cx, y - cy) / radius) ** power
            px[x, y] = lerp(inner, outer, d)
    return img


def squircle_mask(size, radius_frac=0.235):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1),
                                        radius=int(size * radius_frac), fill=255)
    return m


def orb(size, base_cx, base_cy, r):
    """Светящийся янтарный шар с бликом."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # мягкое свечение
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((base_cx - r * 1.9, base_cy - r * 1.9,
                                  base_cx + r * 1.9, base_cy + r * 1.9),
                                 fill=(255, 150, 70, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.75))
    layer = Image.alpha_composite(layer, glow)
    # сам шар: градиент от светлого верха к тёплому низу
    ball = radial((size, size), (base_cx - r * 0.35, base_cy - r * 0.45), r * 1.75,
                  (255, 236, 196, 255), (214, 96, 52, 255), power=0.9)
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((base_cx - r, base_cy - r, base_cx + r, base_cy + r), fill=255)
    layer.paste(ball, (0, 0), m)
    # блик
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((base_cx - r * 0.55, base_cy - r * 0.78,
                                base_cx + r * 0.05, base_cy - r * 0.30),
                               fill=(255, 255, 255, 120))
    hl = hl.filter(ImageFilter.GaussianBlur(r * 0.12))
    hl.putalpha(ImageChops.multiply(hl.getchannel("A"), m))
    return Image.alpha_composite(layer, hl)


def waves(size, cx, cy, radii, width, alpha):
    """Тонкие кольца-волны голоса, справа и слева от шара."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, rr in enumerate(radii):
        a = int(alpha * (1 - i * 0.28))
        for start in (-48, 132):
            d.arc((cx - rr, cy - rr, cx + rr, cy + rr), start, start + 96,
                  fill=(255, 206, 150, a), width=width)
    return layer


FONT_DIR = "/usr/share/fonts/opentype/inter/"
NAVY = (8, 16, 46, 255)
BLUE = (37, 99, 255, 255)
SKY = (120, 170, 255, 255)


def diagonal(size, c1, c2):
    """Диагональный градиент: c1 слева сверху -> c2 справа снизу."""
    w, h = size
    k = 255.0 / max(1, w + h - 2)
    g = Image.new("L", size)
    g.putdata([int((x + y) * k) for y in range(h) for x in range(w)])
    return Image.composite(Image.new("RGBA", size, c2), Image.new("RGBA", size, c1), g)


def letter_s(size, color, shadow=True):
    from PIL import ImageFont
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    f = ImageFont.truetype(FONT_DIR + "InterDisplay-SemiBold.otf", int(size * 0.70))
    cx, cy = size / 2, size * 0.515
    if shadow:
        sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((cx, cy + size * 0.025), "S", font=f, fill=(4, 10, 40, 150), anchor="mm")
        layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(size * 0.025)))
    d = ImageDraw.Draw(layer)
    d.text((cx, cy), "S", font=f, fill=color, anchor="mm")
    return layer


def app_icon():
    bg = diagonal((S, S), (14, 30, 90, 255), (46, 110, 255, 255))
    # мягкий свет сверху слева
    light = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(light).ellipse((-S * 0.3, -S * 0.45, S * 0.75, S * 0.5), fill=(140, 190, 255, 70))
    bg = Image.alpha_composite(bg, light.filter(ImageFilter.GaussianBlur(S * 0.12)))
    # тонкие кольца — «голос»
    rings = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(rings)
    for r, a in ((0.43, 34), (0.36, 22)):
        d.ellipse((S / 2 - S * r, S / 2 - S * r, S / 2 + S * r, S / 2 + S * r),
                  outline=(255, 255, 255, a), width=int(S * 0.008))
    bg = Image.alpha_composite(bg, rings)
    bg = Image.alpha_composite(bg, letter_s(S, (255, 255, 255, 255)))
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle((3, 3, S - 4, S - 4), radius=int(S * 0.232),
                                           outline=(255, 255, 255, 40), width=4)
    bg = Image.alpha_composite(bg, edge)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(bg, (0, 0), squircle_mask(S))
    return img


def setup_icon():
    """Иконка установщика — светлая, со стрелкой, чтобы не путать с программой."""
    bg = diagonal((S, S), (250, 252, 255, 255), (214, 228, 255, 255))
    bg = Image.alpha_composite(bg, letter_s(S, (37, 99, 255, 255), shadow=False))
    d = ImageDraw.Draw(bg)
    cx, cy, r = S * 0.76, S * 0.76, S * 0.17
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(14, 30, 90, 255))
    w = r * 0.42
    d.rectangle((cx - w * 0.28, cy - r * 0.52, cx + w * 0.28, cy + r * 0.05), fill=(255, 255, 255, 255))
    d.polygon([(cx - w, cy), (cx + w, cy), (cx, cy + r * 0.5)], fill=(255, 255, 255, 255))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(bg, (0, 0), squircle_mask(S))
    return img


def save_ico(img, path):
    img.save(path, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
                          (64, 64), (96, 96), (128, 128), (256, 256)])


def wizard_images(icon):
    out = ROOT / "build"
    for w, h in ((164, 314), (410, 797)):
        k = 3
        W, H = w * k, h * k
        bg = radial((W, H), (W * 0.5, H * 0.36), H * 0.75,
                    (22, 40, 104, 255), (6, 10, 28, 255), power=1.0)
        logo = icon.resize((int(W * 0.62),) * 2, Image.LANCZOS)
        bg.alpha_composite(logo, (int((W - logo.width) / 2), int(H * 0.36 - logo.height / 2)))
        try:
            from PIL import ImageFont
            fdir = "/usr/share/fonts/opentype/inter/"
            title = ImageFont.truetype(fdir + "InterDisplay-Light.otf", int(W * 0.17))
            small = ImageFont.truetype(fdir + "InterDisplay-SemiBold.otf", int(W * 0.045))
            d = ImageDraw.Draw(bg)
            d.text((W / 2, H * 0.62), "SenioreM", font=title, fill=(238, 235, 229, 255), anchor="mm")
            d.text((W / 2, H * 0.68), "VOICE  ASSISTANT", font=small,
                   fill=(120, 170, 255, 255), anchor="mm")
        except OSError:
            pass
        bg.convert("RGB").resize((w, h), Image.LANCZOS).save(out / f"wizard_{w}.bmp")
    for w, h in ((55, 55), (138, 140)):
        k = 4
        bg = Image.new("RGBA", (w * k, h * k), (22, 26, 35, 255))
        logo = icon.resize((int(w * k * 0.9),) * 2, Image.LANCZOS)
        bg.alpha_composite(logo, (int((w * k - logo.width) / 2), int((h * k - logo.height) / 2)))
        bg.convert("RGB").resize((w, h), Image.LANCZOS).save(out / f"small_{w}.bmp")


if __name__ == "__main__":
    icon = app_icon()
    save_ico(icon, ROOT / "assets" / "icon.ico")
    icon.resize((512, 512), Image.LANCZOS).save(ROOT / "assets" / "icon.png")
    save_ico(setup_icon(), ROOT / "build" / "setup.ico")
    wizard_images(icon)
    print("ok")
