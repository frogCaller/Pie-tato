"""The AI player's plumbing (pitato/gameai.py, pitato/emulator.py's peek and mem, the game's menu): the real mGBA
playing a Game Boy Advance test game, its memory read as the game sees it (a quick look at a few places, and all of
its working memory into a file); a cartridge that's Pokémon Emerald (its header) and one that isn't, both offered the
AI player in the game's menu; the AI player turned on there with a decision model from your bot's computer (it waits
while the menu's up, has the buttons while it plays: yours wait), and off again; a game with no player of its own
played from its screen; quitting the game stops it."""
import os, shutil, struct, sys, threading, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emerald as E, gameai as A, games as GM

S = SP + "/tgameai"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/Saves")
os.makedirs(S + "/bin")
shutil.copy(SP + "/roms/arm.gba", S + "/home/u/Games/arm.gba")
rom = bytearray(0x100000)                     # a cartridge that says it's Emerald: it loops where it starts
rom[0:4] = struct.pack("<I", 0xEA00002E)      # (b 0x080000C0)
rom[0xA0:0xAC] = b"POKEMON EMER"
rom[0xAC:0xB0] = b"BPEE"
rom[0xC0:0xC4] = struct.pack("<I", 0xEAFFFFFE)   # (b .)
open(S + "/home/u/Games/Emerald.gba", "wb").write(bytes(rom))
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


# ---- the game's memory, read as it plays --------------------------------------------------------------------------
run = GM.GameRun({"path": GAMES + "/arm.gba", "title": "arm", "system": "gba"})
run.start(GM.find_core("gba"), resume=False)
check(f"a Game Boy Advance game plays ({run.wait_started(15)}, {run.state})", run.state == "on")


class Owner:                                  # (what GameIO needs of the AI player)
    def __init__(self, run):
        self.run, self.stopping, self.statuses, self.logged = run, threading.Event(), [], []
        self.server, self.model, self.offline = "", "", False

    def set_status(self, w):
        self.statuses.append(w)

    def log(self, e):
        self.logged.append(e)


cart = open(GAMES + "/arm.gba", "rb").read()
io = A.GameIO(Owner(run), cart)
got = io.peek((0x080000A0, 12), (0x02000000, 16), (0x03007FF0, 16), (0x01000000, 4))
check(f"a quick look: the cartridge's title ({got[0]!r}), working RAM (EWRAM, IWRAM: {len(got[1])}, {len(got[2])} "
      f"bytes), nothing where there's no memory ({got[3]})", got[0] == cart[0xA0:0xAC] and len(got[1]) == 16
      and len(got[2]) == 16 and got[3] is None)
m = io.snapshot()
check(f"all its working memory, in a file: IWRAM {len(m.iwram)} bytes, EWRAM {len(m.ewram)} "
      f"({os.path.dirname(io.mem_path)})", len(m.iwram) == 0x8000 and len(m.ewram) == 0x40000
      and os.path.exists(io.mem_path) and m.bytes(0x080000A0, 12) == cart[0xA0:0xAC])
big = io.peek((0x02000000, 0x4000), (0x03000000, 0x4000))
check(f"...a bigger look: 16 KB from each ({[len(b) for b in big]})", [len(b) for b in big] == [0x4000, 0x4000])
run.pause()
until(lambda: run.state == "paused", 3)
waited = []


def snap_later():
    waited.append(time.monotonic())
    try:
        waited.append(io.snapshot())
    except Exception as ex:
        waited.append(ex)


t = threading.Thread(target=snap_later)
t.start()
time.sleep(0.6)
check("...the game's menu up: a look waits till it's back", t.is_alive() and len(waited) == 1)
run.resume()
t.join(5)
check(f"...back: it goes on ({type(waited[-1]).__name__})", isinstance(waited[-1], E.Mem))
io.close()
check("...its file gone when it's done", not os.path.exists(io.mem_path))
run.quit()

# ---- media mode: the game's menu ---------------------------------------------------------------------------------
check(f"Emerald's cartridge: the AI player can play it ({A.can_play(GAMES + '/Emerald.gba')}); a test game, no "
      f"({A.can_play(GAMES + '/arm.gba')})", A.can_play(GAMES + "/Emerald.gba") and not A.can_play(GAMES + "/arm.gba"))


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
m.sels[m.tab] = [r["title"] for r in rows].index("arm")
m.press("a")
check("a test game: plays", until(lambda: m.game is not None and m.game.state == "on", 15))
m.game_home()
until(lambda: m.view == "gamemenu", 3)
check(f"...its menu: AI player in it too (any game: it plays from the screen) ({[j for j, _ in m.game_menu_items()]})",
      "ai" in [j for j, _ in m.game_menu_items()])
