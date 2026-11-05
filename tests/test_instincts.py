"""The AI player's instincts (pitato/instincts.py) and its live play (pitato/anygame.py), on pretend games made here:
a pseudo-3D racing game (a road with bends, grass, rumble strips, the car at the bottom; off the road it's slow, and
there's a wall), the same with the view on the top half of a split screen and a dirt road, and on an N64 (the stick);
a side-scrolling platformer (pipes to jump, pits, enemies; the camera follows); a fighting game's and a shooter's
buttons. Checked: what kind of game it is from its name, and what its buttons do from what's said of them; the racer
keeps on the road through the bends and goes much further than holding the gas alone; the platformer gets much
further than running alone; and the live loop: the decision model asked on its own thread while it plays (the game
not held up), its picks followed (Start on the title screen, then Drive), the kind of game the coach says taken up,
and a model that doesn't answer: it plays on, pressing on through a still screen."""
import math, os, random, sys, threading, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from PIL import Image
from pitato import anygame as AG, gameai as A, instincts as I

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- what kind of game, and its buttons --------------------------------------------------------------------------
for title, kind in (("Super Mario Kart", "racing"), ("F-Zero", "racing"), ("Rad Racer", "racing"),
                    ("Super Mario World", "platformer"), ("Sonic the Hedgehog 2", "platformer"),
                    ("Mega Man 2", "platformer"), ("Street Fighter II Turbo", "fighting"),
                    ("Mortal Kombat II", "fighting"), ("Gradius III", "shooter"), ("Contra", "shooter"),
                    ("Tetris", "puzzle"), ("Dr. Mario", "puzzle"), ("Pokemon - Emerald Version", "rpg"),
                    ("Final Fantasy VI", "rpg"), ("The Legend of Zelda - A Link to the Past", "adventure"),
                    ("Mario Tennis", "sports"), ("Mario Party 2", "other"), ("nestest", "other")):
    got = I.guess_kind(title.lower())
    check(f"{title}: {got}", got == kind)
SNES = ["A", "B", "X", "Y", "L", "R", "Start", "Select"]
r = I.roles_for("snes", SNES, "B: accelerate; A: use an item; L or R: hop; Y: brake")
check(f"what its buttons do, said as Button: what it does ({r['gas']} gas, {r['brake']} brake)",
      r["gas"] == "B" and r["brake"] == "Y")
r = I.roles_for("nes", ["A", "B", "Start", "Select"], "Press A to jump and B to run. Start pauses.")
check(f"...said in a sentence ({r['jump']} jumps, {r['run']} runs)", r["jump"] == "A" and r["run"] == "B")
r = I.roles_for("snes", SNES, "Y punches lightly, X punches hard; B and A kick")
check(f"...every attack ({r['attack']})", r["attack"] == ("Y", "X", "B", "A"))
r = I.roles_for("ps1", ["Cross", "Square", "Circle", "Triangle", "L1", "R1", "L2", "R2", "Start", "Select"], "")
check(f"...nothing said: how most games on the console go (PlayStation: {r['gas']} gas, {r['jump']} jumps)",
      r["gas"] == "Cross" and r["jump"] == "Cross")
r = I.roles_for("gb", ["A", "B", "Start", "Select"], "a jumps; the B button is used to run")
check(f"...a lone small a is the word, not the button ({r['jump']!r} jumps, {r['run']} runs)",
      r["jump"] == "A" and r["run"] == "B")
r = I.roles_for("nes", ["A", "B", "Start", "Select"], "Up: accelerate; Down: brake. Run right with the d-pad")
up = I.Racing("nes", dict(AG.BUTTONS["nes"]), r)
check(f"...the gas a direction (Up: accelerate): held as one ({up.button('gas')}, the brake {up.button('brake')}); "
      f"running isn't (it's {r['run']})", up.button("gas") == "up" and up.button("brake") == "down"
      and r["run"] == "B")
check(f"the kind, from what a model says ({I.kind_of('A 2D side-scrolling platformer')}, "
      f"{I.kind_of('Kart racing')}, {I.kind_of('turn-based RPG')})", I.kind_of("A 2D side-scrolling platformer")
      == "platformer" and I.kind_of("Kart racing") == "racing" and I.kind_of("turn-based RPG") == "rpg")


