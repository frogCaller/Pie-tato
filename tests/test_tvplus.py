import io, os, sys, time, shutil, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
S = SP + "/t28"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
sys.path.insert(0, SP)
import gk_static; gk_static.use_home(g, S + "/home/u")
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
asked = []
def fake_json(url, timeout=15):
    asked.append(url)
    return {"files": [{"name": "his_girl_friday.mpeg", "source": "original", "size": "900"},
                      {"name": "his_girl_friday_512kb.mp4", "source": "derivative", "original": "his_girl_friday.mpeg", "size": "300"},
                      {"name": "his_girl_friday.mp4", "source": "derivative", "original": "his_girl_friday.mpeg", "size": "600"}]}
g.fetch_json = fake_json
MASTERS = {
  "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8":
    "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\nstream_1080.m3u8\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360\nstream_360.m3u8\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=854x480\nstream_480.m3u8\n",
  "https://bloomberg.com/media-manifest/streams/us.m3u8":
    "#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"aac\",URI=\"audio.m3u8\"\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360,AUDIO=\"aac\"\nv360.m3u8\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,AUDIO=\"aac\"\nv1080.m3u8\n",
}
class Resp:
    def __init__(self, url, text): self.url, self.text = url, text
    def geturl(self): return self.url
    def read(self, n=-1): return self.text.encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
opened = []
def fake_urlopen(req, timeout=10):
    url = req.full_url if hasattr(req, "full_url") else req
    opened.append(url)
    if url in MASTERS:
        return Resp(url, MASTERS[url])
    raise OSError("no network")
g.urllib.request.urlopen = fake_urlopen
CH = [("Anime All Day", "Animation"), ("Retro Toons", "Kids"), ("Action Movies", "Movies"),
      ("ABC News Live", "News"), ("Reuters Now", "News"), ("Stadium", "Sports"), ("PGA Tour", "Golf"),
      ("Fight Network", "Sports"), ("Cooking Live", "Food")]
CHANNELS = [{"title": t, "key": f"/ch/{i}", "thumb": "", "genre": gen} for i, (t, gen) in enumerate(CH)]
plex = {"n": 0, "fail": False, "slow": 0}
def live_channels(self):
    plex["n"] += 1; time.sleep(plex["slow"])
    if plex["fail"]:
        raise OSError("no wifi")
    return CHANNELS
g.Plex.live_channels = live_channels
spawned = []
class Proc:
    stdin = io.StringIO()
    def poll(self): return None
    def kill(self): pass
    def wait(self, timeout=None): return 0
def fake_spawn(self, args, target):
    spawned.append((args, target)); self.proc = Proc(); self.started = time.monotonic()
g.Media.spawn = fake_spawn
class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass
g.Framebuffer = FB
shots = {}
def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last
def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        m.tick()
        if c(): return True
        time.sleep(0.05)
    return False
def titles(): return [x["title"] for x in m.tab_items()]

m = g.Media(); m.enter()
m.home_sel = [a for a, _ in m.home_apps()].index("TV"); m.press("a"); tv = m.tab
print("TV menu:", [(x["title"], x["sub"]) for x in m.tab_items()])
snap("tv")
# Free Movies, not signed in: the films are there at once
m.sels[tv] = titles().index("Free Movies"); m.press("a"); fi = m.tab
print("free movies:", [(x["title"], x["sub"]) for x in m.tab_items()], "| note:", m.channels_note())
snap("movies")
m.sels[fi] = titles().index("Comedy & drama"); m.press("a")
print("comedy:", titles()[:4], "… note:", m.channels_note())
m.sels[fi] = titles().index("His Girl Friday"); m.press("a")
print("plays:", spawned[-1][1])
m.press("b"); m.proc = None; m.press("b")
m.sels[fi] = titles().index("Movie channels"); m.press("a"); print("movie channels, not signed in:", m.status.get(fi), m.list_hints()[0])
m.press("b")
m.sels[fi] = 0; m.press("a")
for ch in "night": m.keyboard_key("char", ch)
m.press("start"); print("search films 'night':", titles())
m.press("b"); m.press("b")
# News, not signed in: it's all Plex's channels now, so one row that says so (no Search: nothing to look in)
m.sels[tv] = titles().index("News"); m.press("a"); ni = m.tab
rows = [(x["title"], x["kind"], x["sub"]) for x in m.tab_items()]
print("news:", rows, "| note:", m.channels_note(), "| hint:", (m.sels.__setitem__(ni, 0), m.list_hints()[0])[1])
assert rows == [("News channels", "chplex", "Sign in to Plex")], rows
snap("news_noplex")
m.press("a"); print("A on News channels ->", g.LIBRARY[m.tab]["name"])
assert g.LIBRARY[m.tab]["name"] == "Plex"
m.press("b")
# Sports, not signed in: the same
m.sels[tv] = titles().index("Sports"); m.press("a"); si = m.tab
print("sports:", [(x["title"], x["kind"]) for x in m.tab_items()])
assert [(x["title"], x["kind"]) for x in m.tab_items()] == [("Sports channels", "chplex")]
m.press("b")
# your own streams.txt: a live .m3u8 plays the version that suits the Pi, as the built-in ones did
open(S + "/home/u/streams.txt", "w").write(
    "# mine\nDW News | https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8\n"
    "Bloomberg TV | https://bloomberg.com/media-manifest/streams/us.m3u8\n"
    "Garden cam | http://192.0.2.7/video.mjpg\nTypo | http://[oops/live.m3u8\n")
