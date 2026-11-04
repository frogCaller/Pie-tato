"""The GPi Case 2 at work: which case it is (from config.txt as setup.sh wrote it), the dock's pin (pinctrl, or
raspi-gpio), where the picture is since the Pi started (vcgencmd, or the device tree), the pin watched by a thread of
its own. Media mode in a GPi Case 2 on its own screen: put in the dock (the pin high, and staying so), the Pi restarts
for the TV, saying so, a game ended first (it carries on from there); a blip isn't enough. On the TV: taken out, it
restarts for the case's screen; the sound goes to the TV first (the case's own is USB). A restart for the dock that
didn't take isn't tried again till the pin's been the other way. In the terminal: it restarts all the same. The 2W:
its speaker hush as before, no dock. No case: nothing."""
import json, os, shutil, sys, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw

S = SP + "/t_gpicase2"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games"):
    os.makedirs(f"{HOME}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.DOCK_FILE = S + "/dock-restart.json"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.PROG_TTY = os.devnull
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


import pitato.gpicase as GC
import pitato.media as MED
import pitato.screen as SCR

# ---- which case: config.txt as setup.sh writes it ---------------------------------------------------------------------
setup = open(ROOT + "/setup.sh").read()
case2_block = setup.split("cat <<'EOF'\n# >>> gpi-case setup >>>", 1)[1]
case2_text = "# >>> gpi-case setup >>>" + case2_block.split("EOF\n", 1)[0]
w2_text = setup.split("cat >> \"$CONFIG\" <<'EOF'\n# >>> gpi-case setup >>>", 1)[1].split("EOF\n", 1)[0]
w2_text = "# >>> gpi-case setup >>>" + w2_text
k2 = GC.case_kind("dtparam=audio=on\n" + case2_text + "\n# <<< gpi-case setup <<<\n")
kw, kn = GC.case_kind(w2_text), GC.case_kind("dtoverlay=vc4-kms-v3d\n")
check(f"which case, from config.txt: the GPi Case 2's part ({k2}), the 2W's ({kw}), none ({kn})",
      k2 == "2" and kw == "2w" and kn is None)
cfg = S + "/config.txt"
open(cfg, "w").write("[all]\n" + case2_text + "\n# <<< gpi-case setup <<<\n")
g.CONFIG_TXT = (S + "/missing.txt", cfg)
check("...read from config.txt where it is (Bookworm's place, else the older one)", GC.case_kind() == "2"
      and g.gpi_case_set_up())

# ---- the dock's pin, where the picture is ---------------------------------------------------------------------------
said = {}


def fake_run(cmd, timeout=3):
    return said.get(cmd[0], "")


GC.run_out = fake_run
said = {"pinctrl": "18: ip    pd | hi // GPIO18 = input\n"}
hi = GC.pin_level()
said = {"pinctrl": "18: ip    pd | lo // GPIO18 = input\n"}
lo = GC.pin_level()
said = {"raspi-gpio": "GPIO 18: level=1 fsel=0 func=INPUT pull=DOWN\n"}
old_hi = GC.pin_level()
said = {}
check(f"the dock's pin: pinctrl's hi and lo ({hi}, {lo}), an older system's raspi-gpio ({old_hi}), neither: no telling "
      f"({GC.pin_level()})", hi is True and lo is False and old_hi is True and GC.pin_level() is None)
said = {"vcgencmd": "enable_dpi_lcd=1\n"}
on_case = GC.started_on_tv()
said = {"vcgencmd": "enable_dpi_lcd=0\n"}
on_tv = GC.started_on_tv()
said = {}
DT = S + "/dt"
os.makedirs(DT + "/soc/firmwarekms@7e600000")
GC.DEVICE_TREE = DT


def tree(fb, fkms):
    """The device tree's framebuffer and fkms nodes so (a status, or None: the node not there), and where the picture
    is by them."""
    for d, st in (("/soc/fb", fb), ("/soc/firmwarekms@7e600000", fkms)):
        if st is None:
            shutil.rmtree(DT + d, ignore_errors=True)
        else:
            os.makedirs(DT + d, exist_ok=True)
            open(DT + d + "/status", "wb").write(st.encode() + b"\x00")
    return GC.started_on_tv()


fw = tree("okay", "disabled")          # (no KMS: the firmware's own framebuffer, as setup.sh's case screen has it)
fk = tree("disabled", "okay")          # (an older setup.sh's: fkms)
kms = tree("disabled", "disabled")     # (KMS, the TV's)
kms_old = tree(None, "disabled")       # (no framebuffer node, fkms's off: KMS)
fw_alone = tree("okay", None)          # (no fkms node at all: the firmware's)
nothing = tree(None, None)
os.makedirs(DT + "/soc/gpu/fb")
open(DT + "/soc/gpu/fb/status", "wb").write(b"okay\x00")
deep = GC.started_on_tv()              # (one further down: not the firmware's)
shutil.rmtree(DT + "/soc/gpu")
os.makedirs(DT + "/soc/fb@0")
open(DT + "/soc/fb@0/status", "wb").write(b"okay\x00")
fw_at = GC.started_on_tv()             # (a framebuffer node with an address)
shutil.rmtree(DT + "/soc")
check(f"where the picture is: the case's screen by vcgencmd ({on_case}), the TV ({on_tv}); without it, by the device "
      f"tree: the firmware's framebuffer on, the case's ({fw}, {fw_alone}, {fw_at}); fkms on, the case's too ({fk}); "
      f"both off, KMS's: the TV ({kms}, {kms_old}); neither there: no telling ({nothing}, {deep})",
      on_case is False and on_tv is True and fw is False and fw_alone is False and fw_at is False and fk is False
      and kms is True and kms_old is True and nothing is None and deep is None and GC.started_on_tv() is None)

levels = [False, False, True, True, True, True, True, True, True, True, True, True]
w = GC.DockWatch(read=lambda: levels.pop(0) if levels else True, every=0.05)
time.sleep(0.04)
first = w.settled(time.monotonic(), 0.05)
time.sleep(0.2)
early = w.settled(time.monotonic(), 0.3)
time.sleep(0.35)
late = w.settled(time.monotonic(), 0.3)
w.stop()
check(f"its watch: not settled at first ({first}), nor just after a change ({early}); then the new level ({late})",
      first is None and early is None and late is True)
w = GC.DockWatch(read=lambda: 1 / 0, every=0.05)
time.sleep(0.15)
check("...a read that fails: no telling, and it carries on", w.settled(time.monotonic(), 0) is None and w.thread.is_alive())
w.stop()
GC.note_dock_restart("tv", [1000.0, 1100.5])
a = GC.dock_tried()
b = GC.dock_tried()
check(f"restarts for the dock noted (where to, when), told once ({a}, then {b})", a == ("tv", [1000.0, 1100.5])
      and b == (None, []))
open(g.DOCK_FILE, "w").write("not json")
check("...a broken note: none", GC.dock_tried() == (None, []) and not os.path.exists(g.DOCK_FILE))

# busy: a shutdown held off (setup.sh's), or apt's lock held
said = {"busctl": json.dumps({"type": "a(ssssuu)", "data": [[
    ["sleep", "ModemManager", "...", "delay", 0, 500],
    ["shutdown:sleep:handle-power-key", "Pietato setup", "Setting up Pietato", "block", 0, 1234]]]})}
held = GC.busy()
said = {"busctl": json.dumps({"type": "a(ssssuu)", "data": [[["sleep", "ModemManager", "...", "delay", 0, 500]]]})}
lockf = S + "/lock-frontend"
open(lockf, "w").close()
st = os.stat(lockf)
GC.DPKG_LOCKS = (lockf,)
GC.PROC_LOCKS = S + "/locks"
open(GC.PROC_LOCKS, "w").write("1: OFDLCK ADVISORY  READ  -1 00:1a:999 0 EOF\n")
free = GC.busy()
open(GC.PROC_LOCKS, "w").write(f"1: OFDLCK ADVISORY  READ  -1 00:1a:999 0 EOF\n"
                               f"2: POSIX  ADVISORY  WRITE 2349 {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:"
                               f"{st.st_ino} 0 EOF\n")
apt = GC.busy()
said = {}
check(f"busy: setup.sh holding off shutdown ({held!r}); nothing ({free!r}); apt's lock held ({apt!r})",
      held == "Pietato setup" and free is None and apt == "apt")
os.remove(GC.PROC_LOCKS)


# ---- media mode in the GPi Case 2 ----------------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): self.show(img)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


class FakeDock:
    """The dock's pin, as the test says it is."""
    def __init__(self):
        self.level, self.since = None, time.monotonic()

    def set(self, level, ago=0.0):
        self.level, self.since = level, time.monotonic() - ago

    def settled(self, now, settle=GC.DOCK_SETTLE_IN):
        return self.level if self.level is not None and now - self.since >= settle else None

    def stop(self):
        pass


docks = []
MED.DockWatch = lambda: (docks.append(FakeDock()), docks[-1])[1]
started = {"tv": False}
MED.started_on_tv = lambda: started["tv"]
busy_now = {"why": None}
MED.busy = lambda: busy_now["why"]
popens = []
real_popen = MED.subprocess.Popen


def fake_popen(cmd, *a, **k):
    if cmd[:1] == ["systemctl"]:
        popens.append(list(cmd))
        return types.SimpleNamespace(poll=lambda: 0, wait=lambda timeout=None: 0)
    return real_popen(cmd, *a, **k)


MED.subprocess.Popen = fake_popen
MED.system_stopping = lambda: False
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
g.Framebuffer = FB
IN, OUT = GC.DOCK_SETTLE_IN, GC.DOCK_SETTLE_OUT


def fresh(quiet_over=True):
    """Media mode as it starts in the case (its first quiet minute over, unless said)."""
    global m
    del popens[:]
    m = g.Media(); m.enter()
    m.keyreader.start = m.keyreader.stop = lambda: None
    m.dock_start()
    if quiet_over and m.dock is not None:
        m.dock_since -= GC.DOCK_QUIET + 1
    return m


def clear_note():
    if os.path.exists(g.DOCK_FILE):
        os.remove(g.DOCK_FILE)


m = fresh(quiet_over=False)
check(f"media mode in a GPi Case 2: it knows ({m.case}); no speaker hush (that's the 2W's); its dock watched, on the "
      f"case's screen ({m.dock_on_tv}); sound as ever (TV_FIRST {SCR.TV_FIRST})", m.case == "2" and not m.gpi_case
      and m.dock is docks[-1] and m.dock_on_tv is False and SCR.TV_FIRST is False)
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"in the dock in media mode's first minute: nothing yet ({popens})", not popens)
m.dock_since -= GC.DOCK_QUIET + 1
m.dock.set(True, ago=1.0)
m.tick()
check(f"put in the dock: not at once ({popens})", not popens)
m.dock.set(True, ago=IN + 0.1)
m.dock.set(False, ago=IN + 1)
m.tick()
check("...nor for a blip that went (low again)", not popens)


