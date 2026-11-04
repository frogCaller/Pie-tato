"""Any camera at a typed address (pitato/cameras.py's cam_detect): pretend cameras the way people's own scripts
and cameras serve them. A Flask-style script (its page with <img src="/video_feed">, the stream there); one that
answers one at a time (http.server, not threaded, a relative <img src>); a picture its page's script loads; a
stream that says it's something else; a stream at a usual path with no page; a page with a logo before the stream;
nothing at the port; a port that answers but has no camera. Then the Camera tab watching the Flask-style one."""
import io, os, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from pitato import cameras as C
from PIL import Image

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(colour):
    b = io.BytesIO()
    Image.new("RGB", (320, 240), colour).save(b, "JPEG")
    return b.getvalue()


PIC = jpeg((200, 40, 40))
LOGO = jpeg((10, 10, 10))
hits = {}


def make(routes, threaded=True):
    """A server on a free port: routes {path: (kind, what)}; kind "page" (html), "mjpeg" (a stream, with its
    content type), "jpeg" (one picture), "raw" (bytes as they are, with a content type)."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            port = self.server.server_address[1]
            hits.setdefault(port, []).append(self.path)
            got = routes.get(self.path) or routes.get(self.path.split("?")[0] + "?*")
            if not got:
                self.send_response(404)
                self.end_headers()
                return
            kind, what = got[0], got[1]
            try:
                if kind == "page":
                    body = what.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif kind == "jpeg":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(what)))
                    self.end_headers()
                    self.wfile.write(what)
                elif kind == "mjpeg":
                    ctype = got[2] if len(got) > 2 else "multipart/x-mixed-replace; boundary=frame"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.end_headers()
                    for _ in range(400):                  # (a stream: on until the viewer goes)
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + what + b"\r\n")
                        self.wfile.flush()
                        time.sleep(0.05)
                elif kind == "json":
                    body = what.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    srv = (ThreadingHTTPServer if threaded else HTTPServer)(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def detect(addr):
    t0 = time.monotonic()
    got = C.cam_detect(addr)
    return got, time.monotonic() - t0


# 1. a Flask-style script: its page shows the stream, which is at /video_feed
flask = make({"/": ("page", '<html><body><h1>My webcam</h1><img src="/video_feed" width="640"></body></html>'),
              "/video_feed": ("mjpeg", PIC)})
got, secs = detect(f"127.0.0.1:{flask}")
check(f"a script's page with the stream on it: {got and got['kind']} at {got and got['url']} ({secs:.1f} s)",
      got and got["kind"] == "mjpeg" and got["url"] == f"http://127.0.0.1:{flask}/video_feed" and secs < 5)

# 2. a script that answers one at a time (http.server, not threaded), its picture a link next to the page
lone = make({"/": ("page", '<img src="stream.mjpg" />'), "/index.html": ("page", '<img src="stream.mjpg" />'),
             "/stream.mjpg": ("mjpeg", PIC)}, threaded=False)
got, secs = detect(f"127.0.0.1:{lone}")
check(f"...one that answers one at a time, a link next to its page: {got and got['url']} ({secs:.1f} s)",
      got and got["kind"] == "mjpeg" and got["url"].endswith("/stream.mjpg"))

# 3. a picture its page's script puts in (refreshed), at a path no list would have
snap = make({"/": ("page", '<img id="v"><script>setInterval(() => { v.src = "/grab/now.jpg?t=" + Date.now() }, 200)'
                           '</script>'), "/grab/now.jpg?*": ("jpeg", PIC)})
got, secs = detect(f"127.0.0.1:{snap}")
check(f"...a picture its page's script loads: {got and got['kind']} at {got and got['url']}",
      got and got["kind"] == "jpeg" and "/grab/now.jpg" in got["url"])

# 4. a stream that says it's something else (application/octet-stream)
odd = make({"/": ("mjpeg", PIC, "application/octet-stream")})
got, secs = detect(f"127.0.0.1:{odd}")
check(f"...a stream that doesn't say it is one: {got and got['kind']}", got and got["kind"] == "mjpeg")

# 5. no page, the stream at one of the usual places
usual = make({"/videostream.cgi": ("mjpeg", PIC)})
got, secs = detect(f"127.0.0.1:{usual}")
check(f"...no page, the stream at a usual place: {got and got['url']} ({secs:.1f} s)",
      got and got["url"].endswith("/videostream.cgi") and secs < 8)

# 6. a page with a logo first, then the stream: the stream
both = make({"/": ("page", '<img src="/static/logo.jpg"><div><img src="/live/cam1"></div>'),
             "/static/logo.jpg": ("jpeg", LOGO), "/live/cam1": ("mjpeg", PIC)})
got, secs = detect(f"127.0.0.1:{both}")
check(f"...a page with a logo before the stream: the stream ({got and got['url']})",
      got and got["kind"] == "mjpeg" and got["url"].endswith("/live/cam1"))

# 7. nothing at the port: no, quickly
s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
got, secs = detect(f"127.0.0.1:{free}")
check(f"nothing at the port: {got}, in {secs:.1f} s", got is None and secs < 4)

# 8. something answers there, but it isn't a camera
api = make({"/": ("json", '{"hello": "world"}'), "/api/ptz": ("json", '{"x": 1}')})
got, secs = detect(f"127.0.0.1:{api}")
check(f"something that isn't a camera: {got}, in {secs:.1f} s (it tried {len(hits.get(api, []))} places)",
      got is None and secs < 10 and len(hits.get(api, [])) >= len(C.CAM_PATHS))

# 9. a link straight to the stream, and one to the page: both
got, _ = detect(f"http://127.0.0.1:{flask}/video_feed")
got2, _ = detect(f"127.0.0.1:{lone}/index.html")
check(f"a link to the stream ({got and got['kind']}), or to the page ({got2 and got2['url']})",
      got and got["kind"] == "mjpeg" and got2 and got2["url"].endswith("/stream.mjpg"))

# the picture helpers
check("a page's pictures, the likely ones: <img>, <video>, a quoted link; not scripts or styles",
      C.page_links('<link href="/a.css"><script src="/app.js"></script><img src="cam.jpg"><video src="/v.mjpg">'
                   '<script>u = "/feed/1"; t = "hello"</script>', "http://h:1/x/")
      == ["http://h:1/x/cam.jpg", "http://h:1/v.mjpg", "http://h:1/feed/1"])
check("what it sends, from its first bytes", C.sniffed(b"--b\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff", None)
      == "mjpeg" and C.sniffed(b"\xff\xd8\xff\xe0", "1234") == "jpeg" and C.sniffed(b"\xff\xd8\xff\xe0", None)
      == "mjpeg" and C.sniffed(b"<html>", None) is None)

# ---- the Camera tab, watching the Flask-style one -------------------------------------------------------------------
cam = C.Camera()
cam.cams = [{"addr": f"127.0.0.1:{flask}", "name": "Desk"}]
cam.running = True
cam.listen = lambda: None
cam.select(f"127.0.0.1:{flask}")
cam.begin()
end = time.time() + 10
while time.time() < end and cam.frame is None:
    time.sleep(0.1)
px = cam.frame.getpixel((10, 10)) if cam.frame is not None else None
check(f"the Camera tab shows its live picture: {cam.kind}, {cam.frame and cam.frame.size}, colour {px}",
      cam.kind == "mjpeg" and cam.frame is not None and px[0] > 150 and px[1] < 90)
cam.stop()
snapped = cam.snapshot(f"127.0.0.1:{lone}")
check(f"...and a small picture of the one-at-a-time one for the list: {snapped and snapped[1].size}",
      snapped is not None and snapped[1].size[0] <= 64)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
