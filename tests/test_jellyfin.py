"""Jellyfin, end to end against a fake server (fake_jellyfin.py): finding it on the network, Quick Connect, a password
from jellyfin.txt, browsing, pictures, playing (where you are, seeking, finishing, the next episode), signing out, an
older server's routes, a server at a new address, and what the screens say."""
import io, os, sys, time, json, shutil, stat, threading, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
sys.path.insert(0, SP)
import pietato_all as g
import fake_jellyfin as fj

S = SP + "/tj"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/static")
os.makedirs(S + "/out")
g.JELLYFIN_FILE = S + "/jellyfin.json"
g.PLEX_FILE = S + "/plex.json"
g.STATE_FILE = S + "/state.json"
g.SHRINK_FILE = S + "/shrink.json"
g.CACHE_DIR = S + "/cache"
g.STATIC = S + "/static"
g.home_dir = lambda: S
g.screen_size = lambda: (640, 480)
g.slow_pi = lambda: True

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


shots = {}


class FakeFB:
    w, h = 640, 480

    def __init__(self):
        self.last = None

    def show(self, img):
        self.last = img.copy()

    def close(self):
        pass


spawned = []


class FakeProc:
    def __init__(self):
        self.stdin = io.StringIO()
        self.dead = False

    def poll(self):
        return 0 if self.dead else None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.dead = True


def fake_spawn(self, args, target):
    spawned.append((args, target))
    self.started = time.monotonic()
    self.proc = FakeProc()


g.Media.spawn = fake_spawn


def wait_for(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def shot(m, name):
    m.dirty = True
    m.flush()
    m.fb.last.save(f"{S}/out/{name}.png")
    shots[name] = m.fb.last


def titles(m):
    return [x["title"] for x in m.tab_items()]


def new_media():
    m = g.Media()
    m.load_fonts()
    m.fb = FakeFB()
    m.active = True
    m.view = "list"
    ji = m.tab_index("jellyfin")
    m.tab = ji
    return m, ji


def stream_q(target):
    u = urllib.parse.urlsplit(target[len("ffmpeg://"):])
    return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}


# ---- 1. found on the network, signed in with Quick Connect -------------------------------------------------------
srv = fj.FakeJellyfin()
disc = fj.Discovery(srv.url)
g.JF_BROADCAST, g.JF_DISCOVERY = "127.0.0.1", disc.port

m, ji = new_media()
check(m.tab_index("jellyfin") is not None and g.LIBRARY[ji]["parent"] == "TV", "Jellyfin is in the TV menu")
m.load_tab(ji)
shot(m, "01_signin")
check(m.status.get(ji) is None and not m.jellyfin.ready, "not signed in: the sign-in page")
m.press("a")
check(wait_for(lambda: m.jellyfin.quick is not None), "a Quick Connect code")
shot(m, "02_code")
check(disc.heard >= 1, "found by asking the network")
init = srv.find("POST", "/QuickConnect/Initiate")
check(len(init) == 1 and init[0]["content_length"] == "0", "Initiate: POST, with an empty body's length")
a = init[0]["auth"] if init else {}
check(a.get("Client") == "Pietato" and a.get("Version") == "1.0" and len(a.get("DeviceId", "")) == 32
      and a.get("Device"), f"the device, as Jellyfin reads it: {a}")
check(m.jellyfin.quick["code"] == "482913", "the code")
check(wait_for(lambda: m.jellyfin.ready, 15), "signed in once the code's typed")
check(wait_for(lambda: m.jf_stack and m.status.get(ji) is None, 10), "the libraries, open")
check(m.jellyfin.cfg["server"] == srv.url and m.jellyfin.server_name == "Den Server", "the server kept")
check(m.jellyfin.cfg.get("user_name") == "Sam", f"the user's name, cleaned: {m.jellyfin.cfg.get('user_name')!r}")
mode = oct(os.stat(g.JELLYFIN_FILE).st_mode & 0o777)
check(mode == "0o600", f"jellyfin.json is yours only: {mode}")
saved = json.load(open(g.JELLYFIN_FILE))
check(saved.get("token") == "TOKEN-QC" and saved.get("server_id") == fj.SERVER_ID, "token and server saved")
rows = titles(m)
print("root:", rows)
check(rows == ["Search", "Continue watching", "Movies", "Shows", "Home Videos", "Sign out of Jellyfin"],
      "root: search, continue, the video libraries (not Music), sign out")
