"""The Simulator's hollywood: Linux's own (byobu, tmux and its panes' programs), run on a pretend console (a pty),
started from the Simulator's list; the menus keep off the screen while it's on; the buttons don't go into it (no
keys of its own), but B, HOME, leaving media mode or shutting down close it all, and the menus come back; the web
page starts and stops it too; not installed: it says so."""
import os, sys, time, shutil, select, struct, fcntl, termios, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/thollywood"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
g.HW_DIR = S + "/hw"
_real_run = g.subprocess.run


def fake_run(cmd, *a, **k):
    """the system's commands (chvt...) pretended, but hollywood's tmux for real"""
    if list(cmd[:1]) == ["tmux"]:
        return _real_run(cmd, *a, **k)
    return type("R", (), {"stdout": "1", "returncode": 0})()


g.subprocess.run = fake_run
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


master, slave = os.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 80, 0, 0))
g.PROG_TTY = os.ttyname(slave)
seen = bytearray()
lock = threading.Lock()


def drain():
    while True:
        r, _, _ = select.select([master], [], [], 0.05)
        if r:
            try:
                data = os.read(master, 65536)
            except OSError:
                return
            with lock:
                seen.extend(data)


threading.Thread(target=drain, daemon=True).start()


def since(n):
    with lock:
        return bytes(seen[n:])


def mark():
    with lock:
        return len(seen)


def hw_procs():
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
            stat = open(f"/proc/{pid}/stat").read().rsplit(") ", 1)[1].split()
        except OSError:
            continue
        if ("lib/hollywood/" in cmd or "-s hollywood" in cmd or "/usr/bin/hollywood" in cmd) and stat[0] != "Z":
            out.append(int(pid))
    return out


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
        FB.invalidated = getattr(FB, "invalidated", 0) + 1

    def close(self):
        pass


g.Framebuffer = FB
keys = []
real_key = g.ProgScreen.prog_key


def spy_key(self, k):
    keys.append(k)
    real_key(self, k)


g.ProgScreen.prog_key = spy_key


def to_hollywood(m):
    si = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Simulator")
    m.tab, m.view = si, "list"
    m.load_tab(si)
    rows = m.tab_items()
    m.sels[si] = next(k for k, it in enumerate(rows) if it["title"] == "hollywood")
    return si, rows


m = g.Media()
m.enter()
si, rows = to_hollywood(m)
row = m.sels[si]
check(f"the Simulator lists hollywood, then nyancat, cacafire and htop, last ({[it['title'] for it in rows]})",
      row == len(rows) - 4 and rows[row]["icon"] == "HACK" and rows[row]["sub"] == "Movie hacker screens")

# A: the real one, on the console
FB.frames.clear()
n0 = mark()
m.press("a")
time.sleep(5)
p = m.prog
out = since(n0)
procs = hw_procs()
check(f"A on it: Linux's own hollywood ({p and p.args}), byobu and tmux drawing its panes on the console "
      f"({len(out)} bytes, {len(procs)} processes)",
      p is not None and p.poll() is None and p.args == [shutil.which("hollywood")] and len(out) > 5000
      and len(procs) >= 5 and g.hw_up())
m.dirty = True
m.flush()
check(f"...the menus keep off the screen while it's on ({len(FB.frames)} drawn), the web page says where "
      f"({m.where_text()!r})", not FB.frames and m.proc_owns_screen() and m.where_text().endswith("hollywood"))
before = len(keys)
for b in ("left", "right", "up", "down", "a", "x", "y", "select", "start", "l", "r"):
    m.press(b)
check(f"the other buttons: nothing typed into it, and no app switching under it ({keys[before:]}, {m.tab == si})",
      keys[before:] == [] and m.tab == si and m.prog is p and p.poll() is None)

# B: it all closes, the menus come back
FB.frames.clear()
t0 = time.monotonic()
m.press("b")
took = time.monotonic() - t0
time.sleep(0.5)
left = hw_procs()
m.flush()
check(f"B: it all closes ({p.returncode}, {took:.2f} s, left: {left}), the menus back, the Simulator's list",
      p.poll() is not None and m.prog is None and not left and not g.hw_up() and took < 2
      and FB.frames and m.tab == si and not m.proc_owns_screen())

# HOME, leaving media mode, shutting down
m.press("a"); time.sleep(3)
p = m.prog
check("HOME: it all closes (back to the Simulator, still in media mode)",
      m.prog_home() and p.poll() is not None and not hw_procs() and m.active and not m.prog_home())
m.press("a"); time.sleep(3)
p = m.prog
m.leave()
check(f"leaving media mode: it all closes first ({p.returncode})", p.poll() is not None and m.prog is None
      and not hw_procs())
m.enter()
to_hollywood(m)
m.press("a"); time.sleep(3)
p = m.prog
m.shutdown()
check(f"shutting down: it all closes first ({p.returncode})", p.poll() is not None and m.prog is None
      and not hw_procs())

# the web page
m2 = g.Media()
m2.enter()
r = m2.web_command({"cmd": "open", "app": "hollywood"})
time.sleep(3)
p = m2.prog
check(f"the web page opens it: the Simulator, and hollywood on ({r}, {m2.where_text()!r})",
      r.get("ok") and p is not None and p.poll() is None and g.LIBRARY[m2.tab]["name"] == "Simulator"
      and m2.prog_name == "hollywood")
r = m2.web_command({"cmd": "open", "app": "cmatrix"})
time.sleep(0.8)
check(f"...cmatrix from there: hollywood closes, cmatrix on ({r}, {m2.where_text()!r})",
      p.poll() is not None and not hw_procs() and m2.prog is not None and m2.prog_name == "cmatrix")
r = m2.web_command({"cmd": "open", "app": "Weather"})
check(f"...and anything else stops it ({r})", m2.prog is None)
m2.leave()

# not installed
real_which = g.shutil.which
g.shutil.which = lambda name, *a, **k: None if name == "hollywood" else real_which(name, *a, **k)
m.enter()
to_hollywood(m)
m.press("a")
check(f"hollywood not installed: it says how to put it in ({m.msg!r})", m.prog is None
      and m.msg == "hollywood isn't installed: sudo apt install hollywood")
g.shutil.which = real_which

# the controls, on the Simulator's help page
FB.frames.clear()
m.press("x")
m.flush()
check(f"X on the Simulator's list: its controls, hollywood's among them ({m.view})", m.view == "help" and FB.frames)
FB.frames[-1].save(SP + "/progs_help.png")
m.leave()
src = open(ROOT + "/setup.sh").read()
check("setup.sh puts hollywood in, and the programs its panes run (not atop or plocate: they'd run all the time)",
      "apt-get install -y --no-install-recommends hollywood" in src
      and "apt-get install -y --no-install-recommends apg bmon bsdextrautils ccze htop jp2a moreutils speedometer tree"
      in src and not any(l.lstrip().startswith("apt-get") and {"atop", "plocate"} & set(l.split())
                         for l in src.splitlines()))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
