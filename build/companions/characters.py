"""Оригинальные персонажи-компаньоны SenioreM в виде SVG (рисует код, без чужих персонажей).
Каждая функция возвращает SVG 400×820 с нужным состоянием глаз (0 — открыты, 1 — прищур,
2 — закрыты) и рта (0 — закрыт, 1 — приоткрыт, 2 — открыт)."""
import math

LINE = "#2A2633"
SKIN = "#FFE9DF"
SKIN_SH = "#F5CFC3"


def _zig(x0, x1, y, depth, n, sign=1):
    """Неровный край волос: зубчики от x0 до x1."""
    pts = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        pts.append((x, y + (depth if i % 2 else 0) * sign))
    return " ".join(f"L {x:.1f} {y_:.1f}" for x, y_ in pts)


def _locks(left, right, top_y, tips, base_y):
    """Чёлка из прядей: tips — список (x, y) кончиков слева направо."""
    d = f"M {left[0]} {left[1]} C {left[0] - 4} {top_y + 30} {left[0] + 30} {top_y} 200 {top_y} " \
        f"C {right[0] - 30} {top_y} {right[0] + 4} {top_y + 30} {right[0]} {right[1]} "
    xs = [right[0]] + [t[0] for t in reversed(tips)] + [left[0]]
    ys = [right[1]] + [t[1] for t in reversed(tips)] + [left[1]]
    for i in range(1, len(xs)):
        # между кончиками — «впадина» повыше, пряди изогнуты
        mx = (xs[i - 1] + xs[i]) / 2
        my = base_y + (ys[i - 1] + ys[i]) / 2 * 0 - 0
        d += f"Q {mx + 3:.1f} {my:.1f} {xs[i]:.1f} {ys[i]:.1f} "
    return d + "Z"


def eye(cx, cy, iris, state, mirror=False, lash=LINE):
    """Аниме-глаз. mirror=True — правый глаз (внешний уголок справа)."""
    tr = f' transform="translate({2 * cx} 0) scale(-1 1)"' if mirror else ""
    gid = f"ir{int(cx)}{int(cy)}"
    if state == 2:
        return (f'<g{tr}><path d="M {cx - 22} {cy + 2} Q {cx} {cy + 13} {cx + 22} {cy + 1}" '
                f'fill="none" stroke="{lash}" stroke-width="4.2" stroke-linecap="round"/>'
                f'<path d="M {cx - 22} {cy + 2} l -6 -4" stroke="{lash}" stroke-width="3" '
                f'stroke-linecap="round"/></g>')
    top = cy - 24 if state == 0 else cy - 6
    clip = f"clip{gid}{state}"
    s = [f'<g{tr}>',
         f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{_shade(iris, -0.55)}"/>'
         f'<stop offset="0.55" stop-color="{iris}"/>'
         f'<stop offset="1" stop-color="{_shade(iris, 0.45)}"/></linearGradient>'
         f'<clipPath id="{clip}"><path d="M {cx - 30} {top + 1} Q {cx} {top - 4} {cx + 30} {top - 3} '
         f'L {cx + 30} {cy + 40} L {cx - 30} {cy + 40} Z"/></clipPath></defs>',
         f'<g clip-path="url(#{clip})">',
         f'<path d="M {cx - 21} {cy - 6} C {cx - 21} {cy - 26} {cx + 21} {cy - 28} {cx + 21} {cy - 6} '
         f'C {cx + 21} {cy + 16} {cx + 10} {cy + 26} {cx} {cy + 26} C {cx - 12} {cy + 26} {cx - 21} '
         f'{cy + 14} {cx - 21} {cy - 6} Z" fill="#FFFFFF"/>',
         f'<ellipse cx="{cx + 1}" cy="{cy + 2}" rx="16" ry="22" fill="url(#{gid})" '
         f'stroke="{_shade(iris, -0.6)}" stroke-width="1.6"/>',
         f'<ellipse cx="{cx + 1}" cy="{cy + 5}" rx="7.5" ry="11" fill="{_shade(iris, -0.75)}"/>',
         f'<path d="M {cx - 13} {cy + 12} Q {cx + 1} {cy + 22} {cx + 15} {cy + 11}" fill="none" '
         f'stroke="{_shade(iris, 0.7)}" stroke-width="2.4" opacity="0.8"/>',
         f'<ellipse cx="{cx - 6}" cy="{cy - 8}" rx="6.2" ry="7.6" fill="#FFFFFF"/>',
         f'<circle cx="{cx + 7}" cy="{cy + 11}" r="2.6" fill="#FFFFFF"/>',
         f'<circle cx="{cx + 9}" cy="{cy - 10}" r="1.6" fill="#FFFFFF" opacity="0.9"/>',
         '</g>',
         # верхнее веко с ресницами
         f'<path d="M {cx - 25} {top + 6} Q {cx - 4} {top - 9} {cx + 22} {top - 1} '
         f'Q {cx + 25} {top + 1} {cx + 24} {top + 5} Q {cx} {top - 4} {cx - 22} {top + 9} Z" '
         f'fill="{lash}" stroke="{lash}" stroke-width="2.6" stroke-linejoin="round"/>',
         f'<path d="M {cx - 23} {top + 6} l -8 -6 M {cx - 23} {top + 9} l -7 1" stroke="{lash}" '
         f'stroke-width="2.6" stroke-linecap="round"/>',
         # нижние ресницы
         f'<path d="M {cx - 8} {cy + 27} Q {cx + 6} {cy + 28} {cx + 14} {cy + 22}" fill="none" '
         f'stroke="{lash}" stroke-width="1.6" stroke-linecap="round" opacity="0.75"/>',
         '</g>']
    return "".join(s)


