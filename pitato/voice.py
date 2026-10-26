"""The bot's voice: Piper, a neural voice that runs on the Pi."""
import glob
import hashlib
import json
import os
import platform
import re
import select
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import wave

from .config import home_dir
from .util import UA


# ---- the bot's voice: Piper, a neural voice that runs on the Pi --------------------------------------
PIPER_DIR = "/usr/local/share/pitato/piper"     # Piper itself, from its own release (checked below)
VOICES_DIR = "/usr/local/share/pitato/voices"   # the voices you've picked
PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_{}.tar.gz"
PIPER_SHA256 = {"aarch64": "fea0fd2d87c54dbc7078d0f878289f404bd4d6eea6e7444a77835d1537ab88eb",
                "armv7l": "c6946fcd57c705ed1d4666ea880f80ba0bbbd14de62ecbdd13460baf3bac8e37",
                "x86_64": "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"}
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{}/{}"
BOT_VOICES = [                                     # (its name in Piper's library, what we call it, what it's like)
    ("en_US-amy-low", "Amy, quick", "American, best on a Pi Zero"),
    ("en_GB-alan-low", "Alan, quick", "British"),
    ("en_US-amy-medium", "Amy", "American, warm"),
    ("en_US-lessac-medium", "Lessac", "American, clear"),
    ("en_US-ryan-medium", "Ryan", "American, male"),
    ("en_GB-alan-medium", "Alan", "British, male"),
    ("en_GB-jenny_dioco-medium", "Jenny", "British, female"),
    ("en_GB-northern_english_male-medium", "Northern English", "British, male"),
]
VOICE_MB = 63            # each of those is about this big
VOICE_IDLE = 120         # seconds quiet before Piper is let go (it holds about 100 MB while it waits)
VOICE_WAIT = 90          # a voice on a small Pi can take this long to load and make its first sentence
VOICE_SAMPLE = "Hello! This is how I sound."
VOICE_SINCE = time.time()  # (leftovers older than this, under this process's number, are from before)


def piper_arch():
    """Which of Piper's builds runs here. The system decides, not the kernel: a Pi with a 64-bit
    kernel and a 32-bit system needs the 32-bit one. None on armv6 (a Pi 1, Zero or Zero W)."""
    m = platform.machine().lower()
    bits64 = sys.maxsize > 2 ** 32
    if m in ("x86_64", "amd64"):
        return "x86_64" if bits64 else None
    if m in ("aarch64", "arm64"):
        return "aarch64" if bits64 else "armv7l"
    if m.startswith("armv7") or m == "armv8l":
        return "armv7l"
    return None


def piper_bin():
    return os.path.join(PIPER_DIR, "piper")


def voice_user():
    """Who Piper runs as: the home folder's owner rather than root (what it reads comes from a
    voice file, and from words anyone could get the bot to say). aplay, only given samples, stays
    root like mplayer, so it plays where mplayer plays.
    (uid, gid, groups, home); uid None when this isn't running as root to begin with."""
    home = home_dir()
    try:
        st = os.stat(home)
    except OSError:
        return None, None, [], home
    if os.geteuid() != 0 or st.st_uid == 0:
        return None, None, [], home
    groups = []
    try:
        import grp
        groups = [grp.getgrnam("audio").gr_gid]
    except (ImportError, KeyError):
        pass
    return st.st_uid, st.st_gid, groups, home


def as_user():
    """Popen's arguments for running something as voice_user()."""
    uid, gid, groups, home = voice_user()
    if uid is None:
        return {}
    return {"user": uid, "group": gid, "extra_groups": groups,
            "env": dict(os.environ, HOME="/nonexistent", XDG_CONFIG_HOME="/nonexistent")}


def shared_dir(path):
    """A folder root writes and everyone can read (Piper runs as you)."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o755)


def voice_files(vid):
    model = os.path.join(VOICES_DIR, vid + ".onnx")
    return model, model + ".json"


def voice_name(vid):
    return next((n for i, n, _ in BOT_VOICES if i == vid), vid)


def voice_folder(vid):
    """Where a voice is in Piper's library: en_US-amy-low is en/en_US/amy/low."""
    parts = vid.split("-")
    return f"{parts[0].split('_')[0]}/{parts[0]}/{'-'.join(parts[1:-1])}/{parts[-1]}"


