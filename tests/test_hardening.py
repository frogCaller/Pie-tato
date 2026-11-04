"""The independent review's findings, fixed in gpi_keys: cameras that send too much, too slowly or
nothing at all, redirects, beacons of every kind, the web page and the Pi's own addresses,
settings files that are links (or pipes), names with new lines in them, chatter that isn't a
number, Ollama's address and answer. The camera that misbehaves (bad_cam.py) runs in its own
process, so the memory measured here is gpi_keys' own."""
import io, json, os, resource, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t56"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.chown(HOME, 1000, 1000)                     # someone's home folder, as on a Pi (this runs as root)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []
P = 18191
B = f"127.0.0.1:{P}"
_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_s.connect(("10.255.255.255", 1))
ME = _s.getsockname()[0]                       # this machine on the network (not 127.x)
_s.close()
real_gai = socket.getaddrinfo


def fake_gai(host, *a, **k):                   # two names: one made to point at the Pi itself
    host = {"rebind.test": "127.0.0.1", "cam.test": ME}.get(host, host)
    return real_gai(host, *a, **k)


socket.getaddrinfo = fake_gai


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


class FB:
    w, h = 640, 480

    def show(self, img):
        pass

    def close(self):
        pass


bad = subprocess.Popen([sys.executable, SP + "/bad_cam.py", str(P)], stdout=subprocess.PIPE)
assert bad.stdout.readline().strip() == b"ready"
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
cam = m.camera

# ---- what a camera sends ---------------------------------------------------------------------
m0, t0 = rss(), time.time()
got = cam.snapshot(f"http://{B}/big.jpg")
check(f"a picture that never ends (a stream that says it's one picture): its first picture, in "
      f"{time.time() - t0:.1f} s, without the 100 MB after it, +{rss() - m0} MB here",
      got is not None and got[1].size[0] <= 64 and len(got[0]) < 1_000_000 and time.time() - t0 < 5
      and rss() - m0 < 40)
cam.thumbs.clear()
t0 = time.time()
got = cam.snapshot(f"http://{B}/slow.jpg")
check(f"one that trickles: given up after {time.time() - t0:.0f} s (6 s each read, 12 s in all)",
      got is None and time.time() - t0 < 20)
t0 = time.time()
got = cam.snapshot(f"http://{B}/stream")
check(f"MJPEG with no picture in it: given up after {time.time() - t0:.0f} s",
      got is None and time.time() - t0 < 15 and cam.known.get(f"http://{B}/stream".split("//")[1])["kind"] == "mjpeg")
try:
    g.cam_json(f"http://{B}/huge.json")
    check("an answer that never ends: refused", False)
except ValueError as ex:
    check(f"an answer that never ends: refused ({ex})", True)


def pictures():
    return sum(1 for t in threading.enumerate() if t.name == "cam-picture" and t.is_alive())


cam.cams = [{"addr": f"http://{B}/stream", "name": ""}]
cam.select(f"http://{B}/stream")
cam.start()
time.sleep(2.5)
check(f"watching it: {pictures()} picture thread", pictures() == 1)
cam.stop()
time.sleep(1.5)
check(f"...the Camera tab closed: none left ({pictures()})", pictures() == 0)
cam.select("")

got = cam.snapshot(f"http://{ME}:{P}/tome.jpg")
check("a camera that sends us on to the Pi's own services: not followed", got is None)
got = cam.snapshot(f"http://{B}/here.jpg")
check("...elsewhere on itself: followed", got is not None and got[1].size[0] > 0)
got = cam.snapshot(f"http://cam.test:{P}/toip.jpg?ip={ME}")
check("...one added by name, to its own address: followed", got is not None)
got = cam.snapshot(f"http://rebind.test:{P}/ok.jpg")
check("a name that turns out to be the Pi itself: refused when it connects", got is None)
got = cam.snapshot(f"http://localhost:{P}/ok.jpg")
check("...localhost, by name, is fine (a camera on this Pi)", got is not None)
got = cam.snapshot(f"http://{B}/photo.jpg")
small = Image.open(io.BytesIO(got[0])) if got else None
check(f"a big picture (several MB): a smaller copy kept, "
      f"{len(got[0]) // 1000 if got else '?'} KB, {small.size if small else '?'}",
      got is not None and len(got[0]) <= g.CAM_KEEP_MAX and max(small.size) <= 1280)

