"""The Mandelbrot set: dives to one well-known place after another, or the d-pad to explore it."""
import math
import threading
import time

from .theme import co_ease
from .sims import Sim


# ---- Mandelbrot Set --------------------------------------------------------------------------------------
# For each point c on the screen, z is squared and c added, again and again: where z never runs off, the
# point is in the set (dark); the others are coloured by how soon theirs did. A dive goes a level at a time,
# each twice as close as the last, to one of the set's well-known places. Each level's picture is worked out
# on a thread of its own, a slice of points at a time (a Pi Zero takes a few seconds for one); meanwhile the
# level before grows on the screen, with the next drawn into its middle as it comes, so the middle stays
# sharp. The zoom waits for the pictures, so a slower Pi just dives more slowly.
MANDEL_START = (-0.65, 0.0, 3.6)        # the whole set: the view's middle (re, im) and its width
MANDEL_DRIFT = 4.0                      # levels it takes the place it dives to to come to the middle
MANDEL_DIVES = (    # (the place, re, im, the level it goes to, the period of the tiny copy of the set it ends at)
    ("Seahorse Valley", -0.77568377, 0.13646737, 41.0, 0),
    ("Elephant Valley", 0.2964859389371122, 0.01617421642689549, 41.0, 0),
    ("Elephant Valley", 0.31444217671524638, 0.03029686155752508, 28.4, 65),
    ("Triple Spiral Valley", -0.0746892945923173, 0.6600388096734732, 41.0, 0),
    ("Quad-Spiral Valley", 0.2884594492858742, 0.47044988315285424, 41.0, 0),
    ("The Antenna", -0.1058191436831112, 0.92167750935953, 41.0, 0),
    ("West Valley", -1.2560158121687501, 0.030788241491828364, 38.8, 177),
    ("Southern Snowflakes", -0.57773001526196366, -0.65074018725816474, 38.0, 53),
)
MANDEL_SPEEDS = {"Slow": 1 / 7, "Normal": 1 / 4.5, "Fast": 1 / 2.5}     # levels a second, at most
MANDEL_COLOURS = {     # the colours a point gets by how soon it ran off, round and round
    "Classic": ((0.0, (0, 7, 100)), (0.16, (32, 107, 203)), (0.42, (237, 255, 255)), (0.6425, (255, 170, 0)),
                (0.8575, (0, 2, 0)), (1.0, (0, 7, 100))),
    "Ember": ((0.0, (14, 6, 22)), (0.3, (120, 24, 52)), (0.55, (228, 92, 36)), (0.75, (255, 212, 120)),
              (0.88, (255, 246, 222)), (1.0, (14, 6, 22))),
    "Ice": ((0.0, (6, 14, 34)), (0.3, (24, 76, 130)), (0.55, (98, 182, 216)), (0.75, (234, 248, 255)),
            (0.88, (120, 168, 208)), (1.0, (6, 14, 34))),
    "Ink": ((0.0, (12, 12, 14)), (0.35, (92, 96, 106)), (0.6, (238, 240, 244)), (0.8, (150, 154, 162)),
            (1.0, (12, 12, 14))),
}
MANDEL_INSIDE = (8, 9, 12)              # the set itself
MANDEL_BANDS = 64                       # steps (z squared) to go once round the colours
MANDEL_HOLD = 6.0                       # seconds at the end of a dive, then the next
MANDEL_FADE = 1.2                       # seconds one dive takes to fade into the next
MANDEL_LUTS = {}


def mandel_lut(name):
    """1024 colours, round the palette."""
    if name not in MANDEL_LUTS:
        import numpy as np
        stops = MANDEL_COLOURS[name]
        xs = np.linspace(0, 1, 1024, endpoint=False)
        MANDEL_LUTS[name] = np.stack([np.interp(xs, [p for p, _ in stops], [c[k] for _, c in stops])
                                      for k in range(3)], 1).astype(np.uint8)
    return MANDEL_LUTS[name]


