"""System's dashboard (drawn as the Pi-hole page is) and its list, SELECT going from one to the other and the one
picked kept; what each button does on it; its numbers from System's own (the list's rows as they were); the last 5
minutes' looks (a look every 10 seconds, from the main loop, its own count of the CPU's time); the power and a newer
version said at the top. Then the Home tab (Home Assistant's, renamed): its name, Settings > Home, the web page's
Home screen and Home tab apart, Check connection; and Apps' rows without "B stops it"."""
import io, json, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import system as sysmod
from PIL import ImageDraw

S = SP + "/t_sysdash"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "", "returncode": 1, "stderr": ""})()
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


NUMS = {"background": [("Converting video", "45% · Cartoon.mp4 · 2 more after it")], "temp": 58.4, "busy": 37.0,
        "mhz": 1000, "power": ("OK", False), "mem": (231 << 20, 425 << 20),
        "disk": (int(21.4 * (1 << 30)), int(7.6 * (1 << 30)), 29 << 30), "ssid": "Basement WiFi", "dbm": -58,
        "wifi_q": None, "ip": "192.168.1.54", "host": "pietato", "up": 3 * 86400 + 4 * 3600 + 17 * 60,
        "board": "Raspberry Pi Zero 2 W Rev 1.0", "os": "Debian GNU/Linux 12 (bookworm)", "kernel": "6.12.47+rpt-rpi-v8"}
nums = dict(NUMS)
real_numbers = sysmod.system_numbers
g.system_numbers = lambda background=(): dict(nums)

# ---- the list's rows, from the numbers, as they were -----------------------------------------------------------
rows = sysmod.system_info(nums=dict(NUMS))
got = [(r["title"], r["sub"], r.get("warn", False)) for r in rows]
check(f"System's list: the same rows as before, from the numbers ({got[:3]}...)", got == [
    ("CPU temperature", "58.4 °C", False), ("CPU", "37% busy · 1000 MHz", False),
    ("Converting video", "45% · Cartoon.mp4 · 2 more after it", False), ("Power", "OK", False),
    ("Memory", "231.0 MB of 425.0 MB", False), ("Storage", "21.4 GB used, 7.6 GB free", False),
    ("WiFi", "Basement WiFi · -58 dBm", False), ("IP address", "192.168.1.54", False), ("Hostname", "pietato", False),
    ("Up for", "3 d 4 h 17 min", False), ("Board", "Raspberry Pi Zero 2 W Rev 1.0", False),
    ("System", "Debian GNU/Linux 12 (bookworm)", False), ("Kernel", "6.12.47+rpt-rpi-v8", False),
    ("Restart media mode", "", False), ("Reboot", "", False), ("Shut down", "", False)])
hot = dict(NUMS, temp=74.2, busy=None, mhz=None, ssid=None, dbm=None, wifi_q=None, ip=None, up=None, board="",
           disk=(28 << 30, 700 << 20, 29 << 30), power=("Now: low power, throttled", True))
got = {r["title"]: (r["sub"], r.get("warn", False)) for r in sysmod.system_info(nums=hot)}
check("...hot, throttled, no WiFi, the card nearly full: said as before",
      got["CPU temperature"] == ("74.2 °C", True) and got["CPU"] == ("…", False) and got["Power"][1]
      and got["WiFi"] == ("not connected", True) and got["IP address"] == ("none", False) and got["Storage"][1]
      and "Up for" not in got and "Board" not in got)
real = real_numbers([("Reading lengths", "3 songs and videos left")])
check(f"the real numbers here: all of them ({sorted(real)})",
      set(real) == set(NUMS) and real["background"] == [("Reading lengths", "3 songs and videos left")]
      and real["mem"] and real["disk"][2] > 0 and real["kernel"] == os.uname().release)

# ---- the last 5 minutes: a look every 10 seconds, its own count of the CPU's time ---------------------------
STAT = S + "/stat"


def stat(work, idle):
    open(STAT, "w").write(f"cpu  {work} 0 0 {idle} 0 0 0 0 0 0\n")


sysmod.PROC_STAT = STAT
h = sysmod.SysHistory()
stat(100, 900)
check("the first look: nothing to go by, nothing kept", h.tick(1000.0) and not h.samples)
check("...not again before 10 seconds", not h.tick(1009.0))
stat(160, 940)                                   # (60 of 100 working)
check("10 seconds on: 60% busy kept, with the temperature then", h.tick(1010.0) and len(h.samples) == 1
      and abs(h.samples[-1][1] - 60.0) < 0.01)
