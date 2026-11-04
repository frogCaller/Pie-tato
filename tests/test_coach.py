"""The AI player's coach and its stuck check (pitato/coach.py, pitato/anygame.py): what's new on the screen and what
isn't (screens made to look like a game's: a jump on the spot, an enemy going by, words blinking, water moving and a
cursor aren't; a few steps, a new page of words or a new menu are); a player that keeps jumping where it gets nowhere
is stuck: told so, and which buttons it hasn't tried; jumping comes off its list till something new comes; the coach
is asked again; the coach (your Bot's model on a pretend Ollama) shown the screen and told the game, your tips, what
it worked out before and the player's last moves, its answer followed by the decision model; its notes kept beside
the game's saves (yours to edit: your tips left as they are, and read again when you change them); a model that can't
see, an older Ollama, an answer that isn't JSON, no answer, no computer; it rests after failing, waits while the
game's menu is up, and never holds the game up; then with the real emulator, the decision model and the coach
together, turned on from the game's menu."""
import base64, io, json, math, os, random, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import anygame as AG, coach as C, emerald as E, gameai as A, games as GM
from PIL import Image, ImageDraw, ImageFont

S = SP + "/tcoach"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/Saves")
os.makedirs(S + "/bin")
shutil.copy(SP + "/roms/nestest.nes", S + "/home/u/Games/nestest.nes")
open(f"{S}/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
for tool in ("chvt", "fgconsole"):
    open(f"{S}/bin/{tool}", "w").write("#!/bin/sh\necho 1\n")
for f in os.listdir(S + "/bin"):
    os.chmod(f"{S}/bin/{f}", 0o755)
FBF = S + "/fb.bin"
open(FBF, "wb").write(bytes(640 * 480 * 2))
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["PITATO_FB"] = FBF + ":640x480:16"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
GAMES = S + "/home/u/Games"
SAVES = GAMES + "/Saves"
ok_all = []


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


# ---- screens made to look like a game's (240 x 160, as a Game Boy Advance's) --------------------------------------
random.seed(3)
W, H = 240, 160
WORLD = Image.new("RGB", (1600, H))
d = ImageDraw.Draw(WORLD)
for y in range(90):                                         # sky
    d.line([(0, y), (1600, y)], fill=(100 + y // 3, 160 + y // 4, 240))
for x in range(0, 1600, 2):                                 # hills
    hy = 70 + int(14 * math.sin(x / 37.0) + 8 * math.sin(x / 13.0))
    d.line([(x, hy), (x, 120)], fill=(60, 140 + (x // 2) % 3 * 10, 70))
    d.line([(x + 1, hy), (x + 1, 120)], fill=(60, 140, 70))
for x in range(0, 1600, 8):                                 # ground: dirt with grass tufts
    for y in range(120, H, 8):
        d.rectangle([x, y, x + 7, y + 7], fill=(120 + random.randint(-15, 15), 80 + random.randint(-10, 10), 40))
    d.line([(x, 120), (x + 4, 116)], fill=(40, 180, 50), width=2)
for bx in (300, 700, 1100):                                 # tall ledges (brick)
    d.rectangle([bx, 70, bx + 80, 120], fill=(150, 70, 50), outline=(60, 20, 10))
    for yy in range(70, 120, 8):
        d.line([(bx, yy), (bx + 80, yy)], fill=(90, 40, 30))
FONT = ImageFont.load_default()
LINES = ["You'll never get across", "the river without the bridge.", "Find a way up to the castle.",
         "Are we there yet?", "Pick up the box,", "then carry it to the ledge.", "The old king wants to see you.",
         "Hurry, the ball starts soon!"]


def crate(dr, x, y):
    dr.rectangle([x, y, x + 15, y + 15], fill=(170, 120, 60), outline=(90, 60, 20))
    dr.line([(x, y), (x + 15, y + 15)], fill=(90, 60, 20))
    dr.line([(x + 15, y), (x, y + 15)], fill=(90, 60, 20))


def scene(px, jump=0, enemy=None, water=0, carry=False, crate_at=250):
    cam = max(0, px - 100)
    im = WORLD.crop((cam, 0, cam + W, H)).copy()
    dr = ImageDraw.Draw(im)
    x, y = px - cam, 92 - jump
    dr.rectangle([x + 4, y, x + 11, y + 7], fill=(240, 200, 160))
    dr.rectangle([x + 2, y + 8, x + 13, y + 17], fill=(200, 30, 30))
    dr.rectangle([x + 3, y + 18, x + 12, y + 27], fill=(40, 40, 160))
    if carry:
        crate(dr, x, y - 16)
    elif crate_at is not None:
        crate(dr, crate_at - cam, 104)
    if enemy is not None:
        dr.ellipse([enemy - cam, 106, enemy - cam + 14, 119], fill=(90, 0, 120))
    if water:
        for xx in range(W):
            dr.line([(xx, 150 + int(3 * math.sin((xx + water * 2) / 5.0))), (xx, H)], fill=(30, 90, 200))
    return im


def dialog(i):
    im = scene(150)
    dr = ImageDraw.Draw(im)
    dr.rectangle([4, 112, 235, 156], fill=(250, 250, 250), outline=(20, 20, 20), width=2)
    dr.text((10, 118), LINES[i % 8], font=FONT, fill=(0, 0, 0))
    dr.text((10, 134), LINES[(i + 3) % 8], font=FONT, fill=(0, 0, 0))
    return im


def menu(sel, items=("New game", "Continue", "Options", "Sound test", "Credits")):
    im = Image.new("RGB", (W, H), (10, 10, 60))
    dr = ImageDraw.Draw(im)
    for k, t in enumerate(items):
        dr.text((70, 30 + k * 22), t, font=FONT, fill=(255, 255, 255))
    dr.text((52, 30 + sel * 22), ">", font=FONT, fill=(255, 220, 0))
    return im


def title(on):
    im = Image.new("RGB", (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rectangle([40, 20, 200, 70], fill=(200, 40, 40))
    dr.text((80, 38), "SUPER GAME", font=FONT, fill=(255, 255, 255))
    if on:
        dr.text((85, 110), "PRESS START", font=FONT, fill=(255, 255, 0))
    return im


def news(images):
    seen, out = AG.Seen(), []
    for im in images:
        lk = A.Look(im)
        out.append(seen.new(lk))
        seen.add(lk)
    return out[1:]


rnd = random.Random(9)
NOT_NEW = {
    "a jump on the spot, again and again": [scene(230)] + [scene(230, jump=18 + rnd.randint(-4, 4)) for _ in range(10)],
    "...looked at anywhere in the jump": [scene(230)] + [scene(230, jump=rnd.choice([0, 5, 12, 20, 24])) for _ in range(10)],
    "a cursor moving in a menu": [menu(k % 5) for k in range(10)],
    "words blinking": [title(k % 2 == 0) for k in range(8)],
    "an enemy going by": [scene(230, enemy=330 - 12 * k) for k in range(10)],
    "water moving": [scene(230, water=k) for k in range(10)],
    "nothing moving": [scene(284)] * 6,
}
NEW = {
    "walking (60 pixels a time)": [scene(100 + 60 * k) for k in range(8)],
    "a step at a time (12 pixels)": [scene(100 + 12 * k) for k in range(10)],
    "pages of words": [dialog(i) for i in range(8)],
}
for name, looks in NOT_NEW.items():
    got = news(looks)
    check(f"not new: {name} (at most {max(got) * 100:.1f}% of it new)", max(got) < AG.NEW_SHARE)
for name, looks in NEW.items():
    got = news(looks)
    check(f"new: {name} (at least {min(got) * 100:.1f}% of it new)", min(got) >= AG.NEW_SHARE)
got = news([menu(0), menu(1), menu(0, ("Easy", "Normal", "Hard"))])
check(f"new: another menu ({got[-1] * 100:.1f}%), not the cursor moving ({got[0] * 100:.1f}%)",
      got[-1] >= AG.NEW_SHARE > got[0])
got = news([scene(100 + 60 * k) for k in range(5)] + [scene(100 + 60 * k) for k in range(4, -1, -1)])
check(f"walking back the way it came: not new ({[round(x * 100, 1) for x in got[4:]]}%)", max(got[4:]) < AG.NEW_SHARE
      and min(got[:4]) >= AG.NEW_SHARE)
seen = AG.Seen()
lk = A.Look(scene(200))
for k in range(AG.SEEN_MOST + 20):
    seen.add(A.Look(scene(100 + k)) if k < 30 else lk)
t0 = time.perf_counter()
for _ in range(20):
    seen.new(lk)
took = (time.perf_counter() - t0) / 20 * 1000
check(f"...{seen.n} looks kept at most ({AG.SEEN_MOST}), the oldest going; a look weighed against them in {took:.1f} ms",
      seen.n == AG.SEEN_MOST and took < 30)


# ---- a player that keeps jumping where it gets nowhere ---------------------------------------------------------------
class World:
    """You're up against a ledge too high to jump onto, with a crate beside you: jumping gets you nowhere, walking
    right neither; B picks the crate up (and that's new)."""

    def __init__(self, x=284):
        self.x, self.air, self.carry = x, 0, False

    def render(self):
        im = scene(self.x, jump=self.air, carry=self.carry, crate_at=None if self.carry else 262)
        self.air = 0                                # (landed by the next look)
        return im

    def act(self, buttons):
        if "a" in buttons:
            self.air = rnd.randint(16, 22)
        elif buttons == {"b"}:
            self.carry = True
        elif "left" in buttons:
            self.x -= 30


class Done(Exception):
    pass


class FakeIO:
    def __init__(self, world, pick, most=60):
        self.world, self.pick, self.most = world, pick, most
        self.asked, self.logged, self.statuses, self.held = [], [], [], set()
        self.blind, self.last_by = False, "model"

    def look(self):
        return A.Look(self.world.render())

    def decide(self, kind, says, state, choices, fallback, picture=None):
        if len(self.asked) >= self.most:
            raise Done()
        self.asked.append((state, dict(choices)))
        return self.pick(state, choices)

    def status(self, w):
        self.statuses.append(w)

    def log(self, **e):
        self.logged.append(e)

    def tap(self, b):
        self.world.act({b})

    def hold(self, b):
        self.held.add(b)

    def stick(self, axis, v):
        pass

    def wait(self, secs):
        pass

    def let_go(self):
        if self.held:
            self.world.act(set(self.held))
        self.held = set()


class FakeCoach:
    def __init__(self):
        self.started, self.seen, self.nudges = None, [], 0
        self.advice, self.tips, self.known = None, "", ""

    def start(self, *a):
        self.started = a

    def see(self, look, story):
        self.seen.append((look, story))

    def nudge(self):
        self.nudges += 1

    def controls(self):
        return (self.advice or {}).get("controls") or self.known


def jumper(state, choices):
    """A decision model that jumps toward the ledge whenever it can; once jumping's off its list, presses a button
    it's told it hasn't tried (B: it picks the crate up), then walks off with it."""
    if "right_a" in choices:
        return "right_a"
    last = (state.get("you did last, oldest first") or [""])[-1]
    if last.startswith("Press B"):
        return "left_held"
    if "haven't tried here: B" in state.get("note", ""):
        return "b"
    return "right_held"


world, coach = World(), FakeCoach()
fio = FakeIO(world, jumper, most=14)
player = AG.AnyGame({"title": "Shrek 2 (USA)", "system": "gba"}, fio, coach)
try:
    player.play()
except Done:
    pass
came = [s.get("you did last, oldest first", [""])[-1] for s, _ in fio.asked]
check(f"keeps jumping against the ledge: the screen changes, but nothing new comes of it ({came[1:3]}...)",
      all(c == "Right and A together: nothing new" for c in came[1:9]))
stuck = [e for e in fio.logged if str(e.get("event", "")).startswith("Stuck")]
check(f"...after {AG.STUCK_AFTER} moves, it's stuck ({stuck[:1]})", stuck and stuck[0]["event"] ==
      f"Stuck: {AG.STUCK_AFTER} moves with nothing new, mostly A (on its own and on the move): that's off its list for "
      f"{AG.OFF_FOR} picks")
state9, choices9 = fio.asked[AG.STUCK_AFTER]
check(f"...jumping's off its list ({sorted(k for k in player.moves if k not in choices9)})",
      {"a", "left_a", "right_a"}.isdisjoint(choices9) and "b" in choices9 and "right_held" in choices9
      and {"a", "left_a", "right_a"} <= set(fio.asked[AG.STUCK_AFTER - 1][1]))
check(f"...and it's told so, and which buttons it hasn't tried ({state9.get('note')!r})",
      f"Your last {AG.STUCK_AFTER} moves got you nowhere" in state9.get("note", "")
      and "Off your list for now, as they got you nowhere: Press A, Left and A together, Right and A together." in
      state9.get("note", "") and "Buttons you haven't tried here: B, L, R, Select." in state9.get("note", ""))
check(f"...the coach is asked to look again ({coach.nudges} nudge), and told how it's going: "
      f"{ {k: v for k, v in coach.seen[AG.STUCK_AFTER][1].items() if k != 'moves'} }",
      coach.nudges == 1 and coach.seen[AG.STUCK_AFTER][1]["stuck"] and coach.seen[AG.STUCK_AFTER][1]["mostly"] ==
      "A (on its own and on the move)" and coach.seen[AG.STUCK_AFTER][1]["untried"] == ["B", "L", "R", "Select"]
      and coach.seen[AG.STUCK_AFTER][1]["off"] == ["Press A", "Left and A together", "Right and A together"])
picks = [s.get("you did last, oldest first", [""])[-1] for s, _ in fio.asked]
k = next(i for i, w in enumerate(picks) if w.startswith("Left, held a second"))
after, choices_after = fio.asked[k]
check(f"...so it tries B, which picks the crate up ({picks[AG.STUCK_AFTER + 1]!r}: a small change, not somewhere new), "
      f"and walks off with it: something new ({picks[k]!r})", picks[AG.STUCK_AFTER + 1].startswith("Press B: ")
      and picks[k] == "Left, held a second: something new")
check(f"...not stuck now, and jumping's back on its list ({after.get('note')!r}, {coach.seen[k][1]['stale']} moves "
      f"with nothing new)", "note" not in after and "right_a" in choices_after and coach.seen[k][1]["stale"] == 0)
check(f"...the coach was started with the game, its system and its buttons ({coach.started})",
      coach.started == ("Shrek 2", "Game Boy Advance", "A, B, L, R, Start, Select and the d-pad (Up, Down, Left, "
                                                       "Right)"))
coach.advice = {"screen": "A ledge.", "goal": "Get onto the ledge", "plan": "Pick up the crate with B.",
                "controls": "A jumps; B picks things up."}
coach.tips = "Stack crates to climb."
st = player.state(None)
check(f"...the coach's goal, plan and what it's worked out about the controls, and your tips, go with each pick "
      f"({ {k: st.get(k) for k in ('goal', 'plan', 'controls', 'tips')} })",
      st.get("goal") == "Get onto the ledge" and st.get("plan") == "Pick up the crate with B." and
      st.get("controls") == "A jumps; B picks things up." and st.get("tips") == "Stack crates to climb.")
check(f"...and the game's menu says its goal ({player.doing('Press A')!r})", player.doing("Press A") ==
      "Goal: Get onto the ledge")
coach.advice, coach.known = None, "B throws."
check(f"...before it's said anything: the controls worked out before ({player.state(None).get('controls')!r})",
      player.state(None).get("controls") == "B throws." and "goal" not in player.state(None))
check("...and with no coach, none of that", "goal" not in AG.AnyGame({"title": "x", "system": "gba"}, fio).state(None))


def walker(state, choices):
    return "left_held"


fio2 = FakeIO(World(x=900), walker, most=12)
p2 = AG.AnyGame({"title": "x", "system": "gba"}, fio2, None)
try:
    p2.play()
except Done:
    pass
check(f"walking somewhere new each time: never stuck ({len(p2.stale)} moves with nothing new)",
      not any("Stuck" in str(e.get("event")) for e in fio2.logged) and "note" not in fio2.asked[-1][0])


def mixer(state, choices):
    return ["right", "l", "r", "select"][len(fio3.asked) % 4]


fio3 = FakeIO(World(), mixer, most=12)
p3 = AG.AnyGame({"title": "x", "system": "gba"}, fio3, None)
try:
    p3.play()
except Done:
    pass
ev = [e["event"] for e in fio3.logged if "Stuck" in str(e.get("event"))]
check(f"trying a bit of everything and getting nowhere: stuck, but nothing comes off its list ({ev})",
      ev == [f"Stuck: {AG.STUCK_AFTER} moves with nothing new"] and p3.off_left == 0)
kinds = AG.kinds_for("ps1")
check(f"a move's kind: its button, on its own or on the move ({kinds['right_cross']}, {kinds['cross']}), its direction "
      f"({kinds['up_held']})", kinds["right_cross"] == kinds["cross"] == "cross" and kinds["up_held"] == "up"
      and kinds["wait"] == "wait" and set(kinds) == set(AG.moves_for("ps1")))
p4 = AG.AnyGame({"title": "x", "system": "sms"}, fio, None)
check(f"...the buttons it hasn't tried: not the one that pauses ({p4.untried()})", p4.untried() == ["1", "2"])


# ---- a pretend Ollama: decision models, and models to talk to ----------------------------------------------------
class Fake:
    asked, said, script, lock = [], [], [], threading.Lock()
    answer = {"screen": "A brick ledge, too high to jump onto, with a crate beside you.",
              "goal": "Get onto the ledge", "plan": "Walk left to the crate, press B to pick it up, carry it right.",
              "controls": "A jumps; B picks things up."}
    slow, words = 0.0, None


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        with Fake.lock:
            (Fake.asked if self.path == "/v1/systemone" else Fake.said).append(dict(body, at=time.monotonic(),
                                                                                 path=self.path))
        model = body.get("model")
        if self.path == "/v1/systemone":
            crit = body["questions"]["pick"]["criteria"]
            with Fake.lock:
                pick = Fake.script.pop(0) if Fake.script else "wait"
            return self.reply(200, {"answers": {"pick": {"type": "choice", "choice": pick if pick in crit else "wait",
                                                         "confidence": 0.7}}})
        if self.path != "/api/generate":
            return self.reply(404, {"error": "not found"})
        if model == "missing":
            return self.reply(404, {"error": f"model '{model}' not found"})
        if model == "blindy" and body.get("images"):
            return self.reply(400, {"error": f"{model} does not support image input"})
        if model == "oldthink" and "think" in body:
            return self.reply(400, {"error": f'"{model}" does not support thinking: think value is not supported'})
        if model == "noformat" and "format" in body:
            return self.reply(400, {"error": "invalid format: expected \"json\" or a JSON schema"})
        if model == "broken":
            return self.reply(500, {"error": "llama runner process has terminated"})
        time.sleep(Fake.slow)
        if model == "chatty":
            text = "Walk left to the crate and press B to pick it up."
        elif model == "wrapped":
            text = "Sure! Here you go: " + json.dumps(Fake.answer) + " Have fun."
        elif model == "quiet":
            return self.reply(200, {"response": "", "thinking": "Hmm, let me think about this ledge..."})
        else:
            text = Fake.words if Fake.words is not None else json.dumps(Fake.answer)
        return self.reply(200, {"response": text, "done": True})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"127.0.0.1:{srv.server_address[1]}"
C.EVERY, C.GAP, C.RESTS = 1.5, 0.4, (0.6, 1.2)          # (quicker, for this)
NOTES = SAVES + "/Shrek 2.ai-notes.txt"
GBA = "A, B, L, R, Start, Select and the d-pad (Up, Down, Left, Right)"
look = A.Look(scene(284))
story = {"moves": ["Right and A together: nothing new"] * 3, "stale": 3, "stuck": False, "mostly": "", "off": [],
         "untried": ["L", "R"]}
logged, paused = [], [False]
co = C.Coach(SERVER, "gemma", NOTES, log=logged.append, paused=lambda: paused[0])
co.start("Shrek 2", "Game Boy Advance", GBA)
time.sleep(0.8)
check("the coach: nothing asked before the player's looked at the screen", not Fake.said)
co.see(look, story)
check("...it looks once the player has", until(lambda: co.advice is not None, 10))
q = Fake.said[0]
shot = Image.open(io.BytesIO(base64.b64decode(q["images"][0]))) if q.get("images") else None
check(f"...your Bot's model, shown the game's screen ({shot.size if shot else None}), asked for JSON in the shape "
      f"wanted (with what it knows of the game, as that's not known yet), with no reasoning first",
      q["model"] == "gemma" and shot is not None and shot.size == (240, 160) and q.get("format") == C.CARD_SCHEMA
      and q["format"]["properties"]["kind"]["enum"] == list(C.KINDS) and q.get("think") is False
      and q.get("stream") is False and C.ASK_CARD in q["prompt"])
check(f"...told what it's for, and to use what it knows of the game ({q['system'][:72]!r}...)", q["system"].startswith(
    "You coach a player that is playing Shrek 2 on the Game Boy Advance.") and "JSON" in q["system"]
      and "use what you know of it" in q["system"] and "never played" not in q["system"])
p = q["prompt"]
check("...the game, its buttons, the player's last moves and what came of them; the screen's attached",
      f"The game: Shrek 2, on the Game Boy Advance. Its buttons: {GBA}." in p
      and "- Right and A together: nothing new" in p and "The attached picture is the game's screen right now." in p
      and "stuck" not in p and C.ASK in p)
check(f"...its answer, kept: {co.advice}", co.advice == Fake.answer)
check(f"...the controls as it said them ({co.controls()!r})", co.controls() == "A jumps; B picks things up.")
txt = open(NOTES).read()
st = os.stat(NOTES)
check(f"...noted beside the game's saves for next time, yours to edit (owned like the folder, {oct(st.st_mode & 0o777)})",
      txt == C.NOTES_HEAD + "Tips: \nControls: A jumps; B picks things up.\nGoal: Get onto the ledge\n"
      and (st.st_uid, st.st_gid) == (os.stat(SAVES).st_uid, os.stat(SAVES).st_gid) and st.st_mode & 0o777 == 0o644
      and not [f for f in os.listdir(SAVES) if f.endswith(".part")])
entry = next(e for e in logged if e.get("kind") == "coach")
check(f"...and logged: what it saw and said, and how long it took ({sorted(entry)})",
      entry.get("goal") == "Get onto the ledge" and entry.get("saw") == "240x160" and isinstance(entry.get("ms"), int)
      and entry.get("plan") and not entry.get("stuck"))
n = len(Fake.said)
t0 = time.monotonic()
check("...and again every so often", until(lambda: len(Fake.said) > n, 6) and time.monotonic() - t0 > C.EVERY - 0.8)
p = Fake.said[-1]["prompt"]
check("...told what it said last time", "seconds ago: goal: Get onto the ledge; plan: Walk left to the crate" in p)

# stuck: asked again soon, and told what the player's been doing
until(lambda: True, 0.1)
n = len(Fake.said)
co.see(look, {"moves": ["Right and A together: nothing new"] * 8, "stale": 8, "stuck": True,
              "mostly": "A (on its own and on the move)", "off": ["Press A", "Left and A together",
                                                                   "Right and A together"],
              "untried": ["B", "L", "R", "Select"]})
t0 = time.monotonic()
co.nudge()
check("the player's stuck: the coach looks again soon", until(lambda: len(Fake.said) > n, 3)
      and time.monotonic() - t0 < C.EVERY)
p = Fake.said[-1]["prompt"]
check("...told it's stuck, doing what, what's off its list and the buttons it hasn't tried; asked for something "
      "different", "It's stuck: its last 8 moves got it nowhere (the screen keeps looking as it has before), doing "
      "mostly A (on its own and on the move)." in p and "Off its list for now: Press A, Left and A together, Right and"
      " A together." in p and "Buttons it hasn't tried here: B, L, R, Select." in p and C.STUCK_SAYS.strip() in p)
until(lambda: any(e.get("stuck") == 8 for e in logged if e.get("kind") == "coach"), 3)
check("...and its log says it was stuck", any(e.get("stuck") == 8 for e in logged if e.get("kind") == "coach"))

# your tips: added to the notes while it plays
time.sleep(0.2)
with open(NOTES, "w") as f:
    f.write(C.NOTES_HEAD + "Tips: R picks up crates.\nStack them to climb the ledge.\nControls: A jumps.\n"
            "Goal: Get onto the ledge\n")
co.see(look, story)
check(f"your tips, written in the notes as it plays: read straight away ({co.tips!r})",
      co.tips == "R picks up crates. Stack them to climb the ledge.")
n = len(Fake.said)
Fake.answer = dict(Fake.answer, controls="A jumps; R picks up crates.", goal="Stack crates by the ledge")
co.nudge()
check("...told to it, to trust", until(lambda: len(Fake.said) > n, 4) and
      "Tips from the person whose game it is (trust these): R picks up crates. Stack them to climb the ledge." in
      Fake.said[-1]["prompt"])
until(lambda: "Stack crates" in open(NOTES).read(), 3)
txt = open(NOTES).read()
check(f"...left as you wrote them, its own notes brought up to date ({txt.splitlines()[3:]})",
      "Tips: R picks up crates.\nStack them to climb the ledge.\nControls: A jumps; R picks up crates.\nGoal: Stack "
      "crates by the ledge\n" in txt)

# waits while the game's menu is up
paused[0] = True
time.sleep(0.5)
n = len(Fake.said)
co.nudge()
time.sleep(2.0)
check("the game's menu up: it doesn't look meanwhile", len(Fake.said) == n)
paused[0] = False
check("...back in the game: it does", until(lambda: len(Fake.said) > n, 3))
co.stop()
check("stopped: its thread ends", until(lambda: not co.thread.is_alive(), 3))

# what it knows of the game: said once, kept in the notes, not asked again
CARD_NOTES = SAVES + "/Kart.ai-notes.txt"
Fake.answer = dict(Fake.answer, kind="Kart racing", buttons="A: accelerate; B: brake; R: hop", how="Take the inside "
                   "line round bends.")
lgk = []
ck = C.Coach(SERVER, "gemma", CARD_NOTES, log=lgk.append)
ck.game, ck.system, ck.buttons = "Super Mario Kart", "SNES", "A, B, X, Y, L, R, Start, Select and the d-pad"
ck.think(look, story)
txt = open(CARD_NOTES).read()
check(f"what it knows of the game, said the first time: {ck.card()}", ck.card() == {
    "kind": "racing", "buttons": "A: accelerate; B: brake; R: hop", "how": "Take the inside line round bends."}
      and any("says it's a racing game" in str(e.get("event")) for e in lgk))
check(f"...kept in its notes ({txt.splitlines()[5:8]})", "Kind: racing\nButtons: A: accelerate; B: brake; R: hop\n"
      "How: Take the inside line round bends.\nControls: " in txt)
n = len(Fake.said)
ck2 = C.Coach(SERVER, "gemma", CARD_NOTES, log=lgk.append)
ck2.game, ck2.system, ck2.buttons = ck.game, ck.system, ck.buttons
ck2.think(look, story)
check(f"...next time, read from them ({ck2.card()['kind']}), and not asked again",
      ck2.card()["kind"] == "racing" and Fake.said[n].get("format") == C.SCHEMA and C.ASK_CARD not in
      Fake.said[n]["prompt"] and "Kind: racing" in Fake.said[n]["prompt"])
with open(CARD_NOTES, "w") as f:
    f.write(txt.replace("Kind: racing", "Kind: platformer") + "Watch out for the shells.\n")
check(f"...your Kind: line goes ({ck2.card()['kind'] if ck2.read_notes() is None else None}), and your tip after it's "
      f"kept ({ck2.tips!r})", ck2.card()["kind"] == "platformer" and ck2.tips == "Watch out for the shells.")
ck2.write_notes({"controls": "A goes", "goal": "Win the cup"}, {"kind": "racing"})
check("...its own lines brought up to date in place; your Kind: line, and your tip, as they were",
      open(CARD_NOTES).read().count("\nKind:") == 1 and "Kind: platformer" in open(CARD_NOTES).read()
      and "Controls: A goes" in open(CARD_NOTES).read()
      and open(CARD_NOTES).read().endswith("Goal: Win the cup\nWatch out for the shells.\n"))
MINE = SAVES + "/Hack.ai-notes.txt"                       # your own Buttons line, no Kind yet
open(MINE, "w").write("Buttons: B is jump in this hack, A runs\nWatch the spikes.\n")
ch = C.Coach(SERVER, "gemma", MINE, log=lgk.append)
ch.game, ch.system, ch.buttons = "Hack", "SNES", "A, B and the d-pad"
ch.think(look, story)
txt = open(MINE).read()
check(f"your own Buttons: line, with no Kind: yet: what it knows of the game's asked for, and added, but your line "
      f"kept ({txt.splitlines()[:3]})", "Buttons: B is jump in this hack, A runs" in txt and "Kind: racing" in txt
      and txt.count("Buttons:") == 1 and ch.card()["buttons"] == "B is jump in this hack, A runs")
open(MINE, "w").write(txt.replace("Kind: racing", "Kind: platformer") + "Jump the third gap early.\n")
ch.known["Kind"] = "racing"                               # (as it was when it started thinking)
ch.write_notes({"controls": "B jumps", "goal": "Reach the flag"}, {"kind": "racing", "buttons": "A: run"})
txt = open(MINE).read()
check(f"...changed while it thought (Kind: platformer, a new tip): kept, and read ({ch.card()['kind']}, "
      f"{ch.tips!r})", "Kind: platformer" in txt and "Kind: racing" not in txt and ch.card()["kind"] == "platformer"
      and "Jump the third gap early." in ch.tips and "Goal: Reach the flag" in txt)
Fake.answer = {k: v for k, v in Fake.answer.items() if k not in ("kind", "buttons", "how")}

# what it worked out before, next time
co2 = C.Coach(SERVER, "gemma", NOTES, log=logged.append)
check(f"next time: what it worked out before, from the notes ({co2.known}), and your tips ({co2.tips!r})",
      co2.known == {"Controls": "A jumps; R picks up crates.", "Goal": "Stack crates by the ledge"}
      and co2.tips.startswith("R picks up crates.") and co2.controls() == "A jumps; R picks up crates.")
co2.start("Shrek 2", "Game Boy Advance", GBA)
co2.see(look, story)
check("...told to it", until(lambda: co2.advice is not None, 6) and "Worked out in earlier games: Controls: A jumps; R "
      "picks up crates. Goal: Stack crates by the ledge" in Fake.said[-1]["prompt"])
co2.stop()
nomodel = C.Coach(SERVER, "", NOTES)
nomodel.start("Shrek 2", "Game Boy Advance", GBA)
nomodel.see(look, story)
check(f"no Bot model: it doesn't think, but your tips and what was worked out before still count ({nomodel.controls()!r})",
      nomodel.thread is None and nomodel.tips.startswith("R picks up") and nomodel.controls() == "A jumps; R picks "
      "up crates.")
open(SAVES + "/free.ai-notes.txt", "w").write("Hold B to run. The exit's on the right.\n")
free = C.Coach(SERVER, "", SAVES + "/free.ai-notes.txt")
check(f"...tips written without Tips: in front are tips too ({free.tips!r})", free.tips == "Hold B to run. The exit's on "
      "the right." and free.known == {})


def one(model, notes=None, story_=story, see=True):
    """A coach with that model, asked once: (it, its log)."""
    lg = []
    c = C.Coach(SERVER, model, notes or SAVES + f"/{model}.ai-notes.txt", log=lg.append)
    c.game, c.system, c.buttons = "Shrek 2", "Game Boy Advance", GBA
    ok = c.think(look if see else None, story_)
    return c, lg, ok


Fake.answer = {"screen": "A ledge.", "goal": "Get onto the ledge", "plan": "Pick up the crate with B.",
               "controls": "A jumps."}
n = len(Fake.said)
c, lg, ok = one("blindy")
check(f"a model that can't look at pictures: asked again without the screen, and told so ({c.advice and c.advice['goal']})",
      ok and c.blind and Fake.said[n].get("images") and not Fake.said[n + 1].get("images")
      and "You can't see the screen this time" in Fake.said[n + 1]["prompt"]
      and any("blindy can't look at pictures" in str(e.get("event")) for e in lg))
n = len(Fake.said)
c.think(look, story)
check("...and never shown it again", not Fake.said[n].get("images"))
n = len(Fake.said)
c, lg, ok = one("oldthink")
check("a model that doesn't reason: asked again without saying not to", ok and "think" in Fake.said[n]
      and "think" not in Fake.said[n + 1] and c.advice["goal"] == "Get onto the ledge")
n = len(Fake.said)
c, lg, ok = one("noformat")
check("an older Ollama (no JSON shapes): asked again without", ok and "format" in Fake.said[n]
      and "format" not in Fake.said[n + 1] and c.advice["goal"] == "Get onto the ledge")
c, lg, ok = one("chatty")
check(f"an answer in words, not JSON: taken as the plan ({c.advice})", ok and c.advice ==
      {"screen": "", "goal": "", "plan": "Walk left to the crate and press B to pick it up.", "controls": ""})
c, lg, ok = one("wrapped")
check("JSON among other words: found", ok and c.advice["goal"] == "Get onto the ledge")
c, lg, ok = one("quiet")
check(f"only reasoning, no answer: it says so ({lg[-1].get('error')!r})", not ok and c.advice is None
      and lg[-1].get("error") == "quiet didn't say what to do")
c, lg, ok = one("missing")
check(f"no such model: it says so ({lg[-1].get('error')!r})", not ok and lg[-1].get("error") ==
      "That computer doesn't have missing")
Fake.words = json.dumps({"Goal": "**Climb** the ledge", "plan": ["Press B,", "then walk right."], "screen": None,
                         "controls": "x" * 900})
c, lg, ok = one("gemma")
check(f"...its answer made plain: no markdown, lists joined, long ones cut ({c.advice['goal']!r}, {c.advice['plan']!r}, "
      f"{len(c.advice['controls'])} characters)", ok and c.advice["goal"] == "Climb the ledge"
      and c.advice["plan"] == "Press B, then walk right." and c.advice["screen"] == ""
      and len(c.advice["controls"]) <= C.SAYS_MOST + 1)
Fake.words = json.dumps({"screen": "Nothing much.", "goal": "", "plan": ""})
c, lg, ok = one("gemma")
check("...an answer with no goal or plan: not taken", not ok and c.advice is None)
Fake.words = None
c, lg, ok = one("gemma", notes=S + "/no/such/folder/x.ai-notes.txt")
check(f"its notes can't be kept: it says so once, and coaches on ({[e.get('event') for e in lg if e.get('event')]})",
      ok and c.advice is not None and any("Couldn't keep its notes" in str(e.get("event")) for e in lg))

# your notes, as you'd write them: every line of yours kept, only its two lines changed
def rewrite(name, text, answer={"controls": "A jumps; B grabs", "goal": "Cross the bridge"}):
    p = SAVES + f"/{name}.ai-notes.txt"
    open(p, "w").write(text)
    C.Coach(SERVER, "", p).write_notes(answer)
    return p, open(p).read()


p, after = rewrite("end", C.NOTES_HEAD + "Tips: Press B to run\nControls: A jumps\nGoal: Find the key\n"
                                  "The key is under the bridge\n")
check("your notes: a tip added after its Goal line, kept", after == C.NOTES_HEAD + "Tips: Press B to run\n"
      "Controls: A jumps; B grabs\nGoal: Cross the bridge\nThe key is under the bridge\n"
      and C.Coach(SERVER, "", p).tips == "Press B to run The key is under the bridge")
p, after = rewrite("two", "Tips: Press B to run\nGoal: x\nTips: avoid the spikes\n# a note to myself\n")
check("...a second Tips line and your own # lines, kept", after == "Tips: Press B to run\nGoal: Cross the bridge\n"
      "Tips: avoid the spikes\n# a note to myself\nControls: A jumps; B grabs\n"
      and C.Coach(SERVER, "", p).tips == "Press B to run avoid the spikes")
p, after = rewrite("free", "Hold right to run.\nTips: jump on the box\n")
check("...words before a Tips line, kept", after.startswith("Hold right to run.\nTips: jump on the box\n")
      and C.Coach(SERVER, "", p).tips == "Hold right to run. jump on the box")
walk = "\n".join(f"Step {i}: go left, then jump twice ({'x' * 60})" for i in range(1100))
p, after = rewrite("walk", "Tips: read this first\n" + walk + "\nGoal: old\n")
check(f"...a long walkthrough ({len(after) // 1024} KB): all of it kept, what it's told of it cut short",
      walk in after and "Goal: Cross the bridge" in after and len(C.Coach(SERVER, "", p).tips) == C.TIPS_MOST)
big = SAVES + "/big.ai-notes.txt"
open(big, "w").write("Tips: " + "y" * (C.NOTES_MOST + 10) + "\nGoal: old\n")
before = open(big).read()
C.Coach(SERVER, "", big).write_notes({"controls": "c", "goal": "new"})
check("...a file too big to read whole: left as it is", open(big).read() == before)
open(SAVES + "/raw.ai-notes.txt", "wb").write(b"Tips: caf\xe9 \xff\nGoal: old\n")
C.Coach(SERVER, "", SAVES + "/raw.ai-notes.txt").write_notes({"controls": "c", "goal": "new"})
check("...bytes in it that aren't UTF-8: kept as they were", open(SAVES + "/raw.ai-notes.txt", "rb").read() ==
      b"Tips: caf\xe9 \xff\nGoal: new\nControls: c\n" and not [f for f in os.listdir(SAVES) if f.endswith(".part")])

# odd answers
Fake.words = '{"screen": "x", "goal": "Go \\ud83c up", "plan": "y", "controls": "z"}'
c, lg, ok = one("gemma", notes=SAVES + "/odd.ai-notes.txt")
check(f"a stray half of a character in its answer: a ? ({c.advice and c.advice['goal']!r}), its notes kept, and the "
      "log still written", ok and c.advice["goal"] == "Go ? up" and "Goal: Go ? up" in
      open(SAVES + "/odd.ai-notes.txt").read())
lg2 = []
glog = A.GameAI(None, SERVER, "clef", SAVES + "/odd.ai.log")
glog.log({"state": {"goal": "Go \ud83c up"}})
check("...the AI player's log takes one too (a ?)", '"Go ? up"' in open(SAVES + "/odd.ai.log").read())
Fake.words = json.dumps("Walk left to the crate.")
c, lg, ok = one("gemma")
check(f"a sentence in quotes: the plan ({c.advice})", ok and c.advice["plan"] == "Walk left to the crate.")
Fake.words = '{"screen": "A ledge.", "goal": "Get onto the ledge", "plan": "Walk left to the cra'
c, lg, ok = one("gemma")
check(f"JSON cut short (it ran out of room): what's there of it ({c.advice})", ok and c.advice["goal"] ==
      "Get onto the ledge" and c.advice["plan"] == "Walk left to the cra")
Fake.words = '{"screen": "A led'
c, lg, ok = one("gemma")
check("...cut short before a goal or plan: not taken", not ok and c.advice is None)
Fake.words = None

# turned off while it thinks: its answer's not wanted then
Fake.slow = 2.0
lgz = []
z = C.Coach(SERVER, "gemma", SAVES + "/zombie.ai-notes.txt", log=lgz.append)
z.start("Shrek 2", "Game Boy Advance", GBA)
n = len(Fake.said)
z.see(look, story)
until(lambda: len(Fake.said) > n, 5)
z.stop()
time.sleep(Fake.slow + 1.0)
check("turned off while it thinks: its answer's not kept, noted or logged", z.advice is None and not
      os.path.exists(SAVES + "/zombie.ai-notes.txt") and not lgz and not z.thread.is_alive())
Fake.slow = 0.0

# it fails: it rests, a while, then longer
lg = []
dead = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
deadsrv = f"127.0.0.1:{dead.server_address[1]}"
dead.server_close()
cd = C.Coach(deadsrv, "gemma", SAVES + "/dead.ai-notes.txt", log=lg.append)
stuck_on = threading.Event()


def nudger():                                   # (the player stuck all along: the coach would look as soon as it may)
    while not stuck_on.is_set():
        cd.nudge()
        time.sleep(0.05)


cd.start("Shrek 2", "Game Boy Advance", GBA)
cd.see(look, story)
threading.Thread(target=nudger, daemon=True).start()
times = []
for k in range(1, 5):
    until(lambda: len([e for e in lg if e.get("error")]) >= k, 6)
    times.append(time.monotonic())
stuck_on.set()
errs = [e for e in lg if e.get("error")]
gaps = [round(b - a, 2) for a, b in zip(times, times[1:])]
check(f"no computer there: it says so ({errs[0]['error']!r}), and rests before trying again, even when the player's "
      f"stuck ({gaps} s apart)", "Can't reach" in errs[0]["error"] and C.RESTS[0] - 0.2 <= gaps[0] < C.RESTS[1] - 0.2
      and C.RESTS[0] - 0.2 <= gaps[1] < C.RESTS[1] - 0.2)
check(f"...after {C.FAILS_LONG} in a row, longer ({gaps[2]} s)", gaps[2] >= C.RESTS[1] - 0.2)
cd.stop()
check("...no notes made for a game it never coached", not os.path.exists(SAVES + "/dead.ai-notes.txt"))

# ---- with the real emulator: the decision model plays, the coach coaches, the game never waits -------------------
C.EVERY, C.GAP = 30.0, 3.0
run = GM.GameRun({"path": GAMES + "/nestest.nes", "title": "nestest (World)", "system": "nes"})
run.start(GM.find_core("nes"), resume=False)
check("an NES game plays", run.wait_started(15))
Fake.asked.clear(); Fake.said.clear()
Fake.script[:] = ["start", "right_held", "a", "down"] * 10
Fake.slow = 3.0
Fake.answer = {"screen": "A test screen with a list of tests.", "goal": "Run the tests",
               "plan": "Press Start to run them all.", "controls": "Start runs; Up and Down pick."}
LOG, NOTES2 = SAVES + "/nestest.ai.log", SAVES + "/nestest.ai-notes.txt"
ai = A.GameAI(run, SERVER, "clef", LOG, coach="gemma", notes_path=NOTES2)
ai.start()
check("the coach asked, with the game's screen", until(lambda: Fake.said, 20) and Fake.said[0].get("images")
      and Image.open(io.BytesIO(base64.b64decode(Fake.said[0]["images"][0]))).size in ((256, 240), (256, 224))
      and "playing nestest on the NES" in Fake.said[0]["system"])
t0 = Fake.said[0]["at"]
check("...while it thinks, the decision model goes on picking (the game never waits for the coach)",
      until(lambda: len([a for a in Fake.asked if t0 < a["at"] < t0 + Fake.slow]) >= 2, 10) and run.state == "on")
check("...its answer comes", until(lambda: ai.coach.advice is not None, 10))
n = len(Fake.asked)
until(lambda: len(Fake.asked) > n + 1, 15)
st = Fake.asked[-1]["state"]
check(f"...and the decision model's told its goal, plan and the controls ({ {k: st.get(k) for k in ('goal', 'plan', 'controls')} })",
      st.get("goal") == "Run the tests" and st.get("plan") == "Press Start to run them all."
      and st.get("controls") == "Start runs; Up and Down pick.")
check(f"...the game's menu says the goal ({ai.status!r})", until(lambda: ai.status == "Goal: Run the tests", 10))
ai.stop()
check("turned off: the player and the coach stop", until(lambda: not ai.thread.is_alive(), 8)
      and until(lambda: not ai.coach.thread.is_alive(), 5))
lines = [json.loads(x) for x in open(LOG).read().splitlines()]
check(f"its log: started with both ({lines[0].get('event')!r}), the coach's answers, each pick",
      lines[0].get("event") == "Started, with clef, looking at the screen, and gemma coaching it"
      and any(x.get("kind") == "coach" and x.get("goal") == "Run the tests" for x in lines)
      and any(x.get("kind") == "move" for x in lines))
check(f"...its notes beside the game's saves ({os.path.basename(NOTES2)})", "Goal: Run the tests" in open(NOTES2).read())
Fake.slow = 0.0

run.quit()

# Pokémon Emerald's own player: no coach (it reads the game's memory)
import struct
rom = bytearray(0x100000)                     # a cartridge that says it's Emerald: it loops where it starts
rom[0:4] = struct.pack("<I", 0xEA00002E)      # (b 0x080000C0)
rom[0xA0:0xAC] = b"POKEMON EMER"
rom[0xAC:0xB0] = b"BPEE"
rom[0xC0:0xC4] = struct.pack("<I", 0xEAFFFFFE)   # (b .)
open(GAMES + "/Emerald.gba", "wb").write(bytes(rom))
run = GM.GameRun({"path": GAMES + "/Emerald.gba", "title": "Emerald", "system": "gba"})
run.start(GM.find_core("gba"), resume=False)
check("Emerald plays", run.wait_started(15))
Fake.said.clear()
ai = A.GameAI(run, SERVER, "clef", SAVES + "/Emerald.ai.log", coach="gemma", notes_path=SAVES + "/Emerald.ai-notes.txt")
ai.start()
time.sleep(4)
first = open(SAVES + "/Emerald.ai.log").readline()
check(f"Pokémon Emerald's own player: no coach ({json.loads(first).get('event')!r})", ai.coach is None and not Fake.said
      and "coaching" not in first and ai.alive())
ai.stop()
until(lambda: not ai.thread.is_alive(), 8)
run.quit()


# ---- from the game's menu: your Bot's model coaches -------------------------------------------------------------------
class FB:
    def __init__(self):
        self.w, self.h, self.last = 640, 480, None

    def show(self, img):
        self.last = img

    def invalidate(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
m.view = "home"
apps = [a for a, _ in m.home_apps()]
m.home_sel = apps.index("Games")
m.press("a")
rows = m.tab_items()
m.sels[m.tab] = [r["title"] for r in rows].index("nestest")
m.press("a")
check("an NES game, from the Games tab", until(lambda: m.game is not None and m.game.state == "on", 15))
m.game_home()
until(lambda: m.view == "gamemenu", 3)
jobs = [j for j, _ in m.game_menu_items()]
m.game_menu["sel"] = jobs.index("ai")
m.snake_server = lambda: SERVER
m.friend.conf = {"server": SERVER, "model": "gemma"}
m.brain.models, m.brain.models_for, m.brain.models_at = ["clef", "d3"], SERVER, time.monotonic()
m.toast = lambda text, secs=3: None
Fake.said.clear()
Fake.script[:] = []
m.press("right")
check(f"AI player on: your Bot's model ({m.game_ai.coach_model}) coaches the decision model ({m.game_value('ai')}), its "
      f"notes beside the game's saves ({os.path.basename(m.game_ai.notes_path)})",
      m.game_ai.coach_model == "gemma" and m.game_value("ai") == "clef"
      and m.game_ai.notes_path == SAVES + "/nestest.ai-notes.txt")
m.press("b")
check("...back in the game, it coaches", until(lambda: Fake.said, 15) and Fake.said[-1]["model"] == "gemma")
m.game_end()
check("quitting the game stops it", m.game_ai is None)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
