import io, os, sys, time, shutil, json, math, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/t16"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
im = Image.new("RGB", (1600, 1000), (30, 80, 120))
dd = ImageDraw.Draw(im)
for k in range(0, 1000, 8):
    dd.line((0, k, 1600, k), fill=(30 + k // 12, 80 + k // 20, 140 - k // 12))
dd.polygon([(0, 800), (400, 420), (800, 760), (1200, 380), (1600, 700), (1600, 1000), (0, 1000)], fill=(40, 60, 50))
im.save(HOME + "/Pictures/mountains.jpg")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
calls = []


def fake_json(url):
    calls.append(url)
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    if "geocoding-api" in url:
        name = q["name"][0].lower()
        if "nowhere" in name:
            return {}
        return {"results": [
            {"name": "Portland", "admin1": "Oregon", "country_code": "US", "latitude": 45.5152, "longitude": -122.6784},
            {"name": "Portland", "admin1": "Texas", "country_code": "US", "latitude": 27.88, "longitude": -97.32},
            {"name": "Portland Vale", "admin1": "Victoria", "country_code": "AU", "latitude": -38.34, "longitude": 141.6}]}
    if "ipapi.co" in url:
        return {"latitude": 39.7392, "longitude": -104.9903, "city": "Denver", "region": "Colorado", "country_code": "US"}
    if "api.open-meteo.com" in url:
        f = q.get("temperature_unit", ["c"])[0] == "fahrenheit"
        c2 = (lambda v: v) if not f else (lambda v: v * 9 / 5 + 32)
        base = time.strftime("%Y-%m-%dT%H")
        t0 = time.mktime(time.strptime(base, "%Y-%m-%dT%H"))
        times = [time.strftime("%Y-%m-%dT%H:%M", time.localtime(t0 + h * 3600)) for h in range(-2, 30)]
        codes = [0, 1, 2, 3, 61, 63, 80, 95, 2, 1, 0, 0] * 3
        return {"current": {"time": base + ":30", "temperature_2m": c2(21.7), "apparent_temperature": c2(20.9),
                            "relative_humidity_2m": 64, "weather_code": 2, "wind_speed_10m": 9.4,
                            "wind_direction_10m": 250, "is_day": 1, "precipitation": 0},
                "hourly": {"time": times, "temperature_2m": [c2(21 - abs(h - 3) * 0.8) for h in range(32)],
                           "weather_code": codes[:32], "precipitation_probability": [10] * 32,
                           "is_day": [1 if 6 <= (int(t[11:13])) < 19 else 0 for t in times]},
                "daily": {"time": [time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * i)) for i in range(7)],
                          "weather_code": [2, 61, 95, 3, 0, 71, 45],
                          "temperature_2m_max": [c2(v) for v in (24, 19, 17, 20, 26, 3, 15)],
                          "temperature_2m_min": [c2(v) for v in (15, 13, 12, 13, 16, -4, 9)],
                          "sunrise": ["2026-10-11T06:52"] * 7, "sunset": ["2026-10-11T18:21"] * 7,
                          "precipitation_probability_max": [10, 70, 90, 20, 0, 40, 10]}}
    if "api.weather.gov/points" in url:
        return {"properties": {"forecast": "https://api.weather.gov/gridpoints/SGX/57,14/forecast"}}
    if "api.weather.gov/gridpoints" in url:
        return {"properties": {"periods": [
            {"name": "Tonight", "detailedForecast": "Partly cloudy, with a low around 59. West wind around 5 mph becoming light and variable."},
            {"name": "Monday", "detailedForecast": "A chance of showers after 11am. Mostly cloudy, with a high near 66. Chance of precipitation is 40%."},
            {"name": "Monday Night", "detailedForecast": "Showers likely. Cloudy, with a low around 57."},
            {"name": "Tuesday", "detailedForecast": "Thunderstorms possible. Mostly cloudy, with a high near 63."}]}}
    raise OSError("offline: " + url)


g.fetch_json = fake_json
g.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
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
print("apps:", [a[0] for a in m.home_apps()])
snap("home_plain")

def open_app(name):
    m.home_sel = [a[0] for a in m.home_apps()].index(name); m.press("a")

# Settings
open_app("Settings")
m.set_sel = [k for k, _, _ in g.SETTINGS].index("wallpaper")
snap("settings")
m.press("right"); print("background:", m.setting("wallpaper"))      # Dusk
m.press("down"); m.press("right"); m.press("right"); print("accent:", m.setting("accent"), g.ACCENT)
m.press("down"); m.press("right"); print("clock:", m.setting("clock"))
snap("settings_changed")
m.press("b"); print("B ->", m.view); snap("home_dusk_24h")

