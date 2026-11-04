"""The web page's copy of the screen, sharp on a computer: the page says how wide it shows it (in its own pixels); shown
big, it's sent as finely as the menus are drawn (a 1080p TV's: twice as finely, a JPEG), and where they aren't drawn
finely for the screen itself (the GPi Case 2's 640 x 480, on a CM4), they're drawn so while a page shows it big
(the screen gets them averaged back to its own pixels), and as before once no page has for a while. A phone's small
copy, and a Pi Zero (it can't draw that many pixels quickly): as before. Pictures saved, to look at."""
import io, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_webfine"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from PIL import Image
from pitato import fine as F, screen as SC
from pitato.screens import web as W

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


RGB32 = [(16, 8), (8, 8), (0, 8)]
RGB16 = [(11, 5), (5, 6), (0, 5)]
model = ["Raspberry Pi Compute Module 4 Rev 1.1"]
SC.pi_model = lambda: model[0]


def fake_fb(w, h, bpp, fields):
    path = f"{S}/fb_{w}x{h}_{bpp}"
    stride = w * bpp // 8
    open(path, "wb").write(b"\x00" * (stride * h))
    fb = object.__new__(g.Framebuffer)
    fb.f = open(path, "r+b", buffering=0)
    fb.turn = 0
    fb.setup(w, h, 0, 0, bpp, fields, stride)
    return fb, path


def screen_rgb(path, w, h, bpp):
    a = np.frombuffer(open(path, "rb").read(), dtype="<u2" if bpp == 16 else "<u4")[:w * h].reshape(h, w).astype(np.uint32)
    if bpp == 16:
        return np.stack([(a >> 11 & 31) << 3, (a >> 5 & 63) << 2, (a & 31) << 3], -1)
    return np.stack([a >> 16 & 255, a >> 8 & 255, a & 255], -1)


def media(w, h, bpp, fields, name):
    m = g.Media(); m.load_fonts()
    m.fb, path = fake_fb(w, h, bpp, fields)
    m.active = True
    m.fine_scale()
    m.view = "home"; m.home_sel = 0
    m.dirty = True; m.flush()
    return m, path


def shot(m, want):
    data, kind, n = m.web_shot(None, 0, want)
    im = Image.open(io.BytesIO(data))
    return kind, im.size, n, im


# ---- a CM4 in the GPi Case 2: its own 640 x 480 screen ---------------------------------------------------------------
m, path = media(640, 480, 16, RGB16, "cm4")
check(f"a CM4's own 640 x 480 screen: drawn as ever, one of its pixels to each ({m.fb.s}, {F.scale()})",
      m.fb.s == 1 and F.scale() == 1)
kind, size, n, plain = shot(m, 1240)
check(f"a page shows it 1240 wide: the menus as they are for now ({kind}, {size})", kind == "image/png"
      and size == (640, 480))
plain.save(S + "/cm4-plain.png")
m.tick()
check(f"...then drawn twice as finely, for the page ({F.scale()})", F.scale() == 2 and m.dirty)
m.flush()
kind, size, n, sharp = shot(m, 1240)
sharp.save(S + "/cm4-sharp.jpg")
check(f"...sent as finely as that, a JPEG ({kind}, {size})", kind == "image/jpeg" and size == (1280, 960))
scr = screen_rgb(path, 640, 480, 16)
want = np.asarray(m.fb.last.pic.convert("RGB").reduce(2)).astype(int)
diff = np.abs(scr.astype(int) - (want >> 3 << 3)).max()             # (16 bits a pixel: each colour's top bits)
check(f"...the screen itself: those pixels averaged back to its own (as near as 16 bits get: {diff})", diff <= 8)
Image.fromarray(scr.astype(np.uint8)).save(S + "/cm4-screen.png")
# (the screen the same picture as drawn plainly, near enough: the menus look as they did)
plain_rgb = np.asarray(plain.convert("RGB")).astype(int)
close = (np.abs(plain_rgb - scr.astype(int)).max(axis=2) <= 40).mean()
check(f"...and it looks as it did: {close:.1%} of its pixels as they were drawn plainly (the rest: edges, smoother)",
      close > 0.93)

