"""Settings > Resolution: a TV or monitor's sizes (from the kernel's screens), cmdline.txt's video= changed
and nothing else, the restart, the question after it (keep, go back, or nothing said: back by itself), the
screen not taking a size, no screen on HDMI (the GPi Case: no row), and setup.sh asking nothing about it (the
screen's own size, till Settings > Resolution changes it)."""
import os, sys, time, shutil, subprocess as sp
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/tres"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
ran, popened = [], []
_run, _popen = sp.run, sp.Popen


def real_run(*a, **k):
    """setup.sh's part, run for real (below): the stand-ins aside for it."""
    stub = sp.Popen
    sp.Popen = _popen
    try:
        return _run(*a, **k)
    finally:
        sp.Popen = stub


g.subprocess.run = lambda cmd, *a, **k: (ran.append(list(cmd)), type("R", (), {"stdout": "1", "returncode": 0})())[1]
g.subprocess.Popen = lambda cmd, *a, **k: popened.append(list(cmd))
g.fetch_json = lambda url: (_ for _ in ()).throw(OSError("offline"))
g.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# the kernel's screens: a 1080p monitor on the first HDMI port, nothing on the second
DRM = S + "/drm"
MODES = ["1920x1080", "3840x2160", "2560x1440", "1920x1080", "1920x1080i", "1680x1050", "1280x1024",
         "1440x900", "1280x720", "1280x720", "1024x768", "800x600", "720x576", "720x480", "640x480", "720x400"]


def screen(port, status, modes=()):
    d = f"{DRM}/card1-{port}"
    os.makedirs(d, exist_ok=True)
    open(d + "/status", "w").write(status + "\n")
    open(d + "/modes", "w").write("".join(m + "\n" for m in modes))


screen("HDMI-A-1", "connected", MODES)
screen("HDMI-A-2", "disconnected")
os.makedirs(DRM + "/card1-Writeback-1", exist_ok=True)
g.DRM_DIR = DRM
BOOT = S + "/boot/firmware"
os.makedirs(BOOT)
CMD = BOOT + "/cmdline.txt"
LINE = ("console=serial0,115200 console=tty1 root=PARTUUID=4e639091-02 rootfstype=ext4 fsck.repair=yes "
        "rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=US")
open(CMD, "w").write(LINE + "\n")
g.CMDLINE_TXT = (CMD, S + "/boot/cmdline.txt")
shots = {}


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


g.Framebuffer = FB


