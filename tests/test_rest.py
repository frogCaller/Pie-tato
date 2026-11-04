"""Settings > Battery saver, and the screen resting. Whether it's on its battery: a GPi Case (the GPi Case 2 not on its
dock's TV), a laptop's battery discharging (not a controller's, not with the charger in). With the saver on, after a
while with nothing happening: the screen black, then its picture off; nothing drawn; the page's polling stopped;
Wi-Fi's power saving on (and back as it was after); the main loop once a second. A press wakes it and does nothing
else; then presses work again. Not while there's something to watch (a video, a game, the camera, the keyboard, a
slideshow, the web page watching); music keeps playing while it rests; reading waits longer. The web page watching
wakes it from its own thread. Off: never. Settings on the Pi and the web page. Then the real main loop (app.py) with
a pretend controller and the control server: a press (HOME too) only wakes it, the web page's press too, a touch on
the web page's screen only wakes it, anything else done there wakes it and is done, and something plugged in wakes it.
Leaving for the terminal, and the case's power switch, turn the screen back on first."""
import json, os, shutil, sys, threading, time, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_rest"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
open(f"{H}/Music/song.mp3", "wb").write(b"x")
os.environ["PATH"] = SP + "/power/bin:" + os.environ["PATH"]
os.environ["FAKE_IW_STATE"] = S + "/iw_state"
os.environ["FAKE_IW_LOG"] = S + "/iw.log"
sys.path.insert(0, TESTS); sys.path.insert(0, SP)
import pietato_all as g
import pitato.power as P
import pitato.screens.rest as R
from evdev import ecodes as e, AbsInfo

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.PLEX_FILE = S + "/plex.json"; g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, H)
real_run = g.subprocess.run
g.subprocess.run = lambda cmd, *a, **k: (real_run(cmd, *a, **k) if isinstance(cmd, (list, tuple)) and cmd
                                         and os.path.basename(str(cmd[0])) == "iw"   # (the pretend iw: as it is)
                                         else type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})())
g.SCAN_EVERY = 0.05
R.wifi_dev = lambda: "wlan0"
R.REST_AFTER, R.REST_READING, R.REST_WATCHED, R.BATTERY_LOOK = 0.6, 1.6, 1.0, 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- on its battery: what says so -------------------------------------------------------------------------------------
PS = S + "/power_supply"


def supply(name, **files):
    os.makedirs(f"{PS}/{name}", exist_ok=True)
    for k, v in files.items():
        open(f"{PS}/{name}/{k}", "w").write(v + "\n")


P.POWER_SUPPLY = PS
check("no battery: not on one", not P.battery_discharging())
supply("hid-controller-battery", type="Battery", scope="Device", status="Discharging")
check("...a controller's battery doesn't count", not P.battery_discharging())
supply("BAT0", type="Battery", status="Discharging")
supply("AC", type="Mains", online="0")
check("a laptop's battery, discharging, its charger out: on its battery", P.battery_discharging())
supply("AC", type="Mains", online="1")
check("...the charger in: not", not P.battery_discharging())
supply("AC", type="Mains", online="0")
supply("BAT0", type="Battery", status="Full")
check("...full: not", not P.battery_discharging())
shutil.rmtree(PS); os.makedirs(PS)


# ---- media mode, resting ----------------------------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    powered = []

    def show(self, img):
        FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames

    def power(self, on):
        FB.powered.append(on)
        return True

    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
check(f"media mode starting: the screen's picture on, whatever it was left as ({FB.powered})", FB.powered == [True])
FB.powered.clear()
from pitato.screen import sound_on_hdmi
check("HDMI's sound (a Pi's, a PC's), not the others'", sound_on_hdmi("vc4hdmi0") and sound_on_hdmi("vc4hdmi")
      and sound_on_hdmi("PCH/hdmi") and not sound_on_hdmi("Headphones") and not sound_on_hdmi("")
      and not sound_on_hdmi("bluetooth") and not sound_on_hdmi("Device"))
