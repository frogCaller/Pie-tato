"""The Bot, bored (screens/attract.py, Settings > Attract mode On; test_attract has its games): left idle, plugged in, it
finds something to do, something else every minute or so (not what it did last), and says something each time: a line
of its own on the screen at once, then its model's words (asked by itself: never kept in the conversation), out loud
too in the day (with a voice; not over a game, whose sound is its own; at night, just on the screen). The weather and
Finance with a word about them; the camera, looked through (its model sees what's there), turned to look around when it
turns (left, then right, back where it was), not when it's following you; one of Apps' watched; a slideshow of your
photos (its model shown one); the Pi's own numbers; a game, with what it says over the game. What it says goes along
the foot of the page (low, over a slideshow); the camera's over its picture. A or START: what it's showing is yours;
any other button: back where you were (your list, on the row you were on). Something else on the screen: it's left as
it is. Without a model: its own lines, said. Games only: just games."""
import os, shutil, sys, threading, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t_bored"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/nes"):
    os.makedirs(f"{HOME}/{d}")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


open(f"{HOME}/Games/nes/Contra (USA).nes", "wb").write(b"\0" * 64)
for k, colour in enumerate(((200, 60, 60), (60, 160, 90), (70, 90, 200))):
    Image.new("RGB", (64, 48), colour).save(f"{HOME}/Pictures/photo{k}.jpg")
for k in range(3):
    open(f"{HOME}/Music/song{k}.mp3", "wb").write(b"\0" * 64)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
for t in g.LIBRARY:
    if "dirs" in t:
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
real_run = g.subprocess.run
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                         {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli",
                                          "vcgencmd", "hostname"} else real_run(cmd, *a, **k))
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
g.playable = lambda key: True
sent = []
g.GameRun.start = lambda self, core, **kw: setattr(self, "state", "on")
g.GameRun.quit = lambda self, timeout=0: setattr(self, "ended", True)
g.GameRun.send = lambda self, line: sent.append(line) or True
g.GameRun.pause = lambda self: True

# ---- its model: a pretend Ollama, what it was asked and shown -------------------------------------------------------
asked = []
gate = threading.Event()
gate.set()


def ollama(server, model, system, prompt, images=None, timeout=0):
    gate.wait(10)
    asked.append((prompt.rsplit("\n\n", 1)[-1], bool(images)))
    return "[[play Contra]] What a sight, " + str(len(asked)) + "."


g.ollama_generate = ollama
import pitato.screens.attract as AM
AM.BORED_TALK = (0, 24)                              # (it talks, whatever the time the test runs at)


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def invalidate(self): pass
    def close(self): pass


texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]

m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("battery", "Off")                       # (plugged in)
m.set_setting("attract", "On")
m.set_setting("location", {"name": "Springfield", "admin": "Oregon", "country": "US", "lat": 44.0, "lon": -123.0})
m.weather.data = {"temp": 64.2, "code": 2, "units": "F", "days": [{"hi": 70, "lo": 51, "rain": 10, "date": "2026-11-05"}]}
m.crypto.quotes = {"bitcoin": {"d": {"price": 67000.0, "change_24h": 2.13, "symbol": "BTC"}}}
BOT = m.friend_files()[0]
open(BOT, "w").write("server = 10.0.0.20\nmodel = seeing-model\n")   # (Settings > Bot: its computer, its model)
m.friend.load(m.friend_files())
log_before = len(m.friend.log)
said = []
m.bot_voice = lambda: "en_US-amy-low"
m.bot_speaks = lambda: True
m.say_aloud = lambda text=None: (said.append(text), (True, ""))[1]

# the camera: one on another Pi that turns (an OBSBOT), its picture and how it's turned, pretended
CAM = "10.0.0.5:5433"
m.friend_camera = lambda text="": CAM
turns = []
cam = m.camera
cam.start = lambda: None
cam.stop = lambda: None
cam.press = lambda name: turns.append(("press", name)) or True
cam.release = lambda name: turns.append(("release", name))
cam.go_home = lambda: turns.append(("home",))
STEERS = [True]
type(cam).steers = property(lambda self: STEERS[0])
jpeg = S + "/cam.jpg"
Image.new("RGB", (64, 48), (90, 90, 90)).save(jpeg)
m.camera_look = lambda addr: (open(jpeg, "rb").read(), "Garage")
m.later = lambda secs, job: job()                    # (its turns: let go at once, here)

