import io, os, sys, time, json, urllib.parse, shutil
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t6"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/out")
g.PLEX_FILE = S + "/plex.json"
g.STATE_FILE = S + "/state.json"
g.CACHE_DIR = S + "/cache"
g.home_dir = lambda: S

calls = []
polls = {"n": 0}


def poster(w, h, seed):
    im = Image.new("RGB", (w, h), ((seed * 70) % 255, (seed * 40) % 255, 120))
    ImageDraw.Draw(im).ellipse((w * .2, h * .3, w * .8, h * .7), fill=(240, 220, 180))
    b = io.BytesIO(); im.save(b, "JPEG"); return b.getvalue()


MOVIES = [
    {"type": "movie", "ratingKey": 101, "key": "/library/metadata/101", "title": "Blade Runner 2049",
     "year": 2017, "duration": 9840000, "viewOffset": 2400000, "thumb": "/library/metadata/101/thumb/1"},
    {"type": "movie", "ratingKey": 102, "key": "/library/metadata/102", "title": "Interstellar",
     "year": 2014, "duration": 10140000, "viewCount": 2, "thumb": "/library/metadata/102/thumb/1"},
    {"type": "movie", "ratingKey": 103, "key": "/library/metadata/103", "title": "Spirited Away",
     "year": 2001, "duration": 7500000, "thumb": "/library/metadata/103/thumb/1"},
]
SHOWS = [{"type": "show", "ratingKey": 200, "key": "/library/metadata/200/children", "title": "Planet Earth II",
          "leafCount": 6, "viewedLeafCount": 2, "thumb": "/library/metadata/200/thumb/1"}]
SEASONS = [{"type": "season", "ratingKey": 210, "key": "/library/metadata/210/children", "title": "Season 1",
            "leafCount": 6, "viewedLeafCount": 2, "thumb": "/library/metadata/210/thumb/1"}]
EPS = [{"type": "episode", "ratingKey": 211 + k, "key": f"/library/metadata/{211 + k}", "title": t,
        "index": k + 1, "parentIndex": 1, "grandparentTitle": "Planet Earth II", "duration": 3000000,
        "viewCount": 1 if k < 2 else 0, "viewOffset": 1200000 if k == 2 else 0,
        "thumb": f"/library/metadata/{211 + k}/thumb/1"}
       for k, t in enumerate(["Islands", "Mountains", "Jungles", "Deserts", "Grasslands", "Cities"])]


def fake_call(self, url, method="GET", token=None, timeout=10, raw=False):
    calls.append((method, url, token))
    u = urllib.parse.urlparse(url)
    path = u.path
    if url.startswith("https://plex.tv/api/v2/pins") and method == "POST":
        return {"id": 77, "code": "K7QF", "expiresIn": 900}
    if url.startswith("https://plex.tv/api/v2/pins/77"):
        polls["n"] += 1
        return {"authToken": "ACCOUNT-TOKEN"} if polls["n"] >= 2 else {}
    if url.startswith("https://plex.tv/api/v2/resources"):
        return [
            {"name": "Phone", "provides": "client,player"},
            {"name": "Basement Plex", "provides": "server", "owned": True, "accessToken": "SERVER-TOKEN",
             "connections": [
                 {"protocol": "https", "address": "203.0.113.9", "port": 32400, "local": False, "relay": False,
                  "uri": "https://203-0-113-9.abc.plex.direct:32400"},
                 {"protocol": "https", "address": "192.168.0.5", "port": 32400, "local": True, "relay": False,
                  "uri": "https://192-168-0-5.abc.plex.direct:32400"}]}]
    if path == "/identity":
        if "plex.direct" in url:
            raise OSError("dns rebinding blocked")
        return {"MediaContainer": {"machineIdentifier": "x"}}
    if path == "/hubs/continueWatching/items":
        raise OSError("old server")
    if url.startswith("https://discover.provider.plex.tv"):
        return {"MediaContainer": {"Metadata": []}}
    if path == "/library/onDeck":
        return {"MediaContainer": {"Metadata": [EPS[2], MOVIES[0]]}}
    if path == "/library/sections":
        return {"MediaContainer": {"Directory": [
            {"key": "1", "type": "movie", "title": "Movies"},
            {"key": "2", "type": "show", "title": "TV Shows"},
            {"key": "3", "type": "artist", "title": "Music"}]}}
    if path == "/library/sections/1/all":
        return {"MediaContainer": {"Metadata": MOVIES}}
    if path == "/library/sections/2/all":
        return {"MediaContainer": {"Metadata": SHOWS}}
    if path == "/library/metadata/200/children":
        return {"MediaContainer": {"Metadata": SEASONS}}
    if path == "/library/metadata/210/children":
        return {"MediaContainer": {"Metadata": EPS}}
    if path == "/photo/:/transcode":
        q = urllib.parse.parse_qs(u.query)
        return poster(int(q["width"][0]), int(q["height"][0]), hash(q["url"][0]) % 7)
    if path in ("/:/timeline", "/:/scrobble", "/video/:/transcode/universal/stop"):
        return b""
    raise OSError("unexpected " + url)


