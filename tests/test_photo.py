import io, json, os, sys, threading, time, shutil, stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t12"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
os.chown(HOME, 1234, 1234)                       # someone other than root, like the Pi's user
os.chown(HOME + "/Pictures", 1234, 1234)
Image.new("RGB", (800, 600), (90, 60, 120)).save(HOME + "/Pictures/old-holiday.jpg")
os.utime(HOME + "/Pictures/old-holiday.jpg", (time.time() - 86400 * 30,) * 2)
open(HOME + "/camera.txt", "w").write("url = 127.0.0.1:5056\n")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [HOME + "/camera.txt"]
    if t["type"] == "photos":
        t["dirs"] = [HOME + "/Pictures"]
import gk_static; gk_static.use_home(g, HOME)

mode = {"v": "new"}       # new PiE-ink / old PiE-ink (no shutter) / paused
log = []


def scene(w, h):
    im = Image.new("RGB", (w, h), (40, 70, 90))
    d = ImageDraw.Draw(im)
    d.rectangle((0, h * 0.78, w, h), fill=(70, 110, 70))
    r = h * 0.18
    d.ellipse((w / 2 - r, h * 0.45 - r, w / 2 + r, h * 0.45 + r), fill=(235, 205, 150))
    b = io.BytesIO(); im.save(b, "JPEG", quality=90); return b.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, ctype="application/json", code=200):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        log.append(("GET", self.path))
        if self.path == "/api/ptz":
            return self.reply({"ok": True, "available": True, "position": {"zoom": 0.1},
                               "follow": {"on": False}, "sleep": {"asleep": False}})
        if self.path == "/api/camera.jpg":
            return self.reply(scene(640, 360), "image/jpeg")
        if self.path.startswith("/api/photos/") and mode["v"] == "new":
            return self.reply(scene(1920, 1080), "image/jpeg")
        self.reply({"ok": False, "error": "not found"}, code=404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        log.append(("POST", self.path, body))
        if self.path == "/api/photos":
            if mode["v"] == "old":
                return self.reply(b"<h1>Not Found</h1>", "text/html", 404)
            if mode["v"] == "paused":
                return self.reply({"ok": False, "error": "the camera is paused for 50 s more"}, code=400)
            time.sleep(0.6)                        # the still takes a moment
            name = "20261011-175501.jpg"
            return self.reply({"ok": True, "photo": {"name": name, "url": f"/api/photos/{name}"}})
        self.reply({"ok": True})


srv = ThreadingHTTPServer(("127.0.0.1", 5056), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

shots = []


class FB:
    w, h = 640, 480
    def show(self, img): shots.append(img.copy())
    def close(self): pass


def wait_for(c, t=10):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


def pump(secs):
    t = time.time()
    while time.time() - t < secs:
        m.tick(); m.flush(); time.sleep(0.05)


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
ci = m.tab_index("camera"); pi = m.tab_index("photos")
m.tab = ci - 1; m.switch_tab(1)
assert wait_for(lambda: m.camera.frame is not None)
pump(0.3)

# 1. the new shutter
m.press("a"); m.press("a")                         # a second press while busy is ignored
pump(0.25); taking = shots[-1]
print("while taking:", m.camera.action, "| footer A:", "Taking…" if m.camera.shooting else "Photo")
assert wait_for(lambda: not m.camera.shooting)
pump(0.3); saved = shots[-1]
pics = sorted(os.listdir(HOME + "/Pictures"))
print("Pictures:", pics)
new = [p for p in pics if p.startswith("camera-")]
assert len(new) == 1 and not any(p.startswith(".") for p in pics)
path = HOME + "/Pictures/" + new[0]
st = os.stat(path)
print("size:", Image.open(path).size, "owner:", st.st_uid, "mode:", oct(st.st_mode & 0o777))
print("toast:", m.msg, "| shutter calls:", len([x for x in log if x[:2] == ("POST", "/api/photos")]))
print("full-size fetch:", [x[1] for x in log if x[0] == "GET" and x[1].startswith("/api/photos/")])

# 2. a second picture in the same second gets its own name
m.camera.shot = None
m.press("a"); assert wait_for(lambda: not m.camera.shooting)
print("two pictures:", sorted(p for p in os.listdir(HOME + "/Pictures") if p.startswith("camera-")))

# 3. the corner picture goes away after a few seconds
m.camera.shot = (m.camera.shot[0], m.camera.shot[1], time.monotonic() - g.CAM_SHOT_SHOW - 0.1)
n = len(shots); pump(0.3)
print("redrawn without the corner picture:", len(shots) > n)

# 4. an older PiE-ink with no shutter: the live picture
mode["v"] = "old"
m.press("a"); assert wait_for(lambda: not m.camera.shooting)
latest = max((HOME + "/Pictures/" + p for p in os.listdir(HOME + "/Pictures")), key=os.path.getmtime)
print("old PiE-ink ->", os.path.basename(latest), Image.open(latest).size, "| action:", repr(m.camera.action))

# 5. PiE-ink says no
mode["v"] = "paused"
m.press("a"); assert wait_for(lambda: not m.camera.shooting)
pump(0.2); refused = shots[-1]
print("paused:", m.camera.action, "| toast cleared:", m.msg is None)

# 6. can't reach it
mode["v"] = "new"
real = m.camera.url; m.camera.url = "http://127.0.0.1:5999"
m.press("a"); assert wait_for(lambda: not m.camera.shooting)
print("unreachable:", m.camera.action)
m.camera.url = real
m.camera.action = ""

# 7. Photos tab: newest first, the last picture taken selected
m.camera.shot = None
m.press("a"); assert wait_for(lambda: not m.camera.shooting)
last = m.last_shot
while m.tab != pi:
    m.press("l")
items = m.tab_items()
print("Photos tab first:", items[0]["title"], "| selected:", items[m.sels[pi]]["title"],
      "| is last taken:", items[m.sels[pi]]["src"] == last, "| count:", len(items))
print("camera stopped on leaving:", not m.camera.running)
time.sleep(3); m.dirty = True; m.flush(); grid = shots[-1]
m.press("a"); m.dirty = True; m.flush(); viewer = shots[-1]
print("viewing:", m.view)

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 2 - 10), (80, 80, 80))
for k, im in enumerate([taking, saved, refused, grid]):
    sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/camera_photo.png")
srv.shutdown()
print("done")

print("ALL OK")   # (got here: every assert above held)
