"""The Camera tab's cameras: your other Pis running camera.py, or any MJPEG or JPEG link."""
import io
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import uuid

from .config import clean_name, read_lines, read_own_text, settings_file, write_setting
from .util import save_picture
from .net import cam_address, cam_host, cam_json, CAM_JSON_MAX, cam_key, cam_open, read_capped


# Camera tab: cameras on other Pis (PiE-ink, or camera.py from this repo), or any MJPEG/JPEG link
CAM_SPEED = {"slow": 25, "normal": None, "fast": 120}   # None: the camera's own setting
CAM_TICK = 0.15          # stick messages while the d-pad is held (it stops after 0.7 s quiet)
CAM_FPS = 4              # how often the picture refreshes on the Camera tab
CAM_PORTS = (5000, 5433)  # where a Pi's camera answers: PiE-ink's web app, then camera.py
CAM_LINKS = [(8080, "/?action=stream"), (8080, "/stream"), (81, "/stream"), (8081, "/")]  # other servers
CAM_PATHS = ("/stream", "/?action=stream", "/video", "/mjpg/video.mjpg", "/")   # ...at an address:port
CAM_BEACON = 5151        # PiE-inks and camera.py say they're there, a few times a minute
CAM_FOUND_FOR = 30       # a camera gone quiet this long drops off "On your network"
CAM_FOUND_KEEP = 16      # at most this many cameras heard on the network are kept in mind


CAM_FRAME_MAX = 12_000_000   # bytes: a camera's live pictures aren't big (a big one is kept as a smaller copy),
CAM_KEEP_MAX = 1_500_000
CAM_PHOTO_MAX = 32_000_000   # and a picture at its biggest size is well under this


CAM_HOLD = 0.6           # seconds: holding SELECT this long turns Follow me on/off
CAM_SHOT_SHOW = 4        # seconds the picture you just took stays in the corner
CAM_TURNS = (0, 90, 180, 270)   # a camera's picture turned clockwise (a camera on its side), a quarter at a time
TURNED_DPAD = {90: {"up": "left", "right": "up", "down": "right", "left": "down"},   # (the picture's up, as the
               180: {"up": "down", "right": "left", "down": "up", "left": "right"},   # camera turns for it)
               270: {"up": "right", "right": "down", "down": "left", "left": "up"}}


def turn_picture(im, deg):
    """A picture (PIL) turned clockwise by deg (0, 90, 180 or 270)."""
    if deg not in (90, 180, 270):
        return im
    from PIL import Image
    t = getattr(Image, "Transpose", Image)            # (Pillow 9.1 on; the names before it otherwise)
    return im.transpose({90: t.ROTATE_270, 180: t.ROTATE_180, 270: t.ROTATE_90}[deg])


def turn_file(data, deg, quality=90):
    """A JPEG (or PNG) turned clockwise by deg: the same bytes when it isn't turned, or isn't a picture."""
    if deg not in (90, 180, 270) or not data:
        return data
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        png = (im.format or "").lower() == "png"
        im = turn_picture(im if png else im.convert("RGB"), deg)
        out = io.BytesIO()
        im.save(out, "PNG") if png else im.save(out, "JPEG", quality=quality)
        return out.getvalue()
    except (OSError, ValueError, SyntaxError):
        return data


# ---- cameras: other Pis (PiE-ink, or camera.py), or any MJPEG/JPEG link ------------------------
CAMERA_HEAD = ("# Cameras for the Camera tab, one per line:   camera = address   (a name after it if you like)\n"
               "# A Pi running Pitato's camera server (sudo bash setup.sh --camera),\n"
               "# or any MJPEG or JPEG camera link.\n")


def read_cameras(patterns):
    """The cameras in camera.txt, in order: 'camera = address' lines (a name after the address
    if you like), and the one 'url =' (or 'ip =' and 'port =') of the earlier PiE-ink setting."""
    cams, ip, port = [], "", "5000"
    for line in read_lines(patterns):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        k = k.lower()
        if k in ("camera", "url") and v:
            addr, _, name = v.partition(" ")
            cams.append({"addr": addr, "name": name.strip()[:40]})
        elif k == "ip":
            ip = v
        elif k == "port" and v:
            port = v
    if ip:
        cams.append({"addr": f"{ip}:{port}", "name": ""})
    out, seen = [], set()
    for c in cams:
        if cam_address(c["addr"]) and cam_key(c["addr"]) not in seen:
            seen.add(cam_key(c["addr"]))
            out.append(c)
    return out


