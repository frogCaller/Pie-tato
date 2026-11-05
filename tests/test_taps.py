"""The web page's copy of the screen, tapped: what draw.py puts down as it draws (the buttons along the bottom, the
tabs, a list's rows, the home screen's apps, Settings' rows and their ◀ ▶, the keyboard's keys, a menu's rows, a page's
links), what a tap there does (a row picked and opened), a swipe and a mouse's wheel (a list scrolled, its
pick kept where it is; ▲▼ elsewhere; a video's volume), typing into the box on the screen, and a picture put up some
other way (its taps: none)."""
import http.server, json, os, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import www as WW

S = SP + "/t_taps"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music/Long")
for k in range(30):
    open(f"{HOME}/Music/Long/song {k:02d}.mp3", "wb").write(b"\xff\xfb" + bytes(400))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
json.dump({"settings": {"home_style": "Glass"}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
real_run = g.subprocess.run       # (this machine's own consoles left as they are: no switching to media mode's)
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd[:1] in (["chvt"], ["fgconsole"])
                                         else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    count = 0

    def __init__(self):
        self.frames, self.last = FB.count, None

    def show(self, img):
        self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.show(img)

    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
m.weather.data = None


def draw():
    m.dirty = True
    m.flush()


def touch(cmd, **kw):
    """As app.handle does: the buttons it stands for, pressed (then the screen drawn, as the main loop would)."""
    names, out = m.web_touch(dict(kw, cmd=cmd))
    for n in names:
        m.press(n)
    m.flush()
    return names, out


def tap(x, y):
    return touch("tap", x=x / m.fb.w, y=y / m.fb.h)


def spot(test):
    """The middle of the first place put down whose what passes test."""
    for (x0, y0, x1, y1), what in m.taps:
        if test(what):
            return (x0 + x1) / 2, (y0 + y1) / 2
    return None


# ---- the home screen ----------------------------------------------------------------------------------------------
m.view = "home"; m.home_sel = 0
draw()
apps = [a for a, _ in m.home_apps()]
tiles = [w for _, w in m.taps if w[:3] == ("sel", "attr", "home_sel")]
check(f"the home screen: each app tappable ({len(tiles)} of {len(apps)})", len(tiles) == len(apps))
feet = [w for _, w in m.taps if w[0] == "keys"]
check(f"...and its buttons along the bottom ({feet})", ("keys", "a") in feet and ("keys", "y") in feet)
check("...the taps are this picture's", m.taps_at == m.fb.frames and m.taps_now() == m.taps)
tv = apps.index("TV")
x, y = spot(lambda w: w == ("sel", "attr", "home_sel", tv))
names, out = tap(x, y)
check(f"a tap on TV: picked and opened (A), in one tap ({names}, {out}, {m.where_text()})", names == ["a"]
      and out == {"ok": True} and m.view == "list" and m.where_text() == "TV")

# ---- a tab's list, the tabs along the top -------------------------------------------------------------------------
rows = [w for _, w in m.taps if w[:3] == ("sel", "sels", m.tab)]
check(f"TV's list: each row on the screen tappable ({len(rows)})", len(rows) == len(m.tab_items()) > 2)
x, y = spot(lambda w: w == ("sel", "sels", m.tab, 2))
names, _ = m.web_touch({"cmd": "tap", "x": x / m.fb.w, "y": y / m.fb.h})     # (A not pressed here: still the list)
check(f"a tap on its third row: picked, and A to open it ({m.sels[m.tab]}, {names})", m.sels[m.tab] == 2
      and names == ["a"] and m.view == "list")
m.sels[m.tab] = 0
names, _ = m.web_touch({"cmd": "tap", "x": x / m.fb.w, "y": y / m.fb.h})
check(f"...one picked already elsewhere: the same, one tap ({m.sels[m.tab]}, {names})", m.sels[m.tab] == 2
      and names == ["a"])
m.flush()
tabs = [w for _, w in m.taps if w[0] == "tab"]
check(f"the tabs along the top tappable ({len(tabs)})", len(tabs) >= 3)
music = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
other = next(w[1] for w in tabs if w[1] != m.strip_tab() and g.LIBRARY[w[1]]["name"] != "TV")
x, y = spot(lambda w: w == ("tab", other))
names, _ = tap(x, y)
check(f"a tap on {g.LIBRARY[other]['name']}, along the top: that tab ({m.where_text()}, {names})", m.tab == other
      and names == [] and m.view == "list")
x, y = spot(lambda w: w == ("tab", other))
tap(x, y)
check("...tapped again: nothing more", m.tab == other)
m.tab = music; m.load_tab(music)
draw()
# a long folder: the wheel and a swipe scroll it, the pick staying where it is on the screen
check(f"Music: {len(m.tab_items())} songs", len(m.tab_items()) == 30)
rows_fit = m.visible_rows()
m.sels[music], m.tops[music] = 2, 0
draw()
touch("scroll", y=3)
check(f"the wheel, 3 notches down: the list scrolled 3, the pick 3 on with it (top {m.tops[music]}, "
      f"pick {m.sels[music]})", m.tops[music] == 3 and m.sels[music] == 5)
touch("swipe", x=0, y=-2 * m.ROW_H / m.fb.h)
check(f"a finger up two rows: 2 more (top {m.tops[music]}, pick {m.sels[music]})", m.tops[music] == 5
      and m.sels[music] == 7)
touch("scroll", y=-12)
check(f"back up: never past the top (top {m.tops[music]}, pick {m.sels[music]})", m.tops[music] == 0
      and m.sels[music] == 0)
for _ in range(5):
    touch("scroll", y=12)
check(f"down: never past the end, the last one picked in the end (top {m.tops[music]}, pick {m.sels[music]})",
      m.tops[music] == 30 - rows_fit and m.sels[music] == 29)
names, _ = touch("swipe", x=-0.3, y=0.02)
check(f"a finger to the left: ◀▶'s ▶ (a screenful on) ({names})", names == ["right"])
# the buttons along the bottom
lr = [box for box, w in m.taps if w in (("keys", "l"), ("keys", "r"))]
check(f"L R along the bottom: two halves, L's on the left ({lr})", len(lr) == 2 and lr[0][2] <= lr[1][0])
x, y = spot(lambda w: w == ("keys", "b"))
names, _ = tap(x, y)
check(f"B along the bottom, tapped: B (home) ({names}, {m.view})", names == ["b"] and m.view == "home")
m.view = "list"
draw()

# ---- a picture put up some other way (not drawn by flush): no taps -----------------------------------------------
m.render_wait("Somewhere", "Loading")
check("a picture put up some other way: none of the last one's taps count", m.taps_now() == [])
names, _ = tap(320, 240)
check(f"...a tap on it does nothing ({names})", names == [])
draw()

# ---- Settings: rows, and a picked row's ◀ value ▶ -----------------------------------------------------------------
m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.set_page = "root"; m.set_sel = 0
draw()
srows = m.settings_rows()
acc = next(i for i, r in enumerate(srows) if r[0] == "accent")
m.set_sel = acc
draw()
check("Settings: each row tappable", sum(w[:3] == ("sel", "attr", "set_sel") for _, w in m.taps) >= 5)
before = m.setting("accent")
x, y = spot(lambda w: w == ("keys", "right"))
names, _ = tap(x, y)
check(f"...the accent's ▶, tapped: the next colour ({before} -> {m.setting('accent')}, {names})", names == ["right"]
      and m.setting("accent") != before)
x, y = spot(lambda w: w == ("keys", "left"))
tap(x, y)
check(f"...its ◀: back ({m.setting('accent')})", m.setting("accent") == before)
other = next(i for i, r in enumerate(srows) if i > acc and r[2])
if any(w == ("sel", "attr", "set_sel", other) for _, w in m.taps):
    x, y = spot(lambda w: w == ("sel", "attr", "set_sel", other))
    names, _ = m.web_touch({"cmd": "tap", "x": x / m.fb.w, "y": y / m.fb.h})
    check(f"another row tapped: picked, and A ({m.set_sel} = {other}, {names})", m.set_sel == other and names == ["a"])
    m.flush()
touch("scroll", y=50)
touch("scroll", y=50)                                  # (twice: more rows than one turn of the wheel goes)
check(f"the wheel down a long way: the last row, never round to the top ({m.set_sel} of {len(srows)})",
      m.set_sel == len(srows) - 1)

# ---- the keyboard on the screen, and typing from the web page -----------------------------------------------------
got = []
m.open_keyboard("Search", "", lambda text: got.append(text), local=True)
draw()
keys = [w for _, w in m.taps if w[0] == "kb"]
check(f"the keyboard: every key tappable ({len(keys)})", len(keys) == 40 + len(g.KEY_BOTTOM))
x, y = spot(lambda w: w == ("kb", 1, 0))
names, _ = tap(x, y)
check(f"a tap on q: q typed ({names}, {m.kb['text']!r})", names == ["a"] and m.kb["text"] == "q")
check(f"the web page sees the box ({m.web_state()['kb']})", m.web_state()["kb"] == {"title": "Search", "text": "q",
                                                                                      "limit": 60})
_, out = touch("type", text="dreamcast\n games", enter=False)
check(f"typed on the web page: in the box, as it is (no new lines) ({out}, {m.kb['text']!r})", out == {"ok": True}
      and m.kb["text"] == "dreamcast games" and m.kb["remote"] is True)
_, out = touch("type", text="x" * 500, enter=False)
check(f"...no more than the box takes ({len(m.kb['text'])})", len(m.kb["text"]) == 60)
_, out = touch("type", text="sega", enter=True)
check(f"...and Done: it's sent ({got}, {m.view})", got == ["sega"] and m.view != "keys")
_, out = touch("type", text="more", enter=True)
check(f"no box on the screen: says so ({out})", "error" in out)

# ---- a menu over a game, and the help pages ----------------------------------------------------------------------
m.tab = music; m.load_tab(m.tab); m.view = "list"
draw()
m.press("x")
draw()
names, _ = tap(320, 200)
check(f"Controls (X): a tap anywhere closes it, as any button does ({names}, {m.view})", names == ["a"]
      and m.view == "list")
m.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": None}
m.view = "gamemenu"
draw()
gm = [w for _, w in m.taps if w[:3] == ("sel", "dict", "game_menu")]
check(f"a game's menu: each row tappable ({len(gm)})", len(gm) == len(g.GAME_MENU))
x, y = spot(lambda w: w == ("sel", "dict", "game_menu", 2))
names, _ = m.web_touch({"cmd": "tap", "x": x / m.fb.w, "y": y / m.fb.h})
check(f"...a row tapped: picked, and A ({m.game_menu['sel']}, {names})", m.game_menu["sel"] == 2 and names == ["a"])
m.view, m.game_menu = "list", None
draw()
# (with a game on: Load state, which loses where you are, asks first, as A once does on the Pi)
import types
m.game = types.SimpleNamespace(disc=(0, 1), slow=False, game={"system": "gba", "title": "A game", "src": "/a.gba"},
                               ask=lambda *a, **k: (None, ""), cheevos=None)
m.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": None}
m.view = "gamemenu"
draw()
load = [r[0] for r in m.game_menu_items()].index("load")
x, y = spot(lambda w: w == ("sel", "dict", "game_menu", load))
names, _ = tap(x, y)
check(f"...a game's Load state, tapped once: it asks first ({names}, {m.game_menu['confirm'][0]}, {m.view})",
      names == ["a"] and m.game_menu["confirm"][0] == "load" and m.view == "gamemenu")
names, _ = m.web_touch({"cmd": "tap", "x": x / m.fb.w, "y": y / m.fb.h})
check(f"...and a second tap is the A that says yes ({names}, still asking: {m.game_menu['confirm'][0]})",
      names == ["a"] and m.game_menu["confirm"][0] == "load")
m.view, m.game_menu, m.game = "list", None, None
draw()

# ---- Settings > Bluetooth: a device tapped, picked and A in one tap (Connect, Pair); Disconnect still asks ----------
class FakeBT:
    def __init__(self):
        self.did = []
        self.devs = [{"addr": "AA", "name": "Pad", "paired": True, "connected": False, "kind": "controller", "what": "Controller"},
                     {"addr": "CC", "name": "Speaker", "paired": True, "connected": True, "kind": "speaker", "what": "Speaker"},
                     {"addr": "BB", "name": "Phones", "paired": False, "connected": False, "kind": "headphones",
                      "what": "Headphones"}]

    def snapshot(self):
        return {"there": True, "on": True, "why": "", "devices": self.devs, "busy": None, "busy_addr": None,
                "code": None, "looking": False, "status": ""}

    def summary(self):
        return self.snapshot()

    def watch(self, *a):
        pass

    def look(self):
        return None

    def __getattr__(self, name):                       # connect, pair, disconnect...: noted
        return lambda *a: self.did.append((name,) + a)


real_bt = m.bt
m.bt = FakeBT()
m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.view = "list"
m.bt_open()
draw()
bts = [w for _, w in m.taps if w[0] == "bt"]
rows = m.bt_rows()
check(f"Settings > Bluetooth: the switch and each device tappable ({len(bts)} of {len(rows)} rows)", len(bts) >= 4)
k_pad = next(k for k, r in enumerate(rows) if r[0] == "bt_dev" and r[2]["addr"] == "AA")
x, y = spot(lambda w: w == ("bt", k_pad))
names, _ = tap(x, y)
check(f"...a device of yours, tapped once: picked and connected ({names}, {m.bt.did})", names == ["a"]
      and ("connect", "AA") in m.bt.did and m.bt_pick == "AA")
k_new = next(k for k, r in enumerate(rows) if r[0] == "bt_new")
x, y = spot(lambda w: w == ("bt", k_new))
names, _ = tap(x, y)
check(f"...one nearby, tapped once: paired ({m.bt.did[-1]})", names == ["a"] and m.bt.did[-1] == ("pair", "BB"))
k_on = next(k for k, r in enumerate(rows) if r[0] == "bt_dev" and r[2]["addr"] == "CC")
x, y = spot(lambda w: w == ("bt", k_on))
n = len(m.bt.did)
tap(x, y)
check(f"...a connected one, tapped once: it asks first ({m.bt.did[n:]}, {m.confirm[0]})", m.bt.did[n:] == []
      and m.confirm[0] == "bt_dis:CC")
tap(x, y)
check(f"...tapped again: disconnected ({m.bt.did[n:]})", m.bt.did[n:] == [("disconnect", "CC")])
m.bt_close()
m.bt = real_bt
m.view = "list"
draw()

# ---- a video: a tap pauses, ▲▼ the volume -----------------------------------------------------------------------
class Proc:
    def poll(self): return None
    def kill(self): pass
    def wait(self, timeout=None): return 0


cmds = []
m.proc, m.kind, m.cur = Proc(), "video", {"title": "Steamboat", "key": "v", "src": "/v.mp4", "kind": "video"}
real_cmd = m.cmd
m.cmd = lambda c: cmds.append(c)
vol = m.volume
names, _ = touch("tap", x=0.5, y=0.5)
check(f"a video on: a tap pauses it ({names}, {cmds[:1]})", names == ["a"] and m.paused and cmds[0] == "pause")
names, _ = touch("swipe", x=0.0, y=-0.4)
check(f"...a finger up: louder ({names}, {vol} -> {m.volume})", names and set(names) == {"up"})
names, _ = touch("swipe", x=0.4, y=0.0)
check(f"...a finger to the right: on 10 seconds ({names})", names == ["right"])
m.cmd = real_cmd
m.proc, m.kind, m.cur, m.paused = None, None, None, False
draw()

# ---- a page in Web: its links, and a finger moving it -----------------------------------------------------------
LINKS = "".join(f"<p>Paragraph {k}. Some words to fill the line up a little more. <a href='/p{k}.html'>Link {k}</a></p>"
                for k in range(40))
PAGES = {"/": f"<html><head><title>Front</title></head><body><h1>Front page</h1>{LINKS}</body></html>"}


class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = PAGES.get(self.path, f"<html><head><title>Page {self.path}</title></head><body><p>Hi</p></body></html>")
        body = body.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
wi = m.tab_index("www")
m.tab, m.view = wi, "list"; m.load_tab(wi)
m.www_go(BASE + "/")


def settle(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.03)
    return False


check("a page in Web", settle(lambda: m.www_on_page() and m.www_wait is None and WW.clean_title(m.www["page"]) == "Front"))
draw()
links = [w for _, w in m.taps if w[0] == "www"]
check(f"...its links on the screen tappable ({len(links)})", len(links) >= 4)
y0 = m.www["y"]
touch("swipe", x=0, y=-0.25)
check(f"a finger up a quarter of the screen: the page moves with it ({y0} -> {m.www['y']})",
      abs(m.www["y"] - (y0 + 0.25 * m.fb.h)) <= 1)
touch("scroll", y=2)
check(f"the wheel, 2 notches: two rows' worth on ({m.www['y']})", abs(m.www["y"] - (y0 + 0.25 * m.fb.h + 2 * m.ROW_H)) <= 1)
draw()
t = next(w for _, w in m.taps if w[0] == "www")
x, y = spot(lambda w: w == t)
want = m.www["page"].links[m.www["targets"][t[1]]["ref"][1]]
names, _ = tap(x, y)
check(f"a link tapped: opened ({names}, {want})", names == ["a"]
      and settle(lambda: m.www_on_page() and m.www_wait is None and m.www["page"].url == want))
srv.shutdown()

# ---- Apps: its buttons along the bottom, though they're drawn once and kept ------------------------------
sim = next((i for i, t in enumerate(g.LIBRARY) if t.get("sim") == "life"), None)
if sim is not None:
    m.tab, m.view = sim, "list"; m.load_tab(sim)
    for _ in range(3):
        draw()
    feet = [w for _, w in m.taps if w[0] == "keys"]
    check(f"a sim, its third frame: its buttons still tappable ({feet[:4]})", ("keys", "a") in feet)
    check("...and the tabs", any(w[0] == "tab" for _, w in m.taps))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
