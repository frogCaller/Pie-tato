"""The bot listening: a USB microphone, and Vosk, which makes out what's said on the Pi itself.

It listens by itself while a microphone's plugged in, once the bot's set up (Settings > Bot > Listens: Auto, as it
comes; On listens with any there is, a webcam's or a PC's own too; Off). It waits for the wake phrase ("hey potato",
or yours), and what you say after it goes to the bot, which answers out loud when it has a voice; "Talk to it" on the
Bot page skips the phrase. It's deaf while the bot speaks, something plays or a game runs (it would hear that
instead). What it hears goes nowhere but to your bot. hear.py does the listening, as you rather than as root (as
Piper does: its model comes from the internet). Vosk (its library, from its release on PyPI, checked against its known
SHA-256) and its small English model come from their own releases the first time it listens."""
import glob
import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

from .system import read_file
from .util import UA
from .voice import as_user, piper_arch, shared_dir

LISTEN_DIR = "/usr/local/share/pitato/listen"     # Vosk's library and its model
VOSK_WHEELS = {          # Vosk 0.3.45's library, in its wheels on PyPI (only the library's used, by hear.py)
    "aarch64": ("https://files.pythonhosted.org/packages/a4/23/3130a69fa0bf4f5566a52e415c18cd854bf561547bb6505666a6eb1"
                "bb625/vosk-0.3.45-py3-none-manylinux2014_aarch64.whl",
                "54efb47dd890e544e9e20f0316413acec7f8680d04ec095c6140ab4e70262704"),
    "armv7l": ("https://files.pythonhosted.org/packages/32/6d/728d89a4fe8d0573193eb84761b6a55e25690bac91e5bbf30308c7f8"
               "0051/vosk-0.3.45-py3-none-linux_armv7l.whl",
               "4221f83287eefe5abbe54fc6f1da5774e9e3ffcbbdca1705a466b341093b072e"),
    "x86_64": ("https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9"
               "ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
               "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f"),
}
VOSK_LIB_MAX = 60_000_000         # bytes: the library in the wheel is 7 to 26 MB
MODEL = "vosk-model-small-en-us-0.15"           # small, English: made for a Pi
MODEL_URL = "https://alphacephei.com/vosk/models/" + MODEL + ".zip"
MODEL_MAX = 100_000_000           # bytes: it's about 40 MB
MODEL_UNPACKED_MAX = 250_000_000  # ...and about 70 MB unpacked
LISTEN_MB = 45                    # what it fetches, all told
WAKE = "hey potato"
WAKE_MOST = 40                    # characters of a wake phrase
LISTENS = ("auto", "on", "off")   # Settings > Bot > Listens: while a microphone's plugged in (as it comes), always, never
PATIENCE = 8.0                    # seconds after the wake phrase it waits for what you say
QUIET_AFTER = 0.7                 # seconds it stays deaf after the bot stops speaking (its voice, still in the room)
RETRY = 5.0                       # seconds between tries when there's no microphone, or it stopped
QUICK_STOP = 30.0                 # ...stopped this soon after it started (another program has the microphone, say):
RETRY_MOST = 300.0                # twice as long each time, up to this (its model takes a Pi Zero a while to load)
MIC_LOOK = 2.0                    # seconds between looks for a microphone plugged in or taken out (Listens: Auto)
LISTEN_AGAIN = 120.0              # seconds before Vosk's fetched again when it couldn't be (no internet yet, at start-up)
LISTEN_TRIES = 3                  # ...that many times, by itself
FILLER = {"the", "a", "an", "uh", "um", "huh", "hmm", "mm", "oh", "ah", "i", "and", "but", "so", "yeah", "hey", "it"}
GREETINGS = {"hey", "hi", "hay", "hello", "ok", "okay", "yo"}   # (heard for one another)
LOOSE = 4                         # letters: at the start of what's said, a word this short goes for a greeting
HEAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hear.py")
ASOUND = "/proc/asound"           # the kernel's sound cards
V4L = "/sys/class/video4linux"    # ...and its cameras (a webcam's own microphone comes after a microphone)
LISTEN_SINCE = time.time()        # (leftovers older than this, under this process's number, are from before)
WEB_MIC = "pietato-web"           # the microphone of a web page with Mic here on (what it hears comes in through the
WEB_MIC_DEVICE = "plughw:CARD=Loopback,DEV=1,SUBDEV=1"   # Loopback card: webui.py plays it into its other side)


