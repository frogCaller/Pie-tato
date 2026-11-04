"""Game saves that follow you from Pi to Pi (savesync.py, Settings > Share with other Pietatos): a game started here
takes its saves from whichever of your other Pietatos played it last, if that was later than here; all of them from
that one, and only the ones that aren't the same here; what they replace kept in Saves/.replaced; their age kept (two
Pis' clocks needn't agree); whose they are, the Games folder's owner's. Not from one that's playing it now, one with
sharing off, or one that answers nonsense; a save that doesn't come whole changes nothing. A game played here tells the
others when it's done, and one told takes the saves from the one that told it (only one of yours). And the web page's
part: a game's saves listed and handed out to your network only, without the page's password, never anything but a
game's own saves, nothing while sharing's off or the game's being played; the news passed on with who sent it. Then
for real: two Pietatos, one's web page on a port of its own, the other starting a game and carrying on from it."""
import io, json, os, pwd, shutil, sys, threading, time, urllib.parse, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import savesync as SS

S = SP + "/t_save_sync"
shutil.rmtree(S, ignore_errors=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def put(folder, name, data, ago):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    open(path, "wb").write(data)
    t = time.time() - ago
    os.utime(path, (t, t))
    return path


GAME = "Pokemon - Emerald Version (USA)"
HERE = S + "/here/Saves"
OTHERS = {"http://192.168.1.21:5432": S + "/pi4/Saves", "http://192.168.1.22:5432": S + "/tv/Saves",
          "http://192.168.1.23:5432": S + "/den/Saves"}
NAMES = {"http://192.168.1.21:5432": "pi4", "http://192.168.1.22:5432": "tv", "http://192.168.1.23:5432": "den"}
state = {"off": set(), "playing": set(), "nonsense": set(), "broken": set(), "asked": [], "fetched": []}


def fake_ask(url):
    base, _, q = url.partition("/api/saves?game=")
    state["asked"].append(base)
    if base in state["nonsense"]:
        return {"on": True, "files": {".srm": {"size": -1, "age": "old", "sum": "x"}, "../x": {}}}
    if base in state["off"]:
        return {"ok": True, "on": False}
    name = urllib.parse.unquote(q)
    return {"ok": True, "on": True, "playing": base in state["playing"],
            "files": SS.save_files(OTHERS[base], name)}


def fake_fetch(url, dest, size):
    base, _, q = url.partition("/api/saves/file?")
    a = dict(urllib.parse.parse_qsl(q))
    state["fetched"].append((base, a["ext"]))
    data = open(os.path.join(OTHERS[base], a["game"] + a["ext"]), "rb").read()
    if base in state["broken"] and a["ext"] == ".state.auto":
        data = data[:-1] + b"?"                     # (cut short on its way, as it were: the sum says so)
    open(dest, "wb").write(data)
    return len(data) == size


PEERS = [(u, NAMES[u]) for u in OTHERS]


def pull(peers=PEERS, **kw):
    state["asked"], state["fetched"] = [], []
    return SS.pull(HERE, GAME, peers, ask=fake_ask, fetch=fake_fetch, **kw)


def here(ext):
    try:
        return open(os.path.join(HERE, GAME + ext), "rb").read()
    except OSError:
        return None


def age(ext, folder=HERE):
    return time.time() - os.stat(os.path.join(folder, GAME + ext)).st_mtime


# ---- names --------------------------------------------------------------------------------------------------
check("a game's name for its saves: a plain file name only",
      SS.game_name(GAME) == GAME and not any(SS.game_name(n) for n in
      ("", "../x", "a/b", ".hidden", " spaced", "a\0b", "x" * 201, 7, None, ".", "..")))

# ---- here: an older save; the TV Pi played it since, the den longer ago, the Pi 4 never --------------------------
put(HERE, GAME + ".srm", b"here srm", 5000)
put(HERE, GAME + ".state.auto", b"here state", 5000)
put(HERE, GAME + ".state", b"here slot", 5000)                      # (a save state of yours: the TV hasn't one)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".srm", b"tv srm", 300)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".state.auto", b"tv state", 300)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".rtc", b"tv clock", 300)
put(OTHERS["http://192.168.1.23:5432"], GAME + ".srm", b"den srm", 2000)
os.makedirs(OTHERS["http://192.168.1.21:5432"], exist_ok=True)
put(OTHERS["http://192.168.1.22:5432"], "Other Game (USA).srm", b"another game", 10)

came = pull()
check(f"the newest of them, the TV's: from it ({came})", came == "tv")
check(f"...all of its saves of the game that aren't the same here, and nothing of another game "
      f"({sorted(e for _, e in state['fetched'])})",
      sorted(e for _, e in state["fetched"]) == [".rtc", ".srm", ".state.auto"]
      and {b for b, _ in state["fetched"]} == {"http://192.168.1.22:5432"})
check("...here now", here(".srm") == b"tv srm" and here(".state.auto") == b"tv state" and here(".rtc") == b"tv clock")
check("...a save state of yours it hasn't got: left as it is", here(".state") == b"here slot")
check(f"...as old as they are there (not just made: {age('.srm'):.0f} s)", 290 < age(".srm") < 320)
kept = S + "/here/Saves/.replaced"
check(f"...what they replaced: kept ({sorted(os.listdir(kept))})",
      sorted(os.listdir(kept)) == [GAME + ".srm", GAME + ".state.auto"]
      and open(f"{kept}/{GAME}.srm", "rb").read() == b"here srm")
check("...and nothing left over on the way", not [f for f in os.listdir(HERE) if f.endswith(".part")])
check(f"asked them all at once, each once ({sorted(state['asked'])})", sorted(state["asked"]) == sorted(OTHERS))

came = pull()
check(f"again: the same now, so nothing comes ({came}, {state['fetched']})", came is None and state["fetched"] == [])

# played here since: here's newest
put(HERE, GAME + ".srm", b"played here", 1)
check(f"played here since: nothing comes ({pull()})", pull() is None and state["fetched"] == [])

# a moment's difference isn't newer (a save being written, a slow answer)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".srm", b"tv a moment later", 0)
check(f"newer by less than a moment: not taken ({pull()})", pull() is None)

# the TV playing it now; sharing off on the den; one answering nonsense
for ext in SS.SAVE_EXTS:                              # (all of here's saves of it old again)
    if os.path.exists(os.path.join(HERE, GAME + ext)):
        put(HERE, GAME + ext, b"old again", 9000)
state["playing"].add("http://192.168.1.22:5432")
came = pull()
check(f"the TV playing it now (its save still changing): from the next newest instead, the den ({came})",
      came == "den" and here(".srm") == b"den srm")
check("...where you left off here (from before the den's save, and the den hasn't one): put aside with it",
      here(".state.auto") is None and open(f"{kept}/{GAME}.state.auto", "rb").read() == b"old again"
      and here(".state") == b"old again")
for ext in SS.SAVE_EXTS:
    if os.path.exists(os.path.join(HERE, GAME + ext)):
        put(HERE, GAME + ext, b"old again", 9000)
state["off"].add("http://192.168.1.23:5432")
check(f"...and the den's sharing off: from none ({pull()})", pull() is None)
state["playing"].clear(); state["off"].clear()
state["nonsense"].add("http://192.168.1.21:5432")
came = pull()
check(f"one answering nonsense: let be, the others still asked ({came})", came == "tv")
state["nonsense"].clear()

# a save that doesn't come whole: nothing changes
put(HERE, GAME + ".srm", b"old again", 9000)
put(HERE, GAME + ".state.auto", b"old again", 9000)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".srm", b"tv srm 2", 100)
put(OTHERS["http://192.168.1.22:5432"], GAME + ".state.auto", b"tv state 2", 100)
state["broken"].add("http://192.168.1.22:5432")
came = pull()
check(f"one of them doesn't come whole: none taken, here as it was ({came}, {here('.srm')!r})",
      came is None and here(".srm") == b"old again" and here(".state.auto") == b"old again"
      and not [f for f in os.listdir(HERE) if f.endswith(".part")])
