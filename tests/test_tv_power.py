"""The TV Remote's Turn on and Turn off: both always in its More menu, each doing just what it says (never the other
way round, whatever the remote last heard), after asking Home Assistant how the TV is right then (a TV that's on is
left alone when you pick Turn on: some take "on" as a press of their power button); and saying the TV is on (or off)
only once Home Assistant says so, or that it didn't turn on; a Samsung asked again meanwhile, while it's still off (its
Wake-on-LAN can go astray). Mute and Unmute likewise. Switching TVs while one turns on says nothing about it. An arrow
held down on a slow TV doesn't get ahead of it (nothing more once you let go)."""
import json, os, sys, threading, time, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_tv_power"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.JELLYFIN_FILE = S + "/jellyfin.json"; g.SHRINK_FILE = S + "/shrink.json"
g.home_dir = lambda: HOME
g.HA_POLL = 0.5
g.HA_WATCH = 3
for t in g.LIBRARY:
    if t["type"] == "remote":
        t["files"] = [HOME + "/homeassistant.txt"]
import gk_static; gk_static.use_home(g, HOME)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


TOKEN = "eyJ.fake.token"
TVS = {"media_player.living_room_tv": {"name": "Living Room TV", "state": "on", "muted": False},
       "media_player.bedroom_tv": {"name": "Bedroom TV", "state": "on", "muted": False}}
world = {"on": "works", "delay": 1.0, "slow": 0}   # turning on: works (after delay), silent, second, 400, 500,
#                                                       toggle; and how long a button takes to reach the TV
calls = []


def states():
    out = []
    for eid, tv in TVS.items():
        out.append({"entity_id": eid, "state": tv["state"],
                    "attributes": {"friendly_name": tv["name"], "device_class": "tv", "volume_level": 0.2,
                                   "is_volume_muted": tv["muted"], "source": "TV", "source_list": ["TV", "HDMI 1"]}})
        out.append({"entity_id": "remote." + eid.split(".")[1], "state": "on", "attributes": {"friendly_name": tv["name"]}})
    return out


