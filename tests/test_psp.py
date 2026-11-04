"""PSP games: the real PPSSPP (v1.20.4 and pitato's patch, built here by setup.sh's own build_ppsspp, as on a Pi 4
or 5; it draws with Mesa's llvmpipe as a Pi draws with its V3D chip) and PSPSDK's free samples (pspautotests' demos: the cube, the controller),
put on test discs (psp/mkfixtures.py). Which files are PSP games (.iso, a .cso, a .pbp, a DVD in a .chd) and their
codes; in the emulator's process: the picture (16:9, on 16 and 32-bit screens, a 720p and a 1080p one, Sharp),
states, picking up where you left off, start over, quitting cleanly (PPSSPP told its OpenGL is going before it's
unloaded), a disc that won't boot, the buttons and the stick reaching the game, its own files; PPSSPP's own thread
for the game given a hard time (psp/storm.py: the patch's pausing, start overs, quitting); in this process: the log
in words; in media mode: the Games list, a Pi too old, the buttons by place, the sticks as they are."""
import os, shutil, signal, struct, subprocess, sys, threading, time, types, io, contextlib
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM, discs as D, gpu as GPUM, webui as W
from pitato.screens import games as SG

S = SP + "/tpsp"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
SAVES = GAMES + "/Saves"
PSP = GAMES + "/psp"
for d in ("psp", "ps2", "Other", "BIOS"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin"); os.makedirs(S + "/cores")
FIX, FAKES = SP + "/psp/fix", SP + "/ps1/fakes"
for n in ("Umd Cube (USA).iso", "Umd Cube Squeezed (USA).cso", "Controller.pbp", "No Boot (USA).iso"):
    shutil.copy(f"{FIX}/{n}", f"{PSP}/{n}")
shutil.copy(f"{FIX}/Cube.iso", f"{GAMES}/Cube.iso")                       # (not in the psp folder: it says so itself)
shutil.copy(f"{FAKES}/Chd Dvd (USA).chd", f"{GAMES}/Dvd Game (USA).chd")   # a DVD in a .chd: a PSP's...
shutil.copy(f"{FAKES}/Chd Dvd (USA).chd", f"{GAMES}/ps2/Ps2 Dvd (USA).chd")   # ...unless it's in a ps2 folder
shutil.copy(f"{FAKES}/Fake PS2 Packed (USA).cso", f"{GAMES}/Other/Fake PS2 Packed (USA).cso")
shutil.copy(f"{SP}/ps1/prog/out/Fake PS2 Game (USA).iso", f"{GAMES}/Other/Fake PS2 Game (USA).iso")
shutil.copy(f"{FAKES}/Pbp Game (USA).pbp", f"{GAMES}/Pbp Game (USA).pbp")    # a PlayStation game made for the PSP


def sfo(vals):
    keys = data = ents = b""
    for k, v in vals.items():
        vb = v.encode() + b"\0"; vb += bytes(-len(vb) % 4)
        ents += struct.pack("<HHIII", len(keys), 0x0204, len(v) + 1, len(vb), len(data))
        keys += k.encode() + b"\0"; data += vb
    keys += bytes(-len(keys) % 4)
    return struct.pack("<4sIIII", b"\x00PSF", 0x101, 20 + len(ents), 20 + len(ents) + len(keys), len(vals)) + ents + keys + data


open(f"{PSP}/Update (USA).pbp", "wb").write(struct.pack("<4sI8I", b"\x00PBP", 0x10000, *([40] * 8))
                                           + sfo({"CATEGORY": "PG", "DISC_ID": "ULUS10041", "TITLE": "Update"}))
open(f"{PSP}/Psn Game (USA).pbp", "wb").write(struct.pack("<4sI8I", b"\x00PBP", 0x10000, *([40] * 8))
                                             + sfo({"CATEGORY": "EG", "DISC_ID": "NPUH10001", "TITLE": "Psn"}))
open(f"{PSP}/Not A Game.iso", "wb").write(os.urandom(64 * 1024))          # (just bytes)

BUILT = SP + "/setuppsp/cores"                     # (setup.sh's build_ppsspp put them there)
CORE = S + "/cores/ppsspp_libretro.so"
shutil.copy(BUILT + "/ppsspp_libretro.so", CORE)
shutil.copytree(BUILT + "/PPSSPP", S + "/cores/PPSSPP")
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


def lit(rgb):
    """(top, bottom, left, right) of what's drawn, or None."""
    m = rgb.any(-1)
    rows, cols = np.flatnonzero(m.any(1)), np.flatnonzero(m.any(0))
    return (int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])) if len(rows) else None


