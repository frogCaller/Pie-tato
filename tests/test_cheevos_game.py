"""Achievements while a game plays, for real: rcheevos built as setup.sh builds it, a pretend NES emulator whose RAM
byte 0x10 turns 5 on frame 120, and a pretend RetroAchievements (with an achievement for that: 0xH0010=5). Signed
in (your account handed over by media mode), the game's found by its hash; its achievements' count told to media
mode, and a notice over the picture; the unlock: sent to RetroAchievements, a notice, the count; the list for the
menu; a state saved with their progress beside it, and put back; a reset; quitting cleanly. Played again: already
yours. Not signed in, a game it doesn't know, RetroAchievements not answering: the game plays just the same."""
import json, os, shutil, struct, subprocess, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tcheevos_game"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
os.makedirs(GAMES + "/Saves")
os.makedirs(S + "/static")
os.makedirs(S + "/bin")
os.environ["PITATO_STATIC"] = S + "/static"
T = SP + "/cheevos_test"
LIB = T + "/build/librcheevos.so"
if not os.path.isfile(LIB):
    subprocess.run(["bash", T + "/build_lib.sh", T + "/build"], check=True)
os.environ["PITATO_RCHEEVOS"] = LIB
sys.path.insert(0, ROOT)
sys.path.insert(0, SP + "/ra")
from fake_server import FakeRAServer, ach
from pitato import cheevos as CV, games as GM, rcheevos as RC
GM.home_dir = lambda: HOME
GM.games_dir = lambda: GAMES
FB = S + "/fb.bin"
os.environ["PITATO_FB"] = f"{FB}:640x480:16"
open(FB, "wb").write(bytes(640 * 480 * 2))
open(S + "/bin/aplay", "w").write("#!/bin/sh\nexec cat > /dev/null\n")
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
CORE = T + "/testcore_libretro.so"
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


def gold_up_top():
    """The notice's gold, in the screen's top rows (RGB565)."""
    a = np.frombuffer(open(FB, "rb").read(), dtype="<u2").reshape(480, 640)[:120]
    r, g, b = (a >> 11) & 31, (a >> 5) & 63, a & 31
    return int(((r >= 27) & (g >= 44) & (g <= 54) & (b <= 13)).sum())


# a NES game (its iNES header, then its bytes), and another RetroAchievements doesn't know
rom = b"NES\x1a\x01\x01" + bytes(10) + bytes(range(256)) * 64
open(GAMES + "/Test Game (USA).nes", "wb").write(rom)
open(GAMES + "/Unknown Game (USA).nes", "wb").write(b"NES\x1a\x01\x01" + bytes(10) + b"\x07" * 16384)
lib = RC.RCheevos(LIB)
digest = lib.hash_buffer(RC.RC_CONSOLE_NINTENDO, rom)
check(f"rcheevos, built as setup.sh builds it: {lib.version_string}, the game's hash ({digest})",
      lib.version_string.startswith("12.5") and digest and len(digest) == 32)

srv = FakeRAServer().start()
srv.add_user("Frog", "right one", token="k3y")
srv.add_game(1234, "Test Game", RC.RC_CONSOLE_NINTENDO, [digest],
             achievements=[ach(5001, "Five Alive", "Make byte 0x10 five", "0xH0010=5", points=10)])
os.environ["PITATO_RA_HOST"] = srv.url
CV.ra_save("Frog", "k3y")


def play(name, **kw):
    run = GM.GameRun({"path": f"{GAMES}/{name}", "title": name, "system": "nes"})
    run.start(CORE, sound="", volume=80, picture="Fit", fb=FB, resume=False, **kw)
    return run


run = play("Test Game (USA).nes")
started = run.wait_started(20)
check(f"signed in, the game starts ({started}, {run.state}, {run.error!r})", started and run.state == "on")
check(f"...its achievements found: none yours yet, of one ({run.cheevos})", until(lambda: run.cheevos == (0, 1), 15))
check(f"...a notice over the picture saying so ({gold_up_top()} gold pixels)", until(lambda: gold_up_top() > 50, 5))
check(f"...asked as RetroAchievements wants: signed in by its key, the game by its hash "
      f"({[r['r'] for r in srv.requests]})", srv.calls("login2") and srv.calls("login2")[0]["params"].get("t") == "k3y"
      and any(r["r"] in ("achievementsets", "patch") for r in srv.requests) and srv.calls("startsession"))
