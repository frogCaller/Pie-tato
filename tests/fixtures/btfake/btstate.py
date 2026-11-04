"""The pretend BlueZ's state, in a JSON file both stand-ins share (BT_FAKE), locked while one changes it."""
import fcntl
import json
import os
import time

PATH = os.environ.get("BT_FAKE", "")
LOG = os.environ.get("BT_LOG", "")


class State:
    def __enter__(self):
        self.f = open(PATH, "r+")
        fcntl.lockf(self.f, fcntl.LOCK_EX)
        self.s = json.load(self.f)
        return self.s

    def __exit__(self, *exc):
        self.f.seek(0)
        self.f.truncate()
        json.dump(self.s, self.f)
        self.f.flush()
        sync_links(self.s)
        fcntl.lockf(self.f, fcntl.LOCK_UN)
        self.f.close()


def sync_links(s):
    """The kernel's Bluetooth links (BT_LINKS, a folder standing in for /sys/class/bluetooth): hci0, and an hci0:N
    for each device connected."""
    folder = os.environ.get("BT_LINKS", "")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    want = set()
    if s.get("adapter", True):
        want.add("hci0")
        if s.get("powered", True) and s.get("running", True):
            for addr, d in s.get("devices", {}).items():
                if d.get("connected"):
                    want.add("hci0:%d" % (int(addr.replace(":", ""), 16) % 3000 + 1))
    have = set(os.listdir(folder))
    for n in have - want:
        try:
            os.remove(os.path.join(folder, n))
        except OSError:
            pass
    for n in want - have:
        open(os.path.join(folder, n), "w").close()


def read():
    with open(PATH) as f:
        fcntl.lockf(f, fcntl.LOCK_SH)
        s = json.load(f)
        fcntl.lockf(f, fcntl.LOCK_UN)
    return s


def log(*words):
    if LOG:
        with open(LOG, "a") as f:
            f.write(f"{time.monotonic():.3f} " + " ".join(str(w) for w in words) + "\n")


def path_of(addr):
    return "/org/bluez/hci0/dev_" + addr.replace(":", "_")


def addr_of(path):
    return path.rsplit("dev_", 1)[-1].replace("_", ":")


ESC = {7: "\\a", 8: "\\b", 12: "\\f", 10: "\\n", 13: "\\r", 9: "\\t", 11: "\\v", 92: "\\\\", 34: '\\"', 39: "\\'"}


def cescape(s):
    """busctl's cescape(): C's escapes, and each byte that isn't plain ASCII as octal."""
    out = []
    for b in s.encode("utf-8"):
        out.append(ESC[b] if b in ESC else "\\%03o" % b if b < 32 or b >= 127 else chr(b))
    return "".join(out)


def type_end(sig, i=0):
    c = sig[i]
    if c == "a":
        return type_end(sig, i + 1)
    if c in "({":
        close, i = ")" if c == "(" else "}", i + 1
        while sig[i] != close:
            i = type_end(sig, i)
        return i + 1
    return i + 1


def types(sig):
    out, i = [], 0
    while i < len(sig):
        j = type_end(sig, i)
        out.append(sig[i:j])
        i = j
    return out


def busctl_text(sig, val):
    """A value of type sig as busctl prints it without --json (its format_cmdline()); a variant is
    {"type": ..., "data": ...}."""
    c = sig[0]
    if c == "a":
        inner = sig[1:]
        if inner[0] == "{":
            k, v = types(inner[1:-1])
            return " ".join([str(len(val))] + [busctl_text(k, a) + " " + busctl_text(v, b) for a, b in val.items()])
        return " ".join([str(len(val))] + [busctl_text(inner, x) for x in val])
    if c == "v":
        return val["type"] + " " + busctl_text(val["type"], val["data"])
    if c == "(":
        return " ".join(busctl_text(t, x) for t, x in zip(types(sig[1:-1]), val))
    if c == "b":
        return "true" if val else "false"
    if c == "d":
        return "%g" % val
    if c in "sog":
        return '"' + cescape(val) + '"'
    return str(int(val))


def int_keys(x):
    """A dict keyed by numbers in it somewhere (busctl --json gives up on one: JSON's keys are strings)."""
    if isinstance(x, dict):
        return any(not isinstance(k, str) or int_keys(v) for k, v in x.items())
    if isinstance(x, list):
        return any(int_keys(v) for v in x)
    return False


def event(what, **kw):
    """busctl tells the pretend bluetoothctl (BlueZ's agent) something: a code to show, a question."""
    with open(os.environ["BT_AGENT_IN"], "a") as f:
        f.write(json.dumps(dict(kw, event=what)) + "\n")


def answer_file():
    return os.environ["BT_AGENT_OUT"]
