"""Every screen on a 4K TV (and a 1080p one), drawn as ever (each of the menus' pixels one of the picture's) and
drawn finely (fine.py: 2 x 2 of the picture's to each): the fine one, reduced to the menus' size, the same picture
as the plain one (nothing out of place, nothing missing), nothing going wrong, and a look at both side by side."""
import json, math, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageDraw

S = SP + "/tfine_test"
_draw_face = g.draw_face           # (the Bot's face as it is at one moment, not blinking or glancing about: drawn alike
g.draw_face = lambda d, x, y, size, look, t, *a, **k: _draw_face(d, x, y, size, look, 0.5, *a, **k)  # both ways)
OUT = SP + "/fine_test"
shutil.rmtree(S, ignore_errors=True); shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/gba", "Games/snes", "Games/ps1"):
    os.makedirs(f"{HOME}/{d}")
for n in ("Blue in Green.mp3", "So What.mp3", "Freddie Freeloader.mp3", "All Blues.mp3"):
    open(f"{HOME}/Music/{n}", "wb").write(b"\0" * 100)
for n in ("Holiday 2025.mp4", "Rocket launch.mkv", "Birthday.mp4"):
    open(f"{HOME}/Videos/{n}", "wb").write(b"\0" * 100)
for k, n in enumerate(("Mountains.jpg", "Beach.jpg", "Garden.jpg", "City.jpg", "Snow.jpg")):
    im = Image.new("RGB", (1200, 800), (40 + 40 * k, 90, 160 - 20 * k))
    ImageDraw.Draw(im).ellipse((300, 200, 900, 700), fill=(220, 180 - 20 * k, 80))
    im.save(f"{HOME}/Pictures/{n}")
open(f"{HOME}/Documents/notes.txt", "w").write("Shopping\n\n- eggs\n- milk\n- bread\n\n" + "A longer line of text that goes on and on to see how the reader wraps it across the page. " * 6)
for n in ("Metroid Fusion.gba", "Golden Sun.gba"):
    open(f"{HOME}/Games/gba/{n}", "wb").write(b"\0" * 64)
open(f"{HOME}/Games/snes/Super Metroid.sfc", "wb").write(b"\0" * 64)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"; g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
json.dump({"settings": {"location": {"name": "Portland", "admin1": "Oregon", "country": "US", "lat": 45.5, "lon": -122.6}}},
          open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd",
                                        "systemctl", "pdftotext", "pdftoppm", "soffice"}
                                       else real_run(cmd, *a, **k))
subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(OSError("no processes in the tour"))


def fake_json(url, *a, **k):
    if "api.open-meteo.com" in url:
        base = time.strftime("%Y-%m-%dT%H")
        t0 = time.mktime(time.strptime(base, "%Y-%m-%dT%H"))
        times = [time.strftime("%Y-%m-%dT%H:%M", time.localtime(t0 + h * 3600)) for h in range(-2, 30)]
        codes = [0, 1, 2, 3, 61, 63, 80, 95, 2, 1, 0, 0] * 3
        return {"current": {"time": base + ":30", "temperature_2m": 71.2, "apparent_temperature": 70.1,
                            "relative_humidity_2m": 64, "weather_code": 2, "wind_speed_10m": 9.4,
                            "wind_direction_10m": 250, "is_day": 1, "precipitation": 0},
                "hourly": {"time": times, "temperature_2m": [70 - abs(h - 3) * 0.8 for h in range(32)],
                           "weather_code": codes[:32], "precipitation_probability": [10] * 32,
                           "is_day": [1 if 6 <= (int(t[11:13])) < 19 else 0 for t in times]},
                "daily": {"time": [time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * i)) for i in range(7)],
                          "weather_code": [2, 61, 95, 3, 0, 71, 45],
                          "temperature_2m_max": [74, 66, 62, 68, 79, 37, 59],
                          "temperature_2m_min": [59, 55, 54, 55, 61, 25, 48],
                          "sunrise": ["2026-10-11T06:52"] * 7, "sunset": ["2026-10-11T18:21"] * 7,
                          "precipitation_probability_max": [10, 70, 90, 20, 0, 40, 10]}}
    if "api.weather.gov/points" in url:
        return {"properties": {"forecast": "https://api.weather.gov/gridpoints/PQR/1,1/forecast"}}
    if "api.weather.gov/gridpoints" in url:
        return {"properties": {"periods": [
            {"name": "Tonight", "detailedForecast": "Partly cloudy, with a low around 55. West wind around 5 mph."},
            {"name": "Friday", "detailedForecast": "A chance of showers after 11am. Mostly cloudy, with a high near 66."},
            {"name": "Friday Night", "detailedForecast": "Showers likely. Cloudy, with a low around 52."}]}}
    raise OSError("offline: " + url)


g.fetch_json = fake_json
g.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))

