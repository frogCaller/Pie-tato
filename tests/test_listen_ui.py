"""The bot listening, in media mode. Settings > Bot's rows (only with a microphone). Listens: Auto, as it comes: a USB
microphone plugged in and it listens by itself (Vosk fetched the first time, and said so; then a word on how to talk to
it), to that microphone only; taken out, it stops, quietly; plugged in again, it listens again; not a webcam's, nor a
PC's own sound card (the note says why), but before the bot's set up (it does things without it); Vosk tried again by
itself, quietly and only a
few times, when it couldn't be fetched. Talking to it: the wake phrase, what's heard going to the bot, its page coming
up, its answer. On: any microphone, the one you pick; the wake phrase typed; the Bot page (Listening…, what it hears,
Talk to it), deaf while something plays, and off in the terminal. Off. The web page's row: Auto, On and Off. A pretend
Ollama; the real Vosk with a pretend arecord."""
import io, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_listen_ui"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
MIC = S + "/mic"
os.makedirs(MIC)
os.environ["PATH"] = SP + "/listen_t/bin:" + os.environ["PATH"]
os.environ["FAKE_MIC_DIR"] = MIC
os.environ["FAKE_MIC_SPEED"] = "3"
os.environ["FAKE_MIC_LOG"] = S + "/mic.log"
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.listen as L
import pitato.screens.bot as B
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


