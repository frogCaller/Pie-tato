"""Apps' other sims, each on its own (Game of Life, Forest Fire, the Mandelbrot Set),
then all of them in media mode: opened from the list, frames, START's options (live, or a new start
when the card closes), X, Y, A, full screen for every sim, the box's round corners, and B back."""
import math, os, random, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
S = SP + "/tsims"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def wait_rest(sim, secs=3.0):
    """Its thread has stopped working (nothing on the go for a while)."""
    end = time.time() + secs
    quiet = 0
    while time.time() < end:
        quiet = quiet + 1 if sim.job is None else 0
        if quiet > 10:
            return True
        time.sleep(0.05)
    return False


def run(sim, secs, dt=0.05):
    out = []
    for _ in range(int(round(secs / dt))):
        r = sim.update(dt)
        if r:
            out.append(r)
    return out


# ---- Game of Life --------------------------------------------------------------------------------------
L = g.Life(440, 340, random.Random(1))
check(f"Life: a board of {L.cols} x {L.rows} cells, a third alive to start with",
      (L.cols, L.rows) == (110, 85) and 0.25 < L.alive() / (110 * 85) < 0.35)


def board(life, cells):
    life.age[:] = 0
    life.gone[:] = 0
    for y, x in cells:
        life.age[y, x] = 1
    life.seen.clear()
    life.ended, life.steady = None, 0


board(L, [(10, 10), (10, 11), (10, 12)])
L.step()
check("...a blinker turns", sorted(map(tuple, np.argwhere(L.age > 0))) == [(9, 11), (10, 11), (11, 11)])
L.step()
L.step()
check(f"...and it's seen to repeat: {L.ended}", L.ended and L.ended[0] == "Settled")
board(L, [(1, 2), (2, 3), (3, 1), (3, 2), (3, 3)])                    # a glider
start = set(map(tuple, np.argwhere(L.age > 0)))
for _ in range(4):
    L.step()
moved = set(map(tuple, np.argwhere(L.age > 0)))
check("...a glider moves one cell down and across in four generations", moved == {(y + 1, x + 1) for y, x in start})
check("...old cells are older (darker), the just-gone fade", L.age.max() >= 2 and L.gone.max() > 0)
six = [(20, 20), (20, 21), (20, 22), (22, 20), (22, 21), (22, 22)]  # a dead cell with six neighbours
for rules, born in (("Life", False), ("HighLife", True)):
    L.values["rules"] = rules
    board(L, six)
    L.step()
    check(f"...{rules}: a cell with six neighbours is {'born' if born else 'not born'}", bool(L.age[21, 21]) == born)
L.values["rules"] = "Life"
board(L, [])
L.step()
check(f"...an empty board: '{L.ended[0]}'", L.ended[0] == "Everything died")
note = L.note()
check(f"...its card: {note}", note[0] == "Everything died" and "A new one in" in note[1])
r = run(L, g.Life.WAIT + 0.2)
check(f"...then a new board by itself ({r})", "next" in r and L.alive() > 1000 and not L.ended)
L.age[:] = 0
L.poke()
check(f"...X: a patch of new life ({L.alive()} cells)", 20 < L.alive() <= 256)
board(L, [(40, 50), (40, 51), (41, 50), (41, 51)])                # a block, in the middle
L.refit(640, 480)
cells = set(map(tuple, np.argwhere(L.age > 0)))
check(f"...full screen: a bigger board ({L.cols} x {L.rows}), the middle kept as it was",
      (L.cols, L.rows) == (160, 120) and {(57, 75), (57, 76), (58, 75), (58, 76)} <= cells)
L.refit(440, 340)
check("...and back", (L.cols, L.rows) == (110, 85) and L.age[40, 50] > 0)
L.restart()
for rules in g.LIFE_RULES:
    L.configure({"rules": rules})
    L.restart()
    run(L, 5)
    if L.gen < 40:
        check(f"...{rules} runs: generation {L.gen}", False)
check("...all four rules run", True)
L.configure({"rules": "Life", "speed": "Fast"})
g0 = L.gen
run(L, 2)
check(f"...Fast: about 25 generations a second ({L.gen - g0} in 2 s)", 40 <= L.gen - g0 <= 52 or L.ended)

