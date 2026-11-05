"""Another Pietato, for the tests that need two (sending a game or a video from one to the other, playing together):
its own home folder, its web page and control server on ports of their own, and its main loop, in a process of its own.
Its emulator and player are stand-ins: what it starts, plays and says goes in a log (JSON, a line each), and its
emulator's saves are written as the real one writes them when a game ends (in its folder of saves: a game played
together has its own).

    python3 peer_pietato.py HOME LOG NAME PEER_URL PEER_NAME [slow]

It prints READY <its web page's address> once it's answering; then takes a line at a time: state (what's on its
screen, as JSON), press BUTTON (pressed, on its main loop), home (HOME on a picture, a PDF or some text: its menu),
news WHAT WHY (its emulator says WHAT, then ends: netgone, say), expire (another's asking to play together, not answered
in time), peer URL NAME, quit."""
import json
import os
import sys
import threading
import time

HOME, LOG, NAME, PEER_URL, PEER_NAME = sys.argv[1:6]
SLOW = "slow" in sys.argv[6:]
TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PITATO_ROOT") or os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
os.environ["HOME"] = HOME
import pietato_all as g  # noqa: E402
import socket  # noqa: E402

lock = threading.Lock()
SAY = sys.stdout                                 # (the test's word with it; what Pietato prints goes with its errors)
sys.stdout = sys.stderr


def log(**what):
    with lock, open(LOG, "a") as f:
        f.write(json.dumps(what) + "\n")


for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)
S = HOME + "/.pietato"
os.makedirs(S, exist_ok=True)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.home_dir = lambda: HOME
import gk_static  # noqa: E402
gk_static.use_home(g, HOME)
socket.gethostname = lambda: NAME
real_run = g.subprocess.run
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd[:1] in (["chvt"], ["fgconsole"],
                                                                                            ["setterm"], ["amixer"])
                                         else real_run(cmd, *a, **k))
g.list_devices = lambda: []
g.MEDIA_VT = 99                                  # (no such console: this machine's own are left as they are)
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
import pitato.screens.together as together  # noqa: E402
together.link_core = lambda: "/fake/gambatte_libretro.so"   # (its Game Boy link cable's emulator, there)
if SLOW:
    g.slow_pi = lambda: True


# ---- its emulator: started, and its saves written as it ends -------------------------------------------------------
def game_start(self, core, **kw):
    self.state = "on"
    self.kw = kw
    log(started=self.game["path"], system=self.game["system"], resume=kw.get("resume", True), core=core,
        saves=kw.get("saves"), net=kw.get("net", ""), options=list(kw.get("options") or ()),
        cheevos=kw.get("cheevos", True))


def game_quit(self, timeout=0):
    if getattr(self, "quitted", False):
        return
    self.quitted = True
    saves = getattr(self, "kw", {}).get("saves") or os.path.join(g.games_dir(), g.SAVES_FOLDER)
    base = os.path.join(saves, g.save_name(self.game["path"]))
    for ext in (".srm", ".state.auto"):
        with open(base + ext, "w") as f:
            f.write(f"{NAME}'s {ext}, {time.time()}")
    self.ended = True
    log(quit=self.game["path"])


g.GameRun.start = game_start
g.GameRun.quit = game_quit
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None


# ---- its player -------------------------------------------------------------------------------------------------
class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.stdout = iter(())
        self.stderr = iter(())
        self.returncode = None
        self.args = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Proc()
    log(play=target, args=list(args), kind=self.kind)


g.PlayerScreen.spawn = spawn


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480

    def show(self, img): pass
    def show_part(self, img, box): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
was_toast = m.toast
m.toast = lambda text, secs=4: (log(toast=text), was_toast(text, secs))[1]
m.pie.heard[PEER_URL] = {"host": PEER_NAME, "seen": time.time() + 3600, "peer": True}
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
webui.HOME = HOME
webui.STATIC = S + "/static"
os.makedirs(webui.STATIC + "/fonts", exist_ok=True)
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server  # noqa: E402
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
done = threading.Event()
threading.Thread(target=lambda: g.run(type("UI", (), {"write": lambda *a: None, "syn": lambda *a: None})(), m,
                                      control, stop=done.is_set), daemon=True).start()
print(f"READY http://127.0.0.1:{web.server_port}", file=SAY, flush=True)
try:
    for line in sys.stdin:                            # (the test says what to do here, a line at a time)
        words = line.split(None, 1)
        if not words:
            continue
        if words[0] == "quit":
            break
        if words[0] == "peer":                         # the other one's web page, now it's up
            url, name = words[1].split()
            m.pie.heard.clear()
            m.pie.heard[url] = {"host": name, "seen": time.time() + 3600, "peer": True}
            print("ok", file=SAY, flush=True)
        elif words[0] == "state":
            run = m.game
            inv = m.invite or {}
            v = dict(m.v)
            shown = {k: v[k] for k in ("type", "title", "path", "page", "pages", "fit", "zoom", "scroll", "sx", "top",
                                       "size", "rot", "items") if k in v}
            if v.get("type") == "text":
                lines = v.get("lines") or []
                shown["first"] = lines[v["top"]] if v.get("top", 0) < len(lines) else ""
            target = m.handoff_target()
            print(json.dumps({"game": run.game["path"] if run else None, "kind": m.kind, "view": m.view,
                              "viewer": shown, "to": target[0] if target else None,
                              "file_menu": [k for k, _ in m.file_menu_items()] if m.view == "filemenu" else [],
                              "menu": [k for k, _ in m.game_menu_items()] if run else [],
                              "send": m.game_value("send") if run else "",
                              "note": m.together_note() if run else "",
                              "invite": {"host": inv.get("host"), "title": (inv.get("ident") or {}).get("title"),
                                         "link": inv.get("link"), "pick": inv.get("pick"),
                                         "games": [x["title"] for x in inv.get("games") or []]} if inv else None}),
                  file=SAY, flush=True)
        elif words[0] in ("press", "news", "expire", "home"):   # (done on its main loop, as a button would be)
            done_it = threading.Event()
            rest = words[1].split() if len(words) > 1 else []

            def job(what=words[0], rest=rest):
                try:
                    if what == "press":
                        m.press(rest[0])
                    elif what == "home":
                        m.file_home()
                    elif what == "news" and m.game is not None:
                        m.game.net_news.append((rest[0], " ".join(rest[1:])))
                        m.game.ended = True
                    elif what == "expire" and m.invite is not None:
                        m.invite["until"] = 0.0
                finally:
                    done_it.set()
            m.soon_jobs.append(job)
            m.wake()
            done_it.wait(10)
            print("ok", file=SAY, flush=True)
finally:
    done.set()
