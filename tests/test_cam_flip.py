"""A camera that turns the wrong way (right when ◀ is pressed, or down when ▲ is): its settings (START on it in
your list of cameras) swap left and right, and up and down, as it's steered (kept for next time), and turn its
picture; ◀▶ on it in the list still swaps left and right; the web page's swap buttons too; a rotated picture
steered right as well; a picture link can't be (its settings: just its picture turned); taken out and added
again, it's steered as it is. Two pretend cameras (one that turns, a JPEG link), media mode, and the web page in
a browser."""
import asyncio, io, json, os, shutil, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
S = SP + "/tcamflip"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{HOME}/{d}")
sys.path.insert(0, SP); sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"; g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [S + "/home/*/camera.txt"]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(w=640, h=480):
    b = io.BytesIO(); Image.new("RGB", (w, h), (90, 140, 200)).save(b, "JPEG"); return b.getvalue()


log = []


porch_first = [True]


class Cams(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        if port == 5081 and self.path in ("/snap.jpg", "/porch.jpg"):
            if self.path == "/porch.jpg" and porch_first:    # (it takes a moment to answer the first time: the web
                porch_first.clear()                          # page has drawn it, not yet knowing what it is)
                time.sleep(1.5)
            return self.reply(jpeg(), "image/jpeg")
        if port == 5082:
            if self.path == "/api/ptz":
                return self.reply({"ok": True, "available": True, "position": {"pan": 0, "tilt": 0, "zoom": 0.3},
                                   "follow": {"can": True, "on": False}, "sleep": {"can": True, "asleep": False},
                                   "name": "Turner"})
            if self.path == "/api/camera.jpg":
                return self.reply(jpeg(), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        log.append((self.path, body))
        self.reply({"ok": True})


for port in (5081, 5082):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Cams)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
g.CAM_PORTS = (5082,)
g.CAM_LINKS = []
LINK, TURNER = "http://127.0.0.1:5081/snap.jpg", "127.0.0.1:5082"
open(HOME + "/camera.txt", "w").write(f"camera = {TURNER}   Turner\ncamera = {LINK}   Door\n")
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
m.footer = lambda d, items, *a, **k: (footers.append([tuple(i) for i in items]), real_footer(d, items, *a, **k))[1]
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


check("Turner's picture, the d-pad steering it", settle(lambda: cam.addr == TURNER and cam.frame is not None
                                                        and cam.info) and cam.steers)
before = {w: steer(w) for w in ("left", "right", "up", "down")}
check(f"as it comes: ◀ is left, ▶ right ({before})", before == {"left": (-1, 0), "right": (1, 0), "up": (0, 1),
                                                                "down": (0, -1)})

# ---- the list: ◀▶ on it -------------------------------------------------------------------------------
m.press("b")
check("B: your cameras", m.cam_list and settle(lambda: g.cam_key(LINK) in cam.known and g.cam_key(TURNER) in cam.known, 10))
m.cam_sel = 0
m.dirty = True; m.flush()
check(f"...on Turner: START for its settings among its keys ({footers[-1]})",
      ("START", "Settings") in footers[-1] and ("Y", "Rotate") in footers[-1] and not any(h[0] == "◀▶" for h in footers[-1]))
m.press("left")
check(f"◀ on it, as before: swapped, and it says so ({m.msg!r})", cam.flipped(TURNER)
      and m.msg == "Turner: left and right swapped")
saved = json.load(open(g.STATE_FILE)).get("cam_flip")
check(f"...kept for next time ({saved})", saved == {g.cam_key(TURNER): True})
m.press("right", repeat=True)
check("...held, it doesn't keep changing", cam.flipped(TURNER))
m.press("right")
check("...again: as normal", not cam.flipped(TURNER))


def menu_rows():
    return [(k, v) for k, _, v in m.cam_menu_rows()] if m.cam_menu else None


m.msg = None
m.press("start"); m.flush()
check(f"START: Turner's settings ({menu_rows()}, {footers[-1]})", m.cam_menu and m.cam_menu["addr"] == TURNER
      and menu_rows() == [("flip_x", "Off"), ("flip_y", "Off"), ("turn", "0°")] and footers[-1] == [("◀▶", "Change"), ("B", "Back")])
m.press("right"); m.flush()
check(f"...▶ on Flip left and right: swapped, no toast (the row says it) ({menu_rows()}, {m.msg!r})",
      cam.flipped(TURNER) and menu_rows()[0] == ("flip_x", "On") and m.msg is None)
shots[-1].save(S + "/settings_flip.png")
m.press("down"); m.press("a"); m.flush()
check(f"...▼, A on Flip up and down: swapped too ({menu_rows()})", cam.flipped(TURNER, "y") and menu_rows()[1] == ("flip_y", "On"))
saved = json.load(open(g.STATE_FILE))
check(f"...both kept for next time ({saved.get('cam_flip')}, {saved.get('cam_flip_v')})",
      saved.get("cam_flip") == {g.cam_key(TURNER): True} and saved.get("cam_flip_v") == {g.cam_key(TURNER): True})
m.press("down"); m.press("right"); m.flush()
check(f"...Turn the picture: ▶ 90° ({menu_rows()[2]})", cam.turn_of(TURNER) == 90 and menu_rows()[2] == ("turn", "90°"))
m.press("left"); m.press("left"); m.flush()
check(f"...◀ ◀: back round to 270° ({menu_rows()[2]})", cam.turn_of(TURNER) == 270)
m.press("right"); m.flush()
check("...▶: not turned", cam.turn_of(TURNER) == 0)
m.press("down"); m.flush()
check("...▼ from the last row: the first again", m.cam_menu["sel"] == 0)
shots[-1].save(S + "/settings_turn.png")
m.press("b"); m.flush()
check(f"B: your cameras again ({footers[-1]})", m.cam_list and not m.cam_menu and ("START", "Settings") in footers[-1])
shots[-1].save(S + "/list_keys.png")
m.press("start"); m.press("start"); m.flush()
check("START, START: opened and closed", m.cam_list and not m.cam_menu)
m.cam_sel = 1
m.dirty = True; m.flush()
check(f"the picture link: START for its settings too ({footers[-1]})", ("START", "Settings") in footers[-1]
      and not any(h[0] == "◀▶" for h in footers[-1]))
m.press("right")
check(f"...◀▶ on it: it doesn't turn ({m.msg!r})", not cam.flipped(LINK) and m.msg == "This camera doesn't turn")
m.press("start"); m.flush()
check(f"...its settings: just its picture turned ({menu_rows()})", menu_rows() == [("turn", "0°")])
m.press("r")
check(f"...R in its settings: on to the next tab, the settings closed ({m.tab_type()})", not m.cam_menu and m.tab_type() != "camera")
m.press("l")
check("...and back", m.tab_type() == "camera" and not m.cam_menu)
m.press("b") if not m.cam_list else None
m.cam_sel = 0

# ---- steering it now ----------------------------------------------------------------------------------
m.cam_sel = 0
m.press("a")
check("A: watching Turner again", settle(lambda: cam.addr == TURNER and cam.frame is not None and cam.info))
after = {w: steer(w) for w in ("left", "right", "up", "down")}
check(f"◀ turns it the other way now, ▶ too; ▲ and ▼ as well ({after})",
      after == {"left": (1, 0), "right": (-1, 0), "up": (0, -1), "down": (0, 1)})
cam.set_flip(TURNER, False, "y")
check(f"up and down back as normal: ▲ up again ({steer('up')})", steer("up") == (0, 1))
m.press("left")
m.dirty = True; m.flush()
check(f"...the arrow pressed lights up on its picture, as before ({sorted(cam.held)})", cam.held == {"left"})
m.release("left")
settle(lambda: False, 0.4)
cam.set_turn(TURNER, 90)
turned = steer("up")
check(f"rotated 90° too: up on its picture still where it shows ({turned})", turned == (1, 0))
cam.set_turn(TURNER, 0)

# ---- the web page's swap button ---------------------------------------------------------------------
rows = {r["addr"]: r for r in m.web_cameras()["cameras"]}
check(f"web: each says whether it turns, and if it's swapped ({[(r['name'], r['steers'], r['flip'], r['flipv']) for r in rows.values()]})",
      rows[TURNER]["steers"] and rows[TURNER]["flip"] and not rows[TURNER]["flipv"] and not rows[LINK]["steers"]
      and not rows[LINK]["flip"] and not rows[LINK]["flipv"])
r = m.web_camera({"do": "flip", "addr": TURNER, "axis": "y"})
check(f"web: up and down swapped ({r})", r == {"ok": True, "flip": True} and cam.flipped(TURNER, "y")
      and json.load(open(g.STATE_FILE)).get("cam_flip_v") == {g.cam_key(TURNER): True}
      and m.web_cameras()["cameras"][0]["flipv"] is True)
check(f"...steered so ({steer('up')})", steer("up") == (0, -1))
r = m.web_camera({"do": "flip", "addr": TURNER, "axis": "y"})
check(f"...and back ({r})", r == {"ok": True, "flip": False} and not cam.flipped(TURNER, "y"))
r = m.web_camera({"do": "flip", "addr": TURNER})
check(f"web: swap back ({r})", r == {"ok": True, "flip": False} and not cam.flipped(TURNER)
      and json.load(open(g.STATE_FILE)).get("cam_flip") == {})
check(f"...steered as it comes again ({steer('left')})", steer("left") == (-1, 0))
r = m.web_camera({"do": "flip", "addr": LINK})
check(f"web: the picture link ({r})", r == {"error": "This camera doesn't turn"})
r = m.web_camera({"do": "flip", "addr": "127.0.0.9:5999"})
check(f"web: not one of yours ({r})", r == {"error": "That camera isn't in your list"})
m.web_camera({"do": "flip", "addr": TURNER})

# ---- next time; taken out and added again -------------------------------------------------------------
m2 = g.Media()
check("started again: still swapped", m2.camera.flipped(TURNER) and not m2.camera.flipped(LINK))
m.press("b")
m.cam_sel = 0
m.web_camera({"do": "flip", "addr": TURNER, "axis": "y"})
m.press("x"); m.press("x")
check(f"Turner taken out: swapped no more ({json.load(open(g.STATE_FILE)).get('cam_flip')})",
      not cam.flipped(TURNER) and not cam.flipped(TURNER, "y") and json.load(open(g.STATE_FILE)).get("cam_flip") == {}
      and json.load(open(g.STATE_FILE)).get("cam_flip_v") == {})
open(HOME + "/camera.txt", "w").write(f"camera = {TURNER}   Turner\ncamera = {LINK}   Door\n")
cam.cams = g.read_cameras(cam.patterns)
m.web_camera({"do": "flip", "addr": TURNER})
check("put back, and swapped again", cam.flipped(TURNER))

# ---- the web page, in a browser --------------------------------------------------------------------------
PORCH = "http://127.0.0.1:5081/porch.jpg"              # (one the Pi hasn't looked at yet: it might turn)
m.press("b")                                           # (off the Pi's list of cameras, which looks at new ones)
check("off the Pi's list of cameras", not m.on_camera_list())
open(HOME + "/camera.txt", "a").write(f"camera = {PORCH}   Porch\n")
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
port = server.server_address[1]
done = threading.Event()


def pump():                                            # (media mode's requests, answered as its loop would)
    while not done.is_set():
        for job in control.take():
            out = {"error": "Something went wrong on the Pi"}
            try:
                out = m.web_command(job["cmd"])
            finally:
                control.done(job, out)
        time.sleep(0.02)


threading.Thread(target=pump, daemon=True).start()
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
os.environ["HOME"] = HOME
webui.HOME = HOME; webui.STATIC = S + "/pitato/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/pitato/setup.sh", "w").write("echo\n")
open(S + "/control-key", "w").write("k" * 32)
webui.THUMBS = HOME + "/.cache/pitato/thumbs"; webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", port); webui.CONTROL_KEY = S + "/control-key"
socket.gethostname = lambda: "gpi"
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5459, threaded=True), daemon=True).start()
time.sleep(1)
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
if os.environ.get("NO_BROWSER"):
    async_playwright = None

FLIPS = ("els => els.map(c => [c.querySelector('.t').textContent, !!c.querySelector('.cam-flip'), "
         "c.querySelector('.cam-flip') ? c.querySelector('.cam-flip').getAttribute('aria-pressed') : null])")


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        await pg.goto("http://localhost:5459/#library")
        await pg.click('#ltabs .ltab:text-is("Cameras")')
        await pg.wait_for_selector("#content .grid.cams .cam .cam-meta .t")
        got = await pg.eval_on_selector_all("#content .grid.cams .cam:not(.add-cam)", FLIPS)
        check(f"web page: the swap button by Turner, pressed (it's swapped); none by the picture link; one by Porch "
              f"(not looked at yet) ({got})", got == [["Turner", True, "true"], ["Door", False, None],
                                                       ["Porch", True, "false"]])
        await pg.fill("#content .add-cam input", "192.168.1.7")      # (typing an address meanwhile)
        await pg.evaluate("window.firstGrid = document.querySelector('#content .grid.cams')")
        await pg.wait_for_function("(() => { const c = [...document.querySelectorAll('#content .cam')].find(c => "
                                   "c.querySelector('.t') && c.querySelector('.t').textContent === 'Porch');"
                                   " return c && !c.querySelector('.cam-flip'); })()", timeout=20000)
        same = await pg.evaluate("document.querySelector('#content .grid.cams') === window.firstGrid")
        typed = await pg.input_value("#content .add-cam input")
        check(f"...Porch, once the Pi knows it's a picture link: its button gone, the list not drawn again, what's "
              f"being typed left alone ({same}, {typed!r})", same and typed == "192.168.1.7")
        await pg.fill("#content .add-cam input", "")
        title = await pg.get_attribute("#content .cam .cam-flip", "title")
        check(f"...what it does, on it ({title!r})", title.startswith("Left and right are swapped as Turner turns"))
        await pg.click("#content .cam .cam-flip")
        await pg.wait_for_function("document.querySelector('#content .cam .cam-flip').getAttribute('aria-pressed') "
                                   "=== 'false' && !document.querySelector('#content .cam .cam-flip').disabled",
                                   timeout=8000)
        check(f"...pressed: back as normal on the Pi, and said so ({await pg.inner_text('#toast')!r})",
              not cam.flipped(TURNER) and await pg.inner_text("#toast") == "Turner: left and right as normal")
        await pg.click("#content .cam .cam-flip")
        await pg.wait_for_function("document.querySelector('#content .cam .cam-flip').getAttribute('aria-pressed') "
                                   "=== 'true'", timeout=8000)
        check("...again: swapped", cam.flipped(TURNER))
        v = await pg.get_attribute("#content .cam .cam-flipv", "aria-pressed")
        title = await pg.get_attribute("#content .cam .cam-flipv", "title")
        check(f"...and one for up and down, not pressed ({v}, {title!r})", v == "false"
              and title.startswith("Swap up and down as Turner turns"))
        await pg.click("#content .cam .cam-flipv")
        await pg.wait_for_function("document.querySelector('#content .cam .cam-flipv').getAttribute('aria-pressed') "
                                   "=== 'true'", timeout=8000)
        check(f"...pressed: up and down swapped on the Pi ({await pg.inner_text('#toast')!r})",
              cam.flipped(TURNER, "y") and await pg.inner_text("#toast") == "Turner: up and down swapped")
        await pg.click("#content .cam .cam-flipv")
        await pg.wait_for_function("document.querySelector('#content .cam .cam-flipv').getAttribute('aria-pressed') "
                                   "=== 'false'", timeout=8000)
        check("...again: as normal", not cam.flipped(TURNER, "y"))
        await pg.eval_on_selector("#content .grid.cams", "e => e.scrollIntoView({block: 'center'})")
        await pg.screenshot(path=S + "/web_flip.png")
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        await ph.goto("http://localhost:5459/#library")
        await ph.click('#ltabs .ltab:text-is("Cameras")')
        await ph.wait_for_selector("#content .grid.cams .cam .cam-flip")
        wide = await ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        check("a phone: no sideways scrolling", wide)
        await ph.eval_on_selector("#content .grid.cams", "e => e.scrollIntoView()")
        await ph.screenshot(path=S + "/web_flip_phone.png")
        await b.close()


if async_playwright:
    asyncio.run(web())
else:
    print("(no browser for this Python: the web page in a browser is left to the other run)")
done.set()
cam.stop()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