g.Plex.call = fake_call

shots = []


class FakeFB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

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


m = g.Media()
m.load_fonts()
m.fb = FakeFB()
m.active = True
pi = m.tab_index("plex")
m.tab = pi
m.load_tab(pi)
m.dirty = True; m.flush()                          # sign-in page
m.press("a")
assert wait_for(lambda: m.plex.pin is not None)
m.dirty = True; m.flush()                          # code page
assert wait_for(lambda: m.plex.ready, 15), "no server"
print("server:", m.plex.cfg["server"], m.plex.cfg["server_name"], "token:", m.plex.cfg["server_token"])
print("plex.json mode:", oct(os.stat(g.PLEX_FILE).st_mode & 0o777))
assert wait_for(lambda: m.plex_stack and m.status.get(pi) is None)
time.sleep(0.3)
m.dirty = True; m.flush()                          # root
print("root:", [x["title"] for x in m.tab_items()])
m.sels[pi] = [x["title"] for x in m.tab_items()].index("Movies"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
wait_for(lambda: all(m.plex_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()), 5)
m.dirty = True; m.flush()                          # movies
m.press("b"); print("after B:", m.plex_stack[-1]["title"], m.sels[pi])
m.sels[pi] = [x["title"] for x in m.tab_items()].index("TV Shows"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
m.press("a")                                       # Planet Earth II -> seasons
assert wait_for(lambda: len(m.plex_stack) == 3 and m.status.get(pi) is None)
m.press("a")                                       # Season 1 -> episodes
assert wait_for(lambda: len(m.plex_stack) == 4 and m.status.get(pi) is None)
wait_for(lambda: all(m.plex_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()), 5)
m.sels[pi] = 2
m.dirty = True; m.flush()                          # episodes
# play episode 3 (has 20 min progress)
m.press("a")
args, target = spawned[-1]
q = urllib.parse.parse_qs(urllib.parse.urlparse(target[len("ffmpeg://"):]).query)
print("stream:", target.split("?")[0])
print("  offset", q["offset"], "res", q["videoResolution"], "bitrate", q["maxVideoBitrate"],
      "directStream", q["directStream"], "path", q["path"])
print("kind:", m.kind, "screen owned:", m.proc_owns_screen())
# mplayer reports absolute time (copyts)
m.pos = 1230.0; m.tick(); print("mode:", m.plex_mode, "now:", m.plex_now())
m.press("right"); m.press("right"); m.press("r")
print("pending:", m.plex_pending)
m.plex_pending_t = 0; m.tick()
_, target2 = spawned[-1]
q2 = urllib.parse.parse_qs(urllib.parse.urlparse(target2[len("ffmpeg://"):]).query)
print("restart offset:", q2["offset"], "sessions differ:", q["session"] != q2["session"])
# relative reporting after restart
m.pos = 15.0; m.tick(); print("mode2:", m.plex_mode, "now:", m.plex_now())
# play to near the end, then the stream ends by itself -> scrobble + next episode
m.plex_last = 2950; m.pos = 2950 - m.plex_base; m.started -= 100
m.proc.dead = True
m.tick()
time.sleep(0.5)
print("next episode playing:", m.cur["title"] if m.cur else None)
print("scrobbles:", [c[1].split("?")[0] for c in calls if "/:/scrobble" in c[1]])
print("timeline states:", [urllib.parse.parse_qs(urllib.parse.urlparse(c[1]).query)["state"][0]
                           for c in calls if "/:/timeline" in c[1]])
m.press("b"); time.sleep(0.3)
print("after stop: kind", m.kind, "view", m.view, "transcode stops:",
      len([c for c in calls if "transcode/universal/stop" in c[1]]))
m.dirty = True; m.flush()                          # episode list after watching
# sign out
m.plex_back(); m.plex_back(); m.plex_back()
m.sels[pi] = len(m.tab_items()) - 1
m.press("a"); m.press("a")
print("signed in after sign out:", m.plex.signed_in, m.plex.ready)
m.dirty = True; m.flush()

W, H = 640, 480
pick = [shots[0], shots[1], shots[2], shots[3], shots[4], shots[-2]]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, im in enumerate(pick):
    sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/plex_screens.png")
print("shots", len(shots))

print("ALL OK")   # (got here: every assert above held)