def green(rgb):
    return (rgb[..., 1] > 200) & (rgb[..., 0] < 180) & (rgb[..., 2] < 180)


def start(path, resume=True, picture="Fit"):
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": "psp"})
    run.start(GM.find_core("psp"), sound="", volume=80, picture=picture, resume=resume)
    runs.append(run)
    return run


def finish(run):
    run.quit()
    return until(lambda: run.ended, 15)


# ---- which files are PSP games -----------------------------------------------------------------------------------
want = {"psp/Umd Cube (USA).iso": ("psp", "ULUS-10041"), "psp/Umd Cube Squeezed (USA).cso": ("psp", "ULUS-10041"),
        "Cube.iso": ("psp", ""), "psp/Controller.pbp": ("psp", ""), "psp/Psn Game (USA).pbp": ("psp", "NPUH-10001"),
        "psp/Update (USA).pbp": (None, ""), "Dvd Game (USA).chd": ("psp", ""), "ps2/Ps2 Dvd (USA).chd": ("ps2", ""),
        "Other/Fake PS2 Packed (USA).cso": ("ps2", "SLUS-20062"), "Other/Fake PS2 Game (USA).iso": ("ps2", "SLUS-20062"),
        "Pbp Game (USA).pbp": ("ps1", "SLUS-00594"), "psp/Not A Game.iso": (None, "")}
got = {k: D.disc_info(f"{GAMES}/{k}", GAMES) for k in want}
bad = {k: v for k, v in got.items() if v != want[k]}
check(f"each kind of file: a PSP game or not, and its code ({len(want) - len(bad)} of {len(want)}) {bad}", not bad)
check("...a UMD's code from its UMD_DATA.BIN, a .cso's from inside it (its blocks squeezed and not), a .pbp's "
      "from its PARAM.SFO; a disc made without the PSP's name on it, by its PSP_GAME folder",
      got["psp/Umd Cube Squeezed (USA).cso"] == ("psp", "ULUS-10041") and got["Cube.iso"][0] == "psp")
check("...not a game update, nor plain bytes; a PlayStation 2's (.iso, .cso, or a DVD in a ps2 folder) told as one "
      "(played on a PC)", all(got[k][0] is None for k in ("psp/Update (USA).pbp", "psp/Not A Game.iso"))
      and all(got[k][0] == "ps2" for k in ("Other/Fake PS2 Packed (USA).cso", "Other/Fake PS2 Game (USA).iso",
                                            "ps2/Ps2 Dvd (USA).chd")))
check(f"the consoles: PSP after the PlayStation ({[s[0] for s in GM.GAME_SYSTEMS]}), a disc system, drawn in 3D, "
      f"with sticks, its own files", [s[0] for s in GM.GAME_SYSTEMS].index("psp")
      == [s[0] for s in GM.GAME_SYSTEMS].index("ps1") + 1
      and GM.DISC_SYSTEMS[:2] == ("ps1", "psp") and "psp" in GM.NEEDS_3D and "psp" in GM.ANALOG_SYSTEMS
      and "psp" in GM.OWN_FILES and GM.system("psp")[1:4] == ("PSP", "PlayStation Portable", (".iso", ".cso", ".pbp", ".chd")))