picks = []
m.bored_pick = lambda kinds: (picks.append(list(kinds)), want[0] if want[0] in kinds else kinds[0])[1]
want = ["weather"]


def idle():
    m.stirred = time.monotonic() - AM.ATTRACT_AFTER - 1


def settle(secs=3.0):
    """Its model's words (asked on a thread of their own) in, and put up on media mode's thread."""
    end = time.monotonic() + secs
    while time.monotonic() < end and any(t.name == "friend-comment" for t in threading.enumerate()):
        time.sleep(0.02)
    for _ in range(3):
        m.tick()


def drawn():
    texts.clear()
    m.dirty = True
    m.flush()
    return " ".join(texts)


def later(secs):
    m.attract["since"] -= secs


# ---- the music list, a row down: then bored -------------------------------------------------------------------------
mi = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Music")
m.open_app(mi)
m.sels[mi] = 2
idle()
m.tick()
a = m.attract
check(f"left idle on your music list, plugged in: bored, it finds something to do ({a and a['kind']}, "
      f"{picks[:1]})", a is not None and a["kind"] == "weather")
check(f"...from all it can do here ({sorted(picks[0]) if picks else None})", picks and
      sorted(picks[0]) == sorted(["game", "camera", "weather", "finance", "app", "photos", "system"]))
check(f"the weather: up on the screen, and a line of its own about it at once ({m.bored_said()!r})",
      g.LIBRARY[m.tab]["name"] == "Weather" and m.view == "list" and "64 degrees" in m.bored_said()
      and any(m.bored_said().startswith(x + " ") for x in AM.BORED_LINES["weather"]))
page = drawn()
FB.last.save(SP + "/bored_weather.png")
check(f"...along the foot of the page, with its face ({page[-90:]!r})", "64 degrees" in page)
settle()
check(f"...then its model's words, asked about the weather ({asked[-1:]}, {m.bored_said()!r})",
      asked and asked[-1] == (AM.BORED_ASKS["weather"], False) and m.bored_said() == "What a sight, 1.")
check(f"...said out loud ({said[-1:]}), and nothing it asked to be done done (it's only talking)",
      said[-1:] == ["What a sight, 1."] and m.view == "list" and m.game is None)
check("...and none of it kept in your conversation", len(m.friend.log) == log_before)

# ---- something else: Finance --------------------------------------------------------------------------------------------
want[0] = "finance"
later(AM.BORED_FOR["weather"] + 1)
m.tick()
check(f"a while on: something else, not what it did last ({m.attract['kind']}, {picks[-1]})",
      m.attract["kind"] == "finance" and "weather" not in picks[-1] and g.LIBRARY[m.tab]["name"] == "Finance")
check(f"...a word about your coins at once ({m.bored_said()!r})", "BTC's at $67,000.00, up 2.1% today." in m.bored_said()
      or "Bitcoin's at $67,000.00, up 2.1% today." in m.bored_said())
settle()
check(f"...then its model's, asked about them ({asked[-1][0][:60]!r})", asked[-1] == (AM.BORED_ASKS["finance"], False)
      and m.bored_said() == "What a sight, 2.")

# ---- the camera: what it sees, looking around ---------------------------------------------------------------------------
want[0] = "camera"
later(AM.BORED_FOR["finance"] + 1)
m.tick()
check(f"the camera: its picture on the screen ({m.attract['kind']}, {cam.addr})", m.attract["kind"] == "camera"
      and m.on_camera_page() and cam.addr == CAM)
later(4.1)
m.tick()
check(f"...no picture from it yet: it waits for one before it looks ({m.cam_bot})", m.cam_bot is None)
cam.frame = Image.new("RGB", (64, 48), (90, 90, 90))   # (its first picture)
m.tick()
check(f"...a moment on: it looks, and says it's looking meanwhile ({m.cam_bot and m.cam_bot['busy']})",
      m.cam_bot is not None and m.cam_bot["busy"])
