"""Notes, in Apps: what you type on a keyboard (USB or Bluetooth), kept as you type it, a file a note in your
Documents' Notes folder (so Files has them, and the web page, and another of your Pietatos can be sent one). The d-pad
picks its colours: up and down the words', left and right the background's. A changes the font (a dozen: handwriting,
a typewriter's, a pixel one...), Y puts an effect on them (a glow, a rainbow, a shadow), X reads the note out loud in
your Bot's voice, L and R go through your notes (R past the last one starts a new one). START has them all, and how
big the letters are; SELECT is the whole screen, B (or Esc on the keyboard) goes back. The keyboard: letters, Enter a
new line, Backspace the last one gone."""
import time

from .fine import detail
from .sims import Sim
from .theme import BG, co_mix, FONT_UI, typeface

NOTE_INKS = (("White", (236, 239, 244)), ("Amber", (255, 186, 73)), ("Green", (118, 232, 140)),
             ("Cyan", (96, 216, 242)), ("Pink", (255, 132, 192)), ("Lemon", (246, 232, 104)), ("Ink", (24, 26, 32)))
NOTE_PAPERS = (("Night", BG), ("Black", (0, 0, 0)), ("Navy", (18, 32, 70)), ("Forest", (16, 48, 34)),
               ("Plum", (54, 24, 62)), ("Brick", (96, 32, 26)), ("Paper", (246, 240, 226)))
NOTE_FONTS = ("Clean", "Handwriting", "Typewriter", "Pixel", "Terminal", "Comic", "Script", "Future", "Retro",
              "Poster", "Neon", "Bold")                # (theme.py's typefaces: A goes through them in this order)
NOTE_SIZES = {"Small": 0.8, "Normal": 1.0, "Big": 1.45}
NOTE_SIZE = 26                   # px: Clean's letters, Normal (the others as big to look at: theme.py)
NOTE_EFFECTS = ("None", "Glow", "Rainbow", "Shadow")
NOTE_BLINK = 0.5                 # seconds the cursor's on, then off
NOTE_MOST = 20000                # characters a note keeps, at most
NOTE_PAD = 26                    # px between the words and the page's edges
NOTE_TOP = 34                    # px for the line at the top (which note, how many words)


def wrap(text, font, width):
    """The note's lines as they fit across: its own lines, broken at spaces (a word too long for one line: where it
    must). [(the line, where it starts in the text)]."""
    out, start = [], 0
    for para in text.split("\n"):
        line, at, k = "", start, 0
        while k < len(para):
            j = k
            while j < len(para) and para[j] != " ":
                j += 1
            while j < len(para) and para[j] == " ":
                j += 1
            word = para[k:j]
            if not line or font.getlength(line + word.rstrip()) <= width:
                if line or font.getlength(word.rstrip()) <= width:
                    line += word
                    k = j
                    continue
                cut = 1                                # (a word wider than a line: as much as fits)
                while cut < len(word) and font.getlength(word[:cut + 1]) <= width:
                    cut += 1
                out.append((word[:cut], at))
                at += cut
                k += cut
                continue
            out.append((line, at))
            at, line = at + len(line), ""
        out.append((line, at))
        start += len(para) + 1
    return out


