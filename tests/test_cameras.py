"""The Camera tab with several cameras: a pretend PiE-ink, the real camera.py (with the pretend
camera from camtest/bin), an MJPEG link and a JPEG link; the list, adding by address, removing,
and a camera heard on the network."""
import io, json, os, shutil, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t50"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.makedirs(S + "/camhome")
open(S + "/camhome/camera-server.txt", "w").write("name = Garage\ndevice = /dev/video0\nfps = 10\n")
os.environ["PATH"] = SP + "/camtest/bin:" + os.environ["PATH"]
os.environ["FAKE_V4L2_STATE"] = S + "/v4l2.json"
os.environ["FAKE_FFMPEG_LOG"] = S + "/ffmpeg.log"
sys.path.append(ROOT)
sys.path.insert(0, TESTS)
import pietato_all as g
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import camera as camserver
from PIL import Image, ImageDraw
camserver.CONF_FILE = S + "/camhome/camera-server.txt"

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [S + "/home/*/camera.txt"]
import gk_static; gk_static.use_home(g, HOME)
CAM_FILES = [S + "/home/*/camera.txt"]
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- a pretend PiE-ink on 127.0.0.1:5055 ----------------------------------------------------
log = []
pie = {"pan": 0.0, "tilt": 0.0, "zoom": 0.2, "follow": True}


