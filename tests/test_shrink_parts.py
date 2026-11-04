"""Big videos made smaller in parts on a slow Pi (shrink.py), with real ffmpeg and parts of 10 seconds: each kept as
it's done; stopped part way (the Pi going off) and started again, it carries on from them rather than starting over,
and the copy comes out as one made in one go would (frames, sound, subtitles, length); a video changed meanwhile
starts afresh, one deleted has its parts tidied away; parts that don't work: in one go (and remembered); no room
for parts: in one go; a picture that ends before the sound; a fast Pi and a short video: in one go as before."""
import json, os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
SRC = SP + "/t_parts_src"                    # (proto_parts.py makes these)
W = SP + "/t_shrink_parts"
shutil.rmtree(W, ignore_errors=True)
V = W + "/Videos"
os.makedirs(V)
os.makedirs(W + "/static")
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.shrink as sh

g.VIDEO_DIRS = (V,)
g.SHRINK_FILE = W + "/shrink.json"
g.STATE_FILE = W + "/state.json"
g.CACHE_DIR = W + "/cache"
g.home_dir = lambda: W
g.screen_size = lambda: (640, 480)
g.slow_pi = lambda: True
g.PART_SECS = 10
g.SETTLE = 0
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
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


def frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.split()
    return sorted(float(x.split(",")[0]) for x in out if x.split(",")[0] not in ("", "N/A"))


old = time.time() - 3 * 86400


def put(src, name):
    shutil.copy(src, V + "/" + name)
    os.utime(V + "/" + name, (old, old))
    return V + "/" + name


ffmpegs = []                                 # what ffmpeg was asked to do: "part 3", "join", "whole"
real_popen = subprocess.Popen


class Popen(real_popen):
    def __init__(self, args, *a, **k):
        if isinstance(args, list) and "ffmpeg" in args:
            if "-copyts" in args:
                ss = args[args.index("-ss") + 1] if "-ss" in args else "0"
                ffmpegs.append(f"part {int(float(ss)) // 10}")
            elif "concat" in args:
                ffmpegs.append("join")
            else:
                ffmpegs.append("whole")
        super().__init__(args, *a, **k)


subprocess.Popen = Popen
P = V + "/.Long Film.mkv.parts"

# ---- 1. made in parts; the Pi goes off part way ------------------------------------------------------------------
film = put(SRC + "/a_offset.mkv", "Long Film.mkv")
st0 = os.stat(film)
s1 = g.Shrinker()
s1.start()
check(wait_for(lambda: os.path.exists(P + "/part-0002.nut"), 120), "parts made, and kept as each is done")
plan = json.load(open(P + "/plan.json"))
check(plan["n"] == 7 and plan["part"] == 10 and plan["size"] == st0.st_size, f"...its plan: {plan}")
check(s1.current == film and 20 <= s1.pct <= 99, f"...how far it's got: {s1.pct}%")
s1.stop()                                    # (the Pi goes off)
check(wait_for(lambda: s1.current is None, 20), "stopped part way")
done = sorted(n for n in os.listdir(P) if n.startswith("part-"))
check(len(done) >= 3 and os.path.exists(film) and os.stat(film).st_size == st0.st_size,
      f"...the parts made so far kept ({len(done)}), the film as it was")
check(not any(n.startswith(".") and "converting" in n for n in os.listdir(V)), "...no half-made copy left")
open(P + "/.part-0005.nut", "wb").write(b"half")      # (as if it was making one as the Pi went off)

# ---- 2. started again: it carries on ---------------------------------------------------------------------------------
ffmpegs.clear()
s2 = g.Shrinker()
s2.tidy()
check(os.path.isdir(P) and not os.path.exists(P + "/.part-0005.nut") and len(
      [n for n in os.listdir(P) if n.startswith("part-")]) == len(done), "started again: its parts kept, the half one gone")
s2.start()
check(wait_for(lambda: not os.path.exists(P) and s2.current is None, 180), "finished")
check(not any(f"part {k}" in ffmpegs for k in range(len(done))) and ffmpegs.count("join") == 1,
      f"...carrying on from where it was, not again from the start ({ffmpegs})")
out = info(film)
vs = next(s for s in out["streams"] if s["codec_type"] == "video")
check((vs["width"], vs["height"]) == (640, 360) and vs["profile"] in ("Constrained Baseline", "Baseline"),
      f"the copy: {vs['width']}x{vs['height']} {vs['profile']}")
check(any(s["codec_type"] == "audio" and s["channels"] == 2 for s in out["streams"])
      and any(s.get("codec_name") == "subrip" for s in out["streams"]), "...its sound, and subtitles kept")
check(abs(float(out["format"]["duration"]) - 65.06) < 0.1, f"...as long as it was: {out['format']['duration']}")
one = W + "/one.mkv"
inf = g.probe(SRC + "/a_offset.mkv")
subprocess.run(g.command(SRC + "/a_offset.mkv", one, inf, (640, 480), True), check=True, stdout=subprocess.DEVNULL)
f1, f2 = frames(one), frames(film)
check(len(f1) == len(f2) and max(abs(a - b) for a, b in zip(f1, f2)) < 0.002,
      f"...the same frames at the same times as one made in one go ({len(f2)} of {len(f1)})")
