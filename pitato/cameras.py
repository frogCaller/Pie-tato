"""The Camera tab's cameras: your other Pis running camera.py, or any camera with a stream, a picture or a web
page (an address and its port is enough: the picture is found there)."""
import html
import io
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import uuid

from .config import clean_name, read_lines, read_own_text, settings_file, write_setting
from .util import save_picture
from .net import cam_address, cam_host, cam_json, CAM_JSON_MAX, cam_key, cam_open, read_capped
from .screen import slow_pi
from .camera import OwnCameras


# Camera tab: cameras on other Pis (PiE-ink, or camera.py from this repo), or any camera on your network
CAM_SPEED = {"slow": 25, "normal": None, "fast": 120}   # None: the camera's own setting
CAM_TICK = 0.15          # stick messages while the d-pad is held (it stops after 0.7 s quiet)
CAM_FPS = 4              # how often a camera that's only a picture is fetched, for the Camera tab
CAM_STREAM_FPS = (15, 8)  # ...and the pictures of one that streams, shown at most this many a second (on a Pi 4
                          # or 5; on a slower Pi)
PIE_STREAM = "/api/camera/stream"   # a Pi's camera (camera.py's): its stream, watched rather than its picture fetched
PIE_STREAMS = ("Pitato camera", "Pietato camera", "USB camera")   # ...the camera servers that have one, as they
                                                     # say (PiE-ink's picture is fetched). camera.py says the first, as
                                                     # it always has (Pis not yet updated look for it): shown as the
                                                     # second. The last: a USB camera plugged into this Pi
CAM_SHOWN_AS = {"Pitato camera": "Pietato camera"}   # a camera server's name, as the Camera tab and web page show it
CAM_STREAM_WAIT = 15.0   # seconds a stream may send nothing before it's connected again (some send a picture only
                         # when they have a new one)
CAM_STALE = 3.0          # seconds without a new picture: "Reconnecting…" over the last one, which stays up
CAM_LOST = 20.0          # ...this long (or nothing yet, twice): "Can't reach this camera"
CAM_RETRY = (0.3, 1.0, 2.0)   # seconds before connecting again, after each time in a row it didn't work
CAM_PORTS = (5000, 5433)  # where a Pi's camera answers: PiE-ink's web app, then camera.py
CAM_LINKS = [(8080, "/?action=stream"), (8080, "/stream"), (81, "/stream"), (8081, "/"), (80, "/")]  # other servers
CAM_PATHS = ("/video_feed", "/stream", "/stream.mjpg", "/video", "/mjpeg", "/?action=stream", "/mjpg/video.mjpg",
             "/video.mjpg", "/live", "/feed", "/cam", "/camera", "/webcam", "/videostream.cgi", "/snapshot.jpg",
             "/shot.jpg", "/capture", "/image.jpg", "/jpg")   # ...at an address:port: where camera servers put it
CAM_BATCH = 4            # places asked at once (a camera that answers one at a time keeps up)
CAM_PAGE_MAX = 300_000   # bytes of a camera's web page read, for the picture on it
CAM_PAGE_LINKS = 8       # pictures on a page tried, at most
CAM_SNIFF = 4096         # bytes looked at, when a camera doesn't say what it sends
CAM_LINK_WORDS = re.compile(r"stream|video|mjpe?g|jpe?g|snap|shot|feed|cam|frame|image|live|capture|picture|cgi",
                            re.I)
CAM_BEACON = 5151        # PiE-inks and camera.py say they're there, a few times a minute
CAM_FOUND_FOR = 30       # a camera gone quiet this long drops off "On your network"
CAM_FOUND_KEEP = 16      # at most this many cameras heard on the network are kept in mind
USB_CAMERA = "USB camera"   # what a USB camera plugged into this Pi answers as (camera.py's OwnCameras)


CAM_FRAME_MAX = 12_000_000   # bytes: a camera's live pictures aren't big (a big one is kept as a smaller copy),
CAM_KEEP_MAX = 1_500_000
CAM_PHOTO_MAX = 32_000_000   # and a picture at its biggest size is well under this


