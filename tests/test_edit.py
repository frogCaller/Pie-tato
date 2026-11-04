import os, sys, time, shutil
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t13"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
os.chown(HOME, 1234, 1234); os.chown(HOME + "/Pictures", 1234, 1234)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "photos":
        t["dirs"] = [HOME + "/Pictures"]
import gk_static; gk_static.use_home(g, HOME)


def scene(path, w, h, sky, when):
    im = Image.new("RGB", (w, h), sky)
    d = ImageDraw.Draw(im)
    for k in range(0, h, 4):                       # a soft sky
        d.line((0, k, w, k), fill=tuple(min(255, c + k * 60 // h) for c in sky))
    d.ellipse((w * .62, h * .12, w * .82, h * .12 + w * .2), fill=(250, 214, 120))
    d.polygon([(0, h * .75), (w * .3, h * .42), (w * .55, h * .7), (w * .8, h * .38), (w, h * .66), (w, h), (0, h)],
              fill=(52, 92, 70))
    d.rectangle((w * .1, h * .6, w * .22, h * .8), fill=(150, 70, 60))
    d.polygon([(w * .08, h * .6), (w * .16, h * .5), (w * .24, h * .6)], fill=(90, 40, 40))
    im.save(path, quality=92)
    os.utime(path, (when, when))


now = time.time()
scene(HOME + "/Pictures/camera-2026-10-11-175632.jpg", 1920, 1080, (70, 120, 170), now - 60)
scene(HOME + "/Pictures/beach.jpg", 1600, 1200, (90, 150, 200), now - 3600)
scene(HOME + "/Pictures/hills.jpg", 1280, 960, (120, 100, 150), now - 7200)

shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


def snap(name):
    m.dirty = True; m.flush()
    if m.view == "photo" and m.v.get("edit"):
        wait_for(lambda: not m.v.get("working"), 10)
        m.dirty = True; m.flush()
    shots[name] = FB.last


def wait_for(c, t=20):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
pi = m.tab_index("photos")
m.tab = pi; m.load_tab(pi)
print("photos:", [x["title"] for x in m.tab_items()])
m.press("a")                                      # open the newest
print("view:", m.view, os.path.basename(m.v["items"][m.v["i"]]))
snap("view")

# filters: preview timings at screen size
im = m.photo_image()
for fid, lab in g.FILTERS:
    t = time.time(); g.apply_filter(im.copy().resize((640, 360)), fid); dt = time.time() - t
    print(f"  preview {lab:10s} {dt * 1000:6.0f} ms")
m.press("x"); print("edit:", m.v["edit"])
snap("edit_original")
m.press("right"); m.press("right")                # Sepia
snap("edit_sepia")
for _ in range(4):
    m.press("right")                              # Sketch
print("filter:", g.FILTERS[m.v["fi"]])
snap("edit_sketch")
m.press("right"); m.press("right")                # Comic
snap("edit_comic")
m.press("left"); m.press("left"); m.press("left") # Blue? -> back to Sketch... pick Sketch
m.press("right")
print("chosen:", g.FILTERS[m.v["fi"]])
t = time.time()
m.press("a")
print("busy:", m.v["busy"])
m.press("right"); print("ignored while saving:", g.FILTERS[m.v["fi"]][0])
assert wait_for(lambda: not m.v["busy"])
print("saved in %.1fs" % (time.time() - t), "| toast:", m.msg)
cur = m.v["items"][m.v["i"]]
print("now showing:", os.path.basename(cur), Image.open(cur).size, "owner:", os.stat(cur).st_uid,
      "| edit off:", not m.v["edit"])
snap("saved")

# a turned copy with no filter
m.press("x"); m.press("y"); m.press("a")
assert wait_for(lambda: not m.v["busy"])
print("turned copy:", os.path.basename(m.v["items"][m.v["i"]]), Image.open(m.v["items"][m.v["i"]]).size)
# nothing to save
m.press("x"); m.press("a"); print("nothing chosen:", m.msg); m.press("b")

# delete: ask first, B keeps it
m.press("select"); print("confirm:", m.v["confirm"]); snap("confirm")
m.press("b"); print("kept:", os.path.exists(m.v["items"][m.v["i"]]))
gone = m.v["items"][m.v["i"]]
m.press("select"); m.press("a")
print("deleted:", not os.path.exists(gone), "| toast:", m.msg, "| left:", len(m.v["items"]))
snap("after_delete")

# back to the grid: list redone
m.press("b")
print("grid:", [x["title"] for x in m.tab_items()], "| selected:", m.tab_items()[m.sels[pi]]["title"])
time.sleep(2.5); snap("grid")

# a picture outside home can't be deleted
os.makedirs(S + "/elsewhere", exist_ok=True)
scene(S + "/elsewhere/x.jpg", 400, 300, (100, 100, 100), now)
m.open_photo([S + "/elsewhere/x.jpg"], 0)
m.press("select"); print("outside home:", m.msg, "| confirm:", m.v["confirm"])
m.press("x"); m.press("right"); m.press("a"); assert wait_for(lambda: not m.v["busy"])
print("copy of outside picture went to:", os.path.dirname(m.v["items"][m.v["i"]]) == HOME + "/Pictures")
m.close_viewer()

# delete everything in a viewer: back to the grid
m.load_tab(pi)
pics = [x["src"] for x in m.tab_items()]
m.open_photo(pics, 0)
for _ in range(len(pics)):
    m.press("select"); m.press("a")
print("all deleted -> view:", m.view, "| grid items:", len(m.tab_items()))

W, H = 640, 480
order = ["view", "edit_sepia", "edit_sketch", "edit_comic", "saved", "confirm", "grid", "edit_original"]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 4 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/photo_edit.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