def mouth(cx, cy, state):
    if state == 0:
        return (f'<path d="M {cx - 9} {cy} Q {cx} {cy + 6} {cx + 9} {cy - 1}" fill="none" '
                f'stroke="#B0566A" stroke-width="2.6" stroke-linecap="round"/>')
    w, h = (8, 7) if state == 1 else (11, 13)
    return (f'<path d="M {cx - w} {cy - 1} Q {cx} {cy - 3} {cx + w} {cy - 1} '
            f'Q {cx + w - 1} {cy + h} {cx} {cy + h} Q {cx - w + 1} {cy + h} {cx - w} {cy - 1} Z" '
            f'fill="#8E3346" stroke="#6E2234" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<path d="M {cx - w * 0.6} {cy + h - 3} Q {cx} {cy + h - 8} {cx + w * 0.6} {cy + h - 3} '
            f'Q {cx} {cy + h + 1} {cx - w * 0.6} {cy + h - 3} Z" fill="#F08DA0"/>'
            f'<path d="M {cx - w + 2} {cy} L {cx + w - 2} {cy}" stroke="#FFFFFF" stroke-width="2" '
            f'opacity="0.9"/>')


def _shade(hex_, k):
    """k<0 — темнее, k>0 — светлее."""
    hex_ = hex_.lstrip("#")
    r, g, b = (int(hex_[i:i + 2], 16) for i in (0, 2, 4))
    if k < 0:
        r, g, b = (int(c * (1 + k)) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * k) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def face(eyes, mouth_state, iris, brow, blush=True):
    s = [
        # лицо
        f'<path d="M 128 150 C 128 98 164 76 200 76 C 236 76 272 98 272 150 C 272 196 256 232 '
        f'230 252 C 216 263 206 268 200 268 C 194 268 184 263 170 252 C 144 232 128 196 128 150 Z" '
        f'fill="{SKIN}" stroke="{LINE}" stroke-width="2.4"/>',
        # тень от чёлки
        f'<path d="M 134 140 C 160 160 240 160 266 140 L 266 172 C 240 182 160 182 134 172 Z" '
        f'fill="{SKIN_SH}" opacity="0.55"/>',
        eye(166, 182, iris, eyes), eye(234, 182, iris, eyes, mirror=True),
        f'<path d="M 146 146 Q 164 138 182 146" fill="none" stroke="{brow}" stroke-width="3" '
        f'stroke-linecap="round" opacity="0.85"/>',
        f'<path d="M 218 146 Q 236 138 254 146" fill="none" stroke="{brow}" stroke-width="3" '
        f'stroke-linecap="round" opacity="0.85"/>',
        f'<path d="M 201 206 l -3 6" stroke="{SKIN_SH}" stroke-width="2.4" stroke-linecap="round"/>',
        mouth(200, 232, mouth_state),
    ]
    if blush:
        s.insert(3, '<ellipse cx="150" cy="214" rx="15" ry="7" fill="#FF8FA8" opacity="0.38"/>'
                    '<ellipse cx="250" cy="214" rx="15" ry="7" fill="#FF8FA8" opacity="0.38"/>'
                    '<path d="M 142 212 l 4 -5 M 150 212 l 4 -5 M 246 212 l 4 -5 M 254 212 l 4 -5" '
                    'stroke="#F06C8A" stroke-width="1.4" opacity="0.6"/>')
    return "".join(s)