# a 1080p monitor's screens, for Settings > Resolution
DRM = S + "/drm/card1-HDMI-A-1"
os.makedirs(DRM)
open(DRM + "/status", "w").write("connected\n")
open(DRM + "/modes", "w").write("\n".join(["1920x1080", "1680x1050", "1280x1024", "1440x900", "1280x720",
                                          "1024x768", "800x600", "640x480"]) + "\n")
g.DRM_DIR = S + "/drm"
os.makedirs(S + "/boot")
open(S + "/boot/cmdline.txt", "w").write("console=tty1 root=PARTUUID=1234-02 rootwait\n")
g.CMDLINE_TXT = (S + "/boot/cmdline.txt",)


RealFB = g.Framebuffer


def make_fb(real_w, real_h):
    """A stand-in screen of this size, drawn at what the real Framebuffer would draw the menus at."""
    probe = object.__new__(RealFB)
    probe.setup(real_w, real_h, 0, 0, 32, [(16, 8), (8, 8), (0, 8)], real_w * 4)

    class FB:
        w, h = probe.w, probe.h
        tw, th = probe.tw, probe.th
        s = probe.s
        last = None

        def show(self, img):
            assert img.size == (self.w, self.h), f"a picture {img.size} on a {self.w}x{self.h} screen"
            FB.last = img.copy()

        def show_part(self, img, box): self.show(img)
        def blank_outside(self, box): pass
        def invalidate(self): pass
        def close(self): pass
    FB.real_w, FB.real_h = real_w, real_h
    return FB


SIZES = {"4k": (3840, 2160)} if os.environ.get("FINE_TIME") else {"4k": (3840, 2160), "1080p": (1920, 1080)}
TIMES = {}
from pitato import fine as FINE
shots = {k: {} for k in SIZES}
order = []
problems = []


