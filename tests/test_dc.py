"""Dreamcast games: the real Flycast (v2.7, built here by setup.sh's own build_flycast, as on a Pi 4 or 5; it draws
with Mesa's llvmpipe as a Pi draws with its V3D chip) and a test program of ours (dctest/pad.c: the controllers'
buttons, triggers and sticks drawn on its screen), put on test discs (dctest/mkdisc.py: a .gdi, a Redump-style .cue,
a GD-ROM .chd). Which files are Dreamcast games (and which are only their tracks) and their codes and names; in the
emulator's process: Flycast's own BIOS, the picture, every button, the triggers and the stick reaching the game by
place, players 2 to 4, states, picking up where you left off, quitting cleanly, its memory card kept with your saves
and made yours, a Dreamcast BIOS of yours linked where Flycast looks; in media mode: the Games list, a Pi too old, an
emulator built for another Pi's memory pages, the buttons as you press them; the AI player's buttons."""
import io, contextlib, os, shutil, signal, subprocess, sys, time, types
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM, discs as D, gpu as GPUM, webui as W, anygame as AG, instincts as IN
from pitato.screens import games as SG

S = SP + "/tdc"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
SAVES = GAMES + "/Saves"
DCF = GAMES + "/dc"
for d in ("dc", "ps1", "Dreamcast", "Other", "BIOS"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin"); os.makedirs(S + "/cores")
MK = SP + "/dctest/mkdisc.py"


def disc(folder, name, code, title):
    subprocess.run([sys.executable, MK, folder, name, code, title], check=True, stderr=subprocess.DEVNULL)
    return f"{folder}/{name}.gdi"


PAD = disc(DCF + "/Pad Test (USA)", "Pad Test (USA)", "T-00001", "PIETATO PAD TEST")
GDEMU = disc(DCF + "/01", "disc", "MK-51035", "PIETATO TAXI TEST")                 # GDEMU's way: a number, disc.gdi
NAMED = disc(GAMES + "/Dreamcast/Racer Test (USA)", "disc", "T-00002", "PIETATO RACER")   # ...its folder's name
# a Redump-style .cue (each track a file, its game in the HIGH-DENSITY AREA), from the same tracks
CUE = DCF + "/Pad Test Cue (USA)/Pad Test Cue (USA).cue"
os.makedirs(os.path.dirname(CUE))
for k, src in ((1, "track01.bin"), (2, "track02.raw"), (3, "track03.bin")):
    shutil.copy(f"{DCF}/Pad Test (USA)/{src}", f"{os.path.dirname(CUE)}/Pad Test Cue (USA) (Track {k}).bin")
open(CUE, "w").write('REM SINGLE-DENSITY AREA\nFILE "Pad Test Cue (USA) (Track 1).bin" BINARY\n  TRACK 01 MODE1/2352\n'
                     '    INDEX 01 00:00:00\nFILE "Pad Test Cue (USA) (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n'
                     '    INDEX 00 00:00:00\n    INDEX 01 00:02:00\nREM HIGH-DENSITY AREA\n'
                     'FILE "Pad Test Cue (USA) (Track 3).bin" BINARY\n  TRACK 03 MODE1/2352\n    INDEX 01 00:00:00\n')
CHD = DCF + "/Pad Test Chd (USA).chd"                       # a GD-ROM in a .chd
subprocess.run(["chdman", "createcd", "-i", PAD, "-o", CHD], check=True, capture_output=True)
# a Dreamcast game burnt to a CD: sound first, then its game (no HIGH-DENSITY AREA: its IP.BIN says so)
BURNT = S + "/burnt"
os.makedirs(BURNT)
shutil.copy(f"{DCF}/Pad Test (USA)/track02.raw", BURNT + "/Burnt (Track 1).bin")
shutil.copy(f"{DCF}/Pad Test (USA)/track03.bin", BURNT + "/Burnt (Track 2).bin")
open(BURNT + "/Burnt.cue", "w").write('FILE "Burnt (Track 1).bin" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
                                      'FILE "Burnt (Track 2).bin" BINARY\n  TRACK 02 MODE1/2352\n    INDEX 01 00:00:00\n')
shutil.copytree(BURNT, DCF + "/Burnt (USA)")
os.rename(DCF + "/Burnt (USA)/Burnt.cue", DCF + "/Burnt (USA)/Burnt (USA).cue")
subprocess.run(["chdman", "createcd", "-i", BURNT + "/Burnt.cue", "-o", GAMES + "/Burnt Chd (USA).chd"], check=True,
               capture_output=True)
shutil.copy(GAMES + "/Burnt Chd (USA).chd", GAMES + "/ps1/Burnt Chd In Ps1 (USA).chd")   # (its folder says otherwise)
# a PlayStation-like CD (data first) in a .chd: a PlayStation's, unless it's in a Dreamcast folder
open(BURNT + "/data.bin", "wb").write(bytes(300 * 2352))
open(BURNT + "/Data.cue", "w").write('FILE "data.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
subprocess.run(["chdman", "createcd", "-i", BURNT + "/Data.cue", "-o", GAMES + "/Other/Data First (USA).chd"],
               check=True, capture_output=True)
shutil.copy(GAMES + "/Other/Data First (USA).chd", GAMES + "/Dreamcast/Data First In Dc (USA).chd")
# a DiscJuggler image: its IP.BIN a little way in (found by looking)
ip = open(f"{DCF}/Pad Test (USA)/track03.bin", "rb").read()[16:16 + 2048]
open(DCF + "/Juggled (USA).cdi", "wb").write(bytes(300 * 2352 + 24) + ip + bytes(2048 * 50))
open(GAMES + "/Other/Not A Disc.cdi", "wb").write(os.urandom(256 * 1024))
# a game on two discs, in a list
for k in (1, 2):
    disc(DCF + f"/Two Discs (USA) (Disc {k})", f"Two Discs (USA) (Disc {k})", "T-00003", f"TWO DISCS {k}")
open(DCF + "/Two Discs (USA).m3u", "w").write("Two Discs (USA) (Disc 1)/Two Discs (USA) (Disc 1).gdi\n"
                                              "Two Discs (USA) (Disc 2)/Two Discs (USA) (Disc 2).gdi\n")
shutil.copy(f"{DCF}/Pad Test (USA)/track03.bin", GAMES + "/Other/track03.bin")   # a game's track on its own

BUILT = SP + "/setupdc/cores"                     # (setup.sh's build_flycast put it there)
CORE = S + "/cores/flycast_libretro.so"
shutil.copy(BUILT + "/flycast_libretro.so", CORE)
shutil.copy(BUILT + "/flycast.version", S + "/cores/flycast.version")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat >> "$GPI_TEST_SOUND"\n')
os.chmod(S + "/bin/aplay", 0o755)
FBF = S + "/fb.bin"
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["GPI_TEST_SOUND"] = S + "/sound.raw"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
g.CORE_DIRS = (S + "/cores",) + tuple(GM.CORE_DIRS)
g.slow_pi = lambda: False
ok_all, runs = [], []


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


def screen_as(bits, w=640, h=480):
    os.environ["PITATO_FB"] = f"{FBF}:{w}x{h}:{bits}"
    open(FBF, "wb").write(bytes(w * h * bits // 8))
    return bits, w, h


def frame(spec):
    bits, w, h = spec
    a = np.fromfile(FBF, dtype="<u2" if bits == 16 else "<u4").reshape(h, w).astype(np.uint32)
    if bits == 16:
        return np.stack([((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3], -1)
    return np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255], -1)


# the test program's screen (640 x 480): its squares, left to right A B X Y Start Up Down Left Right (white when
# pressed), the triggers' bars (L red, R green: as long as they're pressed), the stick's yellow dot, players 2 to 4's
# A (orange when pressed, grey when there and not), and a magenta bar that moves along each frame
SQUARES = ("A", "B", "X", "Y", "Start", "Up", "Down", "Left", "Right")


def pressed(rgb, scale=1):
    return [n for i, n in enumerate(SQUARES) if (rgb[int(64 * scale), int((44 + i * 64) * scale)] > 200).all()]


def bars(rgb):
    red = int(((rgb[132, 20:280, 0] > 200) & (rgb[132, 20:280, 1] < 60)).sum())
    green = int(((rgb[132, 320:580, 1] > 200) & (rgb[132, 320:580, 0] < 60)).sum())
    return red, green


def dot(rgb):
    """Where the stick's dot is, as the game has the stick: (x, y), 0 to 255 (128 the middle), or None."""
    area = rgb[160:440, 10:290]
    ys, xs = np.nonzero((area[..., 0] > 200) & (area[..., 1] > 200) & (area[..., 2] < 60))
    return (round(xs.mean() + 10 - 20 + 0.5), round(ys.mean() + 160 - 170 + 0.5)) if len(xs) else None


def players(rgb):
    out = []
    for p in (1, 2, 3):
        c = rgb[224, 344 + (p - 1) * 64]
        out.append("pressed" if c[0] > 200 and 100 < c[1] < 160 else "there" if abs(int(c[0]) - 64) < 10 else "none")
    return out


def bar_at(rgb):
    xs = np.flatnonzero((rgb[468, :, 0] > 200) & (rgb[468, :, 2] > 200) & (rgb[468, :, 1] < 60))
    return int(xs[0]) if len(xs) else None


def start(path, resume=True, picture="Fit", title=None):
    run = GM.GameRun({"path": path, "title": title or GM.game_title(path), "system": "dc"})
    run.start(GM.find_core("dc"), sound="", volume=80, picture=picture, resume=resume)
    runs.append(run)
    return run


def finish(run):
    run.quit()
    return until(lambda: run.ended, 20)


# ---- which files are Dreamcast games --------------------------------------------------------------------------
want = {"dc/Pad Test (USA)/Pad Test (USA).gdi": ("dc", "T-00001"), "dc/01/disc.gdi": ("dc", "MK-51035"),
        "Dreamcast/Racer Test (USA)/disc.gdi": ("dc", "T-00002"),
        "dc/Pad Test Cue (USA)/Pad Test Cue (USA).cue": ("dc", "T-00001"), "dc/Burnt (USA)/Burnt (USA).cue": ("dc", "T-00001"),
        "dc/Pad Test Chd (USA).chd": ("dc", ""), "Burnt Chd (USA).chd": ("dc", ""),
        "ps1/Burnt Chd In Ps1 (USA).chd": ("ps1", ""), "Other/Data First (USA).chd": ("ps1", ""),
        "Dreamcast/Data First In Dc (USA).chd": ("dc", ""), "dc/Juggled (USA).cdi": ("dc", "T-00001"),
        "Other/Not A Disc.cdi": ("dc", ""), "dc/Two Discs (USA).m3u": ("dc", "T-00003"), "Other/track03.bin": (None, ""),
        "dc/Pad Test (USA)/track03.bin": (None, "")}
got = {k: D.disc_info(f"{GAMES}/{k}", GAMES) for k in want}
bad = {k: v for k, v in got.items() if v != want[k]}
check(f"each kind of file: a Dreamcast game or not, and its code ({len(want) - len(bad)} of {len(want)}) {bad}", not bad)
check("...a .gdi's code from its game track (the one at sector 45000), a Redump .cue's from its HIGH-DENSITY AREA, "
      "a burnt CD's from its data track, a .cdi's found in it, a GD-ROM .chd (and a CD .chd with sound first) a "
      "Dreamcast's, and a game's track on its own isn't a game",
      got["dc/Pad Test (USA)/Pad Test (USA).gdi"] == ("dc", "T-00001") and got["Other/track03.bin"][0] is None)
check("...a CD .chd with its data first: a PlayStation's, unless its folder says Dreamcast (and sound first, unless "
      "its folder says PlayStation)", got["Other/Data First (USA).chd"][0] == "ps1"
      and got["Dreamcast/Data First In Dc (USA).chd"][0] == "dc" and got["ps1/Burnt Chd In Ps1 (USA).chd"][0] == "ps1")
tracks = D.gdi_files(PAD)
check(f"a .gdi's tracks ({[os.path.basename(t) for t in tracks]})", [os.path.basename(t) for t in tracks]
      == ["track01.bin", "track02.raw", "track03.bin"])
check(f"the consoles: Dreamcast after the DS ({[s[0] for s in GM.GAME_SYSTEMS][-5:]}), a disc system, drawn in 3D, "
      f"with sticks, its own files, four players, Flycast",
      [s[0] for s in GM.GAME_SYSTEMS].index("dc") == [s[0] for s in GM.GAME_SYSTEMS].index("nds") + 1
      and GM.DISC_SYSTEMS[:3] == ("ps1", "psp", "dc") and "dc" in GM.NEEDS_3D and "dc" in GM.FAST_PI_ONLY
      and "dc" in GM.ANALOG_SYSTEMS and "dc" in GM.OWN_FILES and GM.GAME_PLAYERS["dc"] == 4
      and GM.system("dc")[1:5] == ("DC", "Dreamcast", (".gdi", ".cdi", ".chd", ".cue", ".m3u"), ("flycast",))
      and GM.GAME_PACKAGES["flycast"] == "flycast" and GM.LIBRETRO_NAMES["dc"] == "Sega - Dreamcast")
check(f"...its files can be dropped on the web page ({[k for k in W.KINDS['games'] if k in ('.gdi', '.cdi', '.raw')]})",
      {".gdi", ".cdi", ".raw", ".chd", ".cue", ".bin"} <= set(W.KINDS["games"]))
check(f"the Dreamcast emulator is found ({GM.find_core('dc')})", GM.find_core("dc") == CORE)
found = GM.find_games()
names = sorted((x["title"], x["system"]) for x in found)
expect = sorted([("Pad Test (USA)", "dc"), ("PIETATO TAXI TEST", "dc"), ("Racer Test (USA)", "dc"),
                 ("Pad Test Cue (USA)", "dc"), ("Burnt (USA)", "dc"), ("Pad Test Chd (USA)", "dc"),
                 ("Burnt Chd (USA)", "dc"), ("Burnt Chd In Ps1 (USA)", "ps1"), ("Data First (USA)", "ps1"),
                 ("Data First In Dc (USA)", "dc"), ("Juggled (USA)", "dc"), ("Not A Disc", "dc"),
                 ("Two Discs (USA)", "dc")])
check(f"the list: each game once, its tracks not ({names})", names == expect)
check("...GDEMU's disc.gdi: the name on the disc when its folder's a number, its folder's name when it's a name; "
      "and each one's saves its own", GM.game_title(GDEMU) == "PIETATO TAXI TEST"
      and GM.game_title(NAMED) == "Racer Test (USA)" and GM.save_name(GDEMU) == "PIETATO TAXI TEST"
      and GM.save_name(NAMED) == "Racer Test (USA)" and GM.save_name(PAD) == "Pad Test (USA)")
g.slow_pi = lambda: True
older = sorted(x["title"] for x in GM.find_games())
check(f"an older Pi: no Dreamcast games at all ({older})", older == ["Burnt Chd In Ps1 (USA)", "Data First (USA)"])
g.slow_pi = lambda: False

# ---- the emulator's process -----------------------------------------------------------------------------------
spec = screen_as(16)
run = start(PAD, resume=False)
check(f"a Dreamcast game starts, on Flycast's own BIOS ({run.wait_started(30)}, {run.state}, {run.error!r})",
      run.state == "on")
check("...its frames reach a 16-bit screen", until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 15))
rgb = frame(spec)
check(f"...640 x 480 as the game drew it: its squares where it put them, none pressed ({pressed(rgb)}, "
      f"{rgb[64, 44].tolist()}, the corner {rgb[2, 2].tolist()})", pressed(rgb) == [] and rgb[2, 2].tolist() == [0, 0, 96])
b0 = bar_at(rgb)
time.sleep(0.5)
check(f"...and on it goes (its bar moved: {b0} -> {bar_at(frame(spec))})", b0 is not None and bar_at(frame(spec)) != b0)
seen = {}
for name in ("b", "a", "y", "x", "start", "up", "down", "left", "right"):
    run.press(name); time.sleep(0.35)
    seen[name] = pressed(frame(spec))
    run.release(name); time.sleep(0.25)
check(f"each button reaches the game, by place (libretro's B is the Dreamcast's A, its A the B, its Y the X, its X "
      f"the Y): {seen}", seen == {"b": ["A"], "a": ["B"], "y": ["X"], "x": ["Y"], "start": ["Start"], "up": ["Up"],
                                  "down": ["Down"], "left": ["Left"], "right": ["Right"]})
check(f"...let go: none ({pressed(frame(spec))})", pressed(frame(spec)) == [])
run.press("l2"); time.sleep(0.35)
left = bars(frame(spec))
run.release("l2"); run.press("r2"); time.sleep(0.35)
right = bars(frame(spec))
run.release("r2"); time.sleep(0.35)
check(f"the triggers: L2 is its left one, all the way ({left}), R2 its right ({right}); let go ({bars(frame(spec))})",
      left[0] > 240 and left[1] == 0 and right[1] > 240 and right[0] == 0 and bars(frame(spec)) == (0, 0))
centre = dot(frame(spec))
run.stick("lx", 127); time.sleep(0.35)
east = dot(frame(spec))
run.stick("lx", 0); run.stick("ly", -127); time.sleep(0.35)
north = dot(frame(spec))
run.stick("ly", 0); time.sleep(0.35)
check(f"the left stick is its own: the middle {centre}, right {east}, up {north}, back {dot(frame(spec))}",
      centre and east and north and abs(centre[0] - 128) < 4 and abs(centre[1] - 128) < 4 and east[0] > 250
      and abs(east[1] - 128) < 4 and north[1] < 6 and dot(frame(spec)) == centre)
check(f"players 2 to 4: not there yet ({players(frame(spec))})", players(frame(spec)) == ["none", "none", "none"])
run.press("b", 1); time.sleep(0.8)
p2 = players(frame(spec))
run.release("b", 1); run.press("b", 3); time.sleep(0.8)
p4 = players(frame(spec))
run.release("b", 3); time.sleep(0.4)
check(f"...player 2's controller there as they press (their A: {p2}), then player 4's ({p4}); player 1's own "
      f"untouched ({pressed(frame(spec))})", p2 == ["pressed", "none", "none"] and p4 == ["there", "none", "pressed"]
      and pressed(frame(spec)) == [])
check("Save state", run.ask("save", ("saved", "error"), 20)[0] == "saved" and os.path.getsize(SAVES + "/Pad Test (USA).state") > 1000000)
answer = run.ask("load", ("loaded", "nostate", "error"), 20)
check(f"Load state ({answer})", answer[0] == "loaded" and until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 10))
reset = run.ask("reset", ("reset",), 20)
open(FBF, "wb").write(bytes(640 * 480 * 2))
check(f"Start over ({reset})", reset[0] == "reset" and until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 20)
      and not run.ended)
paused = run.ask("pause", ("paused",), 10)
open(FBF, "wb").write(bytes(640 * 480 * 2))
time.sleep(0.8)
still = frame(spec).any()
resumed = run.ask("resume", ("resumed",), 10)
check(f"its menu up: it stops drawing ({paused}, drew {still}), then on it goes ({resumed})",
      paused[0] == "paused" and not still and resumed[0] == "resumed"
      and until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 10))
