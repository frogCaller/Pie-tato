"""PlayStation 2, GameCube and Wii games, on a PC alone: their discs told apart and listed on a PC (not on a Pi), their
emulators found (Dolphin, LRPS2: built as setup.sh builds them), a PS2's BIOS looked for in Games/BIOS and linked where
LRPS2 looks, Dolphin's Sys linked where it looks; the emulator process giving them OpenGL ES first (what's here) and a
GameCube's triggers as how far they're pressed; a lone .bin given a .cue; and with the real Dolphin, a small GameCube
program of our own (a .dol) started, its picture read back from the graphics chip, saved, loaded and quit cleanly; a
picture left undrawn, then repeated, drawn then; and with the real LRPS2, a PS2 game with no BIOS for it stopping with
a reason, nothing left hanging, and with a little BIOS of our own: started on the graphics chip, saved, loaded, quit."""
import os, shutil, struct, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tpcgames"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
SAVES = GAMES + "/Saves"
for d in ("gc", "wii", "ps2", "BIOS", "Saves"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/cores"); os.makedirs(S + "/bin")
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
GM = sys.modules["pitato.games"]
E = sys.modules["pitato.emulator"]
D = sys.modules["pitato.discs"]
g.CACHE_DIR = S + "/cache"; g.home_dir = lambda: HOME
g.CORE_DIRS = (S + "/cores",)
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


# ---- discs of each kind (the disc test's own fakes), in their folders --------------------------------------------------
FAKES, OUT = SP + "/ps1/fakes", SP + "/ps1/prog/out"
for name, where in (("Cube Game (USA).iso", "gc"), ("Squeezed Cube (USA).gcz", "gc"), ("Remote Game (USA).iso", "wii"),
                    ("Remote Game Two (USA).wbfs", "wii"), ("Packed RVZ (USA).rvz", "wii"),
                    ("Fake PS2 Packed (USA).cso", "ps2")):
    shutil.copy(f"{FAKES}/{name}", f"{GAMES}/{where}/{name}")
shutil.copy(f"{OUT}/Fake PS2 Game (USA).iso", f"{GAMES}/ps2/Fake PS2 Game (USA).iso")
shutil.copy(f"{FAKES}/Chd Dvd (USA).chd", f"{GAMES}/ps2/Dvd In Ps2 (USA).chd")     # (a DVD .chd: its folder says)
shutil.copy(f"{FAKES}/Chd Dvd (USA).chd", f"{GAMES}/Dvd Loose (USA).chd")          # (...a PSP's, with no folder)
open(f"{GAMES}/Tiny (USA).gb", "wb").write(bytes(32768))

g.is_pc = lambda: True
on_pc = sorted((x["title"], x["system"]) for x in GM.find_games())
check(f"on a PC: the GameCube's, the Wii's and the PS2's, each kind of file, each where it is ({on_pc})", on_pc == sorted([
    ("Cube Game (USA)", "gc"), ("Squeezed Cube (USA)", "gc"), ("Remote Game (USA)", "wii"),
    ("Remote Game Two (USA)", "wii"), ("Packed RVZ (USA)", "wii"), ("Fake PS2 Packed (USA)", "ps2"),
    ("Fake PS2 Game (USA)", "ps2"), ("Dvd In Ps2 (USA)", "ps2"), ("Dvd Loose (USA)", "psp"), ("Tiny (USA)", "gb")]))
g.is_pc = lambda: False
on_pi = sorted((x["title"], x["system"]) for x in GM.find_games())
check(f"...on a Pi: none of them (a DVD .chd with no folder: still a PSP's) ({on_pi})",
      on_pi == [("Dvd Loose (USA)", "psp"), ("Tiny (USA)", "gb")])
g.is_pc = lambda: True
check("their badges, names, files and emulators", [GM.system(k)[1:3] for k in ("ps2", "gc", "wii")]
      == [("PS2", "PlayStation 2"), ("GC", "GameCube"), ("Wii", "Wii")]
      and GM.system("gc")[4] == ("dolphin",) and GM.system("wii")[4] == ("dolphin",) and GM.system("ps2")[4] == ("pcsx2",)
      and all(k in GM.NEEDS_3D and k in GM.ANALOG_SYSTEMS and k in GM.OWN_FILES for k in ("ps2", "gc", "wii"))
      and GM.GAME_PLAYERS["gc"] == 4 and GM.GAME_PLAYERS["wii"] == 4 and GM.GAME_PLAYERS["ps2"] == 2)
check(f"...their pictures' lists, and a GameCube's code as Redump writes it ({GM.code_key('DL-DOL-GALE-USA', 'gc')})",
      GM.LIBRETRO_NAMES["ps2"] == "Sony - PlayStation 2"
      and GM.LIBRETRO_NAMES["gc"] == "Nintendo - GameCube" and GM.LIBRETRO_NAMES["wii"] == "Nintendo - Wii"
      and GM.code_key("DL-DOL-GALE-USA", "gc") == "GALE" == GM.code_key("GALE01", "gc")
      and GM.code_key("SLUS_200.62", "ps2") == "SLUS-20062")

# ---- a PS2's BIOS, and the emulators' own files ------------------------------------------------------------------------
fake_core = S + "/cores/pcsx2_libretro.so"
check(f"no PS2 BIOS: said so ({GM.bios_missing(fake_core)!r})", GM.bios_missing(fake_core) == "the BIOS from your own PS2")


def ps2_rom(code=b"", names=(b"RESET", b"ROMDIR", b"ROMVER"), at=0x2700):
    """4 MB: a PS2 BIOS's shape. Its ROM's directory (RESET, ROMDIR, ROMVER: v1.60, USA, as LRPS2 reads it), and at
    its start (where the PS2's processors begin) the code given."""
    rom = bytearray(4 << 20)
    rom[0:len(code)] = code
    sizes = {b"RESET": at, b"ROMDIR": 0x40, b"ROMVER": 0x10}
    for k, name in enumerate(names):
        rom[at + k * 16:at + k * 16 + 16] = name.ljust(10, b"\0") + struct.pack("<HI", 0, sizes[name])
    if b"ROMVER" in names:
        rom[at + 0x40:at + 0x4E] = b"0160AC20030206"
    return bytes(rom)


bios = ps2_rom()
open(f"{GAMES}/BIOS/scph39001.bin", "wb").write(bios)
open(f"{GAMES}/BIOS/not-a-bios.bin", "wb").write(bytes(4 << 20))                 # (the right size, but not one)
open(f"{GAMES}/BIOS/no-version.bin", "wb").write(ps2_rom(names=(b"RESET", b"ROMDIR")))   # (RESET, but no ROMVER)
os.makedirs(f"{GAMES}/BIOS/ps2")
open(f"{GAMES}/BIOS/ps2/scph70012.bin", "wb").write(bios)
open(f"{GAMES}/BIOS/dc_boot.bin", "wb").write(bytes(2 << 20))                    # (another console's)
found = [os.path.relpath(p, GAMES) for p in GM.ps2_bios()]
check(f"...in Games/BIOS (or its ps2 folder): found, nothing else ({found}); fine now",
      found == ["BIOS/scph39001.bin", "BIOS/ps2/scph70012.bin"] and GM.bios_missing(fake_core) == "")
sysdir = S + "/cache/games/ps2"
GM.ps2_files(sysdir)
links = sorted(os.listdir(sysdir + "/pcsx2/bios"))
check(f"...linked where LRPS2 looks ({links})", links == ["scph39001.bin", "scph70012.bin"]
      and os.readlink(sysdir + "/pcsx2/bios/scph39001.bin") == f"{GAMES}/BIOS/scph39001.bin")
os.remove(f"{GAMES}/BIOS/ps2/scph70012.bin")
GM.ps2_files(sysdir)
check(f"...one gone: its link too ({sorted(os.listdir(sysdir + '/pcsx2/bios'))})",
      sorted(os.listdir(sysdir + "/pcsx2/bios")) == ["scph39001.bin"])
os.makedirs(S + "/cores/dolphin-emu/Sys/GameSettings")
GM.dolphin_files(S + "/cache/games/gc", S + "/cores/dolphin_libretro.so")
check("Dolphin's Sys: linked where it looks", os.readlink(S + "/cache/games/gc/dolphin-emu/Sys") == S + "/cores/dolphin-emu/Sys")

# ---- the emulator process: OpenGL ES first, a GameCube's triggers, a lone .bin ----------------------------------------
core = E.Core.__new__(E.Core)
core.library, core.buttons, core.sticks = "dolphin-emu", [0] * 4, [[0] * 4 for _ in range(4)]
want = E.C.c_int(0)
check("Dolphin and LRPS2 asked what drawing's best: OpenGL ES (what's here)",
      core.answer(56, E.C.addressof(want)) and want.value == 5)
core.library = "Flycast"
check("...another emulator: not asked (as before)", not core.answer(56, E.C.addressof(want)))
check("its own OpenGL context, shared: fine (a frame's read leaves its state as it was)", core.answer(44 | E.EXP, None))
core.buttons[0] = 1 << E.BUTTON_IDS["l2"]
check("a GameCube's L trigger, as how far it's pressed: all the way, or not at all",
      core.state(0, E.ANALOG, 2, E.BUTTON_IDS["l2"]) == 0x7FFF and core.state(0, E.ANALOG, 2, E.BUTTON_IDS["r2"]) == 0)
# a picture left undrawn (it was behind), then the same again (a dupe): that one drawn then, not none at all
seen = []
core.on_video, core.gpu, core.missed = (lambda a, fmt, aspect: seen.append((None if a is None else a.tolist(), fmt))), \
    object(), None
core.av, core.fmt = E.AVInfo(), E.FMT_RGB565
core.draw = False
core.video(E.ON_GPU, 640, 480, 0)
core.draw = True
core.video(None, 640, 480, 0)
core.video(None, 640, 480, 0)
pix = (E.C.c_uint16 * 4)(1, 2, 3, 4)
core.draw = False
core.video(E.C.addressof(pix), 2, 2, 4)
pix[0] = 9                                         # (the emulator's own pixels, changed since)
core.draw = True
core.video(None, 2, 2, 4)
core.video(E.C.addressof(pix), 2, 2, 4)
check(f"a picture left undrawn (it was behind), then the same again: drawn then, once ({seen})",
      seen == [(None, (640, 480)), ([[1, 2], [3, 4]], E.FMT_RGB565), ([[9, 2], [3, 4]], E.FMT_RGB565)])
raw = S + "/Raw Disc.bin"
open(raw, "wb").write(b"\x00" + b"\xff" * 10 + b"\x00" + bytes(4000))
cue = E.bin_cue(raw, S)
check(f"a disc's .bin alone: a .cue made for it ({open(cue).read().splitlines()[1].strip()!r})",
      open(cue).read() == f'FILE "{raw}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')

# ---- the real Dolphin: a small GameCube program of our own --------------------------------------------------------------
BUILT = SP + "/cores"
FBF = S + "/fb.bin"
os.environ["PITATO_FB"] = f"{FBF}:1280x720:32"
open(FBF, "wb").write(bytes(1280 * 720 * 4))
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]


