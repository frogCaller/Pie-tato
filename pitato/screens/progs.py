"""The Simulator's cmatrix, hollywood, nyancat, cacafire and htop: Linux's own, on the whole screen, with the
controller's buttons as keys."""
import fcntl
import os
import shutil
import signal
import socket
import struct
import subprocess
import termios
import time

from ..library import MEDIA_VT
from ..screen import terminal_turn_now
from .player import quiet_child

CM_COLOURS = "@!#$%^&"   # cmatrix's keys for its colours: its own green, then red, yellow, blue, magenta, cyan, white
CM_BOLD = "nbB"          # ...for no bold characters (its own), some, all
CM_SPEED = 4             # its delay between frames, 0 (quickest) to 9: its own to start with
CM_KEYS = {"a": "p", "y": "a", "select": "r"}   # A pauses, Y mixed speeds (each column its own), SELECT rainbow
HTOP_KEYS = {"up": "\x1b[A", "down": "\x1b[B", "left": "\x1b[D", "right": "\x1b[C",   # through the list, along it
             "a": "Z", "x": "P", "y": "M", "select": "t"}   # A pauses it, X sorts by CPU, Y by memory, SELECT a tree
HTOP_HELD = ("up", "down", "left", "right")   # (held: on through the list, as a keyboard's arrows)
PROG_GO = "\x11"         # Ctrl+Q: the console's output going again, if a keyboard's Ctrl+S or Scroll Lock held it
PROG_TTY = None          # (the console they run on: media mode's own. The tests give them a pretend one)
HW_DIR = "/run/pitato-hollywood"   # hollywood's own tmux and byobu, apart from anyone else's (gone at start-up)
PROG_ARGS = {"nyancat": ["-s"]}    # (nyancat: no window title, which a console has nowhere to put)
PROG_OWN = {"cacafire": "/usr/local/lib/pitato/cacafire"}   # setup.sh's own build (without "Powered by libcaca")
PROG_QUIT = {"cacafire": "\x03"}   # its own way out, typed (cmatrix's: q; cacafire's: Ctrl+C)
KD_TEXT, KD_GRAPHICS = 0, 1
KDSETMODE, VT_GETSTATE, VT_ACTIVATE = 0x4B3A, 0x5603, 0x5606


def prog_tty():
    return PROG_TTY or f"/dev/tty{MEDIA_VT}"


_readonly = {}


def htop_args(path):
    """htop read-only where it can be (3.1 on): nothing that ends or changes a process, whatever's pressed (a
    keyboard's keys too). An older one, as it is (it wouldn't start, told to)."""
    if path not in _readonly:
        try:
            out = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        _readonly[path] = ["--readonly"] if "--readonly" in out else []
    return _readonly[path]


def hw_env():
    """hollywood's surroundings: its own tmux (and byobu, which it starts tmux with), never one you're in."""
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "XDG_CONFIG_HOME")}
    env.update(TERM="linux", HOME=HW_DIR, TMUX_TMPDIR=HW_DIR, BYOBU_CONFIG_DIR=os.path.join(HW_DIR, "byobu"))
    return env


