import io, json, os, sys, threading, time, shutil, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t21"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.HA_POLL = 0.5
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.fetch_json = lambda url: (_ for _ in ()).throw(OSError("offline"))
json.dump({"client": "abc", "token": "ACCOUNT", "server": "http://192.168.1.5:32400",
           "server_token": "SRV", "server_name": "Home Plex"}, open(g.PLEX_FILE, "w"))

# ---------------------------------------------------------------- a pretend Plex
CHANNELS = [{"title": t, "key": f"/ch/{i}", "thumb": "", "genre": gen} for i, (t, gen) in enumerate([
    ("Pluto News Now", "News"), ("Cooking Channel Live", "Food"), ("Classic Movies", "Movies"),
    ("Movie Night", "Movies"), ("The Pet Collective", "Animals"), ("Baking Shows", "Food"),
    ("Cartoon Classics", "Kids"), ("Comedy Movies", "Movies")])]
plex_calls = []


def fake_call(self, url, method="GET", token=None, timeout=10, raw=False):
    plex_calls.append(url)
    u = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(u.query)
    if u.path == "/hubs/continueWatching/items":
        return {"MediaContainer": {"Metadata": []}}
    if url.startswith("https://discover.provider.plex.tv"):
        return {"MediaContainer": {"Metadata": []}}
    if u.path == "/library/sections":
        return {"MediaContainer": {"Directory": [{"key": "1", "type": "movie", "title": "Movies"}]}}
    if u.path == "/hubs/search":
        word = q["query"][0].lower()
        hubs = [{"type": "movie", "Metadata": [
            {"type": "movie", "ratingKey": 7, "key": "/library/metadata/7", "title": "Movie Night Mystery",
             "year": 1999, "duration": 5400000}] if "movie" in word else []},
            {"type": "actor", "Metadata": [{"type": "actor", "title": "someone"}]}]
        return {"MediaContainer": {"Hub": hubs}}
    if u.path == "/photo/:/transcode":
        im = Image.new("RGB", (int(q["width"][0]), int(q["height"][0])), (90, 60, 120))
        b = io.BytesIO(); im.save(b, "JPEG"); return b.getvalue()
    raise OSError("unexpected " + url)


g.Plex.call = fake_call
g.Plex.live_channels = lambda self: CHANNELS

