"""RK3326 handhelds on dArkOS (the R36S and its kind). Told from a Pi or a PC by the device tree as Pietato starts: the
R36S's, the RG351MP's (Hardkernel's ODROID-GO3 for a model) and a named one's are; a Pi's, an RK3566's and a PC's (none)
aren't. Its profile: the built-in gamepad's buttons as printed on them (A on the right; FN is HOME, and SELECT and START
together too; Swap A and B; Settings > Controller's buttons; the GO-Advance's); on a Pi the same name is just a pad.
Its battery and the CPU's and GPU's temperatures from /sys (a controller's battery isn't its own), on the status bar
and in System; WiFi through a USB dongle (none plugged in: said); its own speaker; "the handheld" in what's said, and
on the web page; a slow one's settings; no Power row (vcgencmd's); EmulationStation a System action away. On a Pi
none of it. setup.sh on a pretend R36S on dArkOS (inner.sh): no GPi Case question, dArkOS's own emulators instead of
building them, Pietato in EmulationStation's place and the console on; stop.sh, start.sh and uninstall.sh put each
back. The setup screen: This handheld, what's in already, EmulationStation."""
import json, os, re, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:                                # (the tests' own stand-in for it)
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e, AbsInfo
REAL_RUN = subprocess.run
from PIL import Image, ImageDraw

