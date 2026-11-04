"""Media mode finding the lengths of songs and videos (probe_loop): from their headers without starting a program
(ffprobe only for the kinds that need it), each file once, a file gone from the list meanwhile not tried again and
again (it was: mplayer, over and over), the lists redrawn only while one shows, waiting while a video has the
screen, and how many are left (for System)."""
import os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_probe"
LEN = SP + "/t_lengths"                      # (test_lengths.py makes these)
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos"):
    os.makedirs(f"{HOME}/{d}")
for n in ("cbr128.mp3", "vbr.mp3", "song.flac", "song.ogg", "aac.m4a", "voice.opus", "song.wav", "tune.wma"):
    shutil.copy(f"{LEN}/{n}", f"{HOME}/Music/{n}")
for n in ("clip.mp4", "clip.mkv", "clip.avi"):
    shutil.copy(f"{LEN}/{n}", f"{HOME}/Videos/{n}")
for k in range(30):
    shutil.copy(f"{LEN}/cbr_noxing.mp3", f"{HOME}/Music/Track {k:02d}.mp3")
sys.path.insert(0, TESTS)
import pietato_all as g

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if t.get(key):
            t[key] = [f.replace("/home/*", S + "/home/*") for f in t[key]]
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


started = []
RealRun = subprocess.run


def run(args, *a, **k):
    words = [w for w in (args if isinstance(args, list) else [args]) if w not in ("nice", "-n", "15")]
    started.append(os.path.basename(str(words[0])))
    return RealRun(args, *a, **k)


g.subprocess.run = run                        # (lengths.py's, and everyone's: the same module)
m = g.Media()
m.active = True
mi, vi = (next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == k) for k in ("audio", "video"))
m.load_tab(mi); m.load_tab(vi)
songs, videos = m.tab_items(mi), m.tab_items(vi)
check(len(songs) == 38 and len(videos) == 3, f"38 songs and 3 videos ({len(songs)}, {len(videos)})")
check(all(m.length(it) is None for it in songs + videos), "no lengths yet")

# on the home screen: found, without drawing anything
m.view = "home"
os.remove(f"{HOME}/Music/Track 29.mp3")          # (gone, though the list still has it)
dirties = []
m.dirty = False
t0 = time.time()
lefts = []
real_probe = g.probe_length
g.probe_length = lambda p: (lefts.append(m.probe_left), real_probe(p))[1]
th = threading.Thread(target=m.probe_loop, daemon=True)
th.start()
while th.is_alive() and time.time() - t0 < 60:
    if m.dirty:
        dirties.append(time.time())
        m.dirty = False
    time.sleep(0.002)
th.join(5)
took = time.time() - t0
check(not th.is_alive(), f"done in {took:.1f}s")
check(lefts == list(range(41, 0, -1)) and m.probe_left == 0, f"how many were left, as it went: {lefts[:3]}..., then 0")
lens = {os.path.basename(it["src"]): m.length(it) for it in songs + videos}
print({k: (round(v, 2) if v else v) for k, v in lens.items() if not k.startswith("Track")})
check(all(v and v > 1 for k, v in lens.items() if k != "Track 29.mp3"), "every one's length found")
check(abs(lens["cbr128.mp3"] - 61.54) < 0.1 and abs(lens["vbr.mp3"] - 47.33) < 0.1
      and all(abs(lens[f"clip.{x}"] - 12.4) < 0.1 for x in ("mp4", "mkv", "avi")), "...the right ones")
check(lens["Track 29.mp3"] is None, "the one that's gone: no length")
check(sorted(started) == ["ffprobe"] * 3,
      f"programs started: only ffprobe, for the WMA, the MKV and the AVI ({started})")
check(not dirties, f"on the home screen: nothing drawn for it ({len(dirties)})")
check(os.path.exists(S + "/state.json") and "dur" in open(S + "/state.json").read(), "kept in state.json")

# a Music list showing: drawn as they come; a video playing: it waits
for it in songs[:10]:
    m.state["dur"].pop(it["key"], None)
m.view, m.tab = "list", mi
started.clear()


class FakeProc:
    def poll(self):
        return None


m.proc, m.kind = FakeProc(), "video"
th = threading.Thread(target=m.probe_loop, daemon=True)
th.start()
time.sleep(1.5)
check(th.is_alive() and m.length(songs[0]) is None, "a video has the screen: it waits")
m.proc, m.kind = None, None
th.join(30)
check(not th.is_alive() and all(m.length(it) for it in songs[:10]), "the video's over: on it goes")
check(m.dirty, "the Music list showing: drawn again")
check(started == [], f"no programs at all for MP3s ({started})")

# leaving media mode: it stops
for it in songs:
    m.state["dur"].pop(it["key"], None)
m.active = False
th = threading.Thread(target=m.probe_loop, daemon=True)
th.start()
th.join(10)
check(not th.is_alive() and m.length(songs[5]) is None, "media mode left: it stops")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
