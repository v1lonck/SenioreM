"""Котёнок и лисёнок — оригинальные персонажи SenioreM. Позы: стоит, сидит, лежит."""
import math

from drawkit import Canvas, hexc

W, H, FLOOR = 300, 250, 238

CAT = dict(name="Котёнок Мурка", body="#F4A65B", dark="#D57E2E", light="#FFF4E4", inner="#F6B4C2",
           nose="#EE7F98", iris="#4DB36F", iris2="#2E7D4B", outline="#4A3022", ears="cat",
           tail="cat", stripes=True, socks=None, muzzle="cat")
FOX = dict(name="Лисёнок Рыжик", body="#F07B2F", dark="#C9581A", light="#FFF7EE", inner="#FFE3CF",
           nose="#3A2A28", iris="#C98A2B", iris2="#7A4E12", outline="#3F2418", ears="fox",
           tail="fox", stripes=False, socks="#5A3426", muzzle="fox")


def eye(c, x, y, P, blink=False, look=0.0, closed_happy=False, s=1.0):
    if blink or closed_happy:
        if closed_happy:
            c.arc(x, y + 3 * s, 9 * s, 7 * s, 200, 340, P["outline"], 2.8)
        else:
            c.arc(x, y - 2 * s, 10 * s, 6 * s, 20, 160, P["outline"], 2.8)
        return
    c.ell(x, y, 10.5 * s, 13 * s, "#FFFFFF", ow=2.4)
    c.ell(x + look, y + 1.5 * s, 8.5 * s, 11 * s, P["iris"], outline=False)
    c.ell(x + look, y + 4 * s, 7 * s, 6.5 * s, P["iris2"], outline=False, alpha=150)
    c.ell(x + look, y + 1.5 * s, 4.2 * s, 7.5 * s, "#1E1A1A", outline=False)
    c.ell(x + look - 3.2 * s, y - 4 * s, 3.2 * s, 3.6 * s, "#FFFFFF", outline=False)
    c.ell(x + look + 3 * s, y + 5 * s, 1.6 * s, 1.6 * s, "#FFFFFF", outline=False)