S = SP + "/t_handheld"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games"):
    os.makedirs(f"{HOME}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"; g.PLEX_FILE = S + "/plex"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.PROG_TTY = os.devnull
ok_all = []
ONLY = sys.argv[1:]


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


import pitato.handheld as H
import pitato.system as SYS
import pitato.screen as SCR
import pitato.media as MED
import pitato.webui as WEB


def tree(name, compatible, model=None):
    """A pretend device tree: its compatible list (NULs between), and its model."""
    d = f"{S}/dt/{name}"
    os.makedirs(d)
    if compatible is not None:
        open(d + "/compatible", "wb").write(b"".join(c.encode() + b"\0" for c in compatible))
    if model is not None:
        open(d + "/model", "wb").write(model.encode() + b"\0")
    return d


R36S = tree("r36s", ["rockchip,rk3326-odroidgo3-linux", "rockchip,rk3326"], "Hardkernel ODROID-GO3")
NAMED = tree("named", ["rockchip,rk3326-r36s-linux", "rockchip,rk3326"], "R36S Rev 1")
OGA = tree("oga", ["rockchip,rk3326-odroidgo2-linux", "rockchip,rk3326"], "Hardkernel ODROID-GO2")
PI4 = tree("pi4", ["raspberrypi,4-model-b", "brcm,bcm2711"], "Raspberry Pi 4 Model B Rev 1.5")
RK3566 = tree("rg353", ["anbernic,rg353v", "rockchip,rk3566"], "Anbernic RG353V")
NONE = S + "/dt/pc"                             # (a PC: no device tree at all)
H.DARKOS_NAME = S + "/darkos/*/.DEVICE"


def be(where):
    """This machine is the one with this device tree, as Pietato starts (its profile worked out afresh)."""
    H.DEVICE_TREE = where
    H._found.clear()
    return H.profile()


# ---- told by its device tree --------------------------------------------------------------------------------------
if not ONLY or "detect" in ONLY:
    got = {n: H.detect(t) for n, t in (("r36s", R36S), ("named", NAMED), ("oga", OGA), ("pi4", PI4),
                                         ("rk3566", RK3566), ("pc", NONE))}
    check(f"an RK3326 handheld, from its device tree's compatible list ({got['r36s']})",
          got["r36s"] == {"chip": "rk3326", "model": "Hardkernel ODROID-GO3", "name": "RK3326 handheld"}
          and got["oga"]["chip"] == "rk3326")
    check(f"...not a Pi, an RK3566 or a PC ({got['pi4']}, {got['rk3566']}, {got['pc']})",
          got["pi4"] is None and got["rk3566"] is None and got["pc"] is None)
    os.makedirs(S + "/darkos/ark")
    open(S + "/darkos/ark/.DEVICE", "w").write("R36S\n")
    names = [H.detect(R36S)["name"], H.detect(NAMED)["name"]] + [H.nice_name(m) for m in (
        "Anbernic RG351MP", "BatleXP G-G-G-G350!", "A10 Mini aka Da Cute Cute", "Powkiddy RGB10")]
    os.remove(S + "/darkos/ark/.DEVICE")
    check(f"...called what its model says, else what dArkOS's image calls it ({names})",
          names == ["R36S", "R36S", "RG351MP", "G350", "A10 Mini", "RGB10"])
    check("...worked out once, as Pietato starts (the same answer after, with no more looking)",
          be(R36S) is not None and (setattr(H, "DEVICE_TREE", PI4) or H.is_handheld()) and H.name() == "RK3326 handheld")
    be(PI4)
    check("...and on a Pi, it isn't one", not H.is_handheld() and H.name() == "" and H.gamepad_codes("GO-Super Gamepad")
          is None and not H.has_emulationstation())

# ---- its battery, temperatures, WiFi dongle -----------------------------------------------------------------------
PS, TH, NET = S + "/sys/power_supply", S + "/sys/thermal", S + "/sys/net"


def put(path, **files):
    os.makedirs(path, exist_ok=True)
    for k, v in files.items():
        open(os.path.join(path, k), "w").write(str(v) + "\n")


put(PS + "/battery", type="Battery", capacity=76, status="Discharging")
put(PS + "/usb", type="USB", online=0)
put(PS + "/hid-pad-battery", type="Battery", scope="Device", capacity=10, status="Discharging")   # (a controller's)
put(TH + "/thermal_zone0", type="soc-thermal", temp=52000)
put(TH + "/thermal_zone1", type="gpu-thermal", temp=49250)
put(NET + "/lo", mtu=65536)
H.POWER_SUPPLY, H.THERMAL, H.NET = PS, TH, NET
ES = S + "/emulationstation.service"
open(ES, "w").write("[Unit]\nDescription=EmulationStation-fcamod (pretend)\n")
H.ES_UNITS = (ES,)

if not ONLY or "sys" in ONLY:
    b1 = H.battery()
    put(PS + "/battery", status="Charging")
    b2 = H.battery()
    put(PS + "/battery", status="Full", capacity=100)
    b3 = H.battery()
    put(PS + "/battery", capacity="?")
    b4 = H.battery()
    put(PS + "/battery", status="Discharging", capacity=76)
    check(f"its battery from /sys: how full, and charging ({b1}, {b2}, {b3}), not a controller's; no reading: none "
          f"({b4})", (b1, b2, b3, b4) == ((76, False), (76, True), (100, True), None))
    check(f"its CPU's and GPU's temperatures from /sys ({H.temperatures()})", H.temperatures() == [("CPU", 52.0),
                                                                                                   ("GPU", 49.25)])
    w1 = H.wifi_adapter()
    put(NET + "/wlan0/wireless")
    w2 = H.wifi_adapter()
    shutil.rmtree(NET + "/wlan0")
    check(f"WiFi: a USB dongle's, while there's one plugged in ({w1}, {w2})", w1 is None and w2 == "wlan0")

# ---- the built-in gamepad -------------------------------------------------------------------------------------------
class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Dev:
    """An input device, as evdev has it (its name, its buttons and sticks)."""
    def __init__(self, name, keys, axes=None):
        self.name, self.keys, self.path = name, keys, "/dev/input/event9"
        self.axes = axes or {}
        self.info = Info(0x484b, 0x1100)

    def capabilities(self, verbose=False, absinfo=True):
        caps = {e.EV_KEY: list(self.keys)}
        if self.axes:
            caps[e.EV_ABS] = [(c, a) if absinfo else c for c, a in self.axes.items()]
        return caps

    def absinfo(self, code):
        return self.axes[code]


STICK = AbsInfo(value=0, min=-1800, max=1800, fuzz=64, flat=32, resolution=0)
GO_KEYS = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_TL2, e.BTN_TR2,
           e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT, e.BTN_TRIGGER_HAPPY1,
           e.BTN_TRIGGER_HAPPY2, e.BTN_TRIGGER_HAPPY3, e.BTN_TRIGGER_HAPPY4, e.BTN_TRIGGER_HAPPY5,
           e.BTN_TRIGGER_HAPPY6]