ua = srv.calls("login2")[0]["user_agent"]
check(f"...saying who's asking: Pietato, its version, the emulator, rcheevos ({ua})",
      ua.startswith("Pietato/1.1 (") and "testcore_libretro" in ua and "rcheevos/12.5" in ua)
check(f"frame 120, byte 0x10 is 5: unlocked, told to media mode ({run.cheevos})",
      until(lambda: run.cheevos == (1, 1), 15))
award = srv.calls("awardachievement")
check(f"...sent to RetroAchievements: that one, in softcore ({[a['params'] for a in award]})",
      until(lambda: len(srv.calls("awardachievement")) == 1, 10)
      and srv.calls("awardachievement")[0]["params"].get("a") == "5001"
      and srv.calls("awardachievement")[0]["params"].get("h") in ("0", None))
check(f"...a notice over the picture ({gold_up_top()} gold pixels)", gold_up_top() > 50)
listing = S + "/list.json"
what = run.ask(f"cheevolist {listing}", ("cheevolist",), 10)
got = json.load(open(listing)) if os.path.isfile(listing) else {}
check(f"the list, for the menu ({what}, {got})", what == ("cheevolist", "ok") and got.get("head") == "1 of 1 yours: 10 of 10 points"
      and got["list"] == [{"title": "Five Alive", "description": "Make byte 0x10 five", "points": 10, "unlocked": True,
                           "progress": ""}])
saved = run.ask("save", ("saved", "error"), 10)
base = f"{GAMES}/Saves/Test Game (USA)"
check(f"Save state: their progress beside it ({saved}, {os.path.isfile(base + '.state.cheevos')})",
      saved[0] == "saved" and os.path.getsize(base + ".state.cheevos") > 0)
loaded = run.ask("load", ("loaded", "nostate", "error"), 10)
check(f"Load state ({loaded})", loaded[0] == "loaded" and not run.ended)
check(f"Start over ({run.ask('reset', ('reset',), 5)})", not run.ended)
time.sleep(1)
check(f"...still yours, nothing sent again ({run.cheevos}, {len(srv.calls('awardachievement'))})",
      run.cheevos == (1, 1) and len(srv.calls("awardachievement")) == 1)
run.quit(20)
check(f"quit: it ends, cleanly ({run.p.returncode})", until(lambda: run.ended, 20) and run.p.returncode == 0)

run = play("Test Game (USA).nes")
run.wait_started(20)
check(f"played again: already yours ({run.cheevos})", until(lambda: run.cheevos == (1, 1), 15))
time.sleep(2.5)
check(f"...past frame 120: nothing sent again ({len(srv.calls('awardachievement'))})",
      len(srv.calls("awardachievement")) == 1)
run.quit(20)
until(lambda: run.ended, 20)

# not signed in, a game it doesn't know, RetroAchievements not answering: the game plays the same
run = play("Test Game (USA).nes", cheevos=False)
check(f"not signed in (or not asked): it plays, no achievements ({run.wait_started(20)}, {run.cheevos})",
      run.state == "on" and (time.sleep(2) or run.cheevos is None))
run.quit(20); until(lambda: run.ended, 20)
run = play("Unknown Game (USA).nes")
check(f"a game RetroAchievements doesn't know: it plays, none ({run.wait_started(20)}, {run.cheevos})",
      run.state == "on" and (time.sleep(3) or run.cheevos is None))
run.quit(20); until(lambda: run.ended, 20)
# a PSP game in a .cso (its blocks squeezed): read through Python for its hash (rcheevos can't), found, and its
# achievement unlocked the same way