# ---- a PiE-ink that says odd things ----------------------------------------------------------
found = g.cam_detect(B)
check(f"its name on one line: {found['name']!r}", found["kind"] == "pie" and "\n" not in found["name"])
cam.cams = [{"addr": B, "name": ""}]
fi = m.tab_index("camera")
m.open_app(fi)
cam.select(B)
cam.kind, cam.url = "pie", "http://" + B
cam.refresh(cam.gen, cam.url)
check(f"odd answers made safe: follow {cam.info['follow']}, sleep {cam.info['sleep']}, zoom {cam.zoom}",
      cam.info["follow"] == {} and cam.info["sleep"] == {} and cam.zoom == 1.0 and cam.reached)
m.cam_list = False
try:
    m.dirty = True; m.flush()
    check("...and the Camera tab draws", True)
except Exception as ex:
    check(f"...and the Camera tab draws ({ex!r})", False)
try:
    cam.photo_bytes()
    check("a picture from another machine: refused", False)
except ValueError as ex:
    check(f"a picture from another machine: refused ({ex})", "somewhere else" in str(ex))
cam.stop()
gen_a = cam.gen
cam.select("10.1.2.3")
jpeg = io.BytesIO(); Image.new("RGB", (32, 24), "red").save(jpeg, "JPEG")
cam.show(gen_a, jpeg.getvalue())
check("a picture for the camera before doesn't land on this one", cam.frame is None)
cam.select("")

# ---- beacons ---------------------------------------------------------------------------------
g.CAM_BEACON = 18195
cam.found.clear()
cam.listening = False
cam.listen()
time.sleep(0.3)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for junk in (b'{"pie":1,"caps":"x"}', b'{"gpicam":1,"port":1e999}', b'{"gpicam":1,"port":true}', b"not json",
             b"[1, 2]", b'{"gpicam":1,"port":{"a":1}}', b"\xff\xfe", b'{"pie":1,"port":-4}'):
    tx.sendto(junk, ("127.0.0.1", 18195))
tx.sendto(json.dumps({"gpicam": 1, "port": "5433", "name": "Porch\ncamera = http://127.0.0.1:5480/x"}).encode(),
          ("127.0.0.1", 18195))
time.sleep(0.5)
alive = [t for t in threading.enumerate() if t.name == "cam-beacon" and t.is_alive()]
f = cam.found.get("127.0.0.1:5433")
check(f"bad beacons don't stop it hearing ({len(alive)} listening, heard {f and f['name']!r})",
      alive and f and f["name"] == "Porch camera = http://127.0.0.1:5480/x")
for port in range(20000, 20040):
    tx.sendto(json.dumps({"gpicam": 1, "port": port}).encode(), ("127.0.0.1", 18195))
time.sleep(0.8)
check(f"40 more: only the newest {len(cam.found)} kept", len(cam.found) == g.CAM_FOUND_KEEP)
cam.thumbs["gone:1"] = (b"x", None, time.time()); cam.known["gone:1"] = {}; cam.missing["gone:1"] = 1.0
cam.tidy()
check("what was known about a camera that's gone is let go",
      "gone:1" not in cam.thumbs and "gone:1" not in cam.known and "gone:1" not in cam.missing)

# ---- the web page and the Pi's own addresses ---------------------------------------------------
for addr in ("127.0.0.1:5480/screen", "localhost:5433", "http://[::1]:5000", "0.0.0.0:5000",
             "http://127.0.0.1:18092/secret.png", socket.gethostname() + ":5000"):
    out = m.web_camera({"do": "add", "addr": addr})
    check(f"the web page can't add {addr}: {out.get('error', '')[:40]!r}", "error" in out)