sysdir = S + "/cache/games/dc"
check(f"...its own files: the Dreamcast's clock and settings in the cache, Games/BIOS left alone "
      f"({sorted(os.listdir(sysdir + '/dc'))})", os.path.isfile(sysdir + "/dc/dc_nvmem.bin")
      and os.listdir(GAMES + "/BIOS") == [])
check("quit: it ends, cleanly (Flycast told its OpenGL was going first), where it was kept",
      finish(run) and run.p.returncode == 0 and os.path.getsize(SAVES + "/Pad Test (USA).state.auto") > 1000000)
check(f"...its memory card (the first controller's) its own, with your saves ({sorted(os.listdir(SAVES))})",
      os.path.getsize(SAVES + "/T-00001.A1.bin") == 128 * 1024)
os.chown(SAVES, 1000, 1000)
run = start(PAD)
check(f"...next time it picks up where you were ({run.wait_started(30)}, {run.resumed})", run.resumed
      and until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 15))
check("...and ends cleanly again", finish(run) and run.p.returncode == 0)
owners = {n: os.stat(f"{SAVES}/{n}").st_uid for n in os.listdir(SAVES)}
check(f"...what it made in your Saves folder is yours, as the folder is ({owners})",
      owners and all(u == 1000 for u in owners.values()))
