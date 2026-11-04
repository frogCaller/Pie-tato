"""The web page's Computers tab in a real browser, against a fake Pi (Media, its control server and webui.py, all
here) with the real test servers: the list, adding one (a login asked for, then given), a computer's shared folders,
an SSH computer's files, and a phone. Screenshots for a look."""
import asyncio, atexit, json, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
os.environ["PATH"] = SP + "/fakebin:" + os.environ["PATH"]


def port_open(p):
    s = socket.socket(); s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


if not any(port_open(p) for p in (445, 4445, 2222, 2223)):   # (the real test servers, just for this: stopped at the end)
    atexit.register(lambda: subprocess.run(["bash", SP + "/net_servers.sh", "stop"], capture_output=True))
    subprocess.run(["bash", SP + "/net_servers.sh"], capture_output=True)
if not all(port_open(p) for p in (4445, 2222)):
    print("FAIL the test servers didn't start (sshd, smbd: openssh-server and samba, with sshfs and smbclient)")
    sys.exit(1)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
S = SP + "/t_webpc"
for w in sorted(g.mounted(S), reverse=True):
    subprocess.run(["umount", "-l", w])
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.KNOWN_HOSTS = S + "/known_hosts"; g.SECRETS = S + "/run"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
real_run = subprocess.run
FAKE = {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd", "aplay", "systemctl"}
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in FAKE
                                       else real_run(cmd, *a, **k))
g.list_devices = lambda: []


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
m.computers.add("127.0.0.1:2222", "alice", "Op3n Sesame!")
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
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
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5455, threaded=True), daemon=True).start()
time.sleep(1)
from playwright.async_api import async_playwright
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for scheme in ("dark", "light"):
            pg = await b.new_page(viewport={"width": 1280, "height": 860}, color_scheme=scheme)
            await pg.goto("http://localhost:5455/#computers")
            await pg.wait_for_selector(".add-pc")
            await pg.wait_for_selector(".row.dir")
            rows = await pg.eval_on_selector_all("#list .row .name", "els => els.map(e => e.firstChild.textContent)")
            check(f"[{scheme}] the computers ({rows})", rows == ["127.0.0.1:2222"])
            await pg.screenshot(path=f"{SP}/out/web_pc_list_{scheme}.png")
            if scheme == "light":
                await pg.close(); continue
            # add one that wants a login, without it: told, the user name box gets the cursor
            await pg.fill(".add-pc input[aria-label='The computer\\'s address']", "smb://127.0.0.1:4445")
            await pg.click(".add-pc .btn")
            await pg.wait_for_function("document.querySelector('#toast').textContent.includes('user name')")
            focused = await pg.evaluate("document.activeElement.getAttribute('aria-label')")
            check(f"a login asked for ({focused})", focused == "User name on that computer")
            await pg.fill(".add-pc input[aria-label='User name on that computer']", "alice")
            await pg.fill(".add-pc input[aria-label='Password on that computer']", "Op3n Sesame!")
            await pg.click(".add-pc .btn")
            await pg.wait_for_function("location.hash === '#computers/127.0.0.1_4445'")
            await pg.wait_for_function("document.querySelector('#list').textContent.includes('Public')")
            names = await pg.eval_on_selector_all("#list .row .name", "els => els.map(e => e.firstChild.textContent)")
            crumbs = await pg.eval_on_selector_all("#crumbs button", "els => els.map(e => e.textContent)")
            check(f"added: its shared folders ({names}, {crumbs})", names == ["Media", "Public"]
                  and crumbs == ["Other computers", "127.0.0.1:4445"])
            await pg.screenshot(path=SP + "/out/web_pc_shares.png")
            await pg.click("#list .row.dir >> nth=0")
            await pg.wait_for_function("location.hash === '#computers/127.0.0.1_4445/Media'")
            await pg.wait_for_function("document.querySelector('#list').textContent.includes('Films')")
            await pg.click("#list .row.dir >> nth=0")
            await pg.wait_for_function("document.querySelector('#list').textContent.includes('movie.mkv')")
            names = await pg.eval_on_selector_all("#list .row .name", "els => els.map(e => e.textContent)")
            trash = await pg.eval_on_selector_all("#list .row .acts [title='Delete']", "els => els.length")
            check(f"a share's files, read-only (no delete) ({names}, {trash})", any("movie.mkv" in n for n in names) and trash == 0)
            await pg.hover("#list .row:not(.dir)")
            await pg.screenshot(path=SP + "/out/web_pc_files.png")
            # an SSH one: straight into the user's folder
            await pg.click("#crumbs button >> nth=0")
            await pg.wait_for_selector(".add-pc")
            await pg.click("#list .row.dir >> text=127.0.0.1:2222")
            await pg.wait_for_function("location.hash === '#computers/127.0.0.1_2222/home/alice'")
            await pg.wait_for_function("document.querySelector('#list').textContent.includes('notes.txt')")
            names = await pg.eval_on_selector_all("#list .row .name", "els => els.map(e => e.textContent)")
            check(f"an SSH one: the user's own folder ({names})", any("notes.txt" in n for n in names))
            await pg.screenshot(path=SP + "/out/web_pc_ssh.png")
            # dropping files on the Computers tab: they go onto the Pi, not the computer (the overlay isn't offered)
            over = await pg.evaluate("""() => { const ev = new DragEvent('dragover', {bubbles: true, cancelable: true,
                dataTransfer: new DataTransfer()}); ev.dataTransfer.items.add(new File(['x'], 'a.txt'));
                document.querySelector('#list').dispatchEvent(ev); return document.body.className; }""")
            check(f"files dragged over a computer's list: offered to the Pi ({over})", "drag-browse" not in over)
            # forget the Windows-like one, from the list
            await pg.click("#crumbs button >> nth=0")
            await pg.wait_for_selector(".add-pc")
            row = pg.locator("#list .row.dir", has_text="127.0.0.1:4445")
            await row.hover()
            await row.locator("[title='Forget this computer']").click()
            await row.locator(".ib.confirm").click()
            await pg.wait_for_function("!document.querySelector('#list').textContent.includes('127.0.0.1:4445')")
            check("forgotten", True)
            await pg.close()
        # a phone
        ph = await b.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark", is_mobile=True, has_touch=True)
        await ph.goto("http://localhost:5455/#computers")
        await ph.wait_for_selector(".add-pc")
        await ph.wait_for_selector("#list .row.dir")
        wide = await ph.evaluate("document.documentElement.scrollWidth <= 390")
        check("phone: nothing wider than the screen", wide)
        await ph.evaluate("document.querySelector('#browse').scrollIntoView()")
        await ph.screenshot(path=SP + "/out/web_pc_phone.png")
        await b.close()


asyncio.run(main())
done.set(); server.shutdown(); m.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
