"""Videos too big for this Pi to play smoothly, made smaller by the Pi itself, in the background: a 1080p film on
a Pi Zero, or one in a kind that's hard work anywhere (HEVC, VP9, AV1). One at a time, by ffmpeg at the lowest
priority, held while a video or a game plays. The smaller copy is checked, then takes the original's place."""
import glob
import json
import math
import os
import re
import shutil
import signal
import subprocess
import threading
import time

from .screen import screen_size, slow_pi
from .util import find_files, VIDEO_EXTS

SHRINK_FILE = "/var/lib/pitato/shrink.json"   # each video looked at: path -> [size, mtime, what it is]
VIDEO_DIRS = ("/home/*/Videos",)
LOOK_EVERY = 300          # seconds between looks for new videos (at once when the Videos tab opens)
SETTLE = 60               # seconds a file sits unchanged (still being copied?) before it's made smaller
NO_ROOM_WAIT = 3600       # seconds before a video there wasn't room for is tried again
EASY = {"h264", "mpeg4", "mpeg2video", "mpeg1video", "msmpeg4v3", "msmpeg4v2", "h263", "mjpeg"}
TEXT_SUBS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}
PICTURE_SUBS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}
MUXERS = {".mkv": "matroska", ".mp4": "mp4", ".m4v": "mp4", ".mov": "mov"}
WORKING = ".converting"   # the copy being made: .<name>.converting.<ext>, hidden, beside the original


def target_box():
    """The most a video can be for this Pi: (width, height), and whether it's a slow Pi. A Pi Zero, 1, 2 or 3 plays
    480 lines smoothly (the GPi Case's 640x480 screen, or 854x480 on a TV); a Pi 4 or 5 plays 1080p, and a video
    made smaller for it is made 720p."""
    w, h = screen_size()
    if slow_pi():
        return (min(max(w, 640), 854), 480), True
    return (1280, 720), False