os.chown(SAVES, 0, 0)

spec = screen_as(32, 1280, 720)
run = start(CUE, resume=False)
run.wait_started(30)
until(lambda: (frame(spec)[128, 400] > 0).any(), 15)
rgb = frame(spec)
lit_cols = np.flatnonzero(rgb.any(-1).any(0))
check(f"a Redump-style .cue plays, on a 32-bit 720p screen: 4:3 in the middle, the chip making it bigger "
      f"({int(lit_cols[0]) if len(lit_cols) else None}..{int(lit_cols[-1]) if len(lit_cols) else None})",
      len(lit_cols) and abs(int(lit_cols[0]) - 160) <= 2 and abs(int(lit_cols[-1]) - 1119) <= 2)
finish(run)
spec = screen_as(16)
run = start(CHD, resume=False)
run.wait_started(30)
check("a GD-ROM .chd plays", until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 15))
run.p.send_signal(signal.SIGTERM)
check("stopped (the Pi going off): it keeps your place and ends cleanly", until(lambda: run.ended, 20)
      and run.p.returncode == 0 and os.path.isfile(SAVES + "/Pad Test Chd (USA).state.auto"))
run = start(CHD)
check(f"...and next time it picks up there ({run.wait_started(30)}, {run.resumed})", run.resumed
      and until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 15))