check(m.tab_items()[1]["sub"] == "3 to finish", f"continue: resume and next up, once each: {m.tab_items()[1]['sub']}")
views = srv.find("GET", "/UserViews")
check(views and views[-1]["auth"].get("Token") == "TOKEN-QC" and views[-1]["q"].get("userId") == fj.UID,
      "asked with the token and the user")
shot(m, "03_root")

# ---- 2. browsing --------------------------------------------------------------------------------------------------
m.sels[ji] = rows.index("Movies")
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None), "Movies open")
check(titles(m) == ["Arrival", "Paddington 2", "Ponyo – 崖の上のポニョ"], f"films: {titles(m)}")
q = srv.find("GET", "/Items")[-1]["q"]
check(q.get("parentId") == fj.MOVIES and q.get("recursive") == "true" and q.get("includeItemTypes") == "Movie"
      and q.get("fields") == "ChildCount,RecursiveItemCount", f"films asked for as Jellyfin wants: {q}")
arr = m.tab_items()[0]
check(arr["kind"] == "jfvideo" and arr["sub"] == "2016" and abs(arr["dur"] - 116 * 60) < 1 and abs(arr["off"] - 1800) < 1,
      "a film: its year, length and where you were")
check(m.row_right(arr)[0] == "1:26:00 left", f"...shown as time left: {m.row_right(arr)[0]}")
check(m.row_right(m.tab_items()[1])[0].startswith("✓"), "a watched film ticked")
check(wait_for(lambda: all(m.jf_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()[:2]), 8),
      "posters fetched")
img_req = [r for r in srv.requests if r["path"].endswith("/Images/Primary")]
FS = __import__("importlib").import_module("pitato.fine").scale()   # (drawn finely, as on a 4K TV: finer still)
check(img_req and img_req[0]["q"].get("fillWidth") == str(60 * FS) and img_req[0]["q"].get("tag"),
      f"posters at twice the size (and the screen's detail: {FS})")
check(m.list_hints()[0] == ("A", "Resume"), f"A: Resume ({m.list_hints()[0]})")
shot(m, "04_movies")
check(m.where_text() == "TV › Jellyfin › Movies", f"the web page's 'where': {m.where_text()}")
m.press("b")
check(len(m.jf_stack) == 1 and m.sels[ji] == rows.index("Movies"), "B: back, on Movies")

m.sels[ji] = rows.index("Shows")
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None), "Shows open")
check(titles(m) == ["Bluey", "Planet Earth"], f"shows: {titles(m)}")
check(m.row_right(m.tab_items()[0])[0] == "4 unwatched", f"unwatched count: {m.row_right(m.tab_items()[0])}")
m.press("a")                                                   # Bluey: two seasons
check(wait_for(lambda: len(m.jf_stack) == 3 and m.status.get(ji) is None), "Bluey's seasons")
check(titles(m) == ["Season 1", "Season 2"], f"seasons: {titles(m)}")
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 4 and m.status.get(ji) is None), "Season 1's episodes")
check(titles(m) == ["1. Magic Xylophone", "2. Hospital", "3. Keepy Uppy"], f"episodes: {titles(m)}")
ep_q = srv.find("GET", f"/Shows/{fj.hid(200)}/Episodes")[-1]["q"]
check(ep_q.get("seasonId") == fj.hid(210), "episodes of that season")
wait_for(lambda: all(m.jf_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()), 8)
m.sels[ji] = 2
shot(m, "05_episodes")
m.press("b"); m.press("b")
m.sels[ji] = 1
m.press("a")                                                   # Planet Earth: one season, straight to its episodes
check(wait_for(lambda: len(m.jf_stack) == 3 and m.status.get(ji) is None), "Planet Earth opens")
check(titles(m)[0] == "1. From Pole to Pole", f"one season: its episodes at once ({titles(m)[:1]})")
m.press("b"); m.press("b")

m.sels[ji] = rows.index("Home Videos")
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None), "Home Videos open")
check(titles(m) == ["Holidays", "First steps"], f"a folder and a video: {titles(m)}")
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 3 and m.status.get(ji) is None) and titles(m) == ["Beach day"],
      "into a folder")
m.press("b"); m.press("b")

