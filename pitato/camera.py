#!/usr/bin/env python3
"""camera.py - this Pi's USB camera, shared on your network for Pitato's Camera tab.

It answers the same calls as PiE-ink's camera (/api/camera.jpg, /api/ptz/..., /api/photos),
so Pitato treats this Pi like a PiE-ink one: the live picture, pictures into ~/Pictures,
and steering and zoom for a camera that turns (an OBSBOT, a PTZ webcam). Following you, and
waking an OBSBOT that has fallen asleep, need PiE-ink.

Put it on the Pi with the camera (from the pitato folder):
    sudo bash setup.sh --camera
then add that Pi's address on Pitato's Camera tab (it also shows up there by itself, under
"On your network"). Opening http://<this Pi>:5433 in a browser shows the picture too.

Settings, all optional, in static/camera-server.txt (the static folder of the pitato folder:
setup.sh tells the service where that is; run by hand, it's the one beside the folder this script is in):
    name =             what Pitato calls it (this Pi's name if blank)
    size = 640x480     the live picture (the camera's biggest is used for pictures you take)
    fps = 15
    device =           /dev/video0 and so on (blank: the first USB camera)
    hosts =            other names you reach this Pi by, if your router gives it one
"""
import glob
import io
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 5433
BEACON_PORT, BEACON_EVERY = 5151, 5.0   # where PiE-inks announce themselves too
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = HERE if os.path.isdir(os.path.join(HERE, "static")) else os.path.dirname(HERE)   # (in the pitato folder:
STATIC = os.path.abspath(os.environ.get("PITATO_STATIC", "").strip()                  # one folder up)
                         or os.path.join(TOP, "static"))
CONF_FILE = os.path.join(STATIC, "camera-server.txt")
IDLE = 15.0               # nobody has asked for a picture this long: the camera is let go
FIRST_FRAME = 8.0         # a camera just started can take this long for its first picture
NOT_CAMERAS = ("bcm2835", "rpivid", "hevc", "-isp", "codec", "unicam", "pispbe", "rp1-cfe")
TICK, HEARTBEAT = 0.1, 0.7       # a held d-pad moves it every TICK; quiet for HEARTBEAT: it stops
ARCSEC = 3600.0                  # pan and tilt are in arc-seconds
LOWEST = -30.0                   # never further down than this (an OBSBOT pointed down falls asleep)
SPEED = 60.0                     # degrees a second while the d-pad is held
CONTROLS = {"pan": "pan_absolute", "tilt": "tilt_absolute", "zoom": "zoom_absolute"}
ID = uuid.uuid4().hex[:8]


def settings():
    conf = {}
    try:
        with open(CONF_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k.strip().lower()] = v.split("#", 1)[0].strip()
    except OSError:
        pass
    return conf


