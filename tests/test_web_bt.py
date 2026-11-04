"""The web page's Bluetooth, in a real browser, against a fake Pi (Media, its control server and webui.py, all here)
and the pretend BlueZ (btfake): yours, Find devices, the ones nearby, Pair (a keyboard's code shown), Disconnect,
Forget (asked twice), off and Turn it on; asked about only while it's in view; a phone's width. Screenshots."""
import asyncio, copy, json, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/btfake")
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import setup_env as F
import pietato_all as g
S = SP + "/t_webbt"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
F.use(S + "/bt", copy.deepcopy(F.STATE))
st = F.get()
st["nearby"]["54:46:6B:00:00:05"]["typing"] = 2.5
F.put(st)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
real_run = subprocess.run
FAKE = {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd", "aplay", "systemctl"}
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in FAKE
                                       else real_run(cmd, *a, **k))
g.list_devices = lambda: []
g.BT_EVERY, g.BT_WEB, g.BT_LOOK = 0.5, 4.0, 30.0


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui
os.environ["HOME"] = H
webui.HOME = H; webui.STATIC = S + "/pitato/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/pitato/setup.sh", "w").write("echo\n")
webui.THUMBS = H + "/.cache/pitato/thumbs"; webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
socket.gethostname = lambda: "gpi"
done = threading.Event()
threading.Thread(target=lambda: g.run(type("UI", (), {"write": lambda *a: None, "syn": lambda *a: None})(), m, control,
                                      stop=done.is_set), daemon=True).start()
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5457, threaded=True), daemon=True).start()
time.sleep(1)
from playwright.async_api import async_playwright
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def asked():
    return sum(1 for l in F.log() if "GetManagedObjects" in l)


ROWS = "els => els.map(li => li.querySelector('.bn b') ? li.querySelector('.bn b').textContent + ' | ' + li.querySelector('.bn small').textContent : li.textContent)"


