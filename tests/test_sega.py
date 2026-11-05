"""Sega games (Genesis / Mega Drive, Master System, Game Gear) and two players: which files are which (a Genesis .bin
by what's in it or the folder it's in, a PlayStation disc's .bin not taken for one, a Markdown .md not taken for a
Mega Drive game, zips), the real Genesis Plus GX playing tiny test games of our own (two players on a Genesis, each
on a port of their own; a zipped game, its README skipped), each controller's player in media mode, setup.sh, the
web page (a .md that's a game goes to Games, one that's text to Documents) and the README."""
import asyncio, io, json, os, shutil, socket, sys, threading, time, zipfile
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
from pitato import games as GM

S = SP + "/t_sega"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/tmp")
os.environ["TMPDIR"] = S + "/tmp"                       # (the emulator's unzipped games: here, not in /tmp)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
for d in ("genesis", "sms", "gg", "ps1", "Sega Genesis", "Saves", "BIOS"):
    os.makedirs(f"{GAMES}/{d}")
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{HOME}/{d}")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
g.home_dir = lambda: HOME
g.CACHE_DIR = S + "/cache"; g.STATE_FILE = S + "/state.json"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
CORES = SP + "/sega/cores"
GEN = open(SP + "/sega/Pitato Sega Test (World).md", "rb").read()
SMS = open(SP + "/sega/Pitato SMS Test (World).sms", "rb").read()
GG = open(SP + "/sega/Pitato GG Test (World).gg", "rb").read()
PS1 = SP + "/ps1/prog/out"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def put(rel, data):
    path = f"{GAMES}/{rel}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)
    return path


def zipped(rel, members):
    path = f"{GAMES}/{rel}"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    return path


# ---- the consoles -----------------------------------------------------------------------------------------------------
keys = [s[0] for s in GM.GAME_SYSTEMS]
check(f"three Sega consoles, after the SNES ({keys})", keys[:8] == ["gb", "gbc", "gba", "nes", "snes", "genesis", "sms",
                                                                     "gg"])
check("...their names and files", GM.system("genesis")[1:4] == ("MD", "Genesis / Mega Drive", (".md", ".gen", ".smd",
                                                                                                ".bin"))
      and GM.system("sms")[2:4] == ("Master System", (".sms",)) and GM.system("gg")[2:4] == ("Game Gear", (".gg",)))
check("...Genesis Plus GX plays them, from Debian's package", [GM.system(k)[4][0] for k in ("genesis", "sms", "gg")]
      == ["genesis_plus_gx"] * 3 and GM.GAME_PACKAGES["genesis_plus_gx"] == "libretro-genesisplusgx")
check("...two play a Genesis or a Master System game (a Game Gear: one)", GM.GAME_PLAYERS.get("genesis") == 2
      and GM.GAME_PLAYERS.get("sms") == 2 and GM.GAME_PLAYERS.get("gg", 1) == 1)
check("...their pictures under libretro's names", GM.LIBRETRO_NAMES["genesis"] == "Sega - Mega Drive - Genesis"
      and GM.LIBRETRO_NAMES["sms"] == "Sega - Master System - Mark III" and GM.LIBRETRO_NAMES["gg"] == "Sega - Game Gear")
check(".bin isn't taken for a cartridge by its name alone", ".bin" not in GM.GAME_EXTS and GM.GAME_EXTS[".md"] == "genesis"
      and GM.GAME_EXTS[".gen"] == "genesis" and GM.GAME_EXTS[".smd"] == "genesis" and GM.GAME_EXTS[".sms"] == "sms"
      and GM.GAME_EXTS[".gg"] == "gg")

