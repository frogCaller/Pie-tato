"""The case's power switch: found among the input devices, and switched off it shuts the Pi down,
in the terminal (no drawing, systemd's own lines) and in media mode ('Shutting down' that stays)."""
import io, os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/t60"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')   # (this one starts in the terminal)
g.home_dir = lambda: S + "/home/u"
if hasattr(g, "STATIC"):
    g.STATIC = S + "/home/u/gpi-media/static"
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, bustype, vendor=1, product=1):
        self.bustype, self.vendor, self.product = bustype, vendor, product


class FakeDev:
    n = 100

    def __init__(self, name, keys, bustype=0x19, driver=None):
        FakeDev.n += 1
        self.driver = ("gpio-keys" if bustype == 0x19 else "usbhid") if driver is None else driver
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys = name, keys
        self.info = Info(bustype)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)} if self.keys else {}

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


# ---- which devices are a power switch ------------------------------------------------------------
g.input_driver = lambda dev: dev.driver
switch = FakeDev("shutdown_button@1a", [e.KEY_POWER])
pi5 = FakeDev("pwr_button", [e.KEY_POWER])
usb_kbd = FakeDev("USB keyboard with a power key", [e.KEY_A, e.KEY_POWER], bustype=0x03)
plain = FakeDev("gpio_keys", [e.KEY_VOLUMEUP])
check("the gpio-shutdown overlay's key is the power switch", g.is_power_switch(switch))
check("a USB keyboard's power key isn't", not g.is_power_switch(usb_kbd) and not g.is_power_switch(usb_kbd, True))
check("another power key on the Pi's pins only counts on a GPi Case",
      not g.is_power_switch(pi5) and g.is_power_switch(pi5, gpi=True))
check("keys on the Pi's pins without a power key don't", not g.is_power_switch(plain, gpi=True))
ir = FakeDev("gpio_ir_recv", [e.KEY_POWER, e.KEY_VOLUMEUP], driver="")
check("a remote's power button (an IR receiver on the Pi's pins) never does", not g.is_power_switch(ir, gpi=True))
named = FakeDev("shutdown_button@3", [e.KEY_POWER], driver="")
check("...nor anything without the gpio-keys driver, whatever its name", not g.is_power_switch(named, gpi=True))
check("a device without bus info doesn't (and doesn't fail)",
      not g.is_power_switch(type("D", (), {"path": "/dev/input/event9", "name": "x", "info": None})()))

cfg = S + "/config.txt"
open(cfg, "w").write("[all]\n# >>> gpi-case setup >>>\ndtoverlay=gpicase-dpi\n# <<< gpi-case setup <<<\n")
g.CONFIG_TXT = (S + "/missing.txt", cfg)
check("a GPi Case set up by setup.sh is told from config.txt", g.gpi_case_set_up())
open(cfg, "w").write("[all]\ndtoverlay=vc4-kms-v3d\n")
check("...and any other Pi isn't", not g.gpi_case_set_up())

# ---- the main loop, with the switch plugged in -------------------------------------------------------
pad = FakeDev("GPi Case 2W gamepad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_SELECT], bustype=0x03)
plugged = [pad, switch, usb_kbd]
devs = {d.path: d for d in [pad, switch, usb_kbd, pi5]}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)

popens, lines_shown, stopping = [], [], {"now": False}


class FakePopen:
    def __init__(self, cmd, *a, **k):
        popens.append(list(cmd))


g.subprocess.Popen = FakePopen
g.show_shutdown_lines = lambda: lines_shown.append(time.monotonic())
g.system_stopping = lambda: stopping["now"]


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
    frames = []

    def show(self, img):
        FB.frames.append(img.copy())

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
ui = UI()
m = g.Media()
done = threading.Event()
errors = []


def loop():
    try:
        g.run(ui, m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


out = io.StringIO()
real_stdout = sys.stdout
th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.4)
check("the switch is watched, not taken for a controller",
      list(m.pads.power) == [switch.path] and switch.path not in m.pads.by_path and not switch.closed)
check("the USB keyboard isn't watched", usb_kbd.path not in m.pads.power)


def wait(sec=0.15):
    time.sleep(sec)


# terminal mode: switched off
check("terminal mode to start with", not m.active)
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("terminal: switched off -> systemctl poweroff", popens == [["systemctl", "poweroff"]])
check("terminal: systemd's own lines asked for, nothing drawn", len(lines_shown) == 1 and not FB.frames)
check("terminal: no keys typed for it", ui.out == [])
switch.send((e.EV_KEY, e.KEY_POWER, 0)); wait()
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("switched on and off again while it's going: once is enough", len(popens) == 1)

