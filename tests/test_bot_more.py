"""The bot, asked for more in media mode: "I'm bored" (a game of yours, or cartoons: yes starts it, no doesn't), a game
(any of yours, or one by name; Snake when there are none), something to watch (cartoons, a film, a channel: your
streams, or Plex's live ones; the news, sports, one by name) and the next channel; updating, restarting and shutting
down (asked first: yes does it); the camera's picture turned, and a camera that turns turned; listening while music
plays or is paused (what's playing quieter while you talk), not while a game is on; what it's called said with what you
ask ("potato, shut down"); asked your own way ("I want to play shrek two", misheard "schreck to", "start shrek 2",
Mega Man X isn't 10, "miles davies"); your photos (the camera roll, the newest, the next, a slideshow, today's); its
model asking for something to be done ("[[play Shrek 2]]", never yes for you, and its question kept); and its listening
face, its sound clear of its eye."""
import json, os, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tbm"
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
    if t.get("dirs"):                                  # (your Music and Videos: here)
        t["dirs"] = [d.replace("/home/*", S + "/home/*") for d in t["dirs"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# your games, your music, your streams, your camera
os.makedirs(HOME + "/Games")
for name in ("Super Mario World (USA).sfc", "Tetris (World).gb", "Pac-Man (USA).nes", "Sonic the Hedgehog (USA).gen",
             "Metal Gear (USA).nes", "Shrek 2 (USA).gba", "Mega Man X (USA).sfc", "Street Fighter II Turbo (USA).sfc"):
    open(os.path.join(HOME, "Games", name), "wb").write(b"\0" * 64)
os.makedirs(HOME + "/Music/Metal")
open(HOME + "/Music/Metal/Iron Song.mp3", "wb").write(b"\0" * 64)
os.makedirs(HOME + "/Music/Miles Davis")
open(HOME + "/Music/Miles Davis/So What.mp3", "wb").write(b"\0" * 64)
os.makedirs(HOME + "/Pictures")
for name, ago, colour in (("beach.jpg", 2 * 86400, (40, 120, 200)), ("cat.jpg", 60, (200, 120, 40))):
    Image.new("RGB", (64, 48), colour).save(HOME + "/Pictures/" + name)
    os.utime(HOME + "/Pictures/" + name, (time.time() - ago, time.time() - ago))
open(HOME + "/Music/Sunny Day.mp3", "wb").write(b"\0" * 64)
open(HOME + "/streams.txt", "w").write("BBC News | http://example.com/news.m3u8\nLofi Cam | http://example.com/lofi.m3u8\n")
open(HOME + "/camera.txt", "w").write("camera = 192.168.1.50 Porch\n")

# the emulators are here (the tests have none), and games and videos start as far as what they're given
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: None
g.built_for_other_pi = lambda core: False


class FB:
    w, h = 640, 480
    count = 0

    def __init__(self):
        self.frames = 0

    def show(self, img):
        FB.count += 1
        self.frames = FB.count

    def show_part(self, img, box):
        FB.count += 1
        self.frames = FB.count

    def close(self):
        pass


class FakeProc:
    """A player that's playing (for "next channel", and listening while something plays)."""
    def poll(self):
        return None


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts, started, played, acts, cmds = [], [], [], [], []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))


class FakeGame:
    """A game that's on (as far as the main loop looks at one)."""
    ended, state, error, disc, slow = False, "playing", None, None, False
    game = {}

    def __getattr__(self, name):                       # (pressed, sent, asked: nothing happens)
        return lambda *a, **k: None


def fake_open(it):
    started.append(it)
    m.game = FakeGame()


def fake_play(queue, i, start=None, show=True, note=None):
    played.append((queue, i))
    m.queue, m.qi, m.kind, m.cur = queue, i, queue[i]["kind"], queue[i]


m.game_open = fake_open
m.play = fake_play
m.system_do = lambda act: acts.append(act)
m.cmd = lambda c: cmds.append(c)
m.camera.start = lambda *a, **k: None
m.camera.scan = lambda *a, **k: None