sysmod._cpu_was = None
sysmod.cpu_busy()                                # (System's list looking meanwhile doesn't upset it)
stat(170, 1030)
h.tick(1020.0)
check("...and its own count, whatever System's list looked at meanwhile (10%)", abs(h.samples[-1][1] - 10.0) < 0.01)
for k in range(40):
    stat(200 + k * 10, 1100 + k * 90)
    h.tick(1030.0 + k * 10)
check(f"the last 30 kept ({len(h.samples)})", len(h.samples) == 30)
sysmod.PROC_STAT = "/proc/stat"

# ---- the dashboard -------------------------------------------------------------------------------------------
said = []
real_text = ImageDraw.ImageDraw.text


def text(self, xy, t, *a, **k):
    said.append((str(t), k.get("fill")))
    return real_text(self, xy, t, *a, **k)


ImageDraw.ImageDraw.text = text
bars = []
real_bar = g.PiholeScreen.pihole_bar
g.PiholeScreen.pihole_bar = staticmethod(lambda d, box, colour, top_end=True: (bars.append((box, colour)),
                                                                                real_bar(d, box, colour, top_end))[1])


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
si = m.tab_index("system")
m.tab, m.view = si, "list"
m.load_tab(si)
now = time.monotonic()
m.sys_history.samples.clear()
for k in range(30):
    m.sys_history.samples.append((now - (29 - k) * 10, 10.0 + k * 2, 50.0 + k * 0.5))


def draw():
    said.clear(); bars.clear()
    m.dirty = True; m.flush()
    return [t for t, _ in said]


texts = draw()
check(f"System opens on its dashboard ({m.setting('sys_view')})", m.sys_dash() and "CPU busy, last 5 minutes" in texts)
check(f"...its four numbers ({[t for t in texts if t in ('58.4 °C', '37%', '231 MB', '7.6 GB')]})",
      all(t in texts for t in ("CPU temperature", "58.4 °C", "CPU busy", "37%", "Memory used", "231 MB", "7.6 GB")))
check("...the board, and the power said with a light", "Raspberry Pi Zero 2 W Rev 1.0" in texts and "Power OK" in texts)
check(f"...a column for each look, in the CPU's colour ({len(bars)})", len(bars) == 30
      and all(c == g.PH_ALLOWED for _, c in bars) and bars[-1][0][1] < bars[0][0][1])
check("...the network below it first", "Network" in texts and "Basement WiFi" in texts and "-58 dBm" in texts
      and "192.168.1.54" in texts)
check(f"...its buttons: {m.sysdash_hints()}", m.sysdash_hints() == [("◀▶", "More"), ("SELECT", "List"),
                                                                     ("L R", "Tabs"), ("B", "Home")])
for name, want in (("right", ("Temperature, last 5 minutes", "64.5 °C")), ("right", ("This Pi", "3 d 4 h 17 min")),
                   ("right", ("In the background", "45%")), ("right", ("Network", "Basement WiFi"))):
    m.press(name)
    texts = draw()
    check(f"▶: {want[0]}", all(w in texts for w in want))
m.press("left")
check("◀: back round to the last of them", m.sys_panel == 3)
sel = m.sels.get(si)
for name in ("up", "down", "a"):
    m.press(name)
check("▲▼ and A do nothing on it (nothing picked in the list behind it, nothing pressed)",
      m.sels.get(si) == sel and m.confirm[0] is None and m.view == "list")
nums.update(temp=74.2, power=("Now: low power, throttled", True), disk=(28 << 30, 700 << 20, 29 << 30))
m.updater.folder, m.updater.new = "/x", 2
m.load_tab(si)
draw()
fills = dict(said)
check("too hot: the temperature in red; throttled: said, in red; the card nearly full: in red",
      fills.get("74.2 °C") == g.WARN and fills.get("Low power, throttled") == g.WARN and fills.get("700 MB") == g.WARN)
check("a newer version: said up there too", "New version" in fills)
check(f"...and A updates from here ({m.sysdash_hints()[0]})", m.sysdash_hints()[0] == ("A", "Update"))
began = []
m.updater.begin = lambda: (began.append(1), "test: not here")[1]
m.press("a")
check(f"A: asks first, as the list's Update software ({m.msg!r})", m.confirm[0] == "update" and not began
      and m.msg.startswith("Press A again to update"))
m.press("a")
check("A again: the update", began == [1] and m.msg == "test: not here")
nums.clear(); nums.update(NUMS); m.updater.folder, m.updater.new = None, 0
m.load_tab(si)

# SELECT: the list, and back; kept
m.press("select")
texts = draw()
check("SELECT: System's list (its rows; Reboot and the rest further down it)", not m.sys_dash()
      and "CPU temperature" in texts and "37% busy · 1000 MHz" in texts and "CPU busy, last 5 minutes" not in texts
      and m.setting("sys_view") == "List" and "Reboot" in [r["title"] for r in m.tab_items()])