class PieInk(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def status(self):
        return {"ok": True, "available": True, "position": {"pan": pie["pan"], "tilt": pie["tilt"], "zoom": pie["zoom"]},
                "follow": {"can": True, "on": pie["follow"]}, "sleep": {"can": True, "asleep": False}}

    def do_GET(self):
        if self.path == "/api/ptz":
            return self.reply(self.status())
        if self.path == "/api/status":
            return self.reply({"hostname": "pie-zero", "modes": []})
        if self.path == "/api/camera.jpg":
            im = Image.new("RGB", (640, 480), (40, 70, 90))
            d = ImageDraw.Draw(im)
            cx, cy = 320 - pie["pan"] * 8, 240 + pie["tilt"] * 8
            d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill=(235, 205, 150))
            d.rectangle((0, 380, 640, 480), fill=(70, 110, 70))
            b = io.BytesIO(); im.save(b, "JPEG"); return self.reply(b.getvalue(), "image/jpeg")
        if self.path.startswith("/api/photos/"):
            b = io.BytesIO(); Image.new("RGB", (1280, 720), (200, 60, 60)).save(b, "JPEG")
            return self.reply(b.getvalue(), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        log.append((self.path, body))
        if self.path == "/api/ptz/drive" and not pie["follow"]:
            pie["pan"] += body["vx"] * 2; pie["tilt"] += body["vy"] * 2
        elif self.path == "/api/ptz/set" and "zoom" in body:
            pie["zoom"] = body["zoom"]
        elif self.path == "/api/ptz/follow":
            pie["follow"] = bool(body.get("on"))
        elif self.path == "/api/photos":
            return self.reply({"ok": True, "photo": {"url": "/api/photos/p1.jpg"}})
        self.reply(self.status())


pie_srv = ThreadingHTTPServer(("127.0.0.1", 5055), PieInk)
threading.Thread(target=pie_srv.serve_forever, daemon=True).start()

# ---- the real camera.py on port 5492 (every 127.x address) ---------------------------------
feed = camserver.Feed(); feed.configure()
ptz = camserver.Ptz(feed); ptz.find()
cam_srv = camserver.serve(feed, ptz, camserver.Shutter(feed), port=5492)
threading.Thread(target=cam_srv.serve_forever, daemon=True).start()
g.CAM_PORTS = (5055, 5492)
g.CAM_LINKS = []                       # (nothing else is listening here)

# ---- the file, the addresses ---------------------------------------------------------------
check("an address", g.cam_address(" 192.168.1.50 ") == "192.168.1.50")
check("with a port", g.cam_address("192.168.1.50:5000") == "192.168.1.50:5000")
check("a name", g.cam_address("garage.local") == "garage.local")
check("a link", g.cam_address("http://192.168.1.70:81/stream") == "http://192.168.1.70:81/stream")
check("not addresses", all(g.cam_address(x) is None for x in
                          ("", "hello world", "ftp://x/y", "192.168.1.5:99999", "http://", "<b>", "javascript:alert(1)", "file:///etc/passwd")))
open(HOME + "/camera.txt", "w").write("# PiE-ink with the OBSBOT\nurl = 127.0.0.1:5055\n")
check("the earlier url = still works", g.read_cameras(CAM_FILES) == [{"addr": "127.0.0.1:5055", "name": ""}])
open(HOME + "/camera.txt", "w").write("ip = 10.0.0.5\nport = 5001\n")
check("...and ip = with port =", g.read_cameras(CAM_FILES) == [{"addr": "10.0.0.5:5001", "name": ""}])
g.edit_cameras(remove="10.0.0.5:5001")
check(f"taking the ip/port one out: {open(HOME + '/camera.txt').read()!r}", g.read_cameras(CAM_FILES) == [])
open(HOME + "/camera.txt", "w").write("# PiE-ink with the OBSBOT\nurl = 127.0.0.1:5055\n"
                                      "camera = 127.0.0.2   Garage\n"
                                      "camera = http://127.0.0.1:5492/api/camera/stream  Living room stream\n")
cams = g.read_cameras(CAM_FILES)
check(f"three cameras: {[c['name'] for c in cams]}",
      [c["addr"] for c in cams] == ["127.0.0.1:5055", "127.0.0.2", "http://127.0.0.1:5492/api/camera/stream"]
      and cams[2]["name"] == "Living room stream")

# ---- what answers where ----------------------------------------------------------------------
got = g.cam_detect("127.0.0.1:5055")
check(f"PiE-ink: {got}", got and got["kind"] == "pie" and got["name"] == "pie-zero" and got["server"] == "PiE-ink")
got = g.cam_detect("127.0.0.2")
check(f"camera.py by its address alone: {got}", got and got["kind"] == "pie" and got["url"].endswith(":5492")
      and got["name"] == "Garage" and got["server"] == "Pitato camera")
got = g.cam_detect("http://127.0.0.1:5492/api/camera/stream")
check(f"an MJPEG link: {got and got['kind']}", got and got["kind"] == "mjpeg")
got = g.cam_detect("127.0.0.1:5492/api/camera.jpg")
check(f"a JPEG link: {got and got['kind']}", got and got["kind"] == "jpeg")
t0 = time.time()
check("nothing there", g.cam_detect("127.0.0.9:5999") is None and time.time() - t0 < 8)

# ---- the Camera tab ----------------------------------------------------------------------------
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
m.switch_tab(1)


def settle(cond, secs=8):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def hold(names, secs):
    for n in names:
        m.press(n)
    t = time.time()
    while time.time() - t < secs:
        m.tick(); m.flush(); time.sleep(0.05)
    for n in names:
        m.release(n)
    m.tick(); m.flush()


cam = m.camera
check("opens on your first camera's picture", not m.cam_list and cam.addr == "127.0.0.1:5055")
check(f"PiE-ink's picture: {cam.kind}", settle(lambda: cam.frame is not None and cam.info))
pie_view = shots[-1]
check(f"named after the Pi: {cam.title!r}, {cam.place()}", cam.title == "pie-zero" and cam.place() == (1, 3))
hold(["left"], 0.5)
drives = [b for p, b in log if p == "/api/ptz/drive"]
check(f"steering PiE-ink: follow off first, then {len(drives)} drives", log[0] == ("/api/ptz/follow", {"on": False}) and drives)
time.sleep(0.4)
check("...and a stop when let go", log[-1][0] == "/api/ptz/stop" or any(p == "/api/ptz/stop" for p, _ in log[-3:]))
m.press("a")
check("a picture from PiE-ink's shutter", settle(lambda: cam.shot is not None and not cam.shooting))
pics = os.listdir(HOME + "/Pictures")
check(f"...into Pictures: {pics}", len(pics) == 1 and Image.open(HOME + "/Pictures/" + pics[0]).size == (1280, 720))

# R: the next camera (camera.py)
m.press("r")
check(f"R: the next camera, {cam.addr}", cam.addr == "127.0.0.2" and m.state.get("camera") == "127.0.0.2")
check("camera.py's picture", settle(lambda: cam.frame is not None and cam.kind == "pie" and cam.info))
check(f"it turns, can't follow: available {cam.available}, can_follow {cam.can_follow}", cam.available and not cam.can_follow)
garage_view = shots[-1]
before = json.load(open(S + "/v4l2.json")).get("pan_absolute", 0) if os.path.exists(S + "/v4l2.json") else 0
hold(["right"], 0.6)
time.sleep(0.3)
after = json.load(open(S + "/v4l2.json")).get("pan_absolute", 0)
check(f"steering camera.py's camera: pan {before} -> {after}", after > before)
m.press("select")
settle(lambda: False, 0.9)
m.release("select")
check(f"hold SELECT: {cam.action!r}", cam.action == "This camera can't follow you" and not cam.following)
m.press("a")
check("a picture from camera.py", settle(lambda: cam.shot is not None and cam.shot[1] != HOME + "/Pictures/" + pics[0]
                                         and not cam.shooting, 15))
newest = max(os.listdir(HOME + "/Pictures"), key=lambda f: os.path.getmtime(HOME + "/Pictures/" + f))
check(f"...at the camera's biggest: {Image.open(HOME + '/Pictures/' + newest).size}",
      Image.open(HOME + "/Pictures/" + newest).size == (1920, 1080))

# R: an MJPEG link
m.press("r")
check("an MJPEG stream's picture", settle(lambda: cam.frame is not None and cam.kind == "mjpeg"))
m.press("left")
m.release("left")
check(f"the d-pad on a camera that doesn't turn: {cam.action!r}", cam.action == "This camera doesn't turn")
n_pics = len(os.listdir(HOME + "/Pictures"))
m.press("a")
check("A keeps the picture on screen", settle(lambda: len(os.listdir(HOME + "/Pictures")) == n_pics + 1 and not cam.shooting))
stream_view = shots[-1]
m.press("r")
check("R from the last: back to the first", cam.addr == "127.0.0.1:5055")

# B: the list
m.press("b")
check("B: your cameras", m.cam_list and not cam.running)
check("small pictures of each", settle(lambda: len(cam.thumbs) >= 3 and not cam.scanning, 15))
rows = m.cam_rows()
check(f"the list: {[k for k, _ in rows]}", [k for k, _ in rows] == ["cam", "cam", "cam", "add"])
list_view = shots[-1]

# add one by typing its address
m.press("down"); m.press("down"); m.press("down")
check("down to 'Add a camera…'", rows[m.cam_sel][0] == "add")
m.press("a")
check("A: the keyboard, on the digits", m.view == "keys" and m.kb["r"] == 0)
keys_view = (m.dirty or True) and (m.flush() or shots[-1])
for ch in "hello world":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check(f"not an address: {m.msg!r}", m.msg and "isn't an address" in m.msg and m.view == "list")
m.press("a")
for ch in "http://127.0.0.1:5492/api/camera.jpg":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check("a typed link goes in camera.txt", "camera = http://127.0.0.1:5492/api/camera.jpg" in open(HOME + "/camera.txt").read())
check("...the rest of the file as it was", open(HOME + "/camera.txt").read().startswith("# PiE-ink with the OBSBOT\nurl = 127.0.0.1:5055\n"))
check("...and its picture is on", not m.cam_list and settle(lambda: cam.frame is not None and cam.kind == "jpeg"))
check(f"it's 4 of 4: {cam.place()}", cam.place() == (4, 4))

# take it out again
m.press("b")
rows = m.cam_rows()
m.cam_sel = 3
m.press("x")
check(f"X once asks: {m.msg!r}", m.msg and "Press X again" in m.msg and "camera.jpg" in open(HOME + "/camera.txt").read())
m.press("x")
check("X twice: gone from camera.txt", "camera.jpg" not in open(HOME + "/camera.txt").read() and len(cam.cams) == 3)

# one heard on the network
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("127.0.0.3", 0))
s.sendto(json.dumps({"gpicam": 1, "id": "x", "host": "shed", "name": "Shed", "port": 5492}).encode(), ("127.0.0.1", g.CAM_BEACON))
s.sendto(json.dumps({"pie": 1, "id": "y", "host": "nocam", "port": 5000, "caps": {"camera": False}}).encode(), ("127.0.0.1", g.CAM_BEACON))
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s2.bind(("127.0.0.1", 0))
s2.sendto(json.dumps({"gpicam": 1, "id": "z", "host": "me", "name": "Mine", "port": 5492}).encode(), ("127.0.0.1", g.CAM_BEACON))
check("heard on the network", settle(lambda: any(f["name"] == "Shed" for f in cam.found_list())))
names = [f["name"] for f in cam.found_list()]
check(f"only the new one with a camera: {names}", names == ["Shed"])
rows = m.cam_rows()
check(f"listed under 'On your network': {[k for k, _ in rows]}", [k for k, _ in rows][-2:] == ["label", "found"])
m.cam_sel = 3
m.press("down")
check("down skips the heading", rows[m.cam_sel][0] == "found")
check("it gets its small picture too", settle(lambda: g.cam_key("127.0.0.3:5492") in cam.thumbs, 10))
m.dirty = True; m.flush()
found_view = shots[-1]
m.press("a")
check("A on it: added, named, on screen", "camera = 127.0.0.3:5492   Shed" in open(HOME + "/camera.txt").read()
      and cam.addr == "127.0.0.3:5492" and not m.cam_list)
