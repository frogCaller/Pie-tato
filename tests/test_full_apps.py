"""Settings > Full screen apps: Off at first, ◀▶ changes it, kept. On: an app's page, Now playing, a picture and a
document have no status bar, no tabs and no buttons along the bottom, just the app's name (or Now playing's, the
document's) along the top (a delete's are-you-sure keeps its buttons; a credit stays, small); a list shows more rows;
L R: the next app's name there. Not the home screen, Controls, a box to type in, or a sim (SELECT has its own). The
class's own sizes as they were. Off again: as before."""
import json, os, shutil, sys, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t_full_apps"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{HOME}/{d}")
for i in range(24):
    open(f"{HOME}/Music/{i + 1:02d} Song {i + 1}.mp3", "wb").write(b"x" * 100)
for i in range(3):
    Image.new("RGB", (320, 240), (40 + i * 40, 90, 160)).save(f"{HOME}/Pictures/pic{i}.jpg")
open(f"{HOME}/Documents/notes.txt", "w").write("\n".join(f"line {i}" for i in range(200)))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.PROG_TTY = os.devnull
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): self.show(img)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
m.keyreader.start = m.keyreader.stop = lambda: None
drawn = {"keys": [], "bars": 0, "titles": []}
real_key, real_bar, real_title = m.key, m.status_bar, m.app_title
m.key = lambda d, x, y, label, on=False: (drawn["keys"].append(label), real_key(d, x, y, label, on))[1]
m.status_bar = lambda d, clock=True: (drawn.__setitem__("bars", drawn["bars"] + 1), real_bar(d, clock))[1]
m.app_title = lambda d, title, right=None, right_fill=None: (drawn["titles"].append((title, right)),
                                                             real_title(d, title, right, right_fill or g.MUTED))[1]


def draw():
    """The screen drawn afresh: (the buttons drawn along the bottom, the status bar drawn or not)."""
    drawn["keys"], drawn["bars"], drawn["titles"] = [], 0, []
    m.msg = None
    m.dirty = True; m.flush()
    return list(drawn["keys"]), drawn["bars"] > 0


def sizes():
    return (m.STATUS_H, m.HEADER, m.LIST_TOP, m.FOOTER)


# Settings: the row, Off; ◀▶: On, kept
si = m.tab_index("settings")
m.open_app(si)
rows = m.settings_rows()
k = next((i for i, r in enumerate(rows) if r[0] == "app_full"), None)
check(f"Settings has it: Full screen apps, Off ({k is not None and rows[k][1]!r}, {m.setting('app_full')!r})",
      k is not None and rows[k][1] == "Full screen apps" and m.setting("app_full") == "Off")
check(f"...its bars as they were ({sizes()})", sizes() == (26, 68, 76, 48))
keys, bar = draw()
check(f"...drawn with them: the status bar, and the buttons ({keys})", bar and "B" in keys)
m.set_sel = k
m.press("right")
check(f"◀▶: On, kept ({m.setting('app_full')!r}, {json.load(open(g.STATE_FILE))['settings'].get('app_full')!r})",
      m.setting("app_full") == "On" and json.load(open(g.STATE_FILE))["settings"].get("app_full") == "On")
keys, bar = draw()
check(f"...Settings at once without them: no status bar, no buttons, its name on top ({keys}, {bar}, "
      f"{drawn['titles']}, {sizes()})", not bar and keys == [] and drawn["titles"] == [("Settings", None)]
      and sizes() == (0, 40, 48, 8))
check("...the class's own sizes as they were (a test's, say)", (g.Media.STATUS_H, g.Media.HEADER, g.Media.LIST_TOP,
                                                                  g.Media.FOOTER) == (26, 68, 76, 48))

# a list: more rows; L R: the next app's name on top
mi = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
m.open_app(mi)
full_rows = m.visible_rows()
keys, bar = draw()
check(f"Music: no bars, its name on top, more rows ({drawn['titles']}, {full_rows})", not bar and keys == []
      and drawn["titles"] == [("Music", None)] and full_rows == 8)
