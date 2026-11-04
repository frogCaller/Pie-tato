"""Chromium on a Pi 4 or 5, from Web's first page (pitato/chromium.py, pitato/screens/chromium.py). Its command line
(its session on its console, cage's three ways with the screen's size and turn, its size on a TV, its sound); its
pointer and wheel (a nudge, the d-pad held, the sticks, L and R, a wheel's fine steps and its notches); its keys
(typed, shifted, together). Then on two of this machine's own consoles (10 for media mode's, 11 for Chromium's, with a
stand-in for logind's hold on its session's console): opened (media mode's console to text mode first, as one in
graphics mode can't be switched from), the buttons, X and START (Pietato's keyboard on media mode's console, the
words typed into Chromium after), HOME (its menu, and back), each of its menu's jobs, Pietato's menus with it still
open, closed (A twice), closed by itself, failing at once (its console left in graphics mode with nobody's session:
put back, so the switch goes through), media mode left while it's up; the first time's card; Web's first page's rows;
the help pages; music a video stopped not back while it's up. Last, the main loop: a controller with sticks (the left
one the pointer, the right one the wheel), a GPi Case's (its d-pad's on a stick's axes: the d-pad), and a keyboard
(Chromium's own while it's in front). Pictures of its card, its menu and its help."""
import fcntl, os, shutil, struct, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_chrome"
FAKE = SP + "/chromefake"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Documents")
for f in ("run.args", "calls.log", "vt.log", "unit.pid", "fail"):
    try:
        os.remove(os.path.join(FAKE, f))
    except OSError:
        pass
os.environ["PATH"] = FAKE + "/bin:" + os.environ["PATH"]
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import chromium as pc
from pitato.screens import chromium as sc
from evdev import ecodes as e

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
MV, CV = 10, 11                              # (spare consoles: media mode's, Chromium's)
g.MEDIA_VT = MV
g.CHROMIUM_VT = CV
open(FAKE + "/vt", "w").write(str(CV))
pc.owner = lambda: "tester"
pc.SETTLE = 0.05
pc.KEY_GAP = 0.0
pc.KEYS_FIRST = {"T": 0.1}
KDSETMODE, KDGETMODE, VT_GETMODE, VT_GETSTATE, VT_ACTIVATE = 0x4B3A, 0x4B3B, 0x5601, 0x5603, 0x5606
KD_TEXT, KD_GRAPHICS = 0, 1
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


class Dev:
    """A uinput device: what's written to it."""
    made = []

    def __init__(self, caps):
        self.caps, self.ev, self.closed = caps, [], False
        Dev.made.append(self)

    def write(self, t, c, v):
        self.ev.append((t, c, v))

    def syn(self):
        self.ev.append("syn")

    def close(self):
        self.closed = True

    def take(self):
        out, self.ev = [x for x in self.ev if x != "syn"], []
        return out


pc.Chromium.new_device = staticmethod(lambda caps: Dev(caps))

# ---- a screen cage can show it on: KMS's (a card with screens), not the GPi Case 2's own (the firmware's) ------------
DRM = S + "/drm"
os.makedirs(DRM)
for n in ("card0", "renderD128", "version"):          # (the 3D chip on its own: a card, with no screens)
    open(f"{DRM}/{n}", "w").close()
pc.DRM_DIR = DRM
fw_only = (pc.kms_screen(), pc.chromium_ready())
os.makedirs(DRM + "/card1-HDMI-A-1")
check(fw_only == (False, False) and pc.kms_screen() and pc.chromium_ready(),
      f"no screen of KMS's (the 3D chip on its own, the firmware drawing the screen): no Chromium {fw_only}; one "
      f"(card1-HDMI-A-1): Chromium")
HI = getattr(e, "REL_WHEEL_HI_RES", 11)
CODE = {getattr(e, "KEY_" + n): n for n in pc.KEY_NAMES}


def keys_of(evs):
    """Key events as names: ("+A", "-A")."""
    return [("+" if v else "-") + CODE.get(c, str(c)) for t, c, v in evs if t == e.EV_KEY and c in CODE]


# ---- its command line -------------------------------------------------------------------------------------------
check([pc.chromium_scale(*s) for s in ((640, 480), (1280, 720), (1920, 1080), (1080, 1920), (3840, 2160),
                                       (1920, 1200), (1280, 1024))] == [1.0, 1.0, 1.5, 1.5, 3.0, 1.5, 1.25],
      "its size: 640x480 and 720p as they are, 1080p 1.5 times (turned too), 4K 3 times, 1280x1024 1.25")
