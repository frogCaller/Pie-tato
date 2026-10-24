"""Snake (the Games tab), and its AI's own thread: a decision model on your bot's computer."""
import math
import random
import threading
import time
from collections import deque

from .theme import co_mix, LINE
from .bot import ollama_decide, ollama_deciders
from .sims import Sim, SIM_FLOOR


# ---- Snake (the Games tab) -------------------------------------------------------------------------------
SNAKE_BOARDS = (("Small", (16, 12)), ("Medium", (24, 19)), ("Large", (32, 25)))   # cells across and down
SNAKE_SPEEDS = (("Slow", 6.0), ("Normal", 9.0), ("Fast", 12.0))                     # steps a second
SNAKE_FASTER = (0.03, 1.5)     # each apple makes it this much quicker, up to this many times the speed
SNAKE_HEAD, SNAKE_TAIL = (126, 214, 112), (44, 120, 70)                             # its colours, head to tail
SNAKE_APPLE, SNAKE_LEAF, SNAKE_STEM = (232, 78, 64), (104, 184, 84), (120, 86, 52)
SNAKE_DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
SNAKE_OPTIONS = (("speed", "Speed", tuple(n for n, _ in SNAKE_SPEEDS), "Normal"),
                 ("board", "Board", tuple(n for n, _ in SNAKE_BOARDS), "Medium"),
                 ("walls", "Walls", ("Solid", "Wrap"), "Solid"))
SNAKE_AI_WAIT = 8.0        # seconds a move may take to come (the game goes on meanwhile), or it's lost
SNAKE_AI_WAKE = 120.0      # ...the first, while the model wakes up on the other computer (the game waits)
SNAKE_AI_TRIES = 3         # moves lost in a row, and the AI gives up
SNAKE_AI_AGAIN = 3.0       # seconds the AI's game over shows, then it plays again
SNAKE_AI_FRESH = 60.0      # seconds a list of the decision models is good for
SNAKE_AI_GUESS = 0.2       # seconds a move's reckoned to take, till its moves have been timed
SNAKE_AI_SPARE = 1.25      # ...and some to spare (it's asked about where the snake will be when its answer comes)
SNAKE_AI_AHEAD = 30        # moves ahead it's asked about, at most (slower than that, it can't play)
SNAKE_AI_BEHIND = 0.5      # less than this share of the moves decided by it: it's told it can't keep up...
SNAKE_AI_JUDGE = 100       # ...once a game's gone on this many moves
SNAKE_AI_SAYS = ("Which way should the snake go next? Never pick a deadly move, and avoid trapped and risky "
                 "ones. Of the safe moves, pick one that eats the apple, or else one that gets closer to it.")


