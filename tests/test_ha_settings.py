"""Home Assistant set up on the Pi: the TV Remote and Lights say so and A opens its settings; Settings has them too
(the Home tab hasn't a Settings of its own); the address typed (and then the token, straight after), saved in
homeassistant.txt
(yours only, the rest of it kept), checked against a pretend Home Assistant (a wrong token said so), the TV Remote
working after; Forget (A twice). Pictures of each."""
import json, os, shutil, stat, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_ha_settings"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
sys.path.insert(0, TESTS)
import pietato_all as g

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "a" * 140
asked = []


class HA(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        asked.append(self.path)
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self.reply(401, {"message": "Unauthorized"})
        if self.path == "/api/":
            return self.reply(200, {"message": "API running."})
        if self.path == "/api/config":
            return self.reply(200, {"location_name": "Our House", "version": "2026.10.1"})
        if self.path == "/api/states":
            return self.reply(200, [
                {"entity_id": "media_player.living_room_tv", "state": "on",
                 "attributes": {"friendly_name": "Living Room TV", "volume_level": 0.3}},
                {"entity_id": "remote.living_room_tv", "state": "on", "attributes": {"friendly_name": "Living Room TV"}},
                {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen",
                                                                              "brightness": 128}}])
        if self.path.startswith("/api/states/"):
            return self.reply(200, {"entity_id": self.path.rsplit("/", 1)[1], "state": "on",
                                    "attributes": {"friendly_name": "Living Room TV", "volume_level": 0.3}})
        return self.reply(404, {"message": "no"})

    def do_POST(self):
        asked.append(self.path)
        return self.reply(200, [])


srv = ThreadingHTTPServer(("127.0.0.1", 18123), HA)
threading.Thread(target=srv.serve_forever, daemon=True).start()
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))
m.coder_addresses = lambda: ("http://pi.local:5432", "http://192.168.1.50:5432", False)


def draw(name):
    m.dirty = True
    m.flush()
    shots[-1].save(f"{S}/{name}.png")


