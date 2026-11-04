"""A camera that misbehaves every way it can, for test_hardening.py (run in its own process, so
the memory it uses isn't counted against the test's own). Port as the only argument; it answers on
every 127.0.0.x."""
import io, json, os, sys, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image

buf = io.BytesIO()
Image.new("RGB", (64, 48), (200, 30, 30)).save(buf, "JPEG")
JPEG = buf.getvalue()
buf = io.BytesIO()
Image.frombytes("RGB", (2400, 1800), os.urandom(2400 * 1800 * 3)).save(buf, "JPEG", quality=85)
BIG_JPEG = buf.getvalue()                           # a camera's big picture: a few MB
PORT = int(sys.argv[1])


class Cam(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def head(self, code, ctype, length=None, extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()

    def endless(self, first=b"", piece=b"\0" * 65536, pause=0.0, total=None):
        try:
            self.wfile.write(first)
            sent = 0
            while total is None or sent < total:
                self.wfile.write(piece)
                sent += len(piece)
                if pause:
                    time.sleep(pause)
        except OSError:
            pass

    def do_GET(self):
        p = self.path
        if p == "/ok.jpg":
            self.head(200, "image/jpeg", len(JPEG)); self.wfile.write(JPEG); return
        if p == "/big.jpg":                         # a picture, then 100 MB more
            self.head(200, "image/jpeg"); self.endless(JPEG, total=100 << 20); return
        if p == "/slow.jpg":                        # a byte every 2 s
            self.head(200, "image/jpeg")
            try:
                for i in range(len(JPEG)):
                    self.wfile.write(JPEG[i:i + 1]); self.wfile.flush(); time.sleep(2)
            except OSError:
                pass
            return
        if p == "/stream":                          # MJPEG that never has a picture in it
            self.head(200, "multipart/x-mixed-replace; boundary=frame")
            self.endless(piece=b"--frame\r\n" + b"\0" * 65536, pause=0.05); return
        if p == "/away.jpg":                        # sent to another machine
            self.head(302, "text/plain", 0, [("Location", f"http://127.0.0.2:{PORT}/ok.jpg")]); return
        if p == "/here.jpg":                        # sent elsewhere on itself
            self.head(302, "text/plain", 0, [("Location", "/ok.jpg")]); return
        if p.startswith("/toip.jpg?"):              # a camera added by name, sending us to its address
            ip = urllib.parse.parse_qs(p.split("?", 1)[1])["ip"][0]
            self.head(302, "text/plain", 0, [("Location", f"http://{ip}:{PORT}/ok.jpg")]); return
        if p == "/tome.jpg":                        # sending us to the Pi's own services
            self.head(302, "text/plain", 0, [("Location", "http://127.0.0.1:5480/screen")]); return
        if p == "/photo.jpg":
            self.head(200, "image/jpeg", len(BIG_JPEG))
            try:
                self.wfile.write(BIG_JPEG)
            except OSError:
                pass                                # (a look at what it is hangs up early)
            return
        if p == "/api/ptz":                         # a PiE-ink saying odd things
            body = json.dumps({"available": True, "name": "Porch\ncamera = http://127.0.0.1:5480/x",
                               "follow": "yes", "sleep": 5, "position": {"zoom": float("inf")}}).encode()
            self.head(200, "application/json", len(body)); self.wfile.write(body); return
        if p in ("/huge.json", "/api/tags"):        # an answer that never ends
            self.head(200, "application/json"); self.endless(b'{"models": ["', b"x" * 65536, total=50 << 20); return
        if p == "/api/camera.jpg":
            self.head(200, "image/jpeg", len(JPEG)); self.wfile.write(JPEG); return
        self.head(404, "application/json", 2); self.wfile.write(b"{}")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/photos":              # a picture on another machine
            body = json.dumps({"ok": True, "photo": {"url": f"http://127.0.0.2:{PORT}/ok.jpg"}}).encode()
            self.head(200, "application/json", len(body)); self.wfile.write(body); return
        self.head(404, "application/json", 2); self.wfile.write(b"{}")


srv = ThreadingHTTPServer(("", PORT), Cam)
srv.daemon_threads = True
print("ready", flush=True)
srv.serve_forever()
