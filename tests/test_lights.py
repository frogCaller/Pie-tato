"""The Lights page against a fake Home Assistant: lights found (and plugs, not other switches), switched and dimmed
at once on the screen and sent after, a held arrow sent as one change, plugs, scenes in their folder, all lights off,
a change made elsewhere picked up, the lights named in homeassistant.txt, and what it says when it can't."""
import json, os, sys, threading, time, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_lights"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.JELLYFIN_FILE = S + "/jellyfin.json"; g.SHRINK_FILE = S + "/shrink.json"
g.home_dir = lambda: HOME
g.HA_LIGHTS_POLL = 0.6
import gk_static; gk_static.use_home(g, HOME)

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


TOKEN = "eyJ.fake.token"
calls = []
lock = threading.Lock()


def light(eid, name, on, bright=None, modes=("brightness",)):
    a = {"friendly_name": name, "supported_color_modes": list(modes)}
    if on and bright is not None:
        a["brightness"] = bright
    return {"entity_id": eid, "state": "on" if on else "off", "attributes": a}


world = {"states": [
    light("light.living_room_lamp", "Living room lamp", True, 153),
    light("light.kitchen", "Kitchen", False),
    light("light.porch", "Porch", True, None, modes=("onoff",)),
    light("light.hall", "Hall", False, None, modes=("color_temp", "xy")),
    {"entity_id": "light.garage", "state": "unavailable", "attributes": {"friendly_name": "Garage"}},
    {"entity_id": "switch.fan_plug", "state": "off", "attributes": {"friendly_name": "Fan plug", "device_class": "outlet"}},
    {"entity_id": "switch.adguard_protection", "state": "on", "attributes": {"friendly_name": "AdGuard protection"}},
    {"entity_id": "scene.movie_night", "state": "2026-10-20T20:00:00", "attributes": {"friendly_name": "Movie night"}},
    {"entity_id": "scene.morning", "state": "unknown", "attributes": {"friendly_name": "Morning"}},
    {"entity_id": "media_player.tv", "state": "on", "attributes": {"friendly_name": "TV", "device_class": "tv"}},
    {"entity_id": "sensor.temp", "state": "21", "attributes": {"friendly_name": "Temperature"}},
], "slow": 0.0}


def find(eid):
    return next((x for x in world["states"] if x["entity_id"] == eid), None)


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
            with lock:
                return self.reply(world["states"])
        self.reply({"message": "nope"}, 404)

    def do_POST(self):
        if not self.authed():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        svc = self.path.replace("/api/services/", "")
        time.sleep(world["slow"])
        with lock:
            calls.append((svc, body))
            ids = body.get("entity_id")
            for eid in (ids if isinstance(ids, list) else [ids]):
                st = find(eid)
                if not st:
                    continue
                if svc.endswith("/turn_on") and not svc.startswith("scene"):
                    st["state"] = "on"
                    if "brightness_pct" in body:
                        st["attributes"]["brightness"] = round(body["brightness_pct"] * 255 / 100)
                    elif "supported_color_modes" in st["attributes"] and st["attributes"]["supported_color_modes"] != ["onoff"]:
                        st["attributes"].setdefault("brightness", 255)
                elif svc.endswith("/turn_off"):
                    st["state"] = "off"
                    st["attributes"].pop("brightness", None)
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


def snap(name):
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


def rows():
    return [(x["title"], m.row_right(x)[0]) for x in m.tab_items()]


def go(title):
    m.sels[m.tab] = [x["title"] for x in m.tab_items()].index(title)


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
tvi = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab, m.view = tvi, "list"
m.load_tab(tvi)
check("Lights" in [x["title"] for x in m.tab_items()], "Lights is in the Home Assistant menu")
go("Lights")
m.press("a")
li = m.tab
check(g.LIBRARY[li]["type"] == "lights", "...and opens")
snap("0_unset")
check(m.lights_empty()[0] == "Connect Home Assistant", "not set up: says how")
m.press("b")
check(m.tab == tvi and not m.lights.running, "B: back to the Home Assistant menu")

