import json, os, sys, threading, time, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t14"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.HA_POLL = 0.5
for t in g.LIBRARY:
    if t["type"] == "remote":
        t["files"] = [HOME + "/homeassistant.txt"]
import gk_static; gk_static.use_home(g, HOME)
g.fetch_json = lambda url: {"response": {"docs": []}}

TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.token"
world = {"setup": "samsung"}
tv = {"state": "on", "volume_level": 0.23, "is_volume_muted": False, "source": "TV",
      "source_list": ["TV", "HDMI 1", "HDMI 2"], "app_name": None, "media_title": None}
calls = []


def states():
    if world["setup"] == "samsung":
        return [
            {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
            {"entity_id": "media_player.spotify", "state": "idle", "attributes": {"friendly_name": "Spotify"}},
            {"entity_id": "media_player.samsung_the_frame_55", "state": tv["state"],
             "attributes": dict(friendly_name="Living Room TV", device_class="tv", **tv)},
            {"entity_id": "remote.samsung_the_frame_55", "state": "on",
             "attributes": {"friendly_name": "Living Room TV"}},
        ]
    if world["setup"] == "shield":
        return [{"entity_id": "media_player.shield", "state": "on",
                 "attributes": {"friendly_name": "SHIELD", "device_class": "tv"}},
                {"entity_id": "remote.shield_remote", "state": "on", "attributes": {"friendly_name": "SHIELD"}}]
    if world["setup"] == "lg":
        return [{"entity_id": "media_player.lg_webos_tv_oled55", "state": "on",
                 "attributes": {"friendly_name": "LG webOS TV OLED55", "device_class": "tv"}}]
    return []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def authed(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.reply({"message": "Invalid authentication"}, 401)
            return False
        return True

    def do_GET(self):
        if not self.authed():
            return
        if self.path == "/api/states":
            return self.reply(states())
        if self.path.startswith("/api/states/"):
            eid = self.path.rsplit("/", 1)[1]
            st = next((x for x in states() if x["entity_id"] == eid), None)
            return self.reply(st) if st else self.reply({"message": "Entity not found."}, 404)
        self.reply({"message": "nope"}, 404)

    def do_POST(self):
        if not self.authed():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        svc = self.path.replace("/api/services/", "")
        calls.append((svc, body))
        if svc == "media_player/volume_up":
            tv["volume_level"] = round(tv["volume_level"] + 0.01, 2)
        elif svc == "media_player/volume_down":
            tv["volume_level"] = round(tv["volume_level"] - 0.01, 2)
        elif svc == "media_player/volume_mute":
            tv["is_volume_muted"] = body["is_volume_muted"]
        elif svc == "media_player/select_source":
            tv["source"] = body["source"]
        elif svc == "media_player/turn_off":
            tv["state"] = "off"
        elif svc == "media_player/turn_on":
            return self.reply({"message": "Entity media_player.samsung_the_frame_55 does not support "
                                          "action media_player.turn_on"}, 400)
        self.reply([])


srv = ThreadingHTTPServer(("127.0.0.1", 8123), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


def conf(text):
    with open(HOME + "/homeassistant.txt", "w") as f:
        f.write(text)


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
# not set up yet
tvi = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab = tvi; m.load_tab(tvi)
print("Home Assistant menu:", [(x["title"], x["sub"]) for x in m.tab_items()])
m.sels[tvi] = [x["title"] for x in m.tab_items()].index("TV Remote")
snap("menu")
m.press("a")
ri = m.tab
print("on:", g.LIBRARY[ri]["name"], "| configured:", m.hass.configured, "running:", m.hass.running)
snap("unset")
m.press("b")

# set up: url and token only
conf(f"# Home Assistant\nurl = http://127.0.0.1:8123/\ntoken = {TOKEN}\n")
m.press("a")
assert wait_for(lambda: m.hass.tvstate.get("name"))
print("found:", m.hass.tv, "|", m.hass.remote, "| style:", m.hass.style)
print("state:", m.hass.tvstate)
snap("remote")

for b in ["up", "right", "a", "y", "x", "l", "r", "r", "start"]:
    m.press(b); time.sleep(0.05)
m.dirty = True; m.flush(); shots["hit"] = FB.last          # START lit
assert wait_for(lambda: len(calls) >= 9)
time.sleep(0.8)
print("calls:", [(c[0], c[1].get("command") or "") for c in calls])
print("volume now:", m.hass.tvstate.get("volume"))

# held arrow: repeats are spaced out
n = len(calls)
m.press("down")
for _ in range(8):
    time.sleep(0.05); m.press("down", repeat=True)
time.sleep(0.6)
print("held down for 0.4 s ->", len(calls) - n, "commands")

# More: mute, then an input
m.press("select"); snap("more")
print("options:", [o[0] for o in m.remote_options()])
m.remote_more["sel"] = [o[0] for o in m.remote_options()].index("Mute"); m.press("a")
assert wait_for(lambda: m.hass.tvstate.get("muted"))
m.press("select")
m.remote_more["sel"] = [o[0] for o in m.remote_options()].index("HDMI 1")
m.press("a")
assert wait_for(lambda: m.hass.tvstate.get("source") == "HDMI 1")
snap("muted_hdmi")
print("muted:", m.hass.tvstate["muted"], "source:", m.hass.tvstate["source"])

# B in the menu closes it; B again goes back to the TV menu and stops polling
m.press("select"); m.press("b"); print("menu closed:", m.remote_more is None, "| still here:", m.tab == ri)
# power off, then on (this TV can't be turned on by HA: the reason shows)
m.press("select"); m.remote_more["sel"] = [o[0] for o in m.remote_options()].index("Turn off"); m.press("a")
assert wait_for(lambda: m.hass.tvstate.get("state") == "off")
m.press("select"); m.remote_more["sel"] = [o[0] for o in m.remote_options()].index("Turn on"); m.press("a")
assert wait_for(lambda: m.msg and "turn this TV on" in m.msg)
print("turn on:", m.msg)
snap("off")
m.press("b")
print("back on:", g.LIBRARY[m.tab]["name"], "| polling:", m.hass.running)
n = len(calls); time.sleep(1.2)
print("quiet after leaving:", len(calls) == n)

# wrong token
conf(f"url = 127.0.0.1:8123\ntoken = wrong\n")
m.sels[m.tab] = [x["title"] for x in m.tab_items()].index("TV Remote"); m.press("a")
assert wait_for(lambda: m.hass.error)
print("bad token:", m.hass.error)
snap("badtoken")
m.press("l"); m.press("r")
print("L R are volume here, not tabs:", g.LIBRARY[m.tab]["name"])
m.press("b")

# other TVs
for setup in ("shield", "lg"):
    world["setup"] = setup
    conf(f"url = 127.0.0.1:8123\ntoken = {TOKEN}\n")
    n = len(calls)
    m.press("a"); assert wait_for(lambda: m.hass.found and setup[:2] in m.hass.tv)
    m.press("up"); m.press("a"); time.sleep(0.8)
    print(setup, "->", m.hass.tv, m.hass.remote or "-", m.hass.style, [c for c in calls[n:]])
    m.press("b")

# nothing reachable
conf(f"url = 127.0.0.1:8999\ntoken = {TOKEN}\n")
m.press("a"); assert wait_for(lambda: m.hass.error)
print("unreachable:", m.hass.error)
m.press("b")

# leaving media mode stops it
g.subprocess.run = lambda *a, **k: None
m.press("a"); m.leave(); print("after leave:", m.hass.running)
srv.shutdown()

W, H = 640, 480
order = ["menu", "remote", "hit", "more", "muted_hdmi", "off", "unset", "badtoken"]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 4 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/tv_remote.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