def settle(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def typed(text):
    """What's typed in the box that's up, and done."""
    check(m.view == "keys", f"...a box to type in: {m.kb['title'] if m.kb else None!r}")
    m.kb["text"] = text
    m.close_keyboard(True)


ha_tab = m.tab_index("group") if g.LIBRARY[m.tab_index("group")]["name"] == "Home" else \
    next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
ri, li = m.tab_index("remote"), m.tab_index("lights")

# ---- not set up: the TV Remote says so, A opens the settings ------------------------------------------------------
m.tab, m.view = ri, "list"
m.load_tab(ri)
draw("remote_not_set")
check(not m.hass.configured and m.ha_menu is None, "the TV Remote, not set up")
m.press("a")
check(m.ha_menu is not None and m.ha_menu["sel"] == 0, "A: Home Assistant's settings, on Address")
draw("settings_empty")
rows = m.ha_rows()
check([r[0] for r in rows] == ["url", "token", "check"] and rows[0][2] == "Not set" and rows[1][2] == "Not set"
      and rows[0][1] == "Home Assistant IP address",
      f"...Home Assistant IP address and token not set, nothing to forget: {[(r[1], r[2]) for r in rows]}")

# the address, then the token straight after
m.press("a")
check(m.kb and m.kb["text"] == "" and m.kb["title"].startswith("Home Assistant IP address"),
      f"the IP address box: empty, to type it in ({m.kb['title']!r}, {m.kb['text']!r})")
typed("not an address!")
check(toasts and "isn't an address" in toasts[-1], f"...not an address: {toasts[-1]!r}")
m.press("a")
typed("192.168.1.20")
check(m.hass.url == "http://192.168.1.20:8123" and m.view == "keys" and "token" in m.kb["title"],
      f"just its IP address: on Home Assistant's own port, 8123 ({m.hass.url}), and the token's box straight after")
m.close_keyboard(False)
m.ha_menu["sel"] = 0
m.press("a")
check(m.kb and m.kb["text"] == "192.168.1.20:8123", f"...A again: the box starts with it, to change ({m.kb['text']!r})")
typed("127.0.0.1:18123")
check(m.hass.url == "http://127.0.0.1:18123" and m.view == "keys" and "token" in m.kb["title"],
      "an address with its port: kept as it is, and the token's box straight after")
path = HOME + "/homeassistant.txt"
check(os.path.exists(path) and stat.S_IMODE(os.stat(path).st_mode) == 0o600, "...in homeassistant.txt, yours only")
typed("short")
check("too short" in toasts[-1], f"a token that's too short: {toasts[-1]!r}")
m.ha_menu["sel"] = 1
m.press("a")
typed("wrong-" + TOKEN[6:])
check(settle(lambda: m.ha_said and m.ha_said[0] is False), f"a wrong token: checked ({m.ha_said})")
check("didn't accept the token" in m.ha_said[1], "...and said so")
draw("settings_wrong")
m.press("up") if m.ha_menu["sel"] != 1 else None
m.ha_menu["sel"] = 1
m.press("a")
typed(" " + TOKEN[:60] + "\n" + TOKEN[60:] + " ")             # (pasted with spaces and a break in it)
check(settle(lambda: m.ha_said and m.ha_said[0] is True), f"the right one: {m.ha_said}")
check(m.ha_said[1] == "Connected to Our House (2026.10.1)", "...said who it is")
draw("settings_ok")
text = open(path).read()
check(f"token = {TOKEN}" in text and "url = http://127.0.0.1:18123" in text, "...both saved")
check(m.hass.configured and m.lights.configured, "the TV Remote and Lights use them")
m.press("b")
check(m.ha_menu is None and m.tab == ri and m.view == "list", "B: back to the TV Remote")
check(settle(lambda: m.hass.tvstate.get("name") == "Living Room TV", 15), f"...which finds the TV: {m.hass.tvstate}")
draw("remote_working")
m.hass.stop()

# the rest of homeassistant.txt kept
with open(path, "a") as f:
    f.write("lights = light.kitchen\n# a note of yours\n")
os.chmod(path, 0o600)

# ---- the Home tab: its apps, and no Settings of its own (the TV Remote and Lights ask; Settings > Home has them) -------
m.go_home()
m.tab, m.view = ha_tab, "list"
m.load_tab(ha_tab)
items = m.tab_items(ha_tab)
check([it["title"] for it in items] == ["TV Remote", "Lights", "Pi-hole", "Web", "Control another Pietato"],
      f"the Home tab: its apps, no "
      f"Settings of its own ({[it['title'] for it in items]})")
draw("tab")

# ---- Settings > Home Assistant ----------------------------------------------------------------------------------------
si = m.tab_index("settings")
m.tab, m.view, m.set_page = si, "list", "root"
m.load_tab(si)
keys = [k for k, _, _ in m.settings_root_rows()]
check("homeassistant" in keys and keys.index("homeassistant") == keys.index("friend") + 1,
      f"Settings: Home, after Bot ({keys})")
m.set_sel = keys.index("homeassistant")
check(m.ha_value() == "127.0.0.1:18123", f"...its row says where it is ({m.ha_value()!r})")
draw("settings_root")
m.press("a")
check(m.ha_menu is not None and m.ha_menu["sel"] == 2, "A: its settings, on Check (both set)")
rows = m.ha_rows()
check([r[0] for r in rows] == ["url", "token", "check", "forget"] and rows[1][2] == "Saved", "...the token: Saved")
# Forget: A twice
m.ha_menu["sel"] = 3
m.press("a")
check(os.path.exists(path) and m.hass.configured, "Forget, once: not yet")
draw("settings_forget")
m.press("a")
text = open(path).read()
check(not m.hass.configured and "token = \n" in text + "\n" and TOKEN not in text, "...twice: forgotten")
check("lights = light.kitchen" in text and "# a note of yours" in text, "...the rest of the file kept")
check(toasts[-1] == "Forgot Home Assistant" and m.ha_menu["sel"] == 0, "...and said so")
m.press("b")
check(m.ha_menu is None and m.tab == si, "B: back to Settings")

# ---- Lights, not set up: A opens them too; L and R close them --------------------------------------------------------
m.tab, m.view = li, "list"
m.load_tab(li)
draw("lights_not_set")
check(m.lights_empty()[0] == "Connect Home Assistant", "Lights, not set up: says so")
m.press("a")
check(m.ha_menu is not None, "A: Home Assistant's settings")
m.press("r")
check(m.ha_menu is None and m.tab != li, "R: closed, and on to the next tab")
m.hass.stop(); m.lights.stop()
srv.shutdown()
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