check(f"...its buttons say so ({m.list_hints()})", ("SELECT", "Dashboard") in m.list_hints())
k = next(i for i, r in enumerate(m.tab_items()) if r["title"] == "Reboot")
m.sels[si] = k
m.press("a")
check("...A in the list as before (Reboot: asks again first)", m.confirm[0] == "reboot")
m.press("select")
check("SELECT again: the dashboard (and Reboot isn't waiting for a second A)", m.sys_dash() and m.confirm[0] is None)
m.press("select")
m2 = g.Media()
check("the one picked is kept (a restart: the list)", m2.setting("sys_view") == "List")
m.press("select")
m.press("x")
texts = draw()
check("X: its controls", m.view == "help" and "Dashboard / list" in texts and "More (dashboard)" in texts)
m.press("b"); m.view = "list"
m.press("r")
check("R: the next tab", m.tab != si)
m.tab = si; m.load_tab(si)
m.press("b")
check("B: home", m.view == "home")

# its looks come from the main loop, whatever's on the screen
sysmod.PROC_STAT = STAT
m.sys_history = sysmod.SysHistory()
stat(100, 900); m.tick()
stat(130, 970); m.sys_history.next = 0; m.tick()
check(f"the main loop looks (a look kept: {list(m.sys_history.samples)[-1:]})", len(m.sys_history.samples) == 1
      and abs(m.sys_history.samples[-1][1] - 30.0) < 0.01)
sysmod.PROC_STAT = "/proc/stat"

# 640 x 480, 800 x 480 (the Waveshare), 960 x 540, Full screen apps: drawn without trouble, nothing off the edge
for size in ((640, 480), (800, 480), (960, 540)):
    FB.w, FB.h = size
    m.fb = FB(); m.tab, m.view = si, "list"; m.load_tab(si)
    for panel in range(4):
        m.sys_panel = panel
        draw()
    check(f"{size[0]} x {size[1]}: every panel drawn", FB.last is not None and FB.last.size == size)
m.set_setting("app_full", "On")
texts = draw()
check("Full screen apps: drawn, its name on top", "CPU busy, last 5 minutes" in texts)
m.set_setting("app_full", "Off")
FB.w, FB.h = 640, 480
m.fb = FB()

# ---- the Home tab (Home Assistant's) ----------------------------------------------------------------------------
names = [t["name"] for t in g.LIBRARY]
hi = names.index("Home")
check("the tab's called Home (not Home Assistant, nor House)", "Home Assistant" not in names and "House" not in names
      and g.LIBRARY[hi]["children"] == ["TV Remote", "Lights", "Pi-hole", "Web"]
      and all(g.LIBRARY[names.index(c)]["parent"] == "Home" for c in ("TV Remote", "Lights", "Pi-hole", "Web")))
check("Settings > Home", ("homeassistant", "Home", None) in g.SETTINGS)
m.tab, m.view = hi, "list"; m.load_tab(hi)
check("where the web page says: Home", m.where_text() == "Home")
r = m.web_command({"cmd": "open", "home": True})
check("the web page's Home screen: the home screen", r == {"ok": True} and m.view == "home" and m.where_text() == "Home screen")
r = m.web_command({"cmd": "open", "app": "Home"})
check("...its Home app: the Home tab", r == {"ok": True} and m.view == "list" and m.tab == hi)
check(f"...its apps, and no Settings of its own (Settings > Home has them) ({[it['title'] for it in m.tab_items()]})",
      [it["title"] for it in m.tab_items()] == ["TV Remote", "Lights", "Pi-hole", "Web"])
si = m.tab_index("settings")
m.tab, m.view, m.set_page = si, "list", "root"
m.load_tab(si)
m.set_sel = [k for k, _, _ in m.settings_root_rows()].index("homeassistant")
m.press("a")
texts = draw()
check("Settings > Home: Home  ›  Settings, and Check connection",
      "Home  ›  Settings" in texts and "Check connection" in texts and "Check the connection" not in texts)
page = open(ROOT + "/templates/index.html").read()
check("the web page: its Home button asks for the Home screen as that (its Apps tab gone: the apps are on the screen)",
      'pi("open", { home: true })' in page and 'a.home ? { home: true } : { app: a.name }' not in page)

# ---- Apps' rows --------------------------------------------------------------------------------------
abouts = [t.get("about", "") for t in g.LIBRARY if t.get("type") == "prog"]
check(f"Apps' programs: no 'B stops it' ({abouts})",
      abouts == ["Linux's falling code", "Movie hacker screens", "The rainbow cat", "Flames made of letters",
                 "What's running on the Pi"])
ImageDraw.ImageDraw.text = real_text
print("ALL OK" if all(ok_all) else "SOME FAILED")
