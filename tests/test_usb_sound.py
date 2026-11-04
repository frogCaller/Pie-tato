"""Sound outputs and USB speakers (pitato/screen.py, Settings > Sound, media mode) on a pretend Pi 4: its sound cards
(/proc/asound) and its screens (/sys/class/drm, each with its EDID). Settings > Sound lists what can play (not a USB
microphone), a USB speaker by that name; Auto: a USB speaker while one's plugged in, else HDMI, else (a monitor that
says it has no sound) the headphone jack; a game controller's speaker isn't taken for one; two speakers each named; a
choice saved under the card's own name still finds it; Settings > Sound's row says where Auto sends it; a song moves
to a USB speaker plugged in while it plays, and pauses when it's unplugged; the GPi Case's Auto as it was."""
import json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw

S = SP + "/t_usb_sound"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures"):
    os.makedirs(f"{HOME}/{d}")
os.makedirs(S + "/bin")
ASOUND, DRM = S + "/asound", S + "/drm"
g.ASOUND, g.DRM_DIR = ASOUND, DRM
g._bt_seen["here"] = False                         # (no Bluetooth headphones here)

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


# ---- the pretend Pi's sound cards and screens -----------------------------------------------------------------------
HDMI = [(0, "vc4hdmi0", "vc4-hdmi", "vc4-hdmi-0", "p"), (1, "vc4hdmi1", "vc4-hdmi", "vc4-hdmi-1", "p")]
JACK = (2, "Headphones", "bcm2835_headpho", "bcm2835 Headphones", "p")
MIC = (3, "Microphone", "USB-Audio", "USB Microphone", "c")
SPEAKER = (4, "UACDemoV10", "USB-Audio", "UACDemoV1.0", "pc")
JABRA = (5, "USB", "USB-Audio", "Jabra SPEAK 410 USB", "pc")
PAD = (6, "Controller", "USB-Audio", "DualSense Wireless Controller", "pc")
PAD4 = (6, "Controller", "USB-Audio", "Sony Computer Entertainment Wireless Controller", "pc")   # (a DualShock 4)


def cards(*cs):
    shutil.rmtree(ASOUND, ignore_errors=True)
    os.makedirs(ASOUND)
    lines = []
    for num, cid, driver, desc, pcms in cs:
        lines.append(f"{num:2d} [{cid:<15}]: {driver} - {desc}")
        lines.append(f"                      {desc} at somewhere")
        for kind in pcms:
            os.makedirs(f"{ASOUND}/card{num}/pcm0{kind}")
    open(ASOUND + "/cards", "w").write("\n".join(lines) + "\n")