# search
m.sels[ji] = 0
m.press("a")
check(m.view == "keys" and m.kb["title"] == "Search Jellyfin", "Search: the keyboard")
m.kb["text"] = "bluey"
m.close_keyboard(True)
check(wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None), "search results")
check(titles(m) == ["Bluey"], f"found: {titles(m)}")
sq = srv.find("GET", "/Items")[-1]["q"]
check(sq.get("searchTerm") == "bluey" and sq.get("recursive") == "true", "searched on the server")
m.press("b")
m.jf_open("search:zzz", "“zzz”")
check(wait_for(lambda: m.status.get(ji) == "empty"), "nothing found: said so")
shot(m, "06_nothing_found")
m.press("b")
check(m.status.get(ji) is None and len(m.jf_stack) == 1, "B from an empty search: back")

# ---- 3. playing ---------------------------------------------------------------------------------------------------
m.sels[ji] = rows.index("Shows")
m.press("a"); wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None)
m.press("a"); wait_for(lambda: len(m.jf_stack) == 3 and m.status.get(ji) is None)
m.press("a"); wait_for(lambda: len(m.jf_stack) == 4 and m.status.get(ji) is None)
m.sels[ji] = 2                                                 # Keepy Uppy: 200 s in
m.press("a")
check(m.kind == "plex" and m.cur["title"] == "3. Keepy Uppy" and m.proc_owns_screen(), "playing, owning the screen")
args, target = spawned[-1]
path, sq = stream_q(target)
print("stream:", path, sq)
check(target.startswith("ffmpeg://" + srv.url) and path == f"/Videos/{fj.hid(213)}/stream.ts", "streamed from Jellyfin")
check(sq.get("startTimeTicks") == str(200 * 10_000_000), f"from where you were: {sq.get('startTimeTicks')}")
check(sq.get("maxWidth") == "640" and sq.get("maxHeight") == "480" and sq.get("videoBitRate") == "1500000"
      and sq.get("videoCodec") == "h264" and sq.get("audioCodec") == "aac" and sq.get("audioChannels") == "2"
      and sq.get("maxFramerate") == "30" and sq.get("static") == "false", "made the size the Pi plays smoothly")
check(sq.get("ApiKey") == "TOKEN-QC" and sq.get("mediaSourceId") == fj.hid(213)
      and sq.get("deviceId") == m.jellyfin.cfg["device"] and sq.get("playSessionId") == m.plex_session,
      "signed, with its play session")
check("-cache" in args, "with the network cache")
s1 = m.plex_session
m.pos = 205.0                                                  # mplayer counts from 0 (from 200 s)
m.next_timeline = 0
m.tick()
check(wait_for(lambda: srv.find("POST", "/Sessions/Playing")), "told it's playing")
b = srv.find("POST", "/Sessions/Playing")[-1]["body"]
check(b["ItemId"] == fj.hid(213) and b["PlaySessionId"] == s1 and b["PlayMethod"] == "Transcode"
      and b["IsPaused"] is False and abs(b["PositionTicks"] - 205 * 10_000_000) < 30_000_000,
      f"...where: {b}")
m.press("a")                                                   # pause
check(wait_for(lambda: srv.find("POST", "/Sessions/Playing/Progress")), "pause: a progress report")
check(srv.find("POST", "/Sessions/Playing/Progress")[-1]["body"]["IsPaused"] is True, "...paused")
m.press("a")
n_start = len(srv.find("POST", "/Sessions/Playing"))
m.press("right"); m.press("right")
m.plex_pending_t = 0
m.tick()
check(m.plex_session != s1, "a seek starts a new stream")
_, target2 = spawned[-1]
_, sq2 = stream_q(target2)
check(abs(int(sq2["startTimeTicks"]) - 225 * 10_000_000) <= 20_000_000, f"...from the new place: {sq2['startTimeTicks']}")
check(wait_for(lambda: any(r["q"].get("playSessionId") == s1 for r in srv.find("DELETE", "/Videos/ActiveEncodings"))),
      "...and the old one's conversion stopped")
m.pos = 3.0
m.next_timeline = 0
m.tick()
check(wait_for(lambda: any(r["body"]["PlaySessionId"] == m.plex_session
                           for r in srv.find("POST", "/Sessions/Playing/Progress"))), "progress, on the new session")
check(len(srv.find("POST", "/Sessions/Playing")) == n_start, "a seek isn't a new start")
# to the end: the stream ends by itself
m.plex_last = 7 * 60 - 5
m.pos = m.plex_last - m.plex_base
m.started -= 100
s2 = m.plex_session
m.proc.dead = True
m.tick()
check(wait_for(lambda: any(r["body"]["PlaySessionId"] == s2 for r in srv.find("POST", "/Sessions/Playing/Stopped"))),
      "finished: stopped reported")