check(f"...its files can be dropped on the web page ({[k for k in W.KINDS['games'] if k in ('.iso', '.cso', '.pbp', '.chd')]})",
      {".iso", ".cso", ".pbp", ".chd"} <= set(W.KINDS["games"]))
check(f"the PSP emulator is found ({GM.find_core('psp')})", GM.find_core("psp") == CORE)
found = GM.find_games()
names = sorted((x["title"], x["system"]) for x in found)
check(f"the list: PSP games, in their folder or not ({names})", names == sorted([
    ("Controller", "psp"), ("Cube", "psp"), ("Dvd Game (USA)", "psp"), ("No Boot (USA)", "psp"),
    ("Pbp Game (USA)", "ps1"), ("Psn Game (USA)", "psp"), ("Umd Cube (USA)", "psp"),
    ("Umd Cube Squeezed (USA)", "psp")]))
g.slow_pi = lambda: True
check(f"an older Pi: no PSP games at all ({sorted(x['title'] for x in GM.find_games())})",
      [x["title"] for x in GM.find_games()] == ["Pbp Game (USA)"])
g.slow_pi = lambda: False

# ---- the emulator's process ----------------------------------------------------------------------------------
spec = screen_as(16)
run = start(PSP + "/Umd Cube (USA).iso", resume=False)
check(f"a PSP game starts ({run.wait_started(30)}, {run.state}, {run.error!r})", run.state == "on")
check("...its frames reach a 16-bit screen: the green cube", until(lambda: green(frame(spec)).sum() > 15000, 15))
rgb = frame(spec)
check(f"...16:9 as the PSP's picture is (480x270): the screen's width, 360 rows in the middle ({lit(rgb)})",
      lit(rgb) == (60, 419, 0, 639))
check(f"...the cube's way up: its top half greener than its bottom? the picture not upside down "
      f"(the PSP's own grey-blue at the top: {rgb[70, 320].tolist()})", rgb[70, 320].tolist() != [0, 0, 0]
      and abs(int(rgb[70, 320][2]) - int(rgb[70, 320][0])) > 10)
sysdir = S + "/cache/games/psp"
check(f"...its own files: the PSP's fonts beside the emulator, linked from the cache; Games/BIOS left alone "
      f"({os.readlink(sysdir + '/PPSSPP') if os.path.islink(sysdir + '/PPSSPP') else None})",
      os.path.realpath(sysdir + "/PPSSPP") == os.path.realpath(S + "/cores/PPSSPP")
      and os.listdir(GAMES + "/BIOS") == [])
check(f"...its memory stick is Games/Saves ({sorted(os.listdir(SAVES))})", os.path.isdir(SAVES + "/PSP"))
check("Save state", run.ask("save", ("saved", "error"), 20)[0] == "saved" and os.path.getsize(SAVES + "/Umd Cube (USA).state") > 30000000)
answer = run.ask("load", ("loaded", "nostate", "error"), 20)
check(f"Load state ({answer})", answer[0] == "loaded" and until(lambda: green(frame(spec)).sum() > 15000, 10))
for k in range(3):
    reset = run.ask("reset", ("reset",), 20)
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    drawn = until(lambda: green(frame(spec)).sum() > 15000, 15)
    time.sleep(0.5)
    if not (reset[0] == "reset" and drawn and not run.ended):
        break
check(f"Start over, three times (PPSSPP's own thread for the game stopped for it): on it goes from the start "
      f"({k + 1}, {reset}, drawn {drawn}, ended {run.ended})", k == 2 and reset[0] == "reset" and drawn and not run.ended)
paused = run.ask("pause", ("paused",), 10)
open(FBF, "wb").write(bytes(640 * 480 * 2))
time.sleep(0.8)
still = frame(spec).any()
resumed = run.ask("resume", ("resumed",), 10)
check(f"its menu up: it stops drawing ({paused}, drew {still}), then on it goes ({resumed})",
      paused[0] == "paused" and not still and resumed[0] == "resumed" and until(lambda: green(frame(spec)).sum() > 15000, 10))
