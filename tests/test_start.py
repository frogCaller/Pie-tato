"""Start-up: a fresh Pi opens on the home screen; Home goes to the console (the buttons are keys
there) and back; Settings > At start-up = Terminal starts in the console; no screen at all, the
console, and nothing goes wrong."""
import os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/tstartup"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
if hasattr(g, "STATIC"):
    g.STATIC = S + "/home/u/gpi-media/static"
ran = []
g.subprocess.run = lambda cmd, *a, **k: (ran.append(list(cmd)), type("R", (), {"stdout": "1", "returncode": 0})())[1]
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    bustype, vendor, product = 0x03, 1, 1


class FakeDev:
    def __init__(self, name, keys):
        self.driver, self.path, self.name, self.keys = "usbhid", "/dev/input/event70", name, keys
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
pad = FakeDev("GPi Case 2W gamepad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_SELECT, e.BTN_MODE])
g.list_devices = lambda: [pad.path]
g.InputDevice = lambda path: pad
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": 7})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)
g.subprocess.Popen = lambda *a, **k: None


class UI:
    def __init__(self):
        self.out = []

    def write(self, t, c, v):
        self.out.append((c, v))

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    frames = []

    def show(self, img):
        FB.frames.append(img.copy())

    def show_part(self, img, box):
        FB.frames.append(img.copy())

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


class NoScreen:
    def __init__(self):
        raise OSError(2, "No such file or directory: '/dev/fb0'")


def start(fb):
    """Power on: the service's main loop, as at start-up."""
    g.Framebuffer = fb
    FB.frames.clear(); ran.clear()
    ui, m, done, errors = UI(), g.Media(), threading.Event(), []

    def loop():
        try:
            g.run(ui, m, None, stop=done.is_set)
        except Exception as ex:
            import traceback; traceback.print_exc(); errors.append(ex)
    th = threading.Thread(target=loop, daemon=True); th.start(); time.sleep(0.6)
    return ui, m, done, th, errors


def press(code, sec=0.25):
    pad.send((e.EV_KEY, code, 1)); time.sleep(0.12); pad.send((e.EV_KEY, code, 0)); time.sleep(sec)


# a fresh Pi: nothing saved yet
check("nothing saved yet", not os.path.exists(g.STATE_FILE))
ui, m, done, th, errors = start(FB)
check(f"a fresh Pi starts on the home screen ({m.active}, {m.view})", m.active and m.view == "home")
check(f"...drawn ({len(FB.frames)} frames) and switched to its console", FB.frames
      and ["chvt", str(g.MEDIA_VT)] in ran)
check("Settings > At start-up says Home screen", m.setting("start") == "Home screen")
FB.frames[-1].save(SP + "/startup_home.png")
press(e.BTN_SOUTH)
check("its buttons work the apps, nothing typed", m.active and not ui.out)
press(e.BTN_MODE)
check(f"Home: the console ({m.active})", not m.active and ["chvt", "1"] in ran)
ui.out.clear()
press(e.BTN_SOUTH)
check(f"...where A is Enter ({ui.out})", (e.KEY_ENTER, 1) in ui.out and (e.KEY_ENTER, 0) in ui.out)
press(e.BTN_MODE)
check("Home again: back to the apps", m.active and m.view == "home")
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())

# Terminal chosen in Settings
si = m.tab_index("settings"); m.tab, m.view = si, "list"; m.load_tab(si)
m.set_sel = m.settings_root_index("start")
m.press("right")
check(f"Settings > At start-up: Terminal ({m.setting('start')})", m.setting("start") == "Terminal")
ui, m, done, th, errors = start(FB)
check(f"...and it starts in the console ({m.active}, {len(FB.frames)} frames)", not m.active and not FB.frames
      and ["chvt", str(g.MEDIA_VT)] not in ran)
ui.out.clear()
press(e.BTN_SOUTH)
check("...where A is Enter", (e.KEY_ENTER, 1) in ui.out)
press(e.BTN_MODE)
check("...and Home opens the apps", m.active and m.view == "home")
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())

# no screen at all (nothing on HDMI, no case screen): the console, as always
os.remove(g.STATE_FILE)
ui, m, done, th, errors = start(NoScreen)
check(f"no screen: it stays in the console ({m.active})", not m.active and m.fb is None)
ui.out.clear()
press(e.BTN_SOUTH)
check("...the buttons still work as keys", (e.KEY_ENTER, 1) in ui.out)
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
