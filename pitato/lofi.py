"""Lofi art for Now playing: a quiet pixel-art scene on the whole screen while music or radio plays (SELECT there).
Three of them, drawn here: a rainy window at night, a rooftop at dusk, a night train. Each song (or station) has one."""
import math
import random

LOFI_SCENES = ("window", "rooftop", "train")
LOFI_LINES = 120                      # the scene's pixels up the screen's shorter side: each of them 4 of the
                                      # GPi Case's pixels square (a 160 x 120 picture), more on a bigger screen
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))   # (an even scatter, for smooth shading)


def lofi_pixel(W, H):
    """How many of the screen's pixels square each of the scene's is: 4 on the GPi Case."""
    return max(1, min(W, H) // LOFI_LINES)


def lofi_scene(key):
    """A song's (or a station's) scene: the same one each time it plays."""
    h = 0
    for ch in str(key or ""):
        h = (h * 31 + ord(ch)) & 0xFFFFFF
    return LOFI_SCENES[h % len(LOFI_SCENES)]


def mix(a, b, f):
    return tuple(int(round(x + (y - x) * f)) for x, y in zip(a, b))


class Canvas:
    """A small picture to draw a scene on, pixel by pixel (numpy), shaded in steps scattered at their edges. A
    layer (empty=True) starts with nothing in it: what's drawn on it goes over what's behind."""

    def __init__(self, w, h, fill=(0, 0, 0), empty=False):
        import numpy as np
        self.np = np
        self.w, self.h = w, h
        self.a = np.zeros((h, w, 3), np.float32)
        self.a[:] = fill
        self.on = np.zeros((h, w), bool) if empty else None
        ys, xs = np.mgrid[0:h, 0:w]
        self.dither = (np.array(BAYER, np.float32)[ys % 4, xs % 4] + 0.5) / 16.0

    def box(self, x0, y0, x1, y1):
        x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
        return max(0, x0), max(0, y0), min(self.w, x1), min(self.h, y1)

    def rect(self, x0, y0, x1, y1, colour):
        x0, y0, x1, y1 = self.box(x0, y0, x1, y1)
        if x1 > x0 and y1 > y0:
            self.a[y0:y1, x0:x1] = colour
            if self.on is not None:
                self.on[y0:y1, x0:x1] = True

    def dots(self, xs, ys, colour, alpha):
        """Many points at once (what moves, each frame): xs, ys and alpha are arrays, each point alpha of colour."""
        np = self.np
        xs, ys = np.rint(xs).astype(int), np.rint(ys).astype(int)
        m = (xs >= 0) & (xs < self.w) & (ys >= 0) & (ys < self.h)
        xs, ys, alpha = xs[m], ys[m], np.broadcast_to(alpha, m.shape)[m]
        px = self.a[ys, xs]
        self.a[ys, xs] = px + (np.asarray(colour, np.float32) - px) * alpha[:, None]

    def columns(self, x0, tops, bottom, colour):
        """Columns from x0 on, each from its top (fractions count) down to bottom: hills, a cloud's edge."""
        np = self.np
        x1 = min(self.w, x0 + len(tops))
        if x1 <= max(0, x0):
            return
        tops = np.asarray(tops, np.float32)[max(0, -x0):x1 - x0]
        y0 = max(0, int(np.floor(tops.min())))
        if y0 >= bottom:
            return
        ys = np.arange(y0, bottom, dtype=np.float32)[:, None]
        m = ys >= np.round(tops)[None, :]
        self.a[y0:bottom, max(0, x0):x1][m] = colour

    def dot(self, x, y, colour, alpha=1.0):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.a[y, x] += (self.np.asarray(colour, self.np.float32) - self.a[y, x]) * alpha
            if self.on is not None:
                self.on[y, x] = True

    def gradient(self, x0, y0, x1, y1, stops, steps=6):
        """Top to bottom through the colours in stops [(where 0-1, colour)...], in a few steps, scattered between."""
        np = self.np
        x0, y0, x1, y1 = self.box(x0, y0, x1, y1)
        if x1 <= x0 or y1 <= y0:
            return
        f = (np.arange(y0, y1, dtype=np.float32)[:, None] - y0 + 0.5) / max(1, y1 - y0)
        f = np.broadcast_to(f, (y1 - y0, x1 - x0))
        q = np.clip(np.floor(f * steps + self.dither[y0:y1, x0:x1]) / steps, 0.0, 1.0)
        out = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            m = (q >= p0) & (q <= p1)
            k = ((q - p0) / max(1e-6, p1 - p0))[..., None]
            c0, c1 = np.asarray(c0, np.float32), np.asarray(c1, np.float32)
            out[m] = (c0 + (c1 - c0) * k)[m]
        self.a[y0:y1, x0:x1] = out

    def glow(self, cx, cy, r, colour, steps=5, squash=1.0):
        """Light from a point, added, fading out to r away (in a few scattered steps)."""
        np = self.np
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        d = np.sqrt((xs - cx) ** 2 + ((ys - cy) / squash) ** 2) / r
        f = np.floor(np.clip(1.0 - d, 0.0, 1.0) ** 2 * steps + self.dither) / steps
        self.a += np.asarray(colour, np.float32)[None, None, :] * f[..., None]

    def ellipse(self, cx, cy, rx, ry, colour):
        np = self.np
        x0, y0, x1, y1 = self.box(cx - rx - 1, cy - ry - 1, cx + rx + 2, cy + ry + 2)
        if x1 <= x0 or y1 <= y0:
            return
        ys, xs = np.mgrid[y0:y1, x0:x1]
        m = ((xs + 0.5 - cx) / max(rx, 0.5)) ** 2 + ((ys + 0.5 - cy) / max(ry, 0.5)) ** 2 <= 1.0
        self.a[y0:y1, x0:x1][m] = colour
        if self.on is not None:
            self.on[y0:y1, x0:x1][m] = True

    def mask(self, draw):
        from .fine import ImageDraw
        from PIL import Image
        m = Image.new("L", (self.w, self.h), 0)
        draw(ImageDraw.Draw(m))
        return self.np.asarray(m) > 0

    def poly(self, pts, colour):
        """A filled shape (its corners, in order)."""
        m = self.mask(lambda d: d.polygon([(round(x), round(y)) for x, y in pts], fill=255))
        self.a[m] = colour
        if self.on is not None:
            self.on |= m

    def line(self, pts, colour, width=1):
        m = self.mask(lambda d: d.line([(round(x), round(y)) for x, y in pts], fill=255, width=width))
        self.a[m] = colour
        if self.on is not None:
            self.on |= m


def windows_lit(c, rnd, x0, y0, x1, y1, colours, share):
    """A building's windows: some lit (in one of the colours), the rest dark."""
    for y in range(int(y0) + 2, int(y1) - 1, 3):
        for x in range(int(x0) + 1 + (y // 3) % 2, int(x1) - 1, 2):
            if rnd.random() < share:
                c.rect(x, y, x + 1, y + 1, colours[rnd.randrange(len(colours))])


def skyline(c, rnd, x0, x1, base, lo, hi, colour, widths=(6, 14), lit=None, share=0.25, tank=False):
    """A row of buildings standing on base, from x0 to x1, each lo to hi tall, their windows lit now and then (and a
    water tank up on a roof, on legs)."""
    x, tops = x0, []
    while x < x1:
        w, h = rnd.randint(*widths), rnd.randint(lo, hi)
        c.rect(x, base - h, x + w, base, colour)
        if rnd.random() < 0.3:                         # (a step on its roof, or an aerial)
            c.rect(x + w // 3, base - h - 2, x + w // 3 + max(2, w // 3), base - h, colour)
        if rnd.random() < 0.2:
            c.rect(x + w - 3, base - h - 5, x + w - 2, base - h, colour)
        if lit:
            windows_lit(c, rnd, x, base - h, x + w, base, lit, share)
        tops.append((x, w, base - h))
        x += w + rnd.choice((0, 0, 1))
    if tank and tops:
        x, w, top = max(tops[len(tops) // 3:], key=lambda t: t[1])
        tx = x + w // 2
        c.rect(tx - 4, top - 9, tx + 4, top - 4, colour)
        c.poly([(tx - 5, top - 9), (tx, top - 13), (tx + 5, top - 9)], colour)
        for lx in (tx - 3, tx + 2):
            c.rect(lx, top - 4, lx + 1, top, colour)


# ---- the scenes: what's behind (drawn once), what moves (each frame), what's in front of it (once) ------------------
class Window:
    """A desk by a window on a rainy night: the city's lights through the rain, the moon, a lamp, tea steaming, a cat
    asleep on the sill."""
    sky = ((0.0, (14, 16, 40)), (0.6, (38, 34, 82)), (1.0, (70, 54, 112)))
    wall = ((0.0, (46, 34, 68)), (1.0, (28, 22, 44)))
    frame_col = (22, 17, 32)

    def __init__(self, w, h):
        self.w, self.h = w, h
        mid = w // 2
        self.win = (mid - 16, 12, mid + 60, 72)        # the window: outside's left, top, right, bottom
        self.desk = h - 36
        self.mug = (mid - 2, self.desk)                # the mug's left, its foot

    def back(self):
        w, h = self.w, self.h
        c = Canvas(w, h)
        c.gradient(0, 0, w, h, self.wall, steps=5)
        x0, y0, x1, y1 = self.win
        out = Canvas(w, h)                             # outside: the sky, the moon, the city (kept inside the window)
        out.gradient(x0, y0, x1, y1, self.sky, steps=7)
        rnd = random.Random(7)
        for _ in range(14):
            out.dot(rnd.randrange(x0, x1), rnd.randrange(y0, y0 + 26), (200, 200, 240), 0.7)
        mx, my = x1 - 14, y0 + 11
        out.glow(mx, my, 16, (60, 56, 90), steps=4)
        out.ellipse(mx, my, 5, 5, (238, 232, 212))
        out.dot(mx - 2, my - 1, (214, 206, 190))
        out.dot(mx + 2, my + 2, (220, 212, 196))
        skyline(out, rnd, x0 - 4, x1, y1, 10, 24, (40, 36, 78), widths=(5, 10), lit=((250, 220, 150), (150, 210, 230)),
                share=0.12)
        skyline(out, rnd, x0 - 6, x1, y1, 4, 15, (27, 24, 54), widths=(6, 12),
                lit=((255, 214, 150), (240, 150, 190), (250, 230, 170)), share=0.22)
        c.rect(x0 - 3, y0 - 3, x1 + 3, y1 + 3, self.frame_col)
        c.a[y0:y1, x0:x1] = out.a[y0:y1, x0:x1]
        c.rect(x0 - 5, y1 + 1, x1 + 5, y1 + 4, (78, 56, 88))                       # the sill
        c.rect(x0 - 5, y1 + 1, x1 + 5, y1 + 2, (104, 78, 112))
        for i, (cw, col) in enumerate(((7, (104, 64, 108)), (5, (88, 54, 94)))):   # a curtain, gathered
            c.rect(x0 - 9 + i * 3, y0 - 5, x0 - 9 + i * 3 + cw, y1 + 1, col)
        c.rect(x0 - 10, y0 - 7, x1 + 6, y0 - 5, (60, 44, 70))                       # its rail
        self.picture(c, x0 - 34, 20)
        self.cat(c, x0 + 4, y1 + 1)
        self.plant(c, x1 - 4, y1 + 1)
        dy = self.desk                                                            # the desk
        c.rect(0, dy, w, dy + 3, (126, 82, 96))
        c.rect(0, dy + 3, w, h, (78, 50, 70))
        c.rect(0, dy + 3, w, dy + 4, (60, 38, 56))
        for x in range(8, w - 30, 52):                                            # its drawers
            c.rect(x, dy + 12, x + 34, dy + 13, (62, 40, 58))
            c.rect(x + 15, dy + 16, x + 19, dy + 17, (110, 76, 92))
        c.glow(31, dy - 18, 70, (96, 66, 30), steps=6, squash=0.7)                  # the lamp's light
        self.lamp(c, 18, dy)
        self.notebook(c, 30, dy)
        self.books(c, x1 - 6, dy)
        self.mug_at(c, *self.mug)
        return c

    def front(self):
        """The window's bars, over the rain."""
        x0, y0, x1, y1 = self.win
        c = Canvas(self.w, self.h, empty=True)
        c.rect((x0 + x1) // 2 - 1, y0, (x0 + x1) // 2 + 1, y1, self.frame_col)
        c.rect(x0, (y0 + y1) // 2 - 1, x1, (y0 + y1) // 2, self.frame_col)
        return c

    def picture(self, c, x, y):
        """A little framed picture on the wall: hills under a big moon."""
        c.rect(x, y, x + 18, y + 14, (64, 46, 80))
        c.gradient(x + 2, y + 2, x + 16, y + 12, ((0.0, (90, 120, 170)), (1.0, (180, 150, 190))), steps=3)
        c.ellipse(x + 11, y + 6, 2, 2, (240, 230, 210))
        c.poly([(x + 2, y + 12), (x + 7, y + 7), (x + 11, y + 10), (x + 14, y + 8), (x + 16, y + 12)], (70, 90, 120))

    def cat(self, c, x, y):
        """A grey cat curled up asleep: a loaf, its ears, its tail round it, the window's light along its back."""
        col, dark, rim = (112, 104, 136), (84, 78, 108), (168, 160, 196)
        c.ellipse(x + 8, y - 4, 8, 4, col)
        c.ellipse(x + 3, y - 6, 4, 3, col)
        c.poly([(x, y - 8), (x + 1, y - 12), (x + 3, y - 8)], col)
        c.poly([(x + 4, y - 8), (x + 6, y - 12), (x + 7, y - 8)], col)
        c.dot(x + 1, y - 10, (196, 150, 170))
        c.dot(x + 5, y - 10, (196, 150, 170))
        c.rect(x + 4, y - 1, x + 16, y, dark)                                      # its tail
        for px in (x + 9, x + 12):                                                 # its stripes
            c.rect(px, y - 7, px + 1, y - 4, dark)
        for px in range(x + 3, x + 14):
            c.dot(px, y - 8 + (0 if px < x + 6 else 1 if px < x + 12 else 2), rim, 0.8)
        c.rect(x + 1, y - 6, x + 3, y - 5, (70, 64, 92))                            # its eyes, shut
        c.rect(x + 4, y - 6, x + 6, y - 5, (70, 64, 92))

    def plant(self, c, x, y):
        c.rect(x - 3, y - 6, x + 3, y, (176, 110, 98))
        c.rect(x - 4, y - 7, x + 4, y - 5, (196, 128, 112))
        for dx, l in ((-1, 6), (1, 7), (0, 9), (-2, 5), (2, 5)):
            for k in range(l):
                c.dot(x + dx + (k // 3) * (1 if dx > 0 else -1 if dx < 0 else 0), y - 7 - k, (82, 148, 108))
        c.dot(x - 3, y - 12, (110, 178, 130))
        c.dot(x + 3, y - 13, (110, 178, 130))

    def lamp(self, c, x, y):
        col, lit = (88, 66, 100), (128, 100, 128)
        c.rect(x - 6, y - 3, x + 6, y, col)
        c.rect(x - 6, y - 3, x + 6, y - 2, lit)
        c.line([(x, y - 3), (x + 3, y - 18)], col, 2)
        c.line([(x + 3, y - 18), (x + 11, y - 25)], col, 2)
        c.dot(x + 3, y - 18, lit)
        c.poly([(x + 7, y - 31), (x + 17, y - 25), (x + 14, y - 21), (x + 4, y - 27)], (232, 196, 136))
        c.line([(x + 7, y - 31), (x + 4, y - 27)], (250, 222, 170))
        c.line([(x + 14, y - 21), (x + 11, y - 22)], (255, 244, 210), 2)

    def notebook(self, c, x, y):
        """An open notebook in the lamp's light, a pencil across it."""
        c.poly([(x, y), (x + 4, y - 3), (x + 24, y - 3), (x + 22, y)], (236, 228, 214))
        c.line([(x + 12, y - 3), (x + 11, y)], (200, 188, 180))
        for k in (1, 2):
            c.line([(x + 3 + k, y - k), (x + 10, y - k)], (176, 170, 190))
            c.line([(x + 14, y - k), (x + 21 - k, y - k)], (176, 170, 190))
        c.line([(x + 15, y - 5), (x + 23, y - 1)], (232, 180, 90))
        c.dot(x + 23, y - 1, (60, 50, 60))

    def books(self, c, x, y):
        for i, (bw, col) in enumerate(((22, (92, 112, 160)), (19, (150, 96, 132)), (20, (196, 160, 112)))):
            c.rect(x - bw, y - 3 * (i + 1), x, y - 3 * i, col)
            c.rect(x - bw, y - 3 * (i + 1), x, y - 3 * (i + 1) + 1, mix(col, (255, 255, 255), 0.2))
        c.rect(x - 4, y - 17, x - 1, y - 9, (232, 220, 200))                      # a candle on top
        c.dot(x - 3, y - 18, (255, 220, 150))

    def mug_at(self, c, mx, my):
        cream = (222, 210, 226)
        c.rect(mx, my - 9, mx + 8, my, cream)
        c.rect(mx + 1, my - 9, mx + 7, my - 8, (92, 56, 54))
        c.rect(mx + 8, my - 7, mx + 10, my - 6, cream)
        c.rect(mx + 9, my - 6, mx + 10, my - 3, cream)
        c.rect(mx + 8, my - 3, mx + 10, my - 2, cream)

    fps = 6                                            # (the rain and the steam: the same again every 6 seconds)

    def moves(self, c, t):
        """Rain down the window, and steam off the tea."""
        np = c.np
        x0, y0, x1, y1 = self.win
        if getattr(self, "drops", None) is None:
            rnd = np.random.default_rng(11)
            n, fall = int((x1 - x0) * 0.45), y1 - y0 + 6
            self.drops = (rnd.uniform(x0, x1 + 20, n), rnd.uniform(0, fall, n),
                          rnd.choice((2.0, 3.0), n) * fall / 6.0, fall)          # (whole falls in 6 s: it repeats)
        sx, sy, v, fall = self.drops
        y = y0 + (sy + v * t) % fall - 3
        x = sx - (y - y0) * 0.35
        for k, alpha in ((0, 0.45), (1, 0.33), (2, 0.21)):
            px, py = x - k * 0.35, y - k
            m = (px >= x0) & (px < x1) & (py >= y0) & (py < y1)
            c.dots(px[m], py[m], (150, 170, 220), np.float32(alpha))
        mx, my = self.mug
        f = ((t * 0.5 + np.arange(3)[:, None] / 3 + np.arange(6)[None, :] * 0.035) % 1.0).ravel()
        i = np.repeat(np.arange(3), 6)
        c.dots(mx + 3 + i + np.sin(f * 7 + i) * 1.4, my - 10 - f * 14, (210, 206, 230), (0.35 * (1 - f)).astype("f4"))


class Rooftop:
    """A rooftop at dusk: the sky going from pink to night, clouds drifting, the city's towers and their lit windows,
    a water tank, string lights over the parapet, plants in pots."""
    sky = ((0.0, (26, 24, 66)), (0.35, (70, 50, 116)), (0.62, (166, 98, 150)), (0.82, (236, 150, 150)),
           (1.0, (248, 190, 160)))

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.ground = h - 24                           # the parapet's top
        cr = random.Random(5)
        self.clouds = [(cr.uniform(0, w), cr.uniform(18, 50), cr.randint(18, 34), cr.uniform(0.5, 1.2))
                       for _ in range(5)]

    def back(self):
        w, h = self.w, self.h
        c = Canvas(w, h)
        c.gradient(0, 0, w, self.ground - 4, self.sky, steps=8)
        rnd = random.Random(3)
        for _ in range(26):
            c.dot(rnd.randrange(w), rnd.randrange(0, 30), (230, 220, 255), rnd.uniform(0.3, 0.8))
        sx, sy = int(w * 0.68), self.ground - 14       # the sun, going down
        c.glow(sx, sy, 34, (60, 30, 30), steps=5)
        c.ellipse(sx, sy, 12, 12, (255, 214, 176))
        mx = int(w * 0.18)                             # the moon, coming up
        c.ellipse(mx, 14, 3, 3, (240, 236, 220))
        c.ellipse(mx + 1, 13, 3, 3, (40, 32, 82))
        for x, y, col in self.bulbs():                 # the string lights' glow
            c.glow(x, y + 2, 6, tuple(v * 0.3 for v in col), steps=3)
        return c

    def bulbs(self):
        w = self.w
        pts = []
        for i in range(41):
            f = i / 40
            pts.append((9 + (w - 18) * f, self.ground - 36 - 4 * f + math.sin(f * math.pi) * 14))
        self.wire = pts
        return [(x, y, ((255, 220, 150), (250, 170, 200), (170, 220, 240))[i % 3])
                for i, (x, y) in enumerate(pts[2:-1:3])]

    def front(self):
        """The city, the parapet, the string of lights and the plants: in front of the clouds."""
        w, h, g = self.w, self.h, self.ground
        c = Canvas(w, h, empty=True)
        rnd = random.Random(9)
        skyline(c, rnd, -2, w, g - 4, 14, 34, (88, 58, 120), widths=(6, 12), lit=((255, 210, 170),), share=0.06)
        skyline(c, rnd, -4, w, g, 10, 46, (52, 36, 84), widths=(9, 18),
                lit=((255, 220, 150), (250, 160, 190), (160, 220, 230)), share=0.2, tank=True)
        c.rect(0, g, w, h, (44, 32, 62))
        c.rect(0, g, w, g + 3, (70, 52, 90))
        for y in range(g + 6, h, 5):                   # its bricks
            for x in range((y // 5) % 2 * 6, w, 12):
                c.rect(x, y, x + 1, y + 4, (38, 28, 54))
            c.rect(0, y + 4, w, y + 5, (38, 28, 54))
        c.rect(8, g - 36, 10, g + 1, (30, 22, 42))      # the lights' poles, the wire, the bulbs
        c.rect(w - 10, g - 40, w - 8, g + 1, (30, 22, 42))
        bulbs = self.bulbs()
        c.line(self.wire, (30, 22, 42))
        for x, y, col in bulbs:
            c.rect(x, y + 1, x + 1, y + 3, col)
        for px, size in ((22, 1.0), (w - 30, 1.3), (w - 18, 0.8)):   # plants in pots
            c.rect(px - 4 * size, g - 6 * size, px + 4 * size, g, (150, 90, 90))
            for k in range(7):
                a = math.radians(-160 + k * 23)
                for r in range(int(4 * size), int(9 * size)):
                    c.dot(px + math.cos(a) * r * 0.8, g - 6 * size + math.sin(a) * r, (70, 120, 96))
        return c

    fps = 2                                            # (the clouds are slow: a pixel a second or so)

    def moves(self, c, t):
        """The clouds drift by, slowly."""
        np = c.np
        w = self.w
        for x, y, length, speed in self.clouds:
            cx = int((x + t * speed) % (w + 60) - 30)
            k = np.arange(length)
            thick = 1 + (2 * np.sin(k / length * np.pi)).astype(int)
            c.columns(cx, int(y) - thick, int(y), (214, 150, 180))
            c.rect(cx, int(y), cx + length, int(y) + 1, (160, 104, 150))


class Train:
    """A night train: through its window the moon, mountains far off, hills with a town's lights, and poles going by;
    inside, a warm light, a little table with a cup and a book, the seats."""
    sky = ((0.0, (12, 16, 42)), (0.7, (34, 40, 90)), (1.0, (60, 60, 116)))
    frame_col = (24, 26, 44)

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.win = (14, 14, w - 14, h - 42)
        rnd = random.Random(21)
        self.far = [rnd.uniform(14, 30) for _ in range(64)]          # mountain heights, a point every 8 px
        self.hills = [rnd.uniform(4, 12) for _ in range(64)]
        self.towns = [(rnd.uniform(0, 512), rnd.randint(3, 9)) for _ in range(9)]

    def back(self):
        w, h = self.w, self.h
        c = Canvas(w, h)
        c.gradient(0, 0, w, h, ((0.0, (52, 58, 92)), (1.0, (30, 34, 58))), steps=5)    # the carriage's wall
        c.glow(w / 2, -6, 70, (70, 54, 30), steps=5, squash=0.6)                     # its light, from above
        x0, y0, x1, y1 = self.win
        c.rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4, self.frame_col)
        c.gradient(x0, y0, x1, y1, self.sky, steps=7)                                # outside: the sky, the moon
        rnd = random.Random(4)
        for _ in range(16):
            c.dot(rnd.randrange(x0, x1), rnd.randrange(y0, y0 + 30), (200, 205, 240), 0.6)
        c.glow(x1 - 26, y0 + 7, 14, (50, 50, 80), steps=4)
        c.ellipse(x1 - 26, y0 + 7, 4, 4, (236, 232, 214))
        return c

    def front(self):
        """The window's frame (round corners), the table under it with a cup and a book, the seats."""
        w, h = self.w, self.h
        x0, y0, x1, y1 = self.win
        c = Canvas(w, h, empty=True)
        for (cx, cy) in ((x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1)):
            for dx in range(3):
                for dy in range(3):
                    if dx + dy < 3:
                        c.dot(cx + (dx if cx == x0 else -dx), cy + (dy if cy == y0 else -dy), self.frame_col)
        c.rect(x0, y0 + 12, x1, y0 + 13, (20, 20, 36))                                # the wires outside
        c.rect(x0 - 6, y1 + 4, x1 + 6, y1 + 8, (96, 70, 74))                          # the table
        c.rect(x0 - 6, y1 + 4, x1 + 6, y1 + 5, (126, 96, 96))
        mx = w // 2 + 18
        c.rect(mx, y1 - 3, mx + 6, y1 + 4, (226, 216, 228))                          # a cup
        c.rect(mx + 6, y1 - 1, mx + 8, y1 + 2, (226, 216, 228))
        c.rect(w // 2 - 30, y1 + 1, w // 2 - 12, y1 + 4, (110, 140, 180))             # a book
        c.rect(w // 2 - 30, y1 + 1, w // 2 - 12, y1 + 2, (150, 176, 210))
        for sx in (-6, w - 40):                                                     # the seats' backs
            c.rect(sx, h - 28, sx + 46, h, (52, 78, 112))
            c.ellipse(sx + 23, h - 28, 23, 5, (52, 78, 112))
            c.rect(sx + 2, h - 31, sx + 44, h - 26, (64, 94, 132))
            c.rect(sx + 12, h - 33, sx + 34, h - 25, (214, 214, 224))                 # a cloth on its top
            c.rect(sx + 12, h - 26, sx + 34, h - 25, (176, 176, 196))
            for k in range(sx + 6, sx + 44, 9):
                c.rect(k, h - 22, k + 1, h, (44, 66, 96))
        return c

    fps = 6

    def moves(self, c, t):
        """Outside goes by: the far mountains slowly, the hills faster, the poles fastest."""
        np = c.np
        x0, y0, x1, y1 = self.win
        xs = np.arange(x0, x1, dtype=np.float32)
        for heights, speed, col in ((self.far, 2.0, (32, 36, 72)), (self.hills, 7.0, (22, 24, 48))):
            hs = np.asarray(heights, np.float32)
            f = ((xs + t * speed) % (len(hs) * 8)) / 8
            i = f.astype(int)
            hgt = hs[i % len(hs)] + (hs[(i + 1) % len(hs)] - hs[i % len(hs)]) * (f - i)
            c.columns(x0, y1 - hgt, y1, col)
        for tx, n in self.towns:
            x = x1 - ((tx + t * 7.0) % 512) + 40
            for k in range(n):
                px = x + k * 2
                if x0 <= px < x1:
                    c.dot(px, y1 - 3 - (k % 3), ((255, 214, 150), (250, 236, 190), (240, 160, 190))[k % 3])
        for k in range(4):                                                          # poles going by
            px = x1 - ((t * 24.0 + k * 61) % (x1 - x0 + 61)) + 30
            if x0 <= px < x1 - 1:
                c.rect(px, y0 + 8, px + 2, y1, (14, 14, 28))
                c.rect(px - 3, y0 + 10, px + 5, y0 + 11, (14, 14, 28))


SCENES = {"window": Window, "rooftop": Rooftop, "train": Train}


class LofiArt:
    """The scenes at the screen's size: what's behind and what's in front drawn once, then each frame is those with
    what moves between them, each of its pixels a few screen pixels square (lofi_pixel)."""

    def __init__(self):
        self.made = {}                    # (scene, w, h) -> (the scene, behind, in front, where in front is)

    def layers(self, scene, w, h):
        key = (scene, w, h)
        got = self.made.get(key)
        if got is None:
            if len(self.made) >= 3:
                self.made.clear()
            s = SCENES.get(scene, Window)(w, h)
            front = s.front()
            got = self.made[key] = (s, s.back(), front.a, front.on)
        return got

    def frame(self, scene, W, H, t):
        """The scene at time t (seconds), W x H: an RGB picture."""
        import numpy as np
        from PIL import Image
        px = lofi_pixel(W, H)
        w, h = -(-W // px), -(-H // px)
        s, back, front, on = self.layers(scene, w, h)
        c = Canvas.__new__(Canvas)
        c.np, c.w, c.h, c.on, c.dither = np, w, h, None, back.dither
        c.a = back.a.copy()
        s.moves(c, t)
        c.a[on] = front[on]
        img = Image.fromarray(np.clip(c.a + 0.5, 0, 255).astype(np.uint8), "RGB")
        img = img.resize((w * px, h * px), Image.NEAREST)
        return img if img.size == (W, H) else img.crop((0, 0, W, H))
