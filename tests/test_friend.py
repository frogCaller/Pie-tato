"""The smart friend against a pretend Ollama: set-up in Settings, talking, its face, the facts it
knows, looking through the camera, the ways Ollama can say no, remarks, and the home screen."""
import io, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t52"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
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


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- a pretend Ollama ------------------------------------------------------------------------
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
            return self.reply(200, {"models": [{"name": n} for n in ("qwen3:8b", "llama3.2:3b", "gemma3:4b", "old:1b")]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":                  # what a model can do: gemma3 can see
            return self.reply(200, {"capabilities": ["completion", "vision"] if body.get("model") == "gemma3:4b"
                                    else ["completion"]})
        asked.append(body)
        m = body["model"]
        if m == "missing":
            return self.reply(404, {"error": f"model '{m}' not found"})
        if m == "old:1b" and "think" in body:
            return self.reply(400, {"error": f"registry.ollama.ai/library/{m} does not support thinking"})
        if body.get("images") and m != "gemma3:4b":
            return self.reply(500, {"error": "this model is missing data required for image input"})
        if m == "qwen3:8b" and body["options"]["num_predict"] != -1:
            return self.reply(200, {"response": "", "thinking": "Let me think about the weather..."})
        if body.get("images"):
            return self.reply(200, {"response": "I can see bright colour bars, like a test pattern."})
        if "Greet them" in body["prompt"]:
            return self.reply(200, {"response": "<think>hmm</think>Hello! Lovely to see you, it's a great evening."})
        if "weather" in body["prompt"].split("now says:")[-1].lower():
            return self.reply(200, {"response": "**It's sunny and warm** — 71°F. Nice for a walk!"})
        return self.reply(200, {"response": "Sure, I'm here.\n\nWhat would you like to talk about?"})


ol = ThreadingHTTPServer(("127.0.0.1", 11555), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()
SERVER = "127.0.0.1:11555"

# ---- the small parts --------------------------------------------------------------------------
check("a bare address gets Ollama's port", g.ollama_url("192.168.1.20") == "http://192.168.1.20:11434")
check("...a port of its own is kept", g.ollama_url("pc.local:11500") == "http://pc.local:11500")
check("...and a link", g.ollama_url("http://10.0.0.2:11434/") == "http://10.0.0.2:11434")
check("tidy: no reasoning, no markdown, no quotes", g.friend_tidy('<think>x</think>"**Hi** there\n- a *b*"') == "Hi there - a b")
long = g.friend_tidy("word " * 200)
check(f"tidy: long answers cut at a word ({len(long)})", len(long) <= g.FRIEND_LIMIT + 1 and long.endswith("…"))
faces = {t: g.friend_face(t, "chat")[1] for t in ("Sorry, I don't know.", "Time for bed, goodnight.",
                                                    "Want to play a game?", "Great news! It's a lovely day!",
                                                    "That is nice.", "Cold, wet and grim out there.", "Okay.")}
check(f"faces: {faces}", list(faces.values()) == ["sorry", "sleepy", "curious", "cool", "happy", "worried", "pleased"])
check("thinking while it's busy", g.friend_face("", "", busy=True)[1] == "thinking")
check("it wants its eyes for 'what do you see'", g.friend_wants_eyes("What do you see?") and not g.friend_wants_eyes("seed prices"))

# ---- media mode ------------------------------------------------------------------------------------
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.weather.data = {"temp": 71.4, "feels": 70, "humidity": 64, "wind": 9, "code": 2, "units": "F",
                  "days": [{"date": "2026-10-12", "code": 2, "hi": 75, "lo": 59, "rain": 10, "sunrise": "06:52",
                            "sunset": "18:21"}, {"date": "2026-10-13", "code": 61, "hi": 66, "lo": 55}]}
m.crypto.quotes["bitcoin"] = {"t": time.time(), "d": {"symbol": "BTC", "price": 101234.5, "change_24h": 2.3}}


def settle(cond, secs=8):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


# the home screen: 15 icons (Apps' and Games too; the Bot at work is the Bot), three full rows of five
apps = [a for a, _ in m.home_apps()]
check(f"Bot on the home screen: {apps}", "Bot" in apps and "Coder" not in apps and len(apps) == 15)
m.view = "home"; m.home_sel = 0
m.dirty = True; m.flush()
home_shot = shots[-1]
cols = g.home_cols(15)
slots = g.home_layout(15, cols)
check(f"5 across, three full rows: {slots[10:]}", cols == 5 and [c for _, c in slots[10:]] == [0, 1, 2, 3, 4])
short = g.home_layout(14, 5)
check(f"(one fewer: the short last row in the middle {short[10:]})", [c for _, c in short[10:]] == [0.5, 1.5, 2.5, 3.5])
m.home_sel = apps.index("Weather")
m.press("down")
check(f"down from Weather: {apps[m.home_sel]}", apps[m.home_sel] == "System")
m.home_sel = apps.index("Finance")
m.press("down")
check(f"down from Finance: {apps[m.home_sel]}", apps[m.home_sel] == "Settings")
m.press("up")
check(f"up from Settings: {apps[m.home_sel]}", apps[m.home_sel] == "Finance")
m.press("up")
check(f"up from Finance: {apps[m.home_sel]}", apps[m.home_sel] == "Camera")
m.home_sel = apps.index("Games")
m.press("down")
check(f"down from Games (in the middle): {apps[m.home_sel]}", apps[m.home_sel] == "Files")

# not set up: the Bot app says so, A goes to Settings
fi = m.tab_index("friend")
m.open_app(fi)
m.flush()
check("not set up: the app says so", m.tab_type() == "friend" and not m.friend.ready())
unset_shot = shots[-1]
m.press("a")
check("A: its settings, on the Bot itself", m.tab_type() == "friend" and m.bot_settings and m.set_page == "friend")
m.press("a")                                       # the computer
check("the computer's address on the keyboard, digits first", m.view == "keys" and m.kb["r"] == 0)
for ch in SERVER:
    m.keyboard_key("char", ch)
m.keyboard_key("done")
txt = open(HOME + "/bot.txt").read()
check(f"saved in bot.txt with a word on it: {txt!r}", "server = 127.0.0.1:11555" in txt and txt.startswith("# Bot:"))
check("its models", settle(lambda: m.friend.models == ["gemma3:4b", "llama3.2:3b", "old:1b", "qwen3:8b"]))
settings_shot = shots[-1]
m.press("down"); m.press("a")
check("Model: the list from that computer", m.set_page == "f_models")
m.dirty = True; m.flush()
models_shot = shots[-1]
rows = m.settings_rows()
m.set_sel = [r[1] for r in rows].index("llama3.2:3b")
m.press("a")
check("picked", "model = llama3.2:3b" in open(HOME + "/bot.txt").read() and m.set_page == "friend"
      and m.settings_rows()[m.set_sel][0] == "f_model")
check(f"Settings › Bot: its Character first, no 'Model that can see', just Model; Listens, where Vosk runs "
      f"({[r[1] for r in m.settings_rows()]})",
      [r[0] for r in m.settings_rows()] == ["f_char", "f_server", "f_model", "f_listen", "f_face"])
m.set_sel = 0; m.press("a")                        # (its Character: what it calls you, how often it chats)
m.char_sec, m.char_row = 0, 1
m.press("a")
for ch in "Sam":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check("what it calls you (in its Character)", m.friend.name == "Sam" and m.on_char_page())
m.char_sec, m.char_row = 4, 4
m.press("right")
check(f"says something by itself: {m.friend.chatter_text()}", m.friend.chatter() == 60)
m.press("left")
check("...and back", m.friend.chatter() == 30)
m.press("b")
m.press("b")
check("B: back to the Bot", m.tab_type() == "friend" and not m.bot_settings and m.set_page == "root")
m.dirty = True; m.flush()
root_shot = shots[-1]

# it says hello when the app opens
asked.clear()
m.open_app(fi)
check("opened: it says hello", settle(lambda: not m.friend.busy and m.friend.log))
hello = m.friend.log[-1]
check(f"...tidied: {hello['text']!r}", hello["text"] == "Hello! Lovely to see you, it's a great evening." and hello["kind"] == "remark")
check(f"...with a face to match: {m.friend.face()}", m.friend.face()[1] == "cool")
p = asked[-1]
check("asked the way PiE-ink does: no thinking, kept warm, not streamed",
      p["think"] is False and p["keep_alive"] == "30m" and p["stream"] is False and p["model"] == "llama3.2:3b")
check("it knows the time, the weather and the coins",
      "Time: " in p["prompt"] and "Weather now: 71°F, partly cloudy" in p["prompt"] and "BTC $101,234.50 (+2.3% in a day)" in p["prompt"])
check("...and who it lives with", "called Sam" in p["system"])

# talking
m.press("a")
check("A: the keyboard", m.view == "keys")
for ch in "what's the weather like?":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check("your line, then thinking", m.friend.log[-1]["who"] == "you" and m.friend.busy)
m.flush()
thinking_shot = shots[-1]
check("its answer", settle(lambda: not m.friend.busy))
check(f"...tidied: {m.friend.log[-1]['text']!r}", m.friend.log[-1]["text"] == "It's sunny and warm — 71°F. Nice for a walk!")
p = asked[-1]["prompt"]
check("it follows the thread", "The conversation so far:" in p and "You said: Hello! Lovely" in p
      and p.rstrip().endswith("Reply to them, carrying on from what was already said.") and "Sam now says: what's the weather like?" in p)
m.flush()
chat_shot = shots[-1]

# Y: something of its own
m.press("y")
check("Y: a remark of its own", settle(lambda: not m.friend.busy and m.friend.log[-1]["kind"] == "remark"))

# looking through the camera
cam_jpeg = io.BytesIO(); Image.new("RGB", (640, 480), (200, 30, 30)).save(cam_jpeg, "JPEG")
m.camera.cams = [{"addr": "127.0.0.1:5999", "name": "Desk"}]
m.camera.snapshot = lambda addr, max_age=2.0: (cam_jpeg.getvalue(), None, time.time())
asked.clear()
m.friend.say("what do you see?")
settle(lambda: not m.friend.busy)
check(f"a model that can't see: shown the picture, then it answers without it, told it can't see "
      f"({m.friend.log[-1]['text']!r})", m.friend.log[-1]["kind"] == "chat" and len(asked) == 2
      and asked[0].get("images") and not asked[1].get("images")
      and "You can't see: you can't look at pictures" in asked[1]["prompt"] and not m.friend.log[-1].get("pic"))
m.friend_set(model="gemma3:4b")
m.friend.say("what do you see?")
settle(lambda: not m.friend.busy)
check("with a model that can see: it looks", asked[-1]["model"] == "gemma3:4b" and asked[-1].get("images")
      and "camera (Desk)" in asked[-1]["prompt"] and "colour bars" in m.friend.log[-1]["text"])
m.camera.snapshot = lambda addr, max_age=2.0: None
m.friend.say("what do you see now?")
settle(lambda: not m.friend.busy)
check("the camera not answering: it's told why", "can't see anything right now (the camera Desk didn't answer)" in asked[-1]["prompt"]
      and not asked[-1].get("images"))
m.friend_set(model="llama3.2:3b")

# the ways Ollama says no
for model, want in (("qwen3:8b", "Sure, I'm here."), ("old:1b", "Sure, I'm here.")):
    m.friend_set(model=model)
    m.friend.say("hi")
    settle(lambda: not m.friend.busy)
    check(f"{model}: {m.friend.log[-1]['text'][:40]!r}", m.friend.log[-1]["text"].startswith(want))
check("a model that only thought was asked again, plainly", any(a["model"] == "qwen3:8b" and a["options"]["num_predict"] == -1
                                                             and "think" not in a for a in asked))
check("an older Ollama: asked again without 'think'", any(a["model"] == "old:1b" and "think" not in a for a in asked))
m.friend_set(model="missing")
m.friend.say("hi")
settle(lambda: not m.friend.busy)
check(f"a model it doesn't have: {m.friend.log[-1]['text']!r}", "doesn't have missing" in m.friend.log[-1]["text"])
m.friend_set(server="127.0.0.1:1", model="llama3.2:3b")
m.friend.say("hi")
settle(lambda: not m.friend.busy)
check(f"nothing listening: {m.friend.log[-1]['text']!r}", m.friend.log[-1]["text"].startswith("Can't reach 127.0.0.1:1"))
m.friend_set(server=SERVER)
m.flush()
error_shot = shots[-1]

# kept between start-ups
n = len(m.friend.log)
check("kept on disk, for root only", oct(os.stat(g.FRIEND_LOG).st_mode & 0o777) == "0o600")
m2 = g.Media()
check(f"a new start-up has the conversation ({len(m2.friend.log)})", len(m2.friend.log) == n)

# by itself, now and then
m.friend.load(m.friend_files())
m.friend_opened_at = time.time() - 31 * 60
m.friend.log[-1]["t"] = time.time() - 31 * 60
m.friend_jitter = 1.0
before = len(m.friend.log)
check("30 minutes quiet: it says something", settle(lambda: len(m.friend.log) == before + 1 and not m.friend.busy))
check("...not again straight away", not settle(lambda: len(m.friend.log) > before + 1, 1.5))

# X: its menu; Clear the conversation asks first
m.press("x"); m.press("up"); m.press("a")
check(f"X, Clear: asks first ({m.friend_options()[-1][0]!r})", m.friend.log and m.friend_options()[-1][0] == "Press A again to clear it")
m.press("a")
check("A again: cleared", m.friend.log == [] and json.load(open(g.FRIEND_LOG)) == [])
m.dirty = True; m.flush()
empty_shot = shots[-1]

# the web page's app list has it
check("in the web page's apps", any(a["name"] == "Bot" for a in m.web_catalog()["apps"]))
check("its icon draws", m.web_icon("Bot", 96)[:4] == b"\x89PNG")

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 5 - 10), (80, 80, 80))
for k, im in enumerate([home_shot, unset_shot, settings_shot, models_shot, root_shot, thinking_shot, chat_shot,
                        error_shot, empty_shot]):
    sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/friend_sheet.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