# ---- Forest Fire ---------------------------------------------------------------------------------------
ff = g.ForestFire(440, 340, random.Random(1))
check(f"Forest Fire: {ff.cols} x {ff.rows} cells, almost half of them trees",
      (ff.cols, ff.rows) == (110, 85) and 0.4 < ff.counts()[0] / (110 * 85) < 0.5)
ff.values.update(growth="Slow", lightning="Rare")
ff.state[:] = ff.GROUND
ff.state[10, 10:20] = ff.TREE
ff.state[10, 10] = ff.FIRE
g.FIRE_GROW["Slow"], keep = 0.0, g.FIRE_GROW["Slow"]
g.FIRE_STRIKE["Rare"], keep2 = 0.0, g.FIRE_STRIKE["Rare"]
ff.step()
check("...fire spreads to the tree next to it; the fire itself turns to embers",
      ff.state[10, 11] == ff.FIRE and ff.state[10, 10] == ff.EMBER and ff.state[10, 12] == ff.TREE)
ff.step()
check("...embers go out, leaving ash", ff.state[10, 10] == ff.GROUND and ff.ash[10, 10] > 0 and ff.state[10, 12] == ff.FIRE)
for _ in range(20):
    ff.step()
check("...the row burns to the end", (ff.state[10, 10:20] == ff.GROUND).all())
ff.state[:] = ff.GROUND
ff.state[5, 0] = ff.FIRE
ff.state[5, ff.cols - 1] = ff.TREE
ff.step()
check("...the edges don't meet: fire on one side doesn't jump to the other", ff.state[5, ff.cols - 1] == ff.TREE)
g.FIRE_GROW["Slow"], g.FIRE_STRIKE["Rare"] = keep, keep2
ff.values.update(growth="Fast")
ff.state[:] = ff.GROUND
for _ in range(20):
    ff.step()
share = ff.counts()[0] / (ff.cols * ff.rows)
check(f"...trees grow back in empty ground ({share * 100:.0f}% in 20 generations)", 0.3 < share < 0.55)
fires = ff.fires
ff.poke()
check("...X: lightning sets a tree alight", ff.fires == fires + 1 and (ff.state == ff.FIRE).sum() == 1)
ff.restart()
run(ff, 60)
check(f"...an hour of it, in a minute: {ff.fires} fires, the forest at {ff.counts()[0] * 100 // (110 * 85)}%",
      ff.fires >= 1 and ff.counts()[0] > 0 and len(ff.history) > 100)
ff.state[40:45, 50:60] = ff.FIRE
ff.refit(640, 480)
check(f"...full screen: a bigger forest ({ff.cols} x {ff.rows}), the middle kept",
      (ff.cols, ff.rows) == (160, 120) and (ff.state[57:62, 75:85] == ff.FIRE).all())

# ---- Mandelbrot Set ------------------------------------------------------------------------------------
import threading
from PIL import Image
g.Mandelbrot.THREADED = False                      # (its pictures worked out as it goes: no thread)
lv = g.MandelLevel(0, (0.0, 0.0), 0.01, 8, 8, 400)
while not lv.done:
    lv.step()
check("a point in the big heart is in the set (dark), at once", (lv.nu < 0).all() and lv.it == 1)
xs = 1.15 + (np.arange(1701) - 850) * 0.001       # 0.3 to 2.0 along the real line, outside the set
lv = g.MandelLevel(0, (1.15, 0.0), 1.701, 1701, 1, 400)
while not lv.done:
    lv.step()
jump = float(np.abs(np.diff(lv.nu)).max())
check(f"outside, each point gets a smooth count: no jumps from one point to the next ({jump:.3f})",
      (lv.nu >= 0).all() and jump < 0.25 and lv.nu[0] > lv.nu[-1])
z, n = 0j, 0                                       # (by hand: c = 0.5 runs off after a few squarings)
while abs(z) <= 8:
    z, n = z * z + 0.5, n + 1
