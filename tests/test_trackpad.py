"""A trackpad (the BB9900 keyboard's: a mouse of its own, or in with its keys) or a mouse works media mode: a swipe is
the d-pad (a short one a step, a longer one more; it keeps to the way it started till it rests; a finger resting on
it, or a slow drift, nothing); pressed it's A, its right button B; a wheel steps too. In the terminal and Settings >
Controller it isn't touched; in cmatrix and a text box it works, as a controller's d-pad does there (a keyboard's keys
are theirs). Plugged in later: found, the keyboard's name said; gone: let go of. With fake input devices that use the
real evdev codes, and the real main loop."""
import io, json, os, random, shutil, sys, threading, time, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/t_trackpad"
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
g.PROG_TTY = os.devnull                # (cmatrix's console: not this machine's own, never brought to the front)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    vendor, product = 0x1d50, 0x615e


class FakeDev:
    """An input device: select() sees it through a pipe; read() hands out queued events."""

    def __init__(self, n, name, keys=(), rel=(), absolute=()):
        self.path = f"/dev/input/event{n}"
        self.name, self.info = name, Info()
        self.caps = {e.EV_KEY: list(keys)}
        if rel:
            self.caps[e.EV_REL] = list(rel)
        if absolute:
            self.caps[e.EV_ABS] = list(absolute)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        return dict(self.caps)

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
        raise OSError(16, "busy")                      # (the text box's own reader: not in this test)

    def close(self):
        self.closed = True


