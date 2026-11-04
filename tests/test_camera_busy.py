"""camera.py after the review: a camera busy for a moment stays on MJPEG (no raw pictures for
good), the stop calls don't pile up, JSON only by its exact type, numbers that don't fit get an
answer, and a name the router gives the Pi can go in hosts =."""
import http.client, json, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
D = SP + "/t57"
shutil.rmtree(D, ignore_errors=True)
os.makedirs(D + "/home")
os.environ["HOME"] = D + "/home"
os.environ["PATH"] = SP + "/review3/busybin:" + SP + "/camtest/bin:" + os.environ["PATH"]
os.environ["REAL_FAKE"] = SP + "/camtest/bin/ffmpeg"
os.environ["BUSY_ONCE"] = D + "/busy.mark"
os.environ["FAKE_V4L2_STATE"] = D + "/v4l2.json"
os.environ["FAKE_FFMPEG_LOG"] = D + "/ffmpeg.log"
open(os.environ["BUSY_ONCE"], "w").close()
open(os.environ["FAKE_FFMPEG_LOG"], "w").close()
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import camera as c
c.CONF_FILE = D + "/home/camera-server.txt"
c.find_camera = lambda want="": ("/dev/video0", "OBSBOT Tiny 2")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- busy for a moment ---------------------------------------------------------------------
f = c.Feed()
t0 = time.monotonic()
jpeg, _ = f.frame(timeout=15)
check(f"busy: said at once ({f.error!r}), still MJPEG", jpeg is None and "busy" in (f.error or "") and f.mjpeg)
while jpeg is None and time.monotonic() - t0 < 12:
    time.sleep(0.5)
    jpeg, _ = f.frame(timeout=3)
check(f"...a picture {time.monotonic() - t0:.1f} s later, MJPEG as it comes", jpeg is not None and f.mjpeg)
runs = open(os.environ["FAKE_FFMPEG_LOG"]).read().splitlines()
check(f"every ffmpeg run was MJPEG ({len(runs)})", runs and all("-input_format mjpeg" in r for r in runs))
f.stop()
check("stopped: ffmpeg gone", not f.running())
for _ in range(3):                                   # stop and start again, straight away
    f.want(); f.stop()
jpeg, _ = f.frame(timeout=10)
check("stop, start, stop...: a picture again, still MJPEG", jpeg is not None and f.mjpeg)
f.stop()

# ---- requests ------------------------------------------------------------------------------
PORT = 18096
ptz = c.Ptz(f)
srv = c.serve(f, ptz, c.Shutter(f), port=PORT)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(path, body, ctype="application/json", host="127.0.0.1", extra=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"Content-Type": ctype, "Host": host}
    h.update(extra or {})
    try:
        conn.request("POST", path, body=data, headers=h)
        r = conn.getresponse()
        return r.status, r.read()[:120]
    except Exception as ex:
        return "no answer", repr(ex)[:80]
    finally:
        conn.close()


def get(path, host):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    conn.request("GET", path, headers={"Host": host})
    try:
        return conn.getresponse().status
    finally:
        conn.close()


check("a form's type with json in it: 415", post("/api/ptz/stop", {"sid": "a"}, "text/plain; x=json")[0] == 415)
check("JSON with its charset: fine", post("/api/ptz/stop", {"sid": "a"}, "application/json; charset=utf-8")[0] == 200)
for i in range(400):
    post("/api/ptz/stop", {"sid": f"{i:06d}" + "x" * 6000, "seq": 1})
sizes = [len(k) for k in ptz.seqs]
check(f"400 stops from 400 remotes: {len(ptz.seqs)} kept, the longest {max(sizes)} long",
      len(ptz.seqs) <= 50 and max(sizes) <= 64)
st = post("/api/ptz/stop", b'{"sid": "z", "seq": 1e999}')
check(f"seq = 1e999: an answer {st}", st[0] == 400)
st = post("/api/ptz/set", b'{"zoom": NaN}')
check(f"zoom = NaN: an answer {st[0]}", st[0] in (200, 400))
me = socket.gethostname()
check("this Pi's name, and .fritz.box", get("/api/status", f"{me}.local:{PORT}") == 200
      and get("/api/status", f"{me}.fritz.box:{PORT}") == 200)
check("a name it doesn't know: 403", get("/api/status", f"garage-cam.lan:{PORT}") == 403)
with open(c.CONF_FILE, "w") as fh:
    fh.write("hosts = garage-cam.lan, cam2.home.example\n")
check("...in hosts =: fine", get("/api/status", f"garage-cam.lan:{PORT}") == 200
      and get("/api/status", f"cam2.home.example:{PORT}") == 200 and get("/api/status", f"evil.example:{PORT}") == 403)
srv.shutdown()
f.stop()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