check([pc.key_for(c) for c in "aQ!\" \n"] + [pc.key_for("é")] ==
      [("A", False), ("Q", True), ("1", True), ("APOSTROPHE", True), ("SPACE", False), ("ENTER", False), None],
      "keys: a, Q shifted, ! shifted 1, \" shifted ', space, Enter; é: none (a US keyboard's)")
cage = shutil.which("cage")
for kind, turn, want_cage, want_size, want_turn in (("randr", 90, ["-d"], "1920x1080", "90"),
                                                   ("r", 270, ["-d", "-r", "-r", "-r"], "", "normal"),
                                                   ("", 90, ["-d"], "", "normal")):
    pc._cages[cage] = kind
    cmd = pc.start_command("https://example.com/a b", "tester", "default:CARD=vc4hdmi0", "1920x1080", turn, 1.5)
    k = cmd.index("--")
    props = [cmd[i + 1] for i, a in enumerate(cmd[:k]) if a == "-p"]
    cg = cmd[k + 1:]
    j = cg.index("--")
    tail = cg[j + 1:]
    check(cmd[:2] == ["systemd-run", "--unit=pietato-chromium"] and "--wait" in cmd[:k] and "--collect" in cmd[:k]
          and cg[0] == cage and cg[1:j] == want_cage and tail[:5] == ["/bin/sh", "-c", pc.LAUNCH, "pietato-chromium",
                                                                       want_size] and tail[5:7] == [want_turn, "1.5"]
          and tail[7] == pc.chromium_path() and tail[-1] == "https://example.com/a b"
          and "--alsa-output-device=default:CARD=vc4hdmi0" in tail and "--ozone-platform=x11" in pc.LAUNCH,
          f"cage {kind or '0.1.5'!r}, turned {turn}: cage {' '.join(cg[1:j])}, size {want_size or '(its own)'}, "
          f"turn {want_turn}; Chromium's flags, its size 1.5, its sound, the address")
check(all(p in props for p in ("User=tester", "PAMName=login", f"TTYPath=/dev/tty{CV}", "StandardInput=tty-force",
                               "TTYVHangup=yes", f"WorkingDirectory={HOME}", "Environment=XDG_SESSION_TYPE=wayland",
                               "Environment=XCURSOR_SIZE=36", "TimeoutStopSec=5")),
      "its session: as you, PAM's login (setup.sh's own isn't here), on its console, in your home folder, Wayland, a "
      "pointer its size, 5 seconds to go when it's closed")
check("--alsa-output-device" not in " ".join(pc.start_command(None, "tester", "", "", 0, 1.0))
      and pc.start_command(None, "tester", "", "", 0, 1.0)[-1].startswith("--"),
      "no sound named (ALSA's own default): no --alsa-output-device; no address: none on the end")
pc._cages.clear()
check(pc.cage_kind() == "", f"this machine's cage (0.1.5: it goes down when wlr-randr changes the screen): neither")

# ---- its pointer, wheel and keys -----------------------------------------------------------------------------------
c = pc.Chromium(1920, 1080)
c.devices()
mouse, kbd = c.mouse, c.keys
caps_abs = dict(mouse.caps[e.EV_ABS])
check(caps_abs[e.ABS_X].max == pc.ABS_MOST and e.BTN_LEFT in mouse.caps[e.EV_KEY] and HI in mouse.caps[e.EV_REL]
      and e.REL_WHEEL in mouse.caps[e.EV_REL] and e.KEY_A in kbd.caps[e.EV_KEY] and e.KEY_F11 in kbd.caps[e.EV_KEY]
      and e.KEY_LEFTSHIFT in kbd.caps[e.EV_KEY],
      "its pointer: put where it's told (0 to 32767 across), three buttons, a wheel with fine steps; its keyboard")
c.nudge("right")
ev = mouse.take()
check(ev == [(e.EV_ABS, e.ABS_X, round(968 / 1919 * 32767)), (e.EV_ABS, e.ABS_Y, round(540 / 1079 * 32767))],
      f"a press of the d-pad: 8 pixels that way, from the middle ({ev})")
