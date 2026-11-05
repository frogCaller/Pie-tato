"""HOME as a hotkey (app.py), for Konami code: in the menus, HOME does its thing as you let go of it, and HOME with
another button brings up the box for one of your codes (that button isn't part of the code; HOME then does nothing
else). Put the code in with HOME let go or still held: it's done. HOME while the box is up: never mind, at once.
Elsewhere HOME is as ever, as it goes down: the terminal's, the Controls page's, while a code's put in on its page.
A controller without HOME: SELECT and START together, the same. HOME held for ages: the next button is itself. The
real main loop, with pretend controllers."""
import os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t_konami_home"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Videos")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')
g.home_dir = lambda: S + "/home/u"
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", S + "/home/u") for x in t[key]]
import gk_static; gk_static.use_home(g, S + "/home/u")
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


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
        self.q += [Ev(*x) for x in evs] + [Ev(e.EV_SYN, 0, 0)]
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


HATS = {e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)}
FACE = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START]
pad = FakeDev("Microsoft X-Box 360 pad", FACE + [e.BTN_MODE], dict(HATS))
nohome = FakeDev("USB Gamepad", FACE, dict(HATS), vendor=0x79, product=0x11)
plugged = [pad, nohome]
devs = {d.path: d for d in plugged}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: (type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/")
                                else real_stat(p, *a, **k))


class UI:
    def __init__(self):
        self.out = []

    def write(self, t, c, v):
        self.out.append((c, v))

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    last = None

    def show(self, img):
        FB.last = img.copy()

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
switches, progs, toasts = [], [], []
orig_enter, orig_leave = m.enter, m.leave
m.enter = lambda: (switches.append("menu"), orig_enter())[1]
m.leave = lambda: (switches.append("terminal"), orig_leave())[1]
m.prog_start = lambda name: progs.append(name)
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


def wait(sec=0.15):
    time.sleep(sec)


def key(dev, code, down):
    dev.send((e.EV_KEY, code, 1 if down else 0)); wait()


def tap(dev, code):
    key(dev, code, True); key(dev, code, False)


ARROWS = {"up": (e.ABS_HAT0Y, -1), "down": (e.ABS_HAT0Y, 1), "left": (e.ABS_HAT0X, -1), "right": (e.ABS_HAT0X, 1)}
CODES = {"a": e.BTN_SOUTH, "b": e.BTN_EAST}


def buttons(dev, *names):
    for n in names:
        if n in ARROWS:
            axis, val = ARROWS[n]
            dev.send((e.EV_ABS, axis, val)); wait(0.08)
            dev.send((e.EV_ABS, axis, 0)); wait(0.08)
        else:
            tap(dev, CODES[n])


def at_home():
    m.soon_jobs.append(m.go_home)
    m.wake()
    wait(0.3)


orig_enter()
m.boot_media = False
threading.Thread(target=loop, daemon=True).start()
wait(0.5)
check("in the menus, both controllers found", m.active and m.view == "home" and set(m.pads.by_path) == set(devs))

# ---- HOME alone ----------------------------------------------------------------------------------------------------
key(pad, e.BTN_MODE, True)
check("in the menus, HOME down: nothing yet (it waits to see if another button comes)", m.active and switches == [])
key(pad, e.BTN_MODE, False)
check(f"...let go: the terminal ({switches})", not m.active and switches == ["terminal"])
key(pad, e.BTN_MODE, True)
check(f"in the terminal, HOME down: the menus at once, as ever ({switches})", m.active and switches == ["terminal", "menu"])
key(pad, e.BTN_MODE, False)
check("...let go: nothing more", m.active and switches == ["terminal", "menu"])
switches.clear()

# ---- HOME and another button: the box for a code ------------------------------------------------------------------
at_home()
key(pad, e.BTN_MODE, True)
buttons(pad, "up")
check(f"HOME held, then ▲: the box for a code, ▲ not part of it ({m.view}, {m.konami_in})", m.view == "konami"
      and m.konami_in is not None and m.konami_in["keys"] == [] and m.home_sel == 0)
