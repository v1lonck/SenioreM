"""Аля — оригинальная девушка-компаньон в аниме-стиле (худи, леггинсы, кеды).
Позы: стоит, сидит по-турецки, лежит на животе и болтает ногами."""
import math

from drawkit import Canvas

W, H, FLOOR = 320, 400, 390
HS = 1.12           # размер головы
P = dict(skin="#FFE1CF", skin2="#F5C3AA", hair="#4A2F3C", hair2="#6B4456", hair_hi="#8C6378",
         iris="#7B5CD6", iris2="#3F2D86", hood="#9CC8FF", hood2="#78A9EA", legs="#2D2F45",
         shoe="#FFFFFF", sole="#C9D3E6", outline="#2E2230", blush="#FF8FA3", lips="#D86A7A")


def face(c, cx, cy, o, s=1.0):
    """Лицо анфас (центр — середина лица)."""
    blink, talk, smile = o.get("blink"), o.get("talk"), o.get("smile", True)
    # лицо
    c.blob([(cx - 31 * s, cy - 22 * s), (cx - 30 * s, cy + 8 * s), (cx - 20 * s, cy + 28 * s),
            (cx, cy + 38 * s), (cx + 20 * s, cy + 28 * s), (cx + 30 * s, cy + 8 * s),
            (cx + 31 * s, cy - 22 * s), (cx, cy - 34 * s)], P["skin"], ow=2.2)
    # глаза
    for sgn in (-1, 1):
        ex, ey = cx + sgn * 14 * s, cy + 4 * s
        if blink:
            c.arc(ex, ey - 1 * s, 9 * s, 5 * s, 15, 165, P["outline"], 2.6)
            continue
        c.ell(ex, ey, 8.6 * s, 10.5 * s, "#FFFFFF", outline=False)
        c.ell(ex + o.get("look", 0), ey + 1.5 * s, 7 * s, 9 * s, P["iris"], outline=False)
        c.ell(ex + o.get("look", 0), ey + 5 * s, 5.5 * s, 4.5 * s, "#B9A6F2", outline=False, alpha=170)
        c.ell(ex + o.get("look", 0), ey + 0.5 * s, 3.4 * s, 5.2 * s, P["iris2"], outline=False)
        c.ell(ex - 2.6 * s + o.get("look", 0), ey - 3.6 * s, 2.6 * s, 3 * s, "#FFFFFF", outline=False)
        c.ell(ex + 2.8 * s + o.get("look", 0), ey + 4.5 * s, 1.3 * s, 1.3 * s, "#FFFFFF", outline=False)
        # ресницы (верхнее веко)
        c.line([(ex - sgn * -10 * s if False else ex - 10 * s, ey - 7 * s), (ex - 4 * s, ey - 11 * s),
                (ex + 4 * s, ey - 11 * s), (ex + 10 * s, ey - 7 * s)], P["outline"], 2.8, smooth=True)
        c.line([(ex + sgn * 10 * s, ey - 7 * s), (ex + sgn * 13 * s, ey - 9 * s)], P["outline"], 2.0)
    # брови
    for sgn in (-1, 1):
        c.line([(cx + sgn * 8 * s, cy - 13 * s), (cx + sgn * 14 * s, cy - 15 * s),
                (cx + sgn * 21 * s, cy - 13 * s)], P["hair"], 2.0, smooth=True)
    # румянец, нос, рот
    for sgn in (-1, 1):
        c.ell(cx + sgn * 19 * s, cy + 16 * s, 6 * s, 3 * s, P["blush"], outline=False, alpha=110)
    c.line([(cx + 1 * s, cy + 15 * s), (cx, cy + 17 * s)], P["skin2"], 1.6)
    if talk:
        c.blob([(cx - 5 * s, cy + 23 * s), (cx + 5 * s, cy + 23 * s), (cx + 3.5 * s, cy + 30 * s),
                (cx - 3.5 * s, cy + 30 * s)], "#B5485C", ow=1.6)
        c.ell(cx, cy + 28 * s, 2.6 * s, 1.4 * s, "#F49AAA", outline=False)
    elif smile:
        c.arc(cx, cy + 21 * s, 5 * s, 4 * s, 20, 160, P["outline"], 1.9)


def hair_back(c, cx, cy, sway=0.0, length=150, s=1.0):
    """Длинные волосы сзади (рисуются до тела)."""
    L = length * s
    c.blob([(cx - 38 * s, cy - 30 * s), (cx - 46 * s, cy + 10 * s), (cx - 50 * s + sway, cy + L * 0.6),
            (cx - 44 * s + sway * 1.4, cy + L), (cx - 20 * s + sway, cy + L * 0.92),
            (cx + 20 * s + sway, cy + L * 0.92), (cx + 44 * s + sway * 1.4, cy + L),
            (cx + 50 * s + sway, cy + L * 0.6), (cx + 46 * s, cy + 10 * s), (cx + 38 * s, cy - 30 * s),
            (cx, cy - 48 * s)], P["hair"])