c.x = 3
c.nudge("left")
check(c.x == 0 and mouse.take()[0][2] == 0, "...no further than the edge")
t0 = 1000.0
c.held = {"right": t0}
sp = [c.speeds(t)[0] for t in (t0, t0 + pc.DPAD_WAIT, t0 + pc.DPAD_WAIT + pc.DPAD_RAMP, t0 + 9)]
check(sp[0] == 0 and abs(sp[1] - 96) < 0.5 and abs(sp[2] - 1248) < 0.5 and abs(sp[3] - 1248) < 0.5,
      f"the d-pad held: still for {pc.DPAD_WAIT}s, then 96 pixels a second, up to 1248 a second after a second ({sp})")
c.held = {}
c.sticks["lx"], c.sticks["ly"] = 127, 64
vx, vy, wy, wx = c.speeds(t0)
check(abs(vx - 1248) < 0.5 and 205 < vy < 215 and wy == 0 and wx == 0,
      f"the left stick: all the way, 1248 pixels a second; halfway, gently (211) ({vx:.0f}, {vy:.0f})")
c.sticks = {"lx": 15, "ly": -15, "rx": 0, "ry": -127}
vx, vy, wy, wx = c.speeds(t0)
check(vx == 0 and vy == 0 and wy == 12 and wx == 0, f"a stick at rest (15): nothing; the right one up: the wheel up, 12 "
      f"notches a second ({vx}, {vy}, {wy})")
wheel = [[0.0, 0], [0.0, 0]]
c.step(t0, 0.1, wheel)
ev = mouse.take()
check(ev == [(e.EV_REL, HI, 144), (e.EV_REL, e.REL_WHEEL, 1)] and abs(wheel[0][0]) < 1e-6 and wheel[0][1] == 24,
      f"a tenth of a second of it: 144 fine steps, a notch (120 of them), 24 left over for next time ({ev})")
c.step(t0, 0.05, wheel)
ev = mouse.take()
check(ev == [(e.EV_REL, HI, 72)] and wheel[0][1] == 96, f"...a twentieth more: 72 fine steps, no notch yet ({ev})")
c.sticks = {"lx": 0, "ly": 0, "rx": 0, "ry": 0}
c.held = {"l": t0}
w = [c.speeds(t)[2] for t in (t0, t0 + pc.WHEEL_WAIT, t0 + pc.WHEEL_WAIT + pc.WHEEL_RAMP)]
c.held = {"r": t0}
w.append(c.speeds(t0 + 9)[2])
c.held = {}
check(w == [0, 4, 16, -16], f"L held: up the page after a moment, 4 notches a second, up to 16; R: down ({w})")
c.notch("l")
c.notch("r")
check(mouse.take() == [(e.EV_REL, HI, 120), (e.EV_REL, e.REL_WHEEL, 1), (e.EV_REL, HI, -120),
                       (e.EV_REL, e.REL_WHEEL, -1)], "a press of L: a notch up; R: a notch down")
c.click(True)
c.click(False)
ev = mouse.take()
check([x for x in ev if x[0] == e.EV_KEY] == [(e.EV_KEY, e.BTN_LEFT, 1), (e.EV_KEY, e.BTN_LEFT, 0)]
      and ev[0][1] == e.ABS_X, "A: the left button, where the pointer is")
c.key("LEFTALT", "LEFT")
check(keys_of(kbd.take()) == ["+LEFTALT", "+LEFT", "-LEFT", "-LEFTALT"], "keys together: down, then up the other way")
c.type_text("Hi! é", enter=True)
check(keys_of(kbd.take()) == ["+LEFTSHIFT", "+H", "-H", "-LEFTSHIFT", "+I", "-I", "+LEFTSHIFT", "+1", "-1",
                              "-LEFTSHIFT", "+SPACE", "-SPACE", "+ENTER", "-ENTER"],
      "typed: Hi! (shifted where it's shifted), the space, é left out, then Enter")
c.alive = True
c.thread = threading.Thread(target=c.run, daemon=True)
c.thread.start()
c.x = 960
c.hold("right", True)
time.sleep(0.75)
c.hold("right", False)
time.sleep(0.15)
moved = c.x - 960
mouse.take()
time.sleep(0.2)
check(30 < moved < 200 and not c.moving.is_set() and mouse.take() == [],
      f"its thread: the d-pad held three quarters of a second, gliding after a quarter ({moved:.0f} pixels); let go, "
      f"it rests")