stops = []
for name in ("hass", "lights", "pihole"):
    obj = getattr(m, name)
    obj.stop = (lambda n: lambda: stops.append(n))(name)
m.fin_stop = lambda: stops.append("finance")


def iw_state():
    try:
        return open(S + "/iw_state").read().strip()
    except OSError:
        return "off"


def ticks(secs, flush=True):
    end = time.time() + secs
    while time.time() < end:
        m.tick()
        if flush:
            m.flush()
        time.sleep(0.05)


def settle(cond, secs=5, flush=True):
    end = time.time() + secs
    while time.time() < end:
        m.tick()
        if flush:
            m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


m.case = None
check(f"Battery saver: Auto, as it comes; on a Pi on mains power, off ({m.saver_value()}, {m.saver_why()!r})",
      m.setting("battery") == "Auto" and m.saver_value() == "Auto (off)" and not m.saver_on()
      and m.saver_why() == "Off: it isn't running on a battery")
ticks(1.2)
check("...nothing happening for a while: it doesn't rest", not m.resting and FB.powered == [])
m.case, m.battery_seen = "2w", None
check(f"in a GPi Case 2W: on ({m.saver_value()}, {m.saver_why()!r})", m.saver_on() and m.saver_value() == "Auto (on)"
      and m.saver_why() == "On: it's running on its battery")
m.case, m.dock_on_tv, m.battery_seen = "2", True, None
check(f"the GPi Case 2 on its dock's TV: off ({m.saver_value()}, {m.saver_why()!r})", not m.saver_on()
      and m.saver_why() == "Off: in its dock")
m.dock_on_tv, m.battery_seen = False, None
check("...out of its dock: on", m.saver_on())
m.case, m.dock_on_tv, m.battery_seen = None, None, None
supply("BAT0", type="Battery", status="Discharging")
check("a laptop on its battery: on", m.saver_on())
shutil.rmtree(PS); os.makedirs(PS); m.battery_seen = None

m.case = "2w"
m.stir()
m.go_home(); m.dirty = True; m.tick(); m.flush()
sel = m.home_sel
started = []
m.pihole.running = True                           # (Pi-hole's page was asking for its numbers)
m.pihole.start = lambda: started.append("pihole")
t0 = time.time()
ok = settle(lambda: m.resting, 5)
took = time.time() - t0
check(f"in the GPi Case, nothing happening for a while: it rests ({took:.1f} s)", ok and took >= R.REST_AFTER - 0.1)
px = FB.last.getextrema() if FB.last is not None else None
check(f"...the screen black ({px}), then its picture off ({FB.powered})", px == ((0, 0), (0, 0), (0, 0))
      and FB.powered == [False] and m.screen_off)
check(f"...Wi-Fi saving its power ({iw_state()}, {open(S + '/iw.log').read().split()})", iw_state() == "on"
      and m.rest_wifi == "wlan0")
check(f"...the page's polling stopped ({sorted(set(stops))})", {"hass", "lights", "pihole", "finance"} <= set(stops))
check(f"...the main loop once a second ({m.tick_limit()})", m.tick_limit() == R.REST_TICK)
n = FB.frames
m.dirty = True
m.toast("Something to say")
ticks(0.4)
check("...nothing drawn while it rests", FB.frames == n and m.resting)
m.press("down")
check(f"a press: awake, the picture on ({FB.powered}), Wi-Fi as it was ({iw_state()})", not m.resting
      and FB.powered == [False, True] and iw_state() == "off" and m.rest_wifi is None)
check(f"...and the press did nothing else ({m.home_sel} == {sel})", m.home_sel == sel)
check(f"...what was asking the network for news asks again, and only that ({started})", started == ["pihole"])
m.pihole.running = False
ticks(0.2)
check("...drawn again", FB.frames > n)
m.press("right")
check(f"the next press works ({m.home_sel})", m.home_sel != sel)