def tour(which):
    FB = make_fb(*SIZES[which])
    g.Framebuffer = FB
    m = g.Media()
    m.enter()

    def shot(name, fresh=True):
        got = {}
        while time.localtime().tm_sec >= 57:           # (both drawn in the same minute: the clocks on them alike)
            time.sleep(0.2)
        for s in (1, FB.s):
            FB.s = s
            m.fine_scale()
            m.dirty = True
            try:
                m.flush()
            except Exception as ex:
                import traceback
                problems.append(f"{which} {name} at {s}: {ex!r}")
                traceback.print_exc()
            got[s] = FB.last
            if os.environ.get("FINE_TIME"):          # (how long a frame takes once its pictures are made)
                best = 9.0
                for _ in range(3):
                    m.dirty = True
                    t0 = time.perf_counter()
                    try:
                        m.flush()
                    except Exception:
                        pass
                    best = min(best, time.perf_counter() - t0)
                TIMES.setdefault(name, {})[s] = best
        FB.s = max(got)
        if name not in order:
            order.append(name)
        shots[which][name] = got

    for style in ("Bright", "Glass", "Cards"):
        m.set_setting("home_style", style)
        m.home_base = (None, None)
        m.view = "home"
        shot("home_" + style.lower())
    m.set_setting("home_style", "Glass")

    def tab(name):
        i = m.tab_index(name) if name not in [t["name"] for t in g.LIBRARY] else [t["name"] for t in g.LIBRARY].index(name)
        m.open_app(i)
        return i

    for name in ("Home", "TV", "Music", "Radio", "Photos", "Videos", "Games", "Files", "Camera",
                 "Apps", "System", "Plex", "Jellyfin", "Cartoons", "Free Movies", "News", "Streams",
                 "TV Remote", "Lights"):
        try:
            tab(name)
            if name == "Photos":                       # (their thumbnails at both scales first: made as they're
                for sc in (1, FB.s):                   # needed, at the scale it's drawn at)
                    FB.s = sc
                    m.fine_scale()
                    m.thumb_loop()
            shot("tab_" + name.lower().replace(" ", "_"))
        except Exception as ex:
            problems.append(f"{which} tab {name}: {ex!r}")
    # weather pages
    tab("Weather")
    m.weather_changed()
    for _ in range(60):
        if m.weather.data and not m.weather.busy:
            break
        time.sleep(0.05)
    for p in range(3):
        m.wx_page = p
        shot(f"weather_{p}")
    # settings
    tab("Settings")
    m.set_page, m.set_sel = "root", 0
    shot("settings")
    m.set_sel = m.settings_root_index("resolution")
    shot("settings_res_row")
    m.press("a")
    shot("settings_res_page")
    m.set_page = "root"
    m.set_sel = m.settings_root_index("friend"); m.press("a")
    shot("settings_bot")
    m.press("b")
    tab("Weather")                               # (where you are: Weather's settings, START)
    m.press("start")
    shot("weather_settings")
    m.press("a")
    shot("weather_location")
    m.press("b"); m.press("b")
    # finance: a stock's card, and a coin's
    st, cr = m.stocks, m.crypto
    now_t = time.time()
    svals = [233.4 * (1 + 0.004 * math.sin(i / 7.0) + 0.0002 * i) for i in range(78)]
    st.quotes["AAPL"] = {"t": now_t, "d": {
        "symbol": "AAPL", "name": "Apple Inc.", "price": svals[-1], "prev_close": 233.42,
        "change_1d": (svals[-1] - 233.42) / 233.42 * 100, "high_1d": max(svals), "low_1d": min(svals),
        "volume": 38846578, "high_52w": 237.49, "low_52w": 164.08, "currency": "USD", "kind": "EQUITY",
        "exchange": "NasdaqGS", "time": now_t - 60, "tz": "EDT", "gmtoffset": -14400,
        "open_at": now_t - 3600, "close_at": now_t + 3600}}
    st.hist[f"AAPL:{st.days}"] = {"t": now_t, "v": svals}
    n = 288
    vals = [62000 * (1 + 0.012 * i / n + 0.006 * math.sin(i / 9.0) + 0.009 * math.sin(i / 37.0)) for i in range(n)]
    cr.quotes["bitcoin"] = {"t": time.time(), "d": {"name": "Bitcoin", "price": vals[-1], "rank": 1,
                                                     "high_24h": max(vals), "low_24h": min(vals), "change_24h": 1.2}}
    cr.hist[f"bitcoin:{cr.days}"] = {"t": time.time(), "v": vals}
    tab("Finance")
    m.fin_card = m.fin_cards().index(("stock", "AAPL")); m.fin_focus()
    shot("finance")
    m.fin_card = m.fin_cards().index(("coin", "bitcoin")); m.fin_focus()
    shot("crypto")
    # bot: a conversation, its X menu, at work (typing), and the card START shows there
    open(HOME + "/bot.txt", "w").write("server = 192.168.1.20\nmodel = llama3.2:3b\n")
    m.friend.load(m.friend_files())
    now = time.time()                       # (it said something a minute ago: no hello from it as its tab opens, so
    m.friend.log = [                        # nothing's asked of its server, and nothing comes between the drawings){"who": "friend", "kind": "remark", "t": now - 300, "text": "Evening! It's 71 and clear. A good night for a walk."},
                    {"who": "you", "kind": "chat", "t": now - 60, "text": "what's my coding agent up to?"},
                    {"who": "friend", "kind": "chat", "t": now - 55, "text": "It's been typing for four minutes. I'll ring the bell when it's done."}]
    tab("Bot")
    shot("bot")
    try:
        m.press("x")
        shot("bot_menu")
        m.press("b")
        m.coder.ask("typing")
        m.press("right")
        time.sleep(1.0)
        shot("bot_work")
        m.press("start")
        shot("bot_work_card")
        m.press("start")
        m.press("left")
    except Exception as ex:
        problems.append(f"{which} bot work: {ex!r}")
    # Apps' worlds
    for name in ("Rock Paper Scissors", "Game of Life", "Forest Fire", "Mandelbrot Set", "Snake"):
        try:
            tab(name)
            for _ in range(5):
                m.tick()
                time.sleep(0.02)
            shot("sim_" + name.lower().replace(" ", "_"))
            m.press("b")
        except Exception as ex:
            problems.append(f"{which} sim {name}: {ex!r}")
    # full screen (SELECT), one of them
    try:
        tab("Game of Life")
        m.press("select")
        for _ in range(5):
            m.tick(); time.sleep(0.02)
        shot("sim_full")
        m.press("select")
        m.press("b")
    except Exception as ex:
        problems.append(f"{which} sim full: {ex!r}")
    # now playing
    try:
        tab("Music")
        items = m.tab_items()

        class Proc:
            def poll(self): return None
        m.proc, m.kind, m.cur, m.queue, m.qi = Proc(), "audio", items[0], items, 0
        m.meta = {"title": items[0]["title"], "artist": "Miles Davis"}
        m.pos = 61
        m.view = "now"
        shot("now_playing")
        m.view = "home"
        shot("home_playing")
        m.proc, m.kind, m.cur = None, None, None
    except Exception as ex:
        problems.append(f"{which} now playing: {ex!r}")
        m.proc, m.kind, m.cur = None, None, None
    # overlays: help, keyboard, a photo, a text file, wait
    tab("Music")
    m.view = "list"
    try:
        m.help_from = "list"; m.view = "help"
        shot("help")
    except Exception as ex:
        problems.append(f"{which} help: {ex!r}")
    m.view = "list"
    m.open_keyboard("Town or city", "Port", lambda t: None)
    shot("keyboard")
    m.kb = None
    m.view = "list"
    tab("Photos")
    try:
        m.press("a")
        time.sleep(0.3); m.tick()
        shot("photo")
    except Exception as ex:
        problems.append(f"{which} photo: {ex!r}")
    m.view = "list"
    try:
        m.open_text(f"{HOME}/Documents/notes.txt")
        shot("text")
    except Exception as ex:
        problems.append(f"{which} text: {ex!r}")
    m.view = "list"
    m.render_wait("Opening", "One moment")
    if "wait" not in order:
        order.append("wait")
    shots[which]["wait"] = {1: FB.last}
    m.set_setting("resolution_try", {"to": "1920x1080", "size": "1920x1080", "was": [], "ports": ["HDMI-A-1"],
                                     "from": "1280x720"})
    m.view = "keepres"; m.res_until = time.monotonic() + 20
    shot("keepres")
    m.set_setting("resolution_try", None)
    m.view = "home"
    if os.environ.get("FINE_KEPT"):                    # (where pictures are kept: fine ones, after a frame at 2)
        FB.s = 2; m.fine_scale(); m.dirty = True; m.flush()

        def holds(v, depth=0):
            if isinstance(v, FINE.Fine):
                return True
            if depth > 3:
                return False
            if isinstance(v, dict):
                return any(holds(x, depth + 1) for x in list(v.values())[:200])
            if isinstance(v, (list, tuple)):
                return any(holds(x, depth + 1) for x in list(v)[:200])
            return False
        print("KEPT", sorted(k for k, v in vars(m).items() if holds(v)))
    return m