# ---- a racing game -------------------------------------------------------------------------------------------------
class Race:
    """A pseudo-3D racing game: the road's middle bends by its curvature, the camera behind the car; the car's
    across the road (px, metres from the middle), its speed, how far it's gone. Off the road it's slow; the wall
    stops it."""
    W, H, HORIZON, CAM, F = 256, 224, 90, 1.5, 160.0
    R, WALL = 4.0, 6.5                               # the road's half-width, and the wall from the middle
    VMAX = 50.0

    def __init__(self, split=False, dirt=False, curves=None):
        self.split, self.dirt = split, dirt
        self.curves = curves or [(300, 0.0), (400, 0.004), (200, 0.0), (400, -0.005), (200, 0.0), (300, 0.006),
                                 (300, -0.006), (250, 0.0), (350, 0.005), (300, -0.004)]
        self.z, self.px, self.v = 0.0, 0.0, 0.0
        self.held, self.sticks = set(), {}
        self.gas, self.brake = "b", "y"
        self.on_road = self.frames = self.crashes = 0
        self.title = False
        self.view_h = 112 if split else self.H

    def k(self, z):
        z %= sum(n for n, _ in self.curves)
        for n, k in self.curves:
            if z < n:
                return k
            z -= n
        return 0.0

    def steer(self):
        if "lx" in self.sticks:
            return self.sticks["lx"] / 127.0
        return ("right" in self.held) - ("left" in self.held)

    def step(self, dt=1 / 60):
        self.frames += 1
        if self.title:
            self.title = "start" not in self.held
            return
        gas, brake = self.gas in self.held, self.brake in self.held
        v = self.v + (12.0 if gas else -3.0) * dt - (20.0 if brake else 0.0) * dt
        off = abs(self.px) > self.R
        if off and v > 18.0:
            v -= 25.0 * dt
        self.v = max(-5.0, min(self.VMAX, v))
        self.px += (self.steer() * (3.0 + 0.25 * abs(self.v)) - self.k(self.z) * self.v * self.v * 0.6) * dt
        if abs(self.px) > self.WALL:
            self.px = math.copysign(self.WALL, self.px)
            if abs(self.v) > 5:
                self.crashes += 1
            self.v = 0.0
        self.z += self.v * dt
        self.on_road += not off

    def frame(self):
        W, H = self.W, self.view_h
        img = np.zeros((self.H, W, 3), np.uint8)
        if self.title:
            img[:] = (20, 20, 80)
            img[60:90, 60:196] = (220, 200, 40)
            if (self.frames // 30) % 2:
                img[150:160, 90:166] = (255, 255, 255)
            return Image.fromarray(img)
        horizon = self.HORIZON * H // self.H
        img[:horizon] = (100, 150, 255)
        xs = np.arange(W)
        cum, step_d = [], 1.0                                 # the road's middle, ahead: where it's bent to
        off, slope, d = 0.0, 0.0, 0.0
        for i in range(400):
            cum.append(off)
            slope += self.k(self.z + d) * step_d
            off += slope * step_d
            d += step_d
        for y in range(horizon + 1, H):
            D = self.CAM * self.F / (y - horizon) * (H / self.H)
            if D > 399:
                D = 399
            cx = W / 2 + (cum[int(D)] - self.px) * self.F / D
            half = self.R * self.F / D
            rum = 0.4 * self.F / D
            band = int((self.z + D) / 8) % 2
            if self.dirt:
                grass, road = ((70, 150, 50) if band else (60, 135, 45)), ((150, 110, 60) if band else (140, 102, 55))
            else:
                grass, road = ((40, 160, 40) if band else (30, 140, 30)), ((110, 110, 110) if band else (100, 100, 100))
            row = np.empty((W, 3), np.uint8)
            row[:] = grass
            dist = np.abs(xs - cx)
            row[dist < half] = road
            if not self.dirt:
                row[(dist >= half) & (dist < half + rum)] = (200, 30, 30) if band else (230, 230, 230)
                if band and D < 60:
                    row[dist < 0.12 * self.F / D] = (240, 240, 240)
            img[y] = row
        cy = H - 46 * H // self.H                              # the car, at the bottom in the middle
        img[cy:cy + 22, 112:144] = (200, 20, 20)
        img[cy + 14:cy + 22, 108:116] = img[cy + 14:cy + 22, 140:148] = (10, 10, 10)
        img[cy + 2:cy + 8, 118:138] = (60, 60, 90)
        if self.split:                                         # a black bar, then a map of the track below
            img[H:H + 4] = (0, 0, 0)
            img[H + 4:] = (30, 90, 30)
            for t in range(0, 360, 3):
                x = int(128 + 90 * math.cos(math.radians(t)))
                yy = int(H + 4 + 50 + 40 * math.sin(math.radians(t)))
                if H + 4 <= yy < self.H:
                    img[yy, max(0, x - 2):x + 2] = (160, 160, 160)
            a = (self.z / 1000.0) % 1 * 2 * math.pi
            img[int(H + 54 + 40 * math.sin(a)) - 2:int(H + 54 + 40 * math.sin(a)) + 2,
                int(128 + 90 * math.cos(a)) - 2:int(128 + 90 * math.cos(a)) + 2] = (255, 0, 0)
        return Image.fromarray(img)


def drive(race, secs, inst=None, gas_only=False):
    """Plays the race for so many seconds of its time: the instinct's steps (or just the gas)."""
    t = 0.0
    while t < secs:
        look = A.Look(race.frame())
        if gas_only:
            steps = [({race.gas}, {}, 0.1)]
        else:
            steps = inst.tick(look, t)
        for buttons, sticks, s in steps:
            race.held, race.sticks = set(buttons), dict(sticks)
            for _ in range(max(1, round(s * 60))):
                race.step()
            t += s
    return race


SNES_LIB = dict(AG.BUTTONS["snes"])
roles = I.roles_for("snes", SNES, "B: accelerate; Y: brake")
best = Race.VMAX * 60
base = drive(Race(), 60, gas_only=True)
check(f"a racing game, just the gas held for a minute: off the road in the first bend, into the wall ({base.z:.0f} m, "
      f"{100 * base.on_road / base.frames:.0f}% on the road)", base.on_road / base.frames < 0.5 and base.z < 0.5 * best)
t0 = time.perf_counter()
race = drive(Race(), 60, I.Racing("snes", SNES_LIB, roles))
took = (time.perf_counter() - t0) / 600 * 1000
check(f"...by instinct: on the road through the bends ({100 * race.on_road / race.frames:.0f}% of the time), much "
      f"further ({race.z:.0f} m, of {best:.0f} at full speed all the way), {race.crashes} crashes; "
      f"{took:.1f} ms a look", race.on_road / race.frames > 0.9 and race.z > 0.8 * best and race.crashes == 0)
race = drive(Race(split=True, dirt=True), 60, I.Racing("snes", SNES_LIB, roles))
check(f"...a dirt road, the view on the top half of a split screen (a map below): on the road "
      f"{100 * race.on_road / race.frames:.0f}% of the time, {race.z:.0f} m",
      race.on_road / race.frames > 0.85 and race.z > 0.75 * best)
N64_LIB = dict(AG.BUTTONS["n64"])
n64roles = I.roles_for("n64", [l for l, _ in AG.BUTTONS["n64"]], "")
race = Race()
race.gas, race.brake = "b", "y"                      # (an N64's A and B: libretro's B and Y)
inst = I.Racing("n64", N64_LIB, n64roles, stick=True)
seen_sticks = []
t = 0.0
while t < 60:
    look = A.Look(race.frame())
    for buttons, sticks, s in inst.tick(look, t):
        race.held, race.sticks = set(buttons), dict(sticks)
        if sticks:
            seen_sticks.append(sticks.get("lx", 0))
        for _ in range(max(1, round(s * 60))):
            race.step()
        t += s
check(f"...on an N64, steering with the stick, part way ({len(set(seen_sticks))} different pushes): on the road "
      f"{100 * race.on_road / race.frames:.0f}% of the time, {race.z:.0f} m",
      race.on_road / race.frames > 0.9 and race.z > 0.8 * best and len(set(seen_sticks)) > 5)
wall = Race(curves=[(10000, 0.0)])
wall.px, wall.v = Race.WALL, 30.0                    # (against the wall, going fast: it stops dead)
inst = I.Racing("snes", SNES_LIB, roles)
t, backed = 0.0, False
while t < 8:
    look = A.Look(wall.frame())
    for buttons, sticks, s in inst.tick(look, t):
        wall.held, wall.sticks = set(buttons), dict(sticks)
        backed = backed or "y" in buttons
        for _ in range(max(1, round(s * 60))):
            wall.step()
        if abs(wall.px) > wall.WALL - 0.01 and wall.v == 0 and t > 0.2:
            wall.v = 0.0
        t += s
check(f"hit the wall: it backs up (the brake held) and steers back onto the road ({backed}, {wall.px:.1f} m from "
      f"the middle, {wall.z:.0f} m on)", backed and abs(wall.px) < wall.R and wall.z > 50)


# ---- a platformer -----------------------------------------------------------------------------------------------------
class Level:
    """A side-scrolling platformer: 16-pixel tiles, the floor two tiles deep, pipes to jump over, pits, enemies
    walking at you (jump on them, or they get you); the camera follows. Falling in a pit, or into an enemy: back to
    the last checkpoint."""
    W, H, T = 256, 224, 16

    def __init__(self, length=200):
        self.length = length
        self.pipes = {20: 2, 42: 3, 68: 2, 72: 3, 96: 4, 120: 2, 150: 3, 175: 4}
        self.pits = [(30, 3), (58, 2), (85, 4), (108, 3), (135, 3), (162, 4)]
        self.enemies = [[50 * 16.0, 1], [115 * 16.0, 1], [140 * 16.0, 1], [185 * 16.0, 1]]
        self.x, self.y, self.vx, self.vy = 3 * 16.0, 12 * 16.0 - 24, 0.0, 0.0
        self.ground = True
        self.held = set()
        self.deaths, self.best, self.frames = 0, 0.0, 0
        self.jumped = False
        self.frozen = 0

    def solid(self, tx, ty):
        if tx < 0:
            return True
        if ty >= 12:
            return not any(s <= tx < s + w for s, w in self.pits)
        h = self.pipes.get(tx) or self.pipes.get(tx - 1)
        return bool(h) and ty >= 12 - h

    def die(self):
        self.deaths += 1
        cp = max(3, (int(self.x // 16) // 25) * 25 + 3)
        while not self.solid(cp, 12) or self.solid(cp, 11):
            cp += 1
        self.x, self.y, self.vx, self.vy = cp * 16.0, 12 * 16.0 - 24, 0.0, 0.0
        self.frozen = 40

    def step(self):
        self.frames += 1
        if self.frozen:
            self.frozen -= 1
            return
        run, jump = "y" in self.held, "b" in self.held
        want = ("right" in self.held) - ("left" in self.held)
        self.vx = want * (2.5 if run else 1.5)
        if jump and self.ground and not self.jumped:
            self.vy, self.ground, self.jumped = -6.0, False, True
        if not jump:
            self.jumped = False
        self.vy += 0.22 if (jump and self.vy < 0) else 0.6
        self.vy = min(self.vy, 8.0)
        nx = self.x + self.vx                                   # across: pipes stop it
        top, bottom = int(self.y // 16), int((self.y + 23) // 16)
        lead = int((nx + 13) // 16) if self.vx > 0 else int(nx // 16)
        if not any(self.solid(lead, ty) for ty in range(top, bottom + 1)):
            self.x = nx
        ny = self.y + self.vy                                   # up and down: floors and pipe tops
        self.ground = False
        if self.vy > 0:
            feet = int((ny + 24) // 16)
            if any(self.solid(tx, feet) for tx in (int(self.x // 16), int((self.x + 13) // 16))):
                ny, self.vy, self.ground = feet * 16 - 24.0, 0.0, True
        self.y = ny
        if self.y > self.H + 40:
            return self.die()
        for e in self.enemies:                                  # enemies: walk at you; jumped on, they're gone
            if e[1]:
                e[0] -= 0.6
                if abs(e[0] - self.x) < 14 and 12 * 16 - 14 - 24 <= self.y <= 12 * 16 - 14 + 4:
                    if self.vy > 0 and self.y < 12 * 16 - 14 - 12:
                        e[1], self.vy = 0, -4.0
                    else:
                        return self.die()
        self.best = max(self.best, self.x)

    def frame(self):
        W, H = self.W, self.H
        cam = max(0.0, self.x - 112)
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = (100, 150, 255)
        img[8:16, 8:80] = (255, 255, 255)                       # (a score along the top)
        for sx in range(W):
            tx = int((sx + cam) // 16)
            if self.solid(tx, 12):
                img[192:, sx] = (180, 100, 40) if (tx % 2) else (160, 88, 36)
            h = self.pipes.get(tx) or self.pipes.get(tx - 1)
            if h:
                img[192 - 16 * h:192, sx] = (40, 180, 60)
        for e in self.enemies:
            if e[1]:
                ex = int(e[0] - cam)
                if -16 < ex < W:
                    img[178:192, max(0, ex):max(0, ex + 14)] = (120, 30, 20)
        px, py = int(self.x - cam), int(self.y)
        if py < H:
            img[max(0, py):max(0, py + 12), px:px + 14] = (220, 40, 40)
            img[max(0, py + 12):max(0, min(H, py + 24)), px:px + 14] = (40, 40, 200)
        return Image.fromarray(img)


def play_level(level, secs, inst=None, hold=None):
    t = 0.0
    while t < secs:
        look = A.Look(level.frame())
        steps = [(hold, {}, 0.1)] if hold is not None else inst.tick(look, t)
        for buttons, sticks, s in steps:
            level.held = set(buttons)
            for _ in range(max(1, round(s * 60))):
                level.step()
            t += s
    return level


random.seed(11)
base = play_level(Level(), 60, hold={"right", "y"})
check(f"a platformer, just running right for a minute: stopped at the first pipe (tile {base.best / 16:.0f})",
      base.best / 16 < 21)
proles = I.roles_for("snes", SNES, "B: jump; Y: run")
lv = play_level(Level(), 90, I.Platformer("snes", SNES_LIB, proles))
check(f"...by instinct: over the pipes and pits, past the enemies, to the end of the level (tile {lv.best / 16:.0f}, "
      f"the end at {lv.length}; {lv.deaths} times back to a checkpoint)", lv.best / 16 >= lv.length and lv.deaths <= 3)
foe = Level()
foe.pipes, foe.pits, foe.enemies = {}, [], [[16 * 16.0, 1]]
inst = I.Platformer("snes", SNES_LIB, proles)
inst.next_hop = 1e9
said_foe = []
for k in range(40):
    look = A.Look(foe.frame())
    for buttons, sticks, s_ in inst.tick(look, k * 0.1):
        said_foe.append(inst.said)
        foe.held = set(buttons)
        for _ in range(max(1, round(s_ * 60))):
            foe.step()
check(f"...an enemy coming: it jumps it ({'Jumping something coming' in said_foe}; {foe.deaths} deaths, past it to "
      f"tile {foe.best / 16:.0f})", "Jumping something coming" in said_foe and foe.deaths == 0 and foe.best / 16 > 18)
gap = Level()
gap.x = 26 * 16.0
inst = I.Platformer("snes", SNES_LIB, proles)
inst.next_hop = 1e9                                     # (no hops: only what it sees)
seen_gap = []
for k in range(40):
    look = A.Look(gap.frame())
    steps = inst.tick(look, k * 0.1)
    seen_gap.append(inst.said)
    for buttons, sticks, s in steps:
        gap.held = set(buttons)
        for _ in range(max(1, round(s * 60))):
            gap.step()
check(f"...a pit ahead: it jumps it, just before the edge ({'Jumping a gap' in seen_gap}; got past it to tile "
      f"{gap.best / 16:.0f}, {gap.deaths} falls)", "Jumping a gap" in seen_gap and gap.best / 16 > 33
      and gap.deaths == 0)
mm = I.roles_for("nes", ["A", "B", "Start", "Select"], "A: jump; B: shoot")
inst = I.Platformer("nes", dict(AG.BUTTONS["nes"]), mm)
held_b = [("b" in st_[0]) for k in range(16) for st_ in inst.tick(A.Look(Level().frame()), k * 0.1)]
check(f"...a game whose B shoots (said of it): B isn't held to run, it's pressed every so often "
      f"({''.join('B' if h else '.' for h in held_b)})", 3 <= sum(held_b) <= 5 and not all(held_b[:2]))
inst = I.Platformer("snes", SNES_LIB, proles)
inst.way = "left"
st = inst.tick(A.Look(Level().frame()), 0.0)
check(f"...told the level goes left: left and the run button held ({sorted(st[0][0])})", {"left", "y"} <= st[0][0])


# ---- a fighting game, a shooter: their buttons -------------------------------------------------------------------
froles = I.roles_for("snes", SNES, "Y and X punch; B and A kick")
f = I.Fighter("snes", SNES_LIB, froles)
random.seed(4)
blank = A.Look(Image.new("RGB", (256, 224), (90, 60, 120)))
moves, specials = [], 0
for k in range(200):
    steps = f.tick(blank, k * 0.1)
    moves += [b for st_ in steps for b in st_[0]]
    specials += f.said == "A special move"
used = {b for b in moves if b in ("y", "x", "b", "a")}
check(f"a fighting game: a mix of attacks ({sorted(used)}), moving in and blocking ({moves.count('right')} right, "
      f"{moves.count('left')} left), jumps ({moves.count('up')}), special moves ({specials})",
      used == {"y", "x", "b", "a"} and moves.count("right") > moves.count("left") > 0 and moves.count("up") > 0
      and specials > 10)
f.way = "left"
moves = [b for k in range(200) for st_ in f.tick(blank, k * 0.1) for b in st_[0]]
check(f"...the other fighter on the left: toward the left ({moves.count('left')} left, {moves.count('right')} right)",
      moves.count("left") > moves.count("right"))
sroles = I.roles_for("snes", SNES, "Y: shoot")
sh = I.Shooter("snes", SNES_LIB, sroles)
stars = np.random.default_rng(2).integers(0, 2, size=(224, 256)) * 200


def space(k, vertical):
    a = np.roll(stars, (4 * k, 0) if vertical else (0, -4 * k), axis=(0, 1)).astype(np.uint8)
    return A.Look(Image.fromarray(np.stack([a, a, a], -1)))


fires, ways = [], set()
for k in range(40):
    steps = sh.tick(space(k, vertical=False), k * 0.1)
    fires += ["y" in st_[0] for st_ in steps]
    ways |= {b for st_ in steps for b in st_[0] if b in ("up", "down", "left", "right")}
sh2 = I.Shooter("snes", SNES_LIB, sroles)
ways2 = set()
for k in range(40):                                  # (once it's seen which way it scrolls)
    got = {b for st_ in sh2.tick(space(k, vertical=True), k * 0.1) for b in st_[0] if b in ("up", "down", "left", "right")}
    ways2 |= got if k >= 12 else set()
check(f"a shooter: fire pressed and let go each moment ({fires[:4]}...), weaving up and down when it scrolls "
      f"sideways ({sorted(ways)}), left and right when it scrolls up ({sorted(ways2)})",
      fires[:4] == [True, False, True, False] and ways <= {"up", "down"} and ways and ways2 <= {"left", "right"}
      and ways2)


# ---- the live loop: a racing game, the decision model on its own thread ---------------------------------------------
class Owner:
    def __init__(self):
        self.stopping, self.model, self.server, self.offline = threading.Event(), "clef", "", False


class LiveIO:
    """What anygame needs of gameai's GameIO, on a pretend game (real time: the game moves on as it waits)."""

    def __init__(self, game, model):
        self.g, self.model = game, model
        self.ai = Owner()
        self.held, self.pushed, self.sticks = set(), set(), {}
        self.blind, self.last_by = False, "model"
        self.asked, self.logged, self.statuses, self.taps = [], [], [], []
        self.lock = threading.Lock()
        self.looks = 0
        self.t0 = time.monotonic()
        self.most = 8.0

    def live(self):
        if self.ai.stopping.is_set() or time.monotonic() - self.t0 > self.most:
            raise A.emerald.Stop()

    def look(self):
        self.live()
        self.looks += 1
        with self.lock:
            return A.Look(self.g.frame())

    def advance(self, secs):
        end = time.monotonic() + secs
        while True:
            left = end - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(left, 1 / 60))
            with self.lock:
                self.g.held, self.g.sticks = set(self.held), dict(self.sticks)
                self.g.step()

    def wait(self, secs):
        self.live()
        self.advance(secs)

    def hold_only(self, buttons, sticks=None):
        self.held, self.sticks = set(buttons), dict(sticks or {})

    def hold(self, b):
        self.held.add(b)

    def release(self, b):
        self.held.discard(b)

    def stick(self, axis, v):
        self.sticks[axis] = v

    def let_go(self):
        self.held, self.sticks = set(), {}

    def tap(self, b):
        self.taps.append(b)
        if b == "start" and getattr(self.g, "title", False):
            self.g.title = False
        self.held.add(b)
        self.advance(0.05)
        self.held.discard(b)
        self.advance(0.06)

    def decide(self, kind, says, state, choices, fallback, picture=None, quiet=False):
        self.asked.append({"kind": kind, "state": state, "choices": dict(choices), "says": says,
                           "at": time.monotonic(), "thread": threading.current_thread().name, "picture": picture})
        pick, self.last_by = self.model(self.g, choices, fallback)
        return pick

    def status(self, w):
        self.statuses.append(w)

    def log(self, **e):
        self.logged.append(e)


def racer(game, choices, fallback):
    time.sleep(0.4)                                   # (it thinks a while: the game goes on meanwhile)
    want = "start" if game.title or "drive" not in choices else "drive"
    return want, "model"


race = Race()
race.title = True
io = LiveIO(race, racer)
p = AG.AnyGame({"title": "Super Mario Kart (USA)", "system": "snes"}, io)
check(f"a racing game, by its name: played by instinct ({p.kind}; {io.logged[:1]})", p.kind == "racing")
try:
    p.play()
except A.emerald.Stop:
    pass
asked = io.asked
gaps = [b["at"] - a["at"] for a, b in zip(asked, asked[1:])]
check(f"the model asked again and again, on a thread of its own ({len(asked)} times, "
      f"{asked[0]['thread'] if asked else None}), shown the screen each time, while it looked {io.looks} times",
      len(asked) >= 5 and all(a["thread"] == "game-ai-decide" for a in asked) and io.looks > 3 * len(asked)
      and all(isinstance(a["picture"], A.Look) for a in asked))
ch = asked[0]["choices"] if asked else {}
check(f"...its choices: Drive, and the buttons for a menu ({len(ch)}); told it's a racing game, what's going on now "
      f"({asked[-1]['state'].get('now') if asked else None!r})", "drive" in ch and "start" in ch and "a" in ch
      and asked[-1]["state"].get("kind of game") == "racing" and "Drive" in asked[-1]["says"])
check(f"...Start pressed on the title screen ({io.taps}), then it drove: {race.z:.0f} m, on the road "
      f"{100 * race.on_road / max(1, race.frames):.0f}% of the time", io.taps.count("start") >= 1 and not race.title
      and race.z > 150 and race.on_road / max(1, race.frames) > 0.85)


class Coach:
    def __init__(self, card):
        self.c, self.advice, self.tips, self.seen, self.nudges = card, None, "", [], 0

    def start(self, *a):
        pass

    def see(self, look, story):
        self.seen.append(story)

    def nudge(self):
        self.nudges += 1

    def controls(self):
        return ""

    def card(self):
        return self.c


race = Race()
race.gas, race.brake = "a", "b"                     # (this game's gas is A, as the coach says)
io = LiveIO(race, racer)
io.most = 6.0
coach = Coach({"kind": "", "buttons": "", "how": ""})
p = AG.AnyGame({"title": "Untitled (USA)", "system": "snes"}, io, coach)
kinds = []
real_turn = p.turn


def turn_then_say():
    kinds.append(p.kind)
    coach.c = {"kind": "racing", "buttons": "A: accelerate; B: brake", "how": "Take the inside line."}
    real_turn()


p.turn = turn_then_say
try:
    p.play()
except A.emerald.Stop:
    pass
check(f"a game whose kind isn't known from its name: a move at a time ({kinds[:1]}); the coach says it's a racing "
      f"game, A the gas: by instinct from then on ({p.kind}, {p.instinct.roles['gas'] if p.instinct else None} the gas, "
      f"{race.z:.0f} m)", kinds[:1] == ["other"] and p.kind == "racing" and p.instinct.roles["gas"] == "A"
      and any("racing game" in str(e.get("event")) for e in io.logged) and race.z > 50)
told = {k: v for k, v in io.asked[-1]["state"].items() if k in ("kind of game", "its buttons", "how it's played well")}
check(f"...the model's told what it knows of the game ({told})",
      io.asked[-1]["state"].get("its buttons") == "A: accelerate; B: brake"
      and io.asked[-1]["state"].get("how it's played well") == "Take the inside line.")


def silent(game, choices, fallback):
    time.sleep(0.05)
    return fallback, "own"                          # (its computer isn't answering)


race = Race()
race.title = True
io = LiveIO(race, silent)
io.most = 9.0
p = AG.AnyGame({"title": "F-Zero (USA)", "system": "snes"}, io)
try:
    p.play()
except A.emerald.Stop:
    pass
check(f"the model not answering: the title screen sat still, so it pressed on (Start), then raced by "
      f"instinct ({race.z:.0f} m; {[e['event'] for e in io.logged if 'answering' in str(e.get('event'))][:1]})",
      not race.title and race.z > 100 and any("isn't answering" in str(e.get("event")) for e in io.logged))

# ---- a game from its start: past its title screen (Start), whatever the model says ---------------------------------------
class TitledLevel(Level):
    """The platformer from its start: its title screen first (its logo over the level, the player standing in it, and
    now and then its own demo: the level going by by itself), where only Start does anything; then a moment of black
    (WORLD 1-1), and the level. In the level, Start pauses it (the picture still), and Start again plays on."""

    def __init__(self):
        super().__init__()
        self.title, self.demo, self.black, self.paused, self.pauses, self.begun, self.was = True, 0, 0, False, 0, False, 0

    def step(self):
        start = "start" in self.held
        edge, self.was = start and not self.was, start
        if self.title:
            self.demo += 1
            self.frames += 1
            return
        if not self.begun:
            self.begun, self.black = True, 30
        if self.black:
            self.black -= 1
            self.frames += 1
            return
        if edge:
            self.paused = not self.paused
            self.pauses += 1
        if self.paused:
            self.frames += 1
            return
        super().step()

    def frame(self):
        if self.black:
            img = np.zeros((self.H, self.W, 3), np.uint8)
            img[100:116, 90:170] = (255, 255, 255)
            return Image.fromarray(img)
        if self.title:
            x = self.x
            if (self.demo // 60) % 4 >= 2:                   # (its own demo: the level going by)
                self.x = x + (self.demo % 120) * 3.0
            img = np.asarray(super().frame()).copy()
            self.x = x
            img[40:90, 48:208] = (200, 60, 30)               # (its logo)
            return Image.fromarray(img)
        return super().frame()


def sure_its_playing(game, choices, fallback):
    time.sleep(0.2)                                   # (a level, it thinks: the title screen looks like one)
    return ("go_right" if "go_right" in choices else fallback), "model"


lvl = TitledLevel()
io = LiveIO(lvl, sure_its_playing)
io.most = 12.0
p = AG.AnyGame({"title": "Super Mario Bros. (World)", "system": "nes"}, io)
try:
    p.play()
except A.emerald.Stop:
    pass
said = [e["event"] for e in io.logged if "Start" in str(e.get("event")) or "went somewhere" in str(e.get("event"))]
check(f"a game from its start, its title screen like a level with a demo of its own, the model sure it's playing: "
      f"Start pressed a few seconds in ({io.taps}), into the game, and on through the level ({lvl.best:.0f} px; "
      f"{said[:2]})", io.taps[:1] == ["start"] and not lvl.title and not lvl.paused and lvl.best > 3 * 16 + 150
      and any("went somewhere" in e for e in said))

lvl = TitledLevel()
lvl.title = False                                     # (going already: Start pauses it)
io = LiveIO(lvl, sure_its_playing)
io.most = 10.0
p = AG.AnyGame({"title": "Super Mario Bros. (World)", "system": "nes"}, io)
try:
    p.play()
except A.emerald.Stop:
    pass
check(f"...a game going already: Start paused it, so it pressed Start again, and played on ({io.taps}, "
      f"{lvl.pauses} pauses, {lvl.best:.0f} px)", io.taps == ["start", "start"] and lvl.pauses == 2
      and not lvl.paused and lvl.best > 3 * 16 + 100)

lvl = TitledLevel()
lvl.title = False
io = LiveIO(lvl, sure_its_playing)
io.run = type("Run", (), {"resumed": True})()        # (from where you were in it: a save of yours)
io.most = 7.0
p = AG.AnyGame({"title": "Super Mario Bros. (World)", "system": "nes"}, io)
try:
    p.play()
except A.emerald.Stop:
    pass
check(f"...a game it carries on from where you were: no Start ({io.taps})", "start" not in io.taps
      and lvl.pauses == 0)


# ---- the decision model's thread: an answer that's no longer wanted; a pick from another kind's choices ----------------
class SlowIO:
    def __init__(self):
        self.ai, self.go, self.last_by, self.logged = Owner(), threading.Event(), "model", []

    def decide(self, kind, says, state, choices, fallback, picture=None, quiet=False):
        self.go.wait(5)
        return next(iter(choices))

    def log(self, **e):
        self.logged.append(e)


sio = SlowIO()
d = AG.Decider(sio)
d.ask("says", {}, {"go_right": "Play"}, "go_right", False)
time.sleep(0.2)
d.forget()                                          # (the kind of game changed meanwhile)
sio.go.set()
time.sleep(0.3)
dropped = d.take()
d.ask("says", {}, {"drive": "Drive"}, "drive", False)
time.sleep(0.3)
check(f"the model's answer to a question from before the kind of game changed: dropped ({dropped}); the next one "
      f"taken ({d.take()})", dropped is None and d.idle())
sio.ai.stopping.set()
race = Race()
io = LiveIO(race, racer)
p = AG.AnyGame({"title": "Super Mario Kart (USA)", "system": "snes"}, io)
p.make_instinct()
check(f"...and a pick that isn't one of this kind's: passed over, no error ({p.follow(('go_right', 'model'), None)}, "
      f"{p.mode})", p.mode == "menu")


class Run:                                           # (a game that won't give its picture)
    state, ended = "on", False

    def __init__(self):
        self.asks = []

    def ask(self, line, wants, timeout=3.0):
        self.asks.append(time.monotonic())
        return None, ""


class Owner2:
    def __init__(self, run):
        self.run, self.stopping, self.model, self.server = run, threading.Event(), "", ""

    def set_status(self, w):
        pass

    def log(self, e):
        pass


run_ = Run()
gio = A.GameIO(Owner2(run_), None)
A.SHOT_WAIT = 0.01
t_end = time.monotonic() + 3.0
while time.monotonic() < t_end:
    gio.look()
    time.sleep(0.05)
check(f"a game that won't give its picture: asked three times, then again every {A.SHOT_AGAIN:.0f} s, not every "
      f"moment ({len(run_.asks)} asks in 3 s)", 3 < len(run_.asks) <= 5)
gio.close()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
