"""The Bot's voice: Piper (the real one, its x86_64 build, with a real voice) through a pretend aplay;
fetching Piper and a voice from a pretend internet (Piper checked against its SHA-256); Settings >
Bot > Voice; SELECT on the Bot's page; its replies said out loud; the web page's calls; and the
Friend now being the Bot (bot.txt carrying on from friend.txt)."""
import hashlib, io, json, os, shutil, socket, sys, tarfile, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t58"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
PLAYS = S + "/plays"
os.makedirs(PLAYS)
os.environ["FAKE_APLAY_DIR"] = PLAYS
os.environ["FAKE_APLAY_SPEED"] = "4"
os.environ["PATH"] = SP + "/voicetest/bin:" + os.environ["PATH"]
DL = SP + "/piper_dl"
AMY = (DL + "/voices/en-us-amy-low.onnx", DL + "/voices/en-us-amy-low.onnx.json")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.PIPER_DIR = S + "/lib/piper"
g.VOICES_DIR = S + "/lib/voices"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def settle(cond, t=30):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def plays():
    try:
        return open(PLAYS + "/plays.log").read().splitlines()
    except OSError:
        return []


def played(n):
    return os.path.getsize(f"{PLAYS}/play-{n}.raw")


def first_sound(n, t0):
    try:
        return os.path.getmtime(f"{PLAYS}/start-{n}") - t0
    except OSError:
        return -1


# ---- the little things ---------------------------------------------------------------------------
real_machine, real_max = g.platform.machine, g.sys.maxsize
got = {}
for m, bits in (("aarch64", 64), ("aarch64", 32), ("armv7l", 32), ("armv8l", 32), ("armv6l", 32), ("x86_64", 64)):
    g.platform.machine = lambda m=m: m
    g.sys.maxsize = 2 ** 63 - 1 if bits == 64 else 2 ** 31 - 1
    got[f"{m}/{bits}"] = g.piper_arch()
g.platform.machine, g.sys.maxsize = real_machine, real_max
check(f"which Piper: {got}", got == {"aarch64/64": "aarch64", "aarch64/32": "armv7l", "armv7l/32": "armv7l",
                                     "armv8l/32": "armv7l", "armv6l/32": None, "x86_64/64": "x86_64"})
check("where a voice is", g.voice_folder("en_GB-northern_english_male-medium") == "en/en_GB/northern_english_male/medium"
      and g.voice_folder("en_US-amy-low") == "en/en_US/amy/low")
said = g.speech_text("It's 71°F and sunny ☀️ — *lovely* out.\nRain at 4 °C later")
check(f"made for saying: {said!r}", said == "It's 71 degrees and sunny — lovely out. Rain at 4 degrees later")
parts = g.speech_sentences("Hi! This is me. And here's another sentence? Yes. The end.")
check(f"a sentence at a time, a short one with the next: {parts}",
      parts == ["Hi! This is me.", "And here's another sentence?", "Yes. The end."])
wav = S + "/t.wav"
with wave.open(wav, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"".join(int(v).to_bytes(2, "little", signed=True) for v in (1000, -2000, 30000, -30000)))
pcm, rate = g.read_speech(wav, 50)
check("at the media volume", rate == 16000 and [int.from_bytes(pcm[i:i + 2], "little", signed=True)
                                               for i in range(0, 8, 2)] == [500, -1000, 15000, -15000])

# ---- a pretend internet: Piper's release and the voice library ---------------------------------
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as t:
    data = b"#!/bin/sh\necho evil\n"
    ti = tarfile.TarInfo("piper/../../evil.sh"); ti.size = len(data); ti.mode = 0o755
    t.addfile(ti, io.BytesIO(data))
BAD_TAR = buf.getvalue()
FILES = {"/piper_linux_x86_64.tar.gz": open(DL + "/piper_linux_x86_64.tar.gz", "rb").read(),
         "/bad/piper_linux_x86_64.tar.gz": BAD_TAR}
for vid in ("en_US-amy-low", "en_GB-alan-low", "en_US-amy-medium"):
    FILES[f"/v/{g.voice_folder(vid)}/{vid}.onnx"] = open(AMY[0], "rb").read()
    FILES[f"/v/{g.voice_folder(vid)}/{vid}.onnx.json"] = open(AMY[1], "rb").read()
FILES["/v/" + g.voice_folder("en_US-lessac-medium") + "/en_US-lessac-medium.onnx.json"] = b'{"nothing": 1}'
asked = []


