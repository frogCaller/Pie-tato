"""Controllers, the learn wizard, SELECT+START, hotplug and the web page's control server,
with fake input devices that use the real evdev codes."""
import io, os, sys, time, shutil, json, threading, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t30"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Videos")
open(S + "/home/u/Videos/clip.mp4", "wb").write(b"x" * 100)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')   # (this one starts in the terminal)
g.home_dir = lambda: S + "/home/u"
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", S + "/home/u") for x in t[key]]
import gk_static; gk_static.use_home(g, S + "/home/u")
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
g.LEARN_SKIP = 0.4
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class FakeDev:
    """An input device: select() sees it through a pipe; read() hands out queued events."""
    n = 0

    def __init__(self, name, keys, absaxes=None, vendor=0x45e, product=0x28e):
        FakeDev.n += 1
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys, self.absaxes = name, keys, absaxes or {}
        self.info = Info(vendor, product)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        caps = {e.EV_KEY: list(self.keys)} if self.keys else {}
        if self.absaxes:
            caps[e.EV_ABS] = [(c, a) if absinfo else c for c, a in self.absaxes.items()]
        return caps

    def absinfo(self, code):
        return self.absaxes[code]

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        if self.gone:
            raise OSError(19, "No such device")
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        self.closed = True


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


xbox = FakeDev("Microsoft X-Box 360 pad",
               [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT,
                e.BTN_START, e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
               {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_Z: ai(0, 255, 0),
                e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
snes = FakeDev("USB Gamepad ",
               [e.BTN_TRIGGER, e.BTN_THUMB, e.BTN_THUMB2, e.BTN_TOP, e.BTN_TOP2, e.BTN_PINKIE,
                e.BTN_BASE, e.BTN_BASE2, e.BTN_BASE3, e.BTN_BASE4],
               {e.ABS_X: ai(0, 255, 127), e.ABS_Y: ai(0, 255, 127)}, vendor=0x81f, product=0xe401)
kbd = FakeDev("BBQ20 keyboard", [e.KEY_A, e.KEY_Z, e.KEY_ENTER, e.KEY_Q])
touch = FakeDev("Sony Interactive Entertainment Wireless Controller Touchpad", [e.BTN_LEFT, e.BTN_TOUCH])
motion = FakeDev("Sony Interactive Entertainment Wireless Controller Motion Sensors", [],
                 {e.ABS_X: ai(-32768, 32767, 0)})
ours = FakeDev("pitato", [e.KEY_ENTER, e.KEY_UP])
plugged = [snes, kbd, touch, motion, ours]
devs = {d.path: d for d in [xbox, snes, kbd, touch, motion, ours]}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)

# ---- what kind of device -------------------------------------------------------------
check("Xbox pad is a gamepad", g.pad_kind(xbox) == "gamepad")
check("SNES-style pad is a joystick", g.pad_kind(snes) == "joystick")
check("keyboard, touchpad, motion sensors and our own keys are not pads",
      [g.pad_kind(d) for d in (kbd, touch, motion, ours)] == [None] * 4)
check("ident has vendor:product:name", g.pad_ident(snes) == "081f:e401:USB Gamepad ")

# ---- default buttons -----------------------------------------------------------------
p = g.Pad(snes, "joystick")
check("SNES pad: no HOME", p.home is False)
check("SNES: button 2 is A, 3 is B, 1 is X, 4 is Y", [p.translate(Ev(e.EV_KEY, c, 1)) for c in
      (e.BTN_THUMB, e.BTN_THUMB2, e.BTN_TRIGGER, e.BTN_TOP)] == [[("a", True)], [("b", True)], [("x", True)], [("y", True)]])
check("SNES: select/start", p.translate(Ev(e.EV_KEY, e.BTN_BASE3, 1)) == [("select", True)]
      and p.translate(Ev(e.EV_KEY, e.BTN_BASE4, 1)) == [("start", True)])
check("SNES d-pad on ABS_X: 0 -> left", p.translate(Ev(e.EV_ABS, e.ABS_X, 0)) == [("left", True)])
check("ABS_X 127 -> left up", p.translate(Ev(e.EV_ABS, e.ABS_X, 127)) == [("left", False)])
check("ABS_X 255 -> right", p.translate(Ev(e.EV_ABS, e.ABS_X, 255)) == [("right", True)])
check("ABS_X 0 straight from right -> right up, left down",
      p.translate(Ev(e.EV_ABS, e.ABS_X, 0)) == [("right", False), ("left", True)])
check("key repeat (value 2) ignored", p.translate(Ev(e.EV_KEY, e.BTN_THUMB, 2)) == [])
x = g.Pad(xbox, "gamepad")
check("Xbox: HOME present", x.home is True)
check("Xbox hat up", x.translate(Ev(e.EV_ABS, e.ABS_HAT0Y, -1)) == [("up", True)])
check("Xbox trigger axis not mapped", x.translate(Ev(e.EV_ABS, e.ABS_Z, 255)) == [])
check("Xbox BTN_MODE is home", x.translate(Ev(e.EV_KEY, e.BTN_MODE, 1)) == [("home", True)])

# ---- learned buttons on top ----------------------------------------------------------
learned = {"keys": {str(e.BTN_THUMB2): "a", str(e.BTN_THUMB): "b", str(e.BTN_BASE): "home"},
           "axes": {str(e.ABS_Y): {"1": "up", "-1": "down"}}}
p.apply(learned)
check("learned: button 3 is A now, 2 is B", p.translate(Ev(e.EV_KEY, e.BTN_THUMB2, 1)) == [("a", True)]
      and p.translate(Ev(e.EV_KEY, e.BTN_THUMB, 1)) == [("b", True)])
check("learned: X still standard", p.translate(Ev(e.EV_KEY, e.BTN_TRIGGER, 1)) == [("x", True)])
check("learned: BTN_BASE was L, is HOME now (so the pad has HOME)", p.home and
      p.translate(Ev(e.EV_KEY, e.BTN_BASE, 1)) == [("home", True)])
check("learned: Y axis flipped", p.translate(Ev(e.EV_ABS, e.ABS_Y, 255)) == [("up", True)])
check("learned: X axis kept", p.translate(Ev(e.EV_ABS, e.ABS_X, 0)) == [("left", True)])
p.apply({"keys": {"junk": "a"}})
check("bad learned data -> standard buttons", not p.learned and p.keys.get(e.BTN_THUMB) == "a")

# ---- the main loop ---------------------------------------------------------------------
class UI:
    def __init__(self):
        self.out = []

    def write(self, t, c, v):
        self.out.append((c, v))

    def syn(self):
        pass


class Proc:
    stdin = io.StringIO()

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


spawned = []


def fake_spawn(self, args, target):
    spawned.append((args, target)); self.proc = Proc(); self.started = time.monotonic() - 5


g.Media.spawn = fake_spawn


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    last = None
    frames = 0

    def show(self, img):
        FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
ui = UI()
m = g.Media()
control = g.Control()
server = g.serve_control(m, control, port=0)
port = server.server_address[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(ui, m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.3)
check("pads found at start: only the SNES pad", list(m.pads.by_path) == [snes.path])
check("keyboard left to the text boxes", m.keyreader.exclude == {snes.path})


def wait(sec=0.12):
    time.sleep(sec)


def keys_typed():
    out = list(ui.out); ui.out.clear(); return out


# terminal: A -> Enter
snes.send((e.EV_KEY, e.BTN_THUMB, 1)); wait(); snes.send((e.EV_KEY, e.BTN_THUMB, 0)); wait()
check("terminal: A types Enter", keys_typed() == [(e.KEY_ENTER, 1), (e.KEY_ENTER, 0)])
# a quick SELECT tap: Q, after it's let go
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.05)
check("SELECT held a moment: nothing yet", keys_typed() == [])
snes.send((e.EV_KEY, e.BTN_BASE3, 0)); wait()
check("SELECT tap: Q down and up", keys_typed() == [(e.KEY_Q, 1), (e.KEY_Q, 0)])
# SELECT held past the wait: Q goes down then
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.45)
check("SELECT held: Q down after the wait", keys_typed() == [(e.KEY_Q, 1)])
snes.send((e.EV_KEY, e.BTN_BASE3, 0)); wait()
check("...and up when let go", keys_typed() == [(e.KEY_Q, 0)])
# SELECT + START: HOME
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.05); snes.send((e.EV_KEY, e.BTN_BASE4, 1)); wait(0.6)
typed = keys_typed()
check("SELECT+START: media mode, nothing typed", m.active and typed == [])
snes.send((e.EV_KEY, e.BTN_BASE3, 0), (e.EV_KEY, e.BTN_BASE4, 0)); wait()
check("releases swallowed, still in media mode on Home", m.active and m.view == "home" and keys_typed() == [])
# d-pad on the home screen
sel0 = m.home_sel
snes.send((e.EV_ABS, e.ABS_X, 255)); wait(); snes.send((e.EV_ABS, e.ABS_X, 127)); wait()
check("d-pad right moves the icon", m.home_sel == (sel0 + 1) % len(m.home_apps()))
# B on the home screen: nothing; Y: the terminal (its Ctrl+C there not sent as it's let go)
snes.send((e.EV_KEY, e.BTN_THUMB2, 1)); wait(); snes.send((e.EV_KEY, e.BTN_THUMB2, 0)); wait()
check("B on the home screen: still there, nothing typed", m.active and m.view == "home" and keys_typed() == [])
snes.send((e.EV_KEY, e.BTN_TOP, 1)); wait(); snes.send((e.EV_KEY, e.BTN_TOP, 0)); wait()
check("Y on the home screen: the terminal, nothing typed", not m.active and keys_typed() == [])
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.05); snes.send((e.EV_KEY, e.BTN_BASE4, 1)); wait(0.6)
snes.send((e.EV_KEY, e.BTN_BASE3, 0), (e.EV_KEY, e.BTN_BASE4, 0)); wait()
check("...and back (SELECT+START): the home screen", m.active and m.view == "home" and keys_typed() == [])