# ---------------------------------------------------------------- a pretend Home Assistant
TOKEN = "tok"
ha_calls = []
style = {"tv": "samsung"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        sam = style["tv"] == "samsung"
        tv = "media_player.samsung_tv" if sam else "media_player.shield"
        rem = "remote.samsung_tv" if sam else "remote.shield"
        if self.path == "/api/states":
            return self.reply([{"entity_id": tv, "state": "on", "attributes": {"friendly_name": "Living Room TV",
                                                                               "device_class": "tv"}},
                               {"entity_id": rem, "state": "on", "attributes": {"friendly_name": "TV"}}])
        if self.path.startswith("/api/states/"):
            return self.reply({"entity_id": tv, "state": "on", "attributes": {
                "friendly_name": "Living Room TV", "volume_level": 0.2, "source": "TV", "source_list": ["TV"]}})
        self.reply({}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        svc = self.path.replace("/api/services/", "")
        ha_calls.append((svc, body))
        if svc == "media_player/play_media" and style["tv"] != "samsung":
            if not isinstance(body["media_content_id"], int):
                return self.reply({"message": "Channel must be an integer"}, 400)
        self.reply([])


srv = ThreadingHTTPServer(("127.0.0.1", 8124), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
open(HOME + "/homeassistant.txt", "w").write(f"url = 127.0.0.1:8124\ntoken = {TOKEN}\n")

shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


g.Framebuffer = FB


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media()
m.enter()
m.home_sel = [a for a, _ in m.home_apps()].index("TV"); m.press("a")   # TV
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("Plex"); m.press("a")
pi = m.tab_index("plex")
assert wait_for(lambda: m.plex_stack and m.status.get(pi) is None)
print("plex root:", [x["title"] for x in m.tab_items()])
snap("plex_root")
m.sels[pi] = 0; m.press("a")
print("keyboard:", m.view, m.kb["title"])
m.keyboard_key("char", "m"); m.keyboard_key("char", "o"); m.keyboard_key("char", "v"); m.keyboard_key("char", "i")
m.keyboard_key("char", "e")
snap("plex_keys")
m.press("start")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
print("search 'movie':", [(x["title"], x["kind"], x["sub"]) for x in m.tab_items()])
print("crumb:", m.plex_stack[-1]["title"])
snap("plex_results")
m.press("b"); print("B ->", m.plex_stack[-1]["title"])
# from Live TV: channels only
m.sels[pi] = [x["title"] for x in m.tab_items()].index("Live TV"); m.press("a")
assert wait_for(lambda: len(m.plex_stack) == 2 and m.status.get(pi) is None)
print("live tv:", [x["title"] for x in m.tab_items()][:3])
m.sels[pi] = 0; m.press("a"); print("keyboard:", m.kb["title"])
for ch in "food":
    m.keyboard_key("char", ch)
m.press("start")
assert wait_for(lambda: len(m.plex_stack) == 3 and m.status.get(pi) is None)
print("search 'food' (channels):", [x["title"] for x in m.tab_items()], "| asked the server:",
      any("/hubs/search" in c and "food" in c for c in plex_calls))
m.press("b")
m.sels[pi] = 0; m.press("a")
for ch in "zzz":
    m.keyboard_key("char", ch)
m.press("start")
assert wait_for(lambda: m.status.get(pi) == "empty")
snap("plex_none"); print("nothing:", m.status.get(pi), m.tab_items())
m.press("b"); m.press("b"); m.press("b")
print("back to:", g.LIBRARY[m.tab]["name"])

# ---------------------------------------------------------------- the number pad
ha = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab, m.view = ha, "list"; m.load_tab(ha)          # (the TV Remote is in the Home Assistant menu)
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("TV Remote"); m.press("a")
assert wait_for(lambda: m.hass.tvstate.get("name"))
m.press("select"); print("More:", [o[0] for o in m.remote_options()][:3])
m.press("a")                                        # Number pad is first
print("pad open:", m.remote_pad is not None)
for r, c in ((1, 2), (3, 1)):                       # 6, 0
    m.remote_pad["r"], m.remote_pad["c"] = r, c; m.press("a")
m.pad_key("char", "2")                              # from the BBQ20
snap("pad")
print("typed:", m.remote_pad["text"])
m.press("x"); m.press("down"); m.press("down"); m.press("down")
print("cursor after delete + downs:", m.remote_pad["r"], m.remote_pad["c"])
m.remote_pad["text"] = "590"
m.press("start")
assert wait_for(lambda: any(c[0] == "media_player/play_media" for c in ha_calls))
time.sleep(0.3)
print("samsung go:", [c for c in ha_calls if c[0] == "media_player/play_media"][-1][1], "| pad closed:", m.remote_pad is None)
m.press("select"); m.press("a")
m.press("r"); m.press("l")
m.remote_pad["r"], m.remote_pad["c"] = 2, 3; m.press("a")   # Last
time.sleep(0.8)
print("keys:", [c[1]["command"] for c in ha_calls if c[0] == "remote/send_command"][-3:])
m.press("b"); print("B closes the pad, stays on remote:", m.remote_pad is None, g.LIBRARY[m.tab]["name"])
# an Android TV: "7-1" isn't a whole number, so the digits are pressed
style["tv"] = "android"
m.press("b")
open(HOME + "/homeassistant.txt", "w").write(f"url = 127.0.0.1:8124\ntoken = {TOKEN}\n# shield\n")
m.hass.loaded = None
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("TV Remote"); m.press("a")
assert wait_for(lambda: m.hass.found and m.hass.style == "android")
n = len(ha_calls)
m.press("select"); m.press("a"); m.remote_pad["text"] = "7-1"; m.press("start")
time.sleep(1.5)
print("android 7-1:", [(c[0], c[1].get("command") or c[1].get("media_content_id")) for c in ha_calls[n:]])
m.remote_pad = None
srv.shutdown()

W, H = 640, 480
order = ["plex_root", "plex_keys", "plex_results", "pad"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 2 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/search_pad.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