def _svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="820" '
            f'viewBox="0 0 400 820">{body}</svg>')


def _shadow():
    return ('<defs><radialGradient id="gsh"><stop offset="0" stop-color="#000" stop-opacity="0.35"/>'
            '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>'
            '<ellipse cx="200" cy="812" rx="110" ry="9" fill="url(#gsh)"/>')


def _neck(shadow=True):
    return (f'<path d="M 186 246 L 186 298 L 214 298 L 214 246 Z" fill="{SKIN}" stroke="{LINE}" '
            f'stroke-width="2"/>'
            + (f'<path d="M 186 252 Q 200 270 214 252 L 214 268 Q 200 282 186 268 Z" fill="{SKIN_SH}"/>'
               if shadow else ""))


def _legs(skin=SKIN, socks=None, sock_top=650):
    s = []
    for x0, x1, xb0, xb1 in ((158, 197, 166, 191), (203, 242, 209, 234)):
        s.append(f'<path d="M {x0} 556 L {x1} 556 L {xb1 + 1} 700 C {xb1} 740 {xb1} 770 {xb1} 792 '
                 f'L {xb0} 792 C {xb0} 770 {xb0 - 1} 740 {xb0 - 3} 700 Z" fill="{skin}" '
                 f'stroke="{LINE}" stroke-width="2"/>')
        if socks:
            s.append(f'<path d="M {xb0 - 4} {sock_top} L {xb1 + 3} {sock_top} L {xb1} 792 L {xb0} 792 Z" '
                     f'fill="{socks}" stroke="{LINE}" stroke-width="2"/>'
                     f'<path d="M {xb0 - 4} {sock_top + 9} L {xb1 + 3} {sock_top + 9}" '
                     f'stroke="{_shade(socks, 0.25)}" stroke-width="3"/>')
    return "".join(s)


def _sneakers(color="#FFFFFF", accent="#38BDF8", y=784):
    s = []
    for cx in (178, 222):
        s.append(f'<path d="M {cx - 16} {y} C {cx - 20} {y + 14} {cx - 18} {y + 26} {cx - 8} {y + 28} '
                 f'L {cx + 12} {y + 28} C {cx + 22} {y + 26} {cx + 20} {y + 12} {cx + 14} {y} Z" '
                 f'fill="{color}" stroke="{LINE}" stroke-width="2"/>'
                 f'<path d="M {cx - 18} {y + 21} L {cx + 20} {y + 21}" stroke="{accent}" stroke-width="3"/>'
                 f'<path d="M {cx - 9} {y + 6} L {cx + 7} {y + 6} M {cx - 10} {y + 12} L {cx + 9} {y + 12}" '
                 f'stroke="{_shade(color, -0.25)}" stroke-width="1.6"/>')
    return "".join(s)


def _boots(color="#6B4A3A", y=740):
    s = []
    for cx in (178, 222):
        s.append(f'<path d="M {cx - 15} {y} L {cx + 14} {y} L {cx + 14} {y + 44} C {cx + 22} {y + 50} '
                 f'{cx + 22} {y + 70} {cx + 12} {y + 72} L {cx - 10} {y + 72} C {cx - 20} {y + 70} '
                 f'{cx - 20} {y + 52} {cx - 15} {y + 44} Z" fill="{color}" stroke="{LINE}" stroke-width="2"/>'
                 f'<path d="M {cx - 15} {y + 8} L {cx + 14} {y + 8}" stroke="{_shade(color, 0.25)}" '
                 f'stroke-width="3"/>'
                 f'<path d="M {cx - 18} {y + 66} L {cx + 18} {y + 66}" stroke="{_shade(color, -0.4)}" '
                 f'stroke-width="4"/>')
    return "".join(s)


def _hand(cx, cy):
    return (f'<path d="M {cx - 11} {cy - 6} C {cx - 14} {cy + 8} {cx - 6} {cy + 18} {cx + 2} {cy + 16} '
            f'C {cx + 12} {cy + 14} {cx + 13} {cy + 2} {cx + 10} {cy - 6} Z" fill="{SKIN}" '
            f'stroke="{LINE}" stroke-width="2"/>')