def mandel_zoom(m):
    """×2,048, ×340 thousand, ×1.2 million, ×2.2 trillion."""
    if m < 1e4:
        return f"×{m:,.0f}"
    for div, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million"), (1e3, "thousand")):
        if m >= div:
            v = m / div
            return f"×{v:.1f} {word}" if v < 10 else f"×{v:.0f} {word}"
    return f"×{m:,.0f}"


class MandelLevel:
    """One level of a dive, worked out a slice of points at a time (step): for each point, how soon z ran
    off (smoothed: nu), or -1 for one in the set (or still going after maxit steps)."""
    SLICE = 16384                       # points a step
    K = 8                               # times z is squared between looks at it

    def __init__(self, level, middle, width, w, h, maxit):
        import numpy as np
        self.level, self.w, self.h, self.maxit = level, w, h, maxit
        px = width / w
        xs = middle[0] + (np.arange(w) - (w - 1) / 2) * px
        ys = middle[1] + ((h - 1) / 2 - np.arange(h)) * px
        c = (xs[None, :] + 1j * ys[:, None]).ravel()
        self.nu = np.full(w * h, -1.0, np.float32)
        q = (c.real - 0.25) ** 2 + c.imag ** 2       # (in the big heart, or the bulb on its left: in the set)
        out = (q * (q + c.real - 0.25) > 0.25 * c.imag ** 2) & ((c.real + 1) ** 2 + c.imag ** 2 > 0.0625)
        self.idx = np.flatnonzero(out)
        self.c = c[self.idx]
        self.z = self.c.copy()
        self.alive = np.ones(self.idx.size, bool)
        self.it, self.pos = 1, 0
        self.done = self.idx.size == 0

    def step(self):
        import numpy as np
        if self.done:
            return
        a, b = self.pos, min(self.pos + self.SLICE, self.idx.size)
        z, c = self.z[a:b], self.c[a:b]
        with np.errstate(over="ignore", invalid="ignore"):
            for _ in range(self.K):
                np.multiply(z, z, out=z)
                z += c
            a2 = z.real * z.real + z.imag * z.imag           # (one that ran off early can be too big: inf)
        gone = a2 > 64.0
        if gone.any():
            e = np.flatnonzero(gone)
            nu = (self.it + self.K) - np.log2(np.log2(np.abs(z[e])))
            self.nu[self.idx[a + e]] = np.maximum(nu, 0.0)
            self.alive[a + e] = False
        self.pos = b
        if b < self.idx.size:
            return
        self.it += self.K                                # the end of a pass: those that ran off are let go
        self.pos = 0
        if not self.alive.all():
            keep = self.alive
            self.idx, self.z, self.c = self.idx[keep], self.z[keep], self.c[keep]
            self.alive = np.ones(self.idx.size, bool)
        if self.it >= self.maxit or not self.idx.size:
            self.done = True
            self.idx = self.z = self.c = self.alive = None


