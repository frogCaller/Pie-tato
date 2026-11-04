"""Settings > Swap A and B: A and B the other way round on the controller in hand (a Nintendo-style pad, whose
A is where an Xbox pad's B is), kept for that model; held buttons let go of properly as it changes; the
Controller set-up and Reset clear it; and the web page's Swap A and B by each controller, in a real browser
(a phone's width too). Fake input devices with the real evdev codes, media mode's main loop and its control
server."""
import asyncio, json, os, shutil, socket, sys, threading, time, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
from evdev import ecodes as e, AbsInfo
from PIL import ImageDraw

S = SP + "/t_swap"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, vendor, product):
        self.vendor, self.product = vendor, product


class FakeDev:
    """An input device: select() sees it through a pipe; read() hands out queued events."""
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


FACE = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_TL2, e.BTN_TR2,
        e.BTN_SELECT, e.BTN_START, e.BTN_MODE]
STICKS = lambda: {e.ABS_X: ai(-32768, 32767, 0), e.ABS_Y: ai(-32768, 32767, 0), e.ABS_RX: ai(-32768, 32767, 0),
                  e.ABS_RY: ai(-32768, 32767, 0), e.ABS_HAT0X: ai(-1, 1, 0), e.ABS_HAT0Y: ai(-1, 1, 0)}
# a Nintendo-style pad, as Linux has it: its buttons by where they are (the bottom one, B on it, is BTN_SOUTH)
pro = FakeDev("Pro Controller", FACE, STICKS(), vendor=0x57e, product=0x2009)
pro2 = FakeDev("Pro Controller", FACE, STICKS(), vendor=0x57e, product=0x2009)     # (another the same)
xbox = FakeDev("Xbox Wireless Controller", FACE, STICKS(), vendor=0x45e, product=0xb13)
snes = FakeDev("USB Gamepad ", [e.BTN_TRIGGER, e.BTN_THUMB, e.BTN_THUMB2, e.BTN_TOP, e.BTN_BASE3, e.BTN_BASE4],
               {e.ABS_X: ai(0, 255, 127), e.ABS_Y: ai(0, 255, 127)}, vendor=0x81f, product=0xe401)

# ---- a controller's buttons, swapped ------------------------------------------------------------
key = lambda pad, code: pad.translate(Ev(e.EV_KEY, code, 1)) + pad.translate(Ev(e.EV_KEY, code, 0))[:0]
p = g.Pad(pro, "gamepad")
check("standard: its bottom button (B on it) is A, the right one (A on it) is B",
      key(p, e.BTN_SOUTH) == [("a", True)] and key(p, e.BTN_EAST) == [("b", True)] and not p.swapped)
p.apply({"swap": True})
check("swapped: the right one is A, the bottom one B", p.swapped and key(p, e.BTN_EAST) == [("a", True)]
      and key(p, e.BTN_SOUTH) == [("b", True)])
check("...X and Y, the d-pad, L and R as they were", key(p, e.BTN_NORTH) == [("x", True)]
      and key(p, e.BTN_WEST) == [("y", True)] and key(p, e.BTN_TL) == [("l", True)]
      and p.translate(Ev(e.EV_ABS, e.ABS_HAT0X, 1)) == [("right", True)])
p.translate(Ev(e.EV_ABS, e.ABS_HAT0X, 0))
check("...not counted as buttons set up in Settings > Controller", not p.learned)
j = g.Pad(snes, "joystick", {"swap": True})
check("a plain USB pad: its A and B swapped too (buttons 3 and 2)", key(j, e.BTN_THUMB2) == [("a", True)]
      and key(j, e.BTN_THUMB) == [("b", True)] and key(j, e.BTN_TRIGGER) == [("x", True)])
j.apply({"keys": {str(e.BTN_TRIGGER): "a", str(e.BTN_TOP): "b"}, "swap": True})
check("buttons set up, then swapped: those swapped", key(j, e.BTN_TRIGGER) == [("b", True)]
      and key(j, e.BTN_TOP) == [("a", True)] and j.learned and j.swapped)
j.apply({"axes": {str(e.ABS_Y): {"1": "a", "-1": "up"}}, "swap": True})
check("...one on an axis too", j.translate(Ev(e.EV_ABS, e.ABS_Y, 255)) == [("b", True)])
p.apply(None)

