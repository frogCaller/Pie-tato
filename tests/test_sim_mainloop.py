"""The Simulator's programs started as you start them: the real main loop, a controller's A on the program's row,
then 4 seconds of watching. Each must still be running, still drawing on its console (a pty here), with nothing of
media mode's drawn over it and nothing stopping it. On an 800x480 HDMI screen turned 180 degrees (the Waveshare's),
and on the GPi Case's 640x480."""
import json, os, pty, shutil, sys, threading, time, traceback
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t_simloop"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
real_run = g.subprocess.run
g.HW_DIR = S + "/hw"                     # (hollywood's own tmux: here, apart from a Pietato's on this machine)
g.subprocess.run = lambda cmd, *a, **k: (real_run(cmd, *a, **k) if isinstance(cmd, (list, tuple)) and cmd[:1] == ["tmux"]
                                         else type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})())
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


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
pad = FakeDev("Xbox Wireless Controller", FACE, {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0),
                                                 e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
g.list_devices = lambda: [pad.path]
g.InputDevice = lambda path: pad
real_stat = os.stat
g.os.stat = lambda q, *a, **k: type("St", (), {"st_ino": 7})() if q.startswith("/dev/input/") else real_stat(q, *a, **k)


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    shows = []

    def show(self, img): FB.shows.append(time.monotonic())
    def show_part(self, img, box): FB.shows.append(time.monotonic())
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
master, slave = pty.openpty()
g.PROG_TTY = os.ttyname(slave)
got = bytearray()


def drain():
    while True:
        try:
            b = os.read(master, 65536)
        except OSError:
            return
        if not b:
            return
        got.extend(b)


threading.Thread(target=drain, daemon=True).start()

stops = []
real_prog_stop = g.ProgScreen.prog_stop


stops_done = []                                  # (each stop, once it's over: hollywood's takes up to 3 s, its tmux
                                                 #  going, and the main loop's busy with it till then)


def prog_stop(self):
    if self.prog is not None:
        stops.append("".join(traceback.format_stack(limit=8)))
    try:
        return real_prog_stop(self)
    finally:
        stops_done.append(time.monotonic())


g.ProgScreen.prog_stop = prog_stop
m = g.Media(); m.enter()
done = threading.Event()


def loop():
    try:
        g.run(UI(), m, None, stop=done.is_set)
    except Exception:
        traceback.print_exc()


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.5)
si = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Simulator")

for label, size, turn in (("800x480 HDMI turned 180", (800, 480), 180), ("640x480", (640, 480), 0)):
    g.set_turn(turn)
    FB.real_w, FB.real_h = size
    for name in ("cmatrix", "nyancat", "htop", "cacafire", "hollywood"):
        if not g.shutil.which(name):
            print("(not here:", name, ")"); continue
        m.go_home() if hasattr(m, "go_home") else None
        m.tab, m.view = si, "list"
        m.load_tab(si)
        rows = m.items[si]
        k = next((i for i, r in enumerate(rows) if r.get("kind") == "child"
                  and g.LIBRARY[int(r["src"])].get("prog") == name), None)
        if k is None:
            check(f"{label}: {name} has a row in the Simulator", False); continue
        m.sels[si] = k
        m.dirty = True
        time.sleep(0.3)
        stops.clear()
        n0 = len(got)                            # (all it's drawn since it started: htop on a quiet machine draws
        pad.send((e.EV_KEY, e.BTN_SOUTH, 1)); time.sleep(0.12); pad.send((e.EV_KEY, e.BTN_SOUTH, 0))   # little after)
        time.sleep(0.3)
        p = m.prog
        if p is None:
            check(f"{label}: {name} started from its row ({m.msg})", False); continue
        s0 = len(FB.shows)
        time.sleep(4)
        still = m.prog is p and p.poll() is None
        drawn_over = len(FB.shows) - s0
        check(f"{label}: {name} still on 4 s after A ({'running' if still else 'ended: ' + str(p.returncode)}), "
              f"drawing ({len(got) - n0} bytes), media mode drew over it {drawn_over} times, stopped {len(stops)} times",
              still and len(got) - n0 > 500 and drawn_over == 0 and not stops)
        for s in stops[:1]:
            print(s)
        n_done = len(stops_done)
        pad.send((e.EV_KEY, e.BTN_EAST, 1)); time.sleep(0.12); pad.send((e.EV_KEY, e.BTN_EAST, 0))
        time.sleep(1.5)
        check(f"{label}: B stops {name}", m.prog is None)
        until = time.monotonic() + 5                 # (the stop over, before the next one's started)
        while len(stops_done) == n_done and time.monotonic() < until:
            time.sleep(0.05)
        time.sleep(0.2)

done.set()
time.sleep(0.3)
check("nothing of hollywood's left running (its tmux closed)", not g.hw_up())
g.hw_kill()
print("ALL OK" if all(ok_all) else "SOME FAILED")
