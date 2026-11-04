"""The web page's Settings on the Pi's side (media mode's web_settings and web_settings_do): what it says, that
passwords and tokens never go to the page, and each setting checked before it's kept, in the file it belongs in (the
private ones yours only)."""
import json, os, shutil, stat, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_websettings"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Games", "Pictures/Trips", "Documents"):
    os.makedirs(f"{HOME}/{d}")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
sys.path.insert(0, SP)
import gk_static; gk_static.use_home(g, HOME)
def offline(url, timeout=15):
    time.sleep(0.3)
    raise OSError("offline")


g.fetch_json = offline
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def text(name):
    try:
        return open(f"{HOME}/{name}").read()
    except OSError:
        return ""


for n in ("Tetris.gb", "Mario Kart DS.nds"):
    open(f"{HOME}/Games/{n}", "wb").write(b"\0" * 64)
Image.new("RGB", (64, 48), (200, 90, 40)).save(f"{HOME}/Pictures/Sunset.jpg")
Image.new("RGB", (64, 48), (40, 90, 200)).save(f"{HOME}/Pictures/Trips/Lake.png")
open(f"{HOME}/Documents/notes.jpg", "wb").write(b"not really")

# secrets of every kind, already there
TOKEN = "eyJhbGciOiJIUzI1NiJ9." + "Q" * 150
open(f"{HOME}/homeassistant.txt", "w").write(f"url = http://ha.example.lan:8123\ntoken = {TOKEN}\nlights = light.desk\n"
                                             "# a note of yours\n")
open(f"{HOME}/jellyfin.txt", "w").write("server = 10.0.0.9:8096\nuser = sam\npassword = jf-Secret-77\n")
open(f"{HOME}/webui.txt", "w").write("password = web-Secret-55\nhosts = tv.example.lan\n")
open(f"{HOME}/pihole.txt", "w").write("address = http://10.0.0.2:8080\npassword = ph-Secret-33\n")
for f in ("homeassistant.txt", "jellyfin.txt", "webui.txt", "pihole.txt"):
    os.chmod(f"{HOME}/{f}", 0o600)

# a pretend NetworkManager
nmstate = {"radio": True, "active": "HomeNet", "profiles": {"HomeNet": "HomeNet"}}


def fake_nm(args, timeout=20):
    time.sleep(0.15)                             # (NetworkManager takes a moment)
    if args[:2] == ["radio", "wifi"]:
        if len(args) == 3:
            nmstate["radio"] = args[2] == "on"
            return True, "", ""
        return True, "enabled\n" if nmstate["radio"] else "disabled\n", ""
    if "device" in args and "list" in args:
        return True, ("*:HomeNet:80:WPA2\n :Cafe:50:\n" if nmstate["radio"] else ""), ""
    if args[-2:] == ["connection", "show"]:
        return True, "".join(f"{n}:802-11-wireless\n" for n in nmstate["profiles"]), ""
    if args[:2] == ["-g", "802-11-wireless.ssid"]:
        return True, nmstate["profiles"][args[-1]] + "\n", ""
    if args[:3] == ["device", "wifi", "connect"]:
        if args[3] == "Cafe":
            nmstate["profiles"]["Cafe"] = "Cafe"
            nmstate["active"] = "Cafe"
            return True, "", ""
        return False, "", "Error: Connection activation failed: (7) Secrets were required, but not provided."
    if args[:3] == ["connection", "delete", "id"]:
        nmstate["profiles"].pop(args[3], None)
        return True, "", ""
    print("nm: unexpected", args, flush=True)
    return False, "", "unexpected"


g.nm = fake_nm
g.run_out = lambda cmd, timeout=3: f"\tSSID: {nmstate['active']}\n" if cmd[:2] == ["iw", "dev"] else ""

m = g.Media()
m.toast = lambda text, secs=4: None
for i in range(len(g.LIBRARY)):
    if g.LIBRARY[i]["type"] not in ("channels", "camera", "system", "plex", "jellyfin"):
        m.load_tab(i)


def do(key, value):
    return m.web_settings_do({"cmd": "settings", "key": key, "value": value})


def rows():
    out = {}
    for sec in m.web_settings()["sections"]:
        for r in sec["rows"]:
            out[r["key"]] = r
    return out


# ---- what it says ---------------------------------------------------------------------------------------------------
out = m.web_settings()
ids = [s["id"] for s in out["sections"]]
check(ids == ["screen", "sound", "start", "share", "wifi", "weather", "ha", "pihole", "plex", "jellyfin", "bot",
              "character", "games", "cheevos", "sim", "finance", "web"], f"the sections: {ids}")
