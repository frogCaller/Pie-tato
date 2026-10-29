"""This Pi: its temperature, throttling and the rest of System's numbers, and WiFi (NetworkManager)."""
import collections
import os
import re
import shutil
import socket
import subprocess
import time

from .util import human_size, item


# ---- WiFi: NetworkManager (Raspberry Pi OS Bookworm), through nmcli -------------------
def nm(args, timeout=20):
    """(ok, output, error) from nmcli."""
    try:
        r = subprocess.run(["nmcli"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr.strip()
    except FileNotFoundError:
        return False, "", "nmcli isn't installed (NetworkManager)"
    except subprocess.TimeoutExpired:
        return False, "", "it took too long"


def nm_fields(line):
    """nmcli -t splits fields with ':' and writes a ':' inside one as '\\:'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def wifi_saved():
    """SSID -> the saved profile's name (a profile can be named differently from its network)."""
    ok, out, _ = nm(["-t", "-f", "NAME,TYPE", "connection", "show"], 10)
    saved = {}
    for line in out.splitlines() if ok else []:
        f = nm_fields(line)
        if len(f) >= 2 and f[1] == "802-11-wireless":
            ok2, ssid, _ = nm(["-g", "802-11-wireless.ssid", "connection", "show", f[0]], 10)
            saved[(ssid.strip() if ok2 and ssid.strip() else f[0])] = f[0]
    return saved


def wifi_scan():
    """The networks around, strongest first: [{ssid, signal, secure, active}]."""
    ok, out, err = nm(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], 30)
    if not ok:                                      # scanned a moment ago: take what it has
        ok, out, err = nm(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"], 20)
    if not ok:
        raise ValueError(err or "Can't scan for WiFi")
    nets = {}
    for line in out.splitlines():
        f = nm_fields(line)
        if len(f) < 4 or not f[1].strip():
            continue                                # hidden networks have no name
        ssid = f[1]
        sig = int(f[2]) if f[2].isdigit() else 0
        net = {"ssid": ssid, "signal": sig, "secure": f[3].strip() not in ("", "--"),
               "active": f[0].strip() == "*"}
        old = nets.get(ssid)
        if not old or net["active"] or (sig > old["signal"] and not old["active"]):
            nets[ssid] = net
    return sorted(nets.values(), key=lambda n: (not n["active"], -n["signal"]))


def nm_why(err):
    e = err.lower()
    if "secrets were required" in e or "802-1x" in e or "password" in e and "invalid" in e:
        return "Wrong password?"
    if "no network with ssid" in e:
        return "That network isn't in range"
    if "timeout" in e or "too long" in e:
        return "It took too long"
    return err.split("\n")[-1][:70] or "Couldn't connect"


HOT_C = 70                                     # status bar warns above this
SLOW_EVERY = 10.0      # seconds: what takes a program to find out (power, WiFi, the address) is looked at this often
PROC_STAT = "/proc/stat"   # how long the CPU's spent working, and not, since the Pi started
_cpu_was = None        # /proc/stat's CPU line when System last looked: (busy, all, when)
_slow = {}             # what took a program to find out: name -> (when, what it said)
HISTORY_EVERY = 10.0   # seconds: System's dashboard has how busy the CPU was, and how hot, a look this often...
HISTORY_KEEP = 30      # ...for the last this many looks (5 minutes)


def system_stopping():
    """True while the Pi is shutting down or restarting."""
    try:
        out = subprocess.run(["systemctl", "is-system-running"], capture_output=True, text=True,
                             timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out == "stopping"


# ---- system readings ------------------------------------------------------------
def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def run_out(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def cpu_temp():
    t = read_file("/sys/class/thermal/thermal_zone0/temp")
    return int(t) / 1000 if t.isdigit() else None


def wifi_quality():
    """0-70 link quality from /proc/net/wireless, or None when not connected."""
    for line in read_file("/proc/net/wireless").splitlines()[2:]:
        parts = line.split()
        if parts and parts[0].startswith("wl"):
            try:
                return float(parts[2].rstrip("."))
            except (IndexError, ValueError):
                return None
    return None


def wifi_bars(q):
    if q is None or q <= 0:
        return 0
    return 4 if q >= 55 else 3 if q >= 40 else 2 if q >= 25 else 1


def cpu_ticks():
    """How long the CPU's spent working since the Pi started, and how long altogether (/proc/stat's ticks, all its
    cores), or None."""
    try:
        with open(PROC_STAT) as f:
            ticks = [int(x) for x in f.readline().split()[1:9]]   # user nice system idle iowait irq softirq steal
    except (OSError, ValueError):
        return None
    if len(ticks) < 4:
        return None
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)       # (idle, or waiting for the SD card)
    return sum(ticks) - idle, sum(ticks)


def cpu_busy():
    """How busy the CPU's been since System last looked (a few seconds ago), as a share of all its cores, in percent:
    None the first time, with nothing to go by. (The load average, which it showed before, counts what's waiting
    as well as what's working, so it said 100% when the CPU wasn't.)"""
    global _cpu_was
    ticks = cpu_ticks()
    if ticks is None:
        return None
    now, was = time.monotonic(), _cpu_was
    _cpu_was = (ticks[0], ticks[1], now)
    if not was or now - was[2] > 30 or _cpu_was[1] <= was[1]:
        return None
    return max(0.0, min(100.0, 100.0 * (_cpu_was[0] - was[0]) / (_cpu_was[1] - was[1])))


class SysHistory:
    """How busy the CPU was and how hot it was, over the last few minutes, for System's dashboard's charts: a look
    every 10 seconds, whatever's on the screen (two small files: nothing to speak of, even on a Pi Zero). Its own
    count of the CPU's time, apart from System's other numbers. samples: (when (time.monotonic(): the clock set
    at start-up doesn't move them), % busy or None, °C or None)."""

    def __init__(self, every=HISTORY_EVERY, keep=HISTORY_KEEP):
        self.every = every
        self.samples = collections.deque(maxlen=keep)
        self.next = 0.0
        self.was = None                                # (cpu_ticks() at the last look)

    def tick(self, now):
        """A look, if it's time (now: time.monotonic()). True when there was one."""
        if now < self.next:
            return False
        self.next = now + self.every
        ticks, busy = cpu_ticks(), None
        if ticks and self.was and ticks[1] > self.was[1]:
            busy = max(0.0, min(100.0, 100.0 * (ticks[0] - self.was[0]) / (ticks[1] - self.was[1])))
        first = self.was is None
        self.was = ticks
        if not first:                                  # (the first look: nothing to go by yet)
            self.samples.append((now, busy, cpu_temp()))
        return True


def now_and_then(name, look, every=SLOW_EVERY):
    """look(), or what it said less than every seconds ago (System's numbers are looked at every few seconds)."""
    when, what = _slow.get(name, (None, None))
    now = time.monotonic()
    if when is None or now - when >= every:
        what = look()
        _slow[name] = (now, what)
    return what


def throttle_text():
    out = run_out(["vcgencmd", "get_throttled"])
    m = re.search(r"0x([0-9a-fA-F]+)", out)
    if not m:
        return "unknown", False
    v = int(m.group(1), 16)
    now = [t for bit, t in ((0, "low power"), (1, "speed capped"), (2, "throttled"),
                            (3, "temperature limit")) if v & (1 << bit)]
    if now:
        return "Now: " + ", ".join(now), True
    if v & 0xF0000:
        return "OK (low power earlier)", False
    return "OK", False


def system_numbers(background=()):
    """This Pi's numbers now, for System (its list's rows and its dashboard): a dict. background: what Pietato's busy
    with, [(what, how far)]. busy: how busy the CPU's been since the last look (None the first time); WiFi, the
    address and power are looked at every 10 seconds."""
    n = {"background": list(background), "temp": cpu_temp(), "busy": cpu_busy()}
    freq = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    n["mhz"] = int(freq) // 1000 if freq.isdigit() else None
    n["power"] = now_and_then("power", throttle_text)
    mem = {}
    for line in read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        mem[k] = int(v.split()[0]) * 1024 if v.split() else 0
    n["mem"] = (mem["MemTotal"] - mem.get("MemAvailable", 0), mem["MemTotal"]) if mem.get("MemTotal") else None
    du = shutil.disk_usage("/")
    n["disk"] = (du.used, du.free, du.total)
    link = now_and_then("wifi", lambda: run_out(["iw", "dev", "wlan0", "link"]))
    ssid = re.search(r"SSID: (.+)", link)
    sig = re.search(r"signal: (-?\d+)", link)
    n["ssid"] = ssid.group(1) if ssid else None
    n["dbm"] = int(sig.group(1)) if ssid and sig else None
    n["wifi_q"] = None if ssid else wifi_quality()
    ips = now_and_then("ip", lambda: run_out(["hostname", "-I"])).split()
    n["ip"] = ips[0] if ips else None
    n["host"] = socket.gethostname()
    up = read_file("/proc/uptime").split()
    n["up"] = int(float(up[0])) if up else None
    n["board"] = read_file("/proc/device-tree/model").replace("\x00", "")
    osname = re.search(r'PRETTY_NAME="([^"]+)"', read_file("/etc/os-release"))
    n["os"] = osname.group(1) if osname else "Linux"
    n["kernel"] = os.uname().release
    return n


def uptime_text(s):
    """How long it's been up: "2 d 3 h 4 min"."""
    d, h, m = s // 86400, s // 3600 % 24, s // 60 % 60
    return (f"{d} d " if d else "") + f"{h} h {m} min"


def system_info(background=(), nums=None):
    """System's rows: this Pi's numbers (background: what Pietato's busy with, [(what, how far)], said under how busy
    the CPU is), then its buttons. nums: system_numbers(), looked at already (background's in them)."""
    n = system_numbers(background) if nums is None else nums
    rows = []

    def add(label, value, warn=False):
        rows.append(dict(item("sys:" + label, label, "info", "", sub=value), warn=warn))

    t = n["temp"]
    add("CPU temperature", f"{t:.1f} °C" if t is not None else "unknown",
        t is not None and t >= HOT_C)
    busy = n["busy"]
    add("CPU", (f"{busy:.0f}% busy" if busy is not None else "…")
        + (f" · {n['mhz']} MHz" if n["mhz"] is not None else ""))
    for what, far in n["background"]:
        add(what, far)
    text, bad = n["power"]
    add("Power", text, bad)
    if n["mem"]:
        used, total = n["mem"]
        add("Memory", f"{human_size(used)} of {human_size(total)}")
    used, free, _ = n["disk"]
    add("Storage", f"{human_size(used)} used, {human_size(free)} free",
        free < 1 << 30)
    if n["ssid"]:
        add("WiFi", n["ssid"] + (f" · {n['dbm']} dBm" if n["dbm"] is not None else ""))
    else:
        q = n["wifi_q"]
        add("WiFi", "connected" if q else "not connected", not q)
    add("IP address", n["ip"] or "none")
    add("Hostname", n["host"])
    if n["up"] is not None:
        add("Up for", uptime_text(n["up"]))
    if n["board"]:
        add("Board", n["board"])
    add("System", n["os"])
    add("Kernel", n["kernel"])

    rows.append(item("act:restart", "Restart media mode", "action", "restart"))
    rows.append(item("act:reboot", "Reboot", "action", "reboot"))
    rows.append(item("act:poweroff", "Shut down", "action", "poweroff"))
    return rows
