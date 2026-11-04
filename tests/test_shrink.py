"""Big videos made smaller in the background, with real ffmpeg: which ones (a slow Pi and a fast one), the copy
checked and put in the original's place (its name, owner, mode and date; subtitles kept), where you were moved
along, held while a video plays, stopped part way, no room, a file still being copied, leftovers tidied, links left
alone. Always on: there's no setting for it (a Leave them saved from before it went is forgotten)."""
import io, os, sys, time, json, shutil, subprocess
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

W = SP + "/tshrink"
shutil.rmtree(W, ignore_errors=True)
os.makedirs(W + "/static")
V = W + "/Videos"
shutil.copytree(SP + "/vids", V)
old = time.time() - 3 * 86400
for f in os.listdir(V):
    os.utime(os.path.join(V, f), (old, old))
g.VIDEO_DIRS = (V,)
g.SHRINK_FILE = W + "/shrink.json"
g.STATE_FILE = W + "/state.json"
g.JELLYFIN_FILE = W + "/jellyfin.json"
g.PLEX_FILE = W + "/plex.json"
g.CACHE_DIR = W + "/cache"
g.STATIC = W + "/static"
g.home_dir = lambda: W
g.screen_size = lambda: (640, 480)
g.slow_pi = lambda: True
vi = next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == "video")
g.LIBRARY[vi]["dirs"] = [V]

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def wait_for(cond, secs=60):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                         capture_output=True, text=True).stdout
    return json.loads(out or "{}")


def vstream(path):
    return next(s for s in info(path)["streams"] if s["codec_type"] == "video")


def proc_state(pid):
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0]
    except OSError:
        return "?"


B = lambda p: os.path.basename(p)

# ---- 1. which videos are too big ------------------------------------------------------------------------------------
box, slow = g.target_box()
check((box, slow) == ((640, 480), True), f"a Pi Zero with the GPi Case: 640x480 ({box}, {slow})")
g.screen_size = lambda: (1920, 1080)
check(g.target_box() == ((854, 480), True), "...on a TV: 854x480")
g.slow_pi = lambda: False
check(g.target_box() == ((1280, 720), False), "a Pi 4 or 5: 720p")
verdicts = {}
for name in sorted(os.listdir(V)):
    i = g.probe(os.path.join(V, name))
    verdicts[name] = None if i is None else bool(g.too_big(i, (1280, 720), False))
check(verdicts == {"Big Movie (2020).mkv": False, "Broken.mkv": None, "Hevc Clip.mp4": True, "Sixty.avi": False,
                   "Small Fine.mp4": False}, f"...it only makes HEVC (and such) smaller: {verdicts}")
g.slow_pi = lambda: True
g.screen_size = lambda: (640, 480)
verdicts = {}
for name in sorted(os.listdir(V)):
    i = g.probe(os.path.join(V, name))
    verdicts[name] = None if i is None else g.too_big(i, (640, 480), True)
print(verdicts)
check(verdicts == {"Big Movie (2020).mkv": "1280x720", "Broken.mkv": None, "Hevc Clip.mp4": "hevc",
                   "Sixty.avi": "60 fps", "Small Fine.mp4": ""}, "a Pi Zero: 720p, HEVC and 60 a second are too much")
i = g.probe(V + "/Big Movie (2020).mkv")
cmd = g.command("a.mkv", "b.mkv", dict(i, fps=120.0), (640, 480), True)
check(any("fps=30.000" in x for x in cmd), "120 a second becomes 30")
check("-profile:v" in cmd and cmd[cmd.index("-profile:v") + 1] == "baseline" and "fastdecode" in cmd,
      "easy to decode on a slow Pi, as convert_videos.sh makes it")
check(g.out_ext("x.avi", {"subs": []}) == ".mp4" and g.out_ext("x.avi", {"subs": [(2, "subrip")]}) == ".mkv"
      and g.out_ext("x.MKV", {"subs": []}) == ".MKV", "the kind of file: kept if it can be")

# ---- 2. the app: leftovers tidied, links left alone, still being copied --------------------------------------------
open(V + "/.Old.converting.mp4", "wb").write(b"half")
os.symlink(V + "/Hevc Clip.mp4", V + "/Linked.mp4")
shutil.copy(V + "/Hevc Clip.mp4", V + "/Just Copied.mp4")           # (its date: now)
st0 = {}
os.chmod(V + "/Sixty.avi", 0o640)
st0["sixty"] = os.stat(V + "/Sixty.avi")
open(W + "/state.json", "w").write(json.dumps({"pos": {V + "/Sixty.avi": 2.5, V + "/Hevc Clip.mp4": 3.0},
                                               "dur": {}, "settings": {"shrink": "Leave them"}, "radio": {}}))

m = g.Media()
check(not any(k == "shrink" for k, _, _ in g.SETTINGS) and "shrink" not in g.SETTINGS_DEFAULT,
      "no Settings > Big videos: it makes them smaller whenever they need it")