every = json.dumps(out)
for secret in (TOKEN, TOKEN[30:70], "jf-Secret-77", "web-Secret-55", "ph-Secret-33"):
    check(secret not in every, f"...never in what the page is sent: {secret[:12]}…")
r = rows()
check(r["ha_token"]["set"] is True and r["jf_password"]["set"] is True and r["web_password"]["set"] is True,
      "...only that there's a token or a password")
check(r["ha_url"]["value"] == "ha.example.lan:8123" and r["ha_lights"]["value"] == "light.desk",
      f"Home Assistant: its address ({r['ha_url']['value']!r}) and lights")
check(r["ph_where"]["value"] == "10.0.0.2:8080" and "ph_add" not in r, "Pi-hole: where it is")
check(r["jf_server"]["value"] == "10.0.0.9:8096" and r["jf_user"]["value"] == "sam", "Jellyfin: server and user")
check(r["web_hosts"]["value"] == "tv.example.lan", "this page: its other names")
check(sorted(k for k in r if k.startswith("game_picture_")) == ["game_picture_gb", "game_picture_nds"],
      f"Games: a picture setting for each console you have games for ({[k for k in r if k.startswith('game_pic')]})")
check("ds_screens" in r and "ds_touch" in r, "...the DS's own two, as there are DS games")
check("resolution" not in r, "no Resolution without a TV or monitor's sizes")
check(r["accent"]["colours"]["Blue"].startswith("#") and len(r["accent"]["colours"]) == len(r["accent"]["choices"]),
      "Accent: each with its colour")
check(r["f_model"].get("list") is True and r["f_model"]["choices"] == [], "the Bot's model: a list, empty for now")
if "f_voice" in r:
    check(r["f_voice"]["tone"] == "" and not r["f_voice"]["status"], f"the Bot's voice: nothing under way ({r['f_voice']})")
m.ears.got_error = "Couldn't get Vosk"
r2 = rows()
if "f_listen" in r2:
    check(r2["f_listen"]["tone"] == "bad" and r2["f_listen"]["status"] == "Couldn't get Vosk",
          f"listening: a problem said in red ({r2['f_listen'].get('status')!r})")
m.ears.got_error = None

# ---- choices --------------------------------------------------------------------------------------------------------
check(do("clock", "24-hour") == {"ok": True} and m.setting("clock") == "24-hour", "Clock: 24-hour")
check("error" in do("clock", "25-hour") and m.setting("clock") == "24-hour", "...not one of its choices: refused")
check("error" in do("wallpaper", "Picture"), "Background: Picture, with no picture yet: refused")
check(do("game_picture_gb", "Sharp") == {"ok": True} and m.game_picture("gb") == "Sharp", "Game Boy: Sharp")
check("error" in do("game_picture_psx", "Sharp"), "...a console with no games here: refused")
check(do("units", "°C") == {"ok": True} and m.setting("units") == "°C", "Temperature: °C")
for bad in ("", "nope", "__init__", "choice", "pick", "settings_now", "1x"):
    check("error" in do(bad, "x"), f"no such setting: {bad!r}")

# ---- the background: one of your pictures ---------------------------------------------------------------------------
check(do("picture", f"{HOME}/Pictures/Trips/Lake.png") == {"ok": True}
      and m.setting("picture") == f"{HOME}/Pictures/Trips/Lake.png" and m.setting("wallpaper") == "Picture",
      "a picture of yours: the background")
for bad in (f"{HOME}/Documents/notes.jpg", f"{HOME}/Pictures/../Documents/notes.jpg", "/etc/passwd",
            f"{HOME}/Pictures/none.jpg", "Pictures/Sunset.jpg", {"path": "x"}):
    check("error" in do("picture", bad) and m.setting("picture").endswith("Lake.png"), f"...not {str(bad)[-30:]!r}")
os.symlink("/etc/hostname", f"{HOME}/Pictures/sneaky.jpg")
check("error" in do("picture", f"{HOME}/Pictures/sneaky.jpg"), "...nor a link out of Pictures")

# ---- Weather's place -------------------------------------------------------------------------------------------------
place = {"name": "Springfield", "admin": "Illinois", "country": "US", "lat": "39.8", "lon": -89.64,
         "label": "Springfield, Illinois, US", "evil": "x" * 500}
