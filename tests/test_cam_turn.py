"""A camera on its side: its picture rotated 90° at a time (Y on a plain camera's picture, Y on any camera in
the list, the web page's rotate button), kept for next time; the live picture, the list's small pictures,
photos taken, what the bot sees and the web page's pictures all rotated; a camera that turns steered the way
its rotated picture shows; a camera taken out and added again the right way up."""
import io, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
S = SP + "/tcamturn"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import cameras as CM
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [S + "/home/*/camera.txt"]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


COLOURS = {"red": (230, 30, 30), "green": (30, 200, 60), "blue": (40, 60, 220), "white": (240, 240, 240)}


def quarters_picture(w=640, h=480):
    """Red top left, green top right, blue bottom left, white bottom right."""
    im = Image.new("RGB", (w, h))
    for (x, y), c in (((0, 0), "red"), ((1, 0), "green"), ((0, 1), "blue"), ((1, 1), "white")):
        im.paste(COLOURS[c], (x * w // 2, y * h // 2, (x + 1) * w // 2, (y + 1) * h // 2))
    return im


def quarters(im):
    """The colours at its quarters' middles: (top left, top right, bottom left, bottom right)."""
    im = im.convert("RGB")
    w, h = im.size
    out = []
    for fx, fy in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
        px = im.getpixel((int(w * fx), int(h * fy)))
        out.append(min(COLOURS, key=lambda c: sum((a - b) ** 2 for a, b in zip(COLOURS[c], px))))
    return tuple(out)


UPRIGHT = ("red", "green", "blue", "white")
TURNED = {0: UPRIGHT, 90: ("blue", "red", "white", "green"), 180: ("white", "blue", "green", "red"),
          270: ("green", "white", "red", "blue")}


def jpeg(im, q=92):
    b = io.BytesIO(); im.save(b, "JPEG", quality=q); return b.getvalue()


# ---- turning a picture --------------------------------------------------------------------------------------
pic = quarters_picture()
got = {d: quarters(CM.turn_picture(pic, d)) for d in (0, 90, 180, 270)}
check(f"a picture rotated clockwise, a quarter at a time ({got})", got == TURNED)
check("...90 and 270: on its side (480x640)", CM.turn_picture(pic, 90).size == (480, 640)
      and CM.turn_picture(pic, 270).size == (480, 640) and CM.turn_picture(pic, 180).size == (640, 480))
data = jpeg(pic)
t90 = CM.turn_file(data, 90)
check("a JPEG rotated: still a JPEG, on its side, the right way", Image.open(io.BytesIO(t90)).format == "JPEG"
      and Image.open(io.BytesIO(t90)).size == (480, 640) and quarters(Image.open(io.BytesIO(t90))) == TURNED[90])
b = io.BytesIO(); pic.save(b, "PNG")
tp = CM.turn_file(b.getvalue(), 270)
check("a PNG stays a PNG", Image.open(io.BytesIO(tp)).format == "PNG" and quarters(Image.open(io.BytesIO(tp))) == TURNED[270])
check("not rotated, or not a picture: the same bytes", CM.turn_file(data, 0) is data and CM.turn_file(b"nope", 90) == b"nope"
      and CM.turn_file(data, 45) is data)

# ---- two cameras: a plain one (a JPEG link) and one that turns (a pretend PiE-ink) ----------------------------
log = []


class Cams(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        if port == 5071 and self.path == "/snap.jpg":
            return self.reply(jpeg(pic), "image/jpeg")
        if port == 5072:
            if self.path == "/api/ptz":
                return self.reply({"ok": True, "available": True, "position": {"pan": 0, "tilt": 0, "zoom": 0.3},
                                   "follow": {"can": True, "on": False}, "sleep": {"can": True, "asleep": False},
                                   "name": "Turner"})
            if self.path == "/api/camera.jpg":
                return self.reply(jpeg(pic), "image/jpeg")
            if self.path.startswith("/api/photos/"):
                return self.reply(jpeg(quarters_picture(1280, 960)), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        log.append((self.path, body))
        if self.path == "/api/photos":
            return self.reply({"ok": True, "photo": {"url": "/api/photos/p1.jpg"}})
        self.reply({"ok": True})


for port in (5071, 5072):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Cams)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
g.CAM_PORTS = (5072,)
g.CAM_LINKS = []
SIDE, TURNER = "http://127.0.0.1:5071/snap.jpg", "127.0.0.1:5072"
open(HOME + "/camera.txt", "w").write(f"camera = {SIDE}   Side camera\ncamera = {TURNER}   Turner\n")

shots, footers = [], []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
real_footer = m.footer
m.footer = lambda d, items, *a, **k: (footers.append([tuple(i[:2]) for i in items]), real_footer(d, items, *a, **k))[1]
ci = m.tab_index("camera")
m.tab = ci - 1
m.switch_tab(1)
cam = m.camera


def settle(cond, secs=8):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def screen_picture_box(img):
    """Where the camera's picture is on the screen: (left, top, right, bottom) of its colours."""
    a = img.convert("RGB")
    xs, ys = [], []
    for y in range(60, 420, 4):
        for x in range(0, 640, 4):
            px = a.getpixel((x, y))
            if px in COLOURS.values() or (abs(px[0] - 230) < 12 and px[1] < 50 and px[2] < 50):
                xs.append(x); ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


check("the plain camera's picture, the right way up as it comes", settle(lambda: cam.frame is not None and cam.kind == "jpeg")
      and cam.addr == SIDE and quarters(cam.frame) == UPRIGHT)
m.dirty = True; m.flush()
check(f"...Y Rotate among its keys ({footers[-1]})", ("Y", "Rotate") in footers[-1])
m.press("y")
check(f"Y: rotated 90° ({cam.turn_of(SIDE)}, {m.msg!r})", cam.turn_of(SIDE) == 90 and m.msg == "Side camera: turned 90°")
check(f"...the picture on its side at once, the right way ({cam.frame.size}, {quarters(cam.frame)})",
      cam.frame.size == (480, 640) and quarters(cam.frame) == TURNED[90])
settle(lambda: False, 0.6)
box = screen_picture_box(shots[-1])
check(f"...on the screen: taller than it's wide, in the middle ({box})", box and (box[3] - box[1]) > (box[2] - box[0])
      and abs((box[0] + box[2]) / 2 - 320) < 12)
check("...and the next pictures from it too", settle(lambda: cam.frame_at > time.monotonic() - 0.3 and quarters(cam.frame) == TURNED[90], 4))
saved = json.load(open(g.STATE_FILE)).get("cam_turn")
check(f"...kept for next time ({saved})", saved == {g.cam_key(SIDE): 90})
seen = []
for want in (180, 270, 0):
    m.press("y")
    seen.append((cam.turn_of(SIDE), quarters(cam.frame), m.msg))
check(f"Y again: 180, 270, then not rotated ({[s[0] for s in seen]}, {seen[-1][2]!r})",
      [s[0] for s in seen] == [180, 270, 0] and all(s[1] == TURNED[s[0]] for s in seen)
      and seen[-1][2] == "Side camera: not turned" and json.load(open(g.STATE_FILE)).get("cam_turn") == {})
m.press("y")

# what's taken from it: photos, what the bot sees, the web page's pictures
m.press("a")
check("A: a photo", settle(lambda: cam.shot is not None and not cam.shooting))
pics = sorted(os.listdir(HOME + "/Pictures"))
photo = Image.open(HOME + "/Pictures/" + pics[0]) if pics else None
check(f"...rotated as its picture is ({pics}, {photo and photo.size}, {photo and quarters(photo)})",
      photo is not None and photo.size == (480, 640) and quarters(photo) == TURNED[90])
look, name = m.camera_look(SIDE)
check(f"what the bot sees (Describe): rotated ({name}, {Image.open(io.BytesIO(look)).size})",
      Image.open(io.BytesIO(look)).size == (480, 640) and quarters(Image.open(io.BytesIO(look))) == TURNED[90])
look2, _ = m.friend_look()
check("...and when it looks while you chat", look2 and quarters(Image.open(io.BytesIO(look2))) == TURNED[90])
snap = m.camera.photo_of(SIDE)
check("...and a picture it takes", quarters(Image.open(io.BytesIO(snap))) == TURNED[90]
      and Image.open(io.BytesIO(snap)).size == (480, 640))
frame = m.web_camframe(SIDE)
again = m.web_camframe(SIDE)
check("the web page's picture of it: rotated, and not again for the same picture",
      quarters(Image.open(io.BytesIO(frame))) == TURNED[90] and Image.open(io.BytesIO(frame)).size == (480, 640)
      and again is frame)
rows = {r["addr"]: r for r in m.web_cameras()["cameras"]}
check(f"...its list says how far ({rows[SIDE].get('turn')}, {rows[TURNER].get('turn')})",
      rows[SIDE]["turn"] == 90 and rows[TURNER]["turn"] == 0)
r = m.web_camera({"do": "rotate", "addr": SIDE})
check(f"the web page's rotate button ({r})", r == {"ok": True, "turn": 180} and cam.turn_of(SIDE) == 180
      and quarters(Image.open(io.BytesIO(m.web_camframe(SIDE)))) == TURNED[180])
r = m.web_camera({"do": "rotate", "addr": "127.0.0.9:5999"})
check(f"...not one of yours: no ({r})", "error" in r)
m.web_camera({"do": "rotate", "addr": SIDE}); m.web_camera({"do": "rotate", "addr": SIDE})
m.web_camera({"do": "rotate", "addr": SIDE})
check("...round to 90 again", cam.turn_of(SIDE) == 90)

# next time
m2 = g.Media()
check(f"started again: still rotated ({m2.camera.turn_of(SIDE)})", m2.camera.turn_of(SIDE) == 90
      and m2.camera.turn_of(TURNER) == 0)

# the list: Y on any camera, its small picture rotated
m.press("b")
check("B: your cameras", m.cam_list and settle(lambda: g.cam_key(SIDE) in cam.thumbs and g.cam_key(TURNER) in cam.thumbs, 10))
m.cam_sel = 1
m.dirty = True; m.flush()
check(f"...Y Rotate on a camera ({footers[-1]})", ("Y", "Rotate") in footers[-1])
m.press("y")
check(f"Y on Turner (a camera that turns): rotated ({cam.turn_of(TURNER)}, {m.msg!r})", cam.turn_of(TURNER) == 90
      and m.msg == "Turner: turned 90°")
m.dirty = True; m.flush()
lst = shots[-1].convert("RGB")
y_mid = m.LIST_TOP + 28 + m.ROW_H // 2


def small_quarters(row):
    """The colours of a row's small picture (at its quarters), left of the row's name."""
    y = m.LIST_TOP + 28 + row * m.ROW_H
    x0, y0, x1, y1 = 12 + 18, y + 6, 12 + 18 + 48, y + m.ROW_H - 6
    crop = lst.crop((x0, y0, x1, y1))
    bb = Image.eval(crop, lambda v: 255 if v > 20 else 0).getbbox()
    return quarters(crop.crop(bb)) if bb else None


check(f"...the list's small pictures rotated ({small_quarters(0)}, {small_quarters(1)})",
      small_quarters(0) == TURNED[90] and small_quarters(1) == TURNED[90])

# steering a camera that turns: up on its rotated picture is up
m.press("a")
check("Turner's picture", settle(lambda: cam.addr == TURNER and cam.frame is not None and cam.info) and quarters(cam.frame) == TURNED[90])
m.dirty = True; m.flush()
check(f"...Y zooms it, so no Rotate there ({footers[-1]})", ("Y", "Rotate") not in footers[-1] and ("X Y", "Zoom") in footers[-1])


def steer(way):
    del log[:]
    m.press(way)
    end = time.time() + 0.6
    while time.time() < end:
        m.tick(); m.flush(); time.sleep(0.05)
    m.release(way)
    settle(lambda: False, 0.4)
    drives = [b for p, b in log if p == "/api/ptz/drive"]
    return (drives[0]["vx"], drives[0]["vy"]) if drives else None


got = {}
for deg in (90, 180, 270, 0):
    cam.set_turn(TURNER, deg)
    got[deg] = steer("up")
check(f"up on its picture: the camera turns that way, however it's rotated ({got})",
      got == {90: (-1, 0), 180: (0, -1), 270: (1, 0), 0: (0, 1)})
cam.set_turn(TURNER, 90)
right = steer("right")
check(f"...right, rotated 90°: up for the camera ({right})", right == (0, 1))
m.press("y")
check("...Y there zooms, it doesn't rotate", cam.turn_of(TURNER) == 90 and cam.zoom_dir == -1)
m.release("y")

# taken out and added again: the right way up
m.press("b")
m.cam_sel = 1
m.press("x"); m.press("x")
check(f"Turner taken out: its rotation goes too ({json.load(open(g.STATE_FILE)).get('cam_turn')})",
      cam.turn_of(TURNER) == 0 and g.cam_key(TURNER) not in json.load(open(g.STATE_FILE)).get("cam_turn", {})
      and cam.turn_of(SIDE) == 90)

page = open(ROOT + "/templates/index.html").read()
check("the web page: a rotate button on each of your cameras (not ones only heard on the network), "
      "showing all of a picture on its side", 'do: "rotate"' in page and "camTurn(c, card, turn)" in page
      and ".cam.tall .cam-pic img { object-fit: contain; }" in page and "c.turn" in page)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