def edit_cameras(add=None, name="", remove=None):
    """camera.txt with a camera added or taken out, and the rest of it as it was."""
    path = settings_file("camera.txt")
    name = clean_name(name)
    try:
        lines = read_own_text(path).splitlines()
    except FileNotFoundError:
        lines = CAMERA_HEAD.rstrip("\n").split("\n")
    if remove:
        k = cam_key(remove)
        vals = {}
        for line in lines:
            key, _, v = line.strip().partition("=")
            if not line.strip().startswith("#") and v:
                vals.setdefault(key.strip().lower(), v.strip())
        legacy = bool(vals.get("ip")) and cam_key(f"{vals['ip']}:{vals.get('port') or '5000'}") == k
        out = []
        for line in lines:
            key, _, v = line.strip().partition("=")
            key = key.strip().lower()
            if not line.strip().startswith("#") and (
                    (key in ("camera", "url") and cam_key(v.strip().partition(" ")[0]) == k)
                    or (legacy and key in ("ip", "port"))):
                continue
            out.append(line)
        lines = out
    if add:
        if not any(ln.strip() and not ln.strip().startswith("#") for ln in lines) and not lines:
            lines = CAMERA_HEAD.rstrip("\n").split("\n")
        lines.append(f"camera = {add}" + (f"   {name}" if name else ""))
    return write_setting("camera.txt", "\n".join(lines).rstrip("\n") + "\n")


def cam_candidates(addr):
    """(kind, url) to try at an address, most likely first: a Pi's camera on its usual ports, then
    where other camera servers usually put their stream. A link with a path is tried as it is."""
    full = addr if "://" in addr else "http://" + addr
    u = urllib.parse.urlsplit(full)
    base = f"{u.scheme}://{u.netloc}"
    if u.path not in ("", "/") or u.query:
        return [("link", full)]
    if u.port:
        return [("pie", base)] + [("link", base + p) for p in CAM_PATHS]
    return [("pie", f"{base}:{p}") for p in CAM_PORTS] + [("link", f"{base}:{p}{path}") for p, path in CAM_LINKS]


