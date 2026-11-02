"""The Games tab's icons: a tile for each console, in a colour of its own, with a picture of it and its short name, big;
and tiles for Recently played, Favourites and All games. The consoles' pictures are RetroArch's (its menu's Monochrome
icons, CC BY 4.0: icons/consoles/CREDITS.txt), drawn in the tile's ink; a console without one gets a plain shape of
its kind (a handheld, one on its side, one that folds, a cartridge, a disc, an arcade stick)."""
import math
import os

from .theme import FONT_BOLD

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "consoles")   # (key.png: a console's picture)
_masks = {}

CONSOLE_LOOKS = {   # key: (its colour, its kind)
    "gb": ((98, 132, 64), "tall"), "gbc": ((176, 64, 150), "tall"), "gba": ((82, 82, 196), "wide"),
    "nes": ((196, 58, 58), "cart"), "snes": ((128, 104, 206), "cart"), "genesis": ((58, 64, 82), "cart"),
    "sms": ((40, 104, 196), "cart"), "gg": ((36, 150, 140), "wide"), "ngp": ((70, 150, 170), "wide"),
    "ngpc": ((52, 170, 116), "wide"), "neogeo": ((206, 150, 36), "stick"), "n64": ((34, 130, 100), "cart"),
    "ps1": ((120, 124, 140), "disc"), "psp": ((44, 56, 82), "wide"), "nds": ((78, 150, 214), "fold"),
    "dc": ((226, 120, 46), "disc"), "ps2": ((30, 58, 136), "disc"), "gc": ((104, 78, 176), "disc"),
    "wii": ((196, 202, 214), "disc"),
    "recent": ((70, 116, 190), "clock"), "fav": ((214, 160, 38), "star"), "all": ((92, 100, 118), "grid"),
}
CONSOLE_OTHER = ((92, 100, 118), "cart")   # (one this doesn't know)
INK = (244, 246, 250)          # the picture and the name, on a tile
DARK_INK = (34, 38, 46)        # ...on a light one


def mix(a, b, k):
    return tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def console_mask(key):
    """A console's picture (icons/consoles/key.png) as a mask, cropped to it: where it's drawn, how much (its
    transparency, and how light it is). None: none for it, or it won't open. Kept once read."""
    if key in _masks:
        return _masks[key]
    mask = None
    path = os.path.join(ICONS, f"{key}.png")
    if key in CONSOLE_LOOKS and os.path.isfile(path):
        try:
            from PIL import Image, ImageChops
            with Image.open(path) as im:
                rgba = im.convert("RGBA")
            mask = ImageChops.multiply(rgba.getchannel("A"), rgba.convert("L"))
            box = mask.getbbox()
            mask = mask.crop(box) if box else None
        except Exception:                               # (a broken file: its shape instead)
            mask = None
    _masks[key] = mask
    return mask