def voices_here():
    """The voices on the Pi (each with its settings file)."""
    try:
        names = set(os.listdir(VOICES_DIR))
    except OSError:
        return set()
    return {f[:-5] for f in names if f.endswith(".onnx") and f + ".json" in names}


def speech_text(text):
    """What it said, made for saying: degrees as a word, and nothing a voice would spell out."""
    t = re.sub(r"\s*°\s*[FC]\b", " degrees", text or "").replace("°", " degrees")
    t = "".join(" " if ord(c) >= 0x1F000 or 0x2600 <= ord(c) < 0x2800 or c in "‍️*_#~`|<>"
                else c for c in t if c.isprintable() or c.isspace())
    return " ".join(t.split())


def speech_sentences(text):
    """A reply a sentence at a time, so the first can be said while the next is made ("Hi." goes
    with what comes after it)."""
    out = []
    for p in (p.strip() for p in re.split(r"(?<=[.!?…])\s+", text)):
        if not p:
            continue
        if out and len(out[-1]) < 12:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def read_speech(path, volume=100):
    """One of Piper's WAVs as 16-bit mono samples at the media volume, and its rate. Only a plain
    file of a sensible size, not followed through a link (Piper runs as you; this is root)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with open(fd, "rb") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 30_000_000:
            raise ValueError("not a WAV of Piper's")
        with wave.open(f, "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError("not a WAV of Piper's")
            rate, pcm = w.getframerate(), w.readframes(w.getnframes())
    if volume < 100:
        import numpy
        quieter = numpy.frombuffer(pcm, dtype="<i2").astype(numpy.float32) * (max(0, volume) / 100.0)
        pcm = quieter.astype("<i2").tobytes()
    return pcm, rate


class Voice:
    """The bot's voice: Piper, a neural voice that runs on the Pi, and aplay.

    Piper is given a reply a sentence at a time. It writes each one as a WAV (into memory) and says
    so when it's done, while the sentence before plays: speaking starts after one sentence rather
    than the whole reply. Piper stays loaded while it's in use (a voice takes seconds to load on a
    Pi Zero) and is let go after a couple of quiet minutes. Piper and the voices come from their own
    releases the first time a voice is picked; Piper is checked against its known SHA-256."""

    def __init__(self):
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.pending = None          # (gen, text or None to just load, voice, aplay's device, volume)
        self.gen = 0                 # goes up to cut off what's being said
        self.proc = None             # Piper, with self.loaded's voice
        self.loaded = ""
        self.out = ""                # where Piper's WAVs land
        self.err = None              # what Piper says when it won't start
        self.buf = b""               # what Piper has written so far on its way to a whole line
        self.inflight = 0            # sentences given to Piper that haven't come back
        self.play = None             # aplay, while something is being said
        self.speaking = False
        self.error = ""              # why the last thing wasn't said, or a voice didn't arrive
        self.used = 0.0              # when it last said something (time.monotonic())
        self.let_go = False
        self.job = None              # a download: {"id", "what", "pct"}
        self.on_change = lambda: None
        self.on_ready = lambda vid: None
        threading.Thread(target=self.run, daemon=True, name="voice").start()

    @staticmethod
    def tidy():
        """What a Pie-tato stopped part way left behind (each is named after the process it was
        for): half-fetched voices, Piper half unpacked, WAVs in memory."""
        for pattern in (os.path.join(VOICES_DIR, "*.part"), os.path.join(os.path.dirname(PIPER_DIR), ".piper-*"),
                        "/dev/shm/pitato-voice-*"):
            for path in glob.glob(pattern):
                pid = re.search(r"[.-](\d+)[.-]", os.path.basename(path))
                try:
                    mine_now = int(pid.group(1)) != os.getpid() or os.path.getmtime(path) >= VOICE_SINCE
                except (AttributeError, OSError):
                    mine_now = False
                if pid and os.path.exists(f"/proc/{pid.group(1)}") and mine_now:
                    continue                          # (still at it)
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def changed(self):
        try:
            self.on_change()
        except Exception as ex:                       # (its own threads carry on, whatever happens)
            print(f"voice: {ex!r}", flush=True)

    # what's here
    @staticmethod
    def supported():
        return piper_arch() is not None

    @staticmethod
    def have_piper():
        return os.access(piper_bin(), os.X_OK)

    def status(self):
        job = self.job
        if job:
            return f"Getting {job['what']}… {job['pct']}%"
        return self.error

    # saying things
    def say(self, text, vid, device="", volume=100):
        """Say something, cutting off whatever is being said. (True, "") or (False, why not)."""
        text = speech_text(text)
        if not text:
            return False, "There's nothing to say"
        if not vid or vid not in voices_here():
            return False, "Pick a voice in Settings > Bot"
        if not self.have_piper():
            return False, "Piper isn't on the Pi: pick the voice again"
        if not shutil.which("aplay"):
            return False, "aplay is missing: run setup.sh again"
        with self.lock:
            self.gen += 1
            self.pending = (self.gen, text, vid, device, volume)
            self.speaking = True
            self.error = ""
        self.kill_play()
        self.wake.set()
        self.changed()
        return True, ""

    def warm(self, vid):
        """The voice loaded ahead of the first reply (the bot's page just opened)."""
        if vid in voices_here() and self.have_piper():
            with self.lock:
                if self.pending is None and not self.speaking:
                    self.pending = (self.gen, None, vid, "", 100)
            self.wake.set()

    def stop(self, unload=False):
        """Quiet, now (and Piper let go too, when unload)."""
        with self.lock:
            self.gen += 1
            self.pending = None
            self.speaking = False
            self.let_go = self.let_go or unload
        self.kill_play()
        self.wake.set()
        self.changed()

    def kill_play(self):
        play = self.play
        if play is not None and play.poll() is None:
            try:
                play.kill()
            except OSError:
                pass

    def run(self):
        """The one thread that speaks: each new thing to say cuts off the last."""
        self.tidy()
        while True:
            self.wake.wait(5)
            with self.lock:
                job, self.pending = self.pending, None
                self.wake.clear()
                let_go, self.let_go = self.let_go, False
            if let_go:
                self.unload()
            if job is None:
                if self.proc and time.monotonic() - self.used > VOICE_IDLE:
                    self.unload()
                continue
            gen, text, vid, device, volume = job
            try:
                if text is None:
                    self.load(vid)
                else:
                    self.speak(gen, text, vid, device, volume)
            except Exception as ex:                   # (it must keep going, whatever happens)
                self.error = f"Couldn't say it ({ex})"[:90]
                self.kill_play()
                self.unload()
            finally:
                self.used = time.monotonic()
                with self.lock:
                    if self.pending is None:
                        self.speaking = False
                self.changed()

    def load(self, vid):
        """Piper with this voice (started afresh for another voice, or when it has stopped)."""
        if self.proc and self.proc.poll() is None and self.loaded == vid:
            return True
        self.unload()
        model, conf = voice_files(vid)
        self.out = tempfile.mkdtemp(prefix=f"pitato-voice-{os.getpid()}-",
                                    dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
        user = as_user()
        if user:
            os.chown(self.out, user["user"], user["group"])
        self.err = tempfile.TemporaryFile()
        try:
            self.proc = subprocess.Popen(["nice", "-n", "5", piper_bin(), "-q", "-m", model, "-c", conf, "-d", self.out],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err,
                                         cwd=PIPER_DIR, **user)
        except OSError as ex:
            self.proc = None
            self.error = f"Piper wouldn't start ({ex.strerror or ex})"
            shutil.rmtree(self.out, ignore_errors=True)
            self.out = ""
            return False
        self.loaded, self.buf, self.inflight = vid, b"", 0
        return True

    def unload(self):
        proc, self.proc, self.loaded = self.proc, None, ""
        if proc is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.kill()
                proc.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self.out:
            shutil.rmtree(self.out, ignore_errors=True)
            self.out = ""
        self.buf, self.inflight = b"", 0

    def piper_said(self):
        """The last thing Piper said before it stopped."""
        try:
            self.err.seek(0)
            lines = [ln.strip() for ln in self.err.read().decode(errors="ignore").splitlines() if ln.strip()]
        except (OSError, ValueError, AttributeError):
            lines = []
        return lines[-1][:80] if lines else ""

    def feed(self, sentence):
        """A sentence to Piper. False when Piper has stopped (what it already made still plays)."""
        try:
            self.proc.stdin.write(sentence.encode() + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError, AttributeError):
            said = self.piper_said()
            self.error = "Piper stopped" + (f" ({said})" if said else "")
            self.unload()
            return False
        self.inflight += 1
        return True

    def next_wav(self, gen, until):
        """The next WAV Piper has made: its path, or None when it's cut off, out of time, or Piper
        has stopped."""
        if self.proc is None:
            return None
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            if gen != self.gen:
                return None
            if time.monotonic() > until:
                self.error = "Piper took too long"
                self.unload()
                return None
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                chunk = os.read(fd, 4096)
                if not chunk:
                    self.error = "Piper stopped" + (f" ({self.piper_said()})" if self.piper_said() else "")
                    self.unload()
                    return None
                self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        self.inflight -= 1
        path = os.path.realpath(line.decode(errors="ignore").strip())
        return path if os.path.dirname(path) == os.path.realpath(self.out) else ""

    def drain(self):
        """Sentences of a reply that was cut off, still with Piper: they're let come and thrown
        away (Piper is started afresh if they'd hold up the next reply too long)."""
        until = time.monotonic() + 8
        while self.inflight > 0 and self.proc is not None:
            path = self.next_wav(self.gen, until)
            if path is None:
                break
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        if self.inflight > 0:
            self.unload()

    def speak(self, gen, text, vid, device, volume):
        if not self.load(vid):
            return
        self.drain()
        if gen != self.gen or not self.load(vid):
            return
        todo = speech_sentences(text)
        if not todo or not self.feed(todo.pop(0)):
            return
        play, until = None, time.monotonic() + VOICE_WAIT
        try:
            while gen == self.gen:
                path = self.next_wav(gen, until)
                if path is None:
                    break
                pcm = None
                if path:
                    try:
                        pcm, rate = read_speech(path, volume)
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                if todo and not self.feed(todo.pop(0)):   # the next one is made while this one plays
                    todo = []
                until = time.monotonic() + VOICE_WAIT
                if pcm is None:
                    continue
                if play is None:
                    play = self.start_play(rate, device)
                    if play is None:
                        break
                if not self.write(play, pcm, gen):
                    break
                if not todo and self.inflight == 0:
                    break
            if play is not None and gen == self.gen:
                self.finish(play, gen)
        finally:
            if play is not None:
                if play.poll() is None:
                    try:
                        play.kill()
                    except OSError:
                        pass
                for f in (play.stdin, play.said):
                    try:
                        f.close()
                    except (OSError, ValueError):
                        pass

    def start_play(self, rate, device):
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(rate)]
        if device:
            cmd += ["-D", device]
        err = tempfile.TemporaryFile()
        try:
            play = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err)
        except OSError as ex:
            err.close()
            self.error = f"aplay wouldn't start ({ex.strerror or ex})"
            return None
        play.said = err
        self.play = play
        return play

    def aplay_said(self, play):
        try:
            play.said.seek(0)
            lines = [ln.strip() for ln in play.said.read().decode(errors="ignore").splitlines() if ln.strip()]
        except (OSError, ValueError):
            lines = []
        return re.sub(r"^aplay: \w+:\d+: ", "", lines[-1])[:80] if lines else ""

    def write(self, play, pcm, gen):
        """Samples to aplay, a little at a time so being cut off is quick. False when it can't go on."""
        for i in range(0, len(pcm), 8192):
            if gen != self.gen:
                return False
            try:
                play.stdin.write(pcm[i:i + 8192])
            except (BrokenPipeError, OSError, ValueError):
                if gen == self.gen:
                    play.wait()
                    self.error = "Couldn't play it" + (f": {self.aplay_said(play)}" if self.aplay_said(play) else "")
                return False
        return True

    def finish(self, play, gen):
        """The rest played out (unless it's cut off)."""
        try:
            play.stdin.close()
        except OSError:
            pass
        while play.poll() is None:
            if gen != self.gen:
                return
            time.sleep(0.05)
        if play.returncode not in (0, None) and gen == self.gen:
            self.error = "Couldn't play it" + (f": {self.aplay_said(play)}" if self.aplay_said(play) else "")

    # getting Piper and the voices
    def get(self, vid):
        """Piper (the first time) and a voice onto the Pi, in the background; on_ready(vid) once
        it's here. False while another is on its way."""
        if self.job:
            return False
        self.error = ""
        self.job = {"id": vid, "what": "Piper" if not self.have_piper() else voice_name(vid), "pct": 0}
        threading.Thread(target=self.get_job, args=(vid,), daemon=True, name="voice-get").start()
        self.changed()
        return True

    def get_job(self, vid):
        name = voice_name(vid)
        try:
            if not self.have_piper():
                self.get_piper()
            self.job = {"id": vid, "what": name, "pct": 0}
            self.changed()
            self.get_voice(vid)
            self.job = None
            self.on_ready(vid)
        except Exception as ex:
            why = getattr(ex, "reason", None) or ex
            self.error = f"Couldn't get {name} ({why})"[:90]
            self.job = None
        self.changed()

    def fetch(self, url, dest, limit, room=0):
        """A download into dest (with `room` bytes more to spare), how far along it is in self.job;
        its SHA-256."""
        h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r, \
                open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            if total > limit:
                raise ValueError("it's bigger than it should be")
            if total and shutil.disk_usage(os.path.dirname(dest)).free < total + room + 50_000_000:
                raise ValueError("there isn't room for it on the Pi")
            got = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                got += len(chunk)
                if got > limit:
                    raise ValueError("it's bigger than it should be")
                f.write(chunk)
                h.update(chunk)
                job = self.job
                if total and job and min(99, got * 100 // total) != job["pct"]:
                    job["pct"] = min(99, got * 100 // total)
                    self.changed()
            if total and got != total:
                raise ValueError("the download was cut short")
        return h.hexdigest()

    def get_piper(self):
        arch = piper_arch()
        if not arch:
            raise ValueError("Piper doesn't run on this Pi")
        parent = os.path.dirname(PIPER_DIR)
        shared_dir(parent)
        tmp = tempfile.mkdtemp(prefix=f".piper-{os.getpid()}-", dir=parent)
        try:
            tar = os.path.join(tmp, "piper.tar.gz")
            if self.fetch(PIPER_URL.format(arch), tar, 80_000_000, room=80_000_000) != PIPER_SHA256[arch]:
                raise ValueError("the download didn't check out")
            with tarfile.open(tar) as t:
                for m in t.getmembers():
                    parts = m.name.split("/")
                    if parts[0] != "piper" or ".." in parts or not (m.isfile() or m.isdir() or m.issym()) or \
                            (m.issym() and (m.linkname.startswith("/") or ".." in m.linkname.split("/"))):
                        raise ValueError("the download didn't check out")
                t.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
            shutil.rmtree(PIPER_DIR, ignore_errors=True)
            os.chmod(os.path.join(tmp, "piper"), 0o755)
            os.replace(os.path.join(tmp, "piper"), PIPER_DIR)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if not self.have_piper():
            raise ValueError("Piper didn't unpack")

    def get_voice(self, vid):
        shared_dir(os.path.dirname(VOICES_DIR))
        shared_dir(VOICES_DIR)
        model, conf = voice_files(vid)
        parts = (f"{model}.{os.getpid()}.part", f"{conf}.{os.getpid()}.part")
        try:
            self.fetch(VOICE_URL.format(voice_folder(vid), vid + ".onnx.json"), parts[1], 1_000_000)
            with open(parts[1]) as f:
                if not (json.load(f).get("audio") or {}).get("sample_rate"):
                    raise ValueError("that isn't a voice")
            self.fetch(VOICE_URL.format(voice_folder(vid), vid + ".onnx"), parts[0], 200_000_000)
            for part in parts:
                os.chmod(part, 0o644)
            os.replace(parts[0], model)
            os.replace(parts[1], conf)
        finally:
            for p in parts:
                try:
                    os.remove(p)
                except OSError:
                    pass

    def remove(self, vid):
        """A voice off the Pi (Piper let go first, if it's the one loaded)."""
        if self.loaded == vid:
            self.stop(unload=True)
        for p in voice_files(vid):
            try:
                os.remove(p)
            except OSError:
                pass
        self.changed()