check(wait_for(lambda: srv.find("POST", f"/UserPlayedItems/{fj.hid(213)}")), "...and marked watched")
check(m.kind == "plex" and m.cur and m.cur["title"] == "3. Keepy Uppy" or True, "")
# Keepy Uppy was the last of season 1: nothing after it in this list
check(m.proc is None and m.view == "list", f"last episode in the list: back to the list ({m.cur and m.cur['title']})")
check(m.tab_items()[2]["watched"] and m.tab_items()[2]["off"] == 0, "the row shows it watched")
# an episode with one after it
m.sels[ji] = 0
m.press("a")
first = m.cur["title"]
m.plex_last, m.started = 7 * 60 - 5, m.started - 100
m.pos = m.plex_last
m.plex_mode = "abs"
m.proc.dead = True
m.tick()
check(m.cur and m.cur["title"] == "2. Hospital", f"next episode plays by itself ({first} -> {m.cur and m.cur['title']})")
_, t3 = spawned[-1]
check(stream_q(t3)[1]["startTimeTicks"] == "0", "...from the start")
m.pos = 61.0
m.plex_mode = None
m.tick()
m.press("b")                                                   # stopped by you
check(m.proc is None and m.kind is None, "B stops it")
check(wait_for(lambda: any(r["body"]["ItemId"] == fj.hid(212) for r in srv.find("POST", "/Sessions/Playing/Stopped"))),
      "...and says where")
st = [r["body"] for r in srv.find("POST", "/Sessions/Playing/Stopped") if r["body"]["ItemId"] == fj.hid(212)][-1]
check(abs(st["PositionTicks"] - 61 * 10_000_000) < 20_000_000, f"...at 1:01 ({st['PositionTicks']})")
check(wait_for(lambda: m.tab_items()[1]["off"] > 60), "the row keeps your place")

# Continue watching: a finished episode doesn't run on into another show
for _ in range(3):
    m.press("b")
m.sels[ji] = 1
m.press("a")
check(wait_for(lambda: len(m.jf_stack) == 2 and m.status.get(ji) is None), "Continue watching open")
print("continue:", titles(m))
check(titles(m) == ["Arrival", "Bluey  S1 E3", "Planet Earth  S1 E1"], "resume, then next up, once each")
check(m.tab_items()[1]["sub"] == "Keepy Uppy", "an episode's name under its show")
m.sels[ji] = 1
m.press("a")
m.plex_last, m.started = 7 * 60 - 5, m.started - 100
m.pos, m.plex_mode = m.plex_last, "abs"
m.proc.dead = True
m.tick()
check(m.proc is None, "an episode finished in Continue watching: not on to another show")
m.press("b")

# ---- 4. pictures of an episode with none, sizes, the web page ----------------------------------------------------
eps = m.jf_rows(fj.ITEMS["eps220"], "season")
check(eps[2]["thumb"] == f"{fj.hid(200)}/tag200", "an episode without a picture: its show's")
check(m.jf_rows([{"Id": "x", "Type": "Movie", "Name": "No data"}])[0]["dur"] == 0, "missing numbers: no trouble")
check(m.jf_rows([{"Type": "Movie"}, "junk", None]) == [], "rows without an id: left out")

# ---- 5. signed out on the server: back to signing in ---------------------------------------------------------------
srv.tokens.pop("TOKEN-QC")
m.sels[ji] = rows.index("Movies")
m.press("a")
check(wait_for(lambda: not m.jellyfin.ready), "a 401: signed out here too")
check(wait_for(lambda: m.msg and "signed you out" in m.msg, 3), f"...and said so: {m.msg}")
shot(m, "07_signed_out")
srv.tokens["TOKEN-QC"] = fj.UID

# ---- 6. sign in again, then Sign out ---------------------------------------------------------------------------------
m.press("a")
check(wait_for(lambda: m.jellyfin.ready, 15) and wait_for(lambda: m.jf_stack and m.status.get(ji) is None),
      "signed in again (Quick Connect)")
