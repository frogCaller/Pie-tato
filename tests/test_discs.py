"""Disc games: PlayStation in the emulator (PCSX ReARMed, built from source, and a small PlayStation program of
our own on test discs), multi-disc sets, disc changes, the BIOS; which discs are PlayStation games (each kind of
file), which are PSP games (test_psp.py has more), and a PS2's, a GameCube's or a Wii's: told apart, listed on a PC alone;
L2 and R2 from controllers; pictures found by a
disc's game code; the Games folder's folder for each kind of game."""
import json, os, shutil, signal, subprocess, sys, threading, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM, discs as D, inputs as I
from evdev import ecodes as e

RUN = os.environ.get("RUN", "tdiscs")
S = SP + "/" + RUN
shutil.rmtree(S, ignore_errors=True)
P1 = SP + "/ps1"
OUT, FAKES = P1 + "/prog/out", P1 + "/fakes"
HOME = S + "/home/u"
GAMES = HOME + "/Games"
SAVES = GAMES + "/Saves"
for d in ("ps1", "gb", "Listed/discs", "BIOS", "Other"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin"); os.makedirs(S + "/cores")


def cp(src, dst):
    shutil.copy(src, f"{GAMES}/{dst}")


for n in (1, 2):
    for ext in (".cue", ".bin"):
        cp(f"{OUT}/Test Game (USA) (Disc {n}){ext}", f"ps1/Test Game (USA) (Disc {n}){ext}")
cp(f"{OUT}/Solo Test (USA).cue", "Solo Test (USA).cue"); cp(f"{OUT}/Solo Test (USA).bin", "Solo Test (USA).bin")
cp(f"{OUT}/Solo Test (USA).iso", "ps1/Solo Iso (USA).iso")
for n in (1, 2):      # a set with its own .m3u, its discs a folder down
    open(f"{GAMES}/Listed/discs/Listed Disc {n}.cue", "w").write(
        f'FILE "Listed Disc {n}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    shutil.copy(f"{OUT}/Test Game (USA) (Disc {n}).bin", f"{GAMES}/Listed/discs/Listed Disc {n}.bin")
open(f"{GAMES}/Listed/Listed Game (USA).m3u", "w").write("discs/Listed Disc 1.cue\ndiscs/Listed Disc 2.cue\n")
cp(f"{FAKES}/Chd Disc (USA).chd", "Chd Disc Two (USA).chd")
cp(f"{FAKES}/Chd Dvd (USA).chd", "Chd Dvd (USA).chd")
cp(f"{FAKES}/Pbp Game (USA).pbp", "Pbp Game (USA).pbp")
for n in ("Some Linux.iso", "Psp Disc (USA).iso", "Psp Game (USA).pbp", "Chd Dreamcast (USA).chd", "Fake PS2 Packed (USA).cso",
          "Cube Game (USA).iso", "Squeezed Cube (USA).gcz", "Packed WIA (USA).wia", "Cube Game Two (USA).gcm",
          "Remote Game (USA).iso", "Remote Game Two (USA).wbfs", "Packed RVZ (USA).rvz", "Wii Ciso (USA).ciso"):
    cp(f"{FAKES}/{n}", f"Other/{n}")
cp(f"{OUT}/Fake PS2 Game (USA).iso", "Other/Fake PS2 Game (USA).iso")
open(f"{GAMES}/gb/Tiny (USA).gb", "wb").write(bytes(32 * 1024))
open(f"{GAMES}/scph5501.bin", "wb").write(os.urandom(512 * 1024))        # (a BIOS put in the wrong place)
shutil.copy(f"{OUT}/Solo Test (USA).bin", f"{GAMES}/Case Test (USA).bin")    # (its .cue made on Windows: GAME.BIN)
open(f"{GAMES}/Case Test (USA).cue", "w").write('FILE "CASE TEST (USA).BIN" BINARY\r\n  TRACK 01 MODE2/2352\r\n'
                                                '    INDEX 01 00:00:00\r\n')
open(f"{GAMES}/notes.txt", "w").write("not a game")

shutil.copy(P1 + "/pcsx_rearmed/pcsx_rearmed_libretro.so", S + "/cores/pcsx_rearmed_libretro.so")
open(S + "/bin/aplay", "w").write(f'#!/bin/sh\necho "$@" >> "{S}/sound.args"\nexec cat > /dev/null\n')
open(S + "/bin/fgconsole", "w").write("#!/bin/sh\necho 1\n")
open(S + "/bin/chvt", "w").write(f'#!/bin/sh\necho "$@" >> "{S}/chvt.log"\n')
for f in os.listdir(f"{S}/bin"):
    os.chmod(f"{S}/bin/{f}", 0o755)
FBF = S + "/fb.bin"
open(FBF, "wb").write(bytes(640 * 480 * 2))
BASE_PATH = S + "/bin:" + os.environ["PATH"]
os.environ["PATH"] = BASE_PATH
os.environ["PITATO_FB"] = FBF + ":640x480:16"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
g.CORE_DIRS = (S + "/cores", "/usr/lib/*/libretro")
ok_all = []
runs = []

REAL_CODES = e.BTN_SOUTH == 0x130 and e.ABS_HAT0X == 0x10      # (the 3.11 run's evdev stand-in makes its numbers up)


def check(what, cond, codes=False):
    if codes and not REAL_CODES:
        print("skip " + what + " (evdev's real numbers needed)", flush=True)
        return
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def screen():
    return np.fromfile(FBF, dtype="<u2").reshape(480, 640)


def box():
    nz = np.argwhere(screen() != 0)
    return None if not len(nz) else (int(nz[:, 1].min()), int(nz[:, 0].min()), int(nz[:, 1].max()) + 1,
                                     int(nz[:, 0].max()) + 1)


def until(cond, secs=10):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


def colour_at(y=5, x=5):
    return int(screen()[y, x])


BASE, BOX, RED, GREEN, YELLOW, MAGENTA = 0x0210, 0x001F, 0xF800, 0x07C0, 0xFFC0, 0x8010   # (the program's colours)


def start(path, **kw):
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": "ps1"})
    run.start(GM.find_core("ps1"), **kw)
    runs.append(run)
    return run


# ---- which discs are PlayStation games ----------------------------------------------------------------------
want = {
    "Solo Test (USA).cue": ("ps1", "SCUS-94163"), "Solo Test (USA).bin": ("ps1", "SCUS-94163"),
    "ps1/Solo Iso (USA).iso": ("ps1", "SCUS-94163"), "ps1/Test Game (USA) (Disc 2).cue": ("ps1", "SLUS-12346"),
    "Listed/Listed Game (USA).m3u": ("ps1", "SLUS-12345"), "Pbp Game (USA).pbp": ("ps1", "SLUS-00594"),
    "Chd Disc Two (USA).chd": ("ps1", ""), "Chd Dvd (USA).chd": ("psp", ""),
    "Other/Fake PS2 Game (USA).iso": ("ps2", "SLUS-20062"), "Other/Cube Game (USA).iso": ("gc", "GTST01"),
    "Other/Remote Game (USA).iso": ("wii", "RTST01"), "Other/Some Linux.iso": (None, ""), "Other/Psp Disc (USA).iso": ("psp", ""),
    "Other/Psp Game (USA).pbp": ("psp", "ULUS-10041"), "Other/Fake PS2 Packed (USA).cso": ("ps2", "SLUS-20062"),
    "Other/Chd Dreamcast (USA).chd": ("dc", ""), "scph5501.bin": (None, ""),
    "Other/Cube Game Two (USA).gcm": ("gc", "GTWO01"), "Other/Squeezed Cube (USA).gcz": ("gc", ""),
    "Other/Packed WIA (USA).wia": ("gc", "GWIA01"), "Other/Remote Game Two (USA).wbfs": ("wii", "RWBF01"),
    "Other/Packed RVZ (USA).rvz": ("wii", "RRVZ01"), "Other/Wii Ciso (USA).ciso": ("wii", "RCIS01"),
}
got = {k: D.disc_info(f"{GAMES}/{k}", GAMES) for k in want}
bad = {k: v for k, v in got.items() if v != want[k]}
check(f"each kind of disc file: a PlayStation game, a PSP's, a Dreamcast's, a PS2's, a GameCube's, a Wii's or none, and "
      f"its game code ({len(want) - len(bad)} of {len(want)}) {bad}", not bad)
check("...a CD in a .chd: a PlayStation's; a DVD in one: a PSP's (its folder isn't a ps2 one)",
      got["Chd Disc Two (USA).chd"][0] == "ps1" and got["Chd Dvd (USA).chd"][0] == "psp")
check(f"...only discs' kinds of file looked at ({D.DISC_EXTS})",
      set(D.DISC_EXTS) == {".cue", ".chd", ".pbp", ".m3u", ".iso", ".bin", ".img", ".cso", ".gdi", ".cdi", ".gcm", ".rvz",
                           ".wia", ".wbfs", ".ciso", ".gcz"})
check(f"...a .cue's tracks, an .m3u's discs ({[os.path.basename(p) for p in D.m3u_files(GAMES + '/Listed/Listed Game (USA).m3u')]})",
      D.cue_files(GAMES + "/Solo Test (USA).cue") == [GAMES + "/Solo Test (USA).bin"]
      and D.m3u_files(GAMES + "/Listed/Listed Game (USA).m3u") == [GAMES + "/Listed/discs/Listed Disc 1.cue",
                                                                  GAMES + "/Listed/discs/Listed Disc 2.cue"])
check(f"...Disc 2 of a set ({D.disc_number('Final Fantasy VII (USA) (Disc 2)')}, {D.disc_number('Game (Disc 1 of 3) (Rev 1)')})",
      D.disc_number("Final Fantasy VII (USA) (Disc 2)") == ("Final Fantasy VII (USA)", 2)
      and D.disc_number("Game (Disc 1 of 3) (Rev 1)") == ("Game (Rev 1)", 1) and D.disc_number("Plain (USA)")[1] is None)
check(f"the consoles: GB to PlayStation (the Sega ones too), the N64, the PSP, the DS and the Dreamcast, and on a PC the "
      f"PS2, GameCube and Wii ({[s[0] for s in GM.GAME_SYSTEMS]})",
      [s[0] for s in GM.GAME_SYSTEMS] == ["gb", "gbc", "gba", "nes", "snes", "genesis", "sms", "gg", "ngp", "ngpc",
                                          "neogeo", "n64", "ps1", "psp", "nds", "dc", "ps2", "gc", "wii"]
      and GM.DISC_SYSTEMS == ("ps1", "psp", "dc", "ps2", "gc", "wii") and GM.PC_ONLY == ("ps2", "gc", "wii")
      and not hasattr(GM, "GAME_APPS"))

# ---- the Games folder's list ------------------------------------------------------------------------------------------
found = GM.find_games()
names = sorted((x["title"], x["system"]) for x in found)
check(f"the list: each game once, the right console ({len(names)}) {names}", names == sorted([
    ("Case Test (USA)", "ps1"), ("Chd Disc Two (USA)", "ps1"), ("Listed Game (USA)", "ps1"), ("Pbp Game (USA)", "ps1"),
    ("Solo Iso (USA)", "ps1"), ("Solo Test (USA)", "ps1"), ("Test Game (USA)", "ps1"), ("Tiny (USA)", "gb"),
    ("Chd Dvd (USA)", "psp"), ("Psp Disc (USA)", "psp"), ("Psp Game (USA)", "psp"), ("Chd Dreamcast (USA)", "dc")]))
titles = [x["title"] for x in found]
check("...a .cue's tracks and an .m3u's discs aren't games of their own",
      not any(t.startswith("Listed Disc") for t in titles) and titles.count("Solo Test (USA)") == 1
      and not any(x["path"].endswith(".bin") for x in found))
check("...nor a PC's disc, a BIOS in the wrong place, or (on a Pi) a PS2's (.iso, .cso), GameCube's or Wii's (a "
      "Dreamcast's is one now)", [os.path.basename(x["path"]) for x in found if x["path"].startswith(GAMES + "/Other/")]
      == ["Chd Dreamcast (USA).chd", "Psp Disc (USA).iso", "Psp Game (USA).pbp"] and "scph5501" not in titles)
was_pc, g.is_pc = g.is_pc, lambda: True
on_pc = sorted((x["title"], x["system"]) for x in GM.find_games() if x["system"] in ("ps2", "gc", "wii"))
g.is_pc = was_pc
check(f"...on a PC: the PS2's, the GameCube's and the Wii's, each kind of file ({on_pc})", on_pc == sorted([
    ("Fake PS2 Game (USA)", "ps2"), ("Fake PS2 Packed (USA)", "ps2"), ("Cube Game (USA)", "gc"),
    ("Cube Game Two (USA)", "gc"), ("Squeezed Cube (USA)", "gc"), ("Packed WIA (USA)", "gc"), ("Remote Game (USA)", "wii"),
    ("Remote Game Two (USA)", "wii"), ("Packed RVZ (USA)", "wii"), ("Wii Ciso (USA)", "wii")]))
tg = next(x for x in found if x["title"] == "Test Game (USA)")
lines = open(tg["path"]).read().splitlines()
check(f"a PlayStation game's Disc 1 and Disc 2: one game, from a list of its discs kept with the cache ({tg['path'][len(S):]})",
      tg["system"] == "ps1" and tg["path"].startswith(g.CACHE_DIR + "/games/discs/") and tg["path"].endswith("/Test Game (USA).m3u")
      and lines == [f"{GAMES}/ps1/Test Game (USA) (Disc 1).cue", f"{GAMES}/ps1/Test Game (USA) (Disc 2).cue"]
      and tg.get("discs") == 2)
check("...found again: the same list, the same place", GM.find_games() == found)

# ---- PlayStation, in the emulator --------------------------------------------------------------------------------------
core = GM.find_core("ps1")
check(f"PlayStation's emulator: PCSX ReARMed first ({os.path.basename(core or '')})", core == S + "/cores/pcsx_rearmed_libretro.so")
check("...it needs no BIOS file", GM.bios_missing(core) == "")
run = start(GAMES + "/Solo Test (USA).cue")
ready = run.wait_started(20)
time.sleep(1.5)
b = box()
check(f"a .cue: it starts and fills the screen ({run.state}, {b}), the program's colours ({hex(colour_at())}, {hex(colour_at(240, 320))})",
      ready and run.state == "on" and b == (0, 0, 640, 480) and colour_at() == BASE and colour_at(240, 320) == BOX)
check(f"...the box in the middle at 2x ({hex(colour_at(119, 159))} {hex(colour_at(120, 160))} {hex(colour_at(359, 479))} {hex(colour_at(360, 480))})",
      colour_at(119, 159) == BASE and colour_at(120, 160) == BOX and colour_at(359, 479) == BOX and colour_at(360, 480) == BASE)
check(f"...one disc: no disc changing ({run.disc})", run.disc == (0, 1))
for name, colour, what in (("b", RED, "Cross"), ("l2", GREEN, "L2"), ("r2", YELLOW, "R2")):
    run.press(name)
    hit = until(lambda: colour_at() == colour, 3)
    run.release(name)
    back = until(lambda: colour_at() == BASE, 3)
    check(f"...{what} ({name}): the game sees it, and its letting go ({hex(colour_at())})", hit and back)
run.quit()
check("quit: it ends, its place kept, no disc noted (one disc)", not run.alive() and run.p.returncode == 0
      and os.path.exists(SAVES + "/Solo Test (USA).state.auto") and not os.path.exists(SAVES + "/Solo Test (USA).disc"))
run = start(GAMES + "/ps1/Solo Iso (USA).iso")
check("an .iso plays too", run.wait_started(20) and until(lambda: colour_at() == BASE, 4))
run.quit()
import glob as globmod
scratch_before = set(globmod.glob("/tmp/pitato-*"))
run = start(GAMES + "/Case Test (USA).cue")
check("a .cue made on Windows (CASE TEST.BIN for Case Test.bin): it plays", run.wait_started(20)
      and until(lambda: colour_at() == BASE, 4))
run.quit()
check("...and its put-right copy is gone after", set(globmod.glob("/tmp/pitato-*")) <= scratch_before
      and open(GAMES + "/Case Test (USA).cue").read().startswith('FILE "CASE TEST'))

# a set of discs, and changing them
run = start(tg["path"])
run.wait_started(20)
check(f"two discs: it starts on the first, and says how many ({run.disc})", until(lambda: run.disc == (0, 2), 3)
      and until(lambda: colour_at() == BASE, 4))
what = run.ask("disc 2", ("disc",), 3)
check(f"disc 2 in: {what}, {run.disc}", what == ("disc", "2 2") and run.disc == (1, 2))
what = run.ask("disc 5", ("disc",), 3)
check(f"...no such disc: nothing changes ({what})", what == ("disc", "2 2") and run.disc == (1, 2))
time.sleep(1.5)                                       # (the tray shut again a second on)
run.quit()
disc_file = open(SAVES + "/Test Game (USA).disc").read().splitlines()
check(f"quit: which disc noted for next time ({disc_file})", disc_file == ["1", f"{GAMES}/ps1/Test Game (USA) (Disc 2).cue"])
run = start(tg["path"])
run.wait_started(20)
check(f"opened again: picks up where you left off, on disc 2 ({run.resumed}, {run.disc})", run.resumed
      and until(lambda: run.disc == (1, 2), 3))
run.quit()
open(SAVES + "/Test Game (USA).state.auto", "wb").write(b"not a state")   # (it won't load: the disc it starts on shows)
run = start(tg["path"])
run.wait_started(20)
ok = until(lambda: run.disc == (1, 2), 3) and until(lambda: colour_at() == MAGENTA, 4)
check(f"...it starts on that disc, not just jumps to it (disc 2's program: {hex(colour_at())})", not run.resumed and ok)
run.quit()
run = start(tg["path"], resume=False)
run.wait_started(20)
ok = until(lambda: run.disc == (0, 2), 3) and until(lambda: colour_at() == BASE, 4)
check(f"...started over: disc 1 ({run.disc}, {hex(colour_at())})", ok)
run.quit()

# another emulator: Beetle (Debian's), which needs a BIOS file and plays fewer kinds of file
beetle = next((p for p in __import__("glob").glob("/usr/lib/*/libretro/mednafen_psx_libretro.so")), None)
check(f"Beetle: needs its BIOS ({GM.bios_missing(beetle)!r})", beetle and GM.bios_missing(beetle) == "scph5501.bin")
open(GAMES + "/BIOS/scph5501.bin", "wb").write(bytes(512 * 1024))
check("...there now: fine", GM.bios_missing(beetle) == "")
os.remove(GAMES + "/BIOS/scph5501.bin")
r2 = GM.GameRun({"path": GAMES + "/Chd Disc Two (USA).chd", "title": "x", "system": "ps1"})
r2.start(beetle)
ok = not r2.wait_started(15)
check(f"...a .chd it can't play: it says so ({r2.error!r})", ok and r2.error == "This emulator can't play .chd files")
r2.quit()

# ---- in media mode ------------------------------------------------------------------------------------------------------
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
m.tab, m.view = m.tab_index("games"), "list"
m.load_tab(m.tab)
rows = {r["title"]: r for r in m.tab_items()}
check(f"Games: each with its badge ({[(r.get('label'), r.get('icon')) for r in m.tab_items()][1:6]}...)",
      rows["Test Game (USA)"]["icon"] == "PS1" and rows["Test Game (USA)"]["label"] == "Test Game"
      and rows["Test Game (USA)"]["sub"] == "PlayStation" and rows["Tiny (USA)"]["icon"] == "GB")
m.dirty = True; m.flush()
m.view, m.help_from = "help", "list"
m.dirty = True; m.flush()
check("X: the controls, with where your games go", m.fb.last is not None)
m.view = "list"


def pick(title):
    m.load_tab(m.tab)
    m.sels[m.tab] = [r["title"] for r in m.tab_items()].index(title)


for f in os.listdir(SAVES):
    if f.startswith("Solo Test"):
        os.remove(SAVES + "/" + f)
pick("Solo Test (USA)")
m.press("a")
check("A on a PlayStation game: it plays", m.view == "game" and m.game is not None and m.game.wait_started(20)
      and until(lambda: colour_at() == BASE, 4))
m.press("a")
ok = until(lambda: colour_at() == RED, 3)
check(f"...its buttons go by place: the bottom one (A) is Cross ({hex(colour_at())})", ok)
m.release("a")
until(lambda: colour_at() == BASE, 3)
m.press("l2")
check("...L2 reaches it", until(lambda: colour_at() == GREEN, 3))
m.release("l2")
until(lambda: colour_at() == BASE, 3)
check("HOME: its menu, no Disc on it (one disc); Players (two can play)", m.game_home() and m.view == "gamemenu"
      and [j for j, _ in m.game_menu_items()] == ["resume", "save", "load", "reset", "volume", "picture", "players",
                                                  "ai", "quit"])
m.game_end()

pick("Test Game (USA)")
m.press("a")
m.game.wait_started(20)
until(lambda: m.game.disc == (1, 2), 3)        # (it was on disc 2 last time: the .disc file)
check(f"a set of discs: opened on the disc it was on ({m.game.disc})", m.game.disc[1] == 2)
m.game.ask("disc 1", ("disc",), 3)
m.game_home()
items = [j for j, _ in m.game_menu_items()]
check(f"...its menu has Disc ({items})", items == ["resume", "save", "load", "reset", "disc", "volume", "picture", "players",
                                                  "ai", "quit"])
for _ in range(4):
    m.press("down")
m.dirty = True; m.flush()
shot = m.fb.last.copy()
check(f"...Disc: '{m.game_value('disc')}'", m.game_value("disc") == "1 of 2")
m.press("right")
check(f"...◀▶ changes it ({m.msg!r}, {m.game.disc})", m.game.disc == (1, 2) and m.game_value("disc") == "2 of 2"
      and m.msg == "Disc 2 is in. Back to the game to play on")
m.dirty = True; m.flush()
check("...drawn", m.fb.last is not None and m.fb.last.tobytes() != shot.tobytes())
m.press("left")
check(f"...and back ({m.game.disc})", m.game.disc == (0, 2))
m.press("b")
check("B: back to the game", m.view == "game")
m.game_end()

# ---- L2 and R2, from controllers -----------------------------------------------------------------------------------------
class Absinfo:
    def __init__(self, lo, hi, value=0):
        self.min, self.max, self.value = lo, hi, value


class FakeDev:
    def __init__(self, name, keys, axes, path="/dev/input/event90"):
        self.name, self.path, self.keys, self.axes = name, path, keys, axes

    def capabilities(self, absinfo=True):
        return {e.EV_KEY: list(self.keys), e.EV_ABS: list(self.axes)}

    def absinfo(self, code):
        return self.axes[code]

    def close(self):
        pass


XBOX = FakeDev("Microsoft X-Box 360 pad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
                                           e.BTN_SELECT, e.BTN_START, e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
               {e.ABS_X: Absinfo(-32768, 32767), e.ABS_Y: Absinfo(-32768, 32767), e.ABS_Z: Absinfo(0, 255),
                e.ABS_RX: Absinfo(-32768, 32767), e.ABS_RY: Absinfo(-32768, 32767), e.ABS_RZ: Absinfo(0, 255),
                e.ABS_HAT0X: Absinfo(-1, 1), e.ABS_HAT0Y: Absinfo(-1, 1)})
ds4 = FakeDev("Sony Interactive Entertainment Wireless Controller", XBOX.keys + [e.BTN_TL2, e.BTN_TR2], XBOX.axes,
              "/dev/input/event91")


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


xp = I.Pad(XBOX, "gamepad")
check("an Xbox pad's triggers are L2 and R2", xp.triggers == {e.ABS_Z: "l2", e.ABS_RZ: "r2"})
check("...pressed past halfway, let go", xp.translate(Ev(e.EV_ABS, e.ABS_Z, 200)) == [("l2", True)]
      and xp.translate(Ev(e.EV_ABS, e.ABS_Z, 230)) == [] and xp.translate(Ev(e.EV_ABS, e.ABS_Z, 10)) == [("l2", False)]
      and xp.translate(Ev(e.EV_ABS, e.ABS_RZ, 255)) == [("r2", True)] and "r2" in xp.down)
dp = I.Pad(ds4, "gamepad")
check("a PlayStation pad's L2 button", dp.translate(Ev(e.EV_KEY, e.BTN_TL2, 1)) == [("l2", True)])
dinput = FakeDev("Generic DirectInput pad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START],
                 {e.ABS_X: Absinfo(0, 255), e.ABS_Y: Absinfo(0, 255), e.ABS_Z: Absinfo(0, 255), e.ABS_RZ: Absinfo(0, 255)})
dip = I.Pad(dinput, "gamepad")
check("...a pad whose Z and RZ are its right stick: not triggers", dip.triggers == {}
      and dip.translate(Ev(e.EV_ABS, e.ABS_Z, 250)) == [])

# ---- pictures, by a disc's game code -----------------------------------------------------------------------------------
os.makedirs(g.CACHE_DIR + "/games", exist_ok=True)
shutil.copy(f"{SP}/art/Sony - PlayStation.dat", f"{g.CACHE_DIR}/games/Sony - PlayStation.dat")
ps1 = GM.GameList("ps1"); ps1.load()
check(f"Redump's PlayStation list: {len(ps1.names)} games, {len(ps1.by_code)} codes", len(ps1.names) > 10000 and "SCUS-94163" in ps1.by_code)
check(f"a disc known by its code, whatever its file's called ({GM.which_game({'path': GAMES + '/Solo Test (USA).cue', 'system': 'ps1'}, [ps1])})",
      GM.which_game({"path": GAMES + "/Solo Test (USA).cue", "system": "ps1"}, [ps1]) == ("ps1", "Final Fantasy VII (USA) (Disc 1)"))
check(f"...game codes however they're written ({GM.code_key('SLUS_005.94')}, {GM.code_key('scus-94163')}, {GM.code_key('RMGE01')})",
      GM.code_key("SLUS_005.94") == "SLUS-00594" and GM.code_key("scus-94163") == "SCUS-94163" and GM.code_key("RMGE01") is None)
named = "Some Game (USA, Canada) (En,Fr,Es)"
check(f"...its picture tried under the names libretro's pictures may have ({GM.art_names(named)})",
      GM.art_names(named)[:2] == [named, "Some Game (USA) (En,Fr,Es)"])
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
import io
SERVED, ASKED = {}, []


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


def png(colour):
    b = io.BytesIO(); Image.new("RGB", (300, 420), colour).save(b, "PNG"); return b.getvalue()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Library)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
g.GAME_LISTS = base + "/lists/{kind}/{system}.dat"
g.ART_SOURCES = (base + "/server/{system}/{kind}/{name}.png",)
os.remove(f"{g.CACHE_DIR}/games/Sony - PlayStation.dat")          # (not kept: it's asked for)
SERVED["/lists/redump/Sony - PlayStation.dat"] = (
    b'clrmamepro (\n)\ngame (\n\tname "Final Fantasy VII (USA) (Disc 1)"\n\tserial "SCUS-94163"\n)\n'
    b'game (\n\tname "Pbp Thing (USA)"\n\tserial "SLUS-00594"\n)\n')
SERVED["/server/Sony - PlayStation/Named_Boxarts/Final Fantasy VII (USA) (Disc 1).png"] = png((220, 30, 30))
finder = GM.ArtFinder()
games = [x for x in GM.find_games() if x["title"] in ("Solo Test (USA)", "Pbp Game (USA)")]
finder.start(games)
until(lambda: not finder.busy, 60)
imgs = sorted(os.listdir(GAMES + "/Images"))
check(f"Y: pictures for disc games ({finder.note!r}, {imgs})", imgs == ["Solo Test (USA).png"]
      and finder.note == "Found pictures for 1 of 2 games")
check("...Redump's list asked for (not No-Intro's)",
      "/lists/redump/Sony - PlayStation.dat" in ASKED and not any("no-intro" in a for a in ASKED))
check("...the other disc found on it by its code (no picture there for it)",
      "/server/Sony - PlayStation/Named_Boxarts/Pbp Thing (USA).png" in ASKED)
srv.shutdown()

# ---- the web page, and the folders for each kind of game ---------------------------------------------------------------
import ast
tree = ast.parse(open(ROOT + "/pitato/webui.py").read())
consts = {n.targets[0].id: n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
kinds = ast.literal_eval(consts["KINDS"])
check(f"the web page puts disc games in ~/Games too ({len(kinds['games'])} kinds): PlayStation, PSP, PS2, GameCube and "
      "Wii ones", set(GM.GAME_EXTS) | set(D.DISC_EXTS) - {".img"} <= set(kinds["games"]) and ".img" not in kinds["games"]
      and ".cso" in kinds["games"] and {".gcm", ".rvz", ".wia", ".wbfs", ".gcz", ".ciso"} <= set(kinds["games"])
      and ".zso" not in kinds["games"])
setup = open(ROOT + "/setup.sh").read()
import re
loop = re.search(r'^GAME_FOLDERS="([a-z0-9 ]+)"\n.*Pi 4.*Pi 5.*GAME_FOLDERS="\$GAME_FOLDERS ([a-z0-9 ]+)"', setup, re.M)
check(f"setup.sh makes a folder in Games for each kind of game, N64's, PSP's, DS's and Dreamcast's on a Pi 4 or 5 "
      f"({loop and loop.groups()})",
      loop is not None and loop.group(1).split() + loop.group(2).split()
      == [s[0] for s in GM.GAME_SYSTEMS if s[0] not in GM.FAST_PI_ONLY]
      + [s[0] for s in GM.GAME_SYSTEMS if s[0] in GM.FAST_PI_ONLY and s[0] not in GM.PC_ONLY]
      and re.search(r"^for sys in \$GAME_FOLDERS; do", setup, re.M) is not None)
pc_line = re.search(r'^if \[ "\$PC" = yes \]; then GAME_FOLDERS="\$GAME_FOLDERS ([a-z0-9 ]+)"; fi', setup, re.M)
check(f"...and on a PC, the PS2's, GameCube's and Wii's too ({pc_line and pc_line.group(1)})",
      pc_line is not None and pc_line.group(1).split() == loop.group(2).split() + list(GM.PC_ONLY))
block = setup[setup.index('step "Making $USER_HOME/Videos'):setup.index('if [ ! -f "$STATIC/streams.txt" ]')]
block = block.replace('step "', 'echo "')
fresh = S + "/fresh"
os.makedirs(fresh + "/Games/gb")
open(fresh + "/Games/gb/kept.gb", "w").write("x")
r = subprocess.run(["bash", "-c", block], env={**os.environ, "USER_HOME": fresh, "USER_NAME": "root", "STATIC": S},
                   capture_output=True, text=True)
made = sorted(os.listdir(fresh + "/Games"))
check(f"...run: the folders there, empty, what was in one kept ({made}, {r.returncode} {r.stderr.strip()!r})",
      r.returncode == 0 and made == sorted(["BIOS", "gb", "gbc", "gba", "nes", "snes", "genesis", "sms", "gg", "ngp", "ngpc",
                                                     "neogeo", "ps1"])
      and os.listdir(fresh + "/Games/snes") == [] and os.listdir(fresh + "/Games/gb") == ["kept.gb"])
r = subprocess.run(["bash", "-c", block], env={**os.environ, "USER_HOME": fresh, "USER_NAME": "root", "STATIC": S},
                   capture_output=True, text=True)
check("...run again: fine", r.returncode == 0 and sorted(os.listdir(fresh + "/Games")) == made)
r = subprocess.run(["bash", "-c", block], env={**os.environ, "USER_HOME": fresh, "USER_NAME": "root", "STATIC": S,
                                               "MODEL": "Raspberry Pi 4 Model B Rev 1.4"}, capture_output=True, text=True)
check(f"...on a Pi 4: n64, psp, nds and dc folders too ({sorted(os.listdir(fresh + '/Games'))})",
      r.returncode == 0 and sorted(os.listdir(fresh + "/Games")) == sorted(made + ["n64", "psp", "nds", "dc"]))
pc = S + "/fresh_pc"
os.makedirs(pc)
r = subprocess.run(["bash", "-c", block], env={**os.environ, "USER_HOME": pc, "USER_NAME": "root", "STATIC": S,
                                               "MODEL": "", "PC": "yes"}, capture_output=True, text=True)
check(f"...on a PC: those four too, and ps2, gc and wii ({sorted(os.listdir(pc + '/Games'))})",
      r.returncode == 0 and sorted(os.listdir(pc + "/Games")) == sorted(made + ["n64", "psp", "nds", "dc", "ps2", "gc",
                                                                                 "wii"]))
zero = S + "/fresh_zero"
os.makedirs(zero)
r = subprocess.run(["bash", "-c", block], env={**os.environ, "USER_HOME": zero, "USER_NAME": "root", "STATIC": S,
                                               "MODEL": "Raspberry Pi Zero W Rev 1.1", "NEO_OLD": "yes"},
                   capture_output=True, text=True)
check(f"...on a Pi Zero W (no Neo Geo emulator): no neogeo folder ({sorted(os.listdir(zero + '/Games'))})",
      r.returncode == 0 and sorted(os.listdir(zero + "/Games")) == sorted(set(made) - {"neogeo"}))
readme = open(ROOT + "/README.md").read()
check("...and the README says so", "`gb`, `gbc`, `gba`, `nes`, `snes`, `genesis`, `sms`, `gg`, `ngp`, `ngpc`, `neogeo` and "
                                    "`ps1`, and on a Pi 4 or 5 or a PC, `n64`, `psp`, `nds` and `dc`, and on a PC, "
                                    "`ps2`, `gc` and `wii`" in " ".join(readme.split())
      and "the BIOS from your own PS2" in " ".join(readme.split())
      and not any(w in readme for w in ("PCSX2", "GameCube games on a Pi", "Wii games on a Pi"))
      and readme.count("Intel") == 1 and "regular computer (Intel or AMD) with Ubuntu" in " ".join(readme.split()))

for r in runs:
    if r.alive():
        r.quit()
print()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