def dol(path, words, entry=0x80003100):
    """A GameCube program (a .dol): words of PowerPC code, loaded at entry and started there."""
    code = b"".join(struct.pack(">I", w) for w in words)
    code += bytes(-len(code) % 32)
    head = bytearray(0x100)
    struct.pack_into(">I", head, 0x00, 0x100)          # its code: where it is in the file,
    struct.pack_into(">I", head, 0x48, entry)          # ...where it goes,
    struct.pack_into(">I", head, 0x90, len(code))      # ...how big
    struct.pack_into(">II", head, 0xD8, 0x80100000, 0)
    struct.pack_into(">I", head, 0xE0, entry)
    open(path, "wb").write(bytes(head) + code)


if os.path.isfile(BUILT + "/dolphin_libretro.so"):
    shutil.copy(BUILT + "/dolphin_libretro.so", S + "/cores/dolphin_libretro.so")
    shutil.rmtree(S + "/cores/dolphin-emu")
    shutil.copytree(BUILT + "/dolphin-src/Data/Sys", S + "/cores/dolphin-emu/Sys")
    check(f"the GameCube and Wii emulator found ({GM.find_core('gc')})", GM.find_core("gc") == S + "/cores/dolphin_libretro.so"
          and GM.find_core("wii") == GM.find_core("gc"))
    prog = f"{GAMES}/gc/Loop Test.dol"
    # its video set up (240 lines a field; its picture at 1 MB in, in both fields), that picture painted red (YUYV:
    # 51 5A 51 F0, 640 x 240), then round and round
    dol(prog, [0x3C60CC00, 0x60632000,               # r3 = 0xCC002000 (the video registers)
               0x38800F06, 0xB0830000,               # its vertical timing: 240 lines, 6 half-lines' pulse
               0x3C800010, 0x9083001C, 0x90830024,   # the top field's and the bottom's picture: 0x00100000
               0x3CA0C010, 0x3CC0515A, 0x60C651F0,   # r5 = 0xC0100000 (it, uncached), r6 = red, twice
               0x3CE00001, 0x60E72C00, 0x7CE903A6,   # 76800 words
               0x90C50000, 0x38A50004, 0x4200FFF8,   # each one red
               0x48000000])                          # (b .)
    run = GM.GameRun({"path": prog, "title": "Loop Test", "system": "gc"})
    t0 = time.monotonic()
    run.start(GM.find_core("gc"), sound="", volume=80, picture="Fit", resume=False)
    started = run.wait_started(120)
    check(f"a GameCube program starts in Dolphin ({started}, {run.state}, {run.error!r}, "
          f"{time.monotonic() - t0:.1f} s)", started and run.state == "on")
    time.sleep(4)
    shot = run.ask(f"shot {S}/shot.ppm", ("shot",), 30)
    px = None
    if shot == ("shot", "ok"):
        ppm = open(S + "/shot.ppm", "rb").read()
        head = ppm.split(b"\n", 3)
        pw, ph = (int(v) for v in head[1].split())
        mid = len(ppm) - pw * ph * 3 + ((ph // 2) * pw + pw // 2) * 3
        px = tuple(ppm[mid:mid + 3])
    check(f"...drawn by the graphics chip (OpenGL ES), its picture read back: red, as it painted it ({shot}, {px})",
          shot == ("shot", "ok") and px is not None and px[0] > 200 and px[1] < 60 and px[2] < 60 and not run.ended)
    saved = run.ask("save", ("saved", "error"), 120)
    state = f"{SAVES}/Loop Test.state"
    check(f"Save state ({saved}, {os.path.getsize(state) if os.path.isfile(state) else 0} bytes)",
          saved[0] == "saved" and os.path.getsize(state) > 1000000)
    loaded = run.ask("load", ("loaded", "nostate", "error"), 120)
    check(f"Load state ({loaded})", loaded[0] == "loaded" and not run.ended)
    check(f"...its own files: Dolphin's Sys linked in the cache, its User folder with your saves "
          f"({sorted(os.listdir(SAVES))})", os.path.islink(S + "/cache/games/gc/dolphin-emu/Sys")
          and os.path.isdir(SAVES + "/User"))
    run.quit(60)
    check(f"quit: it ends, cleanly ({run.p.returncode})", until(lambda: run.ended, 60) and run.p.returncode == 0)
else:
    check("the GameCube and Wii emulator: built (it isn't yet)", False)

# ---- the real LRPS2: a PS2 game with no BIOS it takes -------------------------------------------------------------------
if os.path.isfile(BUILT + "/pcsx2_libretro.so"):
    shutil.copy(BUILT + "/pcsx2_libretro.so", S + "/cores/pcsx2_libretro.so")
    check(f"the PS2 emulator found ({GM.find_core('ps2')})", GM.find_core("ps2") == S + "/cores/pcsx2_libretro.so")
    os.remove(f"{GAMES}/BIOS/scph39001.bin")         # (no BIOS it takes: none at all, now)
    run = GM.GameRun({"path": f"{GAMES}/ps2/Fake PS2 Game (USA).iso", "title": "Fake PS2 Game (USA)", "system": "ps2"})
    run.start(GM.find_core("ps2"), sound="", volume=80, picture="Fit", resume=False)
    started = run.wait_started(120)
    check(f"...a game with no BIOS for it: it stops, saying why ({started}, {run.error!r})",
          not started and run.error and until(lambda: run.ended, 60))
    # a BIOS of our own that it takes: its ROM's directory (RESET, ROMDIR, ROMVER: v1.60, USA), and at its start (where
    # both of the PS2's processors begin) a little program: the I/O processor (its PRId under 0x100) round and round;
    # the main one sets up the picture (its first circuit on, blended all the way to the background colour, NTSC,
    # 640 wide), the background red, then round and round
    prog = [0x400B7800, 0, 0x2D6C0100, 0x15800015, 0,        # mfc0 t3, PRId; sltiu t4, t3, 0x100; bne t4, zero, iop
            0x3C08B200,                                      # t0 = 0xB2000000 (the GS's registers, uncached)
            0x340900A5, 0xFD090000,                          # PMODE: circuit 1, ALP 0 (MMOD), with the background
            0x34094000, 0xFD090010,                          # SMODE1: NTSC
            0x34090001, 0xFD090020,                          # SMODE2: interlaced
            0x34091400, 0xFD090070,                          # DISPFB1: 640 wide, 32-bit
            0x3C09001B, 0x3529F9FF, 0x0009483C,              # DISPLAY1: 0x001BF9FF0183227C (2560 x 448 at 636, 50)
            0x3C0A0183, 0x354A227C, 0x012A4825, 0xFD090080,
            0x340900FF, 0xFD0900E0,                          # BGCOLOR: red
            0x1000FFFF, 0,                                   # b .
            0x1000FFFF, 0]                                   # iop: b .
    open(f"{GAMES}/BIOS/ps2/our-own.bin", "wb").write(ps2_rom(struct.pack(f"<{len(prog)}I", *prog), at=0x100))
    run = GM.GameRun({"path": f"{GAMES}/ps2/Fake PS2 Game (USA).iso", "title": "Fake PS2 Game (USA)", "system": "ps2"})
    t0 = time.monotonic()
    run.start(GM.find_core("ps2"), sound="", volume=80, picture="Fit", resume=False)
    started = run.wait_started(180)
    check(f"...with a BIOS it takes: it starts ({started}, {run.state}, {run.error!r}, {time.monotonic() - t0:.1f} s)",
          started and run.state == "on")
    time.sleep(4)
    shot = run.ask(f"shot {S}/ps2shot.ppm", ("shot",), 30)
    px = None
    if shot == ("shot", "ok"):
        ppm = open(S + "/ps2shot.ppm", "rb").read()
        pw, ph = (int(v) for v in ppm.split(b"\n", 3)[1].split())
        mid = len(ppm) - pw * ph * 3 + ((ph // 2) * pw + pw // 2) * 3
        px = tuple(ppm[mid:mid + 3])
    # (its picture: only once something's drawn with its graphics chip, as a game does; not this little program)
    print(f"(a PS2 picture needs a real game: {shot}, {px})", flush=True)
    saved = run.ask("save", ("saved", "error"), 120)
    state = f"{SAVES}/Fake PS2 Game (USA).state"
    check(f"Save state ({saved}, {os.path.getsize(state) if os.path.isfile(state) else 0} bytes)",
          saved[0] == "saved" and os.path.getsize(state) > 1000000)
    loaded = run.ask("load", ("loaded", "nostate", "error"), 120)
    check(f"Load state ({loaded})", loaded[0] == "loaded" and not run.ended)
    run.quit(60)
    check(f"quit: it ends, cleanly ({run.p.returncode})", until(lambda: run.ended, 60) and run.p.returncode == 0)
    cards = sorted(os.listdir(SAVES))
    check(f"...its memory cards its own, with its saves ({cards})", any(c.endswith(".ps2") for c in cards))
else:
    print("(LRPS2 isn't built here: its own test skipped)", flush=True)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