# media mode: switched off
m.halting = 0.0
popens.clear(); lines_shown.clear()
m.enter(); wait(0.3)
check("media mode open", m.active and FB.frames)
FB.frames.clear()
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("media: switched off -> systemctl poweroff", popens == [["systemctl", "poweroff"]])
check("media: 'Shutting down' drawn, no console lines asked for", len(FB.frames) == 1 and not lines_shown)
FB.frames[-1].save(SP + "/power_media.png")
n = len(FB.frames)
m.toast("Something new", 3); m.dirty = True; wait(0.3)
check("media: nothing draws over 'Shutting down'", len(FB.frames) == n)
view = (m.view, m.tab, m.active)
pad.send((e.EV_KEY, e.BTN_SOUTH, 1)); wait(); pad.send((e.EV_KEY, e.BTN_SOUTH, 0)); wait()
pad.send((e.EV_KEY, e.BTN_START, 1)); wait(); pad.send((e.EV_KEY, e.BTN_START, 0)); wait(0.5)
check("media: the controller's presses go nowhere while it shuts down",
      (m.view, m.tab, m.active) == view and len(FB.frames) == n and not popens[1:])

# the web page is told
control = g.Control()
server = g.serve_control(m, control, port=0)
import json, urllib.request
done.set(); th.join(2); done.clear()
th = threading.Thread(target=lambda: g.run(ui, m, control, stop=done.is_set), daemon=True); th.start(); wait(0.3)
key = open(g.CONTROL_KEY).read().strip() if os.path.exists(g.CONTROL_KEY) else ""
req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/press", data=json.dumps({"button": "b"}).encode(),
                             headers={"Content-Type": "application/json", "X-Pitato-Key": key})
try:
    got = json.loads(urllib.request.urlopen(req, timeout=10).read())
except urllib.error.HTTPError as ex:
    got = json.loads(ex.read() or b"{}")
check(f"the web page's remote is told it's shutting down: {got}", got.get("error") == "The Pi is shutting down"
      and len(FB.frames) == n)

# the Pi didn't go: after a while the menu comes back and says so
m.halting = time.monotonic() + 0.2; wait(0.5)
check("still here later: the menu's back, saying it didn't shut down",
      len(FB.frames) > n and m.msg == "The Pi didn't shut down")

# systemd-logind got there first: no second poweroff
m.halting = 0.0
popens.clear()
stopping["now"] = True
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("already shutting down: no second poweroff", popens == [])
stopping["now"] = False

# Shut down in the menu: 'Shutting down' stays put too
m.halting = 0.0
popens.clear(); FB.frames.clear()
m.confirm = ("poweroff", time.monotonic() + 4)
m.system_action({"src": "poweroff"})
n = len(FB.frames)
m.dirty = True; wait(0.3)
check("menu's Shut down: poweroff, and nothing draws over it",
      popens == [["systemctl", "poweroff"]] and n == 1 and len(FB.frames) == 1)

# the switch unplugged (the overlay removed, say): dropped quietly
switch.gone = True; plugged.remove(switch); switch.send(); wait(0.3)
check("a switch that's gone is dropped", switch.path not in m.pads.power and not errors)
done.set(); th.join(2)
check("no errors in the loop", not errors)

# ---- a GPi Case without the switch: said once ---------------------------------------------------------
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sel = g.selectors.DefaultSelector()
    open(cfg, "w").write("# >>> gpi-case setup >>>\n")
    plugged[:] = [pad]
    pads = g.Pads(sel)
    pads.scan(time.monotonic(), force=True)
    pads.scan(time.monotonic(), force=True)
check("GPi Case, no switch found: said once", buf.getvalue().count("power switch: not found") == 1)

# ---- the real show_shutdown_lines: only ever signals systemd -------------------------------------------
import importlib
gk = importlib.reload(g)
sent = []
gk.os.kill = lambda pid, sig: sent.append((pid, sig))
gk.show_shutdown_lines()
first = open("/proc/1/comm").read().strip()
check("PID 1 isn't systemd here: no signal sent" if first != "systemd" else "systemd: SIGRTMIN+20",
      sent == ([] if first != "systemd" else [(1, gk.signal.SIGRTMIN + 20)]))

print("ALL OK" if all(ok_all) else "FAILED")
