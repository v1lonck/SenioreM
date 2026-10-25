"""Позы для SVG-персонажей (Аки, Мия, Рэй): стоит, сидит по-турецки, лежит на животе.
Все кадры рисуются на одном холсте 900×820, «пол» — y=806, центр фигуры — x=450."""
import characters as C

LINE = C.LINE
SKIN = C.SKIN
W, H = 1000, 820
FLOOR = 806
CX = 450


def _svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{body}</svg>')


def _shadow(cx, rx):
    return ('<defs><radialGradient id="gsh"><stop offset="0" stop-color="#000" stop-opacity="0.35"/>'
            '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>'
            f'<ellipse cx="{cx}" cy="{FLOOR + 6}" rx="{rx}" ry="9" fill="url(#gsh)"/>')


def stand(p):
    body = p["back"] + p["legs"] + p["skirt"] + p["upper"] + p["head"]
    return _svg(_shadow(CX, 110) + f'<g transform="translate({CX - 200} 0)">{body}</g>')


def _shoe(x, y, sp, flip=1):
    """Подошва/носок обуви, вид спереди (ступня под коленом)."""
    return (f'<path d="M {x - 17} {y - 10} C {x - 22} {y + 6} {x - 12} {y + 16} {x} {y + 16} '
            f'C {x + 12} {y + 16} {x + 22} {y + 6} {x + 17} {y - 10} Z" fill="{sp["shoe"]}" '
            f'stroke="{LINE}" stroke-width="2"/>'
            f'<path d="M {x - 18} {y + 4} Q {x} {y + 10} {x + 18} {y + 4}" fill="none" '
            f'stroke="{sp["shoe_acc"]}" stroke-width="3"/>')


def sit_legs(sp, hip):
    """Ноги по-турецки: колени в стороны, голени скрещены впереди."""
    y = hip
    leg, knee = sp["leg"], sp["knee"]
    s = [
        # бёдра — от таза к коленям
        f'<path d="M 150 {y - 6} C 112 {y + 4} 66 {y + 30} 62 {y + 62} C 60 {y + 84} 82 {y + 96} 110 {y + 92} '
        f'L 290 {y + 92} C 318 {y + 96} 340 {y + 84} 338 {y + 62} C 334 {y + 30} 288 {y + 4} 250 {y - 6} Z" '
        f'fill="{knee}" stroke="{LINE}" stroke-width="2.2" stroke-linejoin="round"/>',
        # голени: левая поверх правой
        f'<path d="M 318 {y + 58} C 300 {y + 82} 230 {y + 96} 168 {y + 98} L 164 {y + 120} '
        f'C 240 {y + 118} 316 {y + 104} 336 {y + 76} Z" fill="{leg}" stroke="{LINE}" stroke-width="2"/>',
        f'<path d="M 82 {y + 58} C 100 {y + 82} 170 {y + 98} 236 {y + 100} L 240 {y + 122} '
        f'C 160 {y + 120} 84 {y + 106} 64 {y + 78} Z" fill="{leg}" stroke="{LINE}" stroke-width="2"/>',
        f'<path d="M 92 {y + 66} q 18 16 46 22" fill="none" stroke="{C._shade(leg, 0.2)}" '
        f'stroke-width="2" opacity="0.7"/>',
        _shoe(150, y + 112, sp), _shoe(250, y + 112, sp),
    ]
    return "".join(s)


def sit_skirt(sp, hip):
    if not sp["skirt"]:
        return ""
    y = hip
    col, ln = sp["skirt"], sp["skirt_line"]
    return (f'<path d="M 156 {y - 12} L 244 {y - 12} C 290 {y + 10} 330 {y + 46} 344 {y + 74} '
            f'C 300 {y + 92} 100 {y + 92} 56 {y + 74} C 70 {y + 46} 110 {y + 10} 156 {y - 12} Z" '
            f'fill="{col}" stroke="{LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
            + "".join(f'<path d="M {170 + i * 15} {y - 6} Q {140 + i * 30} {y + 40} {78 + i * 61} {y + 80}" '
                      f'fill="none" stroke="{ln}" stroke-width="2"/>' for i in range(5)))


def sit(p):
    sp = p["spec"]
    hip = sp["hip"]
    dy = FLOOR - 4 - (hip + 128)
    body = p["back"] + sit_legs(sp, hip) + sit_skirt(sp, hip) + p["upper"] + p["head"]
    return _svg(_shadow(CX, 150) + f'<g transform="translate({CX - 200} {dy})">{body}</g>')


