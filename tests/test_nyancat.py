"""The Simulator's nyancat and cacafire: Linux's own nyancat and setup.sh's own cacafire (libcaca's, built without its
"Powered by libcaca", as setup.sh builds it: its build_cacafire, run for real), each on a pretend console (a pty),
started from the Simulator's list, where Orbits isn't any more; the menus keep off the screen while one's on; B, HOME,
leaving media mode or shutting down stop them, each its own tidy way (nyancat Ctrl+C's signal, cacafire Ctrl+C typed:
the cursor and colours put back), quickly; cacafire's A pauses it; neither takes the other buttons; the web page starts
them; not installed: it says so (cacafire, setup.sh's own: Debian's if that's all there is)."""
import os, sys, time, shutil, select, struct, fcntl, termios, threading, subprocess
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/tnyancat"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
REAL_RUN = subprocess.run
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# setup.sh's own build of cacafire, as it does it (its function, run for real: the source fetched, the banner out)
src = open(ROOT + "/setup.sh").read()
fn = src[src.index("CACAFIRE="):src.index("if [ \"$(cat \"$PROGS/cacafire.version\"")]
script = f"""set -e
apt-get() {{ :; }}          # (already here: build-essential, curl, libcaca-dev)
BUILDING=""
{fn}
PROGS="{S}/progs"
build_cacafire
echo "built: $(cat "$PROGS/cacafire.version")"
"""
r = REAL_RUN(["bash", "-c", script], capture_output=True, text=True, timeout=180)
OWN = S + "/progs/cacafire"
check(f"setup.sh builds cacafire: libcaca's own source at its pinned version, Debian's libcaca ({r.stdout.strip()!r}"
      f"{r.stderr.strip()[-300:]})", r.returncode == 0 and os.access(OWN, os.X_OK)
      and "373c88b9890e67bde91e6acb8f1c442e847d1203" in r.stdout)
check("...not a word of libcaca in what it shows", b"Powered by libcaca" not in open(OWN, "rb").read())
g.PROG_OWN["cacafire"] = OWN

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
                data = os.read(master, 1 << 20)
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
        pass

    def close(self):
        pass


g.Framebuffer = FB
keys = []
real_key = g.ProgScreen.prog_key


def spy_key(self, k):
    keys.append(k)
    real_key(self, k)


g.ProgScreen.prog_key = spy_key


def to(m, title):
    si = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Simulator")
    m.tab, m.view = si, "list"
    m.load_tab(si)
    rows = m.tab_items()
    m.sels[si] = next(k for k, it in enumerate(rows) if it["title"] == title)
    return si, rows


m = g.Media()
m.enter()
si, rows = to(m, "nyancat")
titles = [it["title"] for it in rows]
check(f"the Simulator: no Orbits; nyancat, cacafire and htop after hollywood, last ({titles})",
      "Orbits" not in titles and titles[-4:] == ["hollywood", "nyancat", "cacafire", "htop"]
      and [it["icon"] for it in rows[-3:]] == ["NYAN", "HEAT", "PROC"] and [it["sub"] for it in rows[-3:]] == ["The rainbow cat", "Flames made of letters", "What's running on the Pi"])
check("...and Orbits isn't a sim any more either", "orbit" not in g.SIMS and not hasattr(g, "Orbits"))

