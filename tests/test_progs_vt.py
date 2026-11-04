"""cmatrix on a real console (a spare one here, standing in for media mode's): the menus' graphics mode and its text
mode; a keyboard's switch to another console while it's on (Alt+F1's way: switched straight back, and B lands back
in front with the menus' graphics mode, which a keyboard can't switch away from); a keyboard's Ctrl+S (the console's
output held) in the menus and while it's on; its lock mode (L: no q, no Ctrl+C); cut short while it stops (Pitato
itself stopping: the console still put back); and gone when Pitato goes, even killed outright. Then hollywood the
same way (the real one: byobu, tmux and its panes' programs): its tmux in a place of its own, never the console's
own process; drawing; Alt+F1 switched straight back; B closes it all, at once, even straight after A; and one left
running by a Pitato killed outright is closed before the next starts."""
import os, sys, time, fcntl, struct, subprocess
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

N = 10                                     # (a spare console: this machine's own stays as it is)
KDSETMODE, KDGETMODE, VT_GETSTATE, VT_ACTIVATE = 0x4B3A, 0x4B3B, 0x5603, 0x5606
TIOCSTI = 0x5412
KD_TEXT, KD_GRAPHICS = 0, 1
g.MEDIA_VT = N
HW = SP + "/hw/run"                     # (hollywood's own place, here)
g.HW_DIR = HW
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Fake(g.ProgScreen):
    """Just what cmatrix's part of media mode uses."""
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


def fg():
    return struct.unpack("HHH", fcntl.ioctl(f.ttyfd, VT_GETSTATE, bytes(6)))[0]


def mode():
    return struct.unpack("i", fcntl.ioctl(f.ttyfd, KDGETMODE, bytes(4)))[0]


def activate(n, wait=1.0):
    """A switch to console n, as a keyboard's Alt+Fn asks for one (the console may refuse)."""
    fcntl.ioctl(f.ttyfd, VT_ACTIVATE, n)
    end = time.monotonic() + wait
    while time.monotonic() < end and fg() != n:
        time.sleep(0.02)
    return fg()


def typed(keys):
    """Keys typed on the console's keyboard."""
    for b in keys:
        fcntl.ioctl(f.ttyfd, TIOCSTI, bytes([b]))


def screen():
    with open(f"/dev/vcs{N}", "rb") as v:
        return v.read()


def drawing(secs=0.5):
    a = screen()
    time.sleep(secs)
    return a != screen()