k = int(np.argmin(np.abs(xs - 0.5)))
check(f"...about as soon as it does by hand (c = 0.5: {n} steps, smoothed {lv.nu[k]:.2f})", n - 2 < lv.nu[k] < n + 1)
M = g.Mandelbrot(436, 342, random.Random(1))
check(f"Mandelbrot: a dive to {M.dive[0]}, from the whole set", M.L == 0 and M.phase == "dive" and M.dive in g.MANDEL_DIVES
      and not any(t.name == "mandelbrot" for t in threading.enumerate()))
bad = []
for dive in g.MANDEL_DIVES:                        # each view inside the one before it, all the way down
    M.dive = dive
    prev = None
    for L in np.arange(0, dive[3] + 0.001, 0.05):
        dx, dy, W = M.view(float(L))
        H = W * 342 / 436
        box = (dive[1] + dx - W / 2, dive[2] + dy - H / 2, dive[1] + dx + W / 2, dive[2] + dy + H / 2)
        if prev and not (box[0] >= prev[0] - 1e-15 and box[1] >= prev[1] - 1e-15 and box[2] <= prev[2] + 1e-15
                         and box[3] <= prev[3] + 1e-15):
            bad.append((dive[0], round(float(L), 2)))
            break
        prev = box
    start = M.view(0)
    if abs(dive[1] + start[0] - g.MANDEL_START[0]) > 1e-12 or abs(dive[2] + start[1] - g.MANDEL_START[1]) > 1e-12:
        bad.append((dive[0], "start"))
check(f"each dive: every view inside the last, from the whole set ({len(g.MANDEL_DIVES)} dives) {bad}", not bad)
names = {d[0] for d in g.MANDEL_DIVES}
check(f"...to {len(names)} places, some ending at a tiny copy of the set", len(names) >= 6
      and sum(1 for d in g.MANDEL_DIVES if d[4]) >= 2)
M = g.Mandelbrot(436, 342, random.Random(1), values={"speed": "Fast"})
M.THREADED = True                                  # (as if a thread did the work: none does, so nothing comes)
for _ in range(40):
    M.update(0.05)
check(f"no pictures yet: it waits ({M.L})", M.L == 0 and M.picture() is None)
M.work(0.0001)
M.finish()
check(f"its first pictures: the whole set, and the next levels ({sorted(M.levels)})", sorted(M.levels) == [0, 1, 2])
for _ in range(400):
    M.update(0.05)
check(f"...it goes in as far as it has pictures for, and waits there ({M.L:.2f})", 2.4 < M.L <= 2.5)
M.finish()
for _ in range(120):
    M.update(0.05)
check(f"more pictures: on it goes ({M.L:.2f}), the levels behind it let go ({sorted(M.levels)})",
      M.L > 3 and min(M.levels) == int(M.L))
M.THREADED = False
before = M.L
for _ in range(400):
    M.update(0.05)
went = M.L - before
check(f"working as it goes: Fast, at most 2.5 s a level ({went:.1f} levels in 20 s)", 6 < went <= 8.01)
img = Image.new("RGB", (436, 342))
times = []
for _ in range(30):
    M.update(0.05)
    a = time.perf_counter()
    M.draw(img, 0, 0)
    times.append(time.perf_counter() - a)
med = sorted(times)[15] * 1000
check(f"a frame: the level it's at grown to fit, the next one in its middle ({med:.2f} ms)", med < 8
      and img.getbbox() is not None and len(set(img.tobytes()[i:i + 3] for i in range(0, 436 * 342 * 3, 3))) > 50)
pic = M.picture()
M.poke()
check("X: new colours", M.picture() is not pic and M.picture().tobytes() != pic.tobytes())
M.configure({"colours": "Ice"})
M.picture()
check("Colours: the pictures in them", M.levels[int(M.L)]["colours"][0] == "Ice")
st = M.stats()
check(f"its numbers: {st}", [k for k, _ in st] == ["Zoom", "Iterations"] and st[0][1].startswith("×")
      and st[1][1].replace(",", "").isdigit())