finish(run)


class Sized:   # a core whose state comes out a little bigger than it said (Flycast's, now and then)
    def __init__(self, said, real):
        self.said, self.real, self.asked = said, real, []

    def retro_serialize_size(self):
        return self.said

    def retro_serialize(self, buf, size):
        self.asked.append(size)
        if size < self.real:
            return False
        E.C.memmove(buf, b"s" * self.real, self.real)
        return True


core = E.Core.__new__(E.Core)
core.lib = Sized(27519683, 27519700)
got = core.serialize()
check(f"a state a few bytes bigger than its core said: asked again with room to spare ({core.lib.asked})",
      got is not None and got[:27519700] == b"s" * 27519700 and core.lib.asked[0] == 27519683
      and len(core.lib.asked) == 2)
core.lib = Sized(1000, 1000)
check("...one just the size it said: just that", core.serialize() == b"s" * 1000 and core.lib.asked == [1000])
core.lib = Sized(1000, 10 ** 6)
check("...one much bigger: no state (the one before kept)", core.serialize() is None and len(core.lib.asked) == 3)
run = start(GAMES + "/Other/Not A Disc.cdi", resume=False)
run.wait_started(30)
check(f"...plain bytes named .cdi: it says it didn't start, and ends ({run.error!r})", until(lambda: run.ended, 20)
      and run.error)