settle()
check(f"...what it sees: its model shown the picture, its words over it, and said ({asked[-1][0][:50]!r}, "
      f"{m.cam_bot and m.cam_bot['text']!r})", asked[-1] == (AM.BORED_ASKS["camera"].format(cam=m.cam_called(CAM)), True)
      and m.cam_bot and m.cam_bot["text"] == "What a sight, 3." and said[-1] == "What a sight, 3.")
check("...over the camera's picture", "What a sight, 3." in drawn())
FB.last.save(SP + "/bored_camera.png")
later(20)
m.tick()
check(f"...then it turns to the left to look around ({turns})", turns[:2] == [("press", "left"), ("release", "left")])
later(5)
m.tick()
settle()
check(f"...and says what's there ({asked[-1]})", asked[-1] == (AM.BORED_ASKS["turned"].format(way="left"), True))
later(19)
m.tick()
later(7)
m.tick()
settle()
check(f"...then right, past where it was ({turns[2:4]}), and says what's there",
      turns[2:4] == [("press", "right"), ("release", "right")]
      and asked[-1] == (AM.BORED_ASKS["turned"].format(way="right"), True))
later(17)
m.tick()
check(f"...then back where it was ({turns[4:]})", turns[4:] == [("home",)])
check("...looking all the while: none of it kept in your conversation", len(m.friend.log) == log_before)

# ---- one of Apps' ----------------------------------------------------------------------------------------------------
want[0] = "app"
later(9)
m.tick()
name = g.LIBRARY[m.tab]["name"]
check(f"one of Apps': up, watched, with a word about it ({name}, {m.bored_said()!r})", m.attract["kind"] == "app"
      and name in AM.BORED_APPS and m.on_sim_page() and m.bored_said() == AM.BORED_APP_LINES.get(
          name, f"Fortune cookie time! It says: {m.sims['fortune'].text if 'fortune' in m.sims else ''}"))
check("...along the foot of the page, over the app", m.bored_said() in drawn())
FB.last.save(SP + "/bored_app.png")
settle()
check(f"...then its model's ({asked[-1][0][:40]!r})", (asked[-1][0].startswith(f"You're bored, so you just put {name} on")
      or name == "Fortune Cookie" and "fortune cookie" in asked[-1][0]) and m.bored_said() == f"What a sight, {len(asked)}.")

# ---- your photos ---------------------------------------------------------------------------------------------------
want[0] = "photos"
later(AM.BORED_FOR["app"] + 1)
m.tick()
check(f"your photos: a slideshow of them ({m.view}, {m.v.get('slideshow')}, {len(m.v.get('items', []))})",
      m.attract["kind"] == "photos" and m.view == "photo" and m.v.get("slideshow") and len(m.v["items"]) == 3)
settle()
check(f"...its model shown one ({asked[-1][0][:60]!r})", asked[-1][1] and "one of them, from " in asked[-1][0])
check("...what it says over the slideshow, at its foot", m.bored_said() in drawn())
FB.last.save(SP + "/bored_photos.png")

# ---- the Pi's own numbers --------------------------------------------------------------------------------------------
want[0] = "system"
later(AM.BORED_FOR["photos"] + 1)
m.tick()
check(f"the Pi's numbers: System ({g.LIBRARY[m.tab]['name']}, {m.bored_said()!r})", m.attract["kind"] == "system"
      and g.LIBRARY[m.tab]["name"] == "System" and m.view == "list")
settle()
check(f"...its model told them ({asked[-1][0][:80]!r})", asked[-1][0].startswith("You're bored, so you just put your own "
                                                                                 "numbers on the screen"))

# ---- a game: what it says goes over the game ------------------------------------------------------------------------
want[0] = "game"
gate.clear()                                          # (its model slow to answer)
sent.clear()
said_before = len(said)
later(AM.BORED_FOR["system"] + 1)
m.tick()
check(f"a game: it plays it, a line of its own over the game at once ({m.view}, {sent[-1:]})",
      m.attract["kind"] == "game" and m.view == "game" and m.game is not None
      and any(x.startswith("notice ") and "Contra" in x for x in sent))