class Notes(Sim):
    """A note, on the page itself: its words wrapped across it, the last of them at the bottom (where you're
    typing), a cursor blinking after them. The line at the top says which note (of how many) and its words."""
    key = "notes"
    blurb = "What you type on a keyboard. The d-pad picks its colours, and every button does something."
    poke_label = None
    options = (("ink", "Colour", tuple(n for n, _ in NOTE_INKS), "White"),
               ("paper", "Background", tuple(n for n, _ in NOTE_PAPERS), "Night"),
               ("font", "Font", NOTE_FONTS, "Clean"),
               ("size", "Size", tuple(NOTE_SIZES), "Normal"),
               ("effect", "Effect", NOTE_EFFECTS, "None"))
    bare = True                         # on the page itself: no box, and nothing beside it
    paced = True                        # its picture changes as the cursor blinks (frame_in), not frame by frame

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.text = ""
        self.which = (1, 1)             # (this note, of how many)
        self.keyboard = False           # a keyboard's plugged in (media mode says)
        self.reading = False            # ...and its Bot's reading it out loud
        self.fonts = {}
        self.rainbows = {}              # (w, h) -> a rainbow, for its letters
        self.drawn = (None, None, None)  # (what for, the words' picture, where the cursor goes)

    def update(self, dt):
        return None                     # (it's never paused)

    def frame_in(self, wall):
        """Seconds until its picture changes (wall: the time now): as the cursor blinks."""
        return NOTE_BLINK - wall % NOTE_BLINK + 0.004

    def hints(self):
        """Its buttons, along the bottom (on a screen wider than the GPi Case's, L and R's, SELECT's and START's
        too)."""
        out = [("▲▼", "Colour"), ("◀▶", "Background"), ("A", "Font"), ("Y", "Effect"),
               ("X", "Stop" if self.reading else "Read it")]
        return out + [("L R", "Notes"), ("SELECT", "Full screen"), ("START", "More")] if self.w >= 800 else out

    @property
    def backdrop(self):
        return dict(NOTE_PAPERS).get(self.values.get("paper"), BG)

    def ink(self):
        return dict(NOTE_INKS).get(self.values.get("ink"), NOTE_INKS[0][1])

    def words(self):
        return len(self.text.split())

    def font_size(self):
        """(its font's file, how big its letters are set, px): Font and Size's (a pixel font in steps of 4, and no
        smaller than 12, so its pixels stay square)."""
        name = self.values.get("font")
        path, k = typeface(name if name in NOTE_FONTS else "Clean")
        size = NOTE_SIZE * k * NOTE_SIZES.get(self.values.get("size"), 1.0)
        if name == "Pixel":
            return path, max(12, int(round(size / 4)) * 4)
        return path, max(10, int(round(size)))

    def font(self, s=1):
        path, size = self.font_size()
        key = (path, size * s)
        if key not in self.fonts:
            from PIL import ImageFont
            try:
                basic = ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else ImageFont.LAYOUT_BASIC
                self.fonts[key] = ImageFont.truetype(path, size * s, layout_engine=basic)   # (quicker on a Pi)
            except OSError:
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]

    def small(self, s=1):
        key = ("small", s)
        if key not in self.fonts:
            from PIL import ImageFont
            try:
                self.fonts[key] = ImageFont.truetype(FONT_UI, 15 * s)
            except OSError:
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]

    def rainbow(self, w, h):
        """Rainbow colours across and down the page (its letters take theirs from where they are)."""
        if (w, h) not in self.rainbows:
            import colorsys
            from PIL import Image
            strip = Image.new("RGB", (256, 1))
            strip.putdata([tuple(int(c * 255) for c in colorsys.hsv_to_rgb(k / 256, 0.55, 1.0)) for k in range(256)])
            wide = strip.resize((w + h, 1)).resize((w + h, h))
            self.rainbows[(w, h)] = wide.transform((w, h), Image.AFFINE, (1, 1, 0, 0, 1, 0)).convert("RGBA")
        return self.rainbows[(w, h)]

    def picture(self, W, H, s):
        """Its words, as a picture (W x H, see-through where there are none), and where the cursor goes after them
        (x, y, its height): made again only when something about them changes."""
        key = (self.text, self.values.get("ink"), self.values.get("paper"), self.values.get("font"),
               self.values.get("size"), self.values.get("effect"), self.which, self.keyboard, W, H, s)
        if self.drawn[0] == key:
            return self.drawn[1], self.drawn[2]
        from PIL import Image, ImageDraw, ImageFilter
        ink, paper = self.ink(), self.backdrop
        font, pad = self.font(s), NOTE_PAD * s
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        muted = co_mix(paper, ink, 0.5)
        top = f"Note {self.which[0]} of {self.which[1]}" if self.which[1] > 1 else "Note"
        words = self.words()
        d.text((pad, pad // 2), top, font=self.small(s), fill=muted + (255,))
        d.text((W - pad, pad // 2), f"{words} word{'' if words == 1 else 's'}" if words else "", font=self.small(s),
               fill=muted + (255,), anchor="ra")
        asc, desc = font.getmetrics()
        lh = int(max((asc + desc) * 1.18, font.size * 1.45))   # (a pixel font's lines: as far apart as the others)
        y0 = pad // 2 + NOTE_TOP * s
        rows = max(1, (H - y0 - pad // 2) // lh)
        lines = wrap(self.text, font, W - 2 * pad - 4 * s) or [("", 0)]
        shown = lines[-rows:]                          # (the last of them: where you're typing)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        for k, (line, _) in enumerate(shown):
            md.text((pad, y0 + k * lh), line, font=font, fill=255)
        last = shown[-1][0]
        cursor = (pad + int(font.getlength(last)) + 2 * s, y0 + (len(shown) - 1) * lh, asc + desc)
        effect = self.values.get("effect")
        if effect == "Glow":                           # a soft light round the letters, in their colour
            glow = mask.filter(ImageFilter.GaussianBlur(7 * s)).point(lambda v: min(255, v * 2))
            out.paste(Image.new("RGBA", (W, H), ink + (255,)), (0, 0), glow)
        elif effect == "Shadow":                       # a shadow behind them, down and to the right
            shade = co_mix(paper, (0, 0, 0), 0.65) if sum(paper) > 120 else co_mix(ink, paper, 0.75)
            out.paste(Image.new("RGBA", (W, H), shade + (255,)), (3 * s, 3 * s), mask)
        fill = self.rainbow(W, H) if effect == "Rainbow" else Image.new("RGBA", (W, H), ink + (255,))
        out.paste(fill, (0, 0), mask)
        if not self.text.strip():                      # (nothing yet: what to do)
            say = ("Type on your keyboard" if self.keyboard else
                   "Plug in a keyboard (USB or Bluetooth), then type")
            d.text((pad, cursor[1] + lh), say, font=self.small(s), fill=muted + (255,))
        self.drawn = (key, out, cursor)
        return out, cursor

    def draw(self, img, x0, y0, now=None):
        from .fine import ImageDraw
        s = detail(img)
        pic = img.pic if s > 1 else img
        W, H = self.w * s, self.h * s
        words, (cx, cy, ch) = self.picture(W, H, s)
        pic.paste(words, (x0 * s, y0 * s), words)
        wall = time.time() if now is None else now
        if wall % (2 * NOTE_BLINK) < NOTE_BLINK:       # the cursor, blinking
            colour = self.ink() if self.values.get("effect") != "Rainbow" else (255, 255, 255)
            ImageDraw.Draw(pic).rectangle((x0 * s + cx, y0 * s + cy + 2 * s, x0 * s + cx + 3 * s - 1,
                                           y0 * s + cy + ch - 2 * s), fill=colour)
