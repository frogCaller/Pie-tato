"""This Pi: its temperature, throttling and the rest of System's numbers, and WiFi (NetworkManager)."""
import os
import re
import shutil
import socket
import subprocess

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


def system_info():
    rows = []

    def add(label, value, warn=False):
        rows.append(dict(item("sys:" + label, label, "info", "", sub=value), warn=warn))

    t = cpu_temp()
    add("CPU temperature", f"{t:.1f} °C" if t is not None else "unknown",
        t is not None and t >= HOT_C)
    load = os.getloadavg()[0]
    freq = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    add("CPU", f"{min(load * 100 / (os.cpu_count() or 1), 100):.0f}% busy"
        + (f" · {int(freq) // 1000} MHz" if freq.isdigit() else ""))
    text, bad = throttle_text()
    add("Power", text, bad)

    mem = {}
    for line in read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        mem[k] = int(v.split()[0]) * 1024 if v.split() else 0
    if mem.get("MemTotal"):
        used = mem["MemTotal"] - mem.get("MemAvailable", 0)
        add("Memory", f"{human_size(used)} of {human_size(mem['MemTotal'])}")
    du = shutil.disk_usage("/")
    add("Storage", f"{human_size(du.used)} used, {human_size(du.free)} free",
        du.free < 1 << 30)

    link = run_out(["iw", "dev", "wlan0", "link"])
    ssid = re.search(r"SSID: (.+)", link)
    sig = re.search(r"signal: (-?\d+)", link)
    if ssid:
        add("WiFi", ssid.group(1) + (f" · {sig.group(1)} dBm" if sig else ""))
    else:
        q = wifi_quality()
        add("WiFi", "connected" if q else "not connected", not q)
    ips = run_out(["hostname", "-I"]).split()
    add("IP address", ips[0] if ips else "none")
    add("Hostname", socket.gethostname())

    up = read_file("/proc/uptime").split()
    if up:
        s = int(float(up[0]))
        d, h, m = s // 86400, s // 3600 % 24, s // 60 % 60
        add("Up for", (f"{d} d " if d else "") + f"{h} h {m} min")
    model = read_file("/proc/device-tree/model").replace("\x00", "")
    if model:
        add("Board", model)
    osname = re.search(r'PRETTY_NAME="([^"]+)"', read_file("/etc/os-release"))
    add("System", osname.group(1) if osname else "Linux")
    add("Kernel", os.uname().release)

    rows.append(item("act:restart", "Restart media mode", "action", "restart"))
    rows.append(item("act:reboot", "Reboot", "action", "reboot"))
    rows.append(item("act:poweroff", "Shut down", "action", "poweroff"))
    return rows
