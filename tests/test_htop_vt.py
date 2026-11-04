"""htop in the Simulator (pitato/screens/progs.py), the real one on a real console (a spare one here, standing in for
media mode's): A starts it in text mode, drawing what's running; the controller's buttons are its keys (▲▼ through
the list, held: on and on; A pauses it, SELECT a tree, X and Y sort it); a key that would end a process is never
typed; B stops it (its own q), and the console's back in the menus' graphics mode, in front. Then the Simulator's
list has it, and its help page says htop's buttons when it's picked."""
import json, os, shutil, struct, subprocess, sys, time, fcntl
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw

N = 10                                     # (a spare console: this machine's own stays as it is)
KDSETMODE, KDGETMODE, VT_GETSTATE, VT_ACTIVATE = 0x4B3A, 0x4B3B, 0x5603, 0x5606
KD_TEXT, KD_GRAPHICS = 0, 1
g.MEDIA_VT = N
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Fake(g.ProgScreen):
    """Just what the Simulator's programs use of media mode."""
    def __init__(self):
        self.prog = self.prog_name = None
        self.fb = None
        self.dirty = False
        self.msg = None
        self.cm_colour, self.cm_bold, self.cm_speed = 0, 0, 4
        self.ttyfd = os.open(f"/dev/tty{N}", os.O_RDWR | os.O_NOCTTY)

    def toast(self, msg, secs=2):
        self.msg = msg


f = Fake()
typed = []
real_key = g.ProgScreen.prog_key
f.prog_key = lambda keys: (typed.append(keys), real_key(f, keys))[1]


def fg():
    return struct.unpack("HHH", fcntl.ioctl(f.ttyfd, VT_GETSTATE, bytes(6)))[0]


def mode():
    return struct.unpack("i", fcntl.ioctl(f.ttyfd, KDGETMODE, bytes(4)))[0]


def screen():
    """The console's text, as lines."""
    rows, cols = struct.unpack("HHHH", fcntl.ioctl(f.ttyfd, 0x5413, bytes(8)))[:2]   # TIOCGWINSZ
    with open(f"/dev/vcs{N}", "rb") as v:
        raw = v.read()
    text = raw.decode("latin-1")
    return [text[i:i + cols] for i in range(0, len(text), cols)]


def shows(word, secs=3.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if any(word in line for line in screen()):
            return True
        time.sleep(0.1)
    return False


def unstick():
    """The console in front, if it was left in graphics mode (a stand-in media mode killed outright does that): text
    again, or the kernel won't switch away from it."""
    front = fg()
    if front != N:
        fd = os.open(f"/dev/tty{front}", os.O_RDWR | os.O_NOCTTY)
        try:
            fcntl.ioctl(fd, KDSETMODE, KD_TEXT)
        finally:
            os.close(fd)


unstick()
start_vt = fg()
was_size = subprocess.run(["stty", "-F", f"/dev/tty{N}", "size"], capture_output=True, text=True).stdout.split()
subprocess.run(["stty", "-F", f"/dev/tty{N}", "cols", "132", "rows", "40"])   # (a TV's console: room for "PAUSED")
try:
    fcntl.ioctl(f.ttyfd, VT_ACTIVATE, N)
    time.sleep(0.3)
    fcntl.ioctl(f.ttyfd, KDSETMODE, KD_GRAPHICS)
    f.prog_start("htop")
    argv = open(f"/proc/{f.prog.pid}/cmdline", "rb").read().split(b"\0")
    check(f"A: htop on, read-only ({argv[1:2]}), the console in text mode, showing what's running",
          f.prog is not None and f.prog.poll() is None and b"--readonly" in argv and mode() == KD_TEXT
          and shows("PID") and shows("CPU"))
    f.press_prog("a", False)
    check("A: it pauses (its own Z: PAUSED)", shows("PAUSED"))
    f.press_prog("a", False)
    time.sleep(1.0)
    check("...A again: it goes on", not any("PAUSED" in l for l in screen()))
    check("...read-only: no Nice or Kill on its keys (F7 to F9 blank)",
          any("F10Quit" in l and "Kill" not in l and "Nice" not in l for l in screen()))
    f.press_prog("select", False)
    check("SELECT: a tree (F5 says List, to go back)", shows("List"))
    f.press_prog("select", False)
    typed.clear()
    f.press_prog("down", False)
    for _ in range(3):
        f.press_prog("down", True)                 # (held)
    f.press_prog("up", False)
    f.press_prog("right", False); f.press_prog("left", False)
    f.press_prog("x", False); f.press_prog("y", False)
    f.press_prog("start", False); f.press_prog("l", False); f.press_prog("r", False)
    check(f"▲▼◀▶ its arrows (held: again and again), X and Y its sorts; nothing else typed "
          f"({[repr(t) for t in typed]})", typed == ["\x1b[B"] * 4 + ["\x1b[A", "\x1b[C", "\x1b[D", "P", "M"])
    check("...never a key that ends a process (k, F9) or quits it some other way",
          not any(t in ("k", "\x1b[20~", "\x1bOx") for t in typed) and f.prog.poll() is None)
    p = f.prog
    t0 = time.monotonic()
    f.press_prog("b", False)
    took = time.monotonic() - t0
    check(f"B: it stops ({p.returncode}, {took:.2f} s), the console back in graphics mode, in front",
          p.poll() is not None and f.prog is None and mode() == KD_GRAPHICS and fg() == N and took < 2)
finally:
    try:
        if f.prog is not None:
            f.prog.kill()
        fcntl.ioctl(f.ttyfd, KDSETMODE, KD_TEXT)
        fcntl.ioctl(f.ttyfd, VT_ACTIVATE, start_vt)
    except OSError:
        pass
    if len(was_size) == 2:
        subprocess.run(["stty", "-F", f"/dev/tty{N}", "rows", was_size[0], "cols", was_size[1]])

# ---- the Simulator's list has it; its help says htop's buttons when it's picked ------------------------------------
S = SP + "/t_htop"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.home_dir = lambda: HOME
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
m = g.Media(); m.enter()
si = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Simulator")
m.tab, m.view = si, "list"
m.load_tab(si)
rows = m.tab_items(si)
names = [r["title"] for r in rows]
hi = names.index("htop") if "htop" in names else -1
check(f"the Simulator's list: htop last, with what it is ({rows[hi]['sub'] if hi >= 0 else '-'})",
      names[-1] == "htop" and rows[hi]["sub"] == "What's running on the Pi")
m.sels[si] = hi
m.help_from, m.view = "list", "help"
texts.clear(); m.dirty = True; m.flush()
on_htop = list(texts)
FB.last.save(SP + "/htop_help.png")
m.sels[si] = names.index("cmatrix")
texts.clear(); m.dirty = True; m.flush()
low_htop, low_cm = [t.lower() for t in on_htop], [t.lower() for t in texts]
check("its help, htop picked: htop's buttons (cmatrix's when cmatrix is picked)",
      "while htop is on" in low_htop and "sort by memory" in low_htop and "while cmatrix is on" in low_cm
      and "while htop is on" not in low_cm)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
