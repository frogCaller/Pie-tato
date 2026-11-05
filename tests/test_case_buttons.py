"""A GPi Case's own buttons (a USB controller inside it) that don't come on as it starts, now and then: with no USB
controller a while after start-up, the case's USB is unplugged and plugged in again (each bus's root hub turned off,
then on: its "authorized" in sysfs), twice at most, and what was there (input devices, USB, the kernel's words) goes
to the log first. The screen says it's looking again, and "... connected" once they're back; still not back, it says
to switch it off and on. There at start-up, or not a GPi Case: nothing's done. A Bluetooth controller doesn't count
(the case's own are USB)."""
import io, json, os, selectors, shutil, sys, threading, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g  # noqa: E402
from evdev import ecodes as e  # noqa: E402

S = SP + "/t_case_buttons"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
USB = S + "/usb"
for name, vid, pid, product in (("usb1", "1d6b", "0002", "DWC OTG Controller"),):
    os.makedirs(f"{USB}/{name}")
    for k, v in (("authorized", "1"), ("idVendor", vid), ("idProduct", pid), ("product", product)):
        open(f"{USB}/{name}/{k}", "w").write(v + "\n")
os.makedirs(f"{USB}/1-0:1.0")                     # (the root hub's interface: not a device of its own)
open(S + "/input_devices", "w").write('I: Bus=0019\nN: Name="gpio_keys"\n\nI: Bus=0006\nN: Name="pitato"\n')
g.USB_DEVICES, g.INPUT_LIST, g.REPLUG_GAP = USB, S + "/input_devices", 0.3
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: HOME
DMESG = ("[    3.104] usb 1-1: device descriptor read/64, error -71\n[    3.512] mmc1: new high speed SDIO card\n"
         "[    3.990] usb usb1-port1: unable to enumerate USB device\n")


class R:
    def __init__(self, stdout="1"):
        self.stdout, self.returncode = stdout, 0


g.subprocess.run = lambda cmd, *a, **k: R(DMESG) if list(cmd)[:1] == ["dmesg"] else R()
g.SCAN_EVERY = 0.05
ok_all = []


class Tee(io.TextIOBase):
    """What's printed, kept too (the log)."""
    def __init__(self, out):
        self.out, self.kept = out, []

    def write(self, s):
        self.kept.append(s)
        return self.out.write(s)

    def flush(self):
        self.out.flush()

    def text(self):
        return "".join(self.kept)


log = Tee(sys.stdout)
sys.stdout = log


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, bustype, vendor=1, product=1):
        self.bustype, self.vendor, self.product = bustype, vendor, product


class FakeDev:
    n = 500

    def __init__(self, name, keys, bustype, driver=""):
        FakeDev.n += 1
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys, self.driver = name, keys, driver
        self.info = Info(bustype)
        self.r, self.w = os.pipe()
        self.q, self.closed = [], False

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
        self.closed = True


PAD_KEYS = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_SELECT]
devs = {}
g.list_devices = lambda: list(devs)
g.InputDevice = lambda path: devs[path]
g.input_driver = lambda dev: dev.driver
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if str(p).startswith("/dev/input/") \
    else real_stat(p, *a, **k)


def plug(*more):
    devs.clear()
    switch = FakeDev("gpio_keys", [e.KEY_POWER], 0x19, "gpio-keys")
    devs[switch.path] = switch
    for d in more:
        devs[d.path] = d


def case_pad():
    return FakeDev("GPi Case gamepad", PAD_KEYS, 0x03)


seen = []                                        # what the root hub's "authorized" was, as it went
replugs = []                                     # the replugs done, and what came back after each
back_after = {"n": 0}                            # the replug that brings the case's buttons back (0: none does)
real_replug = g.usb_replug


def watch():
    while True:
        try:
            v = open(f"{USB}/usb1/authorized").read().strip()
        except OSError:
            v = "?"
        if not seen or seen[-1] != v:
            seen.append(v)
        time.sleep(0.01)


threading.Thread(target=watch, daemon=True).start()


def replug():
    ok = real_replug()
    replugs.append(ok)
    if back_after["n"] and len(replugs) >= back_after["n"]:
        d = case_pad()
        devs[d.path] = d                         # (the kernel finds it, now it's looked at afresh)
    return ok


g.usb_replug = replug