def cam_probe(kind, url, timeout=3):
    """What answers at url: {"kind": "pie"/"mjpeg"/"jpeg", "url", "name", "server"}, or None."""
    try:
        if kind == "pie":
            info = cam_json(url + "/api/ptz", timeout)
            if not isinstance(info, dict) or "available" not in info:
                return None
            name = clean_name(info.get("name"))
            if not name:                                # PiE-ink: its name is in its status
                try:
                    name = clean_name(cam_json(url + "/api/status", timeout).get("hostname"))
                except Exception:
                    pass
            return {"kind": "pie", "url": url, "name": name, "server": clean_name(info.get("server") or "PiE-ink")}
        with cam_open(url, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
        if "multipart/x-mixed-replace" in ctype:
            return {"kind": "mjpeg", "url": url, "name": "", "server": "MJPEG stream"}
        if ctype.startswith("image/"):
            return {"kind": "jpeg", "url": url, "name": "", "server": "Picture link"}
    except Exception:
        return None
    return None


def cam_detect(addr, timeout=3):
    """Every likely place at once; the first of them, in order, that answers is the camera."""
    cands = cam_candidates(addr)
    found = [None] * len(cands)

    def one(i, kind, url):
        found[i] = cam_probe(kind, url, timeout)
    threads = [threading.Thread(target=one, args=(i, k, u), daemon=True) for i, (k, u) in enumerate(cands)]
    for t in threads:
        t.start()
    end = time.monotonic() + timeout * 2 + 1
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return next((f for f in found if f), None)


def mjpeg_frames(resp, alive=None, patience=10.0):
    """The JPEGs in an MJPEG stream, cut at each picture's own start and end markers (whether or
    not the stream says how long each part is). It stops as soon as alive() says so, and gives
    up when no whole picture has come for `patience` seconds."""
    buf = b""
    read = resp.read1 if hasattr(resp, "read1") else (lambda n: resp.read(min(n, 16384)))
    last = time.monotonic()
    while True:
        if alive is not None and not alive():
            return
        if time.monotonic() - last > patience:
            raise TimeoutError("no pictures")
        chunk = read(65536)
        if not chunk:
            return
        buf += chunk
        while True:
            a = buf.find(b"\xff\xd8")
            if a < 0:
                buf = buf[-1:]
                break
            z = buf.find(b"\xff\xd9", a + 2)
            if z < 0:
                buf = buf[a:]
                break
            yield buf[a:z + 2]
            last = time.monotonic()
            buf = buf[z + 2:]
        if len(buf) > CAM_FRAME_MAX:                  # no end in sight: start again
            buf = b""


class Camera:
    """The Camera tab: cameras on your other Pis, or anywhere on your network.

    A Pi running PiE-ink, or Pitato's own camera server (camera.py: setup.sh --camera), is
    worked with the same calls as PiE-ink's web page: /api/ptz/drive while the d-pad is held,
    /api/ptz/stop when let go, /api/ptz/set for zoom, /api/ptz/follow and /api/ptz/home; the
    picture comes from /api/camera.jpg, and a picture is taken with its own shutter (POST
    /api/photos: the camera's biggest size) and copied into ~/Pictures. Any other camera with an
    MJPEG or JPEG link (an ESP32-CAM, motion, mjpg-streamer...) can be watched, and A keeps the
    picture on screen. Your cameras are in camera.txt; Pis that say they have one (PiE-ink
    and camera.py announce themselves) are listed as found."""

    def __init__(self):
        self.patterns = []
        self.cams = []               # [{"addr", "name"}]: camera.txt, in order
        self.found = {}              # cam_key -> {"addr", "name", "server", "seen"}: heard on the network
        self.known = {}              # cam_key -> what answered there: {"kind", "url", "name", "server"}
        self.missing = {}            # cam_key -> when nothing answered there
        self.thumbs = {}             # cam_key -> (its JPEG, a small picture, when)
        self.addr = ""               # the camera on screen
        self.kind = None             # "pie", "mjpeg" or "jpeg", once it has answered
        self.url = ""
        self.gen = 0                 # goes up when the camera changes or stops: its threads end
        self.finding = None          # the gen a look at the address is running for
        self.held = set()            # d-pad directions held right now
        self.zoom_dir = 0
        self.zoom = None             # 0..1, once the camera has said
        self.speed = "normal"
        self.info = {}               # the last /api/ptz answer
        self.reached = None          # True / False once we've tried
        self.frame = None            # the newest picture (PIL image)
        self.jpeg = None             # ...as it came (a camera without a shutter: the photo)
        self.frame_at = 0.0
        self.action = ""
        self.sid = uuid.uuid4().hex[:10]
        self.seq = 0
        self.running = False
        self.on_change = lambda: None
        self.on_saved = lambda path: None
        self.shooting = False        # a picture on its way
        self.shot = None             # (small copy, path, when) of the last one taken
        self.sel_down = None         # when SELECT went down: hold = follow, tap = on_select
        self.sel_used = False
        self.on_select = self.next_speed   # (media mode: the bot says what it sees, when there's one)
        self.start_down = None       # when START went down: tap = home, hold = the next speed
        self.start_used = False
        self.listening = False
        self.scanning = False
        self.on_pie = lambda ip, msg: None   # every PiE-ink heard (it's asked first for what it has)
        self.turns = {}              # cam_key -> how far its picture is turned clockwise (90, 180, 270)
        self.flips = {}              # cam_key -> True: it turns left when told right (◀▶ on it, in your list)
        self.raw = None              # the newest picture, as the camera has it (frame is it turned)
        self.turned = {}             # cam_key -> (when, how far, the picture turned): the last one asked for
        self.lock = threading.Lock()   # the gen, and what its threads bring back, change together

    def load(self, patterns, last=None):
        self.patterns = patterns
        self.cams = read_cameras(patterns)
        keys = [cam_key(c["addr"]) for c in self.cams]
        if self.addr and (cam_key(self.addr) in keys or cam_key(self.addr) in self.found):
            return
        if last and cam_key(last) in keys:
            self.select(self.cams[keys.index(cam_key(last))]["addr"])
        else:
            self.select(self.cams[0]["addr"] if self.cams else "")

    # names and places
    def name_of(self, addr):
        """What to call a camera: its name in camera.txt, the name it gave, or its address."""
        k = cam_key(addr)
        for c in self.cams:
            if cam_key(c["addr"]) == k and c["name"]:
                return c["name"]
        got = self.known.get(k) or self.found.get(k) or {}
        return got.get("name") or cam_host(addr) or addr

    def kind_of(self, addr):
        got = self.known.get(cam_key(addr)) or self.found.get(cam_key(addr)) or {}
        return got.get("server", "")

    @property
    def where(self):
        return self.addr.split("://", 1)[-1]

    @property
    def title(self):
        return self.name_of(self.addr) if self.addr else ""

    def place(self):
        """(1-based place, how many) of the camera on screen among yours, or None."""
        keys = [cam_key(c["addr"]) for c in self.cams]
        k = cam_key(self.addr)
        return (keys.index(k) + 1, len(keys)) if k in keys else None

    def mine(self, addr):
        return cam_key(addr) in [cam_key(c["addr"]) for c in self.cams]

    # a camera on its side: its picture turned
    def turn_of(self, addr):
        """How far a camera's picture is turned clockwise: 0, 90, 180 or 270."""
        deg = self.turns.get(cam_key(addr), 0) if addr else 0
        return deg if deg in CAM_TURNS else 0

    def set_turn(self, addr, deg):
        """A camera's picture turned clockwise by deg from now on (the one on screen at once)."""
        k = cam_key(addr)
        if deg in (90, 180, 270):
            self.turns[k] = deg
        else:
            self.turns.pop(k, None)
        self.turned.pop(k, None)
        with self.lock:
            if self.addr and cam_key(self.addr) == k and self.raw is not None:
                self.frame = turn_picture(self.raw, self.turn_of(addr))
        self.on_change()

    # one that turns the wrong way: left and right swapped as it's steered
    def flipped(self, addr):
        return bool(addr) and self.flips.get(cam_key(addr)) is True

    def set_flip(self, addr, on):
        if on:
            self.flips[cam_key(addr)] = True
        else:
            self.flips.pop(cam_key(addr), None)
        self.on_change()

    def may_steer(self, addr):
        """One that may turn: not a plain picture link (an MJPEG or JPEG camera), as far as it's known."""
        return (self.known.get(cam_key(addr)) or {}).get("kind") not in ("mjpeg", "jpeg")

    def turned_file(self, addr, data, when=None):
        """A picture from a camera (its JPEG), turned as its picture is. `when` (a snapshot's time): the
        last one asked for is kept, so the web page asking again for the same one costs nothing."""
        deg, k = self.turn_of(addr), cam_key(addr)
        if not deg:
            return data
        hit = self.turned.get(k)
        if when is not None and hit and hit[0] == when and hit[1] == deg:
            return hit[2]
        out = turn_file(data, deg, quality=85)
        if when is not None:
            self.turned[k] = (when, deg, out)
        return out

    # choosing one, and finding out what it is
    def select(self, addr):
        """A camera on screen; what answers at its address is found out first (once)."""
        if addr and self.addr and cam_key(addr) == cam_key(self.addr):
            return
        with self.lock:
            self.gen += 1
            self.addr = addr or ""
            got = self.known.get(cam_key(addr)) if addr else None
            self.kind, self.url = (got["kind"], got["url"]) if got else (None, "")
            self.frame, self.raw, self.jpeg, self.reached, self.info, self.zoom = None, None, None, None, {}, None
        self.held.clear()
        self.zoom_dir, self.sel_down, self.start_down, self.action = 0, None, None, ""
        if self.running:
            self.begin()
        self.on_change()

    def begin(self):
        gen = self.gen
        if not self.addr:
            return
        if self.kind:
            self.spawn(gen)
        elif self.finding != gen:
            self.finding = gen
            threading.Thread(target=self.find_job, args=(gen, self.addr), daemon=True, name="cam-find").start()

    def find_job(self, gen, addr):
        """What's at the address, asked again every few seconds while nothing answers."""
        try:
            while self.running and gen == self.gen:
                got = cam_detect(addr)
                with self.lock:
                    if gen != self.gen:
                        return
                    if got:
                        self.known[cam_key(addr)] = got
                        self.missing.pop(cam_key(addr), None)
                        self.kind, self.url = got["kind"], got["url"]
                    else:
                        self.missing[cam_key(addr)] = time.time()
                        self.reached = False
                if got:
                    self.spawn(gen)
                    self.on_change()
                    return
                self.on_change()
                for _ in range(50):
                    if not self.running or gen != self.gen:
                        return
                    time.sleep(0.1)
        finally:
            if self.finding == gen:
                self.finding = None

    def spawn(self, gen):
        if not self.running or gen != self.gen:
            return
        if self.kind == "pie":
            threading.Thread(target=self.control_loop, args=(gen, self.url), daemon=True,
                             name="cam-control").start()
        threading.Thread(target=self.picture_loop, args=(gen, self.kind, self.url), daemon=True,
                         name="cam-picture").start()

    # talking to it
    def call(self, path, body=None, timeout=3, raw=False, base=None, limit=None):
        url = path if path.startswith(("http://", "https://")) else (base or self.url) + path
        with cam_open(url, body, timeout) as r:
            out = read_capped(r, limit or (CAM_FRAME_MAX if raw else CAM_JSON_MAX), time.monotonic() + timeout * 2)
        return out if raw else (json.loads(out) if out.strip() else {})

    def post(self, path, body, base=None):
        try:
            return self.call(path, body, base=base)
        except Exception:
            return None

    def refresh(self, gen, base):
        try:
            info = self.call("/api/ptz", base=base)
            for k in ("position", "follow", "sleep"):     # whatever a camera says, these are dicts
                if not isinstance(info.get(k), dict):
                    info[k] = {}
            zoom = info["position"].get("zoom")
            zoom = None if zoom is None else max(0.0, min(1.0, float(zoom)))
        except Exception:
            info = zoom = None
        with self.lock:
            if gen != self.gen:
                return
            if info is None:
                self.reached, self.info = False, {}
            else:
                self.info, self.reached = info, True
                if self.zoom_dir == 0 and zoom is not None:
                    self.zoom = zoom
        self.on_change()

    @property
    def available(self):
        """A camera that turns (and zooms)."""
        return self.kind == "pie" and bool(self.info.get("available"))

    @property
    def steers(self):
        """The d-pad is for turning it: one that turns, or a Pi's camera that hasn't said yet."""
        return self.kind == "pie" and (self.available or not self.info)

    @property
    def can_follow(self):
        return self.available and (self.info.get("follow") or {}).get("can", True) is not False

    @property
    def following(self):
        return bool((self.info.get("follow") or {}).get("on"))

    @property
    def asleep(self):
        return bool((self.info.get("sleep") or {}).get("asleep"))

    # running while the Camera tab's picture is on screen
    def start(self):
        if self.running:
            return
        self.running = True
        self.listen()
        self.begin()

    def stop(self):
        self.held.clear()
        self.zoom_dir = 0
        self.sel_down = self.start_down = None
        with self.lock:
            if self.running:
                self.running = False
                self.gen += 1

    def control_loop(self, gen, base):
        moving, next_info, next_zoom = False, 0.0, 0.0
        while self.running and gen == self.gen:
            now = time.monotonic()
            way = TURNED_DPAD.get(self.turn_of(self.addr), {})   # (up on a turned picture: where it is)
            held = {way.get(d, d) for d in self.held}
            if held:
                vx = ("right" in held) - ("left" in held)
                vy = ("up" in held) - ("down" in held)
                if self.flipped(self.addr):           # (one that turns left when told right)
                    vx = -vx
                self.seq += 1
                body = {"vx": vx, "vy": vy, "sid": self.sid, "seq": self.seq}
                if CAM_SPEED[self.speed]:
                    body["speed"] = CAM_SPEED[self.speed]
                self.post("/api/ptz/drive", body, base)
                moving = True
            elif moving:
                self.seq += 1
                self.post("/api/ptz/stop", {"sid": self.sid, "seq": self.seq}, base)
                moving = False
            if self.zoom_dir and now >= next_zoom:
                self.zoom = max(0.0, min(1.0, (self.zoom or 0.0) + 0.04 * self.zoom_dir))
                self.post("/api/ptz/set", {"zoom": round(self.zoom, 3)}, base)
                self.action = f"Zoom {round(self.zoom * 100)}%"
                next_zoom = now + 0.12
                self.on_change()
            if now >= next_info and not held and not self.zoom_dir:
                self.refresh(gen, base)
                next_info = now + 2
            time.sleep(CAM_TICK)
        if moving:                                    # never leave it turning
            self.seq += 1
            self.post("/api/ptz/stop", {"sid": self.sid, "seq": self.seq}, base)

    def picture_loop(self, gen, kind, url):
        while self.running and gen == self.gen:
            t0 = time.monotonic()
            try:
                if kind == "mjpeg":
                    self.watch_stream(gen, url)
                else:
                    self.show(gen, self.call(url + "/api/camera.jpg" if kind == "pie" else url,
                                             timeout=4, raw=True))
            except Exception:
                with self.lock:
                    if gen != self.gen:
                        return
                    gone = time.monotonic() - self.frame_at > 5 and (self.frame is not None or self.reached is None)
                    if gone:
                        self.frame = self.raw = None
                        if kind != "pie":
                            self.reached = False
                if gone:
                    self.on_change()
                time.sleep(1)
            time.sleep(max(0.0, 1 / CAM_FPS - (time.monotonic() - t0)))

    def show(self, gen, data):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (640, 480))                   # decoded small: quick on a Pi Zero
        rgb = im.convert("RGB")
        with self.lock:
            if gen != self.gen:
                return
            self.raw, self.jpeg, self.frame_at, self.reached = rgb, data, time.monotonic(), True
            self.frame = turn_picture(rgb, self.turn_of(self.addr))
        self.on_change()

    def watch_stream(self, gen, url):
        """An MJPEG camera: its stream, a few pictures a second of it decoded."""
        alive = lambda: self.running and gen == self.gen   # noqa: E731
        with cam_open(url, timeout=5) as r:
            last = 0.0
            for jpeg in mjpeg_frames(r, alive):
                now = time.monotonic()
                if now - last >= 1 / CAM_FPS:
                    last = now
                    try:
                        self.show(gen, jpeg)
                    except OSError:
                        pass                          # a broken picture: the next one
        if alive():
            raise OSError("the stream ended")

    # the cameras on the network, and a small picture of each for the list
    def listen(self):
        """PiE-inks and camera.py say they're there a few times a minute: they show up as found."""
        if self.listening:
            return
        self.listening = True
        threading.Thread(target=self.listen_loop, daemon=True, name="cam-beacon").start()

    def listen_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            s.bind(("", CAM_BEACON))
        except OSError as ex:
            print(f"can't hear cameras on the network: {ex}", flush=True)
            return
        while True:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except OSError:
                time.sleep(0.5)
                continue
            try:
                self.heard(ip, data)
            except Exception:                         # anyone on the network can send anything
                pass

    def heard(self, ip, data):
        """One beacon: a PiE-ink or camera.py saying it's there."""
        msg = json.loads(data.decode())
        if not isinstance(msg, dict):
            return
        if msg.get("pie") == 1:
            self.on_pie(ip, msg)
        caps = msg.get("caps")
        if msg.get("gpicam") == 1:
            server, port = "Pitato camera", msg.get("port") or 5433
        elif msg.get("pie") == 1 and (caps.get("camera", True) if isinstance(caps, dict) else True):
            server, port = "PiE-ink", msg.get("port") or 5000
        else:
            return
        if isinstance(port, str) and port.isdigit():
            port = int(port)
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
            return
        addr = f"{ip}:{port}"
        k = cam_key(addr)
        new = k not in self.found
        self.found[k] = {"addr": addr, "name": clean_name(msg.get("name") or msg.get("host") or ip) or ip,
                         "server": server, "seen": time.time()}
        if new:
            self.tidy()
            self.on_change()

    def tidy(self):
        """Cameras not heard from for a while forgotten (and only the newest few kept), and with
        them what was known about any camera that's neither yours nor heard lately."""
        now = time.time()
        found = sorted(list(self.found.items()), key=lambda kv: -kv[1]["seen"])
        self.found = {k: f for k, f in found[:CAM_FOUND_KEEP] if now - f["seen"] <= CAM_FOUND_FOR * 10}
        keep = set(self.found) | {cam_key(c["addr"]) for c in self.cams} | {cam_key(self.addr)}
        for name in ("known", "missing", "thumbs", "turned"):
            setattr(self, name, {k: v for k, v in list(getattr(self, name).items()) if k in keep})

    def found_list(self):
        """Cameras heard on the network lately that aren't in your list."""
        now = time.time()
        mine = {cam_host(c["addr"]) for c in self.cams}
        out = [f for f in list(self.found.values())
               if now - f["seen"] <= CAM_FOUND_FOR and cam_host(f["addr"]) not in mine]
        return sorted(out, key=lambda f: f["name"].lower())

    def scan(self):
        """A small picture from each camera for the list, in the background (one at a time)."""
        self.listen()
        self.tidy()
        if self.scanning:
            return
        self.scanning = True
        threading.Thread(target=self.scan_job, daemon=True, name="cam-scan").start()

    def unseen(self):
        """Cameras in the list without a small picture yet (and not just found not to answer)."""
        now = time.time()
        return [a for a in [c["addr"] for c in self.cams] + [f["addr"] for f in self.found_list()]
                if cam_key(a) not in self.thumbs and now - self.missing.get(cam_key(a), 0) > 30]

    def scan_job(self):
        try:
            for addr in [c["addr"] for c in self.cams] + [f["addr"] for f in self.found_list()]:
                if time.time() - self.missing.get(cam_key(addr), 0) > 30 or cam_key(addr) in self.thumbs:
                    self.snapshot(addr, max_age=20)
                    self.on_change()
        finally:
            self.scanning = False
            self.on_change()

    def snapshot(self, addr, max_age=2.0):
        """(JPEG, small picture, when) from a camera, no older than max_age seconds; None when it
        doesn't answer."""
        k = cam_key(addr)
        have = self.thumbs.get(k)
        if have and time.time() - have[2] < max_age:
            return have
        got = self.known.get(k)
        if not got:
            got = cam_detect(addr)
            if not got:
                self.missing[k] = time.time()
                return None
            self.known[k] = got
        try:
            if got["kind"] == "mjpeg":
                with cam_open(got["url"], timeout=5) as r:
                    data = next(mjpeg_frames(r, patience=8), None)
            else:
                data = self.call(got["url"] + "/api/camera.jpg" if got["kind"] == "pie" else got["url"],
                                 timeout=6, raw=True)
            from PIL import Image
            im = Image.open(io.BytesIO(data or b""))
            im.draft("RGB", (320, 240))
            small = im.convert("RGB")
            small.thumbnail((64, 48))
            if len(data) > CAM_KEEP_MAX:              # a big picture: a smaller copy is kept
                big = Image.open(io.BytesIO(data))
                big.draft("RGB", (1280, 960))
                big = big.convert("RGB")
                big.thumbnail((1280, 960))
                out = io.BytesIO()
                big.save(out, "JPEG", quality=85)
                data = out.getvalue()
        except Exception:
            self.missing[k] = time.time()
            return None
        self.missing.pop(k, None)
        self.thumbs[k] = (data, small, time.time())
        return self.thumbs[k]

    # buttons
    def press(self, name):
        if name == "a":
            self.take_photo()
            return True
        if not self.steers:
            if name in ("up", "down", "left", "right", "x", "y", "start", "select"):
                self.action = "This camera doesn't turn" if self.reached else ""
                return True
            return False
        if name in ("up", "down", "left", "right"):
            if self.following:                        # steering takes over from follow-me
                self.info.setdefault("follow", {})["on"] = False
                threading.Thread(target=self.post, args=("/api/ptz/follow", {"on": False}),
                                 daemon=True).start()
            self.held.add(name)
            self.action = self.moving_text()
        elif name in ("x", "y"):
            self.zoom_dir = 1 if name == "x" else -1
        elif name == "start":                         # decided when let go, or once held long enough
            self.start_down, self.start_used = time.monotonic(), False
        elif name == "select":                        # decided when let go, or once held long enough
            self.sel_down, self.sel_used = time.monotonic(), False
        else:
            return False
        return True

    def toggle_follow(self):
        if not self.can_follow:
            self.action = "This camera can't follow you"
            return
        on = not self.following
        self.info.setdefault("follow", {})["on"] = on
        self.action = "Following you" if on else "Follow off"
        threading.Thread(target=self.post, args=("/api/ptz/follow", {"on": on}),
                         daemon=True).start()

    def go_home(self):
        self.action = "Going home"
        threading.Thread(target=self.post, args=("/api/ptz/home", {}), daemon=True).start()

    def next_speed(self):
        order = ["normal", "fast", "slow"]
        self.speed = order[(order.index(self.speed) + 1) % len(order)]
        self.action = f"Speed: {self.speed}"

    def check_hold(self):
        """Called every loop: SELECT held long enough turns Follow me on or off; START, the speed."""
        if self.sel_down is not None and not self.sel_used \
                and time.monotonic() - self.sel_down >= CAM_HOLD:
            self.sel_used = True
            self.toggle_follow()
            return True
        if self.start_down is not None and not self.start_used \
                and time.monotonic() - self.start_down >= CAM_HOLD:
            self.start_used = True
            self.next_speed()
            return True
        return False

    # taking a picture
    def take_photo(self):
        if self.shooting or not self.addr:
            return
        self.shooting = True
        self.action = "Taking a picture…"
        threading.Thread(target=self.photo_job, daemon=True, name="cam-photo").start()

    def photo_bytes(self):
        """The camera's own shutter (PiE-ink, camera.py): woken first if asleep, at its biggest size.
        A camera without one, or an older PiE-ink: the picture on screen. Turned as its picture is."""
        addr = self.addr
        if self.kind != "pie":
            if self.jpeg is None:
                raise ValueError("there's no picture yet")
            return turn_file(self.jpeg, self.turn_of(addr), quality=95)
        return turn_file(self.shutter(self.url), self.turn_of(addr), quality=95)

    def photo_of(self, addr):
        """A picture from the camera at addr (for the bot): its own shutter on a Pi with one, the
        live picture from any other, turned as its picture is. ValueError: why not."""
        k = cam_key(addr)
        got = self.known.get(k)
        if not got:
            got = cam_detect(addr)
            if not got:
                self.missing[k] = time.time()
                raise ValueError(f"the camera {self.name_of(addr)} didn't answer")
            self.known[k] = got
            self.missing.pop(k, None)
        try:
            if got["kind"] == "pie":
                return turn_file(self.shutter(got["url"]), self.turn_of(addr), quality=95)
            snap = self.snapshot(addr, max_age=0)
        except urllib.error.HTTPError as e:
            raise ValueError(f"the camera said {e.code}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise ValueError(f"can't reach the camera {self.name_of(addr)}")
        if not snap:
            raise ValueError(f"the camera {self.name_of(addr)} didn't answer")
        return turn_file(snap[0], self.turn_of(addr), quality=95)

    def shutter(self, base):
        """A picture from the camera at base (PiE-ink, camera.py) with its own shutter: woken first if
        asleep, at its biggest size. An older PiE-ink: the live picture."""
        try:
            got = self.call("/api/photos", {"filter": "none"}, timeout=25, base=base)
            got = got if isinstance(got, dict) else {}
            photo = got.get("photo") if isinstance(got.get("photo"), dict) else {}
            url = photo.get("url") if isinstance(photo.get("url"), str) else ""
            if not url:
                raise ValueError(clean_name(got.get("error"), 80) or "the camera sent no picture")
            if url.startswith(("http://", "https://")):
                if cam_host(url) != cam_host(base):
                    raise ValueError("the camera sent a picture from somewhere else")
            elif not url.startswith("/"):
                url = "/" + url
            return self.call(url, timeout=20, raw=True, base=base, limit=CAM_PHOTO_MAX)
        except urllib.error.HTTPError as e:
            if e.code in (404, 405):
                return self.call("/api/camera.jpg", timeout=6, raw=True, base=base)
            try:
                why = clean_name(json.loads(e.read(65536) or b"{}").get("error"), 80)
            except (ValueError, OSError, AttributeError):
                why = None
            raise ValueError(why or f"the camera said {e.code}")

    def photo_job(self):
        from PIL import Image
        try:
            try:
                data = self.photo_bytes()
                im = Image.open(io.BytesIO(data))
                ext = ".png" if (im.format or "").lower() == "png" else ".jpg"
                small = im.convert("RGB")
                small.thumbnail((176, 132))
            except urllib.error.HTTPError as e:
                raise ValueError(f"the camera said {e.code}")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                raise ValueError("can't reach the camera")
            except OSError:
                raise ValueError("that wasn't a picture")
            try:
                path = save_picture(data, ext)
            except OSError as e:
                raise ValueError(f"couldn't save it ({e.strerror or e})")
            self.shot = (small, path, time.monotonic())
            self.action = ""
            self.on_saved(path)
        except Exception as e:
            self.action = f"No picture: {e or 'no answer'}"[:60]
            self.on_saved(None)
        finally:
            self.shooting = False
            self.on_change()

    def moving_text(self):
        parts = [d for d in ("up", "down", "left", "right") if d in self.held]
        return "Moving " + "-".join(parts) if parts else ""

    def release(self, name):
        if name in self.held:
            self.held.discard(name)
            self.action = self.moving_text()
        elif name in ("x", "y") and self.zoom_dir:
            self.zoom_dir = 0
        elif name == "select" and self.sel_down is not None:
            self.sel_down, tapped = None, not self.sel_used
            if tapped:                                # a tap: what the Camera tab says
                self.on_select()
        elif name == "start" and self.start_down is not None:
            self.start_down, tapped = None, not self.start_used
            if tapped:                                # a tap: back to where it started
                self.go_home()
