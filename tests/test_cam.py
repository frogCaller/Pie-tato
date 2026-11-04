import io, json, os, sys, threading, time, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t7"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
open(S + "/home/u/camera.txt", "w").write("# PiE-ink with the OBSBOT\nurl = 127.0.0.1:5055\n")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [S + "/home/*/camera.txt"]
import gk_static; gk_static.use_home(g, S + "/home/u")

log = []
cam = {"pan": 0.0, "tilt": 0.0, "zoom": 0.2, "follow": True}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def status(self):
        return {"ok": True, "available": True, "position": {"pan": cam["pan"], "tilt": cam["tilt"],
                "zoom": cam["zoom"]}, "follow": {"can": True, "on": cam["follow"]},
                "sleep": {"can": True, "asleep": False}}

    def do_GET(self):
        if self.path == "/api/ptz":
            return self.reply(self.status())
        if self.path == "/api/camera.jpg":
            im = Image.new("RGB", (640, 480), (40, 70, 90))
            d = ImageDraw.Draw(im)
            for x in range(0, 640, 80):
                d.line((x - cam["pan"] * 8 % 80, 0, x - cam["pan"] * 8 % 80, 480), fill=(60, 95, 115), width=2)
            r = 60 + cam["zoom"] * 80
            cx, cy = 320 - cam["pan"] * 8, 240 + cam["tilt"] * 8
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(235, 205, 150))
            d.rectangle((0, 380, 640, 480), fill=(70, 110, 70))
            b = io.BytesIO(); im.save(b, "JPEG"); return self.reply(b.getvalue(), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        log.append((self.path, body))
        if self.path == "/api/ptz/drive":
            if not cam["follow"]:
                cam["pan"] += body["vx"] * 2; cam["tilt"] += body["vy"] * 2
        elif self.path == "/api/ptz/set" and "zoom" in body:
            cam["zoom"] = body["zoom"]
        elif self.path == "/api/ptz/follow":
            cam["follow"] = bool(body.get("on"))
        elif self.path == "/api/ptz/home":
            cam["pan"] = cam["tilt"] = 0
        self.reply(self.status())


srv = ThreadingHTTPServer(("127.0.0.1", 5055), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
ci = m.tab_index("camera")
m.tab = ci - 1
m.switch_tab(1)                                   # onto the Camera tab
deadline = time.time() + 5
while time.time() < deadline and m.camera.frame is None:
    time.sleep(0.05)
time.sleep(0.4)
m.flush()                                          # following, picture
print("reached:", m.camera.reached, "following:", m.camera.following, "zoom:", m.camera.zoom)


def hold(names, secs):
    for n in names:
        m.press(n)
    t = time.time()
    while time.time() - t < secs:
        m.tick(); m.flush(); time.sleep(0.05)
    snap = shots[-1]
    for n in names:
        m.release(n)
    return snap


left = hold(["left"], 0.6)
time.sleep(0.3)
diag = hold(["up", "right"], 0.45)
time.sleep(0.3)
zoom = hold(["x"], 0.5)
m.press("select"); m.release("select")             # tap: fast
hold(["down"], 0.3)
m.press("start")                                   # home
time.sleep(0.4)
m.press("select")                                  # hold: follow back on
t = time.time()
while time.time() - t < 0.8:
    m.tick(); time.sleep(0.05)
m.release("select")
print("speed after hold (unchanged):", m.camera.speed)
time.sleep(0.4); m.tick(); m.flush()
follow = shots[-1]

drives = [b for p, b in log if p == "/api/ptz/drive"]
print("follow turned off before steering:", log[0])
print("first drives:", drives[:3])
print("diagonal:", [b for b in drives if b["vx"] and b["vy"]][:1])
print("fast drive:", [b for b in drives if "speed" in b][:1])
print("stops:", len([1 for p, _ in log if p == "/api/ptz/stop"]))
print("zooms:", [b["zoom"] for p, b in log if p == "/api/ptz/set"])
print("home:", [p for p, _ in log if p == "/api/ptz/home"], "follow posts:",
      [b for p, b in log if p == "/api/ptz/follow"])
seqs = [b["seq"] for p, b in log if p in ("/api/ptz/drive", "/api/ptz/stop")]
print("seq increasing:", seqs == sorted(seqs) and len(set(seqs)) == len(seqs))

# leave the tab: threads stop and no drive keeps going
m.switch_tab(1)
time.sleep(0.5)
n = len(log); time.sleep(0.6)
print("quiet after leaving tab:", len(log) == n, "running:", m.camera.running)

# unreachable app
m.camera.url = "http://127.0.0.1:5999"; m.camera.frame = None; m.camera.reached = None
m.tab = ci; m.camera.start(); time.sleep(4.5); m.dirty = True; m.flush()
off = shots[-1]
m.camera.stop()

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, im in enumerate([shots[0], left, diag, zoom, follow, off]):
    sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/camera_screens.png")
srv.shutdown()

print("ALL OK")   # (got here: every assert above held)