c.stick("lx", 127)
time.sleep(0.3)
c.stick("lx", 0)
time.sleep(0.1)
check(c.x - 960 - moved > 250, f"the stick all the way, 0.3s: on across ({c.x - 960 - moved:.0f} pixels)")
c.alive = False
c.moving.set()

# ---- on two consoles: media mode's, and Chromium's -------------------------------------------------------------------
tty0 = os.open("/dev/tty0", os.O_RDWR | os.O_NOCTTY)


def fg():
    return struct.unpack("HHH", fcntl.ioctl(tty0, VT_GETSTATE, bytes(6)))[0]


def kd(n):
    fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)
    try:
        return struct.unpack("i", fcntl.ioctl(fd, KDGETMODE, bytes(4)))[0]
    finally:
        os.close(fd)


def vtmode(n):
    fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)
    try:
        return struct.unpack("bbhhh", fcntl.ioctl(fd, VT_GETMODE, bytes(8)))[0]
    finally:
        os.close(fd)


def put_back():
    """The consoles as they were: text mode, nobody's, the first one in front."""
    for n in (MV, CV):
        fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)
        try:
            fcntl.ioctl(fd, 0x5602, struct.pack("bbhhh", 0, 0, 0, 0, 0))
            fcntl.ioctl(fd, KDSETMODE, KD_TEXT)
        finally:
            os.close(fd)
    subprocess.run(["chvt", "1"])


def log(name):
    try:
        return open(os.path.join(FAKE, name)).read().split("\n")
    except OSError:
        return []


def settle(secs=0.3):
    time.sleep(secs)


shots = {}


class FB:
    w, h = 640, 480
    real_w, real_h, dev_w, dev_h = 1920, 1080, 1920, 1080
    drawn = 0
    invalid = 0

    def show(self, img):
        FB.drawn += 1
        FB.last = img.copy()

    def invalidate(self):
        FB.invalid += 1

    def blank_outside(self, box):
        pass

    def close(self):
        pass


def shot(name):
    m.dirty = True
    m.flush()
    shots[name] = FB.last
    FB.last.save(f"{S}/{name}.png")


put_back()
g.Framebuffer = FB
m = g.Media()
m.load_fonts()
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))
m.enter()
check(fg() == MV and kd(MV) == KD_GRAPHICS and m.ttyfd is not None,
      f"media mode: its console ({MV}) in front, in graphics mode")
fcntl.ioctl(m.ttyfd, VT_ACTIVATE, CV)
settle(0.3)
check(fg() == MV, "the kernel won't switch from a console in graphics mode that's nobody's (why it goes to text first)")

