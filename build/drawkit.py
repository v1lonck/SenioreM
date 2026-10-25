"""Мини-набор для векторного рисования персонажей в Pillow (со сглаживанием через 4× масштаб)."""
import math

from PIL import Image, ImageDraw

S = 4  # суперсэмплинг


def hexc(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def catmull(pts, closed=True, n=10):
    """Гладкая кривая через точки."""
    out = []
    m = len(pts)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0 = pts[(i - 1) % m] if closed or i > 0 else pts[0]
        p1 = pts[i]
        p2 = pts[(i + 1) % m]
        p3 = pts[(i + 2) % m] if closed or i + 2 < m else pts[-1]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not closed:
        out.append(pts[-1])
    return out


def ellipse_pts(cx, cy, rx, ry, ang=0.0, n=72):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


def rot(pts, cx, cy, ang):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


class Canvas:
    def __init__(self, w, h, outline="#3B2A2A", ow=2.6):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.oc = hexc(outline)
        self.ow = ow

    def _p(self, pts):
        return [(x * S, y * S) for x, y in pts]

    def poly(self, pts, fill, outline=True, ow=None, alpha=255):
        f = hexc(fill, alpha) if isinstance(fill, str) else fill
        if alpha < 255:
            layer = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).polygon(self._p(pts), fill=f)
            self.im.alpha_composite(layer)
            return
        if outline:
            w = int((ow or self.ow) * S)
            oc = self.oc if outline is True else hexc(outline)
            self.d.polygon(self._p(pts), fill=f, outline=oc, width=w)
        else:
            self.d.polygon(self._p(pts), fill=f)

    def blob(self, pts, fill, outline=True, ow=None, alpha=255):
        self.poly(catmull(pts), fill, outline, ow, alpha)

    def ell(self, cx, cy, rx, ry, fill, outline=True, ang=0.0, ow=None, alpha=255):
        self.poly(ellipse_pts(cx, cy, rx, ry, ang), fill, outline, ow, alpha)

    def line(self, pts, color, width, smooth=False):
        c = hexc(color) if isinstance(color, str) else color
        if smooth:
            pts = catmull(pts, closed=False)
        pp = self._p(pts)
        w = max(1, int(width * S))
        self.d.line(pp, fill=c, width=w, joint="curve")
        r = w / 2
        for x, y in (pp[0], pp[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=c)

    def limb(self, pts, r0, r1, fill, outline=True, smooth=True, ow=None):
        """Толстая «колбаска» с плавной толщиной (лапа, хвост, рука)."""
        if smooth and len(pts) > 2:
            pts = catmull(pts, closed=False, n=8)
        n = len(pts)
        left, right = [], []
        for i, (x, y) in enumerate(pts):
            a = pts[max(0, i - 1)]
            b = pts[min(n - 1, i + 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L
            r = r0 + (r1 - r0) * i / max(1, n - 1)
            left.append((x + nx * r, y + ny * r))
            right.append((x - nx * r, y - ny * r))
        # закруглённые концы
        def cap(c, r, fwd, steps=10):
            ax, ay = fwd
            base = math.atan2(ay, ax)
            return [(c[0] + r * math.cos(base + math.pi / 2 - math.pi * k / steps),
                     c[1] + r * math.sin(base + math.pi / 2 - math.pi * k / steps)) for k in range(steps + 1)]
        e = pts[-1]
        fe = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        s = pts[0]
        fs = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
        poly = left + cap(e, r1, fe)[1:-1] + right[::-1] + cap(s, r0, fs)[1:-1]
        self.poly(poly, fill, outline, ow)

    def arc(self, cx, cy, rx, ry, a0, a1, color, width):
        pts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
               for a in [a0 + (a1 - a0) * k / 24 for k in range(25)]]
        self.line(pts, color, width)

    def result(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)