def _sleeves(color, cuff, length=512, wide=False):
    """Рукава, руки опущены вдоль тела; кисти выглядывают из манжет."""
    w = 6 if wide else 0
    left = (f'<path d="M 134 300 C 112 318 102 378 98 430 C 96 462 98 490 {102 - w} {length} '
            f'L {140 + w} {length} C 140 482 140 444 144 404 C 147 370 150 338 152 316 Z" '
            f'fill="{color}" stroke="{LINE}" stroke-width="2.2"/>'
            f'<path d="M {102 - w} {length - 14} L {140 + w} {length - 14} L {140 + w} {length} '
            f'L {102 - w} {length} Z" fill="{cuff}" stroke="{LINE}" stroke-width="2"/>'
            f'<path d="M 120 340 C 114 380 112 420 112 470" fill="none" stroke="{_shade(color, -0.25)}" '
            f'stroke-width="2" opacity="0.7"/>')
    right = left.replace("M 134 300", "M 266 300")
    # зеркалим через transform
    return (_hand(121, length + 6) + _hand(279, length + 6) + left
            + f'<g transform="translate(400 0) scale(-1 1)">{left}</g>')


def bangs(tips, hair, shade, top=56, left=(124, 158), right=(276, 158), valley_y=104):
    """Чёлка из изогнутых прядей. tips — кончики слева направо: (x, y, наклон)."""
    d = (f"M {left[0]} {left[1]} C {left[0] - 8} {top + 36} {left[0] + 34} {top} 200 {top} "
         f"C {right[0] - 34} {top} {right[0] + 8} {top + 36} {right[0]} {right[1]} ")
    pts = list(reversed(tips))
    prev = right
    for i, (tx, ty, lean) in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        vx = (tx + (nxt[0] if nxt else left[0])) / 2
        # от предыдущей впадины к кончику
        px, py = prev[0], prev[1]
        d += (f"C {px - 2:.1f} {py + (ty - py) * 0.4:.1f} {tx + lean + 4:.1f} {ty - 22:.1f} "
              f"{tx:.1f} {ty:.1f} ")
        if nxt:
            vy = valley_y + abs(tx - 200) * 0.12
            d += f"C {tx - lean - 2:.1f} {ty - 26:.1f} {vx + 6:.1f} {vy + 18:.1f} {vx:.1f} {vy:.1f} "
            prev = (vx, vy)
        else:
            d += (f"C {tx - lean - 4:.1f} {ty - 20:.1f} {left[0] + 6} {left[1] - 16} "
                  f"{left[0]} {left[1]} ")
    d += "Z"
    inner = "".join(
        f'<path d="M {tx:.1f} {ty - 6:.1f} C {tx + lean * 0.4:.1f} {ty - 30:.1f} {tx + lean:.1f} '
        f'{ty - 50:.1f} {tx + lean * 1.4 + (200 - tx) * 0.1:.1f} {ty - 70:.1f}" fill="none" '
        f'stroke="{shade}" stroke-width="2" stroke-linecap="round" opacity="0.7"/>'
        for tx, ty, lean in tips)
    return (f'<path d="{d}" fill="{hair}" stroke="{LINE}" stroke-width="2.4" '
            f'stroke-linejoin="round"/>' + inner)


def torso(hem=470, fill="#FFF", width=0):
    """Приталенный силуэт верха: плечи, грудь, талия. width — свобода кроя."""
    w = width
    return (f'<path d="M 186 288 C 168 290 152 294 145 306 C {138 - w} 330 {137 - w} 362 {143 - w} 392 '
            f'C {150 - w} 420 {156 - w} 440 {156 - w} {hem} L {244 + w} {hem} C {244 + w} 440 {250 + w} 420 '
            f'{257 + w} 392 C {263 + w} 362 {262 + w} 330 255 306 C 248 294 232 290 214 288 Z" '
            f'fill="{fill}" stroke="{LINE}" stroke-width="2.4" stroke-linejoin="round"/>')


def chest_lines(col):
    return (f'<path d="M 160 382 Q 178 394 194 386 M 206 386 Q 222 394 240 382" fill="none" '
            f'stroke="{col}" stroke-width="2" stroke-linecap="round" opacity="0.8"/>')


def legs2(skin=SKIN, socks=None, sock_top=640):
    out = []
    left = ('M 142 516 C 138 576 150 636 160 668 C 157 704 160 744 167 790 L 190 790 '
            'C 190 752 192 714 192 678 C 194 640 198 600 199 552 Z')
    for t in ("", ' transform="translate(400 0) scale(-1 1)"'):
        g = f'<g{t}><path d="{left}" fill="{skin}" stroke="{LINE}" stroke-width="2"/>'
        g += (f'<path d="M 166 668 q 10 6 20 0" fill="none" stroke="{SKIN_SH}" stroke-width="2"/>'
              if skin == SKIN else "")
        if socks:
            g += (f'<path d="M 158 {sock_top} C 160 {sock_top + 40} 162 744 167 790 L 190 790 '
                  f'C 190 752 192 714 193 {sock_top} Z" fill="{socks}" stroke="{LINE}" stroke-width="2"/>'
                  f'<path d="M 158 {sock_top + 9} L 193 {sock_top + 9}" stroke="{_shade(socks, 0.25)}" '
                  f'stroke-width="3"/>')
        out.append(g + "</g>")
    return "".join(out)