try:
    wi = m.tab_index("www")
    m.tab, m.view = wi, "list"
    m.load_tab(wi)
    rows = m.tab_items(wi)
    keys = [r["key"] for r in rows]
    check("www:chromium" in keys and rows[keys.index("www:chromium")]["title"] == "The whole web, in Chromium",
          "Web's first page: The whole web, in Chromium")
    m.sels[wi] = keys.index("www:chromium")
    m.press("a")
    check(m.view == "chromehow" and m.state["www"].get("chromium_seen") and fg() == MV,
          "A, the first time: how it works, on Pietato's screen")
    shot("chrome_how")
    m.press("b")
    check(m.view == "list" and m.chromium is None, "B: back to Web's first page, nothing opened")
    m.press("a")
    drawn = FB.drawn
    settle(0.5)
    args = log("run.args")
    check(m.view == "chromium" and m.chromium is not None and fg() == CV and kd(MV) == KD_TEXT
          and "holding" in log("vt.log") and vtmode(CV) == 1 and kd(CV) == KD_GRAPHICS,
          f"A again: Chromium up, its console ({fg()}) in front, media mode's in text mode, its session holding it")
    check(f"TTYPath=/dev/tty{CV}" in args and "1920x1080" not in args or pc.cage_kind() == "randr",
          "systemd-run told its console (and this cage keeps the screen as it is)")
    m.flush()
    check(FB.drawn == drawn and m.proc_owns_screen(), "media mode draws nothing while it's in front")
    ch = m.chromium
    mouse, kbd = ch.mouse, ch.keys
    mouse.take(); kbd.take()
    m.press("right"); m.release("right")
    m.press("a"); m.release("a")
    m.press("y"); m.release("y")
    ev = mouse.take()
    check([x for x in ev if x[0] == e.EV_KEY] == [(e.EV_KEY, e.BTN_LEFT, 1), (e.EV_KEY, e.BTN_LEFT, 0),
                                                  (e.EV_KEY, e.BTN_RIGHT, 1), (e.EV_KEY, e.BTN_RIGHT, 0)]
          and ev[0] == (e.EV_ABS, e.ABS_X, round(968 / 1919 * 32767)),
          "the buttons: ▶ nudges the pointer, A clicks (down, up), Y right-clicks")
    m.press("b"); m.release("b")
    m.press("select"); m.release("select")
    m.press("l2"); m.press("r2")
    check(keys_of(kbd.take()) == ["+LEFTALT", "+LEFT", "-LEFT", "-LEFTALT", "+LEFTCTRL", "+TAB", "-TAB", "-LEFTCTRL",
                                  "+LEFTCTRL", "+MINUS", "-MINUS", "-LEFTCTRL", "+LEFTCTRL", "+EQUAL", "-EQUAL",
                                  "-LEFTCTRL"],
          "B: Alt+Left (back); SELECT: Ctrl+Tab (the next tab); L2, R2: Ctrl+- and Ctrl+= (zoom)")
    m.press("l"); m.release("l")
    check(mouse.take()[-2:] == [(e.EV_REL, HI, 120), (e.EV_REL, e.REL_WHEEL, 1)], "L: a notch up the page")
    check(m.takes_repeats("up") and m.takes_repeats("r") and not m.takes_repeats("a"),
          "the web page's remote: ▲ and R held go on and on (A doesn't)")

    # X: Pietato's keyboard, then the words typed into Chromium
    m.press("x")
    check(m.view == "keys" and m.kb.get("chrome") and fg() == MV and kd(MV) == KD_GRAPHICS
          and "released" in log("vt.log") and FB.invalid > 0,
          "X: Pietato's keyboard on media mode's console (Chromium's session let go of the screen), drawn afresh")
    shot("chrome_type")
    for ch_ in "hi":
        m.keyboard_key("char", ch_)
    m.press("start")
    settle(0.4)
    check(m.view == "chromium" and fg() == CV and "acquired" in log("vt.log")
          and keys_of(kbd.take()) == ["+H", "-H", "+I", "-I", "+ENTER", "-ENTER"],
          "START (done): Chromium in front again, then h i Enter typed into it")
    m.press("start")
    check(m.view == "keys" and m.kb["title"].startswith("Address"), "START: the keyboard, for an address")
    for ch_ in "a.b":
        m.keyboard_key("char", ch_)
    m.press("start")
    settle(0.5)
    check(fg() == CV and keys_of(kbd.take()) == ["+LEFTCTRL", "+L", "-L", "-LEFTCTRL", "+A", "-A", "+DOT", "-DOT",
                                                 "+B", "-B", "+ENTER", "-ENTER"],
          "...a.b: Ctrl+L (the address box), a.b, Enter")
    m.press("start")
    m.press("b")
    settle(0.3)
    check(m.view == "chromium" and fg() == CV and keys_of(kbd.take()) == [], "B on the keyboard: back, nothing typed")
    m.press("x")
    check(m.chromium_home() and m.view == "chromium" and fg() == CV, "HOME on the keyboard: back to Chromium")

    # HOME: its menu
    check(m.chromium_home() and m.view == "chromenu" and fg() == MV and kd(MV) == KD_GRAPHICS,
          "HOME: its menu, on media mode's console")
    shot("chrome_menu")
    m.press("down"); m.press("down")
    check(m.chrome_menu["sel"] == 2, "▼▼: New tab")
    m.press("b")
    check(m.view == "chromium" and fg() == CV, "B: back to Chromium")
    m.chromium_home()
    m.press("x")
    check(m.view == "help" and m.help_from == "chromenu", "X in its menu: its buttons")
    shot("chrome_help")
    m.press("a")
    check(m.view == "chromenu", "...any button: its menu again")
    check(m.chromium_home() and m.view == "chromium" and fg() == CV, "HOME in its menu: back to Chromium")
    jobs = [j for j, _ in sc.CHROME_MENU]
    for job, want in (("zoomin", ["+LEFTCTRL", "+EQUAL", "-EQUAL", "-LEFTCTRL"]),
                      ("zoomout", ["+LEFTCTRL", "+MINUS", "-MINUS", "-LEFTCTRL"]), ("reload", ["+F5", "-F5"]),
                      ("closetab", ["+LEFTCTRL", "+W", "-W", "-LEFTCTRL"]), ("full", ["+F11", "-F11"])):
        m.chromium_home()
        m.chrome_menu["sel"] = jobs.index(job)
        m.press("a")
        settle(0.2)
        got = keys_of(kbd.take())
        check(m.view == "chromium" and fg() == CV and got == want, f"its menu, {job}: back in Chromium, {' '.join(got)}")
    m.chromium_home()
    m.chrome_menu["sel"] = jobs.index("newtab")
    m.press("a")
    for ch_ in "x.y":
        m.keyboard_key("char", ch_)
    m.press("start")
    settle(0.5)
    check(keys_of(kbd.take())[:4] == ["+LEFTCTRL", "+T", "-T", "-LEFTCTRL"] and fg() == CV,
          "its menu, New tab: the keyboard, then Ctrl+T, x.y, Enter")

    # Pietato's menus, with it still open
    m.chromium_home()
    m.chrome_menu["sel"] = jobs.index("away")
    m.press("a")
    rows = m.tab_items(wi)
    keys = [r["key"] for r in rows]
    sel = m.sels[wi]
    check(m.view == "list" and m.tab == wi and fg() == MV and m.chromium is not None
          and rows[sel]["key"] == "www:chromium" and rows[sel]["title"] == "Back to Chromium",
          "its menu, Pietato's menus: Web's first page, on Back to Chromium, Chromium still up")
    shot("chrome_open_list")
    check(("Y", "Close it") in m.list_hints(), "...Y: Close it")
    check(not m.chromium_home(), "...HOME there is media mode's own (Chromium's isn't in front)")
    m.press("a")
    check(m.view == "chromium" and fg() == CV, "A on Back to Chromium: in front again")

    # This page, in Chromium (one of Pietato's own pages open)
    m.chromium_home()
    m.chrome_menu["sel"] = jobs.index("away")
    m.press("a")
    page = g.Page("https://example.org/story")
    if page is not None:
        page.title = "A story"
        m.www = {"page": page, "y": 0, "focus": None, "reader": False, "laid": None, "lines": [], "targets": [],
                 "height": 0}
        m.www_list_again()
        rows = m.tab_items(wi)
        keys = [r["key"] for r in rows]
        check(keys[:2] == ["www:page", "www:chromium:page"] and rows[1]["src"] == "https://example.org/story",
              "a page of its own open: This page, in Chromium, under it")
        m.sels[wi] = 1
        kbd.take()
        m.press("a")
        settle(0.5)
        check(fg() == CV and keys_of(kbd.take())[:4] == ["+LEFTCTRL", "+T", "-T", "-LEFTCTRL"],
              "...A: Chromium in front, the page in a tab of its own (Ctrl+T, its address, Enter)")
        m.www = None
        m.chromium_home()
        m.chrome_menu["sel"] = jobs.index("away")
        m.press("a")
        m.www_list_again()

    # Y on Back to Chromium: closed
    rows = m.tab_items(wi)
    m.sels[wi] = [r["key"] for r in rows].index("www:chromium")
    m.press("y")
    settle(0.5)
    check(m.chromium is None and fg() == MV and kd(MV) == KD_GRAPHICS and "gone" in log("vt.log")
          and toasts[-1] == "Chromium closed" and vtmode(CV) == 0 and kd(CV) == KD_TEXT,
          "Y on it: Chromium closed (its session over: its console put back), Web's first page")
    check([r["title"] for r in m.tab_items(wi) if r["key"] == "www:chromium"] == ["The whole web, in Chromium"],
          "...the row as it was")

    # its menu's Close Chromium: A twice
    open(FAKE + "/vt.log", "w").close()
    m.chromium_open()
    settle(0.5)
    m.chromium_home()
    m.chrome_menu["sel"] = jobs.index("quit")
    m.press("a")
    check(m.chromium is not None and m.chrome_menu["confirm"][0] == "quit", "Close Chromium: A once, it asks")
    shot("chrome_quit")
    m.press("a")
    settle(0.5)
    check(m.chromium is None and m.view == "list" and fg() == MV and kd(MV) == KD_GRAPHICS and "gone" in log("vt.log"),
          "...A again: closed, back on Web's first page")
    check("stop pietato-chromium" in log("calls.log"), "...its unit stopped")

    # closed by itself (its last tab closed, say)
    sc.CHROME_EARLY = 0.0
    m.chromium_open()
    settle(0.5)
    os.kill(int(open(FAKE + "/unit.pid").read()), 15)
    settle(0.4)
    m.tick()
    settle(0.3)
    check(m.chromium is None and m.view == "list" and fg() == MV and kd(MV) == KD_GRAPHICS
          and toasts[-1] == "Chromium closed", "closed by itself: media mode's console in front, it says so")

    # failing at once: its console left in graphics mode, nobody's
    sc.CHROME_EARLY = 8.0
    open(FAKE + "/fail", "w").close()
    m.chromium_open()
    settle(0.3)
    stuck = fg() == CV and kd(CV) == KD_GRAPHICS and vtmode(CV) == 0
    m.tick()
    settle(0.3)
    check(stuck and m.chromium is None and fg() == MV and kd(MV) == KD_GRAPHICS and kd(CV) == KD_TEXT
          and toasts[-1].startswith("Chromium didn't start"),
          "it fails at once (its console in graphics mode, nobody's): put back to text mode, so media mode's comes back")
    os.remove(FAKE + "/fail")

    # music a video stopped doesn't come back while it's up
    m.chromium = pc.Chromium()
    m.resume_later, m.resume_at_t = (["x"], 0, 0.0), None
    m.music_back(time.monotonic())
    blocked = m.resume_at_t is None
    m.chromium = None
    m.music_back(time.monotonic())
    check(blocked and m.resume_at_t is not None, "music a video stopped: not back while Chromium's up, back after")
    m.resume_later, m.resume_at_t = None, None

    # the Web tab's help: Chromium's buttons
    m.view, m.help_from = "help", "list"
    shot("www_help")
    m.view = "list"

    # media mode left while it's up
    m.chromium_open()
    settle(0.5)
    m.leave()
    settle(0.5)
    check(m.chromium is None and fg() == 1 and "gone" in log("vt.log") and kd(MV) == KD_TEXT,
          "media mode left while Chromium's up: closed first, then the terminal as ever")