a1 = next(s for s in info(one)["streams"] if s["codec_type"] == "audio")
a2 = next(s for s in out["streams"] if s["codec_type"] == "audio")
check(a1["start_time"] == a2["start_time"] and a1["duration_ts"] == a2["duration_ts"] if "duration_ts" in a1
      else a1["start_time"] == a2["start_time"], "...and its sound where it was")
check(s2.seen.get(film, [0, 0, ""])[2] == "done", "done: kept as done")
s2.stop()

# ---- 3. changed meanwhile: afresh; deleted: its parts tidied away -------------------------------------------------------
film2 = put(SRC + "/b_1080.mp4", "Second.mp4")
P2 = V + "/.Second.mp4.parts"
s3 = g.Shrinker()
s3.start()
check(wait_for(lambda: os.path.exists(P2 + "/part-0001.nut"), 120), "another one under way")
s3.stop()
wait_for(lambda: s3.current is None, 20)
with open(film2, "ab") as f:                  # (changed while the Pi was off)
    f.write(b"\0" * 1000)
os.utime(film2, (old + 5, old + 5))
s4 = g.Shrinker()
s4.tidy()
check(not os.path.exists(P2), "the video changed meanwhile: its parts gone")
ffmpegs.clear()
s4.start()
check(wait_for(lambda: os.path.exists(P2 + "/part-0001.nut"), 120) and "part 0" in ffmpegs, "...made afresh")
s4.stop()
wait_for(lambda: s4.current is None, 20)
os.remove(film2)
s5 = g.Shrinker()
s5.tidy()
check(not os.path.exists(P2), "a video deleted while the Pi was off: its parts tidied away")

# ---- 4. parts that don't work: in one go, and remembered -------------------------------------------------------------
film3 = put(SRC + "/e_hevc.mp4", "Third.mp4")
P3 = V + "/.Third.mp4.parts"
real_part = g.part_command
g.part_command = lambda *a, **k: real_part(*a, **k)[:-2] + ["-no_such_option", "1"] + real_part(*a, **k)[-2:]
ffmpegs.clear()
s6 = g.Shrinker()
s6.start()
check(wait_for(lambda: s6.seen.get(film3, [0, 0, ""])[2] == "done", 180), "parts that don't work: made in one go")
check(ffmpegs[:2] == ["part 0", "whole"] and not os.path.exists(P3), f"...({ffmpegs})")
check(next(s for s in info(film3)["streams"] if s["codec_type"] == "video")["codec_name"] == "h264", "...H.264 now")
s6.stop()
wait_for(lambda: s6.current is None, 20)
g.part_command = real_part
film4 = put(SRC + "/f_vfr.mkv", "Fourth.mkv")
s7 = g.Shrinker()
s7.mark(film4, "whole")                       # (as if its parts hadn't worked, before the Pi went off)
s7.queue = [film4]
ffmpegs.clear()
s7.convert(film4)
check(ffmpegs == ["whole"] and s7.seen[film4][2] == "done", f"...and next time, straight to one go ({ffmpegs})")

# ---- 5. no room for the parts as well as the copy: in one go -----------------------------------------------------------
film5 = put(SRC + "/c_60.avi", "Fifth.avi")
need = 65 * 0.25e6 + 200e6
real_du = shutil.disk_usage
shutil.disk_usage = lambda p: type("U", (), {"free": int(need + 5e6), "total": 1 << 40, "used": 0})()   # (the copy fits; its parts too, not)
ffmpegs.clear()
s8 = g.Shrinker()
s8.queue = [film5]
s8.convert(film5)
shutil.disk_usage = real_du
check(ffmpegs == ["whole"] and os.path.exists(V + "/Fifth.mp4"), f"no room for parts too: in one go ({ffmpegs})")

# ---- 6. a picture that ends before the sound -----------------------------------------------------------------------------
short = W + "/short_pic.mkv"
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=32",
                "-f", "lavfi", "-i", "sine=duration=58", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                short], check=True)
film6 = put(short, "Short Picture.mkv")
ffmpegs.clear()
s9 = g.Shrinker()
s9.queue = [film6]
s9.convert(film6)
out = info(film6)
vs = next((s for s in out.get("streams", []) if s["codec_type"] == "video"), {})
check(vs.get("width") == 640 and abs(float(out["format"]["duration"]) - 58) < 0.2 and "join" in ffmpegs,
      f"a picture that ends before the sound: {len(frames(film6))} frames, {out['format'].get('duration')} s ({ffmpegs})")

# ---- 7. a fast Pi, a short video: in one go, as before -------------------------------------------------------------------
g.slow_pi = lambda: False
film7 = put(SRC + "/e_hevc.mp4", "Seventh.mp4")
ffmpegs.clear()
s10 = g.Shrinker()
s10.queue = [film7]
s10.convert(film7)
check(ffmpegs == ["whole"], f"a fast Pi: in one go ({ffmpegs})")
g.slow_pi = lambda: True
g.PART_SECS = 120
film8 = put(SRC + "/b_1080.mp4", "Eighth.mp4")
ffmpegs.clear()
s11 = g.Shrinker()
s11.queue = [film8]
s11.convert(film8)
check(ffmpegs == ["whole"], f"a video not much longer than a part: in one go ({ffmpegs})")
check(not any(n.endswith(".parts") for n in os.listdir(V)), "no parts left anywhere")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