def stop_timed():
    p = f.prog
    t0 = time.monotonic()
    f.press_prog("b", False)
    return p, time.monotonic() - t0


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
try:
    # media mode: its console in front, in graphics mode (as enter() leaves it)
    check(f"media mode's console in front ({activate(N)})", fg() == N)
    fcntl.ioctl(f.ttyfd, KDSETMODE, KD_GRAPHICS)
    check("...the menus' graphics mode: a keyboard can't switch away (Alt+F1's way)", activate(1, 0.3) == N)

    # A: it starts, in text mode, drawing
    f.prog_start("cmatrix")
    time.sleep(1.0)
    chars = sum(c not in (0, 32) for c in screen())
    check(f"A: cmatrix on, the console in text mode, drawing ({chars} characters, changing)",
          f.prog is not None and f.prog.poll() is None and mode() == KD_TEXT and chars > 50 and drawing())

    # a keyboard's switch away while it's on: it goes through (text mode), and is switched straight back
    check("Alt+F1 while it's on: the switch goes through (text mode allows it)", activate(1) == 1)
    f.prog_tick()
    time.sleep(0.3)
    check(f"...media mode's next tick: its console straight back in front ({fg()}), cmatrix still on",
          fg() == N and f.prog.poll() is None)

    # switched away, then B before a tick: it stops, its console in front again, in graphics mode
    check("Alt+F1 again", activate(1) == 1)
    p, took = stop_timed()
    check(f"...then B at once: it stops ({p.returncode}, {took:.2f} s), media mode's console in front ({fg()}), "
          f"graphics mode ({mode()})", p.returncode == 0 and fg() == N and mode() == KD_GRAPHICS and took < 1.5)
    check("...and a keyboard can't switch away from the menus again", activate(1, 0.3) == N)

    # a keyboard's Ctrl+S in the menus (the console's output held), then A
    typed(b"\x13")
    f.prog_start("cmatrix")
    time.sleep(1.0)
    check("a Ctrl+S typed in the menus: cmatrix still draws when it starts", drawing())

    # ...and while it's on
    typed(b"\x13")
    time.sleep(0.3)
    held = not drawing(0.6)
    p, took = stop_timed()
    check(f"Ctrl+S while it's on: held ({held}), and B still stops it at once ({p.returncode}, {took:.2f} s)",
          held and p.returncode == 0 and took < 1.0 and mode() == KD_GRAPHICS)

    # its lock mode: L on a keyboard, and it takes no q (nor Ctrl+C)
    f.prog_start("cmatrix")
    time.sleep(0.6)
    typed(b"L")
    time.sleep(0.5)
    p, took = stop_timed()
    check(f"its lock mode (L): B still stops it ({p.returncode}, {took:.2f} s), the console in graphics mode",
          p.poll() is not None and took < 2.5 and mode() == KD_GRAPHICS and fg() == N)

    # cut short while it stops (Pitato told to stop meanwhile): the console's still put back, and cmatrix goes
    f.prog_start("cmatrix")
    time.sleep(0.6)
    p = f.prog
    real_wait = p.wait

    def cut(timeout=None):
        raise SystemExit(0)

    p.wait = cut
    try:
        f.prog_stop()
        cut_short = False
    except SystemExit:
        cut_short = True
    code = real_wait(timeout=3)
    check(f"cut short while it stops: the console back in graphics mode ({mode()}), in front ({fg()}), "
          f"cmatrix gone ({code})", cut_short and mode() == KD_GRAPHICS and fg() == N and code is not None
          and f.prog is None)

    # gone when Pitato goes, even killed outright (no clean-up of its own)
    script = f"""
import sys, time
sys.path.insert(0, {TESTS!r})
sys.path.insert(0, {SP!r})
import test_cmatrix_vt_child
"""
    with open(os.path.join(SP, "test_cmatrix_vt_child.py"), "w") as out:      # (made here, in the folder of work)
        out.write(f"""import os, sys, time
sys.path.insert(0, {TESTS!r})
import pietato_all as g
g.MEDIA_VT = {N}


class Fake(g.ProgScreen):
    def __init__(self):
        self.prog = self.prog_name = None
        self.fb = None
        self.dirty = False
        self.cm_colour, self.cm_bold, self.cm_speed = 0, 0, 4
        self.ttyfd = os.open("/dev/tty{N}", os.O_RDWR | os.O_NOCTTY)

    def toast(self, msg, secs=2):
        pass


m = Fake()
m.prog_start("cmatrix")
print(m.prog.pid, flush=True)
time.sleep(60)
""")
    child = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True,
                             env=dict(os.environ, PYTHONPATH=os.environ.get("PYTHONPATH", "")))
    pid = None
    while pid is None:                     # (its own lines first: "cmatrix: started ...")
        line = child.stdout.readline()
        if not line:
            break
        pid = int(line) if line.strip().isdigit() else None
    time.sleep(0.6)
    child.kill()
    child.wait()
    gone = False
    for _ in range(40):
        try:
            with open(f"/proc/{pid}/stat") as st:
                gone = st.read().split(") ", 1)[1].startswith("Z")
        except FileNotFoundError:
            gone = True
        if gone:
            break
        time.sleep(0.05)
    check(f"Pitato killed outright: its cmatrix goes too ({pid})", gone)

    # ---- hollywood: the real one ----
    def hw_procs():
        """hollywood's processes still running (not those finished and waiting to be collected)"""
        out = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
                stat = open(f"/proc/{pid}/stat").read().rsplit(") ", 1)[1].split()
            except OSError:
                continue
            if ("lib/hollywood/" in cmd or "-s hollywood" in cmd or cmd.startswith("/bin/bash /usr/bin/hollywood")
                    or "byobu" in cmd) and stat[0] != "Z":
                out.append((int(pid), int(stat[4]), cmd[:70]))      # (pid, its controlling terminal, what)
        return out

    f.prog_start("hollywood")
    time.sleep(6)
    chars = sum(c not in (0, 32) for c in screen())
    procs = hw_procs()
    server = [x for x in procs if "new-session" in x[2]]
    check(f"A on hollywood: on, the console in text mode, its panes drawing ({chars} characters, "
          f"{len(procs)} processes)", f.prog is not None and f.prog.poll() is None and mode() == KD_TEXT
          and chars > 300 and drawing(1.0) and any("lib/hollywood/" in x[2] for x in procs))
    check(f"...its tmux in a place of its own ({os.listdir(HW)}), and never the console's own process "
          f"(its controlling terminal: {[x[1] for x in server]})",
          server and all(x[1] == 0 for x in server) and g.hw_up())
    check("Alt+F1 while it's on: the switch goes through", activate(1) == 1)
    f.prog_tick()
    time.sleep(0.3)
    check(f"...switched straight back ({fg()}), hollywood still on", fg() == N and f.prog.poll() is None)
    p, took = stop_timed()
    time.sleep(0.5)
    left = hw_procs()
    check(f"B: it all closes ({p.returncode}, {took:.2f} s), the console back in graphics mode, in front; nothing "
          f"left running ({left})", p.poll() is not None and took < 1.5 and mode() == KD_GRAPHICS and fg() == N
          and not left and not g.hw_up())

    f.prog_start("hollywood")
    time.sleep(0.15)
    p, took = stop_timed()
    time.sleep(2.5)
    left = hw_procs()
    check(f"B straight after A: still nothing left running ({took:.2f} s, {left})",
          p.poll() is not None and not left and not g.hw_up() and mode() == KD_GRAPHICS)

    # a Pitato killed outright with hollywood on: its tmux carries on (not ours to follow), until the next start
    script_hw = script.replace("test_cmatrix_vt_child", "test_progs_vt_child")
    with open(os.path.join(SP, "test_progs_vt_child.py"), "w") as out:              # (made here too)
        out.write(open(os.path.join(SP, "test_cmatrix_vt_child.py")).read()
                  .replace('m.prog_start("cmatrix")', 'm.prog_start("hollywood")')
                  .replace("g.MEDIA_VT = " + str(N), "g.MEDIA_VT = " + str(N) + "\ng.HW_DIR = " + repr(HW)))
    child = subprocess.Popen([sys.executable, "-c", script_hw], stdout=subprocess.PIPE, text=True)
    pid = None
    while pid is None:
        line = child.stdout.readline()
        if not line:
            break
        pid = int(line) if line.strip().isdigit() else None
    time.sleep(4)
    child.kill()
    child.wait()
    time.sleep(1)
    before = [x for x in hw_procs() if "new-session" in x[2]]
    f.prog_start("hollywood")
    time.sleep(4)
    servers = [x for x in hw_procs() if "new-session" in x[2]]
    check(f"one left by a Pitato killed outright ({len(before)} running): closed as the next starts "
          f"({len(servers)} now)", len(servers) == 1 and (not before or before[0][0] != servers[0][0]))
    p, took = stop_timed()
    time.sleep(0.5)
    check(f"...and that one closes as well ({hw_procs()})", not hw_procs() and not g.hw_up())
finally:
    if f.prog is not None:
        f.prog.kill()
    g.hw_kill()
    try:
        fcntl.ioctl(f.ttyfd, KDSETMODE, KD_TEXT)
    except OSError:
        pass
    print("back to console", activate(start_vt), flush=True)
    os.close(f.ttyfd)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
