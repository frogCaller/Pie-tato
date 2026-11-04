"""Weather's own settings (START on the Weather tab): where you are (found from the internet address, or a town typed
and picked) and °F or °C, no longer in Settings; B back, START closes, L R on to the next tab; the weather's footer
says START, and still credits Open-Meteo. And the pop-up keyboard: SELECT turns Caps on and off (every letter, till
it's off; ⇧ is still just the next one), and says so along the bottom."""
import json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw
S = SP + "/t_wx_settings"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
said = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (said.append(str(text)), real_text(self, xy, text, *a, **k))[1]
feet = []
PORTLAND = {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.5, "lon": -122.6}
DENVER = {"name": "Denver", "admin": "Colorado", "country": "US", "lat": 39.7, "lon": -105.0}
g.find_me = lambda: dict(DENVER)
g.geocode = lambda text: [dict(PORTLAND), {"name": "Portland", "admin": "Maine", "country": "US", "lat": 43.7,
                                            "lon": -70.3}] if text.lower() == "portland" else []
m = g.Media(); m.enter()
m.pie.place = lambda: None
real_footer = m.footer
m.footer = lambda d, items, *a, **k: (feet.append(list(items)), real_footer(d, items, *a, **k))[1]
m.weather.refresh = lambda *a, **k: None              # (no network here: the weather's put in by hand)


def draw():
    said.clear(); feet.clear()
    m.dirty = True; m.flush()
    return list(said)


def until(cond, secs=5):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


# ---- Settings: no Location, Temperature, or On the home screen ------------------------------------------------------
rows = [r[0] for r in m.settings_rows()]
check(f"Settings: no Location, Temperature or 'On the home screen' ({rows})",
      not {"location", "units", "widget"} & set(rows) and "home_style" in rows)

# ---- the Weather tab, nowhere yet ---------------------------------------------------------------------------------
wi = m.tab_index("weather")
m.open_app(wi)
texts = draw()
check(f"Weather, nowhere yet: it asks, and says START has its settings ({feet[-1]})", "Where are you?" in texts
      and ("START", "Settings") in feet[-1] and any("START to type a town" in t for t in texts))
m.press("start")
texts = draw()
check(f"START: its settings ({[t for t in texts if t in ('Location', 'Temperature', 'Not set', '°F')]})",
      m.wx_menu == "menu" and "Weather  ›  Settings" in texts and "Location" in texts and "Temperature" in texts
      and "Not set" in texts and "°F" in texts)
check(f"...its buttons ({feet[-1]})", feet[-1] == [("A", "Set"), ("B", "Back"), ("START", "Close")])
m.press("down")
texts = draw()
check(f"Temperature: ◀▶ ({feet[-1][0]})", feet[-1][0] == ("◀▶", "Change") and "▶" in texts)
m.weather.data = {"temp": 60}
m.press("right")
check(f"...right: °C, the weather starts over ({m.setting('units')}, {m.weather.data})", m.setting("units") == "°C"
      and m.weather.data is None and json.load(open(g.STATE_FILE))["settings"]["units"] == "°C")
m.press("a")
check(f"...A: back to °F ({m.setting('units')})", m.setting("units") == "°F")
m.press("left")
check(f"...left: °C ({m.setting('units')})", m.setting("units") == "°C")
m.press("right")

# Location: typed and picked
m.press("up")
m.press("a")
texts = draw()
check(f"Location: Find me, or type a town ({feet[-1]})", m.wx_menu == "location" and "Find me" in texts
      and "Type a town…" in texts and "Weather  ›  Location" in texts and "Now: Not set" in texts)
m.press("down"); m.press("a")
check("Type a town: the keyboard", m.view == "keys")
for ch in "Portland":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check("...the towns called that, to pick", until(lambda: len(m.loc_results) == 2 and m.loc_status is None)
      and m.view == "list" and m.wx_menu == "location" and m.wx_sel == 2)
texts = draw()
check(f"...listed ({[t for t in texts if t.startswith('Portland')]})", any(t.startswith("Portland, Oregon") for t in texts)
      and any(t.startswith("Portland, Maine") for t in texts))
m.press("a")
check(f"...A: that's where you are, back to the settings ({m.setting('location')})",
      m.setting("location")["admin"] == "Oregon" and m.wx_menu == "menu" and m.wx_sel == 0)
texts = draw()
check("...and it says so", any(t.startswith("Portland") for t in texts))
# Find me
m.press("a")
m.press("a")
check("Find me: found, back to the settings", until(lambda: m.setting("location")["name"] == "Denver")
      and until(lambda: m.wx_menu == "menu"))
# back, and closing
m.press("a")
m.press("b")
check("B in Location: back to the settings", m.wx_menu == "menu")
m.press("b")
check("B: back to the weather", m.wx_menu is None and m.tab == wi and m.view == "list")
m.press("start"); m.press("start")
check("START, START: open and closed", m.wx_menu is None and m.tab == wi)
m.press("start"); m.press("r")
check(f"R in the settings: on to the next tab, the settings closed ({g.LIBRARY[m.tab]['name']})",
      m.wx_menu is None and m.tab != wi)
m.open_app(wi)
m.press("start"); m.press("b"); m.press("b")
check("B on the weather: home", m.view == "home" and m.wx_menu is None)

# ---- the weather's own footer: START, and the credit still there ---------------------------------------------------
m.open_app(wi)
m.weather.data = {"temp": 61, "feels": 60, "code": 2, "is_day": True, "humidity": 70, "wind": 6, "wind_dir": 200,
                  "units": "C", "hours": [], "days": [{"date": "2026-10-25", "hi": 64, "lo": 50, "code": 2, "rain": 10}]}
m.weather.t = time.time()
texts = draw()
check(f"the weather: START Settings along the bottom, and Open-Meteo credited ({feet[-1]})",
      ("START", "Settings") in feet[-1] and "from Open-Meteo" in texts)
FB.last.save(S + "/weather.png")
m.press("start")
draw()
FB.last.save(S + "/weather_settings.png")
m.press("b")

# ---- the keyboard: SELECT is Caps ---------------------------------------------------------------------------------
got = []
m.open_keyboard("Say something", "", lambda t: got.append(t))
kb = m.kb
texts = draw()
check(f"the keyboard: SELECT Caps along the bottom, off ({feet[-1]})", ("SEL", "Caps", False) in feet[-1])
kb["r"], kb["c"] = 1, 0                                # q
m.press("select")
m.press("a")
kb["c"] = 1                                            # w
m.press("a")
texts = draw()
check(f"SELECT: Caps on, every letter capital till it's off ({kb['text']!r}), lit along the bottom",
      kb["text"] == "QW" and ("SEL", "Caps", True) in feet[-1] and "E" in texts and "e" not in texts)
m.press("select")
kb["c"] = 2
m.press("a")
check(f"...SELECT again: off ({kb['text']!r})", kb["text"] == "QWe")
kb["r"], kb["c"] = len(g.KEY_ROWS), 0                  # ⇧
m.press("a")
kb["r"], kb["c"] = 1, 3                                # r, t
m.press("a")
kb["c"] = 4
m.press("a")
check(f"...⇧: just the next letter, as before ({kb['text']!r})", kb["text"] == "QWeRt")
m.press("start")
check(f"START: done ({got})", got == ["QWeRt"])
ImageDraw.ImageDraw.text = real_text
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