conf(f"url = http://127.0.0.1:{PORT}/api\ntoken = {TOKEN}\n")
go("Lights"); m.press("a")
check(wait_for(lambda: m.lights.found and len(m.tab_items()) > 2), "found")
print("rows:", rows())
check(rows() == [("All lights off", "2 on"), ("Scenes", "2 scenes"), ("Garage", "not answering"), ("Hall", "off"),
                 ("Kitchen", "off"), ("Living room lamp", "60%"), ("Porch", "on"), ("Fan plug", "off")],
      "all lights off, the scenes, each light (by name) and the plug; not other switches, TVs or sensors")
snap("1_lights")

# on and off, at once on the screen
go("Kitchen"); n = len(calls)
m.press("a")
check(rows()[4] == ("Kitchen", "100%"), f"A: on at once ({rows()[4]})")
check(wait_for(lambda: len(calls) > n) and calls[n] == ("light/turn_on", {"entity_id": "light.kitchen"}), f"...sent: {calls[n:]}")
check(m.list_hints()[:2] == [("A", "Turn off"), ("◀▶", "Dimmer")], f"hints: {m.list_hints()[:2]}")
m.press("a")
check(wait_for(lambda: calls[-1] == ("light/turn_off", {"entity_id": "light.kitchen"})), "A again: off")

# the dimmer: a held arrow is one change, where it ends up
go("Living room lamp"); n = len(calls)
world["slow"] = 0.4
m.press("right")
for _ in range(10):
    time.sleep(0.07); m.press("right", repeat=True)
check(rows()[5] == ("Living room lamp", "90%"), f"held right: brighter at once ({rows()[5]})")
check(wait_for(lambda: any(c[1].get("brightness_pct") == 90 for c in calls[n:]), 6), "...sent")
dims = [c for c in calls[n:] if c[0] == "light/turn_on"]
print("dim calls:", dims)
check(len(dims) <= 3 and dims[-1][1] == {"entity_id": "light.living_room_lamp", "brightness_pct": 90},
      f"...as a few changes, not one a press ({len(dims)})")
world["slow"] = 0.0
time.sleep(1.5)
check(rows()[5] == ("Living room lamp", "90%"), "...and stays there when Home Assistant's asked again")
for _ in range(9):
    m.press("left"); time.sleep(0.32)
check(rows()[5] == ("Living room lamp", "off"), f"left to nothing: off ({rows()[5]})")
check(wait_for(lambda: calls[-1] == ("light/turn_off", {"entity_id": "light.living_room_lamp"})), "...sent as off")
m.press("right")
check(rows()[5] == ("Living room lamp", "10%"), "right from off: on, dim")
snap("2_dimmed")

# a light that only goes on and off: the arrows are off and on; a plug
go("Porch"); n = len(calls)
check(m.list_hints()[1] == ("◀▶", "Off / on"), "on/off only: ◀▶ off / on")
m.press("left")
check(rows()[6] == ("Porch", "off") and wait_for(lambda: ("light/turn_off", {"entity_id": "light.porch"}) in calls[n:]),
      "left: off")
go("Fan plug"); n = len(calls)
m.press("a")
check(rows()[7] == ("Fan plug", "on") and wait_for(lambda: ("switch/turn_on", {"entity_id": "switch.fan_plug"}) in calls[n:]),
      "a plug: switch.turn_on")

# all lights off (not the plug)
time.sleep(1.0)
go("All lights off"); n = len(calls)
on_before = [x for x in m.lights.lights() if x["on"] and x["kind"] == "light"]
m.press("a")
check(m.msg == "All lights off" and rows()[0] == ("All lights off", "all off"), f"all off at once ({m.msg}, {rows()[0]})")
check(wait_for(lambda: len(calls) > n) and calls[n][0] == "light/turn_off"
      and sorted(calls[n][1]["entity_id"]) == sorted(x["entity"] for x in on_before), f"...one call for those on: {calls[n:]}")
