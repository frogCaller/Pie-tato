"""Bluetooth: your controllers, keyboards, headphones and the rest, found, paired and connected.

BlueZ does it. What's there, and each thing asked of it (pair, connect, forget, on and off), go through busctl:
BlueZ's D-Bus, read as busctl prints it. Looking round, and pairing's questions (a keyboard's code to type in, a yes or
no), go through a bluetoothctl kept open meanwhile, as BlueZ's agent. Settings > Bluetooth and the web page work
it, and it looks at Bluetooth only while one of them is open."""
import codecs
import os
import pty
import re
import select
import shutil
import subprocess
import threading
import time

from .config import clean_name
from .screen import bt_outputs

BT_LOOK = 60            # seconds a look round lasts (X, or Find devices, looks again)
BT_EVERY = 2.5          # seconds between looks at what's there, while a page shows it
BT_WEB = 10             # the web page's interest lasts this long after it last asked
BT_KEEP = 90            # a device nearby stays on the list this long after it was last heard
BT_PAIR = 45            # seconds pairing may take (a keyboard's code typed in, too)
BT_CONNECT = 25         # ...and connecting
BT_NEAR = 24            # devices nearby shown, at most (the nearest)
BT_SUMMARY = 20         # Settings' first page: what's connected, looked at again after this long
BT_READY = 3.0          # seconds bluetoothctl has to start, before it's asked to look anyway
BT_SOUND_UP = 6.0       # seconds headphones have, once connected, for their sound to come up (BlueALSA's)
BT_STALE = 15           # seconds BlueZ may not answer (a look now and then that fails: the list stays) before it's said
BT_GONE = ("not provided by", "ServiceUnknown", "NameHasNoOwner", "not activatable", "Failed to activate service",
           "dbus-org.bluez.service")       # (busctl's words for no BlueZ to ask)
BUS_WORD = re.compile(r'"((?:[^"\\]|\\.)*)"|(\S+)')
BUS_ESC = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, '"': 34, "'": 39}
BUS = "org.bluez"
DEV = "org.bluez.Device1"
ADAPTER = "org.bluez.Adapter1"
ADDR = re.compile(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Za-z0-9]|\x1b[=>]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
KINDS = {"input-gaming": "controller", "input-keyboard": "keyboard", "input-mouse": "mouse",
         "input-tablet": "mouse", "audio-headset": "headphones", "audio-headphones": "headphones",
         "audio-card": "speaker", "multimedia-player": "speaker", "phone": "phone", "computer": "computer",
         "video-display": "tv", "camera-video": "camera", "camera-photo": "camera", "printer": "printer"}
NAMED = [   # (what's in its name, what it is): for one that doesn't say what it is
    (re.compile(r"controller|gamepad|game ?pad|joy-?con|8bitdo|dualshock|dualsense|xbox|\bpad\b|stadia|"
                r"gamesir|nimbus|ipega|moga", re.I), "controller"),
    (re.compile(r"keyboard|\bkeys\b|\bk\d{3}\b|keychron", re.I), "keyboard"),
    (re.compile(r"mouse|trackpad|trackball", re.I), "mouse"),
    (re.compile(r"buds|airpods|headphone|headset|earbud|earphone|\bwh-|\bwf-|beats", re.I), "headphones"),
    (re.compile(r"speaker|soundlink|soundcore|\bjbl\b|boom|sonos|soundbar", re.I), "speaker"),
]
KIND_WORDS = {"controller": "Controller", "keyboard": "Keyboard", "mouse": "Mouse", "headphones": "Headphones",
              "speaker": "Speaker", "phone": "Phone", "computer": "Computer", "tv": "TV", "camera": "Camera",
              "printer": "Printer"}
SOUND_KINDS = ("headphones", "speaker")
QUESTIONS = [(re.compile(r"\(yes/no\):?\s*$"), "yes"),            # pair with it, let it in: yes (you asked)
             (re.compile(r"Enter PIN code:?\s*$"), "0000"),       # an old one's PIN: most take 0000
             (re.compile(r"Enter passkey[^:]*:?\s*$"), "0")]      # (one with a code of its own to type: rare)