def iso9660(files, sectors=160):
    """A small ISO 9660 disc with these files in it (rcheevos's own test discs' shape, as its tests make them)."""
    img = bytearray(sectors * 2048)
    vd = 16 * 2048
    img[vd:vd + 8] = b"\x01CD001\x01\x00"
    img[vd + 80:vd + 84] = sectors.to_bytes(4, "little")
    img[vd + 84:vd + 88] = sectors.to_bytes(4, "big")
    img[vd + 128:vd + 130] = (2048).to_bytes(2, "little")
    img[vd + 158] = 17
    img[17 * 2048 - 4] = 18
    for filename, contents in files:
        root = 17 * 2048
        nfs = img[root - 4] | img[root - 3] << 8 | img[root - 2] << 16
        entry = root
        *dirs, name = filename.split("\\")
        for d in dirs:
            db, e = d.encode(), entry
            while img[e]:
                if img[e + 25] and img[e + 33 + len(db)] == 0 and img[e + 33:e + 33 + len(db)] == db:
                    entry = img[e + 2] * 2048
                    break
                e += img[e]
            else:
                img[e], img[e + 2], img[e + 3], img[e + 25], img[e + 32] = len(db) + 48, nfs & 255, nfs >> 8 & 255, 1, len(db)
                img[e + 33:e + 33 + len(db)] = db
                entry, nfs = nfs * 2048, nfs + 1
        e = entry
        while img[e]:
            e += img[e]
        nb, size = name.encode(), len(contents)
        img[e], img[e + 2], img[e + 3] = len(nb) + 48, nfs & 255, nfs >> 8 & 255
        img[e + 10:e + 13] = size.to_bytes(3, "little")
        img[e + 32] = len(nb) + 2
        img[e + 33:e + 35 + len(nb)] = nb + b";1"
        img[nfs * 2048:nfs * 2048 + size] = contents
        nfs += (size + 2047) // 2048
        img[root - 4:root - 1] = nfs.to_bytes(3, "little")
    return bytes(img)


def cso(data, block=2048):
    import zlib
    n = (len(data) + block - 1) // block
    offset, index, chunks = 24 + 4 * (n + 1), [], []
    for i in range(n):
        raw = data[i * block:(i + 1) * block]
        z = zlib.compressobj(9, zlib.DEFLATED, -15)
        comp = z.compress(raw) + z.flush()
        stored = len(comp) >= len(raw)
        index.append(offset | (0x80000000 if stored else 0))
        chunks.append(raw if stored else comp)
        offset += len(chunks[-1])
    index.append(offset)
    return struct.pack("<4sIQIBB2x", b"CISO", 24, len(data), block, 1, 0) + struct.pack(f"<{n + 1}I", *index) \
        + b"".join(chunks)


sfo, eboot = bytes(range(256)) * 3, bytes(range(255, -1, -1)) * 900
disc = iso9660([("PSP_GAME\\PARAM.SFO", sfo), ("PSP_GAME\\SYSDIR\\EBOOT.BIN", eboot)])
open(GAMES + "/Squeezed Psp (USA).cso", "wb").write(cso(disc))
srv.add_game(4321, "Squeezed Psp", RC.RC_CONSOLE_PSP, [__import__("hashlib").md5(sfo + eboot).hexdigest()],
             achievements=[ach(6001, "Disc Five", "Make byte 0x10 five, on a disc", "0xH0010=5", points=5)])
run = GM.GameRun({"path": f"{GAMES}/Squeezed Psp (USA).cso", "title": "Squeezed Psp", "system": "psp"})
run.start(T + "/testdisc_libretro.so", sound="", volume=80, picture="Fit", fb=FB, resume=False)
run.wait_started(20)
check(f"a PSP game in a .cso: read through Python for its hash, found ({run.cheevos})",
      until(lambda: run.cheevos is not None, 15) and run.cheevos[1] == 1)
check(f"...its achievement unlocked, as a cartridge's is ({run.cheevos})", until(lambda: run.cheevos == (1, 1), 15)
      and any(a["params"].get("a") == "6001" for a in srv.calls("awardachievement")))
run.quit(20); until(lambda: run.ended, 20)

srv.users["frog"]["expired"] = True
run = play("Test Game (USA).nes")
run.wait_started(20)
check(f"its key too old (or turned down): a notice saying to sign in again, no achievements ({run.cheevos})",
      until(lambda: gold_up_top() > 50, 10) and run.cheevos is None and run.state == "on")
run.quit(20); until(lambda: run.ended, 20)
srv.users["frog"]["expired"] = False
open(FB, "wb").write(bytes(640 * 480 * 2))
srv.offline = True
run = play("Test Game (USA).nes")
started = run.wait_started(20)
time.sleep(3)
shot = run.ask(f"shot {S}/shot.ppm", ("shot",), 10)
check(f"RetroAchievements not answering: it plays just the same, nothing said about signing in ({started}, {shot}, "
      f"{run.cheevos}, {gold_up_top()})", started and shot == ("shot", "ok") and not run.ended and gold_up_top() == 0)
run.quit(20)
check(f"...and quits as quickly ({run.p.returncode})", until(lambda: run.ended, 15) and run.p.returncode == 0)
srv.stop()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