state["broken"].clear()

# whose they are: the Games folder's owner's
try:
    owner = pwd.getpwnam("gpitest")
    came = pull(owner=(owner.pw_uid, owner.pw_gid))
    st = os.stat(os.path.join(HERE, GAME + ".srm"))
    check(f"taken as the Games folder's owner's ({came}, {st.st_uid})", came == "tv" and st.st_uid == owner.pw_uid
          and os.stat(kept).st_uid == owner.pw_uid)
except KeyError:
    print("(no gpitest user here: whose they are, not looked at)")

# telling the others
told = []
n = SS.tell(GAME, PEERS, post=lambda url, body: told.append((url, body)))
check(f"a game played here: the others told ({n})", n == 3 and told[0] == ("http://192.168.1.21:5432/api/saves/news",
                                                                           {"game": GAME}))
check("...never for a name that isn't one", SS.tell("../x", PEERS, post=lambda u, b: told.append(u)) == 0)

# ---- the web page's part ------------------------------------------------------------------------------------------
H = S + "/webhome"
os.makedirs(H + "/Games/Saves")
os.environ["HOME"] = H
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
webui.HOME = H
webui.STATIC = H + "/pietato/static"
os.makedirs(webui.STATIC + "/fonts")
web_saves = H + "/Games/Saves"
put(web_saves, GAME + ".srm", b"web srm", 60)
put(web_saves, GAME + ".state.auto", b"web state", 60)
put(web_saves, "secret.txt", b"not a save", 60)
media = {"share": "On", "playing": None, "news": []}