# ---- the main loop: Settings > Swap A and B, on the controller in hand ----------------------------
plugged = [pro, xbox]
devs = {d.path: d for d in (pro, pro2, xbox, snes)}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda q, *a, **k: type("St", (), {"st_ino": hash(q) % 1000})() if q.startswith("/dev/input/") else real_stat(q, *a, **k)


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]
m = g.Media(); m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
port = server.server_address[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.4)
presses, lets_go = [], []
real_press, real_release = m.press, m.release
m.press = lambda name, repeat=False: (presses.append((name, repeat)), real_press(name, repeat))[1]
m.release = lambda name: (lets_go.append(name), real_release(name))[1]


def wait(sec=0.15):
    time.sleep(sec)


def tap(dev, code):
    dev.send((e.EV_KEY, code, 1)); wait(); dev.send((e.EV_KEY, code, 0)); wait()


def hat(dev, axis, v):
    dev.send((e.EV_ABS, axis, v)); wait(); dev.send((e.EV_ABS, axis, 0)); wait()


def drawn():
    texts.clear(); m.dirty = True; wait(0.2)
    return list(texts)


def row_value(t):
    """What Swap A and B's row says (after its label, past ◀ ▶)."""
    if "Swap A and B" not in t:
        return None
    return next((x for x in t[t.index("Swap A and B") + 1:] if x not in ("◀", "▶")), None)


def saved():
    try:
        return json.load(open(g.PADS_FILE))
    except (OSError, ValueError):
        return {}


