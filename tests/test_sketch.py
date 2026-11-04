"""A drawing from the web page's Draw tab on the Pi: full screen (the screen's size, or fitted), the next one in its
place, B back to where you were (Now playing only while something plays), other buttons nothing; what the web page
says is on the screen; drawings that aren't pictures turned away; nothing over the update; the terminal: media mode
first."""
import io, json, os, shutil, subprocess, sys, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw
from pitato.screens.sketch import sketch_image, SKETCH_SAYS
S = SP + "/t_sketch"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
m.pie.place = lambda: None


def png(size, colour, mode="RGB", fmt="PNG", square=None):
    im = Image.new(mode, size, colour)
    if square:
        ImageDraw.Draw(im).rectangle(square, fill=(30, 90, 220) if mode == "RGB" else (30, 90, 220, 255))
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def send(data):
    return m.web_command({"cmd": "sketch", "image": sketch_image(data)})


def flush():
    m.dirty = True; m.flush()


# what comes from the page: pictures only
bad = []
for what, data in [("not a picture", b"hello"), ("a GIF", png((64, 48), (255, 0, 0), "P", "GIF")),
                   ("too many pixels", png((5000, 4000), (0, 0, 0)))]:
    try:
        sketch_image(data); bad.append(what)
    except ValueError as ex:
        check(f"{what}: {ex}", str(ex) == "That isn't a drawing")
check("...none of them taken", not bad)
im = sketch_image(png((64, 48), (0, 0, 0, 0), "RGBA"))
check(f"see-through: white, like the page's paper ({im.mode} {im.getpixel((5, 5))})", im.mode == "RGB" and im.getpixel((5, 5)) == (255, 255, 255))
check("a JPEG is fine too", sketch_image(png((64, 48), (0, 200, 0), fmt="JPEG")).size == (64, 48))
check("something else from the control server: turned away", m.web_command({"cmd": "sketch", "image": "x"}) == {"error": "That isn't a drawing"})

# on the home screen
m.go_home(); flush()
check("home first", m.view == "home")
r = send(png((640, 480), (220, 40, 40), square=(100, 100, 200, 200)))
flush()
check(f"shown: {r}, {m.view}, {m.where_text()!r}", r == {"ok": True} and m.view == "sketch" and m.where_text() == "Your drawing")
shot = FB.last
check(f"the whole screen, as drawn: {shot.size} {shot.getpixel((150, 150))} {shot.getpixel((20, 20))}",
      shot.size == (640, 480) and shot.getpixel((150, 150)) == (30, 90, 220) and shot.getpixel((20, 20)) == (220, 40, 40))
check(f"...and says how to go back: {m.msg!r}", m.msg == SKETCH_SAYS)
check("web state: the screen's size for the page's paper", m.web_state()["canvas"] == [640, 480])
m.msg = None; flush()
check("...the toast gone: just the drawing", FB.last.getpixel((320, 400)) == (220, 40, 40))
r = send(png((640, 480), (40, 200, 40)))
flush()
check(f"the next one takes its place, no toast again ({m.msg!r})", m.view == "sketch" and m.msg is None
      and FB.last.getpixel((20, 20)) == (40, 200, 40))
for k in ("a", "x", "y", "start", "select", "up", "down", "left", "right", "l", "r"):
    m.press(k)
check("other buttons: nothing", m.view == "sketch")
m.press("b"); flush()
check(f"B: home again ({m.view})", m.view == "home" and m.sketch is None)

# from an app's list, and from Now playing
m.web_tab("Photos"); flush()
tab = m.tab
send(png((640, 480), (0, 0, 0)))
check("from the Photos tab: shown", m.view == "sketch")
m.press("b")
check(f"B: back to Photos ({m.view}, {m.tab == tab})", m.view == "list" and m.tab == tab)
m.view = "now"; m.kind = "audio"; m.proc = types.SimpleNamespace(poll=lambda: None)
send(png((640, 480), (0, 0, 0)))
m.press("b")
check(f"Now playing, still playing: back to it ({m.view})", m.view == "now")
send(png((640, 480), (0, 0, 0)))
m.proc = None
m.press("b")
check(f"...the song over meanwhile: its list instead ({m.view})", m.view == "list")

# another screen's shape: fitted, edges dark
send(png((1280, 720), (255, 200, 0)))
m.msg = None; flush()
shot = FB.last
check(f"another shape, fitted: {shot.size} middle {shot.getpixel((320, 240))} top {shot.getpixel((320, 10))}",
      shot.size == (640, 480) and shot.getpixel((320, 240)) == (255, 200, 0) and shot.getpixel((320, 10)) == g.PHOTO_BG)
m.press("b")

# not over the update; the terminal: media mode first
m.view = "update"
r = send(png((640, 480), (0, 0, 0)))
check(f"over the update: no ({r})", "error" in r and m.view == "update")
m.view = "home"
m.leave()
check("in the terminal", not m.active)
r = send(png((640, 480), (10, 10, 10)))
check(f"from the terminal: media mode, and the drawing ({r}, {m.active}, {m.view})", r == {"ok": True} and m.active and m.view == "sketch")
m.press("b")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