# ---- a pretend Ollama, and microphones -------------------------------------------------------------------------------
asked = []


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self.reply(200, {"models": [{"name": "llama3.2:3b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":
            return self.reply(200, {"capabilities": ["completion"]})
        asked.append(body)
        time.sleep(0.5)
        return self.reply(200, {"response": "Why did the potato cross the road? It saw a fork up ahead."})


ol = ThreadingHTTPServer(("127.0.0.1", 11556), Ollama)
threading.Thread(target=ol.serve_forever, daemon=True).start()

A = S + "/asound"
os.makedirs(A + "/card0/pcm0p")
HDMI = " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
open(A + "/cards", "w").write(HDMI)
V = S + "/v4l"                                     # (a webcam, for when it's plugged in)
os.makedirs(S + "/usbdev/1-1/1-1:1.0")
open(S + "/usbdev/1-1/idVendor", "w").write("046d\n"); open(S + "/usbdev/1-1/idProduct", "w").write("082d\n")
os.makedirs(V)
L.ASOUND, L.V4L = A, V
plugged = {}


def cards():
    open(A + "/cards", "w").write(HDMI + "".join(plugged[n] for n in sorted(plugged)))


def plug_mic(cid, name, num, usb="0c76:161f", plays=False, line=None):
    shutil.rmtree(f"{A}/card{num}", ignore_errors=True)
    os.makedirs(f"{A}/card{num}/pcm0c")
    if plays:
        os.makedirs(f"{A}/card{num}/pcm0p")
    if usb:
        open(f"{A}/card{num}/usbid", "w").write(usb + "\n")
    plugged[num] = line or f" {num} [{cid:<15}]: USB-Audio - {name}\n                      {name} at usb-xhci-hcd.0-1.2\n"
    cards()


def unplug(num):
    shutil.rmtree(f"{A}/card{num}", ignore_errors=True)
    plugged.pop(num, None)
    cards()


def plug_webcam():
    plug_mic("C920", "HD Pro Webcam C920", 2, usb="046d:082d")
    os.makedirs(V + "/video0", exist_ok=True)
    if not os.path.islink(V + "/video0/device"):
        os.symlink(S + "/usbdev/1-1/1-1:1.0", V + "/video0/device")


def unplug_webcam():
    unplug(2)
    shutil.rmtree(V + "/video0", ignore_errors=True)


LD = S + "/listen"                                 # (Vosk not here yet)
L.LISTEN_DIR = LD
L.as_user = lambda: {}
B.is_pc = lambda: False                            # (a Pi; a PC further down)
B.MIC_LOOK = 0.3                                   # (it looks every two seconds: sooner, here)
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))
BOT = "server = 127.0.0.1:11556\nmodel = llama3.2:3b\n"
open(HOME + "/bot.txt", "w").write(BOT)
m.friend.load(m.friend_files())


def settle(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def ticks(secs):
    settle(lambda: False, secs)


def say(*names):
    for k, n in enumerate(names):                  # (whole, when the pretend arecord sees it)
        shutil.copyfile(f"{SP}/listen_t/clips/{n}.raw", f"{MIC}/.{k}.part")
        os.rename(f"{MIC}/.{k}.part", f"{MIC}/{time.time():.6f}-{k}.raw")


def keys():
    return [r[0] for r in m.settings_rows()]


def listen_keys():
    """Settings > Bot's rows after Says its replies out loud: listening's."""
    return [k for k in keys()[keys().index("f_model") + 1:] if k in ("f_listen", "f_wake", "f_mic")]


def bot_txt():
    return open(HOME + "/bot.txt").read()


def web_row(key):
    for sec in m.web_settings()["sections"]:
        for r in sec["rows"]:
            if r["key"] == key:
                return r
    return None


def note_fits(note):
    from PIL import ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    return d.textlength(note, font=m.fonts["small"]) <= 330


got = []


def pretend_get():                                 # (Vosk on its way, a little way along)
    got.append(1)
    m.ears.job = {"what": "Vosk", "pct": 12}
    return True


m.ears.get = pretend_get

# ---- Settings > Bot: Listens there before a microphone's ever plugged in; its wake phrase with one -------------------
m.friend_setup()
check(f"no microphone: Listens there (to turn it off beforehand), no wake phrase yet: {listen_keys()}",
      listen_keys() == ["f_listen"])
check("Listens: Auto, as it comes", m.bot_listen_mode() == "auto" and m.friend_value("f_listen") == "Auto")
check(f"...the note: {m.listen_note()}", m.listen_note() == ("It listens when a microphone's plugged in", False)
      and note_fits(m.listen_note()[0]))
ticks(1)
check("...no microphone: not listening, and nothing fetched", m.ears.state == "off" and not got)
r = web_row("f_listen")
check(f"...the web page's the same ({r and (r['value'], r['status'])})", r and r["value"] == "auto"
      and r["status"] == "It listens when a microphone's plugged in" and web_row("f_wake") is None)
m.set_sel = keys().index("f_listen")
m.press("left")
check(f"Off, before a microphone's plugged in ({toasts[-1:]})", m.bot_listen_mode() == "off" and "listen = off" in bot_txt()
      and toasts[-1] == "It isn't listening now")
plug_mic("Device", "USB PnP Sound Device", 1)
ticks(1.5)
check(f"...then one plugged in: nothing fetched, not listening ({m.ears.state}, {got})", m.ears.state == "off"
      and not got and not m.ears.on)
unplug(1)
ticks(1)
m.set_sel = keys().index("f_listen")
m.press("right")
check(f"Auto again ({toasts[-1:]})", m.bot_listen_mode() == "auto" and "listen = auto" in bot_txt()
      and toasts[-1] == "It listens when a microphone's plugged in")
was_case = getattr(m, "case", None)
m.case = "gpi2"
plug_mic("Audio", "USB Audio Device", 7, plays=True, line=" 7 [Audio          ]: USB-Audio - USB Audio Device\n")
check(f"in a GPi Case, its own sound isn't a microphone: {listen_keys()}", listen_keys() == ["f_listen"])
ticks(1)
check("...nor listened with by itself", m.ears.state == "off" and not got and m.auto_mics() == [])
m.case = None
check("...on another Pi, a headset is", "f_wake" in keys() and [c["id"] for c in m.auto_mics()] == ["Audio"])
unplug(7)
m.case = was_case
ticks(1)

# ---- Auto: a USB microphone plugged in, and it listens by itself -------------------------------------------------------
toasts.clear()
plug_mic("Device", "USB PnP Sound Device", 1)
check(f"a microphone plugged in: Vosk fetched by itself, and said so ({toasts})",
      settle(lambda: got, 5) and toasts[-1:] == ["Getting what it listens with (45 MB)"] and len(got) == 1)
check(f"...Listens and Wake phrase: {listen_keys()}", listen_keys() == ["f_listen", "f_wake"])
check(f"...the row says how far along it is: {m.friend_value('f_listen')!r}", m.friend_value("f_listen") == "Getting it… 12%")
check(f"...and the note: {m.listen_note()}", m.listen_note() == ("Getting Vosk… 12%", True))
check("...not listening yet", m.ears.state == "off")
ticks(1)
check("...fetched once", len(got) == 1)
m.set_sel = keys().index("f_listen")
m.dirty = True; m.tick(); m.flush()
shots[-1].save(S + "/settings_getting.png")

os.makedirs(LD)
shutil.copy(SP + "/vosk_whl/x/manylinux_2_12_x86_64.manylinux2010_x86_64/vosk/libvosk.so", LD + "/libvosk.so")
os.symlink(SP + "/vosk_model_npm/vosk-model-small-en-us-0.15", LD + "/" + L.MODEL)
m.ears.job = None
toasts.clear()
m.ears_ready()
check("Vosk here: listening by itself, with that microphone, and no other in its place",
      settle(lambda: m.ears.state == "waiting", 30) and m.ears.want == ("hey potato", "Device") and m.ears.fallback is False)
check(f"...and it says how to talk to it: {toasts}", toasts == ['Say "hey potato" to talk to your bot'])
check(f"...the note: {m.listen_note()}", m.listen_note() == ('Listening for "hey potato"', True))
def mic_log():
    try:
        return open(S + "/mic.log").read().strip()
    except OSError:
        return ""


check(f"...and the microphone ({mic_log().split()[-1:]})", settle(lambda: mic_log().endswith("plughw:CARD=Device,DEV=0"), 5))
m.dirty = True; m.tick(); m.flush()
shots[-1].save(S + "/settings_auto.png")
r = web_row("f_listen")
check(f"the web page: Auto, On and Off, Auto picked, and what it's doing ({r and (r['value'], r['choices'], r['status'], r['tone'])})",
      r and r["value"] == "auto" and r["choices"] == ["auto", "on", "off"] and r["names"]["auto"] == "Auto"
      and r["status"] == 'Listening for "hey potato"' and r["tone"] == "ok")

# talking to it
m.go_home()
m.view = "home"
toasts.clear()
say("wake")
check(f"the wake phrase: Listening… ({toasts})", settle(lambda: "Listening…" in toasts and m.msg == "Listening…"))
say("joke")
check(f"what you said, to the bot, and its page comes up: {[x['text'] for x in m.friend.log]}",
      settle(lambda: any(x["who"] == "you" for x in m.friend.log)) and m.on_friend_page()
      and "joke" in [x["text"] for x in m.friend.log if x["who"] == "you"][-1].lower())
check("...the Listening… notice gone", m.msg != "Listening…")
check("...and it answers", settle(lambda: not m.friend.busy and m.friend.log[-1]["who"] == "friend")
      and "fork" in m.friend.log[-1]["text"])
check(f"...what it was asked: {asked[-1]['prompt'][-80:]!r}", "joke" in asked[-1]["prompt"].lower())

# taken out, and plugged in again
toasts.clear()
proc = m.ears.proc
unplug(1)
check(f"taken out: it stops listening, quietly ({toasts})", settle(lambda: m.ears.state == "off", 5) and not toasts
      and proc.poll() is not None and not m.ears.on)
check(f"...no Talk to it now: {[o[0] for o in m.friend_options()]}", m.friend_options()[0][1] != "talk")
ticks(1)
check("...and stays stopped", m.ears.state == "off" and not toasts)
plug_mic("Device", "USB PnP Sound Device", 1)
check(f"plugged in again: listening, and a word on how to talk to it ({toasts})",
      settle(lambda: m.ears.state == "waiting", 30) and toasts == ['Say "hey potato" to talk to your bot'])
say("wake", "joke")
n = len([x for x in m.friend.log if x["who"] == "you"])
check("...it hears you", settle(lambda: len([x for x in m.friend.log if x["who"] == "you"]) > n, 30))
settle(lambda: not m.friend.busy)

# not a webcam's, nor a PC's own sound card; before the bot's set up, though
unplug(1)
settle(lambda: m.ears.state == "off", 5)
toasts.clear()
plug_mic("C920", "HD Pro Webcam C920", 2, usb="046d:082d")      # (a webcam's sound card, a moment before its picture)
m.mics_next = 0; m.listen_tick(time.monotonic())
check(f"a webcam's sound before its picture: taken for a microphone, so looked at once more first ({m.mics_maybe})",
      m.mics_maybe == ("C920",) and m.ears.state == "off" and not m.ears.on)
plug_webcam()                                      # (its picture: it's a webcam's)
m.mics_next = 0; m.listen_tick(time.monotonic())
check(f"...its picture there by then: never listened with, nothing said ({m.ears.state}, {toasts})",
      m.ears.state == "off" and not m.ears.on and m.mics_maybe is None and not toasts)
ticks(1.5)
check(f"a webcam's microphone: not by itself ({m.ears.state}, {[c['id'] for c in L.mics()]})",
      m.ears.state == "off" and [c["id"] for c in L.mics()] == ["C920"] and L.mics()[0]["camera"] and not toasts)
m.friend_setup()
check(f"...its rows there, and the note says how: {m.listen_note()}", "f_listen" in keys()
      and m.listen_note() == ("Pick On to listen through your webcam", False) and note_fits(m.listen_note()[0]))
unplug_webcam()
B.is_pc = lambda: True
plug_mic("PCH", "HDA Intel PCH", 3, usb="", plays=True,
         line=" 3 [PCH            ]: HDA-Intel - HDA Intel PCH\n                      HDA Intel PCH at 0xf7f10000 irq 32\n")
ticks(1.5)
check(f"a PC's own sound card: not by itself ({m.ears.state})", m.ears.state == "off" and not toasts)
check(f"...the note: {m.listen_note()}", m.listen_note() == ("Pick On for this PC's own microphone", False)
      and note_fits(m.listen_note()[0]))
plug_mic("Device", "USB PnP Sound Device", 1, plays=True)          # (a USB headset: it plays too)
check(f"...a USB headset on the PC: that one, not the PC's own ({[c['id'] for c in L.mics()]}, {m.ears.want})",
      settle(lambda: m.ears.state == "waiting", 30) and m.ears.want == ("hey potato", "Device")
      and [c["id"] for c in L.mics()] == ["Device", "PCH"])
unplug(3)
B.is_pc = lambda: False
toasts.clear()
m.friend_set(server="")
check(f"no bot yet: listening all the same, for what it does without one ({m.ears.state})",
      settle(lambda: m.ears.state == "waiting", 30))
check(f"...the note: {m.listen_note()}", m.listen_note() == ('Listening for "hey potato"', True))
m.friend_set(server="127.0.0.1:11556")
check("set up: listening still", settle(lambda: m.ears.state == "waiting", 30))
out = m.web_mic_set(True)
check(f"Mic here: the web page's microphone ({out}, {m.ears.want})", out == {"ok": True, "listens": True}
      and settle(lambda: m.ears.want == ("hey potato", L.WEB_MIC), 5))
m.web_mic_set(False)
check(f"...off: the Pi's again ({m.ears.want})", settle(lambda: m.ears.want == ("hey potato", "Device"), 5))

# Vosk couldn't be fetched: tried again by itself, after a while, quietly, a few times
unplug(1)
settle(lambda: m.ears.state == "off", 5)
os.rename(LD, LD + ".away")
fails = []


def failing_get():                                 # (no internet yet: it doesn't arrive)
    fails.append(time.monotonic())
    m.ears.got_error = "Couldn't get Vosk (no internet)"
    return True


m.ears.get = failing_get
B.LISTEN_AGAIN = 0.6
toasts.clear()
plug_mic("Device", "USB PnP Sound Device", 1)
check(f"Vosk not here, and it can't be fetched: said so once ({toasts})", settle(lambda: fails, 5)
      and toasts == ["Getting what it listens with (45 MB)"])
check(f"...the note: {m.listen_note()}", m.listen_note() == ("Couldn't get Vosk (no internet)", False))
ticks(4)
check(f"...tried again by itself, quietly, {len(fails) - 1} more times", len(fails) == 1 + L.LISTEN_TRIES
      and toasts == ["Getting what it listens with (45 MB)"] and all(b - a > 0.5 for a, b in zip(fails, fails[1:])))
os.rename(LD + ".away", LD)
m.ears.get = pretend_get
m.friend_setup()
m.set_sel = keys().index("f_listen")
toasts.clear()
m.listen_set("auto")
check(f"Auto picked again: a fresh try, and it's here now: listening ({toasts})",
      settle(lambda: m.ears.state == "waiting", 30) and toasts == ['Say "hey potato", then what you want']
      and not m.ears.got_error)

# Auto, with a microphone picked in Settings > Bot: that one, while it's plugged in
plug_webcam()
ticks(1)
check(f"a webcam plugged in too: still the USB microphone ({m.ears.want})", m.ears.want == ("hey potato", "Device"))
m.friend_set(mic="C920")
check(f"the webcam's picked: that one ({m.ears.want})", settle(lambda: m.ears.want == ("hey potato", "C920")
      and m.ears.state == "waiting", 30))
unplug_webcam()
m.ears.proc.kill()                                 # (as arecord stops when its microphone's taken out)
check(f"...taken out: the USB microphone again, by itself ({m.ears.want})",
      settle(lambda: m.ears.want == ("hey potato", "Device") and m.ears.state == "waiting", 30))
m.friend_set(mic="")

# a Pi Vosk doesn't run on (a Pi Zero W, say): Auto says so; On can't be picked
os.rename(LD, LD + ".away")
B.listen_supported = lambda: False
m.listen_now()
toasts.clear()
check(f"Vosk doesn't run here: not listening, and the note says so ({m.listen_note()})",
      settle(lambda: m.ears.state == "off", 5) and m.listen_note() == ("Vosk doesn't run on this Pi", False))
check(f"...On can't be picked ({toasts})", m.listen_set("on") is False and toasts == ["Vosk doesn't run on this Pi"]
      and m.bot_listen_mode() == "auto")
out = m.web_settings_do({"cmd": "settings", "key": "f_listen", "value": "on"})
check(f"...nor on the web page ({out})", out == {"error": "Vosk doesn't run on this Pi"} and m.bot_listen_mode() == "auto")
check("...Off and Auto can", m.listen_set("off") and m.listen_set("auto") and m.bot_listen_mode() == "auto")
B.listen_supported = L.supported
os.rename(LD + ".away", LD)
m.listen_now()
check("Vosk back: listening", settle(lambda: m.ears.state == "waiting", 30))

# bot.txt's listen =, typed by hand
modes = {}
for v in ("off # not now", "never", "disabled", "", "AUTO", "Yes", "on   # always", "no", "atuo"):
    m.friend.conf["listen"] = v
    modes[v] = m.bot_listen_mode()
check(f"bot.txt's listen =, typed by hand: anything it doesn't know is off ({modes})", modes == {
      "off # not now": "off", "never": "off", "disabled": "off", "": "auto", "AUTO": "auto", "Yes": "on",
      "on   # always": "on", "no": "off", "atuo": "off"})
open(HOME + "/bot.txt", "w").write(BOT + "listen = off   # not now\n")
m.friend.load(m.friend_files())
check("...changed to off by hand while it listens: it stops by itself", settle(lambda: m.ears.state == "off"
      and not m.ears.on, 5))
open(HOME + "/bot.txt", "w").write(BOT)
m.friend.load(m.friend_files())
check("...no listen = at all: Auto, and listening by itself again", m.bot_listen_mode() == "auto"
      and settle(lambda: m.ears.state == "waiting", 30))
m.friend_setup()
m.set_sel = keys().index("f_listen")

# ---- On: always, with any microphone -------------------------------------------------------------------------------
m.press("right")
check(f"right: On ({toasts[-1]!r})", m.bot_listen_mode() == "on" and m.friend_value("f_listen") == "On"
      and "listen = on" in bot_txt() and toasts[-1] == 'Say "hey potato", then what you want')
check(f"...the first microphone there is ({m.ears.want}, {m.ears.fallback})", settle(lambda: m.ears.want == ("hey potato", "")
      and m.ears.fallback is True and m.ears.state == "waiting", 30))
unplug(1)
plug_webcam()
m.ears.proc.kill()                                 # (as arecord stops when its microphone's taken out)
check(f"...a webcam's too ({mic_log().split()[-1:]})", settle(
      lambda: mic_log().endswith("plughw:CARD=C920,DEV=0") and m.ears.state == "waiting", L.RETRY + 30))
unplug_webcam()
plug_mic("Device", "USB PnP Sound Device", 1)

# the wake phrase, typed
m.set_sel = keys().index("f_wake")
m.press("a")
check("A on Wake phrase: the keyboard", m.view == "keys")
m.close_keyboard(False)
m.listen_wake_typed("hi")
check(f"too short: {toasts[-1]!r}", "word or two" in toasts[-1] and m.bot_wake() == "hey potato")
m.listen_wake_typed("  Hey, SPUD! ")
check(f"a phrase of your own: {m.bot_wake()!r}, listening for it ({toasts[-1]!r})", m.bot_wake() == "hey spud"
      and "wake = hey spud" in bot_txt() and settle(lambda: m.ears.want == ("hey spud", ""))
      and toasts[-1] == 'Say "hey spud", then what you want')
m.listen_wake_typed("")
check("blank: hey potato again", m.bot_wake() == "hey potato" and settle(lambda: m.ears.want == ("hey potato", "")))

# two microphones: which one
plug_webcam()
check(f"two microphones: Microphone too: {listen_keys()}", listen_keys() == ["f_listen", "f_wake", "f_mic"]
      and m.friend_value("f_mic") == "Auto")
m.set_sel = keys().index("f_mic")
m.press("right")
check(f"the next: {m.friend_value('f_mic')!r}", m.friend_value("f_mic") == "USB PnP Sound Device"
      and settle(lambda: m.ears.want == ("hey potato", "Device")))
m.press("left")
check("Auto again", m.friend_value("f_mic") == "Auto" and settle(lambda: m.ears.want == ("hey potato", "")))
check("listening", settle(lambda: m.ears.state == "waiting", 30))

# the Bot page: Talk to it, Listening…, and what it hears as you say it
m.go_home(); m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
m.set_setting("bot_mode", "chat")
m.press("x")
opts = m.friend_options()
check(f"X: Talk to it, first: {[o[0] for o in opts]}", opts[0] == ("Talk to it", "talk"))
m.press("a")
check("Talk to it: listening", settle(lambda: m.ears.state == "listening", 5) and m.friend_more is None)
m.ears.heard = "tell me a"
m.dirty = True; m.tick(); m.flush()
shots[-1].save(S + "/bot_hearing.png")
m.ears.heard = ""
m.dirty = True; m.tick(); m.flush()
shots[-1].save(S + "/bot_listening.png")
n = len([x for x in m.friend.log if x["who"] == "you"])
say("joke")
check("...what's said next goes to it", settle(lambda: len([x for x in m.friend.log if x["who"] == "you"]) > n))
settle(lambda: not m.friend.busy)

# listening while music plays or is paused (and a video, on a Pi 4 or 5); deaf while a game runs, or a video plays on
# a slower Pi
check("not busy now", not m.ears_busy())
was = (m.kind, m.paused, m.pi_slow)
m.proc, m.kind, m.paused = object(), "audio", False
check("music playing: listening", not m.ears_busy())
m.paused = True
check("...paused: listening", not m.ears_busy())
m.kind, m.paused, m.pi_slow = "video", False, True
check("a video playing on a slower Pi: deaf", m.ears_busy())
m.pi_slow = False
check("...on a Pi 4 or 5: listening", not m.ears_busy())
m.proc = None
m.kind, m.paused, m.pi_slow = was
m.game = object()
check("a game: deaf", m.ears_busy())
m.game = None

# not set up: it says so
open(HOME + "/bot.txt", "w").write("listen = on\n")
m.friend.load(m.friend_files())
toasts.clear()
m.bot_heard("Tell me a joke")
check(f"no bot yet: {toasts}", toasts and "Set up your bot first" in toasts[-1])
open(HOME + "/bot.txt", "w").write(BOT + "listen = on\n")
m.friend.load(m.friend_files())

# the terminal: the microphone let go; media mode again: listening again
proc = m.ears.proc
m.active = False
m.listen_now()
check("in the terminal: not listening", m.ears.state == "off" and proc.poll() is not None)
m.listen_tick(time.monotonic() + 60)
check("...and it doesn't start by itself there", m.ears.state == "off")
m.active = True
m.listen_now()
check("back: listening", settle(lambda: m.ears.state == "waiting", 30))

# ---- Off ------------------------------------------------------------------------------------------------------------
m.friend_setup()
m.set_sel = keys().index("f_listen")
m.press("right")
check(f"right again: Off ({toasts[-1]!r})", m.bot_listen_mode() == "off" and settle(lambda: m.ears.state == "off", 5)
      and "listen = off" in bot_txt() and toasts[-1] == "It isn't listening now")
m.dirty = True; m.tick(); m.flush()
shots[-1].save(S + "/settings_off.png")
ticks(1)
check("...a microphone plugged in, and it stays off", m.ears.state == "off" and m.listen_note()[0] ==
      "It makes out what you say on the Pi")
out = m.web_mic_set(True)
check(f"...the web page's Mic here says so: {out}", out == {"ok": True, "listens": False,
      "why": "The bot isn't listening: turn on Settings › Bot › Listens"} and m.ears.state == "off")
m.web_mic_set(False)
m.go_home(); m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
check(f"...no Talk to it: {[o[0] for o in m.friend_options()]}", m.friend_options()[0][1] != "talk")
m.friend_setup()
m.set_sel = keys().index("f_listen")
m.press("right")
check("right once more: Auto again, and listening by itself", m.bot_listen_mode() == "auto" and "listen = auto" in bot_txt()
      and settle(lambda: m.ears.state == "waiting" and m.ears.want == ("hey potato", "Device"), 30))
out = m.web_settings_do({"cmd": "settings", "key": "f_listen", "value": "off"})
check(f"the web page: Off ({out})", out == {"ok": True} and m.bot_listen_mode() == "off"
      and settle(lambda: m.ears.state == "off", 5))
out = m.web_settings_do({"cmd": "settings", "key": "f_listen", "value": "loud"})
check(f"...not one of its choices: refused ({out})", "error" in out and m.bot_listen_mode() == "off")
m.ears.stop()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
