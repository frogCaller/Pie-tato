"""The TV Remote with more than one TV in Home Assistant: every TV found (not the Plex clients, casts and DLNA
renderers), each with its own remote and kind, switched between from the More menu, the pick remembered; TVs listed
in homeassistant.txt; a TV that goes away."""
import json, os, sys, threading, time, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_tvs"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.JELLYFIN_FILE = S + "/jellyfin.json"; g.SHRINK_FILE = S + "/shrink.json"
g.home_dir = lambda: HOME
g.HA_POLL = 0.5
import gk_static; gk_static.use_home(g, HOME)

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


TOKEN = "eyJ.fake.token"
calls = []


def player(eid, name, dc=None, state="on", **a):
    attrs = {"friendly_name": name, "volume_level": 0.3, "is_volume_muted": False, "source": "TV",
             "source_list": ["TV", "HDMI 1"], **a}
    if dc:
        attrs["device_class"] = dc
    return {"entity_id": eid, "state": state, "attributes": attrs}


world = {"states": []}
HOUSE = [
    {"entity_id": "light.hall", "state": "on", "attributes": {"friendly_name": "Hall"}},
    player("media_player.samsung_q60_living_room", "Living Room TV", "tv"),
    {"entity_id": "remote.samsung_q60_living_room", "state": "on", "attributes": {"friendly_name": "Living Room TV"}},
    player("media_player.plex_plex_for_samsung_tv", "Plex (Plex for Samsung TV)"),         # a Plex client
    player("media_player.tv_samsung_q60_dlna", "[TV] Samsung Q60 Series (55)"),           # its DLNA renderer
    player("media_player.lg_webos_tv_oled48", "Bedroom TV", "tv", source="HDMI 2"),
    player("media_player.kitchen_display", "Kitchen display"),                           # a cast speaker-ish
    player("media_player.roku_express", "Roku Express", "receiver"),                       # a Roku stick
    {"entity_id": "remote.roku_express", "state": "on", "attributes": {"friendly_name": "Roku Express"}},
    {"entity_id": "remote.harmony_den", "state": "on", "attributes": {"friendly_name": "Den Harmony"}},
]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self.reply({"message": "Invalid authentication"}, 401)
        if self.path == "/api/states":
            return self.reply(world["states"])
        if self.path.startswith("/api/states/"):
            eid = self.path.rsplit("/", 1)[1]
            st = next((x for x in world["states"] if x["entity_id"] == eid), None)
            return self.reply(st) if st else self.reply({"message": "Entity not found."}, 404)
        self.reply({"message": "nope"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        svc = self.path.replace("/api/services/", "")
        calls.append((svc, body))
        st = next((x for x in world["states"] if x["entity_id"] == body.get("entity_id")), None)
        if st and svc == "media_player/volume_up":
            st["attributes"]["volume_level"] = round(st["attributes"]["volume_level"] + 0.01, 2)
        if st and svc == "media_player/select_source":
            st["attributes"]["source"] = body["source"]
        self.reply([])


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


shots = {}


def snap(m, name):
    m.dirty = True; m.flush(); shots[name] = FB.last
    FB.last.save(f"{S}/{name}.png")


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


def conf(text):
    with open(HOME + "/homeassistant.txt", "w") as f:
        f.write(text)


def open_remote(m):
    tvi = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
    m.tab, m.view = tvi, "list"
    m.load_tab(tvi)
    m.sels[tvi] = [x["title"] for x in m.tab_items()].index("TV Remote")
    m.press("a")
    return m.tab


def opts(m):
    return [o[0] for o in m.remote_options()]


def pick(m, label):
    m.press("select")
    m.remote_more["sel"] = opts(m).index(label)
    m.press("a")


world["states"] = json.loads(json.dumps(HOUSE))
conf(f"url = http://127.0.0.1:{PORT}\ntoken = {TOKEN}\n")
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
ri = open_remote(m)
check(wait_for(lambda: m.hass.found and m.hass.tvstate.get("name")), "found")
found = [(t["tv"], t["remote"], t["style"]) for t in m.hass.tvs]
print("TVs:", found)
check(found == [("media_player.samsung_q60_living_room", "remote.samsung_q60_living_room", "samsung"),
                ("media_player.lg_webos_tv_oled48", "", "lg"),
                ("media_player.roku_express", "remote.roku_express", "roku")],
      "every TV, each with its own remote and kind; not the Plex client, the DLNA renderer or the display")
check(m.hass.tv == "media_player.samsung_q60_living_room", "on the first one, as before")
snap(m, "1_living_room")
check(opts(m)[:3] == ["Switch to Bedroom TV", "Switch to Roku Express", "Number pad"], f"More: the others first {opts(m)[:3]}")

# the bedroom TV: an LG, its buttons through webostv.button
pick(m, "Switch to Bedroom TV")
check(m.hass.tv == "media_player.lg_webos_tv_oled48" and m.hass.style == "lg" and m.hass.remote == "",
      "switched to the bedroom TV")
check(m.msg == "Bedroom TV", f"...said so ({m.msg})")
check(wait_for(lambda: m.hass.tvstate.get("source") == "HDMI 2"), "its state, at once")
n = len(calls)
for b in ("up", "a", "r"):
    m.press(b); time.sleep(0.05)
check(wait_for(lambda: len(calls) >= n + 3), "buttons sent")
got = [(c[0], c[1].get("entity_id"), c[1].get("button")) for c in calls[n:n + 3]]
print("bedroom:", got)
check(got == [("webostv/button", "media_player.lg_webos_tv_oled48", "UP"),
              ("webostv/button", "media_player.lg_webos_tv_oled48", "ENTER"),
              ("media_player/volume_up", "media_player.lg_webos_tv_oled48", None)], "...to the bedroom TV")
check(opts(m)[:2] == ["Switch to Living Room TV", "Switch to Roku Express"], f"More now: {opts(m)[:2]}")
snap(m, "2_bedroom")
m.press("select")
snap(m, "3_more")
m.press("b")
check(json.load(open(g.STATE_FILE))["settings"].get("ha_tv") == "media_player.lg_webos_tv_oled48", "the pick kept")

# the Roku stick: remote.send_command
pick(m, "Switch to Roku Express")
n = len(calls)
m.press("left")
check(wait_for(lambda: len(calls) > n) and calls[n] == ("remote/send_command",
      {"entity_id": "remote.roku_express", "command": "left"}), f"the Roku's remote: {calls[n:n + 1]}")
pick(m, "Switch to Bedroom TV")
m.press("b")

# the next time: the bedroom TV again
m2 = g.Media(); m2.load_fonts(); m2.fb = FB(); m2.active = True
open_remote(m2)
check(wait_for(lambda: m2.hass.found and m2.hass.tvstate.get("name") == "Bedroom TV"), "opened again: the bedroom TV")
m2.press("b")

# the bedroom TV goes from Home Assistant: back to the first
world["states"] = [x for x in world["states"] if x["entity_id"] != "media_player.lg_webos_tv_oled48"]
open_remote(m2)
check(wait_for(lambda: m2.hass.found and m2.hass.tv == "media_player.samsung_q60_living_room"
               and m2.hass.tvstate.get("name") == "Living Room TV", 10), "a TV that's gone: on the first one")
check("Switch to Bedroom TV" not in opts(m2), "...and it's not offered")
m2.press("b")

# TVs listed in the file; one remote named there (a Harmony), the rest found
world["states"] = json.loads(json.dumps(HOUSE))
conf(f"url = http://127.0.0.1:{PORT}\ntoken = {TOKEN}\n"
     "tv = media_player.lg_webos_tv_oled48, media_player.samsung_q60_living_room\nremote = remote.harmony_den\n")
m3 = g.Media(); m3.load_fonts(); m3.fb = FB(); m3.active = True
open_remote(m3)
check(wait_for(lambda: m3.hass.found), "listed: found")
got = [(t["tv"], t["remote"], t["style"]) for t in m3.hass.tvs]
print("listed:", got)
check(got == [("media_player.lg_webos_tv_oled48", "remote.harmony_den", "lg"),
              ("media_player.samsung_q60_living_room", "remote.samsung_q60_living_room", "samsung")],
      "the file's TVs, in its order; its remote for the first, the other's own")
check(m3.hass.tv == "media_player.lg_webos_tv_oled48", "the pick from before (the bedroom TV) still used")
m3.press("b")

# two TVs with the same name: told apart
world["states"] = [player("media_player.samsung_tv", "Samsung TV", "tv"),
                   {"entity_id": "remote.samsung_tv", "state": "on", "attributes": {"friendly_name": "Samsung TV"}},
                   player("media_player.samsung_tv_2", "Samsung TV", "tv"),
                   {"entity_id": "remote.samsung_tv_2", "state": "on", "attributes": {"friendly_name": "Samsung TV"}}]
conf(f"url = http://127.0.0.1:{PORT}\ntoken = {TOKEN}\n")
m4 = g.Media(); m4.load_fonts(); m4.fb = FB(); m4.active = True
m4.state["settings"].pop("ha_tv", None)
m4.hass.pick = ""
open_remote(m4)
check(wait_for(lambda: m4.hass.found), "two alike: found")
check([t["remote"] for t in m4.hass.tvs] == ["remote.samsung_tv", "remote.samsung_tv_2"], "...each its own remote")
check(opts(m4)[0] == "Switch to Samsung TV (media_player.samsung_tv_2)", f"...told apart: {opts(m4)[0]}")
pick(m4, opts(m4)[0])
check(m4.msg == "Samsung TV (media_player.samsung_tv_2)" and m4.hass.remote == "remote.samsung_tv_2", "switched")
snap(m4, "4_alike")
m4.press("b")

# one TV only: the menu as it always was
world["states"] = [x for x in json.loads(json.dumps(HOUSE)) if "lg_" not in x["entity_id"] and "roku" not in x["entity_id"]]
m5 = g.Media(); m5.load_fonts(); m5.fb = FB(); m5.active = True
m5.hass.pick = ""
m5.state["settings"].pop("ha_tv", None)
open_remote(m5)
check(wait_for(lambda: m5.hass.found), "one TV: found")
check(opts(m5)[0] == "Number pad" and len(m5.hass.tvs) == 1, f"one TV: no switching ({opts(m5)[:2]})")
snap(m5, "5_one")
m5.press("b")
srv.shutdown()

from PIL import Image
sheet = Image.new("RGB", (1290, 970), (80, 80, 80))
for k, name in enumerate(["1_living_room", "2_bedroom", "3_more", "4_alike"]):
    sheet.paste(shots[name], ((k % 2) * 650, (k // 2) * 490))
sheet.save(S + "/sheet.png")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