def vosk_lib():
    return os.path.join(LISTEN_DIR, "libvosk.so")


def model_dir():
    return os.path.join(LISTEN_DIR, MODEL)


def model_here():
    return all(os.path.isfile(os.path.join(model_dir(), p)) for p in ("am/final.mdl", "conf/model.conf"))


def have_vosk():
    """Vosk and its model are on the Pi."""
    return os.path.isfile(vosk_lib()) and model_here()


def supported():
    return piper_arch() in VOSK_WHEELS


def camera_usb_ids():
    """The USB cameras' makers' numbers (046d:082d...): a sound card with the same is a webcam's microphone."""
    out = set()
    for node in glob.glob(os.path.join(V4L, "video*")):
        usb = os.path.dirname(os.path.realpath(os.path.join(node, "device")))
        vendor, product = read_file(os.path.join(usb, "idVendor")), read_file(os.path.join(usb, "idProduct"))
        if vendor and product:
            out.add(f"{vendor}:{product}".lower())
    return out


def mics():
    """The microphones: [{"id", "name", "device", "camera", "plays", "usb"}], sound cards that record. One that's only
    a microphone comes first, then one that plays too (a headset; a GPi Case 2's own sound; a PC's own sound card, after
    a USB one), then a webcam's."""
    cams = None
    out = []
    for line in read_file(os.path.join(ASOUND, "cards")).splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]:\s*(\S+)\s+-\s+(.+)", line)
        if not m:
            continue
        num, cid, full = m.group(1), m.group(2), m.group(4).strip()
        if cid == "Loopback" or m.group(3) == "Loopback":
            continue                                  # (the web page's way in: Mic here, not a microphone of the Pi's)
        caps = sorted(glob.glob(os.path.join(ASOUND, f"card{num}", "pcm*c")))
        if not caps:
            continue
        dev = re.search(r"pcm(\d+)c$", caps[0])
        if cams is None:
            cams = camera_usb_ids()
        usb = read_file(os.path.join(ASOUND, f"card{num}", "usbid")).lower()
        out.append({"id": cid, "name": " ".join(full.split())[:32], "camera": bool(usb) and usb in cams,
                    "plays": bool(glob.glob(os.path.join(ASOUND, f"card{num}", "pcm*p"))), "usb": bool(usb),
                    "device": f"plughw:CARD={cid},DEV={dev.group(1) if dev else 0}"})
    return sorted(out, key=lambda c: (c["camera"], c["plays"], not c["usb"]))


def mic_device(choice="", fallback=True):
    """arecord's -D for the microphone you picked (its card's id), or the first there is (while the one you picked
    isn't plugged in, too, with fallback). "" for none. WEB_MIC: a web page's, with Mic here on."""
    if choice == WEB_MIC:
        return WEB_MIC_DEVICE
    found = mics()
    hit = next((c for c in found if c["id"] == choice), None) if choice else None
    if fallback or not choice:
        hit = hit or (found[0] if found else None)
    return hit["device"] if hit else ""


def tokens(text):
    """What Vosk heard, a word at a time: [(its word to compare, as it was said)]."""
    out = []
    for raw in (text or "").split():
        word = re.sub(r"[^a-z0-9]", "", raw.lower())
        if word:
            out.append((word, raw))
    return out


def wake_words(phrase):
    return [w for w, _ in tokens(phrase)]


def wake_end(heard, wake):
    """Where the wake phrase ends in what was heard (its words), or None. "hey" and "hi" go for one another, and
    the last word may be heard with an s (potatoes). At the start of what's said, a greeting is often heard as
    another short word ("a potato", "they potato") or not at all ("potato"): that will do there."""
    def at(i, words):
        if not words or i + len(words) > len(heard):
            return None
        for k, w in enumerate(words):
            h = heard[i + k]
            if not (h == w or (w in GREETINGS and h in GREETINGS)
                    or (k == len(words) - 1 and h in (w + "s", w + "es"))):
                return None
        return i + len(words)
    for i in range(len(heard) - len(wake) + 1):
        end = at(i, wake)
        if end is not None:
            return end
    if len(wake) > 1 and wake[0] in GREETINGS and heard:
        end = at(0, wake[1:])
        if end is None and len(heard[0]) <= LOOSE:
            end = at(1, wake[1:])
        return end
    return None


def meaningful(text):
    """Something said, not just a noise as Vosk hears it ("the", "huh")."""
    return any(w not in FILLER for w, _ in tokens(text))