# ---- a Dreamcast BIOS of yours: linked where Flycast looks -------------------------------------------------------
open(GAMES + "/BIOS/dc_boot.bin", "wb").write(b"\0" * 2 * 1024 * 1024)
GM.dc_files(sysdir)
link = sysdir + "/dc/dc_boot.bin"
check(f"a BIOS in Games/BIOS: linked where Flycast looks ({os.readlink(link) if os.path.islink(link) else None})",
      os.path.islink(link) and os.readlink(link) == GAMES + "/BIOS/dc_boot.bin")
os.remove(GAMES + "/BIOS/dc_boot.bin")
os.makedirs(GAMES + "/BIOS/dc")
open(GAMES + "/BIOS/dc/DC_BOOT.BIN", "wb").write(b"\0" * 16)
GM.dc_files(sysdir)
check(f"...moved to Games/BIOS/dc (named in capitals): the link follows it ({os.readlink(link)})",
      os.readlink(link) == GAMES + "/BIOS/dc/DC_BOOT.BIN")
shutil.rmtree(GAMES + "/BIOS/dc")
GM.dc_files(sysdir)
check("...taken out: the link's gone too (Flycast's own BIOS again)", not os.path.lexists(link))

# ---- built for another Pi's memory pages -------------------------------------------------------------------------
check(f"setup.sh notes the memory pages it was built for ({open(S + '/cores/flycast.version').read().strip()!r}): this "
      f"Pi's", not GM.built_for_other_pi(CORE) and "pages 4096" in open(S + "/cores/flycast.version").read())
