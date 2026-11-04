"""Your own games (the Games tab). The emulator in its own process, with the real cores (mGBA, Nestopia,
Snes9x) and free test ROMs: the picture on the screen at the right size, the sound, the buttons (a quick
tap too), save states, in-game saves, picking up where you left off, zips, a game that won't load, being
stopped. Then in media mode: the Games list (Snake first), a game opened, its menu (HOME), quitting,
things that end a game. Then the real main loop: HOME is the game's menu, not the terminal."""
import os, shutil, signal, subprocess, sys, threading, time, zipfile
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM

RUN = os.environ.get("RUN", "tretro")
S = SP + "/" + RUN
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/More")
os.makedirs(S + "/bin")
R = SP + "/roms"
for name in ("cpu_instrs.gb", "cgb-acid2.gbc", "arm.gba", "sram.gba", "nestest.nes", "HelloWorld.sfc",
             "Twinkle.sfc"):
    shutil.copy(f"{R}/{name}", f"{S}/home/u/Games/{name}")
shutil.copy(f"{R}/MonsterFarmJump.sfc", f"{S}/home/u/Games/More/MonsterFarmJump.sfc")
with zipfile.ZipFile(f"{S}/home/u/Games/Acid Zip.zip", "w") as z:
    z.write(f"{R}/dmg-acid2.gb", "inside/dmg-acid2.gb")
with zipfile.ZipFile(f"{S}/home/u/Games/notagame.zip", "w") as z:
    z.writestr("readme.txt", "hello")
open(f"{S}/home/u/Games/broken.nes", "wb").write(b"not a NES game at all" * 50)
open(f"{S}/home/u/Games/notes.txt", "w").write("not a game")
open(f"{S}/home/u/Games/.hidden.gb", "wb").write(b"x")
os.makedirs(f"{S}/home/u/Games/Saves")
open(f"{S}/home/u/Games/Saves/old.gb", "wb").write(b"x")       # (the Saves folder isn't looked in)
open(f"{S}/bin/aplay", "w").write('#!/bin/sh\necho "$@" >> "$GPI_TEST_SOUND.args"\nexec cat >> "$GPI_TEST_SOUND"\n')
for tool in ("chvt", "fgconsole"):
    open(f"{S}/bin/{tool}", "w").write("#!/bin/sh\necho 1\n")
for f in os.listdir(S + "/bin"):
    os.chmod(f"{S}/bin/{f}", 0o755)
FBF = S + "/fb.bin"
open(FBF, "wb").write(bytes(640 * 480 * 2))
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["PITATO_FB"] = FBF + ":640x480:16"
os.environ["GPI_TEST_SOUND"] = S + "/sound.raw"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
GAMES = S + "/home/u/Games"
SAVES = GAMES + "/Saves"
ok_all = []
runs = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def screen():
    return np.fromfile(FBF, dtype="<u2").reshape(480, 640)


def box():
    nz = np.argwhere(screen() != 0)
    return None if not len(nz) else (int(nz[:, 1].min()), int(nz[:, 0].min()), int(nz[:, 1].max()) + 1,
                                     int(nz[:, 0].max()) + 1)


def inside(b, rect):
    return b is not None and b[0] >= rect[0] and b[1] >= rect[1] and b[2] <= rect[2] and b[3] <= rect[3]


def until(cond, secs=10):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


def start(path, system, **kw):
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": system})
    run.start(GM.find_core(system), **kw)
    runs.append(run)
    return run


def near(a, b, most=100):
    return int((a != b).sum()) <= most


def sound_bytes():
    try:
        return open(S + "/sound.raw", "rb").read()
    except OSError:
        return b""


# ---- finding games and emulators ------------------------------------------------------------------------
found = GM.find_games()
names = [(x["title"], x["system"]) for x in found]
check(f"the Games folder: games of each kind, a folder in it, a zip, by name ({names})",
      names == [("Acid Zip", "gb"), ("arm", "gba"), ("broken", "nes"), ("cgb-acid2", "gbc"), ("cpu_instrs", "gb"),
                ("HelloWorld", "snes"), ("MonsterFarmJump", "snes"), ("nestest", "nes"), ("sram", "gba"),
                ("Twinkle", "snes")])
check("...not hidden files, other files, a zip with no game, or the Saves folder",
      not any(x["title"] in (".hidden", "notes", "notagame", "old") for x in found))
cores = {k: GM.find_core(k) for k in ("gb", "gbc", "gba", "nes", "snes")}
check(f"an emulator for each: {sorted(set(os.path.basename(c) for c in cores.values() if c))}",
      all(cores.values()) and os.path.basename(cores["gba"]) == "mgba_libretro.so"
      and os.path.basename(cores["nes"]) == "nestopia_libretro.so" and os.path.basename(cores["snes"]) == "snes9x_libretro.so")
real_dirs = GM.CORE_DIRS
GM.CORE_DIRS = (S + "/nothing",)
check("...none installed: None", GM.find_core("gba") is None)
GM.CORE_DIRS = real_dirs

# ---- how big the picture is ---------------------------------------------------------------------------------
ps = E.picture_size
check(f"Game Boy on the case's screen: 3x, whole pixels ({ps(640, 480, 160, 144, 10 / 9, 'Fit')})",
      ps(640, 480, 160, 144, 10 / 9, "Fit") == (480, 432))
check(f"Game Boy Advance: as wide as the screen, its shape kept ({ps(640, 480, 240, 160, 1.5, 'Fit')})",
      ps(640, 480, 240, 160, 1.5, "Fit") == (640, 427))
