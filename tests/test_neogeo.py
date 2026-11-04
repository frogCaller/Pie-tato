"""Neo Geo and Neo Geo Pocket games: found in the Games folder (a Neo Geo game by its zip's name, as FinalBurn Neo's list
of games has it, or by the chips in it; never its BIOS), their names, the BIOS looked for in Games/BIOS and beside the
game, a name FinalBurn Neo doesn't know; Beetle NeoPop playing a Neo Geo Pocket Color game (a tiny one made here), its
picture, a save state, a zipped one; FinalBurn Neo opening a zip of chips itself (an incomplete one here: no Neo Geo
game is free to test with), the game ended at once with why (the chips it's missing, in the log);
the AI player's buttons; box art found by FinalBurn Neo's name for the game; then media mode's Games tab."""
import io, json, os, shutil, struct, sys, time, zipfile
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM, anygame as AG, instincts as IN, screen as SC

S = SP + "/tneogeo"
shutil.rmtree(S, ignore_errors=True)
GAMES = S + "/home/u/Games"
for d in ("neogeo", "ngp", "ngpc", "BIOS", "Saves"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin")
os.makedirs(S + "/cores")
NG = SP + "/ng"
shutil.copy(f"{NG}/ngp/mednafen_ngp_libretro.so", S + "/cores/")
shutil.copy(f"{NG}/fb2/src/burner/libretro/fbneo_neogeo_libretro.so", S + "/cores/")
shutil.copy(f"{NG}/fb2/gamelist.txt", S + "/cores/fbneo_neogeo.gamelist.txt")
GM.CORE_DIRS = (S + "/cores",) + GM.CORE_DIRS
GM.NEOGEO_LOOK = 0.0

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
ok_all = []
runs = []


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


def screen():
    return np.fromfile(FBF, dtype="<u2").reshape(480, 640)


def ngp_rom(colour=True, title=b"PIETATO TEST"):
    """A tiny Neo Geo Pocket game: its header (SNK's words, where it starts, colour or not, its name), then a loop
    for ever (TLCS-900H: JR T,$)."""
    rom = bytearray(0x20000)
    rom[0:28] = b" LICENSED BY SNK CORPORATION"
    rom[0x1C:0x20] = struct.pack("<I", 0x200040)
    rom[0x23] = 0x10 if colour else 0x00
    rom[0x24:0x30] = title[:12].ljust(12)
    rom[0x40:0x42] = b"\x68\xFE"
    return bytes(rom)


def zip_of(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


open(f"{GAMES}/ngp/Pocket Test.ngp", "wb").write(ngp_rom(colour=False))
open(f"{GAMES}/ngpc/Colour Test.ngc", "wb").write(ngp_rom())
zip_of(f"{GAMES}/ngpc/Zipped Colour.zip", {"inside/zipped.ngc": ngp_rom(title=b"ZIPPED")})
chips = {"201-p1.p1": b"\x01" * 4096, "201-s1.s1": b"\x02" * 1024, "201-m1.m1": b"\x03" * 1024,
         "201-v1.v1": b"\x04" * 2048, "201-c1.c1": b"\x05" * 4096, "201-c2.c2": b"\x06" * 4096}
zip_of(f"{GAMES}/neogeo/mslug.zip", chips)                                 # (known, its chips: wrong ones, though)
zip_of(f"{GAMES}/kof98.zip", {"242-p1.p1": b"\x01" * 512, "242-c1.c1": b"\x02" * 512})   # (known: in Games itself)
zip_of(f"{GAMES}/neogeo/garou.zip", {"readme.txt": b"chips elsewhere"})    # (known by its name alone)
zip_of(f"{GAMES}/neogeo/homebrewx.zip", {"hbx-p1.p1": b"\x01" * 512, "hbx-c1.c1": b"\x02" * 512})   # (unknown name)
zip_of(f"{GAMES}/neogeo/neogeo.zip", {"sp-s2.sp1": b"\x00" * 1024, "000-lo.lo": b"\x00" * 1024})   # (the BIOS)
zip_of(f"{GAMES}/mslug2.zip", {"game.gba": b"\x00" * 1024})                # (a GBA game, whatever its name)
zip_of(f"{GAMES}/notes.zip", {"readme.txt": b"hello"})

# ---- finding them ------------------------------------------------------------------------------------------
sets = GM.neogeo_sets()
check(f"FinalBurn Neo's list of games, beside it: {len(sets)} sets, Metal Slug among them, not the BIOS",
      len(sets) > 600 and sets.get("mslug", ("",))[0] == "Metal Slug - Super Vehicle-001" and "neogeo" not in sets
      and sets.get("mslugx", ("", ""))[1] == "")
found = GM.find_games()
names = sorted((x["title"], x["system"]) for x in found)
check(f"the Games folder: {names}", names == sorted([
    ("Pocket Test", "ngp"), ("Colour Test", "ngpc"), ("Zipped Colour", "ngpc"),
    ("Metal Slug - Super Vehicle-001", "neogeo"), ("The King of Fighters '98 - The Slugfest", "neogeo"),
    ("Garou - Mark of the Wolves", "neogeo"), ("homebrewx", "neogeo"), ("mslug2", "gba")]))
check("...never the Neo Geo's BIOS, or a zip of notes", not any(os.path.basename(x["path"]) in ("neogeo.zip", "notes.zip")
                                                                for x in found))
check("its badge and name: NEO, Neo Geo; NGP and NGPC", GM.system("neogeo")[1:3] == ("NEO", "Neo Geo")
      and GM.system("ngp")[1] == "NGP" and GM.system("ngpc")[2] == "Neo Geo Pocket Color")
check("saves go by the zip's name (mslug), not the game's long one", GM.save_name(f"{GAMES}/neogeo/mslug.zip") == "mslug")
check("Neo Geo games: two players", GM.GAME_PLAYERS.get("neogeo") == 2)
cores = {k: GM.find_core(k) for k in ("ngp", "ngpc", "neogeo")}
check(f"the emulators: {[os.path.basename(c or '-') for c in cores.values()]}",
      os.path.basename(cores["ngp"]) == os.path.basename(cores["ngpc"]) == "mednafen_ngp_libretro.so"
      and os.path.basename(cores["neogeo"]) == "fbneo_neogeo_libretro.so")
check("the BIOS: beside the game will do (Games/neogeo/neogeo.zip)",
      GM.bios_missing(cores["neogeo"], f"{GAMES}/neogeo/mslug.zip") == "")
check(f"...one in Games itself: neogeo.zip is missing ({GM.bios_missing(cores['neogeo'], f'{GAMES}/kof98.zip')!r})",
      GM.bios_missing(cores["neogeo"], f"{GAMES}/kof98.zip") == "neogeo.zip")
shutil.copy(f"{GAMES}/neogeo/neogeo.zip", f"{GAMES}/BIOS/neogeo.zip")
check("...in Games/BIOS: fine for every game", GM.bios_missing(cores["neogeo"], f"{GAMES}/kof98.zip") == "")
os.remove(f"{GAMES}/BIOS/neogeo.zip")
check("a Neo Geo Pocket game needs no BIOS", GM.bios_missing(cores["ngpc"], f"{GAMES}/ngpc/Colour Test.ngc") == "")
os.makedirs(f"{GAMES}/ps1", exist_ok=True)
open(f"{GAMES}/ps1/scph5501.bin", "wb").close()
check("...but another emulator's BIOS beside its game doesn't count (Beetle PSX looks only in Games/BIOS)",
      GM.bios_missing("beetle_psx", f"{GAMES}/ps1/Some Game.cue") == "scph5501.bin")
os.remove(f"{GAMES}/ps1/scph5501.bin")
real_model = SC.pi_model
for model, ok in (("Raspberry Pi Zero W Rev 1.1", False), ("Raspberry Pi Model B Plus Rev 1.2", False),
                  ("Raspberry Pi Zero 2 W Rev 1.0", True), ("Raspberry Pi 4 Model B Rev 1.4", True), ("", True)):
    SC.pi_model = lambda m=model: m
    check(f"{model or 'a PC'}: Neo Geo games {'shown' if ok else 'not shown (too slow for one)'}, Neo Geo Pocket ones shown",
          GM.playable("neogeo") == ok and GM.playable("ngp") and GM.playable("ngpc"))
SC.pi_model = real_model
check("pictures: Neo Geo Pocket games looked for in both lists, as Game Boy ones are",
      ("ngp", "ngpc") in GM.ART_PAIRS and ("gb", "gbc") in GM.ART_PAIRS)
check("a name FinalBurn Neo doesn't know: homebrewx", GM.neogeo_unknown(f"{GAMES}/neogeo/homebrewx.zip")
      and not GM.neogeo_unknown(f"{GAMES}/neogeo/mslug.zip"))
check("the AI player's buttons: a Neo Geo's A B C D, Coin; a Neo Geo Pocket's A B and Option (which pauses)",
      dict(AG.BUTTONS["neogeo"])["C"] == "y" and dict(AG.BUTTONS["neogeo"])["Coin"] == "select"
      and dict(AG.BUTTONS["ngpc"])["Option"] == "start" and "Option" in AG.PAUSES and "neogeo" in IN.ROLES)
check("Play here: they stay on the Pi", "neogeo" not in g.HERE_GAMES and "ngp" not in g.HERE_GAMES)

# ---- Beetle NeoPop ------------------------------------------------------------------------------------------
def start(path, system, **kw):
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": system})
    run.start(GM.find_core(system), **kw)
    runs.append(run)
    return run


open(S + "/sound.raw", "wb").close()
run = start(f"{GAMES}/ngpc/Colour Test.ngc", "ngpc")
ready = run.wait_started(15)
time.sleep(1.0)
what, rest = run.ask(f"shot {S}/shot.ppm", ("shot",), 5)
size = None
if what == "shot" and rest.startswith("ok"):
    from PIL import Image
    size = Image.open(f"{S}/shot.ppm").size
check(f"Beetle NeoPop: the game starts ({run.state}), its picture 160 x 152 ({size})",
      ready and run.state == "on" and size == (160, 152))
time.sleep(1.0)
pcm = open(S + "/sound.raw", "rb").read()
args = open(S + "/sound.raw.args").read() if os.path.exists(S + "/sound.raw.args") else ""
check(f"...its sound, at 44100 a second ({len(pcm)} bytes)", "-r 44100" in args and len(pcm) > 44100)
check(f"...a save state ({run.ask('save', ('saved', 'nostate'), 5)[0]})", os.path.exists(f"{GAMES}/Saves/Colour Test.state"))
run.quit()
check("...quit: its place kept", not run.alive() and os.path.exists(f"{GAMES}/Saves/Colour Test.state.auto"))
run = start(f"{GAMES}/ngpc/Colour Test.ngc", "ngpc")
check("...and picked up again next time", run.wait_started(15) and run.resumed)
run.quit()
run = start(f"{GAMES}/ngpc/Zipped Colour.zip", "ngpc")
check("a zipped one: out of its zip while it plays", run.wait_started(15) and run.state == "on")
run.quit()
run = start(f"{GAMES}/ngp/Pocket Test.ngp", "ngp")
check("a black-and-white one (.ngp)", run.wait_started(15) and run.state == "on")
run.quit()

# ---- FinalBurn Neo ------------------------------------------------------------------------------------------
LOG = S + "/emulator.log"
real_popen = GM.subprocess.Popen


def popen_logged(cmd, **kw):
    kw["stderr"] = open(LOG, "a")
    return real_popen(cmd, **kw)


GM.subprocess.Popen = popen_logged
open(LOG, "w").close()
run = start(f"{GAMES}/neogeo/mslug.zip", "neogeo")
ready = run.wait_started(20)
until(lambda: not run.alive(), 8)
log = open(LOG).read()
check(f"FinalBurn Neo opens the zip itself: no game in these chips, so it doesn't start, and says why ({run.error!r})",
      not ready and run.error.startswith("Parts of this game aren't in its zip") and not run.alive())
check("...the log has the chips it couldn't find", "201-p1.p1" in log and "is required" in log)
check("...nothing kept for next time (no place to pick up from)", not os.path.exists(f"{GAMES}/Saves/mslug.state.auto"))
GM.subprocess.Popen = real_popen
for r in runs:
    r.quit()

# ---- box art by FinalBurn Neo's name -----------------------------------------------------------------------
tree = {"tree": [{"path": "Named_Boxarts/Metal Slug - Super Vehicle-001.png"},
                 {"path": "Named_Boxarts/Fatal Fury 2 _ Garou Densetsu 2 - arata-naru tatakai (NGM-047)(NGH-047).png"},
                 {"path": "Named_Titles/Garou - Mark of the Wolves (NGM-2530).png"},
                 {"path": "Named_Snaps/Metal Slug X - Super Vehicle-001.png"}]}
asked = []
real_fetch = GM.fetch


def fake_fetch(url, timeout=15):
    asked.append(url)
    if "api.github.com" in url:
        return json.dumps(tree).encode()
    raise GM.urllib.error.URLError("not here")


GM.fetch = fake_fetch
gl = GM.GameList("neogeo")
check(f"Neo Geo pictures: their names from libretro's thumbnails ({len(gl.names) if gl.load() else 0} of them, "
      "boxes and title screens)", sorted(gl.names) == sorted([
          "Fatal Fury 2 _ Garou Densetsu 2 - arata-naru tatakai (NGM-047)(NGH-047)",
          "Garou - Mark of the Wolves (NGM-2530)", "Metal Slug - Super Vehicle-001"])
      and "SNK_-_Neo_Geo" in asked[-1])
picks = {z: GM.which_game({"path": f"{GAMES}/neogeo/{z}.zip", "system": "neogeo"}, [gl])[1]
         for z in ("mslug", "garou", "fatfury2", "mslugx")}
check(f"...each game's picture by FinalBurn Neo's name for it ({picks})",
      picks["mslug"] == "Metal Slug - Super Vehicle-001" and picks["garou"] == "Garou - Mark of the Wolves (NGM-2530)"
      and picks["fatfury2"].startswith("Fatal Fury 2 _ Garou Densetsu 2")
      and picks["mslugx"].startswith("Metal Slug X - Super Vehicle-001"))
clone = next(n for n, (_, parent) in GM.neogeo_sets().items() if parent == "garou")
check(f"...a version of a game ({clone}) without one of its own: its game's picture",
      GM.which_game({"path": f"{GAMES}/neogeo/{clone}.zip", "system": "neogeo"}, [gl])[1]
      == "Garou - Mark of the Wolves (NGM-2530)")
gl2 = GM.GameList("neogeo")
asked.clear()
check("...the names kept a month (not fetched again)", gl2.load() and not asked and len(gl2.names) == 3)
GM.fetch = real_fetch

# ---- media mode: the Games tab ------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True

    def __init__(self):
        self.last = None

    def show(self, img):
        self.last = img.copy()

    def show_part(self, img, box):
        self.last = img.copy()

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
gi = m.tab_index("games")
m.tab, m.view = gi, "list"
m.load_tab(gi)
rows = {r["title"]: r for r in m.tab_items(gi) if r.get("kind") == "game"}
check(f"the Games tab: Neo Geo and Neo Geo Pocket games, their badges ({sorted((r['title'], r.get('icon')) for r in rows.values())})",
      rows.get("Metal Slug - Super Vehicle-001", {}).get("icon") == "NEO" and rows.get("Colour Test", {}).get("icon") == "NGPC"
      and rows.get("Pocket Test", {}).get("icon") == "NGP")
started = []
real_start = GM.GameRun.start
GM.GameRun.start = lambda self, core, **kw: started.append((self.game["path"], core))
m.msg = None
m.game_open(rows["The King of Fighters '98 - The Slugfest"])
check(f"no BIOS where it looks: it says so ({m.msg!r})", m.msg == "Neo Geo games need neogeo.zip in Games/BIOS"
      and not started)
m.msg = None
m.game_open(rows["homebrewx"])
check(f"a name FinalBurn Neo doesn't know: it says so ({m.msg!r})", "doesn't know this game" in (m.msg or "")
      and not started)
m.msg = None
m.game_open(rows["Metal Slug - Super Vehicle-001"])
check(f"Metal Slug, its BIOS beside it: it starts ({started[-1:] and os.path.basename(started[-1][1])})",
      started and started[-1][0].endswith("mslug.zip") and started[-1][1].endswith("fbneo_neogeo_libretro.so"))
GM.GameRun.start = real_start
if m.game is not None:
    m.game = None
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