def said(n=1):
    return [x["text"] for x in m.friend.log[-n:]]


def ask(text):
    """Said to it (its wake phrase, then this): its answer (None: none, here)."""
    last = m.friend.log[-1] if m.friend.log else None
    m.bot_heard(text)
    new = m.friend.log[-1] if m.friend.log else None
    return new["text"] if new is not None and new is not last and new["who"] == "friend" else None


def ticks(secs, until=lambda: False):
    end = time.monotonic() + secs
    while time.monotonic() < end and not until():
        m.tick(); m.flush()
        time.sleep(0.05)


m.open_app(m.tab_index("friend"))
labels = sorted(r["label"] for r in m.game_choices())
check(f"your games, as the bot sees them ({labels})", labels == [
    "Mega Man X", "Metal Gear", "Pac-Man", "Shrek 2", "Sonic the Hedgehog", "Street Fighter II Turbo", "Super Mario World",
    "Tetris"])

# ---- a game -----------------------------------------------------------------------------------------------------------
out = ask("play a game")
check(f"play a game: one of yours, any ({out!r})", len(started) == 1 and out == f"Starting {started[-1]['label']}."
      and started[-1]["label"] in labels and started[-1]["system"])
m.game = None
for text, want in (("play mario", "Super Mario World"), ("play tetris", "Tetris"), ("play pacman", "Pac-Man"),
                   ("play sonic the hedgehog", "Sonic the Hedgehog"), ("play a game of sonic", "Sonic the Hedgehog"),
                   ("play metal gear", "Metal Gear"), ("potato, play mario", "Super Mario World")):
    out = ask(text)
    check(f"{text!r}: {want} ({out!r})", started[-1]["label"] == want and out == f"Starting {want}.")
    m.game = None
n = len(started)
out = ask("play metal")
check(f"'play metal': your metal, not Metal Gear ({out!r})", len(started) == n and played
      and played[-1][0][0]["src"].endswith("Iron Song.mp3") and out.endswith("Playing Iron Song."))
out = ask("play a game of zelda")
check(f"...one you haven't ({out!r})", out == "I couldn't find zelda in your games." and len(started) == n)

# ---- asked your own way: numbers as words, misheard, said as an app ---------------------------------------------------
for text, want in (("I want to play shrek two", "Shrek 2"), ("I want to play the game schreck to", "Shrek 2"),
                   ("I wanna play the game shrek two", "Shrek 2"), ("can I play shrek 2", "Shrek 2"),
                   ("start shrek 2", "Shrek 2"), ("launch tetris", "Tetris"), ("play mega man x", "Mega Man X"),
                   ("play street fighter two turbo", "Street Fighter II Turbo"), ("play mega man", "Mega Man X")):
    out = ask(text)
    check(f"{text!r}: {want} ({out!r})", started[-1]["label"] == want and out == f"Starting {want}.")
    m.game = None
n = len(started)
out = ask("play miles davies")
check(f"'play miles davies' (misheard): your Miles Davis ({out!r})", len(started) == n
      and played[-1][0][0]["src"].endswith("So What.mp3"))
check("'open the pod bay doors': still the model's", m.assist_heard("open the pod bay doors") is False)

# ---- bored ------------------------------------------------------------------------------------------------------------
out = ask("I'm bored")
p = m.assist_asking()
check(f"I'm bored: a game of yours, or cartoons ({out!r})", p and "Say yes" in out and "cartoons" in out
      and any(x in out for x in labels))
question = out
out = ask("yes")
check(f"...yes: that game ({out!r})", started[-1]["label"] in question and out == f"Starting {started[-1]['label']}."
      and m.assist_asking() is None)