finally:
    m.chromium_close(wait=True)
    put_back()

# ---- the main loop: controllers and a keyboard while it's in front -----------------------------------------------------
from evdev import AbsInfo


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    vendor, product = 0x45e, 0x28e


class PadDev:
    n = 0

    def __init__(self, name, keys, absaxes=None, rel=None):
        PadDev.n += 1
        self.path = f"/dev/input/event{PadDev.n}"
        self.name, self.keys, self.absaxes, self.rel = name, keys, absaxes or {}, rel or []
        self.info = Info()
        self.r, self.w = os.pipe()
        self.q = []

    def capabilities(self, verbose=False, absinfo=True):
        caps = {e.EV_KEY: list(self.keys)} if self.keys else {}
        if self.absaxes:
            caps[e.EV_ABS] = [(k, a) if absinfo else k for k, a in self.absaxes.items()]
        if self.rel:
            caps[e.EV_REL] = list(self.rel)
        return caps

    def absinfo(self, code):
        return self.absaxes[code]

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        os.read(self.r, 64)
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        pass


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


xbox = PadDev("Xbox Wireless Controller", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
                                           e.BTN_SELECT, e.BTN_START, e.BTN_MODE],
              {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_RX: ai(-32768, 32767, 0),
               e.ABS_RY: ai(-32768, 32767, 0), e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
gpi = PadDev("Retroflag GPi Case 2 Gamepad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
                                               e.BTN_SELECT, e.BTN_START],
             {e.ABS_X: ai(0, 255, 127), e.ABS_Y: ai(0, 255, 127)})
