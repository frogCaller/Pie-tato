"""Framebuffer.pack: the quick way for a 16-bit RGB565 screen (the GPi Case's) gives exactly the same
bytes as the general way, for whole pictures and pieces of them, odd sizes, any colours; other
screens (BGR565, 32-bit, 15-bit) still go the general way, unchanged."""
import os, random, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from PIL import Image
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def general(img, fields, bpp):
    """The way it always packed (copied from before the quick way)."""
    a = np.asarray(img.convert("RGB"), dtype=np.uint32)
    px = np.zeros(a.shape[:2], dtype=np.uint32)
    for c, (off, ln) in enumerate(fields):
        px |= (a[..., c] >> (8 - ln)) << off
    return px.astype("<u2" if bpp == 16 else "<u4").tobytes()


def screen(bpp, fields):
    fb = object.__new__(g.Framebuffer)
    fb.f = open(os.devnull, "r+b", buffering=0)
    fb.setup(640, 480, 0, 0, bpp, fields, 640 * bpp // 8)
    return fb


rnd = random.Random(5)
pictures = []
for w, h in ((640, 480), (440, 346), (1, 1), (3, 7), (617, 2), (160, 346)):
    data = bytes(rnd.randrange(256) for _ in range(w * h * 3))
    pictures.append(Image.frombytes("RGB", (w, h), data))
edge = Image.new("RGB", (8, 4))
edge.putdata([(v, 255 - v, (v * 37) % 256) for v in (0, 1, 2, 3, 4, 7, 8, 127, 128, 248, 251, 252, 253, 254, 255, 6,
                                                      9, 31, 32, 63, 64, 100, 200, 250, 5, 10, 20, 40, 80, 160, 240, 15)])
pictures.append(edge)
pictures.append(Image.new("L", (20, 10), 200))           # (not RGB: converted first)
print("numpy", np.__version__)
for name, bpp, fields in (("RGB565 (the GPi Case)", 16, [(11, 5), (5, 6), (0, 5)]),
                          ("RGB565, fields as lists", 16, [[11, 5], [5, 6], [0, 5]]),
                          ("BGR565", 16, [(0, 5), (5, 6), (11, 5)]),
                          ("RGB555", 16, [(10, 5), (5, 5), (0, 5)]),
                          ("32-bit RGBX", 32, [(0, 8), (8, 8), (16, 8)]),
                          ("32-bit BGRX (raw)", 32, [(16, 8), (8, 8), (0, 8)])):
    fb = screen(bpp, fields)
    same = all(fb.pack(p) == general(p, [tuple(f) for f in fields], bpp) for p in pictures)
    crops = all(fb.pack(p.crop(b)) == general(p.crop(b), [tuple(f) for f in fields], bpp)
                for p in pictures[:1] for b in (g.SIM_BOX, g.SIM_DIRTY, (0, 0, 640, 480), (13, 77, 452, 425)))
    check(f"{name}: the same bytes as ever", same and crops)
fb = screen(16, [(11, 5), (5, 6), (0, 5)])
big = pictures[0]
t0 = time.perf_counter()
for _ in range(40):
    fb.pack(big)
quick = (time.perf_counter() - t0) / 40
t0 = time.perf_counter()
for _ in range(40):
    general(big, [(11, 5), (5, 6), (0, 5)], 16)
slow = (time.perf_counter() - t0) / 40
check(f"...and quicker: {quick * 1000:.2f} ms for the whole screen (was {slow * 1000:.2f})",
      quick < slow * 0.8)                          # (numpy 1.24 does the general way quicker than numpy 2 does)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