def fake_pi(method, path, body=None, timeout=10, ctype="application/json", keep=()):
    u = urllib.parse.urlsplit(path)
    if method == "GET" and u.path == "/saves":
        name = SS.game_name(dict(urllib.parse.parse_qsl(u.query)).get("game"))
        if name is None:
            out = {"ok": False, "error": "Which game?"}
        elif media["share"] == "Off":
            out = {"ok": True, "on": False}
        else:
            out = {"ok": True, "on": True, "playing": media["playing"] == name,
                   "files": SS.save_files(web_saves, name), "folder": web_saves}
        return 200, json.dumps(out).encode(), "application/json"
    if method == "POST" and u.path == "/savenews":
        media["news"].append(body)
        return 200, b'{"ok": true}', "application/json"
    return 404, b"{}", "application/json"


webui.ask_pi = fake_pi
c = webui.app.test_client()
NET = {"base_url": "http://192.168.1.30:5432", "environ_base": {"REMOTE_ADDR": "192.168.1.21"}}
FAR = {"base_url": "http://192.168.1.30:5432", "environ_base": {"REMOTE_ADDR": "8.8.8.8"}}
open(webui.STATIC + "/webui.txt", "w").write("password = hunter2\n")   # (the page has a password: not for these)
r = c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET)
got = r.get_json()
check(f"a game's saves, to your network, without the page's password: their sizes, ages and sums ({r.status_code})",
      r.status_code == 200 and got["on"] and sorted(got["files"]) == [".srm", ".state.auto"]
      and got["files"][".srm"]["size"] == 7 and 50 < got["files"][".srm"]["age"] < 90)
check("...and not where they are on the Pi", "folder" not in got)
r = c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET)
check(f"...one of them handed out ({r.status_code})", r.status_code == 200 and r.data == b"web srm")
check("...not to anywhere else", c.get("/api/saves?game=x", **FAR).status_code == 403
      and c.get("/api/saves/file?game=x&ext=.srm", **FAR).status_code == 403)
check("...never anything but a game's own saves",
      all(c.get("/api/saves/file?" + urllib.parse.urlencode(q), **NET).status_code == 404 for q in
          ({"game": "secret", "ext": ".txt"}, {"game": GAME, "ext": ".bak"}, {"game": "../" + GAME, "ext": ".srm"},
           {"game": GAME + "/..", "ext": ".srm"}, {"game": GAME, "ext": ""}, {"game": "missing", "ext": ".srm"})))
media["playing"] = GAME
check("...nor while the game's being played here", c.get(
    "/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET).status_code == 404
      and c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET).get_json()["playing"] is True)