def arms(color, cuff, wrist=500, puff=0):
    """Руки вдоль тела с лёгким изгибом в локте; кисти выглядывают из манжет."""
    p = puff
    left = (f'<path d="M 150 302 C {134 - p} 312 {126 - p} 340 {124 - p} 372 C {122 - p} 400 {120 - p} 424 '
            f'{118 - p} 448 C {116 - p} 470 {116 - p} 488 {117 - p} {wrist} L {143 + p} {wrist + 2} '
            f'C {143 + p} 486 {145 + p} 468 {147} 446 C 149 420 151 396 155 372 C 157 350 159 330 161 312 Z" '
            f'fill="{color}" stroke="{LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
            f'<path d="M {117 - p} {wrist - 14} L {143 + p} {wrist - 12} L {143 + p} {wrist + 2} '
            f'L {117 - p} {wrist} Z" fill="{cuff}" stroke="{LINE}" stroke-width="2"/>'
            f'<path d="M 128 410 q 8 4 16 0" fill="none" stroke="{_shade(color, -0.25)}" stroke-width="2"/>')
    hand = _hand(130, wrist + 8)
    return (f'{hand}{left}<g transform="translate(400 0) scale(-1 1)">{hand}{left}</g>')


# ------------------------------------------------------------------ Аки
def aki(eyes=0, mouth=0):
    hair, hair_sh, hair_hl, brow = "#E3EAF7", "#A9B6D3", "#FFFFFF", "#8E9BBC"
    hood, hood_sh, acc = "#20283A", "#151B29", "#38BDF8"
    iris = "#3A9BE6"
    back = (f'<path d="M 200 52 C 118 52 92 122 98 196 C 102 266 84 340 76 410 C 70 458 82 500 '
            f'96 522 {_zig(96, 304, 522, -16, 10)} C 318 500 330 458 324 410 C 316 340 298 266 302 196 '
            f'C 308 122 282 52 200 52 Z" fill="{hair_sh}" stroke="{LINE}" stroke-width="2.4"/>'
            f'<path d="M 112 220 C 104 300 96 380 100 470 M 288 220 C 296 300 304 380 300 470" '
            f'fill="none" stroke="{_shade(hair_sh, -0.2)}" stroke-width="2" opacity="0.6"/>')
    legs = legs2(socks="#1B1F2B", sock_top=632) + _sneakers("#F4F6FB", acc)
    skirt = (f'<path d="M 156 462 L 244 462 L 300 566 L 100 566 Z" fill="#2B3142" stroke="{LINE}" '
             f'stroke-width="2.2" stroke-linejoin="round"/>'
             + "".join(f'<path d="M {166 + i * 17} 468 L {112 + i * 35} 564" stroke="#3E4660" '
                       f'stroke-width="2"/>' for i in range(6)))
    body = (
        f'<path d="M 132 304 C 136 264 264 264 268 304 C 240 292 160 292 132 304 Z" fill="{hood_sh}" '
          f'stroke="{LINE}" stroke-width="2"/>'
        + _neck()
        + f'<defs><linearGradient id="hd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" '
          f'stroke="none" stop-color="{_shade(hood, 0.14)}"/><stop offset="1" stop-color="{hood}"/>'
          f'</linearGradient></defs>'
        + torso(476, "url(#hd)", 4)
        + chest_lines(_shade(hood, -0.5))
        + f'<path d="M 152 462 L 248 462 L 248 478 L 152 478 Z" fill="{hood_sh}" stroke="{LINE}" '
          f'stroke-width="2"/>'
          f'<path d="M 170 298 C 180 314 220 314 230 298" fill="none" stroke="{LINE}" stroke-width="2"/>'
          f'<path d="M 189 310 L 187 360 M 211 310 L 213 360" stroke="{acc}" stroke-width="3" '
          f'stroke-linecap="round"/>'
          f'<circle cx="187" cy="364" r="4" fill="{acc}"/><circle cx="213" cy="364" r="4" fill="{acc}"/>'
          f'<path d="M 172 420 l 56 0" stroke="{acc}" stroke-width="2.5" opacity="0.7"/>'
        + arms(hood, hood_sh, 500)
        + f'<path d="M 118 474 L 145 476 M 255 476 L 282 474" stroke="{acc}" stroke-width="4"/>'
    )
    head = face(eyes, mouth, iris, brow)
    bangs_ = bangs([(142, 160, -4), (168, 174, -6), (196, 168, -2), (224, 176, 5), (252, 166, 6)],
                   hair, hair_sh, valley_y=124)
    sides = ''.join(
        f'<g{t}><path d="M 130 132 C 116 196 112 262 120 340 C 126 306 134 268 140 226 '
        f'C 144 194 144 160 140 136 Z" fill="{hair}" stroke="{LINE}" stroke-width="2.2"/>'
        f'<path d="M 140 168 C 132 240 136 300 150 372 C 152 330 156 268 152 206 Z" '
        f'fill="{_shade(hair, -0.05)}" stroke="{LINE}" stroke-width="2"/></g>'
        for t in ("", ' transform="translate(400 0) scale(-1 1)"'))
    shine = (f'<path d="M 150 86 Q 200 66 250 86" fill="none" stroke="{hair_hl}" stroke-width="5" '
             f'stroke-linecap="round" opacity="0.9"/>'
             f'<path d="M 162 98 l 8 -4 M 230 94 l 8 4" stroke="{hair_hl}" stroke-width="3" '
             f'stroke-linecap="round"/>'
             f'<path d="M 200 56 C 206 26 230 22 226 38 C 218 32 208 40 205 56 Z" fill="{hair}" '
             f'stroke="{LINE}" stroke-width="2"/>'
             # заколка-звезда
             f'<path d="M 252 96 l 4 9 10 1 -8 6 3 10 -9 -6 -9 6 3 -10 -8 -6 10 -1 Z" fill="{acc}" '
             f'stroke="{LINE}" stroke-width="1.6"/>')
    return dict(back=back, legs=legs, skirt=skirt, upper=body, head=head + bangs_ + sides + shine,
                spec=dict(leg="#1B1F2B", knee=SKIN, shoe="#F4F6FB", shoe_acc=acc, skirt="#2B3142",
                          skirt_line="#3E4660", top=hood, sleeve=hood, cuff=hood_sh, hip=470))


