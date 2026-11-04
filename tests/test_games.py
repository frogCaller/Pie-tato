"""Games: Snake on its own (moving, turning, eating, walls that stop it or wrap, running into itself, the
tail moving out of the way, filling the board, quicker as it grows, pausing, your best), then in media
mode (its icon finishing the home screen, the buttons, START's options, full screen, coming back to a
game, the web page), then in the real main loop in real time."""
import os, random, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
S = SP + "/tgames"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def game(**values):
    return g.Snake(436, 342, random.Random(3), values=values)


# ---- a game -------------------------------------------------------------------------------------------
s = game()
check(f"a new game: three long in the middle, heading right, an apple ({list(s.body)}, {s.apple})",
      list(s.body) == [(10, 9), (11, 9), (12, 9)] and s.dir == (1, 0) and s.phase == "ready"
      and s.apple is not None and s.apple not in s.taken and (s.cols, s.rows) == (24, 19))
check(f"...its numbers: {s.stats()}", s.stats() == [("Score", "0"), ("Best", "0"), ("Length", "3")])
s.update(1.0)
check("ready: it waits", s.steps == 0 and s.note() == ("Snake", "A or the d-pad to start"))
s.press_a()
s.apple = (0, 0)
for _ in range(20):
    s.update(0.05)
check(f"A: off it goes, 9 steps a second ({s.steps})", s.phase == "on" and 8 <= s.steps <= 10 and s.body[-1][1] == 9)
s = game()
s.steer("up")
s.apple = (0, 0)
s.step()
check("ready, the d-pad: off it goes that way", s.phase == "on" and s.dir == (0, -1) and s.body[-1] == (12, 8))
s = game()
s.steer("left")
s.apple = (0, 0)
s.step()
check(f"...back the way it came: it turns round first ({list(s.body)})", s.phase == "on" and s.dir == (-1, 0)
      and list(s.body) == [(11, 9), (10, 9), (9, 9)])

# turning
s = game()
s.press_a()
s.apple = (0, 0)
s.steer("left")
check("no going straight back", not s.turns)
s.steer("up")
s.steer("left")
s.steer("down")
check(f"two turns at most, waiting their steps ({s.turns})", s.turns == [(0, -1), (-1, 0)])
s.step(); s.step()
check(f"...a quick U-turn ({list(s.body)})", s.dir == (-1, 0) and list(s.body) == [(12, 9), (12, 8), (11, 8)])
s.steer("left")
check("the way it's going already: nothing more", not s.turns)

# eating
s = game()
s.press_a()
s.apple = (13, 9)
out = s.step()
check(f"an apple: one longer, a new one somewhere free ({out}, {s.stats()})", out == "ate" and len(s.body) == 4
      and s.apples == 1 and s.apple not in s.taken and s.best == 1 and s.new_best)
r0 = dict(g.SNAKE_SPEEDS)["Normal"]
check(f"...quicker for each one ({s.rate():.2f} a second)", abs(s.rate() - r0 * 1.03) < 1e-9)
s.apples = 40
check(f"...up to a point ({s.rate():.1f})", abs(s.rate() - r0 * 1.5) < 1e-9)
s.configure({"speed": "Fast"})
check(f"Speed: at once, no new game ({s.rate():.1f})", abs(s.rate() - 12 * 1.5) < 1e-9 and s.phase == "on"
      and not s.needs_restart())

# walls
s = game()
s.press_a()
s.apple = (0, 0)
outs = [s.step() for _ in range(12)]
check(f"a solid wall: game over ({s.note()})", outs[-1] == "over" and s.phase == "over" and s.why == "the wall"
      and s.note() == ("Game over", "0 apples, then into the wall. A to play again") and s.body[-1] == (23, 9))
s.press_a()
check("...A: a new game", s.phase == "ready" and len(s.body) == 3 and s.apples == 0)
s = game(walls="Wrap")
s.press_a()
s.apple = (0, 0)
for _ in range(12):
    s.step()
check(f"walls that wrap: out one side, in the other ({s.body[-1]})", s.phase == "on" and s.body[-1] == (0, 9))
s.configure({"walls": "Solid"})
check("...Walls and Board: a new game (when START's card closes)", s.needs_restart())