def snap(m, name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def keys(m):
    return [k for k, _, _ in m.settings_rows()]


def labels(m):
    return [r[1] for r in m.settings_rows()]


# ---- the helpers --------------------------------------------------------------------------------
check(f"the HDMI screens: the monitor's, its own size first ({g.hdmi_screens()[0][1][:3]})",
      [p for p, _ in g.hdmi_screens()] == ["HDMI-A-1"] and g.hdmi_screens()[0][1][0] == "1920x1080"
      and "1920x1080i" not in g.hdmi_screens()[0][1])
own, sizes = g.resolution_choices()
check(f"the sizes to pick: 640x480 up to 1080p, biggest first, no interlaced, and a square screen's ({sizes})",
      own == "1920x1080" and sizes == ["1920x1080", "1680x1050", "1440x900", "1280x1024", "1280x720", "1024x768",
                                       "800x600", "720x720", "720x576", "720x480", "640x480"])
check("nothing in cmdline.txt: Auto", g.boot_resolution() is None)
check("the old way of asking which ports have a screen still works", g.hdmi_ports() == [0])

# ---- Settings: the row, the page ----------------------------------------------------------------
m = g.Media()
m.enter()
si = m.tab_index("settings")
m.open_app(si)
check(f"Settings has Resolution, after Video size ({keys(m)[7:11]})",
      keys(m)[keys(m).index("screen") + 1] == "resolution")
m.set_sel = m.settings_root_index("resolution")
snap(m, "root")
check(f"its value: Auto, the screen's own ({m.res_value()})", m.res_value() == "Auto (1920x1080)")
m.press("a")
check(f"A opens its page, on Auto (in use) ({m.set_page}, {m.set_sel}, {labels(m)[:4]})",
      m.set_page == "resolution" and m.set_sel == 0 and labels(m)[0] == "Auto"
      and labels(m)[1:] == [s if s != "720x720" else "720x720 (square)" for s in sizes])
snap(m, "page")
m.press("a")
check("A on the one in use: nothing to do", "uses this one" in (m.msg or "") and not popened)
for _ in range(5):
    m.press("down")
check(f"down to 1280x720 ({labels(m)[m.set_sel]})", labels(m)[m.set_sel] == "1280x720")
m.press("a")
check("A once: asks for A again, nothing written yet",
      m.confirm[0] == "res:1280x720" and open(CMD).read() == LINE + "\n" and not popened)
snap(m, "confirm")
m.press("up"); m.press("a")
check("...A on another size: that one asks instead", m.confirm[0] == "res:1280x1024" and not popened)
m.press("down"); m.press("a"); m.press("a")
text = open(CMD).read()
check(f"A twice: cmdline.txt gets video=HDMI-A-1:1280x720@60, the rest as it was ({text[-50:]!r})",
      text == LINE + " video=HDMI-A-1:1280x720@60\n")
check(f"...the Pi restarts ({popened})", popened == [["systemctl", "reboot"]] and m.halting > time.monotonic())
t = m.setting("resolution_try")
check(f"...and it remembers to ask, and what to go back to ({t})",
      t == {"to": "1280x720", "size": "1280x720", "was": [], "ports": ["HDMI-A-1"], "from": "1920x1080"})
check("no temporary file left by cmdline.txt", sorted(os.listdir(BOOT)) == ["cmdline.txt"])

# ---- after the restart: kept ---------------------------------------------------------------------
popened.clear()
FB.real_w, FB.real_h = 1280, 720
m.set_setting("start", "Terminal")
m = g.Media()
check("after the restart: it opens media mode to ask, even with Terminal at start-up", m.boot_media)
m.enter()
check(f"...asking if it's kept ({m.view})", m.view == "keepres")
snap(m, "keep")
left = m.res_left()
check(f"...{left} seconds to answer", g.RES_KEEP - 1 <= left <= g.RES_KEEP)
m.press("x"); m.press("left")
check("other buttons don't answer it", m.view == "keepres" and m.setting("resolution_try"))
m.press("a")
check(f"A: kept, on to Settings > Resolution ({m.view}, {g.LIBRARY[m.tab]['name']}, {keys(m)[m.set_sel]})",
      m.view == "list" and g.LIBRARY[m.tab]["name"] == "Settings" and keys(m)[m.set_sel] == "resolution"
      and not m.setting("resolution_try") and not popened)
check(f"...its value now ({m.res_value()}), and cmdline.txt still has it",
      m.res_value() == "1280x720" and "video=HDMI-A-1:1280x720@60" in open(CMD).read())
snap(m, "kept")
m.res_tick(time.monotonic() + 999)
check("...and nothing goes back later", "video=HDMI-A-1:1280x720@60" in open(CMD).read() and not popened)

# ---- to Auto, and nothing said: back by itself ---------------------------------------------------
m.press("a")
check(f"the page: 1280x720 in use ({labels(m)[m.set_sel]})", labels(m)[m.set_sel] == "1280x720")
m.set_sel = 0
m.press("a"); m.press("a")
check(f"Auto: video= taken out of cmdline.txt ({open(CMD).read()[-40:]!r})", open(CMD).read() == LINE + "\n")
t = m.setting("resolution_try")
check(f"...to go back to 1280x720 ({t})", t["was"] == ["video=HDMI-A-1:1280x720@60"] and t["from"] == "1280x720"
      and t["size"] == "1920x1080" and t["to"] == "Auto")
popened.clear()
FB.real_w, FB.real_h = 1920, 1080
m = g.Media(); m.enter()
check("after the restart: asked", m.view == "keepres")
snap(m, "keep_auto")
m.res_tick(time.monotonic() + 1)
check("...a second on, still asking", m.view == "keepres" and not popened)
m.res_tick(m.res_until + 0.1)
check(f"nothing said in time: back to 1280x720, and the Pi restarts ({popened})",
      open(CMD).read() == LINE + " video=HDMI-A-1:1280x720@60\n" and popened == [["systemctl", "reboot"]]
      and not m.setting("resolution_try"))

# ---- B: back now ---------------------------------------------------------------------------------
popened.clear()
FB.real_w, FB.real_h = 1280, 720
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a")
m.set_sel = labels(m).index("1024x768"); m.press("a"); m.press("a")
check("1024x768 picked", "video=HDMI-A-1:1024x768@60" in open(CMD).read())
popened.clear()
FB.real_w, FB.real_h = 1024, 768
m = g.Media(); m.enter()
m.press("b")
check(f"B on the question: back to 1280x720 now ({popened})",
      open(CMD).read() == LINE + " video=HDMI-A-1:1280x720@60\n" and popened == [["systemctl", "reboot"]]
      and not m.setting("resolution_try"))

# ---- the screen didn't take the size --------------------------------------------------------------
popened.clear()
FB.real_w, FB.real_h = 1280, 720
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a")
m.set_sel = labels(m).index("1680x1050"); m.press("a"); m.press("a")
popened.clear()
FB.real_w, FB.real_h = 1920, 1080            # (it came up at the screen's own size instead)
m = g.Media(); m.enter()
check(f"the screen came up at another size: not asked, cmdline.txt as it was, no restart ({m.msg})",
      m.view != "keepres" and open(CMD).read() == LINE + " video=HDMI-A-1:1280x720@60\n" and not popened
      and not m.setting("resolution_try") and "1680x1050" in (m.msg or ""))

# ---- never shown (no screen, say): back by itself all the same ------------------------------------
FB.real_w, FB.real_h = 1280, 720
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a")
m.set_sel = labels(m).index("800x600"); m.press("a"); m.press("a")
popened.clear()
m = g.Media()                                # (no enter: media mode never came up)
check("a restart with nothing on the screen: it waits for the Pi to start, then some",
      m.res_until - time.monotonic() > g.RES_START)
m.res_tick(time.monotonic() + g.RES_START + g.RES_KEEP + 1)
check(f"...then goes back, and restarts ({popened})",
      open(CMD).read() == LINE + " video=HDMI-A-1:1280x720@60\n" and popened == [["systemctl", "reboot"]])

# ---- two screens, and what else cmdline.txt says stays ---------------------------------------------
popened.clear()
TV2 = " video=HDMI-A-2:1280x720@60 video=Composite-1:720x480@60ie"
open(CMD, "w").write("video=HDMI-A-1:1280x720@60  " + LINE + TV2 + "\n")
screen("HDMI-A-2", "connected", ["1920x1080", "1280x720"])         # (a TV on the second port)


def pick(size):
    m = g.Media(); m.enter(); m.open_app(si)
    m.set_sel = m.settings_root_index("resolution"); m.press("a")
    m.set_sel = labels(m).index(size); m.press("a"); m.press("a")
    return m


m = pick("1024x768")
text = open(CMD).read()
check(f"a size only the monitor takes: its port only, the TV's and the rest as they were ({text!r})",
      text == LINE + TV2 + " video=HDMI-A-1:1024x768@60\n")
check(f"...to go back to ({m.setting('resolution_try')})", m.setting("resolution_try")["was"]
      == ["video=HDMI-A-1:1280x720@60"] and m.setting("resolution_try")["ports"] == ["HDMI-A-1"])
m.res_undo(restart=False)
text = open(CMD).read()
check(f"going back puts it back ({text!r})", text == LINE + TV2 + " video=HDMI-A-1:1280x720@60\n")
m = pick("1920x1080")
text = open(CMD).read()
check(f"a size both take: both ports ({text!r})",
      text == LINE + " video=Composite-1:720x480@60ie video=HDMI-A-1:1920x1080@60 video=HDMI-A-2:1920x1080@60\n")
m.res_undo(restart=False)
text = open(CMD).read()
check(f"...and back ({text!r})", "video=HDMI-A-1:1280x720@60" in text and "video=HDMI-A-2:1280x720@60" in text
      and "1920x1080" not in text and "video=Composite-1:720x480@60ie" in text and text.count("\n") == 1)
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a"); m.set_sel = 0; m.press("a"); m.press("a")
text = open(CMD).read()
check(f"Auto: both ports' say goes, the rest stays ({text!r})",
      "HDMI-A" not in text and "video=Composite-1:720x480@60ie" in text and "root=PARTUUID=4e639091-02" in text)
m.res_undo(restart=False)
screen("HDMI-A-2", "disconnected")
open(CMD, "w").write(LINE + "\n")

# ---- a square screen (720x720) that says it's a TV: its size there to pick anyway, the timing worked out ------
popened.clear()
open(CMD, "w").write(LINE + "\n")
BOARD = ["1920x1080", "1280x720", "1024x768", "800x600", "640x480"]     # (what a square screen's board says it takes)
screen("HDMI-A-1", "connected", BOARD)
FB.real_w, FB.real_h = 1920, 1080                                         # (and it's sent 1080p: squeezed square)
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a")
check(f"a screen that doesn't list 720x720: there to pick anyway, once, named for square screens ({labels(m)})",
      labels(m) == ["Auto", "1920x1080", "1280x720", "1024x768", "800x600", "720x720 (square)", "640x480"])
snap(m, "square_page")
m.set_sel = labels(m).index("720x720 (square)"); m.press("a"); m.press("a")
text = open(CMD).read()
check(f"...picked: cmdline.txt gets video=HDMI-A-1:720x720M@60, the picture's timing worked out ({text[-40:]!r})",
      text == LINE + " video=HDMI-A-1:720x720M@60\n" and popened == [["systemctl", "reboot"]])
t = m.setting("resolution_try")
check(f"...what the Pi starts at ({g.boot_resolution()}), and what to go back to ({t})",
      g.boot_resolution() == "720x720" and t["size"] == "720x720" and t["was"] == [] and t["ports"] == ["HDMI-A-1"])
popened.clear()
FB.real_w, FB.real_h = 720, 720                                           # (it took it)
m = g.Media(); m.enter()
check(f"after the restart, at 720x720: asked if it's kept ({m.view})", m.view == "keepres")
m.press("a")
check(f"...kept: its value 720x720 ({m.res_value()})", m.res_value() == "720x720" and not popened
      and keys(m)[m.set_sel] == "resolution" and "video=HDMI-A-1:720x720M@60" in open(CMD).read())
m.press("a")
check(f"...its page: that row the one in use ({labels(m)[m.set_sel]})", labels(m)[m.set_sel] == "720x720 (square)")
m.set_sel = 0; m.press("a"); m.press("a")
check(f"...Auto: taken out again ({open(CMD).read()[-30:]!r})", open(CMD).read() == LINE + "\n")
m.res_undo(restart=False)
screen("HDMI-A-1", "connected", BOARD + ["720x720"])                     # (one that lists it: as any other size)
open(CMD, "w").write(LINE + "\n")
FB.real_w, FB.real_h = 1920, 1080
m = pick("720x720 (square)")
check(f"a screen that lists 720x720: there once, set as any size is ({open(CMD).read()[-30:]!r})",
      open(CMD).read() == LINE + " video=HDMI-A-1:720x720@60\n" and labels(m).count("720x720 (square)") == 1)
m.res_undo(restart=False)
screen("HDMI-A-1", "connected", MODES)
open(CMD, "w").write(LINE + "\n")
FB.real_w, FB.real_h = 1920, 1080

# ---- no cmdline.txt (not a Pi) ---------------------------------------------------------------------
popened.clear()
g.CMDLINE_TXT = (S + "/nothing/cmdline.txt",)
m = g.Media(); m.enter(); m.open_app(si)
m.set_sel = m.settings_root_index("resolution"); m.press("a")
m.set_sel = labels(m).index("1280x720"); m.press("a"); m.press("a")
check(f"no cmdline.txt: it says so, and doesn't restart ({m.msg})",
      "Couldn't change it" in (m.msg or "") and not popened and not m.setting("resolution_try"))
g.CMDLINE_TXT = (CMD, S + "/boot/cmdline.txt")

# ---- no screen on HDMI (the GPi Case): no row -----------------------------------------------------
screen("HDMI-A-1", "disconnected")
m = g.Media(); m.enter(); m.open_app(si)
check("nothing plugged into HDMI: no Resolution row", "resolution" not in keys(m))
g.DRM_DIR = S + "/no-drm"
m = g.Media(); m.enter(); m.open_app(si)
check("no KMS screens at all (the GPi Case): no Resolution row", "resolution" not in keys(m)
      and g.resolution_choices() is None and g.hdmi_ports() == [])
g.DRM_DIR = DRM
screen("HDMI-A-1", "connected", MODES)

# ---- back to the right row from the other pages, with Resolution there ----------------------------
m = g.Media(); m.enter(); m.open_app(si)
for row in ("wifi", "resolution"):
    m.set_page, m.set_sel = "root", m.settings_root_index(row)
    m.press("a")
    page = m.set_page
    m.press("b")
    check(f"{row}: A opens {page}, B comes back to it ({keys(m)[m.set_sel]})",
          m.set_page == "root" and keys(m)[m.set_sel] == row)
m.set_page, m.set_sel = "root", m.settings_root_index("friend")
m.press("a"); m.press("b")
check(f"Bot: back to it ({keys(m)[m.set_sel]})", m.set_page == "root" and keys(m)[m.set_sel] == "friend")
m.set_page, m.set_sel = "root", m.settings_root_index("start")
m.press("right")
check(f"At start-up still changes with Resolution above it ({m.setting('start')})", m.setting("start") == "Home screen")

# ---- setup.sh: no question about 720p (the screen's own size stays; Settings > Resolution changes it) ----------
setup = open(ROOT + "/setup.sh").read()
check("setup.sh: no question about 720p, cmdline.txt left alone, the screen's own size kept",
      "720p" not in setup and "cmdline.txt" not in setup
      and "(the screen's own resolution, as it is: Settings > Resolution changes it)" in setup)

# pictures
W, H = 640, 480
order = ["root", "page", "confirm", "keep", "kept", "keep_auto"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/resolution.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