mp, words = M.inset(150, 118)
check(f"beside it, the whole set small, where it is marked ({words})", mp.size == (150, 118) and words == M.dive[0])
check("...zoom and its words", [g.mandel_zoom(x) for x in (1, 2048, 12000, 3.4e5, 1.2e6, 2.6e9, 2.2e12)] ==
      ["×1", "×2,048", "×12 thousand", "×340 thousand", "×1.2 million", "×2.6 billion", "×2.2 trillion"])
L = M.L
M.refit(640, 480)
check("full screen: the same place and depth, the last picture stretched meanwhile", M.L == L and not M.levels
      and M.picture().size == (640, 480))
M.finish()
M.update(0.05)
check("...then its own pictures, at the new size", M.levels and next(iter(M.levels.values()))["pic"].size == (640, 480)
      and M.picture().size == (640, 480))
M.refit(436, 342)
M.finish()
M.L = M.dive[3] - 0.001
M.finish()
M.update(0.05)
M.update(0.05)
M.picture()
note = M.note()
check(f"the end of the dive: {note}", M.phase == "hold" and note and "The next dive in" in note[1]
      and (("tiny copy" in note[0]) == bool(M.dive[4])))
last = M.dive
for _ in range(int(g.MANDEL_HOLD / 0.05) + 2):
    r = M.update(0.05)
    if r:
        break
check(f"...then the next ({M.dive[0]}), the last fading out", r == "next" and M.dive != last and M.fade is not None
      and M.L == 0 and M.phase == "dive")
for _ in range(40):
    M.update(0.05)
check("...faded", M.fade is None)
P = g.Mandelbrot(436, 342, random.Random(5))
places = [P.dive]
for _ in range(len(g.MANDEL_DIVES) * 3):
    P.restart()
    places.append(P.dive)
n = len(g.MANDEL_DIVES)
check(f"every place before any again ({len(set(places[:n]))} of {n}), never the same twice running",
      len(set(places[:n])) == n and all(a != b for a, b in zip(places, places[1:])))
# exploring: the d-pad moves round the set, A zooms in and Y out, held
X = g.Mandelbrot(436, 342, random.Random(3), values={"mode": "Explore"})
check(f"Explore: from the whole set ({X.phase}, {X.here()})", X.phase == "explore" and X.here() == g.MANDEL_START
      and X.L == 0)
X.finish()
check("...a rough picture first, then a sharp one", X.ex_quick["pic"].size == (109, 86) and X.ex_full["pic"].size == (436, 342))
pic = X.picture()
lv = g.MandelLevel(0, g.MANDEL_START[:2], g.MANDEL_START[2], 436, 342, X.ex_full["maxit"])
while not lv.done:
    lv.step()
check("...the sharp one is the view itself", np.array_equal(lv.nu, X.ex_full["nu"]) and pic.tobytes() == X.ex_full["pic"].tobytes())
X.hold("a")
for _ in range(20):
    X.update(0.05)
X.release("a")
L1 = X.L
for _ in range(10):
    X.update(0.05)
check(f"A held: in it goes, about a level a second ({L1:.2f}), and stops when let go", 1.0 <= L1 <= 1.3 and X.L == L1)
X.configure({"speed": "Fast"})
X.hold("a")
for _ in range(20):
    X.update(0.05)
X.release("a")
check(f"...Zoom: Fast goes in quicker ({X.L - L1:.2f})", 1.6 <= X.L - L1 <= 2.1)
X.configure({"speed": "Normal"})
cx, cy, W = X.here()
X.hold("right"); X.update(0.5); X.release("right")
X.hold("up"); X.update(0.25); X.release("up")
cx2, cy2, _ = X.here()
check(f"right and up: that way, at most 0.6 of the view a second ({(cx2 - cx) / W:.2f}, {(cy2 - cy) / W:.2f})",
      0.3 < (cx2 - cx) / W <= 0.08 + 0.3 + 1e-9 and 0.15 < (cy2 - cy) / W <= 0.08 + 0.15 + 1e-9)
X.nudge("left")
check("a press on its own (the web page's remote): a small step", abs((X.here()[0] - cx2) / W + 0.08) < 1e-9)
X.hold("y")
for _ in range(200):
    X.update(0.05)
X.release("y")
check(f"Y held: out again, to the whole set and no further ({X.L})", X.L == 0)
X.hold("left")
for _ in range(400):
    X.update(0.05)
