"""Two Pietatos playing one Genesis game together, end to end (pitato/netplay.py; the emulator's nethost and --net):
two real emulators (Genesis Plus GX, each with a pretend screen of its own) on this machine, as if on two. A tiny test
game of our own: blue, red while player 1 holds B, green while player 2 does, yellow for both (counting its rounds in
its memory, so two that aren't in step can tell). The host's game is
opened to the other (with a key); the other joins it as player 2, from the host's game as it is, and then each one's
B shows on both screens. A pause on one stops both (and says so on the other's picture); one out of step gets the
host's game again; the other leaving, the host plays on; the host leaving, the other's game ends and says why. One
with another copy of the game, or without the key: not let in (and the right one still can be)."""
import os, shutil, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_netplay_game"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Games/genesis", "Games/BIOS", "host-saves", "guest-saves"):
    os.makedirs(f"{H}/{d}" if d.startswith("Games") else f"{S}/{d}")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
ROM = H + "/Games/genesis/Pitato Sega Count (World).md"
shutil.copy(SP + "/sega/Pitato Sega Count (World).md", ROM)
OTHER = H + "/Games/genesis/Pitato Sega Test (Other).md"   # (another copy of it: a byte at its end changed)
data = bytearray(open(ROM, "rb").read())
data[-1] ^= 0xFF
open(OTHER, "wb").write(bytes(data))
CORE = SP + "/sega/cores/genesis_plus_gx_libretro.so"
g.home_dir = lambda: H
W, HH = 640, 480
KEY = "k" * 22
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def start(name, net="", rom=ROM):
    """An emulator with a pretend screen of its own, and what it says on its errors kept (its log)."""
    fb = f"{S}/{name}.fb"
    open(fb, "wb").write(bytes(W * HH * 2))
    os.environ["PITATO_FB"] = f"{fb}:{W}x{HH}:16"
    log = open(f"{S}/{name}.log", "w")
    saved = os.dup(2)
    os.dup2(log.fileno(), 2)                           # (its errors into its log: the emulator's stderr is ours)
    try:
        run = g.GameRun({"path": rom, "title": "Pitato Sega Test", "system": "genesis"})
        run.start(CORE, sound="", volume=0, resume=False, cheevos=False, saves=f"{S}/{name}-saves", net=net)
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        log.close()
    run.fb, run.log = fb, f"{S}/{name}.log"
    return run


