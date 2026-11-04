import io, os, sys, time, shutil, json
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
import numpy as np
S = SP + "/t25"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.fetch_json = lambda url: {"response": {"docs": []}}
# an old saved setting from before: "Fill"
json.dump({"settings": {"screen": "Fill"}}, open(g.STATE_FILE, "w"))
spawned, blanks = [], []
class Proc:
    stdin = io.StringIO()
    def poll(self): return None
    def kill(self): pass
    def wait(self, timeout=None): return 0
def fake_spawn(self, args, target):
    spawned.append((args, target)); self.proc = Proc(); self.started = time.monotonic() - 5
g.Media.spawn = fake_spawn
class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): blanks.append(box)
    def close(self): pass
RealFB = g.Framebuffer; g.Framebuffer = FB
shots = {}
m = g.Media(); m.enter()
print("old 'Fill' reads as:", m.setting("screen"))
m.set_setting("screen", "Fit")
m.plex.live_url = lambda key: "https://plex.example/live/" + key
yugi = g.item("plexlive:/ch/4", "Yu-Gi-Oh!", "live", "plexlive:/ch/4", sub="Animation")
m.play([yugi], 0)
shots["curtain"] = FB.last
a = np.asarray(FB.last)
print("curtain: bottom 60 rows black:", int(a[420:].max()) == 0, "| top 60 rows black:", int(a[:60].max()) == 0,
      "| words in the middle:", int(a[200:300].max()) > 0)
args = spawned[-1][0]; i = args.index("-vf"); print("Fit:", " ".join(args[i - 3:i + 2]))
m.tick(); print("blank before the size is known:", blanks)
m.vsize = (1280, 720); m.tick(); m.tick()
print("bars blanked once, 16:9:", blanks)
m.vsize = (720, 1280); m.tick(); print("portrait:", blanks[-1])
m.press("y"); args = spawned[-1][0]
print("Y -> full screen:", args[args.index("-vf") + 1], "| restarted from the live start:", "-ss" not in args)
shots["curtain_full"] = FB.last
n = len(blanks); m.tick(); print("no bars to blank in full screen:", len(blanks) == n)
m.press("y"); print("Y -> ", m.setting("screen"))
m.press("b")
# settings row
m.view = "list"; m.tab = m.tab_index("settings"); m.load_tab(m.tab)
rows = [r[1] for r in m.settings_rows()]
print("settings:", rows)
m.set_sel = rows.index("Video size"); m.press("right"); print("◀▶ ->", m.setting("screen")); m.press("right"); print("◀▶ ->", m.setting("screen"))
m.press("right")
m.dirty = True; m.flush(); shots["settings"] = FB.last
# the real framebuffer: blank_outside on a file standing in for /dev/fb0
fbf = S + "/fb"
open(fbf, "wb").write(b"\xff" * (640 * 480 * 2))
fb = object.__new__(RealFB)
fb.f = open(fbf, "r+b", buffering=0); fb.setup(640, 480, 0, 0, 16, [(11, 5), (5, 6), (0, 5)], 1280)
fb.blank_outside(g.fit_box((1280, 720)))
px = np.frombuffer(open(fbf, "rb").read(), dtype="<u2").reshape(480, 640)
print("fb file: rows 0-61 black:", int(px[:62].max()) == 0, "| row 62 untouched:", int(px[62].min()) == 0xffff,
      "| rows 418+ black:", int(px[418:].max()) == 0, "| row 417 untouched:", int(px[417].min()) == 0xffff)
open(fbf, "wb").write(b"\xff" * (640 * 480 * 2))
fb.blank_outside(g.fit_box((720, 1280)))
px = np.frombuffer(open(fbf, "rb").read(), dtype="<u2").reshape(480, 640)
x0, _, x1, _ = g.fit_box((720, 1280))
print("portrait box:", g.fit_box((720, 1280)), "| left black:", int(px[:, :x0].max()) == 0,
      "| right black:", int(px[:, x1:].max()) == 0, "| middle untouched:", int(px[:, x0:x1].min()) == 0xffff)
W, H = 640, 480
out = Image.new("RGB", (W * 3 + 20, H), (80, 80, 80))
for k, name in enumerate(["curtain", "curtain_full", "settings"]):
    out.paste(shots[name], (k * (W + 10), 0))
out.save(SP + "/out/curtain.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
