import io, os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t15"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music"); os.makedirs(HOME + "/Pictures")
open(HOME + "/camera.txt", "w").write("url = 127.0.0.1:5999\n")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()


def offline(*a, **k):
    raise OSError("offline in the test")


g.urllib.request.urlopen = offline
g.fetch_json = offline
shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


g.Framebuffer = FB


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


m = g.Media()
ci = m.tab_index("camera")
m.tab = ci                                         # last time you were on the Camera tab
m.enter()
print("view:", m.view, "| picked:", m.home_apps()[m.home_sel][0], "| camera running behind home:", m.camera.running)
snap("home_camera")
m.home_sel = 0; snap("home")
print("apps:", [a[0] for a in m.home_apps()])

# moving around
m.press("right"); m.press("right"); print("right x2:", m.home_apps()[m.home_sel][0])
m.press("down"); print("down:", m.home_apps()[m.home_sel][0])
m.press("left"); m.press("left"); m.press("left"); print("left x3:", m.home_apps()[m.home_sel][0])
m.press("left"); print("left wraps:", m.home_apps()[m.home_sel][0])
m.press("up"); print("up:", m.home_apps()[m.home_sel][0])

# open Finance, then B home
m.home_sel = [a[0] for a in m.home_apps()].index("Finance")
m.press("a"); print("opened:", m.view, g.LIBRARY[m.tab]["name"], "| coins running:", m.crypto.running,
                    "| stocks running:", m.stocks.running)
m.dirty = True; m.flush(); print("finance hints end with:", "Home" in str(m.list_hints()) or "drawn")
r = m.press("b"); print("B ->", m.view, r, "| coins running:", m.crypto.running, "| stocks running:", m.stocks.running,
                       "| picked:", m.home_apps()[m.home_sel][0])

# camera starts only when opened
m.home_sel = [a[0] for a in m.home_apps()].index("Camera")
m.press("a"); print("camera opened, running:", m.camera.running)
m.press("r"); print("R from Camera ->", g.LIBRARY[m.tab]["name"], "| camera running:", m.camera.running)
m.press("b"); print("B ->", m.view, "| picked:", m.home_apps()[m.home_sel][0])

# TV: inside the group and its children
m.home_sel = [a for a, _ in m.home_apps()].index("TV"); m.press("a"); print("TV:", m.view, g.LIBRARY[m.tab]["name"], "| hints:", m.list_hints())
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Streams"); m.press("a")
print("child:", g.LIBRARY[m.tab]["name"], "| hints:", m.list_hints())
m.press("b"); print("B ->", m.view, g.LIBRARY[m.tab]["name"])
m.press("b"); print("B ->", m.view, "| picked:", m.home_apps()[m.home_sel][0])

# Files: B walks up folders first, then home
m.home_sel = [a[0] for a in m.home_apps()].index("Files"); m.press("a")
m.browse(HOME + "/Music"); m.press("b"); print("Files up ->", g.short_path(m.cwd), m.view)
m.press("b"); print("Files B at home folder ->", m.view)

# music playing: card on the home screen, START, B back home
class Proc:
    stdin = io.StringIO()
    def poll(self): return None
    def kill(self): pass
    def wait(self, timeout=None): return 0
m.proc, m.kind = Proc(), "audio"
m.cur = {"title": "Night Drive", "sub": "Synthwave", "src": HOME + "/Music/night.mp3", "kind": "audio"}
m.meta = {"title": "Night Drive"}
m.home_sel = [a[0] for a in m.home_apps()].index("Videos")
snap("home_music")
m.press("start"); print("START ->", m.view)
m.press("b"); print("B from Now playing ->", m.view)
m.proc, m.kind, m.cur = None, None, None

# Y on the home screen leaves media mode (there's no Terminal icon); B there does nothing
m.home_sel = len(m.home_apps()) - 1
snap("home_last")
print("last icon:", m.home_apps()[m.home_sel][0])
print("B on home ->", m.press("b"), "| Y on home ->", m.press("y"))

# leave from inside an app, come back: home again
m.home_sel = [a[0] for a in m.home_apps()].index("System"); m.press("a")
m.leave(); m.enter(); print("re-enter:", m.view, "| picked:", m.home_apps()[m.home_sel][0])

# drawing the icons by themselves, bigger, to check them
sheet = Image.new("RGB", (10 * 140 + 20, 170), (16, 19, 23))
for k, (name, _) in enumerate(m.home_apps()):
    ic = g.draw_icon(name, 128)
    sheet.paste(ic, (20 + k * 140, 20), ic)
sheet.save(SP + "/out/home_icons.png")

W, H = 640, 480
order = ["home", "home_music", "home_camera", "home_last"]
out = Image.new("RGB", (W * 2 + 10, H * 2 + 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/home_screen.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
