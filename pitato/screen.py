"""Any screen, any sound output: the screen's size and the framebuffer media mode draws on, the
sound cards (and Bluetooth headphones and speakers), the video size to ask for, and the size an HDMI screen starts
at."""
import fcntl
import glob
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time

from .system import read_file


# Plex: the server converts video to a size the Pi Zero plays smoothly
PLEX_RESOLUTION = "640x480"
PLEX_BITRATE = 1500                            # kbps


PLEX_LIVE_HEIGHT = 480                         # pick the channel's stream closest to this


# ---- any screen, any sound output ---------------------------------------------------
def pi_model():
    return read_file("/proc/device-tree/model").replace("\x00", "").strip()


def slow_pi():
    """Pi Zero, 1, 2 and 3: they play 480 lines smoothly, not much more."""
    m = pi_model()
    return ("Zero" in m or bool(re.search(r"Raspberry Pi [123]\b", m)) or "Raspberry Pi Model" in m
            or bool(re.search(r"Compute Module( 3)?( Plus)? Rev", m)))


def screen_size():
    """The screen's real size: 640x480 on the GPi Case, 1920x1080 on most TVs."""
    try:
        with open("/dev/fb0", "rb", buffering=0) as f:
            w, h = fb_geometry(f)[:2]
        if w and h:
            return w, h
    except (OSError, struct.error):
        pass
    m = re.match(r"(\d+),(\d+)", read_file("/sys/class/graphics/fb0/virtual_size"))
    return (int(m.group(1)), int(m.group(2))) if m else (640, 480)


def video_target():
    """(Plex's size, its bitrate in kbps, live TV's lines): sharper on a big screen when the
    Pi can keep up (a Pi 4 or 5 on a TV), the GPi Case's 480 lines otherwise."""
    w, h = screen_size()
    if w >= 1280 and h >= 720 and not slow_pi():
        return "1280x720", 4000, 720
    return PLEX_RESOLUTION, PLEX_BITRATE, PLEX_LIVE_HEIGHT


def sound_cards():
    """[(card id, name)] for the sound outputs: ("vc4hdmi0", "HDMI 1"), ("Headphones", ...)..."""
    out = []
    for line in read_file("/proc/asound/cards").splitlines():
        m = re.match(r"\s*\d+\s+\[(\S+)\s*\]:\s*\S+\s+-\s+(.+)", line)
        if not m:
            continue
        cid, desc = m.group(1), m.group(2).strip()
        hd = re.fullmatch(r"vc4hdmi(\d?)", cid)
        if hd:
            name = "HDMI" + (f" {int(hd.group(1)) + 1}" if hd.group(1) else "")
        elif cid == "Headphones" or "headphone" in desc.lower():
            name = "Headphones"
        else:
            name = desc[:24]
        if name not in [n for _, n in out]:
            out.append((cid, name))
    return out


def hdmi_ports():
    """The HDMI ports with a screen plugged in: [0], [1], [0, 1]..."""
    ports = []
    for path in sorted(glob.glob(os.path.join(DRM_DIR, "card*-HDMI-A-*", "status"))):
        if read_file(path).strip() == "connected":
            m = re.search(r"HDMI-A-(\d+)", path)
            if m and int(m.group(1)) - 1 not in ports:
                ports.append(int(m.group(1)) - 1)
    return ports


# ---- HDMI: the picture's size (Settings > Resolution) -------------------------------
DRM_DIR = "/sys/class/drm"                     # the kernel's screens (KMS): none on the GPi Case
CMDLINE_TXT = ("/boot/firmware/cmdline.txt", "/boot/cmdline.txt")   # Bookworm's, then an older system's
HDMI_SIZE = re.compile(r"video=HDMI-A-\d+:(\d+)x(\d+)")
RES_SMALLEST, RES_BIGGEST = (640, 480), (1920, 1200)   # the sizes to pick from: the menus' own, up to 1080p
                                                       # (bigger is slower to draw, and no sharper)


def hdmi_screens():
    """The HDMI ports with a screen plugged in, by the kernel's names for them, and the sizes each
    screen takes, its own first: [("HDMI-A-1", ["1920x1080", "1280x1024", ...])]. [] with none
    plugged in, or without KMS (the GPi Case)."""
    out = []
    for path in sorted(glob.glob(os.path.join(DRM_DIR, "card*-HDMI-A-*"))):
        port = re.search(r"(HDMI-A-\d+)$", path)
        if not port or read_file(os.path.join(path, "status")) != "connected":
            continue
        sizes = []
        for mode in read_file(os.path.join(path, "modes")).split():
            if re.fullmatch(r"\d+x\d+", mode) and mode not in sizes:    # (not 1920x1080i: interlaced)
                sizes.append(mode)
        if sizes and port.group(1) not in [p for p, _ in out]:
            out.append((port.group(1), sizes))
    return out


