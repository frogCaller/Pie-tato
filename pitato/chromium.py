"""Chromium, the whole web, on a Pi 4 or 5 (setup.sh puts it in, with cage, which shows one program on the whole screen
with no desktop round it): run as you, in a session of your own on a console of its own (systemd-run, as cage's own
guide starts it), and shown by switching to that console. While it's up the controller is its mouse and a few of its
keys: two of media mode's own uinput devices (named as its others are, so it never takes them for yours), and a thread
moving the pointer and turning the wheel while the sticks, the d-pad, L or R are held. The pointer goes where it's put
(an absolute one, as a tablet's), so it moves as fast as it's told, whatever the mouse settings."""
import math
import os
import pwd
import re
import shutil
import subprocess
import threading
import time

from .config import home_dir
from .screen import slow_pi

CHROMIUM_NAMES = ("chromium", "chromium-browser", "/snap/bin/chromium")   # (Ubuntu's: a snap)
CHROMIUM_UNIT = "pietato-chromium"     # its systemd unit, while it's up
CHROMIUM_VT = 8                        # its console (media mode's is 7)
CHROMIUM_PAM = "pietato-chromium"      # setup.sh's PAM service for it: a session of your own, no password asked
CHROMIUM_FLAGS = ["--no-first-run", "--no-default-browser-check", "--noerrdialogs", "--disable-session-crashed-bubble",
                  "--hide-crash-restore-bubble", "--password-store=basic", "--start-maximized"]
TRANSFORMS = {0: "normal", 90: "90", 180: "180", 270: "270"}   # the screen's turn, as wlr-randr says it (clockwise)
ABS_MOST = 32767         # the pointer's place, 0 to this across the screen and down it
POINTER_HZ = 60          # the pointer's moves a second, while it moves
POINTER_FAST = 0.65      # of the screen's width (its longer side) a second: the stick all the way, the d-pad held long
POINTER_SLOW = 0.05      # ...the d-pad held, at first: up to POINTER_FAST over DPAD_RAMP seconds
DPAD_WAIT = 0.25         # the d-pad held this long before the pointer glides (a press on its own: a nudge)
DPAD_RAMP = 1.0
NUDGE = 0.004            # ...a nudge, of the screen's width (at least 2 pixels)
WHEEL_FAST = 12.0        # the wheel's notches a second, the right stick all the way
WHEEL_SLOW, WHEEL_HELD = 4.0, 16.0   # ...L or R held: from this, up to that over WHEEL_RAMP seconds (a press: a notch)
WHEEL_WAIT, WHEEL_RAMP = 0.35, 1.5
NOTCH = 120              # a notch, in a fine wheel's steps (REL_WHEEL_HI_RES)
STICK_DEAD = 20          # of 127: a stick nearer the middle than this is at rest
SETTLE = 1.0             # seconds after its console's back in front before keys go to it (its session's input back)
KEYS_FIRST = {"T": 0.6}  # ...then after keys that open something (Ctrl+T: a new tab), before typing into it (else 0.15)
KEY_GAP = 0.012          # between the keys typed
US_KEYS = {"`": ("GRAVE", "~"), "1": ("1", "!"), "2": ("2", "@"), "3": ("3", "#"), "4": ("4", "$"), "5": ("5", "%"),
           "6": ("6", "^"), "7": ("7", "&"), "8": ("8", "*"), "9": ("9", "("), "0": ("0", ")"), "-": ("MINUS", "_"),
           "=": ("EQUAL", "+"), "[": ("LEFTBRACE", "{"), "]": ("RIGHTBRACE", "}"), "\\": ("BACKSLASH", "|"),
           ";": ("SEMICOLON", ":"), "'": ("APOSTROPHE", '"'), ",": ("COMMA", "<"), ".": ("DOT", ">"),
           "/": ("SLASH", "?"), " ": ("SPACE", None)}   # a US keyboard's (cage's, as it starts): its key, and shifted
KEY_NAMES = ({"LEFTCTRL", "LEFTSHIFT", "LEFTALT", "ENTER", "TAB", "BACKSPACE", "ESC", "LEFT", "RIGHT", "UP", "DOWN",
              "PAGEUP", "PAGEDOWN", "HOME", "END", "F5", "F11"} | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
             | {v[0] for v in US_KEYS.values()})
