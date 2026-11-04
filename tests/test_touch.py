"""A touch screen (Waveshare's 4inch 720x720, or any that says it's the screen itself) works media mode as the web
page's copy of the screen does: a tap picks and opens what's there (an app, a row, a button along the bottom), a swipe
moves along (a list scrolls), a resting screen just wakes. Found among the other devices (not a laptop's touchpad, a
drawing tablet, a mouse or a controller), with its own axes' ranges, the single-touch way or by slot (the first finger
alone); a finger resting, or moved not far either way, nothing. Turned with the picture (Settings > Rotate screen) and
off the picture's black edges, nothing. Not the terminal's, Settings > Controller's or Chromium's (which reads it
itself). With fake input devices that use the real evdev codes, and the real main loop."""
import io, json, os, shutil, sys, threading, time, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t_touch"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{HOME}/{d}")
for i in range(30):
    open(f"{HOME}/Music/song {i:02d}.mp3", "wb").write(b"x" * 100)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"; g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    vendor, product = 0x0eef, 0x0005


def axis(lo, hi):
    return AbsInfo(value=0, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


class FakeDev:
    """An input device: select() sees it through a pipe; read() hands out queued events."""

    def __init__(self, n, name, keys=(), rel=(), absolute=(), props=None):
        self.path = f"/dev/input/event{n}"
        self.name, self.info = name, Info()
        self.caps = {e.EV_KEY: list(keys)}
        if rel:
            self.caps[e.EV_REL] = list(rel)
        if absolute:
            self.caps[e.EV_ABS] = list(absolute)        # ((code, range)...), as evdev gives them
        self.props = props
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        caps = dict(self.caps)
        if not absinfo and e.EV_ABS in caps:
            caps[e.EV_ABS] = [c for c, _ in caps[e.EV_ABS]]
        return caps

    def input_props(self, verbose=False):
        if self.props is None:
            raise AttributeError("input_props")          # (an older evdev, or a device that says nothing)
        return list(self.props)

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

    def grab(self):
        raise OSError(16, "busy")

    def close(self):
        self.closed = True


MT = [(e.ABS_MT_SLOT, axis(0, 9)), (e.ABS_MT_TRACKING_ID, axis(0, 65535)),
      (e.ABS_MT_POSITION_X, axis(0, 4095)), (e.ABS_MT_POSITION_Y, axis(0, 4095))]
waveshare = FakeDev(6, "WaveShare WS170120", [e.BTN_TOUCH],
                    absolute=[(e.ABS_X, axis(0, 4095)), (e.ABS_Y, axis(0, 4095))] + MT, props=[e.INPUT_PROP_DIRECT])
mt_only = FakeDev(8, "Goodix Capacitive TouchScreen", [], absolute=MT, props=[e.INPUT_PROP_DIRECT])
plain = FakeDev(9, "Touch Display", [e.BTN_TOUCH], absolute=[(e.ABS_X, axis(0, 799)), (e.ABS_Y, axis(0, 479))])
pointer = FakeDev(10, "ILITEK ILITEK-TOUCH", [e.BTN_LEFT], absolute=[(e.ABS_X, axis(0, 16383)), (e.ABS_Y, axis(0, 9599))],
                  props=[e.INPUT_PROP_DIRECT])
touchpad = FakeDev(11, "SynPS/2 Synaptics TouchPad", [e.BTN_TOUCH, e.BTN_TOOL_FINGER, e.BTN_LEFT],
                   absolute=[(e.ABS_X, axis(1300, 5700)), (e.ABS_Y, axis(1100, 4700))] + MT, props=[e.INPUT_PROP_POINTER])
tablet = FakeDev(12, "Wacom Intuos S Pen", [e.BTN_TOUCH, e.BTN_TOOL_PEN, e.BTN_STYLUS],
                 absolute=[(e.ABS_X, axis(0, 15200)), (e.ABS_Y, axis(0, 9500))], props=[e.INPUT_PROP_POINTER])
mouse = FakeDev(13, "Logitech USB Optical Mouse", [e.BTN_LEFT, e.BTN_RIGHT], [e.REL_X, e.REL_Y, e.REL_WHEEL])
pad = FakeDev(14, "Xbox Wireless Controller", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START],
              absolute=[(e.ABS_X, axis(-32768, 32767)), (e.ABS_Y, axis(-32768, 32767))])