X.release("left")
check(f"...and no further off the side than {g.Mandelbrot.REACH[0]} ({X.here()[0]})", X.here()[0] == g.Mandelbrot.REACH[0])
X.ex.update(cx=-0.7436447860, cy=0.1318252536, L=40.5)
X.L = 40.5
X.hold("a")
for _ in range(40):
    X.update(0.05)
X.release("a")
check(f"...in, no deeper than the numbers go ({X.L})", X.L == g.Mandelbrot.DEEPEST)
X.hold("down")
time.sleep(1.1)
X.update(0.05)
before = X.here()
X.update(0.05)
check("a button held while it was off the screen is let go", X.here() == before and not X.held)

# what's drawn: each picture where it falls in the view, the sharper on top
X.ex.update(cx=-0.75, cy=0.1, L=4.0)
X.L = 4.0
X.ex_quick = X.ex_full = None
X.finish()
full = X.ex_full
px = full["width"] / 436
img = Image.new("RGB", (436, 342))
g.Mandelbrot.place(img, full, -0.75 + 25 * px, 0.1 - 10 * px, full["width"])
same = img.crop((0, 0, 411, 332)).tobytes() == full["pic"].crop((25, 10, 436, 342)).tobytes()
check("moved 25 px right and 10 down: the same picture, 25 px left and 10 up, to the pixel", same)
img = Image.new("RGB", (436, 342), (1, 2, 3))
g.Mandelbrot.place(img, full, -0.75, 0.1, full["width"] * 4)
inner = [x for x in range(436) if img.getpixel((x, 171)) != (1, 2, 3)]
check(f"zoomed out 2 levels: it's a quarter as wide, in the middle ({inner[0]}..{inner[-1]})",
      inner and 160 <= inner[0] <= 165 and 270 <= inner[-1] <= 275)
X.ex_go(0, 0, 3.0)
X.job = None
spec = X.next_spec()
check(f"zoomed in 3 levels: a rough picture of the new view comes first ({spec['kind']}, {spec['size']})",
      spec["kind"] == "quick" and spec["size"] == (109, 86))
job = g.MandelLevel(spec["level"], spec["middle"], spec["width"], *spec["size"], X.maxit_for(spec["L"], spec["prev"]))
while not job.done:                                # (just that one, as the thread would)
    job.step()
got = {"nu": job.nu, "maxit": job.maxit, "w": job.w, "h": job.h, "pic": None, "colours": None}
X.paint(got, X.colours())
X.publish(spec, got)
X.pic_key = None
pic = X.ex_picture()
cx, cy, W = X.here()
ref = Image.new("RGB", (436, 342), g.MANDEL_INSIDE)
g.Mandelbrot.place(ref, X.ex_quick, cx, cy, W)
pink = Image.new("RGB", (436, 342), (255, 0, 255))
g.Mandelbrot.place(pink, X.ex_quick, cx, cy, W)
check("...over the old sharp one (grown 8 times: rougher still), all of the view covered",
      X.ex_full is full and pic.tobytes() == ref.tobytes() and (255, 0, 255) not in [c for _, c in pink.getcolors(1 << 20)])
spec = X.next_spec()
check("...then the sharp one", spec["kind"] == "full" and spec["size"] == (436, 342))
X.job = g.MandelLevel(spec["level"], spec["middle"], spec["width"], 436, 342, 400)
X.job.spec = spec
gen = X.gen
X.ex_go(0.1, 0, 0)
check("...moved a little meanwhile: it's still worth having", X.job is not None and X.gen == gen)
X.ex_go(0.3, 0, 0)
check("...moved away from it: given up", X.job is None and X.gen == gen + 1)

# Tour and Explore, either way
T2 = g.Mandelbrot(436, 342, random.Random(4))
T2.finish()
for _ in range(60):
    T2.update(0.05)
T2.finish()
T2.update(0.05)
here = T2.here()
pic = T2.picture()
T2.configure({"mode": "Explore"})
check(f"the tour to Explore: from where it was ({T2.phase})", T2.phase == "explore" and T2.here() == here
      and T2.picture().tobytes() == pic.tobytes())
