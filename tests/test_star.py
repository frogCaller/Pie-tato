"""The GPi Case 2W's star button: with HOME (either one first) it's one press of HOME (from the terminal, one switch to
the menus; in the menus HOME on its own never leaves them: HOME and ◀ does); a quick press on its own is HOME too;
held while other buttons go (the case's turbo), or held long, it's nothing. Settings > Controller asks for it last on the GPi Case (and only there). When the case keeps
the star to itself, star + HOME is still one switch. Fake input devices with the real evdev codes."""
import io, os, sys, time, shutil, json, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e, AbsInfo

S = SP + "/t_star"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Videos")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')
g.home_dir = lambda: S + "/home/u"
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", S + "/home/u") for x in t[key]]
import gk_static; gk_static.use_home(g, S + "/home/u")
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
g.LEARN_SKIP = 0.4
cfg = S + "/config.txt"
open(cfg, "w").write("dtoverlay=vc4-kms-v3d\n# >>> gpi-case setup >>>\n# <<< gpi-case setup <<<\n")
g.CONFIG_TXT = (cfg,)                       # setup.sh set this Pi up for the GPi Case
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class FakeDev:
    n = 0

    def __init__(self, name, keys, absaxes=None, vendor=0x45e, product=0x28e):
        FakeDev.n += 1
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys, self.absaxes = name, keys, absaxes or {}
        self.info = Info(vendor, product)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        caps = {e.EV_KEY: list(self.keys)} if self.keys else {}
        if self.absaxes:
            caps[e.EV_ABS] = [(c, a) if absinfo else c for c, a in self.absaxes.items()]
        return caps

    def absinfo(self, code):
        return self.absaxes[code]

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        if self.gone:
            raise OSError(19, "No such device")
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        self.closed = True


def ai(lo, hi, val):
    return AbsInfo(value=val, min=lo, max=hi, fuzz=0, flat=0, resolution=0)


STAR = e.BTN_THUMBL                          # what this pretend case sends for its star
case = FakeDev("Microsoft X-Box 360 pad",
               [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT,
                e.BTN_START, e.BTN_MODE, STAR],
               {e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)})
plugged = [case]
devs = {case.path: case}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)

check("the star isn't one of the standard buttons", g.Pad(case, "gamepad").translate(Ev(e.EV_KEY, STAR, 1)) == [])
check("steps: the star last on the GPi Case only", [s[0] for s in g.learn_steps(True)][-2:] == ["home", "star"]
      and g.learn_steps(False) == g.LEARN_STEPS and "star" not in [s[0] for s in g.LEARN_STEPS])
check("the web page still can't press it (not one of the screens' buttons)", "star" not in g.BUTTONS)


class UI:
    def __init__(self):
        self.out = []

    def write(self, t, c, v):
        self.out.append((c, v))

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    last = None

    def show(self, img):
        FB.last = img.copy()

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
ui = UI()
m = g.Media()
done = threading.Event()
errors = []


def loop():
    try:
        g.run(ui, m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.3)
check("the case's pad found, and it's a GPi Case Pi", list(m.pads.by_path) == [case.path] and m.pads.gpi)


def wait(sec=0.12):
    time.sleep(sec)


def keys_typed():
    out = list(ui.out); ui.out.clear(); return out


def tap(code, hold=0.05):
    case.send((e.EV_KEY, code, 1)); wait(hold); case.send((e.EV_KEY, code, 0)); wait()


switches = []
orig_enter, orig_leave = m.enter, m.leave
m.enter = lambda: (switches.append("menu"), orig_enter())[1]
m.leave = lambda: (switches.append("terminal"), orig_leave())[1]

# ---- before it's set up: the case keeps the star to itself, as far as Pitato knows ----------------
check("starts in the terminal", not m.active)
tap(STAR)
check("the star, not set up: nothing", switches == [] and not m.active and keys_typed() == [])
case.send((e.EV_KEY, STAR, 1)); wait(0.05); case.send((e.EV_KEY, e.BTN_MODE, 1)); wait()
case.send((e.EV_KEY, e.BTN_MODE, 0), (e.EV_KEY, STAR, 0)); wait(0.3)
check("star + HOME (the star unseen): one switch, to the menu", switches == ["menu"] and m.active and m.view == "home")
switches.clear()
tap(e.BTN_MODE)
check("HOME alone in the menus: not the terminal", switches == [] and m.active)
case.send((e.EV_KEY, e.BTN_MODE, 1)); wait(0.05); case.send((e.EV_ABS, e.ABS_HAT0X, -1)); wait()
case.send((e.EV_ABS, e.ABS_HAT0X, 0)); wait(0.05); case.send((e.EV_KEY, e.BTN_MODE, 0)); wait(0.3)
check("HOME and ◀: the terminal", switches == ["terminal"] and not m.active)
switches.clear()