ours = FakeDev(15, "pitato", [e.KEY_ENTER, e.KEY_UP])

# ---- what it finds -----------------------------------------------------------------------------------------
found = {d.name: g.is_touchscreen(d) for d in (waveshare, mt_only, plain, pointer, touchpad, tablet, mouse, pad, ours)}
check(f"touch screens: the Waveshare's, one by slot alone, one that says nothing of itself, one that presses as a "
      f"mouse's button does ({found})",
      all(found[d.name] for d in (waveshare, mt_only, plain, pointer)))
check("...not a laptop's touchpad, a drawing tablet, a mouse, a controller, our own keys",
      not any(found[d.name] for d in (touchpad, tablet, mouse, pad, ours)))


# ---- a finger, by itself ----------------------------------------------------------------------------------
def finger(t, points, gap=0.05, start=None, key=e.BTN_TOUCH, x=e.ABS_X, y=e.ABS_Y, slot=False):
    """A finger put down at points[0], moved through the rest, gap seconds a step, then lifted: what it made."""
    now = [start if start is not None else clock[0]]
    out = []

    def report(evs):
        for ev in evs:
            out.extend(t.translate(Ev(*ev), now[0]))
        out.extend(t.translate(Ev(e.EV_SYN, e.SYN_REPORT, 0), now[0]))

    first = True
    for px, py in points:
        evs = []
        if first and slot:
            evs += [(e.EV_ABS, e.ABS_MT_SLOT, 0), (e.EV_ABS, e.ABS_MT_TRACKING_ID, 7)]
        if first and key is not None:
            evs.append((e.EV_KEY, key, 1))
        if px is not None:
            evs.append((e.EV_ABS, x, px))
        if py is not None:
            evs.append((e.EV_ABS, y, py))
        report(evs)
        first = False
        now[0] += gap
    report(([(e.EV_ABS, e.ABS_MT_SLOT, 0), (e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)] if slot else [])
           + ([(e.EV_KEY, key, 0)] if key is not None else []))
    clock[0] = now[0] + 1
    return out


clock = [100.0]
t = g.Touch(waveshare)
check(f"its ranges, from what it says of itself ({t.xr}, {t.yr}, the single-touch way: {not t.mt})",
      t.xr == (0, 4095) and t.yr == (0, 4095) and not t.mt)
got = finger(t, [(2048, 1024), (2060, 1030)])
check(f"a tap: where it went down, as a share of the screen ({got})",
      len(got) == 1 and got[0][0] == "tap" and abs(got[0][1] - 0.5) < 0.01 and abs(got[0][2] - 0.25) < 0.01)
got = finger(t, [(None, None)])
check(f"...the same place again (the screen doesn't say it again): a tap there too ({got})",
      len(got) == 1 and got[0][0] == "tap" and abs(got[0][1] - 0.5) < 0.01)
got = finger(t, [(2048, 3500), (2048, 2600), (2050, 1500), (2050, 800)])
check(f"a swipe up: which way, and how far ({got})",
      len(got) == 1 and got[0][0] == "swipe" and abs(got[0][1]) < 0.01 and -0.67 < got[0][2] < -0.65)
