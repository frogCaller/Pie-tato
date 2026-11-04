"""The Bot's voice, as it's heard (voice.py, with pretend aplays: no Piper needed). The samples go to aplay a little
at a time, and it's heard from the first of them till they've played (and through a short pause between sentences):
the face talks only then, and thinks while its voice gets ready (Piper loading, the first sentence being made). An
aplay that takes nothing (the sound card held by something else): let go after a while, said, and in the log, not
waited on for ever; one that won't start the card: what it said. Its voice is loaded as soon as you've asked it
something it'll answer out loud (over music it pauses too), not only when its page opens with nothing playing."""
import io, os, shutil, sys, threading, time
from contextlib import redirect_stdout
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_voice_heard"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
BIN = S + "/bin"
for d in (HOME + "/Music", BIN):
    os.makedirs(d)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.voice as V

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# pretend aplays: one that plays in real time, one that never takes anything (stuck: the card's someone else's), one
# that can't open the card
open(BIN + "/aplay-ok", "w").write("#!/usr/bin/env python3\nimport sys, time\nr = int(sys.argv[sys.argv.index('-r') + 1])"
                                   "\nwhile True:\n    b = sys.stdin.buffer.read1(4096)\n    if not b:\n        break\n"
                                   "    time.sleep(len(b) / (2 * r))\n")
open(BIN + "/aplay-stuck", "w").write("#!/bin/sh\nexec sleep 60\n")
open(BIN + "/aplay-busy", "w").write("#!/bin/sh\necho 'aplay: main:831: audio open error: Device or resource busy' >&2\n"
                                     "exit 1\n")
for n in ("aplay-ok", "aplay-stuck", "aplay-busy"):
    os.chmod(BIN + "/" + n, 0o755)


def use_aplay(which):
    shutil.copy(BIN + "/aplay-" + which, BIN + "/aplay")


os.environ["PATH"] = BIN + ":" + os.environ["PATH"]
RATE = 16000
SECOND = b"\x10\x00" * RATE                           # (a second of samples, quiet)
v = g.Voice()

# ---- heard: from its first samples till they've played ---------------------------------------------------------------
use_aplay("ok")
v.speaking, v.sounding = True, 0.0
check("getting ready (nothing given aplay yet): not heard, so the mouth doesn't move", not v.talking())
play = v.start_play(RATE, "")
t0 = time.monotonic()
done = {}
th = threading.Thread(target=lambda: done.update(ok=v.write(play, SECOND * 3, v.gen, RATE)))
th.start()
time.sleep(0.5)
check(f"its first samples given aplay: heard ({v.sounding - time.monotonic():.1f} s more)", v.talking())
th.join(10)
check(f"...all of it given, at the pace it plays ({time.monotonic() - t0:.1f} s for 3 s of it)",
      done.get("ok") is True and 0.5 < time.monotonic() - t0 < 4.5)
v.finish(play, v.gen)
check(f"...played out, aplay done ({play.returncode}), and still heard a moment after (a pause between sentences)",
      play.returncode == 0 and v.talking() and not v.error)
time.sleep(V.TALK_GAP + 0.2)
check("...then not", not v.talking())
v.speaking = False

# ---- aplay stuck: let go after a while, and said --------------------------------------------------------------------
use_aplay("stuck")
g.PLAY_STUCK = 1.0
v.error = ""
v.speaking, v.sounding = True, 0.0
play = v.start_play(RATE, "")
t0 = time.monotonic()
ok = v.write(play, SECOND * 10, v.gen, RATE)
took = time.monotonic() - t0
check(f"an aplay that takes nothing: let go ({took:.1f} s, not for ever), and it says why ({v.error!r})",
      ok is False and took < 6 and play.poll() is not None
      and v.error == "Couldn't play it: the sound didn't go (is something else using it?)" and not v.talking())
v.speaking = False

# ---- aplay that won't open the card: what it said --------------------------------------------------------------------
use_aplay("busy")
v.error = ""
v.speaking, v.sounding = True, 0.0
play = v.start_play(RATE, "")
time.sleep(0.3)
ok = v.write(play, SECOND * 2, v.gen, RATE)
check(f"an aplay that can't have the card: as it says ({v.error!r})", ok is False
      and v.error == "Couldn't play it: audio open error: Device or resource busy")
v.speaking = False

# ---- the whole thing, through the voice's own thread: in the log too ----------------------------------------------------
use_aplay("stuck")


def fake_speak(gen, text, vid, device, volume):
    p = v.start_play(RATE, device)
    if v.write(p, SECOND * 4, gen, RATE):
        v.finish(p, gen)


v.speak = fake_speak
g.voices_here = lambda: {"en_US-amy-low"}
v.have_piper = lambda: True
out = io.StringIO()
with redirect_stdout(out):
    said = v.say("Hello there.", "en_US-amy-low")
    end = time.time() + 8
    while v.speaking and time.time() < end:
        time.sleep(0.05)
    time.sleep(0.3)                                   # (its line in the log, just after)
check(f"said through its thread, aplay stuck: it stops speaking, and the log says why ({out.getvalue().strip()!r})",
      said == (True, "") and not v.speaking
      and "voice: Couldn't play it: the sound didn't go (is something else using it?)" in out.getvalue())
g.PLAY_STUCK = 6.0
del v.speak

# ---- Media: the face, and its voice loaded as soon as you've asked ---------------------------------------------------
class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
open(HOME + "/bot.txt", "w").write("server = 127.0.0.1:9\nmodel = llama3.2:3b\nvoice = en_US-amy-low\nspeak = on\n")
m.friend.load(m.friend_files())
warmed = []
m.voice.warm = lambda vid: warmed.append(vid)
m.voice.speaking, m.voice.sounding = True, 0.0
check(f"its voice getting ready: the face thinks ({m.face_look()})", m.face_look() == "thinking")
m.voice.sounding = time.monotonic() + 5
check(f"...heard: it talks ({m.face_look()})", m.face_look() == "talking")
m.voice.speaking, m.voice.sounding = False, 0.0
m.friend.say = lambda text, picture=None: True
m.friend_send("What's an octopus?")
check(f"asked something: its voice loaded at once, for the answer ({warmed})", warmed == ["en_US-amy-low"])
warmed.clear()


class Proc:
    def poll(self): return None


m.proc, m.kind, m.paused = Proc(), "audio", False
m.friend_send("And a squid?")
check("...music playing, and it doesn't pause music: not (it won't say it over the music)", warmed == [])
open(HOME + "/bot.txt", "a").write("pause_music = on\n")
m.friend.load(m.friend_files())
m.friend_send("And a cuttlefish?")
check("...it pauses music: loaded (it'll say it, the music paused)", warmed == ["en_US-amy-low"])
warmed.clear()
open(HOME + "/bot.txt", "a").write("speak = off\n")
m.friend.load(m.friend_files())
m.friend_send("And a nautilus?")
check("...Talks out loud off: not", warmed == [])
m.proc = m.kind = None
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
