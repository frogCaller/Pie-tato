"""The home screen's Games icon: a console you have games for (its picture from the Games list's, in its colour), the
next one each time you come to the home screen (from an app, from the terminal, as it starts), in the Games list's
order, round and round; drawn again without coming anew (a toast, the clock), the same one. Each look (Glass, Bright,
Cards) draws it its own way. No games: the controller, as ever; games for one console: always that one."""
import json, os, shutil, subprocess, sys
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_home_games"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
for d in ("Music", "Pictures", "Videos", "Documents", "Games/gb", "Games/gba", "Games/nes", "Games/Saves"):
    os.makedirs(f"{HOME}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
g.games_dir = lambda: GAMES
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    def show(self, img): FB.last = img
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB


def game(system, name, size=0x8000):
    path = f"{GAMES}/{system}/{name}"
    with open(path, "wb") as f:
        f.write(b"NES\x1a\x01\x01" + bytes(size - 6) if system == "nes" else bytes(size))
    return path


game("gb", "Tetris (World).gb")
game("gba", "Advance Wars (USA).gba")
game("nes", "Zelda (USA).nes")
m = g.Media()
m.enter()
gi = m.tab_index("games")
have = m.games_systems()
check(f"the consoles you have games for, in the Games list's order ({have})", have == ["gb", "gba", "nes"])


def drawn():
    m.dirty = True
    m.flush()
    return m.games_face()


def away_and_back():
    """An app opened from the home screen (the Games list), and B back to it."""
    m.open_app(gi)
    drawn()
    m.press("b")
    return drawn()


first = drawn()
check(f"as it starts: the Games icon shows one of them ({first})", m.view == "home" and first in have)
check("...drawn again, without coming to it anew (a toast, the clock): the same one",
      drawn() == first and (m.toast("Hello", 1) or drawn()) == first)
seen = [first] + [away_and_back() for _ in range(3)]
nxt = [have[(have.index(first) + k) % 3] for k in range(4)]
check(f"each time you come back to the home screen: the next one, round and round ({seen})", seen == nxt)
m.leave()
m.enter()
back = drawn()
check(f"...from the terminal too ({back})", back == have[(have.index(seen[-1]) + 1) % 3])


def pixels(im):
    im = getattr(im, "pic", im)
    return im.convert("RGBA").tobytes()


size = m.home_geometry()[0]
check("its picture: the console's own (as the Games list has it), not the controller",
      pixels(m.home_icon("Games")) == pixels(g.made_fine(g.draw_icon("Games", size, face=back), 1))
      and pixels(m.home_icon("Games")) != pixels(g.draw_icon("Games", size)))
for style in ("Bright", "Cards"):
    m.set_setting("home_style", style)
    m.home_base = (None, None)
    face = away_and_back()
    plain = g.draw_glyph("Games", m.GLYPH) if style == "Cards" else g.draw_bright_icon("Games", size)
    check(f"{style}: its own way, a console's ({face})", face in have and pixels(m.home_icon("Games")) != pixels(plain))
m.set_setting("home_style", "Glass")
m.home_base = (None, None)

for system in ("gb", "nes"):
    shutil.rmtree(f"{GAMES}/{system}")
m.load_tab(gi)
faces = {away_and_back() for _ in range(3)}
check(f"games for one console: always that one ({faces})", faces == {"gba"})
shutil.rmtree(f"{GAMES}/gba")
m.load_tab(gi)
face = away_and_back()
check(f"no games: the controller, as ever ({face})", face is None
      and pixels(m.home_icon("Games")) == pixels(g.made_fine(g.draw_icon("Games", size), 1)))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