CODE = re.compile(r"\[agent\] (?:Passkey|PIN code): ([0-9A-Za-z]{1,16})")


def bt_kind(icon, name):
    """What a device is (controller, keyboard, headphones...): what BlueZ makes of it, or else its name."""
    kind = KINDS.get(str(icon or ""))
    if kind:
        return kind
    for pattern, what in NAMED:
        if pattern.search(name or ""):
            return what
    return ""


def bt_why(err, doing="pair"):
    """BlueZ's error, in words."""
    e = str(err or "").lower()
    if "authentication" in e or "rejected" in e or "canceled" in e or "cancelled" in e:
        return "It didn't pair. Put it in pairing mode, and try again"
    if any(w in e for w in ("page timeout", "attempt failed", "host is down", "timed out", "timeout", "no reply",
                            "connection refused", "abort", "input/output error")):
        return ("It didn't answer. Is it in pairing mode, and close by?" if doing == "pair"
                else "It didn't answer. Is it on, and close by?")
    if "profile-unavailable" in e or "protocol not available" in e or "not supported" in e:
        return "The Pi has nothing it can connect it to"
    if "does not exist" in e or "unknown object" in e or "not available" in e:
        return "It's gone. Look again"
    if "in progress" in e or "busy" in e:
        return "It's busy. Try again in a moment"
    if "blocked" in e or "rfkill" in e:
        return "Bluetooth is switched off on this Pi"
    if "not ready" in e or "not powered" in e:
        return "Bluetooth isn't on"
    words = str(err or "").strip().splitlines()
    return f"It didn't work ({words[-1][:48]})" if words else "It didn't work"


def bus(args, timeout=10):
    """busctl, asking BlueZ: (ok, what it said, its error)."""
    try:
        r = subprocess.run(["busctl"] + args, capture_output=True, text=True, timeout=timeout + 5)
    except FileNotFoundError:
        return False, "", "busctl isn't here"
    except subprocess.TimeoutExpired:
        return False, "", "timed out"
    except OSError as ex:
        return False, "", str(ex)
    if r.returncode != 0:
        lines = (r.stderr or r.stdout or "").strip().splitlines()
        err = lines[-1] if lines else "failed"
        if err.startswith("Call failed: "):
            err = err[len("Call failed: "):]
        elif err.startswith("Failed to") and ": " in err:      # (Failed to set property Powered on ...: why)
            err = err.rsplit(": ", 1)[1]
        return False, r.stdout, err
    return True, r.stdout, ""


def bus_unescape(s):
    """A string as busctl prints it (C's escapes, and each byte that isn't plain ASCII in octal), as text."""
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            digits = s[i + 1:i + 4]
            if len(digits) == 3 and all(ch in "01234567" for ch in digits):
                out.append(int(digits, 8) & 0xFF)
                i += 4
                continue
            if s[i + 1] in BUS_ESC:
                out.append(BUS_ESC[s[i + 1]])
                i += 2
                continue
        out += c.encode()
        i += 1
    return out.decode("utf-8", "replace")


def bus_type_end(sig, i=0):
    """Where the D-Bus type that starts at sig[i] ends."""
    c = sig[i]
    if c == "a":
        return bus_type_end(sig, i + 1)
    if c in "({":
        close, i = ")" if c == "(" else "}", i + 1
        while sig[i] != close:
            i = bus_type_end(sig, i)
        return i + 1
    return i + 1


def bus_types(sig):
    """A signature's types, one by one ("sa{sv}": "s", "a{sv}")."""
    out, i = [], 0
    while i < len(sig):
        j = bus_type_end(sig, i)
        out.append(sig[i:j])
        i = j
    return out


