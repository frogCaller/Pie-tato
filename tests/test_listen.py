"""The bot listening: the wake phrase as Vosk hears it, the microphones, hear.py with the real Vosk (x86_64) and
its small English model hearing spoken clips (espeak-ng) from a pretend arecord, Ears end to end (the wake
phrase, one breath, Talk to it, deaf while busy, patience, a microphone that stops), and getting Vosk and its
model (a local server: the real wheel, checked against its SHA-256; a zip made from the model)."""
import hashlib, http.server, io, json, os, shutil, subprocess, sys, threading, time, zipfile
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_listen"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
LT = SP + "/listen_t"
CLIPS = LT + "/clips"
MIC = S + "/mic"                                  # (clips dropped here are "said")
os.makedirs(MIC)
os.environ["PATH"] = LT + "/bin:" + os.environ["PATH"]
os.environ["FAKE_MIC_DIR"] = MIC
os.environ["FAKE_MIC_SPEED"] = "3"
os.environ["FAKE_MIC_LOG"] = S + "/mic.log"
sys.path.insert(0, ROOT)
import pitato.listen as L

LIB = SP + "/vosk_whl/x/manylinux_2_12_x86_64.manylinux2010_x86_64/vosk/libvosk.so"
MODEL = SP + "/vosk_model_npm/vosk-model-small-en-us-0.15"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def say(*names):
    for k, n in enumerate(names):
        shutil.copyfile(f"{CLIPS}/{n}.raw", f"{MIC}/.{k}.part")          # (whole, when the pretend arecord sees it)
        os.rename(f"{MIC}/.{k}.part", f"{MIC}/{time.time():.6f}-{k}.raw")


