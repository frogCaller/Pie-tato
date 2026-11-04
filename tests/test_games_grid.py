"""The Games tab's folders as a grid of icons: each console's icon (its colour, its short name on it), Snake's card,
Recently played, Favourites and All games; the d-pad going round them (up and down a row, left and right one), A
opening one, B back out with it picked and the grid again; a tap on a tile on the web page opening it; a wider screen
more of them to a row; lots of consoles scrolling; a game with no picture: its console's icon on its row and big
beside the list; a dozen games or fewer: the list as it was; finding one: a list. Pictures saved, to look at."""
import os, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
from pitato import consoles as C
S = SP + "/tgamesgrid"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
os.makedirs(GAMES)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
g.is_pc = lambda: True                              # (every console's games shown)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h, same = 640, 480, True
    frames = 0

    def __init__(self):
        self.last = None

    def show(self, img):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        pass

    def close(self):
        pass


def put(name, size=32768):
    os.makedirs(os.path.dirname(f"{GAMES}/{name}"), exist_ok=True)
    open(f"{GAMES}/{name}", "wb").write(bytes(size))


def shot(name):
    m.dirty = True
    m.flush()
    m.fb.last.save(f"{S}/{name}.png")
    return m.fb.last


def has(img, colour, box, tol=10, least=200):
    a = np.asarray(img.crop(box).convert("RGB")).astype(int)
    return int((np.abs(a - np.array(colour)).max(axis=2) <= tol).sum()) >= least


for i, t in enumerate(("Tetris", "Kirby", "Zelda", "Mario Land", "Wario")):
    put(f"gb/{t}.gb")
for t in ("Advance Wars", "Golden Sun", "Metroid Fusion", "Minish Cap"):
    put(f"gba/{t}.gba")
for t in ("Contra", "Castlevania", "Metroid", "Zelda II"):
    put(f"nes/{t}.nes")
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Games")
m.press("a")
GI = m.tab
items = m.tab_items()
kinds = [(it["kind"], it.get("src")) for it in items]
check(f"thirteen games: a folder for each console, as a grid ({[t['title'] for t in items]})",
      m.games_grid() and [k for k, _ in kinds] == ["child", "gamedir", "gamedir", "gamedir", "gamedir"])
top = shot("grid")
cols = m.games_cols()
check(f"four to a row on the GPi Case's screen ({cols})", cols == 4)
y0 = m.LIST_TOP + 6
tile = g.GAMES_TILE if hasattr(g, "GAMES_TILE") else 96
cw = (640 - 32) / cols


def cell(i):
    """Where tile i is on the screen: (x0, y0, x1, y1) of its icon."""
    r, c = divmod(i, cols)
    x = int(16 + c * cw + (cw - tile) / 2)
    y = int(y0 + 8 + r * 172)
    return x, y, x + tile, y + tile


for i, key in ((1, "gb"), (2, "gba"), (3, "nes")):
    colour = C.CONSOLE_LOOKS[key][0]
    check(f"...{key}'s icon in its place, in its colour", has(top, C.mix(colour, (255, 255, 255), 0.06), cell(i), tol=24))
check("...All games' too, on the next row", has(top, C.mix(C.CONSOLE_LOOKS["all"][0], (255, 255, 255), 0.06), cell(4),
                                                 tol=24))
sel = m.sels.get(GI, 0)
check(f"Snake first, picked ({sel})", sel == 0)
m.press("right")
check(f"right: the next one, Game Boy ({m.sels[GI]})", m.sels[GI] == 1)
m.press("down")
check(f"down: the one under it, All games ({m.sels[GI]}, {m.tab_items()[m.sels[GI]]['title']})",
      m.sels[GI] == 4 + 1 if len(m.tab_items()) > 5 else m.sels[GI] == 4)
m.press("up")
check(f"up: the one above it, the first ({m.sels[GI]})", m.sels[GI] == 0)
m.press("right")
m.press("left"); m.press("left")
check(f"left, at the first: stays ({m.sels[GI]})", m.sels[GI] == 0)
lit = shot("grid-picked")
m.sels[GI] = 2
lit = shot("grid-gba")
x0_, y0_, x1_, y1_ = cell(2)
ring = np.asarray(lit.crop((x0_ - 7, y0_ - 7, x1_ + 7, y0_ - 3)).convert("RGB")).astype(int)
check("the picked one: a ring round it in the accent colour",
      int((np.abs(ring - np.array(g.ACCENT)).max(axis=2) <= 30).sum()) > 60)
m.press("a")
check(f"A: its games (Game Boy Advance), a list ({m.games_dir}, {m.games_grid()})", m.games_dir == "sys:gba"
      and not m.games_grid() and all(it["kind"] == "game" for it in m.tab_items()))
