"""The home screen without its status bar (the clock and weather higher up), no Terminal icon, and a Home Assistant
icon that opens the TV Remote and Lights (no longer in the TV menu)."""
import json, os, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw, Image
S = SP + "/t_home_ha"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {"location": {"name": "Portland", "admin1": "Oregon", "country": "US", "lat": 45.5, "lon": -122.6}}},
          open(g.STATE_FILE, "w"))
g.home_dir = lambda: S + "/home/u"
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
m = g.Media(); m.enter()
start_sel = m.home_sel
m.weather.data = {"code": 2, "is_day": True, "temp": 68, "days": [{"hi": 72, "lo": 55}]}
bars = []
real_bar = m.status_bar
m.status_bar = lambda d, clock=True: (bars.append(clock), real_bar(d, clock))[1]
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append((xy, text)), real_text(self, xy, text, *a, **k))[1]
m.view = "home"; m.home_sel = 0; m.dirty = True; m.flush()
ImageDraw.ImageDraw.text = real_text
check("the home screen has no status bar (no temperature, no WiFi bars)", bars == [] and not any(
    t in ("No WiFi",) or str(t).endswith("°C") for _, t in texts))
clock_xy = next(xy for xy, t in texts if ":" in str(t) and len(str(t)) <= 5)
temp_xy = next(xy for xy, t in texts if str(t).endswith("°") and len(str(t)) <= 5)
check(f"the time and the temperature at the top, on one line ({clock_xy}, {temp_xy})", clock_xy[1] == temp_xy[1] == 66
      and clock_xy[0] < 40 and temp_xy[0] > 500)
check("the date under the time, the weather in words and today's high and low under the temperature",
      any(str(t).startswith(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))
          and xy == (m.HOME_X, 95) for xy, t in texts)
      and any(t == "Partly cloudy  ·  72° / 55°" and xy == (640 - m.HOME_X, 95) for xy, t in texts))
img = FB.last
top = img.crop((0, 0, 640, 12)).convert("L")
check("nothing drawn along the very top", top.getextrema()[1] < 60)
apps = [a for a, _ in m.home_apps()]
check(f"no Terminal icon; Home first, Settings last ({apps[:2]} ... {apps[-1:]})", "Terminal" not in apps
      and apps[0] == "Home" and apps[1] == "TV" and apps[-1] == "Settings" and len(apps) == 15
      and g.home_cols(15) == 5)
check("it's the one picked when media mode starts", apps[start_sel] == "Home")
check("B on the home screen: nothing (it's back everywhere else)", m.press("b") is None and m.view == "home")
check("Y on the home screen goes to the terminal", m.press("y") == "exit")
said = {}
def spy(style, fn):                             # (the buttons each look puts along the bottom)
    real = getattr(type(m), fn)
    def f(*a, **k):
        said[style] = list(a[1] if fn == "footer" else a[-2])
        return real(m, *a, **k)
    return f
for style, fn in (("Bright", "footer"), ("Glass", "footer"), ("Cards", "home_footer4")):
    m.state["settings"]["home_style"] = style
    setattr(m, fn, spy(style, fn))
    m.home_base = (None, None); m.dirty = True; m.flush()
    delattr(m, fn)
m.state["settings"]["home_style"] = "Glass"
check(f"...and says so along the bottom, in each look ({said.get('Glass')})",
      all(said.get(s) == [("A", "Open"), ("Y", "Terminal")] for s in ("Bright", "Glass", "Cards")))
m.home_base = (None, None); m.dirty = True; m.flush()
labels = []
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (labels.append(text), real_text(self, xy, text, *a, **k))[1]
m.home_base = (None, None)                      # (the cards drawn afresh, so each name is seen)
for sel in (1, 0):
    m.home_sel = sel; m.dirty = True; m.flush()
ImageDraw.ImageDraw.text = real_text
check(f"its name under its tile, whole, picked or not ({labels.count('Home')})",
      labels.count("Home") == 2 and not any("…" in str(t) for t in labels))