def hw_up():
    """hollywood's tmux is running: its socket answers (tmux leaves the socket behind when it's closed)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(os.path.join(HW_DIR, f"tmux-{os.getuid()}", "default"))
        return True
    except OSError:
        return False
    finally:
        s.close()


def hw_kill():
    """hollywood's tmux, and everything in its panes, gone."""
    try:
        subprocess.run(["tmux", "kill-server"], env=hw_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass


class ProgScreen:
    """The Simulator's cmatrix, hollywood, nyancat, cacafire and htop: Linux's own, run on media mode's console (in
    text mode while one's on, so the console draws it, just as in the terminal). cmatrix takes the controller's buttons
    as its keys: ◀▶ its colour, ▲▼ its speed, A pauses, X bold, Y mixed speeds, SELECT rainbow; cacafire A, to pause;
    htop ▲▼ through what's running (held: on and on), ◀▶ along it, A pauses it, X sorts by CPU, Y by memory, SELECT a
    tree (never a key that ends a process). B (or HOME) stops any of them, back to the Simulator. A keyboard works
    too, as in the terminal. Media mode keeps the screen while one's on: a keyboard's switch to another console
    (Alt+F1...) is switched straight back."""

    def prog_start(self, name):
        if self.prog is not None:
            return
        own = PROG_OWN.get(name)
        path = own if own and os.access(own, os.X_OK) else shutil.which(name)
        if not path:
            self.toast(f"{name} isn't installed: sudo bash setup.sh puts it in" if own
                       else f"{name} isn't installed: sudo apt install {name}", 4)
            return
        env = dict(os.environ, TERM="linux")
        if name == "hollywood":
            try:
                os.makedirs(os.path.join(HW_DIR, "byobu"), mode=0o700, exist_ok=True)
            except OSError as ex:
                self.toast(f"hollywood can't start ({ex.strerror or ex})", 3)
                return
            env = hw_env()
            if hw_up():
                hw_kill()                              # (one left from before: a fresh start)
        try:
            fd = os.open(prog_tty(), os.O_RDWR | os.O_NOCTTY)
        except OSError as ex:
            self.toast(f"{name} can't start ({ex.strerror or ex})", 3)
            return
        try:
            try:
                termios.tcflush(fd, termios.TCIFLUSH)  # (keys typed while media mode had the screen: not for it)
            except termios.error:
                pass
            self.prog_key(PROG_GO)                     # (a Ctrl+S in the menus would have it stuck from the start)
            self.prog_mode(KD_TEXT)                    # the console draws it, as in the terminal
            terminal_turn_now()                        # ...turned as the screen is (it takes that in text mode),
                                                       # before it starts: it's the size it'll be, turned
            # (in Pie-tato's session, so the console never becomes its own: when it ends, the console carries on;
            # and it goes if Pie-tato goes)
            args = PROG_ARGS.get(name, []) + (htop_args(path) if name == "htop" else [])
            self.prog = subprocess.Popen([path] + args, stdin=fd, stdout=fd, stderr=fd,
                                         close_fds=True, env=env, preexec_fn=quiet_child)
        except OSError as ex:
            self.prog = None
            self.prog_mode(KD_GRAPHICS)
            self.toast(f"{name} didn't start ({ex.strerror or ex})", 3)
            return
        finally:
            os.close(fd)
        self.prog_name = name
        self.cm_colour, self.cm_bold, self.cm_speed = 0, 0, CM_SPEED
        print(f"{name}: started ({self.prog.pid})", flush=True)

    def prog_stop(self):
        """It stops (cmatrix is told q, as from a keyboard, cacafire Ctrl+C and nyancat Ctrl+C's signal, so each puts
        the console back as it was; hollywood's tmux is closed, panes and all), and media mode has the screen again,
        whatever happens meanwhile."""
        p, name, self.prog, self.prog_name = self.prog, self.prog_name, None, None
        if p is None:
            return
        try:
            if name == "hollywood":
                end = time.monotonic() + 3.0           # (just started: its tmux may be on its way)
                while True:
                    hw_kill()
                    try:
                        p.wait(timeout=0.3)
                    except subprocess.TimeoutExpired:
                        pass
                    if (p.poll() is not None and not hw_up()) or time.monotonic() > end:
                        break
            elif name == "nyancat" and p.poll() is None:
                self.prog_key(PROG_GO)                 # (its output going again, if a keyboard's Ctrl+S held it)
                p.send_signal(signal.SIGINT)           # (its own way out: the cursor and colours as they were)
                try:
                    p.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    pass
            elif p.poll() is None:
                self.prog_key(PROG_GO + PROG_QUIT.get(name, "q"))
                try:
                    p.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    pass
            if p.poll() is None:
                # (cmatrix's lock mode takes no q, and no Ctrl+C: its curses' own way out, then for certain)
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        p.send_signal(sig)
                        p.wait(timeout=1.5)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                    except OSError:
                        break
        finally:
            if p.poll() is None:                       # (cut short: Pie-tato itself stopping. It goes too)
                try:
                    p.kill()
                except OSError:
                    pass
            if name == "hollywood" and hw_up():
                hw_kill()
            print(f"{name}: stopped ({p.returncode})", flush=True)
            self.prog_unblank()
            self.prog_mode(KD_GRAPHICS)
            self.prog_front(wait=True)                 # (a keyboard switched away just now: back in front)
            if self.fb is not None and hasattr(self.fb, "invalidate"):
                self.fb.invalidate()                   # (the edges, black again: it was on them too)
            self.dirty = True

    def prog_home(self):
        """HOME while one's on: it stops, back to the Simulator (True). False: none is on."""
        if self.prog is None:
            return False
        self.prog_stop()
        return True

    def prog_tick(self):
        """It stopped by itself (q on a keyboard, say): media mode has the screen again. Still on: media mode's
        console stays in front."""
        if self.prog is None:
            return
        if self.prog.poll() is not None:
            self.prog_stop()
        else:
            self.prog_front()

    def press_prog(self, name, repeat):
        """A button while one's on: B stops it; for cmatrix and htop, the rest are its keys, typed into it (cacafire's:
        A)."""
        if repeat and not (self.prog_name == "htop" and name in HTOP_HELD):
            return None
        self.prog_unblank()                            # (a key wakes a blanked screen, as a keyboard's does)
        if name == "b":
            self.prog_stop()
        elif self.prog_name == "htop":
            if name in HTOP_KEYS:
                self.prog_key(HTOP_KEYS[name])
        elif self.prog_name == "cacafire":
            if name == "a":
                self.prog_key(" ")                     # (its space bar: it pauses, or goes on)
        elif self.prog_name != "cmatrix":
            return None
        elif name in ("left", "right"):
            self.cm_colour = (self.cm_colour + (1 if name == "right" else -1)) % len(CM_COLOURS)
            self.prog_key(CM_COLOURS[self.cm_colour])
        elif name in ("up", "down"):
            self.cm_speed = max(0, min(9, self.cm_speed + (-1 if name == "up" else 1)))
            self.prog_key(str(self.cm_speed))
        elif name == "x":
            self.cm_bold = (self.cm_bold + 1) % len(CM_BOLD)
            self.prog_key(CM_BOLD[self.cm_bold])
        elif name in CM_KEYS:
            self.prog_key(CM_KEYS[name])
        return None

    def prog_key(self, keys):
        """Keys typed into it, as from a keyboard: put in its console's input (as root may)."""
        try:
            fd = os.open(prog_tty(), os.O_RDWR | os.O_NOCTTY)
        except OSError as ex:
            print(f"console keys: none ({ex})", flush=True)
            return
        try:
            for b in keys.encode():
                fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
        except OSError as ex:
            print(f"console keys: none ({ex})", flush=True)
        finally:
            os.close(fd)

    def prog_mode(self, mode):
        """Media mode's console in text mode (theirs, while one's on) or graphics mode (media mode's)."""
        try:
            if self.ttyfd is not None and PROG_TTY is None:
                fcntl.ioctl(self.ttyfd, KDSETMODE, mode)
                return
            fd = os.open(prog_tty(), os.O_RDWR | os.O_NOCTTY)
            try:
                fcntl.ioctl(fd, KDSETMODE, mode)
            finally:
                os.close(fd)
        except OSError:
            pass

    def prog_front(self, wait=False):
        """Media mode's console in front. In text mode a keyboard can switch to another console (Alt+F1, say),
        which the menus' graphics mode never allows: it's switched straight back, so the buttons and the screen
        stay together (and the menus never draw over another console). wait: until it's in front, for a second
        at most (never for ever: the console can refuse)."""
        if self.ttyfd is None or PROG_TTY is not None:
            return
        try:
            if self.prog_vt() == MEDIA_VT:
                return
            fcntl.ioctl(self.ttyfd, VT_ACTIVATE, MEDIA_VT)
            for _ in range(20 if wait else 0):
                time.sleep(0.05)
                if self.prog_vt() == MEDIA_VT:
                    return
        except OSError:
            pass

    def prog_vt(self):
        """The console in front (its number)."""
        return struct.unpack("HHH", fcntl.ioctl(self.ttyfd, VT_GETSTATE, bytes(6)))[0]

    def prog_unblank(self):
        """The screen on, if the console had blanked it (after minutes without a key, if it's set to)."""
        try:
            fd = os.open(prog_tty(), os.O_RDWR | os.O_NOCTTY)
            try:
                fcntl.ioctl(fd, termios.TIOCLINUX, struct.pack("B", 4))   # TIOCL_UNBLANKSCREEN
            finally:
                os.close(fd)
        except OSError:
            pass