m.game_menu_close()
m.game_end()
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("Emerald")
m.press("a")
check("Emerald: plays", until(lambda: m.game is not None and m.game.state == "on", 15))
m.game_home()
until(lambda: m.view == "gamemenu", 3)
jobs = [j for j, _ in m.game_menu_items()]
check(f"...its menu: AI player, Off ({jobs}, {m.game_value('ai')})", "ai" in jobs and m.game_value("ai") == "Off")
m.game_menu["sel"] = jobs.index("ai")
m.toasts = [] if hasattr(m, "toasts") else None
said = []
real_toast = m.toast
m.toast = lambda text, secs=3: said.append(text)
m.snake_server = lambda: ""
m.press("right")
check(f"...no Bot set up: it says so ({said[-1:]})", said and "Set up the Bot" in said[-1] and m.game_value("ai") == "Off")
SERVER = "http://192.0.2.1:11434"
m.snake_server = lambda: SERVER
m.brain.models, m.brain.models_for, m.brain.models_at = ["tev1", "nimble"], SERVER, time.monotonic()
m.press("right")
check(f"...right: on, with your bot's first decision model ({m.game_value('ai')}, {said[-1]!r})",
      m.game_value("ai") == "tev1" and m.game_ai.alive() and "back in the game" in said[-1])
m.dirty = True; m.flush()
check(f"...the menu says what it's doing ({m.game_ai.status!r})", m.fb.last is not None)
m.press("right")
check(f"...right again: the next model ({m.game_value('ai')})", m.game_value("ai") == "nimble")
first = m.game_ai
m.press("b")
check("...back in the game", until(lambda: m.view == "game" and m.game.state == "on", 3))
sent = []
real_press = m.game.press
m.game.press = lambda *a: sent.append(a)
m.press("a")
m.release("a")
check(f"...it has the buttons: yours wait ({sent})", sent == [] and m.game_ai.alive())
m.game.press = real_press
time.sleep(0.6)
check(f"...it's reading the game as it plays ({m.game_ai.status!r}: still going, no errors)",
      m.game_ai.alive() and not m.game_ai.status.startswith("Stopped"))
m.game_home()
until(lambda: m.view == "gamemenu", 3)
m.game_menu["sel"] = [j for j, _ in m.game_menu_items()].index("ai")
m.press("left")
m.press("left")
check(f"...left to Off: it stops ({m.game_value('ai')}, {said[-1]!r})",
      m.game_value("ai") == "Off" and until(lambda: not first.thread.is_alive(), 5) and said[-1] == "Your turn")
m.press("b")
until(lambda: m.view == "game" and m.game.state == "on", 3)
sent.clear()
m.game.press = lambda *a: sent.append(a)
m.press("a")
check(f"...and your buttons are the game's again ({sent})", sent == [("a", 0)])
m.game.press = real_press
m.game_home()
until(lambda: m.view == "gamemenu", 3)
m.game_menu["sel"] = [j for j, _ in m.game_menu_items()].index("ai")
m.press("right")
second = m.game_ai
check(f"...on again: the model it had last time (left went nimble, tev1, Off: {m.game_value('ai')})",
      m.game_value("ai") == "tev1")
m.game_end()
check("quitting the game stops it", until(lambda: not second.thread.is_alive(), 5) and m.game_ai is None)
log = os.path.join(GAMES, "Saves", GM.save_name(GAMES + "/Emerald.gba") + ".ai.log")
lines = open(log).read().splitlines() if os.path.exists(log) else []
check(f"its log, beside the game's saves ({len(lines)} lines: {lines[:1]})",
      lines and '"Started, with tev1"' in lines[0] and any('"Stopped"' in x for x in lines))

# ---- a game with no player of its own: it's played from its screen (pitato/anygame.py) -------------------------------
run = GM.GameRun({"path": GAMES + "/arm.gba", "title": "arm", "system": "gba"})
run.start(GM.find_core("gba"), resume=False)
run.wait_started(15)
ai = A.GameAI(run, SERVER, "tev1", S + "/x.log")
ai.start()
time.sleep(1.0)
check(f"a game with no player of its own: played from its screen ({ai.status!r})", ai.alive()
      and '"Started, with tev1, looking at the screen"' in open(S + "/x.log").read())
ai.stop()
check("...and off again", until(lambda: not ai.thread.is_alive(), 10))
run.quit()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