for which in SIZES:
    tour(which)

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


import numpy as np
from PIL import Image as P
check(f"every screen drawn both ways, nothing went wrong ({problems or 'none'})", not problems)
for which in SIZES:
    FB = make_fb(*SIZES[which])
    check(f"{which}: the menus {FB.w} x {FB.h}, drawn {FB.s} x finer", (FB.w, FB.h, FB.s) == (960, 540, 2))
    worst = []
    for name in order:
        got = shots[which].get(name) or {}
        a, b = got.get(1), got.get(FB.s)
        if a is None or b is None or b is a:
            continue
        fine_ok = FINE.detail(b) == FB.s and b.size == a.size == (FB.w, FB.h) and b.pic.size == (FB.w * FB.s, FB.h * FB.s)
        A = np.asarray(a.convert("RGB")).astype(int)
        B = np.asarray(FINE.plain(b).convert("RGB")).astype(int)
        diff = np.abs(A - B).max(axis=2)
        # (text and curves are drawn anew, so pixels differ along their edges, and a line of text set finely can end
        # a pixel or two from where it did: looked at a little blurred, a block that's wrong is many pixels, together)
        from PIL import ImageFilter as IF
        Ab = np.asarray(a.convert("RGB").filter(IF.GaussianBlur(1.5))).astype(int)
        Bb = np.asarray(FINE.plain(b).convert("RGB").filter(IF.GaussianBlur(1.5))).astype(int)
        far = np.abs(Ab - Bb).max(axis=2) > 64
        blocks = far.reshape(FB.h // 12, 12, FB.w // 12, 12).sum(axis=(1, 3))
        bad = int((blocks > 40).sum())
        worst.append((round(float(diff.mean()), 2), bad, name))
        same = fine_ok and diff.mean() < 4 and bad <= 2
        check(f"{which} {name}: drawn {FB.s}x finely ({fine_ok}), the same picture (mean {diff.mean():.2f}, "
              f"{bad} blocks far off)", same)
        if not same:                                  # (both kept, to look at)
            os.makedirs(SP + "/out", exist_ok=True)
            a.convert("RGB").save(f"{SP}/out/fine_{which}_{name}_1.png")
            FINE.plain(b).convert("RGB").save(f"{SP}/out/fine_{which}_{name}_{FB.s}.png")
        if os.environ.get("FINE_SAVE") or bad > 2 or diff.mean() >= 4:
            side = P.new("RGB", (FB.w * FB.s * 2 + 8, FB.h * FB.s), (255, 0, 255))
            side.paste(a.convert("RGB").resize((FB.w * FB.s, FB.h * FB.s), P.NEAREST), (0, 0))
            side.paste(b.pic.convert("RGB"), (FB.w * FB.s + 8, 0))
            side.save(f"{OUT}/{which}_{name}.png")
    print(which, "worst:", sorted(worst, reverse=True)[:6])
if TIMES:
    for name, t in TIMES.items():
        print(f"time {name:28} plain {t.get(1, 0) * 1000:6.1f} ms   fine {t.get(2, 0) * 1000:6.1f} ms")
    tot1 = sum(t.get(1, 0) for t in TIMES.values()); tot2 = sum(t.get(2, 0) for t in TIMES.values())
    print(f"time all: plain {tot1 * 1000:.0f} ms, fine {tot2 * 1000:.0f} ms ({tot2 / tot1:.2f}x)")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
