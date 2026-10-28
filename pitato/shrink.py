"""Videos too big for this Pi to play smoothly, made smaller by the Pi itself, in the background: a 1080p film on
a Pi Zero, or one in a kind that's hard work anywhere (HEVC, VP9, AV1). One at a time, by ffmpeg at the lowest
priority, held while a video or a game plays. The smaller copy is checked, then takes the original's place.

On a Pi Zero that takes hours for a film, longer than the Pi's often on for, so there a long video's picture is
made a couple of minutes at a time, each part kept as it's done, beside the video in a hidden folder (.<its
name>.parts): turned off part way, the Pi carries on where it was next time, rather than starting again. Once
they're all done they're put together with its sound and subtitles."""
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
PART_SECS = 120           # on a slow Pi, a longer video's picture is made this many seconds at a time
PARTS = ".parts"          # ...each part kept, as it's done, in .<its name>.parts beside it (and a note of the plan)
PARTS_HOW = 1             # (how parts are made: parts from before a change to that are started again)


def target_box():
    """The most a video can be for this Pi: (width, height), and whether it's a slow Pi. A Pi Zero, 1, 2 or 3 plays
    480 lines smoothly (the GPi Case's 640x480 screen, or 854x480 on a TV); a Pi 4 or 5 plays 1080p, and a video
    made smaller for it is made 720p."""
    w, h = screen_size()
    if slow_pi():
        return (min(max(w, 640), 854), 480), True
    return (1280, 720), False