m.sels[tv] = titles().index("Streams"); m.press("a"); sti = m.tab
print("streams:", titles())
m.sels[sti] = titles().index("DW News"); m.press("a")
print("DW plays:", spawned[-1][1])
assert spawned[-1][1] == "ffmpeg://https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/stream_480.m3u8"
m.press("b"); m.proc = None
m.sels[sti] = titles().index("Bloomberg TV"); m.press("a")
print("Bloomberg (sound kept apart) plays the whole stream:", spawned[-1][1])
assert spawned[-1][1] == "ffmpeg://https://bloomberg.com/media-manifest/streams/us.m3u8"
m.press("b"); m.proc = None
before = len(opened)
m.sels[sti] = titles().index("Garden cam"); m.press("a")
print("not an .m3u8, played as it is, nothing fetched first:", spawned[-1][1], len(opened) - before)
assert spawned[-1][1] == "ffmpeg://http://192.0.2.7/video.mjpg" and len(opened) == before
m.press("b"); m.proc = None
m.sels[sti] = titles().index("Typo"); m.press("a")
print("a broken link is handed to the player, media mode carries on:", spawned[-1][1], "| view:", m.view)
assert spawned[-1][1] == "ffmpeg://http://[oops/live.m3u8"
m.press("b"); m.proc = None
m.press("b")
# signed in: Search, and Plex's news channels when they come
m.plex.cfg.update(token="ACCOUNT"); plex["slow"] = 0.4
m.sels[tv] = titles().index("News"); m.press("a")
print("news while Plex answers:", [(x["title"], x["kind"]) for x in m.tab_items()],
      "| hints:", (m.sels.__setitem__(ni, len(titles()) - 1), m.list_hints()[:2])[1])
assert [(x["title"], x["kind"]) for x in m.tab_items()] == [("Search", "chsearch"), ("News channels", "chwait")]
assert wait_for(lambda: "ABC News Live" in titles())
print("news after:", titles())
assert titles() == ["Search", "ABC News Live", "Reuters Now"], titles()
snap("news")
m.sels[ni] = 0; m.press("a")
for ch in "reuters": m.keyboard_key("char", ch)
m.press("start"); print("search news 'reuters':", titles()); assert titles() == ["Reuters Now"]
m.press("b"); m.press("b")
# Sports (channels already fetched)
m.sels[tv] = titles().index("Sports"); m.press("a")
print("sports:", titles()); snap("sports")
assert titles() == ["Search", "Stadium", "PGA Tour", "Fight Network"], titles()
m.sels[si] = 0; m.press("a")
for ch in "golf": m.keyboard_key("char", ch)
m.press("start"); print("search sports 'golf':", titles()); assert titles() == ["PGA Tour"]
m.press("b"); m.press("b")
# Plex fails for Sports: a row to try again
m.plex_live = (0.0, []); plex["fail"] = True; plex["slow"] = 0
m.sels[tv] = titles().index("Sports"); m.press("a")
assert wait_for(lambda: titles()[-1] == "Sports channels" and m.tab_items()[-1]["kind"] == "chretry")
print("sports, Plex down:", [(x["title"], x["sub"]) for x in m.tab_items()], "| hint:", (m.sels.__setitem__(si, len(titles()) - 1), m.list_hints()[0])[1])
plex["fail"] = False; m.press("a")
assert wait_for(lambda: "Stadium" in titles()); print("after A:", titles())
# Cartoons unchanged
m.press("b"); m.sels[tv] = titles().index("Cartoons"); m.press("a")
print("cartoons:", titles()[:5], "| note:", m.channels_note())
print("hls_pick DW ->", g.hls_pick("https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8"))
print("hls_pick down ->", g.hls_pick("https://example.com/x.m3u8"))
W, H = 640, 480
order = ["tv", "movies", "news_noplex", "news", "sports"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/tvplus.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