out = m.web_camera({"do": "add", "addr": "192.168.1.50", "name": "Shed\ncamera = 127.0.0.1:5480"})
txt = open(HOME + "/camera.txt").read()
check("...a camera on your network it can, its name on one line",
      out.get("ok") and "camera = 192.168.1.50   Shed camera = 127.0.0.1:5480\n" in txt
      and [c["addr"] for c in g.read_cameras(g.LIBRARY[fi]["files"])] == ["192.168.1.50"])
m.web_camera({"do": "remove", "addr": "192.168.1.50"})
t0 = time.time()
out = m.web_camera({"do": "add", "addr": f"rebind.test:{P}/ok.jpg"})
check(f"a name is added without looking it up ({time.time() - t0:.2f} s)...", out.get("ok") and time.time() - t0 < 0.5)
check("...but if it's the Pi itself, no picture comes back", m.web_camframe(f"rebind.test:{P}/ok.jpg") is None)
m.web_camera({"do": "remove", "addr": f"rebind.test:{P}/ok.jpg"})

# ---- settings files: root edits them without following links into somewhere private ------------
st = os.stat(HOME + "/camera.txt")
check(f"camera.txt is yours: uid {st.st_uid}, {oct(st.st_mode & 0o777)}", st.st_uid == 1000 and st.st_mode & 0o777 == 0o644)
secret = S + "/secret.txt"
with open(secret, "w") as f:
    f.write("camera = 10.9.9.9   SECRET\npassword = hunter2\n")
os.chmod(secret, 0o600)
os.remove(HOME + "/camera.txt")
os.symlink(secret, HOME + "/camera.txt")
try:
    g.edit_cameras(add="10.0.0.9")
    why = None
except OSError as ex:
    why = str(ex)
check(f"a link to a root-only file: not copied into yours ({why})",
      why and os.path.islink(HOME + "/camera.txt") and "hunter2" in open(secret).read()
      and not any("hunter2" in open(os.path.join(HOME, n), errors="ignore").read()
                  for n in os.listdir(HOME) if not os.path.islink(os.path.join(HOME, n))
                  and os.path.isfile(os.path.join(HOME, n))))
os.remove(HOME + "/camera.txt")
with open(HOME + "/camera.txt", "w") as f:
    f.write("camera = 10.0.0.1   Garage\ncamera = 10.0.0.2   Porch\n")
os.chmod(HOME + "/camera.txt", 0o600)                # made with sudo: root's, and only root's
try:
    g.edit_cameras(add="10.0.0.3")
    why = None
except OSError as ex:
    why = str(ex)
check(f"one only root can read: left as it is, and said ({why})",
      why and open(HOME + "/camera.txt").read() == "camera = 10.0.0.1   Garage\ncamera = 10.0.0.2   Porch\n")
mine = S + "/mine.txt"
with open(mine, "w") as f:
    f.write("# my cameras\ncamera = 10.0.0.1   Door\n")
os.chown(mine, 1000, 1000); os.chmod(mine, 0o600)
os.remove(HOME + "/camera.txt")
os.symlink(mine, HOME + "/camera.txt")
g.edit_cameras(add="10.0.0.2")
txt = open(HOME + "/camera.txt").read()
check("a link to a file of yours: kept what's in it", "camera = 10.0.0.1   Door" in txt and "10.0.0.2" in txt)
os.remove(HOME + "/camera.txt")
os.mkfifo(HOME + "/camera.txt")
t0 = time.time()
try:
    g.edit_cameras(add="10.0.0.3")
    why = None
except OSError as ex:
    why = str(ex)
check(f"a pipe in its place doesn't hang it ({time.time() - t0:.1f} s, {why})", time.time() - t0 < 2 and why)
os.remove(HOME + "/camera.txt")
os.symlink(secret, HOME + "/friend.txt")
try:
    g.edit_config("friend.txt", {"server": "10.0.0.5"}, head=g.FRIEND_HEAD)
    why = None