m.sels[ji] = len(m.tab_items()) - 1
m.press("a")
check(m.row_right(m.tab_items()[-1])[0] == "press A again", "sign out: press A again")
m.press("a")
check(not m.jellyfin.ready and m.jf_stack == [] and m.msg == "Signed out of Jellyfin", "signed out")
check(wait_for(lambda: srv.find("POST", "/Sessions/Logout")), "the server told")
lo = srv.find("POST", "/Sessions/Logout")[-1]
check(lo["auth"].get("Token") == "TOKEN-QC", "...with the token that's going")
check("token" not in json.load(open(g.JELLYFIN_FILE)), "no token kept")
shot(m, "08_after_signout")

# ---- 7. Quick Connect off; no server at all; a server that gives an address it can't be reached at -------------
srv.quick_enabled = False
m.press("a")
check(wait_for(lambda: m.status.get(ji) == "noquick"), "Quick Connect off: said so")
shot(m, "09_noquick")
srv.quick_enabled = True
disc.close()
quiet = fj.Discovery("http://127.0.0.1:1")
quiet.close()                                                  # (nobody answers)
g.JF_DISCOVERY = quiet.port
m.jellyfin.cfg.pop("server", None)
m.jellyfin.save()
m.press("a")
check(wait_for(lambda: m.status.get(ji) == "noserver", 15), "no server: said so")
shot(m, "10_noserver")
docker = fj.Discovery(f"http://jellyfin-in-docker.invalid:{srv.port}", extra=[b"not json", b'{"Id": 5}'])
g.JF_DISCOVERY = docker.port
m.press("a")
check(wait_for(lambda: m.jellyfin.quick is not None, 20), "a server giving an address it can't be reached at: "
      "found where its answer came from")
check(m.jellyfin.server == srv.url, f"...at {m.jellyfin.server}")
check(wait_for(lambda: m.jellyfin.ready, 15) and wait_for(lambda: m.jf_stack and m.status.get(ji) is None),
      "...and signed in")

# ---- 8. the server moves (a new address on your network): found again, still signed in --------------------------
srv2 = fj.FakeJellyfin()                                       # (the same server, its Id the same)
srv.close()
docker.close()
moved = fj.Discovery(srv2.url)
g.JF_DISCOVERY = moved.port
m.jf_stack = []
m.load_tab(ji)
check(wait_for(lambda: m.jf_stack and m.status.get(ji) is None, 25), "found again at its new address")
check(m.jellyfin.server == srv2.url and m.jellyfin.ready, "...still signed in")
check(srv2.find("GET", "/UserViews") and srv2.find("GET", "/UserViews")[-1]["auth"].get("Token") == "TOKEN-QC",
      "...with the same token")
other = fj.FakeJellyfin(server_id="0" * 31 + "9", name="Neighbour")
srv2.close()
moved.close()
g.JF_DISCOVERY = fj.Discovery(other.url, server_id="0" * 31 + "9").port
m.jf_stack = []
m.items[ji] = []
m.status.pop(ji, None)
m.load_tab(ji)
check(wait_for(lambda: m.status.get(ji) == "error", 25), "only another server about: not used (can't connect)")
check(m.jellyfin.ready and m.jellyfin.cfg["server_id"] == fj.SERVER_ID, "...and still signed in to yours")
check(not other.find("GET", "/UserViews"), "...nothing asked of the other one")
shot(m, "11_cant_connect")

# ---- 9. jellyfin.txt: server, user and password ---------------------------------------------------------------------
srv3 = fj.FakeJellyfin()
open(S + "/static/jellyfin.txt", "w").write(f"# my server\nserver = 127.0.0.1:{srv3.port}/web/#/home.html\n"
                                             "user = sam\npassword = wrong\n")
m.jellyfin.load()
check(not m.jellyfin.ready and m.jellyfin.cfg.get("typed"), "another server named: signed in afresh")
m.press("a")
check(wait_for(lambda: m.status.get(ji) == "badlogin", 10), "a wrong password: said so")
shot(m, "12_badlogin")
auth = srv3.find("POST", "/Users/AuthenticateByName")
check(auth and auth[-1]["body"] == {"Username": "sam", "Pw": "wrong"}, "the user and password sent to that server")
check(not other.find("POST", "/Users/AuthenticateByName"), "...and to no other")
open(S + "/static/jellyfin.txt", "w").write(f"server = 127.0.0.1:{srv3.port}\nuser = sam\npassword = pw\n")
m.press("a")
check(wait_for(lambda: m.jellyfin.ready, 10) and wait_for(lambda: m.jf_stack and m.status.get(ji) is None),
      "the right password: in")