open(S + "/cores/flycast.version", "w").write("v2.7 pages 16384\n")
check("...a Pi 5's (16 KB): not this Pi's", GM.built_for_other_pi(CORE))
open(S + "/cores/flycast.version", "w").write("v2.7\n")
check("...nothing noted: fine", not GM.built_for_other_pi(CORE))
os.remove(S + "/cores/flycast.version")
check("...no note at all: fine", not GM.built_for_other_pi(CORE))

# ---- in this process: Flycast's log, through ours (it can't start without one) -----------------------------------
err = io.StringIO()
with contextlib.redirect_stderr(err):
    try:
        E.Core(CORE, GAMES + "/Other/Not A Disc.cdi", (".cdi",), S + "/saves", "t", sysdir, lambda *a: None).close()
        why = None
    except E.GameError as ex:
        why = str(ex)
said = [ln for ln in err.getvalue().splitlines() if "the emulator says" in ln]
check(f"Flycast's warnings and errors in the log, in words, and a disc it can't read said so ({why!r}: "
      f"{said[-1] if said else None!r})", why == "This game didn't load" and said
      and not any("%s" in ln or "%d" in ln for ln in said))

# ---- the box art: a disc's code in Redump's list ------------------------------------------------------------------
os.makedirs(g.CACHE_DIR + "/games", exist_ok=True)
shutil.copy(f"{SP}/dcdat/dc.dat", f"{g.CACHE_DIR}/games/Sega - Dreamcast.dat")
gl = GM.GameList("dc"); gl.load()
check(f"Redump's Dreamcast list: {len(gl.names)} games, {len(gl.by_code)} codes (Sega's own without MK: "
      f"{gl.by_code.get('51035')})", len(gl.names) > 1000 and gl.by_code.get("51035") == ["Crazy Taxi (USA) (En,Ja)"])