def probe(path):
    """What's in a video, by ffprobe: {"codec", "w", "h", "fps", "bits", "duration", "subs": [(index, codec)],
    "audio": bool}, or None if it can't be read."""
    try:
        r = subprocess.run(["nice", "-n", "19", "ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                            "-show_streams", path], capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    if video is None:
        return None

    def rate(text):
        try:
            a, _, b = str(text or "0/1").partition("/")
            return float(a) / float(b or 1) if float(b or 1) else 0.0
        except ValueError:
            return 0.0
    try:
        duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {"codec": video.get("codec_name", ""), "w": int(video.get("width") or 0), "h": int(video.get("height") or 0),
            "fps": rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate")),
            "bits": 10 if re.search(r"1[02]le|p10|p12", video.get("pix_fmt", "")) else 8,
            "duration": duration, "audio": any(s.get("codec_type") == "audio" for s in streams),
            "subs": [(s.get("index"), s.get("codec_name", "")) for s in streams if s.get("codec_type") == "subtitle"]}


def too_big(info, box, slow):
    """Why a video won't play smoothly here ('' when it will)."""
    bw, bh = box
    if info["codec"] not in EASY or info["bits"] > 8:
        return info["codec"] or "unknown"
    if slow:
        if info["w"] > bw * 1.05 or info["h"] > bh * 1.05:
            return f"{info['w']}x{info['h']}"
        if info["fps"] > 31:
            return f"{info['fps']:.0f} fps"
    elif info["w"] > 1920 * 1.05 or info["h"] > 1088 * 1.05 or (info["fps"] > 31 and info["h"] > 728):
        return f"{info['w']}x{info['h']} at {info['fps']:.0f} fps"
    return ""


def command(src, dst, info, box, slow, subs=True):
    """ffmpeg's command to make src smaller into dst: fitted in the box (never bigger than it was), 30 frames a
    second at most, H.264 that's easy to decode (on a slow Pi, as convert_videos.sh makes it), stereo AAC, and
    the subtitles kept."""
    bw, bh = box
    vf = f"scale='min({bw},iw)':'min({bh},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    if info["fps"] > 31:
        vf += f",fps={info['fps'] / math.ceil(info['fps'] / 30.5):.3f}"      # (60 a second: 30; 50: 25; 120: 30)
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    cmd += (["-profile:v", "baseline", "-tune", "fastdecode", "-crf", "25"] if slow else
            ["-profile:v", "high", "-crf", "23"])
    cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    ext = os.path.splitext(dst)[1].lower()
    mkv = ext == ".mkv"
    k = 0
    for index, codec in (info["subs"] if subs else []):
        if codec in TEXT_SUBS:
            cmd += ["-map", f"0:{index}", f"-c:s:{k}", ("copy" if codec != "mov_text" else "srt") if mkv else "mov_text"]
        elif codec in PICTURE_SUBS and mkv:
            cmd += ["-map", f"0:{index}", f"-c:s:{k}", "copy"]
        else:
            continue
        k += 1
    if not mkv:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-max_muxing_queue_size", "4096", "-f", MUXERS.get(ext, "mp4"), "-progress", "pipe:1", "-nostats", dst]
    return cmd


def out_ext(path, info):
    """The smaller copy's kind of file: the original's when it's a common one (so its name stays the same), else
    .mkv when it has subtitles to keep, else .mp4."""
    ext = os.path.splitext(path)[1].lower()
    if ext in MUXERS:
        return os.path.splitext(path)[1]
    return ".mkv" if info["subs"] else ".mp4"


class Shrinker:
    """Looks for videos too big for this Pi, and makes them smaller, one at a time, on a thread of its own.
    hold() keeps it still (a video or a game is playing); status() says how a video's getting on."""

    def __init__(self, enabled=lambda: True):
        self.enabled = enabled
        self.on_done = lambda old, new: None         # a video replaced by its smaller copy (its thread)
        self.seen = {}                               # path -> [size, mtime, what it is: ok, big, done, failed, noroom]
        self.queue = []                              # videos waiting to be made smaller
        self.current = None                          # the one being made smaller
        self.pct = 0
        self.proc = None
        self.held = False                            # (wanted) ...and whether ffmpeg is stopped for it
        self.stopped = False
        self.quit = False
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.next_look = 0.0
        self.thread = None
        self.load()

    # -- what's been looked at, kept --------------------------------------------------------------------------------
    def load(self):
        try:
            with open(SHRINK_FILE) as f:
                data = json.load(f)
            self.seen = {k: v for k, v in data.items() if isinstance(v, list) and len(v) == 3}
        except (OSError, ValueError, AttributeError):
            self.seen = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(SHRINK_FILE), exist_ok=True)
            with self.lock:
                text = json.dumps(self.seen)
            with open(SHRINK_FILE + ".tmp", "w") as f:
                f.write(text)
            os.replace(SHRINK_FILE + ".tmp", SHRINK_FILE)
        except OSError:
            pass

    # -- asked from outside ---------------------------------------------------------------------------------------------
    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def poke(self):
        """Look for new videos now (the Videos tab opened, say)."""
        self.next_look = 0.0
        self.wake.set()

    def hold(self, on):
        """Stop where it is (on) or carry on: ffmpeg is stopped while a video or a game plays."""
        self.held = on
        p = self.proc
        if p is None or p.poll() is not None or self.stopped == on:
            return
        try:
            os.killpg(p.pid, signal.SIGSTOP if on else signal.SIGCONT)
            self.stopped = on
        except OSError:
            pass
        if not on:
            self.wake.set()

    def status(self, path):
        """('converting', percent), ('waiting', 0), or None for a video that's fine as it is."""
        if path == self.current:
            return "converting", self.pct
        if path in self.queue:
            return "waiting", 0
        return None

    def stop(self):
        self.quit = True
        self.kill()
        self.wake.set()

    def kill(self):
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGCONT)
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass

    # -- its thread -------------------------------------------------------------------------------------------------
    @staticmethod
    def tools():
        return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

    def run(self):
        self.tidy()
        while not self.quit:
            self.wake.clear()
            try:
                if self.tools() and self.enabled():
                    if time.monotonic() >= self.next_look:
                        self.next_look = time.monotonic() + LOOK_EVERY
                        self.look()
                    path = self.ready()
                    if path and not self.held:
                        self.convert(path)
                        continue
            except Exception as ex:                       # (never stops for good)
                print(f"videos: {ex!r}", flush=True)
            self.wake.wait(5)

    def tidy(self):
        """Copies left half made (the Pi went off): gone."""
        for folder in self.folders():
            for root, _, names in os.walk(folder):
                for n in names:
                    if n.startswith(".") and WORKING + "." in n:
                        try:
                            os.remove(os.path.join(root, n))
                        except OSError:
                            pass

    @staticmethod
    def folders():
        return [d for pattern in VIDEO_DIRS for d in glob.glob(pattern) if os.path.isdir(d)]

    def look(self):
        """Every video in Videos looked at (once, unless it changes): the too-big ones are queued."""
        box, slow = target_box()
        queue, changed = [], False
        for path in find_files(VIDEO_DIRS, VIDEO_EXTS):
            if os.path.islink(path):                       # (a link to a video somewhere else: left as it is)
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = [st.st_size, int(st.st_mtime)]
            was = self.seen.get(path)
            what = was[2] if was and was[:2] == key else None
            if what and what.startswith("noroom:") and time.time() >= float(what[7:]):
                what = None                                # (time to see if there's room now)
            if what is None:
                info = probe(path)
                what = "failed" if info is None else ("big" if too_big(info, box, slow) else "ok")
                with self.lock:
                    self.seen[path] = key + [what]
                changed = True
            if what == "big":
                queue.append(path)
        with self.lock:
            gone = [p for p in self.seen if not os.path.exists(p)]
            for p in gone:
                self.seen.pop(p, None)
            self.queue = queue
        if changed or gone:
            self.save()

    def ready(self):
        """The first video waiting that's sat still long enough (not still being copied)."""
        for path in list(self.queue):
            try:
                if time.time() - os.path.getmtime(path) >= SETTLE:
                    return path
            except OSError:
                self.queue.remove(path)
        return None

    def mark(self, path, what):
        try:
            st = os.stat(path)
        except OSError:
            return
        if what == "noroom":
            what = f"noroom:{time.time() + NO_ROOM_WAIT:.0f}"   # (tried again after a while)
        with self.lock:
            self.seen[path] = [st.st_size, int(st.st_mtime), what]
            if path in self.queue:
                self.queue.remove(path)
        self.save()

    def convert(self, path):
        """One video made smaller, checked, and put in the original's place."""
        info = probe(path)
        box, slow = target_box()
        if info is None or not too_big(info, box, slow):
            self.mark(path, "failed" if info is None else "ok")
            return
        folder, name = os.path.split(path)
        stem, ext = os.path.splitext(name)
        new_ext = out_ext(path, info)
        work = os.path.join(folder, f".{stem}{WORKING}{new_ext}")
        rate = 0.25e6 if slow else 0.6e6                 # bytes a second, about, of the smaller copy
        need = (info["duration"] * rate if info["duration"] else os.path.getsize(path) / 2) + 200e6
        if shutil.disk_usage(folder).free < need:
            print(f"videos: no room to make {name} smaller", flush=True)
            self.mark(path, "noroom")
            return
        print(f"videos: making {name} smaller ({too_big(info, box, slow)} -> fits {box[0]}x{box[1]})", flush=True)
        self.current, self.pct = path, 0
        ok = False
        try:
            for subs in (True, False):                  # (subtitles it can't keep: again without them)
                ok = self.run_ffmpeg(command(path, work, info, box, slow, subs=subs), info["duration"])
                if ok or self.quit or not self.enabled() or not os.path.exists(path):
                    break
            if ok:
                ok = os.path.exists(path) and self.check(work, info)
            if ok:
                self.replace(path, work, stem, new_ext)
            elif not self.quit and self.enabled() and os.path.exists(path):
                print(f"videos: couldn't make {name} smaller", flush=True)
                self.mark(path, "failed")
        finally:
            self.current, self.proc, self.stopped = None, None, False
            if os.path.exists(work):
                try:
                    os.remove(work)
                except OSError:
                    pass

    def run_ffmpeg(self, cmd, duration):
        cmd = ["nice", "-n", "19"] + (["ionice", "-c", "3"] if shutil.which("ionice") else []) + cmd
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                         start_new_session=True)
        except OSError as ex:
            print(f"videos: ffmpeg didn't start ({ex})", flush=True)
            return False
        self.stopped = False
        if self.held:
            self.hold(True)
        for line in self.proc.stdout:
            k, _, v = line.strip().partition("=")
            if k in ("out_time_us", "out_time_ms") and duration:
                try:
                    self.pct = max(0, min(99, int(int(v) / 1e6 / duration * 100)))
                except ValueError:
                    pass
            if self.quit or not self.enabled():
                self.kill()
        return self.proc.wait() == 0 and not self.quit and self.enabled()

    @staticmethod
    def check(work, info):
        """The smaller copy is whole: a video, as long as the original (when that's known)."""
        got = probe(work)
        if got is None or not got["w"]:
            return False
        if info["duration"] and got["duration"] < min(info["duration"] - 5, info["duration"] * 0.97):
            return False
        return True

    def replace(self, path, work, stem, new_ext):
        st = os.stat(path)
        folder = os.path.dirname(path)
        final = os.path.join(folder, stem + new_ext)
        n = 2
        while final != path and os.path.exists(final):   # (another video has that name: this one's renamed)
            final = os.path.join(folder, f"{stem} ({n}){new_ext}")
            n += 1
        try:
            os.chown(work, st.st_uid, st.st_gid)
            os.chmod(work, st.st_mode & 0o777)
            os.utime(work, ns=(st.st_atime_ns, st.st_mtime_ns))   # (its date as it was: lists keep their order)
        except OSError:
            pass
        os.replace(work, final)
        if final != path:
            os.remove(path)
        print(f"videos: {os.path.basename(path)} is smaller now"
              + (f" ({os.path.basename(final)})" if final != path else ""), flush=True)
        with self.lock:
            self.seen.pop(path, None)
        self.mark(final, "done")
        self.on_done(path, final)
