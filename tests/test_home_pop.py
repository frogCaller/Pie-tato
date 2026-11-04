"""The home screen: what's playing pops up for a few seconds (a song starts, the radio's song changes, you come back
from the terminal) and then the weather's back; every app's line shows at the bottom; smaller, rounder cards."""
import io, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw
S = SP + "/t_home_pop"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music"); os.makedirs(HOME + "/Pictures")
for k in range(3):
    open(HOME + f"/Music/tune {k}.mp3", "wb").write(b"ID3")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {"location": {"name": "Portland", "admin1": "Oregon", "country": "US", "lat": 45.5, "lon": -122.6}}},
          open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
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
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB


class FakeProc:
    def __init__(self, lines=()):
        self.stdin = io.StringIO(); self.dead = False; self.stdout = iter(lines)
    def poll(self): return 0 if self.dead else None
    def wait(self, timeout=None): return 0
    def kill(self): self.dead = True


def fake_spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = FakeProc()


g.Media.spawn = fake_spawn
texts = []
real_text = ImageDraw.ImageDraw.text


def drawn(m):
    """What the home screen says, drawn afresh."""
    texts.clear()
    ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
    try:
        m.dirty = True; m.flush()
    finally:
        ImageDraw.ImageDraw.text = real_text
    return list(texts)


m = g.Media(); m.enter()
m.weather.data = {"code": 2, "is_day": True, "temp": 68, "days": [{"hi": 72, "lo": 55}]}
apps = [a for a, _ in m.home_apps()]

# ---- every app's line at the bottom, Games and TV too
missing = []
for k, name in enumerate(apps):
    m.home_sel = k
    if g.HOME_ICONS[name][1] not in drawn(m):
        missing.append(name)
check(f"every app's line shows at the bottom (missing: {missing})", not missing)
check("Games: Snake, and your Game Boy to PlayStation games (it fits now)",
      g.HOME_ICONS["Games"][1] == "Snake, and your Game Boy to PlayStation games")

# ---- the cards: a little smaller, rounder
slots = g.home_layout(len(apps), g.home_cols(len(apps)))
x0, y0, x1, y1 = m.card_box(3, slots, 5, 0)
check(f"the tiles: {x1 - x0:.0f} square", x1 - x0 == y1 - y0 == m.TILE == 74)
m.home_sel = 0; drawn(m)
img = FB.last.convert("RGB")
corner = img.getpixel((int(x0) + 4, int(y0) + 4))
inside = img.getpixel((int(x0) + 20, int(y0) + 4))
check(f"...with rounder corners ({corner} outside the curve, {inside} inside)", sum(corner) < sum(inside) - 20)
last = m.card_box(len(apps) - 1, slots, 5, 0)
check(f"...all three rows, names and all, above the buttons' line ({last[3] + m.LABEL_DY + 8:.0f} < {480 - m.FOOTER + 4})",
      last[3] + m.LABEL_DY + 8 <= 480 - m.FOOTER + 4)
first = m.card_box(0, slots, 5, 0)
check(f"...from margin to margin, like the time and the weather ({first[0]:.0f} .. {last[2]:.0f})",
      first[0] == m.HOME_X and abs(last[2] - (640 - m.HOME_X)) < 1)
said = drawn(m)
check("Home's name fits under its tile", "Home" in said and not any("…" in t for t in said))
check("...its full name everywhere else", m.web_catalog()["apps"][0]["name"] == "Home"
      and g.LIBRARY[m.home_apps()[0][1]]["name"] == "Home")

# ---- a song starts: what's playing pops up, then goes
mi = next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == "audio")
m.load_tab(mi)
m.play(m.tab_items(mi), 1, show=False)
m.view = "home"; m.home_sel = apps.index("Games")
said = drawn(m)
check("a song starts: it pops up (and START's said)", "NOW PLAYING" in said and "tune 1" in said and "Now playing" in said
      and "68°" not in said)
check("...for a few seconds", 3 <= m.np_until - time.monotonic() <= 6)
m.dirty = False
m.np_until = time.monotonic() - 0.01
m.tick()
check("then it's had its moment: the home screen's drawn again", m.dirty and m.np_until == 0.0)
said = drawn(m)
check("...the weather back, the song gone from the top, START not said", "68°" in said and "NOW PLAYING" not in said
      and "tune 1" not in said and "Now playing" not in said)
check("...and the app's line has its room", g.HOME_ICONS["Games"][1] in said)
img = FB.last.convert("RGB")
ri = apps.index("Music")
bx0, by0, bx1, by1 = m.card_box(ri, slots, 5, 0)
dot = img.getpixel((int(bx1 - 3), int(by0 + 3)))
check(f"...the dot on Music still says it's playing ({dot})", dot == g.ACCENT[:3])
m.dirty = False; m.tick()
check("...(drawn again once, not every tick)", not m.dirty)
m.press("start")
check("START still opens Now playing", m.view == "now" and m.now_from == "home")
m.press("b")
check("...B back home", m.view == "home")

# the next song: up again
m.started = time.monotonic() - 200; m.proc.dead = True
m.tick()
said = drawn(m)
check("the next song starts: up again", m.qi == 2 and "tune 2" in said and "NOW PLAYING" in said)
m.np_until = 0.0
said = drawn(m)
check("...(not while it isn't)", "NOW PLAYING" not in said)

# ---- you come back from the terminal: up for a moment
m.leave()
check("in the terminal, the music goes on", m.playing_now() and not m.active)
m.np_until = 0.0
m.enter()
check("back from the terminal: what's playing, for a moment", m.view == "home" and m.now_popped()
      and "NOW PLAYING" in drawn(m))
m.stop()
check("nothing playing: no card, however recently", not m.now_popped() and "NOW PLAYING" not in drawn(m))

# ---- the radio's song changes: up again
radio = {"key": "r1", "title": "Jazz Radio", "kind": "radio", "src": "http://192.168.1.20:8000/jazz", "sub": ""}
m.play([radio], 0, show=False)
m.view = "home"
m.np_until = 0.0
p = m.proc
m.reader(FakeProc(["StreamTitle='Take Five';\n"]))   # (another player's lines: not this one's)
check("a line from a player that's gone: nothing", not m.np_until)
p.stdout = iter(["StreamTitle='Take Five';\n"])
m.reader(p)
check("the radio's song changes: up again", m.np_until > time.monotonic() and m.meta.get("song") == "Take Five"
      and "Take Five" in drawn(m) and "ON THE RADIO" in texts)
m.np_until = 0.0
p.stdout = iter(["StreamTitle='Take Five';\n"])
m.reader(p)
check("...the same song again: not up again", not m.np_until)
p.stdout = iter(["StreamTitle='So What';\n"])
m.reader(p)
check("...the next one: up", m.np_until > time.monotonic() and m.meta.get("song") == "So What")
m.stop(); m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