base = m.home_base
m.home_sel = 3; m.dirty = True; m.flush()
check("the cards are drawn once, not every time the pick moves", m.home_base is base)
img = FB.last.convert("RGB")
x0, y0, x1, y1 = m.card_box(3, g.home_layout(15, 5), 5, 0)
lit = img.getpixel((int(x0 + 37), int(y0 + 1)))
x0, y0, x1, y1 = m.card_box(8, g.home_layout(15, 5), 5, 0)
unlit = img.getpixel((int(x0 + 37), int(y0 + 1)))
check(f"the picked tile: a bright edge ({lit} against {unlit})", sum(lit) > sum(unlit) + 150)
x0, y0, x1, y1 = m.card_box(4, g.home_layout(15, 5), 5, 0)
px = img.getpixel((int(x0 + 6), int(y0 + 40)))
check(f"the others: dark glass, in their colour (Photos: teal, {px})", sum(px) < 260 and px[1] > px[0] and px[2] > px[0])
icon = g.draw_icon("Music", 56)
top = icon.getpixel((28, 4))
check(f"a tile: round corners (nothing there), its colour in it (Music: {top[:3]})", icon.getpixel((0, 0))[3] == 0
      and top[3] == 255 and top[0] > top[1] and top[2] > top[1])
check("...on a card of its own for the web page", g.draw_icon("Music", 64, card=True).getpixel((32, 4))[3] == 255)
m.home_sel = 0; m.dirty = True; m.flush()
check("its line at the bottom", m.home_sel == 0 and any("Your TV remote, lights, Pi-hole and the web" == t for t in labels))
m.press("a")
ha = m.tab
check(f"A: the Home Assistant menu ({[x['title'] for x in m.tab_items()]})", m.tab_type() == "group"
      and g.LIBRARY[ha]["name"] == "Home"
      and [x["title"] for x in m.tab_items()] == ["TV Remote", "Lights", "Pi-hole", "Web"])
check("where the web page says", m.where_text() == "Home")
m.press("a")
check(f"A on TV Remote: it opens ({m.where_text()})", m.tab_type() == "remote" and m.where_text() == "Home › TV Remote")
m.dirty = True; m.flush()
m.press("b")
check("B: back to the Home Assistant menu, TV Remote picked", m.tab == ha and m.tab_items()[m.sels[ha]]["title"] == "TV Remote")
m.press("down"); m.press("a")
check("Lights opens from it", m.tab_type() == "lights" and m.where_text() == "Home › Lights")
m.press("b"); m.press("b")
check("B, B: home, Home picked", m.view == "home" and m.home_apps()[m.home_sel][0] == "Home")
tv = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "TV")
m.load_tab(tv)
check(f"the TV menu without them ({[x['title'] for x in m.items[tv]]})",
      [x["title"] for x in m.items[tv]] == ["Plex", "Jellyfin", "Cartoons", "Free Movies", "News", "Sports", "Streams"])
cat = m.web_catalog()
check("the web page's apps: Home first, Settings last, no Terminal",
      [a["name"] for a in cat["apps"]][0] == "Home" and [a["name"] for a in cat["apps"]][-1] == "Settings"
      and "Terminal" not in [a["name"] for a in cat["apps"]] and [t["name"] for t in cat["tv"]][:2] == ["Plex", "Jellyfin"])
check("its icon for the web page", (m.web_icon("Home", 128) or b"")[:4] == b"\x89PNG" and m.web_icon("Terminal") is None)
m.go_home()
check("the web page opens it", m.web_command({"cmd": "open", "app": "Home"}) == {"ok": True} and m.tab == ha)
check("...and the terminal still, by name", m.web_command({"cmd": "open", "app": "Terminal"}) == {"ok": True} and not m.active)
m.enter()
check("apps' screens keep their status bar", (bars.clear(), setattr(m, "view", "list"), setattr(m, "dirty", True),
                                              m.flush(), bars)[-1] != [])
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