check("quit: it ends, cleanly (no crash: PPSSPP told its OpenGL was going first), where it was kept",
      finish(run) and run.p.returncode == 0 and os.path.getsize(SAVES + "/Umd Cube (USA).state.auto") > 30000000)
run = start(PSP + "/Umd Cube (USA).iso")
check(f"...next time it picks up where you were ({run.wait_started(30)}, {run.resumed})", run.resumed
      and until(lambda: green(frame(spec)).sum() > 15000, 15))
check("...and ends cleanly again", finish(run) and run.p.returncode == 0)

spec = screen_as(32)
run = start(PSP + "/Umd Cube Squeezed (USA).cso", resume=False)
run.wait_started(30)
check("a .cso plays like the .iso, on a 32-bit screen", until(lambda: green(frame(spec)).sum() > 15000, 15)
      and lit(frame(spec)) == (60, 419, 0, 639))
run.send("picture Sharp")
time.sleep(0.8)
check(f"...Sharp: whole pixels only (480x270 in the middle: {lit(frame(spec))})", lit(frame(spec)) == (105, 374, 80, 559))
finish(run)

spec = screen_as(32, 1280, 720)
run = start(GAMES + "/Cube.iso", resume=False)
run.wait_started(30)
until(lambda: green(frame(spec)).sum() > 60000, 15)
check(f"a 720p screen: the chip makes it fill the screen, 16:9 as it is ({lit(frame(spec))})", lit(frame(spec)) == (0, 719, 0, 1279))
finish(run)
spec = screen_as(32, 1920, 1080)
run = start(GAMES + "/Cube.iso", resume=False)
run.wait_started(30)
until(lambda: green(frame(spec)).sum() > 120000, 15)
check(f"...a 1080p one: four times over, the whole screen ({lit(frame(spec))})", lit(frame(spec)) == (0, 1079, 0, 1919))
finish(run)

spec = screen_as(16)
run = start(PSP + "/No Boot (USA).iso", resume=False)
run.wait_started(30)
ended = until(lambda: run.ended, 15)
check(f"a disc with no game on it: it says it didn't start, and ends cleanly ({run.error!r})",
      ended and run.error == "This game didn't start" and run.p.returncode == 0
      and not os.path.exists(SAVES + "/No Boot (USA).state.auto"))
run = start(PSP + "/Not A Game.iso", resume=False)
run.wait_started(30)
ended = until(lambda: run.ended, 15)
check(f"...plain bytes named .iso: it didn't start either ({run.error!r})", ended
      and run.error == "This game didn't start" and run.p.returncode == 0)

# the buttons and the stick reach the game: PSPSDK's controller sample writes what it's given
run = start(PSP + "/Controller.pbp", resume=False)
run.wait_started(30)
until(lambda: frame(spec).any(), 15)
time.sleep(0.5)


def text_rows():
    rgb = frame(spec)
    return rgb.any(-1).sum(1)


rest = text_rows()
run.press("b"); time.sleep(0.5)
cross = frame(spec)
run.release("b"); time.sleep(0.3)
run.press("a"); time.sleep(0.5)
circle = frame(spec)
run.release("a"); time.sleep(0.3)
check(f"the controller sample: Cross held (libretro's B) is written on its screen, then Circle (A) in its place "
      f"({int(rest.sum())} -> {int(cross.any(-1).sum())} lit, Circle {'different' if (circle != cross).any() else 'the same'})",
      int(cross.any(-1).sum()) > int(rest.sum()) + 100 and (circle != cross).any())
run.send("stick lx 127"); time.sleep(0.5)
pushed = frame(spec)
run.send("stick lx 0"); time.sleep(0.5)
back = frame(spec)
run.send("stick lx -127"); time.sleep(0.5)
other = frame(spec)
run.send("stick lx 0"); time.sleep(0.5)
check("...the left stick is the PSP's: where it's pushed is written on its screen, both ways",
      (pushed != back).any() and (other != back).any() and (pushed != other).any())