kb = PadDev("A keyboard", [getattr(e, "KEY_" + k) for k in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [e.KEY_ENTER, e.KEY_SPACE])
devs = {d.path: d for d in (xbox, gpi, kb)}
g.list_devices = lambda: list(devs)
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") else \
    real_stat(p, *a, **k)
g.Pad.dpad_apart  # (it's there)


class UI:
    def write(self, *a):
        pass

    def syn(self):
        pass


m2 = g.Media()
m2.load_fonts()
m2.fb = FB()
m2.active = True
m2.boot_media = False                        # (the loop's not to open media mode afresh: it's open, Chromium in front)
m2.tab, m2.view = m2.tab_index("www"), "chromium"
c2 = pc.Chromium(1920, 1080)
c2.devices()
c2.proc = subprocess.Popen(["sleep", "60"], stderr=subprocess.PIPE, text=True)
c2.alive = True
c2.thread = threading.Thread(target=c2.run, daemon=True)
c2.thread.start()
m2.chromium = c2
pressed = []
real_press = m2.press_chromium
m2.press_chromium = lambda name, repeat: (pressed.append(name), real_press(name, repeat))[1]
done = threading.Event()
errs = []


def loop():
    try:
        g.run(UI(), m2, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errs.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
settle(0.4)
pads = {p.dev.name: p for p in m2.pads.by_path.values()}
check(pads["Xbox Wireless Controller"].dpad_apart() and not pads["Retroflag GPi Case 2 Gamepad"].dpad_apart()
      and kb.path in m2.pads.keyboards, "an Xbox controller's stick is a stick; a GPi Case's d-pad isn't one")
c2.mouse.take()
x0 = c2.x
xbox.send((e.EV_ABS, e.ABS_X, 32767), (e.EV_SYN, 0, 0))
settle(0.3)
xbox.send((e.EV_ABS, e.ABS_X, 0), (e.EV_SYN, 0, 0))
settle(0.15)
check(c2.x - x0 > 200 and pressed == [], f"its left stick: the pointer on across ({c2.x - x0:.0f} pixels), "
                                        f"no d-pad presses")
xbox.send((e.EV_ABS, e.ABS_RY, -32768), (e.EV_SYN, 0, 0))
settle(0.3)
xbox.send((e.EV_ABS, e.ABS_RY, 0), (e.EV_SYN, 0, 0))
settle(0.1)
ups = sum(v for t, cd, v in c2.mouse.take() if cd == e.REL_WHEEL)
check(ups >= 2, f"its right stick up: the wheel up the page ({ups} notches)")
xbox.send((e.EV_ABS, e.ABS_HAT0X, 1), (e.EV_SYN, 0, 0))
settle(0.1)
xbox.send((e.EV_ABS, e.ABS_HAT0X, 0), (e.EV_SYN, 0, 0))
settle(0.1)
check(pressed == ["right"] and not c2.held, f"its d-pad: a press (a nudge), let go ({pressed})")
pressed.clear()
x0 = c2.x
gpi.send((e.EV_ABS, e.ABS_X, 255), (e.EV_SYN, 0, 0))
settle(0.1)
gpi.send((e.EV_ABS, e.ABS_X, 127), (e.EV_SYN, 0, 0))
settle(0.1)
check(pressed == ["right"] and 0 < c2.x - x0 < 20, f"a GPi Case's d-pad (a stick's axes): the d-pad, a nudge "
                                                   f"({c2.x - x0:.0f} pixels)")
pressed.clear()
kb.send((e.EV_KEY, e.KEY_A, 1), (e.EV_SYN, 0, 0))
settle(0.1)
kb.send((e.EV_KEY, e.KEY_A, 0), (e.EV_SYN, 0, 0))
settle(0.1)
check(pressed == [], "a keyboard's A (◀, in the menus): Chromium's own, not a button")
xbox.send((e.EV_KEY, e.BTN_MODE, 1), (e.EV_SYN, 0, 0))
settle(0.1)
xbox.send((e.EV_KEY, e.BTN_MODE, 0), (e.EV_SYN, 0, 0))
settle(0.2)
check(m2.view == "chromenu" and m2.active, "HOME: its menu (media mode stays on)")
xbox.send((e.EV_KEY, e.BTN_MODE, 1), (e.EV_SYN, 0, 0))
settle(0.1)
xbox.send((e.EV_KEY, e.BTN_MODE, 0), (e.EV_SYN, 0, 0))
settle(0.2)
check(m2.view == "chromium", "HOME again: back to it")
done.set()
th.join(2)
c2.alive = False
c2.moving.set()
if c2.proc is not None:
    c2.proc.kill()
check(not errs, "the main loop: no errors")

print()
print("FAILED: " + "; ".join(fails) if fails else "ALL OK")