# hotplug: the Xbox pad
plugged.append(xbox); wait(0.3)
check("Xbox pad found when plugged in", xbox.path in m.pads.by_path and m.msg and "connected" in m.msg)
check("the web state lists both", [c["name"] for c in m.web_state()["controllers"]] ==
      ["USB Gamepad ", "Microsoft X-Box 360 pad"])
presses = []
orig_press = m.press
m.press = lambda name, repeat=False: (presses.append(name), orig_press(name, repeat))[1]
xbox.send((e.EV_KEY, e.BTN_SELECT, 1)); wait(0.08)
check("Xbox SELECT goes straight through (it has HOME)", presses == ["select"])
xbox.send((e.EV_KEY, e.BTN_SELECT, 0)); wait()
# hold down on the Xbox, then unplug it: the hold must stop
m.tab = m.tab_index("settings"); m.view = "list"; m.set_page = "root"; m.set_sel = 0; m.load_tab(m.tab); wait()
xbox.send((e.EV_ABS, e.ABS_HAT0Y, 1)); wait(0.6)
moved = m.set_sel
check("holding down repeats in a list", moved >= 2)
xbox.gone = True; plugged.remove(xbox); xbox.send(); wait(0.3)
after = m.set_sel; wait(0.3)
check("unplugged: dropped and the hold stopped", xbox.path not in m.pads.by_path and m.set_sel == after)