hit = GM.which_game({"path": GDEMU, "system": "dc", "title": GM.game_title(GDEMU)}, [gl])
check(f"a GDEMU disc.gdi known by the code on it (MK-51035: {hit})", hit == ("dc", "Crazy Taxi (USA) (En,Ja)"))
hit = GM.which_game({"path": GAMES + "/Burnt Chd (USA).chd", "system": "dc", "title": "Burnt Chd (USA)"}, [gl])
check(f"...a .chd (its code not read): by its name, as it is ({hit})", hit == ("dc", "Burnt Chd (USA)"))

# ---- the AI player ------------------------------------------------------------------------------------------------
moves = AG.moves_for("dc")
check(f"the AI player's buttons, by place and its triggers ({AG.BUTTONS['dc']}), the stick its way of moving "
      f"({moves['right'][1]})", AG.BUTTONS["dc"][:2] == (("A", "b"), ("B", "a"))
      and dict(AG.BUTTONS["dc"])["L"] == "l2" and dict(AG.BUTTONS["dc"])["R"] == "r2" and moves["right"][1][2] == (("lx", 127),))
roles = IN.roles_for("dc", [lab for lab, _ in AG.BUTTONS["dc"]])
check(f"...a racing game's gas is R, its brake L (as most Dreamcast ones): {roles}", roles["gas"] == "R"
      and roles["brake"] == "L" and roles["jump"] == "A")

# ---- media mode -----------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True

    def __init__(self):
        self.last = None

    def show(self, img):
        self.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        pass

    def close(self):
        pass


