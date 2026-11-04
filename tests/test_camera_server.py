"""camera.py against a pretend camera (camtest/bin: v4l2-ctl and ffmpeg making a test pattern)."""
import io, json, os, shutil, sys, threading, time, urllib.request, urllib.error
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/camtest/home"
shutil.rmtree(H, ignore_errors=True)
os.makedirs(H)
os.environ["HOME"] = H
os.environ["PATH"] = SP + "/camtest/bin:" + os.environ["PATH"]
STATE = SP + "/camtest/v4l2.json"
for f in (STATE, STATE + ".log", SP + "/camtest/ffmpeg.log"):
    if os.path.exists(f):
        os.remove(f)
os.environ["FAKE_V4L2_STATE"] = STATE
os.environ["FAKE_FFMPEG_LOG"] = SP + "/camtest/ffmpeg.log"
os.environ["PITATO_STATIC"] = H                 # where setup.sh says the static folder is
open(H + "/camera-server.txt", "w").write("# test\nname = Garage\ndevice = /dev/video0\nsize = 640x480\nfps = 10\n")
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import camera
from PIL import Image
assert camera.CONF_FILE == H + "/camera-server.txt", camera.CONF_FILE
camera.IDLE = 3
PORT = 5491
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


feed = camera.Feed()
feed.configure()
ptz = camera.Ptz(feed)
ptz.find()
shutter = camera.Shutter(feed)
server = camera.serve(feed, ptz, shutter, port=PORT)
threading.Thread(target=server.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"


def get(path, headers=None, raw=True, timeout=15):
    req = urllib.request.Request(B + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type")


def post(path, body, headers=None, ctype="application/json"):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def v4l2():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


# the picture
t0 = time.time()
code, data, ctype = get("/api/camera.jpg")
im = Image.open(io.BytesIO(data)) if code == 200 else None
check(f"a picture: {code} {ctype} {im.size if im else None} in {time.time() - t0:.1f}s",
      code == 200 and ctype == "image/jpeg" and im.size == (640, 480))
check("ffmpeg was asked for MJPEG as it comes", "-input_format mjpeg" in open(SP + "/camtest/ffmpeg.log").read()
      and "-c:v copy" in open(SP + "/camtest/ffmpeg.log").read())
code, d2, _ = get("/api/camera.jpg")
check("the next one is quick and new", code == 200 and d2 != data)

# what it is
code, info, _ = get("/api/ptz")
info = json.loads(info)
check(f"/api/ptz: available {info.get('available')}, has {info.get('position', {}).get('has')}, server {info.get('server')}",
      info["available"] and info["position"]["has"] == {"pan": True, "tilt": True, "zoom": True}
      and info["server"] == "Pitato camera" and info["name"] == "Garage" and info["follow"]["can"] is False)

# steering: right for a while, then it stops by itself
for seq in range(1, 6):
    post("/api/ptz/drive", {"vx": 1, "vy": 0, "sid": "t", "seq": seq})
    time.sleep(0.15)
time.sleep(1.2)
pan = v4l2().get("pan_absolute", 0)
check(f"held right: panned to {pan / 3600:.1f}° (60°/s for ~0.75 s + heartbeat, a busy machine's slowness too)",
      30 * 3600 <= pan <= 100 * 3600)
time.sleep(0.6)
check("and stopped when the presses stopped", v4l2().get("pan_absolute") == pan)
check("pan and tilt went together", all("tilt_absolute=" in ln for ln in open(STATE + ".log").read().split() if "pan_absolute=" in ln))
code, r = post("/api/ptz/drive", {"vx": 1, "vy": 0, "sid": "t", "seq": 3})
check("an old message can't start it again", code == 200 and not ptz.driver)

# never too far down
for seq in range(10, 40):
    post("/api/ptz/drive", {"vx": 0, "vy": -1, "sid": "t", "seq": seq, "speed": 180})
    time.sleep(0.1)
time.sleep(1)
tilt = v4l2().get("tilt_absolute", 0)
check(f"down as far as it goes: {tilt / 3600:.0f}° (not below -30°)", tilt == -30 * 3600)

# zoom and home
code, r = post("/api/ptz/set", {"zoom": 0.5})
check(f"zoom to half: {v4l2().get('zoom_absolute')} ({r.get('position', {}).get('zoom')})",
      code == 200 and v4l2().get("zoom_absolute") == 50 and r["position"]["zoom"] == 0.5)
code, r = post("/api/ptz/home", {})
st = v4l2()
check(f"home: {st}", code == 200 and st["pan_absolute"] == 0 and st["tilt_absolute"] == 0 and st["zoom_absolute"] == 0)
code, r = post("/api/ptz/follow", {"on": True})
check(f"follow: {code} {r.get('error')}", code == 400 and r["error"] == "This camera can't follow you")

# a picture taken: the biggest size
t0 = time.time()
code, r = post("/api/photos", {"filter": "none"})
check(f"photo: {code} {r.get('photo')} in {time.time() - t0:.1f}s", code == 200 and r["photo"]["url"].startswith("/api/photos/"))
code, big, ctype = get(r["photo"]["url"])
check(f"it's the camera's biggest: {Image.open(io.BytesIO(big)).size}", code == 200 and Image.open(io.BytesIO(big)).size == (1920, 1080))
code, data, _ = get("/api/camera.jpg")
check("the live picture comes back after", code == 200 and Image.open(io.BytesIO(data)).size == (640, 480))

# the stream, as a browser sees it
req = urllib.request.urlopen(B + "/api/camera/stream", timeout=15)
check("stream type", req.headers.get("Content-Type").startswith("multipart/x-mixed-replace"))
parts = []
for jpeg in camera.read_parts(req):
    parts.append(jpeg)
    if len(parts) == 3:
        break
req.close()
check(f"stream: {len(parts)} pictures", len(parts) == 3 and all(p[:2] == b"\xff\xd8" for p in parts))
code, page, ctype = get("/")
check("a page to look at it", code == 200 and b"/api/camera/stream" in page and b"Garage" in page)

# other sites and made-up names are turned away
check("a made-up name: 403", get("/api/camera.jpg", {"Host": "evil.example:5491"})[0] == 403)
check("this Pi's name: fine", get("/api/ptz", {"Host": f"{__import__('socket').gethostname()}.local:5491"})[0] == 200)
check("another site's page: 403", get("/api/camera.jpg", {"Sec-Fetch-Site": "cross-site"})[0] == 403)
check("a form post from anywhere: 415", post("/api/ptz/home", {}, ctype="application/x-www-form-urlencoded")[0] == 415)
check("another site's POST: 403", post("/api/ptz/home", {}, {"Sec-Fetch-Site": "cross-site"})[0] == 403)

# nobody watching: the camera is let go
time.sleep(camera.IDLE + 3)
check("let go when nobody watches", not feed.running())

# a camera that only sends raw pictures
feed.stop()
os.environ["FAKE_NO_MJPEG"] = "1"
feed.mjpeg, feed.jpeg, feed.failed_at = True, None, -1e9
code, data, _ = get("/api/camera.jpg")
log = open(SP + "/camtest/ffmpeg.log").read().splitlines()
check(f"raw only: {code}, last ffmpeg: ...{log[-1][-60:]}", code == 200 and "-c:v mjpeg" in log[-1])
feed.stop()
del os.environ["FAKE_NO_MJPEG"]

# no camera at all
os.environ["FAKE_NO_CAMERA"] = "1"
feed.mjpeg, feed.jpeg, feed.failed_at = True, None, -1e9
t0 = time.time()
code, body, _ = get("/api/camera.jpg")
check(f"no camera: {code} {json.loads(body).get('error')!r} in {time.time() - t0:.1f}s", code == 503 and time.time() - t0 < 3)
n_before = len(open(SP + "/camtest/ffmpeg.log").read().splitlines())
for _ in range(8):
    get("/api/camera.jpg")
    time.sleep(1)
n_after = len(open(SP + "/camtest/ffmpeg.log").read().splitlines())
check(f"...and it doesn't hammer ffmpeg ({n_after - n_before} more tries in 8 s)", n_after - n_before <= 4)
del os.environ["FAKE_NO_CAMERA"]
feed.stop()
server.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
