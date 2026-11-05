"""Any screen size, any sound output: the framebuffer scaling, pictures of the screen,
sound cards, the video tier and mplayer's arguments."""
import io, os, sys, time, shutil
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
from PIL import Image, ImageDraw

S = SP + "/t31"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what)


RGB32 = [(16, 8), (8, 8), (0, 8)]
RGB16 = [(11, 5), (5, 6), (0, 5)]


def fake_fb(w, h, bpp, fields, stride=None, xo=0, yo=0, vh=None):
    path = f"{S}/fb_{w}x{h}_{bpp}"
    stride = stride or w * bpp // 8
    open(path, "wb").write(b"\x77" * (stride * (vh or h)))
    fb = object.__new__(g.Framebuffer)
    fb.f = open(path, "r+b", buffering=0)
    fb.setup(w, h, xo, yo, bpp, fields, stride)
    return fb, path


def pixels(path, w, h, bpp, stride=None):
    stride = stride or w * bpp // 8
    raw = open(path, "rb").read()
    a = np.frombuffer(raw, dtype="<u2" if bpp == 16 else "<u4")
    return a[:stride * h // (bpp // 8)].reshape(h, stride // (bpp // 8))[:, :w]


menu = Image.new("RGB", (640, 480), (40, 120, 200))
d = ImageDraw.Draw(menu)
d.rectangle((0, 0, 639, 9), fill=(255, 0, 0))          # a red line along the top
d.rectangle((630, 470, 639, 479), fill=(0, 255, 0))    # a green corner

# 1) the GPi Case: 640x480 16 bit, unchanged path
fb, path = fake_fb(640, 480, 16, RGB16)
fb.show(menu)
px = pixels(path, 640, 480, 16)
check("640x480: no scaling, top-left red", fb.same and px[0, 0] == (31 << 11) and px[200, 200] == ((40 >> 3) << 11 | (120 >> 2) << 5 | (200 >> 3)))
check("frames count up across screens", fb.frames == g.Framebuffer.count and fb.last is menu)
check("...and the GPi Case's screen written as ever, not mapped", fb.memory() is None)

def menu_of(w, h=480):
    """A menu picture as wide as the screen's shape: blue, a red line along the top, a green corner."""
    im = Image.new("RGB", (w, h), (40, 120, 200))
    dd = ImageDraw.Draw(im)
    dd.rectangle((0, 0, w - 1, 9), fill=(255, 0, 0))
    dd.rectangle((w - 10, h - 10, w - 1, h - 1), fill=(0, 255, 0))
    return im


BLUE32 = 40 << 16 | 120 << 8 | 200
# 2) a 1080p TV or monitor, 32 bit: the menus 960x540, doubled: filling it, crisp, no black sides
fb, path = fake_fb(1920, 1080, 32, RGB32)
check(f"1080p: menus 960x540, doubled to fill the screen ({fb.w}x{fb.h} -> {fb.tw}x{fb.th} at {fb.ox}, {fb.oy})",
      (fb.w, fb.h) == (960, 540) and (fb.tw, fb.th, fb.ox, fb.oy) == (1920, 1080, 0, 0) and fb.sharp
      and fb.raw == "BGRX" and not fb.same)
wide = menu_of(960, 540)
check("1080p: drawn straight into the screen's mapped memory", fb.memory() is not None)
t = time.time(); fb.show(wide); dt = time.time() - t
px = pixels(path, 1920, 1080, 32)
check(f"1080p: blue right to the edges ({dt * 1000:.0f} ms a picture)", px[540, 0] == BLUE32 and px[540, 1919] == BLUE32
      and px[1079, 960] == BLUE32)
check("1080p: red top line along the very top, 20 rows", px[0, 960] == 0xff0000 and px[19, 960] == 0xff0000
      and px[20, 960] != 0xff0000 and px[0, 0] == 0xff0000 and px[0, 1919] == 0xff0000)
check("1080p: green corner a 20 px block in the bottom right corner", px[1079, 1919] == 0x00ff00
      and px[1060, 1900] == 0x00ff00 and px[1059, 1899] != 0x00ff00)
# a video drew over it, then the menus come back: nothing left of it
open(path, "r+b").write(b"\x55" * (1920 * 4 * 10))
fb.invalidate(); fb.show(wide)
px = pixels(path, 1920, 1080, 32)
check("after a video: the menus cover it all again", (px[:10] == 0xff0000).all())
fb.blank_outside(g.fit_box((1280, 720), 1920, 1080))
px = pixels(path, 1920, 1080, 32)
check("16:9 video on a 16:9 TV: nothing to blank but the 2 px inset", px[540, 960] != 0 and px[0, 960] == 0)

# 2b) 4K: the same 960x540, 4x
fb4, path4 = fake_fb(3840, 2160, 32, RGB32)
check(f"4K: 960x540, 4x, to the edges ({fb4.tw}x{fb4.th} at {fb4.ox}, {fb4.oy})",
      (fb4.w, fb4.h, fb4.tw, fb4.th, fb4.ox, fb4.oy) == (960, 540, 3840, 2160, 0, 0) and fb4.sharp)
fb4.show(menu_of(960, 540))
px = pixels(path4, 3840, 2160, 32)
check("4K: green corner a 40 px block", px[2159, 3839] == 0x00ff00 and px[2120, 3800] == 0x00ff00 and px[2119, 3799] != 0x00ff00)
# 2c) 1080p at 16 bits: packed, then each pixel repeated
fb16, path16 = fake_fb(1920, 1080, 16, RGB16)
fb16.show(wide)
px = pixels(path16, 1920, 1080, 16)
BLUE16 = (40 >> 3) << 11 | (120 >> 2) << 5 | (200 >> 3)
check("1080p 16 bit: filled, red top, blue to the sides", fb16.raw is None and px[2, 960] == (31 << 11)
      and px[540, 0] == BLUE16 and px[540, 1919] == BLUE16)
# 2d) 16:10, 21:9, wider still, a 5:4 monitor, and smaller screens (480 lines, scaled to fill)
for (rw, rh), (w, h, tw, th, ox, sharp) in {(1920, 1200): (960, 600, 1920, 1200, 0, True),
                                           (1680, 1050): (840, 525, 1680, 1050, 0, True),
                                           (2560, 1080): (1280, 540, 2560, 1080, 0, True),
                                           (2560, 1440): (853, 480, 2559, 1440, 0, True),
                                           (3440, 1440): (1140, 480, 3420, 1440, 10, True),
                                           (5120, 1440): (1140, 480, 3420, 1440, 850, True),
                                           (1280, 1024): (640, 512, 1280, 1024, 0, True),
                                           (1600, 1200): (800, 600, 1600, 1200, 0, True),
                                           (1366, 768): (854, 480, 1366, 768, 0, False),
                                           (1600, 900): (853, 480, 1600, 900, 0, False),
                                           (1024, 600): (819, 480, 1024, 600, 0, False)}.items():
    f, _ = fake_fb(rw, rh, 32, RGB32)
    check(f"{rw}x{rh}: menus {f.w}x{f.h}, {f.tw}x{f.th} at {f.ox}, {f.oy}{', whole pixels' if f.sharp else ''}",
          (f.w, f.h, f.tw, f.th, f.ox, f.oy) == (w, h, tw, th, ox, 0) and bool(f.sharp) == sharp)
f, p54 = fake_fb(1080, 1920, 32, RGB32)
check(f"a screen on its side (1080x1920): as before, 640x480 across it ({f.w}x{f.h} -> {f.tw}x{f.th} at {f.ox}, {f.oy})",
      (f.w, f.h) == (640, 480) and f.tw == 1080)
# 2e) 3x on a 21:9 1440p: crisp, shown to the pixel, 10 px black each side
fb3, path3 = fake_fb(3440, 1440, 32, RGB32)
fb3.show(menu_of(1140))
px = pixels(path3, 3440, 1440, 32)
check("3440x1440: 1140 wide at 3x, 10 px each side, green corner 30 px", px[:, :10].max() == 0 and px[:, 3430:].max() == 0
      and px[1439, 3429] == 0x00ff00 and px[1410, 3400] == 0x00ff00 and px[1409, 3399] != 0x00ff00)
# 3) 720p, stride with padding, 16 bit: 853x480 at 1.5x, filling it
fb, path = fake_fb(1280, 720, 16, RGB16, stride=1280 * 2 + 64)
fb.show(menu_of(fb.w))
px = pixels(path, 1280, 720, 16, stride=1280 * 2 + 64)
check(f"720p padded rows: 853 wide, filled to the edges ({fb.w}, {fb.tw}x{fb.th})", fb.w == 853
      and (fb.tw, fb.th, fb.ox) == (1280, 720, 0) and px[360, 1] == BLUE16 and px[360, 1278] == BLUE16 and not fb.sharp)
# 4) 1280x960: exactly 2x, crisp (4:3: as before)
fb, path = fake_fb(1280, 960, 32, RGB32)
check("1280x960: 2x pixel doubling", fb.sharp and (fb.tw, fb.th) == (1280, 960) and fb.w == 640)
fb.show(menu)
px = pixels(path, 1280, 960, 32)
check("2x: green corner is a 20 px block", px[940, 1260] == 0x00ff00 and px[939, 1259] != 0x00ff00)
# 4b) 1024x768, 800x600: 4:3, filled as before
for rw, rh in ((1024, 768), (800, 600)):
    f, _ = fake_fb(rw, rh, 32, RGB32)
    check(f"{rw}x{rh}: 640x480 filling it", (f.w, f.tw, f.th, f.ox, f.oy) == (640, rw, rh, 0, 0))

# 4c) only part of the picture changed (Apps, the Bot at work): just that part goes to a big
# screen, scaled exactly as the whole picture would be
import random
rnd = random.Random(5)
for (rw, rh, bpp, fields, stride) in ((1920, 1080, 32, RGB32, None), (1280, 720, 16, RGB16, 1280 * 2 + 64),
                                      (1280, 960, 16, RGB16, None), (1280, 960, 32, RGB32, None),
                                      (3440, 1440, 32, RGB32, None), (640, 480, 16, RGB16, None)):
    fa, pa = fake_fb(rw, rh, bpp, fields, stride=stride)
    fb_, pb = fake_fb(rw, rh, bpp, fields, stride=stride)
    one = menu_of(fa.w, fa.h)
    dd = ImageDraw.Draw(one)
    for _ in range(40):                                 # (something to scale: edges, colours)
        x, y = rnd.randrange(fa.w), rnd.randrange(fa.h)
        dd.ellipse((x, y, x + rnd.randrange(4, 60), y + rnd.randrange(4, 60)), fill=tuple(rnd.randrange(256) for _ in range(3)))
    two = one.copy()
    box = (101, 69, 549, 384)
    ImageDraw.Draw(two).rectangle((150, 120, 400, 300), fill=(250, 200, 30))
    ImageDraw.Draw(two).text((200, 200), "Typing", fill=(0, 0, 0))
    fa.show(one)
    t = time.time(); fa.show_part(two, box); dt_part = time.time() - t
    counted = fa.frames == g.Framebuffer.count
    t = time.time(); fb_.show(two); dt_whole = time.time() - t
    a = pixels(pa, rw, rh, bpp, stride=stride).astype("int64")
    b = pixels(pb, rw, rh, bpp, stride=stride).astype("int64")
    if bpp == 32:
        diff = max(abs(((a >> sh) & 255) - ((b >> sh) & 255)).max() for sh in (0, 8, 16))
    else:
        diff = max(abs(((a >> sh) & m) - ((b >> sh) & m)).max() for sh, m in ((0, 31), (5, 63), (11, 31)))
    check(f"{rw}x{rh} {bpp} bit: part of it, the same as the whole ({diff} off at most; {dt_part * 1000:.0f} ms "
          f"for the part, {dt_whole * 1000:.0f} ms the whole)", diff <= 1 and fa.last is two and counted)

# 5) pictures of the screen for the web page
fb, path = fake_fb(1920, 1080, 32, RGB32)
fb.show(wide)
with open(path, "rb") as f:
    t = time.time(); img = g.read_screen(f, (1920, 1080, 0, 0, 32, RGB32, 7680), 640); dt = time.time() - t
check(f"1080p screen picture: 640x360, red top, blue to the sides ({dt * 1000:.0f} ms)",
      img.size == (640, 360) and img.getpixel((320, 2)) == (255, 0, 0) and img.getpixel((1, 180)) == (40, 120, 200))
fb, path = fake_fb(640, 480, 16, RGB16)
fb.show(menu)
with open(path, "rb") as f:
    img = g.read_screen(f, (640, 480, 0, 0, 16, RGB16, 1280), 640)
check("GPi screen picture: 640x480, colours back", img.size == (640, 480) and img.getpixel((0, 0)) == (255, 0, 0)
      and img.getpixel((635, 475)) == (0, 255, 0))
fb, path = fake_fb(1280, 720, 16, RGB16, stride=1280 * 2 + 64)
fb.show(menu_of(fb.w))
with open(path, "rb") as f:
    img = g.read_screen(f, (1280, 720, 0, 0, 16, RGB16, 1280 * 2 + 64), 640)
check("padded 720p picture: 640x360", img.size == (640, 360) and img.getpixel((320, 2))[0] > 240)

# 6) sound outputs
CARDS_PI4 = """ 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 1 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 2 [vc4hdmi1       ]: vc4-hdmi - vc4-hdmi-1
                      vc4-hdmi-1
 3 [Device         ]: USB-Audio - USB Audio Device
                      GeneralPlus USB Audio Device at usb-0000:01:00.0-1.3, full speed
"""
files = {"/proc/asound/cards": CARDS_PI4}
real_read = g.read_file
g.read_file = lambda p, *a, **k: files.get(p, "") if p.startswith(("/proc/asound", "/sys/class/drm", "/proc/device-tree")) else real_read(p, *a, **k)
drm = {}
g.glob.glob = (lambda real: lambda pat, *a, **k: sorted(drm) if pat.startswith("/sys/class/drm") else real(pat, *a, **k))(g.glob.glob)
check("cards named", g.sound_cards() == [("Headphones", "Headphones"), ("vc4hdmi0", "HDMI 1"), ("vc4hdmi1", "HDMI 2"),
                                         ("Device", "USB speaker")])
check("Auto, a USB speaker plugged in: the speaker", g.sound_device("Auto") == "alsa:device=default=Device,alsa")
check("chosen USB card, by its name or the card's own (a choice saved before)",
      g.sound_device("USB speaker") == "alsa:device=default=Device,alsa"
      and g.sound_device("USB Audio Device") == "alsa:device=default=Device,alsa")
files["/proc/asound/cards"] = CARDS_PI4.split(" 3 [Device")[0]
check("Auto, no TV: plain alsa", g.sound_device("Auto") == "alsa")
for k in ("/sys/class/drm/card1-HDMI-A-1/status", "/sys/class/drm/card1-HDMI-A-2/status"):
    drm[k] = None
files["/sys/class/drm/card1-HDMI-A-1/status"] = "disconnected\n"
files["/sys/class/drm/card1-HDMI-A-2/status"] = "connected\n"
check("Auto, TV on the second HDMI port: vc4hdmi1 (straight to its IEC958 encoder)",
      g.sound_device("Auto") == "alsa:device=hdmi=vc4hdmi1.0.4.130.0.1,alsa")
check("chosen card gone: plain alsa", g.sound_device("HDMI 3") == "alsa")
files["/proc/asound/cards"] = """ 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi
"""
files["/sys/class/drm/card1-HDMI-A-1/status"] = "connected\n"
check("Zero 2 / Pi 3 with a TV: vc4hdmi", g.sound_device("Auto") == "alsa:device=hdmi=vc4hdmi.0.4.130.0.1,alsa"
      and ("vc4hdmi", "HDMI") in g.sound_cards())

# 7) the video tier
sizes = {"v": (640, 480)}
g.screen_size = lambda: sizes["v"]
files["/proc/device-tree/model"] = "Raspberry Pi Zero 2 W Rev 1.0\x00"
check("Zero 2 W on the GPi: 480 lines", g.video_target() == (g.PLEX_RESOLUTION, g.PLEX_BITRATE, g.PLEX_LIVE_HEIGHT))
sizes["v"] = (1920, 1080)
check("Zero 2 W on a TV: still 480 lines (it can't decode more smoothly)", g.video_target()[2] == g.PLEX_LIVE_HEIGHT)
files["/proc/device-tree/model"] = "Raspberry Pi 4 Model B Rev 1.5\x00"
check("Pi 4 on a TV: 720p", g.video_target() == ("1280x720", 4000, 720))
files["/proc/device-tree/model"] = "Raspberry Pi 5 Model B Rev 1.0\x00"
check("Pi 5 on a TV: 720p", g.video_target()[2] == 720)
files["/proc/device-tree/model"] = "Raspberry Pi 3 Model B Plus Rev 1.3\x00"
check("Pi 3 B+ on a TV: 480", g.video_target()[2] == g.PLEX_LIVE_HEIGHT)
files["/proc/device-tree/model"] = "Raspberry Pi Model B Rev 2\x00"
check("Pi 1: 480", g.video_target()[2] == g.PLEX_LIVE_HEIGHT)

# 8) mplayer's arguments through the real spawn
popen = []


class P:
    def __init__(self, args, **k):
        popen.append(args); self.stdin = io.StringIO(); self.stdout = io.StringIO(""); self.pid = 1

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    def terminate(self):
        pass


g.subprocess.Popen = P
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    last = None
    inval = 0

    def show(self, img): FB.last = img

    def invalidate(self): FB.inval += 1

    def blank_outside(self, box): pass

    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
open(S + "/home/u/clip.mp4", "wb").write(b"x")
clip = g.item(S + "/home/u/clip.mp4", "clip", "video", S + "/home/u/clip.mp4")
m.play([clip], 0)
args = popen[-1]
check("video: -ao is the TV's HDMI", args[args.index("-ao") + 1] == "alsa:device=hdmi=vc4hdmi.0.4.130.0.1,alsa")
check("video: Fit on 1080p with dsize", "dsize=1920:1080:0,scale=0:0" in args)
check("the menus' edges get blacked after", FB.inval == 1)
m.set_setting("sound", "Headphones")
m.play([clip], 0)
args = popen[-1]
check("Settings > Sound: Headphones", args[args.index("-ao") + 1] == "alsa:device=default=Headphones,alsa")
m.set_setting("screen", "Full screen"); m.vsize = None
m.play([clip], 0)
args = popen[-1]
check("Full screen, size unknown: cover and crop", "dsize=1920:1080:1,scale=0:0,crop=1920:1080" in args)
rows = m.settings_rows()
check("Sound row choices", [r for r in rows if r[0] == "sound"][0][2] == ["Auto", "Headphones", "HDMI"])
check("Controller row", any(r[0] == "pad" for r in rows))
FB.real_w, FB.real_h = 640, 480
m.set_setting("screen", "Fit")
m.play([clip], 0)
args = popen[-1]
check("GPi screen: the old Fit (-zoom -xy 640)", "-zoom" in args and "-xy" in args and "dsize" not in " ".join(args))
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