got = finger(t, [(1000, 1000), (1160, 1000)])
check(f"moved a little, not far: nothing ({got})", got == [])
got = finger(t, [(1000, 1000), (1001, 1000)], gap=1.2)
check(f"a finger resting there, not moving: nothing ({got})", got == [])
out = t.translate(Ev(e.EV_KEY, e.BTN_TOUCH, 1), clock[0]) + t.translate(Ev(e.EV_ABS, e.ABS_X, 300), clock[0])
out += t.translate(Ev(e.EV_SYN, e.SYN_REPORT, 0), clock[0]) + t.translate(Ev(e.EV_SYN, e.SYN_DROPPED, 0), clock[0])
out += t.translate(Ev(e.EV_KEY, e.BTN_TOUCH, 0), clock[0] + 0.1) + t.translate(Ev(e.EV_SYN, e.SYN_REPORT, 0), clock[0] + 0.1)
check(f"events lost (SYN_DROPPED): the finger forgotten, nothing ({out})", out == [])

tm = g.Touch(mt_only)
got = finger(tm, [(1024, 3072)], key=None, x=e.ABS_MT_POSITION_X, y=e.ABS_MT_POSITION_Y, slot=True)
check(f"by slot alone (no touch key): its first finger's tap ({tm.mt}, {got})",
      tm.mt and len(got) == 1 and got[0][0] == "tap" and abs(got[0][1] - 0.25) < 0.01 and abs(got[0][2] - 0.75) < 0.01)
evs = [(e.EV_ABS, e.ABS_MT_SLOT, 0), (e.EV_ABS, e.ABS_MT_TRACKING_ID, 3), (e.EV_ABS, e.ABS_MT_POSITION_X, 2048),
       (e.EV_ABS, e.ABS_MT_POSITION_Y, 2048), (e.EV_SYN, e.SYN_REPORT, 0),
       (e.EV_ABS, e.ABS_MT_SLOT, 1), (e.EV_ABS, e.ABS_MT_TRACKING_ID, 4), (e.EV_ABS, e.ABS_MT_POSITION_X, 100),
       (e.EV_ABS, e.ABS_MT_POSITION_Y, 100), (e.EV_SYN, e.SYN_REPORT, 0),
       (e.EV_ABS, e.ABS_MT_SLOT, 0), (e.EV_ABS, e.ABS_MT_TRACKING_ID, -1), (e.EV_SYN, e.SYN_REPORT, 0)]
got = [x for ev in evs for x in tm.translate(Ev(*ev), clock[0])]
check(f"...a second finger meanwhile: let be, the first one's tap ({got})",
      len(got) == 1 and got[0][0] == "tap" and abs(got[0][1] - 0.5) < 0.01)
tp = g.Touch(pointer)
got = finger(tp, [(8192, 4800)], key=e.BTN_LEFT)
check(f"one that presses as a mouse's button does: a tap ({got})",
      len(got) == 1 and got[0][0] == "tap" and abs(got[0][1] - 0.5) < 0.01 and abs(got[0][2] - 0.5) < 0.01)


# ---- where on the picture -----------------------------------------------------------------------------------
class Pic:
    def __init__(self, dev_w, dev_h, tw, th, ox=0, oy=0, turn=0, w=640, h=480):
        self.dev_w, self.dev_h, self.tw, self.th, self.ox, self.oy, self.turn = dev_w, dev_h, tw, th, ox, oy, turn
        self.w, self.h = w, h


class Where:
    touch_cmd = g.Media.touch_cmd

    def __init__(self, fb):
        self.fb = fb


sq = Where(Pic(720, 720, 720, 720, w=720, h=720))
check("the square screen, as it is: the same share", sq.touch_cmd(("tap", 0.5, 0.25)) == {"cmd": "tap", "x": 0.5, "y": 0.25})
side = Where(Pic(480, 800, 800, 480, turn=90, w=800, h=480))        # (a tall screen on its side, turned to lie wide)
got = side.touch_cmd(("tap", 0.25, 0.5))
check(f"turned a quarter (Settings > Rotate screen): where that is on the picture ({got})",
      got == {"cmd": "tap", "x": 0.5, "y": 0.75})
