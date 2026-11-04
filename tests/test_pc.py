"""Pietato on a PC (Intel or AMD, Ubuntu), against a pretend PC (its firmware's description, its sound cards, its
screens, GRUB): it knows it's a PC, and a Pi isn't one; its name (its maker and model, or its board's); its sound
outputs (a desktop's speakers, HDMI on the same card and on the graphics card's, a USB speaker; never the Loopback card
or a controller's) and Auto's pick among them (HDMI with a TV plugged in that plays sound, else the speakers; a USB
speaker first), played straight to the card (sysdefault, or the HDMI port's own device: never ALSA's default,
PipeWire's on a desktop); Settings > Resolution through GRUB (put in by update-grub; as it was if that fails),
DisplayPort and laptop screens too, and through media mode (a moment's wait, then it restarts); System's numbers (its
maker and model, no Pi power light, a Desktop row with a desktop to start) and its dashboard (This PC, its disk);
System > Desktop (A twice: Pietato stops, the desktop starts, by a job of its own); "the PC" said instead of "the Pi",
in media mode and on the web page (its page, a game's page, the server's errors; never a Pi-hole or a Pi 4); its
videos played as they are (never made smaller), at full quality, and 1080p from Plex, Jellyfin and live TV on a 1080p
screen; every kind of game; the home screen's icons drawn on Ubuntu 24.04's Pillow (10.2: its rounded boxes in whole
pixels, which it needs). And a Pi, as it was."""
import json, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import screen as SC, system as SY

