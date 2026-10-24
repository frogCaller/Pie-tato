"""The Simulator's little worlds: Rock Paper Scissors, Game of Life, Orbits and Forest Fire, and
what they share."""
import math
import random
from collections import deque

from .theme import co_mix


# ---- the Simulator tab: little worlds to watch ---------------------------------------------------------
# Each sim runs in a box beside its numbers, or on the whole screen (SELECT, or START's Full screen). A
# pauses, X gives it a poke, Y starts it again, START has its options, B goes back to the list.
# Rock Paper Scissors: pieces bounce around, and one hit by its counter switches sides until one team is
# left (pick a winner before the first capture). Game of Life, Orbits and Forest Fire: see their blurbs
# below, and mandelbrot.py for the Mandelbrot Set.
SIM_FLOOR = (21, 27, 33)                      # the box
SIM_BOX = (12, 78, 452, 424)                  # ...on the GPi Case's screen (a wider one: the box is wider)
SIM_IN = 2                                    # pieces keep this far in from its wall
SIM_PANEL = (468, 78, 628, 424)               # the numbers, beside it
SIM_DIRTY = (SIM_BOX[0], SIM_BOX[1], SIM_PANEL[2], SIM_PANEL[3])   # what changes from one frame to the next
SIM_FPS, SIM_FPS_BIG = 20, 10                 # frames a second (a Pi Zero on a TV: fewer, each one scaled up)
SIM_SAMPLE = 0.2                              # seconds between a chart's points
SIM_FULL = ("full", "Full screen", ("Off", "On"), "Off")   # (the last row of every sim's START card)


def sim_clock(secs):
    """1:05"""
    return f"{int(secs) // 60}:{int(secs) % 60:02d}"


def sim_hue(h, s=0.45, v=1.0):
    import colorsys
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


class Sim:
    """A little world in a box, w x h px. update moves it on, draw puts it on the screen (the box's
    top-left at x0, y0), poke is X, restart is Y. Its options - (key, label, choices, default) - are
    START's card; values holds what you picked."""
    key = ""
    blurb = ""
    poke_label = None               # X: what it does, or None
    options = ()
    restart_for = ()                # options it starts again for

    def __init__(self, w, h, rng=None, values=None):
        self.w, self.h = w, h
        self.rng = rng or random.Random()
        self.values = {k: d for k, _, _, d in self.options}
        self.values.update(values or {})
        self.paused = False
        self.clock = self.sampled = 0.0
        self.history = []               # (seconds, counts...), for a chart
        self.started = {}               # the options it last started with (those it starts again for)

    def configure(self, values):
        """Your choices, put to use: True if it has to start again for them."""
        changed = {k for k, v in values.items() if self.values.get(k) != v}
        self.values.update(values)
        self.apply()
        return bool(changed & set(self.restart_for))

    def apply(self):
        pass

    def needs_restart(self):
        """An option it starts again for has changed since it last started."""
        return any(self.values.get(k) != self.started.get(k) for k in self.restart_for)

    def restart(self):
        self.clock = self.sampled = 0.0
        self.history = []
        self.started = {k: self.values.get(k) for k in self.restart_for}

    def refit(self, w, h):
        """The box changes size (full screen, and back)."""
        self.w, self.h = w, h
        self.restart()

    def update(self, dt):
        return None

    def poke(self):
        pass

    def draw(self, img, x0, y0):
        pass

    def stats(self):
        """(label, value) rows for beside the box."""
        return []

    def chart(self):
        """(history, colours, top) for a chart beside the box, or None."""
        return None

    def note(self):
        """(title, words) for a card at the foot of the box, or None."""
        return None

    def note_top(self):
        """The card goes at the top of the box instead (out of the way of something at the foot)."""
        return False

    def inset(self, w, h):
        """(a picture w x h, a line under it) for beside the box instead of a chart, or None."""
        return None

    def hints(self):
        """Its buttons along the bottom, if it has its own: [(button, what it does)], or None."""
        return None

    def look(self):
        """Something that changes what's beside the box besides its numbers (drawn again when it does), or
        None."""
        return None

    def sample(self, counts):
        self.history.append((self.clock, tuple(counts)))
        if len(self.history) > 400:              # a long run: every other point
            self.history = self.history[:-1:2] + self.history[-1:]

    def np_rng(self):
        import numpy as np
        return np.random.default_rng(self.rng.randrange(1 << 30))

    @staticmethod
    def regrid(old, rows, cols, fill):
        """A board made bigger or smaller round its middle: what fits is kept, new edges come from
        fill(shape)."""
        new = fill((rows, cols)).astype(old.dtype)
        h, w = min(rows, old.shape[0]), min(cols, old.shape[1])
        ny, nx, oy, ox = (rows - h) // 2, (cols - w) // 2, (old.shape[0] - h) // 2, (old.shape[1] - w) // 2
        new[ny:ny + h, nx:nx + w] = old[oy:oy + h, ox:ox + w]
        return new


