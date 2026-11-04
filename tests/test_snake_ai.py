"""Snake's AI: what a decision model is told (the board, the apple, and each move deadly, risky or safe:
a wall, its own body, the apple, a dead end, a wall it can't turn away from in time when it's slow),
looking ahead (where the snake will be when an answer comes), then in the game's own time against a
stand-in that takes so long to answer (each move made right where it was picked for; a quick one keeping
up with every move; a slow one told it can't; late answers not used), then X in media mode against a
stand-in Ollama on 'your bot's computer' (only its decision models offered; the model woken first; the
game never waiting for a slow one; one that keeps failing given up; another picked on START's card; no
Bot set up, no decision models, an Ollama too old), in real time."""
import json, os, random, re, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw
S = SP + "/tsnakeai" + os.environ.get("RUN", "")
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u"); os.makedirs(S + "/static")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: S + "/home/u"
g.settings_dir = lambda: S + "/static"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
for t in g.LIBRARY:
    if "files" in t:
        t["files"] = [S + "/static/" + os.path.basename(f) for f in t["files"]]
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def game(**values):
    return g.Snake(436, 342, random.Random(3), values=values)


def setup(s, body, d, apple):
    s.body = g.deque(body)
    s.taken = set(s.body)
    s.dir, s.apple, s.phase = d, apple, "on"


def policy(choices):
    """A stand-in decision model: safe and the apple; else safe and closer; else safe; else risky; else trapped;
    else anything."""
    for want in ("Safe: it eats", "Safe: it gets closer", "Safe", "Risky", "Trapped"):
        for k, v in choices.items():
            if v.startswith(want):
                return k
    return next(iter(choices))


# ---- what the AI is told ---------------------------------------------------------------------------------
s = game()
setup(s, [(10, 9), (11, 9), (12, 9)], (1, 0), (4, 3))
state, choices = s.situation()
check(f"its moves: up, down or right, not straight back ({sorted(choices)})", sorted(choices) == ["down", "right", "up"])
check(f"...each safe here, closer to the apple one way, further the others: {choices}",
      choices["up"] == "Safe: it gets closer to the apple (13 moves away)."
      and choices["right"] == "Safe, but it gets further from the apple (15 moves away)."
      and choices["down"] == "Safe, but it gets further from the apple (15 moves away).")
check(f"the board, the snake and the apple, in words: {state!r}",
      "24 columns wide and 19 rows high" in state and "walls all round" in state
      and "heading right, its head at column 12, row 9." in state
      and "The apple is at column 4, row 3: 8 columns to the left and 6 rows up from the head." in state)
check(f"...the way the instructions put it: {g.SNAKE_AI_SAYS!r}", "deadly" in g.SNAKE_AI_SAYS and "risky" in g.SNAKE_AI_SAYS
      and "trapped" in g.SNAKE_AI_SAYS and "safe" in g.SNAKE_AI_SAYS and "apple" in g.SNAKE_AI_SAYS)
setup(s, [(21, 2), (22, 2), (23, 2)], (1, 0), (0, 0))
_, choices = s.situation()
check(f"at the edge: {choices['right']!r}", choices["right"] == "Deadly: the snake runs into the wall."
      and choices["up"].startswith("Safe") and choices["down"].startswith("Safe"))
setup(s, [(13, 8), (12, 8), (11, 8), (11, 9), (12, 9)], (1, 0), (0, 0))
_, choices = s.situation()
check(f"its own body: {choices['up']!r}", choices["up"] == "Deadly: the snake runs into its own body.")
setup(s, [(12, 9), (11, 9), (11, 8), (12, 8)], (1, 0), (0, 0))
_, choices = s.situation()
check(f"...but not where its tail is now (it moves on): {choices['down']!r}", choices["down"].startswith("Safe"))
setup(s, [(10, 9), (11, 9), (12, 9)], (1, 0), (13, 8))
_, choices = s.situation(gap=2)
check(f"...a move from the apple: {choices['right']!r}", choices["right"] == "Safe: it gets closer to the apple (1 move away)."
      and choices["down"] == "Safe, but it gets further from the apple (3 moves away).")