# things to watch: never rests; music: rests, and plays on
m.stir()


class Proc:
    def __init__(self): self.stdin = None
    def poll(self): return None


m.proc, m.kind = Proc(), "video"
m.view = "now"
ticks(1.2, flush=False)
check(f"a video playing: no rest ({m.proc_owns_screen()})", not m.resting)
m.proc, m.kind, m.view = None, None, "home"
real_game_tick, m.game_tick = m.game_tick, lambda now: None   # (a pretend game: nothing of its own to do)
m.game = object()
ticks(1.0, flush=False)
check("a game: no rest", not m.resting)
m.game = None
m.game_tick = real_game_tick
m.go_home(); m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab); m.set_setting("bot_mode", "work")
ticks(1.0, flush=False)
check(f"the Bot at work (your coding agent, acted out): no rest ({m.on_coder_page()})", m.on_coder_page()
      and not m.resting)
m.set_setting("bot_mode", "chat")
m.go_home()
m.open_keyboard("Type", "", lambda t: None)
ticks(1.0)
check("the keyboard: no rest", not m.resting and m.view == "keys")
m.close_keyboard(False)
ticks(0.3)
check("...closed: the wait starts again, not straight to rest", not m.resting)
check("...then rests, after a while", settle(lambda: m.resting, 5))
m.press("a")
m.remote_pad = object()                           # (the TV remote's number pad, with a keyboard typing into it)
m.stir()
ticks(1.0, flush=False)
check("the TV remote's number pad open: no rest", not m.resting)
m.remote_pad = None
m.web_watched = time.monotonic()
ticks(0.8)
check("the web page watching the screen: no rest", not m.resting)
m.web_watched = 0.0
m.go_home(); m.tab = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music"); m.load_tab(m.tab); m.view = "list"
m.stir()
music = Proc()
m.proc, m.kind, m.cur = music, "audio", g.item(f"{H}/Music/song.mp3", "song", "audio", f"{H}/Music/song.mp3")
m.view = "now"
check("music playing: it rests (the screen's not needed)", settle(lambda: m.resting, 5))
check("...and plays on", m.proc is music and m.kind == "audio")
m.press("b")
m.proc, m.kind, m.cur = None, None, None
m.view = "photo"
m.v = {"slideshow": False}
m.stir()
ticks(1.0, flush=False)
check(f"a photo open (you may be reading it): not after the usual while ({R.REST_AFTER} s)", not m.resting)
check(f"...but after a longer one ({R.REST_READING} s)", settle(lambda: m.resting, 5, flush=False))
m.press("b")
m.v = {"slideshow": True, "next_t": time.monotonic() + 100}
ticks(2.0, flush=False)
check("a slideshow: no rest", not m.resting)
m.view, m.v = "home", {}
m.go_home()

# the web page watching wakes it, from its own thread
check("resting again", settle(lambda: m.resting, 5))
threading.Thread(target=lambda: m.web_shot()).start()
time.sleep(0.2)
check("the web page asks for the screen's picture (its thread): asked to wake", m.rest_wake or not m.resting)
check("...the main loop wakes it", settle(lambda: not m.resting, 3) and FB.powered[-1] is True)

# the sound going to a TV on HDMI: the screen just black (powering it down would quiet the TV too)
m.press("a")
real_route, R.sound_route = R.sound_route, lambda choice: "vc4hdmi0"
n = len(FB.powered)
check("the sound on HDMI: it rests", settle(lambda: m.resting, 5))
check(f"...the screen black, its picture left on ({FB.powered[n:]})", FB.powered[n:] == [] and not m.screen_off
      and FB.last.getextrema() == ((0, 0), (0, 0), (0, 0)))
m.press("a")
check(f"...a press: awake, nothing to turn on ({FB.powered[n:]})", not m.resting and FB.powered[n:] == [])
R.sound_route = real_route