check(f"...its own buttons: {[k for k, _ in T2.hints()]}", [k for k, _ in T2.hints()] == ["✚", "A", "Y", "X", "START"])
mp, words = T2.inset(150, 118)
check(f"...the map says where: {words!r}", "i" in words and words.startswith(f"{here[0]:.5f}"))
T2.refit(640, 480)
check("...full screen: the same view, its pictures again at the new size", T2.here() == here
      and T2.picture().size == (640, 480))
T2.finish()
check("...(the sharp one at the new size)", T2.ex_full["pic"].size == (640, 480))
T2.refit(436, 342)
T2.configure({"mode": "Tour"})
check(f"Explore to the tour: a new dive, the last view fading ({T2.phase}, {T2.L})", T2.phase == "dive" and T2.L == 0
      and T2.fade is not None and T2.ex is None)

g.Mandelbrot.THREADED = True                        # its own thread: works while it's on screen, then rests
T = g.Mandelbrot(436, 342, random.Random(2))
t_end = time.time() + 3
while time.time() < t_end:
    T.update(0.05)
    time.sleep(0.05)
check(f"with a thread of its own: the pictures come ({T.L:.2f}, {sorted(T.levels)})", T.L > 0.2 and len(T.levels) >= 2
      and any(t.name == "mandelbrot" for t in threading.enumerate()))
time.sleep(1.6)
check("...and it rests once it's off the screen", wait_rest(T))
g.Mandelbrot.THREADED = False

# ---- in media mode: every sim -----------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.parts, self.wholes, self.last = [], 0, None
        self.frames = 0

    def show(self, img):
        self.last = img.copy(); self.wholes += 1; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.last = img.copy(); self.parts.append(tuple(box)); FB.count += 1; self.frames = FB.count

    def close(self):
        pass


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()


def frames(secs, step=0.05):
    n = 0
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        m.tick()
        if m.dirty:
            n += 1
        m.flush()
    return n


m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Apps")
m.press("a")
SIMI = m.tab
corner = (g.SIM_BOX[0], g.SIM_BOX[1])
for row, name in enumerate(g.LIBRARY[SIMI]["children"]):
    if row:
        m.press("down")
    if name in ("Clock", "Notes", "Rock Paper Scissors"):
        continue                                   # (test_clock.py, test_notes.py, test_sim.py)
    if next(t for t in g.LIBRARY if t["name"] == name)["type"] != "sim":
        continue                                   # (cmatrix, not a sim of its own: test_cmatrix.py)
    m.press("a")
    s = m.sim_game()
    key = s.key
    check(f"{name}: opens from the list", m.tab_type() == "sim" and g.LIBRARY[m.tab]["name"] == name)
    m.fb.parts.clear(); m.fb.wholes = 0
    n = frames(2)
    check(f"...{n / 2:.0f} frames a second, mostly just the box", g.SIM_FPS - 2 <= n / 2 <= g.SIM_FPS + 2
          and len(m.fb.parts) >= 0.6 * (len(m.fb.parts) + m.fb.wholes))
    shot = m.fb.last
    check("...the box's round corner and edge stay as they are", shot.getpixel(corner) == g.BG
          and shot.getpixel((corner[0] + 1, corner[1] + 1)) == g.BG)
    hints = [label for _, label, *_ in m.sim_hints(s)]
    check(f"...its buttons: {hints}", hints == (["Pause", s.poke_label, "New start", "Explore", "Options"] if key == "mandel"
                                                else ["Pause", s.poke_label, "New start", "Options"]))
    m.press("a")
    frames(0.5)
    check("...A pauses (and says so)", s.paused and m.sim_card[0] == ("paused",))
    clock = s.clock
    frames(1)
    check("...nothing moves meanwhile", s.clock == clock)
    m.press("a")
    m.press("x")
    m.press("y")
    check("...X and Y: a poke, and a new start", not s.paused and s.clock == 0)
    m.press("start")
    rows = [k for k, _, _, _ in m.sim_rows(type(s))]
    check(f"...START: its options {rows}", m.sim_opts == 0 and rows[-1] == "full" and len(rows) == len(s.options) + 1)
    m.dirty = True; m.flush()
    m.fb.last.save(f"{SP}/sims_opts_{key}.png")
    for i, (k, label, ways, default) in enumerate(s.options):
        before = s.values[k]
        m.press("right")
        now = s.values[k]
        saved = m.setting(f"sim_{key}_{k}")
        if not (now == saved and now != before and now in ways):
            check(f"...{label}: {before} -> {now} (kept: {saved})", False)
        m.press("down")
    check("...each option changes, and is kept", True)
    m.press("b")
    check("...B closes it: a new start for the options that need one", m.sim_opts is None and not s.needs_restart())
    m2 = g.Media()
    check("...kept for next time", all(m2.sim_value(type(s), k) == s.values[k] for k, _, _, _ in s.options))
    m.press("select")
    frames(0.5)
    check(f"...SELECT: full screen ({s.w} x {s.h})", m.sim_full() and (s.w, s.h) == (640, 480))
    m.msg = None
    m.fb.parts.clear(); m.fb.wholes = 0
    frames(1)
    shot = m.fb.last
    check("...just the sim: no clock, no numbers, no buttons", m.fb.wholes >= 18 and not m.fb.parts
          and shot.getpixel((630, 10)) != g.BG and shot.getpixel((320, 470)) != g.BG)
    shot.save(f"{SP}/sims_full_{key}.png")
    m.press("select")
    frames(0.2)
    check("...SELECT again: back beside its numbers", not m.sim_full() and (s.w, s.h) == (436, 342))
    m.press("b")
    check("...B: back to the list, it picked", m.tab == SIMI and m.sels[SIMI] == row)
