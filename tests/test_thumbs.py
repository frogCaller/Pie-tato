"""Photos' thumbnails (thumb_loop): made while a list shows, from the pictures on screen on, a broken picture skipped,
and then it's done (it used to look at every picture every second for as long as media mode was up); loading
Photos again starts it again for new ones; scrolled past the end of a shorter list, it doesn't fall over."""
import os, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_thumbs"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if t.get(key):
            t[key] = [f.replace("/home/*", S + "/home/*") for f in t[key]]
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


now = time.time()
for k in range(24):
    Image.effect_noise((800, 600), 30 + k).convert("RGB").save(f"{HOME}/Pictures/p{k:02d}.jpg")
    os.utime(f"{HOME}/Pictures/p{k:02d}.jpg", (now - 1000 + k, now - 1000 + k))   # (p23 newest: first)
open(f"{HOME}/Pictures/zz broken.jpg", "wb").write(b"\xff\xd8 not really a picture")
os.utime(f"{HOME}/Pictures/zz broken.jpg", (now - 2000, now - 2000))
m = g.Media()
m.active = True
pi = m.tab_index("photos")
made = []
real_fit = g.ImageOps.fit if hasattr(g, "ImageOps") else None
from PIL import ImageOps
real = ImageOps.fit
ImageOps.fit = lambda im, size, *a, **k: (made.append(1), real(im, size, *a, **k))[1]

m.view = "home"
m.load_tab(pi)                                      # (starts it)
th = m.thumber
check(th is not None and th.is_alive(), "loading Photos starts it")
time.sleep(1.0)
check(not made, "on the home screen: it waits")
m.view, m.tab = "list", pi
m.tops[pi] = 2                                       # (scrolled down two rows)
cols = m.grid_cols()
th.join(60)
check(not th.is_alive(), f"every picture has one: it's done ({len(made)} made)")
check(len(made) == 24 and m.thumbs_left == 0, "...24 made, the broken one skipped")
items = m.tab_items(pi)
order = sorted(os.listdir(S + "/cache/thumbs"), key=lambda n: os.path.getmtime(S + "/cache/thumbs/" + n))
first = g.cache_name(items[2 * cols]["src"], ".jpg")
check(order[0] == first, f"...the ones on screen first ({items[2 * cols]['title']})")

# again: nothing to make, it ends at once
m.thumbs.clear()
made.clear()
m.thumber = None
m.load_tab(pi)
m.thumber.join(10)
check(not m.thumber.is_alive() and not made, "loaded again, all there: done at once, nothing made")

# a new picture: loading Photos makes its thumbnail
Image.effect_noise((640, 480), 99).convert("RGB").save(f"{HOME}/Pictures/new.jpg")
m.load_tab(pi)
m.thumber.join(20)
check(len(made) == 1 and m.has_thumb(f"{HOME}/Pictures/new.jpg"), "a new picture: its thumbnail made")

# scrolled far past the end of the list (pictures deleted meanwhile): fine
Image.effect_noise((640, 480), 98).convert("RGB").save(f"{HOME}/Pictures/new2.jpg")
m.load_tab(pi)
m.tops[pi] = 500
m.thumber.join(20)
check(not m.thumber.is_alive() and m.has_thumb(f"{HOME}/Pictures/new2.jpg"), "scrolled past the end: no trouble")

# while it works, how many are left (for System)
shutil.rmtree(S + "/cache/thumbs")
m.thumbs.clear()
seen = []
ImageOps.fit = lambda im, size, *a, **k: (seen.append(m.thumbs_left), time.sleep(0.02), real(im, size, *a, **k))[2]
m.load_tab(pi)
m.thumber.join(60)
check(seen[:3] == [27, 26, 25] and seen[-1] == 2 and m.thumbs_left == 0,   # (27 pictures; the broken one last)
      f"how many are left: {seen[:3]}...{seen[-1:]}, 0")
ImageOps.fit = real
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