run.p.send_signal(signal.SIGTERM)
check("stopped (the Pi going off): it keeps your place and ends cleanly", until(lambda: run.ended, 15)
      and run.p.returncode == 0 and os.path.getsize(SAVES + "/Controller.state.auto") > 30000000)

# ---- PPSSPP's own thread, given a hard time --------------------------------------------------------------------
storms = []
for seed in (1, 2, 3, 4):
    try:
        out = subprocess.run([sys.executable, SP + "/psp/storm.py", CORE, PSP + "/Umd Cube (USA).iso", sysdir, SAVES,
                              str(seed)], capture_output=True, text=True, timeout=150)
        storms.append((out.returncode, [ln for ln in out.stdout.splitlines() if ln.startswith(("storm", "the em"))]))
    except subprocess.TimeoutExpired:
        storms.append(("stuck", []))
check(f"its own thread for the game, given a hard time: frames, states made and put back, start overs and pauses "
      f"in any order, then a state and straight out: never stuck, never a crash ({storms})",
      all(rc == 0 and out and out[-1].startswith("storm ok") for rc, out in storms))

# ---- in this process: the log in words, the links put right -----------------------------------------------------
err = io.StringIO()
with contextlib.redirect_stderr(err):
    core = E.Core(CORE, PSP + "/No Boot (USA).iso", (".iso",), S + "/saves", "t", sysdir, lambda *a: None)
    while not core.quit:
        core.run()
    core.close()
said = [ln for ln in err.getvalue().splitlines() if "the emulator says" in ln]
check(f"the log: what PPSSPP says, in words, its printf filled in ({said[-1] if said else None!r})",
      any("[BOOT] PPSSPP v1.20.4" in ln for ln in said) and any("couldn't be found" in ln for ln in said)
      and not any("%s" in ln for ln in said))
c = types.SimpleNamespace(logged=0)
with contextlib.redirect_stderr(io.StringIO()) as many:
    for k in range(E.LOG_MOST + 50):
        E.Core.log(c, 2, b"[G3D] again %d", k, 0, 0, 0, 0, 0)
lines = many.getvalue().splitlines()
check(f"...a game that goes on and on: {E.LOG_MOST} lines, then one to say so ({len(lines)}: {lines[-1]!r})",
      len(lines) == E.LOG_MOST + 1 and "again 0" in lines[0] and "no more" in lines[-1])
os.remove(sysdir + "/PPSSPP")
os.symlink(S + "/gone/PPSSPP", sysdir + "/PPSSPP")
GM.psp_files(sysdir, CORE)
check("its files' link, left pointing nowhere (the emulator moved): put right", os.path.realpath(sysdir + "/PPSSPP")
      == os.path.realpath(S + "/cores/PPSSPP"))

# ---- pictures, by a PSP game's code ---------------------------------------------------------------------------------
os.makedirs(g.CACHE_DIR + "/games", exist_ok=True)
shutil.copy(f"{SP}/art/Sony - PlayStation Portable.dat", f"{g.CACHE_DIR}/games/Sony - PlayStation Portable.dat")
psp = GM.GameList("psp"); psp.load()
check(f"Redump's PSP list: {len(psp.names)} games, {len(psp.by_code)} codes", len(psp.names) > 3000 and "ULUS-10041" in psp.by_code)
hits = [GM.which_game({"path": PSP + "/" + n, "system": "psp"}, [psp]) for n in ("Umd Cube (USA).iso", "Umd Cube Squeezed (USA).cso")]
check(f"a UMD known by its code, an .iso or a .cso, whatever its file's called ({hits})",
      all(h and h[0] == "psp" and h[1].startswith("Grand Theft Auto - Liberty City Stories (USA)") for h in hits))
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
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
    b = io.BytesIO(); Image.new("RGB", (300, 170), colour).save(b, "PNG"); return b.getvalue()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Library)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