check("shrink" not in m.state["settings"] and m.shrinker.enabled(),
      "...a Leave them saved before it went: forgotten, and it's on")
held = []
real_hold = m.shrinker.hold
m.load_tab(vi)                                                  # (the Videos tab: look now)
m.shrinker.tidy()
check(not os.path.exists(V + "/.Old.converting.mp4"), "a half-made copy from before: gone")
m.shrinker.look()
q = [B(p) for p in m.shrinker.queue]
print("queue:", q, {B(k): v[2] for k, v in m.shrinker.seen.items()})
check(q == ["Big Movie (2020).mkv", "Hevc Clip.mp4", "Just Copied.mp4", "Sixty.avi"], "the too-big ones queued")
check("Linked.mp4" not in [B(k) for k in m.shrinker.seen], "a link to a video: left alone")
check(m.shrinker.seen[V + "/Broken.mkv"][2] == "failed" and m.shrinker.seen[V + "/Small Fine.mp4"][2] == "ok",
      "unreadable: failed; small: ok")
ready = m.shrinker.ready()
check(ready and B(ready) == "Big Movie (2020).mkv", "the first one that's sat still")
rows = {it["title"]: m.row_right(it)[0] for it in m.tab_items(vi)}
check(rows.get("Hevc Clip") == "to convert", f"the Videos tab says so: {rows}")

# ---- 3. made smaller, in the background ---------------------------------------------------------------------------
m.shrinker.start()
check(wait_for(lambda: not os.path.exists(V + "/Sixty.avi"), 60), "Sixty.avi made smaller")
check(os.path.exists(V + "/Sixty.mp4"), "...as Sixty.mp4")
vs = vstream(V + "/Sixty.mp4")
check(vs["codec_name"] == "h264" and vs["avg_frame_rate"] in ("30/1", "30000/1000") and vs["profile"] in (
      "Constrained Baseline", "Baseline"), f"...H.264, 30 a second: {vs['codec_name']} {vs['avg_frame_rate']} {vs['profile']}")
st1 = os.stat(V + "/Sixty.mp4")
check(st1.st_mode & 0o777 == 0o640 and st1.st_mtime_ns == st0["sixty"].st_mtime_ns and st1.st_uid == st0["sixty"].st_uid,
      "...its mode, owner and date as they were")
check(wait_for(lambda: m.shrinker.queue == [] or m.shrinker.queue == [V + "/Just Copied.mp4"], 60), "the rest done")
bm = info(V + "/Big Movie (2020).mkv")
vb = next(s for s in bm["streams"] if s["codec_type"] == "video")
check((vb["width"], vb["height"]) == (640, 360), f"the 720p film: 640x360 ({vb['width']}x{vb['height']})")
check(any(s.get("codec_name") == "subrip" for s in bm["streams"]), "...its subtitles kept")
check(vstream(V + "/Hevc Clip.mp4")["codec_name"] == "h264", "HEVC: H.264 now, same name")
check([B(p) for p in m.shrinker.queue] == ["Just Copied.mp4"], "the one just copied waits its turn")
print("seen:", {B(k): v[2] for k, v in m.shrinker.seen.items()})
check(m.shrinker.seen[V + "/Sixty.mp4"][2] == "done" and V + "/Sixty.avi" not in m.shrinker.seen, "done: kept as done")
m.tick()
check(m.videos_changed is False, "the Videos tab looked again")
titles = [it["src"] for it in m.tab_items(vi)]
check(V + "/Sixty.mp4" in titles and V + "/Sixty.avi" not in titles, "...and has the new file")
state = json.load(open(W + "/state.json"))
check(state["pos"].get(V + "/Sixty.mp4") == 2.5 and V + "/Sixty.avi" not in state["pos"],
      "where you were in it: moved to the new name")
check(state["pos"].get(V + "/Hevc Clip.mp4") == 3.0, "...and kept for one with the same name")
saved = json.load(open(W + "/shrink.json"))
check(saved.get(V + "/Small Fine.mp4", [0, 0, ""])[2] == "ok", "what's been looked at is kept")
m.shrinker.look()
check([B(p) for p in m.shrinker.queue] == ["Just Copied.mp4"], "looked again: nothing new to do")

# ---- 4. held while a video plays; stopped part way ------------------------------------------------------------------
shutil.copy(SP + "/vids_long/long.mp4", V + "/Long Film.mp4")
os.utime(V + "/Long Film.mp4", (old, old))
os.utime(V + "/Just Copied.mp4", (old, old))
m.shrinker.poke()
check(wait_for(lambda: m.shrinker.current == V + "/Just Copied.mp4" or m.shrinker.current == V + "/Long Film.mp4"
               or vstream(V + "/Just Copied.mp4")["codec_name"] == "h264", 30), "started on the rest")