# In cage, before Chromium: the screen at the size and turn media mode has it (cage 0.2 on: wlr-randr; an older cage
# turns it itself, and keeps the screen's own size). Then Chromium, through Xwayland when cage has it (Trixie's does),
# at its size for the screen (1.5 times on a TV); else on Wayland at the screen's own (told 1.5 times there, in cage,
# it comes out a quarter of the screen: L2 and R2 zoom it instead). $1 the size ("1920x1080", or nothing), $2 the turn
# ("normal", "90"...), $3 its size (1.5), then Chromium's own command.
LAUNCH = r"""size=$1 turn=$2 scale=$3; shift 3
if command -v wlr-randr >/dev/null 2>&1; then
  for out in $(wlr-randr 2>/dev/null | awk '/^[^ \t]/ {print $1}'); do
    if [ -n "$size" ]; then wlr-randr --output "$out" --mode "$size" >/dev/null 2>&1; fi
    if [ "$turn" != normal ]; then wlr-randr --output "$out" --transform "$turn" >/dev/null 2>&1; fi
  done
fi
if [ -n "$DISPLAY" ]; then exec "$@" --ozone-platform=x11 --force-device-scale-factor="$scale"; fi
exec "$@" --ozone-platform=wayland
"""


_cages = {}


def cage_kind():
    """How cage takes the screen's size and turn: "r", it turns it itself (-r: cage 0.1.4, Bookworm's), at the
    screen's own size; "randr", wlr-randr sets both (cage 0.2 on: Trixie's); "" neither (cage 0.1.5 goes down when
    wlr-randr changes the screen: as it finds it)."""
    path = shutil.which("cage")
    if path not in _cages:
        text = ""
        for arg in ("-h", "-v"):
            try:
                r = subprocess.run([path, arg], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
                text += r.stdout + r.stderr
            except (OSError, TypeError, ValueError, subprocess.SubprocessError):
                pass
        m = re.search(r"version (\d+)\.(\d+)", text)
        _cages[path] = ("r" if re.search(r"^\s*-r\s", text, re.M) else
                        "randr" if m is None or (int(m.group(1)), int(m.group(2))) >= (0, 2) else "")
    return _cages[path]


def chromium_path():
    """Chromium's program, or None."""
    return next((p for p in (shutil.which(n) for n in CHROMIUM_NAMES) if p), None)


def chromium_ready():
    """A Pi 4 or 5 with Chromium and cage (what shows it on the screen, with no desktop)."""
    return not slow_pi() and chromium_path() is not None and shutil.which("cage") is not None


def owner():
    """You: whoever has the home folder (Chromium runs as you, never as root)."""
    try:
        return pwd.getpwuid(os.stat(home_dir()).st_uid).pw_name
    except (OSError, KeyError):
        return None


def chromium_scale(w, h):
    """Chromium's size on this screen: a TV's 1080p as a 720p laptop's (1.5 times), 4K 3 times, anything smaller as it
    is (in quarter steps, by the screen's shorter side)."""
    return max(1.0, math.floor(min(w, h) / 720 * 4) / 4)


def key_for(ch):
    """(the key, as evdev's KEY_ name ends, shift held?) that types a character on a US keyboard, or None."""
    if "a" <= ch <= "z":
        return ch.upper(), False
    if "A" <= ch <= "Z":
        return ch, True
    if ch in US_KEYS:
        return US_KEYS[ch][0], False
    for name, shifted in US_KEYS.values():
        if shifted == ch:
            return name, True
    return {"\n": ("ENTER", False), "\t": ("TAB", False)}.get(ch)


def pam_service():
    """setup.sh's PAM service for it, or the system's own login's (a session all the same)."""
    return CHROMIUM_PAM if os.path.exists(os.path.join("/etc/pam.d", CHROMIUM_PAM)) else "login"


def start_command(url, user, sound="", size="", turn=0, scale=1.0):
    """systemd-run's command line: cage, and Chromium in it, in a session of your own on its console. --wait: it
    returns when they're gone."""
    flags = CHROMIUM_FLAGS + ([f"--alsa-output-device={sound}"] if sound else [])
    props = [f"User={user}", f"PAMName={pam_service()}", f"TTYPath=/dev/tty{CHROMIUM_VT}", "StandardInput=tty-force",
             "StandardOutput=journal", "StandardError=journal", "TTYVHangup=yes", f"UtmpIdentifier=tty{CHROMIUM_VT}",
             "UtmpMode=user", f"WorkingDirectory={home_dir()}", "TimeoutStopSec=5",
             "Environment=XDG_SESSION_TYPE=wayland", f"Environment=XCURSOR_SIZE={round(24 * scale)}"]
    cmd = ["systemd-run", f"--unit={CHROMIUM_UNIT}", "--collect", "--quiet", "--wait"]
    for p in props:
        cmd += ["-p", p]
    cage, how = ["-d"], TRANSFORMS.get(turn, "normal")       # (-d: no window frame of its own)
    kind = cage_kind()
    if kind != "randr":                                       # (an older cage: it turns the screen itself, a quarter
        cage += ["-r"] * (turn // 90 % 4) if kind == "r" else []   # at a time, at the screen's own size)
        size, how = "", "normal"
    return cmd + ["--", shutil.which("cage") or "cage"] + cage + ["--", "/bin/sh", "-c", LAUNCH, "pietato-chromium",
                                                                   size, how, f"{scale:g}",
                                                                   chromium_path() or "chromium"] + \
        flags + ([url] if url else [])


def stop_unit():
    """Its unit stopped (Chromium and cage told to go; after TimeoutStopSec, made to), if it's there."""
    for args in (["stop", CHROMIUM_UNIT], ["reset-failed", CHROMIUM_UNIT]):
        try:
            subprocess.run(["systemctl"] + args, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass


def stop_leftover():
    """One left running by the last Pietato (it stopped while Chromium was up): stopped, on a thread."""
    if chromium_ready():
        threading.Thread(target=stop_unit, daemon=True, name="chromium-leftover").start()


class Chromium:
    """Chromium while it's up: started, looked at (still there?), closed; the pointer, the wheel and the keys."""
    closing = None                             # (the thread closing the last one: the next one waits for it)

    def __init__(self, width=1920, height=1080):
        self.w, self.h = max(int(width), 2), max(int(height), 2)   # the screen as it's seen, in its pixels
        self.x, self.y = self.w / 2, self.h / 2                     # the pointer (where it's been put)
        self.mouse = self.keys = None          # (the uinput devices, while it's up)
        self.sticks = {"lx": 0, "ly": 0, "rx": 0, "ry": 0}
        self.held = {}                         # d-pad directions, L and R held: when each went down
        self.buttons = set()                   # its mouse buttons down now (LEFT: A held, dragging)
        self.moving = threading.Event()        # (the pointer's thread: something's held)
        self.lock = threading.Lock()
        self.proc = None                       # systemd-run, while Chromium's up
        self.alive = False
        self.thread = None
        self.started = 0.0
        self.said = ""                         # what systemd-run said, if it ended

    # -- the program --------------------------------------------------------------------------------------------
    def start(self, url=None, sound="", size="", turn=0, scale=1.0):
        """Chromium started (at url, or its own first page), its devices made first so it has them from the start:
        (True, "") or (False, why)."""
        user = owner()
        if user is None or user == "root":
            return False, "Chromium runs as you, and there's no home folder of yours"
        last = Chromium.closing
        if last is not None:
            last.join(10)                      # (the last one, still going)
        stop_unit()                            # (one left over from before: gone)
        try:
            self.devices()
        except Exception as ex:                # (no uinput: the controller can't work it, a keyboard and mouse can)
            print(f"chromium: no pointer ({ex!r})", flush=True)
        try:
            self.proc = subprocess.Popen(start_command(url, user, sound, size, turn, scale), stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as ex:
            self.close_devices()
            return False, f"Chromium didn't start ({ex.strerror or ex})"
        self.alive = True
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True, name="chromium")
        self.thread.start()
        return True, ""

    def running(self):
        """It's still up (it may have closed itself: its last tab closed, say)."""
        p = self.proc
        if p is None or p.poll() is None:
            return p is not None
        try:
            self.said = (p.stderr.read() or "").strip()[-300:]
        except (OSError, ValueError):
            pass
        return False

    def close(self, wait=False):
        """Chromium gone, and its devices: its unit stopped on a thread of its own (or now, wait)."""
        self.alive = False
        self.moving.set()                      # (the pointer's thread sees it's over)
        p, self.proc = self.proc, None

        def job():
            stop_unit()
            if p is not None:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                p.stderr.close()
            self.close_devices()
        if wait:
            job()
            return
        t = threading.Thread(target=job, daemon=True, name="chromium-close")
        Chromium.closing = t
        t.start()

    # -- its devices -----------------------------------------------------------------------------------------------
    @staticmethod
    def new_device(caps):
        from evdev import UInput
        from .inputs import NAME
        return UInput(caps, name=NAME)

    def devices(self):
        """Its pointer (where it is across and down the screen, three buttons, a wheel that turns finely) and its
        keyboard (the keys it types with, and the few it presses)."""
        from evdev import AbsInfo, ecodes as e
        if self.mouse is None:
            spot = AbsInfo(value=ABS_MOST // 2, min=0, max=ABS_MOST, fuzz=0, flat=0, resolution=0)
            self.mouse = self.new_device({
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
                e.EV_ABS: [(e.ABS_X, spot), (e.ABS_Y, spot)],
                e.EV_REL: [e.REL_WHEEL, e.REL_HWHEEL, getattr(e, "REL_WHEEL_HI_RES", 11),
                           getattr(e, "REL_HWHEEL_HI_RES", 12)]})
        if self.keys is None:
            self.keys = self.new_device({e.EV_KEY: sorted(getattr(e, "KEY_" + n) for n in KEY_NAMES)})

    def close_devices(self):
        with self.lock:
            for dev in (self.mouse, self.keys):
                if dev is not None:
                    try:
                        dev.close()
                    except OSError:
                        pass
            self.mouse = self.keys = None

    def emit(self, which, events):
        """Events from its pointer ("mouse") or keyboard ("keys"), then a SYN (nothing, if it hasn't that device)."""
        with self.lock:
            dev = self.mouse if which == "mouse" else self.keys
            if dev is None or not events:
                return
            try:
                for t, c, v in events:
                    dev.write(t, c, v)
                dev.syn()
            except OSError:
                pass

    # -- the pointer -----------------------------------------------------------------------------------------------
    def place(self):
        """The pointer where it is now, as its device says it."""
        from evdev import ecodes as e
        return [(e.EV_ABS, e.ABS_X, round(self.x / (self.w - 1) * ABS_MOST)),
                (e.EV_ABS, e.ABS_Y, round(self.y / (self.h - 1) * ABS_MOST))]

    def move(self, dx, dy):
        """The pointer this many pixels across and down (no further than the screen's edges)."""
        self.x = min(max(self.x + dx, 0.0), self.w - 1.0)
        self.y = min(max(self.y + dy, 0.0), self.h - 1.0)
        self.emit("mouse", self.place())

    def nudge(self, name):
        """A press of the d-pad: the pointer a little that way (held, it glides after DPAD_WAIT)."""
        step = max(2, round(NUDGE * max(self.w, self.h)))
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(name, (0, 0))
        self.move(dx * step, dy * step)

    def notch(self, name):
        """A press of L (up) or R (down): the page a notch that way (held, it scrolls on after WHEEL_WAIT)."""
        from evdev import ecodes as e
        d = 1 if name == "l" else -1
        self.emit("mouse", [(e.EV_REL, getattr(e, "REL_WHEEL_HI_RES", 11), d * NOTCH), (e.EV_REL, e.REL_WHEEL, d)])

    def click(self, down, button="LEFT"):
        """A mouse button down (or up: only one that's down), where the pointer is."""
        from evdev import ecodes as e
        if not down and button not in self.buttons:
            return
        (self.buttons.add if down else self.buttons.discard)(button)
        self.emit("mouse", self.place() + [(e.EV_KEY, getattr(e, "BTN_" + button), 1 if down else 0)])

    def stick(self, axis, value):
        """A stick moved (lx ly rx ry, -127 to 127): the left one moves the pointer, the right one scrolls."""
        if axis in self.sticks:
            self.sticks[axis] = value if abs(value) >= STICK_DEAD else 0
            self.wake()

    def hold(self, name, down):
        """A d-pad direction, L or R, held down (or let go of)."""
        if down:
            self.held.setdefault(name, time.monotonic())
            self.wake()
        else:
            self.held.pop(name, None)

    def let_go(self):
        """Nothing held any more: the sticks at rest, its buttons up (its console's going out of the way)."""
        self.sticks = {k: 0 for k in self.sticks}
        self.held.clear()
        for button in list(self.buttons):
            self.click(False, button)

    def wake(self):
        if self.alive:
            self.moving.set()

    # -- its keys --------------------------------------------------------------------------------------------------
    def key(self, *names):
        """Keys pressed together, then let go of (Alt and Left: back)."""
        from evdev import ecodes as e
        codes = [getattr(e, "KEY_" + n) for n in names]
        self.emit("keys", [(e.EV_KEY, c, 1) for c in codes])
        self.emit("keys", [(e.EV_KEY, c, 0) for c in reversed(codes)])

    def type_text(self, text, enter=False):
        """Text typed a key at a time, as on a US keyboard (what it has no key for, left out)."""
        for ch in text:
            k = key_for(ch)
            if k is None:
                continue
            self.key(*(("LEFTSHIFT", k[0]) if k[1] else (k[0],)))
            time.sleep(KEY_GAP)
        if enter:
            self.key("ENTER")

    def send(self, keys=None, text="", enter=False, wait=None):
        """In a moment (SETTLE: its console just back in front, its session takes its input back first), on a thread
        of its own: keys pressed (Ctrl+L, say), then text typed, then Enter."""
        def job():
            time.sleep(SETTLE if wait is None else wait)
            if not self.alive:
                return
            if keys:
                self.key(*keys)
                if text or enter:              # (the address box, or a new tab's, opened: then what goes in it)
                    time.sleep(KEYS_FIRST.get(keys[-1], 0.15))
            self.type_text(text, enter)
        threading.Thread(target=job, daemon=True, name="chromium-keys").start()

    # -- the pointer and the wheel, while they're held -------------------------------------------------------------
    @staticmethod
    def curve(v):
        """A stick's push (-127 to 127) as a speed, -1 to 1: gentle near the middle, quick at the edge."""
        s = (abs(v) - STICK_DEAD) / (127 - STICK_DEAD) if abs(v) >= STICK_DEAD else 0.0
        return s * s * (1 if v > 0 else -1)

    def speeds(self, now):
        """(the pointer across and down, in pixels a second; the wheel up and right, in notches a second) from
        what's held now."""
        side = max(self.w, self.h)
        vx = self.curve(self.sticks["lx"]) * POINTER_FAST * side
        vy = self.curve(self.sticks["ly"]) * POINTER_FAST * side
        for name, (dx, dy) in (("left", (-1, 0)), ("right", (1, 0)), ("up", (0, -1)), ("down", (0, 1))):
            t = now - self.held.get(name, now)
            if name in self.held and t >= DPAD_WAIT:
                k = min(1.0, (t - DPAD_WAIT) / DPAD_RAMP)
                v = (POINTER_SLOW + (POINTER_FAST - POINTER_SLOW) * k * k) * side
                vx, vy = vx + dx * v, vy + dy * v
        wy = -self.curve(self.sticks["ry"]) * WHEEL_FAST
        wx = self.curve(self.sticks["rx"]) * WHEEL_FAST
        for name, d in (("l", 1), ("r", -1)):
            t = now - self.held.get(name, now)
            if name in self.held and t >= WHEEL_WAIT:
                k = min(1.0, (t - WHEEL_WAIT) / WHEEL_RAMP)
                wy += d * (WHEEL_SLOW + (WHEEL_HELD - WHEEL_SLOW) * k * k)
        return vx, vy, wy, wx

    def step(self, now, dt, wheel):
        """One step: the pointer moved, the wheel turned, for what's held; wheel: what's left over of a fine step,
        and of a notch, (up, right), for the next. False: nothing's held (and nothing's moving)."""
        from evdev import ecodes as e
        vx, vy, wy, wx = self.speeds(now)
        if vx or vy:
            self.move(vx * dt, vy * dt)
        events = []
        for i, (v, fine, whole) in enumerate(((wy, getattr(e, "REL_WHEEL_HI_RES", 11), e.REL_WHEEL),
                                              (wx, getattr(e, "REL_HWHEEL_HI_RES", 12), e.REL_HWHEEL))):
            if not v:
                wheel[i] = [0.0, 0]
                continue
            wheel[i][0] += v * dt * NOTCH
            n = int(wheel[i][0])               # (fine steps: a wheel that turns smoothly)
            if n:
                wheel[i][0] -= n
                wheel[i][1] += n
                events.append((e.EV_REL, fine, n))
                whole_n = int(wheel[i][1] / NOTCH)   # (and its notches, for what only has those)
                if whole_n:
                    wheel[i][1] -= whole_n * NOTCH
                    events.append((e.EV_REL, whole, whole_n))
        self.emit("mouse", events)
        return bool(vx or vy or wy or wx or self.held or any(self.sticks.values()))

    def run(self):
        wheel = [[0.0, 0], [0.0, 0]]
        last = None
        while self.alive:
            if not self.moving.wait(0.5):
                continue
            if not self.alive:
                break
            now = time.monotonic()
            dt = 1 / POINTER_HZ if last is None else min(now - last, 0.1)
            last = now
            if not self.step(now, dt, wheel):
                self.moving.clear()            # (till something's held again)
                wheel, last = [[0.0, 0], [0.0, 0]], None
                if self.held or any(self.sticks.values()):
                    self.moving.set()          # (one held just now, as it stopped)
                continue
            time.sleep(1 / POINTER_HZ)