def size_of(text):
    """(1280, 720) from "1280x720"."""
    w, h = text.split("x")
    return int(w), int(h)


def resolution_choices():
    """Settings > Resolution: (the HDMI screen's own size, [the sizes it takes, biggest first]), or None
    without one (the GPi Case's screen)."""
    screens = hdmi_screens()
    if not screens:
        return None
    sizes = screens[0][1]
    fits = [s for s in sizes if RES_SMALLEST[0] <= size_of(s)[0] <= RES_BIGGEST[0]
            and RES_SMALLEST[1] <= size_of(s)[1] <= RES_BIGGEST[1]]
    fits.sort(key=size_of, reverse=True)
    return sizes[0], fits


def cmdline_txt():
    """The file with the kernel's command line, where an HDMI screen's size is set: None if not a Pi."""
    return next((path for path in CMDLINE_TXT if os.path.isfile(path)), None)


def boot_resolution():
    """The size cmdline.txt sets the HDMI screen to ("1280x720"), or None: the screen's own (Auto)."""
    path = cmdline_txt()
    for word in (read_file(path) if path else "").split("\n", 1)[0].split():
        m = HDMI_SIZE.match(word)
        if m:
            return f"{m.group(1)}x{m.group(2)}"
    return None


def set_boot_video(ports, args):
    """cmdline.txt's say on these HDMI ports' picture, from the next start-up: what it had for them
    goes, and args come in (["video=HDMI-A-1:1280x720@60"], or [] for each screen's own size). The rest
    stays as it is. Returns what it had for them (to put back), or raises OSError."""
    path = cmdline_txt()
    if not path:
        raise OSError("this Pi has no cmdline.txt")
    with open(path) as f:
        text = f.read()
    line, nl, rest = text.partition("\n")          # (the kernel's line is the first)
    words = line.split()
    was = [w for w in words if any(w.startswith(f"video={p}:") for p in ports)]
    words = [w for w in words if w not in was] + list(args)
    if "root=" in line and not any(w.startswith("root=") for w in words):
        raise OSError("cmdline.txt doesn't look right")   # (never: but it's what starts the Pi)
    new = " ".join(words) + nl + rest
    if new != text:
        tmp = path + ".pitato"
        with open(tmp, "w") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:                                       # (the new name too, before the Pi restarts)
            fd = os.open(os.path.dirname(path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    return was


def sound_card(choice):
    """The card for Settings > Sound. Auto plays through the TV when one is plugged into HDMI, and
    through the Pi's usual output otherwise (None: the system's default)."""
    cards = sound_cards()
    ids = [c for c, _ in cards]
    cid = None
    if choice and choice != "Auto":
        cid = next((c for c, n in cards if n == choice), None)
    else:
        for port in hdmi_ports():
            cid = next((c for c in (f"vc4hdmi{port}", "vc4hdmi") if c in ids), None)
            if cid:
                break
    return cid


def sound_route(choice):
    """Where Settings > Sound sends sound now: "bluetooth" (Auto, while Bluetooth headphones or a speaker are
    connected), a card's id, or "" (the system's own)."""
    if choice in (None, "", "Auto") and bt_outputs():
        return "bluetooth"
    return sound_card(choice) or ""


def sound_place(choice):
    """sound_route, and which Bluetooth headphones: ("bluetooth", their BlueZ object), or (a card's id or "", "")."""
    route = sound_route(choice)
    if route != "bluetooth":
        return route, ""
    outs = bt_outputs()
    return route, (outs[-1][0] if outs else "")


def sound_name(route):
    """A route's name, as Settings > Sound has it: "HDMI", "Headphones"..., "Bluetooth", or "the Pi" (its own)."""
    if route == "bluetooth":
        return "Bluetooth"
    return next((n for c, n in sound_cards() if c == route), "the Pi") if route else "the Pi"


def sound_device(choice, route=None):
    """mplayer's -ao for Settings > Sound (or for a route already worked out); plain ALSA is the fallback either
    way."""
    route = sound_route(choice) if route is None else route
    if route == "bluetooth":
        return f"alsa:device={BT_SOUND},alsa"
    return f"alsa:device=default={route},alsa" if route else "alsa"


def aplay_device(choice, route=None):
    """aplay's -D for Settings > Sound: the same as mplayer's."""
    route = sound_route(choice) if route is None else route
    if route == "bluetooth":
        return BT_SOUND
    return f"default:CARD={route}" if route else ""


# ---- Bluetooth headphones and speakers: BlueALSA's (setup.sh puts it on) ----------------------------------------
# BlueALSA is asked over D-Bus (busctl) which headphones it can play through: at once when a device connects or goes
# (the kernel lists each link), often for a while after that, and otherwise seldom.
BT_SOUND = "bluealsa"          # ALSA's name for them (the one connected last), with BlueALSA's ALSA plugin
BT_LINKS = "/sys/class/bluetooth"   # hci0, and hci0:N for each device connected to it now
BT_ASK_SOON = 1.5              # seconds BlueALSA's answer is good for, a while after a device connects or goes
BT_ASK_LATER = 15.0            # ...and otherwise
BT_SETTLE = 20.0               # ...that while
_bt_seen = {"at": -1e9, "outs": [], "links": None, "moved": -1e9, "here": None, "names": {}}


def bt_links():
    """The kernel's names for the Bluetooth links up now (hci0:12...): one for each device connected."""
    try:
        return tuple(sorted(n for n in os.listdir(BT_LINKS) if ":" in n))
    except OSError:
        return ()


def bt_outputs(fresh=False):
    """[(its BlueZ object, its place in the order they connected)] for the Bluetooth headphones and speakers sound
    can go to now (BlueALSA has them), the last one connected last. [] without BlueALSA."""
    seen, now = _bt_seen, time.monotonic()
    if seen["here"] is None:
        seen["here"] = bool(shutil.which("bluealsa"))
    links = bt_links()
    if links != seen["links"]:                       # (one connected, or gone: ask now, and often for a while)
        seen["links"], seen["moved"], fresh = links, now, True
    if not seen["here"]:
        return []
    good = BT_ASK_SOON if now - seen["moved"] < BT_SETTLE else BT_ASK_LATER
    if not fresh and now - seen["at"] < good:
        return seen["outs"]
    outs = None                                        # (None: no answer to go by)
    try:
        r = subprocess.run(["busctl", "--json=short", "call", "org.bluealsa", "/org/bluealsa",
                            "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            err = r.stderr or ""
            if any(w in err for w in ("not provided by", "ServiceUnknown", "NameHasNoOwner", "not activatable")):
                outs = []                              # (BlueALSA isn't running: nothing to play through)
        else:
            data = json.loads(r.stdout).get("data")
            objs = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
            outs = []
            for ifaces in objs.values():
                pcm = ifaces.get("org.bluealsa.PCM1") if isinstance(ifaces, dict) else None
                if not isinstance(pcm, dict):
                    continue
                got = {k: (v.get("data") if isinstance(v, dict) else None) for k, v in pcm.items()}
                dev, seq = str(got.get("Device") or ""), got.get("Sequence")
                if str(got.get("Transport") or "").startswith("A2DP-source") and got.get("Mode") == "sink" and dev:
                    outs.append((dev, seq if isinstance(seq, int) and not isinstance(seq, bool) else 0))
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        outs = None
    if outs is None:                                   # (busy, or it timed out: as it was, unless nothing's connected)
        outs = list(seen["outs"]) if links else []
    outs.sort(key=lambda o: o[1])
    seen["at"], seen["outs"] = now, outs
    return outs


def bt_output_name(device=None):
    """The name of Bluetooth headphones (by their BlueZ object; the last connected, by default), or ''."""
    if device is None:
        outs = bt_outputs()
        device = outs[-1][0] if outs else ""
    if not str(device).startswith("/org/bluez/"):
        return ""
    names = _bt_seen["names"]
    if not names.get(device):
        try:
            r = subprocess.run(["busctl", "--json=short", "get-property", "org.bluez", device, "org.bluez.Device1",
                                "Alias"], capture_output=True, text=True, timeout=3)
            got = json.loads(r.stdout).get("data") if r.returncode == 0 else ""
            names[device] = re.sub(r"[\x00-\x1f\x7f]", "", str(got or ""))[:40].strip()
        except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
            return ""
    return names[device]


def fb_geometry(f):
    """(width, height, x offset, y offset, bits per pixel, colour fields, stride) of a framebuffer."""
    info = fcntl.ioctl(f, 0x4600, bytes(160))   # FBIOGET_VSCREENINFO
    (w, h, xv, _, xo, yo, bpp, _) = struct.unpack_from("8I", info, 0)
    fields = [struct.unpack_from("2I", info, o) for o in (32, 44, 56)]
    try:
        with open(f"/sys/class/graphics/{os.path.basename(f.name)}/stride") as fs:
            stride = int(fs.read())
    except (OSError, ValueError):
        stride = xv * bpp // 8
    return w, h, xo, yo, bpp, fields, stride


def read_screen(f, geo, max_w=640):
    """What's on a framebuffer, as a picture at most max_w wide. On a big screen only every
    few pixels are read, so a 1080p TV costs about what the GPi Case's screen does."""
    from PIL import Image
    import numpy as np
    w, h, xo, yo, bpp, fields, stride = geo
    bp = bpp // 8
    step = max(1, w // max_w)
    if step == 1 and stride == w * bp and not xo and not yo:
        f.seek(0)
        raw, n = f.read(w * h * bp), h
    else:
        rows = []
        for y in range(0, h, step):
            f.seek((y + yo) * stride + xo * bp)
            rows.append(f.read(w * bp))
        raw, n = b"".join(rows), len(rows)
    px = np.frombuffer(raw, dtype="<u2" if bpp == 16 else "<u4")[:w * n].reshape(n, w)[:, ::step]
    rh, rw = px.shape
    rgb = np.zeros((rh, rw, 3), dtype=np.uint8)
    for c, (off, ln) in enumerate(fields):
        top = (1 << ln) - 1
        rgb[..., c] = ((px >> off) & top).astype(np.uint32) * 255 // top
    img = Image.fromarray(rgb, "RGB")
    if rw > max_w:
        img = img.resize((max_w, max(1, round(rh * max_w / rw))), Image.BILINEAR)
    return img


def grab_screen(max_w=640, dev="/dev/fb0"):
    """A picture of the screen right now, video and terminal included (for the web page)."""
    with open(dev, "rb", buffering=0) as f:
        return read_screen(f, fb_geometry(f), max_w)


class Framebuffer:
    """Draws a PIL image onto /dev/fb0 in whatever format it uses. The menus are drawn 640x480 on the
    GPi Case's screen. On a big one (1080p, 4K) they're drawn a little bigger, 960x540 on a 1080p
    monitor, and doubled (or more): crisp, quick, and room to spare. On anything else they're 480
    lines high and as wide as the screen's shape, scaled to fill it."""
    W, H = 640, 480
    TALLEST = 600                                     # ...the menus' height on a big screen, at most
    WIDEST = 1140                                     # (a 21:9 screen's, at 480 lines: wider, edges black)
    count = 0                                         # pictures shown, ever: the web page's cue

    def __init__(self, dev="/dev/fb0"):
        self.f = open(dev, "r+b", buffering=0)
        self.setup(*fb_geometry(self.f))

    @classmethod
    def whole_times(cls, w, h):
        """A big screen: how many times bigger it is than the menus, a whole number (2 for 1080p, 4 for
        4K), with the menus 480 to 600 lines high and at least 640 wide. None for anything smaller."""
        return next((k for k in (4, 3, 2) if cls.H <= h / k <= cls.TALLEST and w / k >= cls.W), None)

    def setup(self, w, h, xo, yo, bpp, fields, stride):
        if bpp not in (16, 32):
            raise OSError(f"unsupported framebuffer depth {bpp}")
        self.real_w, self.real_h, self.xo, self.yo = w, h, xo, yo
        self.bpp, self.fields, self.stride = bpp, fields, stride
        self.w, self.h = self.W, self.H               # what the menus are drawn at
        k = self.whole_times(w, h)
        if k:                                          # a big screen: crisp whole pixels, more room
            self.h = h // k
            self.w = min(w // k, self.WIDEST * self.h // self.H)
            self.tw, self.th = self.w * k, self.h * k
        elif w * self.H > h * self.W * 1.05:          # a wide screen (16:9, 16:10): menus its shape, filling it
            self.w = min(round(self.H * w / h), self.WIDEST)
            k = h / self.H
            self.tw, self.th = round(self.w * k), h
            if abs(self.tw - w) <= 3:
                self.tw = w                           # (to the pixel: a hair wider or narrower than its shape)
        else:
            k = min(w / self.W, h / self.H)
            if int(k) >= 1 and int(k) / k >= 0.85:   # 2x on a 1280x1024 monitor: crisp, and quick to draw
                k = int(k)
            self.tw, self.th = max(1, round(self.W * k)), max(1, round(self.H * k))
        self.ox, self.oy = (w - self.tw) // 2, (h - self.th) // 2
        self.same = (w, h) == (self.w, self.h)
        # 2x, 3x: plain pixel doubling stays crisp (and exactly: each pixel repeated)
        self.sharp = k == int(k) and (self.tw, self.th) == (self.w * int(k), self.h * int(k))
        # ...or nearly: still crisp, a column repeated once more. And a Pi Zero on a 1080p TV: its pixels
        # repeated as they come, as it can't smooth that many in good time
        self.blocky = abs(k - round(k)) < 0.01 or (self.tw * self.th > 1280 * 720 * 1.2 and slow_pi())
        # the usual 32-bit screen (KMS, any HDMI TV): PIL packs it itself, ten times quicker
        self.raw = "BGRX" if bpp == 32 and [tuple(f) for f in fields] == [(16, 8), (8, 8), (0, 8)] else None
        self.clear_next = not self.same and (self.tw, self.th) != (w, h)   # black edges first, if it has any
        self.last = None                              # the last menu picture, for the web page
        self.frames = type(self).count

    def pack(self, img):
        if img.mode != "RGB":
            img = img.convert("RGB")
        if getattr(self, "raw", None):
            return img.tobytes("raw", self.raw)
        import numpy as np
        if self.bpp == 16 and [tuple(f) for f in self.fields] == [(11, 5), (5, 6), (0, 5)]:
            a = np.asarray(img)                       # the usual 16-bit screen (the GPi Case's): RGB565,
            px = (a[..., 0] >> 3).astype("<u2") << 11  # four times quicker than below, the same bytes
            px |= (a[..., 1] >> 2).astype("<u2") << 5
            px |= a[..., 2] >> 3
            return px.tobytes()
        a = np.asarray(img, dtype=np.uint32)
        px = np.zeros(a.shape[:2], dtype=np.uint32)
        for c, (off, ln) in enumerate(self.fields):
            px |= (a[..., c] >> (8 - ln)) << off
        return px.astype("<u2" if self.bpp == 16 else "<u4").tobytes()

    def memory(self):
        """A big screen's pixels, mapped (rows of the stride): copying a picture into them is quicker than
        writing it out row by row, and a doubled one needn't be made first. None on the GPi Case's
        screen (it writes its own way, as ever), or if the screen can't be mapped."""
        if getattr(self, "mem", False) is False:      # (not tried yet)
            self.mem = None
            if not self.same:
                try:
                    import mmap
                    import numpy as np
                    rows, bp = self.yo + self.real_h, self.bpp // 8
                    self.mapping = mmap.mmap(self.f.fileno(), rows * self.stride)
                    self.mem = np.frombuffer(self.mapping, dtype="<u2" if bp == 2 else "<u4").reshape(
                        rows, self.stride // bp)[self.yo:, self.xo:self.xo + self.real_w]
                except (OSError, ValueError, ImportError, AttributeError, TypeError):
                    self.mem = None
        return self.mem

    def put(self, data, x, y, w, h):
        """Bytes for a w x h block, written at x, y on the real screen."""
        bp = self.bpp // 8
        row = w * bp
        mem = self.memory()
        if mem is not None:
            import numpy as np
            mem[y:y + h, x:x + w] = np.frombuffer(data, dtype=mem.dtype).reshape(h, w)
            return
        if x == 0 and y == 0 and w == self.real_w and self.stride == row and not self.xo and not self.yo:
            self.f.seek(0)
            self.f.write(data)
            return
        for r in range(h):
            self.f.seek((y + r + self.yo) * self.stride + (x + self.xo) * bp)
            self.f.write(data[r * row:(r + 1) * row])

    def show(self, img):
        self.last = img
        type(self).count += 1
        self.frames = type(self).count
        if self.same:
            self.put(self.pack(img), 0, 0, self.real_w, self.real_h)
            return
        from PIL import Image
        if self.clear_next:
            self.clear_next = False
            self.put(bytes(self.real_w * self.real_h * self.bpp // 8), 0, 0, self.real_w, self.real_h)
        if self.sharp and img.size == (self.w, self.h):    # pack it, then repeat each pixel: the quickest
            self.put_repeated(self.pack(img), 0, 0, self.w, self.h)
            return
        blocky = getattr(self, "blocky", self.sharp)
        data = self.pack(img.resize((self.tw, self.th), Image.NEAREST if blocky else Image.BILINEAR))
        self.put(data, self.ox, self.oy, self.tw, self.th)

    def put_repeated(self, packed, x, y, w, h):
        """Packed pixels (w x h of them, from x, y in the menus), each repeated k times both ways (2x, 3x,
        4x) onto the screen: straight into its memory if it's mapped, the bigger copy never made."""
        import numpy as np
        k = self.tw // self.w
        a = np.frombuffer(packed, dtype="<u2" if self.bpp == 16 else "<u4").reshape(h, 1, w, 1)
        x0, y0 = self.ox + x * k, self.oy + y * k
        mem = self.memory()
        if mem is not None:
            block = mem[y0:y0 + h * k, x0:x0 + w * k]
            block.shape = (h, k, w, k)                 # (a view of it, never a copy: an error otherwise)
            block[...] = a
            return
        self.put(np.broadcast_to(a, (h, k, w, k)).tobytes(), x0, y0, w * k, h * k)

    def show_part(self, img, box):
        """Only box (x0, y0, x1, y1) has changed since the last picture: just that goes to the screen
        (the Bot at work moves ten times a second on a Pi Zero), scaled as the whole picture is (the
        same pixels: a big screen's frames cost about what its box does). The whole picture is kept,
        for the web page."""
        if self.clear_next or self.last is None or img.size != (self.w, self.h):
            return self.show(img)
        self.last = img
        type(self).count += 1
        self.frames = type(self).count
        x0, y0, x1, y1 = (int(v) for v in box)
        if self.same:
            self.put(self.pack(img.crop((x0, y0, x1, y1))), x0, y0, x1 - x0, y1 - y0)
            return
        if self.sharp:                                 # each pixel repeated: just the box's
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(self.w, x1), min(self.h, y1)
            if x1 > x0 and y1 > y0:
                self.put_repeated(self.pack(img.crop((x0, y0, x1, y1))), x0, y0, x1 - x0, y1 - y0)
            return
        from PIL import Image
        kx, ky = self.tw / self.w, self.th / self.h
        x0, y0, x1, y1 = x0 - 1, y0 - 1, x1 + 1, y1 + 1     # (smoothing reaches a pixel past the box)
        tx0, ty0 = max(0, math.floor(x0 * kx)), max(0, math.floor(y0 * ky))
        tx1, ty1 = min(self.tw, math.ceil(x1 * kx)), min(self.th, math.ceil(y1 * ky))
        if tx1 <= tx0 or ty1 <= ty0:
            return
        blocky = getattr(self, "blocky", self.sharp)
        part = img.resize((tx1 - tx0, ty1 - ty0), Image.NEAREST if blocky else Image.BILINEAR,
                          box=(tx0 / kx, ty0 / ky, tx1 / kx, ty1 / ky))
        self.put(self.pack(part), self.ox + tx0, self.oy + ty0, tx1 - tx0, ty1 - ty0)

    def invalidate(self):
        """Something else drew on the screen (a video): blacken the edges again next time."""
        self.clear_next = not self.same and (self.tw, self.th) != (self.real_w, self.real_h)

    def blank_outside(self, box):
        """Black everywhere but the box (x0, y0, x1, y1), in real screen pixels: the bars round
        a video that doesn't fill the screen. mplayer only ever draws its picture."""
        bp = self.bpp // 8
        x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
        x1, y1 = min(self.real_w, int(box[2])), min(self.real_h, int(box[3]))
        row = bytes(self.real_w * bp)
        for y in range(self.real_h):
            at = (y + self.yo) * self.stride + self.xo * bp
            if y < y0 or y >= y1:
                self.f.seek(at)
                self.f.write(row)
                continue
            if x0 > 0:
                self.f.seek(at)
                self.f.write(row[:x0 * bp])
            if x1 < self.real_w:
                self.f.seek(at + x1 * bp)
                self.f.write(row[:(self.real_w - x1) * bp])

    def close(self):
        self.mem, mapping, self.mapping = None, getattr(self, "mapping", None), None
        if mapping is not None:
            try:
                mapping.close()
            except (BufferError, ValueError):
                pass                                   # (a picture of it still about: let it go by itself)
        self.f.close()