got = do("location", place)
loc = m.setting("location")
check(got.get("ok") and loc == {"name": "Springfield", "admin": "Illinois", "country": "US", "lat": 39.8,
                                "lon": -89.64}, f"a town: kept as a place is ({loc})")
for bad in ({"name": "X", "lat": 95, "lon": 0}, {"name": "X", "lat": "a", "lon": 0}, {"lat": 1, "lon": 2}, "Paris"):
    check("error" in do("location", bad), f"...not {bad}")
check(do("location", "find") == {"ok": True} and m.loc_status == "Finding you…", "Find me: finding you")
end = time.time() + 5
while m.loc_status == "Finding you…" and time.time() < end:
    time.sleep(0.05)
r = rows()
check(r["location"]["tone"] == "bad" and r["location"]["status"], f"...offline: said so ({r['location']['status']!r})")
check(m.web_find_place("")["error"] and "error" in m.web_find_place("Springfield"), "towns: none to ask, or offline")

# ---- Home Assistant ----------------------------------------------------------------------------------------------------
check("error" in do("ha_url", "not an address!"), "Home Assistant: not an address, refused")
check(do("ha_url", "homeassistant.local:8123").get("ok") and "url = http://homeassistant.local:8123" in text(
    "homeassistant.txt"), "...homeassistant.local:8123: saved")
check(mode(f"{HOME}/homeassistant.txt") == 0o600, "...homeassistant.txt yours only")
check("error" in do("ha_token", "short"), "a token that's too short: refused")
new = "eyJ0eXAiOiJKV1Qi." + "Z" * 160
check(do("ha_token", " " + new[:40] + "\n" + new[40:] + " ").get("ok") and f"token = {new}\n" in text(
    "homeassistant.txt"), "...a new one, pasted with a break in it: saved whole")
check(m.hass.token == new and m.lights.token == new, "...the TV Remote and Lights use it now")
check("error" in do("ha_lights", "kitchen") and "error" in do("ha_lights", "light.kitchen; drop table"),
      "Lights: not entities, refused")
check(do("ha_lights", "Light.Kitchen, switch.fan_plug;light.kitchen\nlight.porch").get("ok")
      and "lights = light.kitchen, switch.fan_plug, light.porch" in text("homeassistant.txt"),
      "...light.kitchen, switch.fan_plug, light.porch: tidied, once each")
check(do("ha_lights", "").get("ok") and "lights = \n" in text("homeassistant.txt") + "\n", "...none: all of them")
check(do("ha_tv", "media_player.den_tv").get("ok") and "tv = media_player.den_tv" in text("homeassistant.txt"),
      "TVs: media_player.den_tv")
check(do("ha_token", "") == {"ok": True, "said": "Taken off"} and new not in text("homeassistant.txt"),
      "the token taken off")
check(do("ha_forget", True).get("said") == "Forgot Home Assistant" and "# a note of yours" in text("homeassistant.txt")
      and not m.hass.configured, "Forget Home Assistant: address and token gone, the rest kept")
r = rows()
check("ha_forget" not in r and r["ha_check"]["disabled"], "...nothing to forget or check now")

# ---- Pi-hole, Jellyfin, Plex ------------------------------------------------------------------------------------------------
check(do("ph_forget", True).get("said") == "Forgot your Pi-hole" and "ph_add" in rows(), "Forget your Pi-hole: the form")
check("error" in do("ph_add", {"url": "", "password": ""}), "...adding one with no address: refused")
check("error" in do("jf_server", "http://bad host/"), "Jellyfin: not an address, refused")
check(do("jf_server", "192.168.1.10:8096").get("ok") and "server = 192.168.1.10:8096" in text("jellyfin.txt"),
      "...its server")
check(do("jf_password", "").get("ok") and "jf-Secret-77" not in text("jellyfin.txt") and not rows()["jf_password"]["set"],
      "...its password taken off")
check(mode(f"{HOME}/jellyfin.txt") == 0o600, "...jellyfin.txt yours only")
check("error" in do("plex", "nonsense") and "error" in do("jellyfin", "nonsense"), "sign in: only in or out")

# ---- the Bot -----------------------------------------------------------------------------------------------------------------
check("error" in do("f_server", "http://x y"), "the Bot's computer: not an address, refused")
check("error" in do("f_model", "llama3"), "...a model it doesn't have: refused")
check("error" in do("f_chatter", "5"), "...not one of its choices: refused")
check(do("f_chatter", "60").get("ok") and "chatter = 60" in text("bot.txt"), "...Every hour")
check(do("f_name", "  Sam\n\tSmith ").get("ok") and "name = Sam Smith" in text("bot.txt"), "...what it calls you")
check("error" in do("bot_mode", "play") and do("bot_mode", "work").get("ok") and m.setting("bot_mode") == "work",
      "...its page: At work")

