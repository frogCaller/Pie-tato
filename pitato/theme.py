"""How things look: the colours (with the accent you pick in Settings), the fonts, and mixing colours."""
import os
import sys


ACCENTS = [("Blue", (96, 170, 228)), ("Teal", (64, 196, 180)), ("Green", (110, 200, 120)),
           ("Purple", (160, 130, 230)), ("Pink", (232, 120, 170)), ("Red", (236, 100, 100)),
           ("Gold", (230, 190, 80)), ("White", (228, 232, 238))]


def set_accent(name):
    """The accent colour everything draws with: changed in each module that draws with it (each
    keeps its own name for it)."""
    colour = dict(ACCENTS).get(name, ACCENTS[0][1])
    package = __name__.split(".")[0]
    for mod in list(sys.modules.values()):
        if getattr(mod, "__name__", "").split(".")[0] == package and "ACCENT" in vars(mod):
            mod.ACCENT = colour
    BADGE["dir"] = colour


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def bundled_font(name, instead):
    """A typeface that comes with Pie-tato, in its static/fonts folder (where setup.sh puts the code, or the
    Pie-tato folder itself); the system's `instead` if it isn't there."""
    for static in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"),
                   os.environ.get("PITATO_STATIC", "").strip()):
        path = os.path.join(static, "fonts", name) if static else ""
        if path and os.path.isfile(path):
            return path
    return instead


# the home screen's: Inter (thin, for the time and the temperature). Its OpenType (CFF) files, laid out simply
# (draw.py), draw several times quicker than its TrueType ones on a Pi.
FONT_THIN = bundled_font("InterDisplay-Light.otf", FONT)
FONT_UI = bundled_font("Inter-Regular.otf", FONT)
FONT_UI_BOLD = bundled_font("Inter-SemiBold.otf", FONT_BOLD)


# PiE-ink's colour-screen palette
PI_BG, PI_FG, PI_DIM, PI_ACCENT = (0, 0, 0), (255, 255, 255), (150, 150, 150), (98, 210, 255)
PI_UP, PI_DOWN = (0, 255, 0), (255, 80, 80)


# colours: calm dark theme for a small screen
BG     = (16, 19, 23)
ROW    = (31, 37, 46)
TEXT   = (236, 239, 243)
BODY   = (176, 184, 196)
MUTED  = (104, 112, 125)
LINE   = (40, 46, 55)
ACCENT = (96, 170, 228)
DONE   = (122, 186, 150)
WARN   = (230, 120, 120)
PHOTO_BG = (6, 7, 9)
BADGE = {  # file type label colours in the Files tab
    "dir": ACCENT, "image": DONE, "video": (110, 196, 196), "audio": (170, 146, 222),
    "pdf": (224, 122, 128), "doc": (124, 152, 232), "text": BODY, "other": MUTED,
}


def co_ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def co_mix(c1, c2, f):
    return tuple(int(round(a + (b - a) * f)) for a, b in zip(c1, c2))
