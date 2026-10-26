"""Buttons and keys: game controllers, the keys they stand for in terminal mode, a real keyboard (its keys as the
buttons in media mode, and typing while the on-screen one is up), a trackpad or mouse (its swipes the d-pad in media
mode), and the GPi Case's power switch."""
import json
import os
import selectors
import signal
import threading
import time
from evdev import ecodes as e, InputDevice, list_devices


# ---- gamepad code -> button name ------------------------------------------
CODES = {
    e.BTN_SOUTH: "a", e.BTN_EAST: "b", e.BTN_NORTH: "x", e.BTN_WEST: "y",
    e.BTN_TL: "l", e.BTN_TR: "r", e.BTN_TL2: "l2", e.BTN_TR2: "r2",
    e.BTN_SELECT: "select", e.BTN_START: "start", e.BTN_MODE: "home",
    e.BTN_DPAD_UP: "up", e.BTN_DPAD_DOWN: "down",
    e.BTN_DPAD_LEFT: "left", e.BTN_DPAD_RIGHT: "right",
}
AXES = {  # d-pad reported as axes
    e.ABS_HAT0X: {-1: "left", 1: "right"},
    e.ABS_HAT0Y: {-1: "up", 1: "down"},
    e.ABS_X:     {-1: "left", 1: "right"},
    e.ABS_Y:     {-1: "up", 1: "down"},
}
TRIGGERS = {e.ABS_Z: "l2", e.ABS_RZ: "r2"}   # L2 and R2 as triggers (on a pad that has a right stick besides)

# a plain USB pad with no standard layout ("USB Gamepad", most SNES-style pads): the usual
# order of its buttons. If yours differs, set it up in Settings > Controller.
JOY_CODES = {
    e.BTN_TRIGGER: "x", e.BTN_THUMB: "a", e.BTN_THUMB2: "b", e.BTN_TOP: "y",
    e.BTN_TOP2: "l", e.BTN_PINKIE: "r", e.BTN_BASE: "l", e.BTN_BASE2: "r",
    e.BTN_BASE3: "select", e.BTN_BASE4: "start",
}
PADS_FILE = "/var/lib/pitato/pads.json"      # buttons set up in Settings > Controller, and Swap A and B
AB = {"a": "b", "b": "a"}    # Settings > Swap A and B: on a controller that has them the other way round
NOT_PADS = ("motion sensors", "touchpad", "accelerometer", "consumer control", "system control")
BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "select", "start", "home", "l2", "r2")
LEARN_STEPS = [   # Settings > Controller: (button, what to press, can be skipped)
    ("a", "A, the OK button", False), ("b", "B, the back button", False),
    ("up", "UP on the d-pad", False), ("down", "DOWN on the d-pad", False),
    ("left", "LEFT on the d-pad", False), ("right", "RIGHT on the d-pad", False),
    ("x", "X", True), ("y", "Y", True), ("l", "L, the left shoulder button", True),
    ("r", "R, the right shoulder button", True), ("select", "SELECT", True),
    ("start", "START", True), ("home", "HOME, or the Guide button", True),
]
LEARN_SKIP = 8             # seconds before a button your controller may not have is skipped

# the GPi Case 2W's star button (TURBO, to the case): with HOME, or on its own, it's HOME. The case
# may keep it to itself, for its turbo; when it does send it, Settings > Controller asks for it last.
STAR = "star"
STAR_STEP = (STAR, "the star (TURBO) button", True)
STAR_TAP = 0.5             # the star on its own: let go within this, with no other button, or it's nothing
PAD_BUTTONS = BUTTONS + (STAR,)


def learn_steps(gpi=False):
    """Settings > Controller's steps: on the GPi Case, its star button last."""
    return LEARN_STEPS + [STAR_STEP] if gpi else list(LEARN_STEPS)


MEDIA_TOGGLE = "home"


