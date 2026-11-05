"""What you're playing, sent to another of your Pietatos (handoff.py, screens/handoff.py): two Pietatos, this one (the
handheld, "gpi") and another in a process of its own (the TV's, "tv": peer_pietato.py), each with its web page.
A game's menu: Play on another Pietato, the TV's name beside it (only while one's on). A: the TV's asked first; the
game ends here (its saves kept) and the TV picks it up from the same moment, its saves from here; a cartridge the TV
hasn't got goes too (with a key that opens just that file, its sum checked); a disc game it hasn't got, or a console
it can't play: said, and the game plays on here. A video: X once says X again sends it; X again: it carries on on the TV
at the same place, from this one's web page (a key for that file only, read from anywhere in it); a station: the
same station there. A PDF, some text or a picture you're looking at: HOME (while another of yours is on) is its menu,
and View on another Pietato opens it on the TV where you were in it (the page, how close, how far down; the line at the
top and the letters' size; the picture's turn), from a key to that file, and closes it here; HOME there sends it back.
A password's file stays here; one the web page couldn't read goes as a copy. Not from one that isn't one of yours; keys
that don't fit open nothing; the web page's part, your network only."""
import json, os, shutil, subprocess, sys, threading, time, urllib.error, urllib.request
real_run = subprocess.run                            # (what's stood in for, below: put back for PDFs' own programs)
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
check("...and what you're looking at", HO.clean_file({"view": "pdf", "title": "a.pdf", "size": 9, "page": 3,
                                                     "fit": "width", "zoom": 1.5, "at": 0.25, "sx": 0.5})
      == ("pdf", "a.pdf", 9, {"page": 3, "fit": "width", "zoom": 1.5, "at": 0.25, "sx": 0.5})
      and HO.clean_file({"view": "text", "title": "n.txt", "size": 0, "first": "x" * 500, "frac": 2, "big": True})
      == ("text", "n.txt", 0, {"first": "x" * HO.FIRST_MOST, "frac": 0.0, "big": 0})
      and HO.clean_file({"view": "photo", "title": "p.jpg", "size": 5, "rot": 9}) == ("photo", "p.jpg", 5, {"rot": 0})
      and HO.clean_file({"view": "photo", "title": "../p.jpg", "size": 5}) is None
      and HO.clean_file({"view": "game", "title": "p", "size": 5}) is None
      and HO.clean_file({"view": "pdf", "title": "p", "size": HO.FILE_MOST + 1}) is None
      and HO.clean_file({"view": "pdf", "title": "p", "size": True}) is None and HO.file_place("../a/b?.pdf") == "a_b_.pdf")

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
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    F = m.fonts
    items = m.game_menu_items()

    def row_needs(name):
        return 24 + d.textlength("Play on another Pietato", font=F["row_b"]) + 28 \
            + d.textlength(f"◀  {name}  ▶", font=F["small"]) + 22
    mw = m.game_menu_width(d, items, m.game.game["title"])
    check(f"...the menu's wide enough for it, picked, and the name beside it ({mw} for {row_needs('tv'):.0f})",
          mw >= row_needs("tv") and mw > 360)
    m.pie.heard[THEIRS]["host"] = "kitchen-pietato-zero"
    mw2 = m.game_menu_width(d, items, m.game.game["title"])
    check(f"...wider for a longer name ({mw2} for {row_needs('kitchen-pietato-zero'):.0f}), no wider than the screen",
          row_needs("kitchen-pietato-zero") <= mw2 <= 640 - 2 * g.GAME_MENU_EDGE)
    m.pie.heard[THEIRS]["host"] = "tv"
    # two of your Pietatos with the same name: told apart (the end of their addresses, and each one's colour)
    TWIN = "http://127.0.0.3:5432"
    m.pie.heard[THEIRS]["accent"] = "Purple"
    m.pie.heard[TWIN] = {"host": "tv", "seen": time.time() + 3600, "peer": True, "accent": "Gold"}
    end = "." + THEIRS.split("//")[1].split(":")[0].rsplit(".", 1)[1]
    check(f"two of the same name: the end of each one's address after it ({m.saves_peers()})",
          sorted(h for _, h in m.saves_peers()) == sorted([f"tv ({end})", "tv (.3)"]))
    seen = []
    for _ in range(3):
        seen.append(m.handoff_target()[0])
        m.game_change("send", 1)
    check(f"...◀▶ goes to each of them, and round again ({[u.split('//')[1] for u in seen]})",
          set(seen) == {THEIRS, TWIN} and seen[0] == seen[2] != seen[1])
    check(f"...each in its own colour (its accent colour, from its beacon: {m.peer_colour(THEIRS)}, "
          f"{m.peer_colour(TWIN)})", m.peer_colour(THEIRS) == dict(g.ACCENTS)["Purple"]
          and m.peer_colour(TWIN) == dict(g.ACCENTS)["Gold"])
    m.handoff_to = TWIN
    m.game_menu = {"sel": [j for j, _ in items].index("send"), "confirm": (None, 0.0), "bg": None}
    m.view = "gamemenu"
    shot = []
    was_show = m.fb.show
    m.fb.show = lambda img: shot.append(img.copy())
    m.dirty = True; m.flush()
    m.fb.show = was_show
    gold = dict(g.ACCENTS)["Gold"]
    dots = sum(1 for px in shot[-1].convert("RGB").getdata() if px == gold) if shot else 0
    check(f"...the picked one's dot drawn in its colour ({dots} pixels of gold)", dots >= 40)
    del m.pie.heard[TWIN]
    m.handoff_to = THEIRS
    check(f"...one again: its name alone ({m.saves_peers()})", [h for _, h in m.saves_peers()] == ["tv"])
    m.dirty = True; m.flush()

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

    # ---- HOME on a video, or on Now playing: its menu, as a picture's has (Play on another Pietato) ----------------------
    cmds = []
    was_cmd = m.cmd
    m.cmd = lambda c: cmds.append(c)
    n = tv_lines()
    m.play([{"kind": "video", "src": VIDEO, "title": "Holiday", "key": VIDEO}], 0, start=0)
    m.pos, m.paused, m.view = 61.0, False, "list"
    cmds.clear()
    took = m.media_home()
    frames = FB.frames
    m.dirty = True
    m.flush()
    check(f"HOME on a video: its menu over it, the video paused under it ({m.view}, {m.media_menu_items()}, {cmds})",
          took and m.view == "mediamenu" and m.paused and cmds == ["pause"] and FB.frames > frames
          and m.media_menu_items() == [("back", "Back to the video"), ("send", "Play on another Pietato")]
          and not m.proc_owns_screen() and m.media_where() == "1:01")
    cmds.clear()
    m.press("b")
    check(f"...B: back to the video, playing again ({m.view}, {cmds}, paused: {m.paused})",
          m.view == "list" and not m.paused and cmds == ["pause"] and m.proc_owns_screen())
    m.media_home()
    m.press("down")
    m.press("right")                                   # (◀▶: the one it goes to: the TV, the only other one here)
    m.press("a")
    played = tv_said("play", n)
    check(f"...Play on another Pietato, A: it carries on on the TV from where it was ({played and played['args'][-2:]})",
          played is not None and played["kind"] == "video" and played["args"][-2:] == ["-ss", "58"]
          and m.proc is None and m.view == "list" and toasts[-1:] == ["Playing on tv now"])
    m.play([{"kind": "video", "src": VIDEO, "title": "Holiday", "key": VIDEO}], 0, start=0)
    m.pos, m.view = 10.0, "list"
    m.cmd("pause")
    m.paused = True                                    # (paused before HOME: paused after)
    cmds.clear()
    m.media_home()
    m.media_home()                                     # (HOME again: back to it, as the app's HOME does)
    check(f"...paused already: HOME and HOME again, still paused, its picture put back ({cmds}, {m.paused})",
          m.view == "list" and m.paused and cmds == ["pausing_keep_force osd_show_progression"])
    m.stop()
    n = tv_lines()
    m.play([{"kind": "radio", "src": "https://stream.example.com/jazz", "title": "Jazz FM"}], 0)
    m.view, m.paused = "now", False
    cmds.clear()
    took = m.media_home()
    m.dirty = True
    m.flush()
    check(f"HOME on Now playing (a station): its menu, the music playing on ({m.media_menu_items()[0]}, {cmds})",
          took and m.view == "mediamenu" and not m.paused and cmds == [] and m.media_menu_items()[0][1]
          == "Back to the station")
    m.press("b")
    check(f"...B: back to Now playing ({m.view})", m.view == "now" and m.proc is not None)
    m.media_home()
    m.press("down")
    loops = m.music_loops
    m.music_loops = lambda: True                       # (Random song at start-up on: stopped music comes back...)
    m.press("a")
    played = tv_said("play", n)
    m.music_back(time.monotonic())
    m.music_back(time.monotonic() + 3600)
    check(f"...A on Play on another Pietato: it plays on the TV, and stops here, for good, even with music that "
          f"comes back on ({played and played['play']}, {m.resume_later}, {m.proc})",
          played is not None and played["kind"] == "radio" and m.proc is None and m.view == "list"
          and m.resume_later is None)
    m.music_loops = loops
    m.play([{"kind": "radio", "src": "https://stream.example.com/jazz", "title": "Jazz FM"}], 0)
    m.view = "now"
    heard = dict(m.pie.heard)
    m.pie.heard.clear()                                # (no other Pietato on: HOME as ever)
    check("...with no other Pietato on: HOME as ever (the terminal)", m.media_home() is False and m.view == "now")
    m.pie.heard.update(heard)
    m.stop()
    m.cmd = was_cmd

    # ---- what you're looking at: a PDF, some text, a picture ---------------------------------------------------------
    from PIL import Image as PI, ImageDraw as PD
    stub_run = subprocess.run
    subprocess.run = lambda cmd, *a, **k: (real_run(cmd, *a, **k) if isinstance(cmd, list)
                                           and cmd[:1] in (["pdfinfo"], ["pdftoppm"]) else stub_run(cmd, *a, **k))
    PDF = HOME + "/Documents/manual.pdf"
    pages = [PI.new("RGB", (612, 792), "white") for _ in range(3)]
    for k, p in enumerate(pages):
        PD.Draw(p).rectangle((50, 50 + k * 200, 300, 150 + k * 200), fill=(200, 30, 30))
    pages[0].save(PDF, "PDF", save_all=True, append_images=pages[1:], resolution=72)
    TXT = HOME + "/Documents/notes.txt"
    open(TXT, "w").write("".join(f"line {k:03d}: the quick brown fox jumps over the lazy dog\n" for k in range(400)))
    PIC1, PIC2 = HOME + "/Pictures/beach.jpg", HOME + "/Pictures/hills.jpg"
    PI.new("RGB", (320, 240), (30, 120, 200)).save(PIC1)
    PI.new("RGB", (320, 240), (40, 160, 60)).save(PIC2)

    def tv_view(view, secs=15.0):
        """The TV's screen, once it shows view (or as it is, after a while)."""
        end = time.time() + secs
        while True:
            st = tv_state()
            if st["view"] == view or time.time() > end:
                return st
            time.sleep(0.2)

    def tv_do(line):
        tv.stdin.write(line + "\n")
        tv.stdout.readline()

    def home_send():
        """HOME, then View on another Pietato, A."""
        m.file_home()
        m.dirty = True; m.flush()
        m.press("down")
        m.press("a")

    def home_keep():
        """HOME, then Send to another Pietato, A."""
        m.file_home()
        m.dirty = True; m.flush()
        m.press("down")
        m.press("down")
        m.dirty = True; m.flush()
        m.press("a")

    def until_file(path, secs=10.0):
        end = time.time() + secs
        while not os.path.isfile(path) and time.time() < end:
            time.sleep(0.1)
        return os.path.isfile(path)

    def until_kept(path, since, secs=10.0):
        """A copy sent to keep, there on the TV, and the TV done with it: it says so last ("beach.jpg from gpi, in
        Pictures"), a moment after the file's in place (what's checked next mustn't hear it)."""
        name = os.path.basename(path)
        end = time.time() + secs
        while time.time() < end:
            said = tv_said("toast", since, secs=0)
            if os.path.isfile(path) and said and str(said.get("toast", "")).startswith(name + " from "):
                return True
            time.sleep(0.1)
        return False

    heard = dict(m.pie.heard)
    m.pie.heard.clear()
    m.open_pdf(PDF)
    check(f"a PDF open, none of your other Pietatos on: HOME as ever ({m.view})", m.file_home() is False
          and m.view == "pdf")
    m.pie.heard.update(heard)
    m.pdf_goto(2)
    m.pdf_zoom(1)
    m.v["scroll"] = 300
    m.dirty = True; m.flush()
    sx = m.v["sx"]
    check(f"...one on: HOME is its menu, to view it there or send it there to keep ({m.view}, {m.file_menu_items()})",
          m.file_home() and m.view == "filemenu" and m.file_menu_items() == [
              ("back", "Back to the page"), ("send", "View on another Pietato"), ("keep", "Send to another Pietato")])
    frames = FB.frames
    m.dirty = True; m.flush()
    check(f"...drawn, saying where you are in it ({FB.frames - frames}, {m.file_where()!r}, {m.where_text()!r})",
          FB.frames > frames and m.file_where() == "Page 2 of 3" and m.where_text().endswith("manual.pdf"))
    m.press("b")
    check(f"...B: back to the page, as it was ({m.view}, page {m.v.get('page')})", m.view == "pdf" and m.v["page"] == 2
          and m.v["scroll"] == 300)
    m.file_home()
    m.file_home()
    check(f"...HOME again, the same ({m.view})", m.view == "pdf")
    toasts.clear()
    home_send()
    st = tv_view("pdf")
    sh = st["viewer"]
    check(f"View on another Pietato: on the TV, at the same page, as close, as far down and across ({sh.get('title')}, "
          f"page {sh.get('page')}, {sh.get('zoom')}, {sh.get('scroll')}, {sh.get('sx')} for {sx})",
          st["view"] == "pdf" and sh.get("title") == "manual.pdf" and sh.get("page") == 2 and sh.get("zoom") == 1.5
          and abs(sh.get("scroll", 0) - 300) <= 2 and sx > 0 and abs(sh.get("sx", 0) - sx) <= 2)
    check(f"...the very file, from here ({sh.get('path')})", sh.get("path") and open(sh["path"], "rb").read()
          == open(PDF, "rb").read())
    check(f"...and closed here, saying so ({m.view}, {toasts[-1:]})", m.view == "list" and not m.v
          and toasts[-1:] == ["Showing on tv now. HOME there sends it back"])
    tv_do("home")
    st = tv_state()
    check(f"...HOME on the TV: its menu, this one picked to send it back ({st['view']}, {st['file_menu']}, {st['to']})",
          st["view"] == "filemenu" and st["file_menu"] == ["back", "send", "keep"] and st["to"] == MINE)
    tv_do("press b")

    m.open_text(TXT)
    m.v["top"] = 150
    m.press("a")                                       # (bigger letters: the same line at the top)
    top_line = m.text_lines()[m.v["top"]]
    home_send()
    st = tv_view("text")
    sh = st["viewer"]
    check(f"some text: on the TV, its letters as big, the same line at the top ({sh.get('title')}, {sh.get('size')}, "
          f"{sh.get('first')!r})", st["view"] == "text" and sh.get("title") == "notes.txt" and sh.get("size") == 1
          and sh.get("first") == top_line and top_line.startswith("line 150"))

    m.open_photo([PIC1, PIC2], 1)
    m.press("y")                                       # (turned)
    home_send()
    st = tv_view("photo")
    sh = st["viewer"]
    got = (sh.get("items") or [""])[0]
    check(f"a picture: on the TV, turned as it was ({os.path.basename(got)}, {sh.get('rot')})", st["view"] == "photo"
          and sh.get("rot") == 1 and os.path.basename(got) == "hills.jpg" and open(got, "rb").read()
          == open(PIC2, "rb").read())
    check(f"...and here, back to the list ({m.view})", m.view == "list" and not m.v)

    # ---- Send to another Pietato: a copy for it to keep, in its own folders; it stays open here -------------------------
    toasts.clear()
    m.open_photo([PIC1, PIC2], 0)
    n = tv_lines()
    home_keep()
    kept = TV + "/Pictures/beach.jpg"
    got = until_kept(kept, n)
    check(f"Send to another Pietato, a picture: a copy kept in the TV's Pictures; here it stays open "
          f"({m.view}, {toasts[-1:]})", got and open(kept, "rb").read() == open(PIC1, "rb").read() and m.view == "photo"
          and m.v["items"][m.v["i"]] == PIC1 and toasts[-1:] == ["Sending it to tv, for its Pictures"])
    st = tv_state()
    shown = os.path.basename((st["viewer"].get("items") or [""])[0])
    check(f"...the TV's screen left as it was (still {shown})", st["view"] == "photo" and shown == "hills.jpg")
    n = tv_lines()
    home_keep()
    check("...sent again: kept again, beside it, a number on its name", until_kept(TV + "/Pictures/beach-2.jpg", n)
          and open(TV + "/Pictures/beach-2.jpg", "rb").read() == open(PIC1, "rb").read())
    m.close_viewer()

    # ---- HOME on a picture picked in your Photos: the same menu, for it -----------------------------------------------
    pt = m.tab_index("photos")
    was_pdirs = g.LIBRARY[pt]["dirs"]
    g.LIBRARY[pt]["dirs"] = [HOME + "/Pictures"]       # (this test's home folder's, not /home/*'s)
    m.tab, m.view = pt, "list"
    m.load_tab(pt)
    srcs = [r["src"] for r in m.items[pt]]
    m.sels[pt] = srcs.index(PIC1)
    took = m.file_home()
    m.dirty = True
    m.flush()
    check(f"HOME on a picture picked in your Photos: its menu, for it ({m.file_menu_items()}, {m.file_where()})",
          took and m.view == "filemenu" and m.file_title() == "beach.jpg"
          and m.file_where() == f"Picture {srcs.index(PIC1) + 1} of {len(srcs)}"
          and m.file_menu_items() == [("back", "Back to the pictures"), ("send", "View on another Pietato"),
                                      ("keep", "Send to another Pietato")])
    m.press("b")
    check("...B: back to the pictures, it still picked", m.view == "list" and m.tab == pt
          and m.items[pt][m.sels[pt]]["src"] == PIC1)
    toasts.clear()
    home_send()
    end = time.time() + 15
    while True:
        st = tv_state()
        shown = os.path.basename((st["viewer"].get("items") or [""])[0])
        if (st["view"] == "photo" and shown == "beach.jpg") or time.time() > end:
            break
        time.sleep(0.2)
    check(f"...View on another Pietato, A: on the TV ({shown}); here, the pictures, it still picked ({toasts[-1:]})",
          st["view"] == "photo" and shown == "beach.jpg" and m.view == "list" and m.tab == pt
          and m.items[pt][m.sels[pt]]["src"] == PIC1 and toasts[-1:] == ["Showing on tv now. HOME there sends it back"])
    m.sels[pt] = srcs.index(PIC2)
    n = tv_lines()
    home_keep()
    check(f"...Send to another Pietato, A: a copy kept in the TV's Pictures; here, the pictures ({toasts[-1:]})",
          until_kept(TV + "/Pictures/hills.jpg", n) and open(TV + "/Pictures/hills.jpg", "rb").read()
          == open(PIC2, "rb").read() and m.view == "list" and toasts[-1:] == ["Sending it to tv, for its Pictures"])
    heard = dict(m.pie.heard)
    m.pie.heard.clear()
    check("...with no other Pietato on: HOME as ever (the terminal)", m.file_home() is False and m.view == "list")
    m.pie.heard.update(heard)
    g.LIBRARY[pt]["dirs"] = was_pdirs
    m.close_viewer()
    m.open_pdf(PDF)
    n = tv_lines()
    home_keep()
    check("a PDF: kept in the TV's Documents, the very file", until_kept(TV + "/Documents/manual.pdf", n)
          and open(TV + "/Documents/manual.pdf", "rb").read() == open(PDF, "rb").read() and m.view == "pdf")
    m.close_viewer()
    DOC = HOME + "/Documents/plan.md"
    open(DOC, "w").write("# The plan\n\n- one\n- two\n")
    m.open_text(DOC)
    n = tv_lines()
    home_keep()
    check("some text from a file: the file itself kept, by its own name", until_kept(TV + "/Documents/plan.md", n)
          and open(TV + "/Documents/plan.md").read() == open(DOC).read())
    m.close_viewer()

    # ---- a song of yours: Send to another Pietato on Now playing too, a copy for its Music; it plays on here --------
    SONG = HOME + "/Music/Lazy Afternoon.mp3"
    open(SONG, "wb").write(b"ID3\x04\x00" + bytes(range(256)) * 40)
    m.play([{"kind": "audio", "src": SONG, "title": "Lazy Afternoon", "key": SONG}], 0)
    m.view, m.paused = "now", False
    m.media_home()
    check(f"HOME on Now playing, a song of yours: Send to another Pietato too ({m.media_menu_items()})",
          m.view == "mediamenu" and m.media_menu_items() == [("back", "Back to the music"),
                                                             ("send", "Play on another Pietato"),
                                                             ("keep", "Send to another Pietato")])
    m.dirty = True
    m.flush()
    toasts.clear()
    n = tv_lines()
    m.press("down")
    m.press("down")
    m.press("a")
    got = until_kept(TV + "/Music/Lazy Afternoon.mp3", n)
    check(f"...A: a copy kept in the TV's Music, by its own name; here it plays on, on Now playing ({m.view}, "
          f"{toasts[-1:]})", got and open(TV + "/Music/Lazy Afternoon.mp3", "rb").read() == open(SONG, "rb").read()
          and m.view == "now" and m.proc is not None and m.cur.get("src") == SONG
          and toasts[-1:] == ["Sending it to tv, for its Music"])
    m.play([{"kind": "radio", "src": "https://stream.example.com/jazz", "title": "Jazz FM"}], 0)
    m.view = "now"
    m.media_home()
    check(f"...a station: no Send (nobody's file to keep: Play on another Pietato only) ({len(m.media_menu_items())})",
          [j for j, _ in m.media_menu_items()] == ["back", "send"])
    m.press("b")
    m.stop()
    mi = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Music")
    was_dirs = g.LIBRARY[mi]["dirs"]
    g.LIBRARY[mi]["dirs"] = [HOME + "/Music"]          # (this test's home folder's, not /home/*'s)
    open(HOME + "/Music/A Song.mp3", "wb").write(b"ID3")
    open(HOME + "/Music/Zebra Song.mp3", "wb").write(b"ID3")
    m.tab, m.view = mi, "list"
    m.load_tab(mi)
    rows = [r["src"] for r in m.items[mi]]
    m.sels[mi] = rows.index(HOME + "/Music/Zebra Song.mp3")
    open(HOME + "/Music/Beach Song.mp3", "wb").write(b"ID3")   # (one come from another of yours, as on the TV's)
    m.kept_shown(HOME + "/Music/Beach Song.mp3", "Music", "tv")
    rows = [r["src"] for r in m.items[mi]]
    check(f"...and on the one it went to, its Music list, if it's on the screen: the song in it now, the row you were "
          f"on still picked ({os.path.basename(rows[m.sels[mi]])}, {toasts[-1:]})",
          HOME + "/Music/Beach Song.mp3" in rows and rows[m.sels[mi]] == HOME + "/Music/Zebra Song.mp3"
          and toasts[-1:] == ["Beach Song.mp3 from tv, in Music"])

    # ---- HOME on a song picked in your Music list: the same menu, for that song ---------------------------------------
    ZEBRA = HOME + "/Music/Zebra Song.mp3"
    took = m.media_home()
    m.dirty = True
    m.flush()
    check(f"HOME on a song picked in your Music list: its menu, for that song ({m.media_menu_items()})",
          took and m.view == "mediamenu" and m.media_menu["row"]["src"] == ZEBRA
          and m.media_menu_items() == [("back", "Back to the list"), ("send", "Play on another Pietato"),
                                       ("keep", "Send to another Pietato")])
    m.press("b")
    check("...B: back to the list, the song still picked", m.view == "list" and m.tab == mi
          and m.items[mi][m.sels[mi]]["src"] == ZEBRA)
    n = tv_lines()
    toasts.clear()
    m.media_home()
    m.press("down")
    m.press("a")
    played = tv_said("play", n)
    check(f"...Play on another Pietato, A: it plays on the TV, from its start; here, the list as it was "
          f"({played and played['kind']}, {toasts[-1:]})",
          played is not None and played["kind"] == "audio" and "/api/handoff/file?token=" in played["play"]
          and "-ss" not in played["args"] and m.view == "list" and m.proc is None
          and toasts[-1:] == ["Playing on tv now"])
    n = tv_lines()
    m.media_home()
    m.press("down")
    m.press("down")
    m.press("a")
    check(f"...Send to another Pietato, A: a copy kept in the TV's Music ({toasts[-1:]})",
          until_kept(TV + "/Music/Zebra Song.mp3", n) and open(TV + "/Music/Zebra Song.mp3", "rb").read() == b"ID3"
          and m.view == "list")
    m.play([{"kind": "audio", "src": ZEBRA, "title": "Zebra Song", "key": ZEBRA}], 0)
    m.view, m.pos = "list", 12.0
    n = tv_lines()
    m.media_home()
    m.press("down")
    m.press("a")
    played = tv_said("play", n)
    check(f"...the song playing here, picked: it carries on there from where it is, and stops here "
          f"({played and played['args'][-2:]}, {m.proc})", played is not None and played["kind"] == "audio"
          and m.proc is None and m.view == "list")
    heard = dict(m.pie.heard)
    m.pie.heard.clear()
    check("...with no other Pietato on: HOME as ever (the terminal)", m.media_home() is False and m.view == "list")
    m.pie.heard.update(heard)
    g.LIBRARY[mi]["dirs"] = was_dirs
    check("...a song sent just to be shown: not taken (it goes only to be kept)",
          m.handoff_take_file({"view": "music", "title": "x.mp3", "size": 3, "file": "a" * 32}, "http://10.0.0.9",
                              "tv") == {"ok": False, "error": "What's that?"})
    m.view = "list"

    SECRET = HOME + "/Documents/webui.txt"
    open(SECRET, "w").write("password = not-for-the-tv\n")
    n = tv_lines()
    toasts.clear()
    m.open_text(SECRET)
    home_send()
    check(f"a password's file: it stays here ({toasts[-1:]}, {m.view})", toasts[-1:] == ["That one stays on this Pi"]
          and m.view == "filemenu")
    check("...nothing said to the TV", tv_said("toast", n, secs=1.0) is None)
    m.press("b")
    m.close_viewer()

    import http.server

    class Older(http.server.BaseHTTPRequestHandler):
        """Another of yours, not updated yet: it doesn't know what it's asked."""
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            data = json.dumps({"ok": False, "error": "What's that?"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    older = http.server.HTTPServer(("127.0.0.1", 0), Older)
    threading.Thread(target=older.serve_forever, daemon=True).start()
    OLDER = f"http://127.0.0.1:{older.server_address[1]}"
    m.pie.heard[OLDER] = {"host": "attic", "seen": time.time() + 3600, "peer": True}
    m.handoff_to = OLDER
    toasts.clear()
    m.open_photo([PIC1], 0)
    home_send()
    check(f"one not updated yet: said so, and it stays here ({toasts[-1:]}, {m.view})",
          toasts[-1:] == ["attic needs updating first (System > Update software there)"] and m.view == "filemenu")
    m.press("b")
    toasts.clear()
    home_keep()
    check(f"...nor sent to keep ({toasts[-1:]})", toasts[-1:] == ["attic needs updating first (System > Update software "
                                                                  "there)"] and m.view == "filemenu")
    m.press("b")
    m.close_viewer()

    def keep_song():
        m.play([{"kind": "audio", "src": SONG, "title": "Lazy Afternoon", "key": SONG}], 0)
        m.view = "now"
        toasts.clear()
        m.media_home()
        m.press("down")
        m.press("down")
        m.press("a")

    keep_song()
    check(f"...nor a song to keep: said so, and it plays on here ({toasts[-1:]}, {m.view})",
          toasts[-1:] == ["attic needs updating first (System > Update software there)"] and m.view == "now"
          and m.proc is not None)
    m.stop()
    del m.pie.heard[OLDER]
    older.shutdown()

    class Before(Older):
        """One from before songs went to be kept (it keeps pictures and documents): it answers, but not knowing what
        a song to keep is."""
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            data = json.dumps({"ok": False, "error": "What's that?"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    before = http.server.HTTPServer(("127.0.0.1", 0), Before)
    threading.Thread(target=before.serve_forever, daemon=True).start()
    BEFORE = f"http://127.0.0.1:{before.server_address[1]}"
    m.pie.heard[BEFORE] = {"host": "den", "seen": time.time() + 3600, "peer": True}
    m.handoff_to = BEFORE
    keep_song()
    check(f"...one that keeps pictures but not songs yet: needs updating too ({toasts[-1:]})",
          toasts[-1:] == ["den needs updating first (System > Update software there)"] and m.proc is not None)
    m.stop()
    del m.pie.heard[BEFORE]
    before.shutdown()
    m.handoff_to = THEIRS

    LOCKED = S + "/locked"
    os.makedirs(LOCKED)
    os.chmod(LOCKED, 0o700)
    shutil.copy(PDF, LOCKED + "/inside.pdf")
    m.open_pdf(LOCKED + "/inside.pdf")
    got = m.file_what()
    check(f"one the web page couldn't read (shut away, outside your home folder): a copy goes "
          f"({got[0] if isinstance(got, tuple) else got})", isinstance(got, tuple)
          and got[0].startswith(g.CACHE_DIR + "/handoff-out/") and got[0].endswith(".pdf")
          and open(got[0], "rb").read() == open(PDF, "rb").read() and os.stat(got[0]).st_mode & 0o004)
    m.close_viewer()
    out = m.web_peer_handoff({"kind": "file", "from": "127.0.0.1", "view": "photo", "title": "x.jpg", "size": 3,
                              "file": "../../etc/passwd"})
    out2 = m.web_peer_handoff({"kind": "file", "from": "127.0.0.1", "view": "photo", "title": "../x.jpg", "size": 3,
                               "check": True})
    check(f"...a key that isn't one, a name that's a path: not taken ({out}, {out2})", out == out2
          == {"ok": False, "error": "What's that?"})
    subprocess.run = stub_run

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