got = side.touch_cmd(("swipe", 0.0, -0.5))
check(f"...a swipe up the screen's own way: left on the picture ({got})",
      got["cmd"] == "swipe" and abs(got["x"] + 0.5) < 1e-9 and abs(got["y"]) < 1e-9)
got = Where(Pic(640, 480, 640, 480, turn=180)).touch_cmd(("tap", 0.25, 0.25))
check(f"upside down: the other corner ({got})", got == {"cmd": "tap", "x": 0.75, "y": 0.75})
got = Where(Pic(480, 640, 640, 480, turn=270)).touch_cmd(("tap", 0.25, 0.75))
check(f"a quarter the other way ({got})", got == {"cmd": "tap", "x": 0.25, "y": 0.25})
box = Where(Pic(720, 1280, 720, 540, oy=370))                        # (black above and below the picture)
check(f"on the black edges round the picture: nothing ({box.touch_cmd(('tap', 0.5, 0.1))})",
      box.touch_cmd(("tap", 0.5, 0.1)) is None and box.touch_cmd(("tap", 0.5, 0.95)) is None)
got = box.touch_cmd(("tap", 0.5, 0.5))
check(f"...on it: where on it ({got})", got["cmd"] == "tap" and abs(got["x"] - 0.5) < 1e-9 and abs(got["y"] - 0.5) < 1e-3)
check("no screen: nothing", Where(None).touch_cmd(("tap", 0.5, 0.5)) is None)


# ---- the main loop --------------------------------------------------------------------------------------------
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


def fake_spawn(self, args, target):
    self.proc = Proc(); self.started = time.monotonic() - 5


g.Media.spawn = fake_spawn


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    frames = 0

    def show(self, img):
        FB.frames += 1; self.frames = FB.frames

    def show_part(self, img, box):
        self.show(img)

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def power(self, on):
        return True

    def close(self):
        pass


plugged = [waveshare, touchpad, mouse, ours]
later = FakeDev(16, "WaveShare WS170120", [e.BTN_TOUCH], absolute=[(e.ABS_X, axis(0, 4095)), (e.ABS_Y, axis(0, 4095))],
                props=[e.INPUT_PROP_DIRECT])
devs = {d.path: d for d in plugged + [later]}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") \
    else real_stat(p, *a, **k)
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


def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def wait(sec=0.15):
    time.sleep(sec)


def raw(share):
    return round(share * 4095)


def touch_at(dev, x, y):
    """A tap with a finger on the screen at x, y (a share of it)."""
    dev.send((e.EV_KEY, e.BTN_TOUCH, 1), (e.EV_ABS, e.ABS_X, raw(x)), (e.EV_ABS, e.ABS_Y, raw(y)), (e.EV_SYN, e.SYN_REPORT, 0))
    wait(0.05)
    dev.send((e.EV_KEY, e.BTN_TOUCH, 0), (e.EV_SYN, e.SYN_REPORT, 0))
    wait()


def drag(dev, x, y0, y1, steps=6):
    """A finger put down at x, y0 and swiped to x, y1, then lifted."""
    dev.send((e.EV_KEY, e.BTN_TOUCH, 1), (e.EV_ABS, e.ABS_X, raw(x)), (e.EV_ABS, e.ABS_Y, raw(y0)), (e.EV_SYN, e.SYN_REPORT, 0))
    for i in range(1, steps + 1):
        wait(0.02)
        dev.send((e.EV_ABS, e.ABS_Y, raw(y0 + (y1 - y0) * i / steps)), (e.EV_SYN, e.SYN_REPORT, 0))
    dev.send((e.EV_KEY, e.BTN_TOUCH, 0), (e.EV_SYN, e.SYN_REPORT, 0))
    wait()


def spot(what):
    """The middle of where a tap does what (the picture's taps, as drawn), as a share of the screen."""
    for (x0, y0, x1, y1), w in reversed(m.taps_now()):
        if w == what:
            return ((x0 + x1) / 2 / FB.w, (y0 + y1) / 2 / FB.h)
    return None


