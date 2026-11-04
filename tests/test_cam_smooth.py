"""The Camera tab's live picture, smooth (pitato/cameras.py, pitato/screens/camera.py, media mode's loop): a camera
streaming 30 pictures a second is shown about 15 a second on a Pi 4 (8 on a slower Pi), evenly, each drawn as soon
as it comes (the main loop's woken: not at its next tick); just the picture's part of the screen is written, the
picture made its size on the camera's thread, and it looks the same as the whole page drawn afresh; anything else
that changes (a notice, "Reconnecting…") draws the whole page; a Pi's camera with a stream (camera.py's) is watched,
not fetched picture by picture, and one without is fetched as before."""
import io, json, os, selectors, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import cameras as C
from PIL import Image, ImageChops

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(k):
    im = Image.new("RGB", (640, 480), ((k * 37) % 256, (k * 91) % 256, 120))
    b = io.BytesIO(); im.save(b, "JPEG", quality=80); return b.getvalue()


PICS = [jpeg(k) for k in range(30)]
hits = {}


class Cam(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    rate = 30

    def log_message(self, *a):
        pass

    def do_GET(self):
        hits[self.path] = hits.get(self.path, 0) + 1
        if self.path in ("/stream", "/api/camera/stream") and not (self.path.startswith("/api") and self.server.no_stream):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            k, t0 = 0, time.monotonic()
            try:
                while not self.server.done:
                    pic = PICS[k % len(PICS)]
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(pic)
                                     + pic + b"\r\n")
                    self.wfile.flush()
                    k += 1
                    time.sleep(max(0.0, t0 + k / Cam.rate - time.monotonic()))
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path == "/api/camera/stream" and self.server.no_stream == "page":
            body = b"<!doctype html><title>PiE-ink</title><p>Its own page, for any path</p>"
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if self.path == "/api/camera.jpg":
            body = PICS[hits[self.path] % len(PICS)]
            self.send_response(200); self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if self.path == "/api/ptz":
            body = json.dumps({"ok": True, "available": False}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        self.send_response(404); self.end_headers()


def serve(no_stream=False):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Cam)
    srv.daemon_threads, srv.done, srv.no_stream = True, False, no_stream
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


S = SP + "/t_cam_smooth"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480

    def __init__(self):
        self.shown, self.last = [], None      # (when, "all" or the box)

    def show(self, img):
        self.last = img.copy()
        self.shown.append((time.monotonic(), "all"))

    def show_part(self, img, box):
        self.last = img.copy()
        self.shown.append((time.monotonic(), tuple(box)))

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media(); m.enter()
ci = next(k for k, t in enumerate(g.LIBRARY) if t["type"] == "camera")


def watch(addr, kind, url, secs, server=""):
    """The Camera tab on that camera, with media mode's loop running as app.run does it, for secs."""
    open(HOME + "/camera.txt", "w").write(f"camera = {addr}   Desk\n")
    m.open_app(ci)
    cam = m.camera
    cam.stop()
    cam.cams = [{"addr": addr, "name": "Desk"}]
    cam.known[C.cam_key(addr)] = {"kind": kind, "url": url, "name": "", "server": server}
    cam.addr = ""
    cam.select(addr)
    m.cam_list = False
    m.dirty = True
    cam.start()
    m.fb.shown.clear()
    sel = selectors.DefaultSelector()
    sel.register(m.wake_r, selectors.EVENT_READ, "wake")
    end = time.monotonic() + secs
    came = []                                  # when each new picture was ready, and when it was drawn
    real_frame = m.camera_frame

    def frame_came():
        came.append([time.monotonic(), None])
        real_frame()
    cam.on_frame = frame_came
    while time.monotonic() < end:
        for key, _ in sel.select(m.tick_limit()):
            m.woken()
        m.tick()
        n = len(m.fb.shown)
        m.flush()
        if len(m.fb.shown) > n:
            for c in came:
                if c[1] is None:
                    c[1] = m.fb.shown[-1][0]
    sel.close()
    cam.on_frame = real_frame
    return cam, came


