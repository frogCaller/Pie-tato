"""What you're playing, sent to another of your Pietatos (handoff.py, screens/handoff.py): two Pietatos, this one (the
handheld, "gpi") and another in a process of its own (the TV's, "tv": peer_pietato.py), each with its web page.
A game's menu: Play on another Pietato, the TV's name beside it (only while one's on). A: the TV's asked first; the
game ends here (its saves kept) and the TV picks it up from the same moment, its saves from here; a cartridge the TV
hasn't got goes too (with a key that opens just that file, its sum checked); a disc game it hasn't got, or a console
it can't play: said, and the game plays on here. A video: X once says X again sends it; X again: it carries on on the TV
at the same place, from this one's web page (a key for that file only, read from anywhere in it); a station: the
same station there. Not from one that isn't one of yours; keys that don't fit open nothing; the web page's part, your
network only."""
import json, os, shutil, subprocess, sys, threading, time, urllib.error, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import handoff as HO

S = SP + "/t_handoff"
shutil.rmtree(S, ignore_errors=True)
HOME, TV = S + "/gpi", S + "/tv"
for h in (HOME, TV):
    for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/gba", "Games/ps1"):
        os.makedirs(f"{h}/{d}")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the names and the keys, on their own ------------------------------------------------------------------------
keys = HO.Tokens()
f = S + "/x.bin"
open(f, "wb").write(b"x")
k = keys.issue(f)
check("a key opens its own file, and nothing else", keys.path(k) == os.path.abspath(f) and keys.path(k + "x") is None
      and keys.path("../../etc/passwd") is None and keys.path("") is None and keys.path(None) is None)
k2 = keys.issue(f, secs=-1)
check("...not once it's run out", keys.path(k2) is None)
good = {"system": "gba", "rel": "gba/Mon (USA).gba", "name": "Mon (USA)", "title": "Mon", "size": 10, "sum": ""}
check("a game, as another one says it: only as much as makes sense", HO.clean_ident(good) == good
      and HO.clean_ident(dict(good, rel="../x.gba")) is None and HO.clean_ident(dict(good, rel="/etc/x")) is None
      and HO.clean_ident(dict(good, rel="gba/.hidden")) is None and HO.clean_ident(dict(good, system="GBA!")) is None
      and HO.clean_ident(dict(good, name="a/b")) is None and HO.clean_ident(dict(good, size=True)) is None
      and HO.clean_ident(dict(good, sum="zz")) is None and HO.clean_ident("x") is None)
check("...and what's playing", HO.clean_media({"media": "video", "title": "A", "src": "http://x/y", "pos": 3})
      == ("video", "A", "http://x/y", 3.0) and HO.clean_media({"media": "video", "title": "A", "src": "/etc/passwd"})
      is None and HO.clean_media({"media": "game", "title": "A", "src": "http://x"}) is None
      and HO.clean_media({"media": "audio", "title": "A", "src": "http://x", "pos": -1}) is None
      and HO.clean_media({"media": "radio", "title": "A", "src": "file:///etc/passwd"}) is None)

