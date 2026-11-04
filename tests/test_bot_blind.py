"""The bot looks with its one model, assumed to see: no "Model that can see" to set (Settings > Bot, the web page);
a model Ollama doesn't list as seeing (qwen3.8) looks all the same, and does; one that really can't (llama) is shown
the picture once, and then: asked what it sees, it answers without the picture, told it can't see; sent a picture,
it says it can't see it; asked to Describe, it says it can't see; a picture it's asked to take is still taken; its
remarks about what it sees go quietly to something else, and stop being a topic. An old eyes = in bot.txt is left
alone, and not used."""
import io, json, os, random, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_bot_blind"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("dirs"):
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
sys.path.insert(0, SP)
import gk_static; gk_static.use_home(g, HOME)
g.CAM_PORTS = (5061,)
g.CAM_LINKS = []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


asked, shown = [], []


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            return self.reply(200, {"models": [{"name": n} for n in ("qwen3.8:27b", "llama3.2:3b")]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":              # (neither listed as seeing: it isn't asked anyway)
            shown.append(body.get("model"))
            return self.reply(200, {"capabilities": ["completion"]})
        asked.append(body)
        if body.get("images"):
            if body["model"] == "llama3.2:3b":
                return self.reply(400, {"error": "llama3.2:3b does not support images"})
            return self.reply(200, {"response": "I can see a blue picture."})
        if "can't see" in body["prompt"]:
            return self.reply(200, {"response": "Sorry, I can't see pictures."})
        return self.reply(200, {"response": "Sure, I'm here."})


ol = ThreadingHTTPServer(("127.0.0.1", 11561), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()


class Link(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        b = io.BytesIO(); Image.new("RGB", (320, 240), (30, 60, 220)).save(b, "JPEG"); body = b.getvalue()
        self.send_response(200); self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


cam_srv = ThreadingHTTPServer(("127.0.0.1", 5062), Link)
threading.Thread(target=cam_srv.serve_forever, daemon=True).start()
open(HOME + "/bot.txt", "w").write("server = 127.0.0.1:11561\nmodel = qwen3.8:27b\neyes = llava\nname = Sam\n")
open(HOME + "/camera.txt", "w").write("camera = http://127.0.0.1:5062/snap.jpg   Porch\n")
Image.new("RGB", (800, 600), (240, 140, 30)).save(HOME + "/Pictures/sunset.jpg")


class FB:
    w, h = 640, 480

    def show(self, img):
        pass

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


settle(lambda: not fr.busy)
# ---- one model; no "Model that can see" ---------------------------------------------------------------------------
m.tab = m.tab_index("settings"); m.set_page = "friend"
rows = [r[1] for r in m.settings_rows()]
check(f"Settings › Bot: Model, and no model for seeing ({rows})", "Model" in rows and not any("see" in r for r in rows))
w = m.web_friend()
check(f"the web page: no eyes ({sorted(w)})", "eyes" not in w and w["sees"] is True)
check(f"...setting eyes there does nothing ({m.web_friend_do({'do': 'set', 'eyes': 'gemma3:4b'})})",
      m.web_friend_do({"do": "set", "eyes": "gemma3:4b"}) == {"error": "Nothing to change"}
      and "eyes = gemma3" not in open(HOME + "/bot.txt").read())
check("an old eyes = in bot.txt: left there, not used", "eyes = llava" in open(HOME + "/bot.txt").read()
      and not hasattr(fr, "eyes"))
m.tab = fi

# ---- a model Ollama doesn't list as seeing: it looks all the same ---------------------------------------------------
check("its model's assumed to see", fr.sees())
random.seed(3)
check("...so what it sees is a topic (with a camera)", "sight" in {m.friend_topic() for _ in range(200)})
asked.clear()
ok, why = m.camera_describe(m.friend_camera())
check("Describe", ok and settle(lambda: not fr.busy and m.cam_bot and not m.cam_bot["busy"]))
check(f"...it looked, with its model ({m.cam_bot['text']!r})", m.cam_bot["text"] == "I can see a blue picture."
      and asked[-1]["model"] == "qwen3.8:27b" and asked[-1].get("images") and not shown)
check("...and nothing asked Ollama what it can do", shown == [])

# ---- one that really can't see ---------------------------------------------------------------------------------------
m.friend_set(model="llama3.2:3b")
check("another model: assumed to see too", fr.sees())
asked.clear()
m.friend_send("what do you see?")
check("asked what it sees", settle(lambda: not fr.busy))
last = fr.log[-1]
check(f"...shown the picture once, then it answers without it, told it can't see ({last['text']!r})",
      len(asked) == 2 and asked[0].get("images") and not asked[1].get("images")
      and "You can't see" in asked[1]["prompt"] and last["kind"] == "chat" and last["text"] == "Sorry, I can't see pictures."
      and not last.get("pic") and fr.vision.get("llama3.2:3b") is False and not fr.sees())
asked.clear()
m.friend_send("what do you see now?")
settle(lambda: not fr.busy)
check("...and from then on it isn't shown one", len(asked) == 1 and not asked[0].get("images")
      and "You can't see" in asked[0]["prompt"])
asked.clear()
fr.say("what's this?", picture=HOME + "/Pictures/sunset.jpg")
settle(lambda: not fr.busy)
you = fr.log[-2]
check(f"sent a picture: your line keeps it, and it says it can't see it ({fr.log[-1]['text']!r})",
      you["who"] == "you" and you.get("pic") and fr.log[-1]["kind"] == "chat" and not asked[-1].get("images")
      and "sent you a picture, but you can't see pictures" in asked[-1]["prompt"])
ok, why = m.camera_describe(m.friend_camera())
settle(lambda: not fr.busy and not m.cam_bot["busy"])
check(f"Describe (asked to look, it tries): it says it can't see ({m.cam_bot['text']!r})", m.cam_bot["error"]
      and m.cam_bot["text"] == "I can't see: llama3.2:3b can't see pictures" and asked[-1].get("images"))
asked.clear()
m.friend_send("take a picture")
settle(lambda: not fr.busy)
check(f"a picture it's asked to take: taken, nothing said about it ({fr.log[-1]['text']!r})",
      fr.log[-1]["kind"] == "photo" and fr.log[-1]["text"] == "Here's the picture from Porch. It's in Photos too."
      and not any(a.get("images") for a in asked))
check("...what it sees isn't a topic any more", "sight" not in {m.friend_topic() for _ in range(200)})
# a remark about what it sees, for a model found not to see just then: something else, quietly
fr.vision.clear()
asked.clear()
n = len(fr.log)
fr.remark("sight")
settle(lambda: not fr.busy)
check(f"a remark about what it sees, its model not seeing: something else instead, no error ({fr.log[-1]['text']!r})",
      len(fr.log) == n + 1 and fr.log[-1]["kind"] == "remark" and asked[0].get("images") and not asked[1].get("images")
      and g.FRIEND_ASKS["anything"] in asked[1]["prompt"] and not fr.log[-1].get("pic"))
# back to the one that sees
m.friend_set(model="qwen3.8:27b")
check("back to the model that sees: it sees", fr.sees())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