# ---- terminal mode: button -> keys ----------------------------------------
TERMINAL = {
    "a":      [e.KEY_ENTER],
    "b":      [e.KEY_BACKSPACE],
    "x":      [e.KEY_TAB],
    "y":      [e.KEY_LEFTCTRL, e.KEY_C],
    "l":      [e.KEY_PAGEUP],
    "r":      [e.KEY_PAGEDOWN],
    "select": [e.KEY_Q],
    "start":  [e.KEY_ESC],
    "up":     [e.KEY_UP],
    "down":   [e.KEY_DOWN],
    "left":   [e.KEY_LEFT],
    "right":  [e.KEY_RIGHT],
}
REPEAT = {e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_BACKSPACE}
REPEAT_DELAY = 0.40
REPEAT_RATE = 0.06


# the keys of the on-screen keyboard, and what a real keyboard's keys type
KEY_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"]
KEY_SYMBOLS = ["!@#$%^&*()", "-_=+[]{}\\|", ";:'\"<>,.?/", "`~€£¥•°§¿¡"]
KEY_BOTTOM = [("shift", "⇧", 1.5), ("sym", "#+=", 1.5), ("space", "space", 3.5), ("back", "⌫", 1.5),
              ("done", "Done", 2)]


def keyboard_chars():
    table = {}
    for ch in "abcdefghijklmnopqrstuvwxyz":
        code = getattr(e, "KEY_" + ch.upper())
        table[code] = (ch, ch.upper())
    for ch, sh in zip("1234567890", "!@#$%^&*()"):
        table[getattr(e, "KEY_" + ch)] = (ch, sh)
    for name, pair in (("SPACE", (" ", " ")), ("MINUS", ("-", "_")), ("EQUAL", ("=", "+")),
                       ("COMMA", (",", "<")), ("DOT", (".", ">")), ("SLASH", ("/", "?")),
                       ("SEMICOLON", (";", ":")), ("APOSTROPHE", ("'", '"'))):
        table[getattr(e, "KEY_" + name)] = pair
    return table


