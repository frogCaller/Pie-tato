"""The Simulator in the real main loop, in real time: opened with the d-pad from the home screen, Rock
Paper Scissors runs at about SIM_FPS frames a second, mostly sending just its box; START's card stops
the frames; leaving it stops them too; full screen; Forest Fire keeps up full screen too, and so does the
Mandelbrot Set while its own thread works out its pictures. Exploring it: buttons held down (no key
repeat), and the web page's remote, a press at a time or held."""
import os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/tsimloop"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
if hasattr(g, "STATIC"):
    g.STATIC = S + "/home/u/gpi-media/static"
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.subprocess.Popen = lambda *a, **k: None
g.SCAN_EVERY = 0.05
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    bustype, vendor, product = 0x03, 1, 1


class Pad:
    def __init__(self, keys):
        self.driver, self.path, self.name, self.keys = "usbhid", "/dev/input/event71", "Test pad", keys
        self.info = Info()
        self.r, self.w = os.pipe()
        self.q = []

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
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        pass


g.input_driver = lambda dev: dev.driver
pad = Pad([e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_START, e.BTN_SELECT, e.BTN_MODE,
           e.BTN_TL, e.BTN_TR, e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT])
g.list_devices = lambda: [pad.path]
g.InputDevice = lambda path: pad
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": 9})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


class FB:
    w, h, same = 640, 480, True
    real_w, real_h = 640, 480
    log = []                     # (when, "whole" or the box)
    count = 0

    def __init__(self):
        self.frames = 0

    def show(self, img):
        FB.log.append((time.monotonic(), "whole"))
        FB.count += 1; self.frames = FB.count; self.last = img

    def show_part(self, img, box):
        FB.log.append((time.monotonic(), tuple(box)))
        FB.count += 1; self.frames = FB.count; self.last = img

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
done, errors = threading.Event(), []
ctl = g.Control()


def loop():
    try:
        g.run(UI(), m, ctl, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.6)


def press(code, sec=0.2):
    pad.send((e.EV_KEY, code, 1)); time.sleep(0.06); pad.send((e.EV_KEY, code, 0)); time.sleep(sec)


def since(t0):
    return [b for t, b in FB.log if t >= t0]


check("the home screen at start-up", m.active and m.view == "home")
apps = [a for a, _ in m.home_apps()]
row, col = divmod(apps.index("Simulator"), 5)
for _ in range(row):
    press(e.BTN_DPAD_DOWN)
for _ in range(col):
    press(e.BTN_DPAD_RIGHT)
check(f"the d-pad to its icon ({apps[m.home_sel]})", apps[m.home_sel] == "Simulator")
press(e.BTN_SOUTH, 0.3)
check("A opens it: the list of sims", m.tab_type() == "group" and g.LIBRARY[m.tab]["name"] == "Simulator")
SIMI = m.tab
press(e.BTN_DPAD_DOWN, 0.2)                    # (past the Clock)
press(e.BTN_SOUTH, 0.3)
check("A again: Rock Paper Scissors", m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "rps")
G = m.sims["rps"]
press(e.BTN_SOUTH, 0.1)                        # (start now)
t0 = time.monotonic()
time.sleep(2.0)
got = since(t0)
fps = len(got) / 2.0
small = sum(b == g.SIM_BOX for b in got)
check(f"{fps:.1f} frames a second ({len(got)} in 2 s)", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2)
check(f"...{small} of them just the box, {got.count('whole')} whole", small >= 0.6 * len(got) and got.count("whole") <= 2)
check(f"...it plays: {G.captures} captures by now", G.phase == "on" and G.clock > 1.5)
press(e.BTN_START, 0.3)
t0 = time.monotonic()
time.sleep(1.0)
check(f"START's card: no frames meanwhile ({len(since(t0))})", m.sim_opts == 0 and len(since(t0)) == 0)
press(e.BTN_DPAD_DOWN); press(e.BTN_DPAD_DOWN); press(e.BTN_DPAD_RIGHT)
check(f"...Speed: {m.setting('sim_rps_speed')}", m.setting("sim_rps_speed") == "Fast" and G.speed == 120)
press(e.BTN_EAST, 0.3)
check("B closes it, and on it goes", m.sim_opts is None and len(since(time.monotonic() - 0.25)) >= 2)
clock = G.clock
press(e.BTN_TR, 0.3)
check("R: the next app, Files", g.LIBRARY[m.tab]["name"] == "Files")
press(e.BTN_TR, 0.3)
t0 = time.monotonic()
time.sleep(1.0)
check(f"R again: System; the game waits, no more frames ({len(since(t0))})",
      m.tab_type() == "system" and len(since(t0)) <= 2 and G.clock - clock < 0.5)
press(e.BTN_TL, 0.3)
press(e.BTN_TL, 0.4)
check("L, L: back to the Simulator's list", m.tab == SIMI)
press(e.BTN_SOUTH, 0.5)
check("...A: and on it goes", m.tab_type() == "sim" and G.clock > clock)
press(e.BTN_SELECT, 0.4)
check("SELECT: full screen", m.sim_full() and (G.w, G.h) == (640, 480))
t0 = time.monotonic()
time.sleep(2.0)
got = since(t0)
fps = len(got) / 2.0
check(f"...{fps:.1f} frames a second, each the whole screen", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2
      and all(b == "whole" for b in got))