def tidy_phrase(text):
    """A wake phrase as typed, tidied: lower case words, or "" when it won't do."""
    words = re.sub(r"[^a-z' ]", " ", (text or "").lower()).split()
    phrase = " ".join(words)[:WAKE_MOST].strip()
    return phrase if sum(len(w.replace("'", "")) for w in words) >= 4 else ""


def stop_proc(proc):
    if proc is None:
        return
    try:
        proc.stdin.write(b"quit\n")
        proc.stdin.flush()
    except (OSError, ValueError, AttributeError):
        pass
    try:
        proc.wait(2)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            pass
    for f in (proc.stdin, proc.stdout):
        try:
            f.close()
        except (OSError, ValueError, AttributeError):
            pass


class Ears:
    """Listening (Settings > Bot > Listens): hear.py makes out what the microphone hears, a line at a time; the wake
    phrase, then what's said after it, goes to on_heard (from its thread). wake_now(): what's said next, without the
    phrase. Deaf while is_busy() (the bot speaking, something playing). It starts again by itself when it stops (a
    microphone unplugged and plugged in again), and waits for one when there's none."""

    def __init__(self):
        self.lock = threading.Lock()
        self.gen = 0                 # goes up when it's started afresh or stopped: its thread ends
        self.want = None             # (the wake phrase, a microphone's card or "") while it should listen
        self.fallback = True         # ...another microphone while that one isn't plugged in
        self.proc = None             # hear.py
        self.thread = None           # ...and the thread that reads it
        self.state = "off"           # off, starting, waiting (for the wake phrase), listening (after it), error
        self.error = ""              # why it isn't listening
        self.unknown = []            # words of the wake phrase its model doesn't know
        self.heard = ""              # what it's making out after the wake phrase, so far
        self.poked = False           # "Talk to it": what's said next, without the phrase
        self.busy_until = 0.0
        self.job = None              # Vosk on its way: {"what", "pct"}
        self.got_error = ""          # why it didn't arrive
        self.is_busy = lambda: False
        self.on_heard = lambda text: None
        self.on_change = lambda: None
        self.on_ready = lambda: None   # Vosk arrived (from its download's thread)

    def changed(self):
        try:
            self.on_change()
        except Exception as ex:                       # (its threads carry on, whatever happens)
            print(f"ears: {ex!r}", flush=True)

    def set(self, gen, state, error=None):
        if gen != self.gen:
            return
        if error is not None:
            self.error = error
        if state != self.state or error is not None:
            self.state = state
            if state != "listening":
                self.heard = ""
            self.changed()

    # on and off
    def start(self, wake, mic="", fallback=True):
        """Listening for the wake phrase, from the microphone picked (a card's id; "": the first there is; with
        fallback, the first there is while that one isn't plugged in). Started afresh when any of them changes."""
        want = (wake, mic)
        with self.lock:
            if self.want == want and self.fallback == fallback and self.thread is not None and self.thread.is_alive():
                return
            self.gen += 1
            gen, self.want, self.fallback = self.gen, want, fallback
            old, self.proc = self.proc, None
            self.state, self.error, self.heard, self.poked = "starting", "", "", False
            self.thread = threading.Thread(target=self.run, args=(gen, wake, mic, fallback), daemon=True, name="ears")
        stop_proc(old)
        self.changed()
        self.thread.start()

    def stop(self):
        with self.lock:
            was = self.want is not None
            self.gen += 1
            self.want = None
            old, self.proc = self.proc, None
            self.state, self.error, self.heard, self.poked = "off", "", "", False
        stop_proc(old)
        if was:
            self.changed()

    @property
    def on(self):
        return self.want is not None

    def wake_now(self):
        """What's said next goes to the bot, no wake phrase needed. False when it isn't listening."""
        if self.state not in ("waiting", "listening"):
            return False
        self.poked = True
        return True

    def busy_now(self):
        try:
            busy = bool(self.is_busy())
        except Exception:
            busy = False
        now = time.monotonic()
        if busy:
            self.busy_until = now + QUIET_AFTER
        return busy or now < self.busy_until

    # the listening, on its own thread
    def run(self, gen, wake, mic, fallback=True):
        words = wake_words(wake)
        quick = 0                                     # times in a row it stopped soon after it started
        while gen == self.gen:
            if not have_vosk():
                self.set(gen, "error", "Vosk isn't on the Pi: turn Listens off and on again")
                return
            device = mic_device(mic, fallback)
            if not device:
                self.set(gen, "error", "No microphone: plug one in")
                quick = 0                             # (taken out, not busy: once it's back, counted afresh)
                self.nap(gen, RETRY)
                continue
            err = tempfile.TemporaryFile()
            try:
                proc = subprocess.Popen(["nice", "-n", "5", sys.executable, "-I", HEAR, vosk_lib(), model_dir(), device]
                                        + words, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, cwd="/",
                                        **as_user())
            except OSError as ex:
                err.close()
                self.set(gen, "error", f"It couldn't start listening ({ex.strerror or ex})")
                self.nap(gen, RETRY * 6)
                continue
            with self.lock:
                if gen != self.gen:
                    stop_proc(proc)
                    return
                self.proc = proc
            started = time.monotonic()
            why = self.listen(gen, proc, words)
            stop_proc(proc)
            if not why:
                try:
                    err.seek(0)
                    lines = [ln.strip() for ln in err.read().decode(errors="replace").splitlines() if ln.strip()]
                except (OSError, ValueError):
                    lines = []
                why = "It stopped listening" + (f" ({lines[-1][:80]})" if lines else "")
            err.close()
            with self.lock:
                if self.proc is proc:
                    self.proc = None
            self.set(gen, "error", why)
            quick = quick + 1 if time.monotonic() - started < QUICK_STOP else 0
            self.nap(gen, min(RETRY * 2 ** quick, RETRY_MOST))

    def nap(self, gen, secs):
        end = time.monotonic() + secs
        while gen == self.gen and time.monotonic() < end:
            time.sleep(0.1)

    @staticmethod
    def tell(proc, what):
        try:
            proc.stdin.write(what.encode() + b"\n")
            proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def listen(self, gen, proc, wake):
        """hear.py's lines, till it stops (why: its error, or "" when it said none) or listening's turned off."""
        out = proc.stdout.fileno()
        buf, deaf, armed, why = b"", None, 0.0, ""
        while gen == self.gen:
            busy = self.busy_now()
            if busy != deaf:
                if not self.tell(proc, "deaf" if busy else "listen"):
                    break
                deaf = busy
                if armed:
                    armed = time.monotonic()          # (what you say next still goes to the bot)
            if self.poked and not deaf and self.state in ("waiting", "listening"):
                self.poked = False
                self.tell(proc, "reset")
                armed = time.monotonic()
                self.heard = ""
                self.set(gen, "listening")
            if armed and not deaf and time.monotonic() - armed > PATIENCE:
                armed = 0.0                           # (nothing followed the wake phrase)
                self.set(gen, "waiting")
            ready, _, _ = select.select([out], [], [], 0.1)
            if not ready:
                continue
            chunk = os.read(out, 65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "error" in msg:
                    why = str(msg["error"])[:120]
                elif msg.get("ready"):
                    self.unknown = [str(w)[:20] for w in msg.get("unknown") or []][:8]
                    self.set(gen, "listening" if armed else "waiting", "")
                elif "partial" in msg:
                    part = str(msg["partial"])[:300]
                    if armed:
                        if part:
                            armed = time.monotonic()  # (you're still talking: it waits)
                        if part != self.heard:
                            self.heard = part
                            self.changed()
                    elif wake_end([w for w, _ in tokens(part)], wake) is not None and self.state != "listening":
                        self.set(gen, "listening")   # (the phrase, it seems: the screen says so at once)
                elif "final" in msg:
                    armed = self.final(gen, str(msg["final"])[:600], wake, armed)
        return why

    def final(self, gen, text, wake, armed):
        """Something said, at its end: the wake phrase and what came after it (or, after the phrase, anything
        said) goes to the bot. When the wake phrase was heard (it's listening), from now on."""
        said = tokens(text)
        end = wake_end([w for w, _ in said], wake)
        if end is not None:
            rest = " ".join(r for _, r in said[end:])
            if meaningful(rest):
                self.deliver(gen, rest)
                return 0.0
            self.heard = ""
            self.set(gen, "listening")
            return time.monotonic()
        if armed:
            if meaningful(text):
                self.deliver(gen, text)
                return 0.0
            return armed
        if self.state == "listening":                 # (it seemed the phrase, as it was said, but wasn't)
            self.set(gen, "waiting")
        return 0.0

    def deliver(self, gen, text):
        if gen != self.gen:
            return
        self.heard = ""
        self.set(gen, "waiting")
        text = text[:1].upper() + text[1:]
        try:
            self.on_heard(text)
        except Exception as ex:
            print(f"ears: {ex!r}", flush=True)

    # getting Vosk and its model
    def status(self):
        job = self.job
        if job:
            return f"Getting {job['what']}… {job['pct']}%"
        return self.got_error

    def get(self):
        """Vosk and its model onto the Pi, in the background; on_ready() once they're here. False while they're on
        their way already, or Vosk doesn't run on this Pi."""
        if self.job or not supported():
            return False
        self.got_error = ""
        self.job = {"what": "Vosk", "pct": 0}
        threading.Thread(target=self.get_job, daemon=True, name="ears-get").start()
        self.changed()
        return True

    def get_job(self):
        what = "Vosk"
        try:
            self.tidy()
            shared_dir(os.path.dirname(LISTEN_DIR))
            shared_dir(LISTEN_DIR)
            if not os.path.isfile(vosk_lib()):
                self.get_vosk()
            what = "its model"
            self.job = {"what": what, "pct": 0}
            self.changed()
            if not model_here():
                self.get_model()
            self.job = None
            self.on_ready()
        except Exception as ex:
            why = getattr(ex, "reason", None) or ex
            self.got_error = f"Couldn't get {what} ({why})"[:90]
            self.job = None
        self.changed()

    @staticmethod
    def tidy():
        """What a Pietato stopped part way left behind: half-fetched files, a model half unpacked."""
        for path in glob.glob(os.path.join(LISTEN_DIR, ".*-*")):
            pid = re.search(r"-(\d+)[.-]", os.path.basename(path))
            try:
                mine_now = int(pid.group(1)) != os.getpid() or os.path.getmtime(path) >= LISTEN_SINCE
            except (AttributeError, OSError):
                mine_now = False
            if pid and os.path.exists(f"/proc/{pid.group(1)}") and mine_now:
                continue                              # (still at it)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def fetch(self, url, dest, limit, room=0):
        """A download into dest (with `room` bytes more to spare), how far along it is in self.job; its SHA-256."""
        h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r, open(dest, "wb") as f:
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

    def get_vosk(self):
        arch = piper_arch()
        if arch not in VOSK_WHEELS:
            raise ValueError("Vosk doesn't run on this Pi")
        url, sha = VOSK_WHEELS[arch]
        wheel = os.path.join(LISTEN_DIR, f".vosk-{os.getpid()}.whl")
        part = os.path.join(LISTEN_DIR, f".libvosk-{os.getpid()}.so")
        try:
            if self.fetch(url, wheel, 40_000_000, room=VOSK_LIB_MAX) != sha:
                raise ValueError("the download didn't check out")
            with zipfile.ZipFile(wheel) as z:
                info = z.getinfo("vosk/libvosk.so")
                if info.file_size > VOSK_LIB_MAX:
                    raise ValueError("the download didn't check out")
                with z.open(info) as src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            os.chmod(part, 0o644)
            os.replace(part, vosk_lib())
        finally:
            for p in (wheel, part):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def get_model(self):
        zpath = os.path.join(LISTEN_DIR, f".model-{os.getpid()}.zip")
        tmp = tempfile.mkdtemp(prefix=f".model-{os.getpid()}-", dir=LISTEN_DIR)
        try:
            self.fetch(MODEL_URL, zpath, MODEL_MAX, room=MODEL_UNPACKED_MAX)
            with zipfile.ZipFile(zpath) as z:
                infos = z.infolist()
                if sum(i.file_size for i in infos) > MODEL_UNPACKED_MAX:
                    raise ValueError("it's bigger than it should be")
                for i in infos:
                    parts = i.filename.split("/")
                    if parts[0] != MODEL or ".." in parts or "\\" in i.filename or \
                            (i.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("the download didn't check out")
                names = {i.filename for i in infos}
                if not all(f"{MODEL}/{p}" in names for p in ("am/final.mdl", "conf/model.conf")):
                    raise ValueError("that isn't a speech model")
                z.extractall(tmp)
            for root, dirs, files in os.walk(tmp):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o644)
            os.chmod(os.path.join(tmp, MODEL), 0o755)
            shutil.rmtree(model_dir(), ignore_errors=True)
            os.replace(os.path.join(tmp, MODEL), model_dir())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                os.remove(zpath)
            except OSError:
                pass

    def remove(self):
        """Vosk and its model off the Pi (listening stopped first)."""
        self.stop()
        shutil.rmtree(model_dir(), ignore_errors=True)
        try:
            os.remove(vosk_lib())
        except OSError:
            pass
        self.changed()