def colour(run):
    a = int(np.fromfile(run.fb, dtype="<u2").reshape(HH, W)[300, 320])
    r, gr, b = (((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3)
    return {(True, False, False): "red", (False, True, False): "green", (False, False, True): "blue",
            (True, True, False): "yellow", (False, False, False): "black"}.get((r > 128, gr > 128, b > 128),
                                                                              str((r, gr, b)))


def until(cond, secs=6.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def both(c):
    """Both pictures that colour (waited for): whether they are, and what they are."""
    ok = until(lambda: colour(host) == c and colour(guest) == c)
    return ok, f"{colour(host)}, {colour(guest)}"


def news(run, what, secs=6.0):
    until(lambda: any(n[0] == what for n in run.net_news), secs)
    return next((n for n in run.net_news if n[0] == what), None)


def logged(run, words):
    """How many times its log says so."""
    try:
        return open(run.log).read().count(words)
    except OSError:
        return 0


def opened(run):
    what, rest = run.ask(f"nethost 0 {KEY} 127.0.0.1", ("nethost",), 5)
    words = rest.split()
    return int(words[1]) if what == "nethost" and words[:1] == ["ok"] else None


host = start("host")
check("the host's game starts", host.wait_started(20))
port = opened(host)
check(f"...opened to the other, with a key, from its address only (port {port})", port is not None and port > 0)

# ---- not let in: another copy of the game, or without the key ---------------------------------------------------
wrong = start("other", f"127.0.0.1:{port}:{KEY}", rom=OTHER)
until(lambda: wrong.ended, 20)
check(f"another copy of the game: not let in, and it says why ({wrong.error})", wrong.ended
      and wrong.error == "Couldn't play together: its copy of the game isn't the same as this one's")
nokey = start("nokey", f"127.0.0.1:{port}:{'x' * 22}")
until(lambda: nokey.ended, 20)
check(f"without the key: not let in ({nokey.error})", nokey.ended and nokey.error.startswith("Couldn't play together"))
check("...and the host plays on, alone, still open to the other", host.alive() and not host.net_news)

# ---- the other joins, as player 2 ------------------------------------------------------------------------------------
guest = start("guest", f"127.0.0.1:{port}:{KEY}")
check("the other joins, as player 2", guest.wait_started(20) and news(host, "netjoined") is not None)
ok, now = both("blue")
check(f"...both pictures: blue ({now})", ok)
host.press("b")
ok, now = both("red")
check(f"the host's B: player 1's, red on both ({now})", ok)
guest.press("b")
ok, now = both("yellow")
check(f"...the other's too: player 2's, yellow on both ({now})", ok)
host.release("b")
ok, now = both("green")
check(f"...the host lets go: green on both ({now})", ok)
guest.release("b")
ok, now = both("blue")
check(f"...both let go: blue ({now})", ok)
time.sleep(2.5)                                        # (a check or two of both games' memory, meanwhile)
check(f"...the two in step all along (their memory the same at each check: {logged(guest, 'out of step')} not)",
      logged(guest, "out of step") == 0)

# ---- a pause on one stops both ------------------------------------------------------------------------------------------
before = np.fromfile(guest.fb, dtype="<u2").copy()
check("the host's menu up (paused)", host.pause())
time.sleep(0.5)
guest.press("b")
time.sleep(0.5)
after = np.fromfile(guest.fb, dtype="<u2")
check(f"...the other's game waits too: its B does nothing yet ({colour(guest)}), and its picture says why "
      f"({int((after != before).sum())} pixels of a notice)", colour(guest) == "blue" and (after != before).sum() > 500)
host.resume()
ok, now = both("green")
check(f"...back in the game: on both go, the other's B green on both ({now})", ok)
guest.release("b")
both("blue")

# ---- out of step: the host's game again --------------------------------------------------------------------------------
guest.ask("reset", ("reset",), 3)                      # (its game started over: not the host's any more)
check("one out of step: it finds out, and takes the host's game again",
      until(lambda: logged(guest, "game: out of step") and logged(guest, "game: in step again"), 15))
host.press("b")
ok, now = both("red")
check(f"...in step again: the host's B, red on both ({now})", ok)
host.release("b")
both("blue")
time.sleep(2.5)
check(f"...and they stay in step ({logged(guest, 'out of step')} time out of step, in all)",
      logged(guest, "out of step") == 1)

# ---- the other leaves; then the host --------------------------------------------------------------------------------------
guest.quit()
check(f"the other leaves: the host's told, and plays on alone ({news(host, 'netleft')})",
      news(host, "netleft") is not None and host.alive())
host.press("b")
ok = until(lambda: colour(host) == "red")
check(f"...its B still player 1's ({colour(host)})", ok)
host.release("b")
port = opened(host)
guest = start("guest2", f"127.0.0.1:{port}:{KEY}")
check("open again: the other joins again", guest.wait_started(20) and len([n for n in host.net_news
                                                                           if n[0] == "netjoined"]) == 2)
host.quit()
check(f"the host leaves: the other's game ends, and it says why ({news(guest, 'netgone')})",
      until(lambda: guest.ended, 10) and news(guest, "netgone") == ("netgone", "it left"))
for run in (host, guest, wrong, nokey):
    run.quit(3)
check("its saves apart: nothing of the game's own in the Saves folder",
      not os.path.exists(H + "/Games/Saves"))
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