# running into itself, and its tail moving out of the way
s = game()
s.press_a()
s.body = g.deque([(10, 9), (11, 9), (12, 9), (13, 9), (14, 9)])
s.taken = set(s.body)
s.apple = (0, 0)
for d in ("up", "left", "down"):
    s.steer(d)
    s.step()
check(f"into itself: game over ({s.note()[1]})", s.phase == "over" and s.why == "itself")
s = game()
s.press_a()
s.body = g.deque([(11, 9), (11, 8), (12, 8), (12, 9)])           # a square: its head right by its tail
s.taken = set(s.body)
s.dir = (0, 1)
s.apple = (0, 0)
s.steer("left")
out = s.step()
check(f"...where its tail just was: fine, the tail moves on ({list(s.body)})", out is None and s.phase == "on"
      and list(s.body) == [(11, 8), (12, 8), (12, 9), (11, 9)])
s = game()
s.press_a()
s.body = g.deque([(11, 9), (11, 8), (12, 8), (12, 9)])
s.taken = set(s.body)
s.dir = (0, 1)
s.apple = (11, 9)                                      # (never, in a game: apples go on free cells)
s.steer("left")
check("...unless it eats there, and the tail stays", s.step() == "over" and s.why == "itself")

# the whole board
s = game(board="Small")
s.press_a()
cells = [(x, y) for y in range(s.rows) for x in (range(s.cols) if y % 2 == 0 else range(s.cols - 1, -1, -1))]
s.body = g.deque(cells[:-1])
s.taken = set(s.body)
s.dir = (-1, 0) if (s.rows - 1) % 2 else (1, 0)
s.apple = s.place_apple()
check(f"one cell left: the apple goes there ({s.apple})", s.apple == cells[-1])
out = s.step()
check(f"...eaten: the board is full ({s.note()})", out == "over" and s.why is None and s.apple is None
      and s.note()[0] == "You filled the board!")
s = game()
s.taken = {(x, y) for x in range(s.cols) for y in range(s.rows)} - {(5, 5)}
check("a crowded board: the apple still finds the one free cell", s.place_apple() == (5, 5))

# pausing
s = game()
s.press_a()
s.apple = (0, 0)
s.press_a()
s.update(1.0)
check("A again: paused, it waits", s.paused and s.steps == 0 and s.hints()[1] == ("A", "Play"))
s.steer("down")
check("...the d-pad: on again, that way", not s.paused and s.turns == [(0, 1)])