class KeyReader:
    """A real keyboard (the BBQ20, say) while a text box is up: its keys come here
    instead of going to the hidden console, until the box closes."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.on_key = lambda kind, ch="": None      # ("char", c), ("back",), ("done",), ("cancel",)
        self.exclude = set()

    def start(self):
        if self.thread and self.thread.is_alive():
            self.running = False
            self.thread.join(1)
        devs = []
        try:
            for path in list_devices():
                if path in self.exclude:
                    continue
                dev = InputDevice(path)
                keys = dev.capabilities().get(e.EV_KEY, [])
                if dev.name != NAME and e.KEY_A in keys and e.KEY_Z in keys and e.KEY_ENTER in keys:
                    try:
                        dev.grab()
                    except OSError:
                        pass
                    devs.append(dev)
                else:
                    dev.close()
        except Exception:
            pass
        if devs:
            self.running = True
            self.thread = threading.Thread(target=self.loop, args=(devs,), daemon=True, name="keyboard")
            self.thread.start()

    def stop(self):
        self.running = False

    def loop(self, devs):
        table = keyboard_chars()
        shift = False
        sel = selectors.DefaultSelector()
        for dev in devs:
            sel.register(dev, selectors.EVENT_READ)
        try:
            while self.running:
                for key, _ in sel.select(0.2):
                    try:
                        events = list(key.fileobj.read())
                    except OSError:
                        sel.unregister(key.fileobj)
                        continue
                    for ev in events:
                        if ev.type != e.EV_KEY:
                            continue
                        if ev.code in (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT):
                            shift = ev.value != 0
                        elif ev.value == 0:
                            continue
                        elif ev.code in table:
                            self.on_key("char", table[ev.code][1 if shift else 0])
                        elif ev.code == e.KEY_BACKSPACE:
                            self.on_key("back")
                        elif ev.code in (e.KEY_ENTER, e.KEY_KPENTER):
                            self.on_key("done")
                        elif ev.code == e.KEY_ESC:
                            self.on_key("cancel")
        finally:
            for dev in devs:
                try:
                    dev.ungrab()
                except OSError:
                    pass
                try:
                    dev.close()
                except OSError:
                    pass


NAME = "pitato"


# ---- a keyboard in media mode: its keys are the buttons --------------------------------------------
# W A S D is the d-pad (for a keyboard with no arrows: the BB9900's, say), and the arrows; Enter or the space
# bar A; Backspace or Esc B; X and Y; Q and E (or [ and ]) L and R; P START, O SELECT. HOME stays the
# controller's: a key pressed by mistake would leave you typing into the terminal.
KEYBOARD_BUTTONS = {
    e.KEY_W: "up", e.KEY_A: "left", e.KEY_S: "down", e.KEY_D: "right",
    e.KEY_UP: "up", e.KEY_LEFT: "left", e.KEY_DOWN: "down", e.KEY_RIGHT: "right",
    e.KEY_ENTER: "a", e.KEY_KPENTER: "a", e.KEY_SPACE: "a",
    e.KEY_BACKSPACE: "b", e.KEY_ESC: "b",
    e.KEY_X: "x", e.KEY_Y: "y",
    e.KEY_Q: "l", e.KEY_E: "r", e.KEY_LEFTBRACE: "l", e.KEY_RIGHTBRACE: "r",
    e.KEY_P: "start", e.KEY_O: "select",
}

# a trackpad (the BB9900's) or a mouse, in media mode: a swipe is the d-pad, a step for each bit of the way it goes
# (the first comes soon, so a short swipe is one); pressed (its left button) it's A, its right button B. A wheel
# (the BB9900's trackpad with Caps Lock on) steps too, a step a click.
MOUSE_BUTTONS = {e.BTN_LEFT: "a", e.BTN_RIGHT: "b"}
SWIPE_FIRST = 50       # moved this far, a swipe's first step (in the mouse's counts: about 30 a mm on the BB9900's)
SWIPE_MORE = 100       # ...and this much further for each one after it, the same way
SWIPE_REST = 0.2       # still this long (the finger lifted): what moves next is a new swipe
SWIPE_SLOW = 0.6       # a step's way gone in this long, or it's forgotten (a finger resting on it, a mouse nudged)
SWIPE_MOST = 4         # steps at once, at most (one big jump of the mouse)
WHEEL = {(e.REL_WHEEL, 1): "up", (e.REL_WHEEL, -1): "down", (e.REL_HWHEEL, 1): "right", (e.REL_HWHEEL, -1): "left"}
STEPS = {("y", 1): "down", ("y", -1): "up", ("x", 1): "right", ("x", -1): "left"}


def is_keyboard(dev):
    """A keyboard (a Bluetooth one, the BBQ20...): letters and Enter. Not our own keys (a controller's, typed
    into the terminal)."""
    if dev.name == NAME:
        return False
    keys = set(dev.capabilities().get(e.EV_KEY, []))
    return {e.KEY_A, e.KEY_Z, e.KEY_ENTER} <= keys


def is_mouse(dev):
    """A mouse, or a trackpad that is one (the BB9900 keyboard's, on its own or in with its keys): it moves left
    and right and up and down, and has a button."""
    if dev.name == NAME:
        return False
    caps = dev.capabilities()
    return {e.REL_X, e.REL_Y} <= set(caps.get(e.EV_REL, [])) and e.BTN_LEFT in caps.get(e.EV_KEY, [])


class Keys:
    """A keyboard, for media mode: its keys as the buttons (KEYBOARD_BUTTONS); its trackpad, or a mouse, too
    (its swipes the d-pad, its buttons MOUSE_BUTTONS). Only media mode asks it: the terminal, a text box (KeyReader)
    and cmatrix and the others have its keys as they are."""

    def __init__(self, dev, mouse=False):
        self.dev, self.path = dev, dev.path
        self.mouse = mouse                             # just a mouse (a keyboard's trackpad, on its own): no keys
        self.codes = set()                             # its keys (and mouse buttons) held down that are buttons
        self.swipe_reset()

    def held(self):
        return {KEYBOARD_BUTTONS.get(c) or MOUSE_BUTTONS[c] for c in self.codes}

    @staticmethod
    def pointer(ev):
        """It's its mouse's (moving, its wheel, its buttons), not a key."""
        return ev.type in (e.EV_REL, e.EV_SYN) or (ev.type == e.EV_KEY and ev.code in MOUSE_BUTTONS)

    def translate(self, ev, now=None):
        """[(button, pressed)] for one raw event: a button's down while any of its keys is (W and the up arrow
        both up); a swipe's steps, each pressed and let go."""
        if ev.type in (e.EV_REL, e.EV_SYN):
            if now is None:                            # when it moved, not when it's read (the menus drawing slowly
                when = getattr(ev, "timestamp", None)  # on a Pi Zero don't make one swipe two)
                now = when() if callable(when) else time.monotonic()
            return self.swipe(ev, now)
        if ev.type != e.EV_KEY or ev.value not in (0, 1):
            return []
        name = KEYBOARD_BUTTONS.get(ev.code) or MOUSE_BUTTONS.get(ev.code)
        if name is None:
            return []
        was = name in self.held()
        if ev.value:
            self.codes.add(ev.code)
        else:
            self.codes.discard(ev.code)
        if ev.code in MOUSE_BUTTONS:
            self.swipe_reset()                         # (pressing it may roll the finger a little: not a swipe)
        down = name in self.held()
        return [(name, down)] if down != was else []

    def swipe_reset(self):
        """No swipe going: the next movement starts one."""
        self.dx = self.dy = 0                          # moved since the last step
        self.axis, self.steps = None, 0                # "x" or "y": the way it's going, once it's stepped
        self.since = self.last = float("-inf")         # when the way to the next step began; when it last moved

    def swipe(self, ev, now):
        """[(button, pressed)] for its moving: nothing till the report's end (all of it in), its wheel's at once."""
        if ev.type == e.EV_SYN:
            if ev.code == e.SYN_DROPPED:
                self.swipe_reset()                     # (some of it lost: start afresh)
                return []
            return self.swipe_steps(now) if ev.code == e.SYN_REPORT else []
        if not ev.value:
            return []
        name = WHEEL.get((ev.code, 1 if ev.value > 0 else -1))
        if name:                                       # a wheel: a step a click
            return [(name, d) for _ in range(min(abs(ev.value), SWIPE_MOST)) for d in (True, False)]
        if ev.code not in (e.REL_X, e.REL_Y) or self.codes & MOUSE_BUTTONS.keys():
            return []                                  # (moved while it's pressed: nothing)
        if now - self.last > SWIPE_REST:
            self.swipe_reset()                         # a new swipe
            self.since = now
        elif now - self.since > SWIPE_SLOW:
            self.dx = self.dy = 0                      # too slow for a step: forgotten
            self.since = now
        self.last = now
        if ev.code == e.REL_X:
            self.dx += ev.value
        else:
            self.dy += ev.value
        return []

    def swipe_steps(self, now):
        """[(button, pressed)]: the steps it's gone since the last, each one pressed and let go. A swipe keeps to
        the way it started (up and down, or left and right) until it rests."""
        out = []
        for _ in range(SWIPE_MOST):
            axis = self.axis or ("y" if abs(self.dy) >= abs(self.dx) else "x")
            moved = self.dy if axis == "y" else self.dx
            need = SWIPE_MORE if self.steps else SWIPE_FIRST
            if abs(moved) < need:
                return out
            way = 1 if moved > 0 else -1
            name = STEPS[(axis, way)]
            out += [(name, True), (name, False)]
            self.axis, self.steps, self.since = axis, self.steps + 1, now
            if axis == "y":
                self.dx, self.dy = 0, moved - way * need
            else:
                self.dx, self.dy = moved - way * need, 0
        self.dx = self.dy = 0                          # (as many as there may be at once: the rest dropped)
        return out

    def let_go(self, kind=None):
        """The buttons it's holding down, let go of (they aren't media mode's now): all of them, or just its keys'
        ("keys") or its mouse's ("pointer", a swipe going forgotten too)."""
        before = self.held()
        if kind == "keys":
            self.codes = {c for c in self.codes if c in MOUSE_BUTTONS}
        else:
            self.codes = set() if kind is None else {c for c in self.codes if c not in MOUSE_BUTTONS}
            self.swipe_reset()
        return sorted(before - self.held())