setup(s, [(10, 9), (11, 9), (12, 9)], (1, 0), (13, 9))
_, choices = s.situation()
check(f"the apple next to it: {choices['right']!r}", choices["right"] == "Safe: it eats the apple.")
setup(s, [(0, 3), (0, 2), (0, 1), (1, 1), (2, 1), (2, 0)], (0, -1), (20, 15))   # (two cells walled in, top left)
_, choices = s.situation()
check(f"a dead end: {choices['left']!r}",
      choices["left"] == "Trapped: it's a dead end with room for only 2 cells. It gets further from the apple (34 moves away)."
      and choices["right"].startswith("Safe: it gets closer") and choices["up"].startswith("Deadly"))
setup(s, [(0, 3), (0, 2), (0, 1), (1, 1), (2, 1), (2, 0)], (0, -1), (1, 0))   # (the apple in that pocket)
_, choices = s.situation()
check(f"the apple in a dead end: {choices['left']!r}",
      choices["left"] == "Trapped: it's a dead end with room for only 2 cells. It eats the apple."
      and choices["right"].startswith("Safe"))
s = game(board="Small")
body = [(x, y) for y in range(7) for x in (range(16) if y % 2 == 0 else range(15, -1, -1))] + [(15, 7), (14, 7), (13, 7)]
setup(s, body, (-1, 0), (3, 10))                    # (115 cells long, 77 free: whichever way, that's all there is)
_, choices = s.situation()
check(f"late in a game, the space left is all there is: no dead end ({choices['down']!r})",
      choices["down"] == "Safe: it gets closer to the apple (12 moves away)."
      and choices["left"] == "Safe: it gets closer to the apple (12 moves away)." and choices["up"].startswith("Deadly"))
s = game(walls="Wrap")
setup(s, [(21, 2), (22, 2), (23, 2)], (1, 0), (2, 2))
state, choices = s.situation()
check(f"walls that wrap: off the edge is fine ({choices['right']!r})",
      choices["right"] == "Safe: it gets closer to the apple (2 moves away)." and "opposite edge" in state)
check(f"...and the apple's the short way round: {state!r}", "The apple is at column 2, row 2: 3 columns to the right round the edge from the head." in state)
setup(s, [(10, 0), (11, 0), (12, 0)], (1, 0), (12, 9))                           # (19 rows: up or down, as far)
_, choices = s.situation()
check(f"...round the edge, just as far: {choices['up']!r}",
      choices["up"] == "Safe, but it gets no closer to the apple (9 moves away)." and "closer" in choices["down"]
      and "further" in choices["right"])
s = game()
setup(s, [(19, 2), (20, 2), (21, 2)], (1, 0), (0, 10))
_, quick = s.situation()
_, slow = s.situation(gap=3)
check(f"a slow model (3 moves for each it decides): what it'd run into going on straight is risky, it must turn soon "
      f"({slow['right']!r})", all(v.startswith("Safe") for v in quick.values())
      and slow["right"] == ("Risky: it must turn soon. Going on straight, it runs into the wall in 3 moves. "
                            "It gets further from the apple (30 moves away).")
      and slow["up"].startswith("Risky: it must turn soon. Going on straight, it runs into the wall in 3 moves.")
      and slow["down"] == "Safe: it gets closer to the apple (28 moves away).")
setup(s, [(0, 3), (0, 2), (0, 1), (1, 1), (2, 1), (2, 0)], (0, -1), (20, 15))
s.taken |= {(4, 0), (4, 1)}                          # (and something in the way, two cells right)
_, slow = s.situation(gap=3)
check(f"...a dead end's worse: trapped ({slow['left']!r}, {slow['right']!r})",
      slow["left"].startswith("Trapped: it's a dead end") and slow["right"].startswith("Risky: it must turn soon"))
s.taken -= {(4, 0), (4, 1)}

setup(s, [(3, 10), (2, 10), (1, 10)], (-1, 0), (0, 10))
_, slow = s.situation(gap=2)
check(f"...but an apple by the wall isn't (it's worth it, and its next move turns it): {slow['left']!r}",
      slow["left"] == "Safe: it eats the apple." and slow["up"].startswith("Safe") and slow["down"].startswith("Safe"))

# looking ahead: where the snake will be
s = game()
setup(s, [(10, 9), (11, 9), (12, 9)], (1, 0), (13, 9))
s.ai, s.plan = True, {1: "up"}
c, got = s.later(3)
for _ in range(3):
    s.step()