# ---- which files are which ----------------------------------------------------------------------------------------------
noheader = bytearray(GEN)
noheader[0x100:0x110] = b"\0" * 16                 # (a Genesis game with nothing in its header)
files = {
    "genesis/Sonic Test.md": GEN, "Alpha (USA).gen": GEN, "Beta (Europe).smd": GEN,
    "Gamma (Japan).bin": GEN,                                  # SEGA in its header: a Genesis game, wherever it is
    "genesis/Delta (USA).bin": bytes(noheader),                # nothing in its header, but in the Genesis folder
    "Sega Genesis/Epsilon (USA).bin": bytes(noheader),         # ...a folder by another of its names
    "Zeta (USA).bin": bytes(noheader),                         # nothing to say it's one: not a game
    "sms/Master Test.sms": SMS, "gg/Gear Test.gg": GG,
    "README.md": b"# My games\n\nGenesis games go in genesis.\n",
    "genesis/notes.md": "Notes: éè\n".encode(),
}
paths = {k: put(k, v) for k, v in files.items()}
shutil.copy(f"{PS1}/Solo Test (USA).bin", f"{GAMES}/ps1/Solo Test (USA).bin")
shutil.copy(f"{PS1}/Solo Test (USA).cue", f"{GAMES}/ps1/Solo Test (USA).cue")
shutil.copy(f"{PS1}/Test Game (USA) (Disc 1).bin", f"{GAMES}/Loose Disc (USA).bin")    # a PlayStation .bin on its own
with open(f"{GAMES}/Huge (USA).bin", "wb") as f:          # SEGA where a Genesis game has it, but a disc's size
    f.write(GEN[:0x200]); f.truncate(40 << 20)
zips = {
    "Readme First (USA).zip": [("README.md", b"# Read me\n"), ("Readme First (USA).gen", GEN)],
    "Bin Inside (USA).zip": [("Bin Inside (USA).bin", GEN)],
    "Only Notes.zip": [("notes.md", b"just words\n")],
    "Master Zip (USA).zip": [("Master Zip (USA).sms", SMS)],
}
for k, v in zips.items():
    zipped(k, v)
bad = zipped("Damaged (USA).zip", [("Damaged (USA).md", GEN)])
raw = bytearray(open(bad, "rb").read())
raw[60:400] = b"\xff" * 340                            # (its directory as it was, the game inside it garbled)
open(bad, "wb").write(bytes(raw))
kind = lambda rel: GM.game_kind(f"{GAMES}/{rel}", GAMES)
check("Genesis games by their files: .md, .gen, .smd", [kind(k) for k in ("genesis/Sonic Test.md", "Alpha (USA).gen",
                                                                            "Beta (Europe).smd")] == ["genesis"] * 3)
check("a .bin with SEGA in its header: a Genesis game, wherever it is", kind("Gamma (Japan).bin") == "genesis")
check("...one with nothing in its header: a Genesis game in a Genesis folder (by any of its names)",
      kind("genesis/Delta (USA).bin") == "genesis" and kind("Sega Genesis/Epsilon (USA).bin") == "genesis")
check(f"...and not a game anywhere else ({kind('Zeta (USA).bin')})", kind("Zeta (USA).bin") is None)
check(f"a PlayStation disc's .bin isn't a Genesis game ({kind('Loose Disc (USA).bin')}, "
      f"{kind('ps1/Solo Test (USA).cue')})", kind("Loose Disc (USA).bin") == "ps1"
      and kind("ps1/Solo Test (USA).cue") == "ps1" and kind("ps1/Solo Test (USA).bin") != "genesis")
check("...nor is one a disc's size, whatever it says", kind("Huge (USA).bin") != "genesis")
check("Master System and Game Gear games", kind("sms/Master Test.sms") == "sms" and kind("gg/Gear Test.gg") == "gg")
check("a Markdown .md (a README beside the games) isn't a game", kind("README.md") is None
      and kind("genesis/notes.md") is None and GM.markdown("x.md", b"# hi\n") and not GM.markdown("x.md", GEN)
      and not GM.markdown("x.gen", b"text"))
check(f"zips: a game in one, a README before it skipped ({kind('Readme First (USA).zip')}); a .bin by its header; "
      f"notes alone, nothing", kind("Readme First (USA).zip") == "genesis" and kind("Bin Inside (USA).zip") == "genesis"
      and kind("Only Notes.zip") is None and kind("Master Zip (USA).zip") == "sms")