CAM_HOLD = 0.6           # seconds: holding SELECT this long turns Follow me on/off
CAM_SHOT_SHOW = 4        # seconds the picture you just took stays in the corner
CAM_TURNS = (0, 90, 180, 270)   # a camera's picture turned clockwise (a camera on its side), a quarter at a time
TURNED_DPAD = {90: {"up": "left", "right": "up", "down": "right", "left": "down"},   # (the picture's up, as the
               180: {"up": "down", "right": "left", "down": "up", "left": "right"},   # camera turns for it)
               270: {"up": "right", "right": "down", "down": "left", "left": "up"}}


class NotAStream(OSError):
    """What answered where a stream was looked for isn't one (a web page, say)."""


def fit_size(w, h, area):
    """(width, height) of a w x h picture as big as fits in area (w, h), its shape kept."""
    s = min(area[0] / w, area[1] / h)
    return max(int(w * s), 1), max(int(h * s), 1)


def fit_picture(im, area):
    """A picture made as big as fits in area (w, h), its shape kept (None: no area)."""
    if im is None or not area or area[0] < 1 or area[1] < 1:
        return None
    size = fit_size(im.width, im.height, area)
    if size == im.size:
        return im
    from PIL import Image
    return im.resize(size, Image.BILINEAR)


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


# ---- cameras: other Pis (PiE-ink, or camera.py), or any camera on your network -----------------
CAMERA_HEAD = ("# Cameras for the Camera tab, one per line:   camera = address   (a name after it if you like)\n"
               "# Any camera on your network: its address and port (the picture is found there), or its link.\n"
               "# A Pi can share its USB camera too: sudo bash setup.sh --camera on it.\n")


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
    """(kind, url) to try at an address, most likely first, in two parts: (first, then). First a Pi's camera on
    its usual ports and the address's own page; then, at an address with a port, where camera servers usually put
    their stream. A link with a path is tried as it is."""
    full = addr if "://" in addr else "http://" + addr
    u = urllib.parse.urlsplit(full)
    base = f"{u.scheme}://{u.netloc}"
    if u.path not in ("", "/") or u.query:
        return [("link", full)], []
    if u.port:
        return [("pie", base), ("link", base + "/")], [("link", base + p) for p in CAM_PATHS]
    return [("pie", f"{base}:{p}") for p in CAM_PORTS] + [("link", f"{base}:{p}{path}") for p, path in CAM_LINKS], []


ANSWERED = {"kind": "none"}   # cam_probe: something answered there, but not a camera


def read_some(r, most, until):
    """Up to `most` bytes of an answer: as much as has come by `until` (on time.monotonic())."""
    out, n = [], 0
    read = r.read1 if hasattr(r, "read1") else r.read
    while n < most and time.monotonic() < until:
        try:
            chunk = read(min(65536, most - n))
        except OSError:                               # (timed out, or cut off: what came so far)
            break
        if not chunk:
            break
        out.append(chunk)
        n += len(chunk)
    return b"".join(out)


def sniffed(head, length):
    """What a camera sends, from its first bytes, when it doesn't say (or says it's something else): "mjpeg" for
    a stream of pictures (a part's boundary first, or a picture with no length to it), "jpeg" for one picture,
    or None."""
    h = head.lstrip(b"\r\n")
    if h.startswith(b"--") and b"\xff\xd8" in h:
        return "mjpeg"
    if h.startswith(b"\xff\xd8\xff"):
        return "jpeg" if length else "mjpeg"
    if h.startswith(b"\x89PNG"):
        return "jpeg"
    return None


def page_links(text, url):
    """The pictures on a camera's web page, as links to try: its <img>s, <video>s and the like first, then what's
    quoted in it that looks like a link to a stream or a picture (a page's script may put the picture in)."""
    found = re.findall(r"""<(?:img|video|source|iframe|embed|object)\b[^>]*?\b(?:src|data)\s*=\s*["']?([^"'\s>]+)""",
                       text, re.I)
    found += [q for q in re.findall(r"""["']([^"'\s<>(){}]{2,200})["']""", text)
              if ("/" in q or "." in q) and CAM_LINK_WORDS.search(q)]
    out = []
    for link in found:
        link = html.unescape(link).strip()
        path = link.lower().split("?")[0].split("#")[0]
        if not link or link.startswith(("data:", "javascript:", "#", "mailto:", "blob:")) or path.endswith(
                (".js", ".css", ".png", ".gif", ".svg", ".ico", ".html", ".htm", ".json", ".woff", ".woff2", ".ttf")):
            continue
        try:
            full = urllib.parse.urljoin(url, link).split("#")[0]
        except ValueError:
            continue
        if full.startswith(("http://", "https://")) and full != url and full not in out:
            out.append(full)
    return out[:CAM_PAGE_LINKS]