# what's drawn
s = game()
pic = s.picture()
check("a picture the size of the box", pic.size == (436, 342))
img = Image.new("RGB", (436, 342))
s.draw(img, 0, 0)
first = s.pic
s.draw(img, 0, 0)
check("...kept until something moves", s.pic is first)
c, ox, oy = s.layout()
head = (ox + 12 * c + c // 2, oy + 9 * c + c // 2)
greens = sum(1 for x in range(ox + 10 * c, ox + 12 * c) if (lambda p: p[1] > p[0] + 40)(pic.getpixel((x, head[1]))))
eyes = sum(1 for x in range(ox + 12 * c, ox + 13 * c) for y in range(oy + 9 * c, oy + 10 * c)
           if pic.getpixel((x, y)) == (246, 248, 250))
check(f"...the snake: a green band from its tail ({greens} px), eyes on its head ({eyes} px), the apple red",
      greens >= 2 * c - 2 and eyes >= 8
      and pic.getpixel((ox + s.apple[0] * c + c // 2, oy + s.apple[1] * c + c // 2 + 2)) == g.SNAKE_APPLE)
s.press_a()
s.apple = (0, 0)
s.step()
s.refit(640, 480)
check(f"full screen: the same game, bigger cells ({s.layout()[0]} px)", s.phase == "on" and len(s.body) == 3
      and s.layout()[0] == 25 and s.picture().size == (640, 480))
s.body = g.deque([(10, 16), (11, 16), (12, 16)])
check("the end of a game near the bottom: its card goes at the top", s.note_top())

# ---- in media mode ----------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last, self.frames = None, 0

    def show(self, img):
        self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def close(self):
        pass


fake = [1000.0]
real_monotonic = time.monotonic
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()


def frames(secs, step=0.05):
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        m.tick()
        m.flush()


apps = [a for a, _ in m.home_apps()]
check(f"Games in the middle of the home screen: {len(apps)} icons, three rows of five ({apps[5:10]})", len(apps) == 15
      and g.home_cols(15) == 5 and apps[5:10] == ["Photos", "Videos", "Games", "Weather", "Finance"]
      and apps[10:] == ["Bot", "Simulator", "Files", "System", "Settings"])
icon = g.draw_icon("Games")
check("...its icon: a game controller", icon.size == (84, 84) and len(icon.getcolors(1 << 16) or []) > 40)
m.view = "home"
m.home_sel = apps.index("Games")
m.dirty = True; m.flush()
check(f"...what it says: {g.HOME_ICONS['Games'][1]!r}", "Snake" in g.HOME_ICONS["Games"][1])
m.press("a")
check("A: the Games list, Snake first and picked", m.tab_type() == "games" and m.tab_items()[0]["title"] == "Snake" and m.sels.get(m.tab, 0) == 0)
m.press("a")
s = m.sim_game()
check("A: Snake, ready", g.LIBRARY[m.tab]["name"] == "Snake" and g.LIBRARY[m.tab]["parent"] == "Games" and s.key == "snake" and s.phase == "ready"
      and m.on_sim_page() and m.holds_buttons())
frames(0.3)
hints = [label for _, label, *_ in m.sim_hints(s)]
check(f"...its buttons: {hints}", hints == ["Steer", "Start", "AI plays", "Options"])
sim_tab = next(t for t in g.LIBRARY if t["name"] == "Simulator")
check("...an app of its own, not one of the Simulator's", "Games" not in sim_tab["children"]
      and "snake" not in [t.get("sim") for t in g.LIBRARY if t.get("parent") == "Simulator"])
m.press("a")
s.apple = (0, 0)
frames(1.0)
check(f"A: a game, about 9 steps a second in the real frames ({s.steps})", s.phase == "on" and 7 <= s.steps <= 10)
m.press("up")
frames(0.2)
check("the d-pad steers", s.dir == (0, -1))
m.press("up", repeat=True)
check("...a held button changes nothing", not s.turns)
m.press("a")
frames(0.5)
steps = s.steps
frames(0.5)
check("A: paused (and it says so)", s.paused and s.steps == steps and m.sim_card[0] == ("paused",))
m.press("a")
while s.phase == "on":
    frames(0.1)
check(f"into the top wall: game over, its card at the foot ({m.sim_card[0][:2]})", s.why == "the wall"
      and m.sim_card[0][0] == "note" and m.sim_card[0][3] is False)
m.press("a")
s.apple = (13, 9)
m.press("right")
frames(0.3)
check(f"A, right: a new game, an apple eaten ({s.apples})", s.phase == "on" and s.apples == 1)
m.press("y")
check(f"Y: a new game, your best kept ({m.setting('snake_best')})", s.phase == "ready" and m.setting("snake_best") == 1)
check("...for next time", g.Media().snake_best() == 1)
m.press("a")
m.press("start")
check("START: its options, the game waits", m.sim_opts == 0 and s.paused
      and [k for k, *_ in m.sim_rows(type(s))] == ["speed", "board", "walls", "full"])
m.press("down")
m.press("right")
m.press("b")
check(f"...Board: Large, a new game on it ({s.cols} x {s.rows})", (s.cols, s.rows) == (32, 25) and s.phase == "ready"
      and m.setting("sim_snake_board") == "Large")
m.press("a")
s.apple = (0, 0)
frames(0.5)
m.press("b")
check("B: the Games list, Snake picked", m.tab_type() == "games" and m.sels[m.tab] == 0)
m.press("b")
check("B again: home, Games picked", m.view == "home" and apps[m.home_sel] == "Games")
fake[0] += 5
m.press("a")
m.press("a")                                                # (the Games list, then Snake)
frames(0.3)
check("back to a game: it waits for you", m.sim_game() is s and s.paused and s.phase == "on")
m.press("select")
frames(0.3)
check(f"SELECT: full screen, the same game ({s.layout()[0]} px cells)", m.sim_full() and (s.w, s.h) == (640, 480)
      and s.phase == "on" and s.layout()[0] == 19)
m.msg = None
m.press("a")
while s.phase == "on":
    frames(0.1)
check(f"...the end of a game there: a word about it ({m.msg!r})", m.msg and "A to play again" in m.msg)
m.press("select")
frames(0.2)
check("SELECT again: back beside its numbers", not m.sim_full() and (s.w, s.h) == (436, 342))
said = []
real_text = m.sim_text
m.sim_text = lambda img, at, text, *a, **k: (said.append(text), real_text(img, at, text, *a, **k))[1]
m.sim_still = (None, None)
m.sim_panel = (None, None, 0.0)
m.dirty = True; m.flush()
m.sim_text = real_text
check(f"...its name beside it: Snake ({said[:1]})", said[:1] == ["Snake"] and "Games" not in said)
cat = m.web_catalog()
ga = next((a for a in cat["apps"] if a["name"] == "Games"), None)
check(f"the web page: Games among its apps ({ga})", ga and ga["color"] == "#%02x%02x%02x" % g.HOME_ICONS["Games"][0]
      and m.web_icon("Games", 96)[:8] == b"\x89PNG\r\n\x1a\n")
m.go_home()
r = m.web_command({"cmd": "open", "app": "Games"})
check(f"...and it opens it: {r}", r == {"ok": True} and g.LIBRARY[m.tab]["name"] == "Games" and m.view == "list")
m.go_home()
g.time.monotonic = real_monotonic

# ---- in the real main loop, in real time ----------------------------------------------------------------------
from evdev import ecodes as e
g.PADS_FILE = S + "/pads.json"
g.SCAN_EVERY = 0.05


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    bustype, vendor, product = 0x03, 1, 1


class Pad:
    def __init__(self, keys):
        self.driver, self.path, self.name, self.keys = "usbhid", "/dev/input/event72", "Test pad", keys
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
g.subprocess.Popen = lambda *a, **k: None
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


class LFB(FB):
    real_w, real_h = 640, 480
    log = []

    def show(self, img):
        LFB.log.append(time.monotonic()); super().show(img)

    def show_part(self, img, box):
        LFB.log.append(time.monotonic()); super().show_part(img, box)

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass


g.Framebuffer = LFB
m = g.Media()
done, errors = threading.Event(), []


def loop():
    try:
        g.run(UI(), m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.6)


def press(code, sec=0.15):
    pad.send((e.EV_KEY, code, 1)); time.sleep(0.05); pad.send((e.EV_KEY, code, 0)); time.sleep(sec)


apps = [a for a, _ in m.home_apps()]
row, col = divmod(apps.index("Games"), 5)
for _ in range(row):
    press(e.BTN_DPAD_DOWN)
for _ in range(col):
    press(e.BTN_DPAD_RIGHT)
press(e.BTN_SOUTH, 0.4)
press(e.BTN_SOUTH, 0.4)                                    # (the Games list: Snake is first)
s = m.sims.get("snake")
check(f"the real loop: the d-pad to Games, A: Snake ({apps[m.home_sel] if m.view == 'home' else 'open'})",
      s is not None and m.tab_type() == "sim" and s.phase == "ready")
press(e.BTN_SOUTH, 0.05)
s.apple = (0, 0)
t0 = time.monotonic()
steps = s.steps
time.sleep(1.0)
fps = sum(1 for t in LFB.log if t >= t0) / 1.0
check(f"...a game: {s.steps - steps} steps a second, {fps:.0f} frames", s.phase == "on" and 7 <= s.steps - steps <= 10
      and g.SIM_FPS - 4 <= fps <= g.SIM_FPS + 2)
pad.send((e.EV_KEY, e.BTN_DPAD_DOWN, 1)); time.sleep(0.9); pad.send((e.EV_KEY, e.BTN_DPAD_DOWN, 0)); time.sleep(0.1)
check(f"...the d-pad held down: one turn, no key repeat ({s.dir}, {s.turns})", s.dir == (0, 1) and not s.turns)
press(e.BTN_EAST, 0.3)
press(e.BTN_EAST, 0.3)                                     # (the Games list, then home)
check("...B: home", m.view == "home")
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
