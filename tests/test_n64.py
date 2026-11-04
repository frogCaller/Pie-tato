"""N64 games: the real Mupen64Plus-Next (built here; it draws with Mesa's llvmpipe as a Pi 4 draws with its V3D
chip) and Peter Lemon's free test ROMs (public domain). In the emulator's process: frames drawn by the graphics
chip reaching the screen (16-bit, 32-bit, and a big screen the chip scales to), the d-pad, save states, picking
up where you left off, a zip, a .v64, a broken game, no 3D at all. In-process: the sticks, read back from the
N64's own controller reply, and the stick lines. Then media mode: the Games list, a Pi too old, the buttons by
letter, the sticks from controllers (two sticks, none, no L2), the menu letting go of them. Then the real loop."""
import os, shutil, signal, subprocess, sys, threading, time, types, zipfile, array
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM, gpu as GPUM
from evdev import ecodes as e
try:
    from evdev import AbsInfo
except ImportError:                     # (the stand-in evdev the Pi's Python runs these with)
    from collections import namedtuple
    AbsInfo = namedtuple("AbsInfo", "value min max fuzz flat resolution")

S = SP + "/tn64"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/n64")
os.makedirs(S + "/home/u/Games/BIOS")
os.makedirs(S + "/bin")
os.makedirs(S + "/cores")
shutil.copy(SP + "/n64/cores/mupen64plus_next_libretro.so", S + "/cores/")
L = SP + "/peterlemon/n64"                 # (Peter Lemon's test programs: an asset)
N64 = S + "/home/u/Games/n64"
shutil.copy(L + "/Input/RDP/InputRDP.N64", N64 + "/InputRDP.z64")
shutil.copy(L + "/Input/CPU/InputCPU.N64", N64 + "/InputCPU.z64")
rdp = open(L + "/Input/RDP/InputRDP.N64", "rb").read()
v = array.array("H"); v.frombytes(rdp); v.byteswap()
open(N64 + "/Swapped.v64", "wb").write(v.tobytes())
with zipfile.ZipFile(N64 + "/Zipped.zip", "w") as z:
    z.write(L + "/Input/RDP/InputRDP.N64", "inside/Zipped.z64")
open(N64 + "/Broken.z64", "wb").write(b"not an N64 game" * 400)
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat >> "$GPI_TEST_SOUND"\n')
os.chmod(S + "/bin/aplay", 0o755)
FBF = S + "/fb.bin"
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["GPI_TEST_SOUND"] = S + "/sound.raw"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
g.CORE_DIRS = (S + "/cores",) + tuple(GM.CORE_DIRS)
g.slow_pi = lambda: False
GAMES = S + "/home/u/Games"
SAVES = GAMES + "/Saves"
CORE = S + "/cores/mupen64plus_next_libretro.so"
ok_all, runs = [], []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=10):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