check(f"three moves on: its move as it picked it, else straight on, the apple eaten and the next where it'll land "
      f"({c.body[-1]}, {c.apple})", got == 3 and c.body == s.body and c.apple == s.apple and c.apples == 1
      and c.body[-1] == (13, 7) and c.dir == s.dir == (0, -1))
setup(s, [(19, 2), (20, 2), (21, 2)], (1, 0), (0, 10))
s.plan = {}
c, got = s.later(5)
check(f"...as far as it gets before it runs into the wall ({got}, {c.body[-1]})", got == 2 and c.body[-1] == (23, 2)
      and s.body[-1] == (21, 2))
setup(s, [(10, 9), (11, 9), (12, 9)], (1, 0), (0, 0))
s.plan = {s.steps: "left"}
c, got = s.later(1)
check(f"...a move straight back in its plan: straight on, as step makes it ({c.body[-1]})", got == 1 and c.body[-1] == (13, 9))
s.plan = {}
b = g.SnakeBrain()
b.done.append(("move", (1, 0, 1), "up", 5.0, ""))
busy = b.busy()
b.take()
check(f"its thread: busy till what came back's been taken ({busy}, then {b.busy()})", busy and not b.busy())

# its moves, and its games
s = game()
s.ai = True
s.restart()
check("the AI's game: straight on, no waiting for A", s.phase == "on" and s.ai_used)
s.steer("up")
check("...the d-pad does nothing while it plays", not s.turns and s.dir == (1, 0))
s.plan[s.steps] = "up"
s.apple = (12, 8)
s.step()
check(f"...its own moves do, made where it picked them ({s.dir})", s.dir == (0, -1) and not s.plan)
check(f"...its apples count towards its best, not yours ({s.ai_best}, {s.best})", s.ai_best == 1 and s.best == 0)
s.step()
check(f"...a move it didn't pick in time: straight on ({s.ai_kept} of {s.ai_moves}, {s.stats()[-1]})",
      s.ai_kept == 1 and s.ai_moves == 2 and s.dir == (0, -1) and s.stats()[-1] == ("Keeps up", "50%"))
while s.phase == "on":
    s.step()
check(f"its game over: {s.note()}", s.note()[1].endswith("Again in 3 s") and s.note()[0] == "The AI: a new best!")
s.update(1.0)
check("...counting down", s.phase == "over" and s.note()[1].endswith("Again in 2 s"))
out = s.update(2.1)
check(f"...then it plays again ({out})", out == "again" and s.phase == "on" and s.apples == 0 and not s.ai_moves)