inside = shot("gba-list")
row_icon = (12 + 16, m.list_top() + (m.ROW_H - 40) // 2, 12 + 16 + 40, m.list_top() + (m.ROW_H + 40) // 2)
check("...a game with no picture: its console's icon on its row",
      has(inside, C.mix(C.CONSOLE_LOOKS["gba"][0], (255, 255, 255), 0.06), row_icon, tol=24, least=60))
px0 = 640 - 212 - 16
check("...and big beside the list", has(inside, C.mix(C.CONSOLE_LOOKS["gba"][0], (255, 255, 255), 0.06),
                                        (px0, m.list_top(), 640, m.list_top() + 180), tol=24, least=2000))
m.press("b")
check(f"B: the grid again, Game Boy Advance picked ({m.sels[GI]})", m.games_grid() and m.sels[GI] == 2
      and m.tab_items()[2]["src"] == "sys:gba")

# a tap on a tile, on the web page's copy of the screen: picked and opened
shot("grid-again")
x0_, y0_, x1_, y1_ = cell(3)
btns, out = m.web_touch({"cmd": "tap", "x": (x0_ + x1_) / 2 / 640, "y": (y0_ + y1_) / 2 / 480})
for b in btns:
    m.press(b)
check(f"a tap on NES's tile on the web page: its games ({btns}, {m.games_dir})", m.games_dir == "sys:nes")
m.press("b")

# finding one: a list, as it was
m.games_search("metroid")
check(f"finding one: a list of what's found ({[it['title'] for it in m.tab_items()]})", not m.games_grid()
      and len(m.tab_items()) == 2)
m.games_search("")
check("...B: the grid again", m.games_grid())

# lots of consoles: more rows than fit, the grid goes along with you
for key, ext in (("snes", "sfc"), ("genesis", "md"), ("sms", "sms"), ("gg", "gg"), ("n64", "z64"), ("nds", "nds"),
                 ("ngp", "ngp"), ("gbc", "gbc")):
    put(f"{key}/A game.{ext}")
m.load_tab(GI)
n = len(m.tab_items())
check(f"{n} tiles: more than two rows' worth", n > 8 and m.games_grid())
m.sels[GI] = 0
for _ in range(3):
    m.press("down")
big = shot("grid-scrolled")
check(f"down three rows: further along, the grid with it ({m.sels[GI]}, top row {m.tops[GI]})", m.sels[GI] == 12
      and m.tops[GI] >= 2)
check("...where you are, on its right", has(big, g.BODY, (630, m.LIST_TOP, 640, 432), tol=6, least=20))
m.sels[GI] = 0
shot("grid-all")

# a wider screen: more of them to a row
m.fb.w, m.fb.h = 960, 540
m.dirty = True
m.flush()
check(f"a 960-wide screen: {m.games_cols()} to a row", m.games_cols() == 6)
m.fb.last.save(f"{S}/grid-960.png")
m.press("down")
check(f"...down: a row of six on ({m.sels[GI]})", m.sels[GI] == 6)
m.fb.w, m.fb.h = 640, 480

# a dozen games or fewer: the list, as it was
shutil.rmtree(GAMES)
os.makedirs(GAMES)
for t in ("Tetris", "Kirby"):
    put(f"gb/{t}.gb")
m.load_tab(GI)
check(f"two games: the list as it was, no grid ({[it['title'] for it in m.tab_items()]})", not m.games_grid()
      and [it["kind"] for it in m.tab_items()] == ["child", "game", "game"])
few = shot("few")
check("...their console's icon on their rows", has(few, C.mix(C.CONSOLE_LOOKS["gb"][0], (255, 255, 255), 0.06),
                                                  (28, m.list_top() + m.ROW_H, 68, m.list_top() + 3 * m.ROW_H),
                                                  tol=24, least=60))

# every console has an icon of its own: its colour, and a picture of its kind
seen = set()
for s in g.GAME_SYSTEMS:
    key, badge = s[0], s[1]
    pic = C.draw_console(key, badge, 96)
    mid = pic.getpixel((48, 92))
    seen.add((C.CONSOLE_LOOKS[key][0], C.CONSOLE_LOOKS[key][1]))
    check(f"{key}: an icon ({pic.size}, its colour at its foot {mid[:3]})", pic.size == (96, 96) and key in C.CONSOLE_LOOKS
          and pic.getpixel((0, 0))[3] == 0 and mid[3] == 255)
check(f"...each its own colour or kind ({len(seen)} of {len(g.GAME_SYSTEMS)})", len(seen) == len(g.GAME_SYSTEMS))

# their pictures: RetroArch's, one for every console, with its credits; drawn in the tile's ink
no_pic = [s[0] for s in g.GAME_SYSTEMS if C.console_mask(s[0]) is None]
check(f"every console has its picture (RetroArch's) ({no_pic or 'all'})", not no_pic)
credits = open(os.path.join(C.ICONS, "CREDITS.txt")).read()
check("...with their credits: who drew them, where from, their licence",
      "Bibalox" in credits and "retroarch-assets" in credits and "CC BY 4.0" in credits
      and all(f"{s[0]}.png" in credits for s in g.GAME_SYSTEMS))
setup = open(ROOT + "/setup.sh").read()
check("...and setup.sh puts them on the Pi", "pitato/icons/consoles" in setup)
snes = C.draw_console("snes", "SNES", 96)
shape = C.CONSOLE_LOOKS["snes"][1]
C._masks["snes"] = None                       # (as if it had no picture: its shape)
plain = C.draw_console("snes", "SNES", 96)
del C._masks["snes"]
diff = np.abs(np.asarray(snes).astype(int) - np.asarray(plain).astype(int)).max(axis=2)
check(f"...drawn on its tile, not the plain shape ({int((diff > 60).sum())} pixels differ)", (diff > 60).sum() > 300)
ink = np.asarray(snes.convert("RGB")).astype(int)[20:60, 10:86]
check("...in the tile's ink", int((np.abs(ink - np.array(C.INK)).max(axis=2) <= 20).sum()) > 300)
wii = np.asarray(C.draw_console("wii", "Wii", 96).convert("RGB")).astype(int)[10:64, 20:76]
check("...a light tile's (the Wii's) in the dark ink", int((np.abs(wii - np.array(C.DARK_INK)).max(axis=2) <= 40).sum()) > 80)
check("a console it doesn't know: a plain shape, no picture", C.console_mask("zz") is None
      and C.draw_console("zz", "ZZ", 96).size == (96, 96))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