check(wait_for(lambda: m.shrinker.current == V + "/Long Film.mp4" and m.shrinker.pct >= 3, 90), "the long film under way")
rows = {it["title"]: m.row_right(it)[0] for it in m.tab_items(vi)}
m.load_tab(vi)
rows = {it["title"]: m.row_right(it)[0] for it in m.tab_items(vi)}
check(rows.get("Long Film", "").startswith("converting "), f"the Videos tab: {rows.get('Long Film')}")


class FakeProc:
    def __init__(self):
        self.stdin = io.StringIO()
        self.dead = False

    def poll(self):
        return 0 if self.dead else None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.dead = True


m.proc, m.kind = FakeProc(), "video"                           # a video plays
m.tick()
pid = m.shrinker.proc.pid
check(wait_for(lambda: proc_state(pid) == "T", 5), "a video plays: ffmpeg stopped where it is")
p1 = m.shrinker.pct
time.sleep(1.5)
check(m.shrinker.pct == p1 and proc_state(pid) == "T", "...and stays stopped")
m.proc, m.kind = None, None
m.tick()
check(wait_for(lambda: proc_state(pid) in ("R", "S", "D") , 5), "the video's over: on again")
check(wait_for(lambda: m.shrinker.pct > p1, 30), "...and getting on")
m.shrinker.enabled = lambda: False                             # off, part way
check(wait_for(lambda: m.shrinker.current is None, 15), "stopped part way: it stops")
check(os.path.exists(V + "/Long Film.mp4") and vstream(V + "/Long Film.mp4")["width"] == 1920,
      "...the film left as it was")
check(not any(n.startswith(".") for n in os.listdir(V)), "...and no half-made copy left")
check(m.shrinker.seen[V + "/Long Film.mp4"][2] == "big", "...still to do, if you turn it on again")
m.shrinker.poke()
time.sleep(6)
check(m.shrinker.current is None, "while it's off, nothing's done")

# ---- 5. no room -------------------------------------------------------------------------------------------------------
real_du = shutil.disk_usage
shutil.disk_usage = lambda p: type("U", (), {"free": 10_000_000, "total": 1 << 30, "used": 0})()
m.shrinker.enabled = lambda: True
m.shrinker.poke()
check(wait_for(lambda: m.shrinker.seen.get(V + "/Long Film.mp4", [0, 0, ""])[2].startswith("noroom:"), 20),
      "no room: noted, to try again later")
check(V + "/Long Film.mp4" not in m.shrinker.queue and m.shrinker.current is None, "...and not tried meanwhile")
shutil.disk_usage = real_du
g.NO_ROOM_WAIT = 0
m.shrinker.seen[V + "/Long Film.mp4"][2] = "noroom:0"
m.shrinker.poke()
check(wait_for(lambda: m.shrinker.current == V + "/Long Film.mp4", 20), "room again: tried again")

# a video deleted while it's being made smaller
check(wait_for(lambda: m.shrinker.pct >= 2, 60), "under way again")
os.remove(V + "/Long Film.mp4")
check(wait_for(lambda: m.shrinker.current is None, 120), "deleted part way: it gives up")
check(not os.path.exists(V + "/Long Film.mp4") and not any(n.startswith(".") for n in os.listdir(V)),
      "...and leaves nothing behind")

# ---- 6. playing one that's waiting: a word about it; Sixty (2) ------------------------------------------------------
shutil.copy(SP + "/vids/Sixty.avi", V + "/Sixty.avi")          # (Sixty.mp4 is there already)
m.shrinker.hold(True)
m.shrinker.look()
check(V + "/Sixty.avi" in m.shrinker.queue, "another Sixty.avi: queued")
m.load_tab(vi)
items = m.tab_items(vi)
k = next(i for i, it in enumerate(items) if it["src"] == V + "/Sixty.avi")
m.spawn = lambda args, target: (setattr(m, "proc", FakeProc()), setattr(m, "started", time.monotonic()))
m.active = False
m.play(items, k)
check(getattr(m, "screen_note", None) and "smaller" in m.screen_note[0], "playing it before it's done: a word about it")
m.stop()
m.shrinker.hold(False)
os.utime(V + "/Sixty.avi", (old, old))
m.shrinker.poke()
check(wait_for(lambda: os.path.exists(V + "/Sixty (2).mp4"), 60), "a name that's taken: Sixty (2).mp4")
check(os.path.exists(V + "/Sixty.mp4") and not os.path.exists(V + "/Sixty.avi"), "...the other one left be")

# ---- 7. no ffmpeg: nothing happens ----------------------------------------------------------------------------------
m.shrinker.stop()
s2 = g.Shrinker()
real_which = shutil.which
shutil.which = lambda n: None
check(s2.tools() is False, "without ffmpeg: it doesn't try")
shutil.which = real_which
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
