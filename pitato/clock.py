"""The Simulator's Clock: the time and the date in the middle of the screen, on a dial (Analogue) or in big figures
(Digital)."""
import math
import time

from .sims import Sim
from .fine import detail
from .theme import BG, BODY, FONT_THIN, FONT_UI, FONT_UI_BOLD, MUTED, TEXT


# ---- the Clock --------------------------------------------------------------------------------------------
# Its picture changes once a second (once a minute with Seconds off), just as the second (or the minute) begins:
# media mode draws it then, and not in between (frame_in). The dial is drawn once for its size, four times bigger
# and then shrunk, for smooth edges; the date goes on it once a day. Each frame draws only the hands, each pixel by
# how far it is from a hand's middle line (numpy): quick enough for a Pi Zero. The figures and words are kept as
# pictures too, so a frame is mostly pasting.
CLOCK_LOOKS = ("Analogue", "Digital")
CLOCK_COLOURS = (("Blue", (96, 170, 228)), ("Teal", (64, 200, 184)), ("Green", (116, 204, 128)),
                 ("Purple", (166, 138, 236)), ("Pink", (236, 128, 176)), ("White", (236, 239, 243)))
CLOCK_MARGIN = 8                      # px between the clock and the edges of its room
SUPER = 4                             # the dial is drawn this many times bigger, then shrunk

# the dial, in parts of its radius
FACE = (23, 28, 35)                   # the dial itself, a shade lighter than the page
FACE_EDGE = (36, 42, 51)
MINUTE_DOT = (0.9, 0.0085, (92, 100, 113))      # each minute: a dot this far out, this big, this colour
HOUR_MARK = (0.79, 0.89, 0.024, (198, 205, 214))   # each hour: a line from, to, how wide (12, 3, 6, 9: their figures)
FIGURES = (0.8, 0.2, (226, 230, 236))           # 12, 3, 6 and 9: their middles this far out, their letters' size
HANDS = ((-0.07, 0.52, 0.023), (-0.07, 0.8, 0.0165))   # the hour and minute hands: from, to, half how thick
SECOND_HAND = (-0.2, 0.86, 0.0055)    # the second hand: from (its tail), to, half how thick
HUB = (0.042, 0.014)                  # the middle: the second hand's disc, and the pin in it
DATE = (0.4, 0.105)                   # the date: below the middle, its letters' size

# the digital look, in parts of the figures' letter size
SIDE = (0.06, 0.34, 0.14)             # beside the time: the gap, the seconds' letters, AM/PM's
UNDER = (0.22, 0.13)                  # under it: the gap, the date's letters
DIGITAL_ROOM = 0.8                    # how much of the room the widest time (23:59, its seconds) takes


def capsule(a, ax, ay, bx, by, r, colour):
    """A line with round ends from (ax, ay) to (bx, by), r each side of its middle, onto a (an H x W x 3 float32
    picture), its edge smooth."""
    import numpy as np
    H, W = a.shape[:2]
    m = r + 2
    x0, x1 = max(0, int(min(ax, bx) - m)), min(W, int(math.ceil(max(ax, bx) + m)))
    y0, y1 = max(0, int(min(ay, by) - m)), min(H, int(math.ceil(max(ay, by) + m)))
    if x1 <= x0 or y1 <= y0:
        return
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - ax
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - ay
    dx, dy = bx - ax, by - ay
    t = np.clip((xs * dx + ys * dy) / max(dx * dx + dy * dy, 1e-6), 0.0, 1.0)
    ex, ey = xs - t * dx, ys - t * dy
    cover = np.clip(r + 0.5 - np.sqrt(ex * ex + ey * ey), 0.0, 1.0)[..., None]
    part = a[y0:y1, x0:x1]
    part += (np.asarray(colour, np.float32) - part) * cover