# ---- input: controllers ---------------------------------------------------------
CHORD_WAIT = 0.25   # no HOME button: how long SELECT or START waits to see if the other comes
SCAN_EVERY = 2.0    # seconds between looks for controllers plugged in


def pad_kind(dev):
    """'gamepad' for the standard layout (Xbox, PlayStation, 8BitDo, the GPi Case...),
    'joystick' for a plain USB pad that numbers its buttons, None for keyboards, mice and the rest."""
    name = (dev.name or "").lower()
    if dev.name == NAME or any(w in name for w in NOT_PADS):
        return None
    keys = set(dev.capabilities().get(e.EV_KEY, []))
    if keys & {e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_DPAD_UP}:
        return "gamepad"
    if any(e.BTN_TRIGGER <= k <= e.BTN_TRIGGER + 15 for k in keys):
        return "joystick"
    return None


def pad_ident(dev):
    """The controller's model: every one of the same model gets the same buttons."""
    try:
        return f"{dev.info.vendor:04x}:{dev.info.product:04x}:{dev.name}"
    except AttributeError:
        return dev.name


class Pad:
    """One controller: its raw events in, button names out."""

    def __init__(self, dev, kind, learned=None):
        self.dev, self.kind, self.path = dev, kind, dev.path
        self.ident = pad_ident(dev)
        self.has = set(dev.capabilities().get(e.EV_KEY, []))
        self.info = {}                                 # axis -> its range
        self.apply(learned)

    def apply(self, learned=None):
        """Its buttons: the standard ones for its kind, with those set up in Settings > Controller
        in their place (one that wasn't set up keeps its standard code); then A and B swapped, if
        Settings > Swap A and B has them swapped on it."""
        if self.kind == "joystick":
            keys = dict(JOY_CODES)
            keys.update({c: n for c, n in CODES.items() if c in self.has})
        else:
            keys = dict(CODES)
        axes = {c: dict(d) for c, d in AXES.items()}
        names = set()
        if isinstance(learned, dict):
            try:
                lk = {int(c): n for c, n in (learned.get("keys") or {}).items() if n in PAD_BUTTONS}
                la = {int(c): {int(d): n for d, n in dirs.items() if n in PAD_BUTTONS and int(d) in (-1, 1)}
                      for c, dirs in (learned.get("axes") or {}).items()}
            except (TypeError, ValueError, AttributeError):
                lk, la = {}, {}
            names = set(lk.values()) | {n for dirs in la.values() for n in dirs.values()}
            keys = {c: n for c, n in keys.items() if n not in names}
            keys.update(lk)
            axes.update(la)
        self.learned = bool(names)
        self.swapped = isinstance(learned, dict) and bool(learned.get("swap"))
        if self.swapped:
            keys = {c: AB.get(n, n) for c, n in keys.items()}
            axes = {c: {d: AB.get(n, n) for d, n in dirs.items()} for c, dirs in axes.items()}
        self.keys, self.axes = keys, axes
        sticks = set(self.axis_codes())
        self.triggers = ({c: n for c, n in TRIGGERS.items() if c not in axes and n not in names}
                         if {e.ABS_Z, e.ABS_RZ, e.ABS_RX, e.ABS_RY} <= sticks else {})
        self.home = (any(n == "home" and c in self.has for c, n in keys.items())
                     or any("home" in dirs.values() for dirs in axes.values()))
        self.now = {}                                  # axis -> the way it's pushed: -1, 0, 1
        self.down = set()                              # buttons held down
        self.sticks = {}                               # axis -> lx ly (the left stick), rx ry (the right)
        if {e.ABS_X, e.ABS_Y} <= sticks:
            self.sticks.update({e.ABS_X: "lx", e.ABS_Y: "ly"})
        if {e.ABS_RX, e.ABS_RY} <= sticks:
            self.sticks.update({e.ABS_RX: "rx", e.ABS_RY: "ry"})
        elif {e.ABS_Z, e.ABS_RZ} <= sticks and not self.triggers:
            self.sticks.update({e.ABS_Z: "rx", e.ABS_RZ: "ry"})   # (a plain USB pad's right stick)

    def has_stick(self):
        return e.ABS_X in self.sticks

    def has_button(self, name):
        """It has this button (or an axis or trigger that's it)."""
        return (any(n == name and c in self.has for c, n in self.keys.items()) or name in self.triggers.values()
                or any(name in dirs.values() for dirs in self.axes.values()))

    def stick_value(self, code, value):
        """How far a stick's pushed along an axis: -127 to 127 (up and left are minus)."""
        info = self.info.get(code)
        if info is None:
            try:
                info = self.info[code] = self.dev.absinfo(code)
            except OSError:
                return 0
        center = (info.min + info.max) / 2
        span = (info.max - info.min) / 2 or 1
        return int(round(max(-1.0, min(1.0, (value - center) / span)) * 127))

    def stick(self, ev):
        """(lx ly rx ry, -127 to 127) for a stick moved, or None: it wasn't one."""
        if ev.type != e.EV_ABS or ev.code not in self.sticks:
            return None
        return self.sticks[ev.code], self.stick_value(ev.code, ev.value)

    def sticks_now(self):
        """[(lx ly rx ry, -127 to 127)]: where its sticks are now."""
        out = []
        for code, axis in self.sticks.items():
            try:
                out.append((axis, self.stick_value(code, self.dev.absinfo(code).value)))
            except OSError:
                pass
        return out

    def axis_codes(self):
        try:
            return list(self.dev.capabilities(absinfo=False).get(e.EV_ABS, []))
        except OSError:
            return []

    def direction(self, code, value):
        """-1, 0 or 1: an axis pushed past halfway one way or the other."""
        info = self.info.get(code)
        if info is None:
            try:
                info = self.info[code] = self.dev.absinfo(code)
            except OSError:
                return 0
        center = (info.min + info.max) / 2
        span = (info.max - info.min) / 2 or 1
        n = (value - center) / span
        return -1 if n < -0.5 else 1 if n > 0.5 else 0

    def translate(self, ev):
        """[(button, pressed)] for one raw event."""
        out = []
        if ev.type == e.EV_KEY and ev.value in (0, 1):
            name = self.keys.get(ev.code)
            if name:
                out.append((name, ev.value == 1))
        elif ev.type == e.EV_ABS and ev.code in self.triggers:
            info = self.info.get(ev.code)
            if info is None:
                try:
                    info = self.info[ev.code] = self.dev.absinfo(ev.code)
                except OSError:
                    return out
            on = 1 if (ev.value - info.min) > (info.max - info.min) / 2 else 0
            if on != self.now.get(ev.code, 0):
                self.now[ev.code] = on
                out.append((self.triggers[ev.code], bool(on)))
        elif ev.type == e.EV_ABS and ev.code in self.axes:
            d = self.direction(ev.code, ev.value)
            old = self.now.get(ev.code, 0)
            if d != old:
                self.now[ev.code] = d
                dirs = self.axes[ev.code]
                if old and dirs.get(old):
                    out.append((dirs[old], False))
                if d and dirs.get(d):
                    out.append((dirs[d], True))
        for name, down in out:
            if down:
                self.down.add(name)
            else:
                self.down.discard(name)
        return out