# Off: never
m.set_setting("battery", "Off")
ticks(1.5)
check(f"Battery saver Off: no rest ({m.saver_value()})", not m.resting and m.saver_value() == "Off")
m.set_setting("battery", "Auto")
check("resting", settle(lambda: m.resting, 5))
m.set_setting("battery", "Off")
check("...turned off while it rests: awake", settle(lambda: not m.resting, 3))
m.set_setting("battery", "On")
m.case = None
m.battery_seen = None
check(f"On: rests on mains power too ({m.saver_value()})", m.saver_value() == "On" and settle(lambda: m.resting, 5))
m.set_setting("battery", "Auto")
m.case = "2w"

# Settings, on the Pi and the web page
m.press("a")
m.go_home(); m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.set_page = "root"; m.view = "list"
rows = m.settings_rows()
keys = [r[0] for r in rows]
check(f"Settings: Battery saver, after Rotate screen's place ({keys})", "battery" in keys
      and dict((r[0], r[2]) for r in rows)["battery"] == ["Auto", "On", "Off"])
m.set_sel = keys.index("battery")
m.press("right")
check("...right: On", m.setting("battery") == "On")
m.press("right"); m.press("right")
check("...and round to Auto", m.setting("battery") == "Auto")
m.dirty = True; m.flush()
FB.last.save(S + "/settings_battery.png")
web = {r["key"]: r for s in m.web_settings()["sections"] for r in s["rows"]}
b = web.get("battery")
check(f"the web page: Battery saver in Screen, Auto, and why ({b and (b['value'], b['choices'], b.get('note'))})",
      b and b["value"] == "Auto" and b["choices"] == ["Auto", "On", "Off"] and b.get("note") == "On: it's running on its battery"
      and any(r["key"] == "battery" for s in m.web_settings()["sections"] if s["id"] == "screen" for r in s["rows"]))
out = m.web_settings_do({"cmd": "settings", "key": "battery", "value": "Off"})
check(f"...set there: Off ({out})", out == {"ok": True} and m.setting("battery") == "Off")
out = m.web_settings_do({"cmd": "settings", "key": "battery", "value": "Sometimes"})
check(f"...not one of its choices: refused ({out})", "error" in out and m.setting("battery") == "Off")
m.set_setting("battery", "Auto")

# the terminal, and the case's power switch: the screen on again first
m.go_home()
check("resting", settle(lambda: m.resting, 5))
m.leave()
check(f"to the terminal while it rests: the screen's picture on first ({FB.powered[-1]})", not m.resting
      and FB.powered[-1] is True and not m.active)
time.sleep(R.REST_AFTER + 0.3)                    # (a while in the terminal)
m.enter()
m.tick(); m.flush()
check("back to media mode after a while in the terminal: awake, not resting at once", m.active and not m.resting
      and FB.powered[-1] is True)
check("...rests again after a while there", settle(lambda: m.resting, 5))
m.press("a")
m.stop()


# ---- the main loop (app.py): buttons, the web page, something plugged in -----------------------------------------------
class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class FakeDev:
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
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        self.closed = True


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


FACE = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START, e.BTN_MODE]
STICKS = {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_HAT0X: ai(-1, 1, 0),
          e.ABS_HAT0Y: ai(-1, 1, 0)}
pad = FakeDev("Xbox Wireless Controller", FACE, STICKS, vendor=0x45e, product=0xb13)
nohome = FakeDev("USB Gamepad", [k for k in FACE if k != e.BTN_MODE], dict(STICKS), vendor=0x79, product=0x11)
pad2 = FakeDev("8BitDo SN30 Pro", FACE, dict(STICKS), vendor=0x2dc8, product=0x6101)
plugged = [pad, nohome]
devs = {d.path: d for d in (pad, pad2, nohome)}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda q, *a, **k: type("St", (), {"st_ino": hash(q) % 1000})() if q.startswith("/dev/input/") else real_stat(q, *a, **k)