class Net(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        asked.append(self.path)
        body = FILES.get(self.path)
        if body is None:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        try:
            for i in range(0, len(body), 1 << 20):
                self.wfile.write(body[i:i + (1 << 20)])
                time.sleep(0.01)
        except OSError:
            pass


net = ThreadingHTTPServer(("127.0.0.1", 18291), Net); net.daemon_threads = True
threading.Thread(target=net.serve_forever, daemon=True).start()
g.PIPER_URL = "http://127.0.0.1:18291/piper_linux_{}.tar.gz"
g.VOICE_URL = "http://127.0.0.1:18291/v/{}/{}"
real_sha = dict(g.PIPER_SHA256)

# ---- getting Piper and a voice ---------------------------------------------------------------------
v = g.Voice()
ready, seen = [], []
v.on_ready = ready.append
v.on_change = lambda: seen.append(dict(v.job) if v.job else None)
check("no Piper yet, no voices", not v.have_piper() and g.voices_here() == set())
ok, why = v.say("Hello.", "en_US-amy-low")
check(f"can't speak without a voice: {why!r}", not ok and "Pick a voice" in why)
check("get: Piper first", v.get("en_US-amy-low") and v.job["what"] == "Piper")
check("...one at a time", not v.get("en_GB-alan-low"))
check("...then the voice, and it's ready", settle(lambda: ready == ["en_US-amy-low"], 60) and v.job is None)
whats = [x["what"] for x in seen if x]
pcts = [x["pct"] for x in seen if x and x["what"] == "Piper"]
check(f"how far along it was said ({len(seen)} times, Piper up to {max(pcts)}%)",
      "Piper" in whats and "Amy, quick" in whats and max(pcts) >= 90)
check("Piper unpacked, runnable, checked", v.have_piper() and os.path.isdir(g.PIPER_DIR + "/espeak-ng-data")
      and not [n for n in os.listdir(os.path.dirname(g.PIPER_DIR)) if n.startswith(".piper-")])
check("the voice on the Pi", g.voices_here() == {"en_US-amy-low"}
      and not [n for n in os.listdir(g.VOICES_DIR) if n.endswith(".part")])
v.get("en_US-lessac-medium")
settle(lambda: v.job is None, 20)
check(f"a voice that isn't one: {v.error!r}", "isn't a voice" in v.error and "en_US-lessac-medium" not in g.voices_here())
v.get("en_GB-jenny_dioco-medium")
settle(lambda: v.job is None, 20)
check(f"one that isn't there: {v.error!r}", "Not Found" in v.error)

# Piper that doesn't check out
shutil.rmtree(g.PIPER_DIR)
g.PIPER_SHA256["x86_64"] = "0" * 64
v.get("en_US-amy-low")
settle(lambda: v.job is None, 60)
check(f"a Piper that doesn't match its SHA-256: refused ({v.error!r})",
      "didn't check out" in v.error and not os.path.exists(g.PIPER_DIR))
g.PIPER_SHA256["x86_64"] = hashlib.sha256(BAD_TAR).hexdigest()
g.PIPER_URL = "http://127.0.0.1:18291/bad/piper_linux_{}.tar.gz"
v.get("en_US-amy-low")
settle(lambda: v.job is None, 20)
check(f"one reaching outside its folder: refused ({v.error!r})",
      "didn't check out" in v.error and not os.path.exists(S + "/lib/evil.sh") and not os.path.exists(S + "/evil.sh"))
g.PIPER_SHA256 = real_sha
g.PIPER_URL = "http://127.0.0.1:18291/piper_linux_{}.tar.gz"
ready.clear()
v.get("en_US-amy-low")
check("...and the real one again", settle(lambda: ready == ["en_US-amy-low"], 60) and v.have_piper())

# ---- speaking, with the real Piper ---------------------------------------------------------------
t0 = time.time()
ok, why = v.say("Hello there. This is a test of the voice, on a pretend speaker.", "en_US-amy-low", "", 100)
check("say: it starts", ok and v.speaking)
done = settle(lambda: not v.speaking, 60)
check(f"...and finishes ({time.time() - t0:.1f} s, its first words after {first_sound(0, t0):.1f} s)",
      done and not v.error)
log = plays()
check(f"one aplay, raw at the voice's rate: {log[0] if log else None}",
      len(log) == 2 and "-t raw -f S16_LE -c 1 -r 16000" in log[0] and log[1].startswith("0 done"))
n0 = played(0)
check(f"...both sentences, {n0 / 32000:.1f} s of speech", 3.0 < n0 / 32000 < 9)
check("...Piper stays loaded for the next one", v.proc is not None and v.proc.poll() is None and v.loaded == "en_US-amy-low")
wavs = os.listdir(v.out)
check(f"...and its WAVs are cleared away ({wavs})", wavs == [])

t0 = time.time()
v.say("A second thing, said quickly now that the voice is loaded.", "en_US-amy-low", "default:CARD=Headphones", 50)
started = settle(lambda: len(plays()) >= 3, 20)
check(f"the next one, with Piper loaded: its first words after {first_sound(1, t0):.2f} s", started)
settle(lambda: not v.speaking, 60)
log = plays()
check(f"...on the card from Settings > Sound: {log[2]}", "-D default:CARD=Headphones" in log[2])

long_text = ("This is a long reply that goes on. " * 6).strip()
v.say(long_text, "en_US-amy-low")
settle(lambda: len(plays()) >= 5, 30)
time.sleep(0.4)
v.say("Cut in.", "en_US-amy-low")
check("a new line cuts the old one off", settle(lambda: not v.speaking, 60) and not v.error)
log = plays()
first_cut = [ln for ln in log if ln.startswith("2 ")]
check(f"...the long one was cut short ({played(2)} bytes) and the new one said",
      played(2) < len(long_text) * 1200 and played(3) > 0 and v.inflight == 0)

v.say(long_text, "en_US-amy-low")
settle(lambda: len([ln for ln in plays() if ln.startswith("4 ")]) >= 1, 30)
t0 = time.time()
v.stop()
check(f"stop: quiet straight away ({time.time() - t0:.2f} s)", not v.speaking and settle(lambda: v.play.poll() is not None, 3))
time.sleep(0.5)
ok, _ = v.say("After a stop.", "en_US-amy-low")
check("...and it speaks again after", ok and settle(lambda: not v.speaking, 60) and not v.error
      and any(ln.startswith("5 done") for ln in plays()))

os.environ["FAKE_APLAY_FAIL"] = "1"
v.say("Nowhere to play this.", "en_US-amy-low")
settle(lambda: not v.speaking, 60)
check(f"a card that's busy: said so ({v.error!r})", "Device or resource busy" in v.error)
del os.environ["FAKE_APLAY_FAIL"]

# a Piper that stops after its first sentence, and one that hands over a pipe for a WAV
real_dir = g.PIPER_DIR
g.PIPER_DIR = SP + "/voicetest/fakepiper"
os.environ["FAKE_PIPER_WAV"] = wav
os.environ["FAKE_PIPER"] = "dies"
v.stop(unload=True)
settle(lambda: v.proc is None, 10)
n = len(plays())
v.say("The first sentence is long enough. The second one never comes.", "en_US-amy-low")
settle(lambda: not v.speaking, 20)
check(f"Piper stops part way: what it made still plays ({v.error!r})",
      any(ln.startswith(f"{n // 2} done") for ln in plays()) and v.error.startswith("Piper stopped") and v.proc is None)
os.environ["FAKE_PIPER"] = "fifo"
t0 = time.time()
v.say("A pipe instead of a WAV.", "en_US-amy-low")
done = settle(lambda: not v.speaking, 10)
check(f"a pipe for a WAV: not opened, said so ({v.error!r}, {time.time() - t0:.1f} s)", done and "not a WAV" in v.error)
del os.environ["FAKE_PIPER"]
g.PIPER_DIR = real_dir
v.stop(unload=True)
settle(lambda: v.proc is None, 10)

# leftovers: a dead process's, an old one under this process's number, and two still in use
me = os.getpid()
names = {"dead": f"en_US-amy-low.onnx.{999999}.part", "old": f"en_US-amy-low.onnx.{me}.part",
         "now": f"en_GB-alan-low.onnx.{me}.part", "other": "en_GB-alan-low.onnx.1.part"}
for k, n_ in names.items():
    open(os.path.join(g.VOICES_DIR, n_), "w").close()
os.utime(os.path.join(g.VOICES_DIR, names["old"]), (g.VOICE_SINCE - 600, g.VOICE_SINCE - 600))
g.Voice.tidy()
left = {k for k, n_ in names.items() if os.path.exists(os.path.join(g.VOICES_DIR, n_))}
check(f"leftovers tidied, ones in use kept: {sorted(left)}", left == {"now", "other"})
for n_ in names.values():
    if os.path.exists(os.path.join(g.VOICES_DIR, n_)):
        os.remove(os.path.join(g.VOICES_DIR, n_))

g.VOICE_IDLE = 1
check("quiet a while: Piper let go", settle(lambda: v.proc is None and v.out == "", 15))
g.VOICE_IDLE = 120
v.warm("en_US-amy-low")
check("warmed up ahead of a reply: loaded, saying nothing", settle(lambda: v.proc is not None, 10) and not v.speaking)
v.stop(unload=True)
check("stop(unload=True): let go", settle(lambda: v.proc is None, 10))
v.remove("en_US-amy-low")
check("a voice taken off the Pi", "en_US-amy-low" not in g.voices_here())

# ---- media mode: the Bot ---------------------------------------------------------------------------
replies = []


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self.reply({"models": [{"name": "llama3.2:3b"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        replies.append(1)
        self.reply({"response": "It's sunny and 71°F. A lovely evening for a walk!"})


ol = ThreadingHTTPServer(("127.0.0.1", 11557), Ollama); ol.daemon_threads = True
threading.Thread(target=ol.serve_forever, daemon=True).start()


class FB:
    w, h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def close(self):
        pass


shots = {}
open(HOME + "/friend.txt", "w").write("# from before\nserver = 127.0.0.1:11557\nmodel = llama3.2:3b\nname = Sam\n")
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
apps = [a for a, _ in m.home_apps()]
check(f"the home screen: {apps}", "Bot" in apps and "Friend" not in apps)
check("Settings: Bot", ("friend", "Bot", None) in g.SETTINGS)
fi = m.tab_index("friend")
check("its tab is called Bot", g.LIBRARY[fi]["name"] == "Bot")
m.friend.load(m.friend_files())
check("friend.txt (its earlier name) still read", m.friend.ready() and m.friend.name == "Sam")
m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.set_page = "friend"
rows = m.settings_rows()
keys = [r[0] for r in rows]
check(f"Settings > Bot: {[r[1] for r in rows]} (its voice: in its Character, first)", keys[0] == "f_char"
      and "f_speak" not in keys and "f_voice" not in keys and m.char_value("voice") == "None"
      and m.char_value("speak") == "On")
m.set_sel = [r[0] for r in m.settings_rows()].index("f_char"); m.press("a")
m.char_sec, m.char_row = 4, 1                      # (its Character's Talks out loud)
m.press("right")
check("no voice: 'out loud' asks for one", "Pick a voice" in (m.msg or ""))
m.char_sec, m.char_row = 4, 0                      # (its Character's Voice)
m.press("right")
check(f"◀▶ on its Character's Voice, none on the Pi: A gets one ({m.msg!r})", "A gets it a voice" in (m.msg or ""))
m.press("a")
check("A on Voice: the voices", m.set_page == "f_voices")
rows = m.settings_rows()
check(f"...None and {len(rows) - 1} voices", rows[0] == ("v_none", "None", "") and len(rows) == 1 + len(g.BOT_VOICES))
m.dirty = True; m.flush(); shots["voices"] = FB.last
amy = [r[2] for r in rows].index("en_US-amy-low")
m.set_sel = amy; m.press("a")
check(f"A on one that isn't here: fetched ({m.msg!r})", "Getting Amy, quick" in (m.msg or "") and m.voice.job)
m.dirty = True; m.flush(); shots["getting"] = FB.last
check("...ready, put to use, and a word in it", settle(lambda: (m.tick() or True) and m.bot_voice() == "en_US-amy-low", 60))
bot = open(HOME + "/bot.txt").read()
check(f"bot.txt: carried on from friend.txt, its own header, with the voice ({bot.splitlines()[:1]})",
      "server = 127.0.0.1:11557" in bot and "name = Sam" in bot and "voice = en_US-amy-low" in bot
      and bot.startswith("# Bot:") and "# from before" not in bot)
open(HOME + "/friend.txt", "a").write("model = llava\n")
m.friend.load(m.friend_files())
check("...and from now on friend.txt isn't read", m.friend.model != "llava" and m.friend.name == "Sam")
check(f"...'{m.msg}', and the sample said", "is ready" in (m.msg or "") and settle(lambda: m.voice.speaking, 5)
      and settle(lambda: not m.voice.speaking, 60))
m.dirty = True; m.flush(); shots["using"] = FB.last
before = len(plays())
alan = [r[2] for r in rows].index("en_GB-alan-low")
m.set_sel = alan; m.press("a")
settle(lambda: (m.tick() or True) and m.bot_voice() == "en_GB-alan-low", 60)
check("another voice: fetched and used", m.bot_voice() == "en_GB-alan-low" and settle(lambda: len(plays()) > before, 20))
settle(lambda: not m.voice.speaking, 60)
m.set_sel = alan; m.press("x")
check(f"X on a voice: asks first ({m.msg!r})", "Press X again" in (m.msg or "") and "en_GB-alan-low" in g.voices_here())
m.dirty = True; m.flush(); shots["remove"] = FB.last
m.press("x")
check("X again: off the Pi, and no voice now", "en_GB-alan-low" not in g.voices_here() and m.bot_voice() == "")
m.set_sel = amy; m.press("a")
check("a voice that's here: used at once", m.bot_voice() == "en_US-amy-low" and "Using Amy" in (m.msg or ""))
settle(lambda: not m.voice.speaking, 60)
m.press("b")
check("B: back to its Character, on Voice", m.set_page == "f_char" and m.char_key() == "voice")
m.press("b")
check("...B again: Settings > Bot, on Character", m.set_page == "friend" and m.settings_rows()[m.set_sel][0] == "f_char")
m.dirty = True; m.flush(); shots["settings"] = FB.last

# the Bot's page
m.open_app(fi)
settle(lambda: not m.friend.busy, 20)
settle(lambda: not m.voice.speaking, 60)                 # (it said hello)
m.friend.clear()
before = len(plays())


def menu_do(what):
    """X's menu on the Bot: what (its key) picked, if it's there."""
    m.press("x")
    whats = [w for _, w in m.friend_options()]
    if what not in whats:
        m.press("b")
        return False
    m.friend_more["sel"] = whats.index(what)
    m.press("a")
    return True


check(f"nothing said yet: no Say it again in X's menu ({[t for t, _ in m.friend_options()]})",
      "speak" not in [w for _, w in m.friend_options()])
m.friend.say("what's it like out?")
check("a reply...", settle(lambda: m.friend.log and m.friend.log[-1]["who"] == "friend", 20))
check("...said out loud", settle(lambda: m.voice.speaking, 5))
m.dirty = True; m.flush(); shots["speaking"] = FB.last
check(f"while it speaks, X's menu: Stop talking ({[t for t, _ in m.friend_options()]}): quiet",
      menu_do("hush") and settle(lambda: not m.voice.speaking, 5))
time.sleep(0.3)
n = len(plays())
check("X's menu, Say it again: the last reply again", menu_do("speak") and settle(lambda: len(plays()) > n, 20))
settle(lambda: not m.voice.speaking, 60)
m.dirty = True; m.flush(); shots["bot"] = FB.last
m.tab = m.tab_index("settings"); m.load_tab(m.tab); m.set_page = "friend"; m.set_sel = 0
m.press("a")
m.char_sec, m.char_row = 4, 1                      # (its Character's Talks out loud)
m.press("right")
check("'out loud' off", m.char_value("speak") == "Off" and "speak = off" in open(HOME + "/bot.txt").read())
m.press("b")
m.open_app(fi)
n = len(plays())
m.friend.say("and tomorrow?")
settle(lambda: not m.friend.busy, 20)
time.sleep(1)
check("...a reply isn't said", len(plays()) == n and not m.voice.speaking)
m.friend_set(speak="on")
m.proc = type("P", (), {"poll": lambda self: None})()
m.friend.say("and now?")
settle(lambda: not m.friend.busy, 20)
time.sleep(1)
check("...nor while something's playing", len(plays()) == n)
menu_do("speak")
check(f"...Say it again says why: {m.msg!r}", m.msg == "Not while something's playing" and not m.voice.speaking)
out = m.web_friend_do({"do": "aloud"})
check(f"...and so does the web page: {out}", out.get("error") == "Not while something's playing")
m.proc = None

# the web page
w = m.web_friend()["voice"]
check(f"the web page: the voice, and the list ({w['id']}, {len(w['list'])})",
      w["id"] == "en_US-amy-low" and w["speak"] and w["can"] and len(w["list"]) == len(g.BOT_VOICES)
      and [x for x in w["list"] if x["id"] == "en_US-amy-low"][0]["here"])
out = m.web_friend_do({"do": "aloud"})
check(f"'Say it out loud': {out}", out.get("ok") and settle(lambda: m.voice.speaking, 5))
check("...and the page sees it speaking", m.web_friend()["voice"]["speaking"])
out = m.web_friend_do({"do": "hush"})
check("'Stop'", out.get("ok") and settle(lambda: not m.voice.speaking, 5))
out = m.web_friend_do({"do": "set", "speak": "off"})
check("out loud: off", out.get("ok") and not m.bot_speaks())
out = m.web_friend_do({"do": "set", "speak": "on"})
out = m.web_friend_do({"do": "set", "voice": "en_US-amy-medium"})
check(f"a voice from the web page: fetched ({out})", out.get("ok") and "Getting" in out.get("said", "")
      and m.web_friend()["voice"]["getting"] == "en_US-amy-medium")
check("...and used", settle(lambda: (m.tick() or True) and m.bot_voice() == "en_US-amy-medium", 60))
out = m.web_friend_do({"do": "set", "voice": "not-a-voice"})
check(f"one that isn't: {out}", "error" in out)
out = m.web_friend_do({"do": "set", "voice": ""})
check("no voice", out.get("ok") and m.bot_voice() == "")
out = m.web_friend_do({"do": "aloud"})
check(f"...then nothing to say it with: {out}", "Pick a voice" in out.get("error", ""))
m.tab = m.tab_index("settings"); m.load_tab(m.tab)
out = m.web_friend_do({"do": "open"})
check("'Show on the Pi' opens the Bot", out.get("ok") and m.tab == fi and m.on_friend_page())

# ---- Piper and aplay run as the home folder's owner, not root ----------------------------------
SAFE = [SP]                                    # (the folder of work, and each folder it's in)
while os.path.dirname(SAFE[-1]) not in (SAFE[-1], "/"):
    SAFE.append(os.path.dirname(SAFE[-1]))
modes = {d: os.stat(d).st_mode & 0o777 for d in SAFE}
try:
    for d in SAFE:
        os.chmod(d, modes[d] | 0o001)                 # (somewhere they can reach, for this test)
    T = SP + "/t59"
    shutil.rmtree(T, ignore_errors=True)
    os.makedirs(T + "/home/pi")
    os.chown(T + "/home/pi", 1000, 1000)
    os.chmod(T, 0o755)
    shutil.copytree(g.PIPER_DIR, T + "/piper", symlinks=True)
    os.makedirs(T + "/voices")
    for src, ext in zip(AMY, (".onnx", ".onnx.json")):
        shutil.copy(src, T + "/voices/en_US-amy-low" + ext)
        os.chmod(T + "/voices/en_US-amy-low" + ext, 0o644)
    os.chmod(T + "/voices", 0o755)
    os.chmod(PLAYS, 0o777)
    os.chmod(PLAYS + "/plays.log", 0o666)
    g.home_dir = lambda: T + "/home/pi"
    g.PIPER_DIR, g.VOICES_DIR = T + "/piper", T + "/voices"
    uid, gid, groups, home = g.voice_user()
    check(f"who speaks: uid {uid}, groups {groups}, home {home}", uid == 1000 and gid == 1000 and groups == [29])
    u = g.Voice()
    u.warm("en_US-amy-low")
    settle(lambda: u.proc is not None, 10)
    time.sleep(0.3)
    status = open(f"/proc/{u.proc.pid}/status").read()
    real = [ln.split()[1] for ln in status.splitlines() if ln.startswith("Uid:")][0]
    env = open(f"/proc/{u.proc.pid}/environ", "rb").read().split(b"\0")
    check(f"Piper runs as {real}, its WAVs in a folder of its own, no home of its own",
          real == "1000" and os.stat(u.out).st_uid == 1000 and b"HOME=/nonexistent" in env)
    n = len(plays())
    u.say("Not as root, this time.", "en_US-amy-low")
    settle(lambda: not u.speaking, 60)
    last = [ln for ln in plays() if "-t raw" in ln][-1]
    check(f"...aplay plays where mplayer does, as root ({last.split()[-1]}), and it was said ({u.error!r})",
          "uid=0" in last and not u.error
          and any(" done " in ln for ln in plays()[n:]))
    u.stop(unload=True)
    settle(lambda: u.proc is None, 10)
finally:
    for d in SAFE:
        os.chmod(d, modes[d])
check("(the folders as they were)", all(os.stat(d).st_mode & 0o777 == modes[d] for d in SAFE))

for name, img in shots.items():
    img.save(f"{S}/{name}.png")
sheet = Image.new("RGB", (640 * 2 + 10, 480 * 4 + 30), (40, 40, 40))
for k, name in enumerate(["voices", "getting", "using", "remove", "settings", "speaking", "bot"]):
    sheet.paste(shots[name], ((k % 2) * 650, (k // 2) * 490))
sheet.save(SP + "/voice_sheet.png")
m.voice.stop(unload=True)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