m.game = None
n = len(started)
ask("i'm so bored")
out = ask("no thanks")
check(f"...no: nothing ({out!r})", out == "Okay, no game then." and len(started) == n and m.assist_asking() is None)
check("yes, with nothing asked: its model's (not done here)", m.assist_heard("yes") is False)
ask("im bored")
m.assist_pending["until"] = time.monotonic() - 1
check("...asked a while ago: not an answer any more", m.assist_heard("yes") is False and len(started) == n)
os.rename(HOME + "/Games", HOME + "/Games.away")
out = ask("I'm bored")
check(f"no games of yours: cartoons? ({out!r})", "cartoons" in out and "Say yes" in out)
out = ask("yes")
q, i = played[-1]
check(f"...yes: a cartoon ({out!r})", q[i]["kind"] == "video" and q[i]["src"].startswith("ia:")
      and out == f"Here's {q[i]['title']}.")
out = ask("play a game")
check(f"play a game, with none of yours: Snake ({out!r})", out == "You haven't any games of your own yet, so here's Snake."
      and g.LIBRARY[m.tab].get("sim") == "snake")
os.rename(HOME + "/Games.away", HOME + "/Games")
m.open_app(m.tab_index("friend"))

# ---- something to watch -------------------------------------------------------------------------------------------------
out = ask("put on some cartoons")
q, i = played[-1]
check(f"cartoons: one of the TV menu's ({out!r})", q[i]["src"].startswith("ia:") and out == f"Here's {q[i]['title']}."
      and all(r["src"].startswith("ia:") for r in q))
toon_titles = [t[0] for t in g.SHELVES["toons"][0]["Popeye"]]
out = ask("watch popeye")
q, i = played[-1]
check(f"...one by name: Popeye ({out!r})", q[i]["title"] in toon_titles and len(q) == len(toon_titles))
out = ask("watch a movie")
q, i = played[-1]
film_titles = [t[0] for f in g.SHELVES["movies"][0].values() for t in f]
check(f"a film ({out!r})", q[i]["title"] in film_titles)
out = ask("turn on a channel")
q, i = played[-1]
check(f"a channel, not signed in to Plex: one of your streams ({out!r})", q[i]["kind"] == "live"
      and q[i]["title"] in ("BBC News", "Lofi Cam") and len(q) == 2)
first = q[i]["title"]
m.proc = FakeProc()
out = ask("next channel")
q, i = played[-1]
check(f"...next channel: the other ({first} -> {q[i]['title']})", q[i]["title"] != first and out is None)
out = ask("channel down")
check(f"...and back ({played[-1][0][played[-1][1]]['title']})", played[-1][0][played[-1][1]]["title"] == first)
m.proc = None
out = ask("watch the news")
q, i = played[-1]
check(f"the news, not signed in to Plex: your stream of it ({out!r})", q[i]["title"] == "BBC News"
      and out == "Here's BBC News.")
n = len(played)
out = ask("watch sports")
check(f"...sports, with none: Plex has them ({out!r})", out == "Live sports channels come from Plex. Sign in on TV > Plex first."
      and len(played) == n)
CHANS = [{"key": "1", "title": "Big News Now", "genre": "News"}, {"key": "2", "title": "Gridiron Live", "genre": "Sports"},
         {"key": "3", "title": "Toon Town", "genre": "Kids"}, {"key": "4", "title": "Movie Classics", "genre": "Movies"}]