import zlib
crc = "%08X" % (zlib.crc32(GEN) & 0xFFFFFFFF)
check(f"its picture's found by the game's checksum, not the README's ({GM.game_crcs(GAMES + '/Readme First (USA).zip', 'genesis')})",
      GM.game_crcs(GAMES + "/Readme First (USA).zip", "genesis") == [crc]
      and GM.game_crcs(paths["Alpha (USA).gen"], "genesis") == [crc])
try:
    got = (kind("Damaged (USA).zip"), GM.game_crcs(bad, "genesis"))
except Exception as ex:
    got = repr(ex)
check(f"a damaged zip: not a game, and nothing goes wrong looking ({got})", got == (None, []))
found = {x["title"]: x["system"] for x in GM.find_games(GAMES)}
want = {"Sonic Test": "genesis", "Alpha (USA)": "genesis", "Beta (Europe)": "genesis", "Gamma (Japan)": "genesis",
        "Delta (USA)": "genesis", "Epsilon (USA)": "genesis", "Master Test": "sms", "Gear Test": "gg",
        "Readme First (USA)": "genesis", "Bin Inside (USA)": "genesis", "Master Zip (USA)": "sms",
        "Solo Test (USA)": "ps1", "Loose Disc (USA)": "ps1"}
check(f"the Games tab's list: each once, as what it is ({len(found)} games)",
      {k: v for k, v in found.items() if k in want} == want and "README" not in found and "notes" not in found
      and "Zeta (USA)" not in found and "Only Notes" not in found)

# ---- the real Genesis Plus GX -----------------------------------------------------------------------------------------
FBF = S + "/fb.bin"
W, H = 640, 480
os.environ["PITATO_FB"] = f"{FBF}:{W}x{H}:16"
open(FBF, "wb").write(bytes(W * H * 2))


