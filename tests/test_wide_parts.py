"""Through the real Framebuffer on a 1080p screen (a file): the Bot at work and a Simulator world send only
the part that moves; afterwards, what's on the screen is just what a whole picture of the last frame gives."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
S = SP + "/tparts"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.FRIEND_LOG = S + "/friend.json"
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
RealFB = g.Framebuffer
RGB32 = [(16, 8), (8, 8), (0, 8)]
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def make(path, w, h):
    open(path, "wb").write(b"\0" * (w * h * 4))
    fb = object.__new__(RealFB)
    fb.f = open(path, "r+b", buffering=0)
    fb.setup(w, h, 0, 0, 32, RGB32, w * 4)
    return fb


parts = []
for w, h in ((1920, 1080), (1280, 720)):
    path, ref = f"{S}/fb_{w}", f"{S}/ref_{w}"
    fb = make(path, w, h)
    real_part = fb.show_part
    fb.show_part = lambda img, box, real_part=real_part: (parts.append(box), real_part(img, box))[1]
    g.Framebuffer = lambda fb=fb: fb
    m = g.Media()
    m.enter()
    for page in ("coder", "sim"):
        if page == "coder":
            m.open_app(m.tab_index("friend"))
            m.coder.ask("typing")
            m.press("right")
        else:
            m.press("left")
            m.open_app([t["name"] for t in g.LIBRARY].index("Game of Life"))   # (Orbits: gone)
        parts.clear()
        for _ in range(25):
            m.dirty = True
            m.tick()
            m.flush()
            time.sleep(0.03)
        m.flush()
        rf = make(ref, w, h)
        rf.show(fb.last)
        a = np.fromfile(path, dtype="<u4"); b = np.fromfile(ref, dtype="<u4")
        if (a != b).any():
            ys, xs = np.nonzero((a != b).reshape(h, w))
            kx, ky = fb.tw / fb.w, fb.th / fb.h
            print(f"   differ in screen box x {xs.min()}..{xs.max()}, y {ys.min()}..{ys.max()}; menus x "
                  f"{xs.min() / kx:.0f}..{xs.max() / kx:.0f}, y {ys.min() / ky:.0f}..{ys.max() / ky:.0f}; parts {sorted(set(parts))[:4]}")
            print("   most off:", int(max(np.abs(((a >> sh) & 255).astype("int64") - ((b >> sh) & 255).astype("int64")).max()
                                         for sh in (0, 8, 16))))
        off = int(max(np.abs(((a >> sh) & 255).astype("int64") - ((b >> sh) & 255).astype("int64")).max()
                      for sh in (0, 8, 16)))
        check(f"{w}x{h} {page}: {len(parts)} frames sent in part, and the screen is just the last picture "
              f"({off} off at most, rounding)", parts and off <= 1)
    m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