class Pads:
    """The controllers plugged in, looked for again every couple of seconds."""

    def __init__(self, sel):
        self.sel = sel
        self.by_path = {}
        self.keyboards = {}          # path -> Keys: keyboards (and mice), their keys the buttons in media mode
        self.skip = {}               # path -> its device node: looked at, not a controller
        self.power = {}              # path -> PowerKey: the case's power switch
        self.gpi = gpi_case_set_up()
        self.power_told = False
        self.next_scan = 0.0
        self.saved = self.load()     # model -> the buttons set up for it

    @staticmethod
    def load():
        try:
            with open(PADS_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def write(self):
        try:
            os.makedirs(os.path.dirname(PADS_FILE), exist_ok=True)
            tmp = PADS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.saved, f, indent=1)
            os.replace(tmp, PADS_FILE)
        except OSError as ex:
            print(f"couldn't save the controller's buttons: {ex}", flush=True)

    def save(self, ident, keys, axes):
        """Settings > Controller's buttons: the ones pressed are the ones it has (A and B as they were set up,
        not swapped)."""
        self.saved[ident] = {"keys": {str(c): n for c, n in keys.items()},
                             "axes": {str(c): {str(d): n for d, n in dirs.items()} for c, dirs in axes.items()}}
        self.write()
        for pad in self.by_path.values():
            if pad.ident == ident:
                pad.apply(self.saved[ident])

    def swap(self, ident, on):
        """Settings > Swap A and B: A and B the other way round on this model of controller (on), or back."""
        entry = dict(self.saved.get(ident) or {})
        if on:
            entry["swap"] = True
        else:
            entry.pop("swap", None)
        if entry:
            self.saved[ident] = entry
        else:
            self.saved.pop(ident, None)
        self.write()
        for pad in self.by_path.values():
            if pad.ident == ident:
                was, now, down = pad.swapped, pad.now, pad.down
                pad.apply(self.saved.get(ident))
                pad.now = now                          # (one held now is let go of as what it's called now)
                pad.down = {AB.get(n, n) for n in down} if was != pad.swapped else down

    def forget(self):
        """Every controller back to its standard buttons."""
        self.saved = {}
        self.write()
        for pad in self.by_path.values():
            pad.apply(None)

    def scan(self, now, force=False):
        """Controllers (and keyboards and mice) plugged in since the last look: [Pad or Keys]."""
        if now < self.next_scan and not force:
            return []
        self.next_scan = now + SCAN_EVERY
        try:
            paths = set(list_devices())
        except OSError:
            return []
        for path in list(self.skip):
            if path not in paths:
                del self.skip[path]
        new = []
        for path in sorted(paths):
            if path in self.by_path or path in self.power or path in self.keyboards:
                continue
            try:
                node = os.stat(path).st_ino
                if self.skip.get(path) == node:
                    continue
                dev = InputDevice(path)
            except OSError:
                continue
            try:
                kind = pad_kind(dev)
                if not kind:
                    if is_power_switch(dev, self.gpi):
                        switch = PowerKey(dev)
                        self.sel.register(dev, selectors.EVENT_READ, switch)
                        self.power[path] = switch
                        print(f"power switch: {dev.name} ({path})", flush=True)
                        continue
                    keyboard = is_keyboard(dev)
                    if keyboard or is_mouse(dev):      # (a keyboard's trackpad may be a mouse of its own)
                        kb = Keys(dev, mouse=not keyboard)
                        self.sel.register(dev, selectors.EVENT_READ, kb)
                        self.keyboards[path] = kb
                        print(f"{'mouse' if kb.mouse else 'keyboard'}: {dev.name} ({path})", flush=True)
                        new.append(kb)
                        continue
                    dev.close()
                    self.skip[path] = node
                    continue
                pad = Pad(dev, kind, self.saved.get(pad_ident(dev)))
                self.sel.register(dev, selectors.EVENT_READ, pad)
            except (OSError, ValueError, KeyError):
                try:
                    dev.close()
                except OSError:
                    pass
                continue
            self.by_path[path] = pad
            print(f"controller: {dev.name} ({path})", flush=True)
            new.append(pad)
        if self.gpi and not self.power and not self.power_told:
            self.power_told = True
            print("power switch: not found (setup.sh's GPi Case settings work once the Pi has "
                  "restarted)", flush=True)
        return new

    def drop(self, pad):
        if isinstance(pad, PowerKey):
            self.power.pop(pad.path, None)
        elif isinstance(pad, Keys):
            self.keyboards.pop(pad.path, None)
        else:
            self.by_path.pop(pad.path, None)
        try:
            self.sel.unregister(pad.dev)
        except (KeyError, ValueError, OSError):
            pass
        try:
            pad.dev.close()
        except OSError:
            pass