check(rows()[7] == ("Fan plug", "on"), "...the plug left on")
m.press("a")
check(m.msg == "They're all off already", "again: nothing to do")

# scenes
go("Scenes"); m.press("a")
check([x["title"] for x in m.tab_items()] == ["Morning", "Movie night"] and m.lights_scenes, "the scenes, in their folder")
snap("3_scenes")
check(m.where_text() == "Home › Lights › Scenes", f"web page: {m.where_text()}")
m.sels[li] = 1; n = len(calls)
m.press("a")
check(m.msg == "Movie night" and wait_for(lambda: ("scene/turn_on", {"entity_id": "scene.movie_night"}) in calls[n:]),
      "A: the scene set")
m.press("b")
check(not m.lights_scenes and m.tab_items()[m.sels[li]]["title"] == "Scenes" and m.tab == li, "B: back to the lights")

# changed elsewhere (a wall switch): picked up
with lock:
    find("light.kitchen")["state"] = "on"; find("light.kitchen")["attributes"]["brightness"] = 64
check(wait_for(lambda: dict(rows()).get("Kitchen") == "25%", 5), "a change made elsewhere: shown")

# leaving: what's pressed still goes, then it stops asking
go("Kitchen"); n = len(calls)
world["slow"] = 0.5
m.press("a"); m.press("b")
check(m.tab == tvi and not m.lights.running, "B: back, and it stops")
check(wait_for(lambda: ("light/turn_off", {"entity_id": "light.kitchen"}) in calls[n:], 4), "...the A pressed just before still sent")
world["slow"] = 0.0
time.sleep(0.3)
k = len(calls)
time.sleep(1.5)
check(m.lights.thread is None, "...and its thread's done")

# named in the file, in its order, a fan among them
conf(f"url = 127.0.0.1:{PORT}\ntoken = {TOKEN}\nlights = light.porch, switch.adguard_protection, light.nothing_here\n")
go("Lights"); m.press("a")
check(wait_for(lambda: m.lights.found and len(m.tab_items()) == 4), "named: found")
print("named:", rows())
check(rows() == [("All lights off", "all off"), ("Porch", "off"), ("AdGuard protection", "on"),
                 ("light.nothing_here", "not answering")], "the file's, in its order")
m.press("b")

# a wrong token; nothing there
conf(f"url = 127.0.0.1:{PORT}\ntoken = wrong\n")
go("Lights"); m.press("a")
check(wait_for(lambda: m.lights.error), "wrong token: said")
check(m.lights_empty() == ("Couldn't get your lights", "Home Assistant didn't accept the token"), f"{m.lights_empty()}")
check(m.list_hints()[0] == ("A", "Try again"), "A: try again")
snap("4_badtoken")
conf(f"url = 127.0.0.1:{PORT}\ntoken = {TOKEN}\n")
m.load_tab(li)
m.press("a")
check(wait_for(lambda: m.lights.found and not m.lights.error and m.tab_items()), "fixed, A: there")
m.press("b")
srv.shutdown()

# home: it stops
conf(f"url = 127.0.0.1:1\ntoken = {TOKEN}\n")
go("Lights"); m.press("a")
check(wait_for(lambda: m.lights.error and "Can't reach" in m.lights.error), f"unreachable: {m.lights.error}")
m.go_home()
check(not m.lights.running, "home: it stops")

from PIL import Image
sheet = Image.new("RGB", (1290, 970), (80, 80, 80))
for k, name in enumerate(["1_lights", "2_dimmed", "3_scenes", "4_badtoken"]):
    sheet.paste(shots[name], ((k % 2) * 650, (k // 2) * 490))
sheet.save(S + "/sheet.png")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