press(e.BTN_EAST, 0.3)
for _ in range(2):
    press(e.BTN_DPAD_DOWN)
press(e.BTN_SOUTH, 0.5)
check(f"B, down to Forest Fire, A: full screen too ({g.LIBRARY[m.tab]['name']})",
      m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "fire" and m.sim_full())
t0 = time.monotonic()
time.sleep(2.0)
fps = len(since(t0)) / 2.0
check(f"...it keeps up: {fps:.1f} frames a second", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2)
press(e.BTN_SELECT, 0.4)
check("SELECT: back beside its numbers", not m.sim_full() and (m.sims["fire"].w, m.sims["fire"].h) == (436, 342))
press(e.BTN_EAST, 0.3)
press(e.BTN_DPAD_DOWN)
press(e.BTN_SOUTH, 0.5)
check(f"B, down to the Mandelbrot Set, A ({g.LIBRARY[m.tab]['name']})",
      m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "mandel")
Mb = m.sims["mandel"]
t0 = time.monotonic()
time.sleep(3.0)
fps = len(since(t0)) / 3.0
check(f"...it keeps up while its thread works out its pictures: {fps:.1f} frames a second (levels {sorted(Mb.levels)})",
      g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2 and len(Mb.levels) >= 2 and Mb.L > 0.2)
press(e.BTN_SELECT, 0.4)
t0 = time.monotonic()
time.sleep(3.0)
fps = len(since(t0)) / 3.0
check(f"...full screen too: {fps:.1f} frames a second (levels {sorted(Mb.levels)} at {Mb.w} x {Mb.h})",
      g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2 and (Mb.w, Mb.h) == (640, 480) and Mb.levels)
press(e.BTN_SELECT, 0.4)

# exploring: the d-pad and A and Y, held
Mb.finish()
time.sleep(0.3)
cx, cy, W = Mb.here()
L0 = Mb.L
t0 = time.monotonic()
pad.send((e.EV_KEY, e.BTN_DPAD_RIGHT, 1)); time.sleep(1.0); pad.send((e.EV_KEY, e.BTN_DPAD_RIGHT, 0)); time.sleep(0.2)
moved = (Mb.here()[0] - cx) / W
fps = len(since(t0)) / 1.2
check(f"right, held: exploring from where the tour was, on that way ({moved:.2f} of the view), {fps:.1f} frames a second",
      Mb.phase == "explore" and m.setting("sim_mandel_mode") == "Explore" and 0.5 <= moved <= 0.85
      and g.SIM_FPS - 4 <= fps <= g.SIM_FPS + 2)
here = Mb.here()
time.sleep(0.4)
check("...let go: it stays put", Mb.here() == here and not Mb.held)
pad.send((e.EV_KEY, e.BTN_SOUTH, 1)); time.sleep(1.0); pad.send((e.EV_KEY, e.BTN_SOUTH, 0)); time.sleep(0.2)
check(f"A, held: in ({Mb.L - L0:.2f} levels)", 0.9 <= Mb.L - L0 <= 1.45)
L1 = Mb.L
pad.send((e.EV_KEY, e.BTN_WEST, 1)); time.sleep(0.5); pad.send((e.EV_KEY, e.BTN_WEST, 0)); time.sleep(0.2)
check(f"Y, held: out ({L1 - Mb.L:.2f} levels)", 0.4 <= L1 - Mb.L <= 0.85)
x0 = Mb.here()[0]
ctl.ask({"cmd": "press", "button": "left"})
step = (x0 - Mb.here()[0]) / Mb.here()[2]
for _ in range(5):
    ctl.ask({"cmd": "press", "button": "left", "repeat": True})
steps = (x0 - Mb.here()[0]) / Mb.here()[2]
check(f"the web page's remote: a press, a small step ({step:.2f}); held, a step each time ({steps:.2f})",
      abs(step - 0.08) < 1e-6 and abs(steps - 0.48) < 1e-6 and not Mb.held)
L2 = Mb.L
for _ in range(4):
    ctl.ask({"cmd": "press", "button": "a", "repeat": True})
check(f"...A held there: in a little each time ({Mb.L - L2:.2f})", abs(Mb.L - L2 - 0.6) < 1e-6)
press(e.BTN_START, 0.3)
press(e.BTN_DPAD_RIGHT)
press(e.BTN_EAST, 0.4)
check("START, Mode: back on the tour", Mb.phase == "dive" and m.setting("sim_mandel_mode") == "Tour")
for _ in range(3):
    ctl.ask({"cmd": "press", "button": "a", "repeat": True})
check("...where A held on the web page is just the one press", not Mb.paused)
press(e.BTN_MODE, 0.4)
t0 = time.monotonic()
time.sleep(0.6)
check(f"Home: the console, nothing drawn ({len(since(t0))})", not m.active and len(since(t0)) == 0)
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