# ---- learn the SNES pad ----------------------------------------------------------------
m.set_sel = [k for k, _, _ in m.settings_rows()].index("pad")
r = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"http://127.0.0.1:{port}/learn", data=b"{}", headers={"Content-Type": "application/json"}), timeout=5).read())
check("web: learn starts", r == {"ok": True} and m.view == "learn")
st = m.learn_status()
check("asks for A on the controller to set up", st["text"].startswith("Press A, the OK button on the controller"))
snes.send((e.EV_KEY, e.BTN_THUMB2, 1)); wait(); snes.send((e.EV_KEY, e.BTN_THUMB2, 0)); wait(0.3)
check("A taken, asks for B", m.learn["keys"] == {e.BTN_THUMB2: "a"} and m.learn_status()["text"] == "Press B, the back button")
snes.send((e.EV_KEY, e.BTN_THUMB2, 1)); wait()
check("the same button again: told so", "already" in m.learn["said"])
snes.send((e.EV_KEY, e.BTN_THUMB2, 0)); snes.send((e.EV_KEY, e.BTN_THUMB, 1)); wait(0.3)
snes.send((e.EV_KEY, e.BTN_THUMB, 0))
# up: the Y axis pushed to 255 (an upside-down pad), back to rest, then down = 0
for val, name in ((255, "up"), (0, "down")):
    snes.send((e.EV_ABS, e.ABS_Y, val)); wait(0.3); snes.send((e.EV_ABS, e.ABS_Y, 127)); wait(0.1)