class FakeRun:
    def __init__(self):
        self.quitted = False
        self.state, self.disc, self.game = "on", (0, 1), {"system": "gba", "path": "/g/x.gba"}

    def quit(self, timeout=None):
        self.quitted = True


run = FakeRun()
m.game, m.view = run, "game"
texts.clear()
m.dock.set(True, ago=IN + 0.1)
m.tick()
check(f"in the dock {IN:.0f} seconds: the Pi restarts ({popens})", popens == [["systemctl", "reboot"]])
check(f"...saying so ({[t for t in texts if 'dock' in t or 'restarts' in t]})",
      "In the dock: on to the TV" in texts and "The Pi restarts" in texts)
check("...a game in hand ended first (its place kept: it carries on there)", run.quitted and m.game is None)
note = json.load(open(g.DOCK_FILE))
check(f"...noted, where to and when, to see if it takes ({note})", note["to"] == "tv" and len(note["times"]) == 1
      and abs(note["times"][0] - time.time()) < 5)
m.tick()
check("...and only once", len(popens) == 1)

# the next start-up: on the TV, as it should be
started["tv"] = True
m = fresh()
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"started again in the dock: on the TV, sound to the TV first (TV_FIRST {SCR.TV_FIRST}), nothing more to do",
      m.dock_on_tv is True and SCR.TV_FIRST is True and not popens and not os.path.exists(g.DOCK_FILE))