m.plex.cfg["token"] = "x"
m.plex.live_channels = lambda: (time.sleep(0.3), CHANS)[1]
m.plex_live = (0, [])
out = ask("watch sports")
check(f"signed in to Plex: its sports channels, fetched first ({out!r})", out == "Finding some sports…")
ticks(5, lambda: len(played) > n)
q, i = played[-1]
check(f"...then played ({said()})", q[i]["src"] == "plexlive:2" and said() == ["Here's Gridiron Live."])
out = ask("turn on the tv")
q, i = played[-1]
check(f"...a channel: any of Plex's ({out!r})", q[i]["src"].startswith("plexlive:") and len(q) == 4)
out = ask("watch big news")
q, i = played[-1]
check(f"...one by name ({out!r})", q[i]["title"] == "Big News Now")
m.plex_live = (time.time(), [c for c in CHANS if c["genre"] != "News"])
out = ask("watch the news")
check(f"...no news on Plex just now: your stream of it ({out!r})", out == "Here's BBC News.")
m.plex.cfg.pop("token")
out = ask("watch my videos")
check(f"your videos: the Videos tab ({out!r})", out == "Here are your videos." and g.LIBRARY[m.tab]["name"] == "Videos")
out = ask("watch zorblax")
check(f"...one there isn't ({out!r})", out == "I couldn't find zorblax to watch.")
check("'watch out': not for it", m.assist_heard("watch out") is False)
m.open_app(m.tab_index("friend"))

# ---- the Pi itself: asked first --------------------------------------------------------------------------------------
m.updater.available = lambda: False
m.updater.going = lambda: False
begun, shown = [], []
m.updater.begin = lambda: begun.append(1) or None
m.show_update = lambda: shown.append(1)
out = ask("shut down")
check(f"shut down: asked first ({out!r})", out == "Shut down the Pi? Say yes." and not acts)
ask("yes")
check(f"...yes: shut down ({acts})", acts == ["poweroff"])
out = ask("potato, restart")
check(f"'potato, restart' ({out!r})", out == "Restart the Pi? Say yes.")
ask("yes please")
check(f"...yes: restarted ({acts})", acts[-1] == "reboot")
out = ask("restart media mode")
check(f"restart media mode ({out!r})", out == "Restart media mode? Say yes.")
out = ask("no")
check(f"...no: not ({out!r})", out == "Okay, no restart then." and acts == ["poweroff", "reboot"])
out = ask("check for updates")
check(f"check for updates ({out!r})", out.startswith("Look for a new version, and update if there is one?")
      and out.endswith("Say yes."))
ask("okay")
check(f"...yes: updating ({begun}, {shown})", begun == [1] and shown == [1])
m.updater.available = lambda: True
out = ask("update yourself")
check(f"...a new version known: said ({out!r})", out == "There's a new version. Update now? The Pi restarts when it's done. Say yes.")
m.updater.begin = lambda: "There's no internet connection"
out = ask("yes")
check(f"...it couldn't: why ({out!r})", out == "There's no internet connection")
m.updater.going = lambda: True
out = ask("update")
check(f"...updating already ({out!r})", out == "It's updating already.")
ask("shut down")
ask("set a timer for 1 minute")
check("something else asked: its question's gone (yes is the model's again)", m.assist_heard("yes") is False
      and acts == ["poweroff", "reboot"])
m.assist.drop_timers("")
woke = []
m.ears.want = ("hey potato", "")
m.ears.wake_now = lambda: woke.append(1) or True
ask("turn off")
m.ears.want = None
check(f"...its question: listened for at once, no wake phrase needed ({woke})", woke == [1])
m.assist_pending = None

# ---- the camera ---------------------------------------------------------------------------------------------------------
cam = m.camera
out = ask("rotate the camera")
addr = m.friend_camera()
check(f"rotate the camera: its picture turned ({out!r})", cam.turn_of(addr) == 90 and out.endswith("Porch's picture is turned 90°."))
ask("rotate the porch camera left")
check(f"...the porch camera, back a quarter ({cam.turn_of(addr)})", cam.turn_of(addr) == 0)
ask("flip the camera upside down")
check(f"...upside down ({cam.turn_of(addr)})", cam.turn_of(addr) == 180)
out = ask("rotate the camera back")
check(f"...back ({out!r})", cam.turn_of(addr) == 0 and out.endswith("Porch's picture is the right way up."))
out = ask("turn the camera left")
check(f"turn the camera left: its picture on the screen first ({out!r})", m.on_camera_page()
      and g.cam_key(cam.addr or "") == g.cam_key(addr) and out.endswith("Turning left."))
