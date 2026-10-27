"""The RetroFlag GPi Case this Pi is in, as setup.sh set it up (its part of config.txt says which): the 2W (a Pi
Zero 2 W), or the GPi Case 2 (a Compute Module 4). The GPi Case 2's dock puts the picture on a TV: which one is
picked as the Pi starts (config.txt's [gpio18=0] and [gpio18=1] parts: GPIO 18 is high in the dock with the TV on),
and put in the dock or taken out while it's on, the Pi restarts with the picture where it should be (media mode's
dock_tick)."""
import json
import os
import re
import subprocess
import threading
import time

from .config import STATE_FILE

CONFIG_TXT = ("/boot/firmware/config.txt", "/boot/config.txt")
BLOCK_START, BLOCK_END = "# >>> gpi-case setup >>>", "# <<< gpi-case setup <<<"   # setup.sh's part of config.txt
CASE2_MARK = "# GPi Case 2 (CM4)"            # ...the GPi Case 2's starts with this
DOCK_PIN = 18                  # high in the dock with the TV on (as RetroFlag's own script reads it)
DOCK_EVERY = 1.0               # seconds between looks at it
DOCK_SETTLE_IN = 5.0           # high that long (seconds): in the dock, on to the TV
DOCK_SETTLE_OUT = 15.0         # low that long: out of the dock (or the TV off): back to the case's screen. Longer, as a
                               # TV changing input or going to sleep can drop the line for a moment
DOCK_QUIET = 60.0              # nothing in the first minute after media mode starts (a TV finding the picture)
DOCK_WINDOW, DOCK_MOST = 600.0, 2   # at most this many restarts for the dock in that many seconds: then it isn't
                                    # followed till media mode starts again (a TV that drops the line as the Pi starts)
DOCK_FILE = os.path.join(os.path.dirname(STATE_FILE), "dock-restart.json")   # restarts for the dock: where to, when
DEVICE_TREE = "/proc/device-tree"
DPKG_LOCKS = ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock")
PROC_LOCKS = "/proc/locks"


def config_text():
    """config.txt, as it is: Bookworm's place for it, then an older system's ("" with neither)."""
    for path in CONFIG_TXT:
        try:
            with open(path, errors="ignore") as f:
                return f.read()
        except OSError:
            continue
    return ""


def case_kind(text=None):
    """"2" (the GPi Case 2), "2w" (the GPi Case 2W), or None (neither): as setup.sh set the Pi up."""
    text = config_text() if text is None else text
    if BLOCK_START not in text:
        return None
    block = text.split(BLOCK_START, 1)[1].split(BLOCK_END, 1)[0]
    return "2" if CASE2_MARK in block else "2w"


def run_out(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pin_level(pin=DOCK_PIN):
    """A GPIO pin's level now: True (high), False (low), or None (no telling: neither pinctrl nor raspi-gpio)."""
    m = re.search(r"\|\s*(hi|lo)\b", run_out(["pinctrl", "get", str(pin)]))        # 18: ip    pd | hi // GPIO18 = input
    if m:
        return m.group(1) == "hi"
    m = re.search(r"\blevel=([01])\b", run_out(["raspi-gpio", "get", str(pin)]))   # GPIO 18: level=1 fsel=0 ...
    if m:
        return m.group(1) == "1"
    return None


def firmware_kms():
    """True with fkms (the firmware's screen, which the GPi Case 2's own screen is), False with KMS (the TV), None
    with neither found."""
    for root, dirs, files in os.walk(DEVICE_TREE):
        for d in dirs:
            if d.startswith("firmwarekms@"):
                try:
                    with open(os.path.join(root, d, "status"), "rb") as f:
                        return f.read().rstrip(b"\x00").strip() in (b"okay", b"ok")
                except OSError:
                    return True                       # (a node without a status is on)
        if root.count(os.sep) - DEVICE_TREE.count(os.sep) >= 1:
            dirs[:] = []                              # (it's at the top, or in soc)
    return None


def started_on_tv():
    """Where the picture is since the Pi started: on the TV (True), the case's screen (False), or no telling (None).
    The case's screen is the firmware's (config.txt's [gpio18=0] part turns it on, with fkms)."""
    m = re.search(r"enable_dpi_lcd=(\d+)", run_out(["vcgencmd", "get_config", "enable_dpi_lcd"]))
    if m:
        return m.group(1) == "0"
    fkms = firmware_kms()
    return None if fkms is None else not fkms


class DockWatch:
    """The dock's pin, looked at every DOCK_EVERY by a thread of its own (pinctrl takes a moment): its level (True,
    False, or None: no telling) and since when (monotonic)."""

    def __init__(self, read=pin_level, every=DOCK_EVERY):
        self.read, self.every = read, every
        self.level, self.since = None, time.monotonic()
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="dock")
        self.thread.start()

    def run(self):
        while not self.done.is_set():
            try:
                level = self.read()
            except Exception as ex:                    # (never stops for good)
                print(f"dock: {ex!r}", flush=True)
                level = None
            with self.lock:
                if level != self.level:
                    self.level, self.since = level, time.monotonic()
            self.done.wait(self.every)

    def settled(self, now, settle=DOCK_SETTLE_IN):
        """The pin's level once it's stayed so for settle seconds; else None."""
        with self.lock:
            return self.level if self.level is not None and now - self.since >= settle else None

    def stop(self):
        self.done.set()


def dock_tried():
    """The restart before this start-up, if it was for the dock: (where it was for, "tv" or "case"; when each of the
    latest restarts for it was, by the clock), else (None, []). Asked once: it's forgotten as it's told."""
    try:
        with open(DOCK_FILE) as f:
            got = json.load(f)
        to, times = got.get("to"), [float(t) for t in got.get("times", [])]
    except (OSError, ValueError, AttributeError, TypeError):
        to, times = None, []
    try:
        os.remove(DOCK_FILE)
    except OSError:
        pass
    return (to if to in ("tv", "case") else None), times


def note_dock_restart(to, times):
    """A restart for the dock, about to happen: noted (where to, and when this and the latest ones were), so the next
    start-up can tell if it took, and how often it's happened."""
    try:
        os.makedirs(os.path.dirname(DOCK_FILE), exist_ok=True)
        with open(DOCK_FILE, "w") as f:
            json.dump({"to": to, "times": list(times)}, f)
    except OSError as ex:
        print(f"dock: couldn't note the restart ({ex})", flush=True)


def busy():
    """What the Pi mustn't be restarted in the middle of, in words, or None: a shutdown held off (setup.sh holds one
    while it works), or apt or dpkg putting packages in (their lock held)."""
    out = run_out(["busctl", "--json=short", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
                   "org.freedesktop.login1.Manager", "ListInhibitors"], timeout=5)
    try:
        for row in json.loads(out)["data"][0]:          # [what, who, why, mode, uid, pid]
            if row[3] == "block" and "shutdown" in str(row[0]).split(":"):
                return row[1] or "a program"
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    held = set()
    try:
        with open(PROC_LOCKS) as f:                   # 1: POSIX  ADVISORY  WRITE 2349 b3:02:262410 0 EOF
            for line in f:
                m = re.search(r"\s([0-9a-f]+):([0-9a-f]+):(\d+)\s", line)
                if m:
                    held.add((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3))))
    except OSError:
        return None
    for lock in DPKG_LOCKS:
        try:
            st = os.stat(lock)
        except OSError:
            continue
        if (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino) in held:
            return "apt"
    return None