for val in (0, 255):
    snes.send((e.EV_ABS, e.ABS_X, val)); wait(0.3); snes.send((e.EV_ABS, e.ABS_X, 127)); wait(0.1)
check("d-pad learned", m.learn and m.learn["axes"] == {e.ABS_Y: {1: "up", -1: "down"}, e.ABS_X: {-1: "left", 1: "right"}})
for code in (e.BTN_TRIGGER, e.BTN_TOP, e.BTN_TOP2, e.BTN_PINKIE, e.BTN_BASE3, e.BTN_BASE4):
    snes.send((e.EV_KEY, code, 1)); wait(0.3); snes.send((e.EV_KEY, code, 0)); wait(0.05)
check("all but HOME learned, on HOME now", m.learn and m.learn["step"] == len(g.LEARN_STEPS) - 1)
learn_shot = FB.last.copy()
wait(0.8)   # HOME is skipped (no such button)
check("HOME skipped, saved", m.learn and m.learn.get("done") and "home" in m.learn["skipped"])
saved = json.load(open(g.PADS_FILE))
check("pads.json has the model", list(saved) == ["081f:e401:USB Gamepad "]
      and saved["081f:e401:USB Gamepad "]["keys"][str(e.BTN_THUMB2)] == "a")
wait(2.8)
check("back on Settings afterwards", m.learn is None and m.view == "list" and m.tab_type() == "settings")
pad = m.pads.by_path[snes.path]
check("the pad uses them now", pad.learned and pad.keys[e.BTN_THUMB2] == "a" and pad.keys[e.BTN_THUMB] == "b")
check("the web state says so", m.web_state()["controllers"][0]["learned"] is True)
check("settings row shows the pad", m.pad_summary() == "USB Gamepad ")
# up is now Y=255
sel0 = m.set_sel
snes.send((e.EV_ABS, e.ABS_Y, 255)); wait(); snes.send((e.EV_ABS, e.ABS_Y, 127)); wait()
check("learned up moves up", m.set_sel == (sel0 - 1) % len(m.settings_rows()))
# X on the Controller row resets
m.set_sel = [k for k, _, _ in m.settings_rows()].index("pad")
snes.send((e.EV_KEY, e.BTN_TRIGGER, 1)); wait(); snes.send((e.EV_KEY, e.BTN_TRIGGER, 0)); wait()
check("X resets to the standard buttons", not pad.learned and json.load(open(g.PADS_FILE)) == {})

# learning cancelled by another controller's B
plugged.append(xbox); xbox.gone = False; xbox.q = []; wait(0.3)
m.start_learn(); wait()
xbox.send((e.EV_KEY, e.BTN_EAST, 1)); wait()
check("the first press on any controller picks it (the Xbox's B, as its A)",
      m.learn is not None and m.learn["pad"] is not None)
m.cancel_learn(""); xbox.send((e.EV_KEY, e.BTN_EAST, 0)); wait()
m.start_learn(); wait()
snes.send((e.EV_KEY, e.BTN_THUMB, 1)); wait(); snes.send((e.EV_KEY, e.BTN_THUMB, 0)); wait(0.3)
xbox.send((e.EV_KEY, e.BTN_EAST, 1)); wait()
check("then B on the other one stops it", m.learn is None and m.msg == "Controller set-up stopped")
xbox.send((e.EV_KEY, e.BTN_EAST, 0)); wait()

# ---- the web page's requests -----------------------------------------------------------
def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.read(), r.headers.get("Content-Type")