def cam_probe(kind, url, timeout=3):
    """What answers at url: {"kind": "pie"/"mjpeg"/"jpeg", "url", "name", "server"}; {"kind": "page", "links"}: a
    web page, and the pictures on it to try; ANSWERED: something else; None: nothing answered."""
    try:
        if kind == "pie":
            try:
                info = cam_json(url + "/api/ptz", timeout)
            except (ValueError, urllib.error.HTTPError):
                return ANSWERED                         # (something's there: not a Pi's camera)
            if not isinstance(info, dict) or "available" not in info:
                return ANSWERED
            name = clean_name(info.get("name"))
            if not name:                                # PiE-ink: its name is in its status
                try:
                    name = clean_name(cam_json(url + "/api/status", timeout).get("hostname"))
                except Exception:
                    pass
            return {"kind": "pie", "url": url, "name": name, "server": clean_name(info.get("server") or "PiE-ink")}
        with cam_open(url, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            stream = {"kind": "mjpeg", "url": url, "name": "", "server": "MJPEG stream"}
            picture = {"kind": "jpeg", "url": url, "name": "", "server": "Picture link"}
            if "multipart/x-mixed-replace" in ctype:
                return stream
            if ctype.startswith("image/"):
                return picture
            until = time.monotonic() + timeout
            head = read_some(r, CAM_SNIFF, until)       # (what it sends, if it doesn't say, or says it's a page)
            what = sniffed(head, r.headers.get("Content-Length"))
            if what:
                return stream if what == "mjpeg" else picture
            if "html" in ctype or "xml" in ctype or head.lstrip()[:1] == b"<":   # a web page: the pictures on it
                page = head + read_some(r, CAM_PAGE_MAX - len(head), until)
                links = page_links(page.decode("utf-8", "replace"), r.geturl() or url)
                return {"kind": "page", "url": url, "links": links} if links else ANSWERED
            return ANSWERED
    except urllib.error.HTTPError:
        return ANSWERED                                 # (something's there: not this)
    except Exception:
        return None


def cam_probe_all(cands, timeout):
    """cam_probe on each of [(kind, url)] at once: what answered at each, in order."""
    found = [None] * len(cands)

    def one(i, kind, url):
        found[i] = cam_probe(kind, url, timeout)
    threads = [threading.Thread(target=one, args=(i, k, u), daemon=True) for i, (k, u) in enumerate(cands)]
    for t in threads:
        t.start()
    end = time.monotonic() + timeout * 2 + 1
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return list(found)


def cam_pick(found):
    """The camera among what answered: a Pi's camera or a stream before a single picture, each in order."""
    for kinds in (("pie", "mjpeg"), ("jpeg",)):
        hit = next((f for f in found if f and f["kind"] in kinds), None)
        if hit:
            return hit
    return None


def cam_detect(addr, timeout=3, most=20.0):
    """What's at an address: a Pi's camera, or any camera's stream or picture. First a Pi's camera and the
    address's own page (and if that's a web page, the pictures on it); then where camera servers usually put
    their stream, a few at a time (some answer one at a time). None when nothing answers there at all."""
    first, queue = cam_candidates(addr)
    end = time.monotonic() + most
    results = cam_probe_all(first, timeout)
    if not any(results):
        return None
    tried = {u for _, u in first}

    def pictures_first(found, queue):
        """The pictures on any page among found, at the front of the queue (once each)."""
        links = []
        for p in found:
            if p and p["kind"] == "page":
                links += [u for u in p["links"] if u not in tried and u not in links]
        return [("link", u) for u in links] + [c for c in queue if c[1] not in links]
    queue = pictures_first(results, queue)
    while queue and time.monotonic() < end and not any(r and r["kind"] in ("pie", "mjpeg") for r in results):
        batch, queue = queue[:CAM_BATCH], queue[CAM_BATCH:]
        tried.update(u for _, u in batch)
        got = cam_probe_all(batch, timeout)
        results += got
        queue = pictures_first(got, queue)
    return cam_pick(results)


def stream_patience(resp, secs):
    """An answer waited on longer than connecting was: a stream that's quiet a while isn't gone."""
    try:
        resp.fp.raw._sock.settimeout(secs)
    except AttributeError:
        pass                                          # (as it was opened, then)


def cam_grab(url, timeout=4):
    """A picture from a link: all of it when the camera says how long it is; otherwise the first whole JPEG of
    what it sends (some send a stream of them while saying it's one picture)."""
    with cam_open(url, timeout=timeout) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        if r.headers.get("Content-Length") or not (ctype in ("", "application/octet-stream") or "jp" in ctype):
            return read_capped(r, CAM_FRAME_MAX, time.monotonic() + timeout * 2)
        data = next(mjpeg_frames(r, patience=timeout * 2), None)
    if not data:
        raise OSError("no picture came")
    return data


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

    A Pi running PiE-ink, or Pietato's own camera server (camera.py: setup.sh --camera), is
    worked with the same calls as PiE-ink's web page: /api/ptz/drive while the d-pad is held,
    /api/ptz/stop when let go, /api/ptz/set for zoom, /api/ptz/follow and /api/ptz/home; the
    picture comes from /api/camera.jpg, and a picture is taken with its own shutter (POST
    /api/photos: the camera's biggest size) and copied into ~/Pictures. Any other camera with a
    stream or a picture (a script sharing a webcam, an ESP32-CAM, motion, mjpg-streamer...) can be
    watched, found from its address and port alone (cam_detect: on its web page, or where camera
    servers usually put it), and A keeps the picture on screen. Your cameras are in camera.txt; Pis
    that say they have one (PiE-ink and camera.py announce themselves) are listed as found. A USB
    camera plugged into this Pi is first among yours, by itself, while it's plugged in: camera.py's
    OwnCameras answers for it, on this Pi only, as camera.py does for one on another Pi."""

    def __init__(self):
        self.patterns = []
        self.cams = []               # [{"addr", "name"}]: this Pi's USB cameras ("usb": True), then camera.txt's
        self.own = OwnCameras()      # ...the USB ones: what answers for them
        self.usb = []                # ...and them, as they were last looked for
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
        self.fit_to = None           # (w, h): where the Camera tab shows it, for...
        self.fitted = None           # ...(the newest picture, it made that size): made on the camera's thread
        self.frame_at = 0.0
        self.no_stream = set()       # the Pis whose camera has no stream: their picture's fetched instead
        self.connecting = False      # connecting again (its stream ended, or it didn't answer), till a picture comes
        self.was_stale = False       # the screen said "Reconnecting…" last time it looked
        self.action = ""
        self.sid = uuid.uuid4().hex[:10]
        self.seq = 0
        self.running = False
        self.on_change = lambda: None
        self.on_frame = None         # a new picture came (and nothing else changed): on_change, if it's not set
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
        self.flips = {}              # cam_key -> True: it turns left when told right (its settings: START in your
                                     # list of cameras)
        self.flips_v = {}            # cam_key -> True: it turns down when told up (there too)
        self.raw = None              # the newest picture, as the camera has it (frame is it turned)
        self.turned = {}             # cam_key -> (when, how far, the picture turned): the last one asked for
        self.lock = threading.Lock()   # the gen, and what its threads bring back, change together

    def load(self, patterns, last=None):
        self.patterns = patterns
        self.cams = self.listed(patterns)
        keys = [cam_key(c["addr"]) for c in self.cams]
        if self.addr and (cam_key(self.addr) in keys or cam_key(self.addr) in self.found):
            return
        if last and cam_key(last) in keys:
            self.select(self.cams[keys.index(cam_key(last))]["addr"])
        else:
            self.select(self.cams[0]["addr"] if self.cams else "")

    # this Pi's own USB cameras
    def usb_look(self, now=False):
        """The USB cameras plugged into this Pi, looked for (afresh every couple of seconds, or now): first among
        yours, while they're plugged in. True when they've changed."""
        try:
            got = self.own.look(now)
        except Exception as ex:                       # (whatever the kernel says, the Camera tab carries on)
            print(f"usb cameras: {ex!r}", flush=True)
            got = []
        names = [c["name"] for c in got]
        usb, seen = [], {}
        for c in got:
            name = c["name"]
            if names.count(name) > 1:                 # (two of a kind: numbered)
                seen[name] = seen.get(name, 0) + 1
                name = f"{name} {seen[name]}"
            usb.append({"addr": c["addr"], "name": name, "usb": True})
            self.known[cam_key(c["addr"])] = {"kind": "pie", "url": "http://" + c["addr"], "name": name,
                                              "server": USB_CAMERA}
        if usb == self.usb:
            return False
        self.usb = usb
        if self.patterns or self.cams:
            self.cams = usb + [c for c in self.cams if not c.get("usb")]
        if self.is_usb(self.addr) and not any(cam_key(c["addr"]) == cam_key(self.addr) for c in usb):
            with self.lock:                           # (the one on screen, unplugged: its picture goes at once)
                self.frame = self.raw = self.jpeg = self.fitted = None
                self.connecting = True
        self.on_change()
        return True

    def listed(self, patterns=None):
        """Your cameras: this Pi's USB ones first (while they're plugged in), then camera.txt's."""
        self.usb_look()
        return list(self.usb) + read_cameras(patterns if patterns is not None else self.patterns)

    def is_usb(self, addr):
        """A USB camera plugged into this Pi (or one that was)."""
        return bool(addr) and (self.known.get(cam_key(addr)) or {}).get("server") == USB_CAMERA

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

    def kind_shown(self, addr, server=""):
        """What answers at addr (a camera server's name, a stream...), in words for the screen and the web page."""
        kind = self.kind_of(addr) or server or ""
        return CAM_SHOWN_AS.get(kind, kind)

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

    # one that turns the wrong way: left and right (or up and down) swapped as it's steered
    def flipped(self, addr, axis="x"):
        """Left and right swapped as it's steered; axis "y": up and down."""
        flips = self.flips_v if axis == "y" else self.flips
        return bool(addr) and flips.get(cam_key(addr)) is True

    def set_flip(self, addr, on, axis="x"):
        flips = self.flips_v if axis == "y" else self.flips
        if on:
            flips[cam_key(addr)] = True
        else:
            flips.pop(cam_key(addr), None)
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
            self.fitted, self.connecting = None, False
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
        """The d-pad is for turning it: one that turns, or a Pi's camera that hasn't said yet (not a USB camera
        that's been unplugged)."""
        return self.kind == "pie" and (self.available or not self.info) and \
            not (self.is_usb(self.addr) and not self.mine(self.addr))

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

    def close(self):
        """Pietato's stopping: this Pi's USB cameras let go."""
        self.stop()
        self.own.close()

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
                if self.flipped(self.addr, "y"):      # (...or down when told up)
                    vy = -vy
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
        """The picture while the camera's on screen: its stream watched (connected again when it ends), or its
        picture fetched a few times a second. A Pi's camera streams too, when it has one (camera.py's does; one
        that hasn't is fetched from then on). The last picture stays up while it connects again ("Reconnecting…"
        over it); "Can't reach this camera" only once nothing's come for a while."""
        fails = 0
        streams = kind == "pie" and self.kind_of(self.addr) in PIE_STREAMS   # (camera.py's: PiE-ink's is fetched)
        while self.running and gen == self.gen:
            t0 = time.monotonic()
            try:
                stream = url if kind == "mjpeg" else url + PIE_STREAM if streams and \
                    cam_key(url) not in self.no_stream else None
                if stream:
                    try:
                        came = self.watch_stream(gen, stream, only_streams=kind == "pie")
                    except (urllib.error.HTTPError, NotAStream) as ex:
                        if kind != "pie" or getattr(ex, "code", 404) not in (404, 405, 501) or \
                                self.kind_of(self.addr) == USB_CAMERA:   # (one that's unplugged: it'll be back)
                            raise
                        self.no_stream.add(cam_key(url))   # (no stream there after all: its picture, fetched)
                        continue
                    if not came:
                        raise OSError("no pictures came")
                    fails, self.connecting = 0, True
                    self.wait_a_moment(gen, CAM_RETRY[0])   # (a camera that serves one at a time: done with us)
                    continue
                self.show(gen, cam_grab(url + "/api/camera.jpg" if kind == "pie" else url))
                fails = 0
            except Exception:
                fails += 1
                with self.lock:
                    if gen != self.gen:
                        return
                    self.connecting = True
                    lost = (self.frame is None and fails >= 2) or (self.frame is not None and
                                                                   time.monotonic() - self.frame_at > CAM_LOST)
                    if lost:
                        self.frame = self.raw = None
                        if kind != "pie":
                            self.reached = False
                self.on_change()
                self.wait_a_moment(gen, CAM_RETRY[min(fails, len(CAM_RETRY)) - 1])
                continue
            time.sleep(max(0.0, 1 / CAM_FPS - (time.monotonic() - t0)))

    def wait_a_moment(self, gen, secs):
        end = time.monotonic() + secs
        while self.running and gen == self.gen and time.monotonic() < end:
            time.sleep(0.05)

    @property
    def stale(self):
        """The picture on screen is old, and it's connecting again (a stream that's only slow, still connected,
        isn't: some send a picture every few seconds)."""
        return self.frame is not None and self.connecting and time.monotonic() - self.frame_at > CAM_STALE

    def stale_changed(self):
        """Called every loop: True when the picture's just gone old, or come back (the screen says so)."""
        now = self.stale
        if now != self.was_stale:
            self.was_stale = now
            return True
        return False

    def show(self, gen, data):
        """A picture that came: decoded (small: quick on a Pi Zero), turned as the camera is, and made the size
        the Camera tab shows it, here on the camera's thread (the screen's only puts it up)."""
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (640, 480))
        rgb = im.convert("RGB")
        was = self.connecting or self.frame is None   # (back, or the first: the whole screen's drawn again)
        frame = turn_picture(rgb, self.turn_of(self.addr))
        fitted = fit_picture(frame, self.fit_to)
        with self.lock:
            if gen != self.gen:
                return
            self.raw, self.jpeg, self.frame_at, self.reached = rgb, data, time.monotonic(), True
            self.frame, self.fitted, self.connecting = frame, (frame, fitted), False
        (self.on_frame if self.on_frame is not None and not was else self.on_change)()

    @staticmethod
    def stream_fps():
        """A stream's pictures shown a second, at most: as many as this Pi draws easily."""
        return CAM_STREAM_FPS[1 if slow_pi() else 0]

    def watch_stream(self, gen, url, only_streams=False):
        """An MJPEG camera: its stream, as many of its pictures a second decoded as the screen shows (the rest
        passed over), until it ends (or sends nothing for CAM_STREAM_WAIT). How many pictures came; it raises
        when it couldn't connect (NotAStream, only_streams: what answered isn't a stream)."""
        alive = lambda: self.running and gen == self.gen   # noqa: E731
        came = 0
        every = 0.8 / self.stream_fps()               # (a hair less: one sent at just that rate isn't passed over)
        with cam_open(url, timeout=5) as r:
            if only_streams and "multipart/x-mixed-replace" not in (r.headers.get("Content-Type") or "").lower():
                raise NotAStream(url)
            stream_patience(r, CAM_STREAM_WAIT)
            last = 0.0
            try:
                for jpeg in mjpeg_frames(r, alive, patience=CAM_STREAM_WAIT):
                    came += 1
                    now = time.monotonic()
                    if now - last >= every:
                        last = now
                        try:
                            self.show(gen, jpeg)
                        except OSError:
                            pass                      # a broken picture: the next one
            except Exception:
                if not came:
                    raise                             # (it went quiet, or was cut off: again, as it was going)
        return came

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
        keep = set(self.found) | {cam_key(c["addr"]) for c in self.cams + self.usb} | {cam_key(self.addr)}
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
        self.usb_look()
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
        live = self.live_snapshot(addr, max(max_age, 1.0))
        if live:
            return live
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
                data = cam_grab(got["url"] + "/api/camera.jpg" if got["kind"] == "pie" else got["url"], timeout=6)
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

    def live_snapshot(self, addr, max_age):
        """The camera on screen's newest picture, if it's no older than max_age seconds: a snapshot without a
        second connection to it (a camera that serves one at a time would make the two take turns)."""
        with self.lock:
            if not (self.running and self.addr and cam_key(addr) == cam_key(self.addr)) or self.jpeg is None \
                    or self.raw is None or time.monotonic() - self.frame_at > max_age or len(self.jpeg) > CAM_KEEP_MAX:
                return None
            data, small = self.jpeg, self.raw.copy()
        small.thumbnail((64, 48))
        self.missing.pop(cam_key(addr), None)
        self.thumbs[cam_key(addr)] = (data, small, time.time())
        return self.thumbs[cam_key(addr)]

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
