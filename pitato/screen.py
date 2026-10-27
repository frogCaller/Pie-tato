"""Any screen, any sound output: the screen's size and the framebuffer media mode draws on, the
sound cards (and Bluetooth headphones and speakers), the video size to ask for, and the size an HDMI screen starts
at. And a screen on its side or upside down (Settings > Rotate screen: one that's taller than it's wide, turned to
lie wide, or one mounted the other way round): everything here draws on it turned, a quarter or half turn, and looks
at it turned back."""
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


# ---- a screen on its side (Settings > Rotate screen) -------------------------------------------------------
TURNS = (0, 90, 180, 270)      # degrees, clockwise: how the picture's turned for the screen
TURN = 0                       # ...now (set_turn)
FBCON_ROTATE = "/sys/class/graphics/fbcon/rotate_all"   # the terminal's turn: 0 to 3, a quarter turn each
TERMINAL_TURNED = False        # ...and whether it's been turned here (then Off turns it back; else it's left be)


def set_turn(degrees):
    """The picture turned this many degrees clockwise from now on (0, 90, 180 or 270), for everything here that
    draws on the screen or looks at it (a framebuffer opened afresh, a game or video started afresh)."""
    global TURN
    TURN = degrees if degrees in TURNS else 0


def screen_turn():
    """How the picture's turned now (degrees, clockwise)."""
    return TURN


def turned(w, h, turn=None):
    """A screen's size as it's seen: (w, h), or (h, w) a quarter turn round."""
    return (h, w) if (TURN if turn is None else turn) in (90, 270) else (w, h)


def turn_block(turn, dev_w, dev_h, x, y, w, h):
    """A w x h block at x, y on the screen as it's seen: where it is in the screen's own pixels (x, y, w, h), on
    a screen dev_w x dev_h of them."""
    if turn == 90:
        return dev_w - (y + h), x, h, w
    if turn == 180:
        return dev_w - (x + w), dev_h - (y + h), w, h
    if turn == 270:
        return y, dev_h - (x + w), h, w
    return x, y, w, h


def turn_pixels(a, turn):
    """Rows of pixels (a numpy array) as they're seen, as the screen's own: turned that far clockwise (a view)."""
    import numpy as np
    if turn == 90:
        return np.rot90(a, -1)
    if turn == 180:
        return a[::-1, ::-1]
    if turn == 270:
        return np.rot90(a, 1)
    return a


def unturn_pixels(a, turn):
    """The screen's own pixels as they're seen: turned back."""
    return turn_pixels(a, (360 - turn) % 360)


def unturn_image(img, turn):
    """A picture of the screen's own pixels (PIL) as it's seen: turned back."""
    from PIL import Image
    how = {90: Image.ROTATE_90, 180: Image.ROTATE_180, 270: Image.ROTATE_270}.get(turn)
    return img.transpose(how) if how is not None else img


def set_terminal_turn(degrees, path=None):
    """The terminal (the kernel's text on the screen) turned too: True if it could be. Only a console in text mode
    takes it: the kernel passes over one in graphics mode, as media mode's is while the menus are up. So it's done as
    Pie-tato starts and when the setting changes (for the consoles in text mode then), and again whenever media
    mode's own console goes to text mode (terminal_turn_now: a Simulator program on it, or back to the terminal).
    The Pi's own messages as it starts up stay as they are."""
    global TERMINAL_TURNED
    try:
        with open(path or FBCON_ROTATE, "w") as f:
            f.write(str(TURNS.index(degrees) if degrees in TURNS else 0))
    except OSError:
        return False
    TERMINAL_TURNED = TERMINAL_TURNED or bool(degrees)
    return True


def terminal_turn_now():
    """The terminal turned as the screen is, now (a console just gone to text mode takes it): unless nothing here has
    ever turned it and the screen isn't turned (a turn of your own, fbcon=rotate on the kernel's line, stays)."""
    if TURN or TERMINAL_TURNED:
        set_terminal_turn(TURN)


