"""Attract mode (screens/attract.py, Settings > Attract mode): left idle on the home screen, plugged in, a game plays
by itself. Without the AI player: the game's own demo, from its start; with it (your bot's computer, the model last
picked for games): it plays, from where you were, from a copy of your saves. Its saves apart from yours (yours never
change, your other Pietatos aren't told, it isn't one of the games played last), its sound off, no achievements, 2D
games only; the Bot's face in the corner (a picture the emulator puts over the game's, every frame); another game every
few minutes (not the one before), one that won't start never again; START or A: that game, yours, from your own save;
B, HOME, the web page: back where you were. Not on the battery, not with nothing to play, not while something's on,
not with it Off. And the emulator's badge itself, on a pretend screen."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np

S = SP + "/t_attract"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/nes", "Games/gba", "Games/n64"):
    os.makedirs(f"{HOME}/{d}")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


GAMES = {"nes": "Contra (USA).nes", "gba": "Pokemon Emerald (USA).gba", "n64": "Mario (USA).z64"}
for k, f in GAMES.items():
    open(f"{HOME}/Games/{k}/{f}", "wb").write(b"\0" * 64)
MINE = HOME + "/Games/Saves/Pokemon Emerald (USA)"
open(MINE + ".srm", "w").write("your save")
open(MINE + ".state.auto", "w").write("where you were")
os.utime(MINE + ".srm", (1000, 1000))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
g.playable = lambda key: True
starts, sent, ais, told = [], [], [], []


def start(self, core, **kw):
    self.state = "on"
    self.kw = kw
    starts.append((self.game["path"], kw))


def quit_(self, timeout=0):
    saves = getattr(self, "kw", {}).get("saves") or HOME + "/Games/Saves"
    base = os.path.join(saves, g.save_name(self.game["path"]))
    open(base + ".srm", "w").write("the game's own save, as it ended")
    open(base + ".state.auto", "w").write("where it ended")
    self.ended = True


g.GameRun.start = start
g.GameRun.quit = quit_
g.GameRun.send = lambda self, line: sent.append(line) or True
g.GameRun.pause = lambda self: True


class AI:
    def __init__(self, run, server, model, log, **kw):
        ais.append((run.game["path"], server, model, log, kw.get("notes_path")))
        self.on = False

    def start(self):
        self.on = True

    def stop(self):
        self.on = False

    def alive(self):
        return self.on


import pitato.screens.attract as AM
AM.GameAI = AI


class FB:
    w, h = 640, 480
    def show(self, img): pass
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.saves_tell = lambda run: told.append(run.game["path"])
m.set_setting("battery", "Off")                       # (plugged in: the battery saver off)
m.view = "home"
now = time.monotonic()


def idle(secs=AM.ATTRACT_AFTER + 1):
    m.stirred = time.monotonic() - secs


def tick():
    m.tick()


# ---- not yet --------------------------------------------------------------------------------------------------------
idle(60)
tick()
check("a minute idle: nothing yet", m.attract is None and m.game is None)
m.set_setting("battery", "On")
idle()
tick()
check("on the battery (the battery saver on): never", m.attract is None)
m.set_setting("battery", "Off")
tick()                                                # (the screen awake again: it rested, on the battery)
m.set_setting("attract", "Off")
idle()
tick()
check("Settings > Attract mode Off: never", m.attract is None)
m.set_setting("attract", "On")
m.view = "list"
m.tab = m.tab_index("camera")
idle()
tick()
check("on a page that's being watched (the camera's): not then", m.attract is None)
m.tab = m.tab_index("games")
m.view = "home"

# ---- its own demo ---------------------------------------------------------------------------------------------------
recent_before = list(m.state.get("games_recent", []))
g.random.choice = lambda seq: next(x for x in seq if x["system"] == "nes") if any(x["system"] == "nes" for x in seq) \
    else seq[0]
idle()
tick()
path, kw = starts[-1] if starts else (None, {})
check(f"left idle on the home screen: a game plays by itself ({path and os.path.basename(path)}, {m.view})",
      m.attract is not None and path == f"{HOME}/Games/nes/{GAMES['nes']}" and m.view == "game")
check(f"...its own demo, from its start: no AI player set up ({kw.get('resume')}, {ais})", kw.get("resume") is False
      and not ais)
check(f"...its sound off, no achievements, its saves in a folder of their own ({kw.get('volume')}, "
      f"{kw.get('cheevos')}, {kw.get('saves')})", kw.get("volume") == 0 and kw.get("cheevos") is False
      and kw.get("saves") == g.CACHE_DIR + "/attract/Saves")
m.attract["face_at"] = 0
tick()
badge = m.attract["badge"]
from PIL import Image
check(f"...the Bot's face in the corner: a picture for the emulator ({sent[-1:]})",
      sent[-1:] == ["badge " + badge] and Image.open(badge).size == AM.BADGE)

# ---- B: back where you were --------------------------------------------------------------------------------------------
m.press("b")
check(f"B: back where you were (the home screen), the game gone ({m.view}, {m.game})", m.view == "home"
      and m.game is None and m.attract is None)
check(f"...its saves never yours: yours as they were, nobody told, not one of the games played last ({told})",
      open(MINE + ".srm").read() == "your save" and open(MINE + ".state.auto").read() == "where you were"
      and not told and m.state.get("games_recent", []) == recent_before
      and not os.path.exists(HOME + "/Games/Saves/Contra (USA).srm"))
tick()
check("...and the wait starts again", m.attract is None)

# ---- with the AI player: from where you were -----------------------------------------------------------------------------
g.random.choice = lambda seq: next(x for x in seq if x["system"] == "gba")
m.snake_server = lambda: "http://192.168.1.20:11434"
m.set_setting("game_ai_model", "clef-flash")
idle()
tick()
path, kw = starts[-1]
copy = g.CACHE_DIR + "/attract/Saves/Pokemon Emerald (USA)"
check(f"the AI player set up: it plays, from where you were ({os.path.basename(path)}, {kw.get('resume')}, "
      f"{ais[-1:] and ais[-1][1:3]})", path.endswith(GAMES["gba"]) and kw.get("resume") is True
      and ais and ais[-1][1:3] == ("http://192.168.1.20:11434", "clef-flash"))
check("...from a copy of your saves", open(copy + ".state.auto").read() == "where you were"
      and open(copy + ".srm").read() == "your save")
check("...what it learns kept beside your saves, its log with its own",
      ais[-1][4] == MINE + ".ai-notes.txt" and ais[-1][3].startswith(g.CACHE_DIR + "/attract/"))
check("never a 3D game (too much for a game nobody's playing)", all(not p.endswith(".z64") for p, _ in starts)
      and all(x["system"] != "n64" for x in m.attract_games()))

# ---- START: yours ------------------------------------------------------------------------------------------------------
opened = []
was_open = m.game_open
m.game_open = lambda it: (opened.append(it), was_open(it))[1]
m.press("start")
check(f"START: that game's yours, from your own save ({opened and opened[-1]['src'] == path}, "
      f"{m.game and m.game.kw.get('saves')}, {m.game and getattr(m.game, 'attract', False)})",
      opened and opened[-1]["src"] == path and m.game is not None and not getattr(m.game, "attract", False)
      and m.game.kw.get("saves") is None and m.attract is None)
m.game_end()
m.game_open = was_open
m.view = "home"

# ---- another every few minutes; one that won't start, never again -------------------------------------------------------
g.random.choice = lambda seq: seq[0]
idle()
tick()
first = m.attract["game"]["path"]
m.attract["since"] -= AM.ATTRACT_GAME + 1
tick()
second = m.attract["game"]["path"] if m.attract else None
check(f"a few minutes on: another game, not the one before ({os.path.basename(first)} then "
      f"{second and os.path.basename(second)})", second is not None and second != first)
m.attract["run"].ended = True
tick()
check(f"...one that stops by itself: another, and that one's not played by itself again ({sorted(m.attract['bad'])})",
      m.attract is not None and second in m.attract["bad"] and m.attract["game"]["path"] != second)

# ---- the web page, HOME --------------------------------------------------------------------------------------------------
m.stir()
tick()
check("something done on the web page: back where you were", m.attract is None and m.view == "home")
idle()
tick()
check("HOME: back where you were too", m.attract is not None and m.game_home() is True and m.attract is None
      and m.view == "home")
idle()
tick()
m.set_setting("battery", "On")
tick()
check("unplugged (the battery saver on): it stops", m.attract is None)
m.set_setting("battery", "Off")

# ---- nothing to play --------------------------------------------------------------------------------------------------
for k, f in GAMES.items():
    os.remove(f"{HOME}/Games/{k}/{f}")
idle()
tick()
check(f"no games: nothing, and it doesn't look again for a while ({m.attract_wait - time.monotonic():.0f} s)",
      m.attract is None and m.attract_wait - time.monotonic() > 500)

# ---- the emulator's badge, on a pretend screen ----------------------------------------------------------------------------
from pitato import emulator as E
FBF = S + "/fb.bin"
open(FBF, "wb").write(bytes(640 * 480 * 2))
os.environ["PITATO_FB"] = f"{FBF}:640x480:16"
scr = E.Screen()
scr.set_badge(badge)
frame = np.full((240, 320), 0x07E0, dtype=np.uint16)   # (a green picture, as a core gives it: RGB565)
scr.show(frame, E.FMT_RGB565, 4 / 3)
px = np.fromfile(FBF, dtype="<u2").reshape(480, 640)
corner = px[480 - 112 - 4: 480 - 8, 640 - 128 - 4: 640 - 8]
check(f"the emulator: the badge over the picture's bottom right corner, every frame "
      f"({(corner != 0x07E0).mean():.0%} of the corner not the game's)", (corner != 0x07E0).mean() > 0.8
      and (px[:240, :320] == 0x07E0).all())
scr.set_badge(None)
scr.show(frame, E.FMT_RGB565, 4 / 3)
px = np.fromfile(FBF, dtype="<u2").reshape(480, 640)
check("...and gone when it's taken away", (px == 0x07E0).all())
scr.close()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