media["playing"], media["share"] = None, "Off"
check("...nor with sharing off", c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET).get_json() == {"ok": True, "on": False}
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET).status_code == 404)
media["share"] = "On"
r = c.post("/api/saves/news", json={"game": GAME}, **NET)
check(f"news of a game played: passed on, with who sent it ({media['news']})",
      r.status_code == 200 and media["news"] == [{"game": GAME, "from": "192.168.1.21"}])
check("...not from anywhere else, not without a game", c.post("/api/saves/news", json={"game": GAME}, **FAR).status_code == 403
      and c.post("/api/saves/news", json={"x": 1}, **NET).status_code == 400 and len(media["news"]) == 1)
check("the rest of the page: still the password's", c.get("/api/info", **NET).status_code == 401)
os.remove(webui.STATIC + "/webui.txt")

# ---- for real: the other Pietato's web page on a port of its own, and this one's media mode -----------------------
from werkzeug.serving import make_server  # noqa: E402
srv = make_server("127.0.0.1", 0, webui.app, threaded=True)
port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
OTHER = f"http://127.0.0.1:{port}"

HOME = S + "/home/u"
os.makedirs(HOME + "/Games/Saves")
open(HOME + "/Games/" + GAME + ".gba", "wb").write(b"\0" * 64)
put(HOME + "/Games/Saves", GAME + ".srm", b"this pi's old save", 7000)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: None
g.built_for_other_pi = lambda core: False
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0})()
started = []
g.GameRun.start = lambda self, core, **kw: started.append(self.game["path"])
g.GameRun.quit = lambda self, timeout=0: None


class FB:
    w, h = 640, 480
    frames = 0

    def show(self, img):
        FB.frames += 1

    def show_part(self, img, box):
        FB.frames += 1

    def invalidate(self):
        pass

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
curtains = []
was_curtain = m.render_curtain
m.render_curtain = lambda title, status, hints=None: (curtains.append(status), was_curtain(title, status, hints))[1]
m.pie.heard[OTHER] = {"host": "tv", "seen": time.time(), "peer": True}
put(web_saves, GAME + ".srm", b"the tv's save", 120)
put(web_saves, GAME + ".state.auto", b"where you were on the tv", 120)
m.game_open({"src": HOME + "/Games/" + GAME + ".gba", "title": "Pokemon Emerald", "system": "gba"})
mine = HOME + "/Games/Saves/" + GAME
check(f"a game started: its saves from the TV first, then it starts ({curtains}, {started})",
      started == [HOME + "/Games/" + GAME + ".gba"] and curtains[:3] == ["Starting…", "Getting your save from tv…",
                                                                        "Carrying on from tv"])
check("...its in-game save and where you were, here", open(mine + ".srm", "rb").read() == b"the tv's save"
      and open(mine + ".state.auto", "rb").read() == b"where you were on the tv")
check(f"...while it's played here, the others are told so ({m.web_saves(GAME).get('playing')})",
      m.web_saves(GAME).get("playing") is True)
media["news"] = []
m.game_end()
for _ in range(50):
    if media["news"]:
        break
    time.sleep(0.1)
check(f"played and done: the TV told ({media['news']})", media["news"] == [{"game": GAME, "from": "127.0.0.1"}])

# played on the TV again: it says so, and this one takes its saves
put(web_saves, GAME + ".srm", b"the tv's newest", 5)
out = m.web_saves_news({"game": GAME, "from": "127.0.0.1"})
for _ in range(50):
    if open(mine + ".srm", "rb").read() == b"the tv's newest":
        break
    time.sleep(0.1)
check(f"news from the TV: its newest save taken ({out}, {open(mine + '.srm', 'rb').read()!r})",
      out == {"ok": True} and open(mine + ".srm", "rb").read() == b"the tv's newest")
out = m.web_saves_news({"game": GAME, "from": "192.168.1.99"})
check(f"...news from one that isn't one of yours: not taken ({out})", out.get("ok") is False)
m.setting = (lambda real: lambda key: "Off" if key == "share" else real(key))(m.setting)
check("sharing off: nobody asked, nobody told", m.saves_peers() == [] and m.web_saves(GAME) == {"ok": True, "on": False})
srv.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