body, ctype = get("/state")
st = json.loads(body)
check("state: media mode, Settings", st["mode"] == "media" and st["where"] == "Settings" and st["size"] == [1920, 1080])
body, ctype = get("/screen")
check("screen: a PNG of the menus", ctype == "image/png" and body[:4] == b"\x89PNG")
again, _ = get("/screen")
check("same frame: same bytes (cached)", again == body)
r = post("/open", {"app": "Weather"}); wait()
check("open Weather", r == {"ok": True} and m.tab_type() == "weather" and m.view == "list")
r = post("/press", {"button": "b"}); wait()
check("press B: home", r == {"ok": True} and m.view == "home")
r = post("/press", {"button": "nope"})
check("unknown button refused", "error" in r)
cat = json.loads(get("/catalog")[0])
check("catalog: apps, cartoons, films, radio (news and sports are Plex's)", len(cat["apps"]) >= 10
      and len(cat["cartoons"]) == 13 and len(cat["films"]) == 5 and "news" not in cat and "sports" not in cat
      and cat["radio"]["stations"])
toon = cat["cartoons"][0]["items"][0]
g.ia_best = lambda ident, name, timeout=8: f"https://archive.org/download/{ident}/{name}"
r = post("/play", {"items": [{"src": it[2], "title": it[0]} for it in cat["cartoons"][0]["items"][:3]],
                   "index": 1, "where": "Cartoons"})
check("play a cartoon from the list", r.get("ok") and spawned and "archive.org" in spawned[-1][1]
      and m.kind == "video" and len(m.queue) == 3 and m.qi == 1)
args = spawned[-1][0]
check("1080p screen: dsize Fit and the HDMI sound choice", "dsize=1920:1080:0,scale=0:0" in args and "-ao" in args)
st = json.loads(get("/state")[0])
check("state: playing", st["playing"]["title"] == cat["cartoons"][0]["items"][1][0] and st["video"] is True)
r = post("/player", {"do": "pause"})
check("pause", r.get("ok") and m.paused)
r = post("/player", {"do": "stop"}); wait()
check("stop", r.get("ok") and not m.proc)
r = post("/play", {"items": [{"src": "file:///etc/passwd"}, {"src": "/etc/passwd"}]})
check("files outside home refused", "error" in r)
r = post("/show", {"path": S + "/home/u/Videos/clip.mp4"}); wait()
check("show a video from Files", r.get("ok") and spawned[-1][1].endswith("clip.mp4"))
post("/player", {"do": "stop"})
r = post("/show", {"path": "/etc/passwd"})
check("show outside home refused", "error" in r)
r = post("/mode", {"to": "terminal"}); wait()
check("mode terminal", r == {"ok": True} and not m.active)
st = json.loads(get("/state")[0])
check("state: terminal", st["mode"] == "terminal" and st["frame"] == -1)
try:
    get("/screen"); code = 200
except urllib.error.HTTPError as ex:
    code = ex.code