g.GAME_LISTS = base + "/lists/{kind}/{system}.dat"
g.ART_SOURCES = (base + "/server/{system}/{kind}/{name}.png",)
os.remove(f"{g.CACHE_DIR}/games/Sony - PlayStation Portable.dat")          # (not kept: it's asked for)
SERVED["/lists/redump/Sony - PlayStation Portable.dat"] = (
    b'clrmamepro (\n)\ngame (\n\tname "Liberty Test (USA)"\n\tserial "ULUS-10041"\n)\n')
SERVED["/server/Sony - PlayStation Portable/Named_Boxarts/Liberty Test (USA).png"] = png((30, 120, 220))
finder = GM.ArtFinder()
finder.start([x for x in GM.find_games() if x["title"] in ("Umd Cube (USA)", "Controller")])
until(lambda: not finder.busy, 60)
imgs = sorted(os.listdir(GAMES + "/Images")) if os.path.isdir(GAMES + "/Images") else []
check(f"Y: a picture for a PSP game, by its code ({finder.note!r}, {imgs})", imgs == ["Umd Cube (USA).png"]
      and "/lists/redump/Sony - PlayStation Portable.dat" in ASKED and not any("no-intro" in a for a in ASKED))
srv.shutdown()

# ---- media mode ------------------------------------------------------------------------------------------------
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


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.tab = m.tab_index("games"); m.view = "list"; m.load_tab(m.tab)
rows = {r["title"]: r for r in m.tab_items()}
check(f"the Games list: PSP games, badged ({rows['Umd Cube (USA)']['icon']}, {rows['Umd Cube (USA)']['sub']!r})",
      (rows["Umd Cube (USA)"]["icon"], rows["Umd Cube (USA)"]["sub"]) == ("PSP", "PlayStation Portable"))
m.dirty = True; m.flush()
check("...drawn", m.fb.last is not None)
g.slow_pi = lambda: True
m.load_tab(m.tab)
titles = [r["title"] for r in m.tab_items()]
check(f"an older Pi: not shown ({titles}), and in Files a PSP game is just a file",
      not any(t in titles for t in ("Umd Cube (USA)", "Cube", "Controller")) and m.game_system(PSP + "/Controller.pbp") is None)
g.slow_pi = lambda: False
m.load_tab(m.tab)
m.sels[m.tab] = [r["title"] for r in m.tab_items()].index("Umd Cube (USA)")
spec = screen_as(16)
m.press("a")
check(f"a Pi 4 or 5: it starts ({m.view})", m.view == "game" and m.game is not None and m.game.wait_started(30))
check(f"...buttons by place, as a PlayStation's: the bottom one is Cross (libretro's B) "
      f"({[m.game_button(n) for n in ('a', 'b', 'x', 'y', 'l', 'r', 'start', 'up')]})",
      [m.game_button(n) for n in ("a", "b", "x", "y", "l", "r", "start", "up")]
      == ["b", "a", "y", "x", "l", "r", "start", "up"])
check("...it takes the sticks as they are", m.game_sticks())
m.game_end()
check("...ended", m.game is None and m.view == "list")
m.game = types.SimpleNamespace(game={"system": "psp", "path": "x", "title": "x"}, sent=[],
                               send=lambda line: m.game.sent.append(line) or True,
                               stick=lambda axis, value, port=0: m.game.sent.append(f"stick {axis} {value}") or True)
m.view = "game"


class Pad:
    def __init__(self, stick):
        self.down, self.stick_ = set(), stick

    def has_stick(self):
        return self.stick_

    def has_button(self, name):
        return name != "l2"


hat = Pad(False)
hat.down = {"left"}
check(f"...a pad with no stick: the d-pad stays the PSP's d-pad, L stays L ({m.game_pad_button(hat, 'left')}, "
      f"{m.game_pad_button(hat, 'l')}, sent {m.game.sent})",
      m.game_pad_button(hat, "left") == "left" and m.game_pad_button(hat, "l") == "l" and m.game.sent == [])
m.game = None; m.view = "list"

for r in runs:
    if not r.ended:
        r.quit()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