class UI:
    def write(self, *a): pass
    def syn(self): pass


m = g.Media(); m.enter()
m.case = "2w"
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
port = server.server_address[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()


def wait_for(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def post(what, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{what}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Pitato-Key": "k" * 32})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(what):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{what}", headers={"X-Pitato-Key": "k" * 32})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def tap(code):
    pad.send((e.EV_KEY, code, 1), (e.EV_SYN, 0, 0))
    time.sleep(0.1)
    pad.send((e.EV_KEY, code, 0), (e.EV_SYN, 0, 0))
    time.sleep(0.15)


check("the main loop: resting after a while", wait_for(lambda: m.resting, 5))
sel = m.home_sel
tap(e.BTN_MODE)
check(f"HOME while it rests: awake, still media mode (the press did nothing else)", wait_for(lambda: not m.resting)
      and m.active and m.home_sel == sel)
pad.send((e.EV_ABS, e.ABS_HAT0X, 1), (e.EV_SYN, 0, 0))
time.sleep(0.1)
pad.send((e.EV_ABS, e.ABS_HAT0X, 0), (e.EV_SYN, 0, 0))
check(f"...the next press works ({sel} -> {m.home_sel})", wait_for(lambda: m.home_sel != sel, 2))
m.go_home(); m.dirty = True
check("resting", wait_for(lambda: m.resting, 5))
tap(e.BTN_SOUTH)
check("A while it rests: awake, nothing opened", wait_for(lambda: not m.resting) and m.view == "home")
check("resting", wait_for(lambda: m.resting, 5))
nohome.send((e.EV_KEY, e.BTN_SELECT, 1), (e.EV_SYN, 0, 0))
time.sleep(0.05)
nohome.send((e.EV_KEY, e.BTN_START, 1), (e.EV_SYN, 0, 0))
time.sleep(0.1)
nohome.send((e.EV_KEY, e.BTN_SELECT, 0), (e.EV_KEY, e.BTN_START, 0), (e.EV_SYN, 0, 0))
check("SELECT and START (a controller without HOME) while it rests: awake, still media mode",
      wait_for(lambda: not m.resting) and m.active)
check("resting", wait_for(lambda: m.resting, 5))
out = post("press", {"button": "a"})
check(f"the web page's remote: A wakes it, nothing opened ({out})", out.get("ok") and wait_for(lambda: not m.resting)
      and m.view == "home")
check("resting", wait_for(lambda: m.resting, 5))
out = post("tap", {"x": 0.5, "y": 0.5})
check(f"a touch on the web page's screen: awake, nothing touched ({out})", out == {"ok": True} and not m.resting
      and m.view == "home")
check("resting", wait_for(lambda: m.resting, 5))
out = post("settings", {"key": "clock", "value": "24-hour"})
check(f"anything else done on the web page: awake, and done ({out})", out == {"ok": True} and not m.resting
      and m.setting("clock") == "24-hour")
check("resting", wait_for(lambda: m.resting, 5))
got = []
threading.Thread(target=lambda: got.append(get("screen?after=0&wait=5")), daemon=True).start()
check("the web page asks for the screen's picture: awake", wait_for(lambda: not m.resting, 3))
check("...and gets one", wait_for(lambda: bool(got), 8))
time.sleep(R.REST_WATCHED + 0.2)
check("resting (nobody watching now)", wait_for(lambda: m.resting, 5))
plugged.append(pad2)
check("a controller plugged in: awake", wait_for(lambda: not m.resting, 3))
check("resting", wait_for(lambda: m.resting, 5))
out = post("mode", {"to": "terminal"})
check(f"to the terminal from the web page while it rests: the screen's picture on first ({FB.powered[-3:]})",
      wait_for(lambda: not m.active, 3) and FB.powered[-1] is True and not m.resting)
done.set()
time.sleep(0.5)
server.shutdown()
check(f"no errors in the main loop ({errors})", not errors)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