def head(c, cx, cy, P, o, r=56, tilt=0.0, sleeping=False):
    """Голова анфас. o: blink, talk, ear (подёргивание уха)."""
    ear_tw = o.get("ear", 0)
    # уши
    if P["ears"] == "cat":
        for sgn in (-1, 1):
            tw = ear_tw if sgn == 1 else 0
            base_l = (cx + sgn * r * 0.18, cy - r * 0.78)
            base_r = (cx + sgn * r * 0.86, cy - r * 0.32)
            tip = (cx + sgn * (r * 0.78 + tw * 4), cy - r * 1.22 + abs(tw) * 5)
            c.blob([base_l, (tip[0] - sgn * 6, tip[1] + 4), tip, (tip[0] + sgn * 3, tip[1] + 8), base_r,
                    (cx + sgn * r * 0.5, cy - r * 0.62)], P["body"])
            c.blob([(cx + sgn * r * 0.34, cy - r * 0.72), (tip[0] - sgn * 3, tip[1] + 12),
                    (cx + sgn * r * 0.74, cy - r * 0.42)], P["inner"], outline=False)
    else:
        for sgn in (-1, 1):
            tw = ear_tw if sgn == 1 else 0
            base_l = (cx + sgn * r * 0.12, cy - r * 0.74)
            base_r = (cx + sgn * r * 0.9, cy - r * 0.26)
            tip = (cx + sgn * (r * 0.86 + tw * 4), cy - r * 1.42 + abs(tw) * 5)
            c.blob([base_l, (tip[0] - sgn * 5, tip[1] + 5), tip, (tip[0] + sgn * 4, tip[1] + 9), base_r,
                    (cx + sgn * r * 0.5, cy - r * 0.6)], P["body"])
            c.blob([(cx + sgn * r * 0.3, cy - r * 0.7), (tip[0] - sgn * 2, tip[1] + 16),
                    (cx + sgn * r * 0.78, cy - r * 0.4)], P["inner"], outline=False)
    # голова с пушистыми щёчками
    pts = []
    for k in range(28):
        t = 2 * math.pi * k / 28
        rr = r
        if 0.15 < math.sin(t) < 0.75 and abs(math.cos(t)) > 0.55:
            rr = r * (1.10 if k % 2 == 0 else 1.0)       # щёчки-пух
        pts.append((cx + rr * 1.06 * math.cos(t), cy + rr * 0.92 * math.sin(t)))
    c.blob(pts, P["body"])
    if P["stripes"]:
        for dx, ln in ((-9, 16), (0, 20), (9, 16)):
            c.line([(cx + dx, cy - r * 0.9 + 2), (cx + dx * 0.8, cy - r * 0.9 + ln)], P["dark"], 4.2)
        for sgn in (-1, 1):
            c.line([(cx + sgn * r * 1.05, cy + 2), (cx + sgn * r * 0.78, cy + 5)], P["dark"], 3.6)
            c.line([(cx + sgn * r * 1.02, cy + 12), (cx + sgn * r * 0.8, cy + 13)], P["dark"], 3.6)
    # мордочка
    if P["muzzle"] == "fox":
        c.blob([(cx - r * 0.95, cy + r * 0.05), (cx - r * 0.45, cy + r * 0.12), (cx, cy - r * 0.05),
                (cx + r * 0.45, cy + r * 0.12), (cx + r * 0.95, cy + r * 0.05), (cx + r * 0.6, cy + r * 0.62),
                (cx, cy + r * 0.86), (cx - r * 0.6, cy + r * 0.62)], P["light"], outline=False)
    else:
        c.ell(cx - r * 0.2, cy + r * 0.42, r * 0.3, r * 0.26, P["light"], outline=False)
        c.ell(cx + r * 0.2, cy + r * 0.42, r * 0.3, r * 0.26, P["light"], outline=False)
        c.ell(cx, cy + r * 0.56, r * 0.26, r * 0.24, P["light"], outline=False)
    # глаза
    ey = cy + r * 0.05
    for sgn in (-1, 1):
        eye(c, cx + sgn * r * 0.44, ey, P, blink=o.get("blink") or sleeping, look=o.get("look", 0),
            s=r / 56)
    # румянец
    for sgn in (-1, 1):
        c.ell(cx + sgn * r * 0.7, cy + r * 0.36, 8, 4.5, "#FF8FA3", outline=False, alpha=110)
    # нос и рот
    ny = cy + r * 0.32
    c.blob([(cx - 6, ny - 3), (cx + 6, ny - 3), (cx, ny + 4)], P["nose"], ow=1.6)
    if o.get("talk"):
        c.blob([(cx - 8, ny + 7), (cx, ny + 5), (cx + 8, ny + 7), (cx + 5, ny + 17), (cx - 5, ny + 17)],
               "#B8404F", ow=2.2)
        c.ell(cx, ny + 14, 4, 2.5, "#F48FA0", outline=False)
    else:
        c.arc(cx - 5, ny + 5, 5, 4.5, 0, 160, P["outline"], 2.2)
        c.arc(cx + 5, ny + 5, 5, 4.5, 20, 180, P["outline"], 2.2)
    # усы
    if P["ears"] == "cat":
        for sgn in (-1, 1):
            for k, dy in enumerate((-2, 5)):
                c.line([(cx + sgn * r * 0.55, ny + dy), (cx + sgn * r * 1.15, ny + dy - 6 + k * 9)],
                       P["outline"], 1.4)


def tail(c, P, pts, r0, r1):
    from drawkit import catmull
    if P["tail"] == "fox":
        path = catmull(pts, closed=False, n=8)
        c.limb(path, r0 * 1.3, r1 * 2.2, P["body"], smooth=False)
        k = int(len(path) * 0.74)
        c.limb(path[k:], r1 * 2.05, r1 * 1.6, P["light"], smooth=False)
    else:
        c.limb(pts, r0, r1, P["body"])
        if P["stripes"]:
            path = catmull(pts, closed=False, n=8)
            for t in (0.5, 0.7, 0.88):
                x, y = path[int(t * (len(path) - 1))]
                c.ell(x, y, 4.5, 4.5, P["dark"], outline=False)


def leg(c, P, x, top, bottom, w=13, far=False):
    col = P["dark"] if far else P["body"]
    c.limb([(x, top), (x, bottom - 6)], w, w * 0.9, col)
    if P["socks"]:
        c.limb([(x, bottom - 26), (x, bottom - 6)], w * 0.92, w * 0.9, P["socks"])
    c.ell(x - 3, bottom - 5, w * 1.15, 7.5, P["socks"] or (P["dark"] if far else P["light"]))


def stand(P, o):
    c = Canvas(W, H, P["outline"])
    ph = o.get("tail", 0.0)
    br = o.get("breath", 0.0)
    # хвост
    tail(c, P, [(222, 150), (250, 128 + ph * 4), (262, 92 + ph * 3), (258 + ph * 12, 62 + abs(ph) * 4),
                (244 + ph * 18, 48)], 10, 9)
    # дальние лапы
    leg(c, P, 120, 165, FLOOR, far=True)
    leg(c, P, 206, 165, FLOOR, far=True)
    # тело
    c.ell(165, 162 - br, 72, 44 + br, P["body"])
    c.ell(160, 182 - br, 50, 18, P["light"], outline=False)
    if P["stripes"]:
        for x in (170, 192, 212):
            c.blob([(x - 8, 121 - br), (x + 6, 121 - br), (x, 146 - br)], P["dark"], outline=False)
    # ближние лапы
    leg(c, P, 104, 172, FLOOR + 2)
    leg(c, P, 192, 172, FLOOR + 2)
    head(c, 96, 112, P, o)
    return c.result()