key(pad, e.BTN_MODE, False)
check("...HOME let go: nothing else (still the menus, the box up)", m.active and m.view == "konami" and switches == [])
buttons(pad, "up", "up", "down", "down", "left", "right", "left", "right", "b", "a")
check(f"...the classic code: cmatrix ({progs}, {toasts[-1:]})", progs == ["cmatrix"] and m.konami_in is None
      and g.LIBRARY[m.tab]["name"] == "Apps" and m.view == "list")
at_home()
key(pad, e.BTN_MODE, True)
tap(pad, e.BTN_SOUTH)
buttons(pad, "up", "up", "down", "down", "left", "right", "left", "right", "b", "a")
key(pad, e.BTN_MODE, False)
check(f"HOME held all the while (A, then the code): cmatrix, and nothing else ({progs}, {switches})",
      progs == ["cmatrix", "cmatrix"] and m.active and switches == [])
at_home()
key(pad, e.BTN_MODE, True)
tap(pad, e.BTN_NORTH)
key(pad, e.BTN_MODE, False)
buttons(pad, "up")
key(pad, e.BTN_MODE, True)
check(f"HOME while the box is up: never mind, at once ({m.view})", m.view == "home" and m.konami_in is None and m.active)
key(pad, e.BTN_MODE, False)
check("...let go: nothing more", m.active and m.view == "home" and switches == [])

# ---- elsewhere: HOME as ever, as it goes down ------------------------------------------------------------------------
m.soon_jobs.append(lambda: (setattr(m, "help_from", "list"), setattr(m, "view", "help")))
m.wake(); wait(0.3)
key(pad, e.BTN_MODE, True)
check(f"on the Controls page: HOME at once ({switches})", not m.active and switches == ["terminal"])
key(pad, e.BTN_MODE, False)
key(pad, e.BTN_MODE, True); key(pad, e.BTN_MODE, False)
switches.clear()
m.soon_jobs.append(lambda: (m.web_tab("Konami code"), m.sels.__setitem__(m.tab_index("konami"), 1),
                            m.press("a")))
m.wake(); wait(0.3)
check("New code on its page: being put in", m.konami_rec is not None)
key(pad, e.BTN_MODE, True)
check("...HOME stops it, at once", m.konami_rec is None and m.active and switches == [])
key(pad, e.BTN_MODE, False)
check("...let go: nothing more", m.active and switches == [])

# ---- a controller without HOME: SELECT and START together ------------------------------------------------------------
at_home()
key(nohome, e.BTN_SELECT, True); key(nohome, e.BTN_START, True)
check("no HOME: SELECT and START down, in the menus: nothing yet", m.active and switches == [] and m.view == "home")
tap(nohome, e.BTN_SOUTH)
check(f"...and A: the box for a code ({m.view})", m.view == "konami")
key(nohome, e.BTN_START, False); key(nohome, e.BTN_SELECT, False)
check("...let go: nothing else", m.active and m.view == "konami" and switches == [])
buttons(nohome, "up", "up", "down", "down", "left", "right", "left", "right", "b", "a")
check(f"...the code: cmatrix ({progs})", progs[-1:] == ["cmatrix"] and len(progs) == 3 and m.konami_in is None)
at_home()
key(nohome, e.BTN_SELECT, True); key(nohome, e.BTN_START, True)
key(nohome, e.BTN_START, False)
check(f"...SELECT and START on their own: the terminal as you let go ({switches})", not m.active
      and switches == ["terminal"])
key(nohome, e.BTN_SELECT, False)
check("...the other let go: nothing more", not m.active and switches == ["terminal"])
key(nohome, e.BTN_SELECT, True); key(nohome, e.BTN_START, True)
check("...in the terminal: the menus at once", m.active and switches == ["terminal", "menu"])
key(nohome, e.BTN_START, False); key(nohome, e.BTN_SELECT, False)
switches.clear()

# ---- HOME held for ages: the next button is itself -------------------------------------------------------------------
g.HOT_HELD = 0.3
at_home()
key(pad, e.BTN_MODE, True)
wait(0.4)
tap(pad, e.BTN_SOUTH)
check(f"HOME held for ages, then A: A as itself (an app opened, no box) ({m.view})", m.view == "list"
      and m.konami_in is None)
key(pad, e.BTN_MODE, False)
check("...HOME let go: nothing", m.active and switches == [])
g.HOT_HELD = 10.0

done.set()
wait(0.5)
check(f"the main loop: no trouble ({errors})", not errors)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
