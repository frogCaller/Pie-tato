"""Two players, end to end: two controllers (fake input devices with the real evdev codes) in media mode's main loop,
a Genesis game in the real Genesis Plus GX (a tiny test game of our own: blue, red while player 1 holds B, green
while player 2 does, yellow for both). The controller that started the game is player 1, the next one pressed player
2; HOME's menu works from either; its Players picks again; one unplugged lets go and frees its place."""
import json, os, shutil, sys, threading, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t_two"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/genesis"):
    os.makedirs(f"{H}/{d}")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
shutil.copy(SP + "/sega/Pitato Sega Test (World).md", H + "/Games/genesis/Pitato Sega Test (World).md")
FBF = S + "/fb.bin"
W, HH = 640, 480
os.environ["PITATO_FB"] = f"{FBF}:{W}x{HH}:16"
open(FBF, "wb").write(bytes(W * HH * 2))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.SCAN_EVERY = 0.05
g.CORE_DIRS = (SP + "/sega/cores",)
g.screen_picture = lambda *a, **k: None
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
    """An input device: select() sees it through a pipe; read() hands out queued events."""
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
        if self.gone:
            raise OSError(19, "No such device")
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        self.closed = True


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


FACE = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_TL2, e.BTN_TR2,
        e.BTN_SELECT, e.BTN_START, e.BTN_MODE]
STICKS = lambda: {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_HAT0X: ai(-1, 1, 0),
                  e.ABS_HAT0Y: ai(-1, 1, 0)}
one = FakeDev("8BitDo SN30 Pro", FACE, STICKS(), vendor=0x2dc8, product=0x6101)
two = FakeDev("Xbox Wireless Controller", FACE, STICKS(), vendor=0x45e, product=0xb13)
three = FakeDev("Logitech Gamepad F310", FACE, STICKS(), vendor=0x46d, product=0xc21d)
plugged = [one, two]
devs = {d.path: d for d in (one, two, three)}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda q, *a, **k: type("St", (), {"st_ino": hash(q) % 1000})() if q.startswith("/dev/input/") else real_stat(q, *a, **k)


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
control = g.Control()
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.4)


def wait(sec=0.15):
    time.sleep(sec)


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def key(dev, code, down):
    dev.send((e.EV_KEY, code, 1 if down else 0)); wait()


def tap(dev, code):
    key(dev, code, True); key(dev, code, False)


def hat(dev, axis, v):
    dev.send((e.EV_ABS, axis, v)); wait(); dev.send((e.EV_ABS, axis, 0)); wait()


def colour():
    a = int(np.fromfile(FBF, dtype="<u2").reshape(HH, W)[240, 320])
    r, gr, b = (((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3)
    return {(True, False, False): "red", (False, True, False): "green", (False, False, True): "blue",
            (True, True, False): "yellow", (False, False, False): "black"}.get((r > 128, gr > 128, b > 128), str((r, gr, b)))


B, A, HOME = e.BTN_EAST, e.BTN_SOUTH, e.BTN_MODE
check("both controllers found", until(lambda: sorted(m.pads.by_path) == sorted([one.path, two.path]), 3))
gi = m.tab_index("games")
m.open_app(gi)
rows = m.tab_items(gi)
row = next(k for k, it in enumerate(rows) if it.get("kind") == "game")
m.sels[gi] = row
m.dirty = True
tap(one, A)                                            # the first controller starts it
check("the game starts, from the first controller", until(lambda: m.game is not None and m.game.state == "on", 20)
      and m.view == "game")
check(f"...its picture: blue ({colour()})", until(lambda: colour() == "blue"))
check("...that controller is player 1", m.game_players == {one.path: 0})
key(one, B, True)
check(f"player 1 holds B: red ({colour()})", until(lambda: colour() == "red"))
key(two, B, True)
check(f"the other controller holds B too: it's player 2, yellow ({colour()})", until(lambda: colour() == "yellow")
      and m.game_players.get(two.path) == 1)
key(one, B, False)
check(f"player 1 lets go: green ({colour()})", until(lambda: colour() == "green"))
key(two, B, False)
check(f"...both let go: blue ({colour()})", until(lambda: colour() == "blue"))

tap(two, HOME)                                         # HOME on player 2's: the menu
check("HOME on player 2's controller: the game's menu", until(lambda: m.view == "gamemenu", 3))
items = [k for k, _ in m.game_menu_items()]
check(f"...with Players, saying 2 of 2 ({m.game_value('players')})", "players" in items
      and m.game_value("players") == "2 of 2")
for _ in range(items.index("players")):
    hat(two, e.ABS_HAT0Y, 1)
check("...down to it", m.game_menu and m.game_menu_items()[m.game_menu["sel"]][0] == "players")
tap(two, A)
check(f"...A: picked again ({m.msg})", m.game_players == {} and "player 1 first" in (m.msg or ""))
tap(two, B)
check("B: back to the game", until(lambda: m.view == "game" and m.game.state == "on", 3))
key(two, B, True)
check(f"the first to press is player 1 now: red ({colour()})", until(lambda: colour() == "red")
      and m.game_players == {two.path: 0})
key(one, B, True)
check(f"...the next player 2: yellow ({colour()})", until(lambda: colour() == "yellow")
      and m.game_players.get(one.path) == 1)
one.gone = True; plugged.remove(one); one.send(); wait(0.3)
check(f"player 2's unplugged as they hold B: let go of, red ({colour()})", until(lambda: colour() == "red")
      and one.path not in m.pads.by_path)
key(two, B, False)
check(f"...blue ({colour()})", until(lambda: colour() == "blue"))
plugged.append(three)
check("another controller plugged in", until(lambda: three.path in m.pads.by_path, 3))
key(three, B, True)
check(f"...it takes player 2's place: green ({colour()})", until(lambda: colour() == "green")
      and m.game_players.get(three.path) == 1)
key(three, B, False)
check(f"...blue ({colour()})", until(lambda: colour() == "blue"))

tap(three, HOME)
check("HOME: the menu", until(lambda: m.view == "gamemenu", 3))
items = [k for k, _ in m.game_menu_items()]
for _ in range(len(items) - 1):
    hat(three, e.ABS_HAT0Y, 1)
check("...down to Quit game", m.game_menu_items()[m.game_menu["sel"]][0] == "quit")
tap(three, A)
check("...quit", until(lambda: m.game is None and m.view == "list", 8))
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
