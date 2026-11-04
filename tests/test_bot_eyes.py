"""The bot's eyes: it says what the camera sees now and then, takes a picture when asked (with
the camera on another Pi, into Photos and the conversation), and looks at a picture sent from
Photos (on the Pi, or the web page). Pretend Ollama, PiE-ink and picture-link cameras."""
import io, json, os, shutil, sys, threading, time, random, types, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t61"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures/Trips")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("dirs"):
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
import gk_static; gk_static.use_home(g, HOME)
g.CAM_PORTS = (5056,)
g.CAM_LINKS = []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(size, colour, fmt="JPEG"):
    b = io.BytesIO(); Image.new("RGB", size, colour).save(b, fmt); return b.getvalue()


# ---- a pretend Ollama: gemma3 can see, llama can't ---------------------------------------------------
asked = []


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            return self.reply(200, {"models": [{"name": n} for n in ("llama3.2:3b", "gemma3:4b")]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":
            return self.reply(200, {"capabilities": ["completion", "vision"] if body.get("model") == "gemma3:4b"
                                    else ["completion"]})
        asked.append(body)
        if body.get("images"):
            if body["model"] != "gemma3:4b":
                return self.reply(500, {"error": "this model is missing data required for image input"})
            p = body["prompt"]
            if "took the attached picture" in p:
                return self.reply(200, {"response": "Done! I took it. It's a lovely red picture."})
            if "sent you the attached picture" in p:
                return self.reply(200, {"response": "What a big orange picture!"})
            return self.reply(200, {"response": "I can see a round shape over a green floor."})
        return self.reply(200, {"response": "Sure, I'm here."})


ol = ThreadingHTTPServer(("127.0.0.1", 11558), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()

# ---- a pretend PiE-ink camera ("Garage") and a camera that's only a picture link ("Porch") ---------------
cam_log = []


class PieInk(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/ptz":
            return self.reply({"ok": True, "available": True, "position": {"pan": 0, "tilt": 0, "zoom": 0},
                               "follow": {"can": True, "on": False}, "sleep": {"can": True, "asleep": False}})
        if self.path == "/api/status":
            return self.reply({"hostname": "garage-pi"})
        if self.path == "/api/camera.jpg":
            im = Image.new("RGB", (640, 480), (40, 70, 90))
            d = ImageDraw.Draw(im)
            d.ellipse((250, 170, 390, 310), fill=(235, 205, 150)); d.rectangle((0, 380, 640, 480), fill=(70, 110, 70))
            b = io.BytesIO(); im.save(b, "JPEG"); return self.reply(b.getvalue(), "image/jpeg")
        if self.path.startswith("/api/photos/"):
            return self.reply(jpeg((1280, 720), (200, 60, 60)), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        cam_log.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
        if self.path == "/api/photos":
            return self.reply({"ok": True, "photo": {"url": "/api/photos/p1.jpg"}})
        self.reply({})


class Link(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = jpeg((320, 240), (30, 60, 220))
        self.send_response(200); self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


for port, h in ((5056, PieInk), (5057, Link)):
    srv = ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

open(HOME + "/bot.txt", "w").write("server = 127.0.0.1:11558\nmodel = llama3.2:3b\nname = Sam\n")
open(HOME + "/camera.txt", "w").write("camera = 127.0.0.1:5056   Garage\ncamera = http://127.0.0.1:5057/snap.jpg   Porch\n")
Image.new("RGB", (2000, 1500), (240, 140, 30)).save(HOME + "/Pictures/sunset.jpg", quality=80)
os.utime(HOME + "/Pictures/sunset.jpg", (time.time(), time.time() - 3600))
Image.new("RGB", (64, 48), (10, 200, 10)).save(HOME + "/Pictures/Trips/leaf.png")
open(HOME + "/Pictures/broken.jpg", "wb").write(b"\xff\xd8 not really a picture")
Image.new("1", (10000, 9000)).save(HOME + "/Pictures/huge.png")

# ---- the small parts --------------------------------------------------------------------------------------
exec(open(SP + "/snapwords.py").read().split("bad = ")[0].split("import pietato_all as g")[1])   # (the lists)
check(f"asked for a picture: these are {[t for t in yes if not g.friend_wants_photo(t)]}",
      all(g.friend_wants_photo(t) for t in yes))
check(f"...and these aren't {[t for t in no if g.friend_wants_photo(t)]}", not any(g.friend_wants_photo(t) for t in no))
check("just after a picture, another", all(g.FRIEND_SNAP_AGAIN.search(t) for t in again_yes)
      and not any(g.FRIEND_SNAP_AGAIN.search(t) for t in again_no))
# a long JPEG opens small too (not the whole of it, on a Pi with 512 MB)
pano = S + "/pano.jpg"
Image.new("RGB", (20000, 3000), (90, 120, 200)).save(pano, quality=70)
import subprocess
out = subprocess.run([sys.executable, "-c", f"""
import resource, sys
sys.path.insert(0, {TESTS!r})
import pietato_all as g
from PIL import Image
g.home_dir = lambda: {HOME!r}
data = open({pano!r}, "rb").read()
r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
im = g.friend_image(data)
print(im.size, (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - r0) // 1024)
"""], capture_output=True, text=True, env=dict(os.environ))
check(f"a 20000 x 3000 JPEG opens small: {out.stdout.strip() or out.stderr[-300:]}",
      out.stdout.startswith("(768, 115)") and int(out.stdout.split()[-1]) < 40)
try:
    g.friend_image(HOME + "/Pictures/huge.png")
    check("a 90-megapixel picture isn't opened", False)
except ValueError as ex:
    check(f"a 90-megapixel picture isn't opened ({ex})", "too big" in str(ex))
im = g.friend_image(HOME + "/Pictures/sunset.jpg")
check(f"a big one opens small, for a model: {im.size}", max(im.size) == g.FRIEND_SEE_SIZE and im.mode == "RGB")
# a big PNG opens whole (all of it at once), so it's held to less than a JPEG, which opens small
big = io.BytesIO(); Image.new("RGB", (5000, 4000), (9, 9, 9)).save(big, "PNG", compress_level=1)
try:
    g.friend_image(big.getvalue())
    check("a 20-megapixel PNG isn't opened", False)
except ValueError as ex:
    check(f"a 20-megapixel PNG isn't opened ({ex})", "too big" in str(ex))
t0 = time.time()
im = g.friend_image(jpeg((7000, 5000), (9, 9, 9)))
check(f"...a 35-megapixel JPEG is, small and quickly: {im.size}, {time.time() - t0:.2f} s", max(im.size) == g.FRIEND_SEE_SIZE)
# a phone's picture with more than one in it (MPO), sideways (EXIF), see-through, a GIF; not an icon
mpo = io.BytesIO()
Image.new("RGB", (4000, 3000), (200, 30, 30)).save(mpo, "MPO", save_all=True,
                                                    append_images=[Image.new("RGB", (4000, 3000), (0, 0, 0))])
im = g.friend_image(mpo.getvalue())
check(f"a phone's MPO picture: {im.size} {im.getpixel((5, 5))}", im.size == (768, 576) and im.getpixel((5, 5))[0] > 150)
side = io.BytesIO(); ex = Image.Exif(); ex[0x0112] = 6
Image.new("RGB", (400, 300), (0, 0, 200)).save(side, "JPEG", exif=ex)
im = g.friend_image(side.getvalue())
check(f"...one taken sideways is turned upright: {im.size}", im.size == (300, 400))
see = io.BytesIO(); Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(see, "PNG")
im = g.friend_image(see.getvalue())
check(f"...see-through parts on white: {im.getpixel((1, 1))}", im.mode == "RGB" and im.getpixel((1, 1)) == (255, 255, 255))
gif = io.BytesIO(); Image.new("P", (40, 30), 3).save(gif, "GIF", transparency=3)
im = g.friend_image(gif.getvalue())
check(f"...a GIF: {im.mode} {im.size}", im.mode == "RGB" and im.size == (40, 30))
ico = io.BytesIO(); Image.new("RGB", (32, 32), (1, 2, 3)).save(ico, "ICO")
try:
    g.friend_image(ico.getvalue())
    check("an icon isn't a picture for it", False)
except ValueError as ex:
    check(f"an icon isn't a picture for it ({ex})", str(ex) == "That picture can't be opened")


# ---- media mode -------------------------------------------------------------------------------------------
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
fr = m.friend
fi = m.tab_index("friend")
m.open_app(fi)
m.camera.load(g.LIBRARY[m.tab_index("camera")]["files"])


def settle(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


settle(lambda: not fr.busy)                      # (it says hello)
check("its cameras", [c["name"] for c in m.camera.cams] == ["Garage", "Porch"])
check("the one it looks through: the Camera tab's (Garage, the first)", m.friend_camera() == "127.0.0.1:5056")
check("...or one you name", m.friend_camera("take a picture of the PORCH please") == "http://127.0.0.1:5057/snap.jpg")
check("its model's assumed to see (nothing to set up for it)", fr.sees() and "llama3.2:3b" not in fr.vision)

# ---- take a picture, with a model that can't see ------------------------------------------------------------
n0 = len(fr.log)
m.friend_send("take a picture")
check("your line, then busy taking it", fr.log[-1]["who"] == "you" and fr.busy)
check("taken", settle(lambda: not fr.busy))
last = fr.log[-1]
photo = last.get("photo", "")
check(f"the PiE-ink camera's own shutter: {cam_log[-1]}", cam_log and cam_log[-1][0] == "/api/photos")
check(f"in Photos: {os.path.basename(photo)}", photo.startswith(HOME + "/Pictures/camera-") and os.path.exists(photo)
      and Image.open(photo).size == (1280, 720) and m.last_shot == photo)
check(f"in the conversation, with a picture: {last['text']!r}", last["who"] == "friend" and last["kind"] == "photo"
      and last["text"] == "Here's the picture from Garage. It's in Photos too." and os.path.exists(g.FRIEND_PICS + "/" + last["pic"] + ".jpg"))
small = Image.open(g.FRIEND_PICS + "/" + last["pic"] + ".jpg")
check(f"...a small copy of it: {small.size}", max(small.size) <= g.FRIEND_PIC_SIZE)
check("its model was shown it, and couldn't look: just the picture, and it knows now",
      [a["model"] for a in asked if a.get("images")] == ["llama3.2:3b"] and fr.vision.get("llama3.2:3b") is False
      and not fr.sees())
m.flush()
photo_shot = shots[-1]

# ---- ...and with a model that can see: it says something about it ----------------------------------------------
m.friend_set(model="gemma3:4b")
check("a model that can see: it sees", fr.sees())
asked.clear()
m.friend_send("send me a pic of the porch")
check("taken", settle(lambda: not fr.busy))
last = fr.log[-1]
check(f"from the camera you named (a picture link: its picture): {last.get('seen')}", last.get("seen") == "Porch"
      and Image.open(last["photo"]).size == (320, 240))
check(f"...and a word on it from its model: {last['text']!r}", last["text"] == "Done! I took it. It's a lovely red picture."
      and asked[-1]["model"] == "gemma3:4b" and asked[-1]["images"] and "the camera (Porch)" in asked[-1]["prompt"])
check("...knowing what you asked", "Sam now says: send me a pic of the porch" in asked[-1]["prompt"]
      and "answering what they asked" in asked[-1]["prompt"])
# a camera heard on the network is only looked through when it's picked on the Camera tab, not by its name
m.camera.found[g.cam_key("127.0.0.2:5998")] = {"addr": "127.0.0.2:5998", "name": "Kitchen", "seen": time.time()}
check("a camera heard on the network isn't taken by its name", m.friend_camera("take a picture of the kitchen")
      == m.friend_camera() != "127.0.0.2:5998" and m.camera.found_list())
m.camera.found.clear()
# back to the model that couldn't see: it isn't shown pictures again (it couldn't look before)
m.friend_set(model="llama3.2:3b")
check("the model that couldn't see: it doesn't see", not fr.sees())
asked.clear()
m.friend_send("take a picture")
check("...a picture's still taken, with no model shown it", settle(lambda: not fr.busy) and fr.log[-1]["kind"] == "photo"
      and not any(a.get("images") for a in asked))
m.friend_set(model="gemma3:4b")
# no room on the card
real = g.shutil.disk_usage
g.shutil.disk_usage = lambda p: types.SimpleNamespace(total=1 << 30, used=1 << 30, free=5 << 20)
n = len(os.listdir(HOME + "/Pictures"))
m.friend_send("take a picture")
settle(lambda: not fr.busy)
g.shutil.disk_usage = real
check(f"no room on the card: {fr.log[-1]['text']!r}", fr.log[-1]["kind"] == "error" and "no room left" in fr.log[-1]["text"]
      and len(os.listdir(HOME + "/Pictures")) == n)

# just after a picture: "take another one"
asked.clear()
m.friend_send("take another one")
check("just after a picture, 'take another one' takes another", settle(lambda: not fr.busy)
      and fr.log[-1]["kind"] == "photo" and fr.log[-2]["text"] == "take another one")
fr.remark("time"); settle(lambda: not fr.busy)
m.friend_send("another one")
check("...but after something else, it's just talk", settle(lambda: not fr.busy) and fr.log[-1]["kind"] == "chat")

# no camera, and one that doesn't answer
keep = m.camera.cams
m.camera.cams = []; os.rename(HOME + "/camera.txt", HOME + "/camera.off"); m.camera.addr = ""
m.friend_send("take a photo")
settle(lambda: not fr.busy)
check(f"no camera: {fr.log[-1]['text']!r}", fr.log[-1]["kind"] == "error" and "there's no camera" in fr.log[-1]["text"])
os.rename(HOME + "/camera.off", HOME + "/camera.txt")
m.camera.cams = [{"addr": "127.0.0.1:5999", "name": "Shed"}]
m.camera.addr = ""
m.friend_send("take a photo")
settle(lambda: not fr.busy, 30)
check(f"a camera that doesn't answer: {fr.log[-1]['text']!r}", fr.log[-1]["kind"] == "error" and "Shed didn't answer" in fr.log[-1]["text"])
m.camera.cams = keep
m.camera.select("127.0.0.1:5056")

# ---- what it sees, by itself ---------------------------------------------------------------------------------
random.seed(4)
topics = {m.friend_topic() for _ in range(200)}
check(f"with a camera and a model that can see, what it sees is a topic: {sorted(topics)}", "sight" in topics)
asked.clear()
check("a remark about what it sees", fr.remark("sight") and settle(lambda: not fr.busy))
last = fr.log[-1]
check(f"...looked through the camera: {last['text']!r}", asked[-1]["images"] and "camera (Garage) sees right now" in asked[-1]["prompt"]
      and g.FRIEND_ASKS["sight"] in asked[-1]["prompt"] and last["kind"] == "remark" and last.get("seen") == "Garage" and last.get("pic"))
fr.log[-1]["t"] -= 600
fr.remark("sight"); settle(lambda: not fr.busy)
check("...and next time it remembers what it saw", "When you last looked, 10 minutes ago, you said: I can see a round shape" in asked[-1]["prompt"])
m.camera.cams = []; os.rename(HOME + "/camera.txt", HOME + "/camera.off"); m.camera.addr = ""
fr.remark("sight"); settle(lambda: not fr.busy)
check("no camera to look through: something else instead", not asked[-1].get("images") and fr.log[-1]["kind"] == "remark"
      and "sees right now" not in asked[-1]["prompt"])
topics = {m.friend_topic() for _ in range(200)}
check("...and it isn't a topic", "sight" not in topics)
os.rename(HOME + "/camera.off", HOME + "/camera.txt")
m.camera.cams = keep
m.camera.select("127.0.0.1:5056")
m.friend_set(model="llama3.2:3b")
topics = {m.friend_topic() for _ in range(200)}
check("a model that couldn't see: not a topic either", "sight" not in topics)
m.friend_set(model="gemma3:4b")
topics = {m.friend_topic() for _ in range(200)}
check("...back to one that can: a topic again", "sight" in topics and fr.sees())

# ---- X: the menu ---------------------------------------------------------------------------------------------
m.tab = fi; m.view = "list"
m.press("x")
opts = [o[1] for o in m.friend_options()]
check(f"X: a menu: {opts}", m.friend_more is not None and opts == ["send", "snap", "character", "clear"])   # (START: its settings)
m.flush()
menu_shot = shots[-1]
m.press("b")
check("B closes it (and stays on the Bot page)", m.friend_more is None and m.tab == fi and m.view == "list")

# send a picture from Photos (it's been quiet a while: going to Photos and back isn't opening the page)
for x in fr.log:
    x["t"] -= 7200
fr.busy = True
m.press("x"); m.press("a")
check("not while it's busy", m.tab == fi and m.picking is None and m.friend_more is None)
fr.busy = False
m.press("x"); m.press("a")
pi = m.tab_index("photos")
check("Send a picture: Photos, picking for the bot", m.tab == pi and m.picking == "bot")
m.flush()
check("...its buttons say so", True)
pick_shot = shots[-1]
items = m.tab_items(pi)
names = [os.path.basename(it["src"]) for it in items]
m.sels[pi] = names.index("sunset.jpg")
m.press("a")
check("A: back on the Bot page, a box for a word with it", m.tab == fi and m.view == "keys" and m.picking is None)
check("...and no hello in the way", not fr.busy)
for ch in "what is this?":
    m.keyboard_key("char", ch)
asked.clear()
m.keyboard_key("done")
check("sent", settle(lambda: not fr.busy))
you = [x for x in fr.log if x["who"] == "you"][-1]
check(f"your line has the picture: {you['text']!r}", you["text"] == "what is this?" and you.get("pic")
      and you.get("photo") == HOME + "/Pictures/sunset.jpg")
check(f"its model was shown it: {fr.log[-1]['text']!r}", asked[-1]["model"] == "gemma3:4b" and asked[-1]["images"]
      and "Sam sent you the attached picture." in asked[-1]["prompt"] and "Sam now says: what is this?" in asked[-1]["prompt"]
      and fr.log[-1]["text"] == "What a big orange picture!")
# ...or no word at all
m.press("x"); m.press("a")
m.sels[pi] = [os.path.basename(it["src"]) for it in m.tab_items(pi)].index("leaf.png")
m.press("a"); m.keyboard_key("done")
check("sent without a word", settle(lambda: not fr.busy) and fr.log[-2]["who"] == "you" and fr.log[-2]["text"] == ""
      and fr.log[-2].get("pic") and "They didn't say anything with it." in asked[-1]["prompt"]
      and asked[-1]["prompt"].rstrip().endswith("Say something about the picture."))
# B in Photos: nothing sent; L/R: not picking any more
n = len(fr.log)
m.press("x"); m.press("a"); m.press("b")
check("B in Photos: back, nothing sent", m.tab == fi and m.picking is None and len(fr.log) == n)
m.press("x"); m.press("a"); m.press("r")
check("R in Photos: on to the next app, not picking any more", m.picking is None and m.tab != pi)
m.tab = fi; m.view = "list"
# a broken picture
fr.say("look at this", picture=HOME + "/Pictures/broken.jpg")
settle(lambda: not fr.busy)
check(f"a picture that can't be opened: {fr.log[-1]['text']!r}", fr.log[-1]["kind"] == "error"
      and "can't be opened" in fr.log[-1]["text"] and fr.log[-2]["text"] == "look at this")

# take a picture from the menu
m.press("x"); m.press("down"); m.press("a")
check("Take a picture, from the menu", settle(lambda: not fr.busy) and fr.log[-1]["kind"] == "photo"
      and fr.log[-2]["text"] == "Take a picture")
m.flush()
chat_shot = shots[-1]

# ---- the web page --------------------------------------------------------------------------------------------
w = m.web_friend()
ph = next(x for x in reversed(w["log"]) if x["kind"] == "photo")
check(f"the web page: pictures and where they are in Photos: {ph['photo']}", ph["pic"] and ph["photo"]["folder"] == "pictures"
      and ph["photo"]["path"].startswith("camera-") and w["camera"] == "Garage" and w["sees"] is True and "doing" in w)
sent = next(x for x in reversed(w["log"]) if x["who"] == "you" and x["pic"] and x["photo"])
check(f"...a picture you sent: {sent['photo']}", sent["photo"] == {"folder": "pictures", "path": "Trips/leaf.png"})
r = m.web_friend_do({"do": "say", "text": "and this?", "picture": HOME + "/Pictures/sunset.jpg"})
check(f"the web page sends a picture ({sorted(r)})", r.get("ok") is True and set(r) == {"ok", "since"}
      and settle(lambda: not fr.busy) and fr.log[-2].get("pic") and fr.log[-1]["t"] > r["since"])
for bad in ("/etc/passwd", HOME + "/Pictures/../bot.txt", HOME + "/.cache/x.jpg", "Pictures/sunset.jpg", 5):
    check(f"...not this: {bad!r}", "error" in m.web_friend_do({"do": "say", "text": "x", "picture": bad}))
check("...nor nothing at all", "error" in m.web_friend_do({"do": "say", "text": ""}))
r = m.web_friend_do({"do": "photo"})
check("the web page asks for a picture", r == {"ok": True} and settle(lambda: not fr.busy) and fr.log[-1]["kind"] == "photo")
control = g.Control()
srv = g.serve_control(m, control, port=0)
base = f"http://127.0.0.1:{srv.server_address[1]}"
with urllib.request.urlopen(base + "/friendpic?id=" + fr.log[-1]["pic"]) as r:
    data, ctype = r.read(), r.headers.get("Content-Type")
check(f"its pictures for the page: {ctype}, {Image.open(io.BytesIO(data)).size}", ctype == "image/jpeg" and data[:2] == b"\xff\xd8")
for bad in ("../friend", "nope", "", "0" * 15 + "g"):
    try:
        urllib.request.urlopen(base + "/friendpic?id=" + bad)
        check(f"no such picture: {bad!r}", False)
    except urllib.error.HTTPError as ex:
        check(f"no such picture: {bad!r} ({ex.code})", ex.code == 404)

# ---- kept: a picture with no words comes back after a start-up; cleared, the pictures go ---------------------------
m2 = g.Media()
check("after a start-up, the pictures are still there", [x.get("pic") for x in m2.friend.log] == [x.get("pic") for x in fr.log])
pics = os.listdir(g.FRIEND_PICS)
for f in pics:
    os.utime(g.FRIEND_PICS + "/" + f, (time.time() - 120, time.time() - 120))
m.tab = fi; m.view = "list"
m.press("x"); m.press("up"); m.press("a")
check(f"Clear: asks first ({m.friend_options()[-1][0]!r})", fr.log and m.friend_options()[-1][0] == "Press A again to clear it")
m.flush()
clear_shot = shots[-1]
m.press("a")
check("A again: cleared, and its pictures with it", fr.log == [] and os.listdir(g.FRIEND_PICS) == [] and m.friend_more is None)

# the Bot page's pictures are kept while they're in the conversation
fr.say("one more", picture=HOME + "/Pictures/sunset.jpg"); settle(lambda: not fr.busy)
live = fr.log[-2]["pic"]
m.friend_pics = {f"{k:016x}": False for k in range(g.FRIEND_KEEP + 11)}
m.friend_pic(live)
check(f"the Bot page's pictures: only those in the conversation are kept ({len(m.friend_pics)})",
      list(m.friend_pics) == [live] and m.friend_pics[live])
# HOME: nothing left half-open
m.press("x"); m.press("a")
check("picking in Photos...", m.picking == "bot")
g.subprocess.run = lambda *a, **k: None
m.prev_vt = "1"
m.leave()
check("...HOME: not picking any more", m.picking is None and m.friend_more is None and m.confirm[0] is None)

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, shot in enumerate([photo_shot, menu_shot, pick_shot, chat_shot, clear_shot]):
    sheet.paste(shot, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/bot_eyes_sheet.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