check("the terminal isn't sent to the web page", code == 403)
keys_typed()
r = post("/press", {"button": "down"}); wait()
check("web presses don't type in the terminal", "error" in r and keys_typed() == [])
r = post("/press", {"button": "down", "repeat": True}); wait()
check("...held ones either", "error" in r and keys_typed() == [])
r = post("/press", {"button": "home"}); wait(0.4)
check("Home from the web opens media mode", r == {"ok": True} and m.active)
post("/mode", {"to": "terminal"}); wait()
r = post("/open", {"home": True}); wait()
check("open Home from the terminal", r == {"ok": True} and m.active and m.view == "home")
req = urllib.request.Request(f"http://127.0.0.1:{port}/press", data=b"button=a",
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
try:
    urllib.request.urlopen(req, timeout=5); code = 200
except urllib.error.HTTPError as ex:
    code = ex.code
check("form posts refused", code == 415)
icon, ctype = get("/icon?name=Weather&size=64")
check("icon PNG", ctype == "image/png" and icon[:4] == b"\x89PNG")
try:
    get("/icon?name=Nope"); code = 200
except urllib.error.HTTPError as ex:
    code = ex.code
check("unknown icon: 404, nothing kept", code == 404 and all(k[0] in g.HOME_ICONS for k in m.web_icons))

# ---- the web page keeps to your home folder ------------------------------------------
os.makedirs(S + "/home/u/.secret", exist_ok=True)
open(S + "/home/u/homeassistant.txt", "w").write("token = abc")
open(S + "/home/u/.hidden.txt", "w").write("x")
open(S + "/home/u/notes.txt", "w").write("hello")
m.cwd = "/etc"                                   # someone at the Pi left Files there
r = post("/open", {"app": "Files"}); wait()
names = [it["title"] for it in m.tab_items()]
check(f"web: Files starts at home, no '..', hidden or private files: {names}",
      m.cwd == S + "/home/u" and ".." not in names and ".hidden.txt" not in names and ".secret" not in names
      and "homeassistant.txt" not in names and "notes.txt" in names)
post("/press", {"button": "y"}); wait()
check("web: Y doesn't show hidden files", not m.show_hidden and "hidden" in (m.msg or ""))
before = m.view
m.open_item([g.item("/etc/passwd", "passwd", "text", "/etc/passwd")], 0)
check("web: a file outside home won't open", m.view == before and "can't open" in (m.msg or ""))
r = post("/show", {"path": S + "/home/u/homeassistant.txt"})
check("web: show refuses the private file", "error" in r)
r = post("/show", {"path": S + "/home/u/.hidden.txt"})
check("web: show refuses hidden files", "error" in r)
r = post("/show", {"path": S + "/home/u/notes.txt"}); wait()
check("web: show opens a text file", r.get("ok") and m.view == "text")
post("/press", {"button": "b"}); wait()
snes.send((e.EV_KEY, e.BTN_THUMB, 1)); wait(); snes.send((e.EV_KEY, e.BTN_THUMB, 0)); wait()
check("a controller press lifts the guard", m.web_guard is False)
post("/open", {"home": True}); wait()

# ---- play: the row asked for ----------------------------------------------------------
r = post("/play", {"items": [{"src": "rtsp://cam/1", "title": "Cam"},
                             {"src": "http://radio.example/a.mp3", "title": "A", "kind": "radio"},
                             {"src": "http://radio.example/b.mp3", "title": "B", "kind": "radio"}],
                   "index": 1, "where": "Radio"})
check("play: the row asked for, even with one dropped", r.get("title") == "A" and m.cur["title"] == "A")
post("/player", {"do": "stop"}); wait()
r = post("/play", {"items": [{"src": "rtsp://cam/1"}, {"src": "http://radio.example/a.mp3", "kind": "radio"}], "index": 0})
check("play: a row that can't be played is refused", "error" in r and not m.proc)

# ---- SELECT + START held while set-up starts: nothing stays down after -----------------
post("/mode", {"to": "terminal"}); wait(); keys_typed()
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.05); snes.send((e.EV_KEY, e.BTN_BASE4, 1)); wait(0.6)
check("chord: media mode", m.active)
post("/learn", {}); wait()
snes.send((e.EV_KEY, e.BTN_BASE3, 0), (e.EV_KEY, e.BTN_BASE4, 0)); wait()
post("/learn", {"stop": True}); wait()
post("/mode", {"to": "terminal"}); wait(); keys_typed()
snes.send((e.EV_KEY, e.BTN_BASE3, 1)); wait(0.5); snes.send((e.EV_KEY, e.BTN_BASE3, 0)); wait(0.3)
check("after set-up stopped mid-chord, SELECT still lets go of Q", keys_typed() == [(e.KEY_Q, 1), (e.KEY_Q, 0)])

# ---- the control server's key ----------------------------------------------------------
g.CONTROL_KEY = S + "/run/pitato/control-key"
key = g.control_key()
st_ = os.stat(g.CONTROL_KEY)
check("key file: only its owner can read it", open(g.CONTROL_KEY).read() == key and st_.st_mode & 0o777 == 0o600)
server2 = g.serve_control(m, control, port=0, key=key)
port2 = server2.server_address[1]
try:
    urllib.request.urlopen(f"http://127.0.0.1:{port2}/state", timeout=5); code = 200
except urllib.error.HTTPError as ex:
    code = ex.code
check("with a key: turned away without it", code == 401)
req = urllib.request.Request(f"http://127.0.0.1:{port2}/state", headers={"X-Pitato-Key": key})
check("...answered with it", json.loads(urllib.request.urlopen(req, timeout=5).read())["mode"] in ("media", "terminal"))
server2.shutdown()
m2 = g.Media()
m2.learn = {"step": len(g.LEARN_STEPS), "pad": None, "done": None}
check("learn_status just past the last step: no error", m2.learn_status()["done"] is True)
done.set(); th.join(3)
check("loop ended cleanly, pads closed", not th.is_alive() and not errors and snes.closed)
learn_shot.save(SP + "/out/learn.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
