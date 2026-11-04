"""A game's Picture: Fit, Sharp, and now Fill, the whole screen. On a TV (wider than 4:3) an N64 game in Fill is drawn
wide by Mupen64Plus-Next itself (16:9 adjusted: more to each side, nothing stretched), filling the screen, no black
border either side; other games, and an N64 game on a 4:3 screen, are stretched to it. The picture is kept for each
console (at first: as it was for every game). An N64 game changed to Fill or back on a TV starts again where it was
(the emulator takes its wide picture as it starts); the rest change at once. With the real Mupen64Plus-Next (built
here, drawing with Mesa's llvmpipe) and a free test ROM, on a 1080p screen."""
import os, sys, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
src = open(TESTS + "/test_n64.py").read()
exec(src.split("check(f\"the N64 emulator is found")[0].replace('S = SP + "/tn64"', 'S = SP + "/tn64fill"'))
from pitato.screens.games import GAME_PICTURES, N64_WIDE


def extent(spec):
    """Where the picture is lit: (x0, x1, y0, y1)."""
    rgb = frame(spec)
    lit = rgb.max(-1) > 24
    ys, xs = lit.any(1).nonzero()[0], lit.any(0).nonzero()[0]
    return (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())) if len(xs) else None


# ---- the picture's size ------------------------------------------------------------------------------
check(f"Fill: the whole screen, whatever the picture's shape ({E.picture_size(1920, 1080, 640, 480, 4 / 3, 'Fill')})",
      E.picture_size(1920, 1080, 640, 480, 4 / 3, "Fill") == (1920, 1080)
      and E.picture_size(1920, 1080, 240, 160, 1.5, "Fill") == (1920, 1080))
check(f"...a Pi Zero's limit kept, in the screen's shape ({E.picture_size(1920, 1080, 640, 480, 4 / 3, 'Fill', 640 * 480 * 2)})",
      E.picture_size(1920, 1080, 640, 480, 4 / 3, "Fill", 640 * 480 * 2) == (1045, 587))
check("Fit and Sharp as they were", E.picture_size(1920, 1080, 640, 480, 4 / 3, "Fit", whole=False) == (1440, 1080)
      and E.picture_size(1920, 1080, 640, 480, 4 / 3, "Sharp") == (1280, 960))

# ---- the real N64 emulator on a 1080p TV ---------------------------------------------------------------
spec = screen_as(32, 1920, 1080)
run = start(N64 + "/InputRDP.z64", resume=False)
run.wait_started(60)
until(lambda: yellow(frame(spec)).sum() > 500000, 20)
x0, x1, _, _ = extent(spec)
check(f"Fit: 4:3, a thick black border either side ({x0}..{x1})", 230 <= x0 <= 270 and 1650 <= x1 <= 1690)
run.send("picture Fill")
time.sleep(0.8)
x0, x1, _, _ = extent(spec)
rgb = frame(spec)
check(f"...Fill while it plays: stretched to the whole screen at once ({x0}..{x1})", x0 <= 30 and x1 >= 1890)
finish(run)
run = GM.GameRun({"path": N64 + "/InputRDP.z64", "title": "InputRDP", "system": "n64"})
run.start(GM.find_core("n64"), sound="", volume=80, picture="Fill", resume=False, options=[N64_WIDE])
runs.append(run)
run.wait_started(60)
until(lambda: yellow(frame(spec)).sum() > 1500000, 20)
time.sleep(0.5)
rgb = frame(spec)
x0, x1, _, _ = extent(spec)
cur = red(rgb)
pts = cur.nonzero()
cw, ch = int(pts[1].max() - pts[1].min() + 1), int(pts[0].max() - pts[0].min() + 1)
check(f"Fill, started wide: the whole screen ({x0}..{x1}), the game's square still square ({cw}x{ch}: drawn wide, "
      f"not stretched)", x0 <= 30 and x1 >= 1890 and abs(cw - ch) <= 4)
finish(run)