# the same picture again: kept, not made again; a phone's smaller copy: the plain one
t = time.perf_counter()
again = m.web_shot(None, 0, 1240)
check(f"the same picture asked for again: the one made already ({(time.perf_counter() - t) * 1000:.1f} ms)",
      again[1] == "image/jpeg" and time.perf_counter() - t < 0.05)
kind, size, n, _ = shot(m, 700)
check(f"a phone showing it 700 wide: the menus' own size ({kind}, {size})", kind == "image/png" and size == (640, 480))

# not too often: two in a row at least WEB_FINE_GAP apart
m.dirty = True; m.flush()
t = time.monotonic()
shot(m, 1240)
m.dirty = True; m.flush()
shot(m, 1240)
gap = time.monotonic() - t
check(f"finely drawn pictures for the page: at most one every {W.WEB_FINE_GAP} s ({gap:.2f} s for two)",
      gap >= W.WEB_FINE_GAP - 0.01)

# the Bot's face, a frame at a time, drawn finely: the screen gets each (averaged), nothing amiss
m.set_setting("bot_mode", "chat")
m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
m.dirty = True; m.flush()
before = open(path, "rb").read()
for _ in range(3):
    m.face_step = True
    m.face_next = 0
    m.flush()
check("the Bot's face, frame by frame, drawn finely: on the screen as ever", F.detail(m.fb.last) == 2
      and len(open(path, "rb").read()) == len(before))

# no page for a while: drawn as ever again
m.web_want = (1240, time.monotonic() - W.WEB_FINE_FOR - 1)
m.fine_look = 0
m.tick()
m.flush()
kind, size, n, _ = shot(m, 0)
check(f"no page showing it big for {W.WEB_FINE_FOR:.0f} s: drawn as ever again ({F.scale()}, {kind}, {size})",
      F.scale() == 1 and kind == "image/png" and size == (640, 480))

# ---- a Pi Zero 2 W in the GPi Case 2W: it can't draw that many pixels quickly --------------------------------------
model[0] = "Raspberry Pi Zero 2 W Rev 1.0"
mz, pathz = media(640, 480, 16, RGB16, "zero")
shot(mz, 1240)
mz.fine_look = 0
mz.tick()
mz.flush()
kind, size, n, _ = shot(mz, 1240)
check(f"a Pi Zero, a page showing it big: as ever ({F.scale()}, {kind}, {size})", F.scale() == 1
      and kind == "image/png" and size == (640, 480))

# ---- a Pi 4 on a 1080p TV: drawn finely already, for the TV ------------------------------------------------------------
model[0] = "Raspberry Pi 4 Model B Rev 1.4"
mt, patht = media(1920, 1080, 32, RGB32, "tv")
check(f"a Pi 4 on a 1080p TV: the menus {mt.fb.w} x {mt.fb.h}, drawn twice as finely for it ({F.scale()})",
      (mt.fb.w, mt.fb.h) == (960, 540) and F.scale() == 2)
kind, size, n, tv = shot(mt, 1240)
tv.save(S + "/tv-sharp.jpg")
check(f"a page showing it 1240 wide: as finely as it's drawn, a JPEG ({kind}, {size})", kind == "image/jpeg"
      and size == (1920, 1080))
kind, size, n, _ = shot(mt, 900)
check(f"...900 wide (a phone's): the menus' own size, as ever ({kind}, {size})", kind == "image/png" and size == (960, 540))
mt.fine_look = 0
mt.tick()
check(f"...still drawn as finely as the TV wants, no more ({F.scale()})", F.scale() == 2)

# a page that says nothing of its size (an older one): as ever
kind, size, n, _ = shot(mt, None)
check(f"a page that doesn't say how big it shows it: as ever ({kind}, {size})", kind == "image/png" and size == (960, 540))
check("nonsense for its size: as if it didn't say", mt.web_wants("lots") == 0 and mt.web_wants(-5) == 0
      and mt.web_wants(1e12) == 16384)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