m.dock.set(False, ago=IN + 1)
m.tick()
check(f"out of the dock (or the TV off) for {IN + 1:.0f} seconds: not yet ({popens})", not popens)
texts.clear()
m.dock.set(False, ago=OUT + 0.1)
m.tick()
check(f"...for {OUT:.0f}: the Pi restarts for the case's screen ({popens}, {[t for t in texts if 'dock' in t]})",
      popens == [["systemctl", "reboot"]] and "Out of the dock: back to the case's screen" in texts)
check(f"...noted with the one before ({len(json.load(open(g.DOCK_FILE))['times'])} times)",
      len(json.load(open(g.DOCK_FILE))["times"]) == 2)

# twice in ten minutes already: not a third time
started["tv"] = False
m = fresh()
m.dock.set(True, ago=IN + 1)
m.msg = None
m.tick()
check(f"a third restart for the dock within ten minutes: not done; the dock's not followed now ({popens}, "
      f"{m.msg!r})", not popens and m.dock_off and "keeps changing" in str(m.msg))
m.dock.set(False, ago=IN + 1)
m.tick()
m.dock.set(True, ago=IN + 1)
m.tick()
check("...not even when it changes again", not popens)
GC.note_dock_restart("case", [time.time() - 3600, time.time() - 1800])
m = fresh()
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"restarts for it an hour and half an hour ago: those don't count ({popens})", popens == [["systemctl", "reboot"]])