check(f"NES and SNES: 2x tall, their own shape ({ps(640, 480, 256, 224, 1.306, 'Fit')}, "
      f"{ps(640, 480, 256, 224, 4 / 3, 'Fit')})", ps(640, 480, 256, 224, 1.306, "Fit") == (585, 448)
      and ps(640, 480, 256, 224, 4 / 3, "Fit") == (597, 448))
check(f"Sharp: whole pixels only ({ps(640, 480, 240, 160, 1.5, 'Sharp')}, {ps(640, 480, 256, 224, 4 / 3, 'Sharp')})",
      ps(640, 480, 240, 160, 1.5, "Sharp") == (480, 320) and ps(640, 480, 256, 224, 4 / 3, "Sharp") == (512, 448))
big = ps(1920, 1080, 240, 160, 1.5, "Fit")
capped = ps(1920, 1080, 240, 160, 1.5, "Fit", most=640 * 480 * 2)
check(f"a TV: big ({big}), or kept to what a Pi Zero keeps up with ({capped})",
      big == (1440, 960) and capped[0] * capped[1] <= 640 * 480 * 2 and capped[1] % 160 == 0)
check(f"SNES hi-res (512 wide): the same shape ({ps(640, 480, 512, 224, 4 / 3, 'Fit')})",
      ps(640, 480, 512, 224, 4 / 3, "Fit") == (597, 448))
sizes = {"pixels": ps(1920, 1080, 640, 480, 4 / 3, "Fit"), "chip": ps(1920, 1080, 640, 480, 4 / 3, "Fit", whole=False),
         "chip sharp": ps(1920, 1080, 640, 480, 4 / 3, "Sharp", whole=False),
         "chip 4K": ps(3840, 2160, 640, 480, 4 / 3, "Fit", whole=False),
         "chip 720p": ps(1280, 720, 640, 480, 4 / 3, "Fit", whole=False),
         "chip case": ps(640, 480, 640, 480, 4 / 3, "Fit", whole=False),
         "psp": ps(1920, 1080, 480, 272, 480 / 272, "Fit", whole=False)}
check(f"a 1080p TV, a 640x480 picture: whole pixels when nearly as big ({sizes['pixels']}); one the graphics chip "
      f"smooths (an N64's), as tall as the screen ({sizes['chip']}); Sharp, whole pixels still ({sizes['chip sharp']}); "
      f"4K, 720p, the case's screen ({sizes['chip 4K']}, {sizes['chip 720p']}, {sizes['chip case']}); a PSP's "
      f"({sizes['psp']})", sizes["pixels"] == (1280, 960) and sizes["chip"] == (1440, 1080)
      and sizes["chip sharp"] == (1280, 960) and sizes["chip 4K"] == (2880, 2160) and sizes["chip 720p"] == (960, 720)
      and sizes["chip case"] == (640, 480) and sizes["psp"] == (1906, 1080))

# ---- each kind of game, in its own process ----------------------------------------------------------------------
for path, system, rect, want, what in (
        (GAMES + "/cpu_instrs.gb", "gb", (80, 24, 560, 456), "full", "Game Boy"),
        (GAMES + "/cgb-acid2.gbc", "gbc", (80, 24, 560, 456), "full", "Game Boy Color"),
        (GAMES + "/arm.gba", "gba", (0, 26, 640, 453), "full", "Game Boy Advance"),
        (GAMES + "/nestest.nes", "nes", (27, 16, 612, 464), "in", "NES"),
        (GAMES + "/HelloWorld.sfc", "snes", (21, 16, 618, 464), "in", "SNES")):
    run = start(path, system)
    ready = run.wait_started(15)
    time.sleep(1.2)
    b = box()
    check(f"{what}: it starts ({run.state}) and draws, {'filling' if want == 'full' else 'inside'} {rect} ({b})",
          ready and run.state == "on" and not run.resumed
          and (b == rect if want == "full" else inside(b, rect)))
    run.quit()
    check(f"...quit: it ends, its place kept ({os.path.exists(SAVES + '/' + GM.save_name(path) + '.state.auto')})",
          not run.alive() and run.p.returncode == 0
          and os.path.exists(SAVES + "/" + GM.save_name(path) + ".state.auto"))

