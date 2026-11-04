import io, os, sys, time, shutil, json, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t19"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.chown(HOME, 1234, 1234)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, "", ("1.2.3.4", 443)), (2, 1, 6, "", ("5.6.7.8", 443))]
g.socket.gethostbyaddr = lambda ip: ({"1.2.3.4": "de1.api.radio-browser.info",
                                      "5.6.7.8": "fi1.api.radio-browser.info"}[ip], [], [ip])
calls = []
fail = {"on": False}


def st(name, tag, clicks, cc="US", codec="MP3", hls=0, url=None, extra=""):
    slug = name.lower().replace(" ", "")
    return {"name": name, "url": url or f"http://stream.example/{slug}", "url_resolved": url or f"http://stream.example/{slug}.mp3",
            "tags": f"{tag},music{extra}", "countrycode": cc, "codec": codec, "bitrate": 128, "hls": hls,
            "clickcount": clicks, "stationuuid": "uuid-" + slug}


DB = {
    "pop": [st("Hits One", "pop", 9000), st("Today's Pop FM", "pop", 7000, "GB"), st("Pop Talk Daily", "pop", 9999, extra=",talk"),
            st("HLS Pop", "pop", 8000, hls=1), st("Hits One", "pop", 100)],
    "top 40": [st("Top 40 Now", "top 40", 8500), st("Weird Codec", "top 40", 8400, codec="WMA")],
    "hits": [st("Hit Radio Europe", "hits", 6000, "DE")],
    "rock": [st("Classic Rock 101", "rock", 5000), st("Rock Antenne", "rock", 4800, "DE")],
    "classic rock": [st("Rock Legends", "classic rock", 4000)],
}


def fake_json(url):
    calls.append(url)
    if fail["on"]:
        raise OSError("no wifi")
    u = urllib.parse.urlparse(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    if u.path.startswith("/json/url/"):
        return {"ok": True}
    if u.netloc == "de1.api.radio-browser.info":
        raise OSError("de1 is down")
    if u.path == "/json/stations/search":
        if "tag" in q:
            return DB.get(q["tag"], [])
        if "countrycode" in q:
            return DB["pop"] + DB["rock"]
        if "name" in q:
            return [x for v in DB.values() for x in v if q["name"].lower() in x["name"].lower()]
    raise OSError("unexpected " + url)


g.fetch_json = fake_json
shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


g.Framebuffer = FB
spawned = []


class Proc:
    stdin = io.StringIO()
    def poll(self): return None
    def kill(self): pass
    def wait(self, timeout=None): return 0


def fake_spawn(self, args, target):
    spawned.append(target); self.proc = Proc(); self.started = time.monotonic()


g.Media.spawn = fake_spawn


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media()
m.set_setting("location", {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.5, "lon": -122.7})
m.enter()
m.home_sel = [a[0] for a in m.home_apps()].index("Radio"); m.press("a")
print("root:", [(x["title"], x.get("icon")) for x in m.tab_items()][:6], "...", len(m.tab_items()), "rows")
snap("root")
titles = [x["title"] for x in m.tab_items()]
m.sels[m.tab] = titles.index("Pop & Top 40"); m.press("a")
snap("loading")
assert wait_for(lambda: m.status.get(m.tab) is None and m.tab_items())
print("pop:", [(x["title"], x["sub"]) for x in m.tab_items()])
print("servers tried:", sorted({urllib.parse.urlparse(c).netloc for c in calls}))
snap("pop")
m.press("a"); time.sleep(0.3)
print("playing:", m.cur["title"], "->", spawned[-1], "| click counted:", any("/json/url/uuid-hitsone" in c for c in calls))
m.press("b"); print("B from now playing ->", m.view)
m.press("y"); print("Y:", m.msg); m.press("y"); print("Y again:", m.msg)
print("radio.txt:", open(HOME + "/radio.txt").read().strip().splitlines(), "| owner:", os.stat(HOME + "/radio.txt").st_uid)
m.press("b"); print("B ->", "root" if not m.radio_stack else m.radio_stack[-1]["title"],
                    "| selected:", m.tab_items()[m.sels[m.tab]]["title"])
print("your station now first:", m.tab_items()[0]["title"], m.tab_items()[0].get("icon"))
snap("root_mine")
# popular in the US
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Popular in US"); m.press("a")
assert wait_for(lambda: m.status.get(m.tab) is None and m.tab_items())
print("popular:", [x["title"] for x in m.tab_items()])
m.press("b")
# cached: opening again doesn't ask
n = len(calls)
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Pop & Top 40"); m.press("a")
print("from the cache:", len(calls) == n, len(m.tab_items()))
m.press("b")
# search
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Search stations"); m.press("a")
print("keyboard:", m.view, m.kb["title"])
m.kb["text"] = "rock"; m.press("start")
assert wait_for(lambda: m.status.get(m.tab) is None and m.tab_items())
print("search:", m.radio_stack[-1]["title"], [x["title"] for x in m.tab_items()])
snap("search")
m.press("b")
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Search stations"); m.press("a")
m.kb["text"] = "zzzz"; m.press("start")
assert wait_for(lambda: m.status.get(m.tab) == "empty")
snap("search_none")
m.press("b")
# no WiFi: error, then A tries again
fail["on"] = True
m.state["radio"].clear()
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Rock"); m.press("a")
assert wait_for(lambda: m.status.get(m.tab) == "error")
snap("error"); print("hints:", m.list_hints())
fail["on"] = False
m.press("a"); assert wait_for(lambda: m.status.get(m.tab) is None and m.tab_items())
print("rock after retry:", [x["title"] for x in m.tab_items()])
# no SomaFM folder of its own (its channels can go in your radio.txt)
m.press("b")
titles = [x["title"] for x in m.tab_items()]
assert "SomaFM" not in titles and "Radio Paradise" in titles, titles
print("no SomaFM folder; Radio Paradise:", titles.index("Radio Paradise"))
m.sels[m.tab] = titles.index("Rock"); m.press("a")
# B from a folder... then home leaves the folder
m.press("b"); m.press("b"); print("B B ->", m.view, "| stack:", m.radio_stack)

W, H = 640, 480
order = ["root", "pop", "root_mine", "search", "search_none", "error"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/radio_tab.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