cam.kind, cam.info = "pie", {"available": True}          # (a Pi with an OBSBOT: one that turns)
ticks(3.2, lambda: "left" in cam.held)
check(f"...turning left ({cam.held})", cam.held == {"left"})
ticks(1.5, lambda: not cam.held)
check(f"...for a moment ({cam.held})", not cam.held)
out = ask("look up")
ticks(1.0, lambda: "up" in cam.held)
check(f"...on its page already: at once ({cam.held}, {out!r})", cam.held == {"up"})
ticks(1.5, lambda: not cam.held)
cam.known[g.cam_key(addr)] = {"kind": "mjpeg"}
out = ask("turn the camera right")
check(f"one that can't turn ({out!r})", out == 'Porch can\'t turn. Say "rotate the camera" to turn its picture.')
cam.known.pop(g.cam_key(addr), None)
m.open_app(m.tab_index("friend"))

# ---- listening while something plays ------------------------------------------------------------------------------------
m.proc, m.kind, m.paused = FakeProc(), "audio", False
check("music playing: it listens", m.ears_busy() is False)
m.paused = True
check("...paused: it listens", m.ears_busy() is False)
m.kind, m.paused, m.pi_slow = "video", False, True
check("a video on a slower Pi: not while it plays", m.ears_busy() is True)
m.paused = True
check("...paused: it listens", m.ears_busy() is False)
m.pi_slow, m.paused = False, False
check("...a video on a Pi 4 or 5: it listens", m.ears_busy() is False)
m.game = FakeGame()
check("a game: not", m.ears_busy() is True)
m.game = None
m.voice.speaking = True
check("...nor while it talks", m.ears_busy() is True)
m.voice.speaking = False
m.kind, m.volume, m.muted = "audio", 60, False
cmds.clear()
m.ears.state = "listening"
m.ears_tick()
check(f"listening: what's playing goes quieter ({cmds})", cmds == ["pausing_keep volume 15 1"] and m.ducked)
m.ears_tick()
check("...once", len(cmds) == 1)
m.ears.state = "waiting"
m.ears_tick()
check(f"...and back after ({cmds})", cmds[-1] == "pausing_keep volume 60 1" and not m.ducked)
m.paused = True
m.ears.state = "listening"
m.ears_tick()
check("paused: nothing to make quieter", len(cmds) == 2 and not m.ducked)
m.ears.state = "off"
m.ears_tick()
m.proc, m.paused = None, False

# ---- from the web page, and what it says it can do -------------------------------------------------------------------
n = len(started)
out = m.web_friend_do({"do": "say", "text": "play a game"})
check(f"from the web page: a game ({out})", out.get("ok") and out.get("done") and len(started) == n + 1)
m.game = None
out = ask("what can you do")
check(f"what it can do: games, TV, the Pi ({out!r})", "games" in out and "channel" in out and "shut down" in out)
check("...its model's told so too", "play a game" in g.FACE_CAN_DO and "shut down" in g.FACE_CAN_DO)

# ---- your photos --------------------------------------------------------------------------------------------------------
m.open_app(m.tab_index("friend"))
out = ask("browse my camera roll")
check(f"browse my camera roll: Photos ({out!r})", g.LIBRARY[m.tab]["type"] == "photos" and m.view == "list")
out = ask("show me my last photo")
check(f"show me my last photo: the newest, on the screen ({out!r})", m.view == "photo"
      and m.v["items"][m.v["i"]].endswith("cat.jpg") and out == "Here's your newest picture.")
ask("next picture")
check(f"...next picture ({os.path.basename(m.v['items'][m.v['i']])})", m.v["items"][m.v["i"]].endswith("beach.jpg"))
ask("previous")
check("...previous", m.v["items"][m.v["i"]].endswith("cat.jpg"))
out = ask("start a slideshow")
check(f"a slideshow ({out!r})", m.view == "photo" and m.v["slideshow"])
ask("stop")
check("...stopped, where it was", m.view == "photo" and not m.v["slideshow"])
out = ask("show my photos from today")
check(f"today's ({out!r})", [os.path.basename(x) for x in m.v["items"]] == ["cat.jpg"]
      and out == "Here is your picture from today.")
