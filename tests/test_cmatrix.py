"""Apps' cmatrix: Linux's own cmatrix (the real program), run on a pretend console (a pty), started from
Apps' list; the menus keep off the screen while it's on; the buttons are typed into it as its keys (and
it takes them: red for ◀▶, it pauses for A); B, HOME, q on a keyboard, leaving media mode or shutting down stop it,
and the menus come back; not installed: it says so. The web page starts and stops it too."""
import os, sys, time, shutil, select, struct, fcntl, termios, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/tcmatrix"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# a pretend console, 80 x 30 as the GPi Case's: what cmatrix draws comes out of its other end
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

m = g.Media()
m.enter()
si = m.tab_index("group") if False else next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Apps")
m.tab, m.view = si, "list"
m.load_tab(si)
rows = m.tab_items()
row = next((k for k, it in enumerate(rows) if it["title"] == "cmatrix"), None)
check(f"Apps lists cmatrix, then hollywood, nyancat, cacafire and htop, last ({[it['title'] for it in rows]})",
      row == len(rows) - 5 and rows[row]["icon"] == "CODE" and rows[row]["sub"] == "Linux's falling code"
      and [it["title"] for it in rows[-4:]] == ["hollywood", "nyancat", "cacafire", "htop"] and rows[-1]["sub"] == "What's running on the Pi")
m.sels[si] = row
m.dirty = True
m.flush()
check("...drawn in the list", FB.frames)

# A: it starts, the real one, on the console
FB.frames.clear()
n0 = mark()
m.press("a")
time.sleep(1.2)
p = m.prog
out = since(n0)
check(f"A on it: Linux's own cmatrix starts ({p and p.args}), and it's drawing on the console "
      f"({len(out)} bytes, its green: {b'[32m' in out})",
      p is not None and p.poll() is None and p.args == [shutil.which("cmatrix")] and len(out) > 2000 and b"[32m" in out)
m.dirty = True
m.flush()
check(f"...the menus keep off the screen while it's on ({len(FB.frames)} drawn)", not FB.frames and m.proc_owns_screen())
check(f"...the web page says where ({m.where_text()!r})", m.where_text().endswith("cmatrix"))

# its keys
n0 = mark()
m.press("right")
time.sleep(0.6)
check(f"▶: its next colour, red ({keys[-1]!r}), and it's red now", keys[-1] == "!" and b"[31m" in since(n0))
m.press("left"); m.press("left")
check(f"◀ ◀: back past green to white ({keys[-2:]})", keys[-2:] == ["@", "&"])
m.press("up")
m.press("down"); m.press("down")
check(f"▲ ▼ ▼: quicker, then slower (its delay: {keys[-3:]})", keys[-3:] == ["3", "4", "5"])
for _ in range(12):
    m.press("down")
check(f"...no slower than 9 ({keys[-1]})", keys[-1] == "9")
m.press("up", repeat=True)
check("...a held button: once (no repeats)", keys[-1] == "9")
m.press("x"); m.press("x"); m.press("x")
check(f"X: bold, some, all, none ({keys[-3:]})", keys[-3:] == ["b", "B", "n"])
m.press("y")
check(f"Y: mixed speeds ({keys[-1]!r})", keys[-1] == "a")
m.press("select")
check(f"SELECT: rainbow ({keys[-1]!r})", keys[-1] == "r")
m.press("l"); m.press("r"); m.press("start")
check(f"L, R and START: nothing (no app switching under it) ({m.tab == si}, {keys[-1]!r})",
      m.tab == si and keys[-1] == "r" and m.prog is p)
m.press("right")                                  # (a colour: rainbow off, as its colour keys do)
time.sleep(3)                                     # (it takes a key a frame: the ones above, first)
m.press("a")
time.sleep(0.5)
n0 = mark()
time.sleep(0.8)
quiet = len(since(n0))
m.press("a")
time.sleep(0.8)
check(f"A: it pauses ({quiet} bytes while paused), and A again plays on ({len(since(n0)) - quiet} after)",
      keys[-2:] == ["p", "p"] and quiet < 200 and len(since(n0)) - quiet > 1000)

# B: it stops, the menus come back
FB.frames.clear()
t0 = time.monotonic()
m.press("b")
took = time.monotonic() - t0
check(f"B: it stops, told q as from a keyboard (Ctrl+Q first: {keys[-1]!r}, exit {p.returncode}, {took:.2f} s)",
      keys[-1] == "\x11q" and p.returncode == 0 and m.prog is None and took < 1.5)
m.flush()
check(f"...and the menus are back, Apps' list ({len(FB.frames)} drawn, {m.tab == si})",
      FB.frames and m.tab == si and not m.proc_owns_screen() and getattr(FB, "invalidated", 0) >= 1)

# a keyboard's q (its own way out): media mode sees it's gone
m.press("a")
time.sleep(0.8)
p = m.prog
os.write(master, b"q")
for _ in range(40):
    if p.poll() is not None:
        break
    time.sleep(0.05)
m.tick()
check(f"q on a keyboard stops it: media mode sees and has the screen again ({p.returncode}, {m.prog})",
      p.returncode == 0 and m.prog is None and m.dirty)

# HOME, leaving media mode, shutting down
m.press("a"); time.sleep(0.5)
p = m.prog
check("HOME: it stops (back to Apps, still in media mode)", m.prog_home() and p.poll() is not None
      and m.active and not m.prog_home())
m.press("a"); time.sleep(0.5)
p = m.prog
m.leave()
check(f"leaving media mode: it stops first ({p.returncode})", p.poll() is not None and m.prog is None)
m.enter()
m.tab, m.view = si, "list"
m.load_tab(si)
m.sels[si] = row
m.press("a"); time.sleep(0.5)
p = m.prog
m.shutdown()
check(f"shutting down: it stops first ({p.returncode})", p.poll() is not None and m.prog is None)

# the web page
m2 = g.Media()
m2.enter()
r = m2.web_command({"cmd": "open", "app": "cmatrix"})
time.sleep(0.5)
p = m2.prog
check(f"the web page opens it: Apps, and cmatrix on ({r}, {m2.where_text()!r})",
      r.get("ok") and p is not None and p.poll() is None and g.LIBRARY[m2.tab]["name"] == "Apps")
r = m2.web_command({"cmd": "open", "app": "Weather"})
check(f"...and anything else it puts on the screen stops it ({p.poll()}, {r})", p.poll() is not None and m2.prog is None)
m2.leave()

# not installed
real_which = g.shutil.which
g.shutil.which = lambda name, *a, **k: None if name == "cmatrix" else real_which(name, *a, **k)
m.enter()
m.tab, m.view = si, "list"
m.load_tab(si)
m.sels[si] = row
m.press("a")
check(f"cmatrix not installed: it says how to put it in ({m.msg!r})", m.prog is None
      and m.msg == "cmatrix isn't installed: sudo apt install cmatrix")
g.shutil.which = real_which
m.leave()

# the controls, on Apps' help page
m.enter()
m.tab, m.view = si, "list"
m.load_tab(si)
FB.frames.clear()
m.press("x")
m.flush()
check(f"X on Apps' list: its controls, cmatrix's among them ({m.view})", m.view == "help" and FB.frames)
FB.frames[-1].save(SP + "/cmatrix_help.png")
m.leave()
check("setup.sh puts cmatrix in (on a line of its own: setup carries on without it)",
      'apt-get install -y cmatrix || echo "(Couldn\'t install cmatrix' in open(ROOT + "/setup.sh").read())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
