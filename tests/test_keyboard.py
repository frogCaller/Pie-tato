"""A keyboard (a Bluetooth one, like the BB9900's) works media mode: W A S D the d-pad (the arrows too), Enter or
space A, Backspace or Esc B, X Y, Q E L R, P START, O SELECT; held, a key repeats in the lists as a button does;
W and the up arrow together are one press. In the terminal it isn't touched (it types there, as ever); nor while a
text box, cmatrix or Settings > Controller has it; a key that opens a text box isn't left held down. Plugged
in later: found, and said so; gone: let go of. With fake
input devices that use the real evdev codes, and the real main loop."""
import io, json, os, shutil, sys, threading, time, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/t_keyboard"
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
    vendor, product = 0x5ac, 0x220


class FakeDev:
    """An input device: select() sees it through a pipe; read() hands out queued events."""
    n = 0

    def __init__(self, name, keys):
        FakeDev.n += 1
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys, self.info = name, keys, Info()
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)}

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
bb = FakeDev("BB9900 Bluetooth keyboard", LETTERS + [e.KEY_ENTER, e.KEY_BACKSPACE, e.KEY_SPACE, e.KEY_LEFTSHIFT,
                                                      e.KEY_LEFTALT, e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT])
ours = FakeDev("pitato", [e.KEY_ENTER, e.KEY_UP, e.KEY_Q, e.KEY_C])       # (the controller's keys, typed: not one)
later = FakeDev("Logitech K380", LETTERS + [e.KEY_ENTER, e.KEY_ESC, e.KEY_BACKSPACE])
plugged = [bb, ours]
devs = {d.path: d for d in (bb, ours, later)}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") \
    else real_stat(p, *a, **k)

check("a keyboard is one, our own keys aren't", g.is_keyboard(bb) and g.is_keyboard(later) and not g.is_keyboard(ours))
k = g.Keys(bb)
check("W is up, A left, S down, D right", [k.translate(Ev(e.EV_KEY, c, v)) for c, v in
      ((e.KEY_W, 1), (e.KEY_W, 0), (e.KEY_A, 1), (e.KEY_S, 1), (e.KEY_D, 1))]
      == [[("up", True)], [("up", False)], [("left", True)], [("down", True)], [("right", True)]])
k.let_go()
def press_up(code):
    down = k.translate(Ev(e.EV_KEY, code, 1))
    up = k.translate(Ev(e.EV_KEY, code, 0))
    return down[0][0] if down and up == [(down[0][0], False)] else None


check("Enter and space A, Backspace and Esc B, X Y, Q E L R, P START, O SELECT",
      [press_up(c) for c in (e.KEY_ENTER, e.KEY_SPACE, e.KEY_BACKSPACE, e.KEY_ESC, e.KEY_X, e.KEY_Y, e.KEY_Q, e.KEY_E,
                             e.KEY_P, e.KEY_O)]
      == ["a", "a", "b", "b", "x", "y", "l", "r", "start", "select"])
k.let_go()
got = [k.translate(Ev(e.EV_KEY, c, v)) for c, v in ((e.KEY_W, 1), (e.KEY_UP, 1), (e.KEY_W, 0), (e.KEY_UP, 0))]
check(f"W and the up arrow together: one press, let go with the last ({got})",
      got == [[("up", True)], [], [], [("up", False)]])
check("a key held (its repeats) and the rest: nothing", k.translate(Ev(e.EV_KEY, e.KEY_W, 2)) == []
      and k.translate(Ev(e.EV_KEY, e.KEY_Z, 1)) == [] and k.translate(Ev(e.EV_KEY, e.KEY_LEFTSHIFT, 1)) == [])


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


def tap(code, hold=0.05):
    bb.send((e.EV_KEY, code, 1)); wait(hold); bb.send((e.EV_KEY, code, 0)); wait()