gate.set()
settle()
check(f"...then its model's, over the game too ({[x for x in sent if x.startswith('notice')][-1:]}), not said out loud "
      f"(the game's sound is its own)", any(x == f"notice What a sight, {len(asked)}." for x in sent)
      and len(said) == said_before)

# ---- its model slow to answer: not asked again till it has, its own line said meanwhile ------------------------------------
gate.clear()
want[0] = "photos"
later(AM.ATTRACT_GAME + 1)
m.tick()                                              # (your photos: its model asked, and not answering yet)
want[0] = "finance"
later(AM.BORED_FOR["photos"] + 1)
m.tick()
waiting = sum(t.name == "friend-comment" for t in threading.enumerate())
check(f"its model slow to answer: not asked again meanwhile ({waiting} asking), the next thing's own line said "
      f"({said[-1:]})", waiting == 1 and said and said[-1] == m.bored_said() and "67,000.00" in said[-1])
gate.set()
settle()
check(f"...its late answer, about your photo, not put up over Finance ({m.bored_said()!r})",
      "67,000.00" in m.bored_said() and m.attract["kind"] == "finance")

# ---- A: what it's showing is yours; B: back where you were ----------------------------------------------------------------
want[0] = "weather"
later(AM.ATTRACT_GAME + 1)
m.tick()
settle()
m.press("a")
check(f"A: what it's showing is yours, as it is (the weather) ({m.attract}, {g.LIBRARY[m.tab]['name']})",
      m.attract is None and g.LIBRARY[m.tab]["name"] == "Weather" and m.view == "list")
m.open_app(mi)
m.sels[mi] = 2
want[0] = "camera"
idle()
m.tick()
check("left idle again: bored again", m.attract is not None and m.attract["kind"] == "camera")
m.press("b")
check(f"B: back where you were, your music list on the row you were on ({g.LIBRARY[m.tab]['name']}, {m.sels.get(mi)})",
      m.attract is None and m.tab == mi and m.view == "list" and m.sels.get(mi) == 2 and not m.on_camera_page())
idle()
m.tick()
m.open_app(mi)                                        # (your music put up from the web page, say)
m.tick()
check("something else on the screen meanwhile: it's left as it is", m.attract is None and m.tab == mi
      and m.view == "list")

# ---- a camera that doesn't turn; following you ------------------------------------------------------------------------
STEERS[0] = False
turns.clear()
want[0] = "camera"
idle()
m.tick()
cam.frame = Image.new("RGB", (64, 48), (90, 90, 90))
for _ in range(4):
    later(15)
    m.tick()
    settle(1)
check(f"a camera that doesn't turn: it looks once, and doesn't try to turn it ({turns})", not turns)
later(1)
m.tick()
check(f"...and goes on to something else sooner ({m.attract and m.attract['kind']})",
      m.attract is not None and m.attract["kind"] != "camera")
m.press("b")
STEERS[0] = True

# ---- at night: just on the screen; without a model: its own lines, said --------------------------------------------------
AM.BORED_TALK = (25, 25)
said.clear()
want[0] = "weather"
idle()
m.tick()
settle()
check(f"at night: what it says only on the screen, not out loud ({said}, {m.bored_said()!r})",
      not said and m.bored_said() == f"What a sight, {len(asked)}.")
m.press("b")
AM.BORED_TALK = (0, 24)
os.remove(BOT)                                        # (no model set up)
m.friend.load(m.friend_files())
n_asked = len(asked)
want[0] = "finance"
idle()
m.tick()
settle(0.5)
check(f"without a model: its own line, said ({said[-1:]})", len(asked) == n_asked and said
      and said[-1] == m.bored_said() and "67,000.00" in said[-1])
m.press("b")

# ---- Games only ----------------------------------------------------------------------------------------------------
m.set_setting("attract", "Games only")
picks.clear()
idle()
m.tick()
check(f"Games only: just games ({picks})", picks == [["game"]] and m.attract["kind"] == "game")
m.press("b")
check("...B: back where you were", m.attract is None and m.tab == mi and m.view == "list")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