# ---- Rock Paper Scissors ---------------------------------------------------------------------------------
RPS_TEAMS = ("Rock", "Scissors", "Paper")      # each one beats the next, and Paper beats Rock
RPS_COLOUR = ((154, 148, 139), (226, 123, 140), (127, 166, 222))      # ...their colours
RPS_ROCK_EDGE = (94, 89, 82)
RPS_SHEET, RPS_SHEET_EDGE = (230, 236, 241), (127, 142, 156)
RPS_BLADE, RPS_BLADE_EDGE = (201, 210, 217), (134, 146, 156)
RPS_COUNTS = (5, 10, 15, 20, 25, 30)                            # pieces per team
RPS_SIZES = (("Small", 10), ("Medium", 13), ("Large", 16))       # how big a piece is (its radius, px)
RPS_SPEEDS = (("Slow", 40), ("Normal", 70), ("Fast", 120), ("Very fast", 200))   # px a second
RPS_READY = 3               # seconds to pick a winner before a round starts
RPS_NEXT = 10               # seconds the winner shows, then the next round starts by itself
RPS_TURNS = 48              # the angles a piece is drawn at (each one drawn once, then kept)
RPS_EASE = 1.5              # how quickly a piece gets back to the speed (after a bump or a shake)
RPS_LOOKS = random.Random(5)
RPS_ROCKS = [[0.78 + RPS_LOOKS.random() * 0.22 for _ in range(10)] for _ in range(6)]   # six rocks' shapes


def rps_span(r):
    """How wide a piece's picture is (square): room for it at any angle."""
    return 2 * int(math.ceil(r * 1.1)) + 4


