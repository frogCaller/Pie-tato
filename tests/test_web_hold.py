"""The web page's remote in a game: a button held down there is held down in the game till it's let go of (the d-pad
held walks, as a controller's does), not pressed once; the page says it's still held every so often, and the Pi lets go
of it by itself when the page goes quiet. In the menus it's pressed once, and again and again while it's held, as
before. Media mode's main loop and its control server, then the web page in a real browser: the d-pad held with the
mouse, and the keyboard's arrows."""
import asyncio, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_webhold"
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
g.list_devices = lambda: []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


class FakeGame:
    """A game that's on, as far as the main loop looks at one: what it's pressed and let go of, noted."""
    ended, state, error, disc, slow, cheevos, together = False, "on", None, (1, 1), False, None, None
    game = {"system": "nes", "title": "Test Game", "path": "/nowhere/Test Game (USA).nes"}

    def __init__(self):
        self.log = []

    def pause(self):
        return True

    def press(self, button, port):
        self.log.append(("down", button, port))

    def release(self, button, port):
        self.log.append(("up", button, port))

    def __getattr__(self, name):                       # (anything else asked of it: nothing happens)
        return lambda *a, **k: None


g.Framebuffer = FB
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
presses = []
real_press = m.press
m.press = lambda name, repeat=False: (presses.append((name, repeat)), real_press(name, repeat))[1]


def ask(**cmd):
    return control.ask(dict(cmd, cmd="press"))


def in_game():
    run = FakeGame()
    m.game, m.view = run, "game"
    time.sleep(0.15)
    return run


# ---- the Pi's side: what the page asks ---------------------------------------------------------------------------
run = in_game()
out = ask(button="right", hold="down")
time.sleep(0.5)
check(f"in a game, ▶ held down on the web page: down in the game, not let go of ({out}, {run.log})",
      out.get("held") is True and run.log == [("down", "right", 0)])
for _ in range(5):
    out = ask(button="right", hold="still")
    time.sleep(0.3)
check(f"...the page saying it's still held: still down 2 s on ({out}, {run.log})",
      out.get("held") is True and run.log == [("down", "right", 0)])
out = ask(button="right", hold="up")
time.sleep(0.1)
check(f"...let go of on the page: let go of in the game ({out}, {run.log})",
      "held" not in out and run.log == [("down", "right", 0), ("up", "right", 0)])

run.log.clear()
ask(button="a", hold="down")
time.sleep(0.5)
check("A held, then the page goes quiet: still down a moment", run.log == [("down", "a", 0)])
time.sleep(1.0)
check(f"...a second with nothing from it: let go of by itself ({run.log})",
      run.log == [("down", "a", 0), ("up", "a", 0)])
out = ask(button="a", hold="still")
check(f"...the page, back: it says it isn't held any more ({out})", out == {"ok": True})
out = ask(button="a", hold="up")
check(f"...and its letting go: nothing more ({out}, {run.log})",
      out == {"ok": True} and run.log == [("down", "a", 0), ("up", "a", 0)])

run.log.clear()
ask(button="left", hold="down")
ask(button="left", hold="down")
time.sleep(0.1)
check(f"held down twice over (no letting go between): one press ({run.log})", run.log == [("down", "left", 0)])
ask(button="left", hold="up")
time.sleep(0.1)

run.log.clear()
out = ask(button="b")
check(f"a press with no holding, as before: down and up at once ({out}, {run.log})",
      "held" not in out and run.log == [("down", "b", 0), ("up", "b", 0)])

out = ask(button="home", hold="down")
time.sleep(0.2)
check(f"HOME (the Hotkey) held down: never held, its menu as ever ({out}, {m.view})",
      "held" not in out and m.view == "gamemenu")

m.game, m.view = None, "home"
time.sleep(0.15)
presses.clear()
out = ask(button="down", hold="down")
time.sleep(0.1)
check(f"in the menus, held down on the page: pressed once, not held ({out}, {presses})",
      "held" not in out and presses == [("down", False)])
out = ask(button="down", hold="up")
check(f"...its letting go: nothing more ({out}, {presses})", out == {"ok": True} and presses == [("down", False)])

# ---- the web page in a browser ------------------------------------------------------------------------------------
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
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5463, threaded=True), daemon=True).start()
time.sleep(1)
try:
    from playwright.async_api import async_playwright
except ImportError:                                    # (not on the Pi's Python here: the Pi's side is tested)
    async_playwright = None


async def held_down(pg, sel, sec):
    box = await pg.locator(sel).bounding_box()
    await pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await pg.mouse.down()
    await asyncio.sleep(sec)


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        await pg.goto(f"http://localhost:5463/#screen")
        await pg.wait_for_selector('.dp[data-b="right"]', state="visible", timeout=10000)
        await pg.wait_for_function("typeof SCR !== 'undefined' && SCR.state && SCR.state.mode === 'media'",
                                   timeout=10000)
        run = in_game()
        await held_down(pg, '.dp[data-b="right"]', 1.8)
        mid = list(run.log)
        await pg.mouse.up()
        await asyncio.sleep(0.5)
        check(f"web: in a game, ▶ held with the mouse: down, and still down 1.8 s on ({mid}); let go of: up "
              f"({run.log})", mid == [("down", "right", 0)] and run.log == [("down", "right", 0), ("up", "right", 0)])

        run.log.clear()
        await pg.keyboard.down("ArrowLeft")
        await asyncio.sleep(1.6)
        mid = list(run.log)
        await pg.keyboard.up("ArrowLeft")
        await asyncio.sleep(0.5)
        check(f"...the keyboard's ◀ held: down till it's let go of ({mid}, {run.log})",
              mid == [("down", "left", 0)] and run.log == [("down", "left", 0), ("up", "left", 0)])

        run.log.clear()
        await held_down(pg, '.fbtn[data-b="a"]', 0.05)
        await pg.mouse.up()
        await asyncio.sleep(0.5)
        check(f"...a quick tap of A: down and up ({run.log})", run.log == [("down", "a", 0), ("up", "a", 0)])

        run.log.clear()
        await held_down(pg, '.dp[data-b="down"]', 1.0)
        await pg.evaluate("window.dispatchEvent(new Event('blur'))")   # (the page put away, the button still down)
        await asyncio.sleep(0.5)
        check(f"...the page put away while ▼ is held: let go of on the Pi ({run.log})",
              run.log == [("down", "down", 0), ("up", "down", 0)])
        await pg.mouse.up()

        m.game, m.view = None, "home"
        await asyncio.sleep(0.3)
        presses.clear()
        await held_down(pg, '.dp[data-b="down"]', 1.2)
        await pg.mouse.up()
        await asyncio.sleep(0.4)
        again = [p for p in presses if p == ("down", True)]
        check(f"web: in the menus, ▼ held: pressed, then again and again as before ({presses})",
              presses[:1] == [("down", False)] and len(again) >= 3
              and all(p in (("down", False), ("down", True)) for p in presses))
        await b.close()


if async_playwright:
    asyncio.run(web())
else:
    print("(no browser for this Python: the web page in a browser is left to the other run)")
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
