"""The Simulator's programs keep going: started as media mode starts them (on its console: here a pretend one, a
pty), with media mode's own loop ticking for 4 seconds, each is still running and still drawing at the end. Once on a
640x480 screen as it is, once on an 800x480 HDMI screen turned 180 degrees and 90 degrees."""
import json, os, pty, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_simkeeps"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    def __init__(self, rw=640, rh=480): self.real_w, self.real_h = rw, rh
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


master, slave = pty.openpty()
g.PROG_TTY = os.ttyname(slave)               # (the console: a pty here)
g.set_terminal_turn = lambda degrees, path=None: True
got = bytearray()


def drain():
    while True:
        try:
            b = os.read(master, 65536)
        except OSError:
            return
        if not b:
            return
        got.extend(b)


threading.Thread(target=drain, daemon=True).start()
progs = [p for p in ("cmatrix", "nyancat", "htop") if shutil.which(p)]
print("programs here:", progs)

for label, size, turn in (("640x480", (640, 480), 0), ("800x480 turned 180", (800, 480), 180),
                          ("800x480 turned 90", (480, 800), 90)):
    g.set_turn(turn)
    for name in progs:
        m = g.Media()
        m.gpi_case = False
        m.fb = FB(*size)
        m.active, m.ttyfd = True, None
        m.tab = m.tab_index("sims") if m.tab_index("sims") is not None else m.tab
        m.prog_start(name)
        p = m.prog
        if p is None:
            check(f"{label}: {name} started ({m.msg})", False)
            continue
        end = time.monotonic() + 4
        n0 = len(got)
        while time.monotonic() < end:
            m.tick(); m.flush()
            time.sleep(0.05)
        drew = len(got) - n0
        still = m.prog is p and p.poll() is None
        check(f"{label}: {name} still on after 4 s of media mode's loop ({'running' if still else 'stopped: ' + str(p.returncode)}), "
              f"still drawing ({drew} bytes)", still and drew > 1000)
        m.prog_stop()

print("ALL OK" if all(ok_all) else "SOME FAILED")