# ---- Finance --------------------------------------------------------------------------------------------------------------
check(do("fin_stocks", "aapl, ^gspc, brk-b, 7203.t, aapl").get("ok") and m.stocks.symbols() == [
    "AAPL", "^GSPC", "BRK-B", "7203.T"], f"Stocks: as Yahoo writes them, once each ({m.stocks.symbols()})")
check("error" in do("fin_stocks", "Berkshire Hathaway"), "...a company's name: refused")
check("error" in do("fin_stocks", ", ".join(f"S{k}" for k in range(21))), "...more than the tab has room for: refused")
check("error" in do("fin_coins", "bitcoin, Shiba Inu") and do("fin_coins", "bitcoin,shiba-inu").get("ok")
      and m.crypto.ids() == ["bitcoin", "shiba-inu"], "Coins: CoinGecko's ids, not names")

# ---- this web page ---------------------------------------------------------------------------------------------------------
check("error" in do("web_hosts", "tv.example.lan, bad host!"), "this page's names: not names, refused")
check(do("web_hosts", "tv.example.lan  pi.example.com").get("ok") and
      "hosts = tv.example.lan, pi.example.com" in text("webui.txt"), "...two, saved")
check(do("web_password", "").get("said") == "No password now" and "web-Secret-55" not in text("webui.txt"),
      "its password taken off")
check(do("web_password", "n3w-Pass").get("said") == "Your browser asks for it now" and "password = n3w-Pass" in text(
    "webui.txt") and mode(f"{HOME}/webui.txt") == 0o600, "...a new one: saved, webui.txt yours only")

# ---- WiFi --------------------------------------------------------------------------------------------------------------------
w = m.wifi


def wifi_settle():
    end = time.time() + 5
    while w["busy"] and time.time() < end:
        time.sleep(0.02)


check(do("wifi", {"do": "look"}) == {"ok": True}, "WiFi: look")
wifi_settle()
r = rows()["wifi"]
check([n["ssid"] for n in r["nets"]] == ["HomeNet", "Cafe"] and r["here"] == "HomeNet" and r["nets"][0]["saved"],
      f"...HomeNet (here, saved) and Cafe ({r['nets']})")
check("error" in do("wifi", {"do": "connect", "ssid": "Cafe", "password": "short"}), "a password under 8: refused")
check("error" in do("wifi", {"do": "connect", "ssid": ""}), "...no network: refused")
check("error" in do("wifi", {"do": "forget", "ssid": "Cafe"}), "forget one that isn't saved: refused")
check(do("wifi", {"do": "connect", "ssid": "Cafe"}) == {"ok": True}, "Cafe (no password): connecting")
check("error" in do("wifi", {"do": "connect", "ssid": "Cafe"}), "...one thing at a time")
wifi_settle()
r = rows()["wifi"]
check(r["status"] == "Connected to Cafe" and r["tone"] == "ok", f"...said how it went ({r['status']!r}, {r['tone']})")
do("wifi", {"do": "connect", "ssid": "Locked", "password": "wrong-password", "hidden": True})
wifi_settle()
r = rows()["wifi"]
check(r["status"].startswith("Locked:") and r["tone"] == "bad", f"a wrong password: said so ({r['status']!r})")
w["said"] = (True, "Connected to Cafe", time.monotonic() - 60)
check(rows()["wifi"]["status"] == "", "...said for a while, then not")
check(do("wifi", {"do": "radio", "on": False}) == {"ok": True}, "WiFi off")
wifi_settle()
r = rows()["wifi"]
check(r["radio"] is False and r["nets"] == [] and not nmstate["radio"], "...off")
check(do("wifi", {"do": "radio", "on": True}) == {"ok": True}, "...on again")
end = time.time() + 8
while (w["busy"] or not w["radio"]) and time.time() < end:
    time.sleep(0.05)
check(w["radio"] and nmstate["radio"], "...on")
w["status"] = "No networks found. X looks again"
check(rows()["wifi"]["status"] == "No networks found", "the Pi's own words, without its X")
check("error" in do("wifi", {"do": "dance"}), "...nothing else")
m.hass.stop(); m.lights.stop()
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