def hair_front(c, cx, cy, sway=0.0, side=70, s=1.0):
    """Чёлка, макушка и пряди по бокам лица."""
    # макушка
    c.blob([(cx - 37 * s, cy - 6 * s), (cx - 38 * s, cy - 30 * s), (cx - 20 * s, cy - 46 * s),
            (cx + 4 * s, cy - 50 * s), (cx + 26 * s, cy - 44 * s), (cx + 39 * s, cy - 28 * s),
            (cx + 37 * s, cy - 6 * s), (cx + 30 * s, cy - 18 * s), (cx + 22 * s, cy - 8 * s),
            (cx + 13 * s, cy - 22 * s), (cx + 4 * s, cy - 6 * s), (cx - 6 * s, cy - 22 * s),
            (cx - 16 * s, cy - 8 * s), (cx - 26 * s, cy - 20 * s)], P["hair"])
    # блик
    c.arc(cx - 2 * s, cy - 32 * s, 24 * s, 9 * s, 200, 320, P["hair_hi"], 3.2)
    # боковые пряди
    for sgn in (-1, 1):
        sw = sway * (1 if sgn > 0 else 0.7)
        c.blob([(cx + sgn * 30 * s, cy - 24 * s), (cx + sgn * 39 * s, cy - 4 * s),
                (cx + sgn * 40 * s + sw, cy + side * 0.6 * s), (cx + sgn * 33 * s + sw * 1.3, cy + side * s),
                (cx + sgn * 30 * s + sw, cy + side * 0.55 * s), (cx + sgn * 28 * s, cy + 2 * s)],
               P["hair"])
    # заколка-звёздочка
    x, y = cx + 26 * s, cy - 26 * s
    pts = []
    for k in range(10):
        r = (7 if k % 2 == 0 else 3) * s
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((x + r * math.cos(a), y + r * math.sin(a)))
    c.poly(pts, "#FFD86B", ow=1.6)


def sneaker(c, x, y, flip=1, s=1.0):
    c.blob([(x - 13 * s * flip, y - 12 * s), (x + 6 * s * flip, y - 14 * s), (x + 16 * s * flip, y - 4 * s),
            (x + 17 * s * flip, y + 3 * s), (x - 15 * s * flip, y + 3 * s)], P["shoe"])
    c.line([(x - 15 * s * flip, y + 1 * s), (x + 17 * s * flip, y + 1 * s)], P["sole"], 3.2)


def stand(o):
    c = Canvas(W, H, P["outline"])
    cx = 160
    sway = o.get("sway", 0.0)
    hy = 102
    hair_back(c, cx, hy, sway, 150, s=HS)
    # ноги
    for sgn in (-1, 1):
        x = cx + sgn * 14
        c.limb([(x, 262), (x + sgn * 1, 320), (x + sgn * 2, 372)], 14, 10, P["legs"])
        sneaker(c, x + sgn * 4, 380, flip=sgn)
    # капюшон за шеей
    c.ell(cx, 150, 36, 14, P["hood2"])
    # шея
    c.limb([(cx, 132), (cx, 150)], 8, 8, P["skin"], ow=2.0)
    # худи
    c.blob([(cx - 40, 152), (cx - 47, 200), (cx - 50, 268), (cx, 274), (cx + 50, 268), (cx + 47, 200),
            (cx + 40, 152), (cx, 158)], P["hood"])
    c.line([(cx - 49, 262), (cx, 268), (cx + 49, 262)], P["hood2"], 6, smooth=True)
    c.blob([(cx - 26, 222), (cx + 26, 222), (cx + 31, 250), (cx - 31, 250)], P["hood2"], ow=2.0)
    for sgn in (-1, 1):
        c.line([(cx + sgn * 8, 158), (cx + sgn * 9, 196)], "#FFFFFF", 2.4)
        c.ell(cx + sgn * 9, 198, 2.6, 3.2, "#FFFFFF", ow=1.4)
    # руки
    wave = o.get("wave", 0)
    c.limb([(cx - 40, 160), (cx - 54, 212), (cx - 56, 252)], 12, 10, P["hood"])
    c.ell(cx - 56, 260, 8, 9, P["skin"], ow=2.0)
    if wave:
        a = wave
        c.limb([(cx + 40, 160), (cx + 66, 150), (cx + 72 + a * 4, 110)], 12, 10, P["hood"])
        c.ell(cx + 73 + a * 5, 100, 8.5, 10, P["skin"], ow=2.0, ang=a * 10)
    else:
        c.limb([(cx + 40, 160), (cx + 54, 212), (cx + 56, 252)], 12, 10, P["hood"])
        c.ell(cx + 56, 260, 8, 9, P["skin"], ow=2.0)
    face(c, cx, hy, o, s=HS)
    hair_front(c, cx, hy, sway, 70, s=HS)
    return c.result()


