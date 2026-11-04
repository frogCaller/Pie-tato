import io, os, sys, time, json, shutil, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t10"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
g.PLEX_FILE = S + "/plex.json"; g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
json.dump({"client": "abc", "token": "ACCOUNT", "server": "http://192.168.0.5:32400",
           "server_token": "SRV", "server_name": "Basement Plex"}, open(g.PLEX_FILE, "w"))


def poster(w, h, seed):
    im = Image.new("RGB", (w, h), ((seed * 70) % 255, (seed * 40) % 255, 120))
    ImageDraw.Draw(im).ellipse((w * .2, h * .3, w * .8, h * .7), fill=(240, 220, 180))
    b = io.BytesIO(); im.save(b, "JPEG"); return b.getvalue()


CONT = [
    {"type": "movie", "ratingKey": 101, "key": "/library/metadata/101", "title": "Blade Runner 2049",
     "year": 2017, "duration": 9840000, "viewOffset": 2400000, "thumb": "/t/101"},
    {"type": "movie", "ratingKey": 104, "key": "/library/metadata/104", "title": "Arrival",
     "year": 2016, "duration": 6960000, "viewOffset": 5400000, "thumb": "/t/104"},
    {"type": "episode", "ratingKey": 213, "key": "/library/metadata/213", "title": "Jungles",
     "index": 3, "parentIndex": 1, "grandparentTitle": "Planet Earth II", "duration": 3000000,
     "viewOffset": 1200000, "thumb": "/t/213"},
]
WATCH = [
    {"guid": "plex://movie/aaa", "type": "movie", "title": "Dune: Part Two", "year": 2024,
     "thumb": "https://metadata-static.example/dune.jpg"},
    {"guid": "plex://show/bbb", "type": "show", "title": "Severance", "year": 2022,
     "thumb": "https://metadata-static.example/sev.jpg"},
    {"guid": "plex://movie/ccc", "type": "movie", "title": "Oppenheimer", "year": 2023,
     "thumb": "https://metadata-static.example/opp.jpg"},
]
ON_SERVER = {
    "plex://movie/aaa": {"type": "movie", "ratingKey": 150, "key": "/library/metadata/150",
                         "title": "Dune: Part Two", "year": 2024, "duration": 9960000, "thumb": "/t/150"},
    "plex://show/bbb": {"type": "show", "ratingKey": 300, "key": "/library/metadata/300/children",
                        "title": "Severance", "leafCount": 19, "viewedLeafCount": 9, "thumb": "/t/300"},
}
calls = []


def fake_call(self, url, method="GET", token=None, timeout=10, raw=False):
    calls.append(url)
    u = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(u.query)
    if url.startswith("https://discover.provider.plex.tv/library/sections/watchlist/all"):
        assert token == "ACCOUNT"
        return {"MediaContainer": {"Metadata": WATCH}}
    if u.path == "/hubs/continueWatching/items":
        return {"MediaContainer": {"Metadata": CONT}}
    if u.path == "/library/all":
        m = ON_SERVER.get(q["guid"][0])
        return {"MediaContainer": {"Metadata": [m] if m else []}}
    if u.path == "/library/sections":
        return {"MediaContainer": {"Directory": [{"key": "1", "type": "movie", "title": "Movies"},
                                                 {"key": "2", "type": "show", "title": "TV Shows"}]}}
    if u.path == "/photo/:/transcode":
        return poster(int(q["width"][0]), int(q["height"][0]), hash(q["url"][0]) % 7)
    raise OSError("unexpected " + url)


g.Plex.call = fake_call


class Resp:
    def __init__(self, body): self.body = body
    def read(self, n=-1): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


real_urlopen = g.urllib.request.urlopen
g.urllib.request.urlopen = lambda req, timeout=10: Resp(poster(120, 180, 3))   # remote posters
g.Plex.live_channels = lambda self: [{"title": "Retro Toons", "key": "/ch/1", "thumb": "", "genre": "Kids"},
                                     {"title": "Naruto", "key": "/ch/2", "thumb": "", "genre": "Anime"}]

shots = []


class FB:
    w, h = 640, 480
    def show(self, img): shots.append(img.copy())
    def close(self): pass


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.tab = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "TV")   # (Home Assistant is first now)
m.load_tab(m.tab)
print("strip:", [g.LIBRARY[i]["name"] for i in m.visible_tabs()], "| start tab:", g.LIBRARY[m.tab]["name"])
m.dirty = True; m.flush(); k_tv = len(shots) - 1
print("TV menu:", [(x["title"], x["sub"]) for x in m.tab_items()])
m.press("a")                                      # Plex
pi = m.tab_index("plex")
assert m.tab == pi
assert wait_for(lambda: m.plex_stack and m.status.get(pi) is None)
m.dirty = True; m.flush(); k_root = len(shots) - 1
print("Plex root:", [(x["title"], x["sub"]) for x in m.tab_items()])
m.sels[pi] = [x["title"] for x in m.tab_items()].index("Continue watching"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
wait_for(lambda: all(m.plex_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()), 5)
m.dirty = True; m.flush(); k_cont = len(shots) - 1
print("continue:", [(x["title"], m.row_right(x)[0]) for x in m.tab_items()])
m.press("b")
m.sels[pi] = [x["title"] for x in m.tab_items()].index("Watchlist"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
wait_for(lambda: all(m.plex_thumb(x, m.plex_size(x)) is not None for x in m.tab_items()), 5)
m.sels[pi] = 2; m.dirty = True; m.flush(); k_watch = len(shots) - 1
print("watchlist:", [(x["title"], x["kind"], m.row_right(x)[0]) for x in m.tab_items()])
m.press("a"); print("toast on unmatched:", m.msg)
m.press("b"); m.press("b")
print("after B B:", g.LIBRARY[m.tab]["name"], "selected:", m.tab_items()[m.sels[m.tab]]["title"])
m.press("r"); print("R from TV ->", g.LIBRARY[m.tab]["name"])
m.press("l"); m.press("l"); print("L L ->", g.LIBRARY[m.tab]["name"])
m.press("r")
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Cartoons"); m.press("a")   # Cartoons
ci = m.tab
assert wait_for(lambda: m.status.get(ci) is None and m.tab_items(ci))
m.dirty = True; m.flush(); k_cart = len(shots) - 1
print("in:", g.LIBRARY[m.tab]["name"], "hints:", m.list_hints())
m.press("r"); print("R from Cartoons ->", g.LIBRARY[m.tab]["name"])

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, idx in enumerate([k_tv, k_root, k_cont, k_watch, k_cart]):
    sheet.paste(shots[idx], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/tv_tab.png")

print("ALL OK")   # (got here: every assert above held)