# ------------------------------------------------------------------ Мия
def mia(eyes=0, mouth=0):
    hair, hair_sh, brow = "#F7A9C8", "#DE7FA8", "#C66A92"
    sweater, sweater_sh = "#F3ECE3", "#DCD1C3"
    acc = "#B57CF2"
    iris = "#A65BE0"
    back = (f'<path d="M 200 54 C 120 54 96 120 100 190 C 102 240 98 280 104 312 '
            f'{_zig(104, 296, 312, -12, 8)} C 302 280 298 240 300 190 C 304 120 280 54 200 54 Z" '
            f'fill="{hair_sh}" stroke="{LINE}" stroke-width="2.4"/>')
    legs = legs2(skin="#3A3346") + _boots("#7A5240", 730)
    body = (
        _neck()
        + f'<defs><linearGradient id="sw" x1="0" y1="0" x2="0" y2="1"><stop offset="0" '
          f'stop-color="#FFFFFF"/><stop offset="1" stop-color="{sweater}"/></linearGradient></defs>'
        + torso(450, "url(#sw)", 3)
        + chest_lines(sweater_sh)
        + "".join(f'<path d="M {164 + i * 18} 320 L {164 + i * 18} 436" stroke="{sweater_sh}" '
                  f'stroke-width="2"/>' for i in range(5))
        + f'<path d="M 176 284 C 180 268 220 268 224 284 L 228 304 C 210 314 190 314 172 304 Z" '
          f'fill="{sweater}" stroke="{LINE}" stroke-width="2"/>'
          f'<path d="M 154 438 L 246 438 L 246 452 L 154 452 Z" fill="{acc}" stroke="{LINE}" '
          f'stroke-width="1.8"/>'
          f'<path d="M 192 434 l 16 0 0 22 -16 0 Z" fill="#FFD166" stroke="{LINE}" stroke-width="1.6"/>'
        + arms("#FFFFFF", sweater_sh, 500, puff=5)
    )
    skirt = (f'<defs><linearGradient id="sw2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" '
             f'stop-color="#FFFFFF"/><stop offset="1" stop-color="{sweater}"/></linearGradient></defs>'
             f'<path d="M 158 440 L 242 440 C 262 480 290 540 304 590 L 96 590 C 110 540 138 480 158 440 Z" '
             f'fill="url(#sw2)" stroke="{LINE}" stroke-width="2.4" stroke-linejoin="round"/>'
             + "".join(f'<path d="M {170 + i * 15} 456 C {160 + i * 18} 500 {140 + i * 24} 550 '
                       f'{118 + i * 33} 584" fill="none" stroke="{sweater_sh}" stroke-width="2"/>'
                       for i in range(5))
             + f'<path d="M 96 576 L 304 576 L 306 592 L 94 592 Z" fill="{sweater_sh}" stroke="{LINE}" '
               f'stroke-width="2"/>')
    head = face(eyes, mouth, iris, brow)
    bangs_ = bangs([(140, 170, -4), (164, 178, -5), (190, 176, -2), (214, 180, 2), (238, 176, 5),
                    (260, 170, 4)], hair, hair_sh, left=(122, 168), right=(278, 168), valley_y=128)
    sides = ''.join(
        f'<g{t}><path d="M 128 140 C 114 200 112 250 118 300 C 126 278 136 250 140 214 '
        f'C 142 186 142 160 140 140 Z" fill="{hair}" stroke="{LINE}" stroke-width="2.2"/></g>'
        for t in ("", ' transform="translate(400 0) scale(-1 1)"'))
    phones = (
        f'<path d="M 116 170 C 98 18 302 18 284 170" fill="none" stroke="#2B2738" stroke-width="12" '
        f'stroke-linecap="round"/>'
        f'<path d="M 116 170 C 98 18 302 18 284 170" fill="none" stroke="{acc}" stroke-width="4" '
        f'stroke-linecap="round"/>'
        # кошачьи ушки на ободке
        + ''.join(f'<path d="M {x - 20} 74 L {x + (-6 if x < 200 else 6)} 34 L {x + 20} 68 Z" '
                  f'fill="#2B2738" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>'
                  f'<path d="M {x - 12} 68 L {x + (-5 if x < 200 else 5)} 46 L {x + 12} 65 Z" '
                  f'fill="{acc}"/>' for x in (150, 250))
        + ''.join(f'<ellipse cx="{x}" cy="182" rx="20" ry="28" fill="#2B2738" stroke="{LINE}" '
                  f'stroke-width="2"/><ellipse cx="{x}" cy="182" rx="11" ry="17" fill="{acc}"/>'
                  f'<ellipse cx="{x - 3}" cy="174" rx="4" ry="6" fill="#FFFFFF" opacity="0.6"/>'
                  for x in (118, 282)))
    shine = (f'<path d="M 152 90 Q 200 70 248 90" fill="none" stroke="#FFFFFF" stroke-width="5" '
             f'stroke-linecap="round" opacity="0.75"/>')
    return dict(back=back, legs=legs, skirt=skirt, upper=body,
                head=head + bangs_ + sides + shine + phones,
                spec=dict(leg="#3A3346", knee="#3A3346", shoe="#7A5240", shoe_acc="#5E3E30",
                          skirt=sweater, skirt_line=sweater_sh, top=sweater, sleeve="#FFFFFF",
                          cuff=sweater_sh, hip=446))