class Clock(Sim):
    """The time and the date, in the middle of its room: a dial with three hands (Analogue) or big figures
    (Digital). A switches between them; START has the look, the seconds and the colour."""
    key = "clock"
    blurb = "The time and the date. A switches between the dial and the figures."
    poke_label = None
    options = (("look", "Look", CLOCK_LOOKS, "Analogue"),
               ("seconds", "Seconds", ("On", "Off"), "On"),
               ("colour", "Colour", tuple(n for n, _ in CLOCK_COLOURS), "Blue"))
    bare = True                         # on the page itself: no box, and nothing beside it
    paced = True                        # its picture changes as each second begins (frame_in), not frame by frame
    backdrop = BG                       # what's behind it (full screen too)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.hours24 = False            # Settings > Clock is 24-hour (media mode says: pitato/screens/sims.py)
        self.fine = 1                   # the picture's pixels to each of the menus' while it's drawn (fine.py)
        self.dials = {}                 # (radius, date, backdrop) -> the dial with its date (a float32 picture)
        self.masks = {}                 # fonts, and words and figures as pictures: (what, how big...) -> it

    def update(self, dt):
        return None                     # (A switches the look: it's never paused)

    def frame_in(self, wall):
        """Seconds until its picture changes (wall: the time now): as the next second begins (or the next minute,
        without its seconds)."""
        every = 60.0 if self.values.get("seconds") == "Off" else 1.0
        return every - wall % every + 0.004

    def hints(self):
        return [("A", "Analogue" if self.values.get("look") == "Digital" else "Digital"),
                ("SELECT", "Full screen"), ("START", "Options")]

    def colour(self):
        """The colour picked: the second hand and its disc, or the colon and the seconds."""
        pick = self.values.get("colour")
        return next((c for name, c in CLOCK_COLOURS if name == pick), CLOCK_COLOURS[0][1])

    def seconds(self):
        return self.values.get("seconds") != "Off"

    def draw(self, img, x0, y0, now=None):
        s = detail(img)
        if s > 1:                                      # (a screen drawn finely, a 4K TV's: the clock as finely, all of
            w, h = self.w, self.h                      # it s times the size on the picture's own pixels)
            self.w, self.h, self.fine = w * s, h * s, s
            try:
                return self.draw(img.pic, x0 * s, y0 * s, now)
            finally:
                self.w, self.h, self.fine = w, h, 1
        t = time.localtime(time.time() if now is None else now)
        if self.values.get("look") == "Digital":
            self.draw_digital(img, x0, y0, t)
        else:
            self.draw_analogue(img, x0, y0, t)

    # -- kept pictures --------------------------------------------------------------------------------------
    def keep(self, key, make):
        got = self.masks.get(key)
        if got is None:
            if len(self.masks) > 240:                  # (a new size or a new day: the old ones go)
                self.masks.clear()
            got = self.masks[key] = make()
        return got

    def font(self, path, size):
        def make():
            from PIL import ImageFont
            try:
                basic = ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else ImageFont.LAYOUT_BASIC
                return ImageFont.truetype(path, size, layout_engine=basic)    # (Inter: much quicker so)
            except OSError:
                return ImageFont.load_default()
        return self.keep(("font", path, size), make)

    def words(self, text, path, size):
        """Words, white on black: (an L picture just their size, how far down its baseline is) (kept)."""
        def make():
            from .fine import ImageDraw
            from PIL import Image
            f = self.font(path, size)
            x0, y0, x1, y1 = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f, anchor="ls")
            pic = Image.new("L", (max(1, x1 - x0 + 2), max(1, y1 - y0 + 2)), 0)
            ImageDraw.Draw(pic).text((1 - x0, 1 - y0), text, font=f, fill=255, anchor="ls")
            return pic, 1 - y0
        return self.keep(("words", text, path, size), make)

    # -- the dial -------------------------------------------------------------------------------------------
    def radius(self):
        return max(24.0 * self.fine, min(self.w, self.h) / 2 - CLOCK_MARGIN * self.fine)

    @staticmethod
    def date_short(t):
        """The date on the dial: Sat, Oct 31."""
        return f"{time.strftime('%a, %b', t)} {t.tm_mday}"

    def dial(self, R):
        """The dial, R its radius: its face, a dot each minute, a line each hour, 12 3 6 9 (an RGB picture, its middle in
        its middle)."""
        from .fine import ImageDraw
        from PIL import Image
        S = 2 * int(math.ceil(R)) + 4
        c, k = S / 2, SUPER
        big = Image.new("RGB", (S * k, S * k), self.backdrop)
        d = ImageDraw.Draw(big)
        d.ellipse(((c - R) * k, (c - R) * k, (c + R) * k, (c + R) * k), fill=FACE, outline=FACE_EDGE,
                  width=max(1, round(k * 0.8)))
        at, size, colour = MINUTE_DOT
        for m in range(60):
            if m % 5:
                a = math.radians(m * 6)
                x, y, r = c + math.sin(a) * at * R, c - math.cos(a) * at * R, max(0.7, size * R)
                d.ellipse(((x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k), fill=colour)
        r0, r1, w, colour = HOUR_MARK
        for hour in range(12):
            if hour % 3:
                a = math.radians(hour * 30)
                ux, uy = math.sin(a), -math.cos(a)
                d.line(((c + ux * r0 * R) * k, (c + uy * r0 * R) * k, (c + ux * r1 * R) * k, (c + uy * r1 * R) * k),
                       fill=colour, width=max(1, round(w * R * k)))
                for r in (r0, r1):                     # (round ends)
                    x, y, e = c + ux * r * R, c + uy * r * R, w * R / 2
                    d.ellipse(((x - e) * k, (y - e) * k, (x + e) * k, (y + e) * k), fill=colour)
        at, size, colour = FIGURES
        f = self.font(FONT_THIN, max(8, round(size * R * k)))
        for hour, text in ((0, "12"), (3, "3"), (6, "6"), (9, "9")):
            a = math.radians(hour * 30)
            d.text(((c + math.sin(a) * at * R) * k, (c - math.cos(a) * at * R) * k), text, font=f, fill=colour,
                   anchor="mm")
        return big.reduce(k)

    def dial_with_date(self, R, t):
        """The dial with the date on it: a float32 picture (kept: drawn again for a new day)."""
        import numpy as np
        from .fine import ImageDraw
        text = self.date_short(t)
        key = (R, text, self.backdrop)
        got = self.dials.get(key)
        if got is None:
            pic = self.keep(("dial", R, self.backdrop), lambda: self.dial(R)).copy()
            c = pic.width / 2
            ImageDraw.Draw(pic).text((c, c + DATE[0] * R), text, font=self.font(FONT_UI, max(9, round(DATE[1] * R))),
                                     fill=BODY, anchor="mm")
            if len(self.dials) >= 3:
                self.dials.clear()
            got = self.dials[key] = np.asarray(pic, np.float32)
        return got

    def draw_analogue(self, img, x0, y0, t):
        """The dial in the middle of the room, its hands where the time says."""
        import numpy as np
        from PIL import Image
        R = self.radius()
        a = self.dial_with_date(R, t).copy()
        c = a.shape[0] / 2
        mins = t.tm_min + (t.tm_sec / 60 if self.seconds() else 0)
        for turn, (r0, r1, half) in ((((t.tm_hour % 12) + mins / 60) * 30, HANDS[0]), (mins * 6, HANDS[1])):
            ux, uy = math.sin(math.radians(turn)), -math.cos(math.radians(turn))
            capsule(a, c + ux * r0 * R, c + uy * r0 * R, c + ux * r1 * R, c + uy * r1 * R, half * R, TEXT)
        colour = self.colour()
        if self.seconds():
            ux, uy = math.sin(math.radians(t.tm_sec * 6)), -math.cos(math.radians(t.tm_sec * 6))
            r0, r1, half = SECOND_HAND
            capsule(a, c + ux * r0 * R, c + uy * r0 * R, c + ux * r1 * R, c + uy * r1 * R, max(0.75, half * R), colour)
        hub, pin = HUB
        capsule(a, c, c, c, c, hub * R, colour if self.seconds() else TEXT)
        capsule(a, c, c, c, c, max(1.0, pin * R), self.backdrop)
        img.paste(Image.fromarray((a + 0.5).astype(np.uint8), "RGB"),
                  (int(round(x0 + self.w / 2 - c)), int(round(y0 + self.h / 2 - c))))

    # -- the figures ----------------------------------------------------------------------------------------
    def digital_size(self):
        """The figures' letter size: the widest time (23:59, its seconds beside it) and the date under it fill this much
        of the room."""
        f = self.font(FONT_THIN, 100)
        wide = f.getlength("23:59") + 100 * SIDE[0] + 2 * self.font(FONT_THIN, round(100 * SIDE[1])).getlength("0")
        tall = 100 * (0.73 + UNDER[0] + UNDER[1] * 1.2)
        fit = min((self.w - 2 * CLOCK_MARGIN * self.fine) / wide, (self.h - 2 * CLOCK_MARGIN * self.fine) / tall)
        return max(16, int(100 * fit * DIGITAL_ROOM))

    def paste_words(self, img, text, path, size, colour, x, base):
        """Words (kept), their left at x, their baseline at base: how wide they are."""
        pic, down = self.words(text, path, size)
        img.paste(colour, (int(round(x)) - 1, int(round(base)) - down), pic)
        return pic.width - 2

    def draw_digital(self, img, x0, y0, t):
        """The time in big thin figures in the middle of the room (the colon in the colour picked), AM or PM and the
        seconds beside it, the date under it."""
        size = self.digital_size()
        colour, secs = self.colour(), self.seconds()
        hours = f"{t.tm_hour:02d}" if self.hours24 else str(t.tm_hour % 12 or 12)
        parts = (hours, ":", f"{t.tm_min:02d}")
        pics = [self.words(p, FONT_THIN, size)[0] for p in parts]
        gap = size * 0.03                              # (each side of the colon)
        time_w = sum(p.width - 2 for p in pics) + 2 * gap
        small, label = round(size * SIDE[1]), round(size * SIDE[2])
        sec_w = 2 * self.font(FONT_THIN, small).getlength("0") if secs else 0   # (the room two figures can need)
        ampm = "" if self.hours24 else time.strftime("%p", t)
        side = max(sec_w, self.words(ampm, FONT_UI_BOLD, label)[0].width if ampm else 0)
        total = time_w + (size * SIDE[0] + side if side else 0)
        cap = size * 0.73                              # (how tall the figures stand, above their baseline)
        date = f"{time.strftime('%A, %B', t)} {t.tm_mday}"
        date_size = max(10, round(size * UNDER[1]))
        block = cap + size * UNDER[0] + date_size
        x = x0 + (self.w - total) / 2
        base = y0 + (self.h - block) / 2 + cap
        for i, (p, colour_of) in enumerate(zip(parts, (TEXT, colour, TEXT))):
            x += self.paste_words(img, p, FONT_THIN, size, colour_of, x, base) + (gap if i < 2 else 0)
        x += size * SIDE[0]
        if ampm:
            self.paste_words(img, ampm, FONT_UI_BOLD, label, MUTED, x, base - cap + label * 0.73)
        if secs:
            self.paste_words(img, f"{t.tm_sec:02d}", FONT_THIN, small, colour, x, base)
        pic, down = self.words(date, FONT_UI, date_size)
        img.paste(BODY, (int(round(x0 + (self.w - pic.width) / 2)), int(round(base + size * UNDER[0] + date_size * 0.73
                                                                               - down + 1))), pic)