def replug_done(n, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end and len(replugs) < n:
        time.sleep(0.02)
    time.sleep(0.05)
    return len(replugs) >= n


def pads_now(gpi):
    g.gpi_case_set_up = lambda: gpi
    sel = selectors.DefaultSelector()
    return g.Pads(sel), time.monotonic()


W = g.CASE_WAIT

# ---- not a GPi Case: nothing done ------------------------------------------------------------------------------------
plug()
replugs.clear()
pads, t0 = pads_now(False)
for dt in (0, W + 1, 2 * W + 1, 3 * W + 1):
    pads.scan(t0 + dt, force=True)
time.sleep(0.2)
check("not a GPi Case: no controller, and its USB is left alone", replugs == [] and pads.notice is None)

# ---- a GPi Case, its buttons there as it starts ----------------------------------------------------------------------
plug(case_pad())
pads, t0 = pads_now(True)
new = pads.scan(t0, force=True)
for dt in (W / 2, W + 1, 2 * W + 1, 3 * W + 1):
    pads.scan(t0 + dt, force=True)
time.sleep(0.2)
check(f"a GPi Case, its buttons there as it starts: found, and nothing else done ({[p.dev.name for p in new]})",
      len(new) == 1 and replugs == [] and pads.notice is None and pads.case_next is None)

# ---- not there as it starts: looked for again, and back --------------------------------------------------------------
plug()
seen.clear()
back_after["n"] = 1
log.kept.clear()
pads, t0 = pads_now(True)
pads.scan(t0, force=True)
pads.scan(t0 + W / 2, force=True)
check("a GPi Case with its buttons not there as it starts: a while's wait first (they may come on late)",
      replugs == [] and pads.notice is None)
pads.scan(t0 + W + 1, force=True)
done = replug_done(1)
check(f"...then the screen says it's looking again ({pads.notice!r})",
      done and "looking for them again" in str(pads.notice))
went = [v for v in seen if v]                    # (read as it was being written: nothing in it, for a moment)
check(f"...and the case's USB is unplugged and plugged in again: its root hub off, a moment, then on ({went})",
      "0" in went and went[-1] == "1" and went.index("0") < len(went) - 1)
text = log.text()
check("...what was there written to the log first: the input devices, what's on USB and the kernel's words about USB",
      "the case's buttons: not there" in text and "gpio_keys" in text and "usb1 1d6b:0002 DWC OTG Controller" in text
      and "1-0:1.0" not in text and "unable to enumerate USB device" in text and "mmc1" not in text
      and "(1 of 2)" in text)
new = pads.scan(t0 + W + 2, force=True)
check(f"...and its buttons, back, are found ({[p.dev.name for p in new]})",
      [p.dev.name for p in new] == ["GPi Case gamepad"])
for dt in (2 * W + 2, 3 * W + 2, 4 * W + 2):
    pads.scan(t0 + dt, force=True)
time.sleep(0.2)
check(f"...nothing more done once they're back ({len(replugs)} replug)", len(replugs) == 1 and pads.case_next is None)

# ---- a Bluetooth controller doesn't count ----------------------------------------------------------------------------
plug(FakeDev("8BitDo SN30 Pro", PAD_KEYS, 0x05))
replugs.clear()
back_after["n"] = 1
pads, t0 = pads_now(True)
new = pads.scan(t0, force=True)
pads.scan(t0 + W + 1, force=True)
replug_done(1)
new2 = pads.scan(t0 + W + 2, force=True)
check(f"a Bluetooth controller there, but not the case's own: still looked for, and found "
      f"({[p.dev.name for p in new]}, then {[p.dev.name for p in new2]})",
      len(new) == 1 and len(replugs) == 1 and [p.dev.name for p in new2] == ["GPi Case gamepad"])

# ---- never back: twice, then switch it off and on --------------------------------------------------------------------
plug()
replugs.clear()
back_after["n"] = 0
log.kept.clear()
pads, t0 = pads_now(True)
pads.scan(t0, force=True)
pads.scan(t0 + W + 1, force=True)
replug_done(1)
first = pads.notice
pads.notice = None                               # (said)
pads.scan(t0 + W + 2, force=True)
pads.scan(t0 + 2 * W + 2, force=True)
replug_done(2)
check(f"not back after it: plugged in again once more, a while later, without saying so again ({len(replugs)})",
      len(replugs) == 2 and pads.notice is None and "(2 of 2)" in log.text())
pads.scan(t0 + 3 * W + 3, force=True)
check(f"...still not back: the screen says to switch it off and on again ({pads.notice!r})",
      "switch it off and on again" in str(pads.notice) and "still not there" in log.text())
for dt in (4 * W + 3, 6 * W + 3, 9 * W + 3):
    pads.scan(t0 + dt, force=True)
time.sleep(0.2)
check(f"...and that's all: twice at most ({len(replugs)})", len(replugs) == 2 and pads.case_next is None)

# ---- the real thing: Pietato starting, the screen saying so ----------------------------------------------------------
g.CASE_WAIT = 0.6
json.dump({"settings": {"start": "Home screen"}}, open(g.STATE_FILE, "w"))


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    def show(self, img): pass
    def show_part(self, img, box): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
g.subprocess.Popen = lambda *a, **k: type("P", (), {"pid": 0, "poll": lambda me: 0, "wait": lambda me, t=None: 0})()
g.show_shutdown_lines = lambda: None
g.system_stopping = lambda: False
plug()
replugs.clear()
back_after["n"] = 1
g.gpi_case_set_up = lambda: True
m = g.Media()
said = []
real_toast = m.toast
m.toast = lambda text, *a, **k: (said.append(text), real_toast(text, *a, **k))
stop = threading.Event()
th = threading.Thread(target=lambda: g.run(UI(), m, None, stop=stop.is_set), daemon=True)
th.start()
end = time.monotonic() + 8
while time.monotonic() < end and not any("connected" in s for s in said):
    time.sleep(0.05)
check(f"Pietato starting in a GPi Case whose buttons don't come on: the screen says it's looking again, then that "
      f"they're connected ({said})", m.active and len(said) >= 2 and "looking for them again" in said[0]
      and said[-1] == "GPi Case gamepad connected" and len(replugs) == 1)
pad = next(iter(m.pads.by_path.values()), None)
pressed = []
real_press = m.press
m.press = lambda name, *a, **k: (pressed.append(name), real_press(name, *a, **k))[1]
if pad is not None:
    pad.dev.send((e.EV_KEY, e.BTN_SOUTH, 1), (e.EV_SYN, 0, 0))
    pad.dev.send((e.EV_KEY, e.BTN_SOUTH, 0), (e.EV_SYN, 0, 0))
end = time.monotonic() + 3
while time.monotonic() < end and "a" not in pressed:
    time.sleep(0.05)
check(f"...and its buttons work ({pressed})", "a" in pressed)
stop.set()
th.join(3)

sys.stdout = log.out
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