# ---- a stream of 30 a second: about 15 shown, evenly, each at once ---------------------------------------------------
s1 = serve()
p1 = s1.server_address[1]
cam, came = watch(f"127.0.0.1:{p1}", "mjpeg", f"http://127.0.0.1:{p1}/stream", 4.0)
shown = [t for t, what in m.fb.shown]
late = sorted(c[1] - c[0] for c in came[3:] if c[1] is not None)
gaps = [b - a for a, b in zip(shown[5:], shown[6:])]
rate = (len(shown) - 6) / (shown[-1] - shown[5]) if len(shown) > 10 else 0
check(f"30 pictures a second: about 15 shown a second ({rate:.1f})", 12 <= rate <= 17)
check(f"...evenly: none more than a little apart ({max(gaps) * 1000:.0f} ms at most)", gaps and max(gaps) < 0.13)
check(f"...each drawn as soon as it's ready, not at the loop's next tick ({late[len(late) // 2] * 1000:.0f} ms usually, "
      f"{late[-1] * 1000:.0f} ms at most)", late and late[len(late) // 2] < 0.02 and late[-1] < 0.08)
parts = [what for t, what in m.fb.shown if what != "all"]
top, bottom = m.HEADER + 1, m.fb.h - m.FOOTER
check(f"...just the picture's part of the screen written ({len(parts)} of {len(shown)}: {parts[:1]})",
      len(parts) >= len(shown) * 0.8 and all(p == (0, top, m.fb.w, bottom) for p in parts))
fit = cam.fitted
check(f"...the picture made its size on the camera's thread ({fit[1].size if fit and fit[1] else None})",
      fit and fit[0] is cam.frame and fit[1].size == C.fit_size(640, 480, (m.fb.w, bottom - top)))
# the same as the whole page drawn afresh
cam.stop()
time.sleep(0.2)
m.cam_base = (m.cam_base[0], time.monotonic(), m.cam_base[2])
m.render_camera(picture_only=True)
quick = m.fb.last
m.render_camera()
whole = m.fb.last
diff = ImageChops.difference(quick, whole).getbbox()
check(f"...it looks the same as the whole page drawn afresh ({diff})", diff is None)
# a notice: the whole page
m.toast("Saved to Pictures", 3)
m.flush()
check(f"a notice: the whole page drawn ({m.fb.shown[-1][1]})", m.fb.shown[-1][1] == "all")
m.msg = None

# ---- a slower Pi: about 8 a second -------------------------------------------------------------------------------
C.slow_pi = lambda: True
cam, came = watch(f"127.0.0.1:{p1}", "mjpeg", f"http://127.0.0.1:{p1}/stream", 3.0)
shown = [t for t, what in m.fb.shown]
rate = (len(shown) - 4) / (shown[-1] - shown[3]) if len(shown) > 8 else 0
check(f"a slower Pi: about 8 a second ({rate:.1f})", 6 <= rate <= 9)
C.slow_pi = lambda: False
cam.stop()

# ---- a Pi's camera: its stream when it has one (camera.py's), its picture fetched when it hasn't (PiE-ink's) --------
hits.clear()
cam, came = watch(f"127.0.0.1:{p1}", "pie", f"http://127.0.0.1:{p1}", 2.5, server="Pitato camera")
shown = len(m.fb.shown)
check(f"a Pi's camera with a stream: watched ({hits.get('/api/camera/stream')} connection, "
      f"{hits.get('/api/camera.jpg', 0)} picture fetched: the list's small one, {shown} shown)",
      hits.get("/api/camera/stream") == 1 and hits.get("/api/camera.jpg", 0) <= 1 and shown >= 25)
cam.stop()
s2 = serve(no_stream=True)
p2 = s2.server_address[1]
hits.clear()
cam, came = watch(f"127.0.0.1:{p2}", "pie", f"http://127.0.0.1:{p2}", 2.5, server="Pitato camera")
check(f"...one without: asked once, then its picture fetched a few times a second ({hits.get('/api/camera/stream')}, "
      f"{hits.get('/api/camera.jpg', 0)})", hits.get("/api/camera/stream") == 1 and 7 <= hits.get("/api/camera.jpg", 0) <= 12
      and cam.frame is not None)
cam.stop()
s2b = serve(no_stream="page")
p2b = s2b.server_address[1]
hits.clear()
cam, came = watch(f"127.0.0.1:{p2b}", "pie", f"http://127.0.0.1:{p2b}", 2.5, server="Pitato camera")
check(f"...one with a web page there instead: asked once, then fetched ({hits.get('/api/camera/stream')}, "
      f"{hits.get('/api/camera.jpg', 0)})", hits.get("/api/camera/stream") == 1 and 7 <= hits.get("/api/camera.jpg", 0) <= 12
      and cam.frame is not None)
cam.stop()
hits.clear()
cam, came = watch(f"127.0.0.1:{p1}", "pie", f"http://127.0.0.1:{p1}", 2.5, server="PiE-ink")
check(f"a PiE-ink: its picture fetched, as ever, never its stream ({hits.get('/api/camera/stream')}, "
      f"{hits.get('/api/camera.jpg', 0)})", not hits.get("/api/camera/stream") and 7 <= hits.get("/api/camera.jpg", 0) <= 12)
cam.stop()

# ---- the stream stops: "Reconnecting…" over the last picture, the whole page drawn -----------------------------------
C.CAM_STALE = 1.0
texts = []
from PIL import ImageDraw
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
s3 = serve()
p3 = s3.server_address[1]
open(HOME + "/camera.txt", "w").write(f"camera = 127.0.0.1:{p3}   Desk\n")
m.open_app(ci)
cam = m.camera
cam.stop()
cam.cams = [{"addr": f"127.0.0.1:{p3}", "name": "Desk"}]
cam.known[C.cam_key(f"127.0.0.1:{p3}")] = {"kind": "mjpeg", "url": f"http://127.0.0.1:{p3}/stream", "name": "",
                                          "server": ""}
cam.addr = ""
cam.select(f"127.0.0.1:{p3}")
m.cam_list = False
cam.start()
end = time.monotonic() + 1.0
while time.monotonic() < end:
    m.tick(); m.flush(); time.sleep(0.02)
s3.done = True
s3.shutdown(); s3.server_close()
end = time.monotonic() + 4.0
texts.clear()
while time.monotonic() < end and "Reconnecting…" not in texts:
    m.tick(); m.flush(); time.sleep(0.05)
check(f"the stream stops: \"Reconnecting…\" over the last picture ({m.fb.shown[-1][1]})",
      "Reconnecting…" in texts and m.fb.shown[-1][1] == "all" and cam.frame is not None)
cam.stop()
ImageDraw.ImageDraw.text = real_text
for s in (s1, s2, s2b):
    s.done = True
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