m.photo_back()
m.open_app(m.tab_index("friend"))
out = ask("next picture")
check(f"next picture, with none open ({out!r})", out == 'There\'s no picture open. Say "show my newest picture".')

# ---- its model, asking for something to be done ----------------------------------------------------------------------
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
answers, prompts = [], []


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
        prompts.append(body.get("prompt") or "")
        return self.reply(200, {"response": answers.pop(0) if answers else "Hello!"})


ol = ThreadingHTTPServer(("127.0.0.1", 11574), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()
m.friend_set(server="127.0.0.1:11574", model="llama3.2:3b")
m.open_app(m.tab_index("friend"))


def model_says(answer, text):
    """You say text, its model answers: what's kept as its answer."""
    answers.append(answer)
    m.friend_send(text)
    mine = m.friend.log[-1]                                # (what you said)
    ticks(8, lambda: not m.friend.busy and m.friend.log[-1] is not mine)   # (its answer, kept: then no more ticks,
    new = m.friend.log[-1]                                                  # a pretend game may be on)
    return new["text"] if new is not mine and new["who"] == "friend" else None


n = len(started)
out = model_says("[[play Shrek 2]] Here comes Shrek 2!", "I fancy some ogre action")
check(f"its model asks for a game of yours: started, its words kept, not the brackets ({out!r})",
      len(started) == n + 1 and started[-1]["label"] == "Shrek 2" and out == "Here comes Shrek 2!")
p = prompts[-1] if prompts else ""
check("...told your games, your music and how to ask", "Shrek 2" in p and "Miles Davis" in p and "[[play Tetris]]" in p
      and "Their games:" in p)
m.game = None
out = model_says("[[play Zelda Quest]] Starting Zelda Quest!", "put on that elf game")
check(f"...one you haven't: why, not its words ({out!r})", out == "I couldn't find Zelda Quest." and len(started) == n + 1)
ask("shut down")
out = model_says("[[yes]] Sure thing.", "what do you think")
check(f"...never yes for you ({out!r}, {acts})", out == "Sure thing." and acts == ["poweroff", "reboot"])
m.assist_pending = None
out = model_says("[[shut down]] Okay, bye!", "time for bed, turn yourself off")
check(f"...its question kept, not its words ({out!r})", out == "Shut down the Pi? Say yes." and m.assist_asking())
m.assist_pending = None
out = model_says("Shrek 2 is a great movie.", "do you like shrek")
check(f"...nothing asked for: its words ({out!r})", out == "Shrek 2 is a great movie.")
out = model_says("[[Hello there, friend!]]", "hi")
check(f"...its words in brackets, nothing to do: its words still ({out!r})", out == "Hello there, friend!")
m.friend_set(server="")

# ---- its listening face: its sound clear of its eye ----------------------------------------------------------------------
size = 112
im = Image.new("RGB", (240, 200), g.ROW)
g.draw_face(ImageDraw.Draw(im), 100, 100, size, "listening", 0.4, g.TEXT, g.ROW)
px = im.load()
_, (gx, gy), _, grow = g.face_state("listening", 0.4)
ey = int(100 - size * 0.08)
x = int(100 + size * 0.23) + 1
while x < 239 and px[x, ey] != g.ROW:                  # (along the eye's middle: its right edge...)
    x += 1
edge = x
while x < 239 and px[x, ey] == g.ROW:                  # (...then the first of its sound)
    x += 1
check(f"listening: its sound a little way from its eye ({x - edge} px at {size} across)", 10 <= x - edge <= 20)
check("...and inside its box", x + size * 0.2 < 100 + size * 0.78)
im.resize((480, 400)).save(SP + "/face_listening.png")

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
