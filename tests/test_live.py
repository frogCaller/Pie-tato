import io, os, sys, time, json, shutil, urllib.parse, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t9"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
g.PLEX_FILE = S + "/plex.json"; g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
json.dump({"client": "abc", "token": "ACCOUNT", "server": "http://192.168.0.5:32400",
           "server_token": "SRV", "server_name": "Basement Plex"}, open(g.PLEX_FILE, "w"))

GENRES = ["News", "Movies", "Comedy", "Sports", "Kids", "Reality"]
NAMES = ["Plex News", "Bloomberg TV+", "Classic Movies", "Comedy Central Pluto", "Kids Toons",
         "Real Crime", "NFL Channel", "Cinema Gold", "Weather Now", "Funny Bones", "Action Hits",
         "Toon Time", "Court TV", "Western Classics"]
CH = [{"title": n, "thumb": f"https://images.example/logo{k}.png",
       "Genre": [{"tag": GENRES[k % len(GENRES)]}],
       "Media": [{"Part": [{"key": f"/library/parts/5e20b730-{k:04d}.m3u8"}]}]} for k, n in enumerate(NAMES)]

seen = []


class Resp:
    def __init__(self, body, url):
        self.body, self.url = body, url
    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def logo(k):
    im = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((10, 10, 190, 70), radius=12, fill=(60 + k * 12 % 190, 120, 220, 255))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def fake_urlopen(req, timeout=10):
    url = req.full_url if hasattr(req, "full_url") else req
    seen.append(url)
    if url.startswith(g.PLEX_EPG + "/lineups/plex/channels"):
        return Resp(json.dumps({"MediaContainer": {"Channel": CH}}).encode(), url)
    if "/library/parts/" in url:
        master = ("#EXTM3U\n"
                  "#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080\nv1080/index.m3u8\n"
                  "#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720\nv720/index.m3u8\n"
                  "#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=854x480\nv480/index.m3u8\n"
                  "#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=640x360\nv360/index.m3u8\n")
        return Resp(master.encode(), "https://cdn.example/live/abc/master.m3u8?sig=1")
    if url.startswith("https://images.example/"):
        return Resp(logo(int(url.split("logo")[1].split(".")[0])), url)
    raise OSError("unexpected " + url)


g.urllib.request.urlopen = fake_urlopen


def fake_call(self, url, method="GET", token=None, timeout=10, raw=False):
    p = urllib.parse.urlparse(url).path
    if p == "/library/onDeck":
        return {"MediaContainer": {"Metadata": []}}
    if p == "/library/sections":
        return {"MediaContainer": {"Directory": [{"key": "1", "type": "movie", "title": "Movies"},
                                                 {"key": "2", "type": "show", "title": "TV Shows"}]}}
    raise OSError(url)


g.Plex.call = fake_call
shots = []


class FB:
    w, h = 640, 480
    def show(self, img): shots.append(img.copy())
    def close(self): pass


spawned = []


class FakeProc:
    def __init__(self): self.stdin = io.StringIO()
    def poll(self): return None
    def wait(self, timeout=None): return 0
    def kill(self): pass


def fake_spawn(self, args, target):
    spawned.append((args, target)); self.started = time.monotonic(); self.proc = FakeProc()


g.Media.spawn = fake_spawn


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
pi = m.tab_index("plex"); m.tab = pi; m.load_tab(pi)
assert wait_for(lambda: m.plex_stack and m.status.get(pi) is None)
print("root:", [x["title"] for x in m.tab_items()])
m.sels[pi] = [x["title"] for x in m.tab_items()].index("Live TV"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
m.dirty = True; m.flush(); k1 = len(shots) - 1
print("genres:", [(x["title"], x["sub"]) for x in m.tab_items()])
m.sels[pi] = [x["title"] for x in m.tab_items()].index("All channels"); m.press("a")   # (Search channels is first)
assert wait_for(lambda: len(m.plex_stack) == 3 and m.status.get(pi) is None)
wait_for(lambda: all(m.plex_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()[:7]), 6)
m.sels[pi] = 2; m.dirty = True; m.flush(); k2 = len(shots) - 1
m.press("a")
args, target = spawned[-1]
print("plays:", target)
print("cache args:", args[args.index("-cache"):args.index("-cache") + 4])
m.press("start"); print("channel up ->", m.cur["title"])
m.qi = len(m.queue) - 1; m.press("start"); print("wraps to ->", m.cur["title"])
m.press("b")
W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, H), (80, 80, 80))
sheet.paste(shots[k1], (0, 0)); sheet.paste(shots[k2], (W + 10, 0))
sheet.save(SP + "/plex_live.png")
print("shots", len(shots))

print("ALL OK")   # (got here: every assert above held)