def sit(P, o):
    c = Canvas(W, H, P["outline"])
    ph = o.get("tail", 0.0)
    br = o.get("breath", 0.0)
    # хвост, обвивающий лапки
    tail(c, P, [(190, 222), (232, 226), (250, 210 + ph * 3), (246 + ph * 8, 182 + ph * 6),
                (232 + ph * 14, 168 + ph * 4)], 10, 8)
    # тело-груша
    c.blob([(150, 128), (196, 160), (206 - br, 206), (192, 234), (150, 238), (108, 234), (94 + br, 206),
            (104, 160)], P["body"])
    c.blob([(150, 150), (176, 172), (180, 214), (150, 234), (120, 214), (124, 172)], P["light"],
           outline=False)
    # бёдра
    c.ell(109, 214, 22, 24, P["body"], ang=-10)
    c.ell(191, 214, 22, 24, P["body"], ang=10)
    # передние лапки
    for x in (134, 166):
        c.limb([(x, 182), (x, 228)], 11, 10, P["body"])
        if P["socks"]:
            c.limb([(x, 212), (x, 228)], 10.2, 10, P["socks"])
        c.ell(x, 233, 13, 7, P["socks"] or P["light"])
    head(c, 150, 104 - br * 0.5, P, o, tilt=o.get("tilt", 0))
    return c.result()


def lie(P, o):
    c = Canvas(W, H, P["outline"])
    br = o.get("breath", 0.0)
    ph = o.get("tail", 0.0)
    # тело калачиком
    c.ell(176, 206 - br, 92, 34 + br, P["body"])
    if P["stripes"]:
        for x in (176, 204, 230):
            c.blob([(x - 9, 173 - br), (x + 7, 173 - br), (x, 196 - br)], P["dark"], outline=False)
    # задняя лапа
    c.ell(232, 222, 30, 15, P["body"], ang=-8)
    c.ell(258, 230, 13, 7, P["socks"] or P["light"])
    # хвост вдоль земли
    if P["tail"] == "fox":
        tail(c, P, [(258, 200), (282, 214), (270, 230), (210, 232), (160 - ph * 4, 230 - ph * 2)], 8, 7)
    else:
        tail(c, P, [(262, 214), (276, 226), (262, 236), (200, 238), (140 - ph * 4, 236 - ph * 2)], 9, 8)
    # передние лапки под мордой
    c.ell(92, 231, 22, 8, P["socks"] or P["light"])
    c.ell(126, 233, 20, 7.5, P["socks"] or P["light"])
    head(c, 96, 186, P, o, r=52, sleeping=o.get("sleep", True))
    # Zzz
    z = o.get("z")
    if z is not None:
        for k, (dx, dy, s) in enumerate(((28, -70, 9), (44, -88, 12), (62, -110, 15))):
            if k <= z:
                x, y = 96 + dx, 186 + dy
                c.line([(x - s / 2, y - s / 2), (x + s / 2, y - s / 2), (x - s / 2, y + s / 2),
                        (x + s / 2, y + s / 2)], "#8FB4FF", 2.6)
    return c.result()


def frames(P):
    """[(картинка, теги)]: первая в каждой позе — основная."""
    out = []
    out += [(stand(P, {}), ["idle"]),
            (stand(P, {"blink": True}), ["idle"]),
            (stand(P, {"tail": 1.0, "breath": 1.2}), ["idle"]),
            (stand(P, {"tail": -0.8, "ear": 1}), ["idle"]),
            (stand(P, {"look": -2.5, "tail": 0.5}), ["idle"]),
            (stand(P, {"talk": True}), ["idle", "talk"]),
            (stand(P, {"talk": True, "tail": 1.0}), ["idle", "talk"])]
    out += [(sit(P, {}), ["sit"]),
            (sit(P, {"blink": True}), ["sit"]),
            (sit(P, {"tail": 1.0, "breath": 1.0}), ["sit"]),
            (sit(P, {"ear": 1, "look": 2.5}), ["sit"]),
            (sit(P, {"talk": True}), ["sit", "talk"]),
            (sit(P, {"talk": True, "tail": 0.8}), ["sit", "talk"])]
    out += [(lie(P, {"z": 0}), ["lie"]),
            (lie(P, {"z": 1, "breath": 1.5}), ["lie"]),
            (lie(P, {"z": 2, "breath": 2.5, "tail": 1}), ["lie"]),
            (lie(P, {"z": None, "breath": 1.0}), ["lie"]),
            (lie(P, {"sleep": False, "talk": True, "z": None}), ["lie", "talk"])]
    return out