# ---- input: the case's power switch ---------------------------------------------------
BUS_HOST = 0x19                  # a device on the Pi's own pins, rather than USB or Bluetooth
HALT_WAIT = 30.0                 # how long 'Shutting down' waits for the Pi to go before giving up
CONFIG_TXT = ("/boot/firmware/config.txt", "/boot/config.txt")


def gpi_case_set_up():
    """True when setup.sh set this Pi up for the GPi Case 2W (its part of config.txt is there)."""
    for path in CONFIG_TXT:
        try:
            with open(path, errors="ignore") as f:
                if "# >>> gpi-case setup >>>" in f.read():
                    return True
        except OSError:
            pass
    return False


def input_driver(dev):
    """The kernel driver behind an input device ('gpio-keys'...), from sysfs: '' when unknown."""
    try:
        path = f"/sys/class/input/{os.path.basename(dev.path)}/device/device/driver"
        return os.path.basename(os.readlink(path))
    except (OSError, AttributeError, TypeError):
        return ""


def is_power_switch(dev, gpi=False):
    """A power switch on the Pi's own pins (the gpio-keys driver's): the one the gpio-shutdown
    line in config.txt makes (setup.sh adds it for the GPi Case 2W), or on the GPi Case, any.
    Not a remote's power button, or a keyboard's."""
    try:
        if dev.info.bustype != BUS_HOST or e.KEY_POWER not in dev.capabilities().get(e.EV_KEY, []):
            return False
        where = os.path.realpath(f"/sys/class/input/{os.path.basename(dev.path)}/device")
    except (OSError, AttributeError, TypeError):
        return False
    if input_driver(dev) != "gpio-keys":
        return False
    return gpi or "shutdown" in (dev.name or "").lower() or "shutdown" in where.lower()


class PowerKey:
    """The power switch. Switched off, the Pi shuts down: systemd-logind does that too when it
    can, and this makes sure of it, whichever mode the screen is in."""

    def __init__(self, dev):
        self.dev, self.path = dev, dev.path

    @staticmethod
    def switched_off(events):
        return any(ev.type == e.EV_KEY and ev.code == e.KEY_POWER and ev.value == 1 for ev in events)


def show_shutdown_lines():
    """The Pi's own lines as it shuts down ("Stopped ...") on the console, even with 'quiet' on
    its command line: systemd shows them from then on when it's sent SIGRTMIN+20."""
    try:
        with open("/proc/1/comm") as f:
            if f.read().strip() != "systemd":
                return
        os.kill(1, signal.SIGRTMIN + 20)
    except (OSError, AttributeError, ValueError):
        pass
