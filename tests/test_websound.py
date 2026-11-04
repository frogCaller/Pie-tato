"""Sound here and Mic here, on the Pi's side: with a web page listening (webui.py says so every few seconds), the Pi's
sound goes to it through the Loopback card (pietato_web, mixed): mplayer's, aplay's, a game's, the bot's voice; what's
playing moves there and back as it does to Bluetooth headphones; it goes back by itself when webui.py stops saying so.
The Loopback card is never a speaker in Settings > Sound, nor a microphone in Settings > Bot. With a page's microphone
coming in, the bot listens to it instead of the Pi's, and to the Pi's again after it."""
import json, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import screen as SC, listen as LI

S = SP + "/t_websound"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.home_dir = lambda: S + "/home/u"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# the kernel's sound cards: the Pi's headphone jack, HDMI, a USB microphone, and the Loopback card
AS = S + "/asound"
for num, pcms in ((0, ["pcm0p"]), (1, ["pcm0p"]), (2, ["pcm0c"]), (10, ["pcm0p", "pcm0c", "pcm1p", "pcm1c"])):
    os.makedirs(f"{AS}/card{num}")
    for p in pcms:
        os.makedirs(f"{AS}/card{num}/{p}")
open(f"{AS}/cards", "w").write(
    " 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones\n                      bcm2835 Headphones\n"
    " 1 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
    " 2 [Mic            ]: USB-Audio - USB PnP Sound Device\n                      USB PnP Sound Device\n"
    "10 [Loopback       ]: Loopback - Loopback\n                      Loopback 1\n")
for mod in (SC, LI):
    mod.ASOUND = AS
cards = [c for c, _ in SC.sound_cards()]
check(f"Settings > Sound: the Loopback card isn't a speaker ({cards})", "Loopback" not in cards and "Headphones" in cards)
mics = [c["id"] for c in LI.mics()]
check(f"Settings > Bot: nor a microphone ({mics})", mics == ["Mic"])

g.bt_outputs = SC.bt_outputs = lambda fresh=False: []
check("Sound here off: sound goes where Settings says", SC.sound_route("Auto") != "web")
SC.WEB_SOUND["until"] = time.monotonic() + 15
check("Sound here on: the web page's way, whatever Settings says", SC.sound_route("Auto") == "web"
      and SC.sound_route("HDMI") == "web")
check(f"...mplayer's ({SC.sound_device('Auto')}) and aplay's ({SC.aplay_device('Auto')})",
      SC.sound_device("Auto") == "alsa:device=pietato_web,alsa" and SC.aplay_device("Auto") == "pietato_web")
check("...a way sound moves to and from while something plays", SC.sound_moves("web")
      and SC.sound_name("web") == "the web page")
SC.WEB_SOUND["until"] = 0.0


class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


import subprocess, types
import pitato.screens.player as PL
spawned, toasts = [], []


class FakePopen:
    def __init__(self, args, **kw):
        spawned.append(args)
        self.stdin, self.stdout, self.stderr, self.returncode = open(os.devnull, "w"), iter(()), iter(()), None

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


PL.subprocess = types.SimpleNamespace(Popen=FakePopen, PIPE=-1, TimeoutExpired=subprocess.TimeoutExpired)
m = g.Media()
m.voice.stop = lambda unload=False: None
m.toast = lambda text, secs=4: toasts.append(text)
m.cmd = lambda c: None
m.active = True
song = g.item(S + "/home/u/a.mp3", "a.mp3", "audio", S + "/home/u/a.mp3")
m.play([song], 0)
check("a song plays through the Pi", spawned and "alsa:device=pietato_web,alsa" not in spawned[-1])
out = m.web_command({"cmd": "websound", "on": True})
check(f"webui.py: a page listens ({out})", out == {"ok": True} and SC.web_sound())
m.pos = 40.0
m.sound_tick(time.monotonic())
check(f"...the song moves to it, playing on ({spawned[-1][spawned[-1].index('-ao') + 1]}, {toasts[-1:]})",
      len(spawned) == 2 and "alsa:device=pietato_web,alsa" in spawned[-1] and "Sound through the web page" in toasts
      and not m.paused)
m.web_command({"cmd": "websound", "on": False})
m.sound_tick(time.monotonic())
check(f"...the page stops: back to the Pi, playing on, not paused ({toasts[-1:]})", len(spawned) == 3
      and "alsa:device=pietato_web,alsa" not in spawned[-1] and not m.start_paused and not m.paused)
m.web_command({"cmd": "websound", "on": True})
check("...again", SC.web_sound())
SC.WEB_SOUND["until"] = time.monotonic() - 1          # (webui.py stopped saying so)
m.sound_look = 0.0
m.sound_tick(time.monotonic())
check("webui.py gone quiet: it goes back by itself", not SC.web_sound() and "alsa:device=pietato_web,alsa" not in spawned[-1])
m.stop()

# the bot's ears
starts = []
m.ears.start = lambda wake, mic="", fallback=True: (starts.append(mic), setattr(m.ears, "want", (wake, mic)))
m.ears.stop = lambda: (starts.append(None), setattr(m.ears, "want", None))
m.friend.conf["listen"] = "on"                       # (Listens: On)
g.have_vosk = lambda: True
import pitato.screens.bot as B
import pitato.screens.web as WB
B.have_vosk = WB.have_vosk = lambda: True
m.friend.conf["mic"] = "Mic"
check("the bot's microphone: Settings > Bot's", m.bot_mic() == "Mic" and m.bot_mic_set() == "Mic")
out = m.web_command({"cmd": "webmic", "on": True})
check(f"webui.py: a page's microphone ({out}, {starts})", out == {"ok": True, "listens": True}
      and starts[-1] == LI.WEB_MIC and m.bot_mic() == LI.WEB_MIC and m.bot_mic_set() == "Mic")
check(f"...through the Loopback card ({LI.mic_device(LI.WEB_MIC)})",
      LI.mic_device(LI.WEB_MIC) == "plughw:CARD=Loopback,DEV=1,SUBDEV=1")
check(f"...said on the screen ({toasts[-1:]})", toasts[-1] == "The bot hears you through the web page")
n = len(starts)
m.web_command({"cmd": "webmic", "on": True})
check("...said again (every few seconds): nothing starts again", len(starts) == n)
m.web_mic_until = time.monotonic() - 1                # (it stopped coming)
m.tick()
check(f"...gone: the Pi's own again ({starts[-1]})", starts[-1] == "Mic" and m.bot_mic() == "Mic")
check("Settings > Bot shows the web page's while it's on", True)
m.web_mic_until = time.monotonic() + 10
check(f"...({m.friend_value('f_mic')})", m.friend_value("f_mic") == "The web page's")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