# ---- any screen, any sound output ---------------------------------------------------
def pi_model():
    return read_file("/proc/device-tree/model").replace("\x00", "").strip()


def slow_pi():
    """Pi Zero, 1, 2 and 3: they play 480 lines smoothly, not much more."""
    m = pi_model()
    return ("Zero" in m or bool(re.search(r"Raspberry Pi [123]\b", m)) or "Raspberry Pi Model" in m
            or bool(re.search(r"Compute Module( 3)?( Plus)? Rev", m)))


def screen_size():
    """The screen's real size, as it's seen (turned, if it's on its side): 640x480 on the GPi Case, 1920x1080 on
    most TVs."""
    try:
        with open("/dev/fb0", "rb", buffering=0) as f:
            w, h = fb_geometry(f)[:2]
        if w and h:
            return turned(w, h)
    except (OSError, struct.error):
        pass
    m = re.match(r"(\d+),(\d+)", read_file("/sys/class/graphics/fb0/virtual_size"))
    return turned(int(m.group(1)), int(m.group(2))) if m else (640, 480)


def video_target():
    """(Plex's size, its bitrate in kbps, live TV's lines): sharper on a big screen when the
    Pi can keep up (a Pi 4 or 5 on a TV), the GPi Case's 480 lines otherwise."""
    w, h = screen_size()
    if w >= 1280 and h >= 720 and not slow_pi():
        return "1280x720", 4000, 720
    return PLEX_RESOLUTION, PLEX_BITRATE, PLEX_LIVE_HEIGHT


ASOUND = "/proc/asound"                         # the kernel's sound cards
NOT_SPEAKERS = re.compile(r"controller|gamepad|joystick|dualsense|dualshock", re.I)   # USB sound that isn't one
_usb_seen = {}                                 # card id -> name: each USB speaker seen (one unplugged is still known)
TV_FIRST = False                               # Auto: the TV before a USB speaker (a GPi Case 2 in its dock: the case's
                                               # own sound is USB, and the picture's on the TV)
_descs = {}                                    # card id -> the card's own name (what Settings > Sound once called it)


def can_play(num):
    """A sound card with something to play through (not only a microphone): its playback devices (pcm0p...).
    One the kernel doesn't show the insides of: yes."""
    pcms = [os.path.basename(p) for p in glob.glob(os.path.join(ASOUND, f"card{num}", "pcm*"))]
    return not pcms or any(p.endswith("p") for p in pcms)


def sound_list():
    """The sound outputs, in the kernel's order: [{"id", "name", "desc", "usb"}]. Only cards that can play (a USB
    microphone can't); "name" is Settings > Sound's ("HDMI 1", "Headphones", "USB speaker"...), "desc" the card's own,
    "usb" a USB speaker (or headphones, or a DAC: not a game controller's)."""
    out = []
    for line in read_file(os.path.join(ASOUND, "cards")).splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]:\s*(\S+)\s+-\s+(.+)", line)
        if not m or not can_play(m.group(1)):
            continue
        cid, driver, full = m.group(2), m.group(3), m.group(4).strip()
        desc = full[:24]
        usb = driver == "USB-Audio" and not NOT_SPEAKERS.search(full)
        hd = re.fullmatch(r"vc4hdmi(\d?)", cid)
        if hd:
            name = "HDMI" + (f" {int(hd.group(1)) + 1}" if hd.group(1) else "")
        elif cid == "Headphones" or "headphone" in desc.lower():
            name = "Headphones"
        elif usb:
            name = "USB speaker"
        else:
            name = desc
        out.append({"id": cid, "name": name, "desc": desc, "usb": usb})
    names = [c["name"] for c in out]
    for c in out:                                  # two of a name: each its own after it ("USB speaker: Jabra")
        if names.count(c["name"]) > 1 and c["desc"] != c["name"]:
            c["name"] = f"{c['name']}: {c['desc']}"
    seen = {}
    for c in out:                                  # (still two: numbered)
        seen[c["name"]] = seen.get(c["name"], 0) + 1
        if seen[c["name"]] > 1:
            c["name"] = f"{c['name']} {seen[c['name']]}"
        if c["usb"]:
            _usb_seen[c["id"]] = c["name"]
        else:
            _usb_seen.pop(c["id"], None)           # (its name now taken by something else)
        _descs[c["id"]] = c["desc"]
    return out