def px():
    a = int(np.fromfile(FBF, dtype="<u2").reshape(H, W)[240, 320])
    return (((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3)


def colour():
    r, gr, b = px()
    return {(True, False, False): "red", (False, True, False): "green", (False, False, True): "blue",
            (True, True, False): "yellow", (False, False, False): "black"}.get((r > 128, gr > 128, b > 128), str(px()))


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


have_core = os.path.exists(CORES + "/genesis_plus_gx_libretro.so")
if have_core:
    g.CORE_DIRS = (CORES,)
    check("its emulator found", GM.find_core("genesis") and GM.find_core("sms") and GM.find_core("gg"))

    def play(rel, sysk):
        run = GM.GameRun({"path": f"{GAMES}/{rel}", "title": rel, "system": sysk})
        run.start(GM.find_core(sysk), sound="", volume=80, picture="Fit", resume=False)
        return run

    run = play("genesis/Sonic Test.md", "genesis")
    check("a Genesis game starts", run.wait_started(20))
    check(f"...its picture: blue ({colour()})", until(lambda: colour() == "blue"))
    run.press("b")
    check(f"player 1 holds B: red ({colour()})", until(lambda: colour() == "red"))
    run.press("b", 1)
    check(f"...player 2 too: yellow ({colour()})", until(lambda: colour() == "yellow"))
    run.release("b")
    check(f"...player 2 alone: green ({colour()})", until(lambda: colour() == "green"))
    run.release("b", 1)
    check(f"...neither: blue ({colour()})", until(lambda: colour() == "blue"))
    run.press("b", 1); run.press("b")
    check("its menu (paused): both let go", until(lambda: colour() == "yellow") and run.pause())
    run.resume()
    check(f"...back: still let go ({colour()})", until(lambda: colour() == "blue"))
    run.quit()
    for rel, sysk in (("sms/Master Test.sms", "sms"), ("gg/Gear Test.gg", "gg")):
        open(FBF, "wb").write(bytes(W * H * 2))
        run = play(rel, sysk)
        check(f"a {GM.system(sysk)[2]} game: its picture red ({run.wait_started(20) and until(lambda: colour() == 'red')}"
              f", {colour()})", colour() == "red")
        run.quit()
    os.makedirs(S + "/tmp/pitato-game-999999-left")     # (an emulator long gone left this)
    for rel in ("Readme First (USA).zip", "genesis/Delta (USA).bin", "Bin Inside (USA).zip"):
        open(FBF, "wb").write(bytes(W * H * 2))
        run = play(rel, "genesis")
        ok = run.wait_started(20) and until(lambda: colour() == "blue")
        run.press("b")
        check(f"{rel}: plays ({colour()}{', ' + run.error if run.error else ''})",
              ok and until(lambda: colour() == "red"))
        if rel.endswith(".zip"):
            mine = [n for n in os.listdir(S + "/tmp") if n.startswith(f"pitato-game-{run.p.pid}-")]
            check(f"...unzipped into a folder of its own while it plays ({mine}); the one left behind gone "
                  f"({sorted(os.listdir(S + '/tmp'))})", len(mine) == 1 and "pitato-game-999999-left" not in
                  os.listdir(S + "/tmp"))
        run.quit()
    check(f"...and theirs gone as they end ({os.listdir(S + '/tmp')})", os.listdir(S + "/tmp") == [])
else:
    print("(no Genesis Plus GX here: its part skipped)")

# ---- each controller's player, in media mode ---------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


class Dev:
    def __init__(self, name):
        self.name = name


class Pad:
    """Just what media mode asks of a controller here."""
    n = 0

    def __init__(self, name, stick=True):
        Pad.n += 1
        self.path, self.dev, self.down, self.stick = f"/dev/input/event{60 + Pad.n}", Dev(name), set(), stick

    def has_stick(self):
        return self.stick

    def has_button(self, name):
        return True

    def sticks_now(self):
        return []


class Pads:
    def __init__(self, *pads):
        self.by_path = {p.path: p for p in pads}


class Run:
    """A game, as media mode sees it: what it was sent."""
    def __init__(self, sysk):
        self.game, self.sent, self.state, self.disc, self.slow = {"system": sysk, "title": "t", "path": "/x"}, [], "on", (0, 1), False
        self.ended, self.error = False, ""
        self.cheevos = None                     # (no achievements, as a real game without them)

    def press(self, name, port=0): self.sent.append(("down", name, port))
    def release(self, name, port=0): self.sent.append(("up", name, port))
    def stick(self, axis, value, port=0): self.sent.append(("stick", axis, value, port))
    def pause(self): self.state = "paused"; return True
    def resume(self): self.state = "on"
    def send(self, line): self.sent.append(("line", line))
    def quit(self): self.ended = True


g.Framebuffer = FB
g.screen_picture = lambda *a, **k: None
import subprocess
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
m = g.Media(); m.enter()
a, b, c, d = Pad("8BitDo SN30 Pro"), Pad("Xbox Wireless Controller"), Pad("USB Gamepad", stick=False), Pad("Pro Controller")
m.pads = Pads(a, b, c, d)


def start(sysk, used=None):
    m.game, m.view = Run(sysk), "game"
    m.game_players = {used.path: 0} if used is not None else {}
    return m.game


def push(pad, name, down=True):
    m.input_pad = pad
    try:
        (m.press if down else m.release)(name)
    finally:
        m.input_pad = None


run = start("genesis", used=a)
push(a, "b"); push(a, "b", False)
check("the controller that started it: player 1", run.sent == [("down", "b", 0), ("up", "b", 0)])
push(b, "a")
check("the next one pressed: player 2", run.sent[-1] == ("down", "a", 1) and m.game_players[b.path] == 1)
push(b, "a", False)
push(c, "start")
check("a third, on a game for two: nothing", run.sent[-1] == ("up", "a", 1) and c.path not in m.game_players)
push(c, "start", False)
check("...its button let go: nothing either", run.sent[-1] == ("up", "a", 1))
push(None, "b"); push(None, "b", False)
check("the web page's remote: player 1", run.sent[-2:] == [("down", "b", 0), ("up", "b", 0)])
check(f"its menu says who's playing ({m.game_value('players')}, {m.game_player_names()})",
      m.game_value("players") == "2 of 2" and m.game_player_names() == [(1, "8BitDo SN30 Pro"),
                                                                      (2, "Xbox Wireless Controller")])
del m.pads.by_path[b.path]                      # (player 2's controller unplugged)
push(c, "x")
check("player 2's unplugged: the next one pressed takes their place", run.sent[-1] == ("down", "x", 1)
      and m.game_players[c.path] == 1)
push(c, "x", False)
m.pads.by_path[b.path] = b
push(b, "a")
check("...plugged in again: a newcomer (no place left for it)", run.sent[-1] == ("up", "x", 1)
      and b.path not in m.game_players)
push(b, "a", False)
m.view = "gamemenu"
m.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": None}
items = [k for k, _ in m.game_menu_items()]
check(f"its menu: Players, for a game two can play ({items})", "players" in items)
m.game_do("players")
check(f"Players: picked again ({m.msg})", m.game_players == {} and m.msg ==
      "Back in the game, press a button on each controller: player 1 first")
m.view = "game"
push(d, "y"); push(d, "y", False); push(a, "y")
check("...the first to press is player 1 now, the next player 2", run.sent[-3:] == [("down", "y", 0), ("up", "y", 0),
                                                                                    ("down", "y", 1)])
run = start("gg", used=a)
push(b, "a"); push(c, "a"); push(d, "a")
check("a Game Gear game (one player): every controller works it", run.sent == [("down", "a", 0)] * 3)
m.view = "gamemenu"
check("...no Players in its menu", "players" not in [k for k, _ in m.game_menu_items()])
m.view = "game"
run = start("n64", used=a)
for p in (b, c, d):
    push(p, "a")
check("an N64 game: four players", [x[2] for x in run.sent] == [1, 2, 3] and m.game_value("players") == "4 of 4")
m.game_stick("lx", 90, pad=d)
check("...each one's stick is theirs", run.sent[-1] == ("stick", "lx", 90, 3))
c.down = {"right"}
check("...a controller with no stick: its d-pad is its stick", m.game_pad_button(c, "right") is None
      and run.sent[-1] == ("stick", "lx", 127, 2))
run = start("n64", used=None)
m.game_stick("lx", 3, pad=b); m.game_stick("ly", -2, pad=c)
check("a stick at rest (a little off the middle) doesn't make anyone a player", m.game_players == {}
      and not run.sent)
m.game_stick("lx", 100, pad=c)
check("...pushed: a player", m.game_players == {c.path: 0} and run.sent == [("stick", "lx", 100, 0)])
run = start("snes", used=None)
m.game_stick("lx", 0, pad=a)
check("a stick let go of doesn't make anyone a player", a.path not in m.game_players and not run.sent)
push(a, "l")
check("nobody started it from a controller: the first pressed is player 1", run.sent == [("down", "l", 0)])
m.game = None
m.view = "list"
opened = []
m.game_open = lambda it: opened.append(("game", it["src"], it.get("system")))
m.open_text = lambda src, text=None: opened.append(("text", src, None))
files = [g.item(paths["genesis/Sonic Test.md"], "Sonic Test", g.classify(paths["genesis/Sonic Test.md"]),
                paths["genesis/Sonic Test.md"]),
         g.item(paths["README.md"], "README", g.classify(paths["README.md"]), paths["README.md"])]
m.open_item(files, 0); m.open_item(files, 1)
check(f"Files: a .md that's a Mega Drive game plays, one that's text reads ({opened})",
      opened == [("game", paths["genesis/Sonic Test.md"], "genesis"), ("text", paths["README.md"], None)])
del m.game_open, m.open_text
if have_core:
    gi = m.tab_index("games")
    m.load_tab(gi)
    if any(it["kind"] == "gamedir" for it in m.tab_items(gi)):   # (more than a dozen: into the Genesis folder first)
        m.games_open_dir(next(it for it in m.tab_items(gi) if it["src"] == "sys:genesis"))
    row = next(it for it in m.tab_items(gi) if it["src"] == paths["genesis/Sonic Test.md"])
    m.input_pad = c                                    # (A pressed on this one)
    m.game_open(row)
    m.input_pad = None
    check("a game started from a controller: that one's player 1", m.game is not None and m.game.wait_started(20)
          and m.game_players == {c.path: 0})
    m.game_end()
    m.pad_used = a                                     # (the controller pressed last, a while ago)
    m.game_open(row)                                   # (from the web page: no controller pressed)
    check("...from the web page: nobody's player 1 till a controller's pressed", m.game is not None
          and m.game_players == {})
    m.game_end()

# ---- setup.sh, the web page's kinds, and the README --------------------------------------------------------------------
sh = open(ROOT + "/setup.sh").read()
check("setup.sh: Genesis Plus GX with the other ready-made emulators",
      "for pkg in libretro-mgba libretro-nestopia libretro-snes9x libretro-genesisplusgx; do" in sh)
check("...folders for them", 'GAME_FOLDERS="gb gbc gba nes snes genesis sms gg ngp ngpc neogeo ps1"' in sh)
sys.path.append(ROOT + "/pitato")
import webui
check("the web page takes them as games", all(x in webui.KINDS["games"] for x in (".md", ".gen", ".smd", ".sms", ".gg",
                                                                                  ".bin")))
readme = "\n".join(open(f).read() for f in [ROOT + "/README.md"] + sorted(__import__("glob").glob(ROOT + "/docs/*.md")))
flat = " ".join(readme.split())
check("README and docs/: the consoles, their folders, their emulator, two players",
      "SNES, Genesis, Master System, Game Gear, Neo Geo, Neo Geo Pocket and PlayStation games" in flat and "`genesis`, `sms`, `gg`" in flat
      and "Genesis Plus GX" in flat and "the next one to press a button is player 2" in flat
      and "start over, the players, the volume" in flat)
low = readme.lower()
check("...and nothing it doesn't play", not any(w in low for w in ("pcsx2", "sega cd", "32x"))
      and low.count("intel") == low.count("amd") == 1 and "regular computer (intel or amd) with ubuntu" in " ".join(low.split()))

# ---- the web page: a .md that's a game goes to Games ---------------------------------------------------------------------
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
if async_playwright is not None:
    webui.HOME = HOME; webui.STATIC = S + "/pitato/static"; os.makedirs(webui.STATIC + "/fonts")
    for f in os.listdir(ROOT + "/static/fonts"):
        shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
    webui.FONTS_DIR = webui.STATIC + "/fonts"
    webui.THUMBS = HOME + "/.cache/pitato/thumbs"; webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
    import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
    threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5461, threaded=True), daemon=True).start()
    time.sleep(1)

    async def page_side():
        async with async_playwright() as pw:
            br = await pw.chromium.launch()
            pg = await br.new_page()
            await pg.goto("http://127.0.0.1:5461/")
            await pg.wait_for_function("() => typeof S !== 'undefined' && S.info && S.info.kinds", timeout=15000)
            out = await pg.evaluate("""async (rom) => {
              const mk = (name, bytes) => ({ file: new File([new Uint8Array(bytes)], name), rel: name });
              const text = (s) => Array.from(new TextEncoder().encode(s));
              const list = [mk("Sonic.md", rom), mk("notes.md", text("# Notes\\n\\nwords")), mk("Alpha.gen", rom),
                            mk("Master.sms", rom.slice(0, 1024)), mk("song.mp3", [1, 2, 3])];
              await sniff(list);
              S.dest = "auto";
              return plan(list, null).map((j) => [j.path, j.folder]);
            }""", list(GEN[:2048]))
            await br.close()
            return out

    try:
        got = dict(asyncio.run(page_side()))
    except Exception as ex:
        got = {"error": repr(ex)}
    check(f"the web page: a .md that's a game to Games, Markdown to Documents ({got})",
          got.get("Sonic.md") == "games" and got.get("notes.md") == "documents" and got.get("Alpha.gen") == "games"
          and got.get("Master.sms") == "games" and got.get("song.mp3") == "music")
else:
    print("(no Playwright here: the web page's part skipped)")

m.leave()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