S = SP + "/t_pc"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
real_run = g.subprocess.run       # (this machine's own consoles left as they are: no switching to media mode's)
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd[:1] in (["chvt"], ["fgconsole"])
                                         else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def put(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# ---- a Pi isn't a PC; this one is ----
check("no firmware description, no Pi model (a Pi, as far as it knows): not a PC", not SY.is_pc())
DMI = S + "/dmi"
for k, v in (("sys_vendor", "Dell Inc."), ("product_name", "OptiPlex 7050"), ("board_vendor", "Dell Inc."),
             ("board_name", "0NW6H5")):
    put(f"{DMI}/{k}", v + "\n")
SY.DMI = DMI
check("its firmware's description: a PC", SY.is_pc())
put(S + "/model", "Raspberry Pi 4 Model B Rev 1.4\x00")
SY.PI_MODEL = S + "/model"
check("...but never a Pi, whatever else it has", not SY.is_pc())
SY.PI_MODEL = S + "/nomodel"
check(f"the PC's name: {SY.pc_name()!r}", SY.pc_name() == "Dell Inc. OptiPlex 7050")
for k, v in (("sys_vendor", "HP"), ("product_name", "HP EliteDesk 800 G4 SFF")):
    put(f"{DMI}/{k}", v + "\n")
check(f"...a model that says its maker already: once ({SY.pc_name()!r})", SY.pc_name() == "HP EliteDesk 800 G4 SFF")
for k, v in (("sys_vendor", "To Be Filled By O.E.M."), ("product_name", "To Be Filled By O.E.M."),
             ("board_vendor", "ASUSTeK COMPUTER INC."), ("board_name", "PRIME B450M-A")):
    put(f"{DMI}/{k}", v + "\n")
check(f"...one you built (its firmware says nothing much of it): its board's ({SY.pc_name()!r})",
      SY.pc_name() == "ASUSTeK COMPUTER INC. PRIME B450M-A")
for k, v in (("sys_vendor", "Dell Inc."), ("product_name", "OptiPlex 7050"), ("board_vendor", "Dell Inc."),
             ("board_name", "0NW6H5")):
    put(f"{DMI}/{k}", v + "\n")

# ---- its sound: the kernel's cards, their devices, the HDMI jacks and what the screens say they play ----
AS = S + "/asound"
CARDS = [(0, "PCH", "HDA-Intel", "HDA Intel PCH", {0: "ALC892 Analog", 1: "ALC892 Digital", 3: "HDMI 0", 7: "HDMI 1"}),
         (1, "Generic", "HDA-Intel", "HD-Audio Generic", {3: "HDMI 0"}),
         (2, "Speaker", "USB-Audio", "Jabra SPEAK 510 USB", {0: "USB Audio"}),
         (3, "Controller", "USB-Audio", "Sony DualSense Wireless Controller", {0: "USB Audio"}),
         (7, "Loopback", "Loopback", "Loopback", {0: "Loopback PCM", 1: "Loopback PCM"})]


def make_cards(which):
    shutil.rmtree(AS, ignore_errors=True)
    lines = []
    for num, cid, driver, name, pcms in CARDS:
        if num not in which:
            continue
        lines.append(f"{num:2d} [{cid:<15}]: {driver} - {name}\n                      {name}")
        for dev, pname in pcms.items():
            put(f"{AS}/card{num}/pcm{dev}p/info", f"card: {num}\ndevice: {dev}\nid: {pname}\nname: {pname}\n")
        os.symlink(f"card{num}", f"{AS}/{cid}")
    put(f"{AS}/cards", "\n".join(lines) + "\n")
    SC._jacks.clear()


def eld(num, present, sads):
    put(f"{AS}/card{num}/eld#2.0", f"monitor_present\t\t{present}\neld_valid\t\t{present}\nmonitor_name\t\tTV\n"
                                   f"sad_count\t\t{sads}\n")


BIN = S + "/bin"
put(BIN + "/amixer", f'''#!/bin/bash
# stand-in for amixer -c CARD contents: the HDMI jacks, on as {S}/jack.CARD says ("3 7": those devices plugged in)
card="$2"
on=" $(cat "{S}/jack.$card" 2>/dev/null) "
for d in 3 7 8; do
  v=off; case "$on" in *" $d "*) v=on ;; esac
  echo "numid=1$d,iface=CARD,name='HDMI/DP,pcm=$d Jack'"
  echo "  ; type=BOOLEAN,access=r-------,values=1"
  echo "  : values=$v"
done
echo "numid=40,iface=MIXER,name='Master Playback Volume'"
echo "  : values=64"
''')
os.chmod(BIN + "/amixer", 0o755)
os.environ["PATH"] = BIN + ":" + os.environ["PATH"]
SC.ASOUND = AS
make_cards({0, 1, 3, 7})
outs = SC.sound_list()
check(f"its outputs: the speakers and HDMI on the board's card, the graphics card's HDMI; not a controller's, not "
      f"the Loopback card ({[(o['id'], o['name']) for o in outs]})",
      [(o["id"], o["name"]) for o in outs] == [("PCH", "Speakers"), ("PCH/hdmi", "HDMI: HDA Intel PCH"),
                                               ("Generic/hdmi", "HDMI: HD-Audio Generic")])
check("Settings > Sound's choices", [n for _, n in SC.sound_cards()] == ["Speakers", "HDMI: HDA Intel PCH",
                                                                         "HDMI: HD-Audio Generic"])
check(f"Auto, nothing on HDMI: the speakers ({SC.sound_route('Auto')})", SC.sound_route("Auto") == "PCH")
check(f"...straight to the card, not ALSA's default ({SC.sound_device('Auto')}, {SC.aplay_device('Auto')})",
      SC.sound_device("Auto") == "alsa:device=sysdefault=PCH,alsa" and SC.aplay_device("Auto") == "sysdefault:CARD=PCH")
put(S + "/jack.Generic", "3")
eld(1, 1, 2)
SC._jacks.clear()
check(f"a TV on the graphics card's HDMI, that plays sound: there ({SC.sound_route('Auto')})",
      SC.sound_route("Auto") == "Generic/hdmi")
check(f"...through its HDMI device ({SC.sound_device('Auto')}, {SC.aplay_device('Auto')})",
      SC.sound_device("Auto") == "alsa:device=plughw=Generic.3,alsa"
      and SC.aplay_device("Auto") == "plughw:CARD=Generic,DEV=3")
check(f"...its name, as Settings > Sound has it ({SC.sound_name('Generic/hdmi')})",
      SC.sound_name("Generic/hdmi") == "HDMI: HD-Audio Generic")
eld(1, 1, 0)
SC._jacks.clear()
check(f"a monitor without speakers there instead: the speakers again ({SC.sound_route('Auto')})",
      SC.sound_route("Auto") == "PCH")
os.remove(S + "/jack.Generic")
put(S + "/jack.PCH", "7")
eld(0, 1, 2)
SC._jacks.clear()
check(f"a TV on the board's own HDMI, the second port: that one ({SC.sound_route('Auto')}, "
      f"{SC.aplay_device('Auto')})", SC.sound_route("Auto") == "PCH/hdmi"
      and SC.aplay_device("Auto") == "plughw:CARD=PCH,DEV=7")
make_cards({0, 1, 2, 3, 7})
put(S + "/jack.PCH", "7")
eld(0, 1, 2)
check(f"a USB speaker plugged in: it, first ({SC.sound_route('Auto')}, {SC.sound_device('Auto')})",
      SC.sound_route("Auto") == "Speaker" and SC.sound_device("Auto") == "alsa:device=sysdefault=Speaker,alsa")
check("Settings > Sound picks one by its name", SC.sound_route("Speakers") == "PCH"
      and SC.sound_route("HDMI: HD-Audio Generic") == "Generic/hdmi")
check("...a USB speaker moves the sound, as on a Pi", SC.sound_moves("Speaker") and not SC.sound_moves("PCH"))
check(f"no sound at all: says so as a PC ({SC.sound_name('')})", SC.sound_name("") == "the PC")

# ---- Settings > Resolution: GRUB's ----
DRM = S + "/drm"
for port, status, modes in (("card1-HDMI-A-1", "connected", "1920x1080\n1280x720\n1920x1080i\n"),
                            ("card1-eDP-1", "disconnected", ""), ("card1-DP-2", "connected", "2560x1440\n1920x1080\n"),
                            ("card1-Writeback-1", "unknown", "")):
    put(f"{DRM}/{port}/status", status + "\n")
    put(f"{DRM}/{port}/modes", modes)
SC.DRM_DIR = DRM
SC.GRUB = S + "/grub"
put(SC.GRUB, '# If you change this file, run update-grub\nGRUB_DEFAULT=0\nGRUB_TIMEOUT=0\n'
             'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\nGRUB_CMDLINE_LINUX=""\n')
put(BIN + "/update-grub", f'#!/bin/bash\necho "update-grub $*" >> {S}/grub.log\n'
                          f'if [ -f {S}/grub.fail ]; then echo "error: /boot is full" >&2; exit 1; fi\n')
os.chmod(BIN + "/update-grub", 0o755)
check(f"its screens: HDMI and DisplayPort too ({SC.hdmi_screens()})",
      SC.hdmi_screens() == [("DP-2", ["2560x1440", "1920x1080"]), ("HDMI-A-1", ["1920x1080", "1280x720"])])
ch = SC.resolution_choices()
check(f"Settings > Resolution's sizes ({ch})", ch == ("2560x1440", ["1920x1080"]))
check("at start-up: the screen's own (Auto)", SC.boot_resolution() is None)
was = SC.set_boot_video(["DP-2"], ["video=DP-2:1920x1080@60"])
grub = open(SC.GRUB).read()
check(f"a size picked: GRUB's line has it, the rest as it was, and update-grub puts it in ({was})",
      'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash video=DP-2:1920x1080@60"\n' in grub and "GRUB_TIMEOUT=0" in grub
      and open(S + "/grub.log").read() == "update-grub \n" and was == [])
check(f"...and that's the size it starts at now ({SC.boot_resolution()})", SC.boot_resolution() == "1920x1080")
was = SC.set_boot_video(["DP-2"], [])
check(f"Auto again: gone from it ({was})", 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n' in open(SC.GRUB).read()
      and was == ["video=DP-2:1920x1080@60"] and SC.boot_resolution() is None)
put(S + "/grub.fail")
before = open(SC.GRUB).read()
try:
    SC.set_boot_video(["DP-2"], ["video=DP-2:1280x720@60"])
    why = None
except OSError as ex:
    why = str(ex)
check(f"update-grub failing: GRUB's settings as they were, and it says why ({why})",
      why == "error: /boot is full" and open(SC.GRUB).read() == before)
os.remove(S + "/grub.fail")
os.rename(BIN + "/update-grub", S + "/update-grub")
check("no update-grub (not GRUB): no Resolution to pick", SC.resolution_choices() is None)
os.rename(S + "/update-grub", BIN + "/update-grub")

# ---- System, and media mode on a PC ----
n = SY.system_numbers()


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    count = 0

    def __init__(self):
        self.frames, self.last = FB.count, None

    def show(self, img):
        self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.show(img)

    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
check(f"System's numbers: its maker and model as the board, no Pi power light ({n['board']}, {n['power']})",
      n["board"] == "Dell Inc. OptiPlex 7050" and n["power"] is None)
SY.DESKTOP = S + "/display-manager.service"
labels = [r["title"] for r in SY.system_info(nums=n)]
check(f"System's list: no Power row, and no Desktop row without a desktop ({labels[-4:]})",
      "Power" not in labels and "Desktop" not in labels and "Shut down" in labels)
put(SY.DESKTOP, "[Unit]\n")
labels = [r["title"] for r in SY.system_info(nums=n)]
check(f"...a desktop to start: a Desktop row, before Reboot ({labels[-4:]})",
      labels[-4:] == ["Restart media mode", "Desktop", "Reboot", "Shut down"])
import pitato.media as MM
started = []
real_popen = MM.subprocess.Popen
MM.subprocess.Popen = lambda cmd, *a, **k: started.append(cmd) if cmd[:1] == ["systemd-run"] \
    else real_popen(cmd, *a, **k)
it = next(r for r in SY.system_info(nums=n) if r["title"] == "Desktop")
m.system_action(it)
check(f"System > Desktop, A: it asks first, and says how to come back ({m.msg!r})", not started
      and m.msg == "Press A again for the desktop. Restarting the computer comes back to Pietato")
m.system_action(it)
check(f"...A again: Pietato stops and the desktop starts, by a job of its own ({started})",
      started == [["systemd-run", "--no-block", "--collect", "--unit=pietato-desktop", "sh", "-c",
                   "systemctl stop pitato; systemctl start display-manager"]])
MM.subprocess.Popen = real_popen

# ---- Settings > Resolution on a PC: a moment's wait while GRUB takes it, then the PC restarts at that size ----
open(S + "/grub.log", "w").close()
waits, boots = [], []
real_wait = m.render_wait
m.render_wait = lambda title, status, *a, **k: (waits.append((title, status)), real_wait(title, status, *a, **k))[1]
MM.subprocess.Popen = lambda cmd, *a, **k: boots.append(cmd) if cmd[:1] == ["systemctl"] \
    else real_popen(cmd, *a, **k)
m.halting = 0.0
m.set_page = "resolution"
m.press_resolution("a", False, "res", "1920x1080")
asked = (list(waits), list(boots), open(S + "/grub.log").read())
m.press_resolution("a", False, "res", "1920x1080")
grub = open(SC.GRUB).read()
check(f"Settings > Resolution, 1920x1080, A: it asks first ({asked})", asked == ([], [], ""))
check(f"...A again: a moment's wait while GRUB takes it, then it restarts ({waits}, {boots})",
      waits[:1] == [("Changing the resolution", "One moment")] and waits[-1][0] == "Restarting"
      and boots == [["systemctl", "reboot"]] and open(S + "/grub.log").read() == "update-grub \n")
check(f"...at that size, on each screen that takes it ({SC.boot_resolution()})",
      'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash video=DP-2:1920x1080@60 video=HDMI-A-1:1920x1080@60"\n' in grub
      and SC.boot_resolution() == "1920x1080" and m.setting("resolution_try")["to"] == "1920x1080")
del m.render_wait
MM.subprocess.Popen = real_popen
m.set_setting("resolution_try", None)
m.halting = 0.0
m.toast("The Pi didn't restart")
check(f"the PC, not the Pi, in what it says ({m.msg!r})", m.msg == "The PC didn't restart")
m.toast("Your Pi-hole's added")
check("...never a Pi-hole", m.msg == "Your Pi-hole's added")
from pitato.bluetooth import bt_why
check(f"...Bluetooth's words too ({bt_why('org.bluez.Error.Blocked: rfkill')!r})",
      bt_why("org.bluez.Error.Blocked: rfkill") == "Bluetooth is switched off on this PC"
      and bt_why("br-connection-profile-unavailable") == "The PC has nothing it can connect it to")
check("its videos played as they are: none made smaller", not m.shrinker.enabled())
real_size = SC.screen_size
SC.screen_size = lambda: (1920, 1080)
check(f"...Plex, Jellyfin and live TV at 1080p on a 1080p screen ({SC.video_target()})",
      SC.video_target() == ("1920x1080", 10000, 1080))
SC.screen_size = lambda: (1280, 720)
check(f"...720p on a 720p one, as a Pi 4's ({SC.video_target()})", SC.video_target() == ("1280x720", 4000, 720))
SC.screen_size = real_size
va = m.video_args()
check(f"...and at full quality: H.264's smoothing kept, scaled bicubic "
      f"({va[va.index('-lavdopts') + 1]}, -sws {va[va.index('-sws') + 1]})",
      va[va.index("-lavdopts") + 1] == "threads=4" and va[va.index("-sws") + 1] == "2" and va.count("-sws") == 1
      and va[:5] == ["mplayer", "-slave", "-quiet", "-vo", "fbdev2"])
from pitato.games import playable
check("every kind of game, N64, PSP, DS and Dreamcast too", all(playable(k) for k in ("n64", "psp", "nds", "dc")))
from pitato.chromium import CHROMIUM_NAMES
check("Chromium: Ubuntu's snap too", "/snap/bin/chromium" in CHROMIUM_NAMES)

# ---- System's dashboard on a PC: This PC, its disk, no power light ----
from PIL import ImageDraw
said = []
real_text = ImageDraw.ImageDraw.text


def text(self, xy, t, *a, **k):
    said.append(str(t))
    return real_text(self, xy, t, *a, **k)


ImageDraw.ImageDraw.text = text
PC_NUMS = {"background": [], "temp": 41.0, "busy": 12.0, "mhz": 3400, "power": None, "mem": (3 << 30, 16 << 30),
           "disk": (200 << 30, 300 << 30, 500 << 30), "ssid": None, "dbm": None, "wifi_q": None,
           "ip": "192.168.1.70", "host": "den-pc", "up": 3600, "board": "Dell Inc. OptiPlex 7050",
           "os": "Ubuntu 24.04.3 LTS", "kernel": "6.8.0-85-generic"}
nums = dict(PC_NUMS)
real_numbers = g.system_numbers
g.system_numbers = lambda background=(): dict(nums)
si = m.tab_index("system")
m.tab, m.view = si, "list"
m.load_tab(si)


def dash(panel):
    said.clear()
    m.halting = 0.0                                # (System > Desktop above: nothing drew after it)
    m.msg = None                                   # (no message over its top right)
    m.sys_panel = panel
    m.dirty = True; m.flush()
    return list(said)


texts = dash(2)
check(f"System's dashboard: This PC, its maker and model, its disk ({[t for t in texts if 'PC' in t or 'disk' in t]})",
      m.sys_dash() and "This PC" in texts and "Dell Inc. OptiPlex 7050" in texts
      and any(t.startswith("Free on the disk") for t in texts) and not any("card" in t for t in texts))
check("...no power light (a Pi's own)", "Power OK" not in texts and not any(t.startswith("Power") for t in texts))

# ---- and a Pi, as it was ----
SY.DMI = S + "/nodmi"
make_cards({0, 7})
check(f"a Pi: its outputs as before ({SC.sound_cards()})", SC.sound_cards() == [("PCH", "HDA Intel PCH")])
check(f"...and its sound through ALSA's way as before ({SC.sound_device('HDA Intel PCH')})",
      SC.aplay_device("HDA Intel PCH") == "default:CARD=PCH")
check("...no Desktop row", "Desktop" not in [r["title"] for r in SY.system_info(nums=n)])
m.toast("The Pi didn't restart")
check("...the Pi, as ever", m.msg == "The Pi didn't restart"
      and bt_why("org.bluez.Error.Blocked: rfkill") == "Bluetooth is switched off on this Pi")
check("...its videos made smaller when they need it", m.shrinker.enabled())
SC.screen_size = lambda: (1920, 1080)
check(f"...a Pi 4 on a 1080p TV: 720p, as ever ({SC.video_target()})", SC.video_target() == ("1280x720", 4000, 720))
SC.screen_size = real_size
va = m.video_args()
check(f"...and played the quick way ({va[va.index('-lavdopts') + 1]}, -sws {va[va.index('-sws') + 1]})",
      va[va.index("-lavdopts") + 1] == "threads=4:fast:skiploopfilter=all" and va[va.index("-sws") + 1] == "0")
nums = dict(PC_NUMS, power=("OK", False), board="Raspberry Pi 4 Model B Rev 1.4", disk=(10 << 30, 19 << 30, 29 << 30))
m.load_tab(si)
texts = dash(2)
check(f"...its dashboard: This Pi, its card, its power light ({[t for t in texts if 'Pi' in t or 'card' in t]})",
      "This Pi" in texts and any(t.startswith("Free on the card") for t in texts) and "Power OK" in texts)
g.system_numbers = real_numbers
ImageDraw.ImageDraw.text = real_text

# ---- Ubuntu 24.04's Pillow (10.2): the home screen's icons draw (its rounded boxes in whole pixels) ----
import PIL
from PIL import ImageDraw
from pitato import home as HM


def draws(name, size, lit):
    try:
        HM.draw_icon(name, size, lit=lit)
        return True
    except ValueError:
        return False


bad = [(n, z) for z in (40, 41, 44, 45, 64, 96, 120) for n in ("Games", "TV", "Weather", "Bot", "Music", "Camera")
       for lit in (False, True) if not draws(n, z, lit)]
whole = ImageDraw.ImageDraw.rounded_rectangle.__module__ == "pitato"
check(f"the home screen's icons draw on this Pillow ({PIL.__version__}: "
      f"{'rounded boxes in whole pixels' if whole else 'as it is'}, {bad})",
      not bad and whole == PIL.__version__.startswith("10.2."))

# ---- the web page on a PC: "the PC", never a Pi-hole or a Pi 4; on a Pi, the page as it is ----
sys.path.append(ROOT + "/pitato")
import webui
import socket
c = webui.app.test_client()
B = {"base_url": f"http://{socket.gethostname()}.local:5432", "headers": {"X-Pitato-Page": "1"}}
webui.CONTROL = ("127.0.0.1", 9)                 # (no media mode there: its screen isn't answering)
page = open(webui.PAGE, encoding="utf-8").read()
webui.DMI, webui.PI_MODEL = DMI, S + "/nomodel"
r = c.get("/", **B)
t = r.get_data(as_text=True)
check(f"the web page on a PC: the PC's screen, not the Pi's ({t.count('the PC')} of {page.count('the Pi')})",
      r.status_code == 200 and r.mimetype == "text/html" and r.headers.get("Cache-Control") == "no-cache"
      and "the PC's screen" in t and "the Pi" not in t and "The Pi" not in t and "This Pi" not in t)
check("...the rest as it was: Pi-hole, Hyperlegible, its code", t.count("Pi-hole") == page.count("Pi-hole")
      and "Hyperlegible" in t and t.count("function ") == page.count("function ") and len(t) == len(page))
r = c.get("/play.js", **B)
check("...a game's page too (Play here): the PC isn't answering", r.status_code == 200
      and r.mimetype == "text/javascript" and "The PC isn't answering" in r.get_data(as_text=True))
r = c.get("/play", **B)
check("...its page, with its own security policy", r.status_code == 200
      and r.headers.get("Content-Security-Policy") == webui.PLAY_CSP and "the Pi" not in r.get_data(as_text=True))
r = c.get("/api/pi/state", **B)
check(f"...and what the server says: the PC's screen isn't answering ({r.status_code}, {r.get_json()})",
      r.status_code == 503 and r.get_json() == {"error": "The PC's screen isn't answering. Is Pietato running?"})
r = c.get("/", base_url="http://elsewhere.example:5432")
check(f"...opened by another name: by the PC's name or address ({r.status_code}, {r.get_data(as_text=True)!r})",
      r.status_code == 403 and r.get_data(as_text=True) == "Open this page by the PC's name or address")
webui.DMI = S + "/nodmi"
r = c.get("/", **B)
check("on a Pi: the page as it is", r.status_code == 200 and r.get_data(as_text=True) == page)
r = c.get("/api/pi/state", **B)
check("...and the Pi's screen isn't answering, as ever",
      r.status_code == 503 and r.get_json() == {"error": "The Pi's screen isn't answering. Is Pietato running?"})
webui.PI_MODEL = S + "/model"                   # (a Pi's, with a firmware description too: still a Pi)
webui.DMI = DMI
check("...a Pi with its firmware's description too: still the Pi's", c.get("/", **B).get_data(as_text=True) == page)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
