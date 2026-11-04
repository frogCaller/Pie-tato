"""Saving another computer's files onto the Pi: SELECT on one in Files (and SELECT Save in its buttons, not on a folder
or ".."), in the photo viewer (instead of Delete) and the text viewer; each into the folder for its kind (a picture in
Pictures, a video in Videos, a song in Music, a game in Games, a .md that's a Genesis game in Games and one that's
text in Documents, the rest in Documents), owned like your home folder, with its own date; the same file there
already: kept as it is; another of that name: name-2; not enough room: said; one after another; how far it's got,
said; the web page's Save to the Pi (its row's button, webui.py's check of where it is, media mode's)."""
import json, os, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_net_save"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
NETR = S + "/net"
PC = NETR + "/192.168.1.20/Shared"
for d in (HOME, PC + "/Holiday", S + "/static"):
    os.makedirs(d)
os.chown(HOME, 1000, 1000)                          # (your home folder's: what's saved is yours, not root's)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


Image.new("RGB", (64, 48), (200, 80, 40)).save(PC + "/beach.jpg")
Image.new("RGB", (64, 48), (40, 80, 200)).save(PC + "/Holiday/sea.png")
FILES = {"clip.mp4": b"\0\0\0\x18ftypmp42" + b"v" * 5000, "song.mp3": b"ID3" + b"m" * 3000, "notes.txt": b"Shopping: eggs\n",
         "sonic.md": b"\0" * 256 + b"SEGA GENESIS" + b"\0" * 300, "readme.md": b"# Read me\nHello\n",
         "tetris.gba": b"\0" * 1024, "setup.exe": b"MZ" + b"x" * 100, "photos.zip": b"PK" + b"z" * 100}
for n, data in FILES.items():
    open(PC + "/" + n, "wb").write(data)
os.utime(PC + "/beach.jpg", (1_600_000_000, 1_600_000_000))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, S + "/static")
real_run = g.subprocess.run       # (this machine's own consoles left as they are: no switching to media mode's)
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd[:1] in (["chvt"], ["fgconsole"])
                                         else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
m.enter()
m.computers.root = NETR
m.computers.owner = lambda path: (({"addr": "192.168.1.20", "how": "smb"}, "Shared", PC)   # (the computer, its share
                                  if os.path.normpath(path).startswith(PC) else None)    # opened: as it is once added)
toasts = []
real_toast = m.toast
m.toast = lambda text, secs=2: (toasts.append(text), real_toast(text, secs))[1]
bi = m.tab_index("browser")


def browse(path):
    m.net_seen[path] = (time.monotonic(), g.scan(path))   # (what's there, as a look would find)
    m.open_app(bi)
    m.browse(path)


def row(name):
    items = m.tab_items()
    k = next(k for k, it in enumerate(items) if it["title"] == name)
    m.sels[bi] = k
    return items[k]


def hints():
    return [k for k, _ in m.list_hints()]


def saved(secs=10):
    end = time.time() + secs
    while time.time() < end:
        m.tick()
        if not m.net_saves and m.net_saving is None and not m.net_saved and (m.net_saver is None or not m.net_saver.is_alive()):
            return True
        time.sleep(0.05)
    return False


browse(PC)
row("beach.jpg")
check(f"a file on another computer: SELECT Save in its buttons ({m.list_hints()})", "SELECT" in hints()
      and ("SELECT", "Save") in m.list_hints())
row("Holiday")
check("...not on a folder", "SELECT" not in hints())
row("..")
check("...nor on ..", "SELECT" not in hints())
row("beach.jpg")
m.press("select")
check(f"SELECT: saving ({toasts[-1:]})", toasts and "Saving beach.jpg" in toasts[-1])
check("...done", saved())
got = HOME + "/Pictures/beach.jpg"
st = os.stat(got) if os.path.exists(got) else None
check(f"...a picture: in Pictures, the same, yours, its own date ({toasts[-1:]})", st is not None
      and open(got, "rb").read() == open(PC + "/beach.jpg", "rb").read() and (st.st_uid, st.st_gid) == (1000, 1000)
      and int(st.st_mtime) == 1_600_000_000 and toasts[-1] == "Saved to Pictures"
      and os.stat(HOME + "/Pictures").st_uid == 1000)
check("...and nothing half-made left there", sorted(os.listdir(HOME + "/Pictures")) == ["beach.jpg"])
m.press("select")
saved()
check(f"the same again: kept as it is ({toasts[-1]!r})", toasts[-1] == "beach.jpg is in Pictures already"
      and sorted(os.listdir(HOME + "/Pictures")) == ["beach.jpg"])
Image.new("RGB", (80, 60), (10, 200, 10)).save(PC + "/beach.jpg")         # (another picture of that name)
m.press("select")
saved()
check(f"another of that name: beach-2.jpg ({toasts[-1]!r})", toasts[-1] == "Saved to Pictures as beach-2.jpg"
      and sorted(os.listdir(HOME + "/Pictures")) == ["beach-2.jpg", "beach.jpg"])