check("its picture", settle(lambda: cam.frame is not None))

# leaving the tab stops everything
m.switch_tab(1)
time.sleep(0.6)
n = len(log)
time.sleep(0.8)
check("quiet after leaving the tab", len(log) == n and not cam.running)

# just one camera: L R are for the tabs, as before
open(HOME + "/camera.txt", "w").write("url = 127.0.0.1:5055\n")
m2 = g.Media(); m2.load_fonts(); m2.fb = FB(); m2.active = True
m2.state["camera"] = "127.0.0.2"
m2.tab = m2.tab_index("camera") - 1
m2.switch_tab(1)
check("one camera: its picture", not m2.cam_list and m2.camera.addr == "127.0.0.1:5055")
m2.press("r")
check("R goes to the next tab", m2.tab_type() != "camera" and not m2.camera.running)
m2.camera.stop()

# no cameras: the list, with a word on what to add
os.remove(HOME + "/camera.txt")
m3 = g.Media(); m3.load_fonts(); m3.fb = FB(); m3.active = True
m3.tab = m3.tab_index("camera") - 1
m3.switch_tab(1)
m3.flush()
check("no cameras: the list, with 'Add a camera…'", m3.cam_list and [k for k, _ in m3.cam_rows()][0] == "add")
empty_view = shots[-1]
m3.camera.stop()
m.camera.stop()

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 4 - 10), (80, 80, 80))
for k, im in enumerate([pie_view, garage_view, stream_view, list_view, found_view, keys_view, empty_view]):
    sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/cameras_sheet.png")
feed.stop()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