def post(what, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{what}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Pitato-Key": "k" * 32})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=5).read())
    except urllib.error.HTTPError as ex:
        return json.loads(ex.read() or b"{}")


check("both controllers found", sorted(m.pads.by_path) == sorted([pro.path, xbox.path]))
m.open_app(m.tab_index("settings")); m.set_page = "root"
keys = [k for k, _, _ in m.settings_rows()]
check(f"Settings: Swap A and B, just after Controller ({keys[keys.index('pad') - 1:keys.index('pad') + 3]})",
      keys[keys.index("pad") + 1] == "pad_swap" and dict((k, l) for k, l, _ in m.settings_rows())["pad_swap"]
      == "Swap A and B")
row = keys.index("pad_swap")
m.set_sel = row - 1
hat(pro, e.ABS_HAT0Y, 1)                               # down, on the Pro Controller
check("down to it with the Pro Controller's d-pad", m.set_sel == row and m.pad_used is m.pads.by_path[pro.path])
t = drawn()
check(f"...it says Off, and which controller it's for, on the right ({row_value(t)!r})", row_value(t) == "Off"
      and "Pro Controller" in t and "Change" in t)
FB.last.save(S + "/settings_off.png")
hat(pro, e.ABS_HAT0X, 1)                               # ▶
pp = m.pads.by_path[pro.path]
check(f"▶: swapped on the Pro Controller, and it says so ({m.msg!r})", pp.swapped
      and m.msg == "A and B swapped on Pro Controller")
check(f"...kept for that model ({saved()})", saved() == {pp.ident: {"swap": True}})
check("...the Xbox one as it was", not m.pads.by_path[xbox.path].swapped)
check("...the row says On", row_value(drawn()) == "On")
FB.last.save(S + "/settings_on.png")
presses.clear()
tap(pro, e.BTN_SOUTH)                                  # (B on it, at the bottom)
check(f"its B (at the bottom) is B now: Settings goes back to the home screen ({presses})",
      [n for n, _ in presses] == ["b"] and m.view == "home")
presses.clear()
tap(pro, e.BTN_EAST)                                   # (A on it, on the right)
check(f"...and its A (on the right) is A: it opens what's picked ({presses})", [n for n, _ in presses] == ["a"]
      and m.view != "home")
m.open_app(m.tab_index("settings")); m.set_page, m.set_sel = "root", row
wait()
hat(xbox, e.ABS_HAT0Y, -1); hat(xbox, e.ABS_HAT0Y, 1)  # (up and down again, on the Xbox one)
check("another controller pressed: it's the one in hand", m.pad_used is m.pads.by_path[xbox.path]
      and m.set_sel == row)
check("...the row says its own: Off", row_value(drawn()) == "Off" and "Xbox Wireless Controller" in texts)
hat(xbox, e.ABS_HAT0X, -1)                             # ◀, on the Xbox one
check("◀ on the Xbox one: swapped on it, the Pro Controller still swapped",
      m.pads.by_path[xbox.path].swapped and m.pads.by_path[pro.path].swapped and len(saved()) == 2)
tap(xbox, e.BTN_EAST)                                  # (the Xbox one's B, on the right: A now) -> back again
check(f"A on the row (its right button, A now): back as it was ({m.msg!r})", not m.pads.by_path[xbox.path].swapped
      and m.msg == "A and B back to normal on Xbox Wireless Controller" and list(saved()) == [pp.ident])
m.press("right", repeat=True)
check("held, it doesn't keep changing", not m.pads.by_path[xbox.path].swapped)

# held while it changes (the web page swaps it): let go of as what it is now, nothing left held
r = post("pad_swap", {"path": pro.path, "on": False})
check(f"web: back to normal on the Pro Controller ({r})", r == {"ok": True} and not m.pads.by_path[pro.path].swapped)
m.set_sel = keys.index("clock")                       # (a row where ▶ and A only change the clock)
wait()
presses.clear(); lets_go.clear()
pro.send((e.EV_ABS, e.ABS_HAT0X, 1), (e.EV_KEY, e.BTN_SOUTH, 1)); wait(0.7)   # ▶ and A (the bottom one) held
check("▶ held: it goes on (as a held one does)", any(x == ("right", True) for x in presses))
r = post("pad_swap", {"path": pro.path, "on": True})
check(f"web: swapped meanwhile ({r})", r == {"ok": True} and m.pads.by_path[pro.path].swapped)
wait(0.2)
pro.send((e.EV_ABS, e.ABS_HAT0X, 0), (e.EV_KEY, e.BTN_SOUTH, 0)); wait(0.1)
held_after = set(m.pads.by_path[pro.path].down)
before = len([x for x in presses if x[0] == "right"])
wait(0.8)
after = len([x for x in presses if x[0] == "right"])
check(f"...let go: nothing left held ({held_after}), ▶ let go and not going on and on ({before} then {after}),"
      f" the bottom one let go as B ({lets_go})", not held_after and after == before
      and "right" in lets_go and "b" in lets_go)
r = post("pad_swap", {"path": "/dev/input/event99", "on": True})
check(f"web: one that isn't plugged in ({r})", r == {"error": "That controller isn't plugged in"})
st = m.web_state()["controllers"]
check(f"web state: each one, swapped or not ({st})", [(c["name"], c["swap"], c["path"]) for c in st] ==
      [("Pro Controller", True, pro.path), ("Xbox Wireless Controller", False, xbox.path)])

# another of the same model: the same buttons
plugged.append(pro2); wait(0.4)
check("another Pro Controller plugged in: swapped too (its model is)", m.pads.by_path[pro2.path].swapped)
pro2.gone = True; plugged.remove(pro2); pro2.send(); wait(0.3)

# kept: a new start has it
again = g.Pad(pro, "gamepad", g.Pads.load().get(pp.ident))
check("kept for next time", again.swapped and key(again, e.BTN_EAST) == [("a", True)])

# the one in hand unplugged: the row's for the first one there
m.pad_used = m.pads.by_path[xbox.path]
xbox.gone = True; plugged.remove(xbox); xbox.send(); wait(0.3)
check("the one in hand unplugged: the row's for the one left", m.pad_in_hand() is m.pads.by_path[pro.path]
      and m.pad_swap_value() == "On")
pro.gone = True; plugged.remove(pro); pro.send(); wait(0.3)
check("none: it says so", m.pad_swap_value() == "No controller")
m.set_sel = row
m.press("right")
check(f"...◀▶: told why ({m.msg!r})", m.msg == "No controller plugged in")
pro.gone = xbox.gone = False; plugged += [pro, xbox]; wait(0.4)

# Settings > Controller's set-up: the buttons as pressed, the swap gone; Reset: gone too
pp = m.pads.by_path[pro.path]
check("plugged in again: still swapped", pp.swapped)
m.pads.save(pp.ident, {e.BTN_EAST: "a", e.BTN_SOUTH: "b"}, {})
check("set up in Settings > Controller: the buttons as pressed, not swapped", not pp.swapped
      and key(pp, e.BTN_EAST) == [("a", True)] and "swap" not in saved()[pp.ident])
m.pads.swap(pp.ident, True)
check("...swapped after: those swapped, the set-up kept", pp.swapped and key(pp, e.BTN_EAST) == [("b", True)]
      and saved()[pp.ident].get("keys"))
m.pads.swap(pp.ident, False)
check("...back: the set-up as it was", not pp.swapped and key(pp, e.BTN_EAST) == [("a", True)]
      and saved()[pp.ident].get("keys") and "swap" not in saved()[pp.ident])
m.pads.swap(m.pads.by_path[xbox.path].ident, True)
r = post("reset_pads", {})
check("Reset: every controller standard again, none swapped", r == {"ok": True} and saved() == {}
      and not any(x.swapped for x in m.pads.by_path.values()))
ImageDraw.ImageDraw.text = real_text

# ---- the web page: Swap A and B by each controller ---------------------------------------------
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
os.environ["HOME"] = H
webui.HOME = H; webui.STATIC = S + "/pitato/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/pitato/setup.sh", "w").write("echo\n")
open(S + "/control-key", "w").write("k" * 32)
webui.THUMBS = H + "/.cache/pitato/thumbs"; webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", port); webui.CONTROL_KEY = S + "/control-key"
socket.gethostname = lambda: "gpi"
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5458, threaded=True), daemon=True).start()
time.sleep(1)
try:
    from playwright.async_api import async_playwright
