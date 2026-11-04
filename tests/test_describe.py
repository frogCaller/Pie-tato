"""Describe: SELECT on the Camera tab (or Describe on the web page) has the bot look through that
camera and say what it sees, out loud and over the picture. Pretend Ollama (gemma3 can see, llama
can't), a pretend PiE-ink camera that turns ("Garage"), a picture link ("Porch"), and one that's off."""
import io, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t70"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("dirs"):
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
sys.path.insert(0, SP)
import gk_static; gk_static.use_home(g, HOME)
g.CAM_PORTS = (5058,)
g.CAM_LINKS = []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def jpeg(size, colour):
    b = io.BytesIO(); Image.new("RGB", size, colour).save(b, "JPEG"); return b.getvalue()


# ---- a pretend Ollama ---------------------------------------------------------------------------------
asked = []
slow = {"secs": 0.0}
SAYS = "I can see a porch with a blue mat by the door. Nobody's there right now, and it looks calm."


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self.reply(200, {"models": [{"name": n} for n in ("llama3.2:3b", "gemma3:4b")]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":
            return self.reply(200, {"capabilities": ["completion", "vision"] if body.get("model") == "gemma3:4b"
                                    else ["completion"]})
        asked.append(body)
        time.sleep(slow["secs"])
        if body.get("images"):
            if body["model"] != "gemma3:4b":
                return self.reply(500, {"error": "this model is missing data required for image input"})
            return self.reply(200, {"response": SAYS})
        return self.reply(200, {"response": "Hello there."})


ol = ThreadingHTTPServer(("127.0.0.1", 11559), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()

# ---- a PiE-ink camera that turns, and a camera that's a picture link -----------------------------------------
ptz = []


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
            ImageDraw.Draw(im).ellipse((250, 170, 390, 310), fill=(235, 205, 150))
            b = io.BytesIO(); im.save(b, "JPEG"); return self.reply(b.getvalue(), "image/jpeg")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        ptz.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
        self.reply({"ok": True})


class Link(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        im = Image.new("RGB", (640, 480), (70, 90, 150))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 330, 640, 480), fill=(40, 60, 120)); d.rectangle((250, 120, 390, 330), fill=(120, 80, 50))
        b = io.BytesIO(); im.save(b, "JPEG"); body = b.getvalue()
        self.send_response(200); self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


for port, h in ((5058, PieInk), (5059, Link)):
    srv = ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

PORCH, GARAGE, SHED = "http://127.0.0.1:5059/snap.jpg", "127.0.0.1:5058", "http://127.0.0.1:5998/snap.jpg"
open(HOME + "/camera.txt", "w").write(f"camera = {PORCH}   Porch\ncamera = {GARAGE}   Garage\ncamera = {SHED}   Shed\n")

# ---- media mode, with a pretend voice ----------------------------------------------------------------------
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


def bot(**conf):
    lines = "".join(f"{k} = {v}\n" for k, v in conf.items())
    open(HOME + "/bot.txt", "w").write(lines)
    m.friend.load(m.friend_files())


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
fr = m.friend
said, stopped = [], []


def fake_say(text, vid, device="", volume=100):
    if not vid:
        return False, "Pick a voice in Settings > Bot"
    said.append(text)
    m.voice.speaking = True
    return True, ""


m.voice.say = fake_say
m.voice.stop = lambda unload=False: (stopped.append(1), setattr(m.voice, "speaking", False))
m.voice.warm = lambda vid: None


def settle(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def tap(name, secs=0.05):
    m.press(name); settle(lambda: False, secs); m.release(name); m.tick(); m.flush()


def footer():
    """The hints the footer was last asked for."""
    return list(foot["items"])


foot = {}
_footer = m.footer
m.footer = lambda d, items, right=None, credit=None, **kw: (foot.update(items=items), _footer(d, items, right, credit, **kw))[1]
pics = {}


def snap(name):
    m.dirty = True; m.flush(); pics[name] = shots[-1]


def redraw():
    m.dirty = True; m.flush()


cam = m.camera
ci = m.tab_index("camera")
m.state["camera"] = PORCH
m.tab = ci - 1
m.switch_tab(1)
check(f"the Camera tab, on Porch: {cam.addr}", m.on_camera_page() and cam.addr == PORCH)
check("Porch's picture", settle(lambda: cam.frame is not None and cam.jpeg is not None))

# ---- no bot: SELECT does what it did -----------------------------------------------------------------------
redraw()
check(f"no bot: no Describe in the footer {footer()}", all(k != "SEL" for k, *_ in footer()))
tap("select")
check(f"...and SELECT on a camera that doesn't turn: {cam.action!r}", cam.action == "This camera doesn't turn"
      and m.cam_bot is None)

# ---- a bot that can't see -------------------------------------------------------------------------------------
bot(server="127.0.0.1:11559", model="llama3.2:3b", voice="en_US-amy-low")
redraw()
check(f"a bot: SEL Describe in the footer {footer()}", ("SEL", "Describe") in footer())
slow["secs"] = 0.5
m.press("select")
check("SELECT: it's looking", m.cam_bot and m.cam_bot["busy"] and m.cam_bot["addr"] == PORCH and fr.busy)
snap("looking")
m.release("select")
check("...and says why it can't see", settle(lambda: not fr.busy and m.cam_bot and not m.cam_bot["busy"]))
slow["secs"] = 0.0
told = m.cam_bot
check(f"over the picture: {told['text']!r}", told["error"] and told["text"] == "I can't see: llama3.2:3b can't see pictures"
      and not said)
check("...and it knows llama can't see now", fr.vision.get("llama3.2:3b") is False and not fr.sees())
snap("cant_see")
n = len(asked)
tap("select")
check("again (you asked it to look): it tries again, and says so", settle(lambda: not fr.busy) and len(asked) == n + 1
      and m.cam_bot["error"])

# ---- a model that can see, and a voice: it looks, says it, and the words go up over the picture -------------------
bot(server="127.0.0.1:11559", model="gemma3:4b", voice="en_US-amy-low")
asked.clear()
slow["secs"] = 0.6
tap("select")
check("SELECT: looking", settle(lambda: fr.busy and fr.doing == "Looking…", 2))
tap("select")
check(f"SELECT while it looks: {m.msg!r}", m.msg == "Still looking")
check("it answers", settle(lambda: not fr.busy and not m.cam_bot["busy"]))
slow["secs"] = 0.0
q = asked[-1]
check(f"its model was asked, with the camera's picture and what to say: {q['model']}", q["model"] == "gemma3:4b"
      and len(q.get("images") or []) == 1 and "They asked what you see" in q["prompt"]
      and "the camera (Porch) sees right now" in q["prompt"])
check(f"said out loud: {said}", said == [SAYS])
told = m.cam_bot
check(f"...and over the picture: {told['text'][:40]!r}", told["text"] == SAYS and told["spoken"] and not told["error"]
      and told["note"] == "")
last = fr.log[-1]
check(f"...and in the conversation, with what it looked at: {last['kind']}, {last.get('seen')}",
      last["who"] == "friend" and last["kind"] == "remark" and last["text"] == SAYS and last.get("seen") == "Porch"
      and os.path.exists(g.FRIEND_PICS + "/" + last["pic"] + ".jpg"))
redraw()
check(f"while it talks: SEL Stop {footer()}", ("SEL", "Stop") in footer())
snap("said")
m.msg, cam.action = None, ""                     # (a picture without the test's notices)
snap("clean")
pics["clean"].save(SP + "/describe_clean.png")
tap("select")
check("SELECT while it talks: quiet", stopped and not m.voice.speaking)
redraw()
check("...and SEL Describe again", ("SEL", "Describe") in footer())
told["until"] = time.monotonic() - 0.5
settle(lambda: False, 0.2)
snap("gone")
check("the words go after a while", m.cam_bot["until"] < time.monotonic())

# ---- no voice: the words, and a note how to hear them --------------------------------------------------------------
bot(server="127.0.0.1:11559", model="gemma3:4b")
said.clear()
tap("select")
check("no voice: it answers", settle(lambda: not fr.busy and not m.cam_bot["busy"]))
check(f"...not said, and a note: {m.cam_bot['note']!r}", not said and m.cam_bot["note"] == "Pick a voice in Settings > Bot"
      and m.cam_bot["text"] == SAYS)
snap("no_voice")

# ---- something playing: not over it ---------------------------------------------------------------------------------
bot(server="127.0.0.1:11559", model="gemma3:4b", voice="en_US-amy-low")
m.proc = type("P", (), {"poll": lambda self: None})()
tap("select")
check("with music playing: it answers", settle(lambda: not fr.busy and not m.cam_bot["busy"]))
check(f"...not said over it: {m.cam_bot['note']!r}", not said and m.cam_bot["note"] == "Not while something's playing")
m.proc = None

# ---- a camera that's off ----------------------------------------------------------------------------------------------
ok, why = m.camera_describe(SHED)
check(f"Describe for a camera that's off: started {ok}", ok)
check("...and the bot says it can't see", settle(lambda: not fr.busy and not m.cam_bot["busy"]))
check(f"   {m.cam_bot['text']!r}", m.cam_bot["error"] and m.cam_bot["text"] == "I can't see anything: the camera Shed didn't answer")
check("...which isn't over Porch's picture (another camera's)", g.cam_key(m.cam_bot["addr"]) != g.cam_key(cam.addr))

# ---- a camera that turns: SELECT let go quickly, held, and START ----------------------------------------------------------
m.press("r"); m.release("r")
check(f"R: Garage, which turns: {cam.addr}", cam.addr == GARAGE)
check("its picture", settle(lambda: cam.frame is not None and cam.info and cam.steers))
redraw()
check(f"footer: {footer()}", footer()[:4] == [("X Y", "Zoom"), ("A", "Photo"), ("START", "Home"), ("SEL", "Describe")]
      and footer()[4][:2] == ("Hold SEL", "Follow"))
said.clear()
m.press("select")
check("SELECT down on one that turns: nothing yet", not fr.busy)
m.release("select")
check("...let go: it looks", fr.busy or m.cam_bot["addr"] == GARAGE)
check("...and says it", settle(lambda: not fr.busy and not m.cam_bot["busy"]) and said == [SAYS]
      and m.cam_bot["addr"] == GARAGE)
m.voice.speaking = False
ptz.clear()
m.press("select"); settle(lambda: False, g.CAM_HOLD + 0.3); m.release("select")
check(f"SELECT held: Follow me ({ptz[-1] if ptz else None}), and no looking", ptz and ptz[-1] == ("/api/ptz/follow", {"on": True})
      and not fr.busy)
redraw()
lit = [it for it in footer() if len(it) > 2 and it[2]]
check(f"...the Hold SEL key lit while it follows: {lit}", lit == [("Hold SEL", "Follow", True)])
snap("garage_follow")
ptz.clear()
tap("start")
check(f"START let go quickly: home ({ptz})", settle(lambda: ("/api/ptz/home", {}) in ptz, 2) and cam.speed == "normal")
m.press("start"); settle(lambda: False, g.CAM_HOLD + 0.3); m.release("start")
check(f"START held: the next speed ({cam.speed}), and not home", cam.speed == "fast" and ptz.count(("/api/ptz/home", {})) == 1)
# without a bot, SELECT is the speed again
bot()
redraw()
check(f"no bot: SEL Speed {footer()[3]}", footer()[3] == ("SEL", "Speed"))
tap("select")
check(f"...and SELECT: the next speed ({cam.speed})", cam.speed == "slow" and not fr.busy)

# ---- the web page ------------------------------------------------------------------------------------------------------------
w = m.web_cameras()
check(f"the web page's cameras: bot {w['bot']}, voice {w['voice']}", w["bot"] is False)
check(f"Describe with no bot: {m.web_camera({'do': 'describe', 'addr': PORCH})}",
      m.web_camera({"do": "describe", "addr": PORCH}) == {"error": "Set up your bot first, on the Bot tab"})
bot(server="127.0.0.1:11559", model="gemma3:4b", voice="en_US-amy-low")
w = m.web_cameras()
check(f"...with one: bot {w['bot']}, voice {w['voice']}", w["bot"] is True and w["voice"] is True)
check("not one of yours", m.web_camera({"do": "describe", "addr": "10.9.9.9"}) == {"error": "That camera isn't in your list"})
said.clear()
r = m.web_camera({"do": "describe", "addr": PORCH})
check(f"Describe Porch from the web page: {r}", r.get("ok") and isinstance(r.get("since"), float))
check(f"...again while it looks: {m.web_camera({'do': 'describe', 'addr': PORCH})}",
      m.web_camera({"do": "describe", "addr": PORCH}) == {"error": "It's still thinking about the last one"})
check("...it answers, out loud on the Pi", settle(lambda: not fr.busy) and said == [SAYS])
got = [x for x in m.web_friend()["log"] if x["who"] == "friend" and x["t"] >= r["since"]]
check(f"...and the page finds it in the conversation: {got[0]['text'][:30] if got else None!r}",
      len(got) == 1 and got[0]["text"] == SAYS and got[0]["kind"] == "remark")

# ---- pictures ----------------------------------------------------------------------------------------------------------------------
W, H = 640, 480
order = ["looking", "said", "cant_see", "no_voice", "garage_follow", "gone"]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(pics[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/describe.png")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