m.press("down")
check("down from the last goes round to the first", m.sels[SIMI] == 0)

# full screen is for every sim; each sim waits while you're elsewhere
m.sels[SIMI] = g.LIBRARY[SIMI]["children"].index("Game of Life")
m.press("a")
life = m.sim_game()
m.press("select")
m.press("b")
m.press("down")
m.press("a")
check("full screen once is full screen for every sim", m.sim_full() and m.sim_game().key == "fire")
m.press("select")
m.press("b")
gen = life.gen
m.sels[SIMI] = g.LIBRARY[SIMI]["children"].index("Game of Life")
m.press("a")
frames(0.05)
check(f"each sim waits while you're elsewhere (generation {gen}, now {life.gen})", life.gen - gen <= 2
      and m.sim_game() is life)
m.press("b")

# the Mandelbrot Set's own buttons, in media mode
m.sels[SIMI] = g.LIBRARY[SIMI]["children"].index("Mandelbrot Set")
m.press("a")
mb = m.sim_game()
m.set_setting("sim_mandel_mode", "Tour")
mb.configure({"mode": "Tour"})
check("the Mandelbrot Set follows held buttons itself (no key repeat), the tour too",
      mb.key == "mandel" and m.holds_buttons() and not m.takes_repeats("a"))
m.msg = None
m.press("down")
check(f"on the tour, the d-pad: exploring from there ({m.msg!r}), kept for next time",
      mb.phase == "explore" and m.setting("sim_mandel_mode") == "Explore" and "Exploring" in (m.msg or "")
      and mb.held == {"down"})
m.release("down")
check("...let go: it stops", not mb.held)
check("...the web page's remote, held down, goes on and on here", m.takes_repeats("a") and m.takes_repeats("left")
      and not m.takes_repeats("x"))
mb.ex["L"] = mb.L = 0.0
m.press("y")
check(f"Y at the whole set: {m.msg!r}", m.msg == "That's the whole set")
m.release("y")
mb.ex["L"] = mb.L = mb.DEEPEST
m.press("a")
check(f"A as deep as it goes: {m.msg!r}", m.msg == "As deep as it can go")
m.release("a")
m.press("start")
check("START's card: the usual repeat for its rows", not m.holds_buttons() and m.sim_opts == 0
      and m.sim_rows(type(mb))[0][0] == "mode")
m.press("right")
m.press("b")
check("...Mode: Tour, a new dive", mb.phase == "dive" and mb.L == 0)
m.press("b")
m.press("b")
check("B from the list: home", m.view == "home")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