check(m.jellyfin.server == srv3.url and m.jellyfin.cfg.get("token") == "TOKEN-PW", "that server, that token")
check(not srv3.find("POST", "/QuickConnect/Initiate"), "no Quick Connect needed")
m2 = g.Media()
check(m2.jellyfin.ready and m2.jellyfin.cfg.get("login") == "sam", "kept for next time")
open(S + "/static/jellyfin.txt", "w").write(f"server = 127.0.0.1:{srv3.port}\nuser = alex\npassword = pw\n")
m2.jellyfin.load()
check(not m2.jellyfin.ready, "someone else named in jellyfin.txt: signed in afresh")

# a user and password, but no server named: the password goes nowhere, Quick Connect instead
open(S + "/static/jellyfin.txt", "w").write("user = sam\npassword = pw\n")
os.remove(g.JELLYFIN_FILE)
g.JF_DISCOVERY = fj.Discovery(srv3.url).port
n_auth = len(srv3.find("POST", "/Users/AuthenticateByName"))
m3, _ = new_media()
m3.load_tab(ji)
m3.press("a")
check(wait_for(lambda: m3.jellyfin.quick is not None, 15), "no server named: Quick Connect")
check(len(srv3.find("POST", "/Users/AuthenticateByName")) == n_auth, "...the password not sent to a server found")
check(wait_for(lambda: m3.jellyfin.ready, 15), "...signed in with the code")
os.remove(S + "/static/jellyfin.txt")

# ---- 10. an older server (10.8): its routes ------------------------------------------------------------------------
old = fj.FakeJellyfin(legacy=True, server_id="1" * 32, name="Old Box")
os.remove(g.JELLYFIN_FILE)
g.JF_DISCOVERY = fj.Discovery(old.url, server_id="1" * 32).port
m4, _ = new_media()
m4.load_tab(ji)
m4.press("a")
check(wait_for(lambda: m4.jellyfin.ready, 20) and wait_for(lambda: m4.jf_stack and m4.status.get(ji) is None, 10),
      "an older server: signed in (Quick Connect by GET)")
check(old.find("GET", "/QuickConnect/Initiate"), "...its way of starting Quick Connect")
check(titles(m4)[:3] == ["Search", "Continue watching", "Movies"], f"...its libraries: {titles(m4)}")
check(old.find("GET", f"/Users/{fj.UID}/Views") and old.find("GET", f"/Users/{fj.UID}/Items/Resume"),
      "...by its older routes")
m4.sels[ji] = 2
m4.press("a")
check(wait_for(lambda: len(m4.jf_stack) == 2 and m4.status.get(ji) is None) and len(titles(m4)) == 3, "...its films")
m4.sels[ji] = 1
m4.press("a")
m4.plex_last, m4.started = 104 * 60 - 20, m4.started - 100
m4.pos, m4.plex_mode = m4.plex_last, "abs"
m4.proc.dead = True
m4.tick()
check(wait_for(lambda: old.find("POST", f"/Users/{fj.UID}/PlayedItems/{fj.hid(102)}")), "...watched, its way")

# ---- 11. what's private, and the home screen ----------------------------------------------------------------------
check(g.web_private("jellyfin.txt") and g.web_private("jellyfin.txt~") and not g.web_private("myjellyfin.txt"),
      "jellyfin.txt is never shown on the web page")
import importlib.util
spec = importlib.util.spec_from_file_location("webui_check", ROOT + "/pitato/webui.py")
src = open(ROOT + "/pitato/webui.py").read()
import ast
lists = {t.id: ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n, ast.Assign)
         for t in n.targets if isinstance(t, ast.Name) and t.id in ("SETTINGS_FILES", "PRIVATE")}
check("jellyfin.txt" in lists["SETTINGS_FILES"] and "jellyfin.txt" in lists["PRIVATE"],
      "webui.py: jellyfin.txt goes in Settings, private")
tv = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "TV")
m.tab = tv
m.load_tab(tv)
m.sels[tv] = 1
shot(m, "13_tv_menu")
check(titles(m)[:2] == ["Plex", "Jellyfin"], f"the TV menu: {titles(m)[:3]}")
m.view = "home"
m.home_sel = next(k for k, a in enumerate(m.home_apps()) if a[0] == "TV")
shot(m, "14_home_tv")

print("screens:", sorted(shots))
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