for name, args in (("nyancat", [shutil.which("nyancat"), "-s"]), ("cacafire", [OWN])):
    to(m, name)
    FB.frames.clear()
    n0 = mark()
    m.press("a")
    time.sleep(3)
    p = m.prog
    out = since(n0)
    check(f"{name}: A starts it ({p and p.args}), drawing on the console ({len(out)} bytes)",
          p is not None and p.poll() is None and p.args == args and len(out) > 20000)
    if name == "cacafire":
        check("...setup.sh's own: no \"Powered by libcaca\" at any time", b"libcaca" not in out)
    m.dirty = True
    m.flush()
    check(f"...the menus keep off the screen while it's on ({len(FB.frames)} drawn), the web page says where "
          f"({m.where_text()!r})", not FB.frames and m.proc_owns_screen() and m.where_text().endswith(name))
    before = len(keys)
    for b in ("left", "right", "up", "down", "x", "y", "select", "start", "l", "r"):
        m.press(b)
    check(f"...the other buttons: nothing typed into it ({keys[before:]}), no app switching under it",
          keys[before:] == [] and m.tab == si and m.prog is p and p.poll() is None)
    if name == "cacafire":
        m.press("a")
        time.sleep(0.6)
        n1 = mark()
        time.sleep(0.6)
        still = len(since(n1))
        m.press("a")
        time.sleep(0.6)
        n2 = mark()
        time.sleep(0.6)
        going = len(since(n2))
        check(f"...A pauses it, and A again goes on ({keys[-2:]}, {still} bytes paused, {going} going)",
              keys[-2:] == [" ", " "] and still < going / 4)
    n3 = mark()
    t0 = time.monotonic()
    m.press("b")
    took = time.monotonic() - t0
    time.sleep(0.3)
    tail = since(n3)
    m.flush()
    check(f"...B: it stops its own way, quickly ({p.returncode}, {took:.2f} s), the cursor and colours put back, the "
          f"menus back", p.poll() is not None and p.returncode == 0 and took < 1.0 and b"\x1b[?25h" in tail
          and m.prog is None and FB.frames and m.tab == si and not m.proc_owns_screen())

    # HOME, leaving media mode, shutting down
    m.press("a"); time.sleep(1)
    p = m.prog
    check(f"...HOME stops it (back to the Simulator, still in media mode)",
          m.prog_home() and p.poll() is not None and m.active and not m.prog_home())
    m.press("a"); time.sleep(1)
    p = m.prog
    m.leave()
    check(f"...leaving media mode stops it first ({p.returncode})", p.poll() is not None and m.prog is None)
    m.enter()
    to(m, name)
    m.press("a"); time.sleep(1)
    p = m.prog
    m.shutdown()
    check(f"...shutting down stops it first ({p.returncode})", p.poll() is not None and m.prog is None)
    m.enter()

# the web page
r = m.web_command({"cmd": "open", "app": "nyancat"})
time.sleep(1.5)
p = m.prog
check(f"the web page opens nyancat: the Simulator, and nyancat on ({r}, {m.where_text()!r})",
      r.get("ok") and p is not None and p.poll() is None and m.prog_name == "nyancat")
r = m.web_command({"cmd": "open", "app": "cacafire"})
time.sleep(1.5)
check(f"...cacafire from there: nyancat stops, cacafire on ({r})", p.poll() is not None and m.prog is not None
      and m.prog_name == "cacafire")
r = m.web_command({"cmd": "open", "app": "Weather"})
check(f"...and anything else stops it ({r})", m.prog is None)

# not installed
real_which = g.shutil.which
g.PROG_OWN["cacafire"] = S + "/nowhere/cacafire"
to(m, "cacafire")
m.press("a"); time.sleep(1)
p = m.prog
check(f"setup.sh's cacafire not there: Debian's, if that's there ({p and p.args})",
      p is not None and p.args == [real_which("cacafire")])
m.press("b")
g.shutil.which = lambda name, *a, **k: None if name in ("cacafire", "nyancat") else real_which(name, *a, **k)
m.press("a")
check(f"...neither: it says how to put it in ({m.msg!r})", m.prog is None
      and m.msg == "cacafire isn't installed: sudo bash setup.sh puts it in")
to(m, "nyancat")
m.press("a")
check(f"nyancat not installed: it says how to put it in ({m.msg!r})", m.prog is None
      and m.msg == "nyancat isn't installed: sudo apt install nyancat")
g.shutil.which = real_which
m.leave()
setup = open(ROOT + "/setup.sh").read()
check("setup.sh puts nyancat in, and builds cacafire (the banner taken out, or not built at all)",
      "apt-get install -y nyancat" in setup and "build_cacafire ||" in setup
      and "! grep -q 'Powered by libcaca'" in setup and "caca-utils" not in setup)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