# location: Weather's settings (START), a town typed with the d-pad keyboard
assert "location" not in [k for k, _, _ in g.SETTINGS] and "units" not in [k for k, _, _ in g.SETTINGS]
open_app("Weather")
m.press("start"); m.press("a")
print("page:", m.wx_menu, [r[1] for r in m.wx_rows()])
m.press("down"); m.press("a")
print("view:", m.view, m.kb["title"])
for word in ("port", " ", "land"):
    for ch in word:
        if ch == " ":
            m.press("y"); continue
        r = next(i for i, row in enumerate(g.KEY_ROWS) if ch in row)
        m.kb["r"], m.kb["c"] = r, g.KEY_ROWS[r].index(ch)
        m.press("a")
snap("keyboard")
print("typed:", repr(m.kb["text"]))
m.press("start")
assert wait_for(lambda: m.loc_results)
print("results:", [r[1] for r in m.wx_rows()][2:])
snap("location_results")
m.press("a")                                       # first result is picked already
print("location:", m.setting("location"))
assert wait_for(lambda: m.weather.data and not m.weather.busy)
print("weather:", m.weather.data["temp"], m.weather.data["units"], "| nws:", len(m.weather.nws))

# Find me
m.press("a"); m.press("a")                         # (Weather's settings: Location, then Find me)
assert wait_for(lambda: m.setting("location")["name"] == "Denver" and m.wx_menu == "menu")
m.press("b"); m.press("b")                         # (the settings closed, then home)
assert m.view == "home", m.view
print("found:", g.place_text(m.setting("location")))
# back to Portland
m.set_setting("location", {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.5152, "lon": -122.6784})
m.weather_changed(); assert wait_for(lambda: m.weather.data and not m.weather.busy)

# background: a picture
open_app("Settings")
m.set_sel = [k for k, _, _ in g.SETTINGS].index("wallpaper")
for _ in range(10):
    if m.setting("wallpaper") == "Picture":
        break
    m.press("right")
m.press("a"); print("picking:", m.picking, g.LIBRARY[m.tab]["name"], m.list_hints())
m.press("a"); print("after pick:", g.LIBRARY[m.tab]["name"], m.setting("wallpaper"), os.path.basename(m.setting("picture")))
snap("settings_picture")
m.press("b"); snap("home_picture")

# Weather app
m.set_setting("clock", "12-hour")
m.set_setting("wallpaper", "Aurora")
snap("home_aurora")
open_app("Weather")
snap("weather_now")
m.press("right"); snap("weather_week")
m.press("right"); snap("weather_words")
m.press("right"); print("pages wrap to:", m.wx_pages()[m.wx_page])
# Celsius
m.press("start"); m.press("down"); m.press("right"); m.press("start")   # (Weather's settings: Temperature)
assert wait_for(lambda: m.weather.data and m.weather.data["units"] == "C" and not m.weather.busy)
print("units:", m.setting("units"), m.weather.data["temp"])
snap("weather_c")
# no location
m.set_setting("location", None); m.weather.reset(); snap("weather_none")
m.press("a"); assert wait_for(lambda: m.setting("location") and m.setting("location")["name"] == "Denver")
print("Find me from Weather:", g.place_text(m.setting("location")))
# saved and loaded again
m.save_state()
m2 = g.Media(); print("reloaded:", m2.setting("units"), m2.setting("wallpaper"), m2.setting("accent"),
                      g.place_text(m2.setting("location")), "| boot to home:", m2.boot_media)

# all wallpapers
sheet = Image.new("RGB", (7 * 170 + 10, 120), (80, 80, 80))
for k, name in enumerate(g.WALLPAPERS):
    w = g.wallpaper(name, (640, 480), HOME + "/Pictures/mountains.jpg").resize((160, 120))
    sheet.paste(w, (10 + k * 170, 0))
sheet.save(SP + "/out/wallpapers.png")

W, H = 640, 480
order = ["home_plain", "settings", "settings_changed", "home_dusk_24h", "keyboard", "location_results",
         "settings_picture", "home_picture", "home_aurora", "weather_now", "weather_week", "weather_words",
         "weather_c", "weather_none"]
cols = 2
rows = (len(order) + 1) // 2
out = Image.new("RGB", (W * cols + 10, (H + 10) * rows - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/settings_weather.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