def later(secs, fn):
    threading.Timer(secs, fn).start()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/states":
            return self.reply(states())
        if self.path.startswith("/api/states/"):
            eid = self.path.rsplit("/", 1)[1]
            st = next((x for x in states() if x["entity_id"] == eid), None)
            return self.reply(st) if st else self.reply({"message": "Entity not found."}, 404)
        self.reply({"message": "nope"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        svc = self.path.replace("/api/services/", "")
        calls.append((svc, body))
        tv = TVS.get(body.get("entity_id"))
        if svc == "media_player/turn_on":
            how = world["on"]
            if how in ("400", "500"):
                return self.reply({"message": "Entity does not support this action."}, int(how))
            if how == "works" or (how == "second" and len(power_calls()) >= 2):
                later(world["delay"], lambda: tv.update(state="on"))
            elif how == "toggle":                      # (its "on" is a press of its power button)
                tv["state"] = "off" if tv["state"] == "on" else "on"
        elif svc == "media_player/turn_off":
            later(0.5, lambda: tv.update(state="off"))
        elif svc == "media_player/volume_mute":
            tv["muted"] = body["is_volume_muted"]
        elif svc == "remote/send_command":
            time.sleep(world["slow"])
        self.reply([])


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with open(HOME + "/homeassistant.txt", "w") as f:
    f.write(f"url = 127.0.0.1:{srv.server_address[1]}\ntoken = {TOKEN}\n")


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        if c():
            return True
        time.sleep(0.05)
    return False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
hai = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab, m.view = hai, "list"
m.load_tab(hai)
m.sels[hai] = [x["title"] for x in m.tab_items()].index("TV Remote")
m.press("a")
check(wait_for(lambda: m.hass.found and m.hass.tvstate.get("state") == "on"), "the TV Remote: its TV found, on")
TV = m.hass.tv


def options():
    return m.remote_options()


def pick(label, before=None):
    """SELECT, the More menu's label, A (before: done just before A, as if it happened meanwhile)"""
    m.press("select")
    labels = [o[0] for o in options()]
    m.remote_more["sel"] = labels.index(label)
    if before:
        before()
    m.press("a")


def power_calls():
    return [c[0] for c in calls if c[0] in ("media_player/turn_on", "media_player/turn_off")]


opts = dict(options())
check(opts.get("Turn on") == ("power", "on") and opts.get("Turn off") == ("power", "off"),
      f"More: Turn on and Turn off, both, each saying what it does ({[o[0] for o in options()]})")
m.press("select"); m.dirty = True; m.flush(); FB.last.save(S + "/more.png"); m.press("b")

# the old trouble: the remote hadn't heard how the TV was yet (or heard wrong): Turn on turned it off
calls.clear()
pick("Turn on", before=lambda: m.hass.tvstate.pop("state", None))
check(wait_for(lambda: m.msg == "Your TV is already on") and power_calls() == [],
      f"Turn on, the remote not knowing yet, the TV on: says it's already on, sends nothing ({m.msg!r}, {power_calls()})")
calls.clear()
pick("Turn on", before=lambda: m.hass.tvstate.update(state="off"))
check(wait_for(lambda: m.msg == "Your TV is already on") and power_calls() == [],
      f"...the remote having heard it was off a moment ago: asks again, leaves it on ({m.msg!r}, {power_calls()})")

# Turn off: off, and said once it is
calls.clear()
pick("Turn off")
check(wait_for(lambda: m.msg == "Turning your TV off…") and power_calls() == ["media_player/turn_off"],
      f"Turn off: turning it off ({m.msg!r}, {power_calls()})")
check(wait_for(lambda: m.msg == "Your TV is off"), f"...and once Home Assistant says it's off: off ({m.msg!r})")
calls.clear()
pick("Turn off")
check(wait_for(lambda: m.msg == "Your TV is already off") and power_calls() == [],
      f"Turn off again: already off, nothing sent ({m.msg!r})")

# Turn on: on, said once it is
calls.clear()
world.update(on="works", delay=1.5)
pick("Turn on")
check(wait_for(lambda: m.msg == "Turning your TV on…") and power_calls() == ["media_player/turn_on"],
      f"Turn on: turning it on ({m.msg!r})")
time.sleep(0.6)
check(m.msg == "Turning your TV on…", "...not said to be on before Home Assistant says so")
check(wait_for(lambda: m.msg == "Your TV is on"), f"...then on, once it is ({m.msg!r})")
check(wait_for(lambda: m.hass.poll_every() == g.HA_POLL), "...and the remote asks as seldom as before")

# Turn on that doesn't: Home Assistant takes it, the TV stays off
TVS[TV]["state"] = "off"
world.update(on="silent")
wait_for(lambda: m.hass.tvstate.get("state") == "off")
calls.clear()
t0 = time.time()
pick("Turn on")
check(wait_for(lambda: m.msg == "Turning your TV on…"), "Turn on, a TV that won't wake: turning it on...")
check(wait_for(lambda: m.msg == "Your TV didn't turn on", t=10) and power_calls() == ["media_player/turn_on"],
      f"...then that it didn't, after a while ({m.msg!r} after {time.time() - t0:.1f} s)")

# Home Assistant can't turn it on at all
for code in ("400", "500"):
    world.update(on=code)
    calls.clear()
    pick("Turn on")
    check(wait_for(lambda: m.msg == "Home Assistant can't turn this TV on"),
          f"Home Assistant can't ({code}): says so ({m.msg!r})")

# a TV whose "on" is its power button, on: left alone
TVS[TV]["state"] = "on"
world.update(on="toggle")
wait_for(lambda: m.hass.tvstate.get("state") == "on")
calls.clear()
pick("Turn on", before=lambda: m.hass.tvstate.update(state="standby"))
time.sleep(0.8)
check(TVS[TV]["state"] == "on" and power_calls() == [], f"a TV whose on is its power button, on: stays on "
      f"({TVS[TV]['state']}, {power_calls()})")

# Mute, as picked, even if it changed meanwhile
calls.clear()
pick("Mute", before=lambda: TVS[TV].update(muted=True))
check(wait_for(lambda: [c for c in calls if c[0] == "media_player/volume_mute"])
      and [c[1]["is_volume_muted"] for c in calls if c[0] == "media_player/volume_mute"] == [True],
      f"Mute: muted, as picked (not the other way) ({[c for c in calls if 'mute' in c[0]]})")
TVS[TV]["muted"] = False

# switching TVs while one turns on: nothing said about it
TVS[TV]["state"] = "off"
world.update(on="silent")
wait_for(lambda: m.hass.tvstate.get("state") == "off")
pick("Turn on")
wait_for(lambda: m.msg == "Turning your TV on…")
pick("Switch to Bedroom TV")
check(wait_for(lambda: m.hass.tv == "media_player.bedroom_tv"), "switched to the other TV")
time.sleep(g.HA_WATCH + 1.5)
check(m.msg != "Your TV didn't turn on" and m.hass.watch is None, f"...and nothing said about the first one ({m.msg!r})")

pick("Switch to Living Room TV")
wait_for(lambda: m.hass.tv == TV and m.hass.tvstate.get("state"))

# a Samsung that doesn't wake at the first Wake-on-LAN: asked again, while it's still off
g.HA_WAKE_AGAIN = 1
TVS[TV]["state"] = "off"
world.update(on="second", delay=0.5)
wait_for(lambda: m.hass.tvstate.get("state") == "off")
calls.clear()
pick("Turn on")
check(wait_for(lambda: m.msg == "Your TV is on", t=6) and power_calls() == ["media_player/turn_on"] * 2,
      f"a Samsung that misses the first wake-up: asked again, then on ({m.msg!r}, {power_calls()})")
TVS[TV]["state"] = "off"
world.update(on="silent")
wait_for(lambda: m.hass.tvstate.get("state") == "off")
calls.clear()
pick("Turn on")
check(wait_for(lambda: m.msg == "Your TV didn't turn on", t=8), f"...one that never wakes: didn't, in the end ({m.msg!r})")
n = len(power_calls())
time.sleep(2.5)
check(2 <= n <= 4 and len(power_calls()) == n and set(power_calls()) == {"media_player/turn_on"},
      f"...asked again every so often till then, and no more after ({n}, then {len(power_calls())})")
g.HA_WAKE_AGAIN = 8

# an arrow held down on a slow TV: as fast as the TV takes them, and nothing more once you let go
world["slow"] = 0.4
calls.clear()
end = time.time() + 2.0
m.press("up")
while time.time() < end:
    time.sleep(0.05)
    m.press("up", repeat=True)
held = len([c for c in calls if c[0] == "remote/send_command"])
time.sleep(1.5)
after = len([c for c in calls if c[0] == "remote/send_command"])
check(3 <= held <= 7 and after - held <= 1, f"an arrow held 2 s on a TV taking 0.4 s a press: {held} sent, "
      f"{after - held} after letting go")
world["slow"] = 0

m.press("b")
time.sleep(0.6)
check(not m.hass.running, "B: back, and it stops asking")
print("ALL OK" if not fails else f"FAILED {len(fails)}", flush=True)
os._exit(0)
