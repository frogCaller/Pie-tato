"""The Camera tab's live picture from cameras that don't send steadily (pitato/cameras.py): one whose stream goes
quiet for longer than a few seconds (it sends a picture only when it has a new one); one that ends its stream every
few pictures; one that serves one viewer at a time, while the web page and the bot ask for pictures too; one that
sends a stream while saying it's one picture; and one that goes away for good. The picture stays up while it
connects again ("Reconnecting…" over it, drawn), and "Can't reach this camera" comes only once it's really gone."""
import io, json, os, shutil, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import cameras as C
from PIL import Image, ImageDraw

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(colour):
    b = io.BytesIO()
    Image.new("RGB", (320, 240), colour).save(b, "JPEG")
    return b.getvalue()


RED, BLUE = jpeg((210, 30, 30)), jpeg((30, 30, 210))
conns = {}


def serve(handler_body, threaded=True):
    """A camera on a free port: handler_body(self) answers each request; conns[port] counts connections."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            port = self.server.server_address[1]
            conns[port] = conns.get(port, 0) + 1
            try:
                handler_body(self)
            except (BrokenPipeError, ConnectionResetError):
                pass

    srv = (ThreadingHTTPServer if threaded else HTTPServer)(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def part(h, pic):
    h.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(pic)).encode() + b"\r\n\r\n"
                  + pic + b"\r\n")
    h.wfile.flush()


def stream_head(h, ctype="multipart/x-mixed-replace; boundary=frame"):
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.end_headers()


def watch(addr, kind, url):
    cam = C.Camera()
    cam.cams = [{"addr": addr, "name": "Desk"}]
    cam.listen = lambda: None
    cam.known[C.cam_key(addr)] = {"kind": kind, "url": url, "name": "", "server": ""}
    cam.select(addr)
    cam.start()
    return cam


def watched(cam, secs, every=0.1):
    """What the screen would show, looked at every so often for secs: [(a picture up, reached, stale)]."""
    out, end = [], time.monotonic() + secs
    while time.monotonic() < end:
        out.append((cam.frame is not None, cam.reached, cam.stale))
        time.sleep(every)
    return out


# 1. a stream that goes quiet for 6 s between pictures (a camera that sends one only when it has a new one)
def quiet(h):
    stream_head(h)
    for pic in (RED, BLUE, RED):
        part(h, pic)
        time.sleep(6)


s1 = serve(quiet)
p1 = s1.server_address[1]
cam = watch(f"127.0.0.1:{p1}", "mjpeg", f"http://127.0.0.1:{p1}/")
seen = watched(cam, 8.5)
check(f"a stream quiet for 6 s at a time: the picture stays up ({sum(1 for s in seen if not s[0])} looks without "
      f"one, after the first), never \"can't reach\", one connection ({conns.get(p1)}), the second picture came",
      all(s[0] for s in seen[10:]) and not any(s[1] is False for s in seen) and conns.get(p1) == 1
      and cam.raw is not None and cam.raw.getpixel((5, 5))[2] > 150)
check("...no \"Reconnecting…\" over it: it's only slow, still connected", not any(s[2] for s in seen))
cam.stop()

# 1b. a camera that drops, and turns everyone away for 4 s, then streams again
away = [0.0, 0]


def drops(h):
    if time.monotonic() < away[0]:
        h.send_response(503)
        h.end_headers()
        return
    away[1] += 1
    stream_head(h)
    for k in range(15 if away[1] == 1 else 300):      # (the first time: it drops after a moment)
        part(h, (RED, BLUE)[k % 2])
        time.sleep(0.1)
    away[0] = time.monotonic() + 4.0


s1b = serve(drops)
p1b = s1b.server_address[1]
cam = watch(f"127.0.0.1:{p1b}", "mjpeg", f"http://127.0.0.1:{p1b}/")
seen = watched(cam, 10)
back = next((i for i in range(len(seen) - 1, -1, -1) if seen[i][2]), None)
check(f"a camera that drops and turns it away a few seconds: the last picture stays up, \"Reconnecting…\" over it "
      f"({sum(1 for s in seen if s[2])} looks), gone once pictures come again "
      f"({(len(seen) - 1 - back) * 0.1 if back is not None else '-'} s before the end), never \"can't reach\"",
      all(s[0] for s in seen[10:]) and back is not None and not any(s[1] is False for s in seen)
      and not seen[-1][2] and away[1] >= 2)
cam.stop()

# 2. a stream that ends every three pictures: connected again at once, the picture always up
def short(h):
    stream_head(h)
    for pic in (RED, BLUE, RED):
        part(h, pic)
        time.sleep(0.2)


s2 = serve(short)
p2 = s2.server_address[1]
cam = watch(f"127.0.0.1:{p2}", "mjpeg", f"http://127.0.0.1:{p2}/")
time.sleep(1.0)
seen = watched(cam, 4)
check(f"a stream that ends every few pictures: connected again each time ({conns.get(p2)} connections), the "
      f"picture always up, never stale or \"can't reach\"",
      conns.get(p2, 0) >= 4 and all(s[0] and s[1] is not False and not s[2] for s in seen))
cam.stop()

# 3. one viewer at a time (not threaded), streaming steadily; the web page and the bot want pictures meanwhile
def steady(h):
    stream_head(h)
    for k in range(600):
        part(h, (RED, BLUE)[k % 2])
        time.sleep(0.05)


s3 = serve(steady, threaded=False)
p3 = s3.server_address[1]
addr3 = f"127.0.0.1:{p3}"
cam = watch(addr3, "mjpeg", f"http://{addr3}/")
time.sleep(1.0)
t0 = time.monotonic()
snaps = [cam.snapshot(addr3, max_age=1.5) for _ in range(5)]
photo = cam.photo_of(addr3)
took = time.monotonic() - t0
seen = watched(cam, 1.5)
check(f"one viewer at a time: the web page's pictures and the bot's photo are the live one's ({took:.2f} s, "
      f"{conns.get(p3)} connection), and the live picture carries on",
      all(snaps) and photo and conns.get(p3) == 1 and took < 0.5 and all(s[0] and not s[2] for s in seen))
cam.stop()

# 4. a stream that says it's one picture (image/jpeg, no length): a picture from it each time
def liar(h):
    stream_head(h, "image/jpeg")
    for k in range(200):
        h.wfile.write((RED, BLUE)[k % 2])
        h.wfile.flush()
        time.sleep(0.05)


s4 = serve(liar)
p4 = s4.server_address[1]
got = C.cam_detect(f"127.0.0.1:{p4}")
cam = watch(f"127.0.0.1:{p4}", got["kind"], got["url"])
time.sleep(2.0)
at1 = cam.frame_at
time.sleep(1.0)
check(f"a stream that says it's one picture: found ({got['kind']}), and its pictures come "
      f"({conns.get(p4)} asked, new ones keep coming)", cam.frame is not None and cam.frame_at > at1
      and conns.get(p4, 0) >= 4)
cam.stop()

# 5. gone for good: the last picture with "Reconnecting…", then "can't reach" (here after 2 s, not 20)
C.CAM_LOST = 2.0
on5 = [True]


def until_off(h):
    stream_head(h)
    while on5[0]:
        part(h, RED)
        time.sleep(0.05)


s5 = serve(until_off)
p5 = s5.server_address[1]
cam = watch(f"127.0.0.1:{p5}", "mjpeg", f"http://127.0.0.1:{p5}/")
time.sleep(1.0)
s5.shutdown(); s5.server_close(); on5[0] = False
seen = watched(cam, 9, every=0.2)
first_gone = next((i for i, s in enumerate(seen) if s[1] is False), None)
check(f"gone for good: the picture up a while (\"Reconnecting…\" over it), then \"can't reach\" "
      f"({first_gone * 0.2 if first_gone is not None else '-'} s)",
      seen[0][0] and first_gone is not None and first_gone * 0.2 >= 1.5 and any(s[2] for s in seen[:first_gone])
      and not seen[-1][0] and seen[-1][1] is False)
cam.stop()
C.CAM_LOST = 20.0

# ---- the Camera tab draws "Reconnecting…" over the last picture --------------------------------------------------
S = SP + "/t_cam_live"
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
open(HOME + "/camera.txt", "w").write(f"camera = 127.0.0.1:{p1}   Desk\n")
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
m = g.Media(); m.enter()
ci = next(k for k, t in enumerate(g.LIBRARY) if t["type"] == "camera")
m.open_app(ci)
cam = m.camera
cam.stop()
cam.cams = [{"addr": f"127.0.0.1:{p1}", "name": "Desk"}]
cam.select(f"127.0.0.1:{p1}")                     # (not running: nothing connects)
m.cam_list = False
with cam.lock:
    cam.raw = cam.frame = Image.new("RGB", (320, 240), (200, 40, 40))
    cam.frame_at, cam.reached = time.monotonic(), True
texts.clear(); m.dirty = True; m.flush()
fresh = list(texts)
cam.frame_at, cam.connecting = time.monotonic() - 5, True
changed = cam.stale_changed()
texts.clear(); m.dirty = True; m.flush()
FB.last.save(SP + "/cam_reconnecting.png")
check(f"the Camera tab: \"Reconnecting…\" over the last picture once it's old (and not before), the screen told "
      f"to draw it ({changed})", "Reconnecting…" not in fresh and "Reconnecting…" in texts and changed
      and FB.last.getpixel((320, 300))[0] > 150)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