def screen_as(bits, w=640, h=480):
    os.environ["PITATO_FB"] = f"{FBF}:{w}x{h}:{bits}"
    open(FBF, "wb").write(bytes(w * h * bits // 8))
    return bits, w, h


def frame(spec):
    bits, w, h = spec
    a = np.fromfile(FBF, dtype="<u2" if bits == 16 else "<u4").reshape(h, w).astype(np.uint32)
    if bits == 16:
        return np.stack([((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3], -1)
    return np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255], -1)


def yellow(rgb):
    return (rgb[..., 0] > 200) & (rgb[..., 1] > 200) & (rgb[..., 2] < 60)


def red(rgb):
    return (rgb[..., 0] > 200) & (rgb[..., 1] < 60) & (rgb[..., 2] < 60)


def white(rgb):
    return (rgb > 200).all(-1)


def centre(mask):
    pts = np.argwhere(mask)
    return (int(pts[:, 1].mean()), int(pts[:, 0].mean())) if len(pts) else None


def start(path, resume=True, picture="Fit"):
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": "n64"})
    run.start(GM.find_core("n64"), sound="", volume=80, picture=picture, resume=resume)
    runs.append(run)
    return run


def finish(run):
    run.quit()
    return until(lambda: run.ended, 10)


check(f"the N64 emulator is found ({GM.find_core('n64')})", GM.find_core("n64") == CORE)
found = GM.find_games()
kinds = {x["title"]: x["system"] for x in found}
check(f"N64 games are found: .z64, .v64, in a zip ({sorted(kinds)})",
      all(kinds.get(t) == "n64" for t in ("InputRDP", "InputCPU", "Swapped", "Zipped", "Broken")))

# ---- the emulator's process ----------------------------------------------------------------------------------
spec = screen_as(16)
run = start(N64 + "/InputRDP.z64")
check(f"a game drawn in 3D starts ({run.wait_started(30)}, {run.state}, {run.error!r})", run.state == "on")
check("...its frames reach a 16-bit screen", until(lambda: yellow(frame(spec)).sum() > 250000, 10))
rgb = frame(spec)
check(f"...the picture right: yellow, the red cursor in the middle ({centre(red(rgb))}), the N64's own black "
      f"edges ({rgb[240, 2].tolist()})", centre(red(rgb)) in ((319, 239), (320, 239), (319, 240), (320, 240))
      and 900 <= red(rgb).sum() <= 1100 and not rgb[240, 2].any())
check(f"...its settings and shaders go in the cache, not Games/BIOS ({os.listdir(GAMES + '/BIOS')})",
      os.path.isdir(S + "/cache/games/n64/Mupen64plus") and os.listdir(GAMES + "/BIOS") == [])
check("quit: it ends, where it was kept", finish(run) and os.path.getsize(SAVES + "/InputRDP.state.auto") > 16000000)

spec = screen_as(32)
run = start(N64 + "/InputRDP.z64", resume=False)
run.wait_started(30)
check("a 32-bit screen too", until(lambda: yellow(frame(spec)).sum() > 250000, 10)
      and centre(red(frame(spec))) in ((319, 239), (320, 239), (319, 240), (320, 240)))
finish(run)

spec = screen_as(32, 1280, 720)
run = start(N64 + "/InputRDP.z64", resume=False)
run.wait_started(30)
until(lambda: yellow(frame(spec)).sum() > 500000, 10)
rgb = frame(spec)
ys = np.argwhere(yellow(rgb))
check(f"a big screen: the chip makes it 960x720 in the middle ({ys[:, 1].min()}..{ys[:, 1].max()}, "
      f"cursor {centre(red(rgb))})", 160 <= ys[:, 1].min() <= 180 and 1100 <= ys[:, 1].max() <= 1120
      and not rgb[:, :160].any() and not rgb[:, 1120:].any() and centre(red(rgb)) in ((639, 359), (640, 359), (639, 360), (640, 360)))
x720, y720 = (int(ys[:, 1].min()), int(ys[:, 1].max())), (int(ys[:, 0].min()), int(ys[:, 0].max()))
run.send("picture Sharp")
time.sleep(0.6)
ys = np.argwhere(yellow(frame(spec)))
check(f"...Sharp: whole pixels only (640x480, {ys[:, 1].min()}..{ys[:, 1].max()})",
      320 <= ys[:, 1].min() <= 340 and 940 <= ys[:, 1].max() <= 960)
finish(run)

# a 1080p TV: Fit makes it as tall as the screen (1440x1080), not 2x (1280x960) with a black border round it;
# where the game's yellow reaches, from where it reached at 720p (1.5x there, 2.25x here)
spec = screen_as(32, 1920, 1080)
run = start(N64 + "/InputRDP.z64", resume=False)
run.wait_started(30)
until(lambda: yellow(frame(spec)).sum() > 1100000, 10)
rgb = frame(spec)
ys = np.argwhere(yellow(rgb))
got = (int(ys[:, 1].min()), int(ys[:, 1].max()), int(ys[:, 0].min()), int(ys[:, 0].max()))
want = (240 + (x720[0] - 160) * 1.5, 240 + (x720[1] + 1 - 160) * 1.5 - 1, y720[0] * 1.5, (y720[1] + 1) * 1.5 - 1)
check(f"a 1080p TV: as tall as the screen, 1440x1080 in the middle, no border above or below (yellow {got[:2]} across, "
      f"{got[2:]} down; about {tuple(round(v) for v in want)} wanted; cursor {centre(red(rgb))})",
      all(abs(a - b) <= 3 for a, b in zip(got, want)) and not rgb[:, :240].any() and not rgb[:, 1680:].any()
      and centre(red(rgb)) in ((959, 539), (960, 539), (959, 540), (960, 540)))
run.send("picture Sharp")
time.sleep(0.6)
rgb = frame(spec)
ys = np.argwhere(yellow(rgb))
got = (int(ys[:, 1].min()), int(ys[:, 1].max()), int(ys[:, 0].min()), int(ys[:, 0].max()))
want = (320 + (x720[0] - 160) / 1.5 * 2, 320 + (x720[1] + 1 - 160) / 1.5 * 2 - 1, 60 + y720[0] / 1.5 * 2,
        60 + (y720[1] + 1) / 1.5 * 2 - 1)
check(f"...Sharp there: whole pixels, 2x, 1280x960 in the middle ({got[:2]} across, {got[2:]} down; about "
      f"{tuple(round(v) for v in want)})", all(abs(a - b) <= 3 for a, b in zip(got, want))
      and not rgb[:60].any() and not rgb[1020:].any())
finish(run)

# the d-pad, save states, picking up where you left off
spec = screen_as(16)
run = start(N64 + "/InputCPU.z64", resume=False)
run.wait_started(30)
time.sleep(1.0)
before = int(white(frame(spec)).sum())
check(f"Save state ({run.ask('save', ('saved', 'error'), 10)})", os.path.getsize(SAVES + "/InputCPU.state") > 16000000)
run.press("right"); time.sleep(0.8); run.release("right"); time.sleep(0.4)
moved = int(white(frame(spec)).sum())
check(f"the d-pad goes to the game: the cursor draws a line ({before} -> {moved} white)", moved > before + 500)
answer = run.ask("load", ("loaded", "nostate", "error"), 10)
time.sleep(0.6)
back = int(white(frame(spec)).sum())
check(f"Load state: as it was, the line gone ({answer}, {back} white)", answer[0] == "loaded" and back < moved - 500)
run.press("down"); time.sleep(0.5); run.release("down"); time.sleep(0.4)
drawn = int(white(frame(spec)).sum())
finish(run)
run = start(N64 + "/InputCPU.z64")
check(f"...next time it picks up where you were ({run.wait_started(30)}, {run.resumed})", run.resumed)
time.sleep(1.0)
check(f"...the line it drew still there ({drawn} -> {int(white(frame(spec)).sum())} white)",
      abs(int(white(frame(spec)).sum()) - drawn) < 400 and drawn > back + 200)
finish(run)

for name in ("Zipped.zip", "Swapped.v64"):
    run = start(N64 + "/" + name, resume=False)
    run.wait_started(30)
    check(f"{name}: plays like the .z64", until(lambda: yellow(frame(spec)).sum() > 250000, 10)
          and centre(red(frame(spec))) in ((319, 239), (320, 239), (319, 240), (320, 240)))
    finish(run)
run = start(N64 + "/Broken.z64", resume=False)
ok = run.wait_started(30)
check(f"a broken game: it says so ({run.error!r})", not ok and run.error == "This game didn't load"
      and until(lambda: run.ended, 5))
os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"] = S + "/none.json"   # (no OpenGL ES at all)
run = start(N64 + "/InputRDP.z64", resume=False)
ok = run.wait_started(30)
del os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"]
check(f"no 3D here: it says why ({run.error!r})", not ok and run.error == "There's no OpenGL ES 3 here for 3D games"
      and until(lambda: run.ended, 5))
g.pi_model = lambda: "Raspberry Pi 4 Model B Rev 1.4"
check(f"...on a Pi 4 with its 3D off: how to turn it on ({GPUM.why_no_3d()!r})",
      GPUM.why_no_3d() == "Turn on 3D in config.txt: dtoverlay=vc4-kms-v3d")
GPUM.case_kind = lambda: "2"
check(f"...in a GPi Case 2: its own overlay's line, not KMS's, which leaves the case's screen black "
      f"({GPUM.why_no_3d()!r})", GPUM.why_no_3d() == "Turn on 3D in config.txt: dtoverlay=gpicase2-3d")
GPUM.case_kind = lambda: None
g.pi_model = lambda: "Raspberry Pi Zero 2 W Rev 1.0"
g.slow_pi = lambda: True
check(f"...on an older Pi: it needs a Pi 4 or 5 ({GPUM.why_no_3d()!r})", GPUM.why_no_3d() == GPUM.NO_3D)
g.pi_model = lambda: ""
g.slow_pi = lambda: False
run = start(N64 + "/InputRDP.z64", resume=False)
run.wait_started(30)
run.p.send_signal(signal.SIGTERM)
check("stopped (the Pi going off): it keeps your place and ends", until(lambda: run.ended, 10)
      and run.p.returncode == 0)

# ---- in this process: the sticks, in the N64 ---------------------------------------------------------------
shown = []
core = E.Core(CORE, N64 + "/InputCPU.z64", (".z64",), S + "/saves", "t", S + "/cache/games/n64",
              lambda a, fmt, aspect: shown.append(fmt))


def reply():
    """The controller's reply (buttons, x, y) the InputCPU demo copies into N64 memory, by its command block."""
    ptr, size = core.memory(2)
    import ctypes as C
    words = (C.c_uint32 * (size // 4)).from_address(ptr)
    w = np.frombuffer(words, dtype=np.uint32)
    for i in np.flatnonzero(w[:-20] == 0xFF010401):
        if w[i + 8] == 0xFE000000 and w[i + 15] == 1 and w[i + 16] == 0xFF010401:
            v = int(w[i + 17])
            return v >> 16, np.int8(np.uint8((v >> 8) & 255)).item(), np.int8(np.uint8(v & 255)).item()
    return None


for _ in range(90):
    core.run()
check(f"in the N64: the stick at rest ({reply()})", reply() == (0, 0, 0))
want = {(0.5, 0): (0, 33, 0), (1, 0): (0, 80, 0), (-1, 0): (0, -80, 0), (0, -1): (0, 0, 80), (0.7, 0.7): (0, 56, -56)}
got = {}
for (sx, sy), _ in want.items():
    core.sticks[0] = [int(sx * 32767), int(sy * 32767), 0, 0]
    for _ in range(8):
        core.run()
    got[(sx, sy)] = reply()
check(f"...pushed: the N64's own numbers, up is up ({got})", got == want)
core.sticks[0] = [0, 0, -32767, 0]
for _ in range(8):
    core.run()
check(f"...the right stick is its C buttons (left: C-Left, {reply()})", reply() == (0x0002, 0, 0))
core.sticks[0] = [0, 0, 0, 0]
core.buttons[0] = 1 << E.BUTTON_IDS["b"]
for _ in range(8):
    core.run()
check(f"...libretro's B is the N64's A ({reply()})", reply()[0] == 0x8000)
core.buttons[0] = 1 << E.BUTTON_IDS["l2"]
for _ in range(8):
    core.run()
check(f"...L2 is Z ({reply()})", reply()[0] == 0x2000)
core.buttons[0] = 0
check(f"...frames handed over drawn by the chip ({len(shown)}, {shown[:1]})", len(shown) > 50 and shown[0] == (640, 480))
core.close()

s = E.Session.__new__(E.Session)
s.core = types.SimpleNamespace(sticks=[[0, 0, 0, 0] for _ in range(E.PLAYERS)], buttons=[0] * E.PLAYERS,
                                plug=lambda port: None)
s.paused, s.letgo = False, {}
s.sound = types.SimpleNamespace(stop=lambda: None)
s.keep, s.say, s.slow = (lambda: None), (lambda *a: None), (lambda: False)
s.command(["stick", "lx", "64"]); s.command(["stick", "ry", "-127"]); s.command(["stick", "ly", "999"])
check(f"the stick lines: where each stick is, as libretro has it ({s.core.sticks[0]})",
      s.core.sticks[0] == [int(64 * 32767 / 127), 32767, 0, -32767])
s.command(["stick", "lx", "x"]); s.command(["stick", "zz", "5"]); s.command(["stick"])
check("...odd ones change nothing", s.core.sticks[0] == [int(64 * 32767 / 127), 32767, 0, -32767])
s.command(["pause"])
s.command(["stick", "lx", "50"])
check(f"...its menu up: let go, and moves ignored ({s.core.sticks[0]})", s.core.sticks[0] == [0, 0, 0, 0])

# ---- media mode ------------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last = None

    def show(self, img):
        self.last = img.copy(); FB.count += 1

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        pass

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.tab = m.tab_index("games"); m.view = "list"; m.load_tab(m.tab)
rows = {r["title"]: r for r in m.tab_items()}
check(f"the Games list: N64 games, badged ({rows['InputRDP']['icon']}, {rows['InputRDP']['sub']!r})",
      (rows["InputRDP"]["icon"], rows["InputRDP"]["sub"]) == ("N64", "Nintendo 64"))
m.dirty = True; m.flush()
check("...drawn", m.fb.last is not None)
g.slow_pi = lambda: True
m.load_tab(m.tab)
titles = [r["title"] for r in m.tab_items()]
check(f"an older Pi: its N64 games aren't shown at all ({titles})",
      not {"InputRDP", "InputCPU", "Swapped", "Zipped", "Broken"} & set(titles) and titles[0] == "Snake"
      and not any(x["system"] == "n64" for x in GM.find_games()))
check(f"...and in Files an N64 game is just a file ({m.game_system(N64 + '/InputRDP.z64')})",
      m.game_system(N64 + "/InputRDP.z64") is None and m.game_system(GAMES + "/../Games/n64/Zipped.zip") is None)
g.slow_pi = lambda: False
m.load_tab(m.tab)
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("InputRDP")
m.press("a")
check(f"a Pi 4 or 5: it starts ({m.view})", m.view == "game" and m.game is not None and m.game.wait_started(30))
check(f"...buttons by letter: A is the N64's A (libretro's B), B its B (Y) "
      f"({[m.game_button(n) for n in ('a', 'b', 'x', 'y', 'l2', 'r2', 'start', 'up')]})",
      [m.game_button(n) for n in ("a", "b", "x", "y", "l2", "r2", "start", "up")]
      == ["b", "y", "x", "a", "l2", "r2", "start", "up"])
check("...it takes the sticks as they are", m.game_sticks())
m.game_end()
check("...ended", m.game is None and m.view == "list")


class FakeRun:
    def __init__(self, system):
        self.game = {"system": system, "path": "x", "title": "x"}
        self.sent, self.state, self.disc, self.ended, self.slow = [], "on", (0, 1), False, False

    def send(self, line):
        self.sent.append(line)
        return True

    def press(self, n, port=0):
        self.sent.append(f"down {n} {port}" if port else "down " + n)

    def release(self, n, port=0):
        self.sent.append(f"up {n} {port}" if port else "up " + n)

    def stick(self, axis, value, port=0):
        self.sent.append(f"stick {axis} {value} {port}" if port else f"stick {axis} {value}")

    def resume(self):
        self.sent.append("resume")

    def pause(self):
        return True

    def quit(self):
        pass


m.game = FakeRun("gba"); m.view = "game"
check(f"a GBA game: the buttons as they were ({m.game_button('a')}), the sticks as the d-pad",
      m.game_button("a") == "a" and not m.game_sticks())
m.game = FakeRun("ps1")
check(f"a PlayStation game: by place, as before ({m.game_button('a')})", m.game_button("a") == "b")
m.game = FakeRun("n64"); m.stick_sent = {}
m.game_stick("lx", 64); m.game_stick("lx", 64); m.game_stick("ly", 0)
check(f"a stick moved: sent once, at rest not sent again ({m.game.sent})", m.game.sent == ["stick lx 64"])
m.view = "gamemenu"
check("...its menu up: the sticks are the menu's again", not m.game_sticks())
m.view = "game"


class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class FakeDev:
    n = 0

    def __init__(self, name, keys, absaxes=None):
        FakeDev.n += 1
        self.path = f"/dev/input/event{70 + FakeDev.n}"
        self.name, self.keys, self.absaxes = name, keys, absaxes or {}
        self.info = Info(0x45e, 0x28e + FakeDev.n)
        self.r, self.w = os.pipe()
        self.q = []

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
        self.q += [types.SimpleNamespace(type=t, code=c, value=v) for t, c, v in evs]
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


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


FACE = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START]
JOY = [e.BTN_TRIGGER, e.BTN_THUMB, e.BTN_THUMB2, e.BTN_TOP, e.BTN_TOP2, e.BTN_PINKIE, e.BTN_BASE, e.BTN_BASE2,
       e.BTN_BASE3, e.BTN_BASE4]
xbox_dev = FakeDev("Microsoft X-Box 360 pad", FACE + [e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
                   {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_RX: ai(-32768, 32767, 0),
                    e.ABS_RY: ai(-32768, 32767, 0), e.ABS_Z: ai(0, 255, 0), e.ABS_RZ: ai(0, 255, 0),
                    e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
dinput_dev = FakeDev("Logitech Dual Action", JOY, {e.ABS_X: ai(0, 255, 128), e.ABS_Y: ai(0, 255, 128),
                                                   e.ABS_Z: ai(0, 255, 128), e.ABS_RZ: ai(0, 255, 128),
                                                   e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
snes_dev = FakeDev("USB Gamepad ", JOY, {e.ABS_X: ai(0, 255, 127), e.ABS_Y: ai(0, 255, 127)})
hat_dev = FakeDev("8BitDo SN30 Pro", FACE, {e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
xbox, dinput, snes, hat = (g.Pad(d, g.pad_kind(d)) for d in (xbox_dev, dinput_dev, snes_dev, hat_dev))
check(f"a controller's sticks: an Xbox pad's two ({sorted(xbox.sticks.values())}), a plain USB pad's right one on "
      f"Z/RZ ({sorted(dinput.sticks.values())}), a SNES-style pad's d-pad is its 'stick' ({sorted(snes.sticks.values())}), "
      f"one with a d-pad only has none ({hat.sticks})",
      sorted(xbox.sticks.values()) == ["lx", "ly", "rx", "ry"] and dinput.sticks == {e.ABS_X: "lx", e.ABS_Y: "ly",
      e.ABS_Z: "rx", e.ABS_RZ: "ry"} and sorted(snes.sticks.values()) == ["lx", "ly"] and hat.sticks == {})
ev = types.SimpleNamespace
check(f"...how far: full left, middle, full right ({[xbox.stick(ev(type=e.EV_ABS, code=e.ABS_X, value=v)) for v in (-32768, 0, 32767)]}; "
      f"{[snes.stick(ev(type=e.EV_ABS, code=e.ABS_X, value=v)) for v in (0, 127, 255)]})",
      [xbox.stick(ev(type=e.EV_ABS, code=e.ABS_X, value=v)) for v in (-32768, 0, 32767)] == [("lx", -127), ("lx", 0), ("lx", 127)]
      and [snes.stick(ev(type=e.EV_ABS, code=e.ABS_X, value=v)) for v in (0, 127, 255)] == [("lx", -127), ("lx", 0), ("lx", 127)])
check("...not a stick: a button, the hat, a trigger", xbox.stick(ev(type=e.EV_KEY, code=e.BTN_SOUTH, value=1)) is None
      and xbox.stick(ev(type=e.EV_ABS, code=e.ABS_HAT0X, value=1)) is None
      and xbox.stick(ev(type=e.EV_ABS, code=e.ABS_Z, value=255)) is None)
check(f"...L2: the Xbox pad's trigger yes, the d-pad-only pad no ({xbox.has_button('l2')}, {hat.has_button('l2')})",
      xbox.has_button("l2") and not hat.has_button("l2") and hat.has_button("l"))
m.game = FakeRun("n64"); m.stick_sent = {}
names = [m.game_pad_button(xbox, n) for n in ("left", "l", "a")]
check(f"in an N64 game: a pad with a stick keeps its d-pad, and L ({names}, nothing sent: {m.game.sent})",
      names == ["left", "l", "a"] and m.game.sent == [])
hat.down = {"left"}
first = m.game_pad_button(hat, "left")
hat.down = {"left", "up"}
second = m.game_pad_button(hat, "up")
hat.down = set()
third = m.game_pad_button(hat, "up")
check(f"...a pad with no stick: the d-pad is the stick, a diagonal as far as a stick goes ({first}, {second}, "
      f"{third}: {m.game.sent})", (first, second, third) == (None, None, None) and m.game.sent
      == ["stick lx -127", "stick lx -90", "stick ly -90", "stick lx 0", "stick ly 0"])
check(f"...and with no L2, L is Z ({m.game_pad_button(hat, 'l')})", m.game_pad_button(hat, "l") == "l2")
m.game.sent = []
xbox_dev.absaxes[e.ABS_X] = ai(-32768, 32767, -32768)
m.pads = types.SimpleNamespace(by_path={xbox_dev.path: xbox, hat_dev.path: hat})
m.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": None}; m.view = "gamemenu"
m.game_menu_close()
check(f"its menu closed: the game gets the stick where it's held, as that controller's player's (player 2: the "
      f"d-pad-only pad played first) ({m.game.sent})", m.game.sent == ["resume", "stick lx -127 1"])
xbox_dev.absaxes[e.ABS_X] = ai(-32768, 32767, 0)
m.game = None; m.view = "list"; m.pads = None

# ---- the real loop ---------------------------------------------------------------------------------------------
g.PADS_FILE = S + "/pads.json"
g.SCAN_EVERY = 0.05
g.input_driver = lambda dev: "usbhid"
g.list_devices = lambda: [xbox_dev.path]
g.InputDevice = lambda path: xbox_dev
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": 9})() if str(p).startswith("/dev/input/") else real_stat(p, *a, **k)


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


m2 = g.Media()
m2.load_fonts(); m2.fb = FB(); m2.active = True; m2.boot_media = False
m2.tab = m2.tab_index("games"); m2.view = "list"; m2.load_tab(m2.tab)
m2.sels[m2.tab] = [r["title"] for r in m2.tab_items()].index("InputCPU")
done, errors = threading.Event(), []


def loop():
    try:
        g.run(UI(), m2, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.5)


def press(code, sec=0.3):
    xbox_dev.send((e.EV_KEY, code, 1)); time.sleep(0.05); xbox_dev.send((e.EV_KEY, code, 0)); time.sleep(sec)


def axis(code, value, sec=0.25):
    xbox_dev.absaxes[code] = ai(xbox_dev.absaxes[code].min, xbox_dev.absaxes[code].max, value)
    xbox_dev.send((e.EV_ABS, code, value)); time.sleep(sec)


press(e.BTN_SOUTH, 0.2)
check("the real loop: A starts the N64 game", until(lambda: m2.game is not None and m2.game.state == "on", 30))
sent = []
real_send = m2.game.send
m2.game.send = lambda line: (sent.append(line), real_send(line))[1]
axis(e.ABS_X, 32767); axis(e.ABS_X, 16000); axis(e.ABS_X, 0)
check(f"...the left stick goes to it as it is, never as the d-pad ({sent})",
      sent == ["stick lx 127", "stick lx 62", "stick lx 0"])
sent.clear()
axis(e.ABS_RY, -32768); axis(e.ABS_RY, 0)
axis(e.ABS_HAT0X, 1); axis(e.ABS_HAT0X, 0)
press(e.BTN_SOUTH, 0.2)
axis(e.ABS_Z, 255); axis(e.ABS_Z, 0)
check(f"...the right stick too; the d-pad is its d-pad, A its A, the trigger Z ({sent})",
      sent == ["stick ry -127", "stick ry 0", "down right", "up right", "down b", "up b", "down l2", "up l2"])
sent.clear()
press(e.BTN_MODE, 0.4)
check("HOME: its menu", m2.view == "gamemenu")
axis(e.ABS_Y, 32767, 0.2); axis(e.ABS_Y, 0, 0.2)
check(f"...the stick moves around the menu now, and nothing goes to the game ({m2.game_menu['sel']}, {sent})",
      m2.game_menu["sel"] == 1 and not [x for x in sent if x.startswith("stick")])
axis(e.ABS_Y, -32768, 0.2); axis(e.ABS_Y, 0, 0.2)
xbox_dev.absaxes[e.ABS_X] = ai(-32768, 32767, -32768)       # (held left as the menu goes)
press(e.BTN_MODE, 0.6)
check(f"HOME again: back to the game, the stick where it's held ({sent})", m2.view == "game"
      and "stick lx -127" in sent and until(lambda: m2.game.state == "on", 5))
xbox_dev.absaxes[e.ABS_X] = ai(-32768, 32767, 0)
m2.game_end()
done.set()
th.join(5)
check("...no errors in the loop", not errors)

for r in runs:
    if r.p and r.p.poll() is None:
        r.p.kill()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