GO_AXES = {e.ABS_X: STICK, e.ABS_Y: STICK, e.ABS_RX: STICK, e.ABS_RY: STICK}


def presses(pad, codes):
    out = []
    for c in codes:
        got = pad.translate(Ev(e.EV_KEY, c, 1))
        pad.translate(Ev(e.EV_KEY, c, 0))
        out.append(got[0][0] if got else None)
    return out


ORDER = [e.BTN_EAST, e.BTN_SOUTH, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_TL2, e.BTN_TR2, e.BTN_DPAD_UP,
         e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT, e.BTN_TRIGGER_HAPPY1, e.BTN_TRIGGER_HAPPY2,
         e.BTN_TRIGGER_HAPPY3, e.BTN_TRIGGER_HAPPY4, e.BTN_TRIGGER_HAPPY5, e.BTN_TRIGGER_HAPPY6]
if not ONLY or "pad" in ONLY:
    be(R36S)
    dev = Dev("GO-Super Gamepad", GO_KEYS, GO_AXES)
    pad = g.Pad(dev, g.pad_kind(dev))
    got = presses(pad, ORDER)
    check(f"the R36S's gamepad (the GO-Super Gamepad): its buttons as printed on them, A on the right ({got})",
          got == ["a", "b", "x", "y", "l", "r", "l2", "r2", "up", "down", "left", "right", "select", "start", None, None,
                  "home", None])
    check("...its sticks are sticks (its d-pad's its own), and FN is HOME with SELECT and START together HOME too",
          pad.has_stick() and pad.dpad_apart() and pad.has_button("home") and not pad.home)
    sw = presses(g.Pad(dev, g.pad_kind(dev), {"swap": True}), ORDER[:2])
    learned = g.Pad(dev, g.pad_kind(dev), {"keys": {str(e.BTN_TRIGGER_HAPPY6): "home"}})
    check(f"...Swap A and B swaps them ({sw}); Settings > Controller's HOME is HOME, and then SELECT and START aren't "
          f"({presses(learned, [e.BTN_TRIGGER_HAPPY6])})", sw == ["b", "a"] and presses(learned, [e.BTN_TRIGGER_HAPPY6])
          == ["home"] and learned.home)
    oga = presses(g.Pad(Dev("GO-Advance Gamepad (rev 1.1)", GO_KEYS, GO_AXES), "gamepad"), ORDER[12:])
    check(f"...an Odroid Go Advance's (the RGB10's): F1 SELECT, F6 START, F5 HOME ({oga})",
          oga == ["select", None, None, None, "home", "start"])
    xbox = presses(g.Pad(Dev("Microsoft X-Box 360 pad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_MODE]),
                         "gamepad"), [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_MODE])
    check(f"...another controller plugged in is as it always is ({xbox})", xbox == ["a", "b", "start", "home"])
    be(PI4)
    pi = presses(g.Pad(dev, g.pad_kind(dev)), ORDER[:2] + [e.BTN_TRIGGER_HAPPY1])
    check(f"on a Pi, a pad by that name is any pad: the bottom button's A, as ever ({pi})", pi == ["b", "a", None])

# ---- System, the status bar, what's said --------------------------------------------------------------------------
if not ONLY or "sys" in ONLY:
    SYS.cpu_temp = lambda: 52.0
    SYS.run_out = lambda cmd, timeout=3: {"vcgencmd": "throttled=0x0", "hostname": "10.0.0.5"}.get(cmd[0], "")
    SYS.PI_MODEL = R36S + "/model"
    SYS._slow.clear()
    be(R36S)
    rows = {r["title"]: r["sub"] for r in SYS.system_info(nums=SYS.system_numbers())}
    check(f"System on the handheld: its battery, the GPU's temperature, no Power (vcgencmd's), what it is, and "
          f"EmulationStation ({rows})", rows.get("Battery") == "76%" and rows.get("GPU temperature") == "49.2 °C"
          and "Power" not in rows and rows.get("Board") == "RK3326 handheld" and "EmulationStation" in rows
          and rows.get("WiFi") == "no USB WiFi dongle" and rows.get("CPU temperature") == "52.0 °C")
    try:
        SYS.wifi_scan()
        said = None
    except ValueError as ex:
        said = str(ex)
    check(f"...Settings > WiFi, with no dongle: says to plug one in ({said!r})",
          said == "No WiFi adapter: plug in a USB WiFi dongle")
    put(NET + "/wlan0/wireless")
    SYS.nm = lambda args, timeout=20: (True, "*:Home:80:WPA2\n:Cafe:40:\n", "")
    nets = SYS.wifi_scan()
    shutil.rmtree(NET + "/wlan0")
    check(f"...with one: its networks, through NetworkManager ({[n['ssid'] for n in nets]})",
          [n["ssid"] for n in nets] == ["Home", "Cafe"] and nets[0]["active"])
    SYS.DMI = S                                    # (a folder that's there: a PC's firmware would have one)
    words = [SYS.on_pc("Restart the Pi"), SYS.on_pc("This Pi is in a GPi Case 2"), SYS.on_pc("a Pi-hole")]
    check(f"...what's said: the handheld, never a PC ({words})", words == ["Restart the handheld",
          "This handheld is in a GPi Case 2", "a Pi-hole"] and not SYS.is_pc())
    SCR.pi_model = lambda: "Hardkernel ODROID-GO3"
    SCR.sound_cards_seen = lambda: [("rockchiprk817co", "rockchip_rk817-", "rockchip,rk817-codec")]
    check(f"...a slow one's settings (as a Pi 3's), its own speaker ({[c['name'] for c in SCR.sound_list()]})",
          SCR.slow_pi() and [c["name"] for c in SCR.sound_list()] == ["Speaker"])

    be(PI4)
    SYS.PI_MODEL = PI4 + "/model"
    SYS._slow.clear()
    rows = {r["title"]: r["sub"] for r in SYS.system_info(nums=SYS.system_numbers())}
    SCR.pi_model = lambda: "Raspberry Pi 4 Model B Rev 1.5"
    check(f"on a Pi, none of it: Power, its own Board, no battery or EmulationStation ({sorted(rows)})",
          rows.get("Power") == "OK" and rows.get("Board") == "Raspberry Pi 4 Model B Rev 1.5"
          and not {"Battery", "GPU temperature", "EmulationStation"} & set(rows) and rows.get("WiFi") == "not connected"
          and SYS.on_pc("Restart the Pi") == "Restart the Pi" and not SCR.slow_pi()
          and [c["name"] for c in SCR.sound_list()] == ["rockchip,rk817-codec"])
    SYS.PI_MODEL, SYS.DMI = NONE + "/model", S
    check("...and a PC's a PC", SYS.is_pc() and SYS.on_pc("Restart the Pi") == "Restart the PC")
    SYS.DMI = S + "/no-dmi"

    # the web page's own way of telling
    WEB.COMPATIBLE, WEB.PI_MODEL, WEB.DMI = R36S + "/compatible", R36S + "/model", S
    hh = (WEB.is_handheld(), WEB.is_pc(), WEB.pc_said("The Pi restarts"))
    WEB.COMPATIBLE, WEB.PI_MODEL = PI4 + "/compatible", PI4 + "/model"
    pi = (WEB.is_handheld(), WEB.is_pc(), WEB.pc_said("The Pi restarts"))
    WEB.COMPATIBLE, WEB.PI_MODEL = NONE + "/compatible", NONE + "/model"
    pc = (WEB.is_handheld(), WEB.is_pc(), WEB.pc_said("The Pi restarts"))
    check(f"the web page: the handheld ({hh}), a Pi ({pi}), a PC ({pc})",
          hh == (True, False, "The handheld restarts") and pi == (False, False, "The Pi restarts")
          and pc == (False, True, "The PC restarts"))
    WEB.DMI = S + "/no-dmi"


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    frames = []

    def show(self, img):
        FB.frames.append(img.copy())

    def show_part(self, img, box):
        FB.frames.append(img.copy())

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def power(self, on):
        return True

    def close(self):
        pass


g.Framebuffer = FB
if not ONLY or "screen" in ONLY:
    g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
    be(R36S)
    m = g.Media()
    m.enter()

    def charge(capacity, status):
        if capacity is None:
            shutil.rmtree(PS + "/battery", ignore_errors=True)
        else:
            put(PS + "/battery", type="Battery", capacity=capacity, status=status)

    def bar(capacity, status="Discharging"):
        charge(capacity, status)
        img = Image.new("RGB", (640, 40), (0, 0, 0))
        m.status_bar(ImageDraw.Draw(img), clock=False)
        return img

    def pixels(im):
        return list(getattr(im, "get_flattened_data", im.getdata)())

    on, charging, low, none = bar(76), bar(76, "Charging"), bar(9), bar(None)
    right = (360, 0, 600, 40)
    lit = [sum(1 for p in pixels(im.crop(right)) if p != (0, 0, 0)) for im in (on, charging, low, none)]
    acc = sum(1 for p in pixels(charging.crop(right)) if p == g.ACCENT)
    warn = sum(1 for p in pixels(low.crop(right)) if p == g.WARN)
    check(f"the status bar: the battery, how full (its colour while it charges, orange when it's low) ({lit}, {acc}, "
          f"{warn})", lit[0] > lit[3] + 60 and acc > 40 and warn > 40 and lit[3] > 0)
    charge(76, "Discharging")
    sig1 = m.status_signature()
    charge(75, "Discharging")
    check("...drawn again when the battery changes", m.status_signature() != sig1)
    charge(76, "Discharging")
    on.resize((1280, 80)).save(S + "/status_bar.png")
    calls = []
    real_popen = MED.subprocess.Popen
    MED.subprocess.Popen = lambda cmd, *a, **k: calls.append(cmd)
    act = {"src": "es"}
    m.system_action(act)
    first = (list(calls), m.msg)
    m.system_action(act)
    MED.subprocess.Popen = real_popen
    check(f"System > EmulationStation: asked twice ({first[1]!r}), Pietato stops and EmulationStation starts, till the "
          f"handheld restarts ({calls})", first[0] == [] and "Press A again for EmulationStation" in str(first[1])
          and calls == [["systemd-run", "--no-block", "--collect", "--unit=pietato-es", "sh", "-c",
                         "systemctl stop pitato; systemctl start emulationstation"]])
    m.halting = 0.0
    m.leave()
    be(PI4)
    m2 = g.Media()
    m2.enter()
    img = Image.new("RGB", (640, 40), (0, 0, 0))
    m2.status_bar(ImageDraw.Draw(img), clock=False)
    check("on a Pi: no battery on the status bar, its signature as ever",
          sum(1 for p in pixels(img.crop((360, 0, 600, 40))) if p != (0, 0, 0)) == lit[3]
          and len(m2.status_signature()) == 6)
    m2.leave()
    g.subprocess.run = REAL_RUN

# ---- setup.sh's screen ----------------------------------------------------------------------------------------------
if not ONLY or "wizard" in ONLY:
    from pitato import wizard as W
    CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")

    def screen(text):
        lines, row, col, i = [""], 0, 0, 0
        while i < len(text):
            mm = CSI.match(text, i)
            if mm:
                if mm.group(2) == "A":
                    row = max(0, row - int(mm.group(1) or 1))
                elif mm.group(2) == "J":
                    lines[row] = lines[row][:col]
                    del lines[row + 1:]
                i = mm.end()
                continue
            ch = text[i]
            if ch == "\n":
                row, col = row + 1, 0
                while row >= len(lines):
                    lines.append("")
            elif ch == "\r":
                col = 0
            elif ch >= " ":
                ln = lines[row].ljust(col)
                lines[row] = ln[:col] + ch + ln[col + 1:]
                col += 1
            i += 1
        return "\n".join(x.rstrip() for x in lines)

    class Term:
        def __init__(self, keys):
            self.keys, self.out, self.snaps = list(keys), [], []

        def size(self):
            return 100, 40

        def write(self, text):
            self.out.append(text)

        def key(self, timeout=None):
            if timeout is not None:
                time.sleep(0.01)
                return None
            k = self.keys.pop(0)
            if isinstance(k, tuple):
                self.snaps.append(screen("".join(self.out)))
                k = k[1]
            return k

    os.makedirs(S + "/rcores")
    for c in ("mgba", "snes9x", "genesis_plus_gx", "pcsx_rearmed", "fbneo", "mednafen_ngp"):
        open(f"{S}/rcores/{c}_libretro.so", "w").close()
    W.shutil = type("which", (), {"which": staticmethod(lambda n, *a, **k: None),
                                  "get_terminal_size": staticmethod(shutil.get_terminal_size)})
    env = {"PIETATO_W_" + k: v for k, v in dict(
        MODEL="Hardkernel ODROID-GO3", BIG="no", ARCH="arm64", MACHINE="handheld", HANDHELD="R36S", ES="yes",
        DARKOS_CORES=S + "/rcores", OS="Debian GNU/Linux 13 (trixie)", MEM="988", FREE="20000", USER="ark", HOME=HOME,
        STATIC=S + "/static", CORES=S + "/cores", PROGS=S + "/progs", GPI="no").items()}
    t = Term([("snap", "down"), "enter", ("snap", "enter"), "enter", "enter", ("snap", "enter")])
    got = W.Wizard(W.Screen(t, W.Look(fancy=True, colour=False)), W.Machine(env)).run()
    sc = screen("".join(t.out))
    sq = re.sub(r" {2,}", " ", t.snaps[1])
    check("setup's screen on the handheld: This handheld, what it is", "◇  This handheld ─" in sc
          and "│  R36S · Debian GNU/Linux 13 (trixie)" in sc and "everything this handheld can run" in t.snaps[0])
    check("...dArkOS's own emulators in already; nothing a Pi Zero 2 couldn't run",
          all(x in sq for x in ("◼ Game Boy, NES, SNES, Genesis in already", "◼ PlayStation in already",
                                "◼ Neo Geo in already", "◼ Neo Geo Pocket in already"))
          and not re.search(r"N64|PSP|Dreamcast|Chromium|Start in Pietato", sq))
    check(f"...ready: it starts in Pietato, not EmulationStation; leave the handheld on ({got.get('MINUTES')} min)",
          "│  Starts in Pietato, not EmulationStation (System > EmulationStation opens it)" in t.snaps[2]
          and "│  Leave the handheld on until it says All set" in t.snaps[2] and got.get("GO") == "yes"
          and got.get("MINUTES") == str(W.estimate({"classic", "ps1", "neogeo", "ngp", "link", "cheevos", "office",
                                                    "toys", "computers"}, W.Machine(env))) == "37")

# ---- setup.sh on a pretend R36S, on dArkOS ---------------------------------------------------------------------------
F = SP + "/setupspin/full"
if not ONLY or "setup" in ONLY:
    shutil.rmtree(F + "/repo", ignore_errors=True)
    shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    osr = S + "/os-release"
    open(osr, "w").write('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\nVERSION_ID="13"\n'
                         'VERSION_CODENAME=trixie\nID=debian\n')
    answers = S + "/answers.txt"
    open(answers, "w").write("\nn\n")              # (no Home Assistant; no reboot)
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", HANDHELD_MODE="1",
               PITATO_COMPATIBLE_FILE=R36S + "/compatible", PITATO_MODEL_FILE=R36S + "/model", OS_RELEASE=osr,
               DARKOS_CORES_INIT="mgba snes9x genesis_plus_gx pcsx_rearmed fbneo mednafen_ngp gambatte",
               DARKOS_DEVICE="R36S", STUB_ENABLED="emulationstation", SETUP_STDIN=answers, SETUP_ARGS="--plain",
               SETUP_CONF_INIT="link cheevos toys office computers", EXTRA_BIN=SP + "/setupspin/handbin",
               AFTER="stop.sh|start.sh|uninstall.sh --yes")
    for k in ("GIT_TERMINAL_PROMPT", "PITATO_OS_RELEASE", "PIETATO_SETUP_UI"):
        env.pop(k, None)
    t0 = time.monotonic()
    p = REAL_RUN(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                 capture_output=True, text=True, timeout=1500)
    out = p.stdout + p.stderr
    open(S + "/setup.out", "w").write(out)
    stub = open(F + "/stub.log").read().splitlines() if os.path.exists(F + "/stub.log") else []
    print(f"(setup on a pretend R36S: {time.monotonic() - t0:.0f} s)")

    def report(key):
        mm = re.search(rf"^{re.escape(key)}: (.*)$", out, re.M)
        return mm.group(1) if mm else None

    before = out.split("=== stop.sh")[0]
    steps = {s: out.split(f"=== {s}")[1].split("=== EXIT")[0] if f"=== {s}" in out else ""
             for s in ("stop.sh", "start.sh", "uninstall.sh --yes")}
    marks = stub.index("### stop.sh") if "### stop.sh" in stub else len(stub)
    setup_stub = stub[:marks]
    check(f"setup.sh on an R36S: it says what it's setting up, to the end ({report('SETUP EXIT')})",
          report("SETUP EXIT") == "0" and "Setting up for the R36S: its own screen, buttons and battery, and WiFi "
          "through a USB dongle." in before and "Leave the handheld on until it says All set." in before
          and "GPi Case" not in before)
    check(f"...dArkOS's own emulators, none built here ({report('CORES')})",
          "dArkOS's own emulators play Game Boy, NES, SNES and Genesis games: nothing to install." in before
          and "dArkOS's own PlayStation emulator (PCSX ReARMed) is here already." in before
          and "dArkOS's own Neo Geo emulator (FinalBurn Neo) is here already." in before
          and "dArkOS's own Neo Geo Pocket emulator (Beetle NeoPop) is here already." in before
          and report("CORES") == "[]" and "Building" not in before
          and not any("libretro-" in s for s in setup_stub))
    check("...N64, PSP, DS and Dreamcast games left to dArkOS's EmulationStation, said so (not that they need a Pi 4)",
          all(f"({k} games aren't Pietato's on the R36S: dArkOS's EmulationStation plays them.)" in before
              for k in ("N64", "PSP", "DS", "Dreamcast")) and "need a Pi 4 or 5" not in before
          and "The first time takes a while (about half an hour): dArkOS has most game emulators already." in before)
    check(f"...no config.txt, cmdline.txt or overlays, and NAME.local for the web page ({report('CONFIG')})",
          report("CONFIG") == "[]" and report("GPI OVERLAY") == "[]" and any("avahi-daemon" in s for s in setup_stub))
    check(f"...Pietato in EmulationStation's place, the console on for the terminal ({report('VARLIB')})",
          "systemctl disable emulationstation" in setup_stub and "systemctl enable getty@tty1" in setup_stub
          and "was-emulationstation" in report("VARLIB") and "was-no-console" in report("VARLIB")
          and "The R36S starts in Pietato. System > EmulationStation starts EmulationStation" in before
          and report("AUTOLOGIN") == "[--autologin gpitest]")
    check("...no Loopback card in its kernel: said, and nothing left that fails each start",
          "(This handheld's kernel has no Loopback sound card: the web page's Sound here and Mic here won't work.)"
          in before and "pietato-loopback" not in (report("ETC AFTER") or "") and "modinfo snd-aloop" in setup_stub)
    check(f"...not restarting: Pietato started ({[s for s in setup_stub if 'pitato' in s and 'restart' in s]})",
          "systemctl restart pitato" in setup_stub and "systemctl stop emulationstation" not in setup_stub)
    st = stub[marks:]

    def between(a, b):
        i = st.index(f"### {a}") if f"### {a}" in st else len(st)
        j = st.index(f"### {b}") if b and f"### {b}" in st else len(st)
        return st[i:j]

    stop_, start_, un_ = between("stop.sh", "start.sh"), between("start.sh", "uninstall.sh --yes"), \
        between("uninstall.sh --yes", None)
    check(f"stop.sh: EmulationStation at start-up again, and on now; the console off as dArkOS had it ({stop_})",
          "systemctl --quiet enable emulationstation" in stop_ and "systemctl --quiet disable getty@tty1" in stop_
          and "systemctl --no-block start emulationstation" in stop_
          and "The handheld starts in EmulationStation again." in steps["stop.sh"])
    check(f"start.sh: Pietato in its place again, now ({start_})",
          "systemctl --quiet disable emulationstation" in start_ and "systemctl --quiet enable getty@tty1" in start_
          and "systemctl stop emulationstation" in start_ and "systemctl start pitato" in start_)
    check(f"uninstall.sh: EmulationStation as it was ({un_})",
          "systemctl --quiet enable emulationstation" in un_ and "systemctl --quiet disable getty@tty1" in un_
          and "systemctl --no-block start emulationstation" in un_
          and "The handheld starts in EmulationStation again." in steps["uninstall.sh --yes"])

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