# sound
open(S + "/sound.raw", "wb").close()
open(S + "/sound.raw.args", "w").close()
run = start(GAMES + "/Twinkle.sfc", "snes", volume=100)
run.wait_started(15)
time.sleep(2.0)
run.quit()
pcm = np.frombuffer(sound_bytes()[:len(sound_bytes()) // 4 * 4], dtype="<i2")
args = open(S + "/sound.raw.args").read()
check(f"sound: aplay at the game's rate ({args.split()[args.split().index('-r') + 1] if '-r' in args.split() else '?'}), "
      f"music in it ({len(pcm) // 2} frames, loudest {int(np.abs(pcm).max()) if len(pcm) else 0})",
      "-r 32040" in args and len(pcm) > 32040 and np.abs(pcm).max() > 1000)
open(S + "/sound.raw", "wb").close()
run = start(GAMES + "/Twinkle.sfc", "snes", volume=0)
run.wait_started(15)
time.sleep(1.0)
run.quit()
pcm0 = np.frombuffer(sound_bytes()[:len(sound_bytes()) // 4 * 4], dtype="<i2")
check(f"...volume 0: silence, still in time ({len(pcm0) // 2} frames)", len(pcm0) > 16000 and not pcm0.any())

# the buttons: nestest's menu, START runs its tests (a quick tap, down and up at once)
for f in os.listdir(SAVES):
    if f.startswith("nestest"):
        os.remove(SAVES + "/" + f)
run = start(GAMES + "/nestest.nes", "nes")
run.wait_started(15)
time.sleep(0.8)
before = screen().copy()
run.press("start"); run.release("start")
time.sleep(1.5)
after = screen().copy()
check(f"a quick tap of START reaches the game: its screen changes ({int((before != after).sum())} pixels)",
      (before != after).sum() > 500)
time.sleep(0.5)
steady = screen().copy()
time.sleep(0.5)
check("...and then it's let go (nothing more happens)", (steady == screen()).all())

# save states, pause, reset
what = run.ask("save", ("saved", "error"), 8)
check(f"save: {what}", what[0] == "saved" and os.path.getsize(SAVES + "/nestest.state") > 1000)
run.ask("reset", ("reset",), 3)
time.sleep(0.8)
check("start over: back to its menu", near(screen(), before) and not near(screen(), after))
what = run.ask("load", ("loaded", "nostate", "error"), 8)
time.sleep(0.5)
check(f"load: {what}, the tests' screen again", what[0] == "loaded" and near(screen(), after))
check("pause: it stops", run.pause() and run.state == "paused")
open(FBF, "r+b").write(bytes(640 * 480 * 2))
time.sleep(0.5)
check("...nothing drawn while paused", box() is None)
run.resume()
until(lambda: run.state == "on", 3)
time.sleep(0.5)
check("resume: on it goes, drawing", run.state == "on" and box() is not None)
os.remove(SAVES + "/nestest.state")
what = run.ask("load", ("loaded", "nostate", "error"), 8)
check(f"load with no save: {what[0]}", what[0] == "nostate")
run.quit()
run = start(GAMES + "/nestest.nes", "nes")
run.wait_started(15)
time.sleep(0.6)
check("opened again: it picks up where you left off (the tests' screen)", run.resumed and near(screen(), after))
run.quit()
run = start(GAMES + "/nestest.nes", "nes", resume=False)
run.wait_started(15)
time.sleep(0.6)
check("...unless it's asked not to", not run.resumed and near(screen(), before))
run.quit()

# in-game saves
for f in os.listdir(SAVES):
    if f.startswith("sram"):
        os.remove(SAVES + "/" + f)
run = start(GAMES + "/sram.gba", "gba")
run.wait_started(15)
time.sleep(1.5)
run.quit()
srm = SAVES + "/sram.srm"
data = open(srm, "rb").read() if os.path.exists(srm) else b""
check(f"an in-game save is written when it changes ({len(data)} bytes, {sum(1 for x in data if x)} not zero)",
      len(data) in (32768, 65536, 131072) and any(data))


class Stub:
    def __init__(self):
        self.put = []

    def put_memory(self, kind, data):
        self.put.append((kind, data))

    def read_memory(self, kind):
        return b""


s = E.Session.__new__(E.Session)
s.args = type("A", (), {"game": GAMES + "/cpu_instrs.gb", "saves": SAVES})()
s.base = SAVES + "/cpu_instrs"
s.core = Stub()
open(GAMES + "/cpu_instrs.sav", "wb").write(b"\x42" * 64)
s.load_saves()
check(f"a save from another emulator next to the game is used the first time ({[(k, d[:2]) for k, d in s.core.put]})",
      s.core.put == [(0, b"\x42" * 64)])
open(SAVES + "/cpu_instrs.srm", "wb").write(b"\x07" * 64)
s.core = Stub()
s.load_saves()
check("...but its own save comes first", s.core.put == [(0, b"\x07" * 64)])
os.remove(GAMES + "/cpu_instrs.sav"); os.remove(SAVES + "/cpu_instrs.srm")

# running slowly: frames left undrawn, told when its menu comes up
s = E.Session.__new__(E.Session)
s.recent = [[300, 10], [100, 5]]
fast = s.slow()
s.recent = [[300, 90], [100, 30]]
check(f"slow: a fifth of the last few hundred frames undrawn ({fast}, {s.slow()})", not fast and s.slow())
s.recent = [[0, 0], [20, 20]]
check("...not from a moment's hiccup at the start", not s.slow())


class FakeProc:
    def __init__(self, lines):
        import io
        self.stdout, self.stdin = io.StringIO(lines), io.StringIO()

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


fr = GM.GameRun({"path": "x.gba", "title": "x", "system": "gba"})
fr.p = FakeProc("ready new\npaused slow\n")
fr.listen()
check(f"...media mode hears it ({fr.slow}, {fr.state})", fr.slow and fr.ended)

# a zip, a broken game, being stopped
zipped = next(x for x in found if x["title"] == "Acid Zip")
run = start(zipped["path"], "gb")
check(f"a zip: the game inside it plays ({run.wait_started(15)}, {run.state})", run.state == "on")
time.sleep(1.0)
check(f"...drawn like any Game Boy game ({box()})", box() == (80, 24, 560, 456))
run.p.send_signal(signal.SIGTERM)
check("stopped (the Pi going off): it keeps your place and ends", until(lambda: run.ended, 8)
      and run.p.returncode == 0 and os.path.exists(SAVES + "/Acid Zip.state.auto"))
run = start(GAMES + "/broken.nes", "nes")
ok = run.wait_started(15)
check(f"a game that won't load: it says so ({run.error!r}) and ends", not ok and run.error == "This game didn't load"
      and until(lambda: run.ended, 5))
run = start(GAMES + "/cpu_instrs.gb", "gb")
run.wait_started(15)
run.p.kill()
check("killed: it's gone, and that's noticed", until(lambda: run.ended, 5) and not run.alive())

# ---- in media mode ----------------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last, self.frames, self.inval = None, 0, 0

    def show(self, img):
        self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        self.inval += 1

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
m.view = "home"
apps = [a for a, _ in m.home_apps()]
m.home_sel = apps.index("Games")
m.press("a")
rows = m.tab_items()
check(f"Games: a list, Snake first ({[r['title'] for r in rows[:3]]}...)", m.tab_type() == "games" and m.view == "list"
      and rows[0]["title"] == "Snake" and rows[0]["kind"] == "child" and len(rows) == 11)
gr = {r["title"]: r for r in rows}
check(f"...each game with its kind ({gr['arm']['icon']} {gr['arm']['sub']!r}, {gr['nestest']['icon']}, "
      f"{gr['Twinkle']['icon']}, {gr['cgb-acid2']['icon']})", (gr["arm"]["icon"], gr["arm"]["sub"]) == ("GBA", "Game Boy Advance")
      and gr["nestest"]["icon"] == "NES" and gr["Twinkle"]["icon"] == "SNES" and gr["cgb-acid2"]["icon"] == "GBC")
m.dirty = True; m.flush()
check(f"...drawn, its buttons {m.list_hints()}", m.fb.last is not None and m.list_hints()[0] == ("A", "Play"))
m.sels[m.tab] = [r["title"] for r in rows].index("nestest")
check(f"...a game you've played: A continues it ({m.list_hints()[0]})", m.list_hints()[0] == ("A", "Continue"))
m.view, m.help_from = "help", "list"
m.dirty = True; m.flush()
check("X: what the buttons do, games too", m.fb.last is not None)
m.view = "list"
m.sels[m.tab] = 0
m.press("a")
s = m.sim_game()
check("A on Snake: Snake, as before", m.tab_type() == "sim" and s.key == "snake" and s.phase == "ready")
m.press("b")
check("B: back to the Games list, Snake picked", m.tab_type() == "games" and m.sels[m.tab] == 0)
m.press("b")
check("B again: home, Games picked", m.view == "home" and apps[m.home_sel] == "Games")
real_home = g.home_dir
os.makedirs(S + "/empty/u")
g.home_dir = lambda: S + "/empty/u"
m.press("a")
rows = m.tab_items()
check(f"no games yet: a word on where they go ({[(r['title'], r['sub']) for r in rows[1:]]})",
      [r["kind"] for r in rows] == ["child", "info"] and rows[1]["sub"] == "the Games folder")
m.press("down")
check(f"...no A on it, and no Y (no games to find pictures for) ({m.list_hints()})",
      all(h[0] not in ("A", "Y") for h in m.list_hints()))
g.home_dir = real_home
m.load_tab(m.tab)
rows = m.tab_items()

# a game, opened
for f in os.listdir(SAVES):
    if f.startswith("nestest"):
        os.remove(SAVES + "/" + f)
m.sels[m.tab] = [r["title"] for r in rows].index("nestest")
shown = FB.count
m.press("a")
check("A on a game: it starts, a word on the screen meanwhile", m.view == "game" and m.game is not None
      and FB.count == shown + 1)
check("...and it's drawing: the menus keep off the screen", m.game.wait_started(15) and m.proc_owns_screen())
shown = FB.count
m.dirty = True; m.flush(); m.tick(); m.flush()
check("...(nothing drawn over it)", FB.count == shown)
time.sleep(0.8)
before = screen().copy()
m.press("start"); m.release("start")
time.sleep(1.2)
after = screen().copy()
check("the buttons go to the game", (before != after).sum() > 500)
fit_box = box()
check(f"the web page: which game ({m.where_text()!r}), the picture refreshed as for a video",
      m.where_text() == "Games › nestest" and m.web_state_now()["video"] is True)
check("the Bot at work keeps quiet meanwhile", m.coder_may_sound() is None)

# its menu
check("HOME: the game's menu", m.game_home() and m.view == "gamemenu" and m.game.state == "paused")
m.dirty = True; m.flush()
bg = m.game_menu["bg"]
check(f"...over the game, dimmed ({bg.getpixel((320, 300)) if bg else None})", bg is not None and m.fb.last is not None
      and max(bg.getpixel((100, 100))) <= 80)
m.fb.last.save(S + "/menu.png")
from PIL import ImageChops
m.game.slow = True
m.dirty = True; m.flush()
slow_img = m.fb.last.copy()
m.game.slow = False
m.dirty = True; m.flush()
diff = ImageChops.difference(slow_img, m.fb.last).getbbox()
check(f"...a game that's been running slowly: its menu says so, under its name ({diff})",
      diff is not None and 40 <= diff[1] and diff[3] <= 100)
check(f"...its rows (no Disc: a game on one; Players: two can play; AI player: any game): "
      f"{[label for _, label in m.game_menu_items()]}",
      [j for j, _ in m.game_menu_items()] == ["resume", "save", "load", "reset", "volume", "picture", "players", "ai",
                                              "quit"])
m.press("down"); m.press("a")
check(f"Save state: {m.msg!r}", m.msg == "Saved" and os.path.exists(SAVES + "/nestest.state") and m.view == "gamemenu")
m.press("down"); m.press("down"); m.press("down")
v = m.volume
m.press("right")
check(f"Volume: ◀▶ ({v} -> {m.volume})", m.volume == min(100, v + 10))
m.press("left"); m.press("left")
check(f"...and down ({m.volume})", m.volume == min(100, v + 10) - 20)
m.press("down")
m.press("right")
check(f"Picture: Sharp, kept for NES games ({m.game_picture('nes')})", m.game_picture("nes") == "Sharp"
      and m.setting("game_picture_nes") == "Sharp")
m.press("b")
check("B: back to the game", m.view == "game" and until(lambda: m.game.state == "on", 3))
time.sleep(0.8)
b = box()
ratio = (b[2] - b[0]) / (fit_box[2] - fit_box[0]) if b and fit_box else 0
check(f"...whole pixels now: 512 x 448, narrower ({b} vs {fit_box}: {ratio:.3f})",
      inside(b, (64, 16, 576, 464)) and abs(ratio - 512 / 585) < 0.02 and b[3] - b[1] == fit_box[3] - fit_box[1])
m.game_home()
m.press("down"); m.press("down")
m.press("a")
check("Load state: A once only asks", m.view == "gamemenu" and m.game_menu["confirm"][0] == "load")
m.dirty = True; m.flush()
m.press("a")
check("...A again: loaded, and back to the game", m.view == "game" and until(lambda: m.game.state == "on", 3))
m.game_home()
for _ in range(3):
    m.press("down")
m.press("a"); m.press("a")
check("Start over (A twice): back to the game", m.view == "game")
time.sleep(1.0)
check("...from the start", (screen() != 0).sum() > 0)
m.game_home()
for _ in range(5):
    m.press("down")
m.press("right")
check(f"Picture: Fill, the whole screen ({m.game_picture('nes')})", m.game_picture("nes") == "Fill")
m.press("right")
check("...and Fit again", m.game_picture("nes") == "Fit")
m.press("down"); m.press("down"); m.press("down")
m.press("a")
check(f"Quit game: back to the list ({m.msg!r})", m.view == "list" and m.game is None and m.msg
      and "next time" in m.msg and os.path.exists(SAVES + "/nestest.state.auto"))
check(f"...the screen drawn whole again ({m.fb.inval})", m.fb.inval >= 1)
m.msg = None

# from Files, and from the web page
fi = m.tab_index("browser")
m.tab, m.view = fi, "list"
m.browse(GAMES)
items = m.tab_items()
m.sels[fi] = next(i for i, it in enumerate(items) if it["title"] == "cgb-acid2.gbc")
m.press("a")
check("Files: A on a game plays it", m.view == "game" and m.game is not None and m.game.game["system"] == "gbc"
      and m.game.wait_started(15))
m.game_end()
r = m.web_show(GAMES + "/Acid Zip.zip")
check(f"the web page's Show on the Pi's screen: a game plays, a zip too ({r})", r == {"ok": True}
      and m.game is not None and m.game.game["system"] == "gb" and m.game.wait_started(15))
m.game_end()
import ast
tree = ast.parse(open(ROOT + "/pitato/webui.py").read())
consts = {n.targets[0].id: n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
kinds, folders = ast.literal_eval(consts["KINDS"]), ast.literal_eval(consts["FOLDERS"])
check(f"the web page puts dropped games in ~/Games ({kinds.get('games')})", folders.get("games") == "Games"
      and set(GM.GAME_EXTS) <= set(kinds.get("games", [])))
m.tab, m.view = m.tab_index("games"), "list"
m.load_tab(m.tab)
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("nestest")

# things that end a game
m.press("a")
m.game.wait_started(15)
check("opened again: it picks up where you left off", m.game.resumed)
run = m.game
m.stop()
check("something else to play (the web page, say): the game ends, kept", m.game is None and not run.alive()
      and m.view == "list")
m.press("a")
m.game.wait_started(15)
run = m.game
m.game_home()
m.web_ready()
check("the web page takes over while the game's menu is up: the game ends, kept", m.game is None
      and not run.alive() and m.view == "list")
m.press("a")
m.game.wait_started(15)
run = m.game
m.game.p.kill()
until(lambda: run.ended, 5)
m.tick()
check(f"a game that stops by itself: back to the list, a word on it ({m.msg!r})", m.view == "list" and m.game is None
      and m.msg == "The game stopped")
real_dirs = g.CORE_DIRS
g.CORE_DIRS = (S + "/nothing",)
m.msg = None
m.press("a")
check(f"no emulator for it: {m.msg!r}", m.view == "list" and m.game is None and m.msg and "setup.sh" in m.msg)
g.CORE_DIRS = real_dirs
m.press("a")
m.game.wait_started(15)
run = m.game
g.system_stopping = lambda: True
m.power_off()
check("the power switch: the game ends, kept, and the screen says so", m.game is None and not run.alive()
      and m.view == "list")
m.halting = 0.0
m.fb = FB(); m.active = True
m.press("a")
m.game.wait_started(15)
run = m.game
m.leave()
check("back to the terminal: the game ends", m.game is None and not run.alive() and not m.active)

# ---- pictures: finding them, keeping them, drawing them ---------------------------------------------------------
import io, zlib, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
A = SP + "/art/"
check(f"plain names: {GM.plain_title('Pokemon - Emerald Version (USA, Europe) [!]')!r}",
      GM.plain_title("Pokemon - Emerald Version (USA, Europe) [!]") == "Pokemon - Emerald Version")
check(f"the words to compare: {GM.title_words(chr(34) + 'Legend of Zelda, The - Link' + chr(39) + 's Awakening (USA)' + chr(34))}",
      GM.title_words("Legend of Zelda, The - Link's Awakening (USA)") == ("legend", "of", "zelda", "links", "awakening")
      and GM.title_words("The Legend of Zelda") == ("legend", "of", "zelda") and GM.title_words("Pac & Pal") == ("pac", "and", "pal"))
check("the likeliest of several: USA, a finished game", min(["Tetris (Japan)", "Tetris (USA) (Beta)", "Tetris (World) (Rev 1)",
      "Tetris (USA)"], key=GM.name_rank) == "Tetris (USA)")


def real_list(key, fn):
    gl = GM.GameList(key)
    for name, crc in GM.read_game_list(open(A + fn + ".dat", encoding="utf-8").read()):
        gl.by_crc.setdefault(crc, name)
        if name not in gl.words:
            gl.add(name)
    return gl


GB = real_list("gb", "Nintendo - Game Boy")
NES = real_list("nes", "Nintendo - Nintendo Entertainment System")
GBA = real_list("gba", "Nintendo - Game Boy Advance")
SNES = real_list("snes", "Nintendo - Super Nintendo Entertainment System")
check(f"No-Intro's lists read: {len(GB.names)} Game Boy, {len(GBA.names)} GBA, {len(NES.names)} NES, {len(SNES.names)} SNES games",
      len(GB.names) > 1500 and len(GBA.names) > 2500 and len(NES.names) > 4000 and len(SNES.names) > 3000)
pairs = [(GB, "Tetris", "Tetris (World) (Rev 1)"), (GB, "Zelda Links Awakening", "Legend of Zelda, The - Link's Awakening (USA, Europe)"),
         (GB, "Wario Land", "Wario Land - Super Mario Land 3 (World)"), (GB, "Metroid II", "Metroid II - Return of Samus (World)"),
         (GBA, "Pokemon Emerald", "Pokemon - Emerald Version (USA, Europe)"), (GBA, "Minish Cap", "Legend of Zelda, The - The Minish Cap (USA)"),
         (NES, "Super Mario Bros", "Super Mario Bros. (World)"), (NES, "The Legend of Zelda", "Legend of Zelda, The (USA)"),
         (SNES, "Zelda - A Link to the Past", "Legend of Zelda, The - A Link to the Past (USA)"), (SNES, "Earthbound", "EarthBound (USA)")]
bad = [(t, gl.by_name(t)) for gl, t, want in pairs if gl.by_name(t) != want]
check(f"a game by its file's name, as people name them ({len(pairs) - len(bad)} of {len(pairs)}) {bad}", not bad)
check(f"...and no guess at all for a loose word or a stranger ({GB.by_name('Mario')}, {NES.by_name('game')}, {GBA.by_name('My Homebrew Thing')})",
      GB.by_name("Mario") is None and NES.by_name("game") is None and GBA.by_name("My Homebrew Thing") is None)
smb = next(c for c, n in NES.by_crc.items() if n == "Super Mario Bros. (World)")
check(f"NES: the list has the whole file's checksum, header and all ({smb})", NES.by_crc.get("393A432F") == "Super Mario Bros. (World)")

# checksums
data = open(R + "/nestest.nes", "rb").read()
check("a game's checksum", GM.game_crcs(GAMES + "/nestest.nes", "nes") == ["%08X" % zlib.crc32(data)])
zipped = GAMES + "/Acid Zip.zip"
inside_crc = "%08X" % zlib.crc32(open(R + "/dmg-acid2.gb", "rb").read())
check(f"...a zip's, from the zip's own list ({GM.game_crcs(zipped, 'gb')})", GM.game_crcs(zipped, "gb") == [inside_crc])
snes = open(R + "/HelloWorld.sfc", "rb").read()
open(S + "/headered.smc", "wb").write(bytes(512) + snes)
check("...a SNES game with a copier's header: without it too", GM.game_crcs(S + "/headered.smc", "snes")
      == ["%08X" % zlib.crc32(bytes(512) + snes), "%08X" % zlib.crc32(snes)])
fake = GM.GameList("snes")
fake.by_crc["%08X" % zlib.crc32(snes)] = "Hello World (USA)"
fake.add("Hello World (USA)")
check("...so it's known by it", GM.which_game({"path": S + "/headered.smc", "system": "snes"}, [fake]) == ("snes", "Hello World (USA)"))
check("not on a list: tried by its own name", GM.which_game({"path": GAMES + "/Twinkle.sfc", "system": "snes"}, [fake])
      == ("snes", "Twinkle"))

# a stand-in for libretro's lists and thumbnails
def png(colour, size=(400, 560)):
    b = io.BytesIO(); Image.new("RGB", size, colour).save(b, "PNG"); return b.getvalue()


SERVED = {}
ASKED = []


class Library(BaseHTTPRequestHandler):
    def do_GET(self):
        ASKED.append(urllib.parse.unquote(self.path))
        body = SERVED.get(urllib.parse.unquote(self.path))
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), Library)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
g.GAME_LISTS = base + "/lists/{system}.dat"
g.ART_SOURCES = (base + "/server/{system}/{kind}/{name}.png", base + "/github/{repo}/{kind}/{name}.png")
crc_nes = "%08X" % zlib.crc32(open(R + "/nestest.nes", "rb").read())
crc_gba = "%08X" % zlib.crc32(open(R + "/arm.gba", "rb").read())
crc_sram = "%08X" % zlib.crc32(open(R + "/sram.gba", "rb").read())
dat = lambda games: ("clrmamepro (\n\tname \"x\"\n)\n\n" + "".join(
    f'game (\n\tname "{n}"\n\trom ( name "{n}.x" size 1 crc {c} )\n)\n\n' for n, c in games)).encode()
SERVED["/lists/Nintendo - Nintendo Entertainment System.dat"] = dat([("NES Test (USA)", crc_nes)])
SERVED["/lists/Nintendo - Game Boy Advance.dat"] = dat([("ARM Test (World)", crc_gba), ("Sram Tester (USA)", crc_sram)])
SERVED["/lists/Nintendo - Game Boy.dat"] = dat([("CPU Instructions (World)", "11111111")])
SERVED["/lists/Nintendo - Game Boy Color.dat"] = dat([("Acid Two (World)", "22222222")])
SERVED["/lists/Nintendo - Super Nintendo Entertainment System.dat"] = dat([("Hello World (USA)", "33333333")])
SERVED["/server/Nintendo - Nintendo Entertainment System/Named_Boxarts/NES Test (USA).png"] = png((200, 40, 40))
SERVED["/github/Nintendo_-_Game_Boy_Advance/Named_Boxarts/ARM Test (World).png"] = png((40, 200, 40), (600, 600))
SERVED["/server/Nintendo - Game Boy Advance/Named_Titles/Sram Tester (USA).png"] = png((40, 40, 200), (240, 160))
SERVED["/server/Nintendo - Super Nintendo Entertainment System/Named_Boxarts/HelloWorld.png"] = b"<html>not a picture</html>"
shutil.rmtree(GAMES + "/Images", ignore_errors=True)
shutil.rmtree(g.CACHE_DIR + "/games", ignore_errors=True)
os.makedirs(GAMES + "/Other")
shutil.copy(R + "/nestest.nes", GAMES + "/Other/nestest.gb")      # (two games of one name)
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.tab, m.view = m.tab_index("games"), "list"
m.load_tab(m.tab)
check(f"two games of one name: their kinds tell them apart ({[r['label'] for r in m.tab_items() if r['title'] == 'nestest']})",
      sorted(r["label"] for r in m.tab_items() if r["title"] == "nestest") == ["nestest (GB)", "nestest (NES)"])
m.dirty = True; m.flush()
check(f"no pictures yet: badges, and Y to find them ({m.list_hints()[:2]})", m.list_hints()[1] == ("Y", "Find pictures")
      and all(m.game_pic(r, "thumb") is None for r in m.tab_items() if r["kind"] == "game"))
m.press("y")
check(f"Y: off it goes ({m.msg!r})", m.msg == f"Finding pictures for {len([r for r in m.tab_items() if r['kind'] == 'game'])} games"
      and m.art_finder.busy)
m.dirty = True; m.flush()
check(f"...meanwhile no Y, and how far it's got on the right ({m.list_hints()})", ("Y", "Find pictures") not in m.list_hints()
      or not m.art_finder.busy)
m.press("y")
check(f"...Y again: {m.msg!r}", m.msg in ("Finding pictures already", "Every game has a picture") or not m.art_finder.busy)
until(lambda: not m.art_finder.busy, 30)
m.tick()
imgs = sorted(os.listdir(GAMES + "/Images"))
check(f"done: {m.msg!r}, kept as {imgs}", m.msg and m.msg.startswith("Found pictures for 3 of")
      and imgs == ["arm.png", "nestest.nes.png", "sram.png"])
check("...by checksum (NES Test), from the second place when the first hadn't it (ARM Test), the title screen when "
      "there's no box (Sram Tester), and nothing that isn't a picture",
      Image.open(GAMES + "/Images/nestest.nes.png").getpixel((5, 5))[:3] == (200, 40, 40)
      and Image.open(GAMES + "/Images/arm.png").getpixel((5, 5))[:3] == (40, 200, 40)
      and Image.open(GAMES + "/Images/sram.png").getpixel((5, 5))[:3] == (40, 40, 200))
sizes = [Image.open(GAMES + "/Images/" + f).size for f in imgs]
check(f"...kept small ({sizes})", all(max(sz) <= 320 for sz in sizes) and (229, 320) in sizes and (320, 320) in sizes)
check("...two games of one name: the picture named with its file's extension (the other one's isn't taken)",
      os.path.exists(GAMES + "/Images/nestest.nes.png") and not os.path.exists(GAMES + "/Images/nestest.png"))
check("...the lists kept for next time", os.path.exists(g.CACHE_DIR + "/games/Nintendo - Game Boy Advance.dat"))
asked = len(ASKED)
m.press("y")
until(lambda: not m.art_finder.busy, 30)
m.tick()
check(f"Y again: only the games still without one are tried, the lists not fetched again ({m.msg!r})",
      not any("/lists/" in a for a in ASKED[asked:]) and m.msg == "No pictures found for these games")

# drawing them
m.msg = None
m.load_tab(m.tab)
rows = m.tab_items()
m.sels[m.tab] = [r["src"] for r in rows].index(GAMES + "/nestest.nes")
m.dirty = True; m.flush()
shot = m.fb.last
check("a game with a picture: on its row, big beside the list, and softly behind it",
      m.game_pic(rows[m.sels[m.tab]], "thumb").size[1] == 40 and max(m.game_pic(rows[m.sels[m.tab]], "panel").size) == 212
      and shot.getpixel((520, 150))[:3] == (200, 40, 40) and shot.getpixel((300, 426)) != tuple(g.BG))
shot.save(S + "/games_list.png")
m.sels[m.tab] = [r["src"] for r in rows].index(GAMES + "/cpu_instrs.gb")
m.dirty = True; m.flush()
check("a game without: its badge, and a word on Y", m.game_pic(rows[m.sels[m.tab]], "thumb") is None
      and m.fb.last.getpixel((300, 426)) == tuple(g.BG))
Image.new("RGB", (100, 90), (250, 250, 0)).save(GAMES + "/Images/cpu_instrs.jpg", "JPEG")
m.dirty = True; m.flush()
check("your own picture in Games/Images (a .jpg, named like the game): used", m.game_pic(rows[m.sels[m.tab]], "panel") is not None
      and m.fb.last.getpixel((520, 150))[0] > 200)
m.sels[m.tab] = 0
m.dirty = True; m.flush()
snk, snk_big = m.game_pic(rows[0], "thumb"), m.game_pic(rows[0], "panel")


def snk_has(img, rgb, near=40):
    a = np.asarray(img.convert("RGBA")).astype(int)
    return int(((abs(a[..., 0] - rgb[0]) < near) & (abs(a[..., 1] - rgb[1]) < near) & (abs(a[..., 2] - rgb[2]) < near)
                & (a[..., 3] > 200)).sum())


import pitato.snake as SN
check(f"Snake: a little board from the game, not a game controller: its snake and its apple on it, rows and beside "
      f"them ({snk.size}, {snk_big.size}; snake {snk_has(snk_big, SN.SNAKE_HEAD)} px, apple "
      f"{snk_has(snk_big, SN.SNAKE_APPLE)} px), round corners, nothing behind the list",
      snk.size == (40, 40) and snk_big.size == (132, 132) and snk_has(snk_big, SN.SNAKE_HEAD) > 600
      and snk_has(snk_big, SN.SNAKE_APPLE) > 150 and snk_has(snk, SN.SNAKE_APPLE, 60) > 2
      and snk_big.getpixel((0, 0))[3] == 0 and m.game_pic(rows[0], "back") is None)
m.fb.last.save(S + "/games_snake.png")
srv.shutdown()
g.GAME_LISTS = "http://127.0.0.1:9/lists/{system}.dat"
g.ART_SOURCES = ("http://127.0.0.1:9/{system}/{kind}/{name}.png",)
shutil.rmtree(g.CACHE_DIR + "/games", ignore_errors=True)
os.remove(GAMES + "/Images/sram.png")
m.press("y")
until(lambda: not m.art_finder.busy, 30)
m.tick()
check(f"no internet: it says so ({m.msg!r})", m.msg == "Couldn't reach the picture library. Check the WiFi")
shutil.rmtree(GAMES + "/Other")

# ---- in the real main loop: HOME ------------------------------------------------------------------------------------
from evdev import ecodes as e
g.PADS_FILE = S + "/pads.json"
g.SCAN_EVERY = 0.05


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    bustype, vendor, product = 0x03, 1, 1


class Pad:
    def __init__(self, keys):
        self.driver, self.path, self.name, self.keys = "usbhid", "/dev/input/event72", "Test pad", keys
        self.info = Info()
        self.r, self.w = os.pipe()
        self.q = []

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)}

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        pass


g.input_driver = lambda dev: dev.driver
pad = Pad([e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_START, e.BTN_SELECT, e.BTN_MODE,
           e.BTN_TL, e.BTN_TR, e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT])
g.list_devices = lambda: [pad.path]
g.InputDevice = lambda path: pad
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": 9})() if str(p).startswith("/dev/input/") else real_stat(p, *a, **k)


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


m = g.Media()
m.load_fonts(); m.fb = FB(); m.active = True; m.boot_media = False
m.tab = m.tab_index("games"); m.view = "list"; m.load_tab(m.tab)
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("cgb-acid2")
done, errors = threading.Event(), []


def loop():
    try:
        g.run(UI(), m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.5)


def press(code, sec=0.3):
    pad.send((e.EV_KEY, code, 1)); time.sleep(0.05); pad.send((e.EV_KEY, code, 0)); time.sleep(sec)


press(e.BTN_SOUTH, 0.2)
check("the real loop: A starts the game", until(lambda: m.game is not None and m.game.state == "on", 15))
press(e.BTN_MODE)
check("HOME: the game's menu, not the terminal", m.active and m.view == "gamemenu")
press(e.BTN_MODE)
check("HOME again: back to the game", m.active and m.view == "game" and until(lambda: m.game.state == "on", 3))
press(e.BTN_MODE)
press(e.BTN_EAST)
check("...B from its menu: the game too", m.view == "game")
press(e.BTN_MODE)
for _ in range(7):                                     # (a Game Boy Color game: for one, no Players; AI player)
    press(e.BTN_DPAD_DOWN, 0.1)
press(e.BTN_SOUTH, 1.0)
check("Quit game from the real loop: the list", m.view == "list" and m.game is None)
press(e.BTN_MODE, 0.5)
check("HOME in the list: the terminal, as ever", not m.active)
done.set(); th.join(5)
check("no errors in the loop", not errors and not th.is_alive())

for r in runs:
    if r.p and r.p.poll() is None:
        r.p.kill()
left = subprocess.run(["pgrep", "-f", "pitato.emulator"], capture_output=True, text=True).stdout.split()
check(f"no games left running ({left})", not left)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