shutil.copy(BUILT + "/flycast.version", S + "/cores/flycast.version")
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
real_toast = m.toast
m.toast = lambda text, secs=3: (toasts.append(text), real_toast(text, secs))
m.tab = m.tab_index("games"); m.view = "list"
m.games_dir = "sys:dc"                              # (a dozen games and more: a folder for each console; its own)
m.load_tab(m.tab)
rows = {r["title"]: r for r in m.tab_items()}
check(f"the Games list: Dreamcast games, badged ({rows['Pad Test (USA)']['icon']}, {rows['Pad Test (USA)']['sub']!r}), "
      f"GDEMU's under the disc's name", (rows["Pad Test (USA)"]["icon"], rows["Pad Test (USA)"]["sub"]) == ("DC", "Dreamcast")
      and "PIETATO TAXI TEST" in rows)
m.dirty = True; m.flush()
check("...drawn", m.fb.last is not None)
m.games_search("dc")
check(f"...found as dc (START: {len(m.tab_items())})", {r["title"] for r in m.tab_items()} >= {"Pad Test (USA)", "Two Discs (USA)"}
      and not any(r["title"] == "Data First (USA)" for r in m.tab_items()))
m.games_search("")
g.slow_pi = lambda: True
m.load_tab(m.tab)
titles = [r["title"] for r in m.tab_items()]
check(f"an older Pi: not shown, and in Files a .gdi is just a file ({len(titles)} rows)",
      not any(t in titles for t in ("Pad Test (USA)", "Two Discs (USA)")) and m.game_system(PAD) is None)
g.slow_pi = lambda: False
m.games_dir = "sys:dc"
m.load_tab(m.tab)
open(S + "/cores/flycast.version", "w").write("v2.7 pages 16384\n")
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("Pad Test (USA)")
m.press("a")
check(f"built on another kind of Pi (a Pi 5's memory pages): it says so, and doesn't start ({toasts[-1:]})",
      m.game is None and toasts and "built on another kind of Pi" in toasts[-1] and "setup.sh" in toasts[-1])
shutil.copy(BUILT + "/flycast.version", S + "/cores/flycast.version")
saved_dirs = g.CORE_DIRS
g.CORE_DIRS = (S + "/nowhere",)
m.press("a")
check(f"no Dreamcast emulator: run setup.sh again ({toasts[-1:]})", m.game is None
      and toasts[-1] == "The Dreamcast emulator isn't installed. Run setup.sh again to add it")
g.CORE_DIRS = saved_dirs
spec = screen_as(16)
m.press("a")
check(f"a Pi 4 or 5: it starts ({m.view})", m.view == "game" and m.game is not None and m.game.wait_started(30))
check(f"...buttons by place, as a Dreamcast's (A at the bottom), L and R its triggers too "
      f"({[m.game_button(n) for n in ('a', 'b', 'x', 'y', 'l', 'r', 'l2', 'r2', 'start', 'up')]})",
      [m.game_button(n) for n in ("a", "b", "x", "y", "l", "r", "l2", "r2", "start", "up")]
      == ["b", "a", "y", "x", "l2", "r2", "l2", "r2", "start", "up"])
check("...it takes the sticks as they are", m.game_sticks())
until(lambda: frame(spec)[64, 44].tolist() == [64, 64, 64], 15)
m.input_pad = None
m.press("a"); time.sleep(0.4)
a_down = pressed(frame(spec))
m.release("a")
m.press("l"); time.sleep(0.4)
l_down = bars(frame(spec))
m.release("l")
time.sleep(0.4)
check(f"...A pressed reaches the game as its A ({a_down}), L as its left trigger ({l_down})",
      a_down == ["A"] and l_down[0] > 240)
m.game_menu_open()
items = [k for k, _ in m.game_menu_items()]
check(f"...its menu: Players (four can play), no DS's Screens ({items})", "players" in items and "screens" not in items
      and m.game_value("players").endswith("of 4"))
m.game_menu_close()
m.game_end()
check("...ended", m.game is None and m.view == "list")
for r in runs:
    if r.alive():
        r.quit()
print("ALL OK" if all(ok_all) else f"SOME FAILED ({ok_all.count(False)})")
os._exit(0)