# ------------------------------------------------------------------ Рэй
def rei(eyes=0, mouth=0):
    hair, hair_sh, hair_hl, brow = "#2E3142", "#1C1E2A", "#6F7FA8", "#1C1E2A"
    jacket, jacket_sh, lining = "#1F3D47", "#142A31", "#F28C38"
    iris = "#E0962E"
    tail = (f'<path d="M 236 74 C 300 60 336 120 322 200 C 312 260 328 300 318 352 '
            f'C 306 320 296 300 300 268 C 304 220 296 160 262 112 Z" fill="{hair_sh}" '
            f'stroke="{LINE}" stroke-width="2.4"/>'
            f'<path d="M 300 120 C 320 170 306 230 314 300" fill="none" stroke="{hair_hl}" '
            f'stroke-width="2.4" opacity="0.6"/>')
    back = (f'<path d="M 200 56 C 128 56 104 118 108 184 C 110 220 112 248 120 268 '
            f'C 160 250 240 250 280 268 C 288 248 290 220 292 184 C 296 118 272 56 200 56 Z" '
            f'fill="{hair_sh}" stroke="{LINE}" stroke-width="2.4"/>')
    pants = (f'<path d="M 156 462 L 244 462 C 256 490 262 510 264 530 L 272 786 L 214 786 '
             f'L 204 590 L 196 590 L 186 786 L 128 786 L 136 530 C 138 510 144 490 156 462 Z" '
             f'fill="#C9B994" stroke="{LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
             f'<path d="M 132 620 L 166 620 L 166 668 L 132 668 Z M 234 620 L 268 620 L 268 668 '
             f'L 234 668 Z" fill="#B5A57F" stroke="{LINE}" stroke-width="1.8"/>'
             f'<path d="M 200 476 L 200 588" stroke="#9E8F6C" stroke-width="2"/>')
    legs = _sneakers("#F4F6FB", lining, 780) + pants
    body = (
        _neck()
        + torso(470, "#14161E", 0)
        + chest_lines("#3A3F52")
        + f'<path d="M 172 298 C 182 314 218 314 228 298" fill="none" stroke="#3A3F52" stroke-width="2"/>'
          f'<path d="M 184 404 L 216 404 L 208 424 L 192 424 Z" fill="{lining}" opacity="0.9"/>'
          f'<path d="M 154 458 L 246 458 L 246 474 L 154 474 Z" fill="#3A3226" stroke="{LINE}" '
          f'stroke-width="2"/><rect x="191" y="457" width="18" height="18" rx="3" fill="#C9C9C9" '
          f'stroke="{LINE}" stroke-width="1.6"/>'
        # куртка-бомбер нараспашку
        + f'<path d="M 145 306 C 154 296 166 292 176 298 L 172 482 L 140 482 C 140 440 132 400 136 360 '
          f'C 137 336 140 318 145 306 Z" fill="{jacket}" stroke="{LINE}" stroke-width="2.4"/>'
          f'<path d="M 255 306 C 246 296 234 292 224 298 L 228 482 L 260 482 C 260 440 268 400 264 360 '
          f'C 263 336 260 318 255 306 Z" fill="{jacket}" stroke="{LINE}" stroke-width="2.4"/>'
          f'<path d="M 176 298 L 172 482 L 166 482 L 168 300 Z M 224 298 L 228 482 L 234 482 L 232 300 Z" '
          f'fill="{lining}"/>'
          f'<path d="M 140 470 L 172 470 L 172 488 L 140 488 Z M 228 470 L 260 470 L 260 488 L 228 488 Z" '
          f'fill="{jacket_sh}" stroke="{LINE}" stroke-width="2"/>'
          f'<path d="M 238 340 l 18 0 0 6 -18 0 Z" fill="{lining}"/>'
        + arms(jacket, jacket_sh, 498, puff=2)
    )
    head = face(eyes, mouth, iris, brow, blush=True)
    bangs_ = bangs([(144, 158, -4), (172, 166, -9), (204, 164, -12), (236, 160, 4), (260, 152, 5)],
                   hair, hair_hl, left=(126, 160), right=(274, 160), valley_y=120)
    sides = ''.join(
        f'<g{t}><path d="M 130 136 C 120 190 118 236 124 278 C 130 256 136 230 140 200 '
        f'C 142 176 142 154 140 138 Z" fill="{hair}" stroke="{LINE}" stroke-width="2.2"/></g>'
        for t in ("", ' transform="translate(400 0) scale(-1 1)"'))
    extras = (f'<path d="M 156 84 Q 200 68 244 84" fill="none" stroke="{hair_hl}" stroke-width="4" '
              f'stroke-linecap="round" opacity="0.8"/>'
              f'<path d="M 232 74 C 244 64 256 66 262 76 C 254 74 244 76 236 84 Z" fill="{lining}" '
              f'stroke="{LINE}" stroke-width="1.6"/>'
              # очки
              f'<g fill="none" stroke="#3A3F52" stroke-width="2.6">'
              f'<rect x="138" y="160" width="56" height="42" rx="16"/>'
              f'<rect x="206" y="160" width="56" height="42" rx="16"/>'
              f'<path d="M 194 176 Q 200 170 206 176"/></g>'
              f'<path d="M 146 166 l 14 0" stroke="#FFFFFF" stroke-width="2.5" opacity="0.6"/>'
              f'<path d="M 214 166 l 14 0" stroke="#FFFFFF" stroke-width="2.5" opacity="0.6"/>')
    return dict(back=tail + back, legs=legs, skirt="", upper=body,
                head=head + bangs_ + sides + extras,
                spec=dict(leg="#C9B994", knee="#C9B994", shoe="#F4F6FB", shoe_acc=lining,
                          skirt=None, skirt_line="#9E8F6C", top=jacket, sleeve=jacket,
                          cuff=jacket_sh, hip=476))


def stand_svg(parts):
    return _svg(_shadow() + parts["back"] + parts["legs"] + parts["skirt"] + parts["upper"]
                + parts["head"])


CHARACTERS = {"aki": aki, "mia": mia, "rei": rei}