def bus_reply(text):
    """A call's reply as busctl prints it without --json (its signature, then each value, the way busctl takes them
    itself): (signature, [values]), a variant as {"type": ..., "data": ...} as --json has it. (--json can't do
    BlueZ's devices once it looks round: numbers key their makers' data, JSON's keys are words, and busctl gives up.)"""
    words = BUS_WORD.finditer(text)

    def word():
        m = next(words, None)
        if m is None:
            raise ValueError("busctl's reply ended early")
        return bus_unescape(m.group(1)) if m.group(1) is not None else m.group(2)

    def value(t):
        c = t[0]
        if c == "a":
            n, inner = int(word()), t[1:]
            if inner[0] == "{":
                k, v = bus_types(inner[1:-1])
                d = {}
                for _ in range(n):
                    key = value(k)
                    d[key] = value(v)
                return d
            return [value(inner) for _ in range(n)]
        if c == "v":
            sig = word()
            return {"type": sig, "data": value(sig)}
        if c == "(":
            return [value(m) for m in bus_types(t[1:-1])]
        w = word()
        if c == "b":
            return w == "true"
        if c == "d":
            return float(w)
        if c in "ynqiuxth":
            return int(w)
        return w                                       # (s, o, g)

    sig = word()
    return sig, [value(t) for t in bus_types(sig)]


def prop(props, key, default=None):
    """One of a D-Bus object's properties, from busctl ({"type": "b", "data": true})."""
    v = props.get(key) if isinstance(props, dict) else None
    return v.get("data", default) if isinstance(v, dict) else default


class Agent:
    """bluetoothctl, kept open while a page shows Bluetooth: it looks round (scan on), and as BlueZ's agent it
    says yes to pairing's questions, and passes on a keyboard's code to type in."""

    def __init__(self, on_code=None, on_said=None):
        self.lock = threading.Lock()
        self.proc = None
        self.fd = None
        self.ready = threading.Event()
        self.scanning = False         # (what it was last asked)
        self.on_code = on_code or (lambda code: None)
        self.on_said = on_said or (lambda line: None)
        self.answered = {}            # a question -> when it was answered (each, once)
        self.lines = []               # its last lines (what went wrong, for one)

    def alive(self):
        p = self.proc
        return p is not None and p.poll() is None

    def start(self):
        """Running (True), or it can't be (no bluetoothctl)."""
        with self.lock:
            if self.alive():
                return True
            self.scanning = False
            self.ready.clear()
            try:
                master, slave = pty.openpty()          # (a terminal of its own: it says everything as it happens)
            except OSError:
                return False
            try:
                proc = subprocess.Popen(["bluetoothctl"], stdin=slave, stdout=slave, stderr=slave,
                                        env=dict(os.environ, TERM="dumb"), start_new_session=True, close_fds=True)
            except OSError:
                os.close(master)
                os.close(slave)
                return False
            os.close(slave)
            self.proc, self.fd = proc, master
        threading.Thread(target=self.read_loop, args=(proc, master), daemon=True, name="bt-agent").start()
        return True

    def wait_ready(self, secs=BT_READY):
        return self.ready.wait(secs)

    def send(self, line):
        with self.lock:
            if self.fd is None or not self.alive():
                return False
            try:
                os.write(self.fd, (line + "\n").encode())
                return True
            except OSError:
                return False

    def scan(self, on):
        """Looking round, or not."""
        if self.send("scan on" if on else "scan off"):
            self.scanning = on

    def stop(self):
        with self.lock:
            proc, fd = self.proc, self.fd
            self.proc = self.fd = None
            self.scanning = False
            self.ready.clear()
            if proc is None or proc.poll() is not None:
                return
            for line in ("scan off", "quit"):
                try:
                    os.write(fd, (line + "\n").encode())
                except OSError:
                    break
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(2)
                except subprocess.TimeoutExpired:
                    pass

    def read_loop(self, proc, fd):
        """What it says, a line at a time; and a question waiting at the end of what it's said (no line break
        after it), answered."""
        raw, text = "", codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                try:
                    r, _, _ = select.select([fd], [], [], 1.0)
                except (OSError, ValueError):
                    break
                if not r:
                    if proc.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(fd, 4096)
                except OSError:                        # (EIO: it's ended)
                    break
                if not chunk:
                    break
                raw += text.decode(chunk)
                *lines, raw = re.split(r"[\r\n]", raw)
                for line in lines:
                    self.heard(ANSI.sub("", line).strip())
                raw = raw[-400:]
                self.asked(ANSI.sub("", raw).strip())
        finally:
            with self.lock:
                if self.fd == fd:
                    self.fd = None
                if self.proc is proc:
                    self.scanning = False
            try:
                os.close(fd)
            except OSError:
                pass

    def heard(self, line):
        if not line:
            return
        self.lines = (self.lines + [line])[-60:]
        if "Agent registered" in line or "Agent is already registered" in line:
            self.send("default-agent")                 # (its questions come here, whoever asked to pair)
            self.ready.set()
        m = CODE.search(line)
        if m:
            self.on_code(m.group(1))
        if "Failed to start discovery" in line:
            self.scanning = False
        try:
            self.on_said(line)
        except Exception as ex:
            print(f"bluetooth: {ex!r}", flush=True)
        self.asked(line)

    def asked(self, text):
        for pattern, answer in QUESTIONS:
            if pattern.search(text):
                now = time.monotonic()
                key = text[-60:]
                if now - self.answered.get(key, -10.0) > 3:     # (the same question, drawn again: once)
                    self.answered = {k: t for k, t in self.answered.items() if now - t < 30}
                    self.answered[key] = now
                    self.send(answer)
                    if answer == "0000":                # (an old keyboard: that's what to type on it)
                        self.on_code(answer)
                return