class Mandelbrot(Sim):
    """Tour: dives into the Mandelbrot set, one well-known place after another (MANDEL_DIVES), from the
    whole set down as far as a computer's numbers go, or to a tiny copy of the set; then the next.
    Explore: the d-pad moves round the set and A zooms in, Y out (held, on and on): a quick rough
    picture of each new view comes first, then a sharp one once it stays put."""
    key = "mandel"
    blurb = "For each point c, z becomes z² + c, again and again. Where z never runs off, c is in the set."
    poke_label = "Colours"
    options = (("mode", "Mode", ("Tour", "Explore"), "Tour"),
               ("colours", "Colours", tuple(MANDEL_COLOURS), "Classic"),
               ("speed", "Zoom", tuple(MANDEL_SPEEDS), "Normal"))
    THREADED = True                     # pictures worked out on a thread of their own (or as it goes)
    AHEAD = 2                           # levels worked out ahead of the one on screen
    PAN, ZOOM = 0.6, 1.0                # exploring, held: the view's width a second; levels a second
    NUDGE = (0.08, 0.15)                # ...pressed once: the view's width; levels
    DEEPEST = 41.0                      # as deep as exploring goes (as far as the numbers hold out)
    REACH = (-2.6, 1.4, -1.6, 1.6)      # where the view's middle can go: re from, to; im from, to
    MOVES = {"up": (0, 1, 0), "down": (0, -1, 0), "left": (-1, 0, 0), "right": (1, 0, 0),
             "a": (0, 0, 1), "y": (0, 0, -1)}

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.lock = threading.Condition()
        self.gen = 0                    # up by one whenever the pictures in hand are no use any more
        self.levels = {}                # touring: level -> {"nu", "maxit", "w", "h", "pic", "colours"}
        self.job = None                 # the picture being worked out
        self.starts = {}                # (w, h) -> the whole set's nu and maxit: every dive starts there
        self.order, self.dive = [], None
        self.shift = 0.0                # where in the colours the counts start (X moves it on)
        self.pic, self.pic_key = None, None    # the picture last drawn
        self.fade = None                # (the last dive's picture, how far it has faded)
        self.stand_in = None            # a picture to show until the first level comes (after refit)
        self.wanted = 0.0               # the thread works until then (time.perf_counter())
        self.map = (None, None)
        self.ex = None                  # exploring: {"cx", "cy", "L"}: the view's middle (re, im) and level
        self.ex_quick = self.ex_full = None    # ...its latest rough picture and sharp one (each: where it is)
        self.held, self.held_at = set(), 0.0   # ...the buttons held down
        self.mode_now = "Tour"
        self.restart()
        if self.THREADED:
            threading.Thread(target=self.run, daemon=True, name="mandelbrot").start()

    def restart(self):
        """A new dive: the next place (in a shuffled order), new colours; the last fades away. (Exploring:
        from the whole set.)"""
        super().restart()
        with self.lock:
            old = self.pic if self.pic is not None else self.stand_in
            if old is not None:
                self.fade, self.stand_in = (old, 0.0), None
            if not self.order:
                order = list(range(len(MANDEL_DIVES)))
                self.rng.shuffle(order)
                if self.dive is not None and len(order) > 1 and MANDEL_DIVES[order[-1]] == self.dive:
                    order.insert(0, order.pop())               # (not the same place twice in a row)
                self.order = order
            self.dive = MANDEL_DIVES[self.order.pop()]
            self.shift = self.rng.uniform(-0.08, 0.04) % 1.0   # (dark round the whole set, to start with)
            self.L, self.phase, self.wait = 0.0, "dive", 0.0
            self.gen += 1
            self.job = None
            self.levels = {}
            self.ex = self.ex_quick = self.ex_full = None
            self.held = set()
            start = self.starts.get((self.w, self.h))
            if start is not None:
                self.levels[0] = {"nu": start[0], "maxit": start[1], "w": self.w, "h": self.h, "pic": None,
                                  "colours": None}
            self.lock.notify_all()
        self.mode_now = "Tour"
        if self.values.get("mode") == "Explore":
            self.mode_now = "Explore"
            self.explore_from_here(keep_pic=False)

    def apply(self):
        """Tour or Explore, as chosen."""
        mode = self.values.get("mode", "Tour")
        if mode == self.mode_now:
            return
        if mode == "Explore":
            self.mode_now = mode
            self.explore_from_here()
        else:
            self.restart()

    def explore_from_here(self, keep_pic=True):
        """Exploring, from the view the tour is at (its picture stands in until the first of its own)."""
        with self.lock:
            if self.phase == "explore":
                return
            dx, dy, W = self.view(self.L)
            cx, cy = self.dive[1] + dx, self.dive[2] + dy
            self.ex = {"cx": cx, "cy": cy, "L": self.L}
            pic = (self.pic if self.pic is not None else self.stand_in) if keep_pic else None
            self.ex_quick = None
            self.ex_full = None if pic is None else {"cx": cx, "cy": cy, "width": W, "w": pic.width, "h": pic.height,
                                                     "pic": pic, "nu": None, "colours": None, "maxit": None}
            if keep_pic:
                self.fade = None
            self.phase, self.paused = "explore", False
            self.gen += 1
            self.job = None
            self.levels = {}
            self.held = set()
            self.pic_key = None
            self.lock.notify_all()

    def refit(self, w, h):
        """Full screen, and back: the same place and depth, its pictures worked out again at the new size
        (the last one, stretched, stands in meanwhile; exploring, the pictures in hand still fit where
        they are)."""
        from PIL import Image
        with self.lock:
            self.w, self.h = w, h
            self.gen += 1
            self.job = None
            self.levels = {}
            self.pic_key = None
            if self.phase == "explore":
                self.lock.notify_all()
                return
            if self.L == 0 and (w, h) in self.starts:
                start = self.starts[(w, h)]
                self.levels[0] = {"nu": start[0], "maxit": start[1], "w": w, "h": h, "pic": None, "colours": None}
            old = self.pic if self.pic is not None else self.stand_in
            self.stand_in = old.resize((w, h), Image.BILINEAR) if old is not None else None
            self.pic, self.fade = None, None
            self.lock.notify_all()

    def view(self, L):
        """L levels into the dive: the view's middle, from the place it's diving to, and its width."""
        _, tx, ty, _, _ = self.dive
        cx0, cy0, w0 = MANDEL_START
        f = 2.0 ** -L * math.exp(-L / MANDEL_DRIFT)
        return (cx0 - tx) * f, (cy0 - ty) * f, w0 * 2.0 ** -L

    def here(self):
        """The view now: its middle (re, im) and width."""
        if self.phase == "explore" and self.ex:
            return self.ex["cx"], self.ex["cy"], MANDEL_START[2] * 2.0 ** -self.ex["L"]
        dx, dy, W = self.view(self.L)
        return self.dive[1] + dx, self.dive[2] + dy, W

    def colours(self):
        return self.values["colours"], round(self.shift, 6)

    @staticmethod
    def paint(lv, colours):
        """A picture (lv: its nu, h x w), in these colours."""
        import numpy as np
        from PIL import Image
        nu = lv["nu"]
        idx = (nu * (1024.0 / MANDEL_BANDS) + colours[1] * 1024).astype(np.int64) & 1023
        rgb = mandel_lut(colours[0])[idx]
        rgb[nu < 0] = MANDEL_INSIDE
        lv["pic"] = Image.fromarray(rgb.reshape(lv["h"], lv["w"], 3), "RGB")
        lv["colours"] = colours

    # the thread: each picture
    def next_spec(self):
        """What to work out next (the lock is held), or None: touring, the level on screen, then up to
        AHEAD more; exploring, a rough picture of the view, then a sharp one."""
        if self.job is not None or self.dive is None:
            return None
        if self.phase == "explore":
            return self.ex_next()
        if self.phase != "dive":
            return None
        n = int(self.L)
        for lv in range(n, min(n + self.AHEAD, math.ceil(self.dive[3])) + 1):
            if lv not in self.levels:
                dx, dy, width = self.view(lv)
                return {"kind": "level", "level": lv, "middle": (self.dive[1] + dx, self.dive[2] + dy),
                        "width": width, "size": (self.w, self.h), "L": lv, "prev": self.levels.get(lv - 1)}
        return None

    def ex_next(self):
        v = self.ex
        if v is None:
            return None
        W = MANDEL_START[2] * 2.0 ** -v["L"]
        qw, qh = max(8, -(-self.w // 4)), max(8, -(-self.h // 4))    # (a pixel of it: 4 x 4 of the view's,
        jobs = {"full": ((self.w, self.h), W), "quick": ((qw, qh), W * 4 * qw / self.w)}   # all of it covered)

        def same(p, kind):
            size, width = jobs[kind]
            return (p is not None and p.get("nu") is not None and (p["w"], p["h"]) == size
                    and (p["cx"], p["cy"], p["width"]) == (v["cx"], v["cy"], width))
        if same(self.ex_full, "full"):
            return None
        prev = self.ex_full if self.ex_full is not None and self.ex_full.get("nu") is not None \
            and abs(math.log2(self.ex_full["width"] / W)) < 2 else None
        kind = "full" if same(self.ex_quick, "quick") else "quick"
        return {"kind": kind, "middle": (v["cx"], v["cy"]), "width": jobs[kind][1], "size": jobs[kind][0],
                "L": v["L"], "prev": prev, "level": int(v["L"])}

    def maxit_for(self, lv, prev):
        """How many times to square z at most: enough for the slowest points of the picture before it,
        with room to spare (the deeper, the more it may take)."""
        import numpy as np
        cap = int(min(3200, 250 + 64 * lv))
        if prev is None:
            return cap
        nu = prev["nu"]
        out = nu[nu >= 0]
        if not out.size:
            return cap
        return int(max(300, min(cap, 1.4 * float(np.quantile(out, 0.999)) + 150)))

    def work(self, budget):
        """Pictures worked out for up to budget seconds. False when there's nothing left to do."""
        end = time.perf_counter() + budget
        while time.perf_counter() < end:
            with self.lock:
                job, gen = self.job, self.gen
                spec = None if job else self.next_spec()
                if job is None and spec is None:
                    return False
            if job is None:
                size = spec["size"]
                job = MandelLevel(spec["level"], spec["middle"], spec["width"], size[0], size[1],
                                  self.maxit_for(spec["L"], spec["prev"]))
                job.spec = spec
                with self.lock:
                    if self.gen != gen or self.job is not None:
                        continue
                    self.job = job
            job.step()
            if job.done:
                got = {"nu": job.nu, "maxit": job.maxit, "w": job.w, "h": job.h, "pic": None, "colours": None}
                self.paint(got, self.colours())
                with self.lock:
                    if self.gen == gen and self.job is job:
                        self.publish(job.spec, got)
                        self.job = None
        return True

    def publish(self, spec, got):
        """A picture done (the lock is held)."""
        if spec["kind"] == "level":
            self.levels[spec["level"]] = got
            if spec["level"] == 0:
                self.starts[spec["size"]] = (got["nu"], got["maxit"])
            return
        got.update(cx=spec["middle"][0], cy=spec["middle"][1], width=spec["width"])
        if spec["kind"] == "quick":
            self.ex_quick = got
        else:
            self.ex_full = got

    def run(self):
        while True:
            with self.lock:
                while time.perf_counter() > self.wanted or (self.job is None and self.next_spec() is None):
                    self.lock.wait(0.5)
            try:
                self.work(0.04)
            except Exception as ex:                     # (the sim carries on, whatever happens)
                print(f"mandelbrot: {ex!r}", flush=True)
                with self.lock:
                    self.job = None
                time.sleep(1)
            time.sleep(0.001)

    def finish(self):
        """Everything due worked out now (tests)."""
        while self.work(5.0):
            pass

    # moving on
    def update(self, dt):
        self.wanted = time.perf_counter() + 1.0          # (the thread works while it's on screen)
        if self.THREADED:
            with self.lock:
                self.lock.notify_all()
        else:
            self.work(0.02)
        if self.phase == "explore":
            now = time.perf_counter()
            if now - self.held_at > 1.0:
                self.held.clear()                      # (let go while it was off the screen)
            self.held_at = now
            if dt > 0:
                self.clock += dt
                if self.fade and (self.ex_quick or self.ex_full):
                    f = self.fade[1] + dt / MANDEL_FADE
                    self.fade = (self.fade[0], f) if f < 1 else None
                self.ex_step(dt)
            return None
        if self.paused or dt <= 0:
            return None
        self.clock += dt
        with self.lock:
            n = int(self.L)
            ready = n - 1
            while ready + 1 in self.levels:
                ready += 1
            for k in [k for k in self.levels if k < n]:   # (behind it now)
                del self.levels[k]
        if self.fade and ready >= n:
            f = self.fade[1] + dt / MANDEL_FADE
            self.fade = (self.fade[0], f) if f < 1 else None
        if self.phase == "hold":
            self.wait -= dt
            if self.wait <= 0:
                self.restart()
                return "next"
            return None
        if ready < n:
            return None                                  # (nothing to show yet)
        end = self.dive[3]
        limit = min(end, ready + 0.5)
        room = (limit - self.L) / (1.2 if limit >= end else 0.4)
        ease = max(0.06, min(1.0, room) ** 2 * (3 - 2 * min(1.0, room)))
        start = min(1.0, 0.3 + self.clock / 4)
        self.L = min(limit, self.L + MANDEL_SPEEDS[self.values["speed"]] * dt * ease * start)
        if self.L >= end - 1e-3:
            self.L, self.phase, self.wait = end, "hold", MANDEL_HOLD
        return None

    def poke(self):
        """X: new colours."""
        self.shift = (self.shift + 0.381966) % 1.0

    # exploring: the buttons
    def hold(self, name):
        """A button pressed while exploring: a step at once, and on and on while it's held."""
        if name in self.MOVES:
            self.held.add(name)
            self.held_at = time.perf_counter()
            self.nudge(name)

    def nudge(self, name):
        """One step (a button pressed once, or a press repeated by the web page)."""
        if name in self.MOVES:
            mx, my, mz = self.MOVES[name]
            self.ex_go(mx * self.NUDGE[0], my * self.NUDGE[0], mz * self.NUDGE[1])

    def release(self, name):
        self.held.discard(name)

    def ex_step(self, dt):
        """The buttons held down move the view on (zooming as quickly as Zoom says)."""
        mx = sum(self.MOVES[k][0] for k in self.held if k in self.MOVES)
        my = sum(self.MOVES[k][1] for k in self.held if k in self.MOVES)
        mz = sum(self.MOVES[k][2] for k in self.held if k in self.MOVES)
        rate = MANDEL_SPEEDS.get(self.values.get("speed"), MANDEL_SPEEDS["Normal"]) / MANDEL_SPEEDS["Normal"]
        self.ex_go(mx * self.PAN * dt, my * self.PAN * dt, mz * self.ZOOM * rate * dt)

    def ex_go(self, dx, dy, dz):
        """The view moves (dx, dy: in its own widths) and zooms (dz: levels). A sharp picture being worked
        out for a view it has left behind is given up."""
        if not (dx or dy or dz) or self.ex is None:
            return
        lo_x, hi_x, lo_y, hi_y = self.REACH
        with self.lock:
            v = self.ex
            W = MANDEL_START[2] * 2.0 ** -v["L"]
            v["cx"] = min(hi_x, max(lo_x, v["cx"] + dx * W))
            v["cy"] = min(hi_y, max(lo_y, v["cy"] + dy * W))
            v["L"] = self.L = min(self.DEEPEST, max(0.0, v["L"] + dz))
            j = self.job
            if j is not None and j.spec["kind"] == "full":
                jw, (jx, jy) = j.spec["width"], j.spec["middle"]
                W = MANDEL_START[2] * 2.0 ** -v["L"]
                if abs(math.log2(jw / W)) > 0.25 or max(abs(v["cx"] - jx), abs(v["cy"] - jy)) > 0.25 * jw:
                    self.job = None
                    self.gen += 1
            self.lock.notify_all()

    # drawing
    def picture(self):
        """The view now. Touring: the level it's at, grown to fit, with the next level drawn into its
        middle. Exploring: the rough picture and then the sharp one, each where it falls in the view."""
        from PIL import Image
        new = None
        if self.phase == "explore":
            new = self.ex_picture()
        else:
            with self.lock:
                n = int(self.L)
                A, B = self.levels.get(n), self.levels.get(n + 1) if self.L > n else None
            if A is not None:
                colours = self.colours()
                for lv in (A, B):
                    if lv is not None and lv["colours"] != colours:
                        self.paint(lv, colours)
                key = (self.L, id(A), id(B), colours, self.w, self.h)
                if key != self.pic_key:
                    self.pic, self.pic_key, self.stand_in = self.compose(n, A, B), key, None
                new = self.pic
        if self.fade:
            old = self.fade[0]
            if old.size != (self.w, self.h):
                old = old.resize((self.w, self.h), Image.BILINEAR)
            return Image.blend(old, new, co_ease(self.fade[1])) if new is not None else old
        return new if new is not None else self.stand_in

    def compose(self, n, A, B):
        from PIL import Image
        w, h = self.w, self.h
        vx, vy, W = self.view(self.L)
        H = W * h / w
        ax, ay, AW = self.view(n)
        AH = AW * h / w
        left, top = ((vx - W / 2) - (ax - AW / 2)) / AW * w, ((ay + AH / 2) - (vy + H / 2)) / AH * h
        box = (max(0.0, left), max(0.0, top), min(float(w), left + W / AW * w), min(float(h), top + H / AH * h))
        pic = A["pic"].resize((w, h), Image.BILINEAR, box=box)
        if B is not None:                                # the next level, sharp, in the middle
            bx, by, BW = self.view(n + 1)
            BH = BW * h / w
            l, t = ((bx - BW / 2) - (vx - W / 2)) / W * w, ((vy + H / 2) - (by + BH / 2)) / H * h
            r, b = l + BW / W * w, t + BH / H * h
            x0, y0, x1, y1 = max(0, math.ceil(l)), max(0, math.ceil(t)), min(w, math.floor(r)), min(h, math.floor(b))
            if x1 - x0 >= 2 and y1 - y0 >= 2:
                sx, sy = w / (r - l), h / (b - t)
                src = (max(0.0, (x0 - l) * sx), max(0.0, (y0 - t) * sy), min(float(w), (x1 - l) * sx),
                       min(float(h), (y1 - t) * sy))
                pic.paste(B["pic"].resize((x1 - x0, y1 - y0), Image.BILINEAR, box=src), (x0, y0))
        return pic

    def ex_picture(self):
        from PIL import Image
        with self.lock:
            v = dict(self.ex) if self.ex else None
            quick, full = self.ex_quick, self.ex_full
        if v is None:
            return None
        colours = self.colours()
        for p in (quick, full):
            if p is not None and p.get("nu") is not None and p["colours"] != colours:
                self.paint(p, colours)
        key = ("ex", v["cx"], v["cy"], v["L"], id(quick), id(full), quick and quick["colours"],
               full and full["colours"], self.w, self.h)
        if key == self.pic_key:
            return self.pic
        W = MANDEL_START[2] * 2.0 ** -v["L"]
        img = Image.new("RGB", (self.w, self.h), MANDEL_INSIDE)
        got = [p for p in (quick, full) if p is not None and p.get("pic") is not None]
        for p in sorted(got, key=lambda p: p["w"] / p["width"]):     # (the sharper one on top)
            self.place(img, p, v["cx"], v["cy"], W)
        self.pic, self.pic_key = img, key
        return img

    @staticmethod
    def place(img, p, cx, cy, W):
        """Picture p, as much of it as falls in the view (its middle cx, cy and width W), drawn where it
        falls on img."""
        from PIL import Image
        w, h = img.size
        H = W * h / w
        pw, ph = p["width"], p["width"] * p["h"] / p["w"]
        l0, t0 = (p["cx"] - cx) - pw / 2, (p["cy"] - cy) + ph / 2      # its edges, from the view's middle
        il, ir = max(l0, -W / 2), min(l0 + pw, W / 2)
        it, ib = min(t0, H / 2), max(t0 - ph, -H / 2)
        if ir <= il or it <= ib:
            return
        x0, x1 = math.ceil((il + W / 2) / W * w - 1e-9), math.floor((ir + W / 2) / W * w + 1e-9)
        y0, y1 = math.ceil((H / 2 - it) / H * h - 1e-9), math.floor((H / 2 - ib) / H * h + 1e-9)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        def sx(X):
            return ((X / w * W - W / 2) - l0) / pw * p["w"]

        def sy(Y):
            return (t0 - (H / 2 - Y / h * H)) / ph * p["h"]
        box = (max(0.0, sx(x0)), max(0.0, sy(y0)), min(float(p["w"]), sx(x1)), min(float(p["h"]), sy(y1)))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        if (x1 - x0, y1 - y0) == p["pic"].size and box == (0.0, 0.0, float(p["w"]), float(p["h"])):
            img.paste(p["pic"], (x0, y0))
        else:
            img.paste(p["pic"].resize((x1 - x0, y1 - y0), Image.BILINEAR, box=box), (x0, y0))

    def draw(self, img, x0, y0):
        pic = self.picture()
        if pic is not None:
            img.paste(pic, (x0, y0))
        if self.phase == "explore":                    # (where A zooms in to)
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            x, y = x0 + self.w // 2, y0 + self.h // 2
            arms = [((x - 7, y), (x - 3, y)), ((x + 3, y), (x + 7, y)), ((x, y - 7), (x, y - 3)), ((x, y + 3), (x, y + 7))]
            for colour, width in (((0, 0, 0), 3), ((255, 255, 255), 1)):
                for arm in arms:
                    d.line(arm, fill=colour, width=width)

    def hints(self):
        """Its buttons (beside the usual ones' place along the bottom)."""
        if self.phase == "explore":
            return [("✚", "Move"), ("A", "Zoom in"), ("Y", "Zoom out"), ("X", "Colours"), ("START", "Options")]
        return [("A", "Play" if self.paused else "Pause"), ("X", "Colours"), ("Y", "New start"), ("✚", "Explore"),
                ("START", "Options")]

    def inset(self, w, h):
        """For beside the box: the whole set, small, with where the view is now marked on it, and the
        place's name (or, exploring, where it is)."""
        from PIL import ImageDraw
        cx0, cy0, w0 = MANDEL_START
        h0 = w0 * h / w
        key = (w, h, self.colours())
        if self.map[0] != key:
            lv = MandelLevel(0, (cx0, cy0), w0, w, h, 300)
            while not lv.done:
                lv.step()
            got = {"nu": lv.nu, "w": w, "h": h}
            self.paint(got, self.colours())
            self.map = (key, got["pic"])
        img = self.map[1].copy()
        d = ImageDraw.Draw(img)
        cx, cy, W = self.here()
        mx, my = (cx - (cx0 - w0 / 2)) / w0 * w, ((cy0 + h0 / 2) - cy) / h0 * h
        rw, rh = W / w0 * w, W / w0 * w * self.h / self.w
        if rw >= 8:
            d.rectangle((mx - rw / 2, my - rh / 2, mx + rw / 2, my + rh / 2), outline=(255, 255, 255))
        else:
            d.ellipse((mx - 5, my - 5, mx + 5, my + 5), outline=(0, 0, 0), width=3)
            d.ellipse((mx - 5, my - 5, mx + 5, my + 5), outline=(255, 255, 255), width=1)
        if self.phase == "explore":
            return img, f"{cx:.5f} {'-' if cy < 0 else '+'} {abs(cy):.5f}i"
        return img, self.dive[0]

    def look(self):
        """Exploring: where the view is (the map beside the box shows it)."""
        if self.phase != "explore":
            return None
        cx, cy, W = self.here()
        return round(cx, 5), round(cy, 5), round(math.log2(W), 1)

    def stats(self):
        if self.phase == "explore":
            full = self.ex_full
            its = full.get("maxit") if full else None
        else:
            lv = self.levels.get(int(self.L))
            its = lv["maxit"] if lv else None
        return [("Zoom", mandel_zoom(2.0 ** self.L)), ("Iterations", f"{its:,}" if its else "…")]

    def note(self):
        if self.phase != "hold":
            return None
        left = f"The next dive in {max(1, math.ceil(self.wait))} s"
        if self.dive[4]:
            return "A tiny copy of the whole set", f"{mandel_zoom(2.0 ** self.L)} closer. {left}"
        return self.dive[0], f"As deep as it can go. {left}"