async def rows(pg):
    return await pg.eval_on_selector_all("#btList li", ROWS)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 440})    # (short: Bluetooth below what's in view,
                                                                           # under the remote beside the screen)
        await pg.goto("http://localhost:5457/#screen")
        await pg.wait_for_selector("#btCard")
        top = await pg.evaluate("document.querySelector('#btCard').getBoundingClientRect().top - innerHeight")
        time.sleep(5.0)                                    # (anything asked as the page loaded, let go)
        before = asked()
        time.sleep(2.0)
        check(f"out of view ({top:.0f} px below): the Pi isn't asked about Bluetooth ({asked() - before} looks)",
              top > 0 and (not m.bt.wanted() or asked() - before <= 1))
        await pg.set_viewport_size({"width": 1280, "height": 900})
        await pg.eval_on_selector("#btCard", "e => e.scrollIntoView()")
        await pg.wait_for_function("document.querySelector('#btList').textContent.includes('8BitDo')", timeout=8000)
        r = await rows(pg)
        check(f"in view: yours, connected or not ({r})", r == ["8BitDo SN30 Pro | Connected", "Keyboard K380 | Not connected"])
        acts = await pg.eval_on_selector_all("#btList li .btacts button", "els => els.map(e => e.textContent)")
        check(f"...Connect or Disconnect, and Forget, by each ({acts})", acts == ["Disconnect", "Forget", "Connect", "Forget"])
        check("...Find devices", await pg.inner_text("#btLook") == "Find devices")
        await pg.click("#btLook")
        await pg.wait_for_function("document.querySelector('#btList').textContent.includes('Pro Controller')", timeout=8000)
        r = await rows(pg)
        check(f"Find devices: the ones nearby, under Nearby, what each is ({r})", "Nearby" in r
              and "Pro Controller | Controller" in r and "WH-1000XM4 | Headphones" in r
              and r.index("Nearby") == 2)
        check("...Stop looking, and it says it's looking", await pg.inner_text("#btLook") == "Stop looking"
              and "Looking for devices" in await pg.inner_text("#btBox"))
        await pg.eval_on_selector("#btCard", "e => e.scrollIntoView({block: 'center'})")
        await pg.screenshot(path=S + "/web_bt_found.png")
        # a keyboard: its code
        await pg.click("#btList li:has-text('Logi K480') button:text-is('Pair')")
        await pg.wait_for_function("document.querySelector('#btBox .code') && document.querySelector('#btBox .code').textContent === '482915'",
                                   timeout=8000)
        box = await pg.inner_text("#btBox")
        check(f"Pair a keyboard: its code to type, and what to do ({box!r})", "482915" in box
              and "Type this on the keyboard, then press Enter on it." in box)
        r = await rows(pg)
        check(f"...it says Pairing… ({[x for x in r if 'K480' in x]})", "Logi K480 | Pairing…" in r)
        await pg.screenshot(path=S + "/web_bt_code.png")
        await pg.wait_for_function("document.querySelector('#btBox').textContent.includes('Logi K480 is connected')", timeout=12000)
        r = await rows(pg)
        check(f"...connected, one of yours now ({r[:4]})", "Logi K480 | Connected" in r and r.index("Logi K480 | Connected") < r.index("Nearby"))
        # disconnect, and forget (asked twice)
        await pg.click("#btList li:has-text('8BitDo') button:text-is('Disconnect')")
        await pg.wait_for_function("document.querySelector('#btList').textContent.includes('8BitDo SN30 ProNot connected')", timeout=8000)
        check("Disconnect: not connected", not F.get()["devices"]["E4:17:D8:00:00:01"]["connected"])
        await pg.click("#btList li:has-text('Keyboard K380') button:text-is('Forget')")
        txt = await pg.inner_text("#btList li:has-text('Keyboard K380') .btacts")
        check(f"Forget: asked first ({txt!r})", "Forget it?" in txt and "DC:2C:26:00:00:02" in F.get()["devices"])
        await pg.click("#btList li:has-text('Keyboard K380') button:text-is('Forget it?')")
        await pg.wait_for_function("!document.querySelector('#btList').textContent.includes('Keyboard K380')", timeout=8000)
        check("...again: forgotten", "DC:2C:26:00:00:02" not in F.get()["devices"])
        # off, and on from the page
        await pg.click("#btLook")                          # (Stop looking)
        m.bt.do("off")
        await pg.wait_for_function("document.querySelector('#btList').textContent.includes('Bluetooth is off')", timeout=8000)
        check("off: said so, Find devices hidden", await pg.is_hidden("#btLook"))
        await pg.screenshot(path=S + "/web_bt_off.png")
        await pg.click("#btList button:text-is('Turn it on')")
        await pg.wait_for_function("document.querySelector('#btList').textContent.includes('8BitDo')", timeout=8000)
        check("Turn it on: on again", F.get()["powered"])
        # a phone
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        await ph.goto("http://localhost:5457/#screen")
        await ph.wait_for_selector("#btCard")
        await ph.eval_on_selector("#btCard", "e => e.scrollIntoView()")
        await ph.wait_for_function("document.querySelector('#btList').textContent.includes('8BitDo')", timeout=8000)
        await ph.click("#btLook")
        await ph.wait_for_function("document.querySelector('#btList').textContent.includes('Nearby')", timeout=8000)
        wide = await ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        check("a phone: no sideways scrolling", wide)
        fits = await ph.evaluate("""[...document.querySelectorAll('#btList li .btacts')].every(a => a.getBoundingClientRect().right <= window.innerWidth - 8)""")
        check("...each row's buttons on the screen", fits)
        await ph.eval_on_selector("#btCard", "e => e.scrollIntoView()")
        await ph.screenshot(path=S + "/web_bt_phone.png")
        await b.close()


asyncio.run(main())
done.set()
m.bt.watch("screen", False)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
