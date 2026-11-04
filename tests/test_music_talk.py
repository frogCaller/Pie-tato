"""The bot and your music. Its ears over music (hear.py with the real Vosk and a pretend arecord): the wake phrase
alone while something plays (a grammar, and only when Vosk's sure), nothing heard in a song with no wake phrase in it,
what's said after the wake phrase made out as ever (then the wake phrase alone again, once told), as ever when nothing
plays, and everything made out when the model doesn't know the wake phrase's words. listen.py telling it when
something plays, and after each thing said. In media mode, Character > Voice > Pauses music: Off, the music quieter
while you talk to it and the bot quiet over it (as before); On, the music paused while you talk to it, stopped while
it talks (then on again where it was, or the station again), a remark of its own not said over it, your pause or play
said to it kept, music you'd paused started again paused, a reminder said over it; its row on the Pi and the web
page. The Bot's face: a rounder square, its model (or the day) under it."""
import collections, io, json, os, select, shutil, subprocess, sys, threading, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_music_talk"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
MIC = S + "/mic"
for d in (HOME + "/Music", MIC):
    os.makedirs(d)
LIB = SP + "/vosk_whl/x/manylinux_2_12_x86_64.manylinux2010_x86_64/vosk/libvosk.so"
MODEL = SP + "/vosk_model_npm/vosk-model-small-en-us-0.15"
W = SP + "/wakeexp"                                # (music with words sung, and spoken clips: wakeexp/make_*.py)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.listen as L
import pitato.assist as AS
ok_all = []
R = 16000


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- hear.py over music ----------------------------------------------------------------------------------------------
music = np.load(W + "/music2.npy")


def rms(a):
    return float(np.sqrt((a.astype(np.float64) ** 2).mean()))


def pcm(a):
    return np.clip(a, -32768, 32767).astype("<i2").tobytes()


def mixed(clip, snr, lead=4.0, off=0):
    sp = np.load(f"{W}/speech/{clip}.npy")
    pre = int(lead * R)
    bed = music[off:off + pre + len(sp) + 3 * R].copy()
    bed *= rms(sp) / (rms(bed[pre:pre + len(sp)]) * 10 ** (snr / 20))
    bed[pre:pre + len(sp)] += sp
    return pcm(bed)


def drop(data):
    name = f"{time.time():.6f}"
    open(f"{MIC}/.{name}", "wb").write(data)
    os.rename(f"{MIC}/.{name}", f"{MIC}/{name}.raw")


env = dict(os.environ, PATH=SP + "/listen_t/bin:" + os.environ["PATH"], FAKE_MIC_DIR=MIC, FAKE_MIC_SPEED="4")


class Hear:
    def __init__(self, *words):
        self.p = subprocess.Popen([sys.executable, "-I", ROOT + "/pitato/hear.py", LIB, MODEL, "", *words],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)

    def tell(self, what):
        self.p.stdin.write((what + "\n").encode())
        self.p.stdin.flush()

    def said(self, secs):
        out, end = [], time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.p.stdout], [], [], 0.2)
            if r:
                line = self.p.stdout.readline()
                if not line:
                    break
                out.append(json.loads(line))
        return out

    def quit(self):
        self.tell("quit")
        self.p.wait(10)


def secs_of(data):
    return len(data) / 2 / R / 4 + 3                 # (at four times real time, and a moment)


h = Hear("hey", "potato")
first = h.said(8)
check(f"hear.py starts as ever ({first})", first and first[0].get("ready") is True and first[0].get("unknown") == [])
h.tell("noisy")
song = pcm(music[40 * R:70 * R] * 1.5)              # (30 s of a song: "hey you", "potatoes in the kitchen" and all)
drop(song)
got = h.said(secs_of(song))
check(f"music playing, no wake phrase in it: nothing heard ({got[:3]})", not got)
hits = 0
for clip, off in (("cmd2_en-us-f3_160", 900000), ("cmd3_en-gb_130", 200000), ("wake_en_160", 1500000)):
    data = mixed(clip, 8, off=off)
    drop(data)
    got = h.said(secs_of(data))
    heard = [x for x in got if "final" in x]
    hits += bool(heard) and heard[0] == {"final": "hey potato"}
    h.tell("reset")
    h.said(0.5)