# ---- media mode: the menu's Picture -------------------------------------------------------------------
g.Framebuffer = type("FB", (), {"w": 640, "h": 480, "real_w": 1920, "real_h": 1080, "show": lambda self, img: None,
                                "show_part": lambda self, img, box: None, "blank_outside": lambda self, box: None,
                                "invalidate": lambda self: None, "close": lambda self: None})
m = g.Media(); m.enter()
check(f"at first: Fit for every console ({[m.game_picture(k) for k in ('n64', 'gba', 'snes')]})",
      [m.game_picture(k) for k in ("n64", "gba", "snes")] == ["Fit"] * 3)
m.state["settings"]["game_picture"] = "Sharp"
check("...or as it was for every game before (Sharp)", m.game_picture("gba") == "Sharp")
del m.state["settings"]["game_picture"]

started = []


class FakeRun:
    def __init__(self, game, on_change=None):
        self.game, self.sent = game, []
        self.ended, self.state, self.error, self.slow, self.disc = False, "on", "", False, (0, 1)

    def start(self, core, sound="", volume=80, picture="Fit", options=()):
        started.append((self.game["system"], picture, list(options)))

    def send(self, line):
        self.sent.append(line)

    def quit(self, timeout=None):
        self.ended = True


g.GameRun = FakeRun
g.find_core = lambda key: "/cores/fake_libretro.so"
g.bios_missing = lambda core, game=None: None
for k in ("n64", "gba"):
    m.game_open({"src": f"/games/{k}/Game.{k}", "title": "Game", "system": k})
    check(f"{k}: started in Fit, nothing wide ({started[-1]})", started[-1] == (k, "Fit", []))
    m.game_end()

m.game_open({"src": "/games/n64/Mario.z64", "title": "Mario", "system": "n64"})
first = m.game
del started[:]
m.game_change("picture", 1)
check(f"Picture ▶: Sharp, at once, no restart ({first.sent}, {started})", first.sent[-1:] == ["picture Sharp"]
      and not started and m.game is first)
m.game_change("picture", 1)
check(f"...▶ Fill: on a TV the N64 game starts again, wide, where it was ({started}, {first.ended})",
      started == [("n64", "Fill", [N64_WIDE])] and first.ended and m.game is not first and m.view == "game")
check(f"...kept for N64 games ({m.state['settings'].get('game_picture_n64')!r}), not the others' ({m.game_picture('gba')})",
      m.state["settings"].get("game_picture_n64") == "Fill" and m.game_picture("gba") == "Fit")
wide = m.game
del started[:]
m.game_change("picture", 1)
check(f"...▶ Fit again: 4:3, so it starts again ({started})", started == [("n64", "Fit", [])] and wide.ended)
check(f"...◀ from Fit: Fill, wide again ({m.game_change('picture', -1) or started[-1]})", started[-1] == ("n64", "Fill", [N64_WIDE]))
m.game_end()
m.game_open({"src": "/games/n64/Mario.z64", "title": "Mario", "system": "n64"})
check(f"the next N64 game: Fill, wide, from the start ({started[-1]})", started[-1] == ("n64", "Fill", [N64_WIDE]))
m.game_end()

del started[:]
m.game_open({"src": "/games/gba/Zelda.gba", "title": "Zelda", "system": "gba"})
gba = m.game
m.game_change("picture", -1)
check(f"a GBA game: ◀ Fill, stretched at once, no restart ({gba.sent}, {len(started)})",
      gba.sent[-1:] == ["picture Fill"] and len(started) == 1 and m.game is gba)
m.game_end()

m.fb.real_w, m.fb.real_h = 640, 480                     # (a 4:3 screen: nothing wider to fill)
del started[:]
m.game_open({"src": "/games/n64/Mario.z64", "title": "Mario", "system": "n64"})
check(f"a 4:3 screen: an N64 game in Fill isn't drawn wide ({started})", started == [("n64", "Fill", [])])
n64 = m.game
m.game_change("picture", 1)
check(f"...and changes at once ({n64.sent}, {len(started)})", n64.sent[-1:] == ["picture Fit"] and len(started) == 1)
m.game_end()
m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