# ---- Settings > Controller on the GPi Case: the star last ----------------------------------------
orig_enter()
m.tab = m.tab_index("settings"); m.view = "list"; m.set_page = "root"
m.set_sel = [k for k, _, _ in m.settings_rows()].index("pad"); m.load_tab(m.tab); wait()
tap(e.BTN_SOUTH)                             # A on the Controller row
check("set-up started, 14 steps", m.learning and m.learn_status()["of"] == len(g.LEARN_STEPS) + 1 == 14)
for code in (e.BTN_SOUTH, e.BTN_EAST):
    case.send((e.EV_KEY, code, 1)); wait(0.3); case.send((e.EV_KEY, code, 0)); wait(0.05)
for code, val in ((e.ABS_HAT0Y, -1), (e.ABS_HAT0Y, 1), (e.ABS_HAT0X, -1), (e.ABS_HAT0X, 1)):
    case.send((e.EV_ABS, code, val)); wait(0.3); case.send((e.EV_ABS, code, 0)); wait(0.1)
for code in (e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START, e.BTN_MODE):
    case.send((e.EV_KEY, code, 1)); wait(0.3); case.send((e.EV_KEY, code, 0)); wait(0.05)
st = m.learn_status()
check(f"asks for the star last: {st['text']!r} ({st['n']} of {st['of']})",
      st["text"] == "Press the star (TURBO) button" and st["n"] == st["of"] == 14)
star_shot = FB.last.copy()
cx, top = 320, 104
px = star_shot.convert("RGB").getpixel((cx, top + 38))
check(f"the screen shows the star, lit: {px}", px == g.ACCENT[:3])
case.send((e.EV_KEY, STAR, 1)); wait(0.3); case.send((e.EV_KEY, STAR, 0)); wait(0.1)
check("star learned, saved", m.learn and m.learn.get("done") and "star" not in m.learn["skipped"])
saved = json.load(open(g.PADS_FILE))
ident = "045e:028e:Microsoft X-Box 360 pad"
check("pads.json: the star with the rest", saved[ident]["keys"].get(str(STAR)) == "star"
      and saved[ident]["keys"].get(str(e.BTN_MODE)) == "home")
done_shot = FB.last.copy()
wait(2.8)
check("back on Settings", m.learn is None and m.view == "list")
pad = m.pads.by_path[case.path]
check("the pad knows its star now", pad.keys.get(STAR) == "star" and pad.home)

# ---- the star, set up -------------------------------------------------------------------------
orig_leave(); wait(); keys_typed(); switches.clear()
tap(STAR)
check("terminal: a quick star press, the menu", switches == ["menu"] and m.active and keys_typed() == [])
switches.clear()
tap(STAR)
check("menu: a quick star press, not the terminal (as HOME on its own)", switches == [] and m.active)
orig_leave(); wait(); switches.clear()
# star first, then HOME
case.send((e.EV_KEY, STAR, 1)); wait(0.05); case.send((e.EV_KEY, e.BTN_MODE, 1)); wait()
case.send((e.EV_KEY, e.BTN_MODE, 0)); wait(0.05); case.send((e.EV_KEY, STAR, 0)); wait(0.3)
check("star, then HOME: one switch", switches == ["menu"] and m.active)
orig_leave(); wait(); switches.clear()
# HOME first, then the star
case.send((e.EV_KEY, e.BTN_MODE, 1)); wait(0.05); case.send((e.EV_KEY, STAR, 1)); wait()
case.send((e.EV_KEY, STAR, 0)); wait(0.05); case.send((e.EV_KEY, e.BTN_MODE, 0)); wait(0.3)
check("HOME, then the star: one switch", switches == ["menu"] and m.active)
orig_leave(); wait(); switches.clear()
# both in one report, let go in one report
case.send((e.EV_KEY, STAR, 1), (e.EV_KEY, e.BTN_MODE, 1)); wait()
case.send((e.EV_KEY, STAR, 0), (e.EV_KEY, e.BTN_MODE, 0)); wait(0.3)
check("both at once: one switch", switches == ["menu"] and m.active)
case.send((e.EV_KEY, e.BTN_MODE, 1), (e.EV_KEY, STAR, 1)); wait()
case.send((e.EV_KEY, e.BTN_MODE, 0), (e.EV_KEY, STAR, 0)); wait(0.3)
check("...and in the menus, both at once: one HOME, which doesn't leave them", switches == ["menu"] and m.active)
orig_leave(); wait(); switches.clear(); keys_typed()
# the case's turbo: the star held while A goes
case.send((e.EV_KEY, STAR, 1)); wait(0.05); tap(e.BTN_SOUTH); case.send((e.EV_KEY, STAR, 0)); wait(0.3)
check("star held with A (the case's turbo): no switch, A types Enter",
      switches == [] and not m.active and keys_typed() == [(e.KEY_ENTER, 1), (e.KEY_ENTER, 0)])