check(f"found at start: the keyboard, not as a controller ({list(m.pads.keyboards)}, {list(m.pads.by_path)})",
      list(m.pads.keyboards) == [bb.path] and m.pads.by_path == {})
check("...and left to the text boxes too (it isn't a controller)", m.keyreader.exclude == set())

# the terminal: its keys are its own
tap(e.KEY_D); tap(e.KEY_ENTER)
check(f"in the terminal: nothing done with its keys ({ui.out}, media mode {m.active})", ui.out == [] and not m.active)

# media mode
post("/mode", {"to": "media"}); wait()
check("media mode, on the home screen", m.active and m.view == "home")
sel0 = m.home_sel
tap(e.KEY_D)
check(f"D: the next app ({sel0} -> {m.home_sel})", m.home_sel == (sel0 + 1) % len(m.home_apps()))
tap(e.KEY_A)
check("A: back", m.home_sel == sel0)
tap(e.KEY_RIGHT); tap(e.KEY_LEFT)
check("the arrows too", m.home_sel == sel0)
apps = m.home_apps()
m.home_sel = next(i for i, a in enumerate(apps) if a[0] == "Music")
tap(e.KEY_ENTER)
check(f"Enter: Music opens ({m.view}, {g.LIBRARY[m.tab]['name']})", m.view == "list" and g.LIBRARY[m.tab]["name"] == "Music")
n = len(m.tab_items())
before = m.sels.get(m.tab, 0)
bb.send((e.EV_KEY, e.KEY_S, 1)); wait(1.0); bb.send((e.EV_KEY, e.KEY_S, 0)); wait()
moved = m.sels.get(m.tab, 0) - before
check(f"S held: down the list, again and again ({moved} of {n})", moved >= 3)
tap(e.KEY_W)
check("W: up one", m.sels.get(m.tab, 0) == before + moved - 1)
tab = m.tab
tap(e.KEY_E)
check(f"E: the next app (R) ({m.strip_tab()})", m.tab != tab)
tap(e.KEY_Q)
check("Q: back (L)", m.tab == tab)
tap(e.KEY_X)
check(f"X: its controls ({m.view})", m.view == "help")
tap(e.KEY_X)
check("...X again: closed", m.view == "list")
tap(e.KEY_BACKSPACE)
check(f"Backspace: home (B) ({m.view})", m.view == "home")

# START and SELECT: Weather's settings (START), and back
m.home_sel = next(i for i, a in enumerate(m.home_apps()) if a[0] == "Weather")
tap(e.KEY_SPACE)
check(f"space: Weather opens (A) ({m.tab_type()})", m.view == "list" and m.tab_type() == "weather")
tap(e.KEY_P)
check(f"P: its settings (START) ({m.wx_menu})", m.wx_menu == "menu")
tap(e.KEY_P)
check("P again: closed", not m.wx_menu)
pressed = []
real_press = m.press
m.press = lambda name, repeat=False: (pressed.append(name), real_press(name, repeat))[1]
tap(e.KEY_O); tap(e.KEY_Y)
check(f"O is SELECT, Y is Y ({pressed})", pressed == ["select", "y"])

# a text box, cmatrix, Settings > Controller: the keys are theirs
del pressed[:]
m.keyreader.start = m.keyreader.stop = lambda: None   # (the text box's own reader of the keyboard: not this test's)
m.open_keyboard("Name", "", lambda text: None)
tap(e.KEY_D); tap(e.KEY_ENTER)
check(f"a text box up: its keys not buttons ({pressed}, {m.view})", pressed == [] and m.view == "keys")
m.close_keyboard(False)
m.prog = Proc()
tap(e.KEY_D); tap(e.KEY_Q)
check(f"cmatrix or htop on: the keys are theirs ({pressed})", pressed == [])
m.prog = None
g.Media.learning = property(lambda self: True)       # (Settings > Controller, setting up a controller)
tap(e.KEY_D)
check(f"Settings > Controller: not the keyboard's ({pressed})", pressed == [])
del g.Media.learning

