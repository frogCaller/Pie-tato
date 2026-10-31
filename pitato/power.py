"""Saving the battery: whether this computer's running on one that the kernel knows of (a laptop's, or a battery HAT
with a driver: the GPi Cases' say nothing, media mode knows those by the case), and Wi-Fi's own power saving, turned
on while the screen rests (Settings > Battery saver)."""
import glob
import os
import re
import shutil
import subprocess

from .system import read_file

POWER_SUPPLY = "/sys/class/power_supply"


def battery_discharging():
    """A battery that runs this computer says it's discharging, and nothing that charges it is plugged in. Not a
    controller's or a mouse's (their batteries are there too, as the computer's devices'). False when there's none."""
    discharging = plugged = False
    for d in glob.glob(os.path.join(POWER_SUPPLY, "*")):
        kind = read_file(os.path.join(d, "type")).strip()
        if read_file(os.path.join(d, "scope")).strip().lower() == "device":
            continue                                   # (a controller's battery, a mouse's)
        if kind == "Battery":
            discharging = discharging or read_file(os.path.join(d, "status")).strip() == "Discharging"
        elif kind in ("Mains", "USB", "USB_C", "USB_PD", "USB_PD_DRP", "Wireless"):
            plugged = plugged or read_file(os.path.join(d, "online")).strip() == "1"
    return discharging and not plugged


def wifi_power_save(dev, on=None):
    """Wi-Fi's power saving (iw), set (on: True or False) or asked (on: None): how it was, True or False, or None when
    there's no telling (no iw, no Wi-Fi)."""
    iw = shutil.which("iw")
    if not iw or not dev:
        return None
    try:
        out = subprocess.run([iw, "dev", dev, "get", "power_save"], capture_output=True, text=True, timeout=3,
                             stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Power save:\s*(on|off)", out)
    if not m:
        return None
    was = m.group(1) == "on"
    if on is not None and on != was:
        try:
            subprocess.run([iw, "dev", dev, "set", "power_save", "on" if on else "off"], capture_output=True,
                           timeout=3, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return was
