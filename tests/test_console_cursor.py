"""Media mode's console cursor: off for the menus, on for a Simulator program and the terminal; never waits on a
console a Ctrl+S has held, nor on one too full to take it (a pretend console: a pty)."""
import os, pty, select, sys, termios, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.screens.progs as progs
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


master, slave = pty.openpty()
progs.PROG_TTY = os.ttyname(slave)
attrs = termios.tcgetattr(slave)
attrs[1] &= ~termios.OPOST                      # (the bytes as they're written)
termios.tcsetattr(slave, termios.TCSANOW, attrs)


def said(wait=1.0):
    out = b""
    end = time.time() + wait
    while time.time() < end:
        r, _, _ = select.select([master], [], [], 0.05)
        if r:
            out += os.read(master, 4096)
        elif out:
            break
    return out


class M(progs.ProgScreen if hasattr(progs, "ProgScreen") else object):
    pass


m = g.Media()
m.ttyfd = None
m.console_cursor(False)
check("off for the menus", said() == b"\x1b[?25l")
m.console_cursor(True)
check("on again", said() == b"\x1b[?25h")
m.prog_mode(progs.KD_TEXT)
check("a program: on, as in the terminal", said() == b"\x1b[?25h")
m.prog_mode(progs.KD_GRAPHICS)
check("...and off when it's done", said() == b"\x1b[?25l")

# a Ctrl+S held it: it's let go, and the cursor goes off all the same
termios.tcflow(slave, termios.TCOOFF)
t0 = time.time()
done = threading.Event()
threading.Thread(target=lambda: (m.console_cursor(False), done.set()), daemon=True).start()
check(f"held by Ctrl+S: no wait ({time.time() - t0:.2f}s)", done.wait(3))
check("...let go, and it's off", said() == b"\x1b[?25l")

# too full to take it: left as it is, no wait
attrs = termios.tcgetattr(slave)
os.set_blocking(slave, False)
n = 0
try:
    while True:
        n += os.write(slave, b"x" * 4096)
except BlockingIOError:
    pass
done.clear()
threading.Thread(target=lambda: (m.console_cursor(False), done.set()), daemon=True).start()
check(f"a full console ({n} bytes waiting): no wait", done.wait(3))
progs.PROG_TTY = "/nonexistent/tty"
m.console_cursor(False)
check("no console at all: nothing to do", True)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