class Bluetooth:
    """Bluetooth, for Settings > Bluetooth and the web page: what's there (snapshot), and pairing, connecting,
    disconnecting and forgetting devices, and switching it on and off: one at a time, on threads of its own."""

    def __init__(self):
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.fresh = threading.Lock()   # (one look at BlueZ at a time)
        self.there = None       # None: not looked yet; False: no Bluetooth here (why says so)
        self.why = ""
        self.on = False
        self.adapter = None     # its object (/org/bluez/hci0)
        self.devices = []       # [{addr, name, kind, what, paired, connected, path, rssi}]: yours, then nearby
        self.seen = {}          # a device nearby -> when it was last heard (monotonic)
        self.status = None      # what it's doing, or what came of it
        self.code = None        # a keyboard's code to type in, while it pairs
        self.busy = None        # (what, addr): pairing, connecting... one at a time
        self.look_until = 0.0   # looking round till then (monotonic)
        self.screen = False     # Settings > Bluetooth is open
        self.web_until = 0.0    # ...the web page's Bluetooth, till then
        self.looked = 0.0       # when it last looked at BlueZ
        self.answered_at = 0.0  # ...and when BlueZ last answered
        self.thread = None
        self.agent = Agent(self.got_code, self.agent_said)
        self.on_change = lambda: None
        self.sound_note = lambda: "Sound plays through it"   # (headphones connected: media mode says where it goes)

    # -- what's there -------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            busy = self.busy or (None, None)
            return {"there": self.there, "why": self.why, "on": self.on, "looking": self.looking(),
                    "busy": busy[0], "busy_addr": busy[1], "status": self.status, "code": self.code,
                    "devices": [{k: d[k] for k in ("addr", "name", "kind", "what", "paired", "connected")}
                                for d in self.devices]}

    def looking(self):
        return self.on and time.monotonic() < self.look_until

    def wanted(self):
        return self.screen or time.monotonic() < self.web_until

    def summary(self):
        """The snapshot, for Settings' first page: looked at again now and then, on a thread."""
        if time.monotonic() - self.looked > BT_SUMMARY and not (self.thread and self.thread.is_alive()):
            self.looked = time.monotonic()
            threading.Thread(target=self.refresh_told, daemon=True, name="bt-summary").start()
        return self.snapshot()

    def refresh_told(self):
        self.refresh()
        self.changed()

    def refresh(self):
        """Looks at BlueZ: its adapter, on or off, and its devices."""
        with self.fresh:
            ok, out, err = bus(["call", BUS, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"], 8)
            objs = None
            if ok:
                try:
                    sig, values = bus_reply(out)
                    objs = values[0] if sig == "a{oa{sa{sv}}}" and isinstance(values[0], dict) else None
                    err = "" if objs is not None else f"a reply of {sig}"
                except (ValueError, IndexError, KeyError, TypeError) as ex:
                    err = f"its reply unread ({ex})"
            now = time.monotonic()
            with self.lock:
                self.looked = now
                if objs is None:
                    gone = not ok and any(w in err for w in BT_GONE)
                    if gone or self.there is not True or now - self.answered_at > BT_STALE:
                        why = "Bluetooth isn't running on this Pi" if gone else "Bluetooth isn't answering"
                        if self.why != why:
                            print(f"bluetooth: {why} ({err[:120]})", flush=True)
                        self.there, self.on, self.devices = False, False, []
                        self.why = why
                    return
                self.answered_at = now
                adapters = sorted(p for p, o in objs.items() if isinstance(o, dict) and ADAPTER in o)
                if not adapters:
                    self.there, self.on, self.devices = False, False, []
                    self.why = "This Pi has no Bluetooth"
                    return
                self.adapter = adapters[0]
                self.there, self.why = True, ""
                self.on = bool(prop(objs[self.adapter][ADAPTER], "Powered", False))
                mine, near = [], []
                for path, o in objs.items():
                    d = o.get(DEV) if isinstance(o, dict) else None
                    if not isinstance(d, dict) or prop(d, "Adapter", self.adapter) != self.adapter:
                        continue
                    addr = str(prop(d, "Address", "")).upper()
                    if not ADDR.fullmatch(addr):
                        continue
                    name = clean_name(prop(d, "Name") or "", 48)
                    alias = clean_name(prop(d, "Alias") or "", 48)
                    if alias and alias.replace("-", ":").upper() != addr:
                        name = alias                       # (a name you gave it, if you did)
                    rssi = prop(d, "RSSI")
                    dev = {"addr": addr, "path": path, "name": name or addr, "kind": bt_kind(prop(d, "Icon"), name),
                           "paired": bool(prop(d, "Paired", False)), "connected": bool(prop(d, "Connected", False)),
                           "rssi": rssi if isinstance(rssi, int) and not isinstance(rssi, bool) else None}
                    dev["what"] = KIND_WORDS.get(dev["kind"], "")
                    if dev["paired"] or dev["connected"]:
                        mine.append(dev)
                    elif name:                             # (one with no name: a beacon, most likely)
                        if dev["rssi"] is not None:        # heard on this look round
                            self.seen[addr] = now
                        if now - self.seen.get(addr, -1e9) <= BT_KEEP:
                            near.append(dev)
                mine.sort(key=lambda d: (not d["connected"], d["name"].lower()))
                near.sort(key=lambda d: -(d["rssi"] if d["rssi"] is not None else -200))
                self.devices = mine + near[:BT_NEAR]
                self.seen = {k: t for k, t in self.seen.items() if now - t <= BT_KEEP}

    def find(self, addr):
        with self.lock:
            return next((dict(d) for d in self.devices if d["addr"] == addr), None)

    def changed(self):
        try:
            self.on_change()
        except Exception as ex:
            print(f"bluetooth: {ex!r}", flush=True)

    def say(self, text):
        with self.lock:
            self.status = text
        self.changed()

    def got_code(self, code):
        """A keyboard's code to type in (None: done with)."""
        with self.lock:
            self.code = code
        self.changed()

    def agent_said(self, line):
        if "Failed to start discovery" in line:
            with self.lock:
                self.look_until = 0.0
            self.say("Can't look for devices right now")

    # -- watched: looking at BlueZ, and round, while a page shows it --------------------
    def watch(self, who, on=True):
        """Settings > Bluetooth open (who="screen": on or off), or the web page asking (who="web": for a while)."""
        with self.lock:
            if who == "web":
                self.web_until = time.monotonic() + BT_WEB
            elif self.screen == bool(on):
                return
            else:
                self.screen = bool(on)
                if not on and time.monotonic() >= self.web_until:
                    self.look_until = 0.0              # (gone from the page: done looking)
            if not self.wanted():
                return
        self.keep_going()

    def keep_going(self):
        """Its thread: running, and awake."""
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.loop, daemon=True, name="bluetooth")
                self.thread.start()
        self.wake.set()

    def loop(self):
        while True:
            with self.lock:
                if not (self.wanted() or self.busy):
                    self.thread = None
                    self.look_until = 0.0
                    break
            self.refresh()
            self.tend_agent()
            self.changed()
            self.wake.wait(BT_EVERY)
            self.wake.clear()
        self.agent.stop()
        self.changed()

    def tend_agent(self):
        """bluetoothctl open while a page shows Bluetooth (or it's pairing), looking round only while it looks."""
        with self.lock:
            looking = self.looking()
            pairing = bool(self.busy and self.busy[0] == "pair")
            if not looking:
                self.look_until = 0.0
            if self.there is not True:                 # (no Bluetooth to ask)
                return
        if not self.agent.alive():
            if not self.agent.start():
                if looking:
                    with self.lock:
                        self.look_until = 0.0
                    self.say("Can't look for devices: bluetoothctl isn't here")
                return
            self.agent.wait_ready()
        want = looking and not pairing
        if want != self.agent.scanning:
            self.agent.scan(want)

    def look(self):
        """Looking round for a while: None, or why it can't."""
        with self.lock:
            if self.there is False:
                return self.why
            if self.there and not self.on:
                return "Bluetooth is off"
            self.look_until = time.monotonic() + BT_LOOK
            if not self.busy:
                self.status = None
        self.keep_going()
        self.changed()
        return None

    def stop_looking(self):
        with self.lock:
            self.look_until = 0.0
        self.wake.set()
        self.changed()

    # -- doing things: one at a time --------------------------------------------------
    def start_job(self, what, addr, fn, *args):
        """fn on a thread of its own: None once it's started, or why it can't."""
        with self.lock:
            if self.there is not True:
                return self.why or "Bluetooth isn't ready yet"
            if self.busy:
                return "One thing at a time. Try again in a moment"
            if what != "power" and not self.on:
                return "Bluetooth is off"
            self.busy = (what, addr)
            self.status = None
        self.keep_going()
        threading.Thread(target=self.job, args=(fn, args), daemon=True, name="bt-" + what).start()
        self.changed()
        return None

    def job(self, fn, args):
        """fn, then what came of it (its last word) said as it's done: never said while it's still busy, so
        the moment it says so, the next thing can be asked."""
        said = None
        try:
            said = fn(*args)
        except Exception as ex:
            said = f"Something went wrong ({ex})"[:80]
        finally:
            self.refresh()                             # (what came of it, on the list before it's said to be done)
            with self.lock:
                self.busy = None
                self.code = None
                self.status = said
            self.changed()
            self.wake.set()

    def device_job(self, what, addr, fn):
        d = self.find(str(addr or "").upper())
        if d is None:
            return "It's gone. Look again"
        return self.start_job(what, d["addr"], fn, d)

    def pair(self, addr):
        d = self.find(str(addr or "").upper())
        if d is not None and d["paired"]:
            return self.connect(d["addr"])
        return self.device_job("pair", addr, self.pair_job)

    def connect(self, addr):
        return self.device_job("connect", addr, self.connect_job)

    def disconnect(self, addr):
        return self.device_job("disconnect", addr, self.disconnect_job)

    def forget(self, addr):
        return self.device_job("forget", addr, self.forget_job)

    def power(self, on):
        return self.start_job("power", None, self.power_job, bool(on))

    def pair_job(self, d):
        name = d["name"]
        self.say(f"Pairing with {name}…")
        if self.agent.start():                        # (its questions answered, a keyboard's code passed on)
            self.agent.wait_ready()
            self.agent.scan(False)                    # (pairing goes better with the looking stopped)
        with self.lock:
            self.look_until = 0.0
        ok, _, err = bus([f"--timeout={BT_PAIR}", "call", BUS, d["path"], DEV, "Pair"], BT_PAIR)
        self.got_code(None)
        if not ok and "already" not in err.lower():
            if "time" in err.lower():
                bus(["call", BUS, d["path"], DEV, "CancelPairing"], 5)
            return f"{name}: {bt_why(err, 'pair')}"
        bus(["set-property", BUS, d["path"], DEV, "Trusted", "b", "true"], 5)    # (it comes back by itself)
        self.say(f"Connecting to {name}…")
        return self.connect_job(d, paired=True)

    def connect_job(self, d, paired=False):
        name = d["name"]
        ok, _, err = bus([f"--timeout={BT_CONNECT}", "call", BUS, d["path"], DEV, "Connect"], BT_CONNECT)
        if not ok and "already connected" not in err.lower():
            self.refresh()
            now = self.find(d["addr"])
            if not (now and now["connected"]):        # (a controller may have connected by itself)
                if d["kind"] in SOUND_KINDS and "profile" in err.lower():    # (no BlueALSA to play through it)
                    return (f"{name} is paired. To hear sound through it, run setup.sh again" if paired
                            else f"To hear sound through {name}, run setup.sh again")
                why = bt_why(err, "connect")
                return f"{name} is paired, but didn't connect. {why}" if paired else f"{name}: {why}"
        if d["kind"] in SOUND_KINDS or not d["kind"]:  # headphones, a speaker (or one that doesn't say)
            up = self.sound_up(d["path"], wait=d["kind"] in SOUND_KINDS)
            if up:
                return f"{name} is connected. {self.sound_note()}"
            if up is None and d["kind"] in SOUND_KINDS:
                return f"{name} is connected. To hear sound through it, run setup.sh again"
        return f"{name} is connected"

    @staticmethod
    def sound_up(path, wait=True):
        """Just connected: True once BlueALSA plays through it (it may take a moment), False if it doesn't, None
        without BlueALSA. wait: a few seconds for it (one that doesn't say what it is: just a look)."""
        if not shutil.which("bluealsa"):
            return None
        end = time.monotonic() + (BT_SOUND_UP if wait else 0.0)
        while True:
            if path in [dev for dev, _ in bt_outputs(fresh=True)]:
                return True
            if time.monotonic() >= end:
                return False
            time.sleep(0.5)

    def disconnect_job(self, d):
        ok, _, err = bus(["--timeout=15", "call", BUS, d["path"], DEV, "Disconnect"], 15)
        return f"{d['name']} is disconnected" if ok else f"{d['name']}: {bt_why(err, 'connect')}"

    def forget_job(self, d):
        ok, _, err = bus(["call", BUS, self.adapter, ADAPTER, "RemoveDevice", "o", d["path"]], 10)
        with self.lock:
            self.seen.pop(d["addr"], None)
        return f"Forgot {d['name']}" if ok else f"{d['name']}: {bt_why(err, 'connect')}"

    def power_job(self, on):
        args = ["set-property", BUS, self.adapter, ADAPTER, "Powered", "b", "true" if on else "false"]
        with self.fresh:                               # (no look at BlueZ meanwhile: one from before would undo this)
            ok, _, err = bus(args, 10)
            if not ok and on and ("block" in err.lower() or "rfkill" in err.lower()):
                try:                                   # (switched off by rfkill: on again, then on)
                    subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                time.sleep(1)
                ok, _, err = bus(args, 10)
            if ok:
                with self.lock:
                    self.on = on
                    if not on:
                        self.look_until = 0.0
        if not ok:
            return ("Couldn't turn Bluetooth on. " if on else "Couldn't turn Bluetooth off. ") + bt_why(err, "power")
        if on and self.wanted():
            self.look()
        return None

    def do(self, what, addr=None):
        """The web page's request: {"ok": True}, or {"error": why}."""
        what = str(what or "")
        if what == "look":
            err = self.look()
        elif what == "stop":
            self.stop_looking()
            err = None
        elif what in ("on", "off"):
            err = self.power(what == "on")
        elif what in ("pair", "connect", "disconnect", "forget"):
            addr = str(addr or "").upper()
            if not ADDR.fullmatch(addr):
                return {"error": "No such device"}
            err = getattr(self, what)(addr)
        else:
            return {"error": "Unknown request"}
        return {"error": err} if err else {"ok": True}
