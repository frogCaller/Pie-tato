"""A notice over a game's picture (an achievement unlocked): drawn onto the frames at the top middle of the picture, in
gold on dark, for NOTE_SECS; then the picture under it put back and written, even with no new frame (a still
screen); the next one after it; on a screen on its side, turned with the picture, in the same place as it's seen; a
picture too small for one: none. And back from the menu, the last picture written again (not left black)."""
import os, shutil, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from pitato import emulator as E

S = SP + "/tnotice"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def screen(w, h, bits=16, turn=0):
    path = f"{S}/fb{w}x{h}x{bits}t{turn}"
    open(path, "wb").write(bytes(w * h * bits // 8))
    os.environ["PITATO_FB"] = f"{path}:{w}x{h}:{bits}"
    return E.Screen(turn=turn), path


def fb(path, w, h, bits):
    return np.frombuffer(open(path, "rb").read(), dtype="<u2" if bits == 16 else "<u4").reshape(h, w)


def frame(w, h, colour):
    """A plain frame, RGB565."""
    r, g, b = colour
    return np.full((h, w), ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3), dtype=np.uint16)


def gold_at(a, bits):
    """How many pixels are the notice's gold."""
    if bits == 16:
        r, g, b = (a >> 11) & 31, (a >> 5) & 63, a & 31
        return int(((r >= 27) & (g >= 44) & (g <= 54) & (b <= 13)).sum())
    r, g, b = (a >> 16) & 255, (a >> 8) & 255, a & 255
    return int(((r >= 220) & (g >= 176) & (g <= 216) & (b <= 110)).sum())


GREEN = (0, 200, 0)
E.NOTE_SECS = 0.4
sc, path = screen(640, 480)
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
before = fb(path, 640, 480, 16).copy()
sc.notice(["★ Achievement unlocked · 10 points", "First Blood", "Defeat the first boss"])
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
now = fb(path, 640, 480, 16)
changed = np.argwhere(now != before)
top, left, bottom, right = changed[:, 0].min(), changed[:, 1].min(), changed[:, 0].max(), changed[:, 1].max()
check(f"a notice: on the next frame, at the top middle of the picture ({top}, {left} to {bottom}, {right})",
      len(changed) > 2000 and 6 <= top <= 12 and abs((left + right) / 2 - 320) <= 2 and bottom < 140
      and gold_at(now[top:bottom + 1, left:right + 1], 16) > 100)
check("...its corners round: the picture shows through them", now[top, left] == before[top, left])
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
check("...on each frame while it's up", (fb(path, 640, 480, 16) != before).sum() == len(changed))
sc.notice(["★ Achievement unlocked · 5 points", "Second", "The next one"])
time.sleep(0.5)
sc.notice_tick()
check("its time up, no new frame (a still screen): the picture under it put back, at once",
      (fb(path, 640, 480, 16) == before).all() and sc.note is None)
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
check(f"...the next one waiting: on the next frame ({sc.note and sc.note['lines'][1]})",
      sc.note is not None and sc.note["lines"][1] == "Second" and (fb(path, 640, 480, 16) != before).any())
time.sleep(0.5)
sc.notice_tick()
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
check("...then none", sc.note is None and (fb(path, 640, 480, 16) == before).all())

# a screen on its side: turned with the picture, in the same place as it's seen
for turn in (90, 180, 270):
    sc, path = screen(480, 640, 32, turn=turn) if turn in (90, 270) else screen(640, 480, 32, turn=turn)
    dev_w, dev_h = (480, 640) if turn in (90, 270) else (640, 480)
    sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
    before = fb(path, dev_w, dev_h, 32).copy()
    sc.notice(["★ Achievement unlocked · 10 points", "First Blood", "Defeat the first boss"])
    sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
    seen = E.unturn_pixels(fb(path, dev_w, dev_h, 32), turn)        # (as it's seen)
    was = E.unturn_pixels(before, turn)
    changed = np.argwhere(seen != was)
    top, left, right = changed[:, 0].min(), changed[:, 1].min(), changed[:, 1].max()
    inside = seen[:, left + 4:right - 3]                             # (not its gold edge)
    check(f"turned {turn}: as it's seen, at the top middle, the right way up: gold at its top, not lower down "
          f"({top}, {left}-{right})", 6 <= top <= 12 and abs((left + right) / 2 - 320) <= 2
          and gold_at(inside[top + 4:top + 28], 32) > 30 and gold_at(inside[top + 50:top + 70], 32) == 0)

# a picture too small for one
sc, path = screen(160, 120)
sc.show(frame(160, 120, GREEN), E.FMT_RGB565, 4 / 3)
before = fb(path, 160, 120, 16).copy()
sc.notice(["★ Achievement unlocked · 10 points", "First Blood", "Defeat the first boss"])
sc.show(frame(160, 120, GREEN), E.FMT_RGB565, 4 / 3)
check("a picture too small for it: none (the game as it is)", (fb(path, 160, 120, 16) == before).all())

# back from the menu: the last picture again, not black
sc, path = screen(640, 480)
sc.show(frame(320, 240, GREEN), E.FMT_RGB565, 4 / 3)
shown = fb(path, 640, 480, 16).copy()
open(path, "r+b").write(b"\xff" * 1000)                 # (the menu, over it)
sc.clear()
sc.again()
check("back from the menu: the last picture written again", (fb(path, 640, 480, 16) == shown).all())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