LETTERS = [getattr(e, "KEY_" + c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
KEYS = LETTERS + [e.KEY_ENTER, e.KEY_BACKSPACE, e.KEY_SPACE, e.KEY_LEFTSHIFT, e.KEY_ESC, e.KEY_CAPSLOCK]
MOUSE_KEYS = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA]
MOUSE_REL = [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL, e.REL_WHEEL_HI_RES, e.REL_HWHEEL_HI_RES]

# the BB9900 over Bluetooth: its keys, and its trackpad as a mouse of its own (and its call keys, as a "Consumer
# Control" of their own); a touch screen, our own keys, a controller
bbk = FakeDev(3, "BB9900 Keyboard", KEYS)
bbm = FakeDev(5, "BB9900 Mouse", MOUSE_KEYS, MOUSE_REL)
bbc = FakeDev(4, "BB9900 Consumer Control", [e.KEY_SEARCH, e.KEY_HOMEPAGE, e.KEY_VOLUMEUP])
touch = FakeDev(6, "Touch Display", [e.BTN_TOUCH], absolute=[e.ABS_X, e.ABS_Y, e.ABS_MT_POSITION_X])
ours = FakeDev(7, "pitato", [e.KEY_ENTER, e.KEY_UP, e.KEY_Q, e.KEY_C])
combo = FakeDev(20, "Logitech K400 Plus", KEYS + [e.BTN_LEFT, e.BTN_RIGHT], [e.REL_X, e.REL_Y, e.REL_WHEEL])
plugged = [bbk, bbm, bbc, touch, ours]
devs = {d.path: d for d in plugged + [combo]}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") \
    else real_stat(p, *a, **k)

# ---- what it finds -----------------------------------------------------------------------------
check("a mouse is one (the BB9900's trackpad), a keyboard with a trackpad too",
      g.is_mouse(bbm) and g.is_mouse(combo) and g.is_keyboard(combo))
check("...not the keys, a touch screen, its call keys, our own keys",
      not any(g.is_mouse(d) for d in (bbk, touch, bbc, ours)))
check("...and not a controller", g.pad_kind(bbm) is None and g.pad_kind(combo) is None)


# ---- swipes, by themselves -------------------------------------------------------------------
def report(k, t, dx=0, dy=0):
    out = []
    if dx:
        out += k.translate(Ev(e.EV_REL, e.REL_X, dx), t)
    if dy:
        out += k.translate(Ev(e.EV_REL, e.REL_Y, dy), t)
    return out + k.translate(Ev(e.EV_SYN, e.SYN_REPORT, 0), t)


clock = [100.0]


def swipe(k, dx, dy, n, gap=0.01, rest=True):
    """n reports of (dx, dy), gap apart (after a rest, unless not): the buttons it stepped, each pressed and let go."""
    if rest:
        clock[0] += 1.0
    out = []
    for _ in range(n):
        clock[0] += gap
        out += report(k, clock[0], dx, dy)
    downs = [name for name, down in out if down]
    paired = out == [(n_, d) for n_ in downs for d in (True, False)]
    return downs if paired else ("not pressed and let go", out)


k = g.Keys(bbm, mouse=True)
check("a short swipe down: one step", swipe(k, 0, 20, 3) == ["down"])
check("...a shorter one: none", swipe(k, 0, 15, 3) == [])
got = swipe(k, 0, 20, 20)
check(f"a long one: more (the first soon, each after it further): {got}", got == ["down"] * 4)
check("up, left, right", (swipe(k, 0, -20, 3), swipe(k, -20, 0, 3), swipe(k, 20, 0, 3)) == (["up"], ["left"], ["right"]))
got = swipe(k, 8, 20, 12)
check(f"aslant: the way it's mostly going ({got})", got == ["down", "down"])
got = swipe(k, 30, 0, 6, rest=False)
check(f"...then sideways, the same swipe: nothing (it keeps to its way) ({got})", got == [])
clock[0] += 0.3
got = swipe(k, 30, 0, 3, rest=False)
check(f"...rested (the finger lifted), sideways: a new swipe ({got})", got == ["right"])
got = swipe(k, 0, 20, 4) + swipe(k, 0, -20, 7, rest=False)
check(f"down and back up, without stopping: a step each way ({got})", got == ["down", "up"])
got = swipe(k, 0, 5, 30, gap=0.1)
check(f"a slow drift (a finger resting on it): nothing ({got})", got == [])
rnd = random.Random(7)
clock[0] += 1
jitter = []
for _ in range(200):
    clock[0] += 0.01
    jitter += report(k, clock[0], rnd.randint(-3, 3), rnd.randint(-3, 3))
check(f"...jittering: nothing ({jitter[:4]})", jitter == [])
got = swipe(k, 0, 127, 2)
check(f"a quick flick, the most a report holds: a step, then two ({got})", got == ["down"] * 3)
got = swipe(k, 0, 1000, 1)
check(f"a huge jump: four steps at most, the rest dropped ({got}, {k.dy})", got == ["down"] * 4 and k.dy == 0)
clock[0] += 1
lost = report(k, clock[0], 0, 40) + k.translate(Ev(e.EV_SYN, e.SYN_DROPPED, 0), clock[0]) + report(k, clock[0] + 0.01, 0, 20)
check(f"events lost (SYN_DROPPED): what came before forgotten ({lost})", lost == [])

# read late (the menus drawing slowly), the swipe's own times count: still one swipe
class Timed(Ev):
    def __init__(self, t, c, v, when):
        super().__init__(t, c, v); self.when = when

    def timestamp(self):
        return self.when


kt, late, at = g.Keys(bbm, mouse=True), [], 5000.0
for batch in range(3):
    for _ in range(3):
        at += 0.012
        late += kt.translate(Timed(e.EV_REL, e.REL_Y, 25, at)) + kt.translate(Timed(e.EV_SYN, e.SYN_REPORT, 0, at))
    time.sleep(0.25)
check(f"read late, a while between (the menus drawing slowly): its own times, one swipe ({late})",
      [n for n, d in late if d] == ["down", "down"])

# its buttons; its wheel
check("pressed (the left button): A, held while it's held",
      [k.translate(Ev(e.EV_KEY, e.BTN_LEFT, v), 0) for v in (1, 2, 0)] == [[("a", True)], [], [("a", False)]])
check("the right button: B", [k.translate(Ev(e.EV_KEY, e.BTN_RIGHT, v), 0) for v in (1, 0)] == [[("b", True)], [("b", False)]])
check("the others: nothing", k.translate(Ev(e.EV_KEY, e.BTN_MIDDLE, 1), 0) == [] and k.translate(Ev(e.EV_KEY, e.BTN_SIDE, 1), 0) == [])
k.translate(Ev(e.EV_KEY, e.BTN_LEFT, 1), 0)
got = swipe(k, 0, 30, 5, rest=False)
k.translate(Ev(e.EV_KEY, e.BTN_LEFT, 0), 0)
check(f"moved while it's pressed (a press rolls the finger): nothing ({got})", got == [])
check("...let go, a swipe: a step again", swipe(k, 0, 20, 3, rest=False) == ["down"])
wheel = [[n for n, d in k.translate(Ev(e.EV_REL, c, v), 0) if d] for c, v in
         ((e.REL_WHEEL, 1), (e.REL_WHEEL, -2), (e.REL_WHEEL, 9), (e.REL_HWHEEL, 1), (e.REL_HWHEEL, -1),
          (e.REL_WHEEL_HI_RES, 120))]
check(f"a wheel: a step a click (four at most), sideways too, its fine steps not again ({wheel})",
      wheel == [["up"], ["down", "down"], ["up"] * 4, ["right"], ["left"], []])

# a keyboard with its trackpad in with it: Enter and the trackpad's press, one A
kc = g.Keys(combo)
got = [kc.translate(Ev(e.EV_KEY, c, v), 0) for c, v in ((e.KEY_ENTER, 1), (e.BTN_LEFT, 1))]
check(f"Enter and the press together: one A ({got})", got == [[("a", True)], []])
check("...its keys let go of: A still held, by the press", kc.let_go("keys") == [] and kc.held() == {"a"})
check("...its trackpad's: A let go of", kc.let_go("pointer") == ["a"] and kc.held() == set())
kc.translate(Ev(e.EV_KEY, e.KEY_W, 1), 0)
check("its trackpad's let go of, its keys kept (W)", kc.let_go("pointer") == [] and kc.held() == {"up"})
check("...all of it", kc.let_go() == ["up"])


# ---- the main loop -------------------------------------------------------------------------
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


def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def wait(sec=0.12):
    time.sleep(sec)


def glide(dev, dx, dy, n, gap=0.012):
    """A finger along the trackpad: n reports, as they come (a report each 12 ms or so), then lifted."""
    for _ in range(n):
        evs = ([(e.EV_REL, e.REL_X, dx)] if dx else []) + ([(e.EV_REL, e.REL_Y, dy)] if dy else [])
        dev.send(*evs, (e.EV_SYN, e.SYN_REPORT, 0))
        time.sleep(gap)
    wait(0.3)                                         # (lifted: the next one's a new swipe)


def click(dev, code=e.BTN_LEFT):
    dev.send((e.EV_KEY, code, 1), (e.EV_SYN, e.SYN_REPORT, 0)); wait(0.05)
    dev.send((e.EV_KEY, code, 0), (e.EV_SYN, e.SYN_REPORT, 0)); wait()


def tap(dev, code):
    dev.send((e.EV_KEY, code, 1)); wait(0.05); dev.send((e.EV_KEY, code, 0)); wait()


kbs = m.pads.keyboards
check(f"found at start: the keyboard and its trackpad, nothing else, not as controllers "
      f"({sorted((d.dev.name, d.mouse) for d in kbs.values())}, {list(m.pads.by_path)})",
      sorted((d.dev.name, d.mouse) for d in kbs.values()) == [("BB9900 Keyboard", False), ("BB9900 Mouse", True)]
      and m.pads.by_path == {})

# the terminal: nothing
glide(bbm, 30, 0, 4); click(bbm)
check(f"in the terminal: its swipes and its press do nothing ({ui.out}, media mode {m.active})", ui.out == [] and not m.active)

# media mode: the home screen
post("/mode", {"to": "media"}); wait()
check("media mode, on the home screen", m.active and m.view == "home")
n_apps = len(m.home_apps())
sel0 = m.home_sel = 0
glide(bbm, 25, 0, 3)
check(f"a short swipe right: the next app ({sel0} -> {m.home_sel})", m.home_sel == 1)
glide(bbm, -25, 0, 3)
check("...left: back", m.home_sel == 0)
glide(bbm, 25, 0, 14)
check(f"a long swipe right: on a few ({m.home_sel})", m.home_sel == 4)
pressed = []
real_press = m.press
m.press = lambda name, repeat=False: (pressed.append(name), real_press(name, repeat))[1]
glide(bbm, 2, -25, 3)
check(f"up (a little aslant): up, nothing else ({pressed})", pressed == ["up"])
m.home_sel = next(i for i, a in enumerate(m.home_apps()) if a[0] == "Music")
click(bbm)
check(f"pressed: Music opens (A) ({m.view}, {g.LIBRARY[m.tab]['name']})", m.view == "list" and g.LIBRARY[m.tab]["name"] == "Music")

# a list
before = m.sels.get(m.tab, 0)
glide(bbm, 0, 25, 3)
check(f"a short swipe down: the next one ({before} -> {m.sels.get(m.tab, 0)})", m.sels.get(m.tab, 0) == before + 1)
glide(bbm, 0, 25, 14)
check(f"a long one: on a few more ({m.sels.get(m.tab, 0)})", m.sels.get(m.tab, 0) == before + 5)
glide(bbm, 0, -25, 3)
check("up: back one", m.sels.get(m.tab, 0) == before + 4)
del pressed[:]
glide(bbm, 0, 2, 40, gap=0.03)
check(f"a finger resting on it, slipping slowly: nothing ({pressed})", pressed == [])
bbm.send((e.EV_REL, e.REL_WHEEL, -1), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
bbm.send((e.EV_REL, e.REL_WHEEL, -1), (e.EV_REL, e.REL_WHEEL_HI_RES, -120), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
check(f"its wheel (Caps Lock on): a step a click ({m.sels.get(m.tab, 0)}, {pressed})",
      m.sels.get(m.tab, 0) == before + 6 and pressed == ["down", "down"])
click(bbm, e.BTN_RIGHT)
check(f"the right button: B, home ({m.view})", m.view == "home")

# cmatrix: the keyboard's keys are its own, the trackpad works it as the d-pad does
typed = []
m.prog_key = lambda keys: typed.append(keys)
m.prog_unblank = lambda: None
m.prog, m.prog_name = Proc(), "cmatrix"
del pressed[:]
colour = m.cm_colour
glide(bbm, 25, 0, 3)
tap(bbk, e.KEY_D)
check(f"cmatrix on: a swipe right is its next colour, the keyboard's D its own ({pressed}, {typed})",
      pressed == ["right"] and m.cm_colour == (colour + 1) % len(g.CM_COLOURS) and len(typed) == 1)
m.prog = m.prog_name = None

# a text box: the trackpad moves on its keys and types the one it's on; the keyboard's keys are the box's
m.keyreader.start = m.keyreader.stop = lambda: None   # (the text box's own reader of the keyboard: not this test's)
m.open_keyboard("Name", "", lambda text: None)
del pressed[:]
glide(bbm, 25, 0, 3)
click(bbm)
tap(bbk, e.KEY_D)
check(f"a text box: a swipe to the next key, pressed it types it; the keyboard's D not a button "
      f"({m.kb['text']!r}, {pressed})", m.kb["text"] == "w" and pressed == ["right", "a"])
m.close_keyboard(False)

# Settings > Controller: not the trackpad's
del pressed[:]
g.Media.learning = property(lambda self: True)
glide(bbm, 25, 0, 3); click(bbm)
check(f"Settings > Controller: not the trackpad's ({pressed})", pressed == [])
del g.Media.learning

# held when it stops being media mode's: let go of, not stuck
real_press_only = m.press
m.press = lambda name, repeat=False: pressed.append(name)
bbm.send((e.EV_KEY, e.BTN_LEFT, 1), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
check(f"pressed and held ({pressed})", pressed == ["a"] and kbs[bbm.path].held() == {"a"})
post("/mode", {"to": "terminal"}); wait()
glide(bbm, 30, 0, 3)
check(f"...the terminal meanwhile: the next move lets it go, nothing typed ({ui.out})",
      not m.active and kbs[bbm.path].held() == set() and ui.out == [])
bbm.send((e.EV_KEY, e.BTN_LEFT, 0), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
m.press = real_press_only
post("/mode", {"to": "media"}); wait()

# a keyboard with a touchpad in with it, plugged in later: one device, its keys and its swipes both
m.toast("x", 0.01); wait()
plugged.append(combo); wait(0.4)
check(f"a keyboard with a touchpad, plugged in: found as a keyboard, and said so ({kbs.get(combo.path) and kbs[combo.path].mouse}, {m.msg!r})",
      combo.path in kbs and kbs[combo.path].mouse is False and m.msg == "Logitech K400 Plus connected")
del pressed[:]
m.go_home(); m.home_sel = 0
glide(combo, 25, 0, 3)
tap(combo, e.KEY_D)
check(f"...its swipe and its D both right ({pressed}, {m.home_sel})", pressed == ["right", "right"] and m.home_sel == 2)
m.prog, m.prog_name = Proc(), "cmatrix"
del pressed[:]
glide(combo, 0, 25, 3)
tap(combo, e.KEY_S)
check(f"...cmatrix on: its touchpad works it, its keys are cmatrix's ({pressed})", pressed == ["down"])
m.prog = m.prog_name = None

# its press opens a text box: the box has it to itself from then on (its touchpad too), its letting go not seen here:
# not left pressed here (its swipes would be nothing, after the box)
real_press_box = m.press


def opens_box(name, repeat=False):
    pressed.append(name)
    if name == "a" and m.view != "keys":
        m.open_keyboard("Name", "", lambda text: None)


m.press = opens_box
del pressed[:]
combo.send((e.EV_KEY, e.BTN_LEFT, 1), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
check(f"its press opens a text box: not left pressed here ({m.view}, {kbs[combo.path].held()})",
      m.view == "keys" and pressed == ["a"] and kbs[combo.path].held() == set())
m.close_keyboard(False); wait()
m.press = real_press_box
del pressed[:]
glide(combo, 25, 0, 3)
check(f"...the box closed: its swipes work ({pressed})", pressed == ["right"])

# the BB9900 off and on again: its keys and its trackpad come back together, the keyboard's name said
for d in (bbk, bbm, bbc):
    d.gone = True
    d.send((e.EV_SYN, e.SYN_REPORT, 0))
    plugged.remove(d)
wait(0.3)
check(f"switched off: its keys and trackpad dropped, closed ({sorted(d.dev.name for d in kbs.values())})",
      bbk.path not in kbs and bbm.path not in kbs and bbk.closed and bbm.closed)
bbk2 = FakeDev(8, "BB9900 Keyboard", KEYS)
bbm2 = FakeDev(9, "BB9900 Mouse", MOUSE_KEYS, MOUSE_REL)              # (its trackpad after its keys, as they come)
devs.update({bbk2.path: bbk2, bbm2.path: bbm2})
m.toast("x", 0.01); wait()
plugged += [bbk2, bbm2]; wait(0.4)
check(f"...on again: both found, the keyboard's name said, not its trackpad's ({m.msg!r})",
      bbk2.path in kbs and bbm2.path in kbs and m.msg == "BB9900 Keyboard connected")

# gone while pressed: let go of
released = []
real_release = m.release
m.release = lambda name: (released.append(name), real_release(name))[1]
m.press = lambda name, repeat=False: pressed.append(name)
bbm2.send((e.EV_KEY, e.BTN_RIGHT, 1), (e.EV_SYN, e.SYN_REPORT, 0)); wait()
bbm2.gone = True
plugged.remove(bbm2)
bbm2.send((e.EV_SYN, e.SYN_REPORT, 0)); wait(0.3)
check(f"its trackpad gone, pressed: dropped, its B let go of ({released})", bbm2.path not in kbs and "b" in released and bbm2.closed)

post("/mode", {"to": "terminal"}); wait()   # (this machine's console as it was: in text mode)
done.set(); th.join(3)
check("loop ended cleanly, all closed", not th.is_alive() and not errors and bbk2.closed and combo.closed)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
