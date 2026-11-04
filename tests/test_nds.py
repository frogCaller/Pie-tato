"""DS games: the real melonDS (libretro's, built here by setup.sh's own build_melonds, for a PC instead of a Pi 4) and a
tiny DS program made here (nds/mkrom.py: the top screen red, green while A's held, blue while R is). The consoles'
table; DS games found (a .nds, and one in a zip), not on an older Pi; in the emulator's process: both screens side by
side on a TV, the buttons reaching the game, the right stick moving the pointer on the touch screen, the screens laid
out afresh as it plays (one above the other, the top one big), states, picking up where you left off, quitting; in
media mode: the Games list, its menu's Screens and Touch screen, the left stick as its d-pad, the right stick half
as fast, R2 to touch, and the d-pad and A to touch instead."""
import os, shutil, subprocess, sys, time, zipfile
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import emulator as E, games as GM
from pitato.screens import games as SG

S = SP + "/tnds"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
SAVES = GAMES + "/Saves"
for d in ("nds", "BIOS"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin"); os.makedirs(S + "/cores")
ROM = SP + "/nds/Pitato Test (World).nds"
shutil.copy(ROM, f"{GAMES}/nds/Pitato Test (World).nds")
with zipfile.ZipFile(f"{GAMES}/Zipped Test (World).zip", "w") as z:
    z.write(ROM, "Zipped Test (World).nds")
CORE = S + "/cores/melonds_libretro.so"
shutil.copy(SP + "/setupds/cores/melonds_libretro.so", CORE)   # (setup.sh's build_melonds put it there)
open(S + "/bin/aplay", "w").write('#!/bin/sh\necho "$@" >> "$GPI_TEST_SOUND.args"\nexec cat >> "$GPI_TEST_SOUND"\n')
os.chmod(S + "/bin/aplay", 0o755)
FBF = S + "/fb.bin"
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["GPI_TEST_SOUND"] = S + "/sound.raw"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
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


def screen_as(bits, w, h):
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


def colour(px):
    r, gg, b = (int(v) for v in px)
    return "red" if r > 200 and gg < 60 and b < 60 else "green" if gg > 200 and r < 60 and b < 60 else \
        "blue" if b > 200 and r < 60 and gg < 60 else f"{r},{gg},{b}"


def start(path, layout=None, resume=True):
    run = GM.GameRun({"path": path, "title": os.path.splitext(os.path.basename(path))[0], "system": "nds"})
    run.start(GM.find_core("nds"), sound="", volume=80, picture="Fit", resume=resume,
              options=[f"melonds_screen_layout={layout}"] if layout else [])
    runs.append(run)
    return run


def finish(run):
    run.quit()
    return until(lambda: run.ended, 15)


# ---- the table, the games, the emulator ---------------------------------------------------------------------
check(f"the consoles: the DS after the PSP ({[s[0] for s in GM.GAME_SYSTEMS][-6:]}), .nds files, melonDS first",
      [s[0] for s in GM.GAME_SYSTEMS].index("nds") == [s[0] for s in GM.GAME_SYSTEMS].index("psp") + 1
      and GM.system("nds")[1:4] == ("DS", "Nintendo DS", (".nds",)) and GM.system("nds")[4][0] == "melonds")
check("...a Pi 4 or 5 only, its sticks as they are (the right one: the touch screen's pointer), not drawn by the "
      "graphics chip, no files of its own, setup.sh builds it, its box art's list",
      "nds" in GM.FAST_PI_ONLY and "nds" in GM.ANALOG_SYSTEMS and "nds" not in GM.NEEDS_3D
      and "nds" not in GM.OWN_FILES and GM.GAME_PACKAGES.get("melonds") == "melonds"
      and GM.LIBRETRO_NAMES["nds"] == "Nintendo - Nintendo DS")
check(f"the DS emulator is found ({GM.find_core('nds')})", GM.find_core("nds") == CORE)
names = sorted((x["title"], x["system"]) for x in GM.find_games())
check(f"the list: a .nds, in its folder or in a zip ({names})",
      names == [("Pitato Test (World)", "nds"), ("Zipped Test (World)", "nds")])
g.slow_pi = lambda: True
check(f"an older Pi: no DS games at all ({GM.find_games()})", GM.find_games() == [])
g.slow_pi = lambda: False

# ---- the emulator's process: on a TV ------------------------------------------------------------------------
spec = screen_as(32, 1920, 1080)
run = start(f"{GAMES}/nds/Pitato Test (World).nds", resume=False)
check(f"a DS game starts ({run.wait_started(30)}, {run.state}, {run.error!r})", run.state == "on")
top_mid = lambda: colour(frame(spec)[540, 480])
check("...its frames reach the screen: the top screen red", until(lambda: top_mid() == "red", 15))
rgb = frame(spec)
check(f"...both screens side by side, as wide as the TV: 1920 by 720, in the middle ({lit(rgb)})",
      lit(rgb) == (180, 899, 0, 1919))
check("...the touch screen on the right, the top one on the left", colour(rgb[540, 480]) == "red"
      and colour(rgb[540, 1440]) != "red")
run.press("a")
check("A held: green (the game sees it)", until(lambda: top_mid() == "green", 5))
run.release("a")
check("...let go: red", until(lambda: top_mid() == "red", 5))
run.press("r")
check("R held: blue", until(lambda: top_mid() == "blue", 5))
run.release("r")
until(lambda: top_mid() == "red", 5)


def pointer():
    """Where the pointer is on the touch screen (the right half): the middle of what's drawn differently there."""
    half = frame(spec)[180:900, 960:1920].astype(int)
    base = np.median(half.reshape(-1, 3), axis=0)
    odd = np.abs(half - base).sum(-1) > 90
    ys, xs = np.nonzero(odd)
    return (int(xs.mean()), int(ys.mean())) if len(xs) else None


p0 = pointer()
run.send("stick rx 127")
time.sleep(0.6)
run.send("stick rx 0")
time.sleep(0.2)
p1 = pointer()
run.send("stick ry 127")
time.sleep(0.4)
run.send("stick ry 0")
time.sleep(0.2)
p2 = pointer()
check(f"the right stick moves the pointer on the touch screen: right, then down ({p0}, {p1}, {p2})",
      p0 is not None and p1 is not None and p2 is not None and p1[0] > p0[0] + 100 and abs(p1[1] - p0[1]) < 20
      and p2[1] > p1[1] + 60)
run.press("r3")
time.sleep(0.2)
run.release("r3")
check("...R3 touches it (the game goes on)", until(lambda: top_mid() == "red", 3) and not run.ended)

# laid out afresh as it plays
run.send("option melonds_screen_layout Top/Bottom")
check("one above the other, as it plays: 256 by 384, as tall as the TV",
      until(lambda: lit(frame(spec)) == (0, 1079, 600, 1319), 8))
rgb = frame(spec)
check(f"...the top one on top ({colour(rgb[270, 960])}, {colour(rgb[810, 960])})", colour(rgb[270, 960]) == "red"
      and colour(rgb[810, 960]) != "red")
run.send("option melonds_screen_layout Hybrid Top")
near = lambda box, want: box is not None and all(abs(a - b) <= 8 for a, b in zip(box, want))
check(f"the top one big, the touch screen small beside it: 768 by 384, as wide as the TV (melonDS leaves a few "
      f"rows and columns at its edges dark: {lit(frame(spec)) if until(lambda: near(lit(frame(spec)), (60, 1019, 0, 1919)), 8) else None})",
      near(lit(frame(spec)), (60, 1019, 0, 1919)))
rgb = frame(spec)
check(f"...the big one red ({colour(rgb[540, 640])})", colour(rgb[540, 640]) == "red")
run.send("option melonds_screen_layout Left/Right")
check("back side by side", until(lambda: lit(frame(spec)) == (180, 899, 0, 1919), 8))
sound = os.path.getsize(S + "/sound.raw") if os.path.exists(S + "/sound.raw") else 0
args = open(S + "/sound.raw.args").read() if os.path.exists(S + "/sound.raw.args") else ""
check(f"its sound goes out, at the DS's 32768 a second ({sound} bytes; aplay {args.strip()[:60]!r})",
      sound > 100000 and "32768" in args)

# states
check("Save state", run.ask("save", ("saved", "error"), 20)[0] == "saved"
      and os.path.getsize(SAVES + "/Pitato Test (World).state") > 1000000)
check("Load state", run.ask("load", ("loaded", "nostate", "error"), 20)[0] == "loaded" and until(lambda: top_mid() == "red", 5))
check("Start over", run.ask("reset", ("reset",), 20)[0] == "reset" and until(lambda: top_mid() == "red", 8))
paused = run.ask("pause", ("paused",), 10)
open(FBF, "wb").write(bytes(1920 * 1080 * 4))
time.sleep(0.6)
still = frame(spec).any()
resumed = run.ask("resume", ("resumed",), 10)
check(f"its menu up: it stops drawing, then on it goes ({paused}, drew {still}, {resumed})",
      paused[0] == "paused" and not still and resumed[0] == "resumed" and until(lambda: top_mid() == "red", 8))
check("quit: it ends cleanly, where it was kept", finish(run) and run.p.returncode == 0
      and os.path.getsize(SAVES + "/Pitato Test (World).state.auto") > 1000000)
run = start(f"{GAMES}/nds/Pitato Test (World).nds", layout="Top/Bottom")
check(f"...next time it picks up where you were, laid out as asked ({run.wait_started(30)}, {run.resumed})",
      run.resumed and until(lambda: lit(frame(spec)) == (0, 1079, 600, 1319), 10))
check("...and ends cleanly again", finish(run) and run.p.returncode == 0)
run = start(f"{GAMES}/Zipped Test (World).zip")
check(f"a zipped one plays too ({run.wait_started(30)})", run.state == "on" and until(lambda: top_mid() == "red", 10))
check("...and ends", finish(run) and run.p.returncode == 0)

# a Pi 5's 16 KB memory pages: melonDS's quick memory (4 KB pages only) off, the rest as it was
real_page = E.page_size
E.page_size = lambda: 16384
core = E.Core(CORE, ROM, (".nds",), SAVES, "pages", GAMES + "/BIOS", lambda *a: None)
for _ in range(30):
    core.run()
check(f"16 KB pages (a Pi 5): its quick memory off, and it runs ({core.options})",
      core.options.get("melonds_jit_fast_memory") == "disabled" and core.av.timing.sample_rate == 32768)
core.close()
E.page_size = lambda: 4096
core = E.Core(CORE, ROM, (".nds",), SAVES, "pages", GAMES + "/BIOS", lambda *a: None)
check(f"...4 KB pages (a Pi 4): left on ({core.options})", "melonds_jit_fast_memory" not in core.options)
core.close()
E.page_size = real_page

# ---- media mode -------------------------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 1920, 1080; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
m = g.Media(); m.enter()
gi = m.tab_index("games")
m.open_app(gi)
rows = [(it["title"], it.get("icon"), it.get("sub")) for it in m.tab_items(gi) if it["kind"] == "game"]
check(f"the Games tab: the DS games, with DS on them ({rows})", rows == [
    ("Pitato Test (World)", "DS", "Nintendo DS"), ("Zipped Test (World)", "DS", "Nintendo DS")])
m.sels[gi] = 1
m.set_setting("ds_screens", "Hybrid Top")
m.press("a")
check(f"A plays it, its screens as you had them ({m.game is not None and m.game.wait_started(30)})",
      m.game is not None and m.game.state == "on" and "melonds_screen_layout=Hybrid Top" in m.game.p.args)
sent = []
real_send = m.game.send
m.game.send = lambda line: (sent.append(line), real_send(line))[1]


class Pad:
    def __init__(self, down=(), stick=True, l2=True):
        self.down, self.stick, self.l2 = set(down), stick, l2
    def has_stick(self): return self.stick
    def has_button(self, b): return b != "l2" or self.l2


check("its sticks go to it as they are", m.game_sticks())
m.game_stick("lx", 100)
m.game_stick("ly", -90)
check(f"the left stick: the d-pad (right, then up too) ({sent})", sent == ["down right", "down up"])
sent.clear()
m.game_stick("lx", 10)
m.game_stick("ly", 0)
check(f"...back: let go ({sent})", sent == ["up right", "up up"])
sent.clear()
m.game_stick("rx", 120)
check(f"the right stick: the pointer, half as fast ({sent})", sent == ["stick rx 60"])
sent.clear()
m.press("r2"); m.release("r2")
check(f"R2: touches (R3, to melonDS) ({sent})", sent == ["down r3", "up r3"])
sent.clear()
m.press("l2"); m.release("l2")
check(f"L2: blows on its microphone (L2) ({sent})", sent == ["down l2", "up l2"])
sent.clear()
check("the d-pad goes to the game as it is (touch: the right stick, R2)", m.game_pad_button(Pad({"up"}), "up") == "up"
      and m.game_pad_button(Pad(), "a") == "a" and sent == [])

# its menu
m.game_stick("rx", 0)
sent.clear()
m.game_menu_open()
items = [j for j, _ in m.game_menu_items()]
check(f"HOME: its menu, with Screens and Touch screen ({items})", m.view == "gamemenu"
      and items == ["resume", "save", "load", "reset", "screens", "touch", "volume", "picture", "ai", "quit"])
check(f"...as they are ({m.game_value('screens')}, {m.game_value('touch')})",
      m.game_value("screens") == "Top one big" and m.game_value("touch") == "Right stick, R2")
m.render_game_menu()
m.game_menu["sel"] = items.index("screens")
sent.clear()
m.press("right")
check(f"◀▶ on Screens: the next layout, told to the game and kept ({sent}, {m.setting('ds_screens')})",
      sent == ["option melonds_screen_layout Hybrid Bottom"] and m.setting("ds_screens") == "Hybrid Bottom"
      and m.game_value("screens") == "Touch screen big")
m.press("right")
check(f"...round to side by side ({m.setting('ds_screens')})", m.setting("ds_screens") == "Left/Right")
FB.last.save(S + "/menu.png")
m.game_menu["sel"] = items.index("touch")
sent.clear()
m.press("right")
check(f"◀▶ on Touch screen: the d-pad and A ({m.setting('ds_touch')}, {sent})", m.setting("ds_touch") == "D-pad, A"
      and m.game_value("touch") == "D-pad, A")
m.game_menu_close()
sent.clear()
check("the d-pad now moves the pointer (not to the game)", m.game_pad_button(Pad({"right"}), "right") is None
      and m.game_pad_button(Pad({"right", "down"}), "down") is None)
check(f"...right, then down too ({sent})", sent == ["stick rx 24", "stick ry 24"])
sent.clear()
check("...let go: still", m.game_pad_button(Pad(), "right") is None and sent == ["stick rx 0", "stick ry 0"])
check("...A touches (as R2: R3 to melonDS), B is B", m.game_pad_button(Pad(), "a") == "r2"
      and m.game_pad_button(Pad(), "b") == "b")
m.game_end()
check("quit: done", m.game is None and m.view == "list")
import struct as _struct
real_calc, real_dirs = SG.struct.calcsize, g.CORE_DIRS
g.CORE_DIRS = (S + "/nowhere",)
SG.struct.calcsize = lambda f: 4
m.game_open(m.tab_items(gi)[1])
check(f"no DS emulator, on a 32-bit system: it says what it needs ({m.msg})",
      m.msg == "DS games need the 64-bit Raspberry Pi OS" and m.game is None)
SG.struct.calcsize = real_calc
m.game_open(m.tab_items(gi)[1])
check(f"...on a 64-bit one: run setup.sh again ({m.msg})",
      m.msg == "The Nintendo DS emulator isn't installed. Run setup.sh again to add it" and m.game is None)
g.CORE_DIRS = real_dirs
m.set_setting("ds_touch", "Right stick, R2")
for r in runs:
    if r.alive():
        r.quit()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