# Enter opens a text box: the box has the keyboard to itself from then on (KeyReader: Enter's letting go is the box's,
# not seen here), so it isn't left held down here, and the next Enter, after the box, is a press again
del pressed[:]
press_was = m.press


def opens_box(name, repeat=False):
    pressed.append(name)
    if name == "a" and m.view != "keys":
        m.open_keyboard("Name", "", lambda text: None)


m.press = opens_box
bb.send((e.EV_KEY, e.KEY_ENTER, 1)); wait()
check(f"Enter: a box opens ({m.view}, {pressed})", m.view == "keys" and pressed == ["a"])
check(f"...Enter not left held down here ({m.pads.keyboards[bb.path].codes})", not m.pads.keyboards[bb.path].codes)
m.close_keyboard(False); wait()
tap(e.KEY_ENTER)
check(f"...the box closed, Enter again: a press again ({pressed})", pressed == ["a", "a"])
m.close_keyboard(False)


# the TV remote's number pad: the same (the keyboard types its numbers into it)
def opens_pad(name, repeat=False):
    pressed.append(name)
    if name == "a" and m.remote_pad is None:
        m.remote_pad = {"text": "", "r": 0, "c": 1}


del pressed[:]
m.press = opens_pad
bb.send((e.EV_KEY, e.KEY_ENTER, 1)); wait()
tap(e.KEY_D)
check(f"Enter: the number pad opens; the keys not buttons while it's up, Enter not left held down ({pressed})",
      pressed == ["a"] and not m.pads.keyboards[bb.path].codes)
m.remote_pad = None; wait()
tap(e.KEY_ENTER)
check(f"...closed, Enter again: a press again ({pressed})", pressed == ["a", "a"])
m.remote_pad = None
m.press = press_was
del pressed[:]

# held when it stops being media mode's: let go of, not stuck
released = []
real_release = m.release
m.release = lambda name: (released.append(name), real_release(name))[1]
bb.send((e.EV_KEY, e.KEY_D, 1)); wait()
check("D held down", pressed[-1:] == ["right"])
post("/mode", {"to": "terminal"}); wait()
bb.send((e.EV_KEY, e.KEY_A, 1)); wait()
check(f"...the terminal meanwhile: the next key lets D go, nothing else ({pressed}, {released})",
      pressed == ["right"] and not m.active and not m.pads.keyboards[bb.path].codes)
bb.send((e.EV_KEY, e.KEY_A, 0), (e.EV_KEY, e.KEY_D, 0)); wait()
check(f"...nothing typed by us in the terminal ({ui.out})", ui.out == [])
post("/mode", {"to": "media"}); wait()

# another keyboard later; one gone
m.toast("x", 0.01); wait()
plugged.append(later); wait(0.4)
check(f"another keyboard, plugged in: found, and said so ({list(m.pads.keyboards)}, {m.msg!r})",
      later.path in m.pads.keyboards and m.msg == "Logitech K380 connected")
del pressed[:]
later.send((e.EV_KEY, e.KEY_ESC, 1)); wait(); later.send((e.EV_KEY, e.KEY_ESC, 0)); wait()
check(f"...its Esc is B ({pressed})", pressed == ["b"])
later.send((e.EV_KEY, e.KEY_W, 1)); wait()
later.gone = True
plugged.remove(later)
later.send((e.EV_KEY, e.KEY_W, 0)); wait(0.3)
check(f"...gone (switched off): dropped, its W let go of ({list(m.pads.keyboards)})",
      later.path not in m.pads.keyboards and "up" in released and later.closed)

post("/mode", {"to": "terminal"}); wait()   # (this machine's console as it was: in text mode)
done.set(); th.join(3)
check("loop ended cleanly, keyboards closed", not th.is_alive() and not errors and bb.closed)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