def lie(p, swing=0.0):
    """Лежит на животе, подбородок на ладонях, ноги подняты и болтаются (swing — фаза 0..2)."""
    import math
    sp = p["spec"]
    fy = FLOOR
    top, sleeve, cuff, leg = sp["top"], sp["sleeve"], sp["cuff"], sp["leg"]
    bottom_col = sp["skirt"] or leg
    chin = (330, fy - 118)                       # подбородок лежит на ладонях
    tx, ty = chin[0] - 200, chin[1] - 268
    clip = ('<defs><clipPath id="hc"><ellipse cx="200" cy="170" rx="152" ry="136"/>'
            '</clipPath></defs>')
    hair_back = f'<g transform="translate({tx} {ty})">{clip}<g clip-path="url(#hc)">{p["back"]}</g></g>'
    head = f'<g transform="translate({tx} {ty})">{p["head"]}</g>'
    # ноги: бёдра лежат, голени подняты и качаются
    knee_y = fy - 30
    legs = ""
    for k, ph in ((0, 0.0), (1, 1.0)):
        kx = 790 + 24 * k
        a = math.radians(72 + 24 * math.sin(swing * math.pi + ph * 2.4))
        fx = kx + math.cos(a) * 165
        fy2 = knee_y - math.sin(a) * 165
        nx, ny = -math.sin(a), -math.cos(a)          # нормаль к голени
        w = 15
        legs += (f'<path d="M {kx + nx * w:.1f} {knee_y + ny * w:.1f} L {fx + nx * w * 0.8:.1f} '
                 f'{fy2 + ny * w * 0.8:.1f} L {fx - nx * w * 0.8:.1f} {fy2 - ny * w * 0.8:.1f} '
                 f'L {kx - nx * w:.1f} {knee_y - ny * w:.1f} Z" fill="{leg}" stroke="{LINE}" '
                 f'stroke-width="2" stroke-linejoin="round"/>'
                 f'<ellipse cx="{fx:.1f}" cy="{fy2:.1f}" rx="24" ry="14" fill="{sp["shoe"]}" '
                 f'stroke="{LINE}" stroke-width="2" transform="rotate({-math.degrees(a) + 90 - 90:.1f} '
                 f'{fx:.1f} {fy2:.1f})"/>'
                 f'<circle cx="{kx}" cy="{knee_y}" r="{w + 1}" fill="{leg}" stroke="{LINE}" stroke-width="2"/>')
    thighs = (f'<path d="M 600 {fy - 64} C 680 {fy - 62} 760 {fy - 56} 806 {fy - 46} '
              f'C 830 {fy - 38} 830 {fy - 6} 806 {fy - 2} L 600 {fy - 2} Z" fill="{leg}" '
              f'stroke="{LINE}" stroke-width="2.2"/>')
    hips = (f'<path d="M 540 {fy - 86} C 600 {fy - 94} 650 {fy - 86} 676 {fy - 64} '
            f'C 690 {fy - 40} 684 {fy - 8} 664 {fy - 2} L 540 {fy - 2} Z" fill="{bottom_col}" '
            f'stroke="{LINE}" stroke-width="2.2"/>')
    if sp["skirt"]:
        hips += "".join(f'<path d="M {566 + i * 22} {fy - 84} L {572 + i * 26} {fy - 6}" '
                        f'stroke="{sp["skirt_line"]}" stroke-width="2"/>' for i in range(4))
    torso = (f'<path d="M 380 {fy - 112} C 440 {fy - 122} 520 {fy - 108} 566 {fy - 88} '
             f'C 584 {fy - 66} 580 {fy - 12} 560 {fy - 2} L 390 {fy - 2} C 368 {fy - 20} 362 {fy - 90} '
             f'380 {fy - 112} Z" fill="{top}" stroke="{LINE}" stroke-width="2.4"/>')
    # руки: плечо → локоть на полу → ладонь под подбородком
    arms = ""
    for sx, ex, ox in ((420, 286, -20), (450, 380, 20)):
        hx = chin[0] + ox
        arms += (f'<path d="M {sx} {fy - 96} C {sx - 40} {fy - 70} {ex + 30} {fy - 30} {ex + 18} {fy - 4} '
                 f'L {ex - 22} {fy - 4} C {ex - 20} {fy - 30} {sx - 70} {fy - 74} {sx - 20} {fy - 108} Z" '
                 f'fill="{sleeve}" stroke="{LINE}" stroke-width="2.2"/>'
                 f'<path d="M {ex - 22} {fy - 4} C {ex - 24} {fy - 40} {hx - 18} {chin[1] + 30} {hx - 14} '
                 f'{chin[1] + 14} L {hx + 14} {chin[1] + 16} C {hx + 16} {chin[1] + 34} {ex + 20} {fy - 40} '
                 f'{ex + 18} {fy - 4} Z" fill="{sleeve}" stroke="{LINE}" stroke-width="2.2"/>'
                 f'<path d="M {hx - 15} {chin[1] + 12} L {hx + 15} {chin[1] + 14} L {hx + 14} {chin[1] + 26} '
                 f'L {hx - 16} {chin[1] + 24} Z" fill="{cuff}" stroke="{LINE}" stroke-width="1.8"/>')
    hands = "".join(
        f'<path d="M {chin[0] + o * 1.6 - 16} {chin[1] + 14} C {chin[0] + o * 1.6 - 20} {chin[1] - 4} '
        f'{chin[0] + o * 1.6 - 4} {chin[1] - 16} {chin[0] + o * 1.6 + 6} {chin[1] - 12} '
        f'C {chin[0] + o * 1.6 + 18} {chin[1] - 6} {chin[0] + o * 1.6 + 18} {chin[1] + 6} '
        f'{chin[0] + o * 1.6 + 14} {chin[1] + 14} Z" fill="{SKIN}" stroke="{LINE}" stroke-width="2"/>'
        for o in (-20, 20))
    body = legs + thighs + hips + torso + hair_back + arms + head + hands
    return _svg(_shadow(560, 300) + body)