check(f"over music: the wake phrase heard, said as just the wake phrase ({hits} of 3)", hits >= 2)
drop(mixed("cmd2_en-us-f3_160", 8, off=900000))
got = h.said(secs_of(mixed("cmd2_en-us-f3_160", 8, off=900000)))
check(f"...the wake phrase: {[x for x in got if 'final' in x][:1]}", {"final": "hey potato"} in got)
h.tell("clear")                                       # (the music paused for it)
clean = pcm(np.concatenate([np.zeros(R // 2), np.load(W + "/speech/cmd_en-us_160.npy")[int(0.9 * R):], np.zeros(R)]))
drop(clean)
got = h.said(secs_of(clean))
finals = [x["final"] for x in got if "final" in x]
check(f"...then what you say is made out as ever ({finals})", any("time" in f for f in finals))
h.tell("reset")
h.tell("noisy")
drop(song)
got = h.said(secs_of(song))
check(f"...told it's had what you said, and music again: the wake phrase alone again ({got[:2]})", not got)
h.tell("clear")
drop(pcm(np.concatenate([np.zeros(R // 2), np.load(W + "/speech/cmd_en-us_160.npy"), np.zeros(R)])))
got = h.said(8)
finals = [x["final"] for x in got if "final" in x]
check(f"nothing playing: everything made out, as ever ({finals})", any("time" in f for f in finals))
h.quit()
h = Hear("hey", "zorblaxx")
first = h.said(8)
h.tell("noisy")
drop(pcm(music[40 * R:52 * R] * 1.5))
got = h.said(8)
check(f"a wake phrase the model doesn't know ({first[0].get('unknown')}): over music, everything made out as ever "
      f"({len(got)} lines)", first[0].get("unknown") == ["zorblaxx"] and any("partial" in x for x in got))
h.quit()

# ---- listen.py tells it when something plays, and when it's had what you said -----------------------------------------
class FakeHear:
    def __init__(self):
        self.told, self.r, self.w = [], *os.pipe()
        self.stdout = os.fdopen(self.r, "rb", buffering=0)
        self.stdin = self

    def write(self, b):
        self.told.append(b.decode().strip())

    def flush(self):
        pass

    def send(self, **msg):
        os.write(self.w, (json.dumps(msg) + "\n").encode())


ears, delivered = L.Ears(), []
ears.on_heard = delivered.append
playing = [False]
ears.is_noisy = lambda: playing[0]
fake = FakeHear()
ears.gen, ears.state = 3, "waiting"
threading.Thread(target=ears.listen, args=(3, fake, L.wake_words("hey potato")), daemon=True).start()
time.sleep(0.4)
playing[0] = True
time.sleep(0.4)
playing[0] = False
time.sleep(0.4)
check(f"something playing, then not: hear.py told so ({fake.told})", fake.told[:3] == ["listen", "noisy", "clear"])
fake.send(final="hey potato")
time.sleep(0.3)
fake.send(final="what time is it")
time.sleep(0.4)
check(f"what you said after the wake phrase, passed on: then it's told so ({delivered}, {fake.told[3:]})",
      delivered == ["What time is it"] and fake.told[3:] == ["reset"])
L.PATIENCE, was_patience = 0.6, L.PATIENCE
fake.send(final="hey potato")
time.sleep(1.4)
check(f"...nothing said after it, a while: told so too ({fake.told[4:]}, {ears.state})",
      fake.told[4:] == ["reset"] and ears.state == "waiting")
L.PATIENCE = was_patience
ears.gen += 1

# ---- media mode: Pauses music -----------------------------------------------------------------------------------------
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
for n in ("So What.mp3", "Blue in Green.mp3", "All Blues.mp3"):
    open(f"{HOME}/Music/{n}", "wb").write(b"\0" * 100)
spawned = []


class Player:
    def __init__(self, args, target):
        self.args, self.target, self.lines, self.dead = args, target, [], False
        self.stdin, self.said = self, collections.deque(maxlen=50)

    def write(self, s):
        self.lines.append(s.strip())

    def flush(self):
        pass

    def poll(self):
        return 0 if self.dead else None

    def wait(self, timeout=None):
        self.dead = True
        return 0

    def kill(self):
        self.dead = True


def fake_spawn(self, args, target):
    self.started = time.monotonic()
    paused = self.start_paused
    self.muted = self.settling = False
    self.proc = Player(args, target)
    spawned.append((os.path.basename(target), args[args.index("-ss") + 1] if "-ss" in args else None, paused))
    if paused:
        self.muted = self.settling = self.paused = True


g.Media.spawn = fake_spawn
spoken, chimes = [], []


class FB:
    w, h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
m.enter()


def fake_say(text, vid, device="", volume=100):
    spoken.append(text)
    m.voice.speaking = True
    return True, ""


m.voice.say = fake_say
m.voice.chime = lambda device="", volume=100: chimes.append(1) or True
m.ears.start = lambda *a, **k: None                   # (no microphone here: its state's set as it would be)
BOT = "server = 127.0.0.1:9\nmodel = llama3.2:3b\nvoice = en_US-lessac-medium\nspeak = on\n"


def bot_txt(extra=""):
    open(HOME + "/bot.txt", "w").write(BOT + extra)
    m.friend.load(m.friend_files())


bot_txt()
mi = m.music_tab()
m.load_tab(mi)
songs = [it for it in m.tab_items(mi) if it.get("kind") == "audio"]


def play_music(pos=61):
    m.play(songs, 1, start=0, show=False)
    m.pos, m.paused = pos, False


def ears(state):
    m.ears.state = state
    m.ears_tick()


def done_talking():
    m.voice.speaking = False


clock = [time.monotonic()]


def hold_ticks():
    """A tick, then the music's hold looked at as time goes by (a pretend clock, always on)."""
    m.tick()
    for _ in range(2):
        clock[0] = max(clock[0], time.monotonic()) + g.HOLD_AFTER + 0.1
        m.music_hold_tick(clock[0])


check("Pauses music: off, as it comes", not m.bot_pauses_music())
play_music()
check("music playing: noisy, for its ears", m.ears_noisy())
p = m.proc
ears("listening")
check(f"Off: the wake phrase heard, the music quieter, not paused ({p.lines[-1:]})",
      m.ducked and not m.paused and m.proc is p and any("volume" in x for x in p.lines) and not m.ears_noisy())
m.bot_replied("It's half past nine.")
check(f"...its answer not said over the music, as before ({spoken})", not spoken and m.proc is p)
ears("waiting")
check("...done: the music as loud as before", not m.ducked and m.ears_noisy())

bot_txt("pause_music = on\n")
check("Pauses music: on", m.bot_pauses_music())
ears("listening")
check(f"On: the wake phrase heard, the music paused ({p.lines[-1:]})", m.paused and m.proc is p and p.lines[-1] == "pause"
      and m.music_held and not m.ducked and not m.ears_noisy())
replied = threading.Thread(target=m.bot_replied, args=("It's half past nine.",))   # (from its own thread, as it is)
replied.start(); replied.join()
check("...its answer, from its own thread: left for media mode's own", not spoken and m.proc is p)
ears("waiting")
m.tick()
check(f"...then said: the music stopped for it (the player has the sound card) ({spoken}, {p.dead})",
      spoken == ["It's half past nine."] and p.dead and m.proc is None and m.music_held["pos"] == 61)
hold_ticks()
check("...not on again while it talks", m.proc is None and len(spawned) == 1)
done_talking()
hold_ticks()
check(f"...done talking: on again, the same song, where it was ({spawned[-1]})",
      m.proc is not None and spawned[-1][0] == "Blue in Green.mp3" and spawned[-1][1] == "58" and not spawned[-1][2]
      and m.music_held is None and not m.paused)

spoken.clear()
p = m.proc
before = p.lines.count("pause")
ears("listening")
ears("waiting")
hold_ticks()
check("the wake phrase and nothing said after it: the music on again, not started again",
      m.proc is p and not m.paused and p.lines.count("pause") == before + 2 and len(spawned) == 2)

spoken.clear()
m.friend.log.append({"who": "friend", "kind": "remark", "t": time.time(), "text": "Nice tune."})
m.bot_replied("Nice tune.")
m.tick()
check(f"something it says by itself: not over the music ({spoken})", not spoken and m.proc is p and not m.paused)
m.friend.log.append({"who": "friend", "kind": "chat", "t": time.time(), "text": "Sure."})

ears("listening")
m.assist_media(AS.parse("pause"))
ears("waiting")
hold_ticks()
check("\"pause\", said to it: paused, and it stays paused", m.paused and m.proc is p and m.music_held is None)
ears("listening")
check("...the wake phrase heard while it's paused: nothing to pause", m.music_held is None and m.paused)
out = m.assist_media(AS.parse("resume"))
ears("waiting")
check(f"...\"play\" said to it: playing again ({out!r})", not m.paused and m.proc is p)

m.cmd("pause"); m.paused = True                       # (you paused it)
m.say_aloud("Your timer's up!")
check(f"music you'd paused, and it talks: stopped for it ({spoken[-1:]})", spoken[-1:] == ["Your timer's up!"]
      and m.proc is None and m.music_held["paused"])
done_talking()
hold_ticks()
check(f"...then started again, paused, where it was ({spawned[-1]})", spawned[-1][2] and m.paused and m.proc is not None)
m.stop()

spoken.clear(); chimes.clear()
play_music(30)
m.assist_announce("timer", {"label": "pasta", "until": time.time()})
check(f"a timer's up, over music: said, the music stopped for it ({spoken})",
      spoken and "pasta" in spoken[0] and m.proc is None and not chimes)
done_talking()
hold_ticks()
check("...and on again after", m.proc is not None and spawned[-1][1] == "27")
bot_txt()
spoken.clear()
m.assist_announce("timer", {"label": "pasta", "until": time.time()})
check(f"...Pauses music off: a chime, the music playing on, as before ({chimes})", chimes and not spoken
      and m.proc is not None)
ok, why = m.say_aloud("Hello")
check(f"...and Say it again over music: not now, as before ({why})", not ok and "playing" in why)
m.stop()

# a radio station: the station again, after
bot_txt("pause_music = on\n")
st = {"key": "r1", "title": "Jazz24", "kind": "radio", "src": "http://radio.example/jazz24.mp3"}
m.play([st], 0, start=0, show=False)
m.paused = False
spoken.clear()
m.say_aloud("It's sunny.")
check("the radio, and it talks: stopped for it", spoken == ["It's sunny."] and m.proc is None)
done_talking()
hold_ticks()
check(f"...then the station again ({spawned[-1]})", m.proc is not None and m.kind == "radio" and spawned[-1][1] is None)
m.stop()

# a video: not paused for it (it doesn't talk over videos)
m.proc, m.kind, m.paused = Player([], "film.mp4"), "video", False
ears("listening")
check("a video: quieter while you talk to it, as before (not paused)", m.ducked and not m.paused and not m.music_held)
ears("waiting")
ok, why = m.say_aloud("Hi")
check(f"...and not said over it ({why})", not ok)
m.proc, m.kind = None, None

# ---- its row: Character > Voice, and the web page --------------------------------------------------------------------
m.char_open()
import pitato.screens.character as CH
m.char_sec = [n for n, _ in CH.CHAR_PARTS].index("Voice")
keys = m.char_keys()
check(f"Character > Voice: Pauses music, after Talks out loud ({keys})", keys[keys.index("speak") + 1] == "pause_music"
      and m.char_value("pause_music") == "On")
m.char_change("pause_music", 1)
check(f"...changed: off, in bot.txt ({m.msg!r})", not m.bot_pauses_music() and "pause_music = off" in
      open(HOME + "/bot.txt").read() and "quieter" in (m.msg or ""))
rows = {r["key"]: r for sec in m.web_settings_now()["sections"] for r in sec["rows"]}
check(f"the web page's row ({rows.get('f_pause')})", rows["f_pause"]["value"] == "off"
      and rows["f_pause"]["names"] == {"on": "Yes", "off": "No"})
out = m.web_settings_do({"cmd": "settings", "key": "f_pause", "value": "on"})
check(f"...set on there ({out})", out == {"ok": True} and m.bot_pauses_music())
out = m.web_settings_do({"cmd": "settings", "key": "f_pause", "value": "loud"})
check(f"...not one of its choices ({out})", "error" in out and m.bot_pauses_music())

# ---- its face: a rounder square, its model under it -------------------------------------------------------------------
m.go_home()
m.open_app([t["name"] for t in g.LIBRARY].index("Bot"))
m.set_setting("bot_mode", "chat")
m.friend.busy = False
m.dirty = True; m.flush()
im = FB.last.convert("RGB")
im.save(S + "/bot_page.png")
a = np.asarray(im).astype(int)
back = np.array(m.bot_palette()[1])
top, bottom = m.LIST_TOP + 4, FB.h - m.FOOTER - 10      # (its card, the face's panel in it)
inside = a[top + 40:bottom - 20, 18:194]   # (not its card's round corners: the page shows there)
ys, xs = np.nonzero(np.abs(inside - back).sum(axis=2) < 6)
y0, y1, x0, x1 = ys.min() + top + 40, ys.max() + top + 40, xs.min() + 18, xs.max() + 18
w, hgt = x1 - x0 + 1, y1 - y0 + 1
check(f"its face's panel: a square ({w} x {hgt})", abs(w - hgt) <= 2 and w > 140)
corner = a[y0 + 2, x0 + 2]
check(f"...with rounder corners (its corner's the card's colour, {corner.tolist()})",
      np.abs(corner - np.array(g.ROW)).sum() < 12)
below = a[y1 + 8:y1 + 36, x0:x1]
words = (np.abs(below - np.array(g.ROW)).sum(axis=2) > 60).sum()
check(f"...its model (or what it's doing) under it ({words} pixels of words there)", words > 30)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