class Snake(Sim):
    """Snake: the d-pad steers it to the apples, and each one it eats makes it longer, until it runs
    into itself (or a wall: Walls can wrap round instead). A game: ready (A or the d-pad starts it), on,
    over (A plays again). The board is so many cells (Board) in the box and full screen alike, so a
    game carries on when the box changes size."""
    key = "snake"
    blurb = "Steer with the d-pad and eat the apples: each one makes the snake longer. Don't run into yourself."
    poke_label = None
    options = SNAKE_OPTIONS             # (and AI: the decision models on your bot's computer, once found)
    restart_for = ("board", "walls")
    holds = True                        # (it follows the d-pad itself: no key repeat)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.best = 0                   # the most apples in a game (kept with your settings)
        self.ai_best = 0                # ...in a game the AI played
        self.ai = False                 # a decision model is playing (X)
        self.ai_model = ""              # ...which
        self.ai_waking = False          # ...waiting for its first move (the game waits too)
        self.ai_ms = None               # how long its moves take to come, of late (ms)
        self.ai_want = False            # X pressed: it takes over once a decision model is found
        self.ai_lost = 0                # its moves lost in a row
        self.games = 0                  # (each game's number: a move meant for one isn't used in the next)
        self.pic, self.pic_key, self.floor = None, None, (None, None)
        self.restart()

    def restart(self):
        """A new game: a short snake in the middle, heading right, and an apple."""
        super().restart()
        self.cols, self.rows = dict(SNAKE_BOARDS)[self.values["board"]]
        x, y = self.cols // 2, self.rows // 2
        self.body = deque([(x - 2, y), (x - 1, y), (x, y)])         # tail first, head last
        self.taken = set(self.body)
        self.dir = (1, 0)
        self.turns = []                 # d-pad presses still to come (two at most: a quick U-turn)
        self.apples = 0
        self.phase = "on" if self.ai and not self.ai_waking else "ready"   # ready, on, over (the AI: straight on)
        self.why = None                 # over: what it ran into (None: it filled the board)
        self.acc = 0.0                  # seconds towards the next step
        self.steps = 0
        self.paused = False
        self.new_best = False
        self.ai_used = self.ai          # (a game the AI had a hand in counts towards its best, not yours)
        self.plan = {}                  # the AI's moves, decided ahead: {k: its move after the k-th step}
        self.ai_moves = self.ai_kept = 0    # (moves made while it plays, and those it picked in time)
        self.again = SNAKE_AI_AGAIN     # (the AI's game over: seconds until it plays again)
        self.games += 1
        self.apple = self.place_apple()

    def refit(self, w, h):
        """Full screen, and back: the same board with bigger or smaller cells, the game carrying on."""
        self.w, self.h = w, h
        self.pic_key = None

    def place_apple(self):
        """An empty cell for the next apple (None: there are none left)."""
        for _ in range(60):
            cell = (self.rng.randrange(self.cols), self.rng.randrange(self.rows))
            if cell not in self.taken:
                return cell
        free = [(x, y) for y in range(self.rows) for x in range(self.cols) if (x, y) not in self.taken]
        return self.rng.choice(free) if free else None

    # the buttons
    def steer(self, name):
        """A d-pad press: its next turn (and the one after, if you're quick). Straight back the way it
        came, no. Ready: off it goes (that way). Paused: on again. While the AI plays, the d-pad does
        nothing (its moves are its plan: see step)."""
        d = SNAKE_DIRS[name]
        if self.phase == "over" or self.ai:
            return
        if self.phase == "ready":
            if d == (-self.dir[0], -self.dir[1]):     # (back the other way: the snake turns round first)
                self.body.reverse()
                self.dir = d
            elif d != self.dir:
                self.turns = [d]
            self.phase = "on"
            return
        self.paused = False
        last = self.turns[-1] if self.turns else self.dir
        if d != last and d != (-last[0], -last[1]) and len(self.turns) < 2:
            self.turns.append(d)

    def press_a(self):
        """A: start, pause or play on, or play again."""
        if self.ai_waking:
            return                      # (the AI isn't ready to play yet)
        if self.phase == "ready":
            self.phase = "on"
        elif self.phase == "on":
            self.paused = not self.paused
        else:
            self.restart()

    # moving on
    def rate(self):
        """Steps a second: quicker for each apple eaten, up to a point."""
        step, most = SNAKE_FASTER
        return dict(SNAKE_SPEEDS)[self.values["speed"]] * min(most, 1 + step * self.apples)

    def update(self, dt):
        if self.phase == "over" and self.ai and dt > 0:     # (the AI plays again, after a moment)
            self.again -= dt
            if self.again <= 0:
                self.restart()
                return "again"
            return None
        if self.phase != "on" or self.paused or dt <= 0:
            return None
        self.clock += dt
        self.acc += dt
        out = None
        while self.phase == "on" and self.acc >= 1.0 / self.rate():
            self.acc -= 1.0 / self.rate()
            out = self.step() or out
        return out

    def step(self):
        """One cell on: "ate" an apple, "over" (it ran into something, or filled the board), or None.
        While the AI plays, it goes the way it picked for here, if its answer came in time (else straight
        on: the game doesn't wait for it)."""
        picked = self.plan.pop(self.steps, None) if self.plan else None
        if picked is not None:
            d = SNAKE_DIRS[picked]
            if d != (-self.dir[0], -self.dir[1]):
                self.dir = d
        elif self.turns:
            self.dir = self.turns.pop(0)
        if self.ai:
            self.ai_moves += 1
            if picked is not None:
                self.ai_kept += 1
        hx, hy = self.body[-1]
        x, y = hx + self.dir[0], hy + self.dir[1]
        if self.values["walls"] == "Wrap":
            x, y = x % self.cols, y % self.rows
        elif not (0 <= x < self.cols and 0 <= y < self.rows):
            return self.end("the wall")
        head, tail = (x, y), self.body[0]
        eats = head == self.apple
        if head in self.taken and (eats or head != tail):  # (where its tail was is free: the tail moves on)
            return self.end("itself")
        if not eats:
            self.taken.discard(self.body.popleft())
        self.body.append(head)
        self.taken.add(head)
        self.steps += 1
        if not eats:
            return None
        self.apples += 1
        if self.ai_used and self.apples > self.ai_best:
            self.ai_best, self.new_best = self.apples, True
        elif not self.ai_used and self.apples > self.best:
            self.best, self.new_best = self.apples, True
        self.apple = self.place_apple()
        return "ate" if self.apple is not None else self.end(None)

    def end(self, why):
        self.phase, self.why, self.paused = "over", why, False
        return "over"

    # what's shown
    def stats(self):
        if not self.ai:
            return [("Score", str(self.apples)), ("Best", str(self.best)), ("Length", str(len(self.body)))]
        name = self.ai_model[:-7] if self.ai_model.endswith(":latest") else self.ai_model
        return [("Score", str(self.apples)), ("AI best", str(self.ai_best)), ("Length", str(len(self.body))),
                ("AI", name if len(name) <= 13 else name[:12] + "…"),
                ("Decides in", "…" if self.ai_ms is None else f"{self.ai_ms:,.0f} ms"),
                ("Keeps up", f"{round(100 * self.ai_kept / self.ai_moves)}%" if self.ai_moves else "…")]

    def keeps_up(self):
        """The share of the snake's moves (this game) the AI decided in time: None, too soon to say."""
        return self.ai_kept / self.ai_moves if self.ai_moves >= SNAKE_AI_JUDGE else None

    def note(self):
        name = (self.ai_model[:-7] if self.ai_model.endswith(":latest") else self.ai_model) or "The AI"
        if self.ai_waking:
            return f"Waking up {name}", "Its first move can take a moment"
        if self.phase == "ready":
            return "Snake", "A or the d-pad to start"
        if self.phase != "over":
            return None
        apples = f"{self.apples} apple{'' if self.apples == 1 else 's'}"
        if self.ai:
            title = f"{name}: a new best!" if self.new_best else f"{name}: game over"
            if self.why is None:
                title = f"{name} filled the board!"
            into = f", then into {self.why}" if self.why else ""
            return title, f"{apples}{into}. Again in {max(1, math.ceil(self.again))} s"
        if self.why is None:
            return "You filled the board!", f"{apples}. A to play again"
        return ("A new best!" if self.new_best else "Game over"), f"{apples}, then into {self.why}. A to play again"

    def note_top(self):
        return self.body[-1][1] >= self.rows / 2           # (not over where it crashed)

    def hints(self):
        if self.ai:
            if self.ai_waking or self.phase != "on":
                return [("X", "You play"), ("START", "Options")]
            return [("X", "You play"), ("A", "Play" if self.paused else "Pause"), ("Y", "New game"),
                    ("START", "Options")]
        if self.phase == "ready":
            return [("✚", "Steer"), ("A", "Start"), ("X", "AI plays"), ("START", "Options")]
        if self.phase == "over":
            return [("A", "Play again"), ("X", "AI plays"), ("START", "Options")]
        return [("✚", "Steer"), ("A", "Play" if self.paused else "Pause"), ("X", "AI plays"), ("Y", "New game"),
                ("START", "Options")]

    # the AI: what it's told
    def ahead(self, d):
        """Where a move takes the head: (cell, what's there: "wall", "body", "apple" or None)."""
        hx, hy = self.body[-1]
        x, y = hx + d[0], hy + d[1]
        if self.values["walls"] == "Wrap":
            x, y = x % self.cols, y % self.rows
        elif not (0 <= x < self.cols and 0 <= y < self.rows):
            return None, "wall"
        cell = (x, y)
        if cell == self.apple:
            return cell, "apple"
        if cell in self.taken and cell != self.body[0]:    # (its tail moves on: that's free)
            return cell, "body"
        return cell, None

    def steps_to(self, a, b):
        """Moves from cell a to cell b, if nothing were in the way (round the edges when they wrap)."""
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        if self.values["walls"] == "Wrap":
            dx, dy = min(dx, self.cols - dx), min(dy, self.rows - dy)
        return dx + dy

    def room(self, start, most):
        """Free cells the head could get to from start (up to `most`: enough is enough). Its body is in the
        way, except the tail, which moves on."""
        wrap = self.values["walls"] == "Wrap"
        blocked = self.taken - {self.body[0]}
        seen, todo = {start}, [start]
        while todo and len(seen) < most:
            x, y = todo.pop()
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if wrap:
                    nx, ny = nx % self.cols, ny % self.rows
                elif not (0 <= nx < self.cols and 0 <= ny < self.rows):
                    continue
                if (nx, ny) not in seen and (nx, ny) not in blocked:
                    seen.add((nx, ny))
                    todo.append((nx, ny))
        return len(seen)

    def copy(self):
        """The game as it stands, to look ahead with (the next apple lands where it will in the game)."""
        c = object.__new__(type(self))
        c.__dict__.update(self.__dict__)
        c.body, c.taken, c.turns, c.plan = deque(self.body), set(self.taken), list(self.turns), dict(self.plan)
        c.rng = random.Random()
        c.rng.setstate(self.rng.getstate())
        return c

    def later(self, moves):
        """The game so many moves on (the AI's moves as it decided them, else straight on): where the
        snake will be. Or as far on as it gets before it runs into something: (that, how many moves on)."""
        c = self.copy()
        for k in range(moves):
            picked = c.plan.get(c.steps)
            d = SNAKE_DIRS[picked] if picked else (c.turns[0] if c.turns else c.dir)
            if d == (-c.dir[0], -c.dir[1]):
                d = c.dir                                  # (as step does: straight back isn't a move)
            if c.ahead(d)[1] in ("wall", "body"):
                return c, k
            c.step()
            if c.phase == "over":                          # (it filled the board)
                return c, k + 1
        return c, moves

    def run_into(self, d, moves):
        """That move, then straight on, for so many moves in all: (how many moves till it runs into
        something, what) or None."""
        c = self.copy()
        c.plan, c.turns = {}, [d]
        for k in range(1, moves + 1):
            what = c.ahead(c.turns[0] if c.turns else c.dir)[1]
            if what in ("wall", "body"):
                return k, what
            c.step()
            if c.phase == "over":                          # (it filled the board)
                return None
        return None

    def situation(self, gap=1):
        """For the AI: the game as it stands, in words (state), and its moves (choices: straight back the
        way it came isn't one), each deadly (into a wall or its body), trapped, risky or safe, and what it
        does about the apple. Trapped: into a dead end too small for the snake (unless the other moves have
        no more room: late in a game, that's all there is). Risky, when the AI's slow (gap: how many moves
        the snake makes for each of its decisions): it runs into something going on straight before it
        could turn again, so it must turn soon (the apple's worth it: eating it isn't risky)."""
        hx, hy = self.body[-1]
        names = {v: k for k, v in SNAKE_DIRS.items()}
        n = len(self.body)
        words = [f"Snake, on a grid {self.cols} columns wide and {self.rows} rows high (column 0 on the left, "
                 "row 0 at the top), " + ("with walls all round." if self.values["walls"] == "Solid"
                                          else "with no walls: off one edge, the snake comes back on at the opposite edge."),
                 f"The snake is {n} cells long, heading {names[self.dir]}, its head at column {hx}, row {hy}."]
        if self.apple is not None:
            ax, ay = self.apple

            def way(off, size):                         # (the short way: round the edge, when they wrap)
                if self.values["walls"] == "Wrap" and abs(off) > size - abs(off):
                    return off - size if off > 0 else off + size, " round the edge"
                return off, ""
            dx, rx = way(ax - hx, self.cols)
            dy, ry = way(ay - hy, self.rows)
            across = f"{abs(dx)} column{'' if abs(dx) == 1 else 's'} to the {'right' if dx > 0 else 'left'}{rx}"
            down = f"{abs(dy)} row{'' if abs(dy) == 1 else 's'} {'down' if dy > 0 else 'up'}{ry}"
            where = " and ".join(x for x, k in ((across, dx), (down, dy)) if k)
            words.append(f"The apple is at column {ax}, row {ay}: {where} from the head.")
        back = (-self.dir[0], -self.dir[1])                 # (straight back: into its neck)
        moves = {name: (d, *self.ahead(d)) for name, d in SNAKE_DIRS.items() if d != back}
        rooms = {name: self.room(cell, n + 2) for name, (_, cell, what) in moves.items() if what in (None, "apple")}
        most = max(rooms.values(), default=0)
        things = {"wall": "the wall", "body": "its own body"}
        choices = {}
        for name, (d, cell, what) in moves.items():
            if what in things:
                choices[name] = f"Deadly: the snake runs into {things[what]}."
                continue
            if what == "apple":
                food = "it eats the apple"
            elif self.apple is not None:
                now, then = self.steps_to(self.body[-1], self.apple), self.steps_to(cell, self.apple)
                away = f"{then} move{'' if then == 1 else 's'} away"
                food = (f"it gets closer to the apple ({away})" if then < now
                        else f"it gets further from the apple ({away})" if then > now
                        else f"it gets no closer to the apple ({away})")
            else:
                food = ""
            more = f" {food[0].upper()}{food[1:]}." if food else ""
            long = n + 1 if what == "apple" else n          # (an apple: one longer)
            hit = self.run_into(d, gap) if gap > 1 and what != "apple" else None   # (the apple: it's worth it)
            if rooms[name] <= long and rooms[name] < most:
                choices[name] = (f"Trapped: it's a dead end with room for only {rooms[name]} "
                                 f"cell{'' if rooms[name] == 1 else 's'}.{more}")
            elif hit:                                  # (it can turn in time, if its next answer comes in time)
                choices[name] = (f"Risky: it must turn soon. Going on straight, it runs into {things[hit[1]]} "
                                 f"in {hit[0]} moves.{more}")
            elif food.startswith(("it eats", "it gets closer")):
                choices[name] = f"Safe: {food}."
            else:
                choices[name] = f"Safe, but {food}." if food else "Safe."
        return " ".join(words), choices

    def layout(self):
        """The size of a cell (px), and where the board starts in the box."""
        c = max(4, min(self.w // self.cols, self.h // self.rows))
        return c, (self.w - c * self.cols) // 2, (self.h - c * self.rows) // 2

    def board(self):
        """The empty board, kept: faint squares, and an edge when the walls are solid."""
        from PIL import Image, ImageDraw
        c, ox, oy = self.layout()
        key = (self.w, self.h, self.cols, self.rows, c, self.values["walls"])
        if self.floor[0] != key:
            img = Image.new("RGB", (self.w, self.h), SIM_FLOOR)
            d = ImageDraw.Draw(img)
            light = co_mix(SIM_FLOOR, (255, 255, 255), 0.025)
            for y in range(self.rows):
                for x in range(y % 2, self.cols, 2):
                    d.rectangle((ox + x * c, oy + y * c, ox + x * c + c - 1, oy + y * c + c - 1), fill=light)
            if self.values["walls"] == "Solid":
                d.rectangle((ox - 1, oy - 1, ox + c * self.cols, oy + c * self.rows), outline=LINE)
            self.floor = (key, img)
        return self.floor[1].copy()

    def picture(self):
        """The board with the apple and the snake on it: a band from its tail to its head, round at
        both ends, its eyes looking where it's going."""
        from PIL import ImageDraw
        img = self.board()
        d = ImageDraw.Draw(img)
        c, ox, oy = self.layout()
        if self.apple is not None:
            ax, ay = ox + self.apple[0] * c + c / 2, oy + self.apple[1] * c + c / 2 + c * 0.05
            r = c * 0.34
            d.line((ax, ay - r * 0.8, ax + c * 0.07, ay - r - c * 0.12), fill=SNAKE_STEM, width=max(1, c // 12))
            d.ellipse((ax - r, ay - r, ax + r, ay + r), fill=SNAKE_APPLE)
            d.ellipse((ax + c * 0.05, ay - r - c * 0.13, ax + c * 0.27, ay - r - c * 0.02), fill=SNAKE_LEAF)
        cells, n = list(self.body), len(self.body)
        w = c - 2 * max(1, c // 10)                   # (how thick it is)

        def mid(cell):
            return ox + cell[0] * c + (c - 1) / 2, oy + cell[1] * c + (c - 1) / 2

        def dot(at, colour):                          # (as round as the lines are thick)
            r = (w - 1) / 2
            d.ellipse((at[0] - r, at[1] - r, at[0] + r, at[1] + r), fill=colour)
        # a few thick lines, each a stretch of it in one colour (from the tail's to the head's); one
        # wrapped round an edge goes off that side, and on again from the other
        pieces = min(8, n - 1)
        line, colour, was = [mid(cells[0])], None, None
        for k in range(n - 1):
            a, b = cells[k], cells[k + 1]
            hue = co_mix(SNAKE_TAIL, SNAKE_HEAD, (k * pieces // (n - 1) + 0.5) / pieces)
            dx, dy = b[0] - a[0], b[1] - a[1]
            wrap = abs(dx) + abs(dy) != 1
            if wrap:
                dx = -1 if dx > 1 else 1 if dx < -1 else dx
                dy = -1 if dy > 1 else 1 if dy < -1 else dy
            pa, pb = mid(a), mid(b)
            if colour is not None and (hue != colour or wrap):
                if len(line) >= 2:
                    d.line(line, fill=colour, width=w, joint="curve")
                if not wrap and (dx, dy) != was:
                    dot(pa, hue)                      # (a corner where the colour changes: round it)
                line = [pa]
            colour = hue
            if wrap:
                line.append((pa[0] + dx * c / 2, pa[1] + dy * c / 2))
                d.line(line, fill=colour, width=w, joint="curve")
                line = [(pb[0] - dx * c / 2, pb[1] - dy * c / 2), pb]
            elif (dx, dy) == was and len(line) >= 2:
                line[-1] = pb                         # (straight on: one longer line)
            else:
                line.append(pb)
            was = (dx, dy)
        if len(line) >= 2:
            d.line(line, fill=colour, width=w, joint="curve")
        dot(mid(cells[0]), SNAKE_TAIL)
        dot(mid(cells[-1]), SNAKE_HEAD)
        hx, hy = cells[-1]
        cx, cy = ox + hx * c + c / 2, oy + hy * c + c / 2
        dx, dy = self.dir
        e, pr = max(1.5, c * 0.15), max(1.0, c * 0.08)
        for side in (-1, 1):                          # its eyes: ahead of the middle, either side
            ex, ey = cx + dx * c * 0.12 - dy * side * c * 0.2, cy + dy * c * 0.12 + dx * side * c * 0.2
            if self.phase == "over" and self.why is not None:
                d.line((ex - e, ey - e, ex + e, ey + e), fill=(24, 30, 26), width=max(1, c // 14))
                d.line((ex - e, ey + e, ex + e, ey - e), fill=(24, 30, 26), width=max(1, c // 14))
                continue
            d.ellipse((ex - e, ey - e, ex + e, ey + e), fill=(246, 248, 250))
            px, py = ex + dx * pr * 0.8, ey + dy * pr * 0.8
            d.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(24, 30, 26))
        return img

    def draw(self, img, x0, y0):
        key = (self.steps, self.phase, self.apple, self.dir, self.w, self.h, self.cols, self.rows,
               self.values["walls"])
        if key != self.pic_key:
            self.pic, self.pic_key = self.picture(), key
        img.paste(self.pic, (x0, y0))


class SnakeBrain:
    """Snake's AI: a decision model on your bot's computer, asked on a thread of its own, so the game
    never waits for it (a move that comes too late is the model's own fault). One question at a time:
    which decision models that computer has, or the next move."""

    def __init__(self):
        self.cv = threading.Condition()
        self.job = None                 # ("models", server) or ("move", server, model, state, choices, tag, timeout)
        self.done = []                  # what came back, for the main loop: (kind, tag, answer, ms, error)
        self.models, self.models_for, self.models_at = [], "", -1e9    # the decision models, from where, when
        self.thread = None

    def busy(self):
        """Still on a question, or its answer's not been taken yet."""
        with self.cv:
            return self.job is not None or bool(self.done)

    def ask(self, job):
        """A question for the thread (False: it's still on the last one)."""
        with self.cv:
            if self.job is not None:
                return False
            self.job = job
            self.cv.notify()
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.run, daemon=True, name="snake-ai")
            self.thread.start()
        return True

    def take(self):
        with self.cv:
            out, self.done = self.done, []
        return out

    def run(self):
        while True:
            with self.cv:
                while self.job is None:
                    self.cv.wait()
                job = self.job
            t0, out = time.monotonic(), None
            try:
                if job[0] == "models":
                    found = ollama_deciders(job[1])
                    with self.cv:
                        self.models, self.models_for, self.models_at = found, job[1], time.monotonic()
                    out = ("models", None, found, 0.0, "")
                else:
                    _, server, model, state, choices, tag, timeout = job
                    pick, _ = ollama_decide(server, model, state, SNAKE_AI_SAYS, choices, timeout)
                    out = ("move", tag, pick, (time.monotonic() - t0) * 1000, "")
            except Exception as ex:                    # (it says why; the game carries on regardless)
                out = (job[0], job[5] if job[0] == "move" else None, None, 0.0, str(ex) or repr(ex))
            with self.cv:
                self.done.append(out)
                self.job = None