check(f"found at start: the Waveshare's touch screen alone, not the touchpad ({sorted(m.pads.touches)})",
      sorted(m.pads.touches) == [waveshare.path] and touchpad.path not in m.pads.by_path)

touch_at(waveshare, 0.5, 0.5)
check(f"the terminal: a tap does nothing ({ui.out}, media mode {m.active})", ui.out == [] and not m.active)

post("/mode", {"to": "media"}); wait()
check("media mode, on the home screen", m.active and m.view == "home")
music = next(i for i, a in enumerate(m.home_apps()) if a[0] == "Music")
where = spot(("sel", "attr", "home_sel", music))
check(f"where Music is on the home screen ({where})", where is not None)
touch_at(waveshare, *where)
check(f"Music tapped: it opens ({m.view}, {g.LIBRARY[m.tab]['name'] if m.view == 'list' else ''})",
      m.view == "list" and g.LIBRARY[m.tab]["name"] == "Music")
top0 = m.tops.get(m.tab, 0)
drag(waveshare, 0.5, 0.8, 0.3)
check(f"a swipe up the list: it scrolls on ({top0} -> {m.tops.get(m.tab, 0)})", m.tops.get(m.tab, 0) > top0)
pressed = []
real_press = m.press
m.press = lambda name, repeat=False: (pressed.append(name), real_press(name, repeat))[1]
back = spot(("keys", "b"))
check(f"B along the bottom, where it's drawn ({back})", back is not None)
touch_at(waveshare, *back)
check(f"...tapped: B, home ({pressed}, {m.view})", pressed == ["b"] and m.view == "home")
m.press = real_press

# resting (the battery saver on): a tap wakes it, and that's all
real_saver = g.Media.saver_on
g.Media.saver_on = lambda self: True
m.resting = True
wait(0.3)
rested = m.resting
touch_at(waveshare, *where)
wait(0.3)
check(f"the screen resting: a tap wakes it, nothing opens ({rested} -> {m.resting}, {m.view})",
      rested and not m.resting and m.view == "home")
g.Media.saver_on = real_saver

# turned upside down (Settings > Rotate screen): the screen's own corner opposite is where Music is
FB.turn, FB.dev_w, FB.dev_h, FB.tw, FB.th, FB.ox, FB.oy = 180, 640, 480, 640, 480, 0, 0
m.dirty = True; wait()
touch_at(waveshare, 1 - where[0], 1 - where[1])
check(f"upside down: tapped where Music is as you see it, it opens ({m.view})",
      m.view == "list" and g.LIBRARY[m.tab]["name"] == "Music")
FB.turn = 0
m.press("b"); wait()

# Chromium in front, Settings > Controller: not theirs
real_shown = g.Media.chromium_shown
g.Media.chromium_shown = lambda self: True
touch_at(waveshare, *where)
check(f"Chromium in front (it reads the screen's touches itself): nothing here ({m.view})", m.view == "home")
g.Media.chromium_shown = real_shown
g.Media.learning = property(lambda self: True)
touch_at(waveshare, *where)
check(f"Settings > Controller: nothing ({m.view})", m.view == "home")
del g.Media.learning

# unplugged, and plugged in again later
plugged.remove(waveshare)
waveshare.gone = True
waveshare.send((e.EV_SYN, e.SYN_REPORT, 0)); wait(0.3)
check(f"unplugged: gone ({sorted(m.pads.touches)})", m.pads.touches == {})
m.msg = None
plugged.append(later); wait(0.5)
check(f"plugged in later: found, and said so ({sorted(m.pads.touches)}, {m.msg!r})",
      later.path in m.pads.touches and "WaveShare" in str(m.msg))
touch_at(later, *where)
check(f"...and it works (Music opens) ({m.view})", m.view == "list" and g.LIBRARY[m.tab]["name"] == "Music")

done.set()
th.join(3)
check(f"the main loop ran without an error ({errors})", not errors)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