def draw_console(key, label, size=96, fine=1):
    """A console's tile (RGBA, size square): its colour, its picture (or a shape of its kind), its short name (label)
    under it ("": none). Drawn three times bigger and scaled down, so its edges come out smooth. fine: size is that
    many times the tile's, for a screen drawn finely (fine.py): its edge as much thicker."""
    from PIL import Image, ImageDraw, ImageFont
    colour, kind = CONSOLE_LOOKS.get(key, CONSOLE_OTHER)
    S = size * 3
    ink = DARK_INK if sum(colour) > 520 else INK
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shape = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.23), fill=255)
    grad = Image.linear_gradient("L").resize((S, S))   # (lighter at the top)
    tile = Image.composite(Image.new("RGBA", (S, S), mix(colour, (0, 0, 0), 0.28) + (255,)),
                           Image.new("RGBA", (S, S), mix(colour, (255, 255, 255), 0.12) + (255,)), grad)
    out.paste(tile, (0, 0), shape)
    d = ImageDraw.Draw(out)
    hole = mix(colour, (0, 0, 0), 0.35) + (255,)       # a screen, a hole, a label: in a darker shade of it
    cx, cy = S * 0.5, (S * 0.4 if label else S * 0.5)   # the picture's middle (its name goes under it)
    u = S / 100                                         # (laid out in hundredths of the tile)

    def rr(x0, y0, x1, y1, r, fill):
        d.rounded_rectangle((cx + x0 * u, cy + y0 * u, cx + x1 * u, cy + y1 * u), radius=r * u, fill=fill)

    def dot(x, y, r, fill):
        d.ellipse((cx + (x - r) * u, cy + (y - r) * u, cx + (x + r) * u, cy + (y + r) * u), fill=fill)

    def plus(x, y, arm, w, fill):
        rr(x - arm, y - w / 2, x + arm, y + w / 2, w * 0.3, fill)
        rr(x - w / 2, y - arm, x + w / 2, y + arm, w * 0.3, fill)

    pic = console_mask(key)
    if pic is not None:                                 # its picture (RetroArch's), in the ink, as big as fits
        bw, bh = (0.80 * S, 0.54 * S) if label else (0.80 * S, 0.72 * S)
        k = min(bw / pic.width, bh / pic.height)
        pw, ph = max(1, round(pic.width * k)), max(1, round(pic.height * k))
        out.paste(Image.new("RGBA", (pw, ph), ink + (255,)), (round(cx - pw / 2), round(cy - ph / 2)),
                  pic.resize((pw, ph), Image.LANCZOS))
    elif kind == "tall":                                # a handheld, standing up
        rr(-17, -25, 17, 25, 5, ink)
        rr(-12, -20, 12, -2, 2.5, hole)
        plus(-7, 11, 5, 3.4, hole)
        dot(5, 13, 2.8, hole)
        dot(10.5, 9, 2.8, hole)
    elif kind == "wide":                                # a handheld on its side
        rr(-30, -14, 30, 14, 12, ink)
        rr(-14, -10, 14, 10, 2.5, hole)
        plus(-22, 0, 4.6, 3.2, hole)
        dot(20, 3, 2.6, hole)
        dot(25, -2, 2.6, hole)
    elif kind == "fold":                                # one that folds: a screen above, another below
        rr(-19, -27, 19, -3, 4, ink)
        rr(-13, -23, 13, -7, 2, hole)
        rr(-19, 1, 19, 25, 4, ink)
        rr(-10, 5, 10, 21, 2, hole)
        plus(-15, 13, 2.6, 1.8, hole)
        dot(15, 11, 1.6, hole)
        dot(15, 16, 1.6, hole)
    elif kind == "cart":                                # a cartridge: its corners cut, its label, its grip
        d.polygon([(cx + x * u, cy + y * u) for x, y in ((-15, -25), (15, -25), (20, -20), (20, 25), (-20, 25),
                                                          (-20, -20))], fill=ink)
        rr(-14, -18, 14, 7, 2.5, hole)
        for k in range(3):
            rr(-12, 12 + k * 4.4, 12, 13.8 + k * 4.4, 0.9, hole)
    elif kind == "disc":                                # a disc: its hole, a ring round it, a shine
        dot(0, 0, 25, ink)
        dot(0, 0, 9, hole)
        dot(0, 0, 4.5, ink)
        dot(0, 0, 2.2, hole)
        d.arc((cx - 19 * u, cy - 19 * u, cx + 19 * u, cy + 19 * u), 200, 250, fill=hole, width=max(1, int(2.2 * u)))
    elif kind == "stick":                               # an arcade stick: its lever, its buttons
        rr(-30, 6, 30, 22, 5, ink)
        rr(-17.5, -14, -14.5, 8, 1.4, ink)
        dot(-16, -17, 7.5, ink)
        for x, y in ((4, 12), (13, 10), (22, 12)):
            dot(x, y, 3.2, hole)
    elif kind == "clock":                               # Recently played: a clock
        dot(0, 0, 24, ink)
        dot(0, 0, 19, hole)
        rr(-1.6, -14, 1.6, 1.6, 1.6, ink)
        rr(-1.6, -1.6, 11, 1.6, 1.6, ink)
    elif kind == "star":                                # Favourites: a star
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            r = (25 if k % 2 == 0 else 10.5) * u
            pts.append((cx + math.cos(a) * r, cy + 2 * u + math.sin(a) * r))
        d.polygon(pts, fill=ink)
    elif kind == "grid":                                # All games: four little tiles
        for x in (-12.5, 12.5):
            for y in (-12.5, 12.5):
                rr(x - 10, y - 10, x + 10, y + 10, 3, ink)
    if label:                                           # its short name, big, under the picture
        try:
            font = ImageFont.truetype(FONT_BOLD, int(S * (0.19 if len(label) <= 3 else 0.16)))
        except OSError:
            font = ImageFont.load_default()
        d.text((S / 2, S * 0.83), label, font=font, fill=ink, anchor="mm")
    edge = mix(colour, (255, 255, 255), 0.35)
    d.rounded_rectangle((1, 1, S - 2, S - 2), radius=int(S * 0.23), outline=edge + (255,), width=3 * fine)
    out.putalpha(Image.composite(out.getchannel("A"), Image.new("L", (S, S), 0), shape))
    return out.resize((size, size), Image.LANCZOS)
