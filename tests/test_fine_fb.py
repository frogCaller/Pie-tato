"""The menus drawn finely (fine.py) on the real Framebuffer, written to a stand-in screen (a file): how finely each
screen gets them (a 4K TV: 2, each of those pixels shown 2 x 2; a 1080p one: 2, each its own; 1440p: 3 on a Pi 5 or a
PC, 1 on a Pi 4; a Pi Zero, a 720p TV, the GPi Case: 1, as ever; PITATO_FINE to say otherwise), the fine picture's
own pixels reaching the screen (a detail only it has, there), the whole picture and just a box of it, 16 and 32
bits, a screen on its side, a plain picture still shown as ever, and the web page's copy at the menus' size."""
import io, os, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from PIL import Image
from pitato import fine as F, screen as SC

S = SP + "/tfinefb"
os.makedirs(S, exist_ok=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


RGB32 = [(16, 8), (8, 8), (0, 8)]
RGB16 = [(11, 5), (5, 6), (0, 5)]
model = ["Raspberry Pi 5 Model B Rev 1.0"]
SC.pi_model = lambda: model[0]


def fake_fb(w, h, bpp, fields, turn=0):
    path = f"{S}/fb_{w}x{h}_{bpp}_{turn}"
    stride = w * bpp // 8
    open(path, "wb").write(b"\x00" * (stride * h))
    fb = object.__new__(g.Framebuffer)
    fb.f = open(path, "r+b", buffering=0)
    fb.turn = turn
    fb.setup(w, h, 0, 0, bpp, fields, stride)
    return fb, path


def pixels(path, w, h, bpp):
    a = np.frombuffer(open(path, "rb").read(), dtype="<u2" if bpp == 16 else "<u4")
    return a[:w * h].reshape(h, w)


def menu(fb, colour=(40, 120, 200)):
    """The menus, drawn as finely as the screen takes: blue, a red line along the top (one of the menus' pixels),
    and a checker of the picture's own pixels in a corner (a detail only a fine picture has)."""
    F.set_scale(fb.s)
    im = F.Image.new("RGB", (fb.w, fb.h), colour)
    d = F.ImageDraw.Draw(im)
    d.rectangle((0, 0, fb.w - 1, 0), fill=(255, 0, 0))
    if F.detail(im) > 1:
        a = np.zeros((40, 40, 3), np.uint8)
        a[::2, ::2] = (255, 255, 255)
        a[1::2, 1::2] = (255, 255, 255)
        im.pic.paste(Image.fromarray(a), (40, 40))
    return im


WHITE, BLACK, RED, BLUE = 0xffffff, 0x000000, 0xff0000, 40 << 16 | 120 << 8 | 200

# ---- how finely, where -----------------------------------------------------------------------------------------
for name, (w, h), want in (("4K", (3840, 2160), (960, 540, 2, 2)), ("1080p", (1920, 1080), (960, 540, 2, 1)),
                           ("1440p", (2560, 1440), (853, 480, 3, 1)), ("720p", (1280, 720), (853, 480, 1, 1)),
                           ("GPi Case", (640, 480), (640, 480, 1, 1)), ("1280x1024", (1280, 1024), (640, 512, 2, 1))):
    fb, _ = fake_fb(w, h, 32, RGB32)
    got = (fb.w, fb.h, fb.s, fb.rep)
    check(f"a Pi 5, {name}: the menus {fb.w} x {fb.h}, drawn {fb.s} x finer, each shown {fb.rep} x {fb.rep} ({got})",
          got == want)
model[0] = "Raspberry Pi 4 Model B Rev 1.4"
fb, _ = fake_fb(2560, 1440, 32, RGB32)
check(f"a Pi 4 at 1440p: as ever (drawn {fb.s} x), 1080p and 4K finely", fb.s == 1 and fake_fb(1920, 1080, 32, RGB32)[0].s == 2
      and fake_fb(3840, 2160, 32, RGB32)[0].s == 2)
model[0] = "Raspberry Pi Zero 2 W Rev 1.0"
check("a Pi Zero 2 on a 4K TV: as ever", fake_fb(3840, 2160, 32, RGB32)[0].s == 1)
model[0] = ""
check("a PC on a 4K monitor: twice", fake_fb(3840, 2160, 32, RGB32)[0].s == 2)
os.environ["PITATO_FINE"] = "4"
fb, _ = fake_fb(3840, 2160, 32, RGB32)
check(f"PITATO_FINE=4 on a 4K TV: the TV's every pixel its own ({fb.s}, {fb.rep})", (fb.s, fb.rep) == (4, 1))
os.environ["PITATO_FINE"] = "1"
check("PITATO_FINE=1: as ever", fake_fb(3840, 2160, 32, RGB32)[0].s == 1)
os.environ["PITATO_FINE"] = "3"
check("PITATO_FINE=3 where it can't be (4K): as ever", fake_fb(3840, 2160, 32, RGB32)[0].s == 1)
del os.environ["PITATO_FINE"]
model[0] = "Raspberry Pi 5 Model B Rev 1.0"

# ---- 4K, 32 bits: the fine picture's own pixels, each 2 x 2 ---------------------------------------------------------
fb, path = fake_fb(3840, 2160, 32, RGB32)
im = menu(fb)
fb.show(im)
px = pixels(path, 3840, 2160, 32)
check("4K: blue to the edges", px[1080, 0] == BLUE and px[1080, 3839] == BLUE and px[2159, 1920] == BLUE)
check("4K: the red line one of the menus' pixels high: 4 of the TV's", (px[:4, 100] == RED).all() and px[4, 100] == BLUE)
cell = px[80:84, 80:84]
check(f"4K: the picture's own checker there, each of its pixels 2 x 2 of the TV's ({cell.tolist()})",
      (cell[:2, :2] == WHITE).all() and (cell[:2, 2:] == BLACK).all() and (cell[2:, :2] == BLACK).all()
      and (cell[2:, 2:] == WHITE).all())
check("...the frame counted, kept for the web page", fb.last is im and fb.frames == g.Framebuffer.count)
buf = io.BytesIO()
fb.last.save(buf, "PNG")
web = Image.open(io.BytesIO(buf.getvalue()))
check(f"...the web page's copy at the menus' size ({web.size})", web.size == (960, 540))

# just a box of it, changed
im2 = im.copy()
F.ImageDraw.Draw(im2).rectangle((300, 200, 349, 249), fill=(0, 200, 0))
F.ImageDraw.Draw(im2).rectangle((700, 400, 709, 409), fill=(0, 200, 0))     # (outside the box: not written)
fb.show_part(im2, (290, 190, 360, 260))
px = pixels(path, 3840, 2160, 32)
check("4K, a box: the box written, at the TV's pixels", px[200 * 4, 300 * 4] == 0x00c800 and px[249 * 4 + 3, 349 * 4 + 3] == 0x00c800
      and px[250 * 4, 300 * 4] == BLUE)
check("...nothing outside it", px[400 * 4, 700 * 4] == BLUE)
check("...the whole picture kept", fb.last is im2)

# a plain picture still shown as ever (each of its pixels 4 x 4)
F.set_scale(1)
plain = Image.new("RGB", (960, 540), (10, 20, 30))
fb.show(plain)
px = pixels(path, 3840, 2160, 32)
check("4K, a plain picture: as ever, 4 x 4", px[0, 0] == 0x0a141e and px[2159, 3839] == 0x0a141e)
fb.show_part(im2, (0, 0, 960, 540))                     # (another kind of picture than the last: the whole of it)
px = pixels(path, 3840, 2160, 32)
check("...then a fine one again, part of it: all of it goes", px[1080, 0] == BLUE and px[0, 100] == RED)

# ---- 1080p: each of the fine picture's pixels the TV's own ---------------------------------------------------------
fb, path = fake_fb(1920, 1080, 32, RGB32)
fb.show(menu(fb))
px = pixels(path, 1920, 1080, 32)
cell = px[40:42, 40:42]
check(f"1080p: the checker pixel for pixel ({cell.tolist()})", cell[0, 0] == WHITE and cell[0, 1] == BLACK
      and cell[1, 0] == BLACK and cell[1, 1] == WHITE)
check("1080p: the red line two of the TV's pixels high", (px[:2, 500] == RED).all() and px[2, 500] == BLUE)
im = menu(fb)
F.ImageDraw.Draw(im).ellipse((100, 100, 140, 140), fill=(250, 200, 0))
fb.show_part(im, (95, 95, 145, 145))
px = pixels(path, 1920, 1080, 32)
check("1080p, a box: the circle drawn finely in it", px[240, 240] == 0xfac800 and px[200, 240] in (0xfac800, BLUE))

# ---- 16 bits, 4K ----------------------------------------------------------------------------------------------------
fb, path = fake_fb(3840, 2160, 16, RGB16)
fb.show(menu(fb))
px = pixels(path, 3840, 2160, 16)
W16 = 0xffff
check("4K at 16 bits: the checker too", px[80, 80] == W16 and px[81, 81] == W16 and px[80, 82] == 0 and px[82, 80] == 0)

# ---- a screen on its side ---------------------------------------------------------------------------------------------
fb, path = fake_fb(3840, 2160, 32, RGB32, turn=90)
check(f"4K on its side: menus {fb.w} x {fb.h}, drawn {fb.s} x", fb.w > 0 and fb.h > 0)
im = menu(fb)
fb.show(im)
px = pixels(path, 3840, 2160, 32)
reds = np.argwhere(px == RED)
check(f"...shown, turned: the red line a band down the TV, {fb.s} of its pixels wide, as long as the menus are wide "
      f"({len(reds)} px, columns {sorted(set(reds[:, 1].tolist()))[:4]})",
      len(reds) == fb.s * fb.w * fb.s and len(set(reds[:, 1].tolist())) == fb.s)
fb.show_part(im, (0, 0, 50, 50))
check("...a box of it too", True)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