except OSError as ex:
    why = str(ex)
check("friend.txt the same", why and os.path.islink(HOME + "/friend.txt"))
os.remove(HOME + "/friend.txt")
g.edit_config("friend.txt", {"server": "10.0.0.5\nmodel = evil"}, head=g.FRIEND_HEAD)
txt = open(HOME + "/friend.txt").read()
st = os.stat(HOME + "/friend.txt")
check("...a value on one line, and the file yours",
      "server = 10.0.0.5 model = evil" in txt and "\nmodel" not in txt and st.st_uid == 1000)
p = g.write_setting("note.txt", "x", private=True)
check("a private one: only yours", oct(os.stat(p).st_mode & 0o777) == "0o600" and os.stat(p).st_uid == 1000)
was = g.STATIC
g.STATIC = HOME + "/gpi-media/static"                 # the gpi-media folder gone: nothing made as root
try:
    g.write_setting("radio.txt", "x")
    check("no gpi-media folder: not made", False)
except OSError as ex:
    check(f"no gpi-media folder: not made ({ex.strerror})", not os.path.exists(HOME + "/gpi-media"))
os.makedirs(HOME + "/gpi-media"); os.chown(HOME + "/gpi-media", 1000, 1000)
p = g.write_setting("radio.txt", "Jazz | http://x\n")      # its static folder not there yet: made, and yours
check(f"the static folder made when it isn't there, yours: {p}", p == g.STATIC + "/radio.txt"
      and os.stat(g.STATIC).st_uid == 1000 and os.stat(p).st_uid == 1000 and open(p).read() == "Jazz | http://x\n")
g.STATIC = was
w = g.STATIC
g.STATIC = HOME + "/odd [1] *"                        # a folder name that's a pattern of its own
os.makedirs(g.STATIC); open(g.STATIC + "/bot.txt", "w").write("server = 10.0.0.9\n")
check("a static folder with [ ] * in its name is still read", g.read_config([g.settings_glob("bot.txt")]).get("server") == "10.0.0.9")
g.STATIC = w

# ---- chatter, whatever is in friend.txt --------------------------------------------------------
fr = m.friend
want = {"inf": 30, "nan": 30, "-inf": 30, "1e308": 1440, "-5": 0, "abc": 30, "never": 0, "45": 45, "2000": 1440}
got = {}
for v in want:
    with open(HOME + "/friend.txt", "w") as f:
        f.write(f"server = 127.0.0.1:1\nmodel = x\nchatter = {v}\n")
    fr.load(m.friend_files())
    got[v] = fr.chatter()
check(f"chatter: {got}", got == want)
with open(HOME + "/friend.txt", "w") as f:
    f.write("server = 127.0.0.1:1\nmodel = x\nchatter = inf\n")
m.open_app(m.tab_index("friend"))
try:
    m.tick(); m.dirty = True; m.flush()
    m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.set_page = "friend"; m.dirty = True; m.flush()
    check("chatter = inf: media mode carries on", True)
except Exception as ex:
    check(f"chatter = inf: media mode carries on ({ex!r})", False)

# ---- Ollama: a machine and a port, and an answer of a sensible size ------------------------------
urls = {"http://10.0.0.2:11434/api/x?y=1#z": "http://10.0.0.2:11434", "pc.local": "http://pc.local:11434",
        "[fe80::1]:11500": "http://[fe80::1]:11500", "https://ai.lan/": "https://ai.lan:11434", "": "", "http://": ""}
got = {k: g.ollama_url(k) for k in urls}
check(f"Ollama's address: {got}", got == urls)
t0 = time.time()
try:
    g.ollama_models(B)
    check("an answer that never ends: refused", False)
except ValueError as ex:
    check(f"an answer that never ends: refused in {time.time() - t0:.1f} s ({str(ex)[:40]}…)", time.time() - t0 < 10)

bad.kill()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