def edid(*blocks):
    base = bytearray(128)
    base[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    base[126] = len(blocks)
    return bytes(base) + b"".join(blocks)


def cea(basic_audio=False, audio_block=False, hdmi=True):
    b = bytearray(128)
    b[0], b[1] = 0x02, 3
    data = b""
    if audio_block:
        data += bytes((0x20 | 3, 0x09, 0x07, 0x07))             # an audio block: 2-channel PCM
    if hdmi:
        data += bytes((0x60 | 5, 0x03, 0x0C, 0x00, 0x10, 0x00))  # HDMI's own block (IEEE 00-0C-03)
    b[2] = 4 + len(data)
    b[3] = 0x40 if basic_audio else 0
    b[4:4 + len(data)] = data
    return bytes(b)


TV = edid(cea(basic_audio=True))
MONITOR = edid(cea())                                  # HDMI, no speakers
DVI = edid()                                           # (a screen on a DVI adapter: no HDMI block at all)
AUDIO_BLOCK = edid(cea(audio_block=True))


def screen(data=None, connected=True):
    shutil.rmtree(DRM, ignore_errors=True)
    os.makedirs(DRM + "/card1-HDMI-A-1")
    os.makedirs(DRM + "/card1-HDMI-A-2")
    open(DRM + "/card1-HDMI-A-1/status", "w").write("connected\n" if connected else "disconnected\n")
    open(DRM + "/card1-HDMI-A-2/status", "w").write("disconnected\n")
    if data is not None:
        open(DRM + "/card1-HDMI-A-1/edid", "wb").write(data)


# ---- what Settings > Sound lists, and where Auto goes -------------------------------------------------------------------
cards(*HDMI, JACK, MIC, SPEAKER)
screen(MONITOR)
check(f"the outputs: HDMI, the jack and the USB speaker, not the microphone ({g.sound_cards()})",
      g.sound_cards() == [("vc4hdmi0", "HDMI 1"), ("vc4hdmi1", "HDMI 2"), ("Headphones", "Headphones"),
                          ("UACDemoV10", "USB speaker")])
check(f"Auto, a USB speaker plugged in: there ({g.sound_route('Auto')}); aplay's and mplayer's names for it",
      g.sound_route("Auto") == "UACDemoV10" and g.aplay_device("Auto") == "default:CARD=UACDemoV10"
      and g.sound_device("Auto") == "alsa:device=default=UACDemoV10,alsa" and g.sound_name("UACDemoV10") == "USB speaker")
check("...picked by its name, or by the card's own name a choice was saved under before",
      g.sound_route("USB speaker") == "UACDemoV10" and g.sound_route("UACDemoV1.0") == "UACDemoV10"
      and g.sound_route("HDMI 2") == "vc4hdmi1")
cards(*HDMI, JACK, MIC)
check(f"...unplugged, a monitor on HDMI that says it has no sound: the headphone jack ({g.sound_route('Auto')})",
      g.sound_route("Auto") == "Headphones")
for data, what, want in ((TV, "a TV with sound", "vc4hdmi0"), (AUDIO_BLOCK, "a TV listing its sound", "vc4hdmi0"),
                         (DVI, "a screen on a DVI adapter", "Headphones"), (None, "a screen that doesn't say", "vc4hdmi0"),
                         (b"\x00garbage", "an EDID that isn't one", "vc4hdmi0")):
    screen(data)
    check(f"...{what}: {want} ({g.sound_route('Auto')})", g.sound_route("Auto") == want)
cards(*HDMI, MIC)
screen(MONITOR)
check("...no headphone jack (a Pi 5): the system's own, as before", g.sound_route("Auto") == "")
screen(MONITOR, connected=False)
cards(JACK)
check("the GPi Case (no HDMI screen): the system's own, as before (its speaker)", g.sound_route("Auto") == ""
      and g.sound_cards() == [("Headphones", "Headphones")])

cards(*HDMI, JACK, PAD)
screen(TV)
check(f"a game controller with a speaker (a DualSense): listed by its own name, not where Auto sends it "
      f"({g.sound_cards()[-1]}, Auto: {g.sound_route('Auto')})",
      g.sound_cards()[-1] == ("Controller", "DualSense Wireless Contr") and g.sound_route("Auto") == "vc4hdmi0")
cards(*HDMI, JACK, PAD4)
check(f"...a DualShock 4, its name too long to show whole: not one either ({g.sound_route('Auto')})",
      g.sound_route("Auto") == "vc4hdmi0")
cards(*HDMI, JACK, SPEAKER, JABRA)
names = [n for _, n in g.sound_cards()]
check(f"two USB speakers: each by its own name ({names[-2:]}); Auto, the last", names[-2:] ==
      ["USB speaker: UACDemoV1.0", "USB speaker: Jabra SPEAK 410 USB"] and g.sound_route("Auto") == "USB")
twin = (7, "UACDemoV10_1", "USB-Audio", "UACDemoV1.0", "p")
cards(*HDMI, JACK, SPEAKER, twin)
check(f"...two of the same: numbered ({[n for _, n in g.sound_cards()][-2:]})",
      [n for _, n in g.sound_cards()][-2:] == ["USB speaker: UACDemoV1.0", "USB speaker: UACDemoV1.0 2"])

# ---- media mode: Settings > Sound's row, and a song moving -----------------------------------------------------------
MPLOG = S + "/mplayer.log"
open(S + "/bin/mplayer", "w").write('''#!/usr/bin/env python3
import json, os, sys
def log(**kw):
    with open(os.environ["MPLAYER_LOG"], "a") as f:
        f.write(json.dumps(dict(kw, pid=os.getpid())) + "\\n")
log(argv=sys.argv[1:])
paused = False
for line in sys.stdin:
    c = line.strip()
    log(cmd=c)
    if c == "quit":
        break
    words = c.split()
    if words == ["pause"]:
        paused = not paused
    elif words and words[0] == "pausing":
        paused = True
    elif words and words[0] != "pausing_keep_force":
        paused = False
    if words[-2:] == ["get_property", "pause"]:
        print("ANS_pause=" + ("yes" if paused else "no"), flush=True)
''')
open(S + "/bin/aplay", "w").write("#!/bin/sh\nexec cat > /dev/null\n")
for f in ("mplayer", "aplay"):
    os.chmod(f"{S}/bin/{f}", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["MPLAYER_LOG"] = MPLOG
for k in range(1, 3):
    open(f"{HOME}/Music/song {k}.mp3", "wb").write(b"ID3")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
g.probe_length = lambda path: 600.0


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB


def log():
    try:
        return [json.loads(x) for x in open(MPLOG).read().splitlines() if x.strip()]
    except OSError:
        return []


def starts():
    return [e for e in log() if "argv" in e]


def start_no(n):
    until(lambda: len(starts()) >= n, 5)
    st = starts()
    return st[n - 1] if len(st) >= n else {"argv": [], "pid": -1}


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def look():
    m.sound_look = 0.0
    m.sound_tick(time.monotonic())


cards(*HDMI, JACK, MIC)
screen(TV)
m = g.Media(); m.enter()
rows = {k: c for k, _, c in m.settings_root_rows()}
check(f"Settings > Sound's choices: no microphone ({rows['sound']})",
      rows["sound"] == ["Auto", "HDMI 1", "HDMI 2", "Headphones"])
check(f"...its row says where Auto sends it ({m.sound_value()})", m.sound_value() == "Auto: HDMI 1")
mi = next(k for k, t in enumerate(g.LIBRARY) if t["type"] == "files" and t.get("kind") == "audio")
m.load_tab(mi)
songs = m.tab_items(mi)
m.tab, m.view = mi, "list"
m.play(songs, 0)
first = start_no(1)
check(f"a song on the TV ({opt(first['argv'], '-ao')})", opt(first["argv"], "-ao") == "alsa:device=hdmi=vc4hdmi0.0.4.130.0.1,alsa"
      and m.sound_used == ("vc4hdmi0", ""))
m.pos = 100.0
cards(*HDMI, JACK, MIC, SPEAKER)
look()
moved = start_no(2)
check(f"a USB speaker plugged in while it plays: the song moves to it, from where it was "
      f"({opt(moved['argv'], '-ao')}, {opt(moved['argv'], '-ss')}), and says so ({m.msg})",
      opt(moved["argv"], "-ao") == "alsa:device=default=UACDemoV10,alsa" and opt(moved["argv"], "-ss") == "100"
      and m.msg == "Sound through USB speaker" and not m.paused and m.sound_used == ("UACDemoV10", ""))
check(f"...Settings > Sound's row says so ({m.sound_value()}), and lists it",
      m.sound_value() == "Auto: USB speaker" and "USB speaker" in {k: c for k, _, c in m.settings_root_rows()}["sound"])
m.pos = 150.0
cards(*HDMI, JACK, MIC)
look()
back = start_no(3)
check(f"...unplugged: back on the TV, paused, a moment before where it was, as with headphones "
      f"({opt(back['argv'], '-ao')}, {opt(back['argv'], '-ss')}, {m.msg})",
      opt(back["argv"], "-ao") == "alsa:device=hdmi=vc4hdmi0.0.4.130.0.1,alsa" and m.paused
      and m.msg == "Paused: USB speaker disconnected" and opt(back["argv"], "-ss") == "147")
screen(None, connected=False)
look()
time.sleep(0.4)
check("...the TV unplugged: it plays on as it was (only Bluetooth and USB speakers move it)", len(starts()) == 3)
m.stop()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
