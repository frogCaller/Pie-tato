"""RK3326 handhelds on dArkOS (Debian's ArkOS): the R36S and its kind (the R33S, R35S, RG351MP, G350, A10 Mini) and
the Odroid Go Advance and Super (and the RGB10). Told from a Pi or a PC by the device tree as Pietato starts (its
compatible list names the chip), and what's their own: the built-in gamepad, its buttons as they're printed on it; the
640x480 screen; the battery, and the CPU's and GPU's temperatures, from /sys; WiFi through a USB dongle (there's none
built in: NetworkManager takes one when it's plugged in). What's a Pi's own (config.txt, vcgencmd, the GPi Case, the
Pi camera, HDMI's modes) isn't there, and dArkOS's own EmulationStation is a System action away."""
import glob
import os
import re

DEVICE_TREE = "/proc/device-tree"
CHIPS = {"rockchip,rk3326": "rk3326"}         # a compatible entry -> the handheld's chip
DARKOS_NAME = "/home/*/.config/.DEVICE"       # what dArkOS's image calls it ("RG351MP", "R36S"), for its name only
POWER_SUPPLY = "/sys/class/power_supply"
THERMAL = "/sys/class/thermal"
NET = "/sys/class/net"
ES_UNITS = ("/etc/systemd/system/emulationstation.service", "/lib/systemd/system/emulationstation.service",
            "/usr/lib/systemd/system/emulationstation.service")   # dArkOS's own front end, as a service
NAMED = re.compile(r"\b(R3\dS|RG351[A-Z]*|RGB10[A-Z]*|G350|A10 Mini)\b", re.I)   # a model that says what it is

# the built-in gamepads (as the kernel's joypad drivers name them), their buttons as they're printed on them: A the
# one on the right (BTN_EAST), as on a GPi Case or a Nintendo pad, B below it; the d-pad's buttons; and the F buttons
# as the device tree has them (BTN_TRIGGER_HAPPY1 is F1). The GO-Super Gamepad's (the R36S, RG351MP, G350, A10 Mini):
# F1 SELECT, F2 START, F3 and F4 the sticks' clicks, F5 the FN button, HOME. The GO-Advance's (an Odroid Go Advance,
# the RGB10): the row under the screen, F1 SELECT and F6 START, F5 HOME. The sticks are the usual ABS_X, ABS_Y, ABS_RX
# and ABS_RY. (evdev's names: evdev's numbers for them only once a gamepad's there, so the rest needs no evdev.)
FACE = {"BTN_EAST": "a", "BTN_SOUTH": "b", "BTN_NORTH": "x", "BTN_WEST": "y", "BTN_TL": "l", "BTN_TR": "r",
        "BTN_TL2": "l2", "BTN_TR2": "r2", "BTN_DPAD_UP": "up", "BTN_DPAD_DOWN": "down", "BTN_DPAD_LEFT": "left",
        "BTN_DPAD_RIGHT": "right"}
F = "BTN_TRIGGER_HAPPY"                       # F1 is BTN_TRIGGER_HAPPY1, ... F6 BTN_TRIGGER_HAPPY6
GO_SUPER = {**FACE, F + "1": "select", F + "2": "start", F + "5": "home"}
GO_ADVANCE = {**FACE, F + "1": "select", F + "6": "start", F + "5": "home"}
GAMEPADS = {"GO-Super Gamepad": GO_SUPER, "GO-Advance Gamepad": GO_ADVANCE, "GO-Advance Gamepad (rev 1.1)": GO_ADVANCE}

_found = {}


def read(path, default=""):
    """A file's words (a device tree's NULs as new lines), or default."""
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").replace("\0", "\n").strip()
    except OSError:
        return default


def detect(tree=None):
    """This machine, from its device tree: {"chip": "rk3326", "model": ..., "name": ...} for an RK3326 handheld, None
    for anything else (a Pi's tree names a Broadcom chip; a PC has none)."""
    tree = tree or DEVICE_TREE
    compatible = [c.strip() for c in read(os.path.join(tree, "compatible")).split("\n") if c.strip()]
    chip = next((CHIPS[c] for c in compatible if c in CHIPS), None)
    if not chip:
        return None
    model = " ".join(read(os.path.join(tree, "model")).split())
    return {"chip": chip, "model": model, "name": nice_name(model)}


def nice_name(model):
    """What to call it: what its model says it is ("R36S"); else what dArkOS's image calls it (its RG351MP image,
    which an R36S runs too, has Hardkernel's ODROID-GO3 for a model); else "RK3326 handheld"."""
    m = NAMED.search(model or "")
    if m:
        return m.group(1).upper().replace("A10 MINI", "A10 Mini")
    for path in sorted(glob.glob(DARKOS_NAME)):
        word = read(path).split("\n")[0].strip()
        if re.fullmatch(r"[A-Za-z0-9 ._-]{2,24}", word):
            return word
    return "RK3326 handheld"


def profile():
    """This machine's handheld profile (detect's, worked out once, as Pietato starts), or None: a Pi, a PC."""
    if "it" not in _found:
        _found["it"] = detect()
    return _found["it"]


def is_handheld():
    return profile() is not None


def name():
    p = profile()
    return p["name"] if p else ""


def gamepad_codes(dev_name):
    """The built-in gamepad's buttons (evdev's code -> Pietato's button) when this is one; None for any other
    controller."""
    if dev_name not in GAMEPADS or not is_handheld():
        return None
    from evdev import ecodes                       # (here: what's said and the web page need no evdev)
    return {getattr(ecodes, code): button for code, button in GAMEPADS[dev_name].items()}


def battery(supply=None):
    """Its own battery: (percent, charging), or None when there's no reading. Charging: it's charging, or full on the
    charger."""
    for d in sorted(glob.glob(os.path.join(supply or POWER_SUPPLY, "*"))):
        if read(os.path.join(d, "type")) != "Battery" or read(os.path.join(d, "scope")).lower() == "device":
            continue                                   # (a controller's battery, a mouse's)
        try:
            percent = max(0, min(100, int(read(os.path.join(d, "capacity")))))
        except ValueError:
            continue
        return percent, read(os.path.join(d, "status")) in ("Charging", "Full")
    return None


def temperatures(thermal=None):
    """[(what, °C)]: the CPU's and the GPU's, as the kernel's thermal zones read them (soc-thermal, gpu-thermal)."""
    out = []
    zones = glob.glob(os.path.join(thermal or THERMAL, "thermal_zone*"))
    for zone in sorted(zones, key=lambda z: int(re.sub(r"\D", "", os.path.basename(z)) or 0)):
        kind = read(os.path.join(zone, "type")).lower()
        what = "CPU" if kind.startswith(("soc", "cpu")) else "GPU" if kind.startswith("gpu") else None
        try:
            c = int(read(os.path.join(zone, "temp"))) / 1000.0
        except ValueError:
            continue
        if what and what not in dict(out) and -40 < c < 150:
            out.append((what, c))
    return out


def wifi_adapter(net=None):
    """The USB WiFi dongle's network interface (wlan0), or None while there's none plugged in."""
    found = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(net or NET, "*", "wireless")))
    return found[0] if found else None


def has_emulationstation():
    """dArkOS's EmulationStation is here to start (System > EmulationStation)."""
    return is_handheld() and any(os.path.exists(u) for u in ES_UNITS)