# held long on its own
case.send((e.EV_KEY, STAR, 1)); wait(g.STAR_TAP + 0.2); case.send((e.EV_KEY, STAR, 0)); wait(0.3)
check("star held long on its own: nothing", switches == [] and not m.active)
# a button already held when the star goes down
case.send((e.EV_ABS, e.ABS_HAT0Y, 1)); wait(0.05); tap(STAR); case.send((e.EV_ABS, e.ABS_HAT0Y, 0)); wait()
check("star while DOWN is held: no switch", switches == [] and not m.active)
keys_typed()
# in a game, it's HOME: the game's menu
orig_enter(); wait(); switches.clear()
game_homes = []
m.game_home = lambda: (game_homes.append(1), True)[1]
tap(STAR)
check("in a game: the star opens the game's menu, as HOME does", game_homes == [1] and m.active and switches == [])
case.send((e.EV_KEY, STAR, 1)); wait(0.05); case.send((e.EV_KEY, e.BTN_MODE, 1)); wait()
case.send((e.EV_KEY, e.BTN_MODE, 0), (e.EV_KEY, STAR, 0)); wait(0.3)
check("...and star + HOME there: once", game_homes == [1, 1] and m.active)
del m.game_home
# unplugged with the star held: nothing left over, no trouble
case.send((e.EV_KEY, STAR, 1)); wait()
case.gone = True; plugged.remove(case); case.send(); wait(0.3)
check("unplugged with the star down: dropped, no switch", case.path not in m.pads.by_path and m.active and not errors)
case.gone = False; case.q = []; plugged.append(case); wait(0.3)
orig_leave(); wait(); switches.clear()
tap(STAR)
check("plugged back in: the star works again", case.path in m.pads.by_path and switches == ["menu"] and m.active)
orig_leave(); wait(); switches.clear()

# ---- set up again, the star skipped (a case that keeps it): said so --------------------------------
orig_enter(); m.start_learn(); wait()
for code in (e.BTN_SOUTH, e.BTN_EAST):
    case.send((e.EV_KEY, code, 1)); wait(0.3); case.send((e.EV_KEY, code, 0)); wait(0.05)
for code, val in ((e.ABS_HAT0Y, -1), (e.ABS_HAT0Y, 1), (e.ABS_HAT0X, -1), (e.ABS_HAT0X, 1)):
    case.send((e.EV_ABS, code, val)); wait(0.3); case.send((e.EV_ABS, code, 0)); wait(0.1)
for code in (e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START, e.BTN_MODE):
    case.send((e.EV_KEY, code, 1)); wait(0.3); case.send((e.EV_KEY, code, 0)); wait(0.05)
wait(0.8)                                     # no star: skipped
check("star skipped", m.learn and m.learn.get("done") and m.learn["skipped"] == ["star"])
skip_shot = FB.last.copy()
wait(2.8)
pad = m.pads.by_path[case.path]
check("...so the pad has no star now", "star" not in pad.keys.values() and pad.home)
orig_leave(); wait(); switches.clear()
tap(STAR)
check("the star: nothing", switches == [] and not m.active)

# ---- not a GPi Case: no star step ---------------------------------------------------------------
m.pads.gpi = False
orig_enter(); m.start_learn(); wait()
check("not the GPi Case: 13 steps, as before", m.learn_status()["of"] == len(g.LEARN_STEPS) == 13)
m.cancel_learn(""); wait()

done.set(); th.join(3)
check("loop ended cleanly", not th.is_alive() and not errors)
star_shot.save(SP + "/out/learn_star.png")
done_shot.save(SP + "/out/learn_star_done.png")
skip_shot.save(SP + "/out/learn_star_skipped.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
