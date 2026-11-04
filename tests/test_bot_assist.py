"""The bot as an assistant, in media mode: what you ask it to do done at once, typed, said or sent from the web page,
with its bot set up or not (asked of one that is, its model still answers the questions it knows the answers to); its
pages, Today, Chat and Work, left to right; the Today page (your list ticked off and taken off, timers, reminders,
notes); timers and reminders said as they come due (a chime with no voice, its face looking up); the status bar's
timer; how it talks (Settings > Bot, the web page; a persona of yours still wins); its face, drawn as it changes and
only it; and the web page's Bot tab: your day, and things done from there."""
import json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tba"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


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
            return self.reply(200, {"models": [{"name": "llama3.2:3b"}]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":
            return self.reply(200, {"capabilities": ["completion"]})
        asked.append(body)
        time.sleep(0.4)
        return self.reply(200, {"response": "It's a lovely mild day out there."})


ol = ThreadingHTTPServer(("127.0.0.1", 11573), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()

shots, parts = [], []


class FB:
    w, h = 640, 480
    count = 0

    def __init__(self):
        self.frames = 0

    def show(self, img):
        FB.count += 1
        self.frames = FB.count
        shots.append(img.copy())

    def show_part(self, img, box):
        FB.count += 1
        self.frames = FB.count
        parts.append((tuple(box), img.crop(box)))

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.weather.data = {"temp": 71.4, "feels": 70, "humidity": 64, "wind": 9, "code": 2, "units": "F",
                  "days": [{"date": "2026-10-31", "code": 2, "hi": 75, "lo": 59, "rain": 10, "sunrise": "06:52",
                            "sunset": "18:21"}]}
chimed, toasts = [], []
m.voice.chime = lambda device="", volume=100: chimed.append((device, volume)) or True
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))
A = m.assist
check(f"what's asked of it, kept where the tests keep it ({A.path})", A.path == S + "/assist.json")


def frame():
    m.dirty = True
    m.flush()
    return shots[-1]


def typed(text):
    m.press("a")
    for ch in text:
        m.keyboard_key("char", ch)
    m.keyboard_key("done")


def said(n=1):
    return [(x["who"], x["kind"], x["text"]) for x in m.friend.log[-n:]]


# ---- its pages, left to right -------------------------------------------------------------------------------------
fi = m.tab_index("friend")
m.open_app(fi)
check("the Bot: chatting, at first", m.bot_mode() == "chat" and m.on_friend_page() and m.on_face_page())
unset = frame()
check(f"...not set up: its face asleep ({m.face_look()})", m.face_look() == "sleepy")
m.press("left")
check("left: Today", m.bot_mode() == "today" and m.on_today_page() and m.on_face_page() and not m.on_friend_page())
m.press("left")
check("...left again: still Today (the first)", m.bot_mode() == "today")
m.press("right"); m.press("right")
check("right, right: at work", m.bot_mode() == "work" and m.on_coder_page() and not m.on_face_page())
m.press("right")
check("...right again: still at work (the last)", m.bot_mode() == "work")
m.press("left"); m.press("left")
check("back to Today", m.bot_mode() == "today")
empty_today = frame()

# ---- the Today page, with no bot set up ---------------------------------------------------------------------------
toasts.clear()
typed("set a timer for 1 minute")
check(f"typed on Today: a timer, set at once ({[(x['secs'], x['label']) for x in A.timers]})",
      [(x["secs"], x["label"]) for x in A.timers] == [(60, "")])
check(f"...in the conversation, its answer in its own words ({said(2)})",
      said(2)[0][:2] == ("you", "chat") and said(2)[0][2] == "set a timer for 1 minute" and said(2)[1][1] == "done"
      and said(2)[1][2].endswith("Timer set for 1 minute.") and said(2)[1][2].split()[0] in ("Okay.", "Sure.", "Done.", "Got"))
check(f"...and said where you are ({toasts})", toasts and toasts[-1] == said()[0][2])
check(f"the status bar: how long it has left ({m.assist_status()!r}, {m.status_signature()[-1]!r})",
      m.assist_status() == "1 min" and m.status_signature()[-1] == "1 min")
typed("milk")
typed("add eggs to my list")
typed("remind me in 20 minutes to take the pizza out")
typed("take a note the car is on level 3")
check(f"...a plain thing: on your list; and the rest ({[x['text'] for x in A.tasks]}, {[r['text'] for r in A.reminders]}, "
      f"{[x['text'] for x in A.notes]})", [x["text"] for x in A.tasks] == ["Milk", "Eggs"]
      and [r["text"] for r in A.reminders] == ["take the pizza out"] and A.notes[-1]["text"] == "The car is on level 3")
check(f"...the reminder said back: when ({said()[0][2]!r})", said()[0][2].endswith(
      "Noted.") and "in 20 minutes" in m.friend.log[-3]["text"])
today = frame()
m.today_sel = 0
m.press("x")
check(f"X: Milk done, at the bottom ({[(x['text'], bool(x.get('done'))) for x in m.today_rows()]})",
      [(x["text"], bool(x.get("done"))) for x in m.today_rows()] == [("Eggs", False), ("Milk", True)])
m.press("down")
m.press("x")
check("...X again: back on your list", not A.tasks[0].get("done"))
m.press("select")
check("SELECT once: asks first", len(A.tasks) == 2 and m.confirm[0] == "taskdrop")
m.press("select")
check(f"...twice: off your list ({[x['text'] for x in A.tasks]})", [x["text"] for x in A.tasks] == ["Milk"])
typed("eggs")

# ---- said to it: no bot needed ------------------------------------------------------------------------------------
toasts.clear()
m.bot_heard("set a pasta timer for ten minutes")
check(f"said (its wake phrase, then this): done, no bot needed ({[(x['secs'], x['label']) for x in A.own_timers()]})",
      (600, "pasta") in [(x["secs"], x["label"]) for x in A.own_timers()] and said()[0][1] == "done")
m.bot_heard("what time is it")
check(f"...a question it knows: answered, with no bot to ask ({said()[0][2]!r})", said()[0][2].startswith("It's ")
      and said()[0][1] == "done")
m.bot_heard("tell me a joke")
check(f"...anything else: it says it needs setting up ({toasts[-1]!r})", "Set up your bot first" in toasts[-1])

# ---- come due -----------------------------------------------------------------------------------------------------
toasts.clear()
first = min(A.own_timers(), key=lambda x: x["until"])
first["until"] = time.time() - 1
m.assist_next = 0
m.tick()
check(f"a timer up: said, kept in the conversation ({said()}), a chime with no voice ({chimed})",
      said()[0][1:] == ("alarm", "Time's up!") and len(chimed) == 1 and toasts[-1] == "Time's up!")
check(f"...its face looks up ({m.face_look()})", m.face_look() == "alert")
alarm = frame()
m.alarm_until = 0
check("...not for long", m.face_look() != "alert")
A.reminders[0]["at"] = time.time() - 1
m.assist_next = 0
m.tick()
check(f"a reminder: said ({said()[0][2]!r})", said()[0][2] == "Reminder: take the pizza out." and not A.reminders)
m.alarm_until = 0
m.assist_heard("wake me up at 7")
check(f"an alarm ({said()[0][2]!r})", said()[0][2].endswith("Alarm set for tomorrow at 7:00 AM.")
      and A.reminders[0].get("alarm") and time.localtime(A.reminders[0]["at"]).tm_hour == 7)
A.reminders[0]["at"] = time.time() - 1
m.assist_next = 0
m.tick()
check(f"...when it goes off ({said()[0][2]!r})", said()[0][2].startswith("It's ")
      and said()[0][2].endswith("Here's your alarm!") and not A.reminders)
m.alarm_until = 0
m.assist_heard("set an alarm for 6 pm")
m.assist_heard("cancel my alarm")
check(f"...one cancelled ({said()[0][2]!r})", said()[0][2].endswith("Alarm off.") and not A.reminders)
m.assist_heard("set a timer")
check(f"a timer, but how long? ({said()[0][2]!r})", said()[0][2] == 'For how long? Say "set a timer for 10 minutes".')

# ---- set up: its model, for the rest ------------------------------------------------------------------------------
m.friend_set(server="127.0.0.1:11573", model="llama3.2:3b")
check("set up", m.friend.ready())
m.press("right")
check("chatting", m.on_friend_page())
asked.clear()
m.friend_send("what's on my list")
check(f"asked what's on your list: answered at once, not by its model ({said()[0][2]!r})",
      said()[0][2] == "You have 2 things on your list: Milk and Eggs." and not asked)
m.friend_send("what's the weather like?")
check("...the weather: its model answers (in its own way)", m.friend.busy)
for _ in range(60):
    m.tick(); m.flush()
    if not m.friend.busy:
        break
    time.sleep(0.05)
p = asked[-1]["prompt"] if asked else ""
check(f"...told your list, your timers and notes, and what's done without it",
      "Their to-do list: Milk; Eggs" in p and "A timer for pasta is running" in p and "level 3" in p
      and "set a timer for 10 minutes" in p and said()[0][2] == "It's a lovely mild day out there.")
chat = frame()

# ---- how it talks ---------------------------------------------------------------------------------------------------
m.friend_setup()
keys = [r[0] for r in m.settings_rows()]
m.set_sel = keys.index("f_char")
m.press("a")
m.press("l"); m.press("l")                         # (Character: from Eyes to Name, then round to Voice, the last)
m.press("down"); m.press("down"); m.press("down")
check(f"Settings > Bot > Character > Voice: How it talks, after Voice ({m.char_keys()}, {m.char_key()})",
      m.char_keys() == ("voice", "speak", "pause_music", "style", "chatter") and m.char_key() == "style")
check(f"...Friendly at first ({m.char_value('style')})", m.char_value("style") == "Friendly")
toasts.clear()
m.press("right")
check(f"right: Big brother, kept, and a taste of it ({toasts})", "style = brother" in open(HOME + "/bot.txt").read()
      and m.friend.style()["name"] == "Big brother" and toasts[-1] == "You got it. Timer set for 10 minutes.")
style_shot = frame()
check("...its model's told how to talk", "laid-back big brother" in m.friend.system()
      and m.friend.system().startswith("You are a friendly little bot") and "Reply in one to three" in m.friend.system())
m.press("left")
check("left: back to Friendly, its name told it too", m.friend.style()["key"] == "friendly"
      and m.friend.system() == g.FRIEND_PERSONA + " Your name is Potato.")
m.press("left")
check(f"...left again: round to the last ({m.friend.style()['name']})", m.friend.style()["name"] == "Calm")
m.friend_set(style="pirate")
m.web_tab("Bot")
m.bot_set_mode("chat")
m.friend_send("set a timer for 3 minutes")
check(f"a pirate does what you ask: {said()[0][2]!r}", said()[0][2].split(" Timer")[0] in g.FRIEND_STYLES[3][3])
x = min(A.own_timers(), key=lambda t: t["secs"])
x["until"] = time.time() - 1
m.assist_next = 0
m.tick()
check(f"...and says so when it's up: {said()[0][2]!r}", said()[0][2] == "Ahoy! Time's up!")
m.alarm_until = 0
open(HOME + "/bot.txt", "a").write("persona = You are a grumpy cat.\n")
m.friend.load(m.friend_files())
check("a persona of yours: still how it talks to its model", m.friend.system() == "You are a grumpy cat.")
m.friend_set(persona="", style="friendly")

# ---- its face: drawn as it changes, and only it ---------------------------------------------------------------------
m.web_tab("Bot"); m.bot_set_mode("chat")
frame()
n_shots, n_parts = len(shots), len(parts)
end = time.monotonic() + 9
while time.monotonic() < end:
    m.tick(); m.flush()
    time.sleep(max(0.0, min(m.tick_limit(), 0.25)))
blinks = parts[n_parts:]
box = m.face_shot[1]
check(f"9 seconds idle: the face alone drawn again, a few times ({len(blinks)} parts, {len(shots) - n_shots} whole)",
      2 <= len(blinks) <= 60 and all(b == box for b, _ in blinks) and len(shots) - n_shots <= 3)
m.voice.speaking = True
check(f"about to talk (its voice getting ready, nothing heard yet): still thinking ({m.face_look()})",
      m.face_look() == "thinking")
m.voice.sounding = time.monotonic() + 30            # (heard: aplay has its first samples)
check(f"talking, heard: its mouth ({m.face_look()})", m.face_look() == "talking")
n_parts = len(parts)
end = time.monotonic() + 1.0
m.face_next = 0
while time.monotonic() < end:
    m.tick(); m.flush()
    time.sleep(max(0.0, min(m.tick_limit(), 0.25)))
check(f"...a dozen frames a second ({len(parts) - n_parts})", 8 <= len(parts) - n_parts <= 14)
m.voice.speaking = False
m.friend.busy = True
check(f"thinking ({m.face_look()})", m.face_look() == "thinking")
m.friend.busy = False
check(f"tick_limit: no later than its next change ({m.tick_limit():.3f})", m.tick_limit() <= 0.25)
m.toast("Something else")
m.flush()
check("something else on the screen: the whole page again, not just the face", shots[-1] is not None
      and m.face_shot[2] == m.fb.frames)

# looks, for a look at them
looks = []
for look in ("idle", "happy", "sad", "curious", "thinking", "listening", "talking", "alert", "sleepy", "cool"):
    im = Image.new("RGB", (200, 160), g.ROW)
    d = ImageDraw.Draw(im)
    g.draw_face(d, 100, 86, 112, look, 0.4, g.TEXT, g.ROW, font=m.fonts["small"])
    looks.append(im)

# ---- the web page ---------------------------------------------------------------------------------------------------
m.friend_set(server="")
out = m.web_friend_do({"do": "say", "text": "add bread to my list"})
check(f"the web page, its bot not set up: done all the same ({out})", out.get("ok") and out.get("done")
      and A.tasks[-1]["text"] == "Bread")
out = m.web_friend_do({"do": "say", "text": "tell me a joke"})
check(f"...anything else: set it up first ({out})", out.get("error") == "Set up your bot first")
w = m.web_friend()
t = w["today"]
check(f"its Bot tab: your day ({[x['text'] for x in t['tasks']]}, {[x['name'] for x in t['timers']]}, {t['notes']})",
      [x["text"] for x in t["tasks"]] == ["Milk", "Eggs", "Bread"] and t["timers"][0]["name"] == "The pasta timer"
      and t["notes"] == ["The car is on level 3"] and w["style"] == "friendly" and ["pirate", "Pirate"] in w["styles"])
bread = t["tasks"][-1]
out = m.web_friend_do({"do": "tick", "text": "Bread", "t": bread["t"]})
check(f"...ticked off there ({out})", out == {"ok": True} and A.tasks[-1].get("done"))
out = m.web_friend_do({"do": "drop", "text": "Bread", "t": bread["t"]})
check("...taken off", out == {"ok": True} and "Bread" not in [x["text"] for x in A.tasks])
check("...one that isn't there", m.web_friend_do({"do": "tick", "text": "Bread", "t": bread["t"]}).get("error"))
check("...added there", m.web_friend_do({"do": "task", "text": "  call  the bank "}) == {"ok": True}
      and A.tasks[-1]["text"] == "Call the bank")
check("...once", m.web_friend_do({"do": "task", "text": "call the bank"}).get("error"))
out = m.web_friend_do({"do": "set", "style": "robot"})
check(f"how it talks, from the web page ({out})", out == {"ok": True} and m.friend.style()["key"] == "robot")
check("...not a made-up one", m.web_friend_do({"do": "set", "style": "evil"}).get("error"))
m.friend_set(style="")

# ---- a look at it ---------------------------------------------------------------------------------------------------
m.tab = m.tab_index("music") if m.tab_index("music") is not None else m.tab
music = None
for i, tab in enumerate(g.LIBRARY):
    if tab.get("kind") == "audio":
        m.tab, m.view = i, "list"
        m.load_tab(i)
        music = frame()
        break
sheet = Image.new("RGB", (1280, 1440 + 320), (0, 0, 0))
for k, im in enumerate([unset, today, alarm, chat, style_shot, music or chat]):
    sheet.paste(im, ((k % 2) * 640, (k // 2) * 480))
for k, im in enumerate(looks):
    sheet.paste(im, ((k % 6) * 210 + 10, 1450 + (k // 6) * 165))
sheet.save(SP + "/out/assist_sheet.png")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