def sound_cards():
    """[(card id, name)] for the sound outputs: ("vc4hdmi0", "HDMI 1"), ("Headphones", ...)..."""
    return [(c["id"], c["name"]) for c in sound_list()]


def sound_moves(route):
    """A route the sound moves to and from while something plays: Bluetooth, or a USB speaker (plugged in or out)."""
    return route == "bluetooth" or route in _usb_seen


def usb_name(route):
    """A USB speaker's name, even once it's unplugged: "USB speaker"."""
    return _usb_seen.get(route, "USB speaker")


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


def edid_sound(edid):
    """From a screen's EDID: True when it can play sound (an HDMI screen that says it can, as the kernel reads
    it), False when it can't (a computer monitor without speakers, a screen on a DVI adapter), None when there's
    no telling (no EDID)."""
    if len(edid) < 128 or edid[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return None
    hdmi = audio = False
    for i in range(1, min(edid[126], len(edid) // 128 - 1) + 1):
        b = edid[128 * i:128 * (i + 1)]
        if b[0] != 0x02:                           # (only the CEA block says what a TV can do)
            continue
        audio = audio or bool(b[3] & 0x40)         # basic audio
        j = 4
        while j < min(b[2], 127):                  # its data blocks, up to where its picture timings start
            tag, n = b[j] >> 5, b[j] & 0x1F
            if tag == 1:                           # an audio block
                audio = True
            elif tag == 3 and n >= 3 and b[j + 1:j + 4] == b"\x03\x0c\x00":   # HDMI's own block (IEEE 00-0C-03)
                hdmi = True
            j += 1 + n
    return hdmi and audio


def hdmi_sound(port):
    """Whether the screen on an HDMI port (0, 1) can play sound, as it says: True, False, or None (it doesn't say)."""
    for path in sorted(glob.glob(os.path.join(DRM_DIR, f"card*-HDMI-A-{port + 1}", "edid"))):
        try:
            with open(path, "rb") as f:
                got = edid_sound(f.read(32768))
        except OSError:
            continue
        if got is not None:
            return got
    return None


def sound_card(choice):
    """The card for Settings > Sound (by its name, or by the card's own name it had before). Auto: a USB speaker
    while one's plugged in (the last, with two), else the TV on HDMI, else the Pi's usual output (None: the
    system's default); with the screen on HDMI saying it can't play sound (a monitor without speakers), the
    Pi's headphone jack. TV_FIRST (a GPi Case 2 in its dock): the TV, then a USB speaker (the case's own)."""
    cards = sound_cards()
    ids = [c for c, _ in cards]
    if choice and choice != "Auto":
        return next((c for c, n in cards if n == choice), None) or \
            next((c for c in ids if choice in (_descs.get(c), c)), None)
    usb = [c for c in ids if c in _usb_seen]        # (the USB speakers plugged in now)
    if usb and not TV_FIRST:
        return usb[-1]
    silent = False
    for port in hdmi_ports():
        cid = next((c for c in (f"vc4hdmi{port}", "vc4hdmi") if c in ids), None)
        if cid and hdmi_sound(port) is False:
            silent = True                              # (a screen without speakers: not there)
        elif cid:
            return cid
    if usb:
        return usb[-1]
    if silent and "Headphones" in ids:
        return "Headphones"
    return None


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
    """A route's name, as Settings > Sound has it: "HDMI", "Headphones", "USB speaker"..., "Bluetooth", or "the Pi"
    (its own)."""
    if route == "bluetooth":
        return "Bluetooth"
    if not route:
        return "the Pi"
    return next((n for c, n in sound_cards() if c == route), None) or _usb_seen.get(route) or "the Pi"


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


def read_screen(f, geo, max_w=640, turn=None):
    """What's on a framebuffer, as a picture at most max_w wide, as it's seen (turned back, if the screen's on its
    side: turn, or TURN). On a big screen only every few pixels are read, so a 1080p TV costs about what the GPi
    Case's screen does."""
    from PIL import Image
    import numpy as np
    turn = TURN if turn is None else turn
    w, h, xo, yo, bpp, fields, stride = geo
    bp = bpp // 8
    step = max(1, turned(w, h, turn)[0] // max_w)
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
    img = unturn_image(Image.fromarray(rgb, "RGB"), turn)
    if img.width > max_w:
        img = img.resize((max_w, max(1, round(img.height * max_w / img.width))), Image.BILINEAR)
    return img


def grab_screen(max_w=640, dev="/dev/fb0"):
    """A picture of the screen right now, video and terminal included (for the web page), as it's seen."""
    with open(dev, "rb", buffering=0) as f:
        return read_screen(f, fb_geometry(f), max_w)


class Framebuffer:
    """Draws a PIL image onto /dev/fb0 in whatever format it uses. The menus are drawn 640x480 on the
    GPi Case's screen. On a big one (1080p, 4K) they're drawn a little bigger, 960x540 on a 1080p
    monitor, and doubled (or more): crisp, quick, and room to spare. On anything else they're 480
    lines high and as wide as the screen's shape, scaled to fill it. A screen on its side (turn: degrees,
    clockwise; TURN's unless said) is all that, as it's seen: real_w and real_h are its size as it's seen, and
    each picture's turned as it goes onto the screen's own pixels (dev_w x dev_h)."""
    W, H = 640, 480
    TALLEST = 600                                     # ...the menus' height on a big screen, at most
    WIDEST = 1140                                     # (a 21:9 screen's, at 480 lines: wider, edges black)
    count = 0                                         # pictures shown, ever: the web page's cue

    def __init__(self, dev="/dev/fb0", turn=None):
        self.f = open(dev, "r+b", buffering=0)
        self.turn = TURN if turn is None else (turn if turn in TURNS else 0)
        self.setup(*fb_geometry(self.f))

    def turn_to(self, turn):
        """Turned another way, from the next picture on (the screen's black, to start)."""
        self.turn = turn if turn in TURNS else 0
        self.close_memory()
        self.setup(self.dev_w, self.dev_h, self.xo, self.yo, self.bpp, self.fields, self.stride)
        self.put_dev(bytes(self.dev_w * self.dev_h * self.bpp // 8), 0, 0, self.dev_w, self.dev_h)

    @classmethod
    def whole_times(cls, w, h):
        """A big screen: how many times bigger it is than the menus, a whole number (2 for 1080p, 4 for
        4K), with the menus 480 to 600 lines high and at least 640 wide. None for anything smaller."""
        return next((k for k in (4, 3, 2) if cls.H <= h / k <= cls.TALLEST and w / k >= cls.W), None)

    def setup(self, w, h, xo, yo, bpp, fields, stride):
        if bpp not in (16, 32):
            raise OSError(f"unsupported framebuffer depth {bpp}")
        self.turn = getattr(self, "turn", 0)
        self.dev_w, self.dev_h = w, h                 # the screen's own pixels
        w, h = turned(w, h, self.turn)                # ...and as it's seen: what the rest is worked out for
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
            if not self.same or self.turn:
                try:
                    import mmap
                    import numpy as np
                    rows, bp = self.yo + self.dev_h, self.bpp // 8
                    self.mapping = mmap.mmap(self.f.fileno(), rows * self.stride)
                    self.mem = np.frombuffer(self.mapping, dtype="<u2" if bp == 2 else "<u4").reshape(
                        rows, self.stride // bp)[self.yo:, self.xo:self.xo + self.dev_w]
                except (OSError, ValueError, ImportError, AttributeError, TypeError):
                    self.mem = None
        return self.mem

    def close_memory(self):
        self.mem, mapping, self.mapping = False, getattr(self, "mapping", None), None
        if mapping is not None:
            try:
                mapping.close()
            except (BufferError, ValueError):
                pass                                   # (a picture of it still about: let it go by itself)

    def put(self, data, x, y, w, h):
        """Bytes for a w x h block, written at x, y on the real screen (as it's seen: turned onto its own pixels
        if it's on its side)."""
        if not self.turn:
            return self.put_dev(data, x, y, w, h)
        import numpy as np
        a = np.frombuffer(data, dtype="<u2" if self.bpp == 16 else "<u4").reshape(h, w)
        bx, by, bw, bh = turn_block(self.turn, self.dev_w, self.dev_h, x, y, w, h)
        a = turn_pixels(a, self.turn)
        mem = self.memory()
        if mem is not None:
            mem[by:by + bh, bx:bx + bw] = a
            return
        self.put_dev(np.ascontiguousarray(a).tobytes(), bx, by, bw, bh)

    def put_dev(self, data, x, y, w, h):
        """Bytes for a w x h block, written at x, y on the screen's own pixels."""
        bp = self.bpp // 8
        row = w * bp
        mem = self.memory()
        if mem is not None:
            import numpy as np
            mem[y:y + h, x:x + w] = np.frombuffer(data, dtype=mem.dtype).reshape(h, w)
            return
        if x == 0 and y == 0 and w == self.dev_w and self.stride == row and not self.xo and not self.yo:
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
        if self.same and img.size == (self.real_w, self.real_h):   # (one of another size: scaled to it, below)
            self.put(self.pack(img), 0, 0, self.real_w, self.real_h)
            return
        from PIL import Image
        if self.clear_next:
            self.clear_next = False
            self.put_dev(bytes(self.dev_w * self.dev_h * self.bpp // 8), 0, 0, self.dev_w, self.dev_h)
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
        a = np.frombuffer(packed, dtype="<u2" if self.bpp == 16 else "<u4").reshape(h, w)
        x0, y0 = self.ox + x * k, self.oy + y * k
        x0, y0, bw, bh = turn_block(self.turn, self.dev_w, self.dev_h, x0, y0, w * k, h * k)
        a = turn_pixels(a, self.turn)                  # (turned while it's small: the screen's on its side)
        h, w = a.shape
        a = a.reshape(h, 1, w, 1)
        mem = self.memory()
        if mem is not None:
            block = mem[y0:y0 + bh, x0:x0 + bw]
            block.shape = (h, k, w, k)                 # (a view of it, never a copy: an error otherwise)
            block[...] = a
            return
        self.put_dev(np.broadcast_to(a, (h, k, w, k)).tobytes(), x0, y0, bw, bh)

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
        """Black everywhere but the box (x0, y0, x1, y1), in real screen pixels (as it's seen): the bars round
        a video that doesn't fill the screen. mplayer only ever draws its picture."""
        bp = self.bpp // 8
        x0, y0, bw, bh = turn_block(self.turn, self.dev_w, self.dev_h, int(box[0]), int(box[1]),
                                    int(box[2]) - int(box[0]), int(box[3]) - int(box[1]))
        x1, y1 = min(self.dev_w, x0 + bw), min(self.dev_h, y0 + bh)
        x0, y0 = max(0, x0), max(0, y0)
        row = bytes(self.dev_w * bp)
        for y in range(self.dev_h):
            at = (y + self.yo) * self.stride + self.xo * bp
            if y < y0 or y >= y1:
                self.f.seek(at)
                self.f.write(row)
                continue
            if x0 > 0:
                self.f.seek(at)
                self.f.write(row[:x0 * bp])
            if x1 < self.dev_w:
                self.f.seek(at + x1 * bp)
                self.f.write(row[:(self.dev_w - x1) * bp])

    def close(self):
        self.close_memory()
        self.mem = None
        self.f.close()