except ImportError:                                    # (not on the Pi's Python here: the Pi's side is tested)
    async_playwright = None

ROWS = "els => els.map(li => [li.querySelector('.pn') ? li.querySelector('.pn').textContent : li.textContent, li.querySelector('.k') ? li.querySelector('.k').textContent : '', li.querySelector('.swap') ? li.querySelector('.swap').textContent : ''])"


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        await pg.goto("http://localhost:5458/#screen")
        await pg.wait_for_function("document.querySelectorAll('#padList li .swap').length === 2", timeout=10000)
        rows = await pg.eval_on_selector_all("#padList li", ROWS)
        check(f"web: each controller, Swap A and B by it ({rows})", rows == [
            ["Pro Controller", "Standard buttons", "Swap A and B"],
            ["Xbox Wireless Controller", "Standard buttons", "Swap A and B"]])
        check("...no Reset buttons (nothing to reset)", await pg.is_hidden("#resetBtn"))
        await pg.click("#padList li:has-text('Pro Controller') .swap")
        await pg.wait_for_function("document.querySelector('#padList').textContent.includes('A and B swapped')",
                                   timeout=8000)
        rows = await pg.eval_on_selector_all("#padList li", ROWS)
        check(f"...pressed: swapped on the Pi, said so, Swap back by it ({rows[0]})",
              m.pads.by_path[pro.path].swapped and not m.pads.by_path[xbox.path].swapped
              and rows[0] == ["Pro Controller", "A and B swapped", "Swap back"]
              and "A and B swapped on Pro Controller" in await pg.inner_text("body"))
        check("...Reset buttons there now", not await pg.is_hidden("#resetBtn"))
        await pg.eval_on_selector("#padList", "e => e.scrollIntoView({block: 'center'})")
        await pg.screenshot(path=S + "/web_swap.png")
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        await ph.goto("http://localhost:5458/#screen")
        await ph.wait_for_function("document.querySelectorAll('#padList li .swap').length === 2", timeout=10000)
        await ph.eval_on_selector("#padList", "e => e.scrollIntoView({block: 'center'})")
        wide = await ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        fits = await ph.evaluate("[...document.querySelectorAll('#padList li .swap')].every(x => "
                                 "x.getBoundingClientRect().right <= window.innerWidth - 8)")
        check("a phone: no sideways scrolling, each Swap button on the screen", wide and fits)
        await ph.screenshot(path=S + "/web_swap_phone.png")
        await pg.click("#padList li:has-text('Pro Controller') .swap")
        await pg.wait_for_function("!document.querySelector('#padList').textContent.includes('A and B swapped')",
                                   timeout=8000)
        check("Swap back: as it was", not m.pads.by_path[pro.path].swapped and saved() == {})
        await b.close()


if async_playwright:
    asyncio.run(web())
else:
    print("(no browser for this Python: the web page in a browser is left to the other run)")
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