want = {"clip.mp4": "Videos", "song.mp3": "Music", "notes.txt": "Documents", "sonic.md": "Games", "readme.md": "Documents",
        "tetris.gba": "Games", "setup.exe": "Documents", "photos.zip": "Documents"}
for n in want:
    row(n)
    m.press("select")
check(f"one after another: said so ({toasts[-1]!r})", "after" in toasts[-1])
check("...all done", saved(20))
where = {n: next((f for f in ("Videos", "Music", "Documents", "Games", "Pictures")
                  if os.path.isfile(f"{HOME}/{f}/{n}")), None) for n in want}
check(f"each in the folder for its kind ({where})", where == want)
check("...all of them as they are", all(open(f"{HOME}/{want[n]}/{n}", "rb").read() == FILES[n] for n in want))

# not enough room
real_usage = shutil.disk_usage
g.shutil.disk_usage = lambda p: type("D", (), {"free": 10_000_000, "total": 1, "used": 1})()
Image.new("RGB", (8, 8)).save(PC + "/big.png")
browse(PC)
row("big.png")
m.press("select")
saved()
check(f"not enough room on the Pi: said, nothing saved ({toasts[-1]!r})", "Not enough room" in toasts[-1]
      and not os.path.exists(HOME + "/Pictures/big.png"))
g.shutil.disk_usage = real_usage

# how far it's got
m.net_saving = {"src": PC + "/clip.mp4", "name": "clip.mp4", "done": 3_000_000, "size": 12_000_000, "said": 0.0}
m.net_save_tick(time.monotonic())
check(f"how far a save has got, said now and then ({toasts[-1]!r})", toasts[-1] == "Saving clip.mp4… 25%")
m.net_saving = None

# the photo viewer and the text viewer
browse(PC + "/Holiday")
m.open_photo([PC + "/Holiday/sea.png"], 0)
m.dirty = True; m.flush()
check("the photo viewer, a picture on another computer: SEL Save instead of Delete", m.view == "photo")
m.press("select")
saved()
check(f"...SELECT saves it ({toasts[-1]!r})", os.path.isfile(HOME + "/Pictures/sea.png") and not m.v.get("confirm"))
m.close_viewer()
own = HOME + "/Pictures/beach.jpg"
m.open_photo([own], 0)
m.press("select")
check("...one of yours: Delete, as before", m.v["confirm"])
m.press("b"); m.close_viewer()
m.open_text(PC + "/notes.txt")
os.remove(HOME + "/Documents/notes.txt")
m.press("select")
saved()
check(f"the text viewer, a file on another computer: SELECT saves it ({toasts[-1]!r})",
      os.path.isfile(HOME + "/Documents/notes.txt"))
m.close_viewer()
mine = HOME + "/Documents/notes.txt"
m.open_text(mine)
before = list(toasts)
m.press("select")
check("...one of yours: nothing", toasts == before and not m.net_saves)
m.close_viewer()

# the web page
out = m.web_net_save(PC + "/song.mp3")
saved()
check(f"media mode's Save to the Pi: ok, saved ({out})", out == {"ok": True, "said": "Saving it onto the Pi"})
out = m.web_net_save(HOME + "/Music/song.mp3")
check(f"...not one on another computer: refused ({out})", "error" in out)
sys.path.append(ROOT + "/pitato")
import webui
webui.NET_ROOT = NETR
webui.STATIC = S + "/static"
asked = []
webui.ask_pi = lambda method, path, body=None, **k: (asked.append((method, path, body)),
                                                     (200, json.dumps({"ok": True, "said": "Saving it onto the Pi"}).encode(),
                                                      "application/json"))[1]
webui.open_computer = lambda parts: None
c = webui.app.test_client()
H = {"X-Pitato-Page": "1"}
r = c.post("/api/pi/save", json={"folder": "computers", "path": "192.168.1.20/Shared/clip.mp4"}, headers=H)
check(f"webui.py: Save to the Pi passed on, as where it really is ({r.status_code}, {asked[-1:]})",
      r.status_code == 200 and asked[-1] == ("POST", "/save", {"path": os.path.realpath(PC + "/clip.mp4")}))
n = len(asked)
for body, why in (({"folder": "music", "path": "song.mp3"}, "one of the Pi's own"),
                  ({"folder": "computers", "path": "192.168.1.20/Shared/nothing.mp3"}, "not there"),
                  ({"folder": "computers", "path": "192.168.1.20/Shared/Holiday"}, "a folder"),
                  ({"folder": "computers", "path": "../../etc/passwd"}, "outside")):
    r = c.post("/api/pi/save", json=body, headers=H)
    check(f"...{why}: refused ({r.status_code})", r.status_code >= 400 and len(asked) == n)
page = open(ROOT + "/templates/index.html").read()
check("the web page: a Save to the Pi button on other computers' files", 'pi("save", { folder: S.folder, path })' in page
      and 'S.folder === "computers"' in page and "Save to the Pi" in page)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