# ---- this one: the handheld -------------------------------------------------------------------------------------------
GAME = "Pokemon Emerald (USA)"
ROM = HOME + "/Games/gba/" + GAME + ".gba"
open(ROM, "wb").write(bytes(range(256)) * 64)
DISC = HOME + "/Games/ps1/Disc Game (USA).cue"
open(DISC, "w").write('FILE "Disc Game (USA).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
open(HOME + "/Games/ps1/Disc Game (USA).bin", "wb").write(b"\0" * 4096)
VIDEO = HOME + "/Videos/holiday.mp4"
open(VIDEO, "wb").write(bytes(range(256)) * 400)
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
quits = []


def game_quit(self, timeout=0):
    base = os.path.join(g.games_dir(), g.SAVES_FOLDER, g.save_name(self.game["path"]))
    for ext in (".srm", ".state.auto"):
        with open(base + ext, "w") as fh:
            fh.write(f"gpi's {ext}")
    quits.append(self.game["path"])
    self.ended = True


g.GameRun.start = lambda self, core, **kw: setattr(self, "state", "on")
g.GameRun.quit = game_quit
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None


class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


g.PlayerScreen.spawn = lambda self, args, target: (setattr(self, "proc", Proc()), setattr(self, "started", time.monotonic()))


class FB:
    w, h = 640, 480
    frames = 0
    def show(self, img): FB.frames += 1
    def show_part(self, img, box): FB.frames += 1
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts, osds = [], []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
m.osd = lambda text, ms=1500: osds.append(text)
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
webui.STATIC = S + "/gpistatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
MINE = f"http://127.0.0.1:{web.server_port}"

# ---- the other one: the TV's ------------------------------------------------------------------------------------------
LOG = S + "/tv.log"
open(LOG, "w").close()
shutil.copy(ROM, TV + "/Games/gba/" + GAME + ".gba")      # (it has the same game)
open(TV + "/Games/Saves/" + GAME + ".state.auto", "w").write("the tv's old place")
os.utime(TV + "/Games/Saves/" + GAME + ".state.auto", (time.time() - 86400, time.time() - 86400))
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "gpi"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
line = tv.stdout.readline().split()
if line[:1] != ["READY"]:
    print("FAIL the TV's Pietato didn't start", line)
    sys.exit(1)
THEIRS = line[1]


def tv_said(key, since=0, secs=8.0):
    """What the TV's Pietato did, from its log: the newest with that key (after since lines), waiting a while."""
    end = time.time() + secs
    while True:
        rows = [json.loads(x) for x in open(LOG).read().splitlines()[since:] if x.strip()]
        hits = [r for r in rows if key in r]
        if hits or time.time() > end:
            return hits[-1] if hits else None
        time.sleep(0.1)


def tv_lines():
    return len(open(LOG).read().splitlines())


def tv_state():
    tv.stdin.write("state\n")
    return json.loads(tv.stdout.readline())


def opened(path, system="gba"):
    m.game_open({"src": path, "title": g.game_title(path), "system": system})
    m.game_menu_open()


try:
    # ---- a game's menu -------------------------------------------------------------------------------------------
    opened(ROM)
    jobs = [k for k, _ in m.game_menu_items()]
    check(f"no other Pietato on: nothing to send to ({jobs})", "send" not in jobs)
    m.pie.heard[THEIRS] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
    jobs = [k for k, _ in m.game_menu_items()]
    check(f"the TV's on: Play on another Pietato, with its name, before Quit ({jobs[-2:]}, {m.game_value('send')})",
          jobs[-2:] == ["send", "quit"] and m.game_value("send") == "tv")
    m.pie.heard["http://127.0.0.2:5432"] = {"host": "den", "seen": time.time() + 3000, "peer": True}
    m.game_change("send", 1)
    picked = m.game_value("send")
    m.game_change("send", 1)
    check(f"...◀▶ picks another of yours ({picked}, then {m.game_value('send')})", picked == "den"
          and m.game_value("send") == "tv")
    del m.pie.heard["http://127.0.0.2:5432"]

    # ---- sent: the TV has it -----------------------------------------------------------------------------------------
    n = tv_lines()
    toasts.clear()
    m.game_send()
    started = tv_said("started", n)
    check(f"A: the game ends here, its saves kept ({quits}, {m.game is None})", quits == [ROM] and m.game is None)
    check(f"...the TV picks it up: its own copy ({started})", started is not None
          and started["started"] == TV + "/Games/gba/" + GAME + ".gba" and started["resume"] is True)
    check("...from the same moment: where you were here, and the in-game save",
          open(TV + "/Games/Saves/" + GAME + ".state.auto").read() == "gpi's .state.auto"
          and open(TV + "/Games/Saves/" + GAME + ".srm").read() == "gpi's .srm")
    check(f"...and it says so here ({toasts[-1:]})", toasts[-1:] == ["Playing on tv now. Its menu there sends it back"])
    st = tv_state()
    check(f"...the TV's menu sends it back: Play on another Pietato, gpi ({st['menu'][-2:]}, {st['send']})",
          st["menu"][-2:] == ["send", "quit"] and st["send"] == "gpi")

    # ---- a cartridge the TV hasn't got: it goes too ------------------------------------------------------------------
    os.remove(TV + "/Games/gba/" + GAME + ".gba")
    n = tv_lines()
    opened(ROM)
    m.game_send()
    started = tv_said("started", n)
    copied = TV + "/Games/gba/" + GAME + ".gba"
    check(f"a cartridge the TV hasn't got: copied over, the same game, then picked up ({started})",
          started is not None and started["started"] == copied and os.path.isfile(copied)
          and open(copied, "rb").read() == open(ROM, "rb").read())
    check("...nothing left half-copied", not [x for x in os.listdir(TV + "/Games/gba") if x.endswith(".part")])

    # ---- a disc game it hasn't got: not sent ------------------------------------------------------------------------------
    quits.clear()
    toasts.clear()
    opened(DISC, "ps1")
    m.game_send()
    check(f"a disc game the TV hasn't got: said, and it plays on here ({toasts[-1:]}, {quits})",
          toasts[-1:] == ["tv doesn't have this game. Put it in its Games folder too"] and quits == []
          and m.game is not None)
    m.game_end()
    quits.clear()

    # ---- a console it can't play ----------------------------------------------------------------------------------------
    N64 = HOME + "/Games/Mario (USA).z64"
    open(N64, "wb").write(b"\x80\x37\x12\x40" + bytes(4092))
    g.playable = lambda key: True
    toasts.clear()
    m.game_open({"src": N64, "title": "Mario", "system": "n64"})
    m.game_menu_open()
    tv.stdin.write("quit\n")                           # (the TV again, as a Pi too slow for N64 games)
    tv.wait(10)
    tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "gpi", "slow"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    THEIRS = tv.stdout.readline().split()[1]
    m.pie.heard.clear()
    m.pie.heard[THEIRS] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
    m.game_send()
    check(f"a console the TV can't play: said, and it plays on here ({toasts[-1:]}, {quits})",
          toasts[-1:] == ["tv: Nintendo 64 games don't play on this Pi"] and quits == [] and m.game is not None)
    m.game_end()

    # ---- a video: X, then X again --------------------------------------------------------------------------------------
    n = tv_lines()
    m.play([{"kind": "video", "src": VIDEO, "title": "Holiday", "key": VIDEO}], 0, start=0)
    m.pos = 125.0
    m.view = "list"
    osds.clear()
    m.press("x")
    check(f"a video: X says X again sends it ({osds[-1:]})", osds[-1:] == ["2:05   X again: play it on tv"]
          and m.proc is not None)
    m.press("x")
    played = tv_said("play", n)
    check(f"...X again: it carries on on the TV, a moment before where it was ({played and played['play'][:60]}, "
          f"{played and played['args'][-2:]})", played is not None and played["kind"] == "video"
          and played["play"].startswith("ffmpeg://" + MINE + "/api/handoff/file?token=")
          and played["args"][-2:] == ["-ss", "122"])
    check(f"...and here it's stopped ({m.proc}, {toasts[-1:]})", m.proc is None and toasts[-1:] == ["Playing on tv now"])
    url = played["play"][len("ffmpeg://"):]
    req = urllib.request.Request(url, headers={"Range": "bytes=100-199"})
    with urllib.request.urlopen(req, timeout=5) as r:
        part, code = r.read(), r.status
    check(f"...the TV reads the video from here as it plays it, from anywhere in it ({code}, {len(part)} bytes)",
          code == 206 and part == open(VIDEO, "rb").read()[100:200])
    try:
        urllib.request.urlopen(url[:-3] + "abc", timeout=5)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    check(f"...a key that doesn't fit opens nothing ({code})", code == 404)
    c = webui.app.test_client()
    far = c.get(url[len(MINE):], base_url="http://192.168.1.30:5432", environ_base={"REMOTE_ADDR": "8.8.8.8"})
    check(f"...nor from outside your network ({far.status_code})", far.status_code == 403)

    # ---- a station ----------------------------------------------------------------------------------------------------
    n = tv_lines()
    m.play([{"kind": "radio", "src": "https://stream.example.com/jazz", "title": "Jazz FM"}], 0)
    m.view = "now"
    m.press("x")
    shown = m.view
    m.press("x")
    played = tv_said("play", n)
    check(f"a station: X on Now playing shows its Controls, X again sends it ({shown}, "
          f"{played and played['play']})", shown == "help" and played is not None and played["kind"] == "radio"
          and "stream.example.com/jazz" in played["play"] and m.proc is None)

    # ---- not one of yours ----------------------------------------------------------------------------------------------
    out = m.web_peer_handoff({"kind": "game", "from": "192.168.1.99", **good})
    check(f"from a Pi that isn't one of your Pietatos: not taken ({out})", out == {"ok": False,
                                                                                   "error": "Not one of your Pietatos"})
    far = c.post("/api/handoff", json={"kind": "game"}, base_url="http://192.168.1.30:5432",
                 environ_base={"REMOTE_ADDR": "8.8.8.8"})
    check(f"...and the web page's part answers your network only ({far.status_code})", far.status_code == 403)
finally:
    try:
        tv.stdin.write("quit\n")
        tv.stdin.flush()
        tv.wait(10)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        tv.kill()
    web.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
