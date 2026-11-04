"""The AI player for any game (pitato/anygame.py, pitato/gameai.py, pitato/emulator.py's shot): the game's picture
as the game made it (out of the rows the screen was given: exact, for 16- and 32-bit screens, and smaller when it's
big), from the real emulators (NES, SNES, Game Boy, Game Boy Advance); shown to a pretend decision model that can
see (Ollama's /v1/systemone, its images), which picks moves that reach the game as buttons; told what it did and
whether the screen changed; a model that can't see is asked again without the screen, and told so from then on; the
game goes on while the model thinks; Pokémon Emerald's player shows it the screen too; every game's menu has AI
player; each system's buttons (a PlayStation's Cross, an N64's stick)."""
import base64, io, json, os, shutil, struct, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import anygame as AG, bot as B, emulator as EMU, gameai as A, games as GM
from PIL import Image

S = SP + "/tanygame"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/Saves")
os.makedirs(S + "/bin")
for rom in ("nestest.nes", "HelloWorld.sfc", "arm.gba", "cpu_instrs.gb"):
    shutil.copy(SP + "/roms/" + rom, S + "/home/u/Games/" + rom)
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


# ---- the game's picture, out of the rows the screen was given: exact --------------------------------------------
def screen_on(path, w, h, bits):
    open(path, "wb").write(bytes(w * h * bits // 8))
    os.environ["PITATO_FB"] = f"{path}:{w}x{h}:{bits}"
    try:
        return EMU.Screen()
    finally:
        os.environ["PITATO_FB"] = FBF + ":640x480:16"


rng = np.random.default_rng(5)
scr = screen_on(S + "/fb16.bin", 640, 480, 16)
check("before the game's drawn anything: no picture", scr.shot(S + "/s.ppm") is False)
frame = rng.integers(0, 65536, size=(224, 256), dtype=np.uint16)
scr.show(frame, EMU.FMT_RGB565, 256 / 224)
check("a frame: its picture", scr.shot(S + "/s.ppm"))
got = np.asarray(Image.open(S + "/s.ppm"))
want = np.stack([((frame >> 11) & 31) << 3, ((frame >> 5) & 63) << 2, (frame & 31) << 3], -1).astype(np.uint8)
check(f"...as the game made it ({got.shape[1]}x{got.shape[0]}), every pixel (a 16-bit screen)",
      got.shape == (224, 256, 3) and np.array_equal(got, want))
scr.close()
scr = screen_on(S + "/fb32.bin", 640, 480, 32)
frame = rng.integers(0, 1 << 24, size=(160, 240), dtype=np.uint32)
scr.show(frame, EMU.FMT_XRGB8888, 1.5)
scr.shot(S + "/s.ppm")
got = np.asarray(Image.open(S + "/s.ppm"))
want = np.stack([(frame >> 16) & 255, (frame >> 8) & 255, frame & 255], -1).astype(np.uint8)
check(f"...a 32-bit screen too ({got.shape[1]}x{got.shape[0]})", got.shape == (160, 240, 3) and np.array_equal(got, want))
scr.mode = "Sharp"
frame2 = rng.integers(0, 1 << 24, size=(144, 160), dtype=np.uint32)
scr.show(frame2, EMU.FMT_XRGB8888, 160 / 144)
scr.shot(S + "/s.ppm")
got = np.asarray(Image.open(S + "/s.ppm"))
want = np.stack([(frame2 >> 16) & 255, (frame2 >> 8) & 255, frame2 & 255], -1).astype(np.uint8)
check(f"...Sharp (whole pixels), a new size ({got.shape[1]}x{got.shape[0]})", np.array_equal(got, want))
scr.mode = "Fit"
big = rng.integers(0, 1 << 24, size=(960, 1280), dtype=np.uint32)
scr.show(big, EMU.FMT_XRGB8888, 4 / 3)
scr.shot(S + "/s.ppm")
got = Image.open(S + "/s.ppm")
check(f"...a picture bigger than the screen: as it is on it ({got.size})", got.size == (640, 480))
scr.shot(S + "/s.ppm", most=320)
check(f"...and no more than so many pixels across ({Image.open(S + '/s.ppm').size})",
      Image.open(S + "/s.ppm").size == (320, 240))
rounds = []
for _ in range(3):                                     # (the best of three: this machine busy a moment isn't it)
    t0 = time.perf_counter()
    for _ in range(20):
        scr.shot(S + "/s.ppm")
    rounds.append((time.perf_counter() - t0) / 20 * 1000)
took = min(rounds)
check(f"...quick, between frames ({took:.1f} ms)", took < 15)
scr.close()

# ---- a pretend Ollama with decision models: clef can see, d3 can't ----------------------------------------------
class Fake:
    asked, script, blind, slow, lock = [], [], {"d3"}, 0.0, threading.Lock()


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

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path != "/v1/systemone":
            return self.answer(404, {"error": "not found"})
        with Fake.lock:
            Fake.asked.append(dict(body, at=time.monotonic()))
        if body.get("images") and body.get("model") in Fake.blind:
            return self.answer(400, {"error": f"{body['model']} does not support image input"})
        if body.get("model") == "broken":
            return self.answer(400, {"error": "scoring failed"})
        time.sleep(Fake.slow)
        crit = body["questions"]["pick"]["criteria"]
        with Fake.lock:
            pick = Fake.script.pop(0) if Fake.script else "wait"
        return self.answer(200, {"answers": {"pick": {"type": "choice", "choice": pick if pick in crit else "wait",
                                                      "confidence": 0.7}}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"127.0.0.1:{srv.server_address[1]}"

# what the decision call says when it can't see
try:
    B.ollama_decide(SERVER, "d3", "x", "pick", {"a": "A", "b": "B"}, 5, images=["aGk="])
    check("a model that can't see, shown a picture: CantSee", False)
except B.CantSee as ex:
    check(f"a model that can't see, shown a picture: CantSee ({ex})", str(ex) == "d3 can't see pictures")
try:
    B.ollama_decide(SERVER, "broken", "x", "pick", {"a": "A", "b": "B"}, 5, images=["aGk="])
    check("...another failure, with a picture: not CantSee", False)
except B.CantSee:
    check("...another failure, with a picture: not CantSee", False)
except ValueError as ex:
    check(f"...another failure, with a picture: not CantSee ({ex})", "couldn't decide" in str(ex))
Fake.asked.clear()
check("...and one that can, shown it: a pick", B.ollama_decide(SERVER, "clef", "x", "pick", {"a": "A", "wait": "W"}, 5,
                                                              images=["aGk="])[0] == "wait"
      and Fake.asked[-1]["images"] == ["aGk="])

# ---- the real emulators' pictures ---------------------------------------------------------------------------------
class Owner:                                  # (what GameIO needs of the AI player)
    def __init__(self, run, model="clef"):
        self.run, self.stopping, self.statuses, self.logged = run, threading.Event(), [], []
        self.server, self.model, self.offline = SERVER, model, False

    def set_status(self, w):
        self.statuses.append(w)

    def log(self, e):
        self.logged.append(e)


sizes = {}
for rom, sysk in (("nestest.nes", "nes"), ("HelloWorld.sfc", "snes"), ("cpu_instrs.gb", "gb"), ("arm.gba", "gba")):
    run = GM.GameRun({"path": GAMES + "/" + rom, "title": os.path.splitext(rom)[0], "system": sysk})
    run.start(GM.find_core(sysk), resume=False)
    if not run.wait_started(15):
        check(f"{rom} plays", False)
        continue
    time.sleep(1.5)
    io_ = A.GameIO(Owner(run), None)
    look = io_.look()
    raw = Image.open(io_.shot_path) if look else None
    png = Image.open(io.BytesIO(base64.b64decode(look.data))) if look else None
    sizes[sysk] = look.size if look else None
    lit = sum(1 for p in raw.convert("L").getdata() if p > 40) if raw else 0
    check(f"{sysk}: the game's picture ({look.size if look else None}, {lit} lit pixels), shown to the model as a PNG "
          f"({png.format if png else None}, {len(look.data) if look else 0} characters)",
          look is not None and png.format == "PNG" and png.size == look.size and lit > 50
          and np.array_equal(np.asarray(png.convert("RGB")), np.asarray(raw.convert("RGB"))))
    io_.close()
    check(f"...its file gone when it's done", not os.path.exists(io_.shot_path))
    run.quit()
check(f"...each the size the game made it: {sizes}", sizes.get("gba") == (240, 160) and sizes.get("gb") == (160, 144)
      and sizes.get("snes") == (256, 224) and sizes.get("nes") in ((256, 240), (256, 224)))

# ---- playing: the model looks and picks; its picks reach the game ---------------------------------------------------
run = GM.GameRun({"path": GAMES + "/nestest.nes", "title": "nestest (World)", "system": "nes"})
run.start(GM.find_core("nes"), resume=False)
check("an NES game plays", run.wait_started(15))
until(lambda: run.ask(f"shot {S}/first.ppm", ("shot",), 1.5) == ("shot", "ok"), 15)   # (its first picture drawn)
sent = []
real_press, real_release, real_stick = run.press, run.release, run.stick
run.press = lambda name, port=0: (sent.append(("down", name, time.monotonic())), real_press(name, port))
run.release = lambda name, port=0: (sent.append(("up", name, time.monotonic())), real_release(name, port))
Fake.asked.clear()
Fake.script[:] = ["start", "right_held", "right_a", "down", "a"]
Fake.slow = 1.0
log = S + "/nes.ai.log"
ai = A.GameAI(run, SERVER, "clef", log)
ai.start()
check("it asks the model, again and again", until(lambda: len(Fake.asked) >= 6, 30))
first = Fake.asked[0]
st, crit = first["state"], first["questions"]["pick"]["criteria"]
shot = Image.open(io.BytesIO(base64.b64decode(first["images"][0])))
check(f"...shown the game's screen ({shot.size}), and told it's attached ({st.get('screen')!r})",
      len(first["images"]) == 1 and shot.size == sizes.get("nes") and st.get("screen") == A.SCREEN_SAYS)
check(f"...the game and its system ({st.get('game')!r}, {st.get('system')!r}), in what it's asked too",
      st.get("game") == "nestest" and st.get("system") == "NES"
      and "nestest on the NES" in first["questions"]["pick"]["instructions"])
check(f"...its moves: the NES's buttons, directions for a moment or held, with a button, nothing ({len(crit)})",
      {"up", "up_held", "down", "left", "right_held", "a", "b", "start", "select", "right_a", "left_b", "wait"}
      <= set(crit) and "x" not in crit and crit["start"] == "Press Start")
ups = {(s[1]): s[2] for s in sent if s[0] == "up"}


def held(name, k=0):
    downs = [s[2] for s in sent if s[0] == "down" and s[1] == name]
    up = [s[2] for s in sent if s[0] == "up" and s[1] == name]
    return (up[k] - downs[k]) if len(downs) > k and len(up) > k else None


check(f"...Start tapped ({held('start'):.2f} s), Right held a second ({held('right'):.2f} s), Right and A together "
      f"({held('right', 1):.2f} s, A {held('a'):.2f} s)", 0.03 < held("start") < 0.3 and 0.9 < held("right") < 1.4
      and 0.5 < held("right", 1) < 0.9 and 0.5 < held("a") < 0.9)
check("...and let go of each after", all(sum(1 for s in sent if s[1] == n and s[0] == "down")
                                         == sum(1 for s in sent if s[1] == n and s[0] == "up") for n in ("start", "right", "a")))
later = Fake.asked[2]["state"]
did = later.get("you did last, oldest first") or []
check(f"...told what it did, and what came of it: {did}",
      len(did) == 2 and did[0].startswith("Press Start: ") and did[1].startswith("Right, held a second: ")
      and all(d.split(": ")[1] in ("something new", "nothing new", "nothing changed") for d in did))
gaps = [b["at"] - a["at"] for a, b in zip(Fake.asked, Fake.asked[1:4])]
check(f"...the game goes on while it thinks (on, not paused: {run.state}); one pick at a time ({[round(x, 2) for x in gaps]} s)",
      run.state == "on" and all(x >= 1.0 for x in gaps))
check(f"...what it's doing, for the game's menu ({ai.status!r})", ai.alive() and ai.status)
n = len(Fake.asked)
ai.stop()
check("turned off: it stops, and lets go", until(lambda: not ai.thread.is_alive(), 8)
      and all(sum(1 for s in sent if s[1] == nm and s[0] == "down") == sum(1 for s in sent if s[1] == nm and s[0] == "up")
              for nm in {s[1] for s in sent}))
lines = [json.loads(x) for x in open(log).read().splitlines()]
picks = [x for x in lines if x.get("kind") == "move"]
check(f"its log: started, each pick (what it saw: {picks[0].get('saw') if picks else None}), stopped",
      lines[0].get("event") == "Started, with clef, looking at the screen" and picks
      and picks[0].get("saw") == "x".join(map(str, sizes["nes"])) and picks[0].get("pick") == "start"
      and isinstance(picks[0].get("choices"), dict) and picks[1].get("choices") == "as before"
      and lines[-1].get("event") == "Stopped")

# a model that can't see: asked again without the screen, and told it can't see from then on
Fake.asked.clear()
Fake.script[:] = ["a", "a", "a"]
Fake.slow = 0.2
ai = A.GameAI(run, SERVER, "d3", S + "/d3.ai.log")
ai.start()
check("a model that can't see: it plays on", until(lambda: len(Fake.asked) >= 4, 20))
ai.stop()
until(lambda: not ai.thread.is_alive(), 8)
check(f"...shown the screen once ({[bool(x.get('images')) for x in Fake.asked[:4]]}), then never again",
      bool(Fake.asked[0].get("images")) and not any(x.get("images") for x in Fake.asked[1:]))
check(f"...that pick asked again at once, without it; then told it can't see ({Fake.asked[2]['state'].get('screen')!r})",
      Fake.asked[1]["state"].get("screen") is None and "can't see the screen" in Fake.asked[2]["state"].get("screen", "")
      and ai.blind)
blog = open(S + "/d3.ai.log").read()
check("...and its log says so", "d3 can't look at pictures" in blog)

# the model not answering: it waits, and asks again
Fake.asked.clear()
srv2 = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
dead = f"127.0.0.1:{srv2.server_address[1]}"
srv2.server_close()                             # (nothing there)
ai = A.GameAI(run, dead, "clef", S + "/dead.ai.log")
pressed_before = len(sent)
ai.start()
time.sleep(3)
check(f"no answer: it waits, pressing nothing ({ai.status!r})", ai.alive() and len(sent) == pressed_before
      and "Waiting" in ai.status)
ai.stop()
until(lambda: not ai.thread.is_alive(), 8)
run.quit()

# ---- Pokémon Emerald's player: the screen goes with its picks too ---------------------------------------------------
run = GM.GameRun({"path": GAMES + "/arm.gba", "title": "arm", "system": "gba"})
run.start(GM.find_core("gba"), resume=False)
run.wait_started(15)
Fake.asked.clear()
io_ = A.GameIO(Owner(run), None)
pick = io_.decide("walk", "Pick what to do next.", {"goal": "Get your first Pokémon"}, {"lab": "Go into the lab",
                                                                                         "grass": "Walk in the grass"}, "lab")
q = Fake.asked[-1] if Fake.asked else {}
check(f"a pick from its own player: the screen with it ({len(q.get('images') or [])}), the state as it was and the "
      f"screen's line ({sorted(q.get('state', {}))})", q.get("images") and q["state"].get("goal") == "Get your first Pokémon"
      and q["state"].get("screen") == A.SCREEN_SAYS and pick in ("lab", "grass"))
io_.close()

# ---- the game's menu: AI player for every game ---------------------------------------------------------------------
run.quit()


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
check(f"...its menu has AI player ({jobs})", "ai" in jobs and m.game_value("ai") == "Off")
m.game_menu["sel"] = jobs.index("ai")
m.snake_server = lambda: SERVER
m.brain.models, m.brain.models_for, m.brain.models_at = ["clef", "d3"], SERVER, time.monotonic()
said = []
m.toast = lambda text, secs=3: said.append(text)
Fake.asked.clear()
Fake.script[:] = []
m.press("right")
check(f"...on, with your bot's first decision model ({m.game_value('ai')})", m.game_value("ai") == "clef" and m.game_ai.alive())
m.press("b")
check("...back in the game, it looks and picks", until(lambda: len(Fake.asked) >= 2, 15) and Fake.asked[0].get("images"))
was = m.game.game["system"]
m.game.game["system"] = "psp"                   # (a game that takes the sticks as they are)
on = m.game_sticks()
m.game.game["system"] = was
check(f"...your sticks wait too, as your buttons do (a PSP game's: {on})", on is False)
m.game_home()
until(lambda: m.view == "gamemenu", 3)
m.dirty = True; m.flush()
check(f"...the menu says what it's doing ({m.game_ai.status!r})", m.fb.last is not None)
m.game_end()
check("quitting the game stops it", m.game_ai is None)

# ---- each system's buttons ------------------------------------------------------------------------------------------
ps = AG.moves_for("ps1")
check(f"PlayStation: Cross is libretro's B, Circle its A ({ps['cross'][1]}, {ps['circle'][1]}), and with a direction",
      ps["cross"][1] == ("tap", "b") and ps["circle"][1] == ("tap", "a") and "right_cross" in ps and "l2" in ps)
gen = AG.moves_for("genesis")
check(f"Genesis: A B C ({gen['a'][1]}, {gen['b'][1]}, {gen['c'][1]})", gen["a"][1] == ("tap", "y")
      and gen["b"][1] == ("tap", "b") and gen["c"][1] == ("tap", "a"))
sms = AG.moves_for("sms")
check(f"Master System: 1 and 2 ({sms['button_1'][1]}, {sms['button_2'][1]})", sms["button_1"][1] == ("tap", "b")
      and sms["button_2"][1] == ("tap", "a") and sms["button_1"][0] == "Press 1")
n64 = AG.moves_for("n64")
check(f"N64: its directions are the stick ({n64['up_held'][1]}), A is libretro's B, Z its L2",
      n64["up_held"][1] == ("hold", (), (("ly", -127),), AG.HELD) and n64["a"][1] == ("tap", "b")
      and n64["z"][1] == ("tap", "l2") and n64["right_a"][1] == ("hold", ("b",), (("lx", 127),), AG.TOGETHER))


class FakeIO:
    def __init__(self):
        self.did, self.blind, self.last_by = [], False, "model"

    def hold(self, b):
        self.did.append(("hold", b))

    def stick(self, axis, v):
        self.did.append(("stick", axis, v))

    def wait(self, s):
        self.did.append(("wait", s))

    def let_go(self):
        self.did.append(("let go",))

    def tap(self, b):
        self.did.append(("tap", b))


fio = FakeIO()
player = AG.AnyGame({"title": "Super Mario 64 (USA)", "system": "n64"}, fio)
player.do(n64["right_a"][1])
check(f"...an N64 move: the stick pushed and A held together, then let go ({fio.did})",
      fio.did == [("hold", "b"), ("stick", "lx", 127), ("wait", AG.TOGETHER), ("let go",)])
check(f"...its name, plainly ({player.title!r}, {player.system_name!r})", player.title == "Super Mario 64"
      and player.system_name == "Nintendo 64")
player.recent.extend([{"move": "Press A", "key": "a", "came": "nothing"}] * 3)
st = player.state(None)
check(f"...three moves that changed nothing: it's told ({st.get('note')!r})", "changed nothing" in st.get("note", ""))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