# a restart that didn't take: the firmware saw the pin low, and the Pi's on its own screen again
clear_note()
started["tv"] = False
GC.note_dock_restart("tv", [time.time()])
m = fresh()
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"a restart for the TV that didn't take (still on the case's screen, in the dock): not again ({popens}), "
      f"said once ({m.msg!r})", not popens and m.dock_stuck == "tv" and "own screen" in str(m.msg))
m.msg = None
m.tick()
check("...nor the next time it looks", not popens and m.msg is None)
m.dock.set(False, ago=IN + 1)
m.tick()
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"...taken out and put back in: tried again ({popens})", popens == [["systemctl", "reboot"]])

# in the terminal
clear_note()
m = fresh()
m.leave()
lines = []
MED.show_shutdown_lines = lambda: lines.append(1)
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"in the terminal: put in the dock, it restarts all the same ({popens}, its lines shown {bool(lines)})",
      popens == [["systemctl", "reboot"]] and lines)

# not while Update software puts a new version in, nor setup.sh or apt is at work
clear_note()
m = fresh()
m.updater.started = time.monotonic()
m.dock.set(True, ago=IN + 1)
m.tick()
check(f"put in the dock while Update software puts a new version in: no restart then ({popens})", not popens)
m.updater.started = 0.0
busy_now["why"] = "Pietato setup"
m.msg = None
m.tick()
check(f"...while setup.sh is at work: not then either, and it says why ({popens}, {m.msg!r})", not popens
      and "when Pietato setup is done" in str(m.msg))
busy_now["why"] = None
m.dock_busy = (m.dock_busy[0] - 6, m.dock_busy[1])
m.tick()
check(f"...once they're done, it restarts ({popens})", popens == [["systemctl", "reboot"]])
m.leave()
clear_note()

# sound: the TV first, in the dock
SCR.ASOUND = S + "/asound"
os.makedirs(SCR.ASOUND)
open(SCR.ASOUND + "/cards", "w").write(
    " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
    " 1 [Device         ]: USB-Audio - USB Audio Device\n                      GeneralPlus USB Audio Device at ...\n")
SCR.hdmi_ports = lambda: [0]
SCR.hdmi_sound = lambda port: None
SCR.TV_FIRST = True
tv_first = SCR.sound_card("Auto")
SCR.TV_FIRST = False
usb_first = SCR.sound_card("Auto")
SCR.TV_FIRST = True
SCR.hdmi_ports = lambda: []
no_tv = SCR.sound_card("Auto")
SCR.TV_FIRST = False
check(f"Auto sound: in the dock, the TV ({tv_first}) over the case's own USB sound; out of it, the USB as ever "
      f"({usb_first}); in the dock without a TV, the USB ({no_tv})",
      tv_first == "vc4hdmi0" and usb_first == "Device" and no_tv == "Device")

# the 2W, and no case
open(cfg, "w").write("[all]\n" + w2_text)
m = fresh()
check(f"the 2W: its speaker hush as before, no dock ({m.case}, {m.gpi_case}, {m.dock})", m.case == "2w" and m.gpi_case
      and m.dock is None)
open(cfg, "w").write("[all]\ndtoverlay=vc4-kms-v3d\n")
m = fresh()
check(f"no case: neither ({m.case}, {m.gpi_case}, {m.dock})", m.case is None and not m.gpi_case and m.dock is None)
m.tick()
check("...and nothing restarts", not popens)
m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