def probe(path):
    """What's in a video, by ffprobe: {"codec", "vindex" (its picture's stream), "start" (its times start there),
    "w", "h", "fps", "bits", "duration", "subs": [(index, codec)], "audio": bool}, or None if it can't be read."""
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
    try:
        start = float((data.get("format") or {}).get("start_time") or 0)
    except ValueError:
        start = 0.0
    return {"codec": video.get("codec_name", ""), "vindex": video.get("index"), "start": start,
            "w": int(video.get("width") or 0), "h": int(video.get("height") or 0),
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


def picture_args(info, box, slow):
    """ffmpeg's part of a command for the picture, made smaller: fitted in the box (never bigger than it was), 30
    frames a second at most, and H.264 that's easy to decode (on a slow Pi, as convert_videos.sh makes it)."""
    bw, bh = box
    vf = f"scale='min({bw},iw)':'min({bh},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    if info["fps"] > 31:
        vf += f",fps={info['fps'] / math.ceil(info['fps'] / 30.5):.3f}"      # (60 a second: 30; 50: 25; 120: 30)
    cmd = ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    cmd += (["-profile:v", "baseline", "-tune", "fastdecode", "-crf", "25"] if slow else
            ["-profile:v", "high", "-crf", "23"])
    return cmd


def sound_and_rest(dst, info, subs=True, src=0):
    """The rest of ffmpeg's command: stereo AAC, the subtitles kept (from input src), and the file it makes."""
    cmd = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    ext = os.path.splitext(dst)[1].lower()
    mkv = ext == ".mkv"
    k = 0
    for index, codec in (info["subs"] if subs else []):
        if codec in TEXT_SUBS:
            cmd += ["-map", f"{src}:{index}", f"-c:s:{k}",
                    ("copy" if codec != "mov_text" else "srt") if mkv else "mov_text"]
        elif codec in PICTURE_SUBS and mkv:
            cmd += ["-map", f"{src}:{index}", f"-c:s:{k}", "copy"]
        else:
            continue
        k += 1
    if not mkv:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-max_muxing_queue_size", "4096", "-f", MUXERS.get(ext, "mp4"), "-progress", "pipe:1", "-nostats", dst]
    return cmd


def picture_map(info):
    """Which stream is the picture (not a cover picture that comes first)."""
    return f"0:{info['vindex']}" if info.get("vindex") is not None else "0:v:0"


def command(src, dst, info, box, slow, subs=True):
    """ffmpeg's command to make src smaller into dst, in one go: the picture made smaller (picture_args), stereo
    AAC, and the subtitles kept."""
    return (["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", src, "-map", picture_map(info),
             "-map", "0:a:0?"] + picture_args(info, box, slow) + sound_and_rest(dst, info, subs))


def part_command(src, dst, info, box, slow, start, end):
    """ffmpeg's command for one part of a long video: its picture from start to end (seconds from the video's own
    start; end None: to the end), made smaller as command() makes it, into a NUT file. Each frame keeps the time it
    had in the video (-copyts: ffmpeg would otherwise move a part's times, and by how much depends on the kind of
    file), and the part ends just where the next begins: not a frame twice, nor one missed."""
    first = info.get("start") or 0.0
    cut = f"trim=start={first + start:.6f}" + (f":end={first + end:.6f}" if end is not None else "")
    args = picture_args(info, box, slow)
    vf = args[args.index("-vf") + 1]
    args[args.index("-vf") + 1] = cut + "," + vf + ("," + cut if ",fps=" in vf else "")   # (the frames, as they were,
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-copyts"]        # and again as fps made them)
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-t", f"{end - start + 30:.3f}"]   # (it needn't read on: the trim's what ends it just there)
    return (cmd + ["-i", src, "-map", picture_map(info)] + args
            + ["-max_muxing_queue_size", "4096", "-f", "nut", "-progress", "pipe:1", "-nostats", dst])


def join_command(listing, src, dst, info, offset, subs=True):
    """ffmpeg's command putting the parts together (listing: ffmpeg's concat list of them, each as long as from its
    first frame to the next part's) with the video's own sound, made stereo AAC, and its subtitles. offset: when the
    picture starts after the video does (ffmpeg would otherwise start it with the sound)."""
    return (["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-itsoffset", f"{offset:.6f}", "-f", "concat",
             "-safe", "0", "-i", listing, "-i", src, "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy"]
            + sound_and_rest(dst, info, subs, src=1))


def first_time(path):
    """When a file's first frame is, in seconds (0.0 if it can't be told)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=start_time", "-of",
                            "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=60)
        return max(0.0, float(r.stdout.strip() or 0))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def parts_dir(path):
    """Where a long video's parts are kept as they're made: a hidden folder beside it."""
    folder, name = os.path.split(path)
    return os.path.join(folder, f".{name}{PARTS}")


def read_plan(pdir):
    try:
        with open(os.path.join(pdir, "plan.json")) as f:
            plan = json.load(f)
        return plan if isinstance(plan, dict) else None
    except (OSError, ValueError):
        return None


def folder_size(folder):
    total = 0
    try:
        for en in os.scandir(folder):
            if en.is_file(follow_symlinks=False):
                total += en.stat().st_size
    except OSError:
        pass
    return total


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
        self.seen = {}                               # path -> [size, mtime, what it is: ok, big, done, failed, noroom,
                                                     # or whole: big, and its parts didn't work, so it's made in one go]
        self.queue = []                              # videos waiting to be made smaller
        self.current = None                          # the one being made smaller
        self.pct = 0
        self.frames = None                           # (frames ffmpeg has made, as it says)
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
        """Copies left half made (the Pi went off): gone. A long video's parts are kept (it carries on from them), all
        but the one it was making, unless the video's gone or changed meanwhile."""
        for folder in self.folders():
            for root, dirs, names in os.walk(folder):
                for n in names:
                    if n.startswith(".") and WORKING + "." in n:
                        try:
                            os.remove(os.path.join(root, n))
                        except OSError:
                            pass
                for d in [d for d in dirs if d.startswith(".") and d.endswith(PARTS)]:
                    dirs.remove(d)                       # (not looked inside by the walk)
                    self.tidy_parts(os.path.join(root, d))

    @staticmethod
    def tidy_parts(pdir):
        name = os.path.basename(pdir)[1:-len(PARTS)]
        plan = read_plan(pdir)
        try:
            st = os.stat(os.path.join(os.path.dirname(pdir), name))
            fits = bool(plan) and plan.get("size") == st.st_size and plan.get("mtime") == int(st.st_mtime)
        except OSError:
            fits = False
        if not fits:
            shutil.rmtree(pdir, ignore_errors=True)
            return
        for n in os.listdir(pdir):
            if n.startswith("."):                        # (the part it was making)
                try:
                    os.remove(os.path.join(pdir, n))
                except OSError:
                    pass

    @staticmethod
    def folders():
        return [d for pattern in VIDEO_DIRS for d in glob.glob(pattern) if os.path.isdir(d)]

    def look(self):
        """Every video in Videos looked at (once, unless it changes): the too-big ones are queued."""
        self.tidy()                                        # (parts of one deleted meanwhile, say)
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
            if what in ("big", "whole"):
                queue.append(path)
        with self.lock:
            gone = [p for p in self.seen if not os.path.exists(p)]
            for p in gone:
                self.seen.pop(p, None)
            self.queue = queue
        if changed or gone:
            self.save()

    def ready(self):
        """The first video waiting that's sat still long enough (not still being copied): one with parts made
        already first, so it's finished."""
        settled = []
        for path in list(self.queue):
            try:
                if time.time() - os.path.getmtime(path) >= SETTLE:
                    settled.append(path)
            except OSError:
                self.queue.remove(path)
        started = [p for p in settled if os.path.isdir(parts_dir(p))]
        return (started or settled or [None])[0]

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
        """One video made smaller, checked, and put in the original's place. On a slow Pi, a long one's made a
        part at a time (convert_parts), so the Pi going off loses only the part it was on; in one go if there's no
        room for the parts as well as the copy, or they don't work for it."""
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
        copy = (info["duration"] * rate if info["duration"] else os.path.getsize(path) / 2) + 200e6
        pdir = parts_dir(path)
        plan = self.plan(path, info, box, slow)
        kept = folder_size(pdir)
        free = shutil.disk_usage(folder).free
        if plan and free < copy + max(0.0, copy - 200e6 - kept):
            plan = None                                  # (no room for the parts as well as the copy: in one go)
        if not plan and os.path.isdir(pdir):
            shutil.rmtree(pdir, ignore_errors=True)
            free += kept
        if free < copy:
            print(f"videos: no room to make {name} smaller", flush=True)
            self.mark(path, "noroom")
            return
        print(f"videos: making {name} smaller ({too_big(info, box, slow)} -> fits {box[0]}x{box[1]})"
              + (f", {plan['n']} parts" if plan else ""), flush=True)
        self.current, self.pct = path, 0
        ok = False
        try:
            if plan:
                ok = self.convert_parts(path, work, info, box, slow, plan) and os.path.exists(path) \
                    and self.check(work, info)
                if not ok and not self.quit and self.enabled() and os.path.exists(path):
                    print(f"videos: {name} didn't work in parts: in one go", flush=True)
                    shutil.rmtree(pdir, ignore_errors=True)
                    self.mark(path, "whole")
                    self.current, self.pct, plan = path, 0, None
            if not plan:
                for subs in (True, False):              # (subtitles it can't keep: again without them)
                    ok = self.run_ffmpeg(command(path, work, info, box, slow, subs=subs), info["duration"])
                    if ok or self.quit or not self.enabled() or not os.path.exists(path):
                        break
                if ok:
                    ok = os.path.exists(path) and self.check(work, info)
            if ok:
                self.replace(path, work, stem, new_ext)
                shutil.rmtree(pdir, ignore_errors=True)
            elif not self.quit and self.enabled() and os.path.exists(path):
                print(f"videos: couldn't make {name} smaller", flush=True)
                self.mark(path, "failed")
                shutil.rmtree(pdir, ignore_errors=True)
        finally:
            self.current, self.proc, self.stopped = None, None, False
            if os.path.exists(work):
                try:
                    os.remove(work)
                except OSError:
                    pass
            if not os.path.exists(path):
                shutil.rmtree(pdir, ignore_errors=True)  # (deleted part way)

    def plan(self, path, info, box, slow):
        """How a video's made a part at a time: {"size", "mtime" (the video's, as it was), "box", "part" (seconds a
        part), "how", "n" (how many)}; None to make it in one go: a fast Pi, a short video or one whose length
        isn't known, or one its parts didn't work for."""
        if not slow or info["duration"] <= PART_SECS * 1.5 or info.get("vindex") is None:
            return None
        if (self.seen.get(path) or [0, 0, ""])[2] == "whole":
            return None
        try:
            st = os.stat(path)
        except OSError:
            return None
        return {"size": st.st_size, "mtime": int(st.st_mtime), "box": list(box), "part": PART_SECS, "how": PARTS_HOW,
                "n": max(1, math.ceil((info["duration"] - 1.0) / PART_SECS))}

    def convert_parts(self, path, work, info, box, slow, plan):
        """A long video's picture made smaller a part at a time, each kept as it's done (any made already, by a Pi
        that went off part way, kept to), then put together with its sound and subtitles into work. True once
        that's made."""
        pdir = parts_dir(path)
        if read_plan(pdir) != plan:                     # (none yet, or from another video by that name)
            shutil.rmtree(pdir, ignore_errors=True)
            try:
                os.makedirs(pdir)
                st = os.stat(path)
                os.chown(pdir, st.st_uid, st.st_gid)    # (yours to delete, like the video)
                with open(os.path.join(pdir, "plan.json"), "w") as f:
                    json.dump(plan, f)
            except OSError as ex:
                print(f"videos: couldn't keep parts ({ex})", flush=True)
                return False
        dur, n, made = info["duration"], plan["n"], []
        for k in range(n):
            part = os.path.join(pdir, f"part-{k:04d}.nut")
            if not os.path.exists(part):
                tmp = os.path.join(pdir, f".part-{k:04d}.nut")
                start = k * PART_SECS
                end = start + PART_SECS if k < n - 1 else None
                self.pct = max(0, min(99, int(start / dur * 100)))
                ok = self.run_ffmpeg(part_command(path, tmp, info, box, slow, start, end), dur, before=start)
                if not ok or not os.path.exists(tmp):
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    return False
                if self.frames == 0:                    # (the picture ended before the sound did: that's all)
                    os.remove(tmp)
                    break
                os.replace(tmp, part)
            made.append(part)
        if not made:
            return False
        firsts = [first_time(p) for p in made]          # (each part's first frame: where the next one starts)
        listing = os.path.join(pdir, "parts.ffconcat")
        with open(listing, "w") as f:
            f.write("ffconcat version 1.0\n")
            for k, part in enumerate(made):
                f.write(f"file '{os.path.basename(part)}'\n")
                if k + 1 < len(made):
                    f.write(f"duration {firsts[k + 1] - firsts[k]:.6f}\n")
        self.pct = 99
        offset = max(0.0, firsts[0] - (info.get("start") or 0.0))
        ok = False
        for subs in (True, False):                     # (subtitles it can't keep: again without them)
            ok = self.run_ffmpeg(join_command(listing, path, work, info, offset, subs=subs), None)
            if ok or self.quit or not self.enabled() or not os.path.exists(path):
                break
        return ok

    def run_ffmpeg(self, cmd, duration, before=0.0):
        """ffmpeg, at the lowest priority, saying how far it's got (of duration, from before: a part of it). True if
        it finished as it should."""
        cmd = ["nice", "-n", "19"] + (["ionice", "-c", "3"] if shutil.which("ionice") else []) + cmd
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                         start_new_session=True)
        except OSError as ex:
            print(f"videos: ffmpeg didn't start ({ex})", flush=True)
            return False
        self.stopped = False
        self.frames = None
        if self.held:
            self.hold(True)
        for line in self.proc.stdout:
            k, _, v = line.strip().partition("=")
            if k in ("out_time_us", "out_time_ms") and duration:
                try:
                    self.pct = max(0, min(99, int((before + int(v) / 1e6) / duration * 100)))
                except ValueError:
                    pass
            elif k == "frame" and v.isdigit():
                self.frames = int(v)
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