def sit(o):
    """Сидит по-турецки, руки на коленях."""
    c = Canvas(W, H, P["outline"])
    cx = 160
    sway = o.get("sway", 0.0)
    hy = 200
    hair_back(c, cx, hy, sway, 120, s=HS)
    # ноги по-турецки
    for sgn in (-1, 1):
        c.limb([(cx + sgn * 12, 350), (cx + sgn * 60, 362), (cx + sgn * 82, 372)], 16, 14, P["legs"])
    c.limb([(cx - 76, 376), (cx - 20, 382), (cx + 30, 380)], 12, 10, P["legs"])
    c.limb([(cx + 76, 374), (cx + 20, 380), (cx - 26, 382)], 12, 10, P["legs"])
    sneaker(c, cx + 36, 384, flip=1, s=0.9)
    sneaker(c, cx - 34, 386, flip=-1, s=0.9)
    # капюшон, шея, худи
    c.ell(cx, hy + 50, 36, 14, P["hood2"])
    c.limb([(cx, hy + 30), (cx, hy + 50)], 8, 8, P["skin"], ow=2.0)
    c.blob([(cx - 40, hy + 52), (cx - 48, hy + 100), (cx - 54, 356), (cx, 362), (cx + 54, 356),
            (cx + 48, hy + 100), (cx + 40, hy + 52), (cx, hy + 58)], P["hood"])
    c.blob([(cx - 26, 318), (cx + 26, 318), (cx + 31, 344), (cx - 31, 344)], P["hood2"], ow=2.0)
    for sgn in (-1, 1):
        c.line([(cx + sgn * 8, hy + 58), (cx + sgn * 9, hy + 92)], "#FFFFFF", 2.4)
    # руки на коленях
    for sgn in (-1, 1):
        c.limb([(cx + sgn * 40, hy + 60), (cx + sgn * 56, hy + 110), (cx + sgn * 70, 352)], 12, 10, P["hood"])
        c.ell(cx + sgn * 74, 358, 8.5, 8, P["skin"], ow=2.0)
    face(c, cx, hy, o, s=HS)
    hair_front(c, cx, hy, sway, 70, s=HS)
    return c.result()


def lie(o):
    """Лежит на животе, подперев подбородок, и болтает ногами."""
    c = Canvas(W, H, P["outline"])
    kick = o.get("kick", 0.0)        # -1..1
    hx, hy = 92, 296
    # ноги (голени вверх)
    for k, (sgn, ph) in enumerate(((1, kick), (-1, -kick))):
        knee = (250 + k * 6, 372)
        foot = (knee[0] + 6 + ph * 22, knee[1] - 62 + abs(ph) * 8)
        c.limb([(208, 368), knee], 14, 12, P["legs"] if k else "#3A3D58")
        c.limb([knee, foot], 12, 9, P["legs"] if k else "#3A3D58")
        c.blob([(foot[0] - 10, foot[1] + 4), (foot[0] - 8, foot[1] - 16), (foot[0] + 4, foot[1] - 20),
                (foot[0] + 12, foot[1] - 8), (foot[0] + 10, foot[1] + 6)], P["shoe"])
    # тело в худи (лежит)
    c.blob([(118, 334), (170, 340), (226, 352), (232, 378), (170, 384), (120, 382), (100, 360)], P["hood"])
    c.line([(150, 344), (156, 382)], P["hood2"], 4)
    # волосы сзади
    hair_back(c, hx, hy, 0, 64, s=HS)
    # локти на полу, кисти под подбородком
    for sgn in (-1, 1):
        c.limb([(hx + sgn * 34, 382), (hx + sgn * 22, 356), (hx + sgn * 12, 340)], 12, 10, P["hood"])
    face(c, hx, hy, o, s=HS)
    for sgn in (-1, 1):
        c.ell(hx + sgn * 12, 342, 10, 8, P["skin"], ow=2.0)
    hair_front(c, hx, hy, 0, 58, s=HS)
    return c.result()


def frames():
    out = [(stand({}), ["idle"]),
           (stand({"blink": True}), ["idle"]),
           (stand({"sway": 3}), ["idle"]),
           (stand({"look": 2}), ["idle"]),
           (stand({"wave": 1}), ["idle"]),
           (stand({"wave": -1}), ["idle"]),
           (stand({"talk": True}), ["idle", "talk"]),
           (stand({"talk": True, "sway": 2}), ["idle", "talk"]),
           (stand({"talk": True, "wave": 1}), ["idle", "talk"])]
    out += [(sit({}), ["sit"]),
            (sit({"blink": True}), ["sit"]),
            (sit({"sway": 3}), ["sit"]),
            (sit({"look": -2}), ["sit"]),
            (sit({"talk": True}), ["sit", "talk"]),
            (sit({"talk": True, "sway": 2}), ["sit", "talk"])]
    seq = (0.0, 0.5, 0.9, 0.5, 0.0, -0.5, -0.9, -0.5)
    out += [(lie({"kick": k, "blink": i == 5}), ["lie"]) for i, k in enumerate(seq)]
    out += [(lie({"talk": True, "kick": 0.5}), ["lie", "talk"]),
            (lie({"talk": True, "kick": -0.5}), ["lie", "talk"])]
    return out