# ---- a stand-in Ollama on your bot's computer ----------------------------------------------------------------
class Fake:
    models = {"nimble:latest": ["decision"], "tev1:latest": ["decision", "completion"], "llama3.2:3b": ["completion", "tools"]}
    wake = 0.6            # seconds a model takes to wake up (its first move)
    slow = 0.0            # ...each move after that
    fail = False          # moves fail
    old = False           # an Ollama from before decision models
    crash = False         # its moves: into whatever's there, or straight on till something is
    awake = set()
    asked = []            # (model, the request) for each move


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def answer(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            return self.answer(200, {"models": [{"name": n} for n in Fake.models]})
        self.answer(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/show":
            caps = Fake.models.get(body.get("model"))
            if caps is None:
                return self.answer(404, {"error": "model not found"})
            return self.answer(200, {"capabilities": caps} if not Fake.old else {})
        if self.path == "/v1/systemone":
            if Fake.old:
                return self.answer(404, {"error": "404 page not found"})
            model = body.get("model")
            if "decision" not in Fake.models.get(model, []):
                return self.answer(400, {"error": f"{model} does not support decisions"})
            q = (body.get("questions") or {}).get("pick") or {}
            Fake.asked.append((model, body))
            if Fake.fail:
                return self.answer(500, {"error": "scoring failed"})
            time.sleep(Fake.wake if model not in Fake.awake else Fake.slow)
            Fake.awake.add(model)
            crit = q.get("criteria") or {}
            pick = policy(crit)
            if Fake.crash:
                ahead = re.search(r"heading (\w+)", str(body.get("state"))).group(1)
                pick = next((k for k, v in crit.items() if v.startswith("Deadly")), ahead if ahead in crit else pick)
            return self.answer(200, {"model": model, "answers": {"pick": {"type": "choice", "choice": pick,
                                     "probabilities": {k: (0.9 if k == pick else 0.05) for k in crit},
                                     "confidence": 0.6}}, "usage": {"input_tokens": 300, "output_tokens": 1}})
        self.answer(404, {"error": "not found"})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]


class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last, self.frames = None, 0

    def show(self, img):
        self.last = img; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.last = img; FB.count += 1; self.frames = FB.count

    def close(self):
        pass


def frames(m, secs, step=0.05):
    """The page, in real time (the AI's thread is real too)."""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        time.sleep(step)
        m.tick()
        m.flush()


def until(m, cond, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        frames(m, 0.05)
    return bool(cond())


def media():
    m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
    m.status_sig = m.status_signature()
    m.view = "home"
    m.home_sel = [a for a, _ in m.home_apps()].index("Games")
    m.press("a")
    m.press("a")                                       # (the Games list: Snake is first)
    return m, m.sim_game()


# ---- in the game's own time: when it's asked, and which answers are used -------------------------------------
class Brain:
    """A stand-in for the AI's thread, in the game's own time: each move comes `took` seconds after it's
    asked for, picked the way policy would."""

    def __init__(self, took):
        self.took, self.t = took, 0.0
        self.asks, self.coming, self.back = [], [], []
        self.models, self.models_for, self.models_at = [], "", 0.0

    def busy(self):
        return bool(self.coming) or bool(self.back)

    def ask(self, job):
        if self.coming:
            return False
        self.asks.append(job)
        self.coming.append((self.t + self.took, job))
        return True

    def tick(self, t):
        self.t = t
        for when, job in self.coming[:]:
            if when <= t + 1e-9:
                self.coming.remove((when, job))
                self.back.append(("move", job[5], policy(job[4]), self.took * 1000, ""))

    def take(self):
        out, self.back = self.back, []
        return out


made, watched = [], []                 # each move the snake being watched made: (game, step, head, way, its pick)
real_step = g.Snake.step


def watching(self):
    if watched and self is watched[0]:
        made.append((self.games, self.steps, self.body[-1], self.dir, self.plan.get(self.steps)))
    return real_step(self)


g.Snake.step = watching
NAMES = {v: k for k, v in g.SNAKE_DIRS.items()}


def where(state):
    got = re.search(r"heading (\w+), its head at column (\d+), row (\d+)", state)
    return got.group(1), (int(got.group(2)), int(got.group(3)))


def play(took, secs, speed="Normal", dt=0.05, then=None):
    """X, and the game played for secs of its own time, a frame each dt; its moves come took seconds after
    they're asked for (then: from halfway on, that). (media, the snake, its moves it picked, those made
    anywhere but where they were picked for, how its games ended, its share of the moves)."""
    m, s = media()
    m.brain, m.snake_ai_model = Brain(took), lambda: "nimble:latest"
    s.values["speed"] = speed
    s.rng = random.Random(7)
    s.restart()
    made.clear(); watched[:] = [s]
    m.snake_ai_start(s)
    t, ends = 0.0, []
    while t < secs:
        if then is not None and t >= secs / 2:
            m.brain.took = then
        m.brain.tick(t)
        m.snake_ai_take(s)
        if s.update(dt) == "over":
            ends.append(s.why)
        m.snake_ai_ask(s)
        t += dt
    watched.clear()
    asked = {(job[5][0], job[5][1]): job[3] for job in m.brain.asks}
    used = [e for e in made if e[4] is not None]
    wrong = [e for e in used if where(asked[(e[0], e[1])]) != (NAMES[e[3]], e[2])]
    return m, s, used, wrong, ends, len(used) / max(1, len(made))


m, s, used, wrong, ends, share = play(0.02, 12)
check(f"a quick model (20 ms a move): each move it picked is made right where it picked it ({len(used)} moves, "
      f"{len(wrong)} anywhere else)", len(used) > 80 and not wrong)
check(f"...it keeps up with the game ({share:.0%} of the moves its own), a move or so ahead "
      f"({max(job[5][1] for job in m.brain.asks) - s.steps if s.games == 1 else '-'})", share >= 0.95)
check(f"...and plays: {s.ai_best} apples, its games ending {ends or 'never'}", s.ai_best >= 4 and "the wall" not in ends)
check(f"...nothing said about keeping up ({m.msg!r})", "keep up" not in (m.msg or ""))
m, s, used, wrong, ends, share = play(0.25, 24)
check(f"a slow model (250 ms a move, 111 ms a move in the game): the moves it picked are still made right where it "
      f"picked them ({len(used)} moves, {len(wrong)} anywhere else)", len(used) > 15 and not wrong)
check(f"...it can't keep up ({share:.0%} of the moves its own), and it says so ({m.msg!r})", 0.2 < share < 0.5
      and "nimble can't keep up at this speed" in (m.msg or "") and "Try Slow in START" in (m.msg or ""))
check(f"...each it decides, it's told what it'd run into going on straight: {m.brain.asks[-1][4]}",
      any("must turn soon. Going on straight" in v for job in m.brain.asks for v in job[4].values()))
m, s, used, wrong, ends, share = play(0.12, 12, speed="Slow")
check(f"...at Slow, it keeps up ({share:.0%} of the moves its own, {len(wrong)} anywhere else)", share >= 0.9 and not wrong)
m, s, used, wrong, ends, share = play(0.02, 12, then=0.5)
check(f"a model slower than it's reckoned: a move that comes too late isn't made anywhere else ({len(used)} moves, "
      f"{len(wrong)} anywhere else)", used and not wrong and share < 0.9)

# a move that comes while it's paused; another model picked, with a move from the last one on its way
m, s = media()
m.brain, m.snake_ai_model = Brain(0.01), lambda: "nimble:latest"
m.snake_ai_start(s)
m.snake_ai_ask(s)
job = m.brain.asks[-1]
check(f"X: its first move asked for, where the snake is, given time to wake up ({job[5]}, {job[6]} s)",
      job[2] == "nimble:latest" and job[5] == (s.games, 0, m.brain_round) and job[6] == g.SNAKE_AI_WAKE and s.ai_waking)
m.snake_ai_ask(s)
check("...once", len(m.brain.asks) == 1)
m.brain.tick(1.0)
m.snake_ai_take(s)
check(f"...awake: off it goes, its move to be made from right there ({s.plan})", s.phase == "on" and not s.ai_waking
      and s.plan == {0: policy(job[4])})
m.snake_ai_ask(s)
s.paused = True
m.brain.tick(2.0)
m.snake_ai_take(s)
check(f"...a move that comes while you've paused it doesn't start it again ({s.plan})", s.paused and len(s.plan) == 2)
s.paused = False
old = m.brain_asked
m.snake_ai_ask(s)
m.brain.coming.clear()
m.brain.back.append(("move", old, "left", 40.0, ""))       # (back from the last model, not yet used)
m.snake_ai_model = lambda: "tev1:latest"
m.snake_ai_ask(s)
check("another model picked, with a move from the last one back: nothing's asked till that's taken",
      m.brain.asks[-1][2] == "nimble:latest")
m.snake_ai_take(s)
m.snake_ai_ask(s)
job = m.brain.asks[-1]
check(f"...then it wakes up first, the game waiting, the last one's moves dropped ({job[2]})", job[2] == "tev1:latest"
      and job[6] == g.SNAKE_AI_WAKE and s.ai_waking and s.paused and not s.plan)
m.brain.coming.clear()
m.brain.back.append(("move", old, "left", 40.0, ""))       # (one more from before it woke)
m.snake_ai_take(s)
check("...a move from before it woke isn't used", s.ai_waking and s.paused and not s.plan)
m.brain.coming.append((m.brain.t + 0.01, job))
m.brain.tick(3.0)
m.snake_ai_take(s)
check(f"...its own is ({s.plan})", not s.ai_waking and not s.paused and s.plan == {s.steps: policy(job[4])})
m.press("b")

# a move that fails: asked for again, while there's time
m, s = media()
m.brain, m.snake_ai_model = Brain(0.01), lambda: "nimble:latest"
m.snake_ai_start(s)
m.snake_ai_ask(s)
m.brain.tick(1.0)
m.snake_ai_take(s)
m.snake_ai_ask(s)
job = m.brain.asks[-1]
m.brain.coming.clear()
m.brain.back.append(("move", job[5], None, 0.0, "nimble:latest couldn't decide: scoring failed"))
m.snake_ai_take(s)
m.snake_ai_ask(s)
again = m.brain.asks[-1]
check(f"a move that failed is asked for again, where it was ({job[5]} then {again[5]})", s.ai and again is not job
      and again[5] == job[5] and s.ai_lost == 1)
m.press("b")

# a frame: what came back used, the move made with it, and the next question asked straight away
m, s = media()
m.brain, m.snake_ai_model = Brain(0.01), lambda: "nimble:latest"
m.snake_ai_start(s)
m.snake_ai_ask(s)
m.brain.tick(1.0)
m.sim_t, s.acc = time.monotonic() - 0.1, 1.0 / s.rate() - 0.05
m.render_sim()
check(f"a frame: its move used, made, and the next asked straight away ({s.steps} steps, {m.brain.asks[-1][5]})",
      s.steps == 1 and s.ai_kept == 1 and len(m.brain.asks) == 2 and m.brain.asks[-1][5][1] >= 1)
m.press("b")
g.Snake.step = real_step

# ---- X, against the stand-in Ollama, in real time ---------------------------------------------------------------
# no Bot set up
m, s = media()
m.press("x")
check(f"X, no Bot set up: it says so ({m.msg!r})", not s.ai and "Set up the Bot" in (m.msg or ""))
m.press("b")

# your bot's computer, with decision models
with open(S + "/static/bot.txt", "w") as f:
    f.write(f"server = 127.0.0.1:{PORT}\nmodel = llama3.2:3b\n")
m, s = media()
until(m, lambda: len(g.Snake.options) > len(g.SNAKE_OPTIONS), 5)
rows = [r for r in m.sim_rows(g.Snake) if r[0] == "ai"]
check(f"opened: its decision models, on START's card ({rows[0][2] if rows else None})",
      rows and rows[0][2] == ("nimble:latest", "tev1:latest"))
hints = [label for _, label, *_ in m.sim_hints(s)]
check(f"its buttons: {hints}", hints == ["Steer", "Start", "AI plays", "Options"])
d = ImageDraw.Draw(Image.new("RGB", (9, 9)))
w = 20 + sum(m.key_w(d, k) + 7 + d.textlength(l, font=m.fonts["small"]) + 18
             for k, l in [("✚", "Steer"), ("A", "Pause"), ("X", "AI plays"), ("Y", "New game"), ("START", "Options")]) - 18
check(f"...the most there are fit along the bottom ({w:.0f} px)", w <= 620)
m.press("x")
frames(m, 0.15)
check(f"X: the AI takes over, waking its model first ({s.note()})", s.ai and s.ai_waking and s.ai_model == "nimble:latest"
      and s.note() == ("Waking up nimble", "Its first move can take a moment") and s.phase == "ready")
check(f"...the game waits for it ({s.steps} steps)", s.steps == 0)
until(m, lambda: s.phase == "on", 5)
check("...awake: off it goes", s.phase == "on" and not s.ai_waking)
until(m, lambda: s.apples >= 2 and s.steps >= 30, 12)       # (where the apples land is luck: 90 steps is plenty)
check(f"it plays: {s.apples} apples, {s.steps} steps, its moves in {s.ai_ms:.0f} ms", s.apples >= 2 and s.steps >= 30
      and s.ai_ms is not None and s.ai_ms < 200)
check(f"...keeping up ({s.ai_kept} of its {s.ai_moves} moves its own)", s.ai_moves and s.ai_kept / s.ai_moves >= 0.9)
check(f"...a move a step at most ({len(Fake.asked)} for {s.steps} steps)", len(Fake.asked) <= s.steps + 3)
model, body = Fake.asked[-1]
q = body["questions"]["pick"]
check("...each a choice of moves, with what each would do, and the game as it stands",
      model == "nimble:latest" and q["type"] == "choice" and q["instructions"] == g.SNAKE_AI_SAYS
      and set(q["criteria"]) <= set(g.SNAKE_DIRS) and len(q["criteria"]) == 3 and body["keep_alive"] == "30m"
      and "apple" in body["state"] and "snake" in body["state"]
      and all(v.split(":")[0].split(",")[0] in ("Deadly", "Trapped", "Risky", "Safe") for v in q["criteria"].values()))
stats = s.stats()
check(f"...beside the board: {stats}", [k for k, _ in stats] == ["Score", "AI best", "Length", "AI", "Decides in", "Keeps up"]
      and stats[3][1] == "nimble" and stats[4][1].endswith(" ms") and stats[5][1].endswith("%"))
hints = [label for _, label, *_ in m.sim_hints(s)]
check(f"...its buttons: {hints}", hints == ["You play", "Pause", "New game", "Options"])
m.msg = None
before = s.turns[:]
m.press("left")
check(f"...the d-pad: it's the AI's game ({m.msg!r})", "X to take over" in (m.msg or "") and s.turns == before)

# the game never waits for a slow model: its moves come late, and that's on it
Fake.slow = 0.8
until(m, lambda: m.brain.busy() and s.phase == "on" and not s.ai_waking and not s.paused, 5)
steps = s.steps
frames(m, 0.4)
moved, thinking = s.steps - steps, m.brain.busy()
check(f"a slow model: while it thinks, the game goes on at its own speed ({moved} steps in 0.4 s)",
      thinking and (moved >= 3 or s.phase == "over"))
until(m, lambda: s.ai_ms is not None and s.ai_ms > 100 or s.phase == "over", 5)
check(f"...its moves take longer now ({s.ai_ms:.0f} ms)", s.ai_ms > 100 or s.phase == "over")
Fake.slow = 0.0

# X again: yours
m.press("x")
frames(m, 0.1)
check(f"X again: your turn ({m.msg!r})", not s.ai and not s.plan and (s.paused or s.phase != "on"))
way = "left" if s.dir[0] == 0 else "up"                   # (a way it can turn: not straight back)
m.press(way)
check(f"...the d-pad works again ({way}: {s.turns}, {s.dir})", s.turns == [g.SNAKE_DIRS[way]] and not s.paused
      or s.phase != "on")

# another model, picked on START's card
m.press("x")
until(m, lambda: s.ai and not s.ai_waking, 5)
m.press("start")
row = [k for k, *_ in m.sim_rows(g.Snake)].index("ai")
for _ in range(row):
    m.press("down")
m.press("right")
m.press("b")
check(f"START: AI, tev1 ({m.setting('sim_snake_ai')})", m.setting("sim_snake_ai") == "tev1:latest")
m.press("a")
until(m, lambda: s.ai_model == "tev1:latest" and not s.ai_waking and s.phase == "on", 5)
frames(m, 1.0)
check(f"...it wakes up, and plays ({Fake.asked[-1][0]})", Fake.asked[-1][0] == "tev1:latest" and s.ai_model == "tev1:latest")

# its game over, then again by itself (it plays too well to wait for one)
Fake.crash = True
until(m, lambda: s.phase == "over", 30)
Fake.crash = False
over = s.games
check(f"its game over: {s.note()}", s.phase == "over" and "tev1" in s.note()[0] and "Again in" in s.note()[1])
until(m, lambda: s.games > over and s.phase == "on", 6)
check("...and it plays again, by itself", s.phase == "on" and s.ai)
check(f"its best is kept apart from yours ({m.setting('snake_ai_best')}, {m.setting('snake_best')})",
      (m.setting("snake_ai_best") or 0) >= 1 and not m.setting("snake_best"))

# moves that keep failing
Fake.fail = True
until(m, lambda: not s.ai, 10)
check(f"moves that keep failing: it gives up, and says why ({m.msg!r})", not s.ai and "The AI stopped" in (m.msg or "")
      and not s.plan)
Fake.fail = False
m.press("b")

# no decision models there, and an Ollama too old for them
Fake.models = {"llama3.2:3b": ["completion"]}
m, s = media()
frames(m, 0.5)
m.press("x")
until(m, lambda: "pull" in (m.msg or ""), 5)
check(f"no decision models: it says so ({m.msg!r})", not s.ai and "ollama pull nimble" in (m.msg or "")
      and len(g.Snake.options) == len(g.SNAKE_OPTIONS))
m.press("b")
Fake.models = {"nimble:latest": ["decision"]}
Fake.old = True
m, s = media()
frames(m, 0.5)
m.press("x")
frames(m, 1.0)
check(f"an Ollama from before decision models: none found ({m.msg!r})", not s.ai and "decision" in (m.msg or ""))
srv.shutdown()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