def rps_sprite(team, r, turn, look=0):
    """A piece of a team (0 rock, 1 scissors, 2 paper), turned to one of RPS_TURNS angles: drawn four
    times bigger and shrunk, for smooth edges. RGBA, the piece's middle in its middle."""
    from PIL import Image, ImageDraw
    K = 4
    S = rps_span(r)
    big = Image.new("RGBA", (S * K, S * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c = S * K / 2
    a = turn * 2 * math.pi / RPS_TURNS
    ca, sa = math.cos(a), math.sin(a)

    def P(px, py):
        return (c + (px * ca - py * sa) * K, c + (px * sa + py * ca) * K)

    def dot(px, py, rad, fill):
        x, y = P(px, py)
        d.ellipse((x - rad * K, y - rad * K, x + rad * K, y + rad * K), fill=fill)

    def seg(p, q, w, fill):                    # a line with round ends
        for x, y in (P(*p), P(*q)):
            d.ellipse((x - w * K / 2, y - w * K / 2, x + w * K / 2, y + w * K / 2), fill=fill)
        d.line((P(*p), P(*q)), fill=fill, width=max(1, round(w * K)))

    def edge(pts, w, fill):                    # an outline, its corners rounded (round once more)
        d.line(pts + pts[:2], fill=fill, width=max(1, round(w * K)), joint="curve")

    if team == 0:                              # a lumpy stone
        shape = RPS_ROCKS[look % len(RPS_ROCKS)]
        n = len(shape)
        pts = [P(math.cos(i / n * 2 * math.pi) * r * s, math.sin(i / n * 2 * math.pi) * r * s)
               for i, s in enumerate(shape)]
        d.polygon(pts, fill=RPS_COLOUR[0])
        edge(pts, max(1, r * 0.09), RPS_ROCK_EDGE)
        dot(-r * 0.25, -r * 0.25, r * 0.28, co_mix(RPS_COLOUR[0], (255, 255, 255), 0.18))
        dot(r * 0.3, r * 0.15, r * 0.08, RPS_ROCK_EDGE)
        dot(-r * 0.05, r * 0.42, r * 0.06, RPS_ROCK_EDGE)
    elif team == 2:                            # a sheet with a folded corner, written on
        w, hh, f = r * 0.62, r * 0.8, r * 0.3
        pts = [P(-w, -hh), P(w - f, -hh), P(w, -hh + f), P(w, hh), P(-w, hh)]
        d.polygon(pts, fill=RPS_SHEET)
        lw = max(1, r * 0.07)
        edge(pts, lw, RPS_SHEET_EDGE)
        d.line((P(w - f, -hh), P(w - f, -hh + f), P(w, -hh + f)), fill=RPS_SHEET_EDGE,
               width=max(1, round(lw * K)), joint="curve")
        for y in (-0.22, 0.08, 0.38):
            seg((-w * 0.62, y * r), (w * (0.3 if y < 0 else 0.62), y * r), max(1.2, r * 0.1), RPS_COLOUR[2])
    else:                                      # two blades and two rings
        for sgn in (1, -1):
            seg((-r * 0.3, sgn * r * 0.2), (r * 0.92, -sgn * r * 0.34), r * 0.22, RPS_BLADE_EDGE)
            seg((-r * 0.3, sgn * r * 0.2), (r * 0.9, -sgn * r * 0.33), r * 0.12, RPS_BLADE)
        o = (0.26 + 0.08) * r * K
        for sgn in (1, -1):
            x, y = P(-r * 0.56, sgn * r * 0.36)
            d.ellipse((x - o, y - o, x + o, y + o), outline=RPS_COLOUR[1], width=max(1, round(r * 0.16 * K)))
        dot(r * 0.12, 0, r * 0.08, RPS_BLADE_EDGE)
    return big.reduce(K)


class RockPaperScissors(Sim):
    """Rock, paper and scissors bounce around the box; a piece hit by its counter switches sides, until
    one team is left. A round: a moment to pick a winner (ready), the round (on), the winner (over), then
    the next round by itself. Positions are px inside the box."""
    key = "rps"
    blurb = "Paper covers rock, rock crushes scissors, scissors cut paper. A piece hit by its counter switches sides."
    poke_label = "Shake"
    options = (("count", "Pieces per team", RPS_COUNTS, 20),
               ("size", "Size", tuple(n for n, _ in RPS_SIZES), "Medium"),
               ("speed", "Speed", tuple(n for n, _ in RPS_SPEEDS), "Normal"))
    restart_for = ("count",)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.count, self.r, self.speed = 20, 13, 70   # pieces per team, their radius, px a second
        self.x, self.y, self.vx, self.vy = [], [], [], []
        self.t = []                     # each piece's team
        self.ang, self.spin, self.look = [], [], []
        self.round = 0
        self.phase = "ready"            # ready (a moment to pick a winner), on, over (a team has won)
        self.wait = 0.0                 # ready: seconds until it starts; over: until the next round
        self.captures = 0
        self.pick = None                # the team you think will win (kept for the next rounds)
        self.winner = None
        self.calls = [0, 0]             # winners you picked, rounds you picked one in
        self.sprites = {}               # (team, look, turn) -> a piece's picture, at the size it is now
        self.apply()
        self.new_round()

    def apply(self):
        self.count = self.values["count"]
        self.resize(dict(RPS_SIZES)[self.values["size"]])
        self.speed = dict(RPS_SPEEDS)[self.values["speed"]]

    def restart(self):
        self.new_round()

    # -- a round ------------------------------------------------------------------------------
    def new_round(self):
        """Each team in a bunch of its own, round the middle, set off in all directions."""
        rnd, W, H = self.rng, self.w, self.h
        base = rnd.random() * math.pi * 2
        homes = [(W / 2 + math.cos(base + t * math.pi * 2 / 3) * W * 0.3,
                  H / 2 + math.sin(base + t * math.pi * 2 / 3) * H * 0.3) for t in range(3)]
        xs, ys, ts = [], [], []
        for t in range(3):
            for _ in range(self.count):
                x, y = self.free_spot(xs, ys, homes, t)
                xs.append(x)
                ys.append(y)
                ts.append(t)
        order = list(range(len(xs)))
        rnd.shuffle(order)                      # (no team always drawn on top)
        self.x, self.y, self.t = [xs[i] for i in order], [ys[i] for i in order], [ts[i] for i in order]
        self.vx, self.vy = [], []
        for _ in order:
            a = rnd.random() * math.pi * 2
            self.vx.append(math.cos(a) * self.speed)
            self.vy.append(math.sin(a) * self.speed)
        self.ang = [rnd.random() * math.pi * 2 for _ in order]
        self.spin = [(rnd.random() - 0.5) * 1.2 for _ in order]
        self.look = [rnd.randrange(len(RPS_ROCKS)) for _ in order]
        self.round += 1
        self.phase, self.wait, self.paused = "ready", float(RPS_READY), False
        self.clock = self.sampled = 0.0
        self.captures = 0
        self.winner = None
        self.history = []
        self.started = {k: self.values.get(k) for k in self.restart_for}
        self.sample(self.counts())

    def free_spot(self, xs, ys, homes, t):
        """A place no piece is on yet, near team t's home and nearer it than the others' (a small box
        fills up: the bunch spreads out on its own side), or anywhere on its side."""
        rnd, r, W, H = self.rng, self.r, self.w, self.h
        far = (2 * r) ** 2
        cx, cy = homes[t]
        spread = min(W, H) * 0.2
        best = None
        for k in range(150):
            a, d = rnd.random() * math.pi * 2, math.sqrt(rnd.random()) * spread * (1 + k / 25)
            x = min(max(cx + math.cos(a) * d, r), W - r)
            y = min(max(cy + math.sin(a) * d, r), H - r)
            mine = (x - cx) ** 2 + (y - cy) ** 2
            if any((x - hx) ** 2 + (y - hy) ** 2 < mine for hx, hy in homes):
                continue                                   # (another team's side)
            if all((ox - x) ** 2 + (oy - y) ** 2 >= far for ox, oy in zip(xs, ys)):
                return x, y
            if best is None:
                best = (x, y)
        return best or (min(max(cx, r), W - r), min(max(cy, r), H - r))

    def is_open(self):
        """Picks are open until the first capture."""
        return self.phase == "ready" or (self.phase == "on" and not self.captures)

    def choose(self, d):
        """Left and right: no pick, Rock, Scissors, Paper."""
        ways = [None, 0, 1, 2]
        self.pick = ways[(ways.index(self.pick) + d) % len(ways)]

    def start(self):
        if self.phase == "ready":
            self.phase, self.wait = "on", 0.0

    def shake(self):
        for i in range(len(self.x)):
            a = self.rng.random() * math.pi * 2
            self.vx[i], self.vy[i] = math.cos(a) * self.speed * 1.8, math.sin(a) * self.speed * 1.8

    def poke(self):
        if self.phase != "ready":
            self.shake()

    def resize(self, r):
        self.r = r
        for i in range(len(self.x)):
            self.x[i] = min(max(self.x[i], r), max(r, self.w - r))
            self.y[i] = min(max(self.y[i], r), max(r, self.h - r))

    def refit(self, w, h):
        """The box changes size (full screen, and back): everything spreads out or closes up with it."""
        sx, sy = w / self.w, h / self.h
        self.w, self.h = w, h
        r = self.r
        for i in range(len(self.x)):
            self.x[i] = min(max(self.x[i] * sx, r), max(r, w - r))
            self.y[i] = min(max(self.y[i] * sy, r), max(r, h - r))

    def counts(self):
        c = [0, 0, 0]
        for t in self.t:
            c[t] += 1
        return c

    def update(self, dt):
        """Time goes on: "won" when a team has just won, "next" when the next round has begun."""
        if self.paused or dt <= 0:
            return None
        if self.phase == "ready":
            for i in range(len(self.ang)):
                self.ang[i] += self.spin[i] * dt
            self.wait -= dt
            if self.wait <= 0:
                self.start()
            return None
        self.move(dt)
        if self.phase == "over":
            self.wait -= dt
            if self.wait <= 0:
                self.new_round()
                return "next"
            return None
        self.clock += dt
        self.sampled += dt
        if self.sampled >= SIM_SAMPLE:
            self.sampled = 0.0
            self.sample(self.counts())
        left = set(self.t)
        if len(left) == 1:
            self.winner = left.pop()
            self.phase, self.wait = "over", float(RPS_NEXT)
            self.sample(self.counts())
            if self.pick is not None:
                self.calls = [self.calls[0] + (self.pick == self.winner), self.calls[1] + 1]
            return "won"
        return None

    def move(self, dt):
        """Everything moves on: off the walls, off each other, and a piece hit by its counter
        changes sides. (Small steps, with only nearby pieces checked: quick enough for a Pi Zero.)"""
        n = len(self.x)
        if not n:
            return
        X, Y, VX, VY, T = self.x, self.y, self.vx, self.vy, self.t
        r, W, H = self.r, self.w, self.h
        rr = 2 * r
        rr2 = rr * rr
        lo, hi_x, hi_y = r, W - r, H - r
        top = max(max(map(abs, VX)), max(map(abs, VY)))
        steps = max(2, min(8, int(math.ceil(top * 1.42 * dt / (0.5 * r)))))
        h = dt / steps
        cols = int(W // rr) + 1
        sqrt = math.sqrt
        caps = 0
        for _ in range(steps):
            for i in range(n):
                x = X[i] + VX[i] * h
                y = Y[i] + VY[i] * h
                if x < lo:
                    x = lo
                    if VX[i] < 0:
                        VX[i] = -VX[i]
                elif x > hi_x:
                    x = hi_x
                    if VX[i] > 0:
                        VX[i] = -VX[i]
                if y < lo:
                    y = lo
                    if VY[i] < 0:
                        VY[i] = -VY[i]
                elif y > hi_y:
                    y = hi_y
                    if VY[i] > 0:
                        VY[i] = -VY[i]
                X[i] = x
                Y[i] = y
            grid = {}
            for i in range(n):
                k = int(Y[i] // rr) * cols + int(X[i] // rr)
                cell = grid.get(k)
                if cell is None:
                    grid[k] = [i]
                else:
                    cell.append(i)
            for k, cell in grid.items():
                for nb in (k, k + 1, k + cols - 1, k + cols, k + cols + 1):   # (the other half
                    other = cell if nb == k else grid.get(nb)            # checks this one)
                    if other is None:
                        continue
                    for a in range(len(cell)):
                        i = cell[a]
                        for j in (other[a + 1:] if nb == k else other):
                            dx = X[j] - X[i]
                            dy = Y[j] - Y[i]
                            d2 = dx * dx + dy * dy
                            if d2 >= rr2:
                                continue
                            d = sqrt(d2) or 0.0001
                            nx, ny = dx / d, dy / d
                            corr = (rr - d) / 2
                            X[i] -= nx * corr
                            Y[i] -= ny * corr
                            X[j] += nx * corr
                            Y[j] += ny * corr
                            vn = (VX[j] - VX[i]) * nx + (VY[j] - VY[i]) * ny
                            if vn < 0:                   # coming together: they bounce
                                VX[i] += vn * nx
                                VY[i] += vn * ny
                                VX[j] -= vn * nx
                                VY[j] -= vn * ny
                                if T[i] != T[j]:
                                    if T[j] == (T[i] + 1) % 3:
                                        T[j] = T[i]
                                    else:
                                        T[i] = T[j]
                                    caps += 1
        self.captures += caps
        k = min(1.0, dt * RPS_EASE)               # back toward the speed, gently
        sp, ang, spin = self.speed, self.ang, self.spin
        for i in range(n):
            X[i] = min(max(X[i], lo), hi_x)          # (a crowd can push one into the wall: not through it)
            Y[i] = min(max(Y[i], lo), hi_y)
            ang[i] += spin[i] * dt
            s = sqrt(VX[i] * VX[i] + VY[i] * VY[i])
            if s < 1:
                a = self.rng.random() * math.pi * 2
                VX[i], VY[i] = math.cos(a) * sp, math.sin(a) * sp
                continue
            f = 1 + (sp / s - 1) * k
            VX[i] *= f
            VY[i] *= f

    def draw(self, img, x0, y0):
        """Every piece, where it is: its picture at the nearest of RPS_TURNS angles."""
        sprites = self.sprites
        if sprites.get("r") != self.r:                 # (another size: drawn again, as needed)
            sprites.clear()
            sprites["r"] = self.r
        half = rps_span(self.r) // 2
        ox, oy = x0 - half, y0 - half
        k = RPS_TURNS / (2 * math.pi)
        for x, y, t, a, look in zip(self.x, self.y, self.t, self.ang, self.look):
            turn = int(a * k + 0.5) % RPS_TURNS
            key = (t, look if t == 0 else 0, turn)
            s = sprites.get(key)
            if s is None:
                s = sprites[key] = rps_sprite(t, self.r, turn, look)
            img.paste(s, (ox + int(x + 0.5), oy + int(y + 0.5)), s)


# ---- Game of Life ----------------------------------------------------------------------------------------
LIFE_RULES = {"Life": ({3}, {2, 3}), "HighLife": ({3, 6}, {2, 3}),          # born with, lives on with
              "Day & Night": ({3, 6, 7, 8}, {3, 4, 6, 7, 8}), "Seeds": ({2}, set())}
LIFE_SOUP = {"Life": 0.3, "HighLife": 0.3, "Day & Night": 0.5, "Seeds": 0.04}   # how full it starts


def life_colours():
    """Each cell's colour by its age (1..255), then a cell just gone, fading (256..263)."""
    import numpy as np
    lut = np.zeros((264, 3), np.uint8)
    lut[0] = SIM_FLOOR
    stops = [(1, (236, 255, 226)), (3, (150, 236, 196)), (10, (70, 196, 186)), (30, (64, 132, 214)),
             (80, (88, 90, 196)), (255, (110, 72, 170))]
    for (a0, c0), (a1, c1) in zip(stops, stops[1:]):
        for a in range(a0, a1 + 1):
            lut[a] = co_mix(c0, c1, (a - a0) / (a1 - a0))
    for k in range(8):
        lut[256 + k] = co_mix(SIM_FLOOR, (46, 84, 96), (k + 1) / 9)
    return lut


class Life(Sim):
    """Conway's Game of Life (and three other rules), on a board whose edges meet. Cells are coloured by
    age; when the board settles (or dies out) it starts again by itself."""
    key = "life"
    blurb = "A cell lives on, dies or is born by how many of its eight neighbours are alive."
    poke_label = "Add life"
    options = (("rules", "Rules", tuple(LIFE_RULES), "Life"),
               ("cells", "Cells", ("Small", "Large"), "Small"),
               ("speed", "Speed", ("Slow", "Normal", "Fast"), "Normal"))
    restart_for = ("rules", "cells")
    CELL = {"Small": 4, "Large": 7}                 # px
    GENS = {"Slow": 5, "Normal": 12, "Fast": 25}    # generations a second
    WAIT = 4.0                                      # seconds a settled board shows, then a new one

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.lut = life_colours()
        self.restart()

    def restart(self):
        import numpy as np
        super().restart()
        c = self.CELL[self.values["cells"]]
        self.cols, self.rows = max(8, self.w // c), max(8, self.h // c)
        alive = self.np_rng().random((self.rows, self.cols)) < LIFE_SOUP[self.values["rules"]]
        self.age = alive.astype(np.uint16)
        self.gone = np.zeros((self.rows, self.cols), np.uint8)
        self.gen, self.carry = 0, 0.0
        self.seen = deque(maxlen=60)                # recent boards, to see it repeat
        self.steady, self.last_pop = 0, -1
        self.ended, self.wait = None, 0.0
        self.sample((self.alive(),))

    def refit(self, w, h):
        """Full screen, and back: the board grows or shrinks round its middle (new edges: new soup)."""
        import numpy as np
        c = self.CELL[self.values["cells"]]
        rows, cols = max(8, h // c), max(8, w // c)
        rnd, soup = self.np_rng(), LIFE_SOUP[self.values["rules"]]
        self.age = self.regrid(self.age, rows, cols, lambda sh: rnd.random(sh) < soup)
        self.gone = self.regrid(self.gone, rows, cols, lambda sh: np.zeros(sh, np.uint8))
        self.w, self.h, self.rows, self.cols = w, h, rows, cols
        self.seen.clear()
        self.steady = 0

    def alive(self):
        return int((self.age > 0).sum())

    def update(self, dt):
        if self.paused or dt <= 0:
            return None
        if self.ended:
            self.wait -= dt
            if self.wait <= 0:
                self.restart()
                return "next"
            return None
        self.clock += dt
        self.carry = min(self.carry + dt * self.GENS[self.values["speed"]], 4)
        while self.carry >= 1 and not self.ended:
            self.carry -= 1
            self.step()
        self.sampled += dt
        if self.sampled >= SIM_SAMPLE:
            self.sampled = 0.0
            self.sample((self.alive(),))
        return "ended" if self.ended else None

    def step(self):
        import numpy as np
        born, stay = LIFE_RULES[self.values["rules"]]
        a = self.age > 0
        n = np.zeros(a.shape, np.uint8)
        for dy in (-1, 0, 1):
            row = np.roll(a, dy, 0)
            for dx in (-1, 0, 1):
                if dy or dx:
                    n += np.roll(row, dx, 1)
        b, s = np.zeros(9, bool), np.zeros(9, bool)
        b[list(born)] = True
        s[list(stay)] = True
        new = (~a & b[n]) | (a & s[n])
        self.gone = np.where(a & ~new, 8, np.where(self.gone > 0, self.gone - 1, 0)).astype(np.uint8)
        self.age = np.where(new, np.minimum(self.age + 1, 255), 0).astype(np.uint16)
        self.gen += 1
        pop = int(new.sum())
        h = hash(new.tobytes())
        if pop == 0:
            self.end("Everything died")
        elif h in self.seen:
            self.end("Settled")
        self.seen.append(h)
        self.steady = self.steady + 1 if abs(pop - self.last_pop) <= max(2, pop // 200) else 0
        self.last_pop = pop
        if self.steady >= 400 and not self.ended:      # (a few gliders going round for ever)
            self.end("Settled")

    def end(self, why):
        self.ended, self.wait = (why, self.gen), self.WAIT

    def poke(self):
        """X: a patch of new life somewhere."""
        ph, pw = min(16, self.rows), min(16, self.cols)
        y, x = self.rng.randrange(self.rows - ph + 1), self.rng.randrange(self.cols - pw + 1)
        patch = self.np_rng().random((ph, pw)) < 0.4
        view = self.age[y:y + ph, x:x + pw]
        view[patch & (view == 0)] = 1
        if self.ended:
            self.ended, self.seen, self.steady = None, deque(maxlen=60), 0

    def draw(self, img, x0, y0):
        import numpy as np
        from PIL import Image
        idx = np.where(self.age > 0, self.age,
                       np.where(self.gone > 0, 255 + (9 - self.gone.astype(np.uint16)), 0))
        c = self.CELL[self.values["cells"]]
        pic = Image.fromarray(self.lut[np.minimum(idx, 263)], "RGB").resize((self.cols * c, self.rows * c),
                                                                             Image.NEAREST)
        img.paste(pic, (x0 + (self.w - self.cols * c) // 2, y0 + (self.h - self.rows * c) // 2))

    def stats(self):
        return [("Generation", str(self.gen)), ("Alive", str(self.alive())), ("Rules", self.values["rules"])]

    def chart(self):
        return self.history, [(150, 236, 196)], max(1, self.rows * self.cols // 3)

    def note(self):
        if not self.ended:
            return None
        why, gen = self.ended
        return why, f"After {gen} generations. A new one in {max(1, math.ceil(self.wait))} s"


# ---- Orbits ----------------------------------------------------------------------------------------------
ORBIT_SPEEDS = {"Slow": 0.6, "Normal": 1.0, "Fast": 1.7}      # how fast time goes
ORBIT_TRAILS = {"Off": 0, "Short": 30, "Long": 110}            # points behind each planet
ORBIT_SUN = 12                                                 # px


def orbit_sun(r=ORBIT_SUN):
    """The sun, glowing."""
    from PIL import Image, ImageDraw
    K, R = 4, r * 3
    big = Image.new("RGBA", (2 * R * K, 2 * R * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    for k in range(18, 0, -1):
        rad = r + (R - r) * k / 18
        d.ellipse((R * K - rad * K, R * K - rad * K, R * K + rad * K, R * K + rad * K),
                  fill=(255, 196, 90, int(70 * (1 - k / 18) ** 2)))
    d.ellipse((R * K - r * K, R * K - r * K, R * K + r * K, R * K + r * K), fill=(255, 214, 120, 255))
    d.ellipse((R * K - r * 0.6 * K, R * K - r * 0.7 * K, R * K + r * 0.3 * K, R * K + r * 0.2 * K),
              fill=(255, 240, 190, 255))
    return big.reduce(K)


class Orbits(Sim):
    """A sun and planets: each pulls on the sun and on every other planet (leapfrog steps). Planets that
    touch become one; one that falls into the sun or flies far away is gone. New planets come in when
    there are few left."""
    key = "orbit"
    blurb = "Every planet pulls on the sun and on every other planet. Planets that meet become one."
    poke_label = "Add planet"
    options = (("planets", "Planets", (6, 12, 20, 30), 12),
               ("trails", "Trails", tuple(ORBIT_TRAILS), "Short"),
               ("speed", "Speed", tuple(ORBIT_SPEEDS), "Normal"))
    restart_for = ("planets",)
    GM = 560000.0           # the sun's pull, px³/s²
    SOFT = 3.0              # px: so a close pass doesn't fling one off for ever

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.sun = None
        self.restart()

    def restart(self):
        import numpy as np
        super().restart()
        self.cx, self.cy = self.w / 2, self.h / 2
        self.p, self.v, self.m = np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
        self.colour, self.trails = [], []
        self.merged = self.lost = 0
        self.trail_t = self.refill = 0.0
        for _ in range(self.values["planets"]):
            self.add()

    def add(self):
        """A planet on a roughly round orbit somewhere it fits."""
        import numpy as np
        rnd = self.rng
        lim = max(46.0, min(self.w, self.h) / 2 - 10)
        for _ in range(20):
            r = rnd.uniform(36, lim)
            a = rnd.uniform(0, 2 * math.pi)
            pos = np.array((self.cx + math.cos(a) * r, self.cy + math.sin(a) * r))
            if not len(self.p) or ((self.p - pos) ** 2).sum(1).min() > 24 ** 2:
                break
        speed = math.sqrt(self.GM / r) * rnd.uniform(0.86, 1.06)
        self.p = np.vstack([self.p, pos])
        self.v = np.vstack([self.v, (-math.sin(a) * speed, math.cos(a) * speed)])
        self.m = np.append(self.m, self.GM * rnd.uniform(0.0006, 0.004))
        self.colour.append(sim_hue(rnd.random(), 0.42))
        self.trails.append(deque(maxlen=ORBIT_TRAILS["Long"]))

    def radius(self, m):
        return 2.4 + 2.2 * (m / (self.GM * 0.002)) ** (1 / 3)

    def refit(self, w, h):
        dx, dy = w / 2 - self.cx, h / 2 - self.cy
        self.w, self.h, self.cx, self.cy = w, h, w / 2, h / 2
        if len(self.p):
            self.p += (dx, dy)
        for tr in self.trails:
            pts = [(x + dx, y + dy) for x, y in tr]
            tr.clear()
            tr.extend(pts)

    def accel(self, p):
        import numpy as np
        d = (self.cx, self.cy) - p
        r2 = (d * d).sum(1) + self.SOFT ** 2
        a = d * (self.GM / (r2 * np.sqrt(r2)))[:, None]
        if len(p) > 1:
            dd = p[None, :, :] - p[:, None, :]
            rr = (dd * dd).sum(-1) + self.SOFT ** 2
            np.fill_diagonal(rr, np.inf)
            a += (dd * (self.m[None, :] / (rr * np.sqrt(rr)))[:, :, None]).sum(1)
        return a

    def update(self, dt):
        if self.paused or dt <= 0:
            return None
        dt *= ORBIT_SPEEDS[self.values["speed"]]
        self.clock += dt
        h = dt / 4
        for _ in range(4):
            if not len(self.p):
                break
            self.v += self.accel(self.p) * (h / 2)
            self.p += self.v * h
            self.v += self.accel(self.p) * (h / 2)
            self.collide()
        self.trail_t += dt
        if self.trail_t >= 0.05:
            self.trail_t = 0.0
            for tr, (x, y) in zip(self.trails, self.p.tolist()):
                tr.append((x, y))
        self.refill = self.refill + dt if len(self.p) < max(2, self.values["planets"] // 2) else 0.0
        if self.refill > 4:                              # few left: a new one comes in
            self.refill = 0.0
            self.add()
        return None

    def collide(self):
        import numpy as np
        if not len(self.p):
            return
        d = self.p - (self.cx, self.cy)
        r = np.sqrt((d * d).sum(1))
        rad = self.radius(self.m)
        gone = (r <= ORBIT_SUN + rad * 0.5) | (r > 2.5 * max(self.w, self.h))   # into the sun, or far off
        self.lost += int(gone.sum())
        keep = ~gone
        if len(self.p) > 1:
            dd = self.p[None, :, :] - self.p[:, None, :]
            dist = np.sqrt((dd * dd).sum(-1))
            touch = dist < (rad[:, None] + rad[None, :]) * 0.8
            np.fill_diagonal(touch, False)
            for i, j in zip(*np.nonzero(np.triu(touch))):
                if keep[i] and keep[j]:
                    mi, mj = self.m[i], self.m[j]
                    self.v[i] = (self.v[i] * mi + self.v[j] * mj) / (mi + mj)
                    self.p[i] = (self.p[i] * mi + self.p[j] * mj) / (mi + mj)
                    self.m[i] = mi + mj
                    keep[j] = False
                    self.merged += 1
        if not keep.all():
            idx = np.nonzero(keep)[0].tolist()
            self.p, self.v, self.m = self.p[keep], self.v[keep], self.m[keep]
            self.colour = [self.colour[i] for i in idx]
            self.trails = [self.trails[i] for i in idx]

    def poke(self):
        self.add()

    def draw(self, img, x0, y0):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        if self.sun is None:
            self.sun = orbit_sun()
        n = ORBIT_TRAILS[self.values["trails"]]
        for tr, c, (x, y) in zip(self.trails, self.colour, self.p.tolist()):
            pts = list(tr)[-n:] if n else []
            if len(pts) > 1:                             # a tail: dimmer the older it is
                pts = [(x0 + px, y0 + py) for px, py in pts] + [(x0 + x, y0 + y)]
                k = len(pts)
                for part, f in ((pts[:k // 3 + 1], 0.25), (pts[k // 3:2 * k // 3 + 1], 0.45),
                                (pts[2 * k // 3:], 0.75)):
                    if len(part) > 1:
                        d.line(part, fill=co_mix(SIM_FLOOR, c, f), width=1)
        s = self.sun
        img.paste(s, (x0 + int(self.cx) - s.width // 2, y0 + int(self.cy) - s.height // 2), s)
        for c, (x, y), m in zip(self.colour, self.p.tolist(), self.m.tolist()):
            r = self.radius(m)
            d.ellipse((x0 + x - r, y0 + y - r, x0 + x + r, y0 + y + r), fill=c)

    def stats(self):
        return [("Planets", str(len(self.p))), ("Merged", str(self.merged)), ("Lost", str(self.lost))]


# ---- Forest Fire -----------------------------------------------------------------------------------------
FIRE_GROW = {"Slow": 0.004, "Normal": 0.01, "Fast": 0.025}            # a tree in empty ground, a generation
FIRE_STRIKE = {"Rare": 0.000001, "Normal": 0.000004, "Often": 0.00002}   # lightning, a tree, a generation


class ForestFire(Sim):
    """Trees grow in empty ground; lightning sets one alight now and then; fire spreads to the trees
    next to it, burns out, and the forest grows back."""
    key = "fire"
    blurb = "Trees grow in empty ground. Lightning starts fires that spread from tree to tree, and the forest grows back."
    poke_label = "Lightning"
    options = (("growth", "Growth", tuple(FIRE_GROW), "Normal"),
               ("lightning", "Lightning", tuple(FIRE_STRIKE), "Normal"),
               ("cells", "Cells", ("Small", "Large"), "Small"),
               ("speed", "Speed", ("Slow", "Normal", "Fast"), "Normal"))
    restart_for = ("cells",)
    CELL = {"Small": 4, "Large": 7}
    GENS = {"Slow": 6, "Normal": 14, "Fast": 28}
    GROUND, TREE, FIRE, EMBER = 0, 1, 2, 3

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.lut = self.colours()
        self.restart()

    @staticmethod
    def colours():
        """0..63 ground and ash, 64..127 trees by age, 128..131 fire, 132 embers."""
        import numpy as np
        lut = np.zeros((136, 3), np.uint8)
        for k in range(64):
            lut[k] = co_mix((30, 26, 22), (70, 66, 62), min(1.0, k / 12))   # ash, fading to ground
        for k in range(64):
            lut[64 + k] = co_mix((120, 196, 96), (34, 104, 62), min(1.0, k / 40))
        for k, c in enumerate(((255, 232, 140), (255, 190, 80), (250, 140, 50), (236, 96, 40))):
            lut[128 + k] = c
        lut[132] = (140, 46, 30)
        return lut

    def restart(self):
        import numpy as np
        super().restart()
        c = self.CELL[self.values["cells"]]
        self.cols, self.rows = max(8, self.w // c), max(8, self.h // c)
        self.rnd = self.np_rng()
        self.state = np.where(self.rnd.random((self.rows, self.cols)) < 0.45, self.TREE,
                              self.GROUND).astype(np.uint8)
        self.age = self.rnd.integers(0, 40, (self.rows, self.cols)).astype(np.uint8)
        self.ash = np.zeros((self.rows, self.cols), np.uint8)
        self.fires, self.carry, self.gen = 0, 0.0, 0
        self.sample(self.counts())

    def refit(self, w, h):
        """Full screen, and back: the forest grows or shrinks round its middle (new edges: new trees)."""
        import numpy as np
        c = self.CELL[self.values["cells"]]
        rows, cols = max(8, h // c), max(8, w // c)
        self.state = self.regrid(self.state, rows, cols,
                                 lambda sh: np.where(self.rnd.random(sh) < 0.45, self.TREE, self.GROUND))
        self.age = self.regrid(self.age, rows, cols, lambda sh: self.rnd.integers(0, 40, sh))
        self.ash = self.regrid(self.ash, rows, cols, lambda sh: np.zeros(sh, np.uint8))
        self.w, self.h, self.rows, self.cols = w, h, rows, cols

    def counts(self):
        st = self.state
        return int((st == self.TREE).sum()), int(((st == self.FIRE) | (st == self.EMBER)).sum())

    def update(self, dt):
        if self.paused or dt <= 0:
            return None
        self.clock += dt
        self.carry = min(self.carry + dt * self.GENS[self.values["speed"]], 4)
        while self.carry >= 1:
            self.carry -= 1
            self.step()
        self.sampled += dt
        if self.sampled >= SIM_SAMPLE:
            self.sampled = 0.0
            self.sample(self.counts())
        return None

    def step(self):
        import numpy as np
        st = self.state
        fire = st == self.FIRE
        near = np.zeros_like(fire)                       # next to a fire (the edges don't meet)
        near[1:, :] |= fire[:-1, :]
        near[:-1, :] |= fire[1:, :]
        near[:, 1:] |= fire[:, :-1]
        near[:, :-1] |= fire[:, 1:]
        near[1:, 1:] |= fire[:-1, :-1]
        near[:-1, :-1] |= fire[1:, 1:]
        near[1:, :-1] |= fire[:-1, 1:]
        near[:-1, 1:] |= fire[1:, :-1]
        tree = st == self.TREE
        strike = tree & (self.rnd.random(st.shape) < FIRE_STRIKE[self.values["lightning"]])
        self.fires += int((strike & ~near).sum())
        catch = tree & (near | strike)
        grow = (st == self.GROUND) & (self.rnd.random(st.shape) < FIRE_GROW[self.values["growth"]])
        new = st.copy()
        out = st == self.EMBER
        new[out] = self.GROUND
        self.ash = np.where(out, 12, np.where(self.ash > 0, self.ash - 1, 0)).astype(np.uint8)
        new[fire] = self.EMBER
        new[catch] = self.FIRE
        new[grow] = self.TREE
        self.age = np.where(grow, 0, np.minimum(self.age.astype(np.uint16) + 1, 63)).astype(np.uint8)
        self.state = new
        self.gen += 1

    def poke(self):
        """X: lightning hits a tree."""
        import numpy as np
        trees = np.flatnonzero(self.state == self.TREE)
        if len(trees):
            self.state.flat[int(trees[self.rng.randrange(len(trees))])] = self.FIRE
            self.fires += 1

    def draw(self, img, x0, y0):
        import numpy as np
        from PIL import Image
        st = self.state
        idx = np.where(st == self.TREE, 64 + self.age,
                       np.where(st == self.FIRE, 128 + self.rnd.integers(0, 4, st.shape),    # (it flickers)
                                np.where(st == self.EMBER, 132, self.ash))).astype(np.uint8)
        c = self.CELL[self.values["cells"]]
        pic = Image.fromarray(self.lut[idx], "RGB").resize((self.cols * c, self.rows * c), Image.NEAREST)
        img.paste(pic, (x0 + (self.w - self.cols * c) // 2, y0 + (self.h - self.rows * c) // 2))

    def stats(self):
        trees, burning = self.counts()
        return [("Trees", f"{100 * trees // max(1, self.rows * self.cols)}%"), ("Burning", str(burning)),
                ("Fires", str(self.fires))]

    def chart(self):
        return self.history, [(120, 196, 96), (255, 170, 70)], max(1, self.rows * self.cols)