def until(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# ---- the wake phrase, as Vosk hears it ---------------------------------------------------------------------------
W = L.wake_words("hey potato")
heard = lambda t: L.wake_end([w for w, _ in L.tokens(t)], W)   # noqa: E731
check("hey potato", heard("hey potato") == 2 and heard("hey potato what time is it") == 2)
check("...heard as they potato, a potato, or just potato, as it's said first",
      heard("they potato") == 2 and heard("a potato tell me") == 2 and heard("potato") == 1)
check("...but not a potato in the middle of something", heard("can you pass me a potato please") is None
      and heard("she gave me a potato yesterday") is None)
check("...nor hey tomato", heard("hey tomato how are you") is None)
check("hi potatoes", heard("hi potatoes") == 2 and heard("well hey potato what") == 3)
check("a one-word phrase, anywhere", L.wake_end(["my", "computer", "is"], ["computer"]) == 2)
check("noise isn't something said", not L.meaningful("the") and not L.meaningful("uh the") and L.meaningful("what time"))
check("phrases tidied", L.tidy_phrase("  Hey, POTATO! ") == "hey potato" and L.tidy_phrase("hi") == ""
      and L.tidy_phrase("ok computer") == "ok computer" and len(L.tidy_phrase("word " * 30)) <= L.WAKE_MOST)

# ---- the microphones -------------------------------------------------------------------------------------------
A = S + "/asound"
os.makedirs(A + "/card0/pcm0p"); os.makedirs(A + "/card1/pcm0p"); os.makedirs(A + "/card1/pcm0c")
os.makedirs(A + "/card2/pcm0c"); os.makedirs(A + "/card3/pcm1c"); os.makedirs(A + "/card4/pcm0c"); os.makedirs(A + "/card4/pcm0p")
open(A + "/card1/usbid", "w").write("046d:082d\n")
open(A + "/card2/usbid", "w").write("0c76:161f\n")
open(A + "/cards", "w").write(
    " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
    " 1 [C920           ]: USB-Audio - HD Pro Webcam C920\n                      HD Pro Webcam C920 at usb-xhci-hcd\n"
    " 2 [Device         ]: USB-Audio - USB PnP Sound Device\n                      C-Media USB PnP Sound Device at usb\n"
    " 3 [Mic2           ]: USB-Audio - Samson Go Mic\n"
    " 4 [Head           ]: USB-Audio - Jabra EVOLVE 20\n")
V = S + "/v4l"
os.makedirs(S + "/usbdev/1-1/1-1:1.0"); os.makedirs(V + "/video0")
open(S + "/usbdev/1-1/idVendor", "w").write("046d\n"); open(S + "/usbdev/1-1/idProduct", "w").write("082d\n")
os.symlink(S + "/usbdev/1-1/1-1:1.0", V + "/video0/device")
L.ASOUND, L.V4L = A, V
got = L.mics()
check(f"microphones, a headset's next, the webcam's last: {[(c['id'], c['device'], c['camera'], c['plays']) for c in got]}",
      [c["id"] for c in got] == ["Device", "Mic2", "Head", "C920"] and got[0]["device"] == "plughw:CARD=Device,DEV=0"
      and got[2]["plays"] and not got[0]["plays"]
      and got[1]["device"] == "plughw:CARD=Mic2,DEV=1" and got[3]["camera"] and got[0]["name"] == "USB PnP Sound Device")
check(f"...which are USB: {[(c['id'], c['usb']) for c in got]}", [c["usb"] for c in got] == [True, False, False, True])
check("a microphone picked, not plugged in: the first there is, or (without fallback) none",
      L.mic_device("Gone") == "plughw:CARD=Device,DEV=0" and L.mic_device("Gone", fallback=False) == ""
      and L.mic_device("Mic2", fallback=False) == "plughw:CARD=Mic2,DEV=1"
      and L.mic_device("", fallback=False) == "plughw:CARD=Device,DEV=0")
PCA = S + "/asound_pc"                           # (a PC: its own sound card, and a USB headset)
for card in ("card0/pcm0p", "card0/pcm0c", "card1/pcm0p", "card1/pcm0c", "card2/pcm3p"):
    os.makedirs(f"{PCA}/{card}")
open(PCA + "/card1/usbid", "w").write("0b0e:0300\n")
open(PCA + "/cards", "w").write(
    " 0 [PCH            ]: HDA-Intel - HDA Intel PCH\n                      HDA Intel PCH at 0xf7f10000 irq 32\n"
    " 1 [Headset        ]: USB-Audio - Jabra EVOLVE 30 II\n                      GN Jabra EVOLVE 30 II at usb-0000:00:14.0\n"
    " 2 [NVidia         ]: HDA-Intel - HDA NVidia\n")
L.ASOUND = PCA
got = L.mics()
check(f"on a PC: a USB headset before its own sound card, HDMI's none ({[(c['id'], c['usb'], c['plays']) for c in got]})",
      [c["id"] for c in got] == ["Headset", "PCH"] and got[0]["usb"] and not got[1]["usb"]
      and L.mic_device() == "plughw:CARD=Headset,DEV=0")
L.ASOUND = A
check("the first, or the one you picked", L.mic_device() == "plughw:CARD=Device,DEV=0"
      and L.mic_device("C920") == "plughw:CARD=C920,DEV=0" and L.mic_device("gone") == "plughw:CARD=Device,DEV=0")
L.ASOUND = S + "/nothing"
check("none", L.mics() == [] and L.mic_device() == "")
L.ASOUND = A

# ---- hear.py, with the real Vosk ----------------------------------------------------------------------------------
proc = subprocess.Popen([sys.executable, "-I", L.HEAR, LIB, MODEL, "plughw:CARD=Device,DEV=0", "hey", "potato", "zzqx"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd="/")
lines = []


def reader(p, into):
    for line in p.stdout:
        into.append(json.loads(line))


threading.Thread(target=reader, args=(proc, lines), daemon=True).start()
check("hear.py: ready, and it doesn't know zzqx", until(lambda: lines and lines[0].get("ready"), 30)
      and lines[0]["unknown"] == ["zzqx"])
until(lambda: os.path.exists(S + "/mic.log"), 5)
check("...from the microphone it was given", "-D plughw:CARD=Device,DEV=0" in open(S + "/mic.log").read()
      and "-r 16000 -c 1" in open(S + "/mic.log").read())
say("onebreath2")
until(lambda: any(x.get("final") for x in lines))
time.sleep(1)
check(f"what it hears, as it's said and at its end: {[x for x in lines if 'final' in x]}",
      any(x.get("partial") for x in lines) and len([x for x in lines if x.get("final")]) == 1
      and [x["final"] for x in lines if x.get("final")][0].startswith("hey potato "))
proc.stdin.write(b"deaf\n"); proc.stdin.flush()
n = len(lines)
say("joke")
time.sleep(2.5)
check("deaf: it hears nothing", len(lines) == n)
proc.stdin.write(b"listen\n"); proc.stdin.flush()
say("joke")
ok = until(lambda: any("joke" in (x.get("final") or "") for x in lines[n:]))
check(f"listening again: {[x for x in lines[n:] if 'final' in x]}", ok)
proc.stdin.close()
check("Pietato gone: it goes too", proc.wait(5) == 0)

os.environ["FAKE_MIC_FAIL"] = "Device or resource busy"
proc = subprocess.Popen([sys.executable, "-I", L.HEAR, LIB, MODEL, "plughw:CARD=Device,DEV=0"], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, cwd="/")
msgs = [json.loads(x) for x in proc.stdout]
check(f"a microphone that won't open: {msgs[-1]}", proc.wait(10) == 1 and "busy" in msgs[-1].get("error", ""))
del os.environ["FAKE_MIC_FAIL"]
out = subprocess.run([sys.executable, "-I", L.HEAR, S + "/nolib.so", MODEL, ""], capture_output=True, timeout=30)
check(f"no Vosk: {out.stdout.decode().strip()}", out.returncode == 2 and "Vosk wouldn't load" in out.stdout.decode())
out = subprocess.run([sys.executable, "-I", L.HEAR, LIB, S + "/nomodel", ""], capture_output=True, timeout=30)
check(f"no model: {out.stdout.decode().strip()}", out.returncode == 2 and "model wouldn't load" in out.stdout.decode())

# ---- Ears, end to end ---------------------------------------------------------------------------------------------
LD = S + "/listen"
os.makedirs(LD)
shutil.copy(LIB, LD + "/libvosk.so")
os.symlink(MODEL, LD + "/" + L.MODEL)
L.LISTEN_DIR = LD
L.as_user = lambda: {}                           # (hear.py as you: here, that's who runs this)
check("Vosk is here", L.have_vosk())
L.PATIENCE = 3.0
ears = L.Ears()
said, busy, states = [], [False], []
ears.on_heard = said.append
ears.is_busy = lambda: busy[0]
ears.on_change = lambda: states.append(ears.state)
ears.start("hey potato")
check("listening for the wake phrase", until(lambda: ears.state == "waiting", 30) and states[0] == "starting")
say("wake")
check("the wake phrase: listening", until(lambda: ears.state == "listening"))
say("joke")
ok = until(lambda: said)
check(f"...and what comes after it, to the bot: {said}", ok and len(said) == 1 and "joke" in said[0].lower()
      and said[0][0].isupper())
check("...then waiting again", until(lambda: ears.state == "waiting", 3))
said.clear()
say("onebreath2")
ok = until(lambda: said)
check(f"in one breath: {said}", ok and len(said) == 1 and "potato" not in said[0].lower())
said.clear()
say("wake_they", "joke")
ok = until(lambda: said)
check(f"'they potato': {said}", ok and len(said) == 1 and "joke" in said[0].lower())
said.clear()
say("tomato", "ate4", "joke")
time.sleep(6)
check(f"hey tomato, a potato in passing, and talk: nothing to the bot ({said})", said == [] and ears.state == "waiting")
check("Talk to it", ears.wake_now() and until(lambda: ears.state == "listening", 3))
say("joke")
ok = until(lambda: said)
check(f"...what's said next, without the phrase: {said}", ok and len(said) == 1 and "joke" in said[0].lower())
said.clear()
say("wake")
check("the wake phrase, then nothing", until(lambda: ears.state == "listening"))
check("...it gives up after a while", until(lambda: ears.state == "waiting", L.PATIENCE + 4))
busy[0] = True
say("onebreath")
time.sleep(4)
check(f"deaf while the bot speaks: {said}", said == [])
busy[0] = False
time.sleep(L.QUIET_AFTER + 0.3)
say("onebreath")
ok = until(lambda: said)
check(f"...and listening once it's done: {said}", ok and len(said) == 1 and "potato" not in said[0].lower())
said.clear()

# the microphone stops (unplugged), and comes back (not counted as stopping soon after it started: below, that)
was_quick, L.QUICK_STOP = L.QUICK_STOP, 0.0
os.environ["FAKE_MIC_FAIL"] = "No such file or directory"
ears.proc.kill()
ok = until(lambda: ears.state == "error", 10)
check(f"it stopped: {ears.error!r}", ok and ears.error.startswith("It stopped listening"))
ok = until(lambda: "No such file" in ears.error, L.RETRY + 15)
check(f"...the microphone won't open: {ears.error!r}", ok and ears.state == "error")
del os.environ["FAKE_MIC_FAIL"]
check("...and starts again by itself", until(lambda: ears.state == "waiting", L.RETRY + 20))
L.ASOUND = S + "/nothing"
ears.proc.kill()
ok = until(lambda: ears.error == "No microphone: plug one in", L.RETRY + 10)
check(f"no microphone: {ears.error!r}", ok)
L.ASOUND = A
check("...plugged in: listening", until(lambda: ears.state == "waiting", L.RETRY + 20))
L.QUICK_STOP = was_quick

# a new phrase, words it doesn't know
ears.start("hey zzqx")
ok = until(lambda: ears.state == "waiting" and ears.unknown == ["zzqx"], 30)
check(f"a word it doesn't know: {ears.unknown}", ok)
ears.start("hey potato", "C920")
ok = until(lambda: ears.state == "waiting" and open(S + "/mic.log").read().strip().splitlines()[-1].endswith(
    "plughw:CARD=C920,DEV=0"), 30)
check(f"another microphone: {open(S + '/mic.log').read().strip().splitlines()[-1]}", ok and ears.unknown == [])
ears.start("hey potato", "C920", fallback=False)
check("...the same, to be only that one: started afresh", until(lambda: ears.state == "waiting" and ears.fallback is False, 30))
old = ears.proc
ears.stop()
check("off: hear.py stops", ears.state == "off" and old.poll() is not None and ears.proc is None)
ears.stop()
only = L.Ears()
only.start("hey potato", "Gone", fallback=False)
ok = until(lambda: only.error == "No microphone: plug one in", 10)
check(f"only that microphone, and it isn't plugged in: no other in its place ({only.error!r})", ok and only.proc is None)
only.stop()

# stopping just after it starts, again and again (another program has the microphone): it waits twice as long each
# time, up to a limit (its model takes a Pi Zero a while to load)
naps = []
again = L.Ears()
real_nap = again.nap
again.nap = lambda gen, secs: (naps.append(secs), real_nap(gen, 0.05))
was_most, L.RETRY_MOST = L.RETRY_MOST, L.RETRY * 5
os.environ["FAKE_MIC_FAIL"] = "Device or resource busy"
again.start("hey potato")
ok = until(lambda: len(naps) >= 4, 90)
again.stop()
del os.environ["FAKE_MIC_FAIL"]
L.RETRY_MOST = was_most
check(f"the microphone busy, again and again: it waits longer each time, up to a limit ({naps[:4]})",
      ok and naps[:4] == [L.RETRY * 2, L.RETRY * 4, L.RETRY * 5, L.RETRY * 5])
naps.clear()
os.environ["FAKE_MIC_FAIL"] = "Device or resource busy"
again.start("hey potato")
ok = until(lambda: len(naps) >= 2, 60)
L.ASOUND = S + "/nothing"                        # (then taken out: not busy, gone)
ok = ok and until(lambda: again.error == "No microphone: plug one in", 30)
del os.environ["FAKE_MIC_FAIL"]
L.ASOUND = A
ok = ok and until(lambda: again.state == "waiting", 30)
mark = len(naps)
proc = again.proc
if proc:
    proc.kill()                                  # (and it stops soon after it started: counted afresh, from one)
ok = ok and until(lambda: len(naps) > mark, 30)
after = naps[mark] if len(naps) > mark else None
again.stop()
check(f"...taken out and put back: it counts afresh ({naps[:2]}, then {sorted(set(naps[2:mark]))}, then {after})",
      ok and naps[:2] == [L.RETRY * 2, L.RETRY * 4] and L.RETRY in naps[2:mark] and after == L.RETRY * 2)

# music playing on and on: what it makes out after the wake phrase never ends, so after a while what it made out is it
FAKE = S + "/fake_hear.py"
open(FAKE, "w").write("""import json, sys, time
print(json.dumps({"ready": True, "unknown": []}), flush=True)
for k in range(300):
    print(json.dumps({"partial": "shut down the pi" if k > 3 else "shut down"}), flush=True)
    time.sleep(0.1)
""")
was_most, L.LISTEN_MOST = L.LISTEN_MOST, 2.0
music, heard_m = L.Ears(), []
music.on_heard = heard_m.append
music.gen, music.state, music.poked = 7, "waiting", True       # (Talk to it: what's said next goes to the bot)
fake = subprocess.Popen([sys.executable, "-I", FAKE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
threading.Thread(target=music.listen, args=(7, fake, L.wake_words("hey potato")), daemon=True).start()
t0 = time.time()
ok = until(lambda: heard_m, 8)
check(f"music on and on, never an end to what it hears: what it made out goes to the bot after a while "
      f"({heard_m}, {time.time() - t0:.1f} s)", ok and heard_m == ["Shut down the pi"] and 1.5 < time.time() - t0 < 4)
check("...then it waits for the wake phrase again", until(lambda: music.state == "waiting", 3))
music.gen += 1
fake.kill()
L.LISTEN_MOST = was_most

# ---- getting Vosk and its model -------------------------------------------------------------------------------------
WEB = S + "/web"
os.makedirs(WEB)
shutil.copy(SP + "/vosk_whl/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl", WEB + "/vosk.whl")
with zipfile.ZipFile(WEB + "/model.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(MODEL):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, L.MODEL + "/" + os.path.relpath(full, MODEL))
with zipfile.ZipFile(WEB + "/evil.zip", "w") as z:
    z.writestr(L.MODEL + "/am/final.mdl", b"x"); z.writestr(L.MODEL + "/conf/model.conf", b"x")
    z.writestr(L.MODEL + "/../../escaped.txt", b"x")
with zipfile.ZipFile(WEB + "/notamodel.zip", "w") as z:
    z.writestr(L.MODEL + "/README", b"x")
open(WEB + "/tampered.whl", "wb").write(open(WEB + "/vosk.whl", "rb").read() + b"x")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 5677), Quiet)
threading.Thread(target=srv.serve_forever, daemon=True).start()
sha = L.VOSK_WHEELS["x86_64"][1]
L.VOSK_WHEELS["x86_64"] = ("http://127.0.0.1:5677/vosk.whl", sha)
L.MODEL_URL = "http://127.0.0.1:5677/model.zip"
LD2 = S + "/listen2"
L.LISTEN_DIR = LD2
check("not here yet", not L.have_vosk() and L.supported())
ready, seen = [], []
ears = L.Ears()
ears.on_ready = lambda: ready.append(1)
ears.on_change = lambda: seen.append(ears.status())
check("getting it", ears.get() and not ears.get())
check(f"...how far along: {sorted(set(seen))[:3]}...", until(lambda: ready, 60) and any("Getting Vosk" in x for x in seen)
      and any("Getting its model" in x for x in seen))
check("...here", L.have_vosk() and ears.job is None and ears.status() == "")
mode = lambda p: oct(os.stat(p).st_mode & 0o777)   # noqa: E731
check(f"...readable by you: {mode(LD2 + '/libvosk.so')} {mode(L.model_dir())} {mode(L.model_dir() + '/am/final.mdl')}",
      mode(LD2 + "/libvosk.so") == "0o644" and mode(L.model_dir()) == "0o755" and mode(L.model_dir() + "/am/final.mdl") == "0o644")
check("...the library, as it is in the wheel", hashlib.sha256(open(LD2 + "/libvosk.so", "rb").read()).hexdigest()
      == hashlib.sha256(open(LIB, "rb").read()).hexdigest())
check("...nothing left behind", sorted(os.listdir(LD2)) == sorted(["libvosk.so", L.MODEL]))


def fresh(url_whl=None, url_model=None):
    shutil.rmtree(LD2, ignore_errors=True)
    if url_whl:
        L.VOSK_WHEELS["x86_64"] = (url_whl, sha)
    if url_model:
        L.MODEL_URL = url_model
    e = L.Ears()
    e.get()
    until(lambda: e.job is None, 60)
    return e


e = fresh("http://127.0.0.1:5677/tampered.whl")
check(f"a wheel that doesn't check out: {e.got_error!r}", "didn't check out" in e.got_error and not os.path.exists(LD2 + "/libvosk.so")
      and not [f for f in os.listdir(LD2) if f.startswith(".")])
e = fresh("http://127.0.0.1:5677/vosk.whl", "http://127.0.0.1:5677/evil.zip")
check(f"a model zip reaching out of its folder: {e.got_error!r}", "didn't check out" in e.got_error
      and not os.path.exists(S + "/escaped.txt") and not L.model_here() and not [f for f in os.listdir(LD2) if f.startswith(".")])
e = fresh(url_model="http://127.0.0.1:5677/notamodel.zip")
check(f"not a model: {e.got_error!r}", "isn't a speech model" in e.got_error and not L.model_here())
e = fresh(url_model="http://127.0.0.1:5677/gone.zip")
check(f"nothing there: {e.got_error!r}", e.got_error.startswith("Couldn't get its model") and os.path.isfile(LD2 + "/libvosk.so"))
L.MODEL_URL = "http://127.0.0.1:5677/model.zip"
L.MODEL_MAX = 1000
e = fresh()
check(f"too big: {e.got_error!r}", "bigger than it should be" in e.got_error)
srv.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