shot = FB.last.convert("RGB")
bottom = [shot.getpixel((x, 470)) for x in range(20, 400, 4)]
check("...nothing along the bottom but the list", len(set(bottom)) <= 2)
m.press("r")
draw()
check(f"R: the next app, its name on top ({g.LIBRARY[m.tab]['name']!r}, {drawn['titles']})",
      drawn["titles"] == [(g.LIBRARY[m.tab]["name"], None)])
m.press("l")
draw()
check(f"...L: back ({drawn['titles']})", m.tab == mi and drawn["titles"] == [("Music", None)])
ha = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "TV Remote")
m.tab, m.view = ha, "list"
m.load_tab(ha)
draw()
check(f"a page in Home: its app's name on top, the page's above its list ({drawn['titles']})",
      drawn["titles"] == [("Home", None)])
m.open_app(mi)

# Now playing
items = [it for it in m.tab_items() if it["kind"] == "audio"]
m.queue, m.qi, m.cur, m.kind = items, 0, items[0], "audio"
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=None)
m.meta = {"title": "Song 1", "artist": "Someone", "length": 200}
m.shuffle = True
m.view = "now"
keys, bar = draw()
check(f"Now playing: its title and Shuffle on top, no bars ({drawn['titles']}, {keys}, {bar})", not bar and keys == []
      and drawn["titles"] == [("Now playing", "Shuffle")])
m.shuffle = False
m.proc, m.kind, m.cur = None, None, None
m.view = "list"

# what keeps its bars: the home screen, Controls, a box to type in, a sim
m.go_home()
check(f"the home screen: its own as ever ({sizes()})", sizes() == (26, 68, 76, 48))
m.open_app(mi)
m.press("x")
keys, bar = draw()
check(f"Controls (X): its title and buttons ({m.view}, {keys})", m.view == "help" and bar and "ANY" in keys)
m.press("x")
m.open_keyboard("Name", "", lambda t: None)
keys, bar = draw()
check(f"a box to type in: its buttons ({keys})", bar and "A" in keys and "START" in keys)
m.close_keyboard(False)
life = next(i for i, t in enumerate(g.LIBRARY) if t.get("sim") == "life")
m.tab, m.view = life, "list"
m.load_tab(life)
check(f"a sim: its own (SELECT's full screen) ({sizes()})", sizes() == (26, 68, 76, 48) and not m.full_app())
m.sim_close()

# a picture, its delete question, a document
pi = m.tab_index("photos")
m.open_app(pi)
m.open_photo([it["src"] for it in m.tab_items()], 0)
keys, bar = draw()
check(f"a picture: no buttons ({m.view}, {keys}, {sizes()})", m.view == "photo" and keys == [] and m.FOOTER == 8)
m.v["confirm"] = True
keys, bar = draw()
check(f"...deleting it: are you sure, with its buttons ({keys})", keys == ["A", "B"])
m.v["confirm"] = False
m.photo_back()
m.open_text(f"{HOME}/Documents/notes.txt")
if m.view == "text":
    keys, bar = draw()
    rows_n, _ = m.text_rows()
    check(f"a document: its name on top, no buttons, more lines ({drawn['titles']}, {keys}, {bar}, {rows_n})",
          not bar and keys == [] and drawn["titles"][0][0] == "notes.txt" and rows_n == (480 - 56) // 20)
    m.press("b")
else:
    check(f"a document: opened as text ({m.view})", False)

# Finance's credit stays, small
fi = m.tab_index("finance")
m.open_app(fi)
draw()
corner = FB.last.convert("RGB").crop((500, 462, 636, 479))
check("Finance: where its numbers come from, small in the corner", corner.getextrema()[0][1] > 60)

# Off again: as before
m.open_app(si)
m.set_sel = next(i for i, r in enumerate(m.settings_rows()) if r[0] == "app_full")
m.press("left")
keys, bar = draw()
check(f"Off again: the bars back ({m.setting('app_full')!r}, {sizes()}, {keys})",
      m.setting("app_full") == "Off" and sizes() == (26, 68, 76, 48) and bar and "B" in keys)
m.open_app(mi)
check(f"...Music as it was ({m.visible_rows()})", m.visible_rows() == 7)
m.press("r")
keys, bar = draw()
check(f"...L R: the tabs again ({drawn['titles']}, {bar})", drawn["titles"] == [] and bar)
m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