def run(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def node_caps(path):
    """The capabilities of this one node (not the whole camera's), from v4l2-ctl --info."""
    caps, inside = [], False
    for line in run(["v4l2-ctl", "-d", path, "--info"]).splitlines():
        if line.strip().startswith("Device Caps"):
            inside = True
        elif inside and line.startswith("\t\t"):
            caps.append(line.strip())
        elif inside:
            break
    return caps


def find_camera(want=""):
    """(device, its name): the node a USB camera sends pictures on. Each camera has a second
    node for metadata, and the Pi's own video blocks have some too; those are passed over."""
    if want:
        return want, card_name(want)
    nodes = sorted(glob.glob("/dev/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0))
    for path in nodes:
        card = card_name(path)
        if any(w in card.lower() for w in NOT_CAMERAS):
            continue
        caps = node_caps(path)
        if caps and "Video Capture" not in caps:
            continue
        if not caps and not os.path.exists(f"/sys/class/video4linux/{os.path.basename(path)}/device/driver"):
            continue
        return path, card
    return None, ""


def card_name(path):
    try:
        with open(f"/sys/class/video4linux/{os.path.basename(path)}/name") as f:
            return f.read().strip()
    except OSError:
        return ""


def mjpeg_sizes(path):
    """The sizes the camera sends as MJPEG, biggest first."""
    sizes, mjpeg = set(), False
    for line in run(["v4l2-ctl", "-d", path, "--list-formats-ext"]).splitlines():
        m = re.search(r"\[\d+\]:\s*'(\w+)'", line)
        if m:
            mjpeg = m.group(1) in ("MJPG", "JPEG")
            continue
        m = re.search(r"Size: Discrete (\d+)x(\d+)", line)
        if m and mjpeg:
            sizes.add((int(m.group(1)), int(m.group(2))))
    return sorted(sizes, key=lambda s: -s[0] * s[1])


def ffmpeg_cmd(dev, size=None, fps=None, mjpeg=True, frames=None):
    """ffmpeg reading the camera and writing JPEGs one after another, each with its length.
    A camera that sends MJPEG has its pictures passed on as they are (next to no work for the
    Pi); one that only sends raw pictures has them turned into JPEGs."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "v4l2"]
    if mjpeg:
        cmd += ["-input_format", "mjpeg"]
    if size:
        cmd += ["-video_size", f"{size[0]}x{size[1]}"]
    if fps:
        cmd += ["-framerate", str(fps)]
    cmd += ["-i", dev]
    if frames:
        cmd += ["-frames:v", str(frames)]
    cmd += ["-c:v", "copy"] if mjpeg else ["-c:v", "mjpeg", "-q:v", "5", "-pix_fmt", "yuvj420p"]
    return cmd + ["-f", "mpjpeg", "-"]


def read_parts(stream):
    """The JPEGs in ffmpeg's multipart output: each part says how long it is."""
    while True:
        line = stream.readline()
        if not line:
            return
        if not line.startswith(b"--"):
            continue
        length = None
        while True:
            head = stream.readline()
            if not head:
                return
            if head in (b"\r\n", b"\n"):
                break
            key, _, value = head.decode("latin-1").partition(":")
            if key.strip().lower() == "content-length":
                try:
                    length = int(value.strip())
                except ValueError:
                    length = None
        if not length or length > 20_000_000:
            continue
        data = stream.read(length)
        if len(data) < length:
            return
        yield data


def parse_size(text, default=(640, 480)):
    m = re.match(r"\s*(\d{2,5})\s*[x×*]\s*(\d{2,5})\s*$", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else default


# ---- the live picture -----------------------------------------------------------------------
class Feed:
    """ffmpeg runs while someone is watching; the newest picture is kept for whoever asks."""

    def __init__(self):
        self.cond = threading.Condition()
        self.starting = threading.Lock()   # one start or stop at a time: a new ffmpeg never meets the old
        self.jpeg, self.seq, self.at = None, 0, 0.0
        self.proc = None
        self.wanted = 0.0
        self.error = None
        self.held = 0               # a picture being taken has the camera to itself
        self.failed_at = -1e9       # when it last couldn't start: not tried again straight away
        self.dev, self.card = None, ""
        self.size, self.fps = (640, 480), 15
        self.mjpeg = True           # MJPEG, or raw pictures turned into JPEGs
        threading.Thread(target=self.idle_loop, daemon=True, name="idle").start()

    def configure(self):
        conf = settings()
        self.size = parse_size(conf.get("size"))
        try:
            self.fps = max(1, min(60, int(conf.get("fps") or 15)))
        except ValueError:
            self.fps = 15
        dev, card = find_camera(conf.get("device", ""))
        if dev != self.dev:
            self.dev, self.card, self.mjpeg = dev, card, True
        return self.dev

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def want(self):
        """Someone wants pictures: the camera is started if it isn't running."""
        self.wanted = time.monotonic()
        with self.cond:
            if self.held or self.running() or time.monotonic() - self.failed_at < 3:
                return
        with self.starting:
            with self.cond:
                if self.held or self.running() or time.monotonic() - self.failed_at < 3:
                    return                                   # (started meanwhile)
            if not self.configure():
                with self.cond:
                    self.error, self.failed_at = "No USB camera is plugged in", time.monotonic()
                return
            size = self.size
            if shutil_which("v4l2-ctl"):                     # it says what the camera sends
                sizes = mjpeg_sizes(self.dev)
                self.mjpeg = bool(sizes)                     # no MJPEG at all: raw it is
                if sizes and size not in sizes:              # the nearest size it has, not bigger
                    fits = [s for s in sizes if s[0] <= size[0] and s[1] <= size[1]]
                    size = fits[0] if fits else sizes[-1]
            try:
                proc = subprocess.Popen(ffmpeg_cmd(self.dev, size, self.fps, self.mjpeg),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as ex:
                with self.cond:
                    self.error, self.failed_at = f"Can't start ffmpeg ({ex.strerror or ex})", time.monotonic()
                return
            with self.cond:
                self.proc, self.error = proc, None
            said = []
            drain = threading.Thread(target=self.drain, args=(proc, said), daemon=True, name="feed-err")
            drain.start()
            threading.Thread(target=self.read, args=(proc, said, drain), daemon=True, name="feed").start()

    @staticmethod
    def drain(proc, said):
        """ffmpeg's messages, read as they come (so it never waits on them); the last few kept."""
        try:
            for line in proc.stderr:
                said.append(line)
                del said[:-4]
        except (OSError, ValueError):
            pass

    def read(self, proc, said, drain):
        got = 0
        for jpeg in read_parts(proc.stdout):
            got += 1
            with self.cond:
                self.jpeg, self.at = jpeg, time.monotonic()
                self.seq += 1
                self.cond.notify_all()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            pass
        drain.join(1)
        lines = b"".join(said).decode(errors="ignore").strip().splitlines()
        why = lines[-1][:120] if lines else "The camera sent no pictures"
        with self.cond:
            if self.proc is proc:
                self.proc = None
                if not got and not self.held:
                    if self.mjpeg and not shutil_which("v4l2-ctl") and "busy" not in why.lower():
                        self.mjpeg = False                   # it may send raw pictures only: those next
                    else:
                        self.error, self.failed_at = why, time.monotonic()
                        if not shutil_which("v4l2-ctl"):
                            self.mjpeg = True                # next time: MJPEG first again
            self.cond.notify_all()

    def stop(self):
        with self.starting:                                  # (the camera is free when this returns)
            with self.cond:
                proc, self.proc = self.proc, None
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(3)
                    except subprocess.TimeoutExpired:
                        pass

    def idle_loop(self):
        while True:
            time.sleep(2)
            if self.running() and time.monotonic() - self.wanted > IDLE:
                self.stop()

    def frame(self, newer_than=None, timeout=FIRST_FRAME):
        """The newest picture (bytes), waiting for one newer than `newer_than` if asked."""
        end = time.monotonic() + timeout
        while True:
            self.want()
            with self.cond:
                if not self.running() and not self.held and self.error and time.monotonic() - self.failed_at < 3:
                    return None, self.seq                    # it just failed to start: say so now
                fresh = self.jpeg is not None and time.monotonic() - self.at < 3
                if fresh and (newer_than is None or self.seq > newer_than):
                    return self.jpeg, self.seq
                left = end - time.monotonic()
                if left <= 0:
                    return (self.jpeg, self.seq) if self.jpeg is not None and newer_than is None and fresh else (None, self.seq)
                self.cond.wait(min(left, 0.5))


def shutil_which(name):
    from shutil import which
    return which(name)


# ---- turning it: the standard pan, tilt and zoom controls, through v4l2-ctl -------------------
class Ptz:
    def __init__(self, feed):
        self.feed = feed
        self.lock = threading.RLock()
        self.ctrls = {}             # "pan" / "tilt" / "zoom" -> {min, max, step, default}
        self.target = {}
        self.want_pos = {}
        self.vel, self.vel_at = (0.0, 0.0), 0.0
        self.speed = SPEED
        self.seqs = {}
        self.driver = None
        self.looked = -1e9
        self.dev = None
        self.error = None

    def find(self):
        """The camera's turning controls (looked for at most every ten seconds)."""
        dev = self.feed.dev or self.feed.configure()
        if self.ctrls and dev == self.dev:
            return True
        if time.monotonic() - self.looked < 10 and dev == self.dev:
            return False
        self.looked, self.dev, self.ctrls = time.monotonic(), dev, {}
        if not dev:
            return False
        for line in run(["v4l2-ctl", "-d", dev, "--list-ctrls"]).splitlines():
            name = line.strip().split(" ", 1)[0]
            key = next((k for k, c in CONTROLS.items() if c == name), None)
            if not key or "inactive" in line or "read-only" in line:
                continue
            vals = dict(re.findall(r"(\w+)=(-?\d+)", line))
            try:
                c = {k: int(vals[k]) for k in ("min", "max", "default", "value")}
            except KeyError:
                continue
            c["step"] = max(1, int(vals.get("step", 1)))
            if c["max"] > c["min"]:
                self.ctrls[key] = c
                self.target[key] = c["value"]
                self.want_pos[key] = float(c["value"])
        return bool(self.ctrls)

    def degrees(self, key):
        """True when the camera counts pan or tilt in arc-seconds, as it should."""
        c = self.ctrls[key]
        return c["max"] - c["min"] >= 2 * ARCSEC

    def bounds(self, key):
        c = self.ctrls[key]
        lo, hi = c["min"], c["max"]
        if key == "tilt" and self.degrees("tilt"):
            lo = max(lo, min(hi, int(LOWEST * ARCSEC)))
        return lo, hi

    def clamp(self, key, raw):
        c = self.ctrls[key]
        lo, hi = self.bounds(key)
        raw = max(lo, min(hi, raw))
        raw = c["min"] + round((raw - c["min"]) / c["step"]) * c["step"]
        return int(max(lo, min(hi, raw)))

    def write(self, values):
        pairs = ",".join(f"{CONTROLS[k]}={v}" for k, v in values.items() if k in self.ctrls)
        if not pairs:
            return
        out = subprocess.run(["v4l2-ctl", "-d", self.dev, "-c", pairs], capture_output=True, text=True, timeout=4)
        if out.returncode != 0:
            self.error = (out.stderr.strip().splitlines() or ["the camera didn't take it"])[-1][:120]
            raise ValueError(self.error)
        self.error = None
        self.target.update(values)

    def zoom_frac(self):
        c = self.ctrls.get("zoom")
        if not c:
            return 0.0
        return (self.target.get("zoom", c["min"]) - c["min"]) / float(c["max"] - c["min"])

    def position(self):
        p, t = self.ctrls.get("pan"), self.ctrls.get("tilt")
        deg = lambda k: round(self.target.get(k, 0) / (ARCSEC if self.degrees(k) else 1), 1)   # noqa: E731
        return {"pan": deg("pan") if p else 0.0, "tilt": deg("tilt") if t else 0.0,
                "zoom": round(self.zoom_frac(), 3), "has": {k: k in self.ctrls for k in CONTROLS}}

    def status(self):
        with self.lock:
            ok = self.find()
            return {"available": ok, "device": self.dev, "card": self.feed.card, "error": self.error,
                    "position": self.position() if ok else None, "speed": self.speed,
                    "moving": bool(self.driver and self.driver.is_alive()),
                    "follow": {"can": False, "on": False}, "sleep": {"can": False, "asleep": False}}

    def drive(self, vx, vy, sid="", seq=0, speed=None):
        """The d-pad: -1…1 each way (right and up positive), sent a few times a second while held."""
        with self.lock:
            if not self.find():
                raise ValueError("This camera doesn't turn")
            if sid:
                if seq <= self.seqs.get(sid, -1):
                    return self.position()           # overtaken by a newer message (a stop, say)
                self.remember(sid, seq)
            clip = lambda v: max(-1.0, min(1.0, float(v or 0)))   # noqa: E731
            self.vel, self.vel_at = (clip(vx), clip(vy)), time.monotonic()
            try:
                self.speed = max(5.0, min(180.0, float(speed))) if speed else SPEED
            except (TypeError, ValueError):
                self.speed = SPEED
            if any(self.vel) and not (self.driver and self.driver.is_alive()):
                for k in ("pan", "tilt"):
                    if k in self.ctrls:
                        self.want_pos[k] = float(self.target.get(k, 0))
                self.driver = threading.Thread(target=self.drive_loop, daemon=True, name="ptz")
                self.driver.start()
            return self.position()

    def remember(self, sid, seq):
        """The newest message from each of the last few remotes (a d-pad held on each)."""
        self.seqs.pop(sid, None)
        self.seqs[sid] = seq
        if len(self.seqs) > 50:
            self.seqs = dict(list(self.seqs.items())[-20:])

    def stop(self, sid="", seq=0):
        with self.lock:
            if sid:
                self.remember(sid, max(int(seq or 0), self.seqs.get(sid, -1)))
            self.vel = (0.0, 0.0)
            return self.position() if self.ctrls else {}

    def drive_loop(self):
        last = time.monotonic()
        while True:
            time.sleep(TICK)
            with self.lock:
                now = time.monotonic()
                vx, vy = self.vel
                if now - self.vel_at > HEARTBEAT:
                    vx = vy = 0.0                    # the d-pad went quiet: stop where it is
                if not vx and not vy:
                    self.driver = None
                    return
                dt, last = min(0.6, now - last), now
                speed = self.speed / (1 + 3 * self.zoom_frac())   # zoomed in, it turns gentler
                values = {}
                for k, v in (("pan", vx), ("tilt", vy)):
                    if not v or k not in self.ctrls:
                        continue
                    lo, hi = self.bounds(k)
                    unit = ARCSEC if self.degrees(k) else (hi - lo) / 180.0
                    want = self.want_pos.get(k, float(self.target.get(k, 0))) + v * speed * dt * unit
                    self.want_pos[k] = max(float(lo), min(float(hi), want))
                    raw = self.clamp(k, self.want_pos[k])
                    if raw != self.target.get(k):
                        values[k] = raw
                if values:
                    for k in ("pan", "tilt"):         # pan and tilt go together
                        if k in self.ctrls and k not in values:
                            values[k] = self.target.get(k, self.ctrls[k]["default"])
                    try:
                        self.write(values)
                    except (ValueError, OSError, subprocess.TimeoutExpired):
                        self.driver = None
                        return

    def set(self, pan=None, tilt=None, zoom=None):
        with self.lock:
            if not self.find():
                raise ValueError("This camera doesn't turn")
            self.vel = (0.0, 0.0)
            values = {}
            for k, v in (("pan", pan), ("tilt", tilt)):
                if v is not None and k in self.ctrls:
                    values[k] = self.clamp(k, float(v) * (ARCSEC if self.degrees(k) else 1))
            if zoom is not None and "zoom" in self.ctrls:
                c = self.ctrls["zoom"]
                values["zoom"] = self.clamp("zoom", c["min"] + max(0.0, min(1.0, float(zoom))) * (c["max"] - c["min"]))
            self.write(values)
            for k in values:
                self.want_pos[k] = float(self.target[k])
            return self.position()

    def home(self):
        return self.set(pan=0, tilt=0, zoom=0)


# ---- pictures you take: the camera's biggest size --------------------------------------------
class Shutter:
    def __init__(self, feed):
        self.feed = feed
        self.photos = OrderedDict()          # name -> JPEG, the last few
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            feed = self.feed
            dev = feed.dev or feed.configure()
            if not dev:
                raise ValueError("No USB camera is plugged in")
            data = None
            sizes = mjpeg_sizes(dev)
            if sizes:
                with feed.cond:
                    feed.held += 1
                try:
                    feed.stop()
                    try:
                        out = subprocess.run(ffmpeg_cmd(dev, sizes[0], None, True, frames=12),
                                             capture_output=True, timeout=20)
                        shots = list(read_parts(io.BytesIO(out.stdout)))
                        data = shots[-1] if shots else None   # a few in: the exposure has settled
                    except (OSError, subprocess.TimeoutExpired):
                        data = None
                finally:
                    with feed.cond:
                        feed.held -= 1
            if data is None:                                  # the live picture will do
                data, _ = feed.frame()
            if data is None:
                raise ValueError(feed.error or "The camera sent no picture")
            name = time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:4]}.jpg"
            self.photos[name] = data
            while len(self.photos) > 5:
                self.photos.popitem(last=False)
            return name


# ---- telling Pitato this camera is here ----------------------------------------------------
def beacon_loop(ptz, port=PORT):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        # ("gpicam": the word a camera's beacon has always had, so older and newer ones still find each other)
        msg = {"gpicam": 1, "id": ID, "host": socket.gethostname(), "port": port,
               "name": settings().get("name") or socket.gethostname(), "turns": bool(ptz.ctrls)}
        try:
            s.sendto(json.dumps(msg).encode(), ("255.255.255.255", BEACON_PORT))
        except OSError:
            pass
        time.sleep(BEACON_EVERY)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{name}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #101318;
       color: #d9dee6; font: 15px/1.4 system-ui, sans-serif; }}
main {{ width: min(960px, 100vw - 32px); }}
img {{ display: block; width: 100%; border-radius: 10px; background: #1a1f27; }}
p {{ color: #8b95a3; margin: 10px 2px; }}
</style></head><body><main>
<img src="/api/camera/stream" alt="The live picture from {name}">
<p>{name} &middot; add this Pi's address on Pitato's Camera tab</p>
</main></body></html>"""


def serve(feed, ptz, shutter, port=PORT):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def host_ok(self):
            """Only this Pi's own names and addresses (and any in hosts =): a website can't point a
            made-up name here."""
            try:
                host = (urllib.parse.urlsplit("//" + (self.headers.get("Host") or "")).hostname or "").lower()
            except ValueError:
                return False
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                pass
            me = socket.gethostname().lower()
            names = {"localhost", me} | {f"{me}.{d}" for d in ("local", "lan", "home", "home.arpa", "localdomain",
                                                               "internal", "fritz.box")}
            names |= {h.lower() for h in re.split(r"[\s,]+", settings().get("hosts", "")) if h}
            return host in names

        def allowed(self):
            if not self.host_ok():
                self.reply(403, {"ok": False, "error": "Open this by the Pi's name or address"})
                return False
            if self.path != "/" and self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reply(403, {"ok": False, "error": "Not from another site"})
                return False
            return True

        def reply(self, code, body, ctype="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                name = settings().get("name") or socket.gethostname()
                import html
                return self.reply(200, PAGE.format(name=html.escape(name)).encode(), "text/html; charset=utf-8")
            if path == "/api/camera.jpg":
                jpeg, _ = feed.frame()
                if jpeg is None:
                    return self.reply(503, {"ok": False, "error": feed.error or "The camera is starting"})
                return self.reply(200, jpeg, "image/jpeg")
            if path == "/api/camera/stream":
                return self.stream()
            if path == "/api/ptz":
                return self.reply(200, {"ok": True, **ptz.status(), **about()})
            if path in ("/api/info", "/api/status"):
                return self.reply(200, {"ok": True, **about(),
                                        "camera": {"device": feed.dev, "card": feed.card, "size": list(feed.size),
                                                   "fps": feed.fps, "running": feed.running(), "error": feed.error}})
            m = re.fullmatch(r"/api/photos/([\w.-]+\.jpg)", path)
            if m:
                data = shutter.photos.get(m.group(1))
                return self.reply(200, data, "image/jpeg") if data else self.reply(404, {"ok": False, "error": "No such picture"})
            self.reply(404, {"ok": False, "error": "Not found"})

        def stream(self):
            """MJPEG for a browser's <img>: it keeps showing the newest picture."""
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = None
            try:
                while True:
                    jpeg, got = feed.frame(newer_than=seq, timeout=FIRST_FRAME)
                    if jpeg is None:
                        return
                    seq = got
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                    self.wfile.write(jpeg + b"\r\n")
                    self.wfile.flush()
            except (OSError, ValueError):
                return

        def do_POST(self):
            if not self.allowed():
                return
            if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/json":
                return self.reply(415, {"ok": False, "error": "JSON only"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if 0 <= n <= 65536 else None
            except ValueError:
                body = None
            if not isinstance(body, dict):
                return self.reply(400, {"ok": False, "error": "Bad request"})
            path = urllib.parse.urlsplit(self.path).path
            num = lambda k: float(body[k]) if body.get(k) is not None else None   # noqa: E731
            try:
                if path == "/api/ptz/drive":
                    pos = ptz.drive(body.get("vx", 0), body.get("vy", 0), sid=str(body.get("sid") or "")[:64],
                                    seq=int(body.get("seq") or 0), speed=body.get("speed"))
                    return self.reply(200, {"ok": True, "position": pos, "following": False})
                if path == "/api/ptz/stop":
                    pos = ptz.stop(sid=str(body.get("sid") or "")[:64], seq=int(body.get("seq") or 0))
                    return self.reply(200, {"ok": True, "position": pos})
                if path == "/api/ptz/set":
                    pos = ptz.home() if body.get("center") else ptz.set(num("pan"), num("tilt"), num("zoom"))
                    return self.reply(200, {"ok": True, "position": pos})
                if path == "/api/ptz/home":
                    return self.reply(200, {"ok": True, "position": ptz.home()})
                if path == "/api/ptz/follow":
                    return self.reply(400, {"ok": False, "error": "This camera can't follow you"})
                if path == "/api/photos":
                    name = shutter.take()
                    return self.reply(200, {"ok": True, "photo": {"name": name, "url": f"/api/photos/{name}"}})
            except (ValueError, TypeError, OverflowError, OSError, subprocess.TimeoutExpired) as ex:
                return self.reply(400, {"ok": False, "error": str(ex)[:160] or "That didn't work"})
            self.reply(404, {"ok": False, "error": "Not found"})

    def about():
        return {"server": "Pitato camera", "name": settings().get("name") or socket.gethostname(),
                "hostname": socket.gethostname()}

    server = ThreadingHTTPServer(("", port), Handler)
    server.daemon_threads = True
    return server


def main():
    port = PORT
    if "--port" in sys.argv[1:-1]:                    # another port, if something else has 5433
        port = int(sys.argv[sys.argv.index("--port") + 1])
    feed = Feed()
    feed.configure()
    ptz = Ptz(feed)
    ptz.find()
    shutter = Shutter(feed)
    try:
        server = serve(feed, ptz, shutter, port=port)
    except OSError as ex:
        print(f"can't use port {port}: {ex}", flush=True)
        sys.exit(1)
    threading.Thread(target=beacon_loop, args=(ptz, port), daemon=True, name="beacon").start()
    print(f"camera: {feed.card or feed.dev or 'none yet'} on port {port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        feed.stop()


if __name__ == "__main__":
    main()
