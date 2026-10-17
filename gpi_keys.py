#!/usr/bin/env python3
"""
gpi_keys.py - game controller buttons as keyboard keys, plus a media mode.

Made for the RetroFlag GPi Case 2W, and works on any Raspberry Pi with a screen: a TV or monitor
on HDMI, or the GPi Case's own. The menus are drawn at 640x480 and scaled up to fit.

Controllers: the GPi Case's buttons, or any USB or Bluetooth game controller (Xbox, PlayStation,
8BitDo, the cheap SNES-style ones...), plugged in or out at any time. If a button does the wrong
thing, Settings > Controller sets yours up: press each button it asks for. No HOME button? Press
SELECT and START together.

The web page (webui.py) shows what's on the screen, has a remote, and puts cartoons, films, news,
radio, apps and your own files on the screen. It talks to this script on 127.0.0.1:5480.

While a video plays, Y turns full screen on or off (the choice is kept for the next videos);
Settings > Video size picks Fit (all of the picture), Full screen (zoomed) or Stretch.

Home button toggles between:
  terminal mode - buttons type keys in the console (arrows, Enter, Tab...)
  media mode    - opens on a home screen of app icons (d-pad and A to open one,
                  B or the Terminal icon back to the console). Inside an app,
                  L/R switch apps, X shows the controls and B goes home.

Tabs (edit LIBRARY below to change them):
  TV          - one menu for:
    Plex        - your Plex movies and shows, Continue watching, your Watchlist,
                  and Plex's free Live TV, with search; sign in once with a code at plex.tv/link
    Cartoons    - about 250 old cartoons from the Internet Archive (Popeye, Looney Tunes, Superman,
                  Betty Boop, Casper...), listed in CLASSIC_TOONS below and streamed from
                  archive.org; plus the cartoon and anime channels on Plex's free Live TV
    Free Movies - about 150 old films from the Internet Archive (comedy, noir, horror, westerns,
                  silents), listed in FREE_FILMS below and streamed from archive.org;
                  plus the movie channels on Plex's free Live TV
    News        - the news channels on Plex's free Live TV
    Sports      - the sports channels on Plex's free Live TV
                  (Live TV needs you signed in to Plex, in TV > Plex)
    Streams     - your own list in static/streams.txt, one per line:  Name | URL
                  (a live .m3u8 plays the version that suits the Pi)
    TV Remote   - your TV through Home Assistant (url and long-lived token in
                  static/homeassistant.txt): arrows, OK, back, home, volume, power, inputs,
                  and a number pad for channels (SELECT, then Number pad)
  Music       - files in ~/Music, keeps playing when you go back to the terminal
  Radio       - real stations by genre, popular near you, or search by name (from the free
                Radio Browser directory), and your own list in static/radio.txt
  Photos      - pictures in ~/Pictures as a thumbnail grid, with zoom and slideshow;
                X adds a filter (saved as a copy), SELECT deletes
  Videos      - files in ~/Videos, resume where you left off
  Weather     - like PiE-ink's: now, the next hours, the week, and the US Weather
                Service's own words; the place is set in Settings
  Crypto      - coin prices with charts, laid out like PiE-ink's crypto screen (the coins
                in static/crypto.txt)
  Files       - browse everything; opens photos, PDFs, documents, text, video, music
  Camera      - cameras on your other Pis (PiE-ink, or this repo's camera.py: setup.sh
                --camera) or any MJPEG/JPEG link, listed in static/camera.txt or added by typing
                an address; L/R switch between them, the d-pad steers one that turns
                (an OBSBOT), A takes a picture into ~/Pictures; SELECT has the bot say what it
                sees, out loud with a voice (then holding START sets how fast one turns)
  Bot         - like PiE-ink's bot: a model on another computer running Ollama (Settings >
                Bot, or static/bot.txt) that knows the time, the weather, your coins and what's
                playing, and now and then says something by itself; its face follows the tone
                of what it says. With a model that can see, it looks through your camera and
                says what it sees, and looks at a picture you send it from Photos (X); ask it
                to take a picture and your camera takes one, into Photos and the conversation.
                With a voice (Piper, on the Pi) it says its replies out loud; SELECT says the
                last one again
  System      - CPU temperature, WiFi, storage and more; reboot and shut down
  Settings    - WiFi (scan, connect, forget), home screen background and colours, clock,
                location, units, video size, sound (HDMI, headphones...), controller, start-up

Your settings files (radio.txt, bot.txt...) are in the static folder of the gpi-media folder.
setup.sh tells the service where that is; run by hand, it's the static folder next to this script.

Setup:
    sudo apt install python3-evdev python3-pil python3-numpy fonts-dejavu-core \
                     mplayer poppler-utils
    sudo python3 gpi_keys.py        # try it, Ctrl+C to stop
Optional: sudo apt install libreoffice-core libreoffice-writer libreoffice-calc
          libreoffice-impress  -> documents open with their real layout
          (slow the first time on a Pi Zero). Without it you get the text.

If a button does the wrong thing, set it up in Settings > Controller (or fix CODES below).
"""
import fcntl
import glob
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
import os
import platform
import random
import re
import secrets
import select
import selectors
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
import zipfile

from evdev import InputDevice, UInput, ecodes as e, list_devices

# ---- gamepad code -> button name ------------------------------------------
CODES = {
    e.BTN_SOUTH: "a", e.BTN_EAST: "b", e.BTN_NORTH: "x", e.BTN_WEST: "y",
    e.BTN_TL: "l", e.BTN_TR: "r",
    e.BTN_SELECT: "select", e.BTN_START: "start", e.BTN_MODE: "home",
    e.BTN_DPAD_UP: "up", e.BTN_DPAD_DOWN: "down",
    e.BTN_DPAD_LEFT: "left", e.BTN_DPAD_RIGHT: "right",
}
AXES = {  # d-pad reported as axes
    e.ABS_HAT0X: {-1: "left", 1: "right"},
    e.ABS_HAT0Y: {-1: "up", 1: "down"},
    e.ABS_X:     {-1: "left", 1: "right"},
    e.ABS_Y:     {-1: "up", 1: "down"},
}

# a plain USB pad with no standard layout ("USB Gamepad", most SNES-style pads): the usual
# order of its buttons. If yours differs, set it up in Settings > Controller.
JOY_CODES = {
    e.BTN_TRIGGER: "x", e.BTN_THUMB: "a", e.BTN_THUMB2: "b", e.BTN_TOP: "y",
    e.BTN_TOP2: "l", e.BTN_PINKIE: "r", e.BTN_BASE: "l", e.BTN_BASE2: "r",
    e.BTN_BASE3: "select", e.BTN_BASE4: "start",
}
PADS_FILE = "/var/lib/gpi-keys/pads.json"      # buttons set up in Settings > Controller
NOT_PADS = ("motion sensors", "touchpad", "accelerometer", "consumer control", "system control")
BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "select", "start", "home")
LEARN_STEPS = [   # Settings > Controller: (button, what to press, can be skipped)
    ("a", "A, the OK button", False), ("b", "B, the back button", False),
    ("up", "UP on the d-pad", False), ("down", "DOWN on the d-pad", False),
    ("left", "LEFT on the d-pad", False), ("right", "RIGHT on the d-pad", False),
    ("x", "X", True), ("y", "Y", True), ("l", "L, the left shoulder button", True),
    ("r", "R, the right shoulder button", True), ("select", "SELECT", True),
    ("start", "START", True), ("home", "HOME, or the Guide button", True),
]
LEARN_SKIP = 8             # seconds before a button your controller may not have is skipped
CONTROL_PORT = 5480        # the web page (webui.py) works media mode through this, on this Pi only
CONTROL_KEY = "/run/gpi-keys/control-key"   # ...with this key, readable by you and root only
WEB_PRIVATE = {"webui.txt", "homeassistant.txt", "plex.txt"}   # a password and tokens: never shown
FILE_KINDS = ("dir", "up", "video", "audio", "image", "doc", "text", "pdf", "other")  # files on this Pi

MEDIA_TOGGLE = "home"


# ---- your settings files: the static folder ---------------------------------
def settings_dir():
    """Where your settings files are (radio.txt, bot.txt...): the static folder in the gpi-media
    folder. The service is told where that is (setup.sh); run by hand, it's the one by this script."""
    told = os.environ.get("GPI_MEDIA_STATIC", "").strip()
    if told:
        return os.path.abspath(told)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


STATIC = settings_dir()


def settings_file(name):
    """A settings file's path, in the static folder."""
    return os.path.join(STATIC, name)


def settings_glob(name):
    """...as the pattern the tabs read it by (a folder name with [ or * in it stays as it is)."""
    return glob.escape(settings_file(name))


WEB_PRIVATE_NAME = re.compile(r"[#.~]*(" + "|".join(map(re.escape, sorted(WEB_PRIVATE))) + ")")


def web_private(name):
    """A password or a token, or a copy of one an editor left (webui.txt.save, homeassistant.txt~,
    #plex.txt#), but not complex.txt."""
    return bool(WEB_PRIVATE_NAME.match((name or "").lower()))


# ---- terminal mode: button -> keys ----------------------------------------
TERMINAL = {
    "a":      [e.KEY_ENTER],
    "b":      [e.KEY_BACKSPACE],
    "x":      [e.KEY_TAB],
    "y":      [e.KEY_LEFTCTRL, e.KEY_C],
    "l":      [e.KEY_PAGEUP],
    "r":      [e.KEY_PAGEDOWN],
    "select": [e.KEY_Q],
    "start":  [e.KEY_ESC],
    "up":     [e.KEY_UP],
    "down":   [e.KEY_DOWN],
    "left":   [e.KEY_LEFT],
    "right":  [e.KEY_RIGHT],
}
REPEAT = {e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_BACKSPACE}
REPEAT_DELAY = 0.40
REPEAT_RATE = 0.06

# ---- media mode: file types ---------------------------------------------------
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
DOC_EXTS = {".docx", ".odt", ".pptx", ".odp", ".xlsx", ".ods", ".rtf",
            ".doc", ".xls", ".ppt"}
TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml",
             ".ini", ".cfg", ".conf", ".toml", ".xml", ".html", ".htm", ".css",
             ".py", ".sh", ".js", ".ts", ".c", ".h", ".cpp", ".rs", ".go",
             ".java", ".srt", ".service", ".rules", ".env", ".lua"}

# ---- internet radio: free stations, plus anything in static/radio.txt -------
RADIO_STATIONS = [
    ("Radio Paradise", "eclectic mix", "http://stream.radioparadise.com/mp3-128"),
]
# Real stations from Radio Browser (radio-browser.info): a free, open directory of ~50,000
# stations' own streams. Each genre is the busiest stations across a few of its tags.
RADIO_GENRES = [
    ("Pop & Top 40", "POP", ["pop", "top 40", "hits"]),
    ("Hip-hop & R&B", "HIP", ["hip hop", "hiphop", "rnb"]),
    ("Rock", "ROCK", ["rock", "classic rock"]),
    ("Alternative & Indie", "ALT", ["alternative", "indie"]),
    ("Country", "CTRY", ["country"]),
    ("Latin", "LAT", ["latin", "reggaeton"]),
    ("Dance & EDM", "EDM", ["dance", "edm", "house"]),
    ("80s", "80S", ["80s"]),
    ("90s", "90S", ["90s"]),
    ("Oldies", "OLD", ["oldies", "70s", "60s"]),
    ("Jazz & Soul", "JAZZ", ["jazz", "soul"]),
    ("Reggae", "REGG", ["reggae"]),
    ("K-pop & J-pop", "KPOP", ["kpop", "k-pop", "jpop"]),
    ("Classical", "CLAS", ["classical"]),
    ("Lo-fi & chill", "LOFI", ["lofi", "lo-fi", "chillout"]),
]
RADIO_TTL = 86400                  # a genre's list is fetched again after a day
NOT_MUSIC = {"news", "talk", "sport", "sports", "podcast", "religious", "christian talk", "politics"}
_RB_HOSTS = []


def rb_hosts():
    """Radio Browser's servers, the way it asks: the names behind all.api.radio-browser.info."""
    if not _RB_HOSTS:
        names = []
        try:
            for info in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
                try:
                    name = socket.gethostbyaddr(info[4][0])[0]
                except OSError:
                    continue
                if name.endswith("radio-browser.info") and name not in names:
                    names.append(name)
        except OSError:
            pass
        random.shuffle(names)
        _RB_HOSTS.extend(names or ["de1.api.radio-browser.info", "de2.api.radio-browser.info",
                                   "fi1.api.radio-browser.info"])
    return list(_RB_HOSTS)


def rb_get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    last = None
    for host in rb_hosts():
        try:
            out = fetch_json(f"https://{host}{path}{q}")
            if _RB_HOSTS and _RB_HOSTS[0] != host:      # remember the one that answered
                _RB_HOSTS.remove(host)
                _RB_HOSTS.insert(0, host)
            return out
        except Exception as ex:
            last = ex
    raise last or OSError("no Radio Browser server")


def rb_stations(tags=(), country="", name="", limit=40):
    """The busiest working music stations for some tags, a country or a name."""
    base = {"order": "clickcount", "reverse": "true", "hidebroken": "true", "limit": 80}
    if country:
        base["countrycode"] = country
    queries = [dict(base, tag=t, tagExact="true") for t in tags] or [dict(base, name=name) if name else base]
    found = []
    for q in queries:
        try:
            found += rb_get("/json/stations/search", q) or []
        except Exception:
            if not found and q is queries[-1]:
                raise
    out, seen = [], set()
    for st in sorted(found, key=lambda x: -int(x.get("clickcount") or 0)):
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        title = re.sub(r"\s+", " ", st.get("name") or "").strip()
        tags_ = [t.strip() for t in (st.get("tags") or "").lower().split(",") if t.strip()]
        if (not url or not title or st.get("hls") in (1, "1") or "://" not in url
                or url.split("?")[0].lower().endswith((".m3u8", ".pls", ".m3u", ".asx"))
                or (st.get("codec") or "MP3").upper() not in ("MP3", "AAC", "AAC+", "OGG", "UNKNOWN")
                or set(tags_) & NOT_MUSIC):
            continue
        key = title.lower()
        if key in seen or url in seen:
            continue
        seen.update((key, url))
        sub = " · ".join(x for x in ((st.get("countrycode") or "").upper(),
                                     next((t for t in tags_ if t not in ("music",)), "")) if x)
        it = item("rb:" + (st.get("stationuuid") or url), title[:60], "radio", url, sub=sub)
        it["uuid"] = st.get("stationuuid") or ""
        logo = (st.get("favicon") or "").strip()
        it["logo"] = logo if logo.startswith(("https://", "http://")) else ""   # (for the web page)
        out.append(it)
        if len(out) >= limit:
            break
    return out

# ---- settings: saved with the rest of the state ---------------------------------------
ACCENTS = [("Blue", (96, 170, 228)), ("Teal", (64, 196, 180)), ("Green", (110, 200, 120)),
           ("Purple", (160, 130, 230)), ("Pink", (232, 120, 170)), ("Red", (236, 100, 100)),
           ("Gold", (230, 190, 80)), ("White", (228, 232, 238))]
WALLPAPERS = ["Midnight", "Dusk", "Ocean", "Forest", "Aurora", "Black", "Picture"]
SCREEN_MODES = ["Fit", "Full screen", "Stretch"]   # Settings > Video size; Y while a video plays
SETTINGS = [   # key, label, choices (None: opens a page of its own)
    ("wifi", "WiFi", None),
    ("wallpaper", "Background", WALLPAPERS),
    ("accent", "Accent colour", [a for a, _ in ACCENTS]),
    ("clock", "Clock", ["12-hour", "24-hour"]),
    ("widget", "On the home screen", ["Weather", "Just the time"]),
    ("location", "Location", None),
    ("units", "Temperature", ["°F", "°C"]),
    ("screen", "Video size", SCREEN_MODES),
    ("sound", "Sound", None),
    ("pad", "Controller", None),
    ("friend", "Bot", None),
    ("start", "At start-up", ["Terminal", "Home screen"]),
]
SETTINGS_DEFAULT = {"wallpaper": "Midnight", "picture": "", "accent": "Blue", "clock": "12-hour",
                    "widget": "Weather", "units": "°F", "start": "Terminal", "location": None,
                    "screen": "Fit", "sound": "Auto"}
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WHERE_AM_I = [   # where your internet address says you are (the same ones PiE-ink asks)
    ("https://ipapi.co/json/", lambda d: (d.get("latitude"), d.get("longitude"), d.get("city"),
                                          d.get("region"), d.get("country_code"))),
    ("https://ipwho.is/", lambda d: (d.get("latitude"), d.get("longitude"), d.get("city"),
                                     d.get("region"), d.get("country_code"))),
    ("http://ip-api.com/json/?fields=status,lat,lon,city,regionName,countryCode",
     lambda d: (d.get("lat"), d.get("lon"), d.get("city"), d.get("regionName"), d.get("countryCode"))),
]


def set_accent(name):
    """The accent colour everything draws with."""
    global ACCENT
    ACCENT = dict(ACCENTS).get(name, ACCENTS[0][1])
    BADGE["dir"] = ACCENT


def place_text(loc):
    if not loc:
        return "Not set"
    bits = [loc.get("name")]
    if loc.get("admin") and loc.get("admin") != loc.get("name"):
        bits.append(loc["admin"])
    return ", ".join(b for b in bits if b)


def geocode(name):
    q = urllib.parse.urlencode({"name": name, "count": 8, "language": "en", "format": "json"})
    out = []
    for r in (fetch_json(f"{GEOCODE_URL}?{q}") or {}).get("results") or []:
        out.append({"name": r.get("name", ""), "admin": r.get("admin1", ""),
                    "country": r.get("country_code", ""), "lat": r.get("latitude"),
                    "lon": r.get("longitude")})
    return out


def find_me():
    """Where your internet address says you are, or None."""
    for url, pick in WHERE_AM_I:
        try:
            lat, lon, city, region, cc = pick(fetch_json(url))
            if lat is not None and lon is not None:
                return {"name": city or "Here", "admin": region or "", "country": cc or "",
                        "lat": float(lat), "lon": float(lon)}
        except Exception:
            continue
    return None


def wallpaper(name, size, picture=""):
    """The home screen's background: a picture (darkened so the icons read), or a soft
    gradient with a glow, worked out small and scaled up so it costs little."""
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    w, h = size
    if name == "Picture" and picture:
        try:
            im = ImageOps.fit(ImageOps.exif_transpose(Image.open(picture)).convert("RGB"), size,
                              Image.LANCZOS)
            return Image.blend(im, Image.new("RGB", size, (0, 0, 0)), 0.45)
        except Exception:
            name = "Midnight"
    looks = {   # top colour, bottom colour, glows: (x, y, radius, colour) as fractions of the screen
        "Midnight": (BG, BG, []),
        "Black": ((0, 0, 0), (0, 0, 0), []),
        "Dusk": ((52, 36, 86), (14, 14, 30), [(0.85, 0.05, 0.55, (150, 84, 120))]),
        "Ocean": ((8, 66, 100), (6, 18, 32), [(0.15, 0.0, 0.6, (40, 140, 170))]),
        "Forest": ((22, 72, 52), (8, 20, 16), [(0.8, 0.1, 0.5, (70, 130, 80))]),
        "Aurora": ((10, 16, 30), (8, 14, 22), [(0.2, 0.15, 0.45, (40, 170, 140)),
                                               (0.65, 0.05, 0.5, (100, 80, 200)),
                                               (0.95, 0.35, 0.35, (40, 110, 190))]),
    }
    top, bottom, glows = looks.get(name, looks["Midnight"])
    sw, sh = max(w // 4, 1), max(h // 4, 1)
    small = Image.new("RGB", (sw, sh))
    d = ImageDraw.Draw(small)
    for y in range(sh):
        t = y / max(sh - 1, 1)
        d.line((0, y, sw, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    for gx, gy, gr, col in glows:
        glow = Image.new("L", (sw, sh), 0)
        r = gr * sw
        ImageDraw.Draw(glow).ellipse((gx * sw - r, gy * sh - r, gx * sw + r, gy * sh + r), fill=110)
        glow = glow.filter(ImageFilter.GaussianBlur(r / 2))
        small = Image.composite(Image.new("RGB", (sw, sh), col), small, glow)
    return small.resize(size, Image.BICUBIC)


# the keys of the on-screen keyboard, and what a real keyboard's keys type
KEY_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"]
KEY_SYMBOLS = ["!@#$%^&*()", "-_=+[]{}\\|", ";:'\"<>,.?/", "`~€£¥•°§¿¡"]
KEY_BOTTOM = [("shift", "⇧", 1.5), ("sym", "#+=", 1.5), ("space", "space", 3.5), ("back", "⌫", 1.5),
              ("done", "Done", 2)]


def keyboard_chars():
    table = {}
    for ch in "abcdefghijklmnopqrstuvwxyz":
        code = getattr(e, "KEY_" + ch.upper())
        table[code] = (ch, ch.upper())
    for ch, sh in zip("1234567890", "!@#$%^&*()"):
        table[getattr(e, "KEY_" + ch)] = (ch, sh)
    for name, pair in (("SPACE", (" ", " ")), ("MINUS", ("-", "_")), ("EQUAL", ("=", "+")),
                       ("COMMA", (",", "<")), ("DOT", (".", ">")), ("SLASH", ("/", "?")),
                       ("SEMICOLON", (";", ":")), ("APOSTROPHE", ("'", '"'))):
        table[getattr(e, "KEY_" + name)] = pair
    return table


class KeyReader:
    """A real keyboard (the BBQ20, say) while a text box is up: its keys come here
    instead of going to the hidden console, until the box closes."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.on_key = lambda kind, ch="": None      # ("char", c), ("back",), ("done",), ("cancel",)
        self.exclude = set()

    def start(self):
        if self.thread and self.thread.is_alive():
            self.running = False
            self.thread.join(1)
        devs = []
        try:
            for path in list_devices():
                if path in self.exclude:
                    continue
                dev = InputDevice(path)
                keys = dev.capabilities().get(e.EV_KEY, [])
                if dev.name != NAME and e.KEY_A in keys and e.KEY_Z in keys and e.KEY_ENTER in keys:
                    try:
                        dev.grab()
                    except OSError:
                        pass
                    devs.append(dev)
                else:
                    dev.close()
        except Exception:
            pass
        if devs:
            self.running = True
            self.thread = threading.Thread(target=self.loop, args=(devs,), daemon=True, name="keyboard")
            self.thread.start()

    def stop(self):
        self.running = False

    def loop(self, devs):
        table = keyboard_chars()
        shift = False
        sel = selectors.DefaultSelector()
        for dev in devs:
            sel.register(dev, selectors.EVENT_READ)
        try:
            while self.running:
                for key, _ in sel.select(0.2):
                    try:
                        events = list(key.fileobj.read())
                    except OSError:
                        sel.unregister(key.fileobj)
                        continue
                    for ev in events:
                        if ev.type != e.EV_KEY:
                            continue
                        if ev.code in (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT):
                            shift = ev.value != 0
                        elif ev.value == 0:
                            continue
                        elif ev.code in table:
                            self.on_key("char", table[ev.code][1 if shift else 0])
                        elif ev.code == e.KEY_BACKSPACE:
                            self.on_key("back")
                        elif ev.code in (e.KEY_ENTER, e.KEY_KPENTER):
                            self.on_key("done")
                        elif ev.code == e.KEY_ESC:
                            self.on_key("cancel")
        finally:
            for dev in devs:
                try:
                    dev.ungrab()
                except OSError:
                    pass
                try:
                    dev.close()
                except OSError:
                    pass


# ---- weather: Open-Meteo (free, no key), like PiE-ink ----------------------------------
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
NWS_POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
WEATHER_TTL = 600
WX_CODES = {   # WMO weather codes -> (words, kind)
    0: ("Clear", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "cloud"), 3: ("Overcast", "cloud"),
    45: ("Fog", "fog"), 48: ("Icy fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm, hail", "storm"), 99: ("Thunderstorm, hail", "storm"),
}
WX_TINT = {   # PiE-ink's colours for each kind of weather (on a dark screen)
    "sun": (255, 200, 60), "moon": (205, 215, 240), "cloud": (195, 200, 210), "dark": (150, 156, 168),
    "rain": (90, 160, 255), "snow": (215, 235, 255), "bolt": (245, 200, 80), "fog": (175, 180, 190),
    "wind": (195, 200, 210), "sunset": (255, 150, 80),
}


def wx_words(code):
    try:
        return WX_CODES.get(int(code), ("—", "cloud"))
    except (TypeError, ValueError):
        return ("—", "cloud")


def wx_icon_name(code, is_day=True):
    words, kind = wx_words(code)
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 3
    if kind == "clear":
        return ("sun" if is_day else "moon") if code == 0 else ("partly_day" if is_day else "partly_night")
    if kind == "cloud":
        return "overcast" if code == 3 else ("partly_day" if is_day else "partly_night")
    if kind == "rain":
        return "heavyrain" if code in (55, 57, 65, 67, 82) else "rain"
    return kind                                   # fog, snow, storm


def compass(degrees):
    try:
        return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((float(degrees) + 22.5) // 45) % 8]
    except (TypeError, ValueError):
        return ""


def draw_wx(name, size):
    """A weather picture, drawn three times bigger and scaled down for smooth edges."""
    from PIL import Image, ImageDraw
    S = size * 3
    k = S / 120
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    T = WX_TINT

    def B(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    def L(*pts):
        return [(x * k, y * k) for x, y in pts]

    def sun(cx, cy, r):
        import math
        for t in range(8):
            a = math.radians(t * 45)
            d.line(L((cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35),
                     (cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75)),
                   fill=T["sun"], width=max(1, int(r * 0.22 * k)))
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=T["sun"])

    def moon(cx, cy, r):
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=T["moon"])
        d.ellipse(B(cx - r * 0.35, cy - r * 1.15, cx + r * 1.45, cy + r * 0.65), fill=(0, 0, 0, 0))

    def cloud(x, y, w, colour):
        h = w * 0.5
        d.ellipse(B(x + w * 0.08, y + h * 0.35, x + w * 0.48, y + h * 1.0), fill=colour)
        d.ellipse(B(x + w * 0.26, y, x + w * 0.74, y + h * 0.95), fill=colour)
        d.ellipse(B(x + w * 0.56, y + h * 0.28, x + w * 0.94, y + h * 1.0), fill=colour)
        d.rounded_rectangle(B(x, y + h * 0.55, x + w, y + h * 1.12), radius=h * 0.28 * k, fill=colour)

    if name == "sun":
        sun(60, 60, 26)
    elif name == "moon":
        moon(58, 60, 34)
    elif name == "partly_day":
        sun(76, 42, 18)
        cloud(10, 46, 84, T["cloud"])
    elif name == "partly_night":
        moon(78, 40, 22)
        cloud(10, 46, 84, T["cloud"])
    elif name == "overcast":
        cloud(34, 20, 74, T["dark"])
        cloud(8, 44, 88, T["cloud"])
    elif name == "fog":
        for i, (x0, x1) in enumerate(((18, 102), (8, 92), (24, 108), (14, 84))):
            y = 34 + i * 16
            d.rounded_rectangle(B(x0, y, x1, y + 8), radius=4 * k, fill=T["fog"])
    elif name in ("rain", "heavyrain", "snow", "storm"):
        cloud(10, 14, 100, T["dark"] if name == "storm" else T["cloud"])
        if name == "storm":
            d.polygon(L((62, 64), (44, 94), (58, 94), (50, 116), (78, 82), (63, 82), (72, 64)), fill=T["bolt"])
        elif name == "snow":
            for x, y in ((34, 84), (60, 96), (86, 84), (46, 108), (74, 108)):
                d.ellipse(B(x - 5, y - 5, x + 5, y + 5), fill=T["snow"])
        else:
            drops = (30, 52, 74, 96) if name == "heavyrain" else (38, 62, 86)
            for x in drops:
                d.line(L((x, 76), (x - 8, 102)), fill=T["rain"], width=int(6 * k))
    elif name == "humidity":
        d.polygon(L((60, 14), (30, 70), (90, 70)), fill=T["rain"])
        d.ellipse(B(30, 46, 90, 106), fill=T["rain"])
    elif name == "wind":
        for y, w in ((36, 70), (60, 92), (84, 56)):
            d.line(L((14, y), (14 + w, y)), fill=T["wind"], width=int(9 * k))
            d.arc(B(14 + w - 14, y - 24, 14 + w + 14, y + 4), -90, 90, fill=T["wind"], width=int(9 * k))
    elif name in ("sunrise", "sunset"):
        col = T["sun"] if name == "sunrise" else T["sunset"]
        d.pieslice(B(28, 52, 92, 116), 180, 360, fill=col)
        d.line(L((10, 86), (110, 86)), fill=col, width=int(8 * k))
        tip, base = ((60, 8), 40) if name == "sunrise" else ((60, 44), 12)
        d.line(L((60, 12), (60, 42)), fill=col, width=int(8 * k))
        d.polygon(L((44, base + (0 if name == "sunrise" else 20)), (76, base + (0 if name == "sunrise" else 20)),
                    tip), fill=col)
    return im.resize((size, size), Image.LANCZOS)


class _Stale(Exception):
    pass


class Weather:
    """Now, the next hours and the week from Open-Meteo, and for US places the
    National Weather Service's worded forecast; fetched on a thread and kept on
    disk, so the last forecast shows (with its age) without WiFi. PiE-ink on
    another Pi is asked first: when its forecast is fresh and for here, the home
    screen (and the bot) use it. It has no hours and a shorter week, so the
    Weather tab gets the whole forecast itself."""

    def __init__(self, get_loc, get_units, pie=None):
        self.get_loc, self.get_units = get_loc, get_units
        self.pie = pie
        self.data, self.nws, self.t = None, [], 0.0
        self.src = ""                # "PiE-ink" when what's here came from it
        self.checked = 0.0           # when it was last looked for (PiE-ink asked, or the internet)
        self.error = None
        self.busy = False
        self.on_change = lambda: None
        self.load_cache()

    def key(self):
        loc = self.get_loc()
        if not loc or loc.get("lat") is None:
            return None
        return f"{float(loc['lat']):.3f},{float(loc['lon']):.3f},{self.get_units()}"

    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "weather.json")

    def load_cache(self):
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            if c.get("key") == self.key():
                self.data, self.nws, self.t = c.get("data"), c.get("nws") or [], c.get("t", 0.0)
                self.src = c.get("src") or ""
        except (OSError, ValueError):
            pass

    def save_cache(self, key):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self.cache_path, "w") as f:
                json.dump({"key": key, "data": self.data, "nws": self.nws, "t": self.t, "src": self.src}, f)
        except OSError:
            pass

    def reset(self):
        self.data, self.nws, self.t, self.error, self.src, self.checked = None, [], 0.0, None, "", 0.0
        self.load_cache()
        self.refresh(force=True)

    def partial(self):
        """What's here is PiE-ink's: no hours, a shorter week."""
        return bool(self.data) and not self.data.get("hours")

    def refresh(self, force=False, full=False):
        """Fetched again when it's old (full: the Weather tab, which wants the hours too)."""
        if self.busy or self.key() is None:
            return
        upgrade = full and self.partial()
        if not force:
            if not upgrade and time.time() - self.t < WEATHER_TTL:
                return
            if time.time() - self.checked < 60 and (self.error or not upgrade):
                return                                 # looked a moment ago
        self.busy = True
        threading.Thread(target=self.job, args=(full,), daemon=True, name="weather").start()

    def from_pie(self, key, loc, units):
        """PiE-ink's forecast when it has one for here that isn't too old: taken when it's newer than
        what's here; otherwise its next one is waited for (it's asked again in a minute), as PiE-ink
        is keeping it fresh. True either way: False means the internet is asked."""
        try:
            got = self.pie.weather(loc, units) if self.pie is not None else None
        except Exception:
            got = None
        if not got or got["age"] >= WEATHER_TTL * 1.5:
            return False
        if time.time() - got["age"] <= self.t + 1:
            return True
        if key != self.key():
            raise _Stale()
        self.data, self.t, self.error, self.src = got["data"], time.time() - got["age"], None, "PiE-ink"
        if got["nws"]:
            self.nws = got["nws"]
        self.save_cache(key)
        return True

    def job(self, full=False):
        key, loc, units = self.key(), self.get_loc(), self.get_units()
        self.checked = time.time()
        try:
            if not full and self.from_pie(key, loc, units):
                return
            params = {"latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto",
                      "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                                 "wind_speed_10m,wind_direction_10m,is_day,precipitation",
                      "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
                      "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,"
                               "precipitation_probability_max",
                      "forecast_days": 7}
            if units == "F":
                params.update(temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch")
            else:
                params.update(wind_speed_unit="kmh")
            d = fetch_json(WEATHER_URL + "?" + urllib.parse.urlencode(params))
            c, hr, dl = d.get("current") or {}, d.get("hourly") or {}, d.get("daily") or {}
            hours = []
            times = hr.get("time") or []
            now_hour = str(c.get("time", ""))[:13]
            start = next((i for i, t in enumerate(times) if t[:13] >= now_hour), 0) + 1
            for i in range(start, min(start + 8, len(times))):
                hours.append({"time": times[i], "temp": (hr.get("temperature_2m") or [None] * 999)[i],
                              "code": (hr.get("weather_code") or [None] * 999)[i],
                              "rain": (hr.get("precipitation_probability") or [None] * 999)[i],
                              "is_day": bool((hr.get("is_day") or [1] * 999)[i])})
            days = []
            for i, day in enumerate(dl.get("time") or []):
                def col(name, default=None):
                    v = dl.get(name) or []
                    return v[i] if i < len(v) else default
                days.append({"date": day, "code": col("weather_code"), "hi": col("temperature_2m_max"),
                             "lo": col("temperature_2m_min"), "rain": col("precipitation_probability_max"),
                             "sunrise": str(col("sunrise", ""))[-5:], "sunset": str(col("sunset", ""))[-5:]})
            if key != self.key():                      # the place or units changed meanwhile
                raise _Stale()
            self.data = {"temp": c.get("temperature_2m"), "feels": c.get("apparent_temperature"),
                         "humidity": c.get("relative_humidity_2m"), "wind": c.get("wind_speed_10m"),
                         "wind_dir": c.get("wind_direction_10m"), "code": c.get("weather_code"),
                         "is_day": bool(c.get("is_day", 1)), "units": units, "hours": hours, "days": days}
            self.t, self.error, self.src = time.time(), None, ""
            if str(loc.get("country", "")).upper() == "US":
                try:
                    pt = fetch_json(NWS_POINTS.format(lat=float(loc["lat"]), lon=float(loc["lon"])))
                    fc = fetch_json(pt["properties"]["forecast"])
                    self.nws = [[p.get("name", ""), p.get("detailedForecast", "")]
                                for p in fc["properties"]["periods"][:6]]
                except Exception:
                    pass
            if key == self.key():
                self.save_cache(key)
        except _Stale:
            self.t = 0.0
        except Exception:
            self.error = "Can't reach the weather service"
            if not self.data:
                self.t = time.time()
        finally:
            self.busy = False
            self.on_change()
            if key != self.key():
                self.refresh(force=True)               # for where you are now


# ---- WiFi: NetworkManager (Raspberry Pi OS Bookworm), through nmcli -------------------
def nm(args, timeout=20):
    """(ok, output, error) from nmcli."""
    try:
        r = subprocess.run(["nmcli"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr.strip()
    except FileNotFoundError:
        return False, "", "nmcli isn't installed (NetworkManager)"
    except subprocess.TimeoutExpired:
        return False, "", "it took too long"


def nm_fields(line):
    """nmcli -t splits fields with ':' and writes a ':' inside one as '\\:'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def wifi_saved():
    """SSID -> the saved profile's name (a profile can be named differently from its network)."""
    ok, out, _ = nm(["-t", "-f", "NAME,TYPE", "connection", "show"], 10)
    saved = {}
    for line in out.splitlines() if ok else []:
        f = nm_fields(line)
        if len(f) >= 2 and f[1] == "802-11-wireless":
            ok2, ssid, _ = nm(["-g", "802-11-wireless.ssid", "connection", "show", f[0]], 10)
            saved[(ssid.strip() if ok2 and ssid.strip() else f[0])] = f[0]
    return saved


def wifi_scan():
    """The networks around, strongest first: [{ssid, signal, secure, active}]."""
    ok, out, err = nm(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], 30)
    if not ok:                                      # scanned a moment ago: take what it has
        ok, out, err = nm(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"], 20)
    if not ok:
        raise ValueError(err or "Can't scan for WiFi")
    nets = {}
    for line in out.splitlines():
        f = nm_fields(line)
        if len(f) < 4 or not f[1].strip():
            continue                                # hidden networks have no name
        ssid = f[1]
        sig = int(f[2]) if f[2].isdigit() else 0
        net = {"ssid": ssid, "signal": sig, "secure": f[3].strip() not in ("", "--"),
               "active": f[0].strip() == "*"}
        old = nets.get(ssid)
        if not old or net["active"] or (sig > old["signal"] and not old["active"]):
            nets[ssid] = net
    return sorted(nets.values(), key=lambda n: (not n["active"], -n["signal"]))


def nm_why(err):
    e = err.lower()
    if "secrets were required" in e or "802-1x" in e or "password" in e and "invalid" in e:
        return "Wrong password?"
    if "no network with ssid" in e:
        return "That network isn't in range"
    if "timeout" in e or "too long" in e:
        return "It took too long"
    return err.split("\n")[-1][:70] or "Couldn't connect"


# ---- the home screen: an icon for each tab, plus one back to the terminal -----------
HOME_COLS = (4, 5, 6)     # icons across: whichever fills the rows best (4 first, like a phone)


def home_cols(n, rows=3):
    """Columns for n icons so the last row isn't left with gaps (in up to `rows` rows)."""
    def gaps(c):
        r = -(-n // c)
        return (r > rows, r * c - n)
    return min(HOME_COLS, key=gaps)
def home_layout(n, cols):
    """(row, column) of each icon on the home screen. A short last row sits in the middle, so
    there are no gaps at its end (its columns can be halves)."""
    rows = -(-n // cols)
    last = n - (rows - 1) * cols
    out = []
    for k in range(n):
        r, c = divmod(k, cols)
        if r == rows - 1 and last < cols:
            c += (cols - last) / 2
        out.append((r, c))
    return out


HOME_ICONS = {    # tab name -> (tile colour, a line about it)
    "TV": ((62, 112, 204), "Plex, cartoons, films, news, sports, remote"),
    "Music": ((200, 82, 118), "Your music in ~/Music"),
    "Radio": ((126, 96, 200), "Internet radio"),
    "Photos": ((38, 146, 136), "Pictures in ~/Pictures"),
    "Videos": ((196, 84, 72), "Your videos in ~/Videos"),
    "Crypto": ((8, 10, 10), "Coin prices and charts"),
    "Files": ((76, 114, 154), "Everything in your home folder"),
    "Camera": ((64, 72, 86), "Your cameras: watch, steer, take pictures"),
    "Bot": ((60, 156, 104), "A bot to talk to"),
    "System": ((88, 96, 110), "Temperature, WiFi, storage"),
    "Settings": ((112, 120, 134), "WiFi, background, sound, controllers"),
    "Weather": ((60, 150, 212), "Now, the next hours and the week"),
    "Terminal": ((20, 22, 26), "Back to the console"),
}


def draw_icon(name, size=84):
    """An app icon: a rounded tile with a simple white glyph, drawn three times
    bigger and scaled down so the edges come out smooth."""
    from PIL import Image, ImageDraw, ImageFont
    S = size * 3
    k = S / 252                                     # the glyphs are laid out on a 252 square
    colour = HOME_ICONS.get(name, ((70, 80, 96), ""))[0]
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dark = sum(colour) < 120
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(66 * k), fill=colour,
                        outline=(52, 58, 68) if dark else None, width=int(4 * k))
    white = (246, 248, 250)

    def P(*pts):
        return [(x * k, y * k) for x, y in pts]

    def B(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    if name == "TV":
        for tip in ((96, 42), (156, 42)):
            d.line(P((126, 76), tip), fill=white, width=int(10 * k))
            d.ellipse(B(tip[0] - 7, tip[1] - 7, tip[0] + 7, tip[1] + 7), fill=white)
        d.rounded_rectangle(B(44, 74, 208, 178), radius=int(20 * k), fill=white)
        d.rounded_rectangle(B(60, 90, 192, 162), radius=int(8 * k), fill=colour)
        d.rectangle(B(118, 176, 134, 194), fill=white)
        d.rounded_rectangle(B(86, 190, 166, 204), radius=int(7 * k), fill=white)
    elif name == "Music":
        d.rectangle(B(104, 68, 118, 168), fill=white)
        d.rectangle(B(180, 52, 194, 152), fill=white)
        d.polygon(P((104, 68), (194, 52), (194, 80), (104, 96)), fill=white)
        d.ellipse(B(62, 146, 118, 188), fill=white)
        d.ellipse(B(138, 130, 194, 172), fill=white)
    elif name == "Radio":
        c = (126, 112)
        for r in (46, 78):
            box = B(c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            d.arc(box, 140, 220, fill=white, width=int(13 * k))
            d.arc(box, -40, 40, fill=white, width=int(13 * k))
        d.polygon(P((126, 118), (98, 208), (154, 208)), fill=white)
        d.ellipse(B(108, 94, 144, 130), fill=white)
    elif name == "Photos":
        d.rounded_rectangle(B(40, 62, 212, 192), radius=int(20 * k), fill=white)
        d.polygon(P((54, 180), (106, 112), (140, 150), (168, 122), (200, 180)), fill=colour)
        d.ellipse(B(150, 78, 182, 110), fill=colour)
    elif name == "Videos":                          # a clapperboard
        d.rounded_rectangle(B(44, 104, 208, 198), radius=int(14 * k), fill=white)
        d.polygon(P((40, 74), (196, 46), (202, 78), (46, 106)), fill=white)
        for x in (62, 104, 146):                    # the stripes on the arm and the board
            d.polygon(P((x, 70 - (x - 40) * 0.18), (x + 20, 66 - (x - 40) * 0.18),
                        (x + 26, 98 - (x - 40) * 0.18), (x + 6, 102 - (x - 40) * 0.18)), fill=colour)
            d.polygon(P((x, 104), (x + 22, 104), (x + 8, 126), (x - 14, 126)), fill=colour)
        d.rectangle(B(44, 126, 208, 130), fill=colour)
    elif name == "Crypto":
        green = (0, 230, 90)
        d.line(P((46, 180), (88, 140), (120, 158), (162, 100), (198, 70)), fill=green,
               width=int(15 * k), joint="curve")
        d.polygon(P((214, 54), (174, 62), (206, 94)), fill=green)
        d.line(P((46, 206), (206, 206)), fill=(60, 66, 72), width=int(5 * k))
    elif name == "Files":
        d.polygon(P((42, 66), (104, 66), (124, 90), (42, 90)), fill=white)
        d.rounded_rectangle(B(42, 84, 210, 192), radius=int(16 * k), fill=white)
        d.rectangle(B(42, 102, 210, 108), fill=colour)
    elif name == "Camera":
        d.rounded_rectangle(B(92, 60, 160, 92), radius=int(10 * k), fill=white)
        d.rounded_rectangle(B(38, 82, 214, 194), radius=int(24 * k), fill=white)
        d.ellipse(B(82, 96, 170, 184), fill=colour)
        d.ellipse(B(102, 116, 150, 164), fill=white)
        d.ellipse(B(182, 100, 198, 116), fill=colour)
    elif name == "System":                         # a chip
        d.rounded_rectangle(B(74, 74, 178, 178), radius=int(14 * k), fill=white)
        d.rounded_rectangle(B(98, 98, 154, 154), radius=int(8 * k), fill=colour)
        for t in range(4):
            off = 90 + t * 24
            for a, b_ in (((off, 46), (off, 74)), ((off, 178), (off, 206)),
                          ((46, off), (74, off)), ((178, off), (206, off))):
                d.line(P(a, b_), fill=white, width=int(10 * k))
    elif name == "Settings":                       # a gear
        import math
        pts = []
        for t in range(8):
            a = math.radians(t * 45)
            for r, da in ((64, -17), (88, -9), (88, 9), (64, 17)):
                pts.append((126 + r * math.cos(a + math.radians(da)), 126 + r * math.sin(a + math.radians(da))))
        d.polygon(P(*pts), fill=white)
        d.ellipse(B(98, 98, 154, 154), fill=colour)
    elif name == "Weather":                        # sun behind a cloud
        d.ellipse(B(118, 52, 194, 128), fill=(255, 214, 90))
        for x0, y0, x1, y1 in ((52, 116, 120, 184), (88, 88, 168, 168), (136, 118, 200, 182)):
            d.ellipse(B(x0, y0, x1, y1), fill=white)
        d.rounded_rectangle(B(70, 140, 186, 184), radius=int(22 * k), fill=white)
    elif name == "Bot":                            # a speech bubble with a smile
        d.rounded_rectangle(B(40, 54, 212, 170), radius=int(42 * k), fill=white)
        d.polygon(P((76, 158), (60, 210), (126, 166)), fill=white)
        d.ellipse(B(88, 90, 110, 112), fill=colour)
        d.ellipse(B(142, 90, 164, 112), fill=colour)
        d.arc(B(90, 96, 162, 148), 25, 155, fill=colour, width=int(11 * k))
    elif name == "Terminal":
        green = (96, 222, 144)
        d.line(P((68, 90), (112, 126), (68, 162)), fill=green, width=int(17 * k), joint="curve")
        d.rectangle(B(128, 150, 190, 166), fill=green)
    else:                                           # a tab added by hand: its first letter
        try:
            font = ImageFont.truetype(FONT_BOLD, int(120 * k))
        except OSError:
            font = ImageFont.load_default()
        d.text((S / 2, S / 2), (name[:1] or "?").upper(), font=font, fill=white, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


# Cartoons and Free Movies: channels from Plex's free Live TV, picked by name and kind
ANIME_WORDS = ("anime", "animé", "naruto", "one piece", "dragon ball", "pokémon", "pokemon", "sailor moon",
               "gundam", "yu-gi-oh", "hidive", "crunchyroll", "retrocrush", "funimation", "toei", "shonen",
               "shōnen", "manga", "hunter x hunter", "bleach", "inuyasha", "ultraman", "voltron")
TOON_WORDS = ("cartoon", "toon", "animat", "kids", "children", "junior", "nick", "looney", "popeye",
              "scooby", "pink panther", "garfield", "smurf", "teletubbies", "barney", "sesame",
              "power rangers", "transformers", "he-man", "inspector gadget", "care bears", "baby")
CHANNEL_REFRESH = 6 * 3600    # Plex's list of Live TV channels is fetched again after this


def channel_text(c):
    return (c["title"] + " " + c["genre"]).lower()


def is_anime(c):
    return any(w in channel_text(c) for w in ANIME_WORDS)


def is_toon(c):
    return any(w in channel_text(c) for w in TOON_WORDS)


NEWS_WORDS = ("news", "reuters", "bloomberg", "euronews", "france 24", "al jazeera", "weather",
              "c-span", "cheddar", "politic")
SPORT_WORDS = ("sport", "nfl", "nba", "mlb", "nhl", "golf", "tennis", "soccer", "football", "fútbol",
               "racing", "motor", "boxing", "wrestling", "fight", "ufc", "mma", "olympic", "fubo",
               "stadium", "pbr", "rodeo", "poker", "billiard", "surf", "skate", "fishing", "hunting",
               "outdoor", "cycling", "rugby", "cricket", "hockey", "baseball", "basketball",
               "volleyball", "lacrosse", "red bull")


def is_news(c):
    return any(w in channel_text(c) for w in NEWS_WORDS)


def is_sport(c):
    return any(w in channel_text(c) for w in SPORT_WORDS)


def live_pick(what, c):
    """Whether a Plex Live TV channel belongs in a list: anime, toons, movies, news or sports."""
    if what == "anime":
        return is_anime(c)
    if what == "toons":
        return is_toon(c) and not is_anime(c)
    if what == "movies":
        return "movie" in c["genre"].lower()
    if what == "news":
        return is_news(c)
    if what == "sports":
        return is_sport(c)
    return False


def channel_row(c):
    return dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"], sub=c["genre"]),
                thumb=None, ptype="channel")


# Old cartoons from the Internet Archive, built in so Cartoons opens at once: no
# searching the Archive. Each streams from archive.org when you play it.
#   folder | title | year | archive.org item | the file in it
# (add more the same way: the item is the last part of its archive.org/details/... link)
CLASSIC_TOONS = """
Popeye | I'm in the Army Now | 1936 | im_in_the_army_now | im_in_the_army_now_512kb.mp4
Popeye | Little Swee'Pea | 1936 | little-sweepea-1936 | Little Swee'pea (1936).mp4
Popeye | Popeye the Sailor Meets Sindbad the Sailor | 1936 | Popeye_meetsSinbadtheSailor | Popeye_meetsSinbadtheSailor_512kb.mp4
Popeye | I Never Changes My Altitude | 1937 | MorePopeyeCartoons | INeverChangesMyAltitude_512kb.mp4
Popeye | Popeye the Sailor Meets Ali Baba's Forty Thieves | 1937 | PopeyeAliBaba | PopeyeAliBaba_512kb.mp4
Popeye | The Paneless Window Washer | 1937 | Popeye_ThePanelessWindowWasher | Popeye_ThePanelessWindowWasher_512kb.mp4
Popeye | A Date to Skate | 1938 | MorePopeyeCartoons | ADateToSkate_512kb.mp4
Popeye | Aladdin and His Wonderful Lamp | 1939 | Popeye_the_Sailor_Meets_Aladdin_and_His_Wonderful_Lamp | Popeye_-_Aladdin_and_His_Wonderful_Lamp_512kb.mp4
Popeye | Customers Wanted | 1939 | customers_wanted | customers_wanted_512kb.mp4
Popeye | Me Musical Nephews | 1942 | popeye-pubdomain | Me-Musical-Nephews.mp4
Popeye | Big Bad Sindbad | 1952 | AHaulInOne1956 | Big Bad Sindbad (1952).mp4
Popeye | Shuteye Popeye | 1952 | popeye_shuteye_popeye | popeye_shuteye_popeye_512kb.mp4
Popeye | Ancient Fistory | 1953 | popeye_the_sailor_ancient_fantasy | popeye_the_sailor_ancient_fantasy_512kb.mp4
Popeye | Bride and Gloom | 1954 | Popeye_BrideandGloom | Popeye_BrideandGloom_512kb.mp4
Popeye | Floor Flusher | 1954 | Popeye_Floor_Flusher_1954 | Popeye_Floor_Flusher_512kb.mp4
Popeye | Fright to the Finish | 1954 | popeye_fright_to_the_finish | popeye_fright_to_the_finish_512kb.mp4
Popeye | Gopher Spinach | 1954 | Popeye_Gopher_Spinach_1954 | Popeye_Gopher_Spinach_512kb.mp4
Popeye | Greek Mirthology | 1954 | Popeye_Greek_Mirthology_1954 | Popeye_Greek_Mirthology_512kb.mp4
Popeye | Popeye's 20th Anniversary | 1954 | MorePopeyeCartoons | Popeyes20thAnniversary_512kb.mp4
Popeye | Private Eye Popeye | 1954 | popeye_private_eye_popeye | popeye_private_eye_popeye_512kb.mp4
Popeye | Taxi-Turvy | 1954 | popeye_taxi-turvey | popeye_taxi-turvey_512kb.mp4
Popeye | Cookin' with Gags | 1955 | Popeye_Cooking_With_Gags_1954 | Popeye_Cookin_with_Gags_512kb.mp4
Popeye | A Haul in One | 1956 | AHaulInOne1956 | A Haul in One (1956).mp4
Popeye | Assault and Flattery | 1956 | Popeye_Assault_and_Flattery_1956 | Popeye_Assault_and_Flattery_512kb.mp4
Popeye | I Don't Scare | 1956 | popeye_i_dont_scare | popeye_i_dont_scare_512kb.mp4
Popeye | Insect to Injury | 1956 | insect_to_injury | insect_to_injury_512kb.mp4
Popeye | Out to Punch | 1956 | Popeye_Out_of_the_Punch_1956 | Popeye_Out_To_Punch_1956_512kb.mp4
Popeye | Parlez Vous Woo | 1956 | Popeye_Parlez_Vous_Woo_1956 | Popeye_Parlez_Vous_Woo_1956_512kb.mp4
Popeye | Popeye for President | 1956 | Popeye_forPresident | Popeye_forPresident_512kb.mp4
Popeye | Nearlyweds | 1957 | Popeye_Nearlyweds | Popeye_Nearlyweds_512kb.mp4
Popeye | Patriotic Popeye | 1957 | popeye_patriotic_popeye | popeye_patriotic_popeye_512kb.mp4
Popeye | Spooky Swabs | 1957 | MorePopeyeCartoons | SpookySwabs_512kb.mp4
Popeye | Spree Lunch | 1957 | spree_lunch | spree_lunch_512kb.mp4
Popeye | The Crystal Brawl | 1957 | MorePopeyeCartoons | TheCrystalBrawl_512kb.mp4
Looney Tunes | Bosko the Doughboy | 1931 | bosko-the-doughboy-1931_202305 | Bosko the Doughboy (1931).mp4
Looney Tunes | Ups 'n Downs | 1931 | ups-n-downs-1931 | Ups 'n Downs (1931).mp4
Looney Tunes | Yodeling Yokels | 1931 | yodeling-yokels-1931 | Yodeling Yokels (1931).mp4
Looney Tunes | Battling Bosko | 1932 | BattlingBosko1931HughHarmanRudolfIsing | Battling Bosko 1931 Hugh Harman, Rudolf Ising .mp4
Looney Tunes | Get Rich Quick Porky | 1937 | get-rich-quick-porky-1937 | Get Rich Quick Porky (1937).mp4
Looney Tunes | Porky's Railroad | 1937 | PorkysRailroad_48 | 1937-porkyPig-PorkysRailroad.mp4
Looney Tunes | Daffy Duck and the Dinosaur | 1939 | DaffyDuckAndTheDinosaur1939_201707 | Daffy Duck and the Dinosaur (1939).mp4
Looney Tunes | Prest-O Change-O | 1939 | prest-o-change-o-1939 | Prest-O Change-O (1939).mp4
Looney Tunes | Robin Hood Makes Good | 1939 | robin-hood-makes-good-1939 | Robin Hood Makes Good (1939).mp4
Looney Tunes | A Coy Decoy | 1941 | a-coy-decoy-1941 | A Coy Decoy (1941).mp4
Looney Tunes | Notes to You | 1941 | notes-to-you-1941 | Notes to You (1941).mp4
Looney Tunes | Porky's Ant | 1941 | porkys-ant-1941 | Porky's Ant (1941).mp4
Looney Tunes | Porky's Bear Facts | 1941 | porkys-bear-facts-1941 | Porky's Bear Facts (1941).mp4
Looney Tunes | Porky's Preview | 1941 | porkys-preview-1941 | Porky's Preview (1941).mp4
Looney Tunes | Porky's Prize Pony | 1941 | porkys-prize-pony-1941 | Porky's Prize Pony (1941).mp4
Looney Tunes | The Henpecked Duck | 1941 | the-henpecked-duck-1941 | The Henpecked Duck (1941).mp4
Looney Tunes | We, the Animals Squeak! | 1941 | we-the-animals-squeak-1941 | We, the Animals Squeak! (1941).mp4
Looney Tunes | A Tale of Two Kitties | 1942 | a-tale-of-two-kitties-1942_202304 | A Tale of Two Kitties (1942).mp4
Looney Tunes | Case of the Missing Hare | 1942 | case-of-the-missing-hare-1942 | Case of the Missing Hare (1942).mp4
Looney Tunes | Fox Pop | 1942 | fox-pop-1942 | Fox Pop (1942).mp4
Looney Tunes | Fresh Hare | 1942 | fresh-hare-1942 | Fresh Hare (1942).mp4
Looney Tunes | Porky's Cafe | 1942 | porkys-cafe-1942 | Porky's Cafe (1942).mp4
Looney Tunes | Porky's Pastry Pirates | 1942 | porkys-pastry-pirates-1942 | Porky's Pastry Pirates (1942).mp4
Looney Tunes | The Daffy Duckaroo | 1942 | TheDaffyDuckaroo_109 | TheDaffyDuckaroo.mp4
Looney Tunes | The Dover Boys at Pimento University | 1942 | the-dover-boys-at-pimento-university-or-the-rivals-of-roquefort-hall | The Dover Boys at Pimento University or The Rivals of Roquefort Hall.mp4
Looney Tunes | The Ducktators | 1942 | DucktatorsWwii | 08-TheDucktators_512kb.mp4
Looney Tunes | The Impatient Patient | 1942 | the-impatient-patient-1942 | The Impatient Patient (1942).mp4
Looney Tunes | The Wabbit Who Came to Supper | 1942 | the-wabbit-who-came-to-supper-1942 | The Wabbit Who Came to Supper (1942).mp4
Looney Tunes | The Wacky Wabbit | 1942 | the-wacky-wabbit-1942 | The Wacky Wabbit (1942).mp4
Looney Tunes | A Corny Concerto | 1943 | ACornyConcerto1943BugsBunny | ACornyConcerto1943BugsBunnyDaffyDuckElmerFudd-m735o_eewgg.mp4
Looney Tunes | Confusions of a Nutzy Spy | 1943 | ConfusionsOfANutzySpy1943 | Confusions of a Nutzy Spy (1943)-b0uVtS7nrCA.mp4
Looney Tunes | Daffy - The Commando | 1943 | DaffyDuckAndTheDinosaur1939_201707 | Daffy the Commando (1943).mp4
Looney Tunes | Falling Hare | 1943 | falling-hare-1943 | Falling Hare (1943).mp4
Looney Tunes | Pigs in a Polka | 1943 | pigs-in-a-polka-1943 | Pigs in a Polka (1943).mp4
Looney Tunes | Porky Pig's Feat | 1943 | porky-pigs-feat-1943 | Porky Pig's Feat (1943).mp4
Looney Tunes | Scrap Happy Daffy | 1943 | scraphappydaffy | scraphappydaffy.mp4
Looney Tunes | The Fifth-Column Mouse | 1943 | the-fifth-column-mouse-1943 | The Fifth-Column Mouse (1943).mp4
Looney Tunes | To Duck or Not to Duck | 1943 | DaffyDuckAndTheDinosaur1939_201707 | To Duck or not To Duck (1943).mp4
Looney Tunes | Wackiki Wabbit | 1943 | wackiki-wabbit-1943 | Wackiki Wabbit (1943).mp4
Looney Tunes | Yankee Doodle Daffy | 1943 | yankee-doodle-daffy-1943_202304 | Yankee Doodle Daffy (1943).mp4
Superman | The Mad Scientist | 1941 | superman_the_mad_scientist | Superman-01-The_Mad_Scientist_512kb.mp4
Superman | The Mechanical Monsters | 1941 | superman_the_mechanical_monsters | superman_the_mechanical_monsters_512kb.mp4
Superman | Billion Dollar Limited | 1942 | superman_billion_dollar_limited | billion_dollar_limited.mp4
Superman | Destruction, Inc. | 1942 | superman_destruction_inc | Superman-13-Destruction_Inc_512kb.mp4
Superman | Electric Earthquake | 1942 | superman_electric_earthquake | superman_electric_earthquake_512kb.mp4
Superman | Eleventh Hour | 1942 | superman_eleventh_hour | superman_eleventh_hour_512kb.mp4
Superman | Japoteurs | 1942 | japoteurs | japoteurs_512kb.mp4
Superman | Showdown | 1942 | showdown | showdown_512kb.mp4
Superman | Terror on the Midway | 1942 | superman_terror_on_the_midway | Superman-09-Terror_on_the_Midway_512kb.mp4
Superman | The Arctic Giant | 1942 | arctic_giant | arctic_giant_512kb.mp4
Superman | The Bulleteers | 1942 | bulleteers | bulleteers_512kb.mp4
Superman | The Magnetic Telescope | 1942 | magnetic_telescope | magnetic_telescope_512kb.mp4
Superman | Volcano | 1942 | superman_volcano | Superman-08-Volcano_512kb.mp4
Superman | Jungle Drums | 1943 | jungle_drums | jungle_drums_512kb.mp4
Superman | Secret Agent | 1943 | secret_agent | secret_agent_512kb.mp4
Superman | The Mummy Strikes | 1943 | mummy_strikes | mummy_strikes_512kb.mp4
Superman | The Underground World | 1943 | superman_underground_world | Superman-16-The_Underground_World_512kb.mp4
Betty Boop | Bamboo Isle | 1932 | bb_bamboo_isle | bb_bamboo_isle_512kb.mp4
Betty Boop | Betty Boop for President | 1932 | Betty_Boop_for_President_1932 | Betty_Boop_for_President_1932_512kb.mp4
Betty Boop | Chess-Nuts | 1932 | bb_chess_nuts | bb_chess_nuts_512kb.mp4
Betty Boop | Minnie the Moocher | 1932 | bb_minnie_the_moocher | bb_minnie_the_moocher_512kb.mp4
Betty Boop | Betty Boop's Big Boss | 1933 | bb_big_boss | bb_big_boss_512kb.mp4
Betty Boop | Betty Boop's Crazy Inventions | 1933 | Betty_Boops_Crazy_Inventions_1933 | Betty_Boops_Crazy_Inventions_1933_512kb.mp4
Betty Boop | Betty Boop's Ker-Choo | 1933 | BettyBoopCartoons | Betty_Boops_KerCho_1932_512kb.mp4
Betty Boop | I Heard | 1933 | BettyBoop-IHeared1932 | BettyBoop-IHeared1932._512kb.mp4
Betty Boop | Is My Palm Read? | 1933 | BettyBoopCartoons | Betty_Boop_Is_My_Palm_Read_1932_512kb.mp4
Betty Boop | Morning, Noon and Night | 1933 | bb_morning_noon_and_night | bb_morning_noon_and_night_512kb.mp4
Betty Boop | Mother Goose Land | 1933 | Betty_Boop_Mother_Goose_Land_1933 | Betty_Boop_Mother_Goose_Land_1933_512kb.mp4
Betty Boop | Parade of the Wooden Soldiers | 1933 | bb_parade_of_the_wooden_soldiers | bb_parade_of_the_wooden_soldiers_512kb.mp4
Betty Boop | Snow White | 1933 | bb_snow_white | bb_snow_white_512kb.mp4
Betty Boop | The Old Man of the Mountain | 1933 | bb_old_man_of_the_mountain | bb_old_man_of_the_mountain_512kb.mp4
Betty Boop | Betty Boop's Rise to Fame | 1934 | bb_rise_to_fame | bb_rise_to_fame_512kb.mp4
Betty Boop | Betty in Blunderland | 1934 | bb_betty_in_blunderland | bb_betty_in_blunderland_512kb.mp4
Betty Boop | A Language All My Own | 1935 | Betty_Boop_a_Language_All_My_Own_1935 | Betty_Boop_a_Language_All_My_Own_1935_512kb.mp4
Betty Boop | Baby Be Good | 1935 | Betty_Boop_Baby_Be_Good_1935 | Betty_Boop_Baby_Be_Good_1935_512kb.mp4
Betty Boop | Betty Boop and Grampy | 1935 | bb_and_grampy | bb_and_grampy_512kb.mp4
Betty Boop | Betty Boop with Henry | 1935 | Betty_Boop_with_Henry_1935 | Betty_Boop_with_Henry_1935_512kb.mp4
Betty Boop | Judge for a Day | 1935 | Betty_Boop_Judge_For_a_Day_1935 | Betty_Boop_Judge_For_a_Day_1935_512kb.mp4
Betty Boop | Stop That Noise | 1935 | bb_stop_that_noise | bb_stop_that_noise_512kb.mp4
Betty Boop | Swat the Fly | 1935 | bb_swat_the_fly | bb_swat_that_fly_512kb.mp4
Betty Boop | A Song a Day | 1936 | BettyBoopCartoons | Betty_Boop_A_Song_a_Day_1936_512kb.mp4
Betty Boop | Betty Boop and Little Jimmy | 1936 | Betty_Boop_and_Little_Jimmy_1936 | Betty_Boop_and_Little_Jimmy_1936_512kb.mp4
Betty Boop | Betty Boop and the Little King | 1936 | bb_and_the_little_king | bb_and_the_little_king_512kb.mp4
Betty Boop | Happy You and Merry Me | 1936 | bb_happy_you | bb_happy_you_512kb.mp4
Betty Boop | More Pep | 1936 | BettyBoopCartoons | Betty_Boop_More_Pep_1936_512kb.mp4
Betty Boop | Not Now | 1936 | bb_not_now | bb_not_now_512kb.mp4
Betty Boop | Training Pigeons | 1936 | Betty_Boop_Training_Pigeons_1936 | Betty_Boop_Training_Pigeons_1936_512kb.mp4
Betty Boop | House Cleaning Blues | 1937 | bb_house_cleaning_blues | bb_house_cleaning_blues_512kb.mp4
Betty Boop | The Candid Candidate | 1937 | BettyBoopCartoons | The_Candid_Candidate_1937_512kb.mp4
Betty Boop | The Impractical Joker | 1937 | bb_the_impractical_joker | bb_the_impractical_joker_512kb.mp4
Betty Boop | Whoops! I'm a Cowboy | 1937 | Betty_Boop_Whoops_Im_a_Cowboy_1937 | Whoops_Im_a_Cowboy_1937_512kb.mp4
Betty Boop | Musical Mountaineers | 1939 | bb_musical_mountaineers | bb_musical_mountaineers_512kb.mp4
Betty Boop | The Scared Crows | 1939 | Betty_Boop_The_Scared_Crows_1939 | Betty_Boop_The_Scared_Crows_1939_512kb.mp4
Casper & friends | Little Lulu: Lulu's Birthday Party | 1944 | 1944LulusBirthdayParty | 1944-12-29 Lulu's Birthday Party.mp4
Casper & friends | The Friendly Ghost | 1945 | TheFriendlyGhost | TheFriendlyGhost_512kb.mp4
Casper & friends | Little Lulu: Bargain Counter Attack | 1946 | littlelulu-publicdomain | Bargain Counter Attack (1946).mp4
Casper & friends | Little Lulu: Bored of Education | 1946 | littlelulu-publicdomain | Bored of Education (1946).mp4
Casper & friends | Little Lulu: Chick and Double Chick | 1946 | littlelulu-publicdomain | Chick and Double Chick (1946).mp4
Casper & friends | Herman: Naughty But Mice | 1947 | herman-the-mouse-naughty-but-mice | Herman the Mouse - Naughty But Mice.mp4
Casper & friends | Little Lulu: A Bout with a Trout | 1947 | littlelulu-publicdomain | A Bout with a Trout (1947).mp4
Casper & friends | Little Lulu: Cad and Caddy | 1947 | littlelulu-publicdomain | Cad and Caddy (1947).mp4
Casper & friends | Little Lulu: Musica-Lulu | 1947 | littlelulu-publicdomain | Musica-Lulu (1947).mp4
Casper & friends | Little Lulu: Super Lulu | 1947 | littlelulu-publicdomain | Super Lulu (1947).mp4
Casper & friends | Little Audrey: Butterscotch and Soda | 1948 | LittleAudreyInbutterscotchAndSoda1948 | ButterscotchAndSoda_512kb.mp4
Casper & friends | Little Lulu: The Dog Show-Off | 1948 | littlelulu-publicdomain | The Dog Show-Off (1948).mp4
Casper & friends | Screen Song: Little Brown Jug | 1948 | paramounts-screen-songs-the-famous-studios-collection-1948-50 | Screen Songs - Little Brown Jug (1948).mp4
Casper & friends | There's Good Boos To-Night | 1948 | noveltoon_casper_tfg_theres_good_boos_tonight | noveltoon_casper_tfg_theres_good_boos_tonight_512kb.mp4
Casper & friends | A Haunting We Will Go | 1949 | noveltoons-a-haunting-we-will-go-1949-philip-loro-print | Casper the Ghost & Friends 03. A Haunting We Will Go (1949, Famous Studios).mp4
Casper & friends | Little Audrey: The Lost Dream | 1949 | Little_Audrey_The_Lost_Dream_1949 | Little_Audrey_The_Lost_Dream_512kb.mp4
Casper & friends | Noveltoon: Hep Cat Symphony | 1949 | HepCatSymphony | HepCatSymphony_512kb.mp4
Casper & friends | Screen Song: Toys Will Be Toys | 1949 | paramounts-screen-songs-the-famous-studios-collection-1948-50 | Screen Songs - Toys Will Be Toys (1949).mp4
Casper & friends | Little Audrey: Goofy Goofy Gander | 1950 | little_audry_goofy_goofy_gander | little_audry_goofy_goofy_gander_512kb.mp4
Casper & friends | Little Audrey: Tarts and Flowers | 1950 | noveltoon_tarts_and_flowers | noveltoon_tarts_and_flowers_512kb.mp4
Mighty Mouse & Terrytoons | Caviar | 1930 | All-30s-Terrytoon-Cartoons | 30.02.23 Caviar.mp4
Mighty Mouse & Terrytoons | Golf Nuts | 1930 | All-30s-Terrytoon-Cartoons | 30.12.14 Golf Nuts.mp4
Mighty Mouse & Terrytoons | Pretzels | 1930 | All-30s-Terrytoon-Cartoons | 30.03.09 Pretzels.mp4
Mighty Mouse & Terrytoons | Billy Mouse's Akwakade | 1940 | 1940publicdomainanimation | 1940.08.09 - Billy Mouse's Akwakade.mp4
Mighty Mouse & Terrytoons | Mighty Mouse: Wolf! Wolf! | 1944 | mighty_mouse_wolf_wolf | mighty_mouse_wolf_wolf_512kb.mp4
Mighty Mouse & Terrytoons | Heckle and Jeckle: The Talking Magpies | 1946 | the-talking-magpies-1946 | The Talking Magpies (1946).mp4
Woody Woodpecker & Lantz | Oswald: Permanent Wave | 1929 | oswald-collection | 54 - Permanent Wave (Lantz, 1929).mp4
Woody Woodpecker & Lantz | Oswald: Snow Use | 1929 | oswald-collection | 57 - Snow Use (Lantz, 1929).mp4
Woody Woodpecker & Lantz | Oswald: Henpecked | 1930 | oswald-collection | 78 - Henpecked (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Oswald: My Pal Paul | 1930 | oswald-collection | 74 - My Pal Paul (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Oswald: Spooks | 1930 | oswald-collection | 76 - Spooks (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Boy Meets Dog! | 1938 | Boy_Meets_Dog_1938 | Boy_Meets_Dog_1938_512kb.mp4
Woody Woodpecker & Lantz | Woody Woodpecker: Pantry Panic | 1941 | woody_woodpecker_pantry_panic | woody_woodpecker_pantry_panic_512kb.mp4
Woody Woodpecker & Lantz | Andy Panda: Canine Commandos | 1943 | CanineCommandos | CanineCommandos.mp4
Color Classics | Poor Cinderella | 1934 | Betty_Boop_Poor_Cinderella_1934 | Betty_Boop_Poor_Cinderella_1934_512kb.mp4
Color Classics | The Little Dutch Mill | 1934 | 1934ParamountFleischerStudiosColorClassicsCartoonLittleDutchMillwalterLantzMaxFleischer | 1934-paramount-fleischerStudios-colorClassicsCartoon-LittleDutchMillwalterLantzMaxFleischer.mp4
Color Classics | The Song of the Birds | 1935 | TheSongOfTheBirds-1935 | CC-The_Song_Of_The_Birds-512K_512kb.mp4
Color Classics | Somewhere in Dreamland | 1936 | 1936_20240806 | Somewhere in Dreamland (1936) Color Classic.mp4
Color Classics | The Little Stranger | 1936 | TheLittleStranger1936 | Color_Classics-The_Little_Stranger-256K_512kb.mp4
Color Classics | A Car-Tune Portrait | 1937 | ACarTunePortrait-1937 | CC-A_Car-Tune_Portrait-512K_512kb.mp4
Color Classics | Educated Fish | 1937 | EducatedFish-1937 | CC-Educated_Fish-512K_512kb.mp4
Color Classics | Hunky and Spunky | 1938 | hunky-and-spunky | Hunky and Spunky (1938).mp4
Color Classics | The Playful Polar Bears | 1938 | ThePlayfulPolarBears-1938 | CC-The_Playful_Polar_Bears-512K_512kb.mp4
Color Classics | Small Fry | 1939 | SmallFry-1939 | CC-Small_Fry-512K_512kb.mp4
Color Classics | The Barnyard Brat | 1939 | hunky-and-spunky | The Barnyard Brat (1939).mp4
Color Classics | A Kick in Time | 1940 | hunky-and-spunky | A Kick in Time (1940).mp4
Color Classics | Little Lambkins | 1940 | LittleLambkins-1940 | CC-Little_Lambkins-512K_512kb.mp4
Color Classics | Snubbed by a Snob | 1940 | hunky-and-spunky | Snubbed by a Snob (1940).mp4
Felix & silents | Krazy Kat Goes A-Wooing | 1916 | Krazy_kat_goesA-wooing_1916 | Krazy_Kat_goes_a-wooing_1916_512kb.mp4
Felix & silents | Krazy Kat: Bugologist | 1916 | Krazy_Kat_Bugolist_1916 | Krazy_Kat_bugolist_1916_512kb.mp4
Felix & silents | Out of the Inkwell: Invisible Ink | 1921 | InvisibleInkDaveFleischer1921 | Invisible Ink (Dave Fleischer, 1921) .mp4
Felix & silents | Out of the Inkwell: Bubbles | 1922 | KokoInBubbles | OutOfTheInkwell-KokoBubblesmaxFleischer1922.mp4
Felix & silents | Alice Comedies: Alice Loses Out | 1925 | silent-alice-loses-out | Alice Loses Out.mp4
Felix & silents | Felix the Cat: Felix All Puzzled | 1925 | FelixAllPuzzled1925 | Felix All Puzzled [1925].mp4
Felix & silents | Felix the Cat: Germ Mania | 1927 | FelixGermMania1927 | Felix Germ Mania [1927].mp4
Felix & silents | Felix the Cat: The Non-Stop Fright | 1927 | FelixTheCat-TheNonStopFright1927 | FelixTheCatInNonStopFright1927_512kb.mp4
Felix & silents | Oswald the Lucky Rabbit: Trolley Troubles | 1927 | WaltDisney1927OSWALDTHELUCKYRABBITTROLLEYTROUBLESXvid | Walt Disney 1927 - OSWALD THE LUCKY RABBIT - TROLLEY TROUBLES_xvid.mp4
Felix & silents | Felix the Cat: Comicalamities | 1928 | FelixComicalamities1928 | Felix Comicalamities [1928].mp4
Felix & silents | Inkwell Imps: KoKo's Earth Control | 1928 | out-of-the-inkwell-cartoon-collection | Inkwell Imps _ KoKo's Earth Control _ 1928 (480p_30fps_H264-128kbit_AAC).mp4
Felix & silents | Mickey Mouse: Plane Crazy (silent version) | 1928 | disneycartoons-publicdomain | Plane Crazy (1928, silent version).mp4
Felix & silents | Mickey Mouse: Steamboat Willie | 1928 | steamboat-willie-mickey | 01 - Steamboat Willie.mp4
Felix & silents | Mickey Mouse: The Gallopin' Gaucho | 1928 | disneycartoons-publicdomain | The Gallopin' Gaucho (1928).mp4
Felix & silents | Oswald the Lucky Rabbit: Oh What a Knight | 1928 | WaltDisney1927OSWALDTHELUCKYRABBITTROLLEYTROUBLESXvid | Oswald the Lucky Rabbit ~ Oh What a Knight.mp4
Felix & silents | Felix the Cat: Felix Woos Whoopee | 1930 | FelixWoosWhoopee1930 | Felix Woos Whoopee [1930].mp4
Felix & silents | Felix the Cat: Bold King Cole | 1936 | all-van-beuren-cartoons-1921-1936 | Felix_BoldKingCole_512kb.mp4
Felix & silents | Felix the Cat: The Goose That Laid the Golden Egg | 1936 | felix_the_cat_the_goos_that_laid_the_golden_egg | felix_the_cat_the_goos_that_laid_the_golden_egg_512kb.mp4
Flip the Frog & Iwerks | Flip the Frog: Fiddlesticks | 1930 | FLIP_FROG-FIDDLESTICKS | FLIP_FROG-FIDDLESTICKS_DVD_512kb.mp4
Flip the Frog & Iwerks | Flip the Frog: Africa Squeaks | 1931 | AfricaSqueaks1931UbIwerksSoundCartoon | AfricaSqueaks1931UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | Flip the Frog: Jail Birds | 1931 | JailBirds1931UbIwerksSoundCartoon | JailBirds1931UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | Flip the Frog: Laughing Gas | 1931 | flip-the-frog-ub-iwerks-1930-33 | Laughing Gas (1931) Flip the Frog.mp4
Flip the Frog & Iwerks | Flip the Frog: Spooks | 1931 | flip-the-frog-ub-iwerks-1930-33 | Spooks (1931) Flip the Frog.mp4
Flip the Frog & Iwerks | Flip the Frog: The Office Boy | 1932 | TheOfficeBoy1932UbIwerksSoundCartoon | TheOfficeBoy1932UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | ComiColor: Jack and the Beanstalk | 1933 | JackAndTheBeanstalk1933 | Jack and the Beanstalk (1933).mp4
Flip the Frog & Iwerks | Flip the Frog: Soda Squirt | 1933 | FlipTheFrog-SodaSquirt1933 | FlipTheFrog-SodaSquirt_512kb.mp4
Flip the Frog & Iwerks | Willie Whopper: Stratos Fear | 1933 | StratosFear | StratosFearUbIwerks_512kb.mp4
Flip the Frog & Iwerks | Willie Whopper: The Air Race | 1933 | YheAirRace | AirRaceThe1933WillieWhopperiwerks_512kb.mp4
Flip the Frog & Iwerks | ComiColor: The Headless Horseman | 1934 | ub-iwerks-comicolor-classics-the-complete-collection-1933-36 | Comicolor Cartoons - The Headless Horseman - 1934 (HD).mp4
Flip the Frog & Iwerks | ComiColor: The Little Red Hen | 1934 | ub-iwerks-comicolor-classics-the-complete-collection-1933-36 | Comicolor Cartoons - The Little Red Hen - 1934 (Remastered)  (The first ComiColor cartoon).mp4
Van Beuren | Aesop's Fables: Watered Stock | 1926 | all-van-beuren-cartoons-1921-1936 | Van Beuren Studios Cartoons - 1926x01 - Aesop's Fables Watered Stock.mp4
Van Beuren | Aesop's Fables: A Toytown Tale | 1931 | aesopsFablesAToytownTaleByVanBeurenStudios | VanBeuren_AesopsFable_AToytownTale_512kb.mp4
Van Beuren | Tom and Jerry: Polar Pals | 1931 | all-van-beuren-cartoons-1921-1936 | Van Beuren's Tom & Jerry 02 - Polar Pals.mp4
Van Beuren | Tom and Jerry: Wot a Night | 1931 | TomAndJerryWotANight | WotANight_512kb.mp4
Van Beuren | Tom and Jerry: A Spanish Twist | 1932 | TomAndJerryInASpanishTwist | RareLostCartoonsAndKidsShows-VanBeuren-TomJerry-ASpanishTwistdvdRip1932.mp4
Van Beuren | Tom and Jerry: Pencil Mania | 1932 | PencilMania_482 | VanBeuren-1932-TomJerry-PencilManiadvdRip.mp4
Van Beuren | Tom and Jerry: Rocketeers | 1932 | rocketeers | rocketeers_512kb.mp4
Van Beuren | Cubby Bear: Opening Night | 1933 | van-beurens-cubby-bear-the-complete-collection | Cubby Bear E01 - Opening Night (1933).mp4
Van Beuren | Cubby Bear: The Nut Factory | 1933 | van-beurens-cubby-bear-the-complete-collection | Cubby Bear E08 - The Nut Factory (1933).mp4
Van Beuren | Rainbow Parade: Pastry Town Wedding | 1934 | van-beurens-rainbow-parade-the-complete-collection | Pastry Town Wedding (1934) Van Beuren Studios Rainbow Parade Short Cartoon.mp4
Van Beuren | Rainbow Parade: Molly Moo-Cow and the Indians | 1935 | Molly_Moo-Cow_and_the_Indians_1935 | Molly_Moo-Cow_and_the_Indians_1935_512kb.mp4
Van Beuren | Rainbow Parade: The Sunshine Makers | 1935 | all-van-beuren-cartoons-1921-1936 | The_Sunshine_Makers_1935_512kb.mp4
Private Snafu | Coming!! Snafu | 1943 | private-snafu | Private Snafu S01E01 Coming Snafu.mp4
Private Snafu | Fighting Tools | 1943 | PrivateSnafuCartoons | Private_SNAFU_-_Fighting_Tools_1943.mp4
Private Snafu | Gripes | 1943 | PrivateSnafuCartoons | Private_SnafuGripes.mp4
Private Snafu | Rumors | 1943 | PrivateSnafuCartoons | Private_SNAFU-_Rumors.mp4
Private Snafu | Spies | 1943 | private_snafu_spies | private_snafu_spies_512kb.mp4
Private Snafu | The Goldbrick | 1943 | PrivateSnafuCartoons | Private_Snafu_-_The_Goldbrick.mp4
Private Snafu | The Home Front | 1943 | home_front | home_front_512kb.mp4
Private Snafu | The Infantry Blues | 1943 | Pvt.SNAFU.TheInfantryBlues | Pvt.SNAFU.TheInfantryBlues_512kb.mp4
Private Snafu | A Lecture on Camouflage | 1944 | PrivateSnafuCartoons | Private_Snafu_-_A_Lecture_On_Camouflage_1944.mp4
Private Snafu | Booby Traps | 1944 | booby_traps | booby_traps_512kb.mp4
Private Snafu | Censored | 1944 | PrivateSnafuCartoons | PrivateSnafu-Censored1944WarnerBros.-Youtube.mp4
Private Snafu | Gas | 1944 | PrivateSnafuCartoons | Private_SNAFU_-_Gas_1944.mp4
Private Snafu | Going Home | 1944 | PrivateSnafuCartoons | Private_Snafu_Going_Home.mp4
Private Snafu | Outpost | 1944 | PrivateSnafuCartoons | Private_Snafu_-_Outpost.mp4
Private Snafu | Payday | 1944 | PrivateSnafuCartoons | Private_Snafu_-_Payday.mp4
Private Snafu | Private Snafu vs. Malaria Mike | 1944 | private-snafu | Private Snafu S02E03 Private Snafu vs Malaria Mike_x264.mp4
Private Snafu | Snafuperman | 1944 | PrivateSnafuSnafuperman | Private_Snafu_as_Snafuperman_512kb.mp4
Private Snafu | Target: Snafu | 1944 | private-snafu | Private Snafu S02E11 Target Snafu.mp4
Private Snafu | The Chow Hound | 1944 | PrivateSnafuCartoons | Private_Snafu_-_The_Chow_Hound.mp4
Private Snafu | Three Brothers | 1944 | private-snafu | Private Snafu S01E13 The Three Brothers.mp4
Private Snafu | Hot Spot | 1945 | private-snafu | Private Snafu S03E04 Hot Spot.mp4
Private Snafu | In the Aleutians – Isles of Enchantment | 1945 | private-snafu | Private Snafu S03E01 In The Aleutians.mp4
Private Snafu | It's Murder She Says | 1945 | private-snafu | Private Snafu S03E03 Its Murder She Says.mp4
Private Snafu | No Buddy Atoll | 1945 | private-snafu | Private Snafu S03E06 No Buddy Atoll_x264.mp4
Private Snafu | Operation Snafu | 1945 | private-snafu | Private Snafu S03E05 Operation Snafu.mp4
Private Snafu | Seaman Tarfu in the Navy | 1946 | private-snafu | Private Snafu S04E01 Seaman Tarfu in the Navy.mp4
Specials & holidays | Jack Frost | 1934 | JackFrost_ | JackFrost_512kb.mp4
Specials & holidays | The Lion Tamer (Amos 'n' Andy) | 1934 | TheLionTamer_645 | TheLionTamer-AmosAndAndy_512kb.mp4
Specials & holidays | Christmas Comes But Once a Year | 1936 | ChristmasComesButOnceAYear-1936 | CC-Christmas_Comes_But_Once_A_Year-512K.mp4
Specials & holidays | Gulliver's Travels | 1939 | Gullivers_Travels-1939 | GulliversTravels-1939_512kb.mp4
Specials & holidays | Raggedy Ann and Raggedy Andy | 1941 | RaggedyAnnAndAndy | cartoonFleischer-RaggedyAnnRaggedyAndy1940.mp4
Specials & holidays | Santa's Surprise | 1947 | SantasSuprise | SantasSuprise_512kb.mp4
Specials & holidays | Hector's Hectic Life | 1948 | hectors_hectic_life | hectors_hectic_life_512kb.mp4
Specials & holidays | Rudolph the Red-Nosed Reindeer | 1948 | RudolphTheRed-nosedReindeer1948 | RudolphTheRed-nosedReindeer1948_512kb.mp4
"""
TOON_BADGES = {"Popeye": "POPE", "Looney Tunes": "LOON", "Superman": "SUPE", "Betty Boop": "BOOP",
               "Casper & friends": "CASP", "Mighty Mouse & Terrytoons": "TERR",
               "Woody Woodpecker & Lantz": "WOOD", "Color Classics": "COLR", "Felix & silents": "FELX",
               "Flip the Frog & Iwerks": "FLIP", "Van Beuren": "VANB", "Private Snafu": "SNFU",
               "Specials & holidays": "SPEC"}


# Old films from the Internet Archive, the same way as the cartoons above.
#   folder | title | year | archive.org item | the file in it
FREE_FILMS = """
Comedy & drama | The Front Page | 1931 | TheFrontPage1931AdolpheMenjouPatOBrienLewismiles | TheFrontPage1931AdolpheMenjouPatOBrienLewismiles_512kb.mp4
Comedy & drama | A Farewell to Arms | 1932 | farewell_to_arms | farewell_to_arms_512kb.mp4
Comedy & drama | Rain | 1932 | rain1932 | Rain_512kb.mp4
Comedy & drama | Of Human Bondage | 1934 | humanbondage | HUMANBONDAGE_512kb.mp4
Comedy & drama | My Man Godfrey | 1936 | MyManGodfrey1936 | MyManGodfrey1936_512kb.mp4
Comedy & drama | A Star Is Born | 1937 | AStarIsBorn | AStarIsBorn_512kb.mp4
Comedy & drama | Nothing Sacred | 1937 | NothingSacred | NothingSacred.mp4
Comedy & drama | Algiers | 1938 | Algiers_ | Algiers_512kb.mp4
Comedy & drama | Love Affair | 1939 | LoveAffair | LoveAffair_512kb.mp4
Comedy & drama | Made for Each Other | 1939 | made_for_each_other_film | made_for_each_other_512kb.mp4
Comedy & drama | The Little Princess | 1939 | little_princess | little_princess_512kb.mp4
Comedy & drama | His Girl Friday | 1940 | his_girl_friday | his_girl_friday_512kb.mp4
Comedy & drama | Our Town | 1940 | Our_Town | OurTown_512kb.mp4
Comedy & drama | Second Chorus | 1940 | second_chorus | second_chorus_512kb.mp4
Comedy & drama | Meet John Doe | 1941 | meet_john_doe | meet_john_doe_512kb.mp4
Comedy & drama | Penny Serenade | 1941 | penny_serenade | penny_serenade_512kb.mp4
Comedy & drama | Topper Returns | 1941 | Topper_Returns_41 | Topper_Returns_41_512kb.mp4
Comedy & drama | The Southerner | 1945 | TheSoutherner | TheSoutherner_512kb.mp4
Comedy & drama | Till the Clouds Roll By | 1946 | till_the_clouds_roll_by | till_the_clouds_roll_by_512kb.mp4
Comedy & drama | Life with Father | 1947 | LifeWithFather | LifeWithFather_512kb.mp4
Comedy & drama | Africa Screams | 1949 | AfricaScreams | Africa_Screams_512kb.mp4
Comedy & drama | The Inspector General | 1949 | the_inspector_general | the_inspector_general_512kb.mp4
Comedy & drama | Father's Little Dividend | 1951 | fatherslittledividend | FathersLittleDividend_512kb.mp4
Comedy & drama | Royal Wedding | 1951 | royal_wedding | royal_wedding_512kb.mp4
Comedy & drama | Jack and the Beanstalk | 1952 | cco_jackandthebeanstalk | ccoPublicDomainJack_and_the_Beanstalk_512kb.mp4
Comedy & drama | Road to Bali | 1952 | TheRoadToBali | ClassicCinemaOnline-road_to_bali_256kb.mp4
Comedy & drama | The Last Time I Saw Paris | 1954 | last_time_i_saw_paris | last_time_i_saw_paris_512kb.mp4
Comedy & drama | The Man with the Golden Arm | 1955 | the-man-with-the-golden-arm-1955_202405 | The Man With The Golden Arm 1955.mp4
Comedy & drama | Charade | 1963 | ecatma-Old_Time_Movie_Show_-_Charade_1963 | Old_Time_Movie_Show_-_Charade_1963.mp4
Film noir & crime | Sherlock Holmes and the Secret Weapon | 1942 | secret_weapon | sherlock_holmes_and_the_secret_weapon_512kb.mp4
Film noir & crime | Bluebeard | 1944 | Bluebeard | Bluebeard_512kb.mp4
Film noir & crime | Detour | 1945 | Detour | Detour_512kb.mp4
Film noir & crime | Scarlet Street | 1945 | ScarletStreet | Scarlet_Street_512kb.mp4
Film noir & crime | Strange Illusion | 1945 | Strange_Illusion | Strange_Illusion_512kb.mp4
Film noir & crime | The Great Flamarion | 1945 | Great_Flamarion_1945 | Great_Flamarion_512kb.mp4
Film noir & crime | The Woman in Green | 1945 | TWIG1945 | The_Woman_in_Green_512kb.mp4
Film noir & crime | Dressed to Kill | 1946 | dressed_to_kill | dressed_to_kill_512kb.mp4
Film noir & crime | Shock | 1946 | shock | Shock_512kb.mp4
Film noir & crime | Terror by Night | 1946 | Terror_By_Night | Terror_By_Night_512kb.mp4
Film noir & crime | The Chase | 1946 | thechase1946_202002 | The Chase (1946, USA) Featuring Peter Lorre, Robert Cummings - Film Noir Full Movie.mp4
Film noir & crime | The Stranger | 1946 | TheStranger_0 | The_Stranger_512kb.mp4
Film noir & crime | Fear in the Night | 1947 | Fear_in_the_Night | Fear_in_the_Night_512kb.mp4
Film noir & crime | Railroaded! | 1947 | railroaded1947_202003 | Railroaded! (1947, USA) Directed by Anthony Mann Featuring John Ireland - Film Noir Full Movie.mp4
Film noir & crime | The Red House | 1947 | TheRedHouse | The_Red_House_512kb.mp4
Film noir & crime | Blonde Ice | 1948 | BlondeIce1948 | BlondeIce1948_512kb.mp4
Film noir & crime | D.O.A. | 1949 | D.o.a.VideoQualityUpgrade | D.o.a.VideoQualityUpgrade.mp4
Film noir & crime | Impact | 1949 | impact | impact_512kb.mp4
Film noir & crime | Port of New York | 1949 | Port_of_New_York | Port_of_New_York_512kb.mp4
Film noir & crime | Too Late for Tears | 1949 | 7.3-too-late-for-tears-1949 | 7.3 Too Late for Tears (1949).ia.mp4
Film noir & crime | Trapped | 1949 | Trapped_ | Trapped_512kb.mp4
Film noir & crime | Quicksand | 1950 | Quicksand_clear | Quicksand.mp4
Film noir & crime | The Man Who Cheated Himself | 1950 | TheManWhoCheatedHimself1950 | TheManWhoCheatedHimself1950.mp4
Film noir & crime | The Second Woman | 1950 | The_Second_Woman_ | The_Second_Woman__512kb.mp4
Film noir & crime | Woman on the Run | 1950 | Woman_on_the_Run | Woman_on_the_Run_512kb.mp4
Film noir & crime | Kansas City Confidential | 1952 | KansasCityConfidential720p | KansasCityConfidential1952-720p_512kb.mp4
Film noir & crime | The Bigamist | 1953 | the_bigamist | the_bigamist_512kb.mp4
Film noir & crime | The Hitch-Hiker | 1953 | Hitch_Hiker | Hitch-Hiker_512kb.mp4
Film noir & crime | Suddenly | 1954 | suddenly | suddenly_512kb.mp4
Film noir & crime | The Big Combo | 1955 | TheBigComboCornellWilde1955BOO | TheBigComboCornellWilde1955BOO_512kb.mp4
Horror & sci-fi | White Zombie | 1932 | white_zombie | white_zombie_512kb.mp4
Horror & sci-fi | The Devil Bat | 1940 | Devil_Bat_movie | Devil_Bat_512kb.mp4
Horror & sci-fi | Dead Men Walk | 1943 | DeadMenWalk | DeadMenWalk.mp4
Horror & sci-fi | The Ape Man | 1943 | TheApeMan | TheApeMan_512kb.mp4
Horror & sci-fi | Voodoo Man | 1944 | VoodooManVideoAudioUpgrade | VoodooManVideoAudioUpgrade.mp4
Horror & sci-fi | Scared to Death | 1947 | SCAREDTODEATHVideoQualityUpgrade | SCARED TO DEATH video quality upgrade.mp4
Horror & sci-fi | Phantom from Space | 1953 | PHANTOMFROMSPACEVideoQualityUpgrade | PHANTOM FROM SPACE video quality upgrade.mp4
Horror & sci-fi | Robot Monster | 1953 | robot-monster-1953 | Robot Monster (1953).mp4
Horror & sci-fi | Killers from Space | 1954 | Killers_from_space | Killers_from_space_512kb.mp4
Horror & sci-fi | Indestructible Man | 1956 | indestructible_man | indestructible_man_512kb.mp4
Horror & sci-fi | Plan 9 from Outer Space | 1957 | plan-9-from-outer-space | plan-9-from-outer-space.mp4
Horror & sci-fi | The Screaming Skull | 1958 | TheScreamingSkullHD1958 | TheScreamingSkullHD1958.mp4
Horror & sci-fi | A Bucket of Blood | 1959 | ABucketofBlood | Bucket_1959_512kb.mp4
Horror & sci-fi | Attack of the Giant Leeches | 1959 | AttackOfTheGiantLeeches | AttackOfTheGiantLeeches_512kb.mp4
Horror & sci-fi | Beast from Haunted Cave | 1959 | BeastFromHauntedCave1959 | BeastFromHauntedCave1959_512kb.mp4
Horror & sci-fi | House on Haunted Hill | 1959 | House_On_Haunted_Hill.avi | The_House_on_Haunted_Hill_512kb.mp4
Horror & sci-fi | Teenagers from Outer Space | 1959 | TeenagersFromOuterSpace | TeenagersFromOuterSpace_512kb.mp4
Horror & sci-fi | The Bat | 1959 | The_Bat.mpeg | The_Bat_512kb.mp4
Horror & sci-fi | The Giant Gila Monster | 1959 | TheGiantGilaMonsterWidescreenQualityUpgrade | THE GIANT GILA MONSTER.mp4
Horror & sci-fi | The Killer Shrews | 1959 | TheKillerShrews | The_Killer_Shrews.mp4
Horror & sci-fi | The Wasp Woman | 1959 | The_Wasp_Women | The_Wasp_Women_512kb.mp4
Horror & sci-fi | The Little Shop of Horrors | 1960 | The_Little_Shop_of_Horrors_60 | The_Little_Shop_of_Horrors_60.mp4
Horror & sci-fi | Night Tide | 1961 | NightTide1961 | NightTide1961_512kb.mp4
Horror & sci-fi | Carnival of Souls | 1962 | CarnivalofSouls | CarnivalOfSouls_512kb.mp4
Horror & sci-fi | The Brain That Wouldn't Die | 1962 | brain_that_wouldnt_die | brain_that_wouldnt_die_512kb.mp4
Horror & sci-fi | Dementia 13 | 1963 | dementia-13-1963_202312 | Dementia 13 (1963).mp4
Horror & sci-fi | The Terror | 1963 | TheTerrorwidescreen | RogerCormansTheTerror1963FullMovie-WidescreenVersion_512kb.mp4
Horror & sci-fi | The Last Man on Earth | 1964 | lastmanonearth-1964 | lastmanonearth-1964.mp4
Horror & sci-fi | Night of the Living Dead | 1968 | NightOfTheLivingDead-MPEG | NightOfTheLivingDead_512kb.mp4
Westerns & adventure | The Mark of Zorro | 1920 | the-mark-of-zorro-1920 | The Mark Of Zorro (1920).mp4
Westerns & adventure | Robin Hood | 1922 | FairbanksRobinHood1922 | FairbanksRobinHood1922/FairbanksRobinHood1922_512kb.mp4
Westerns & adventure | The Thief of Bagdad | 1924 | TheThiefOfBagdad1924 | TOB1924-512.mp4
Westerns & adventure | The Black Pirate | 1926 | the-black-pirate-1926 | The Black Pirate 1926.ia.mp4
Westerns & adventure | Riders of Destiny | 1933 | RidersofDestiny_ | RidersofDestiny_512kb.mp4
Westerns & adventure | Sagebrush Trail | 1933 | SagebrushTrail | SagebrushTrail_512kb.mp4
Westerns & adventure | 'Neath the Arizona Skies | 1934 | NeaththeArizonaSkys | NeaththeArizonaSkys_512kb.mp4
Westerns & adventure | Blue Steel | 1934 | BlueSteel | BlueSteel_512kb.mp4
Westerns & adventure | Randy Rides Alone | 1934 | RandyRidesAlone | RandyRideAlone_512kb.mp4
Westerns & adventure | The Lawless Frontier | 1934 | TheLawlessFontier | TheLawlessFontier_512kb.mp4
Westerns & adventure | The Lucky Texan | 1934 | TheLuckyTexan | TheLuckyTexan_512kb.mp4
Westerns & adventure | The Man from Utah | 1934 | TheManFromUtah | TheManFromUtah_512kb.mp4
Westerns & adventure | The Star Packer | 1934 | The_Star_Packer | The_Star_Packer_512kb.mp4
Westerns & adventure | The Trail Beyond | 1934 | TheTrailBeyond | TheTrailBeyond_512kb.mp4
Westerns & adventure | West of the Divide | 1934 | west_of_the_divide | west_of_the_divide_512kb.mp4
Westerns & adventure | Paradise Canyon | 1935 | ParadiseCanyon | ParadiseCanyon_512kb.mp4
Westerns & adventure | Rainbow Valley | 1935 | RainbowValley | RainbowValley_512kb.mp4
Westerns & adventure | Texas Terror | 1935 | texas_terror_1935 | texas_terror_1935_512kb.mp4
Westerns & adventure | The Dawn Rider | 1935 | TheDawnRider | TheDawnRider_512kb.mp4
Westerns & adventure | The Desert Trail | 1935 | TheDesertTrail | TheDesertTrail_512kb.mp4
Westerns & adventure | The New Adventures of Tarzan | 1935 | new_adventures_of_tarzan | new_adventures_of_tarzan_512kb.mp4
Westerns & adventure | Tarzan and the Green Goddess | 1938 | tarzan_and_the_green_goddess | tarzan_and_the_green_goddess_512kb.mp4
Westerns & adventure | Santa Fe Trail | 1940 | SantaFeTrail1940 | SantaFeTrail1940_512kb.mp4
Westerns & adventure | Jungle Book | 1942 | JungleBook | Jungle_Book_512kb.mp4
Westerns & adventure | Captain Kidd | 1945 | CaptainKidd_ | CaptainKidd_512kb.mp4
Westerns & adventure | Abilene Town | 1946 | AbileneTown | AbileneTown_512kb.mp4
Westerns & adventure | Angel and the Badman | 1947 | angel_and_the_badman | angel_and_the_badman_512kb.mp4
Westerns & adventure | Kansas Pacific | 1953 | KansasPacific | KansasPacific_512kb.mp4
Westerns & adventure | McLintock! | 1963 | Mclintock.avi | Mclintock_512kb.mp4
Silent classics | A Trip to the Moon | 1902 | 1902-a-trip-to-the-moon | 1902   A Trip To The Moon.mp4
Silent classics | The Great Train Robbery | 1903 | silent-the-great-train-robbery | The Great Train Robbery.mp4
Silent classics | The Rink | 1916 | silent-the-rink | The Rink.mp4
Silent classics | Easy Street | 1917 | silent-easy-street | Easy Street.mp4
Silent classics | The Adventurer | 1917 | silent-the-adventurer | The Adventurer.mp4
Silent classics | The Cure | 1917 | silent-the-cure | The Cure.mp4
Silent classics | The Immigrant | 1917 | silent-the-immigrant | The Immigrant.mp4
Silent classics | Dr. Jekyll and Mr. Hyde | 1920 | DrJekyllandMrHyde | DrJekyllandMrHyde_512kb.mp4
Silent classics | The Cabinet of Dr. Caligari | 1920 | thecabinetofdrcaligari | KabinettDesDoktorCaligariDas_512kb.mp4
Silent classics | Häxan | 1922 | Haxan1922 | Haxan (1922).mp4
Silent classics | Nosferatu | 1922 | nosferatu-1922-silent-movie | Nosferatu -1922- -Silent Movie-.mp4
Silent classics | Our Hospitality | 1923 | OurHospitality_29 | OurHospitality_512kb.mp4
Silent classics | Safety Last! | 1923 | silent-safety-last | Safety Last!.mp4
Silent classics | The Hunchback of Notre Dame | 1923 | The_Hunchback_of_Notre_Dame | The_Hunchback_of_Notre_Dame_512kb.mp4
Silent classics | Sherlock Jr. | 1924 | silent-sherlock-jr- | Sherlock Jr..mp4
Silent classics | The Navigator | 1924 | the-navigator-1924. | The Navigator 1924. .mp4
Silent classics | Battleship Potemkin | 1925 | BattleshipPotemkin | Battleship_Potemkin_512kb.mp4
Silent classics | Seven Chances | 1925 | silent-seven-chances | Seven Chances.mp4
Silent classics | The Freshman | 1925 | silent-the-freshman | The Freshman.mp4
Silent classics | The Lost World | 1925 | TheLostWorld1925 | TheLostWorld1925_512.mp4
Silent classics | The Phantom of the Opera | 1925 | ThePhantomOfTheOpera_364 | ThePhantomOfTheOperaPresentedByMoviePowder_512kb.mp4
Silent classics | The General | 1926 | TheGeneral | The_General_512kb.mp4
Silent classics | College | 1927 | college | College_512kb.mp4
Silent classics | It | 1927 | it_20240118 | it.mp4
Silent classics | Metropolis | 1927 | metropolis_202109 | Metropolis.ia.mp4
Silent classics | Sunrise: A Song of Two Humans | 1927 | sunrise-1927_202301 | Sunrise.ia.mp4
Silent classics | Wings | 1927 | wings_1927 | Wings (1927).mp4
Silent classics | Steamboat Bill, Jr. | 1928 | steamboat-bill-jr_1928 | steamboat-bill-jr_1928.ia.mp4
Silent classics | The Passion of Joan of Arc | 1928 | MartyreDeJeanneDarc | Jeanne Darc.mp4
"""
FILM_BADGES = {"Comedy & drama": "COMD", "Film noir & crime": "NOIR", "Horror & sci-fi": "HORR",
               "Westerns & adventure": "WEST", "Silent classics": "SILN"}

def archive_shelves(text):
    """folder -> [(title, year, item, file)], in the order they're listed."""
    out = {}
    for line in text.strip().splitlines():
        parts = line.split(" | ")
        if len(parts) == 5 and not line.startswith("#"):
            folder, title, year, ident, name = (x.strip() for x in parts)
            out.setdefault(folder, []).append((title, year, ident, name))
    return out


CLASSIC = archive_shelves(CLASSIC_TOONS)
FILMS = archive_shelves(FREE_FILMS)
SHELVES = {"toons": (CLASSIC, TOON_BADGES, "cartoons"), "movies": (FILMS, FILM_BADGES, "films")}
PLEX_FOLDERS = {"toons": [("Anime", "ANIM", "anime"), ("Cartoon channels", "live", "toons")],
                "movies": [("Movie channels", "live", "movies")]}
IA_URLS = {}       # cartoon or film -> the lightest copy of it, once looked up


def ia_row(folder, title, year, ident, name):
    src = f"ia:{ident}/{name}"
    return dict(item(src, title, "video", src, sub=year), folder=folder)


def is_hls(url):
    """A live stream that lists its versions (an .m3u8), for hls_pick to choose from."""
    try:
        return urllib.parse.urlsplit(url).path.lower().endswith(".m3u8")
    except ValueError:                   # not a link at all (a typo in streams.txt)
        return False


def hls_pick(url, timeout=8):
    """A live stream's version closest to the screen's size (the big ones stutter on the Pi),
    or the stream as it is when it has one version or keeps its sound apart."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final, text = r.geturl(), r.read(200_000).decode("utf-8", "ignore")
    except Exception:
        return url
    if re.search(r"#EXT-X-MEDIA:[^\n]*TYPE=AUDIO[^\n]*URI=", text):
        return url                      # one version alone would have no sound
    variants, info = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            res = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            info = (int(res.group(2)) if res else 0, int(bw.group(1)) if bw else 0)
        elif line and not line.startswith("#") and info:
            variants.append((info, line))
            info = None
    if len(variants) < 2:
        return url
    lines = video_target()[2]
    small = [v for v in variants if 0 < v[0][0] <= lines]
    pick = max(small, key=lambda v: v[0]) if small else min(variants, key=lambda v: v[0])
    try:
        return urllib.parse.urljoin(final, pick[1])
    except ValueError:                   # a version listed with a broken link
        return url


def ia_best(ident, name, timeout=8):
    """Where to stream a cartoon from: the lightest copy of it in its archive.org item (the
    320x240 one plays easily on the Pi and is fine on this screen), or the file listed in
    CLASSIC_TOONS if the Archive doesn't say."""
    base = "https://archive.org/download/" + urllib.parse.quote(ident) + "/"
    known = base + urllib.parse.quote(name)
    if known in IA_URLS:
        return IA_URLS[known]
    try:
        files = fetch_json("https://archive.org/metadata/" + urllib.parse.quote(ident), timeout).get("files") or []
    except Exception:
        return known
    vids = [f for f in files if f.get("name", "").lower().endswith(tuple(VIDEO_EXTS) + (".ogv",))]

    def source(f):                       # the file a copy was made from
        return f.get("original") if f.get("source") == "derivative" and f.get("original") else f.get("name")
    me = next((f for f in vids if f.get("name") == name), None)
    if me is not None:
        key = source(me)
    elif len({source(f) for f in vids}) == 1:     # renamed, but it's the item's only video
        key = source(vids[0])
    else:
        return known
    copies = [f for f in vids if source(f) == key]
    mp4 = [f for f in copies if f["name"].lower().endswith(".mp4")] or copies
    best = min(mp4, key=lambda f: int(f.get("size") or 1 << 40))
    IA_URLS[known] = base + urllib.parse.quote(best["name"])
    return IA_URLS[known]


# ---- media mode: what's in each tab -----------------------------------------
LIBRARY = [
    {"name": "TV", "type": "group", "empty": "",
     "children": ["Plex", "Cartoons", "Free Movies", "News", "Sports", "Streams", "TV Remote"]},
    {"name": "Music", "type": "files", "dirs": ["/home/*/Music"],
     "exts": AUDIO_EXTS, "kind": "audio", "empty": "Copy music into ~/Music"},
    {"name": "Radio", "type": "radio", "files": [settings_glob("radio.txt")],
     "empty": "Add stations to static/radio.txt  as  Name | URL"},
    {"name": "Photos", "type": "photos", "dirs": ["/home/*/Pictures"],
     "empty": "Copy pictures into ~/Pictures"},
    {"name": "Videos", "type": "files", "dirs": ["/home/*/Videos"],
     "exts": VIDEO_EXTS, "kind": "video", "empty": "Copy video files into ~/Videos"},
    {"name": "Weather", "type": "weather", "empty": ""},
    {"name": "Crypto", "type": "crypto", "files": [settings_glob("crypto.txt")], "empty": ""},
    {"name": "Files", "type": "browser", "empty": "This folder is empty"},
    {"name": "Camera", "type": "camera", "files": [settings_glob("camera.txt")], "empty": ""},
    {"name": "Bot", "type": "friend", "files": [settings_glob("bot.txt")], "empty": ""},
    {"name": "System", "type": "system", "empty": ""},
    {"name": "Settings", "type": "settings", "empty": ""},
    # inside the TV tab (no tab of their own along the top)
    {"name": "Plex", "type": "plex", "parent": "TV", "badge": "PLEX",
     "about": "Your movies and shows, Live TV", "empty": "This library is empty"},
    {"name": "Cartoons", "type": "channels", "parent": "TV", "badge": "TOON", "pick": "toons",
     "about": "Classic cartoons, anime", "empty": "No cartoon channels on Plex Live TV right now"},
    {"name": "Free Movies", "type": "channels", "parent": "TV", "badge": "FILM", "pick": "movies",
     "about": "Old films, movie channels", "empty": "No movie channels on Plex Live TV right now"},
    {"name": "News", "type": "channels", "parent": "TV", "badge": "NEWS", "pick": "news",
     "about": "Live news channels", "empty": "No news channels right now"},
    {"name": "Sports", "type": "channels", "parent": "TV", "badge": "SPRT", "pick": "sports",
     "about": "Live sports channels", "empty": "No sports channels right now"},
    {"name": "Streams", "type": "streams", "parent": "TV", "badge": "LIVE",
     "about": "Your stream list", "files": [settings_glob("streams.txt"), settings_glob("streams.m3u")],
     "empty": "Add streams to static/streams.txt  as  Name | URL"},
    {"name": "TV Remote", "type": "remote", "parent": "TV", "badge": "TV",
     "about": "Your TV through Home Assistant", "files": [settings_glob("homeassistant.txt")],
     "empty": ""},
]

MEDIA_VT = 7          # spare console the menu and player draw on
STATE_FILE = "/var/lib/gpi-keys/state.json"   # resume points, lengths, lists
CACHE_DIR = "/var/cache/gpi-keys"             # thumbnails, converted documents
MENU_REPEAT = {"up", "down", "left", "right"}  # hold to keep scrolling
MENU_RATE = 0.11
SLIDESHOW_SECS = 5
TEXT_LIMIT = 2_000_000                         # bytes of a text file to show
HOT_C = 70                                     # status bar warns above this

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

VIDEO_PLAYER = ["mplayer", "-slave", "-quiet", "-vo", "fbdev2", "-sws", "0",
                "-framedrop", "-autosync", "30",
                "-lavdopts", "threads=4:fast:skiploopfilter=all",
                "-softvol", "-ao", "alsa", "-font", FONT]
AUDIO_PLAYER = ["mplayer", "-slave", "-quiet", "-novideo", "-softvol", "-ao", "alsa"]
LOCAL_CACHE = ["-cache", "8192"]
NET_CACHE = ["-cache", "16384", "-cache-min", "10"]
RADIO_CACHE = ["-cache", "512", "-cache-min", "20"]
PLAYER_NICE = -5      # give the player priority over everything else
VOLUME_STEP = 5

# while a video plays: button -> mplayer command
PLAYING = {
    "left":  "seek -10 0",
    "right": "seek 10 0",
    "l":     "seek -60 0",
    "r":     "seek 60 0",
    "x":     "osd_show_progression",
}
SCREEN_SAY = {"Fit": "Whole picture", "Full screen": "Full screen", "Stretch": "Full screen (stretched)"}


def video_scale(mode, size, w=640, h=480):
    """mplayer's scaling for the screen: Fit keeps the whole picture, Fill zooms it to cover the
    screen (cutting the edges, so letterboxed or 16:9 shows fill it), Stretch pulls it to fit."""
    if mode == "Stretch":
        return ["-vf", f"scale={w}:{h}"]
    if mode in ("Full screen", "Fill"):
        if not size and (w, h) != (640, 480):            # any shape: cover the screen, cut the rest
            return ["-vf", f"dsize={w}:{h}:1,scale=0:0,crop={w}:{h}"]
        if not size:                                      # not known yet: keep its shape, cut the sides
            return ["-vf", f"scale=-2:{h},crop={w}:{h}"]
        vw, vh = size
        if vw * h > vh * w:                               # wider than the screen: cut the sides
            sw = int(round(h * vw / vh / 2)) * 2
            return ["-vf", f"scale={sw}:{h},crop={w}:{h}"]
        sh = int(round(w * vh / vw / 2)) * 2              # taller: cut top and bottom
        return ["-vf", f"scale={w}:{sh},crop={w}:{h}"]
    if (w, h) != (640, 480):                             # any screen: the whole picture, as big as fits
        return ["-vf", f"dsize={w}:{h}:0,scale=0:0"]
    return ["-zoom", "-xy", str(w), "-vf", "scale"]


def fit_box(size, w=640, h=480, inset=2):
    """Where a Fit picture lands on the screen (mplayer centres it), a little inside its edges."""
    vw, vh = size
    k = min(w / vw, h / vh)
    pw, ph = vw * k, vh * k
    x0, y0 = (w - pw) / 2, (h - ph) / 2
    return (int(x0) + inset, int(y0) + inset, int(x0 + pw) - inset, int(y0 + ph) - inset)

# Crypto tab: the same sources PiE-ink uses, fetched by this Pi itself
COINGECKO = "https://api.coingecko.com/api/v3"
CRYPTO_COINS = [("bitcoin", "BTC", "Bitcoin"), ("ethereum", "ETH", "Ethereum"),
                ("dogecoin", "DOGE", "Dogecoin")]          # when crypto.txt doesn't list any
CRYPTO_WINDOWS = [(1, "1D"), (7, "7D"), (30, "30D"), (365, "1Y")]
CRYPTO_GAP = 2.5          # seconds between CoinGecko calls (its free tier is ~10 a minute)
CRYPTO_ROTATE = 20        # seconds per card when Auto is on
# PiE-ink's colour-screen palette
PI_BG, PI_FG, PI_DIM, PI_ACCENT = (0, 0, 0), (255, 255, 255), (150, 150, 150), (98, 210, 255)
PI_UP, PI_DOWN = (0, 255, 0), (255, 80, 80)

# Camera tab: cameras on other Pis (PiE-ink, or camera.py from this repo), or any MJPEG/JPEG link
CAM_SPEED = {"slow": 25, "normal": None, "fast": 120}   # None: the camera's own setting
CAM_TICK = 0.15          # stick messages while the d-pad is held (it stops after 0.7 s quiet)
CAM_FPS = 4              # how often the picture refreshes on the Camera tab
CAM_PORTS = (5000, 5433)  # where a Pi's camera answers: PiE-ink's web app, then camera.py
CAM_LINKS = [(8080, "/?action=stream"), (8080, "/stream"), (81, "/stream"), (8081, "/")]  # other servers
CAM_PATHS = ("/stream", "/?action=stream", "/video", "/mjpg/video.mjpg", "/")   # ...at an address:port
CAM_BEACON = 5151        # PiE-inks and camera.py say they're there, a few times a minute
CAM_FOUND_FOR = 30       # a camera gone quiet this long drops off "On your network"
CAM_FOUND_KEEP = 16      # at most this many cameras heard on the network are kept in mind
CAM_JSON_MAX = 256_000   # bytes: what a camera says is short,
CAM_FRAME_MAX = 12_000_000   # its live pictures aren't big (a big one is kept as a smaller copy),
CAM_KEEP_MAX = 1_500_000
CAM_PHOTO_MAX = 32_000_000   # and a picture at its biggest size is well under this
HA_POLL = 3              # seconds between asking Home Assistant how the TV is
HA_HELD = 0.3            # seconds between repeats while an arrow is held on the TV Remote
CAM_HOLD = 0.6           # seconds: holding SELECT this long turns Follow me on/off
CAM_SHOT_SHOW = 4        # seconds the picture you just took stays in the corner

# Plex: the server converts video to a size the Pi Zero plays smoothly
PLEX_FILE = "/var/lib/gpi-keys/plex.json"      # sign-in token (readable by root only)
PLEX_PRODUCT = "GPi Case Player"
PLEX_RESOLUTION = "640x480"
PLEX_BITRATE = 1500                            # kbps
PLEX_CACHE = ["-cache", "4096", "-cache-min", "5"]
PLEX_TIMELINE_SECS = 10                        # how often progress goes back to Plex
PLEX_EPG = "https://epg.provider.plex.tv"      # Plex's free live TV channels
PLEX_LIVE_HEIGHT = 480                         # pick the channel's stream closest to this

# colours: calm dark theme for a small screen
BG     = (16, 19, 23)
ROW    = (31, 37, 46)
TEXT   = (236, 239, 243)
BODY   = (176, 184, 196)
MUTED  = (104, 112, 125)
LINE   = (40, 46, 55)
ACCENT = (96, 170, 228)
DONE   = (122, 186, 150)
WARN   = (230, 120, 120)
PHOTO_BG = (6, 7, 9)
BADGE = {  # file type label colours in the Files tab
    "dir": ACCENT, "image": DONE, "video": (110, 196, 196), "audio": (170, 146, 222),
    "pdf": (224, 122, 128), "doc": (124, 152, 232), "text": BODY, "other": MUTED,
}

NAME = "gpi-keys"
NEVER = float("inf")
UA = {"User-Agent": "gpi-keys/1.0 (Raspberry Pi media player)"}
LISTEN_KINDS = ("audio", "radio")          # keep playing in the terminal
SCREEN_KINDS = ("video", "live", "plex")  # the player owns the screen


# ---- helpers -----------------------------------------------------------------
def find_files(patterns, exts):
    files = []
    for pattern in patterns:
        for d in glob.glob(pattern):
            for root, dirs, names in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                files += [os.path.join(root, n) for n in names
                          if not n.startswith(".")
                          and os.path.splitext(n)[1].lower() in exts]
    return sorted(files, key=lambda p: os.path.basename(p).lower())


def system_stopping():
    """True while the Pi is shutting down or restarting."""
    try:
        out = subprocess.run(["systemctl", "is-system-running"], capture_output=True, text=True,
                             timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out == "stopping"


def home_dir():
    homes = sorted(h for h in glob.glob("/home/*") if os.path.isdir(h))
    return homes[0] if homes else "/root"


def short_path(path):
    h = home_dir()
    return "~" + path[len(h):] if path == h or path.startswith(h + "/") else path


def title_of(path):
    t = os.path.splitext(os.path.basename(path))[0]
    t = re.sub(r"[._]+", " ", t)
    return re.sub(r"\s+", " ", t).strip() or os.path.basename(path)


def item(key, title, kind, src, sub=""):
    return {"key": key, "title": title, "kind": kind, "src": src, "sub": sub}


def classify(path):
    if os.path.isdir(path):
        return "dir"
    ext = os.path.splitext(path)[1].lower()
    for kind, exts in (("video", VIDEO_EXTS), ("audio", AUDIO_EXTS), ("image", IMAGE_EXTS),
                       ("doc", DOC_EXTS), ("text", TEXT_EXTS)):
        if ext in exts:
            return kind
    return "pdf" if ext == ".pdf" else "other"


def looks_like_text(path):
    try:
        with open(path, "rb") as f:
            data = f.read(4096)
        if b"\0" in data:
            return False
        data.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def read_lines(patterns):
    for pattern in patterns:
        for fn in sorted(glob.glob(pattern)):
            try:
                yield from open(fn, errors="ignore").read().splitlines()
            except OSError:
                continue


def read_streams(patterns, kind="live"):
    """'Name | URL' lines, bare URLs, or an M3U playlist with #EXTINF names."""
    out, name = [], None
    for line in read_lines(patterns):
        line = line.strip()
        if line.startswith("#EXTINF"):
            name = line.split(",", 1)[1].strip() if "," in line else None
            continue
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            n, url = (x.strip() for x in line.split("|", 1))
        else:
            n, url = name, line
        if "://" in url:
            out.append(item("url:" + url, n or url, kind, url))
        name = None
    return out


def read_config(patterns):
    """'key = value' lines; lines starting with # are notes."""
    cfg = {}
    for line in read_lines(patterns):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip().lower()] = v.strip()
    return cfg


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def resolve(it):
    """Turn an item into something mplayer can open."""
    if it["src"].startswith("ia:"):
        ident, name = it["src"][3:].split("/", 1)
        return ia_best(ident, name)
    return it["src"]


def clock(sec):
    sec = int(max(sec, 0))
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def probe_length(path):
    try:
        r = subprocess.run(
            ["nice", "-n", "15", "mplayer", "-identify", "-frames", "0",
             "-vo", "null", "-ao", "null", path],
            capture_output=True, text=True, timeout=30)
        m = re.search(r"^ID_LENGTH=([\d.]+)", r.stdout, re.M)
        return float(m.group(1)) if m else 0.0
    except (OSError, subprocess.TimeoutExpired):
        return 0.0


def cache_name(path, ext):
    try:
        st = os.stat(path)
        key = f"{path}:{st.st_mtime}:{st.st_size}"
    except OSError:
        key = path
    return hashlib.md5(key.encode()).hexdigest() + ext


# ---- system readings ------------------------------------------------------------
def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def run_out(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def cpu_temp():
    t = read_file("/sys/class/thermal/thermal_zone0/temp")
    return int(t) / 1000 if t.isdigit() else None


def wifi_quality():
    """0-70 link quality from /proc/net/wireless, or None when not connected."""
    for line in read_file("/proc/net/wireless").splitlines()[2:]:
        parts = line.split()
        if parts and parts[0].startswith("wl"):
            try:
                return float(parts[2].rstrip("."))
            except (IndexError, ValueError):
                return None
    return None


def wifi_bars(q):
    if q is None or q <= 0:
        return 0
    return 4 if q >= 55 else 3 if q >= 40 else 2 if q >= 25 else 1


def throttle_text():
    out = run_out(["vcgencmd", "get_throttled"])
    m = re.search(r"0x([0-9a-fA-F]+)", out)
    if not m:
        return "unknown", False
    v = int(m.group(1), 16)
    now = [t for bit, t in ((0, "low power"), (1, "speed capped"), (2, "throttled"),
                            (3, "temperature limit")) if v & (1 << bit)]
    if now:
        return "Now: " + ", ".join(now), True
    if v & 0xF0000:
        return "OK (low power earlier)", False
    return "OK", False


def system_info():
    rows = []

    def add(label, value, warn=False):
        rows.append(dict(item("sys:" + label, label, "info", "", sub=value), warn=warn))

    t = cpu_temp()
    add("CPU temperature", f"{t:.1f} °C" if t is not None else "unknown",
        t is not None and t >= HOT_C)
    load = os.getloadavg()[0]
    freq = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    add("CPU", f"{min(load * 100 / (os.cpu_count() or 1), 100):.0f}% busy"
        + (f" · {int(freq) // 1000} MHz" if freq.isdigit() else ""))
    text, bad = throttle_text()
    add("Power", text, bad)

    mem = {}
    for line in read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        mem[k] = int(v.split()[0]) * 1024 if v.split() else 0
    if mem.get("MemTotal"):
        used = mem["MemTotal"] - mem.get("MemAvailable", 0)
        add("Memory", f"{human_size(used)} of {human_size(mem['MemTotal'])}")
    du = shutil.disk_usage("/")
    add("Storage", f"{human_size(du.used)} used, {human_size(du.free)} free",
        du.free < 1 << 30)

    link = run_out(["iw", "dev", "wlan0", "link"])
    ssid = re.search(r"SSID: (.+)", link)
    sig = re.search(r"signal: (-?\d+)", link)
    if ssid:
        add("WiFi", ssid.group(1) + (f" · {sig.group(1)} dBm" if sig else ""))
    else:
        q = wifi_quality()
        add("WiFi", "connected" if q else "not connected", not q)
    ips = run_out(["hostname", "-I"]).split()
    add("IP address", ips[0] if ips else "none")
    add("Hostname", socket.gethostname())

    up = read_file("/proc/uptime").split()
    if up:
        s = int(float(up[0]))
        d, h, m = s // 86400, s // 3600 % 24, s // 60 % 60
        add("Up for", (f"{d} d " if d else "") + f"{h} h {m} min")
    model = read_file("/proc/device-tree/model").replace("\x00", "")
    if model:
        add("Board", model)
    osname = re.search(r'PRETTY_NAME="([^"]+)"', read_file("/etc/os-release"))
    add("System", osname.group(1) if osname else "Linux")
    add("Kernel", os.uname().release)

    rows.append(item("act:restart", "Restart media mode", "action", "restart"))
    rows.append(item("act:reboot", "Reboot", "action", "reboot"))
    rows.append(item("act:poweroff", "Shut down", "action", "poweroff"))
    return rows


# ---- documents to text (no extra packages needed) ---------------------------
def _xml(z, name):
    import xml.etree.ElementTree as ET
    return ET.fromstring(z.read(name))


def _numbered(names, pattern):
    found = [n for n in names if re.match(pattern, n)]
    return sorted(found, key=lambda n: int(re.findall(r"\d+", n.rsplit("/", 1)[-1])[0]))


def doc_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".rtf":
        raw = open(path, errors="ignore").read()
        raw = re.sub(r"\\par[d]?\b ?", "\n", raw)
        raw = re.sub(r"\{\\\*[^{}]*\}", "", raw)
        raw = re.sub(r"\\'[0-9a-f]{2}|\\[a-zA-Z]+-?\d* ?|[{}]", "", raw)
        return raw.strip()
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if ext == ".docx":
            W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for p in _xml(z, "word/document.xml").iter(W + "p"):
                parts = []
                for el in p.iter():
                    if el.tag == W + "t":
                        parts.append(el.text or "")
                    elif el.tag == W + "tab":
                        parts.append("    ")
                    elif el.tag in (W + "br", W + "cr"):
                        parts.append("\n")
                out.append("".join(parts))
        elif ext == ".pptx":
            A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            for k, n in enumerate(_numbered(names, r"ppt/slides/slide\d+\.xml$"), 1):
                out += ["", f"── Slide {k} ──", ""]
                for p in _xml(z, n).iter(A + "p"):
                    line = "".join(t.text or "" for t in p.iter(A + "t"))
                    if line.strip():
                        out.append(line)
        elif ext == ".xlsx":
            S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = ["".join(t.text or "" for t in si.iter(S + "t"))
                          for si in _xml(z, "xl/sharedStrings.xml").iter(S + "si")]
            for k, n in enumerate(_numbered(names, r"xl/worksheets/sheet\d+\.xml$"), 1):
                out += ["", f"── Sheet {k} ──", ""]
                for row in _xml(z, n).iter(S + "row"):
                    cells = []
                    for c in row.iter(S + "c"):
                        v = c.find(S + "v")
                        if c.get("t") == "s" and v is not None:
                            cells.append(shared[int(v.text)])
                        elif c.get("t") == "inlineStr":
                            cells.append("".join(t.text or "" for t in c.iter(S + "t")))
                        else:
                            cells.append(v.text if v is not None and v.text else "")
                    out.append("  |  ".join(cells))
        elif ext in (".odt", ".odp", ".ods"):
            T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
            TB = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
            root = _xml(z, "content.xml")
            if ext == ".ods":
                for r in root.iter(TB + "table-row"):
                    cells = ["".join(c.itertext()) for c in r.findall(TB + "table-cell")]
                    while cells and not cells[-1]:
                        cells.pop()
                    out.append("  |  ".join(cells))
            else:
                for el in root.iter():
                    if el.tag in (T + "p", T + "h"):
                        out.append("".join(el.itertext()))
        else:
            raise OSError("needs LibreOffice")
    return "\n".join(out).strip()


# ---- cameras: other Pis (PiE-ink, or camera.py), or any MJPEG/JPEG link ------------------------
CAMERA_HEAD = ("# Cameras for the Camera tab, one per line:   camera = address   (a name after it if you like)\n"
               "# A Pi running PiE-ink or gpi-media's camera server (sudo bash setup.sh --camera),\n"
               "# or any MJPEG or JPEG camera link.\n")


def cam_key(addr):
    """One spelling per address, for comparing: no http://, no slash at the end, lower case."""
    a = (addr or "").strip()
    if a.lower().startswith("http://"):
        a = a[7:]
    return a.rstrip("/").lower()


def cam_host(addr):
    """The machine in an address: 192.168.1.50 for 'http://192.168.1.50:5000/stream'."""
    try:
        return (urllib.parse.urlsplit(addr if "://" in addr else "http://" + addr).hostname or "").lower()
    except ValueError:
        return ""


def cam_address(text):
    """A camera address as typed, tidied: an address or a name (a port after it if you like), or
    an http(s) link. None when it isn't one."""
    t = (text or "").strip()
    if not t or len(t) > 200 or any(c.isspace() for c in t):
        return None
    try:
        u = urllib.parse.urlsplit(t if "://" in t else "http://" + t)
        port = u.port
    except ValueError:
        return None
    host = u.hostname or ""
    if u.scheme not in ("http", "https") or not host or not re.fullmatch(r"[a-z0-9.:\-]+", host):
        return None
    if port is not None and not 0 < port < 65536:
        return None
    return t if "://" in t else t.rstrip("/")


def clean_name(text, limit=40):
    """A name fit for a line of a settings file, and the screen: printable, on one line."""
    text = "".join(c if c.isprintable() else " " for c in str(text or ""))
    return " ".join(text.split())[:limit]


def cam_names_pi(host):
    """Does this name or address mean the Pi itself: localhost, 127.0.0.1, ::1, 0.0.0.0, or the
    Pi's own name (which /etc/hosts points at 127.0.1.1)?"""
    h = (host or "").strip("[]").lower().rstrip(".")
    if h in ("localhost", socket.gethostname().lower()) or h.endswith(".localhost"):
        return True
    try:
        a = ipaddress.ip_address(h.split("%")[0])
    except ValueError:
        return False
    a = getattr(a, "ipv4_mapped", None) or a
    return a.is_loopback or a.is_unspecified


def cam_is_local(addr):
    """An address the web page doesn't add: the Pi itself. Anyone on your WiFi can open the
    page, and the Pi's own services are its own."""
    return cam_names_pi(cam_host(addr))


def cam_check_peer(sock, host):
    """A camera reached by a name must not turn out to be the Pi itself (a name can be made to
    point anywhere); one reached by localhost, 127.0.0.1 or the Pi's own name may be."""
    try:
        a = ipaddress.ip_address(sock.getpeername()[0].split("%")[0])
    except (OSError, ValueError, IndexError, TypeError):
        return
    a = getattr(a, "ipv4_mapped", None) or a
    if (a.is_loopback or a.is_unspecified) and not cam_names_pi(host):
        sock.close()
        raise ConnectionRefusedError(f"{host} is this Pi")


def read_capped(r, limit, until, alive=None):
    """An answer read a piece at a time: at most `limit` bytes, all of it by `until` (on
    time.monotonic()), and dropped as soon as alive() says it isn't wanted any more."""
    out, n = [], 0
    read = r.read1 if hasattr(r, "read1") else r.read
    while True:
        if time.monotonic() > until:
            raise TimeoutError("timed out")
        if alive is not None and not alive():
            raise InterruptedError("not wanted any more")
        chunk = read(65536)
        if not chunk:
            return b"".join(out)
        n += len(chunk)
        if n > limit:
            raise ValueError("too big")
        out.append(chunk)


class CamHTTP(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class CamHTTPS(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class CamHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(CamHTTP, req)


class CamHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(CamHTTPS, req, context=self._context)


class CamRedirect(urllib.request.HTTPRedirectHandler):
    """A camera may send us elsewhere, but not on to the Pi itself (unless it's on the Pi)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if cam_names_pi(cam_host(newurl)) and not cam_names_pi(cam_host(req.full_url)):
            return None                               # (the redirect becomes an error)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# cameras and Ollama are on your network: straight there, never through a proxy
CAM_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), CamHTTPHandler, CamHTTPSHandler,
                                         CamRedirect)
OLLAMA_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def cam_open(url, body=None, timeout=3):
    """A request to a camera (JSON when there's a body)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", **UA} if data is not None else dict(UA)
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET", headers=headers)
    return CAM_OPENER.open(req, timeout=timeout)


def cam_json(url, timeout=3):
    with cam_open(url, timeout=timeout) as r:
        out = read_capped(r, CAM_JSON_MAX, time.monotonic() + timeout * 2)
    return json.loads(out) if out.strip() else {}


# ---- PiE-ink on another Pi: what it has already fetched is asked for first --------------------------
PIE_PORT = 5000                  # PiE-ink's web app
PIE_FRESH = 30                   # seconds an answer from it is used before it's asked again
PIE_TIMEOUT = 3                  # it's on your network: it answers quickly, or not at all
PIE_MAX = 3_000_000              # bytes: what it has is small
PIE_RETRY = 120                  # seconds before a PiE-ink that didn't answer is asked again,
PIE_NOT = 3600                   # ...and before an address that isn't a PiE-ink is
PIE_NEAR = 25                    # km: its weather is yours when it's for somewhere this close
PIE_NWS_AGE = 3 * 3600           # its worded forecast is used while it's younger than this


def _fnum(v, lo=None, hi=None):
    """A number from another machine: an int or a float (not too big to be one), between lo and hi
    when they're given; None otherwise."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        v = float(v)
    except OverflowError:
        return None
    if v != v or abs(v) == float("inf") or (lo is not None and v < lo) or (hi is not None and v > hi):
        return None
    return v


def _age(v):
    """How old, from another machine: seconds, never less than none."""
    v = _fnum(v, hi=1e10)
    return None if v is None else max(0.0, v)


def km_apart(a, b):
    """Kilometres between two (lat, lon) points."""
    import math
    (la1, lo1), (la2, lo2) = a, b
    k = math.pi / 180
    h = (math.sin((la2 - la1) * k / 2) ** 2
         + math.cos(la1 * k) * math.cos(la2 * k) * math.sin((lo2 - lo1) * k / 2) ** 2)
    return 12742 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def pie_addr(text):
    """A PiE-ink's address as http://host:port (port 5000 when none is given), from pieink.txt, a
    camera.txt line or a beacon; None when it isn't one (a link with a path is a camera's)."""
    a = cam_address(text or "")
    if not a:
        return None
    try:
        u = urllib.parse.urlsplit(a if "://" in a else "http://" + a)
        port = u.port or PIE_PORT
    except ValueError:
        return None
    if u.path not in ("", "/") or u.query or not u.hostname:
        return None
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    return f"{u.scheme}://{host}:{port}"


def wx_units(data, have, want):
    """A forecast in the other units: °F and mph, or °C and km/h."""
    if have == want:
        return data

    def t(v):
        return None if v is None else round((v - 32) * 5 / 9 if want == "C" else v * 9 / 5 + 32, 1)

    def w(v):
        return None if v is None else round(v * 1.609344 if want == "C" else v / 1.609344, 1)
    out = dict(data, temp=t(data.get("temp")), feels=t(data.get("feels")), wind=w(data.get("wind")), units=want)
    out["days"] = [dict(d, hi=t(d.get("hi")), lo=t(d.get("lo"))) for d in data.get("days") or []]
    out["hours"] = [dict(h, temp=t(h.get("temp"))) for h in data.get("hours") or []]
    return out


def pie_weather(w):
    """PiE-ink's forecast (now and the next days, where it's for, how old), checked over and in the
    shape the Weather tab keeps; None when it isn't one. Numbers no weather has are left out."""
    if not isinstance(w, dict) or not isinstance(w.get("data"), dict):
        return None
    lat, lon, age, d = _fnum(w.get("lat"), -90, 90), _fnum(w.get("lon"), -180, 180), _age(w.get("age")), w["data"]
    units = d.get("units") if d.get("units") in ("F", "C") else w.get("units")

    def deg(v):                                       # (the hottest and coldest on record, in °F or °C)
        return _fnum(v, -130, 140)

    def code(v):
        v = _fnum(v, 0, 99)
        return None if v is None else int(v)

    def hhmm(v):
        return v if isinstance(v, str) and re.fullmatch(r"\d\d:\d\d", v) else ""
    if lat is None or lon is None or age is None or units not in ("F", "C") or deg(d.get("temp")) is None:
        return None
    days = []
    for x in d.get("days")[:16] if isinstance(d.get("days"), list) else []:
        if isinstance(x, dict) and isinstance(x.get("date"), str) and re.fullmatch(r"\d{4}-\d\d-\d\d", x["date"]):
            rain = _fnum(x.get("rain"), 0, 100)
            days.append({"date": x["date"], "code": code(x.get("code")), "hi": deg(x.get("hi")), "lo": deg(x.get("lo")),
                         "rain": None if rain is None else int(rain),
                         "sunrise": hhmm(x.get("sunrise")), "sunset": hhmm(x.get("sunset"))})
    nws = [[clean_name(n[0], 40), clean_name(n[1], 600)]
           for n in (w.get("nws")[:8] if isinstance(w.get("nws"), list) else [])
           if isinstance(n, (list, tuple)) and len(n) >= 2]
    return {"lat": lat, "lon": lon, "units": units, "place": clean_name(w.get("place"), 60),
            "country": clean_name(w.get("country"), 4).upper(), "age": age,
            "data": {"temp": deg(d.get("temp")), "feels": deg(d.get("feels")), "humidity": _fnum(d.get("humidity"), 0, 100),
                     "wind": _fnum(d.get("wind"), 0, 500), "wind_dir": _fnum(d.get("wind_dir"), 0, 360),
                     "code": code(d.get("code")), "is_day": d.get("is_day") is not False, "units": units,
                     "hours": [], "days": days},
            "nws": [n for n in nws if n[0] and n[1]], "nws_age": _age(w.get("nws_age"))}


def pie_coin(x):
    """One of PiE-ink's coins: (its id, {"q": the quote as the Crypto tab keeps it, "age", "graph",
    "graph_days", "graph_age"}), or None. Numbers no coin has are left out."""
    if not isinstance(x, dict) or not isinstance(x.get("data"), dict) or not isinstance(x.get("id"), str) \
            or not re.fullmatch(r"[a-z0-9-]{1,80}", x["id"]):
        return None
    d, age = x["data"], _age(x.get("age"))

    def usd(v):
        return _fnum(v, 0, 1e16)
    if age is None or usd(d.get("price")) is None:
        return None
    change = d.get("change") if isinstance(d.get("change"), dict) else {}
    rank = _fnum(d.get("rank"), 1, 1e7)
    q = {"symbol": clean_name(x.get("symbol"), 12).upper(), "name": clean_name(x.get("name"), 40),
         "price": usd(d.get("price")), "ath": usd(d.get("ath")), "market_cap": usd(d.get("market_cap")),
         "rank": None if rank is None else int(rank), "circulating_supply": usd(d.get("circulating_supply")),
         "sentiment_up": _fnum(d.get("sentiment_up"), 0, 100), "high_24h": usd(d.get("high_24h")),
         "low_24h": usd(d.get("low_24h")), "change_24h": _fnum(change.get("24h"), -99.99, 1e6)}
    graph = [usd(v) for v in (x.get("graph")[:5000] if isinstance(x.get("graph"), list) else [])]
    days = _fnum(x.get("graph_days"), 1, 3650)
    return x["id"], {"q": q, "age": age, "graph": graph if None not in graph else [],
                     "graph_days": None if days is None else int(days), "graph_age": _age(x.get("graph_age"))}


def pie_words(text):
    """A place's name from another machine, as a town's name is written."""
    return re.sub(r"[^\w .,'()\-]", "", text or "").strip()[:40]


class PieInk:
    """PiE-ink on another Pi of yours. Before the weather or a coin's price or chart is fetched
    from the internet, it's asked what it has already (GET /api/shared: what it has fetched and how
    old each is), and what it has is used when it's fresh and for the same place or coin, so the
    two Pis don't both fetch the same thing. It's found by itself: PiE-ink says it's there on the network
    every few seconds, and a camera in camera.txt may be one. pieink.txt can name it
    (pieink = 192.168.1.30) or turn this off (pieink = off). It's only asked: nothing is sent to it,
    and it fetches nothing for us. Nothing on the screen or in the README mentions it: it's a
    little extra for anyone who runs both."""

    def __init__(self, cameras=lambda: ([], [])):
        self.cameras = cameras        # () -> (cameras that answered as PiE-ink, camera.txt's addresses)
        self.heard = {}               # its address -> {"host", "seen"}: its beacon
        self.bad = {}                 # an address -> when it may be asked again
        self.answer = (0.0, None)     # (when, what it had): see fetch()
        self.remembered = None        # {"url", "host"}: the one that answered last (kept on disk)
        self.lock = threading.Lock()
        self.asking = threading.Lock()   # one question at a time; the others wait for its answer
        self.load()

    @property
    def path(self):
        return os.path.join(CACHE_DIR, "pieink.json")

    def load(self):
        try:
            with open(self.path) as f:
                got = json.load(f)
            url = pie_addr(got.get("url"))
            if url:
                self.remembered = {"url": url, "host": clean_name(got.get("host"), 40)}
        except (OSError, ValueError, AttributeError):
            pass

    def remember(self, url, host):
        if self.remembered == {"url": url, "host": host}:
            return
        self.remembered = {"url": url, "host": host}
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self.path + ".tmp", "w") as f:
                json.dump(self.remembered, f)
            os.replace(self.path + ".tmp", self.path)
        except OSError:
            pass

    def setting(self):
        """pieink.txt: "" (find it), "off", or the address it names."""
        v = read_config([settings_glob("pieink.txt")]).get("pieink", "").strip()
        if v.lower() in ("off", "no", "none", "false", "0"):
            return "off"
        return pie_addr(v) or ""

    def hear(self, ip, msg):
        """A PiE-ink's beacon: it's there (the Camera tab's listener hears them all)."""
        port = msg.get("port") or PIE_PORT
        if isinstance(port, str) and port.isdigit():
            port = int(port)
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            return
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return
        url, now = f"http://{ip}:{port}", time.time()
        with self.lock:
            back = now - (self.heard.get(url) or {}).get("seen", 0) > 60     # new, or back after a while
            self.heard[url] = {"host": clean_name(msg.get("host"), 40) or ip, "seen": now}
            if len(self.heard) > 16:
                for old in sorted(self.heard, key=lambda u: self.heard[u]["seen"])[:len(self.heard) - 16]:
                    del self.heard[old]
            if back:
                self.bad.pop(cam_key(url), None)      # (it's there now, whatever it did before)
                if self.answer[1] is None:
                    self.answer = (0.0, None)         # (nobody to ask a moment ago: there is now)

    def candidates(self):
        """Who to ask, best first: (addresses, the ones of them that are only guesses). The one
        pieink.txt names; else the one that answered last time, those heard lately and cameras that
        answered as PiE-ink; and only when none of those is answering, the cameras in camera.txt (a
        PiE-ink's camera is at its address), each tried once an hour at most."""
        s = self.setting()
        if s == "off":
            return [], set()
        if s:
            return [s], set()
        now = time.time()
        with self.lock:
            heard = [u for u, h in sorted(self.heard.items(), key=lambda kv: -kv[1]["seen"])
                     if now - h["seen"] <= 60]
        sure, maybe = self.cameras()

        def tidy(addrs):
            out, seen = [], set()
            for u in addrs:
                u = pie_addr(u)
                if u and cam_key(u) not in seen:
                    seen.add(cam_key(u))
                    out.append(u)
            return out
        sure = tidy(([self.remembered["url"]] if self.remembered else []) + heard + list(sure))
        if any(self.bad.get(cam_key(u), 0) <= now for u in sure):
            return sure, set()
        mine = {cam_key(u) for u in sure}               # (none of those answering lately: camera.txt's too)
        maybe = [u for u in tidy(maybe) if cam_key(u) not in mine]
        return sure + maybe, {cam_key(u) for u in maybe}

    def known(self):
        """A PiE-ink has answered, or said it's there, lately."""
        if self.answer[1]:
            return True
        now = time.time()
        with self.lock:
            heard = any(now - h["seen"] <= 60 for h in self.heard.values())
        return heard and self.setting() != "off"

    def ask(self):
        """What PiE-ink has: the answer from a moment ago, or a new one. None when there's no
        PiE-ink to ask or it isn't answering (or another question to it is taking long)."""
        at, got = self.answer
        if time.time() - at < PIE_FRESH:
            return got
        if not self.asking.acquire(timeout=PIE_TIMEOUT * 4):
            return None
        try:
            at, got = self.answer
            if time.time() - at < PIE_FRESH:
                return got
            got, start, tried = None, time.monotonic(), set()
            for _ in range(2):                         # (again when none answered: camera.txt's come in then)
                urls, guesses = self.candidates()
                for url in [u for u in urls if self.bad.get(cam_key(u), 0) <= time.time()
                            and cam_key(u) not in tried][:3]:
                    if time.monotonic() - start > PIE_TIMEOUT * 2:
                        break                          # (long enough on one question)
                    tried.add(cam_key(url))
                    got = self.fetch(url, guess=cam_key(url) in guesses)
                    if got:
                        break
                if got or time.monotonic() - start > PIE_TIMEOUT * 2:
                    break
            self.answer = (time.time(), got)
            return got
        finally:
            self.asking.release()

    def get(self, url):
        """(status, body) of a GET to a PiE-ink: all of it within a few seconds, however slowly it
        comes (each read waits PIE_TIMEOUT, so the whole is cut off as well)."""
        u = urllib.parse.urlsplit(url)
        conn = (CamHTTPS if u.scheme == "https" else CamHTTP)(u.hostname, u.port, timeout=PIE_TIMEOUT)
        timer = None
        try:
            conn.connect()
            sock, late = conn.sock, []

            def cut():
                late.append(True)
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(PIE_TIMEOUT * 2, cut)
            timer.daemon = True
            timer.start()
            try:
                conn.request("GET", u.path or "/", headers=dict(UA, Accept="application/json"))
                r = conn.getresponse()
                body = read_capped(r, PIE_MAX, time.monotonic() + PIE_TIMEOUT * 2)
            except Exception:
                if late:
                    raise TimeoutError("too slow")
                raise
            if late:                                   # (cut off: what came isn't all of it)
                raise TimeoutError("too slow")
            return r.status, body
        finally:
            if timer:
                timer.cancel()
            conn.close()

    def fetch(self, url, guess=False):
        """Ask one PiE-ink: {"at", "url", "host", "weather", "coins": {id: ...}}, or None (and it's
        left alone for a while: an hour if it isn't a PiE-ink, or was only a guess)."""
        def leave(secs):
            self.bad[cam_key(url)] = time.time() + (PIE_NOT if guess else secs)
            return None
        try:
            status, body = self.get(url + "/api/shared")
            if status != 200:                          # (404: an older PiE-ink, with nothing to share)
                return leave(PIE_NOT if status == 404 else PIE_RETRY)
            got = json.loads(body)
        except ValueError:                             # not JSON (or far too much of it): not a PiE-ink
            return leave(PIE_NOT)
        except Exception:
            return leave(PIE_RETRY)
        if not isinstance(got, dict) or got.get("ok") is not True:
            return leave(PIE_NOT)
        try:
            coins = {}
            for x in got.get("coins")[:100] if isinstance(got.get("coins"), list) else []:
                c = pie_coin(x)
                if c:
                    coins[c[0]] = c[1]
            weather = pie_weather(got.get("weather"))
        except Exception:                              # (something in it no PiE-ink would send)
            return leave(PIE_RETRY)
        with self.lock:
            host = (self.heard.get(url) or {}).get("host") or cam_host(url)
        self.remember(url, host)
        return {"at": time.time(), "url": url, "host": host, "weather": weather, "coins": coins}

    # what it has
    def weather(self, loc, units):
        """Its forecast for where you are (now and the next days, no hours), in your units:
        {"data", "age", "nws"}; None when it has none for somewhere near."""
        a = self.ask()
        w = a and a["weather"]
        try:
            here = (float(loc["lat"]), float(loc["lon"]))
        except (TypeError, ValueError, KeyError):
            return None
        if not w or km_apart(here, (w["lat"], w["lon"])) > PIE_NEAR:
            return None
        gone = time.time() - a["at"]
        nws = w["nws"] if w["nws_age"] is not None and w["nws_age"] + gone < PIE_NWS_AGE else []
        return {"data": wx_units(w["data"], w["units"], units), "age": w["age"] + gone, "nws": nws}

    def place(self):
        """Where its weather is for, as a location (Find me), or None."""
        a = self.ask()
        w = a and a["weather"]
        if not w:
            return None
        name, _, admin = w["place"].partition(",")
        return {"name": pie_words(name) or "Here", "admin": pie_words(admin), "country": pie_words(w["country"])[:2],
                "lat": round(w["lat"], 4), "lon": round(w["lon"], 4)}

    def quote(self, cid):
        """(a coin's quote, its age), or None."""
        a = self.ask()
        c = a and a["coins"].get(cid)
        return (c["q"], c["age"] + time.time() - a["at"]) if c else None

    def chart(self, cid, days):
        """(a coin's prices over `days`, their age), or None (it keeps one window: its own)."""
        a = self.ask()
        c = a and a["coins"].get(cid)
        if not c or c["graph_days"] != days or len(c["graph"]) < 2 or c["graph_age"] is None:
            return None
        return c["graph"], c["graph_age"] + time.time() - a["at"]


def read_own_text(path):
    """A settings file of yours, read in order to change it (this runs as root): only a plain
    file you could read yourself, so a link to somewhere private isn't copied into your folder."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with open(fd, errors="ignore") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or \
                (st.st_uid != os.stat(home_dir()).st_uid and not st.st_mode & stat.S_IROTH):
            raise PermissionError(f"{os.path.basename(path)} isn't a file of yours")
        return f.read(1_000_000)


def read_cameras(patterns):
    """The cameras in camera.txt, in order: 'camera = address' lines (a name after the address
    if you like), and the one 'url =' (or 'ip =' and 'port =') of the earlier PiE-ink setting."""
    cams, ip, port = [], "", "5000"
    for line in read_lines(patterns):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        k = k.lower()
        if k in ("camera", "url") and v:
            addr, _, name = v.partition(" ")
            cams.append({"addr": addr, "name": name.strip()[:40]})
        elif k == "ip":
            ip = v
        elif k == "port" and v:
            port = v
    if ip:
        cams.append({"addr": f"{ip}:{port}", "name": ""})
    out, seen = [], set()
    for c in cams:
        if cam_address(c["addr"]) and cam_key(c["addr"]) not in seen:
            seen.add(cam_key(c["addr"]))
            out.append(c)
    return out


def write_setting(name, text, private=False):
    """A settings file in the static folder, written whole and owned by you: a new file swapped
    in, so a link left in its place is replaced rather than followed (this runs as root)."""
    st = os.stat(home_dir())
    if not os.path.isdir(STATIC):                     # not made yet: yours, like the rest (and only
        os.mkdir(STATIC)                              # in a gpi-media folder that's there)
        os.chown(STATIC, st.st_uid, st.st_gid, follow_symlinks=False)
    fd, tmp = tempfile.mkstemp(dir=STATIC, prefix="." + name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            os.fchown(f.fileno(), st.st_uid, st.st_gid)     # (the open file: a swapped name can't
            os.fchmod(f.fileno(), 0o600 if private else 0o644)   # point root anywhere else)
            f.write(text)
        os.replace(tmp, settings_file(name))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return settings_file(name)


def edit_cameras(add=None, name="", remove=None):
    """camera.txt with a camera added or taken out, and the rest of it as it was."""
    path = settings_file("camera.txt")
    name = clean_name(name)
    try:
        lines = read_own_text(path).splitlines()
    except FileNotFoundError:
        lines = CAMERA_HEAD.rstrip("\n").split("\n")
    if remove:
        k = cam_key(remove)
        vals = {}
        for line in lines:
            key, _, v = line.strip().partition("=")
            if not line.strip().startswith("#") and v:
                vals.setdefault(key.strip().lower(), v.strip())
        legacy = bool(vals.get("ip")) and cam_key(f"{vals['ip']}:{vals.get('port') or '5000'}") == k
        out = []
        for line in lines:
            key, _, v = line.strip().partition("=")
            key = key.strip().lower()
            if not line.strip().startswith("#") and (
                    (key in ("camera", "url") and cam_key(v.strip().partition(" ")[0]) == k)
                    or (legacy and key in ("ip", "port"))):
                continue
            out.append(line)
        lines = out
    if add:
        if not any(ln.strip() and not ln.strip().startswith("#") for ln in lines) and not lines:
            lines = CAMERA_HEAD.rstrip("\n").split("\n")
        lines.append(f"camera = {add}" + (f"   {name}" if name else ""))
    return write_setting("camera.txt", "\n".join(lines).rstrip("\n") + "\n")


def cam_candidates(addr):
    """(kind, url) to try at an address, most likely first: a Pi's camera on its usual ports, then
    where other camera servers usually put their stream. A link with a path is tried as it is."""
    full = addr if "://" in addr else "http://" + addr
    u = urllib.parse.urlsplit(full)
    base = f"{u.scheme}://{u.netloc}"
    if u.path not in ("", "/") or u.query:
        return [("link", full)]
    if u.port:
        return [("pie", base)] + [("link", base + p) for p in CAM_PATHS]
    return [("pie", f"{base}:{p}") for p in CAM_PORTS] + [("link", f"{base}:{p}{path}") for p, path in CAM_LINKS]


def cam_probe(kind, url, timeout=3):
    """What answers at url: {"kind": "pie"/"mjpeg"/"jpeg", "url", "name", "server"}, or None."""
    try:
        if kind == "pie":
            info = cam_json(url + "/api/ptz", timeout)
            if not isinstance(info, dict) or "available" not in info:
                return None
            name = clean_name(info.get("name"))
            if not name:                                # PiE-ink: its name is in its status
                try:
                    name = clean_name(cam_json(url + "/api/status", timeout).get("hostname"))
                except Exception:
                    pass
            return {"kind": "pie", "url": url, "name": name, "server": clean_name(info.get("server") or "PiE-ink")}
        with cam_open(url, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
        if "multipart/x-mixed-replace" in ctype:
            return {"kind": "mjpeg", "url": url, "name": "", "server": "MJPEG stream"}
        if ctype.startswith("image/"):
            return {"kind": "jpeg", "url": url, "name": "", "server": "Picture link"}
    except Exception:
        return None
    return None


def cam_detect(addr, timeout=3):
    """Every likely place at once; the first of them, in order, that answers is the camera."""
    cands = cam_candidates(addr)
    found = [None] * len(cands)

    def one(i, kind, url):
        found[i] = cam_probe(kind, url, timeout)
    threads = [threading.Thread(target=one, args=(i, k, u), daemon=True) for i, (k, u) in enumerate(cands)]
    for t in threads:
        t.start()
    end = time.monotonic() + timeout * 2 + 1
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return next((f for f in found if f), None)


def mjpeg_frames(resp, alive=None, patience=10.0):
    """The JPEGs in an MJPEG stream, cut at each picture's own start and end markers (whether or
    not the stream says how long each part is). It stops as soon as alive() says so, and gives
    up when no whole picture has come for `patience` seconds."""
    buf = b""
    read = resp.read1 if hasattr(resp, "read1") else (lambda n: resp.read(min(n, 16384)))
    last = time.monotonic()
    while True:
        if alive is not None and not alive():
            return
        if time.monotonic() - last > patience:
            raise TimeoutError("no pictures")
        chunk = read(65536)
        if not chunk:
            return
        buf += chunk
        while True:
            a = buf.find(b"\xff\xd8")
            if a < 0:
                buf = buf[-1:]
                break
            z = buf.find(b"\xff\xd9", a + 2)
            if z < 0:
                buf = buf[a:]
                break
            yield buf[a:z + 2]
            last = time.monotonic()
            buf = buf[z + 2:]
        if len(buf) > CAM_FRAME_MAX:                  # no end in sight: start again
            buf = b""


class Camera:
    """The Camera tab: cameras on your other Pis, or anywhere on your network.

    A Pi running PiE-ink, or gpi-media's own camera server (camera.py: setup.sh --camera), is
    worked with the same calls as PiE-ink's web page: /api/ptz/drive while the d-pad is held,
    /api/ptz/stop when let go, /api/ptz/set for zoom, /api/ptz/follow and /api/ptz/home; the
    picture comes from /api/camera.jpg, and a picture is taken with its own shutter (POST
    /api/photos: the camera's biggest size) and copied into ~/Pictures. Any other camera with an
    MJPEG or JPEG link (an ESP32-CAM, motion, mjpg-streamer...) can be watched, and A keeps the
    picture on screen. Your cameras are in camera.txt; Pis that say they have one (PiE-ink
    and camera.py announce themselves) are listed as found."""

    def __init__(self):
        self.patterns = []
        self.cams = []               # [{"addr", "name"}]: camera.txt, in order
        self.found = {}              # cam_key -> {"addr", "name", "server", "seen"}: heard on the network
        self.known = {}              # cam_key -> what answered there: {"kind", "url", "name", "server"}
        self.missing = {}            # cam_key -> when nothing answered there
        self.thumbs = {}             # cam_key -> (its JPEG, a small picture, when)
        self.addr = ""               # the camera on screen
        self.kind = None             # "pie", "mjpeg" or "jpeg", once it has answered
        self.url = ""
        self.gen = 0                 # goes up when the camera changes or stops: its threads end
        self.finding = None          # the gen a look at the address is running for
        self.held = set()            # d-pad directions held right now
        self.zoom_dir = 0
        self.zoom = None             # 0..1, once the camera has said
        self.speed = "normal"
        self.info = {}               # the last /api/ptz answer
        self.reached = None          # True / False once we've tried
        self.frame = None            # the newest picture (PIL image)
        self.jpeg = None             # ...as it came (a camera without a shutter: the photo)
        self.frame_at = 0.0
        self.action = ""
        self.sid = uuid.uuid4().hex[:10]
        self.seq = 0
        self.running = False
        self.on_change = lambda: None
        self.on_saved = lambda path: None
        self.shooting = False        # a picture on its way
        self.shot = None             # (small copy, path, when) of the last one taken
        self.sel_down = None         # when SELECT went down: hold = follow, tap = on_select
        self.sel_used = False
        self.on_select = self.next_speed   # (media mode: the bot says what it sees, when there's one)
        self.start_down = None       # when START went down: tap = home, hold = the next speed
        self.start_used = False
        self.listening = False
        self.scanning = False
        self.on_pie = lambda ip, msg: None   # every PiE-ink heard (it's asked first for what it has)
        self.lock = threading.Lock()   # the gen, and what its threads bring back, change together

    def load(self, patterns, last=None):
        self.patterns = patterns
        self.cams = read_cameras(patterns)
        keys = [cam_key(c["addr"]) for c in self.cams]
        if self.addr and (cam_key(self.addr) in keys or cam_key(self.addr) in self.found):
            return
        if last and cam_key(last) in keys:
            self.select(self.cams[keys.index(cam_key(last))]["addr"])
        else:
            self.select(self.cams[0]["addr"] if self.cams else "")

    # names and places
    def name_of(self, addr):
        """What to call a camera: its name in camera.txt, the name it gave, or its address."""
        k = cam_key(addr)
        for c in self.cams:
            if cam_key(c["addr"]) == k and c["name"]:
                return c["name"]
        got = self.known.get(k) or self.found.get(k) or {}
        return got.get("name") or cam_host(addr) or addr

    def kind_of(self, addr):
        got = self.known.get(cam_key(addr)) or self.found.get(cam_key(addr)) or {}
        return got.get("server", "")

    @property
    def where(self):
        return self.addr.split("://", 1)[-1]

    @property
    def title(self):
        return self.name_of(self.addr) if self.addr else ""

    def place(self):
        """(1-based place, how many) of the camera on screen among yours, or None."""
        keys = [cam_key(c["addr"]) for c in self.cams]
        k = cam_key(self.addr)
        return (keys.index(k) + 1, len(keys)) if k in keys else None

    def mine(self, addr):
        return cam_key(addr) in [cam_key(c["addr"]) for c in self.cams]

    # choosing one, and finding out what it is
    def select(self, addr):
        """A camera on screen; what answers at its address is found out first (once)."""
        if addr and self.addr and cam_key(addr) == cam_key(self.addr):
            return
        with self.lock:
            self.gen += 1
            self.addr = addr or ""
            got = self.known.get(cam_key(addr)) if addr else None
            self.kind, self.url = (got["kind"], got["url"]) if got else (None, "")
            self.frame, self.jpeg, self.reached, self.info, self.zoom = None, None, None, {}, None
        self.held.clear()
        self.zoom_dir, self.sel_down, self.start_down, self.action = 0, None, None, ""
        if self.running:
            self.begin()
        self.on_change()

    def begin(self):
        gen = self.gen
        if not self.addr:
            return
        if self.kind:
            self.spawn(gen)
        elif self.finding != gen:
            self.finding = gen
            threading.Thread(target=self.find_job, args=(gen, self.addr), daemon=True, name="cam-find").start()

    def find_job(self, gen, addr):
        """What's at the address, asked again every few seconds while nothing answers."""
        try:
            while self.running and gen == self.gen:
                got = cam_detect(addr)
                with self.lock:
                    if gen != self.gen:
                        return
                    if got:
                        self.known[cam_key(addr)] = got
                        self.missing.pop(cam_key(addr), None)
                        self.kind, self.url = got["kind"], got["url"]
                    else:
                        self.missing[cam_key(addr)] = time.time()
                        self.reached = False
                if got:
                    self.spawn(gen)
                    self.on_change()
                    return
                self.on_change()
                for _ in range(50):
                    if not self.running or gen != self.gen:
                        return
                    time.sleep(0.1)
        finally:
            if self.finding == gen:
                self.finding = None

    def spawn(self, gen):
        if not self.running or gen != self.gen:
            return
        if self.kind == "pie":
            threading.Thread(target=self.control_loop, args=(gen, self.url), daemon=True,
                             name="cam-control").start()
        threading.Thread(target=self.picture_loop, args=(gen, self.kind, self.url), daemon=True,
                         name="cam-picture").start()

    # talking to it
    def call(self, path, body=None, timeout=3, raw=False, base=None, limit=None):
        url = path if path.startswith(("http://", "https://")) else (base or self.url) + path
        with cam_open(url, body, timeout) as r:
            out = read_capped(r, limit or (CAM_FRAME_MAX if raw else CAM_JSON_MAX), time.monotonic() + timeout * 2)
        return out if raw else (json.loads(out) if out.strip() else {})

    def post(self, path, body, base=None):
        try:
            return self.call(path, body, base=base)
        except Exception:
            return None

    def refresh(self, gen, base):
        try:
            info = self.call("/api/ptz", base=base)
            for k in ("position", "follow", "sleep"):     # whatever a camera says, these are dicts
                if not isinstance(info.get(k), dict):
                    info[k] = {}
            zoom = info["position"].get("zoom")
            zoom = None if zoom is None else max(0.0, min(1.0, float(zoom)))
        except Exception:
            info = zoom = None
        with self.lock:
            if gen != self.gen:
                return
            if info is None:
                self.reached, self.info = False, {}
            else:
                self.info, self.reached = info, True
                if self.zoom_dir == 0 and zoom is not None:
                    self.zoom = zoom
        self.on_change()

    @property
    def available(self):
        """A camera that turns (and zooms)."""
        return self.kind == "pie" and bool(self.info.get("available"))

    @property
    def steers(self):
        """The d-pad is for turning it: one that turns, or a Pi's camera that hasn't said yet."""
        return self.kind == "pie" and (self.available or not self.info)

    @property
    def can_follow(self):
        return self.available and (self.info.get("follow") or {}).get("can", True) is not False

    @property
    def following(self):
        return bool((self.info.get("follow") or {}).get("on"))

    @property
    def asleep(self):
        return bool((self.info.get("sleep") or {}).get("asleep"))

    # running while the Camera tab's picture is on screen
    def start(self):
        if self.running:
            return
        self.running = True
        self.listen()
        self.begin()

    def stop(self):
        self.held.clear()
        self.zoom_dir = 0
        self.sel_down = self.start_down = None
        with self.lock:
            if self.running:
                self.running = False
                self.gen += 1

    def control_loop(self, gen, base):
        moving, next_info, next_zoom = False, 0.0, 0.0
        while self.running and gen == self.gen:
            now = time.monotonic()
            held = set(self.held)
            if held:
                vx = ("right" in held) - ("left" in held)
                vy = ("up" in held) - ("down" in held)
                self.seq += 1
                body = {"vx": vx, "vy": vy, "sid": self.sid, "seq": self.seq}
                if CAM_SPEED[self.speed]:
                    body["speed"] = CAM_SPEED[self.speed]
                self.post("/api/ptz/drive", body, base)
                moving = True
            elif moving:
                self.seq += 1
                self.post("/api/ptz/stop", {"sid": self.sid, "seq": self.seq}, base)
                moving = False
            if self.zoom_dir and now >= next_zoom:
                self.zoom = max(0.0, min(1.0, (self.zoom or 0.0) + 0.04 * self.zoom_dir))
                self.post("/api/ptz/set", {"zoom": round(self.zoom, 3)}, base)
                self.action = f"Zoom {round(self.zoom * 100)}%"
                next_zoom = now + 0.12
                self.on_change()
            if now >= next_info and not held and not self.zoom_dir:
                self.refresh(gen, base)
                next_info = now + 2
            time.sleep(CAM_TICK)
        if moving:                                    # never leave it turning
            self.seq += 1
            self.post("/api/ptz/stop", {"sid": self.sid, "seq": self.seq}, base)

    def picture_loop(self, gen, kind, url):
        while self.running and gen == self.gen:
            t0 = time.monotonic()
            try:
                if kind == "mjpeg":
                    self.watch_stream(gen, url)
                else:
                    self.show(gen, self.call(url + "/api/camera.jpg" if kind == "pie" else url,
                                             timeout=4, raw=True))
            except Exception:
                with self.lock:
                    if gen != self.gen:
                        return
                    gone = time.monotonic() - self.frame_at > 5 and (self.frame is not None or self.reached is None)
                    if gone:
                        self.frame = None
                        if kind != "pie":
                            self.reached = False
                if gone:
                    self.on_change()
                time.sleep(1)
            time.sleep(max(0.0, 1 / CAM_FPS - (time.monotonic() - t0)))

    def show(self, gen, data):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (640, 480))                   # decoded small: quick on a Pi Zero
        rgb = im.convert("RGB")
        with self.lock:
            if gen != self.gen:
                return
            self.frame, self.jpeg, self.frame_at, self.reached = rgb, data, time.monotonic(), True
        self.on_change()

    def watch_stream(self, gen, url):
        """An MJPEG camera: its stream, a few pictures a second of it decoded."""
        alive = lambda: self.running and gen == self.gen   # noqa: E731
        with cam_open(url, timeout=5) as r:
            last = 0.0
            for jpeg in mjpeg_frames(r, alive):
                now = time.monotonic()
                if now - last >= 1 / CAM_FPS:
                    last = now
                    try:
                        self.show(gen, jpeg)
                    except OSError:
                        pass                          # a broken picture: the next one
        if alive():
            raise OSError("the stream ended")

    # the cameras on the network, and a small picture of each for the list
    def listen(self):
        """PiE-inks and camera.py say they're there a few times a minute: they show up as found."""
        if self.listening:
            return
        self.listening = True
        threading.Thread(target=self.listen_loop, daemon=True, name="cam-beacon").start()

    def listen_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            s.bind(("", CAM_BEACON))
        except OSError as ex:
            print(f"can't hear cameras on the network: {ex}", flush=True)
            return
        while True:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except OSError:
                time.sleep(0.5)
                continue
            try:
                self.heard(ip, data)
            except Exception:                         # anyone on the network can send anything
                pass

    def heard(self, ip, data):
        """One beacon: a PiE-ink or camera.py saying it's there."""
        msg = json.loads(data.decode())
        if not isinstance(msg, dict):
            return
        if msg.get("pie") == 1:
            self.on_pie(ip, msg)
        caps = msg.get("caps")
        if msg.get("gpicam") == 1:
            server, port = "gpi-media camera", msg.get("port") or 5433
        elif msg.get("pie") == 1 and (caps.get("camera", True) if isinstance(caps, dict) else True):
            server, port = "PiE-ink", msg.get("port") or 5000
        else:
            return
        if isinstance(port, str) and port.isdigit():
            port = int(port)
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
            return
        addr = f"{ip}:{port}"
        k = cam_key(addr)
        new = k not in self.found
        self.found[k] = {"addr": addr, "name": clean_name(msg.get("name") or msg.get("host") or ip) or ip,
                         "server": server, "seen": time.time()}
        if new:
            self.tidy()
            self.on_change()

    def tidy(self):
        """Cameras not heard from for a while forgotten (and only the newest few kept), and with
        them what was known about any camera that's neither yours nor heard lately."""
        now = time.time()
        found = sorted(list(self.found.items()), key=lambda kv: -kv[1]["seen"])
        self.found = {k: f for k, f in found[:CAM_FOUND_KEEP] if now - f["seen"] <= CAM_FOUND_FOR * 10}
        keep = set(self.found) | {cam_key(c["addr"]) for c in self.cams} | {cam_key(self.addr)}
        for name in ("known", "missing", "thumbs"):
            setattr(self, name, {k: v for k, v in list(getattr(self, name).items()) if k in keep})

    def found_list(self):
        """Cameras heard on the network lately that aren't in your list."""
        now = time.time()
        mine = {cam_host(c["addr"]) for c in self.cams}
        out = [f for f in list(self.found.values())
               if now - f["seen"] <= CAM_FOUND_FOR and cam_host(f["addr"]) not in mine]
        return sorted(out, key=lambda f: f["name"].lower())

    def scan(self):
        """A small picture from each camera for the list, in the background (one at a time)."""
        self.listen()
        self.tidy()
        if self.scanning:
            return
        self.scanning = True
        threading.Thread(target=self.scan_job, daemon=True, name="cam-scan").start()

    def unseen(self):
        """Cameras in the list without a small picture yet (and not just found not to answer)."""
        now = time.time()
        return [a for a in [c["addr"] for c in self.cams] + [f["addr"] for f in self.found_list()]
                if cam_key(a) not in self.thumbs and now - self.missing.get(cam_key(a), 0) > 30]

    def scan_job(self):
        try:
            for addr in [c["addr"] for c in self.cams] + [f["addr"] for f in self.found_list()]:
                if time.time() - self.missing.get(cam_key(addr), 0) > 30 or cam_key(addr) in self.thumbs:
                    self.snapshot(addr, max_age=20)
                    self.on_change()
        finally:
            self.scanning = False
            self.on_change()

    def snapshot(self, addr, max_age=2.0):
        """(JPEG, small picture, when) from a camera, no older than max_age seconds; None when it
        doesn't answer."""
        k = cam_key(addr)
        have = self.thumbs.get(k)
        if have and time.time() - have[2] < max_age:
            return have
        got = self.known.get(k)
        if not got:
            got = cam_detect(addr)
            if not got:
                self.missing[k] = time.time()
                return None
            self.known[k] = got
        try:
            if got["kind"] == "mjpeg":
                with cam_open(got["url"], timeout=5) as r:
                    data = next(mjpeg_frames(r, patience=8), None)
            else:
                data = self.call(got["url"] + "/api/camera.jpg" if got["kind"] == "pie" else got["url"],
                                 timeout=6, raw=True)
            from PIL import Image
            im = Image.open(io.BytesIO(data or b""))
            im.draft("RGB", (320, 240))
            small = im.convert("RGB")
            small.thumbnail((64, 48))
            if len(data) > CAM_KEEP_MAX:              # a big picture: a smaller copy is kept
                big = Image.open(io.BytesIO(data))
                big.draft("RGB", (1280, 960))
                big = big.convert("RGB")
                big.thumbnail((1280, 960))
                out = io.BytesIO()
                big.save(out, "JPEG", quality=85)
                data = out.getvalue()
        except Exception:
            self.missing[k] = time.time()
            return None
        self.missing.pop(k, None)
        self.thumbs[k] = (data, small, time.time())
        return self.thumbs[k]

    # buttons
    def press(self, name):
        if name == "a":
            self.take_photo()
            return True
        if not self.steers:
            if name in ("up", "down", "left", "right", "x", "y", "start", "select"):
                self.action = "This camera doesn't turn" if self.reached else ""
                return True
            return False
        if name in ("up", "down", "left", "right"):
            if self.following:                        # steering takes over from follow-me
                self.info.setdefault("follow", {})["on"] = False
                threading.Thread(target=self.post, args=("/api/ptz/follow", {"on": False}),
                                 daemon=True).start()
            self.held.add(name)
            self.action = self.moving_text()
        elif name in ("x", "y"):
            self.zoom_dir = 1 if name == "x" else -1
        elif name == "start":                         # decided when let go, or once held long enough
            self.start_down, self.start_used = time.monotonic(), False
        elif name == "select":                        # decided when let go, or once held long enough
            self.sel_down, self.sel_used = time.monotonic(), False
        else:
            return False
        return True

    def toggle_follow(self):
        if not self.can_follow:
            self.action = "Following you needs PiE-ink"
            return
        on = not self.following
        self.info.setdefault("follow", {})["on"] = on
        self.action = "Following you" if on else "Follow off"
        threading.Thread(target=self.post, args=("/api/ptz/follow", {"on": on}),
                         daemon=True).start()

    def go_home(self):
        self.action = "Going home"
        threading.Thread(target=self.post, args=("/api/ptz/home", {}), daemon=True).start()

    def next_speed(self):
        order = ["normal", "fast", "slow"]
        self.speed = order[(order.index(self.speed) + 1) % len(order)]
        self.action = f"Speed: {self.speed}"

    def check_hold(self):
        """Called every loop: SELECT held long enough turns Follow me on or off; START, the speed."""
        if self.sel_down is not None and not self.sel_used \
                and time.monotonic() - self.sel_down >= CAM_HOLD:
            self.sel_used = True
            self.toggle_follow()
            return True
        if self.start_down is not None and not self.start_used \
                and time.monotonic() - self.start_down >= CAM_HOLD:
            self.start_used = True
            self.next_speed()
            return True
        return False

    # taking a picture
    def take_photo(self):
        if self.shooting or not self.addr:
            return
        self.shooting = True
        self.action = "Taking a picture…"
        threading.Thread(target=self.photo_job, daemon=True, name="cam-photo").start()

    def photo_bytes(self):
        """The camera's own shutter (PiE-ink, camera.py): woken first if asleep, at its biggest size.
        A camera without one, or an older PiE-ink: the picture on screen."""
        if self.kind != "pie":
            if self.jpeg is None:
                raise ValueError("there's no picture yet")
            return self.jpeg
        return self.shutter(self.url)

    def photo_of(self, addr):
        """A picture from the camera at addr (for the bot): its own shutter on a Pi with one, the
        live picture from any other. ValueError: why not."""
        k = cam_key(addr)
        got = self.known.get(k)
        if not got:
            got = cam_detect(addr)
            if not got:
                self.missing[k] = time.time()
                raise ValueError(f"the camera {self.name_of(addr)} didn't answer")
            self.known[k] = got
            self.missing.pop(k, None)
        try:
            if got["kind"] == "pie":
                return self.shutter(got["url"])
            snap = self.snapshot(addr, max_age=0)
        except urllib.error.HTTPError as e:
            raise ValueError(f"the camera said {e.code}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise ValueError(f"can't reach the camera {self.name_of(addr)}")
        if not snap:
            raise ValueError(f"the camera {self.name_of(addr)} didn't answer")
        return snap[0]

    def shutter(self, base):
        """A picture from the camera at base (PiE-ink, camera.py) with its own shutter: woken first if
        asleep, at its biggest size. An older PiE-ink: the live picture."""
        try:
            got = self.call("/api/photos", {"filter": "none"}, timeout=25, base=base)
            got = got if isinstance(got, dict) else {}
            photo = got.get("photo") if isinstance(got.get("photo"), dict) else {}
            url = photo.get("url") if isinstance(photo.get("url"), str) else ""
            if not url:
                raise ValueError(clean_name(got.get("error"), 80) or "the camera sent no picture")
            if url.startswith(("http://", "https://")):
                if cam_host(url) != cam_host(base):
                    raise ValueError("the camera sent a picture from somewhere else")
            elif not url.startswith("/"):
                url = "/" + url
            return self.call(url, timeout=20, raw=True, base=base, limit=CAM_PHOTO_MAX)
        except urllib.error.HTTPError as e:
            if e.code in (404, 405):
                return self.call("/api/camera.jpg", timeout=6, raw=True, base=base)
            try:
                why = clean_name(json.loads(e.read(65536) or b"{}").get("error"), 80)
            except (ValueError, OSError, AttributeError):
                why = None
            raise ValueError(why or f"the camera said {e.code}")

    def photo_job(self):
        from PIL import Image
        try:
            try:
                data = self.photo_bytes()
                im = Image.open(io.BytesIO(data))
                ext = ".png" if (im.format or "").lower() == "png" else ".jpg"
                small = im.convert("RGB")
                small.thumbnail((176, 132))
            except urllib.error.HTTPError as e:
                raise ValueError(f"the camera said {e.code}")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                raise ValueError("can't reach the camera")
            except OSError:
                raise ValueError("that wasn't a picture")
            try:
                path = save_picture(data, ext)
            except OSError as e:
                raise ValueError(f"couldn't save it ({e.strerror or e})")
            self.shot = (small, path, time.monotonic())
            self.action = ""
            self.on_saved(path)
        except Exception as e:
            self.action = f"No picture: {e or 'no answer'}"[:60]
            self.on_saved(None)
        finally:
            self.shooting = False
            self.on_change()

    def moving_text(self):
        parts = [d for d in ("up", "down", "left", "right") if d in self.held]
        return "Moving " + "-".join(parts) if parts else ""

    def release(self, name):
        if name in self.held:
            self.held.discard(name)
            self.action = self.moving_text()
        elif name in ("x", "y") and self.zoom_dir:
            self.zoom_dir = 0
        elif name == "select" and self.sel_down is not None:
            self.sel_down, tapped = None, not self.sel_used
            if tapped:                                # a tap: what the Camera tab says
                self.on_select()
        elif name == "start" and self.start_down is not None:
            self.start_down, tapped = None, not self.start_used
            if tapped:                                # a tap: back to where it started
                self.go_home()

# ---- the bot's voice: Piper, a neural voice that runs on the Pi --------------------------------------
PIPER_DIR = "/usr/local/share/gpi-media/piper"     # Piper itself, from its own release (checked below)
VOICES_DIR = "/usr/local/share/gpi-media/voices"   # the voices you've picked
PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_{}.tar.gz"
PIPER_SHA256 = {"aarch64": "fea0fd2d87c54dbc7078d0f878289f404bd4d6eea6e7444a77835d1537ab88eb",
                "armv7l": "c6946fcd57c705ed1d4666ea880f80ba0bbbd14de62ecbdd13460baf3bac8e37",
                "x86_64": "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"}
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{}/{}"
BOT_VOICES = [                                     # (its name in Piper's library, what we call it, what it's like)
    ("en_US-amy-low", "Amy, quick", "American, best on a Pi Zero"),
    ("en_GB-alan-low", "Alan, quick", "British"),
    ("en_US-amy-medium", "Amy", "American, warm"),
    ("en_US-lessac-medium", "Lessac", "American, clear"),
    ("en_US-ryan-medium", "Ryan", "American, male"),
    ("en_GB-alan-medium", "Alan", "British, male"),
    ("en_GB-jenny_dioco-medium", "Jenny", "British, female"),
    ("en_GB-northern_english_male-medium", "Northern English", "British, male"),
]
VOICE_MB = 63            # each of those is about this big
VOICE_IDLE = 120         # seconds quiet before Piper is let go (it holds about 100 MB while it waits)
VOICE_WAIT = 90          # a voice on a small Pi can take this long to load and make its first sentence
VOICE_SAMPLE = "Hello! This is how I sound."
VOICE_SINCE = time.time()  # (leftovers older than this, under this process's number, are from before)


def piper_arch():
    """Which of Piper's builds runs here. The system decides, not the kernel: a Pi with a 64-bit
    kernel and a 32-bit system needs the 32-bit one. None on armv6 (a Pi 1, Zero or Zero W)."""
    m = platform.machine().lower()
    bits64 = sys.maxsize > 2 ** 32
    if m in ("x86_64", "amd64"):
        return "x86_64" if bits64 else None
    if m in ("aarch64", "arm64"):
        return "aarch64" if bits64 else "armv7l"
    if m.startswith("armv7") or m == "armv8l":
        return "armv7l"
    return None


def piper_bin():
    return os.path.join(PIPER_DIR, "piper")


def voice_user():
    """Who Piper runs as: the home folder's owner rather than root (what it reads comes from a
    voice file, and from words anyone could get the bot to say). aplay, only given samples, stays
    root like mplayer, so it plays where mplayer plays.
    (uid, gid, groups, home); uid None when this isn't running as root to begin with."""
    home = home_dir()
    try:
        st = os.stat(home)
    except OSError:
        return None, None, [], home
    if os.geteuid() != 0 or st.st_uid == 0:
        return None, None, [], home
    groups = []
    try:
        import grp
        groups = [grp.getgrnam("audio").gr_gid]
    except (ImportError, KeyError):
        pass
    return st.st_uid, st.st_gid, groups, home


def as_user():
    """Popen's arguments for running something as voice_user()."""
    uid, gid, groups, home = voice_user()
    if uid is None:
        return {}
    return {"user": uid, "group": gid, "extra_groups": groups,
            "env": dict(os.environ, HOME="/nonexistent", XDG_CONFIG_HOME="/nonexistent")}


def shared_dir(path):
    """A folder root writes and everyone can read (Piper runs as you)."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o755)


def voice_files(vid):
    model = os.path.join(VOICES_DIR, vid + ".onnx")
    return model, model + ".json"


def voice_name(vid):
    return next((n for i, n, _ in BOT_VOICES if i == vid), vid)


def voice_folder(vid):
    """Where a voice is in Piper's library: en_US-amy-low is en/en_US/amy/low."""
    parts = vid.split("-")
    return f"{parts[0].split('_')[0]}/{parts[0]}/{'-'.join(parts[1:-1])}/{parts[-1]}"


def voices_here():
    """The voices on the Pi (each with its settings file)."""
    try:
        names = set(os.listdir(VOICES_DIR))
    except OSError:
        return set()
    return {f[:-5] for f in names if f.endswith(".onnx") and f + ".json" in names}


def speech_text(text):
    """What it said, made for saying: degrees as a word, and nothing a voice would spell out."""
    t = re.sub(r"\s*°\s*[FC]\b", " degrees", text or "").replace("°", " degrees")
    t = "".join(" " if ord(c) >= 0x1F000 or 0x2600 <= ord(c) < 0x2800 or c in "‍️*_#~`|<>"
                else c for c in t if c.isprintable() or c.isspace())
    return " ".join(t.split())


def speech_sentences(text):
    """A reply a sentence at a time, so the first can be said while the next is made ("Hi." goes
    with what comes after it)."""
    out = []
    for p in (p.strip() for p in re.split(r"(?<=[.!?…])\s+", text)):
        if not p:
            continue
        if out and len(out[-1]) < 12:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def read_speech(path, volume=100):
    """One of Piper's WAVs as 16-bit mono samples at the media volume, and its rate. Only a plain
    file of a sensible size, not followed through a link (Piper runs as you; this is root)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with open(fd, "rb") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 30_000_000:
            raise ValueError("not a WAV of Piper's")
        with wave.open(f, "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError("not a WAV of Piper's")
            rate, pcm = w.getframerate(), w.readframes(w.getnframes())
    if volume < 100:
        import numpy
        quieter = numpy.frombuffer(pcm, dtype="<i2").astype(numpy.float32) * (max(0, volume) / 100.0)
        pcm = quieter.astype("<i2").tobytes()
    return pcm, rate


class Voice:
    """The bot's voice: Piper, a neural voice that runs on the Pi, and aplay.

    Piper is given a reply a sentence at a time. It writes each one as a WAV (into memory) and says
    so when it's done, while the sentence before plays: speaking starts after one sentence rather
    than the whole reply. Piper stays loaded while it's in use (a voice takes seconds to load on a
    Pi Zero) and is let go after a couple of quiet minutes. Piper and the voices come from their own
    releases the first time a voice is picked; Piper is checked against its known SHA-256."""

    def __init__(self):
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.pending = None          # (gen, text or None to just load, voice, aplay's device, volume)
        self.gen = 0                 # goes up to cut off what's being said
        self.proc = None             # Piper, with self.loaded's voice
        self.loaded = ""
        self.out = ""                # where Piper's WAVs land
        self.err = None              # what Piper says when it won't start
        self.buf = b""               # what Piper has written so far on its way to a whole line
        self.inflight = 0            # sentences given to Piper that haven't come back
        self.play = None             # aplay, while something is being said
        self.speaking = False
        self.error = ""              # why the last thing wasn't said, or a voice didn't arrive
        self.used = 0.0              # when it last said something (time.monotonic())
        self.let_go = False
        self.job = None              # a download: {"id", "what", "pct"}
        self.on_change = lambda: None
        self.on_ready = lambda vid: None
        threading.Thread(target=self.run, daemon=True, name="voice").start()

    @staticmethod
    def tidy():
        """What a gpi_keys stopped part way left behind (each is named after the process it was
        for): half-fetched voices, Piper half unpacked, WAVs in memory."""
        for pattern in (os.path.join(VOICES_DIR, "*.part"), os.path.join(os.path.dirname(PIPER_DIR), ".piper-*"),
                        "/dev/shm/gpi-voice-*"):
            for path in glob.glob(pattern):
                pid = re.search(r"[.-](\d+)[.-]", os.path.basename(path))
                try:
                    mine_now = int(pid.group(1)) != os.getpid() or os.path.getmtime(path) >= VOICE_SINCE
                except (AttributeError, OSError):
                    mine_now = False
                if pid and os.path.exists(f"/proc/{pid.group(1)}") and mine_now:
                    continue                          # (still at it)
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def changed(self):
        try:
            self.on_change()
        except Exception as ex:                       # (its own threads carry on, whatever happens)
            print(f"voice: {ex!r}", flush=True)

    # what's here
    @staticmethod
    def supported():
        return piper_arch() is not None

    @staticmethod
    def have_piper():
        return os.access(piper_bin(), os.X_OK)

    def status(self):
        job = self.job
        if job:
            return f"Getting {job['what']}… {job['pct']}%"
        return self.error

    # saying things
    def say(self, text, vid, device="", volume=100):
        """Say something, cutting off whatever is being said. (True, "") or (False, why not)."""
        text = speech_text(text)
        if not text:
            return False, "There's nothing to say"
        if not vid or vid not in voices_here():
            return False, "Pick a voice in Settings > Bot"
        if not self.have_piper():
            return False, "Piper isn't on the Pi: pick the voice again"
        if not shutil.which("aplay"):
            return False, "aplay is missing: run setup.sh again"
        with self.lock:
            self.gen += 1
            self.pending = (self.gen, text, vid, device, volume)
            self.speaking = True
            self.error = ""
        self.kill_play()
        self.wake.set()
        self.changed()
        return True, ""

    def warm(self, vid):
        """The voice loaded ahead of the first reply (the bot's page just opened)."""
        if vid in voices_here() and self.have_piper():
            with self.lock:
                if self.pending is None and not self.speaking:
                    self.pending = (self.gen, None, vid, "", 100)
            self.wake.set()

    def stop(self, unload=False):
        """Quiet, now (and Piper let go too, when unload)."""
        with self.lock:
            self.gen += 1
            self.pending = None
            self.speaking = False
            self.let_go = self.let_go or unload
        self.kill_play()
        self.wake.set()
        self.changed()

    def kill_play(self):
        play = self.play
        if play is not None and play.poll() is None:
            try:
                play.kill()
            except OSError:
                pass

    def run(self):
        """The one thread that speaks: each new thing to say cuts off the last."""
        self.tidy()
        while True:
            self.wake.wait(5)
            with self.lock:
                job, self.pending = self.pending, None
                self.wake.clear()
                let_go, self.let_go = self.let_go, False
            if let_go:
                self.unload()
            if job is None:
                if self.proc and time.monotonic() - self.used > VOICE_IDLE:
                    self.unload()
                continue
            gen, text, vid, device, volume = job
            try:
                if text is None:
                    self.load(vid)
                else:
                    self.speak(gen, text, vid, device, volume)
            except Exception as ex:                   # (it must keep going, whatever happens)
                self.error = f"Couldn't say it ({ex})"[:90]
                self.kill_play()
                self.unload()
            finally:
                self.used = time.monotonic()
                with self.lock:
                    if self.pending is None:
                        self.speaking = False
                self.changed()

    def load(self, vid):
        """Piper with this voice (started afresh for another voice, or when it has stopped)."""
        if self.proc and self.proc.poll() is None and self.loaded == vid:
            return True
        self.unload()
        model, conf = voice_files(vid)
        self.out = tempfile.mkdtemp(prefix=f"gpi-voice-{os.getpid()}-",
                                    dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
        user = as_user()
        if user:
            os.chown(self.out, user["user"], user["group"])
        self.err = tempfile.TemporaryFile()
        try:
            self.proc = subprocess.Popen(["nice", "-n", "5", piper_bin(), "-q", "-m", model, "-c", conf, "-d", self.out],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err,
                                         cwd=PIPER_DIR, **user)
        except OSError as ex:
            self.proc = None
            self.error = f"Piper wouldn't start ({ex.strerror or ex})"
            shutil.rmtree(self.out, ignore_errors=True)
            self.out = ""
            return False
        self.loaded, self.buf, self.inflight = vid, b"", 0
        return True

    def unload(self):
        proc, self.proc, self.loaded = self.proc, None, ""
        if proc is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.kill()
                proc.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self.out:
            shutil.rmtree(self.out, ignore_errors=True)
            self.out = ""
        self.buf, self.inflight = b"", 0

    def piper_said(self):
        """The last thing Piper said before it stopped."""
        try:
            self.err.seek(0)
            lines = [ln.strip() for ln in self.err.read().decode(errors="ignore").splitlines() if ln.strip()]
        except (OSError, ValueError, AttributeError):
            lines = []
        return lines[-1][:80] if lines else ""

    def feed(self, sentence):
        """A sentence to Piper. False when Piper has stopped (what it already made still plays)."""
        try:
            self.proc.stdin.write(sentence.encode() + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError, AttributeError):
            said = self.piper_said()
            self.error = "Piper stopped" + (f" ({said})" if said else "")
            self.unload()
            return False
        self.inflight += 1
        return True

    def next_wav(self, gen, until):
        """The next WAV Piper has made: its path, or None when it's cut off, out of time, or Piper
        has stopped."""
        if self.proc is None:
            return None
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            if gen != self.gen:
                return None
            if time.monotonic() > until:
                self.error = "Piper took too long"
                self.unload()
                return None
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                chunk = os.read(fd, 4096)
                if not chunk:
                    self.error = "Piper stopped" + (f" ({self.piper_said()})" if self.piper_said() else "")
                    self.unload()
                    return None
                self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        self.inflight -= 1
        path = os.path.realpath(line.decode(errors="ignore").strip())
        return path if os.path.dirname(path) == os.path.realpath(self.out) else ""

    def drain(self):
        """Sentences of a reply that was cut off, still with Piper: they're let come and thrown
        away (Piper is started afresh if they'd hold up the next reply too long)."""
        until = time.monotonic() + 8
        while self.inflight > 0 and self.proc is not None:
            path = self.next_wav(self.gen, until)
            if path is None:
                break
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        if self.inflight > 0:
            self.unload()

    def speak(self, gen, text, vid, device, volume):
        if not self.load(vid):
            return
        self.drain()
        if gen != self.gen or not self.load(vid):
            return
        todo = speech_sentences(text)
        if not todo or not self.feed(todo.pop(0)):
            return
        play, until = None, time.monotonic() + VOICE_WAIT
        try:
            while gen == self.gen:
                path = self.next_wav(gen, until)
                if path is None:
                    break
                pcm = None
                if path:
                    try:
                        pcm, rate = read_speech(path, volume)
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                if todo and not self.feed(todo.pop(0)):   # the next one is made while this one plays
                    todo = []
                until = time.monotonic() + VOICE_WAIT
                if pcm is None:
                    continue
                if play is None:
                    play = self.start_play(rate, device)
                    if play is None:
                        break
                if not self.write(play, pcm, gen):
                    break
                if not todo and self.inflight == 0:
                    break
            if play is not None and gen == self.gen:
                self.finish(play, gen)
        finally:
            if play is not None:
                if play.poll() is None:
                    try:
                        play.kill()
                    except OSError:
                        pass
                for f in (play.stdin, play.said):
                    try:
                        f.close()
                    except (OSError, ValueError):
                        pass

    def start_play(self, rate, device):
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(rate)]
        if device:
            cmd += ["-D", device]
        err = tempfile.TemporaryFile()
        try:
            play = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err)
        except OSError as ex:
            err.close()
            self.error = f"aplay wouldn't start ({ex.strerror or ex})"
            return None
        play.said = err
        self.play = play
        return play

    def aplay_said(self, play):
        try:
            play.said.seek(0)
            lines = [ln.strip() for ln in play.said.read().decode(errors="ignore").splitlines() if ln.strip()]
        except (OSError, ValueError):
            lines = []
        return re.sub(r"^aplay: \w+:\d+: ", "", lines[-1])[:80] if lines else ""

    def write(self, play, pcm, gen):
        """Samples to aplay, a little at a time so being cut off is quick. False when it can't go on."""
        for i in range(0, len(pcm), 8192):
            if gen != self.gen:
                return False
            try:
                play.stdin.write(pcm[i:i + 8192])
            except (BrokenPipeError, OSError, ValueError):
                if gen == self.gen:
                    play.wait()
                    self.error = "Couldn't play it" + (f": {self.aplay_said(play)}" if self.aplay_said(play) else "")
                return False
        return True

    def finish(self, play, gen):
        """The rest played out (unless it's cut off)."""
        try:
            play.stdin.close()
        except OSError:
            pass
        while play.poll() is None:
            if gen != self.gen:
                return
            time.sleep(0.05)
        if play.returncode not in (0, None) and gen == self.gen:
            self.error = "Couldn't play it" + (f": {self.aplay_said(play)}" if self.aplay_said(play) else "")

    # getting Piper and the voices
    def get(self, vid):
        """Piper (the first time) and a voice onto the Pi, in the background; on_ready(vid) once
        it's here. False while another is on its way."""
        if self.job:
            return False
        self.error = ""
        self.job = {"id": vid, "what": "Piper" if not self.have_piper() else voice_name(vid), "pct": 0}
        threading.Thread(target=self.get_job, args=(vid,), daemon=True, name="voice-get").start()
        self.changed()
        return True

    def get_job(self, vid):
        name = voice_name(vid)
        try:
            if not self.have_piper():
                self.get_piper()
            self.job = {"id": vid, "what": name, "pct": 0}
            self.changed()
            self.get_voice(vid)
            self.job = None
            self.on_ready(vid)
        except Exception as ex:
            why = getattr(ex, "reason", None) or ex
            self.error = f"Couldn't get {name} ({why})"[:90]
            self.job = None
        self.changed()

    def fetch(self, url, dest, limit, room=0):
        """A download into dest (with `room` bytes more to spare), how far along it is in self.job;
        its SHA-256."""
        h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r, \
                open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            if total > limit:
                raise ValueError("it's bigger than it should be")
            if total and shutil.disk_usage(os.path.dirname(dest)).free < total + room + 50_000_000:
                raise ValueError("there isn't room for it on the Pi")
            got = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                got += len(chunk)
                if got > limit:
                    raise ValueError("it's bigger than it should be")
                f.write(chunk)
                h.update(chunk)
                job = self.job
                if total and job and min(99, got * 100 // total) != job["pct"]:
                    job["pct"] = min(99, got * 100 // total)
                    self.changed()
            if total and got != total:
                raise ValueError("the download was cut short")
        return h.hexdigest()

    def get_piper(self):
        arch = piper_arch()
        if not arch:
            raise ValueError("Piper doesn't run on this Pi")
        parent = os.path.dirname(PIPER_DIR)
        shared_dir(parent)
        tmp = tempfile.mkdtemp(prefix=f".piper-{os.getpid()}-", dir=parent)
        try:
            tar = os.path.join(tmp, "piper.tar.gz")
            if self.fetch(PIPER_URL.format(arch), tar, 80_000_000, room=80_000_000) != PIPER_SHA256[arch]:
                raise ValueError("the download didn't check out")
            with tarfile.open(tar) as t:
                for m in t.getmembers():
                    parts = m.name.split("/")
                    if parts[0] != "piper" or ".." in parts or not (m.isfile() or m.isdir() or m.issym()) or \
                            (m.issym() and (m.linkname.startswith("/") or ".." in m.linkname.split("/"))):
                        raise ValueError("the download didn't check out")
                t.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
            shutil.rmtree(PIPER_DIR, ignore_errors=True)
            os.chmod(os.path.join(tmp, "piper"), 0o755)
            os.replace(os.path.join(tmp, "piper"), PIPER_DIR)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if not self.have_piper():
            raise ValueError("Piper didn't unpack")

    def get_voice(self, vid):
        shared_dir(os.path.dirname(VOICES_DIR))
        shared_dir(VOICES_DIR)
        model, conf = voice_files(vid)
        parts = (f"{model}.{os.getpid()}.part", f"{conf}.{os.getpid()}.part")
        try:
            self.fetch(VOICE_URL.format(voice_folder(vid), vid + ".onnx.json"), parts[1], 1_000_000)
            with open(parts[1]) as f:
                if not (json.load(f).get("audio") or {}).get("sample_rate"):
                    raise ValueError("that isn't a voice")
            self.fetch(VOICE_URL.format(voice_folder(vid), vid + ".onnx"), parts[0], 200_000_000)
            for part in parts:
                os.chmod(part, 0o644)
            os.replace(parts[0], model)
            os.replace(parts[1], conf)
        finally:
            for p in parts:
                try:
                    os.remove(p)
                except OSError:
                    pass

    def remove(self, vid):
        """A voice off the Pi (Piper let go first, if it's the one loaded)."""
        if self.loaded == vid:
            self.stop(unload=True)
        for p in voice_files(vid):
            try:
                os.remove(p)
            except OSError:
                pass
        self.changed()


# ---- the bot: a model on another computer, through Ollama ---------------------------------------------
FRIEND_LOG = "/var/lib/gpi-keys/friend.json"   # what was said (root only)
FRIEND_PICS = "/var/lib/gpi-keys/bot-pictures"  # the pictures in the conversation, small (root only)
FRIEND_PIC_SIZE = 480            # pixels across, at most, of a picture kept in the conversation
FRIEND_SEE_SIZE = 768            # ...and of one a model is shown
FRIEND_PIC_BYTES = 40 << 20      # a picture file bigger than this isn't opened
FRIEND_PIC_KINDS = ("JPEG", "PNG", "GIF", "BMP", "WEBP", "TIFF")   # ...nor any other kind
FRIEND_PIC_PIXELS = {"JPEG": 60_000_000, "MPO": 60_000_000,   # ...nor one bigger than this: a JPEG opens
                     "WEBP": 4_000_000}
FRIEND_PIC_OTHER = 16_000_000                                 # small, the rest open whole
FRIEND_PIC_ROOM = 64 << 20       # a picture it takes leaves this much room on the card
FRIEND_BUBBLE = (220, 165)       # a picture in the Bot page's conversation, at most
FRIEND_TIMEOUT = 180             # a big model asleep on the other computer can take a minute or more
FRIEND_KEEP = 60                 # lines of the conversation kept
FRIEND_LIMIT = 320               # characters of an answer: a few sentences fit the screen
FRIEND_ANSWER_MAX = 4_000_000    # bytes: more than this isn't Ollama answering
FRIEND_HELLO_AFTER = 1800        # opened after this long quiet: it says hello
FRIEND_HEAD = ("# Bot: a computer on your network running Ollama. On that computer Ollama has to\n"
               "# listen on the network (OLLAMA_HOST=0.0.0.0). Settings > Bot sets these too.\n")
FRIEND_PERSONA = ("You are a friendly little bot who lives on a small handheld screen: a Raspberry Pi "
                  "in a game-console case. Reply in one to three short sentences, as it has to fit on that "
                  "screen. Plain text: no emoji, no quotation marks, no markdown, no stage directions.")
FRIEND_LOOK = ("see", "look", "looking", "camera", "in front of you", "around you", "wearing", "holding",
               "room", "what is this", "what's this", "colour", "color")
FRIEND_TOPICS = ["weather", "weather", "time", "time", "anything", "anything", "coins", "playing"]
FRIEND_SIGHT = 4                 # ...and with a camera and a model that can see, this many of what it sees
# asked for a picture: "take a picture", "snap a quick pic of the garage", "grab a couple of photos",
# "get me a picture of the door", "send me a photo", "selfie!", and "another one" just after one
# (not "take a look at this picture", "did you take my picture down", "I'll send you a photo",
# "please don't take my picture", "why did you take that picture?")
FRIEND_SNAP_WHAT = r"(?:picture|photo|pic|snapshot|selfie|image|snap)s?"
FRIEND_SNAP_FILL = (r"(?:(?:a|an|another|one|more|me|us|the|this|that|my|our|your|some|few|couple|of|several|two|"
                    r"three|\d+|second|third|quick|new|fresh|live|current|latest|nice|good|better|clear|clearer|proper|"
                    r"real|little|big|wide|close-up|closeup|group)\s+){0,4}")
FRIEND_SNAP = re.compile(
    r"\b(?:take|snap|shoot|capture|grab)\s+" + FRIEND_SNAP_FILL + FRIEND_SNAP_WHAT + r"\b(?!\s+(?:down|off|away|back)\b)"
    r"|\bsnap\s+(?:a|another|one|some)\s+(?:quick\s+)?shots?\b"
    r"|\b(?:get|send)\s+(?:me|us)\s+" + FRIEND_SNAP_FILL + FRIEND_SNAP_WHAT + r"\b"
    r"|\bphotograph\s+(?:me|us|it|this|that|the|my|our)\b"
    r"|^\W*(?:(?:a|another)\s+)?(?:selfie|picture|photo|pic|snapshot)(?:\s+please)?\W*$|^\W*say\s+cheese\W*$", re.I)
FRIEND_SNAP_NO = {"don't", "dont", "never", "not", "stop", "quit", "did", "didn't", "didnt", "does", "doesn't",
                  "won't", "wont", "shouldn't", "mustn't", "when", "whenever"}   # ...just before it: not asking
FRIEND_SNAP_AGAIN = re.compile(                  # just after a picture: "take another one", "one more", "try again"
    r"^\W*(?:(?:ok|okay|now|please|great|nice|cool|thanks)\W+)*(?:(?:take|snap|grab|get)\s+(?:me\s+)?)?"
    r"(?:another(?:\s+one)?|one\s+more|a\s+new\s+one|(?:try\s+|do\s+it\s+)?again)(?:\s+please)?\W*$", re.I)
FRIEND_ASKS = {
    "hello": "They just opened your screen. Greet them, and say one thing about right now.",
    "weather": "Say something about the weather.",
    "time": "Say something about the time of day.",
    "coins": "Say something about how the coins are doing.",
    "playing": "Say something about what's playing.",
    "anything": "Say one thing about right now.",
    "sight": ("Say something about what you see, in a sentence or two: who or what is there, or what's "
              "different from last time. Don't list everything."),
    "describe": ("They asked what you see. Describe it in two or three short sentences, the way you'd "
                 "say it out loud: who or what is there and what's going on. No lists."),
}
FRIEND_CHATTER = [("Every 30 min", "30"), ("Every hour", "60"), ("Never", "0")]
FRIEND_PAGES = ("friend", "f_models", "f_eyes", "f_voices")   # Settings > Bot and its lists
# its face follows the tone of what it said: PiE-ink's faces and words
FRIEND_FACES = {"happy": "(◕‿◕)", "pleased": "(•‿‿•)", "cool": "(⌐■_■)", "curious": "(☉_☉)",
                "sorry": "(╥_╥)", "worried": "(°▃▃°)", "sleepy": "(⇀‿‿↼)", "thinking": "(•_•)",
                "plain": "(•‿•)", "surprised": "(⊙o⊙)"}
FRIEND_GOOD = ("glad", "lovely", "great", "nice", "good", "happy", "yes", "sure", "thanks", "thank",
               "wonderful", "excellent", "perfect", "enjoy", "fun", "delight", "warm", "sunny", "well",
               "finally", "clear", "bright", "ready", "cheer", "love", "best", "better")
FRIEND_BAD = ("cold", "wet", "grim", "dull", "miserable", "tired", "bad", "wrong", "trouble", "problem",
              "miss", "late", "busy", "stuck", "dark", "grey", "gray")
FRIEND_SORRY = ("sorry", "afraid", "unfortunately", "sadly", "can't", "cannot", "don't know", "no idea")
FRIEND_SLEEPY = ("sleep", "bed", "dream", "yawn", "goodnight", "good night", "nap")
FRIEND_THINK = re.compile(r"<think>.*?</think>|<thinking>.*?</thinking>", re.S | re.I)


def friend_face(text, kind="", busy=False):
    """(face, mood) for what it last said: good and gloomy words weighed against each other."""
    low = (text or "").lower()
    if busy:
        mood = "thinking"
    elif kind == "error":
        mood = "sorry"
    elif not low:
        mood = "plain"
    else:
        words = set(re.findall(r"[a-z']+", low))

        def has(ws):
            return any((w in low) if " " in w else (w in words) for w in ws)
        score = sum(w in words for w in FRIEND_GOOD) - sum(w in words for w in FRIEND_BAD)
        if has(FRIEND_SORRY):
            mood = "sorry"
        elif has(FRIEND_SLEEPY):
            mood = "sleepy"
        elif low.rstrip().endswith("?"):
            mood = "curious"
        elif score >= 2 or ("!" in low and score >= 1):
            mood = "cool"
        elif score >= 1:
            mood = "happy"
        elif score <= -2:
            mood = "worried"
        elif kind == "chat":
            mood = "pleased"
        else:
            mood = "plain"
    return FRIEND_FACES[mood], mood


def friend_wants_eyes(text):
    """Does this sound like a question about what's in front of the camera?"""
    low = (text or "").lower()
    words = set(re.findall(r"[a-z']+", low))
    return any((w in low) if " " in w else (w in words) for w in FRIEND_LOOK)


def friend_wants_photo(text):
    """Does this ask for a picture to be taken? (Not when it says not to, or asks about one taken.)"""
    low = (text or "").lower().replace("\u2019", "'")
    for m in FRIEND_SNAP.finditer(low):
        said = re.split(r"[.,!?;:]", low[:m.start()])[-1]          # what comes just before it, in that sentence
        said = re.sub(r"\b(?:don'?t|wouldn'?t)\s+mind\b", " ", said)
        if re.search(r"\bwhy\s+(?:don'?t\s+you|not)\s*$", said):    # a suggestion: "why don't you take one?"
            return True
        words = re.findall(r"[a-z0-9']+", said)[-4:]
        if FRIEND_SNAP_NO.intersection(words) or words[-2:] in (["do", "you"], ["can", "it"]):
            continue
        return True
    return False


def read_own_bytes(path, limit):
    """A file of yours, read whole (this runs as root): only a plain file you could read yourself,
    no bigger than limit."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with open(fd, "rb") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or \
                (st.st_uid != os.stat(home_dir()).st_uid and not st.st_mode & stat.S_IROTH):
            raise PermissionError(f"{os.path.basename(path)} isn't a file of yours")
        if st.st_size > limit:
            raise ValueError("That picture is too big")
        return f.read(limit + 1)


def friend_image(src):
    """A picture for the bot, from its bytes or a file of yours: upright, in colour, no bigger than a
    model needs. ValueError when it can't be opened."""
    import warnings
    from PIL import Image, ImageOps
    try:
        data = read_own_bytes(src, FRIEND_PIC_BYTES) if isinstance(src, str) else src
        with warnings.catch_warnings():               # (its size is looked at here, before it's opened)
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data or b""), formats=FRIEND_PIC_KINDS)
        if im.width * im.height > FRIEND_PIC_PIXELS.get(im.format, FRIEND_PIC_OTHER):
            raise ValueError("That picture is too big")
        k = FRIEND_SEE_SIZE * 2 / max(im.size)
        if k < 1:                                       # (a JPEG opens smaller, quickly: a long one too)
            im.draft("RGB", (max(1, int(im.width * k)), max(1, int(im.height * k))))
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode == "PA" else "RGB")
        im.thumbnail((FRIEND_SEE_SIZE, FRIEND_SEE_SIZE))   # small first, then the rest
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA"):                   # see-through parts on white
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im.convert("RGBA"), mask=im.convert("RGBA").getchannel("A"))
            im = flat
        return im.convert("RGB") if im.mode != "RGB" else im
    except Exception as ex:                         # (not a picture, or a broken one)
        if isinstance(ex, ValueError) and str(ex).startswith("That picture"):
            raise
        raise ValueError("That picture can't be opened")


def friend_tidy(text, limit=FRIEND_LIMIT):
    """An answer made fit for the screen: no reasoning, no markdown, no quotes, one paragraph."""
    text = FRIEND_THINK.sub(" ", text or "")
    text = re.sub(r"^\s*<think>.*", "", text, flags=re.S | re.I).strip()
    for junk in ("```", "**", "*", "__", "#"):
        text = text.replace(junk, "")
    line = " ".join(ln.strip() for ln in text.splitlines() if ln.strip()).strip('"“”\' ')
    if len(line) > limit:
        line = line[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return line


def ollama_url(server):
    """http://address:11434 from what was typed: an address or a name, a port or not. Only the
    machine and the port are kept: Ollama's calls are always at the top."""
    t = (server or "").strip()
    if not t:
        return ""
    if not t.startswith(("http://", "https://")):
        t = "http://" + t
    try:
        u = urllib.parse.urlsplit(t)
        host, port = u.hostname, u.port
    except ValueError:
        return ""
    if not host:
        return ""
    return f"{u.scheme}://{f'[{host}]' if ':' in host else host}:{port or 11434}"


class OllamaError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


class CantSee(ValueError):
    """The model was shown a picture, and can't look at pictures."""

    def __init__(self, model):
        super().__init__(f"{model} can't look at pictures. Choose a model that can see in Settings > Bot")
        self.model = model


def ollama_call(server, path, body=None, timeout=FRIEND_TIMEOUT):
    url = ollama_url(server)
    if not url:
        raise ValueError("That isn't an address. Try 192.168.1.20")
    where = url.split("://", 1)[-1]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json", **UA})
    try:
        with OLLAMA_OPENER.open(req, timeout=timeout) as r:
            got = json.loads(read_capped(r, FRIEND_ANSWER_MAX, time.monotonic() + timeout) or b"{}")
        if not isinstance(got, dict):
            raise ValueError("not Ollama")
        return got
    except urllib.error.HTTPError as e:
        try:
            detail = clean_name(json.loads(e.read(65536) or b"{}").get("error"), 200)
        except (ValueError, OSError, AttributeError):
            detail = ""
        raise OllamaError(e.code, detail or f"Ollama said {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason):
            raise ValueError(f"No answer from {where} in {timeout} s. A big model can take longer")
        raise ValueError(f"Can't reach {where}. Is Ollama on there, and listening on the network?")


def ollama_sees(server, model, timeout=6):
    """True when Ollama says the model can see, False when it says it can't, None when it doesn't
    say (an older Ollama)."""
    got = ollama_call(server, "/api/show", {"model": model, "name": model}, timeout=timeout)
    caps = got.get("capabilities")
    return ("vision" in caps) if isinstance(caps, list) else None


def ollama_models(server, timeout=6):
    got = ollama_call(server, "/api/tags", timeout=timeout)
    return sorted({m.get("name", "") for m in got.get("models", []) if isinstance(m, dict) and m.get("name")})


def ollama_generate(server, model, system, prompt, images=None, timeout=FRIEND_TIMEOUT):
    """One answer, the same way PiE-ink asks: no reasoning pass, kept warm for the next one."""
    body = {"model": model, "prompt": prompt, "system": system, "stream": False, "think": False,
            "keep_alive": "30m", "options": {"temperature": 0.8, "num_predict": 300}}
    if images:
        body["images"] = images

    def ask():
        try:
            return ollama_call(server, "/api/generate", body, timeout)
        except OllamaError as e:
            low = e.detail.lower()
            if e.code == 400 and "think" in low and "think" in body:
                raise                                 # (asked again, below)
            if e.code == 404:
                raise ValueError(f"That computer doesn't have {model}. Pick another in Settings > Bot")
            if images and any(w in low for w in ("image", "vision", "multimodal")):
                raise CantSee(model)
            raise
    try:
        out = ask()
    except OllamaError as e:
        if not (e.code == 400 and "think" in e.detail.lower()):
            raise
        body.pop("think", None)                       # an older Ollama, or a model that doesn't think
        out = ask()
    text = friend_tidy(out.get("response", ""))
    if text:
        return text
    if (out.get("thinking") or "").strip():          # it spent the whole answer thinking: again, plainly
        body.pop("think", None)
        body["options"] = dict(body["options"], num_predict=-1)
        body["prompt"] = prompt + "\n\nAnswer directly. Do not show your reasoning."
        text = friend_tidy(ask().get("response", ""))
        if text:
            return text
        raise ValueError(f"{model} only gave its reasoning. Try another model")
    raise ValueError(f"{model} said nothing")


def edit_config(name, updates, head="", was=""):
    """'key = value' lines in a settings file changed or added; the rest kept. A file that isn't
    there yet starts from `was` (its earlier name), if that one is."""
    path = settings_file(name)
    updates = {k: clean_name(v, 400) for k, v in updates.items()}
    try:
        lines = read_own_text(path).splitlines()
    except FileNotFoundError:
        try:
            lines = read_own_text(settings_file(was)).splitlines() if was else None
        except FileNotFoundError:
            lines = None
        if lines is not None:                          # its own header, rather than the old one's
            while lines and lines[0].lstrip().startswith("#"):
                lines.pop(0)
            lines = (head.rstrip("\n").split("\n") if head else []) + lines
        else:
            lines = head.rstrip("\n").split("\n") if head else []
    done, out = set(), []
    for line in lines:
        k, eq, _ = line.partition("=")
        key = k.strip().lower()
        if eq and not line.strip().startswith("#") and key in updates:
            if key not in done:
                out.append(f"{key} = {updates[key]}")
                done.add(key)
            continue
        out.append(line)
    out += [f"{k} = {v}" for k, v in updates.items() if k not in done]
    return write_setting(name, "\n".join(out).rstrip("\n") + "\n")


class Friend:
    """The bot: its settings (bot.txt), what it knows right now (from media mode),
    and the conversation, kept on disk. One answer at a time, asked for in the background."""

    def __init__(self):
        self.conf = {}
        self.log = []                # [{"who": "you"/"friend", "text", "t", "kind": "chat"/"remark"/"error"}]
        self.busy = False
        self.models, self.models_at, self.models_status = [], "", ""
        self.on_change = lambda: None
        self.facts = lambda: []      # lines of what's true right now
        self.look = lambda text="": (None, "there's no camera")   # (a picture's bytes, whose) or (None, why not)
        self.snap = self.no_camera   # a picture taken: (where it's saved, its bytes, whose) or ValueError
        self.on_reply = lambda text: None
        self.doing = ""              # what it's busy with: "Taking a picture…", "Looking…"
        self.vision = {}             # model -> it can see (True / False), as Ollama said, or as it went
        self.vision_asked = {}       # model -> when Ollama was last asked
        self.lock = threading.Lock()
        self.load_log()

    def load(self, patterns):
        if not any(glob.glob(p) for p in patterns):        # not moved over yet: its earlier name
            patterns = [os.path.join(os.path.dirname(p), "friend.txt") for p in patterns]
        self.conf = read_config(patterns)

    @property
    def server(self):
        return (self.conf.get("server") or "").strip()

    @property
    def model(self):
        return (self.conf.get("model") or "").strip()

    @property
    def eyes(self):
        return (self.conf.get("eyes") or "").strip()

    @property
    def name(self):
        return (self.conf.get("name") or "").strip()[:40]

    def ready(self):
        return bool(self.server and self.model)

    def chatter(self):
        """Minutes between remarks of its own; 0: never."""
        v = (self.conf.get("chatter") or "30").strip().lower()
        if v in ("never", "off", "no"):
            return 0
        try:
            n = float(v)
        except ValueError:
            return 30
        if n != n or abs(n) == float("inf"):          # (nan, inf)
            return 30
        return int(max(0, min(1440, n)))

    def chatter_text(self):
        n = self.chatter()
        return next((t for t, v in FRIEND_CHATTER if int(v) == n), f"Every {n} min")

    # the conversation, kept between start-ups
    def load_log(self):
        try:
            with open(FRIEND_LOG) as f:
                got = json.load(f)
            self.log = [x for x in got if isinstance(x, dict) and (x.get("text") or x.get("pic"))][-FRIEND_KEEP:]
        except (OSError, ValueError, TypeError):
            self.log = []

    def save_log(self):
        try:
            os.makedirs(os.path.dirname(FRIEND_LOG), exist_ok=True)
            tmp = FRIEND_LOG + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.log[-FRIEND_KEEP:], f)
            os.replace(tmp, FRIEND_LOG)
        except OSError as ex:
            print(f"couldn't keep the conversation: {ex}", flush=True)
        keep = {x.get("pic") for x in list(self.log)}
        try:
            with os.scandir(FRIEND_PICS) as it:            # pictures no longer in it go (not one just made)
                for en in it:
                    if en.name.endswith(".jpg") and en.name[:-4] not in keep and \
                            time.time() - en.stat().st_mtime > 60:
                        os.remove(en.path)
        except OSError:
            pass

    def add(self, who, text, kind, **more):
        """A line of the conversation; more: pic (a picture kept with it), photo (where the picture
        is in Photos), seen (the camera it looked through)."""
        with self.lock:
            self.log.append(dict({"who": who, "text": text, "t": time.time(), "kind": kind},
                                 **{k: v for k, v in more.items() if v}))
            self.log = self.log[-FRIEND_KEEP:]
        self.save_log()
        self.on_change()

    @staticmethod
    def no_camera(text=""):
        raise ValueError("there's no camera")

    # pictures in the conversation
    def keep_picture(self, im):
        """A small copy of a picture, kept with the conversation: its id."""
        os.makedirs(FRIEND_PICS, mode=0o700, exist_ok=True)
        pid = uuid.uuid4().hex[:16]
        small = im.copy()
        small.thumbnail((FRIEND_PIC_SIZE, FRIEND_PIC_SIZE))
        path = os.path.join(FRIEND_PICS, pid + ".jpg")
        small.save(path + ".part", "JPEG", quality=82)
        os.replace(path + ".part", path)
        return pid

    @staticmethod
    def picture_bytes(pid):
        """One of the conversation's pictures, as JPEG: None when there's no such picture."""
        if not re.fullmatch(r"[0-9a-f]{16}", str(pid or "")):
            return None
        try:
            with open(os.path.join(FRIEND_PICS, pid + ".jpg"), "rb") as f:
                return f.read(FRIEND_PIC_BYTES)
        except OSError:
            return None

    @staticmethod
    def for_model(im):
        """A picture as a model is shown it: base64 JPEG."""
        import base64
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()

    def sees(self):
        """It can look at pictures: a model for its eyes, or one Ollama says can see (and neither
        found it can't)."""
        model = self.eyes or self.model
        if self.vision.get(model) is False:
            return False
        return bool(self.eyes) or self.vision.get(model) is True

    def check_vision(self):
        """Whether the model it looks with can see, asked of Ollama in the background (once in a while)."""
        model, server = self.eyes or self.model, self.server
        if not (model and server) or model in self.vision \
                or time.time() - self.vision_asked.get(model, 0) < 600:
            return
        self.vision_asked[model] = time.time()

        def job():
            try:
                got = ollama_sees(server, model)
            except Exception:
                return                                  # (not now: asked again in a while)
            if got is not None:
                self.vision[model] = got
                self.on_change()
        threading.Thread(target=job, daemon=True, name="friend-vision").start()

    def clear(self):
        with self.lock:
            self.log = []
        self.save_log()
        self.on_change()

    def last_said(self):
        return self.log[-1]["t"] if self.log else 0.0

    def face(self):
        last = next((x for x in reversed(self.log) if x["who"] == "friend"), None)
        return friend_face(last["text"] if last else "", last["kind"] if last else "", self.busy)

    # asking it
    def start(self):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        self.on_change()
        return True

    def say(self, text, picture=None):
        """You said something (and sent a picture: a file of yours, perhaps); it answers in the
        background. False while it's on the last one."""
        text = " ".join((text or "").split())[:400]
        if not (text or picture) or not self.start():
            return False
        if picture is None:
            self.add("you", text, "chat")
        else:
            self.doing = "Looking…"                    # (your line comes once the picture is open)
        threading.Thread(target=self.job, args=(text, None, picture), daemon=True, name="friend").start()
        return True

    def remark(self, topic="anything"):
        """Something of its own, about right now."""
        if not self.ready() or not self.start():
            return False
        threading.Thread(target=self.job, args=(None, topic), daemon=True, name="friend").start()
        return True

    def describe(self, look, done=lambda text, error: None):
        """It looks through the camera you chose and says what it sees (the Camera tab's SELECT, the
        web page's Describe): look() gives (a JPEG, the camera) or (None, why not), and done(what it
        said, or None; why it couldn't, or None) comes after. False while it's on the last one."""
        if not self.start():
            return False
        self.doing = "Looking…"
        threading.Thread(target=self.describe_job, args=(look, done), daemon=True, name="friend").start()
        return True

    def describe_job(self, look, done):
        text, error = None, None
        try:
            if not self.server:
                raise ValueError("I'm not set up yet. Put your Ollama computer in Settings > Bot")
            if not self.model:
                raise ValueError("Pick a model for me in Settings > Bot")
            model = self.eyes or self.model
            if self.vision.get(model) is False:
                raise CantSee(model)
            got, note = look()
            if not got:
                raise ValueError(f"I can't see anything: {note}")
            try:
                im = friend_image(got)
            except ValueError:
                raise ValueError("I can't see anything: the camera's picture was broken")
            pid = self.keep_picture(im)
            lines = []
            try:
                lines += list(self.facts())
            except Exception as ex:
                print(f"the bot couldn't look around: {ex!r}", flush=True)
            lines.append(f"The attached picture is what the camera ({note}) sees right now.")
            text = ollama_generate(self.server, model, self.system(),
                                   "\n".join(lines) + "\n\n" + FRIEND_ASKS["describe"], [self.for_model(im)])
            self.vision.setdefault(model, True)
            self.add("friend", text, "remark", pic=pid, seen=note)
        except CantSee as ex:
            self.vision[ex.model] = False
            text, error = None, str(ex)[:200]
            self.add("friend", error, "error")
        except Exception as ex:
            text, error = None, str(ex)[:200] or "That didn't work"
            self.add("friend", error, "error")
        finally:
            with self.lock:
                self.busy = False
                self.doing = ""
            self.on_change()
        try:
            done(text, error)
        except Exception as ex:
            print(f"after the bot looked: {ex!r}", flush=True)

    def job(self, message, topic, picture=None):
        try:
            sent = None
            if picture is not None:                    # your picture: in the conversation first
                try:
                    im = friend_image(picture)
                except (ValueError, OSError) as ex:
                    if message:
                        self.add("you", message, "chat")
                    raise ValueError(str(ex) if isinstance(ex, ValueError) else "That picture can't be opened")
                pid = self.keep_picture(im)
                self.add("you", message, "chat", pic=pid, photo=picture)
                sent = self.for_model(im)
            if not self.server:
                raise ValueError("I'm not set up yet. Put your Ollama computer in Settings > Bot")
            if not self.model:
                raise ValueError("Pick a model for me in Settings > Bot")
            if message and picture is None and (friend_wants_photo(message) or
                                                 self.after_photo() and FRIEND_SNAP_AGAIN.search(message)):
                return self.photo(message)
            prompt, images, seen = self.prompt(message, topic, sent)
            model = self.eyes if images and self.eyes else self.model
            self.doing = "Thinking…"
            self.on_change()
            text = ollama_generate(self.server, model, self.system(), prompt, images)
            self.add("friend", text, "chat" if message or sent else "remark",
                     pic=seen[0] if seen else None, seen=seen[1] if seen else None)
            self.on_reply(text)
        except CantSee as ex:
            self.vision[ex.model] = False
            self.add("friend", str(ex)[:200], "error")
        except Exception as ex:
            self.add("friend", str(ex)[:200] or "That didn't work", "error")
        finally:
            with self.lock:
                self.busy = False
                self.doing = ""
            self.on_change()

    def after_photo(self):
        """The last thing it said was a picture it took (or why it couldn't take one)."""
        last = next((x for x in reversed(self.log) if x["who"] == "friend"), None)
        return bool(last) and (last.get("kind") == "photo" or last.get("kind") == "error"
                               and last.get("text", "").startswith("I couldn't take a picture"))

    def photo(self, message):
        """They asked for a picture: the camera takes one (into Photos too), and it's shown here,
        with a word on it from a model that can see."""
        self.doing = "Taking a picture…"
        self.on_change()
        try:
            path, data, cam = self.snap(message)
            im = friend_image(data)
        except Exception as ex:
            self.add("friend", f"I couldn't take a picture: {str(ex)[:150] or 'no answer'}", "error")
            return
        pid = self.keep_picture(im)
        text = f"Here's the picture from {cam}. It's in Photos too."
        model = self.eyes or self.model
        if self.vision.get(model) is not False:
            self.doing = "Looking…"
            self.on_change()
            lines = self.context(message)
            lines.append(f"{self.name} now says: {message}" if self.name else f"They now say: {message}")
            lines.append(f"So you took the attached picture with the camera ({cam}). It's saved in Photos.")
            try:
                text = ollama_generate(self.server, model, self.system(), "\n".join(lines) + "\n\nTell them you "
                                       "took it, and say something about what's in it, answering what they asked.",
                                       [self.for_model(im)])
                self.vision.setdefault(model, True)
            except CantSee:
                self.vision[model] = False
            except Exception as ex:
                print(f"the bot couldn't look at the picture: {ex}", flush=True)
        self.add("friend", text, "photo", pic=pid, photo=path, seen=cam)
        self.on_reply(text)

    def system(self):
        persona = (self.conf.get("persona") or "").strip() or FRIEND_PERSONA
        return persona + (f" The person you live with is called {self.name}." if self.name else "")

    def context(self, message):
        """What's true right now, and the last few lines said."""
        lines = []
        try:
            lines += list(self.facts())
        except Exception as ex:
            print(f"the bot couldn't look around: {ex!r}", flush=True)
        said = [x for x in self.log if x.get("kind") in ("chat", "remark", "photo")]
        if message is not None and said and said[-1]["who"] == "you":
            said = said[:-1]                          # (what you just said, or sent, goes last)
        if said[-6:]:
            lines.append("The conversation so far:")
            for x in said[-6:]:
                what = x.get("text") or ""
                if x.get("pic"):
                    what = ("[sent a picture] " if x["who"] == "you" else
                            "[took a picture] " if x.get("kind") == "photo" else "[looking through the camera] ") + what
                lines.append(("  They said: " if x["who"] == "you" else "  You said: ") + what[:200])
        return lines

    def look_now(self, text=""):
        """A picture from the camera for a model to look at: ((its id here, the camera), base64) or
        (None, why not)."""
        got, note = self.look(text)
        if not got:
            return None, note
        try:
            im = friend_image(got)
        except ValueError:
            return None, "the camera's picture was broken"
        return ((self.keep_picture(im), note), self.for_model(im)), note

    def prompt(self, message, topic, sent=None):
        """What's true right now, the last few lines said, and what to answer; the pictures it's
        shown; and the one it looked at (its id, the camera), if it did."""
        lines = self.context(message if message or sent else None)
        images, seen = None, None
        who = self.name or "They"
        if sent:
            images = [sent]
            lines.append(f"{who} sent you the attached picture.")
            lines.append(f"{who} now say{'s' if self.name else ''}: {message}" if message else
                         "They didn't say anything with it.")
            ask = ("Reply to them about the picture, carrying on from what was already said." if message
                   else "Say something about the picture.")
        elif message:
            if friend_wants_eyes(message):
                got, note = self.look_now(message)
                if got:
                    seen, images = got[0], [got[1]]
                    lines.append(f"The attached picture is what the camera ({note}) sees right now.")
                else:
                    lines.append(f"You can't see anything right now ({note}); say so if they asked.")
            lines.append(f"{self.name} now says: {message}" if self.name else f"They now say: {message}")
            ask = "Reply to them, carrying on from what was already said."
        else:
            if topic == "sight":
                got, note = self.look_now()
                if got:
                    seen, images = got[0], [got[1]]
                    lines.append(f"The attached picture is what the camera ({note}) sees right now.")
                    last = next((x for x in reversed(self.log) if x.get("seen") and x["who"] == "friend"), None)
                    if last and time.time() - last["t"] < 6 * 3600:
                        mins = max(1, int((time.time() - last["t"]) // 60))
                        lines.append(f"When you last looked, {mins} minutes ago, you said: {last['text'][:200]}")
                else:
                    topic = "anything"                 # nothing to see: something else, then
            ask = FRIEND_ASKS.get(topic, FRIEND_ASKS["anything"])
        return "\n".join(lines) + "\n\n" + ask, images, seen

    def fetch_models(self, server=None):
        """The models on the Ollama computer, asked for in the background."""
        server = server or self.server
        if not server:
            self.models, self.models_status = [], "Set the computer first"
            self.on_change()
            return
        where = ollama_url(server).split("://", 1)[-1]
        self.models_status = f"Asking {where}…"
        self.on_change()

        def job():
            try:
                ms = ollama_models(server)
                self.models, self.models_at = ms, server
                self.models_status = (f"{len(ms)} model{'s' if len(ms) != 1 else ''} on {where}" if ms
                                      else f"No models on {where} yet (ollama pull one there)")
            except Exception as ex:
                self.models, self.models_at, self.models_status = [], "", str(ex)[:90]
            self.on_change()
        threading.Thread(target=job, daemon=True, name="friend-models").start()


def in_home(path):
    """True for a file inside your home folder: the only place pictures get deleted
    or written next to (this runs as root)."""
    home = os.path.realpath(home_dir())
    return os.path.realpath(path).startswith(home + os.sep)


def pictures_dir():
    home = home_dir()
    folder = os.path.join(home, "Pictures")
    if not os.path.isdir(folder):
        st = os.stat(home)
        os.makedirs(folder, exist_ok=True)
        os.chown(folder, st.st_uid, st.st_gid)
    return folder


def write_new(folder, stem, ext, data):
    """A new file <stem><ext> in folder (stem-2, stem-3... if taken), owned like the
    folder. Written under a hidden name first, so the Photos tab never sees half a file."""
    st = os.stat(folder)
    path, n = os.path.join(folder, stem + ext), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f"{stem}-{n}{ext}"), n + 1
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".part")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def save_picture(data, ext=".jpg"):
    """Keeps a picture from the camera in ~/Pictures as camera-<date>-<time>.jpg."""
    return write_new(pictures_dir(), time.strftime("camera-%Y-%m-%d-%H%M%S"), ext, data)


# ---- photo filters: the same looks as PiE-ink's camera -----------------------------
FILTERS = [("none", "Original"), ("bw", "B&W"), ("sepia", "Sepia"), ("warm", "Warm"),
           ("vivid", "Vivid"), ("blue", "Blue"), ("sketch", "Sketch"), ("trace", "Edge trace"),
           ("comic", "Comic"), ("pixel", "Pixel"), ("eink", "E-ink")]
FILTER_CSS = {      # colour filters: the CSS filter functions, in order
    "none": [], "bw": [("grayscale", 1), ("contrast", 1.15)],
    "sepia": [("sepia", 0.9), ("contrast", 1.05)],
    "warm": [("sepia", 0.3), ("saturate", 1.35), ("contrast", 1.05)],
    "vivid": [("saturate", 1.8), ("contrast", 1.15)],
    "blue": [("grayscale", 1), ("sepia", 0.9), ("hue-rotate", 175), ("saturate", 1.6)],
}


def _matrix(fn, v):
    """One CSS filter function as a 3x3 matrix and an offset (0-255)."""
    import math
    if fn in ("grayscale", "sepia"):
        a = 1 - max(0.0, min(1.0, v))
        if fn == "grayscale":
            return ((0.2126 + 0.7874 * a, 0.7152 - 0.7152 * a, 0.0722 - 0.0722 * a),
                    (0.2126 - 0.2126 * a, 0.7152 + 0.2848 * a, 0.0722 - 0.0722 * a),
                    (0.2126 - 0.2126 * a, 0.7152 - 0.7152 * a, 0.0722 + 0.9278 * a)), 0.0
        return ((0.393 + 0.607 * a, 0.769 - 0.769 * a, 0.189 - 0.189 * a),
                (0.349 - 0.349 * a, 0.686 + 0.314 * a, 0.168 - 0.168 * a),
                (0.272 - 0.272 * a, 0.534 - 0.534 * a, 0.131 + 0.869 * a)), 0.0
    if fn == "saturate":
        s = max(0.0, v)
        return ((0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s),
                (0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s),
                (0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s)), 0.0
    if fn == "hue-rotate":
        c, s = math.cos(math.radians(v)), math.sin(math.radians(v))
        return ((0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928),
                (0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283),
                (0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072)), 0.0
    if fn == "contrast":
        return ((v, 0, 0), (0, v, 0), (0, 0, v)), 127.5 * (1 - v)
    return ((1, 0, 0), (0, 1, 0), (0, 0, 1)), 0.0


def _working(img, most=960):
    """Drawn filters work at a modest size (quick on a Pi Zero), then go back up."""
    from PIL import Image
    if img.width <= most:
        return img, None
    return img.resize((most, max(1, round(img.height * most / img.width))), Image.LANCZOS), img.size


def _sketch(img):
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
    work, size = _working(img)
    g = work.convert("L")
    blur = g.filter(ImageFilter.GaussianBlur(max(2.0, g.width / 80)))
    a, b = np.asarray(g, dtype=np.float32), np.asarray(blur, dtype=np.float32)
    dodge = np.clip(a * 255.0 / np.maximum(b, 1.0), 0, 255)          # pencil on paper
    out = Image.fromarray((255 - np.clip((255 - dodge) * 1.8, 0, 255)).astype("uint8"), "L")
    out = ImageOps.colorize(out, black=(46, 42, 50), white=(248, 246, 238))
    return out.resize(size, Image.LANCZOS) if size else out


def _trace(img):
    import numpy as np
    from PIL import Image, ImageFilter
    work, size = _working(img)
    g = work.convert("L").filter(ImageFilter.GaussianBlur(max(0.8, work.width / 700)))
    q = np.pad(np.asarray(g, dtype=np.float32), 1, mode="edge")
    gx = (q[:-2, 2:] + 2 * q[1:-1, 2:] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[1:-1, :-2] + q[2:, :-2])
    gy = (q[2:, :-2] + 2 * q[2:, 1:-1] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[:-2, 1:-1] + q[:-2, 2:])
    mag = np.hypot(gx, gy)
    top = max(float(np.percentile(mag, 98)), 90.0)
    out = Image.fromarray((np.clip(mag / top, 0, 1) ** 1.3 * 255).astype("uint8"), "L").convert("RGB")
    return out.resize(size, Image.LANCZOS) if size else out


def _comic(img):
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
    work, size = _working(img, most=800)
    smooth = work.filter(ImageFilter.MedianFilter(5))
    g = smooth.convert("L")
    around = g.filter(ImageFilter.BoxBlur(max(3, work.width // 110)))
    ink = ImageChops.subtract(around, g).point(lambda v: 0 if v > 10 else 255)
    ink = ink.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    base = ImageEnhance.Color(ImageOps.posterize(smooth, 3)).enhance(1.4)
    out = ImageChops.multiply(base, Image.merge("RGB", (ink, ink, ink)))
    return out.resize(size, Image.LANCZOS) if size else out


def _blocks(img, across):
    w, h = img.size
    block = max(1, round(w / max(8, min(across, w))))
    across = max(1, w // block)
    return block, across, max(1, round(h * across / w))


def _pixel(img, across=96, colours=24):
    from PIL import Image
    block, across, down = _blocks(img, across)
    small = img.resize((across, down), Image.BOX)
    try:
        small = small.quantize(colors=colours, dither=getattr(getattr(Image, "Dither", Image), "NONE", 0))
    except (TypeError, ValueError):
        small = small.quantize(colors=colours)
    return small.convert("RGB").resize((across * block, down * block), Image.NEAREST)


def _eink(img, across=400):
    from PIL import Image, ImageOps
    block, across, down = _blocks(img, across)
    g = ImageOps.autocontrast(img.convert("L").resize((across, down), Image.LANCZOS), cutoff=1)
    dots = g.convert("1", dither=Image.FLOYDSTEINBERG).convert("L")
    dots = dots.resize((across * block, down * block), Image.NEAREST)
    return ImageOps.colorize(dots, black=(34, 34, 38), white=(226, 224, 216))


def apply_filter(img, fid):
    """The picture with a filter on (RGB). Small pictures (the preview) get the
    drawn filters scaled to match how they'll look on the full-size copy."""
    img = img.convert("RGB")
    drawn = {"sketch": _sketch, "trace": _trace, "comic": _comic, "pixel": _pixel, "eink": _eink}
    if fid in drawn:
        return drawn[fid](img)
    for fn, v in FILTER_CSS.get(fid, []):
        m, off = _matrix(fn, float(v))
        img = img.convert("RGB", (m[0][0], m[0][1], m[0][2], off,
                                  m[1][0], m[1][1], m[1][2], off,
                                  m[2][0], m[2][1], m[2][2], off))
    return img


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def price_text(p):
    p = _num(p, None)
    if p is None:
        return "—"
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    if p >= 0.01:
        return f"${p:,.4f}"
    return f"${p:.8f}"


def big_number(n):
    n = _num(n, None)
    if n is None:
        return "—"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= cut:
            return f"{n / cut:.1f}{suffix}"
    return str(int(n))


class Crypto:
    """Coin prices and charts from CoinGecko, fetched on a thread of its own and kept on
    disk — so the tab shows the last numbers it had, with their age, when there's no WiFi."""

    def __init__(self, pie=None):
        self.cfg = {}
        self.pie = pie                # PiE-ink on another Pi: asked first for what it has
        self.coins = [{"id": i, "symbol": s, "name": n} for i, s, n in CRYPTO_COINS]
        self.quotes, self.hist = {}, {}
        self.days = 1
        self.focus = None             # the card on screen: ("coin", id)
        self.force = False
        self.running = False
        self.last_call = 0.0
        self.backoff_until = 0.0
        self.on_change = lambda: None
        self.lock = threading.Lock()
        self.load_cache()

    # settings
    def load(self, patterns):
        self.cfg = read_config(patterns)
        ids = [c.strip().lower() for c in re.split(r"[,\s]+", self.cfg.get("coins", "")) if c.strip()]
        known = {i: (s, n) for i, s, n in CRYPTO_COINS}
        coins = []
        for cid in ids or [c[0] for c in CRYPTO_COINS]:
            q = (self.quotes.get(cid) or {}).get("d") or {}
            sym, name = known.get(cid, (cid[:5].upper(), cid.replace("-", " ").title()))
            coins.append({"id": cid, "symbol": q.get("symbol") or sym, "name": q.get("name") or name})
        self.coins = coins

    def cards(self):
        return [("coin", c["id"]) for c in self.coins]

    def coin(self, cid):
        return next((c for c in self.coins if c["id"] == cid), {"id": cid, "symbol": cid, "name": cid})

    # the disk copy
    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "crypto.json")

    def load_cache(self):
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            self.quotes, self.hist = c.get("quotes", {}), c.get("hist", {})
        except (OSError, ValueError):
            pass

    def save_cache(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with self.lock:
                data = json.dumps({"quotes": self.quotes, "hist": self.hist})
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    # fetching
    def get_json(self, url, gecko=False):
        if gecko:
            wait = self.last_call + CRYPTO_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.time()
        req = urllib.request.Request(url, headers=dict(UA, Accept="application/json"))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                          # too many calls: wait a minute
                self.backoff_until = time.time() + 60
            raise

    def fetch_quote(self, cid):
        q = urllib.parse.urlencode({"localization": "false", "tickers": "false",
                                    "community_data": "false", "developer_data": "false"})
        d = self.get_json(f"{COINGECKO}/coins/{urllib.parse.quote(cid)}?{q}", gecko=True)
        m = d.get("market_data", {})

        def usd(k):
            return (m.get(k) or {}).get("usd")
        price, ath = usd("current_price"), usd("ath")
        out = {"symbol": (d.get("symbol") or "").upper(), "name": d.get("name") or cid,
               "price": price, "ath": ath, "market_cap": usd("market_cap"),
               "rank": d.get("market_cap_rank"), "circulating_supply": m.get("circulating_supply"),
               "sentiment_up": d.get("sentiment_votes_up_percentage"),
               "high_24h": usd("high_24h"), "low_24h": usd("low_24h"),
               "change_24h": m.get("price_change_percentage_24h")}
        with self.lock:
            self.quotes[cid] = {"t": time.time(), "d": out}
        c = self.coin(cid)
        if c in self.coins:
            c["symbol"], c["name"] = out["symbol"] or c["symbol"], out["name"]

    def fetch_hist(self, cid, days):
        d = self.get_json(f"{COINGECKO}/coins/{urllib.parse.quote(cid)}/market_chart?"
                          + urllib.parse.urlencode({"vs_currency": "usd", "days": days}), gecko=True)
        with self.lock:
            self.hist[f"{cid}:{days}"] = {"t": time.time(), "v": [p[1] for p in d.get("prices", [])]}

    # what to fetch next: the card on screen first
    def stale(self, key, ttl):
        if time.time() < self.backoff_until:
            return False                               # CoinGecko said slow down
        e = self.quotes.get(key[1]) if key[0] == "quote" else self.hist.get(f"{key[1]}:{key[2]}")
        if ttl and e and time.time() - e.get("tried", 0) < 60:
            return False                               # failed a moment ago: give it a minute
        return not e or time.time() - e.get("t", 0) > ttl

    def next_job(self):
        jobs = []
        kind, what = self.focus or ("coin", self.coins[0]["id"] if self.coins else "")
        hist_ttl = 300 if self.days == 1 else 900
        if kind == "coin" and what:
            jobs += [(("quote", what), 0 if self.force else 300),
                     (("hist", what, self.days), 0 if self.force else hist_ttl)]
        self.force = False
        for c in self.coins:
            jobs += [(("quote", c["id"]), 300), (("hist", c["id"], self.days), hist_ttl)]
        return next(((key, ttl) for key, ttl in jobs if self.stale(key, ttl)), None)

    def from_pie(self, job, ttl):
        """PiE-ink's numbers for a job when it has them and they aren't too old (a little past their
        time is fine: it's asked again in a minute): taken when newer than what's here, or else its
        next ones are waited for, as PiE-ink is keeping them fresh. False: the internet is asked."""
        if self.pie is None:
            return False
        try:
            if job[0] == "quote":
                got, store, key = self.pie.quote(job[1]), self.quotes, job[1]
            else:
                got, store, key = self.pie.chart(job[1], job[2]), self.hist, f"{job[1]}:{job[2]}"
        except Exception:
            return False
        if not got:
            return False
        value, age = got
        now = time.time()
        if age >= (ttl * 1.5 if ttl else 60):
            return False                               # too old: the internet is asked
        held = store.get(key) or {}
        if now - age <= held.get("t", 0) + 1:          # what's here is as new as its: its next is coming
            if ttl:
                with self.lock:
                    store[key] = dict(held, tried=now)   # (asked again in a minute)
            return True
        entry = {"t": now - age, "pie": True}
        if job[0] == "quote":
            q = dict(value)
            c = self.coin(job[1])
            q["symbol"], q["name"] = q["symbol"] or c["symbol"], q["name"] or c["name"]
            entry["d"] = q
            if c in self.coins:
                c["symbol"], c["name"] = q["symbol"], q["name"]
        else:
            entry["v"] = value
        if age >= ttl:
            entry["tried"] = now                      # already due: PiE-ink is asked again in a minute
        with self.lock:
            store[key] = entry
        return True

    def start(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self.loop, daemon=True, name="crypto").start()

    def stop(self):
        self.running = False

    def loop(self):
        while self.running:
            got = self.next_job()
            if not got:
                time.sleep(1)
                continue
            job, ttl = got
            try:
                if self.from_pie(job, ttl):
                    pass                               # PiE-ink had it: the internet isn't asked
                elif job[0] == "quote":
                    self.fetch_quote(job[1])
                else:
                    self.fetch_hist(job[1], job[2])
                self.save_cache()
            except Exception:
                # keep the old numbers (and their age); try again in a minute
                with self.lock:
                    store = self.quotes if job[0] == "quote" else self.hist
                    key = job[1] if job[0] == "quote" else f"{job[1]}:{job[2]}"
                    store[key] = dict(store.get(key) or {}, tried=time.time())
                time.sleep(2)
            self.on_change()


# The TV's own buttons, by how its Home Assistant integration names them. Samsung,
# Android/Google TV, Roku and Apple TV take them through remote.send_command;
# LG webOS through webostv.button on the TV itself.
TV_KEYS = {
    "samsung": {"up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
                "ok": "KEY_ENTER", "back": "KEY_RETURN", "home": "KEY_HOME",
                "chup": "KEY_CHUP", "chdown": "KEY_CHDOWN", "last": "KEY_PRECH", "guide": "KEY_GUIDE",
                "enter": "KEY_ENTER", "dash": "KEY_PLUS100", **{str(n): f"KEY_{n}" for n in range(10)}},
    "android": {"up": "DPAD_UP", "down": "DPAD_DOWN", "left": "DPAD_LEFT", "right": "DPAD_RIGHT",
                "ok": "DPAD_CENTER", "back": "BACK", "home": "HOME",
                "chup": "CHANNEL_UP", "chdown": "CHANNEL_DOWN", "last": "LAST_CHANNEL", "guide": "GUIDE",
                "enter": "ENTER", "dash": "MINUS", **{str(n): str(n) for n in range(10)}},
    "roku": {"up": "up", "down": "down", "left": "left", "right": "right",
             "ok": "select", "back": "back", "home": "home",
             "chup": "channel_up", "chdown": "channel_down", "enter": "enter"},
    "apple": {"up": "up", "down": "down", "left": "left", "right": "right",
              "ok": "select", "back": "menu", "home": "home"},
    "lg": {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
           "ok": "ENTER", "back": "BACK", "home": "HOME",
           "chup": "CHANNELUP", "chdown": "CHANNELDOWN", "guide": "GUIDE", "enter": "ENTER", "dash": "DASH",
           **{str(n): str(n) for n in range(10)}},
}
# the number pad: (label, what it does)
TV_PAD = [[("1", "1"), ("2", "2"), ("3", "3"), ("CH +", "chup")],
          [("4", "4"), ("5", "5"), ("6", "6"), ("CH −", "chdown")],
          [("7", "7"), ("8", "8"), ("9", "9"), ("Last", "last")],
          [("–", "dash"), ("0", "0"), ("⌫", "del"), ("Guide", "guide")],
          [("Go to channel", "go")]]
TV_STYLE_WORDS = [({"samsung", "tizen", "frame"}, "samsung"), ({"roku"}, "roku"),
                  ({"apple", "appletv"}, "apple"), ({"lg", "webos"}, "lg"),
                  ({"android", "google", "shield", "chromecast", "bravia", "sony", "philips",
                    "hisense", "tcl", "fire", "firetv"}, "android")]


class HomeAssistant:
    """Your TV through Home Assistant's REST API and a long-lived access token:
    its state every few seconds, and the buttons pressed, one at a time, on a
    thread of its own. homeassistant.txt:
        url = homeassistant.local:8123
        token = <long-lived access token>
        tv = media_player.living_room_tv      (optional: found by itself)
        remote = remote.living_room_tv        (optional: found by itself)
        style = samsung                       (optional: samsung, android, roku, apple, lg)
    """

    def __init__(self):
        self.cfg = {}
        self.url = self.token = ""
        self.tv = self.remote = self.style = ""
        self.found = False
        self.loaded = None
        self.tvstate = {}
        self.error = None
        self.jobs = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.running = False
        self.on_change = lambda: None
        self.on_note = lambda text: None

    def load(self, patterns):
        self.cfg = read_config(patterns)
        url = self.cfg.get("url", "").strip().rstrip("/")
        if url.endswith("/api"):
            url = url[:-4]
        if url and "://" not in url:
            url = "http://" + url
        key = (url, self.cfg.get("token", "").strip(), self.cfg.get("tv", "").strip(),
               self.cfg.get("remote", "").strip(), self.cfg.get("style", "").strip().lower())
        if key != self.loaded:                         # new settings: find the TV again
            self.loaded = key
            self.url, self.token, self.tv, self.remote, self.style = key
            self.found, self.tvstate, self.error = False, {}, None

    @property
    def configured(self):
        return bool(self.url and self.token)

    @property
    def where(self):
        return self.url.split("://", 1)[-1]

    # talking to Home Assistant
    def call(self, method, path, body=None, timeout=8):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read()
        return json.loads(out) if out.strip() else None

    def why(self, e):
        if isinstance(e, urllib.error.HTTPError):
            if e.code == 401:
                return "Home Assistant didn't accept the token"
            try:
                body = e.read().decode("utf-8", "replace")
            except OSError:
                body = ""
            try:
                msg = json.loads(body).get("message")
            except (ValueError, AttributeError):
                msg = body.strip()[:80]
            return msg or f"Home Assistant said {e.code}"
        if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
            return f"Can't reach Home Assistant at {self.where}"
        return str(e) or "Something went wrong"

    def service(self, domain, name, **data):
        return self.call("POST", f"/api/services/{domain}/{name}", data)

    # finding the TV when the file doesn't say
    def discover(self):
        states = self.call("GET", "/api/states", timeout=15) or []
        ids = {st.get("entity_id"): st for st in states if isinstance(st, dict)}

        def words(st):
            text = (st.get("entity_id", "") + " " + str(st.get("attributes", {}).get("friendly_name", "")))
            return set(re.split(r"[^a-z0-9]+", text.lower()))
        if not self.tv:
            players = [st for k, st in ids.items() if k and k.startswith("media_player.")]
            tvs = ([st for st in players if st.get("attributes", {}).get("device_class") == "tv"]
                   or [st for st in players if words(st) & {"tv", "television", "samsung", "lg",
                                                            "bravia", "roku", "webos"}])
            if not tvs:
                raise ValueError("No TV in Home Assistant: put  tv = media_player.…  in the file")
            self.tv = tvs[0]["entity_id"]
        if not self.remote:
            same = "remote." + self.tv.split(".", 1)[1]
            remotes = [k for k in ids if k and k.startswith("remote.")]
            if same in ids:
                self.remote = same
            else:
                mine = words(ids.get(self.tv, {})) - {"media", "player", "tv", ""}
                near = [k for k in remotes if words(ids[k]) & mine]
                self.remote = (near or (remotes if len(remotes) == 1 else [""]))[0]
        if not self.style:
            seen = words(ids.get(self.tv, {})) | (words(ids[self.remote]) if self.remote in ids else set())
            self.style = next((style for keys, style in TV_STYLE_WORDS if seen & keys), "samsung")
        self.found = True

    def refresh(self):
        try:
            if not self.found:
                self.discover()
            st = self.call("GET", f"/api/states/{self.tv}")
            a = st.get("attributes", {})
            self.tvstate = {"state": st.get("state", ""), "name": a.get("friendly_name") or self.tv,
                            "volume": a.get("volume_level"), "muted": bool(a.get("is_volume_muted")),
                            "source": a.get("source"), "sources": list(a.get("source_list") or []),
                            "title": a.get("media_title"), "app": a.get("app_name")}
            self.error = None
        except urllib.error.HTTPError as e:
            if e.code == 404 and self.found and not self.loaded[2]:
                # the TV it found has gone (renamed in Home Assistant): look again
                _, _, self.tv, self.remote, self.style = self.loaded
                self.found = False
                self.error = "Looking for your TV again"
            else:
                self.error = (f"Home Assistant has no {self.tv}" if e.code == 404 and self.found
                              else self.why(e))
        except Exception as e:
            self.error = self.why(e)
        self.on_change()

    # the buttons
    def send(self, *job):
        with self.lock:
            if len(self.jobs) < 8:                    # held buttons don't pile up
                self.jobs.append(job)
        self.wake.set()

    def run_job(self, job):
        what = job[0]
        tv = {"entity_id": self.tv}
        if what == "key":
            self.press_key(job[1])
        elif what == "channel":
            number = job[1]
            try:                                       # Samsung, LG and Android TV take a number
                cid = int(number) if self.style == "android" else number
                self.service("media_player", "play_media", media_content_type="channel",
                             media_content_id=cid, **tv)
            except (urllib.error.HTTPError, ValueError):
                for ch in number:                      # otherwise press the digits, then enter
                    self.press_key("dash" if ch in "-." else ch)
                    time.sleep(0.15)
                self.press_key("enter")
            self.on_note(f"Channel {number}")
        elif what == "volume":
            self.service("media_player", "volume_up" if job[1] > 0 else "volume_down", **tv)
        elif what == "mute":
            self.service("media_player", "volume_mute", is_volume_muted=not self.tvstate.get("muted"), **tv)
        elif what == "play":
            self.service("media_player", "media_play_pause", **tv)
        elif what == "power":
            off = self.tvstate.get("state") in ("off", "standby", "unavailable", "")
            try:
                self.service("media_player", "turn_on" if off else "turn_off", **tv)
            except urllib.error.HTTPError as e:
                if off and e.code == 400:              # e.g. a Samsung without Wake-on-LAN set up
                    raise ValueError("Home Assistant can't turn this TV on")
                raise
            self.on_note("Turning the TV on" if off else "Turning the TV off")
        elif what == "source":
            self.service("media_player", "select_source", source=job[1], **tv)

    def press_key(self, name):
        tv = {"entity_id": self.tv}
        keys = TV_KEYS.get(self.style) or TV_KEYS["samsung"]
        if name not in keys:
            raise ValueError("This TV has no such button in Home Assistant")
        if self.style == "lg":
            self.service("webostv", "button", button=keys[name], **tv)
        elif self.remote:
            self.service("remote", "send_command", entity_id=self.remote, command=keys[name])
        else:
            raise ValueError("No remote for the buttons: add  remote = remote.…  to the file")

    # running while the TV Remote page is on screen
    def start(self):
        if self.running or not self.configured:
            return
        self.running = True
        threading.Thread(target=self.loop, daemon=True, name="home-assistant").start()

    def stop(self):
        self.running = False
        with self.lock:
            self.jobs.clear()
        self.wake.set()

    def loop(self):
        next_poll = 0.0
        while self.running:
            with self.lock:
                job = self.jobs.pop(0) if self.jobs else None
            if job:
                try:
                    if not self.found:
                        self.discover()
                    self.run_job(job)
                except Exception as e:
                    self.on_note(self.why(e) if not isinstance(e, ValueError) else str(e))
                next_poll = min(next_poll, time.monotonic() + 0.5)
                continue
            if time.monotonic() >= next_poll:
                self.refresh()
                next_poll = time.monotonic() + HA_POLL
            self.wake.wait(0.25)
            self.wake.clear()


class Plex:
    """Your Plex account: sign in with a code, find your server, browse and stream."""

    def __init__(self):
        self.cfg = {}
        self.pin = None
        self.load()

    def load(self):
        try:
            with open(PLEX_FILE) as f:
                self.cfg = json.load(f)
        except (OSError, ValueError):
            self.cfg = {}
        if not self.cfg.get("client"):
            self.cfg["client"] = uuid.uuid4().hex
            self.save()
        manual = read_config([settings_glob("plex.txt")])     # optional: server + token by hand
        if manual.get("server") and manual.get("token"):
            self.cfg.update(server=manual["server"].rstrip("/"), server_token=manual["token"],
                            server_name=manual.get("name", "Plex"))
            self.cfg.setdefault("token", manual["token"])

    def save(self):
        try:
            os.makedirs(os.path.dirname(PLEX_FILE), exist_ok=True)
            tmp = PLEX_FILE + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.cfg, f)
            os.replace(tmp, PLEX_FILE)
        except OSError:
            pass

    @property
    def signed_in(self):
        return bool(self.cfg.get("token"))

    @property
    def ready(self):
        return bool(self.cfg.get("server") and self.cfg.get("server_token"))

    @property
    def server_name(self):
        return self.cfg.get("server_name", "Plex")

    def headers(self, token=None):
        h = {"Accept": "application/json", "X-Plex-Product": PLEX_PRODUCT,
             "X-Plex-Version": "1.0", "X-Plex-Client-Identifier": self.cfg["client"],
             "X-Plex-Platform": "Linux", "X-Plex-Device": "Raspberry Pi",
             "X-Plex-Device-Name": socket.gethostname()}
        if token:
            h["X-Plex-Token"] = token
        return h

    def call(self, url, method="GET", token=None, timeout=10, raw=False):
        req = urllib.request.Request(url, method=method, headers=self.headers(token))
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        if raw:
            return body
        return json.loads(body) if body.strip() else {}

    # sign in with a code typed at plex.tv/link
    def start_pin(self):
        r = self.call("https://plex.tv/api/v2/pins", method="POST")
        self.pin = {"id": r["id"], "code": r["code"],
                    "until": time.monotonic() + int(r.get("expiresIn") or 900)}

    def check_pin(self):
        if not self.pin:
            return False
        r = self.call(f"https://plex.tv/api/v2/pins/{self.pin['id']}")
        if r.get("authToken"):
            self.cfg["token"] = r["authToken"]
            self.pin = None
            self.save()
            return True
        return False

    def find_server(self):
        """Pick your own server first, and the first connection that answers."""
        res = self.call("https://plex.tv/api/v2/resources?includeHttps=1&includeRelay=1",
                        token=self.cfg["token"])
        servers = [r for r in res if "server" in (r.get("provides") or "")]
        servers.sort(key=lambda r: not r.get("owned"))
        for srv in servers:
            token = srv.get("accessToken") or self.cfg["token"]
            conns = sorted(srv.get("connections") or [],
                           key=lambda c: (bool(c.get("relay")), not c.get("local")))
            uris = []
            for c in conns:
                if c.get("uri"):
                    uris.append(c["uri"])
                if c.get("local") and c.get("address") and c.get("port"):
                    uris.append(f"http://{c['address']}:{c['port']}")
            for uri in uris:
                try:
                    self.call(uri.rstrip("/") + "/identity", token=token, timeout=4)
                except Exception:
                    continue
                self.cfg.update(server=uri.rstrip("/"), server_token=token,
                                server_name=srv.get("name") or "Plex")
                self.save()
                return True
        return False

    def watchlist(self):
        q = urllib.parse.urlencode({"includeCollections": 1, "includeExternalMedia": 1,
                                    "X-Plex-Container-Start": 0, "X-Plex-Container-Size": 300})
        data = self.call("https://discover.provider.plex.tv/library/sections/watchlist/all?" + q,
                         token=self.cfg["token"], timeout=20)
        return (data.get("MediaContainer") or {}).get("Metadata") or []

    def find_on_server(self, guid):
        mc = self.get("/library/all?" + urllib.parse.urlencode({"guid": guid}))
        return next((m for m in mc.get("Metadata") or []
                     if m.get("type") in ("movie", "show")), None)

    def sign_out(self):
        self.cfg = {"client": self.cfg.get("client") or uuid.uuid4().hex}
        self.pin = None
        self.save()

    # the server
    def url(self, endpoint, **params):
        params["X-Plex-Token"] = self.cfg["server_token"]
        return (self.cfg["server"] + endpoint + ("&" if "?" in endpoint else "?")
                + urllib.parse.urlencode(params))

    def get(self, path):
        return self.call(self.cfg["server"] + path,
                         token=self.cfg["server_token"]).get("MediaContainer", {})

    def stream_url(self, rating_key, offset, session):
        """Ask the server to convert the video to a size the Pi plays smoothly."""
        return self.url(
            "/video/:/transcode/universal/start.m3u8",
            path=f"/library/metadata/{rating_key}", mediaIndex=0, partIndex=0,
            protocol="hls", fastSeek=1, copyts=1, offset=int(offset),
            directPlay=0, directStream=0, videoResolution=video_target()[0],
            maxVideoBitrate=video_target()[1], session=session,
            **{"X-Plex-Session-Identifier": session,
               "X-Plex-Client-Identifier": self.cfg["client"],
               "X-Plex-Product": PLEX_PRODUCT, "X-Plex-Platform": "Chrome"})

    def thumb_url(self, thumb, w, h):
        return self.url("/photo/:/transcode", width=w, height=h, minSize=1, upscale=1, url=thumb)

    def quiet(self, endpoint, **params):
        try:
            self.call(self.url(endpoint, **params), token=self.cfg["server_token"], timeout=6, raw=True)
        except Exception:
            pass

    def timeline(self, rating_key, state, pos, length):
        self.quiet("/:/timeline", ratingKey=rating_key, key=f"/library/metadata/{rating_key}",
                   identifier="com.plexapp.plugins.library", state=state,
                   time=int(pos * 1000), duration=int((length or 0) * 1000))

    def scrobble(self, rating_key):
        self.quiet("/:/scrobble", key=rating_key, identifier="com.plexapp.plugins.library")

    def stop_transcode(self, session):
        self.quiet("/video/:/transcode/universal/stop", session=session)

    # free live TV channels (the same list the Plex app shows under Live TV)
    def live_channels(self):
        h = dict(self.headers(self.cfg["token"]), **{"X-Plex-Provider-Version": "7.2",
                                                     "X-Plex-Language": "en"})
        req = urllib.request.Request(PLEX_EPG + "/lineups/plex/channels", headers=h)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        mc = data.get("MediaContainer") or data
        out = []
        for ch in mc.get("Channel") or mc.get("Metadata") or []:
            key = next((p["key"] for m in ch.get("Media") or [] for p in m.get("Part") or []
                        if p.get("key")), None) or ch.get("key")
            if not key:
                continue
            g = ch.get("Genre")
            genre = (g[0].get("tag") if isinstance(g, list) and g else ch.get("genre")) or "Other"
            out.append({"title": ch.get("title") or ch.get("callSign") or "Channel",
                        "key": key, "thumb": ch.get("thumb") or ch.get("art") or "",
                        "genre": str(genre).strip() or "Other"})
        return sorted(out, key=lambda c: c["title"].lower())

    def live_url(self, key):
        """The channel's stream, picking the version closest to the Pi's screen size."""
        url = key if key.startswith("http") else PLEX_EPG + key
        tok = "X-Plex-Token=" + urllib.parse.quote(self.cfg.get("token", ""))
        url += ("&" if "?" in url else "?") + tok
        try:
            req = urllib.request.Request(url, headers={
                "X-Plex-Client-Identifier": self.cfg["client"], "X-Plex-Product": PLEX_PRODUCT})
            with urllib.request.urlopen(req, timeout=10) as r:
                final, text = r.geturl(), r.read(200_000).decode("utf-8", "ignore")
        except Exception:
            return url
        variants, info = [], None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-STREAM-INF"):
                res = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                bw = re.search(r"BANDWIDTH=(\d+)", line)
                info = (int(res.group(2)) if res else 0, int(bw.group(1)) if bw else 0)
            elif line and not line.startswith("#") and info:
                variants.append((info, line))
                info = None
        if not variants:
            return url
        lines = video_target()[2]
        small = [v for v in variants if 0 < v[0][0] <= lines]
        pick = max(small, key=lambda v: v[0]) if small else min(variants, key=lambda v: v[0])
        out = urllib.parse.urljoin(final, pick[1])
        if "epg.provider.plex.tv" in out and "X-Plex-Token" not in out:
            out += ("&" if "?" in out else "?") + tok
        return out


# ---- any screen, any sound output ---------------------------------------------------
def pi_model():
    return read_file("/proc/device-tree/model").replace("\x00", "").strip()


def slow_pi():
    """Pi Zero, 1, 2 and 3: they play 480 lines smoothly, not much more."""
    m = pi_model()
    return ("Zero" in m or bool(re.search(r"Raspberry Pi [123]\b", m)) or "Raspberry Pi Model" in m
            or bool(re.search(r"Compute Module( 3)?( Plus)? Rev", m)))


def screen_size():
    """The screen's real size: 640x480 on the GPi Case, 1920x1080 on most TVs."""
    try:
        with open("/dev/fb0", "rb", buffering=0) as f:
            w, h = fb_geometry(f)[:2]
        if w and h:
            return w, h
    except (OSError, struct.error):
        pass
    m = re.match(r"(\d+),(\d+)", read_file("/sys/class/graphics/fb0/virtual_size"))
    return (int(m.group(1)), int(m.group(2))) if m else (640, 480)


def video_target():
    """(Plex's size, its bitrate in kbps, live TV's lines): sharper on a big screen when the
    Pi can keep up (a Pi 4 or 5 on a TV), the GPi Case's 480 lines otherwise."""
    w, h = screen_size()
    if w >= 1280 and h >= 720 and not slow_pi():
        return "1280x720", 4000, 720
    return PLEX_RESOLUTION, PLEX_BITRATE, PLEX_LIVE_HEIGHT


def sound_cards():
    """[(card id, name)] for the sound outputs: ("vc4hdmi0", "HDMI 1"), ("Headphones", ...)..."""
    out = []
    for line in read_file("/proc/asound/cards").splitlines():
        m = re.match(r"\s*\d+\s+\[(\S+)\s*\]:\s*\S+\s+-\s+(.+)", line)
        if not m:
            continue
        cid, desc = m.group(1), m.group(2).strip()
        hd = re.fullmatch(r"vc4hdmi(\d?)", cid)
        if hd:
            name = "HDMI" + (f" {int(hd.group(1)) + 1}" if hd.group(1) else "")
        elif cid == "Headphones" or "headphone" in desc.lower():
            name = "Headphones"
        else:
            name = desc[:24]
        if name not in [n for _, n in out]:
            out.append((cid, name))
    return out


def hdmi_ports():
    """The HDMI ports with a screen plugged in: [0], [1], [0, 1]..."""
    ports = []
    for path in sorted(glob.glob("/sys/class/drm/card*-HDMI-A-*/status")):
        if read_file(path).strip() == "connected":
            m = re.search(r"HDMI-A-(\d+)", path)
            if m and int(m.group(1)) - 1 not in ports:
                ports.append(int(m.group(1)) - 1)
    return ports


def sound_card(choice):
    """The card for Settings > Sound. Auto plays through the TV when one is plugged into HDMI, and
    through the Pi's usual output otherwise (None: the system's default)."""
    cards = sound_cards()
    ids = [c for c, _ in cards]
    cid = None
    if choice and choice != "Auto":
        cid = next((c for c, n in cards if n == choice), None)
    else:
        for port in hdmi_ports():
            cid = next((c for c in (f"vc4hdmi{port}", "vc4hdmi") if c in ids), None)
            if cid:
                break
    return cid


def sound_device(choice):
    """mplayer's -ao for Settings > Sound; plain ALSA is the fallback either way."""
    cid = sound_card(choice)
    return f"alsa:device=default={cid},alsa" if cid else "alsa"


def aplay_device(choice):
    """aplay's -D for Settings > Sound: the same card as mplayer's."""
    cid = sound_card(choice)
    return f"default:CARD={cid}" if cid else ""


def fb_geometry(f):
    """(width, height, x offset, y offset, bits per pixel, colour fields, stride) of a framebuffer."""
    info = fcntl.ioctl(f, 0x4600, bytes(160))   # FBIOGET_VSCREENINFO
    (w, h, xv, _, xo, yo, bpp, _) = struct.unpack_from("8I", info, 0)
    fields = [struct.unpack_from("2I", info, o) for o in (32, 44, 56)]
    try:
        with open(f"/sys/class/graphics/{os.path.basename(f.name)}/stride") as fs:
            stride = int(fs.read())
    except (OSError, ValueError):
        stride = xv * bpp // 8
    return w, h, xo, yo, bpp, fields, stride


def read_screen(f, geo, max_w=640):
    """What's on a framebuffer, as a picture at most max_w wide. On a big screen only every
    few pixels are read, so a 1080p TV costs about what the GPi Case's screen does."""
    from PIL import Image
    import numpy as np
    w, h, xo, yo, bpp, fields, stride = geo
    bp = bpp // 8
    step = max(1, w // max_w)
    if step == 1 and stride == w * bp and not xo and not yo:
        f.seek(0)
        raw, n = f.read(w * h * bp), h
    else:
        rows = []
        for y in range(0, h, step):
            f.seek((y + yo) * stride + xo * bp)
            rows.append(f.read(w * bp))
        raw, n = b"".join(rows), len(rows)
    px = np.frombuffer(raw, dtype="<u2" if bpp == 16 else "<u4")[:w * n].reshape(n, w)[:, ::step]
    rh, rw = px.shape
    rgb = np.zeros((rh, rw, 3), dtype=np.uint8)
    for c, (off, ln) in enumerate(fields):
        top = (1 << ln) - 1
        rgb[..., c] = ((px >> off) & top).astype(np.uint32) * 255 // top
    img = Image.fromarray(rgb, "RGB")
    if rw > max_w:
        img = img.resize((max_w, max(1, round(rh * max_w / rw))), Image.BILINEAR)
    return img


def grab_screen(max_w=640, dev="/dev/fb0"):
    """A picture of the screen right now, video and terminal included (for the web page)."""
    with open(dev, "rb", buffering=0) as f:
        return read_screen(f, fb_geometry(f), max_w)


class Framebuffer:
    """Draws a PIL image onto /dev/fb0 in whatever format it uses. The menus are drawn at
    640x480, the GPi Case's screen, and scaled up to fill any other screen, edges black."""
    W, H = 640, 480
    count = 0                                         # pictures shown, ever: the web page's cue

    def __init__(self, dev="/dev/fb0"):
        self.f = open(dev, "r+b", buffering=0)
        self.setup(*fb_geometry(self.f))

    def setup(self, w, h, xo, yo, bpp, fields, stride):
        if bpp not in (16, 32):
            raise OSError(f"unsupported framebuffer depth {bpp}")
        self.real_w, self.real_h, self.xo, self.yo = w, h, xo, yo
        self.bpp, self.fields, self.stride = bpp, fields, stride
        self.w, self.h = self.W, self.H               # what the menus are drawn at
        k = min(w / self.W, h / self.H)
        if int(k) >= 1 and int(k) / k >= 0.85:       # 2x on a 1080p TV: crisp, and quick to draw
            k = int(k)
        self.tw, self.th = max(1, round(self.W * k)), max(1, round(self.H * k))
        self.ox, self.oy = (w - self.tw) // 2, (h - self.th) // 2
        self.same = (w, h) == (self.W, self.H)
        self.sharp = k == int(k)                      # 2x, 3x: plain pixel doubling stays crisp
        # the usual 32-bit screen (KMS, any HDMI TV): PIL packs it itself, ten times quicker
        self.raw = "BGRX" if bpp == 32 and [tuple(f) for f in fields] == [(16, 8), (8, 8), (0, 8)] else None
        self.clear_next = not self.same               # black edges first
        self.last = None                              # the last menu picture, for the web page
        self.frames = type(self).count

    def pack(self, img):
        if img.mode != "RGB":
            img = img.convert("RGB")
        if getattr(self, "raw", None):
            return img.tobytes("raw", self.raw)
        import numpy as np
        a = np.asarray(img, dtype=np.uint32)
        px = np.zeros(a.shape[:2], dtype=np.uint32)
        for c, (off, ln) in enumerate(self.fields):
            px |= (a[..., c] >> (8 - ln)) << off
        return px.astype("<u2" if self.bpp == 16 else "<u4").tobytes()

    def put(self, data, x, y, w, h):
        """Bytes for a w x h block, written at x, y on the real screen."""
        bp = self.bpp // 8
        row = w * bp
        if x == 0 and y == 0 and w == self.real_w and self.stride == row and not self.xo and not self.yo:
            self.f.seek(0)
            self.f.write(data)
            return
        for r in range(h):
            self.f.seek((y + r + self.yo) * self.stride + (x + self.xo) * bp)
            self.f.write(data[r * row:(r + 1) * row])

    def show(self, img):
        self.last = img
        type(self).count += 1
        self.frames = type(self).count
        if self.same:
            self.put(self.pack(img), 0, 0, self.real_w, self.real_h)
            return
        from PIL import Image
        if self.clear_next:
            self.clear_next = False
            self.put(bytes(self.real_w * self.real_h * self.bpp // 8), 0, 0, self.real_w, self.real_h)
        if self.sharp and not self.raw:               # pack the small picture, then repeat each pixel
            import numpy as np
            k = self.tw // self.W
            a = np.frombuffer(self.pack(img), dtype="<u2" if self.bpp == 16 else "<u4").reshape(self.H, self.W)
            data = np.repeat(np.repeat(a, k, axis=0), k, axis=1).tobytes()
        else:
            data = self.pack(img.resize((self.tw, self.th), Image.NEAREST if self.sharp else Image.BILINEAR))
        self.put(data, self.ox, self.oy, self.tw, self.th)

    def invalidate(self):
        """Something else drew on the screen (a video): blacken the edges again next time."""
        self.clear_next = not self.same

    def blank_outside(self, box):
        """Black everywhere but the box (x0, y0, x1, y1), in real screen pixels: the bars round
        a video that doesn't fill the screen. mplayer only ever draws its picture."""
        bp = self.bpp // 8
        x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
        x1, y1 = min(self.real_w, int(box[2])), min(self.real_h, int(box[3]))
        row = bytes(self.real_w * bp)
        for y in range(self.real_h):
            at = (y + self.yo) * self.stride + self.xo * bp
            if y < y0 or y >= y1:
                self.f.seek(at)
                self.f.write(row)
                continue
            if x0 > 0:
                self.f.seek(at)
                self.f.write(row[:x0 * bp])
            if x1 < self.real_w:
                self.f.seek(at + x1 * bp)
                self.f.write(row[:(self.real_w - x1) * bp])

    def close(self):
        self.f.close()


# ---- media mode -------------------------------------------------------------
class Media:
    REPEAT_VIEWS = ("list", "photo", "pdf", "text", "home", "keys")
    STATUS_VIEWS = ("list", "now", "help", "text", "home")

    def __init__(self):
        self.active = False
        self.tab = 0
        self.tab_off = 0            # how far the tab strip is scrolled
        self.items = {}             # tab index -> list of items
        self.status = {}            # tab index -> "loading" / "error"
        self.sels, self.tops = {}, {}
        self.view = "list"          # list, help, now, photo, pdf, text, wait
        self.help_from = "list"
        self.v = {}                 # state of the open photo / pdf / text viewer
        self.proc = None
        self.kind = None            # playing: video, audio, live, radio, plex
        self.cur = None             # the item playing
        self.queue, self.qi = [], 0
        self.pos = 0.0
        self.meta = {}
        self.paused = False
        self.shuffle = False
        self.volume = 80
        self.started = 0.0
        self.retry = None           # (args, target) to try if a stream fails at once
        self.next_query = 0.0
        self.next_status = 0.0
        self.status_sig = None
        self.confirm = (None, 0.0)  # system action waiting for a second press
        self.halting = 0.0          # shutting down: the screen says so until then (monotonic)
        self.halt_note = ""         # ...and says this if it's still here after that
        self.dirty = False
        self.msg, self.msg_until = None, 0.0
        self.fb = None
        self.ttyfd = None
        self.prev_vt = "1"
        self.prober = self.thumber = self.sysloop = None
        self.thumbs = {}            # path -> small PIL image (most recent ~300)
        self.cwd = home_dir()
        self.dir_sel = {}           # folder -> selected row
        self.show_hidden = False
        self.camera = Camera()
        self.camera.on_select = self.camera_select
        self.cam_list = False        # the Camera tab shows your cameras rather than one's picture
        self.cam_sel = 0
        self.cam_bot = None          # what the bot said it sees (SELECT): {"addr", "busy", "text", ...}
        self.friend = Friend()
        self.friend.facts = self.friend_facts
        self.friend.look = self.friend_look
        self.friend.snap = self.friend_snap
        self.friend.on_change = self.friend_changed
        self.friend.on_reply = self.bot_replied
        self.voice = Voice()
        self.voice.on_change = self.friend_changed
        self.voice.on_ready = self.voice_ready
        self.voice_want = None       # a voice you picked that's on its way
        self.voice_arrived = None    # ...and here (for the main loop to use)
        self.voice_told = ""         # the last of the voice's troubles shown
        self.friend_scroll = 0       # how far back the conversation is scrolled (pixels)
        self.friend_seen = len(self.friend.log)
        self.friend_opened_at = 0.0
        self.friend_jitter = 1.0     # its remarks come not quite on the dot
        self.friend_more = None      # the Bot page's X menu, when open: {"sel": n}
        self.friend_pics = {}        # a picture's id -> (it, its rounded corners) as the Bot page shows it
        self.pie = PieInk(cameras=self.pie_cameras)   # PiE-ink on another Pi: asked first for what it has
        self.camera.on_pie = self.pie.hear
        self.crypto = Crypto(self.pie)
        self.crypto_card = 0
        self.crypto_auto = False
        self.last_shot = None        # a picture the Camera tab just saved, to select in Photos
        self.hass = HomeAssistant()
        self.home_sel = 0            # the icon picked on the home screen
        self.wall = (None, None)     # (what it's for, the home screen's background)
        self.set_sel = 0             # Settings: the row picked
        self.set_page = "root"       # Settings: "root" or "location"
        self.loc_results, self.loc_status = [], None
        self.wifi = {"nets": [], "saved": {}, "status": None, "busy": False, "radio": True, "ssid": "",
                     "ssid_t": 0.0}
        self.picking = None          # "wallpaper" while a picture is being picked in Photos
        self.kb = None               # the on-screen keyboard, while it's up
        self.keyreader = KeyReader()
        self.weather = None          # made once the settings are loaded
        self.wx_page = 0             # Weather: now, the week, the forecast in words
        self.wx_icons = {}
        self.radio_stack = []        # Radio: folders opened (genre, popular, search)
        self.chan_stack = {}         # Cartoons, Free Movies...: tab -> the folder opened (Anime, a search)
        self.live_wait = {}          # News, Sports: tab -> "loading" or "error" while Plex's channels come
        self.vsize = None            # the playing video's size, for Full screen
        self.bars_for = None         # the video whose black bars have been drawn
        self.now_from = "list"       # where B goes from Now playing
        self.icons = {}              # drawn app icons
        self.remote_more = None      # the TV Remote's More menu, when open: {"sel": n}
        self.remote_pad = None       # the TV Remote's number pad, when open: {"text", "r", "c"}
        self.remote_hit = ("", 0.0)  # the button just pressed there, and when
        self.cam_said = ("", 0.0)    # the camera's last message and when it changed
        self.crypto_next = 0.0
        self.plex = Plex()
        self.plex_stack = []        # Plex folders you've opened, top is on screen
        self.plex_session = None
        self.plex_base = 0.0        # where the current Plex stream started
        self.plex_mode = None       # whether mplayer reports absolute or relative time
        self.plex_last = 0.0
        self.plex_pending = None    # seek target waiting for more presses
        self.plex_pending_t = 0.0
        self.next_timeline = 0.0
        self.plexthumber = None
        self.plex_live = (0.0, [])  # (when fetched, channels)
        self.learn = None           # Settings > Controller: setting up a controller's buttons
        self.pads = None            # the controllers plugged in (the input loop sets this)
        self.shot = (None, b"", "")  # the last picture of the screen sent to the web page
        self.web_radio_cache = {}   # Radio Browser lists the web page asked for
        self.web_icons = {}
        self.web_guard = False      # the web page is at the controls: your home folder only
        self.lock = threading.Lock()
        self.state = {"pos": {}, "dur": {}, "settings": {}, "radio": {}}
        self.fonts = None
        self.load_state()
        self.boot_media = self.setting("start") == "Home screen"
        set_accent(self.setting("accent"))
        self.weather = Weather(lambda: self.setting("location"),
                               lambda: "C" if self.setting("units") == "°C" else "F", pie=self.pie)
        self.weather.on_change = self.weather_drawn

    # -- settings ------------------------------------------------------------
    def setting(self, key):
        v = self.state["settings"].get(key)
        if key == "screen" and v not in SCREEN_MODES:
            return "Full screen" if v == "Fill" else "Fit"          # "Fill" is its old name
        return SETTINGS_DEFAULT.get(key) if v is None else v

    def set_setting(self, key, value):
        self.state["settings"][key] = value
        if key == "accent":
            set_accent(value)
            self.icons.clear()
        if key in ("wallpaper", "picture"):
            self.wall = (None, None)
        self.save_state()
        self.dirty = True

    def clock_text(self, t=None, ampm=True):
        t = t or time.localtime()
        if self.setting("clock") == "24-hour":
            return time.strftime("%H:%M", t)
        return time.strftime("%-I:%M %p" if ampm else "%-I:%M", t)

    # -- saved state ---------------------------------------------------------
    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            for k in self.state:
                self.state[k].update(s.get(k, {}))
            self.volume = int(s.get("volume", self.volume))
        except (OSError, ValueError):
            pass

    def save_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with self.lock:
                data = json.dumps(dict(self.state, volume=self.volume))
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
            os.replace(tmp, STATE_FILE)
        except OSError:
            pass

    def length(self, it):
        if it["kind"] not in ("video", "audio") or "://" in it["src"]:
            return None
        entry = self.state["dur"].get(it["key"])
        try:
            mtime = os.path.getmtime(it["src"])
        except OSError:
            return None
        return entry[1] if entry and entry[0] == mtime else None

    def resume_at(self, it):
        """Seconds to resume a video from, or 0. -1 in state means watched."""
        if it["kind"] != "video":
            return 0
        p = self.state["pos"].get(it["key"], 0)
        n = self.length(it) or 0
        if p > 5 and (not n or p < n - 10):
            return p
        return 0

    def toast(self, text, secs=4):
        self.msg, self.msg_until = text, time.monotonic() + secs
        self.dirty = True

    # -- tabs ----------------------------------------------------------------
    def tab_items(self, i=None):
        return self.items.get(self.tab if i is None else i, [])

    def tab_type(self, i=None):
        return LIBRARY[self.tab if i is None else i]["type"]

    def tab_index(self, ttype):
        return next((i for i, t in enumerate(LIBRARY) if t["type"] == ttype), None)

    @staticmethod
    def parent_of(i):
        """The tab a tab lives inside (TV for Plex, say), or None."""
        name = LIBRARY[i].get("parent")
        return next((k for k, t in enumerate(LIBRARY) if t["name"] == name), None) if name else None

    @staticmethod
    def visible_tabs():
        return [i for i, t in enumerate(LIBRARY) if not t.get("parent")]

    def strip_tab(self):
        """The tab lit up along the top: the group, while you're inside it."""
        p = self.parent_of(self.tab)
        return self.tab if p is None else p

    def on_camera_page(self):
        """A camera's live picture is on screen."""
        return self.active and self.view == "list" and self.tab_type() == "camera" and not self.cam_list

    def on_camera_list(self):
        return self.active and self.view == "list" and self.tab_type() == "camera" and self.cam_list

    def holds_buttons(self):
        """Pages that follow buttons held down themselves (no key repeat)."""
        return self.on_camera_page()

    def tick_limit(self):
        """How long the input loop may wait before the next tick."""
        return 0.1 if self.on_camera_page() else 0.25

    def load_tab(self, i):
        tab = LIBRARY[i]
        if tab["type"] == "files":
            self.items[i] = [item(p, title_of(p), tab["kind"], p)
                             for p in find_files(tab["dirs"], tab["exts"])]
        elif tab["type"] == "photos":
            files = find_files(tab["dirs"], IMAGE_EXTS)
            files.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                       reverse=True)          # newest first
            self.items[i] = [item(p, os.path.basename(p), "image", p) for p in files]
            if self.last_shot in files:       # the picture just taken on the Camera tab
                self.sels[i] = files.index(self.last_shot)
                self.last_shot = None
            if self.active and not (self.thumber and self.thumber.is_alive()):
                self.thumber = threading.Thread(target=self.thumb_loop, daemon=True)
                self.thumber.start()
        elif tab["type"] == "group":
            rows = []
            for name in tab["children"]:
                ci = next(k for k, t in enumerate(LIBRARY) if t["name"] == name)
                rows.append(dict(item("grp:" + name, name, "child", str(ci),
                                      sub=LIBRARY[ci].get("about", "")),
                                 icon=LIBRARY[ci].get("badge", "")))
            self.items[i] = rows
        elif tab["type"] == "radio":
            if self.radio_stack:
                self.items[i] = self.radio_stack[-1]["items"]
            else:
                self.items[i] = self.radio_root(tab)
        elif tab["type"] == "streams":
            self.items[i] = read_streams(tab["files"])
        elif tab["type"] == "browser":
            if self.web_guard and not self.web_may_see(self.cwd):
                self.cwd = home_dir()                  # the web page keeps to your home folder
            self.items[i] = self.list_dir(self.cwd)
            self.sels[i] = self.dir_sel.get(self.cwd, self.first_row(self.items[i]))
        elif tab["type"] == "plex":
            if self.plex.ready:
                if self.plex_stack:
                    self.items[i] = self.plex_stack[-1]["items"]
                elif self.status.get(i) != "loading":
                    self.plex_open("root", "Plex")
                self.start_plex_thumbs()
            else:
                self.items[i] = []
        elif tab["type"] == "crypto":
            self.crypto.load(tab["files"])
            self.crypto.on_change = self.crypto_changed
            cards = self.crypto.cards()
            self.crypto_card = min(self.crypto_card, max(len(cards) - 1, 0))
            self.crypto_focus()
            if self.active and self.tab == i and self.view == "list":
                self.crypto.start()
            self.items[i] = []
        elif tab["type"] == "remote":
            self.hass.load(tab["files"])
            self.hass.on_change = self.remote_changed
            self.hass.on_note = lambda text: self.toast(text, 3)
            if self.active and self.tab == i and self.view == "list":
                self.hass.start()
            self.items[i] = []
        elif tab["type"] == "weather":
            self.weather.refresh(full=self.active and self.tab == i and self.view == "list")
            self.items[i] = []
        elif tab["type"] == "friend":
            self.friend.load(tab["files"])
            self.items[i] = []
            if self.active and self.tab == i and self.view == "list":
                self.friend_opened()
        elif tab["type"] == "camera":
            self.friend.load(self.friend_files())     # (SELECT: the bot, if there's one)
            self.camera.load(tab["files"], last=self.state.get("camera"))
            self.camera.on_change = self.camera_changed
            self.camera.on_saved = self.picture_saved
            if not self.camera.addr:
                self.cam_list = True
            if self.active and self.tab == i and self.view == "list":
                if self.cam_list:
                    self.camera.scan()
                else:
                    self.camera.start()
            self.items[i] = []
        elif tab["type"] == "system":
            self.items[i] = system_info()
            if not (self.sysloop and self.sysloop.is_alive()):
                self.sysloop = threading.Thread(target=self.system_loop, daemon=True)
                self.sysloop.start()
        elif tab["type"] == "channels" and self.chan_stack.get(i):
            self.items[i] = self.chan_stack[i][-1]["items"]
        elif tab["type"] == "channels":
            self.load_channels(i)
        n = len(self.tab_items(i))
        self.sels[i] = min(self.sels.get(i, 0), max(n - 1, 0))

    def switch_tab(self, d):
        if self.tab_type() == "camera":
            self.camera.stop()
        if self.tab_type() == "crypto":
            self.crypto.stop()
        if self.tab_type() == "remote":
            self.hass.stop()
            self.remote_more = None
        self.confirm = (None, 0.0)
        self.picking = None                            # (picking a picture: not any more)
        self.friend_more = None
        vis = self.visible_tabs()
        self.tab = vis[(vis.index(self.strip_tab()) + d) % len(vis)]
        self.load_tab(self.tab)

    def system_loop(self):
        si = self.tab_index("system")
        while self.active and self.tab == si:
            time.sleep(2)
            if self.active and self.tab == si and self.view == "list" and not self.proc_owns_screen():
                self.items[si] = system_info()
                self.dirty = True

    def list_dir(self, path):
        out = []
        try:
            entries = list(os.scandir(path))
        except OSError:
            self.toast("Can't open that folder")
            entries = []
        guard = self.web_guard
        if path != "/" and not (guard and os.path.realpath(path) == os.path.realpath(home_dir())):
            out.append(item(os.path.dirname(path.rstrip("/")) or "/", "..", "up",
                            os.path.dirname(path.rstrip("/")) or "/"))
        dirs, files = [], []
        for en in entries:
            if en.name.startswith(".") and (guard or not self.show_hidden):
                continue
            if guard and web_private(en.name):
                continue
            try:
                is_dir = en.is_dir()
            except OSError:
                continue
            (dirs if is_dir else files).append(en)
        for en in sorted(dirs, key=lambda x: x.name.lower()):
            out.append(item(en.path, en.name, "dir", en.path))
        for en in sorted(files, key=lambda x: x.name.lower()):
            out.append(item(en.path, en.name, classify(en.path), en.path))
        return out

    def web_may_see(self, path):
        """What the web page may open: things in your home folder, not hidden, not private."""
        home = os.path.realpath(home_dir())
        real = os.path.realpath(path)
        if real != home and not real.startswith(home + os.sep):
            return False
        parts = [] if real == home else os.path.relpath(real, home).split(os.sep)
        return not any(x.startswith(".") for x in parts) and not (parts and web_private(parts[-1]))

    def browse(self, path, select=None):
        if self.web_guard and not self.web_may_see(path):
            path, select = home_dir(), None            # the web page keeps to your home folder
        bi = self.tab_index("browser")
        self.dir_sel[self.cwd] = self.sels.get(bi, 0)
        self.cwd = path
        self.items[bi] = self.list_dir(path)
        sel = self.dir_sel.get(path, self.first_row(self.items[bi]))
        if select:
            sel = next((k for k, it in enumerate(self.items[bi]) if it["src"] == select), sel)
        self.sels[bi] = min(sel, max(len(self.items[bi]) - 1, 0))
        self.tops[bi] = 0
        self.dirty = True

    @staticmethod
    def first_row(items):
        """Start on the first real entry rather than the '..' row."""
        return 1 if len(items) > 1 and items[0]["kind"] == "up" else 0

    # -- Plex ------------------------------------------------------------------
    def plex_items(self, mc, context=""):
        out = []
        for d in mc.get("Directory", []):                  # library sections
            if d.get("type") in ("movie", "show") and d.get("key") is not None:
                out.append(dict(item("plexsec:" + str(d["key"]), d.get("title", ""), "plexdir",
                                     f"/library/sections/{d['key']}/all",
                                     sub="Movies" if d["type"] == "movie" else "TV shows"),
                                thumb=None, ptype="section", icon=d["type"]))
        for m in mc.get("Metadata", []):
            t, rk = m.get("type"), str(m.get("ratingKey", ""))
            thumb = m.get("thumb") or m.get("parentThumb") or m.get("grandparentThumb")
            if t in ("movie", "episode", "clip"):
                title, sub = m.get("title", ""), ""
                if t == "movie":
                    sub = str(m.get("year") or "")
                elif context == "season":
                    title = f"{m.get('index', '')}. {title}"
                else:
                    sub = title
                    title = (f"{m.get('grandparentTitle', '')}  S{m.get('parentIndex', '?')}"
                             f" E{m.get('index', '?')}")
                out.append(dict(item("plex:" + rk, title, "plexvideo", rk, sub=sub),
                                dur=(m.get("duration") or 0) / 1000,
                                off=(m.get("viewOffset") or 0) / 1000,
                                watched=(m.get("viewCount") or 0) > 0, thumb=thumb, ptype=t))
            elif t in ("show", "season"):
                n, seen = m.get("leafCount"), m.get("viewedLeafCount")
                out.append(dict(item("plexdir:" + rk, m.get("title", ""), "plexdir",
                                     m.get("key", ""), sub=f"{n} episodes" if n else ""),
                                thumb=thumb, ptype=t,
                                unwatched=(n - seen) if n is not None and seen is not None else None))
        return out

    def plex_open(self, path, title, context=""):
        pi = self.tab_index("plex")
        if self.plex_stack:
            self.plex_stack[-1]["sel"] = self.sels.get(pi, 0)
            self.plex_stack[-1]["top"] = self.tops.get(pi, 0)
        self.status[pi] = "loading"
        self.dirty = True
        threading.Thread(target=self.plex_fetch, args=(path, title, context), daemon=True).start()

    def plex_fetch(self, path, title, context):
        pi = self.tab_index("plex")
        try:
            if path == "root":
                items = [dict(item("plexsearch", "Search", "plexsearch", "search",
                                   sub="Channels, movies and shows"), thumb=None, ptype="search", icon="find")]
                cont = self.plex_continue()
                items.append(dict(item("plexdeck", "Continue watching", "plexdir", "continue",
                                       sub=f"{len(cont)} to finish" if cont else "Nothing in progress"),
                                  thumb=None, ptype="deck", icon="deck"))
                if self.plex.signed_in:
                    items.append(dict(item("plexwatch", "Watchlist", "plexdir", "watchlist",
                                           sub="Your Plex watchlist"),
                                      thumb=None, ptype="watchlist", icon="list"))
                items += self.plex_items(self.plex.get("/library/sections"))
                if self.plex.signed_in:
                    items.append(dict(item("plexlivetv", "Live TV", "plexdir", "livetv",
                                           sub="Free channels"), thumb=None, ptype="livetv", icon="live"))
                    items.append(dict(item("plexmoviech", "Free movie channels", "plexdir",
                                           "livetv:~movie", sub="Movies, live"),
                                      thumb=None, ptype="livetv", icon="live"))
                items.append(item("act:plex_signout", "Sign out of Plex", "action", "plex_signout"))
            elif path == "continue":
                items = self.plex_continue()
            elif path == "watchlist":
                items = self.plex_watchlist_items()
            elif path.startswith("livetv"):
                items = self.plex_live_items(path)
            elif path.startswith("search:") or path.startswith("livesearch:"):
                items = self.plex_search(path.split(":", 1)[1], library=path.startswith("search:"))
                if not items:
                    self.status[pi] = "empty"
            else:
                items = self.plex_items(self.plex.get(path), context)
            level = {"title": title, "path": path, "context": context,
                     "items": items, "sel": 0, "top": 0}
            if path == "root":
                self.plex_stack = [level]
            else:
                self.plex_stack.append(level)
            self.items[pi], self.sels[pi], self.tops[pi] = items, 0, 0
            if items or self.status.get(pi) != "empty":
                self.status.pop(pi, None)
        except Exception:
            self.status[pi] = "error"
            if self.plex_stack:
                self.toast("Couldn't reach your Plex server")
        self.dirty = True
        self.start_plex_thumbs()

    def plex_continue(self):
        """Movies you haven't finished and the next episodes, newest first."""
        for path in ("/hubs/continueWatching/items", "/library/onDeck"):
            try:
                return self.plex_items(self.plex.get(path))
            except Exception:
                continue
        return []

    def plex_watchlist_items(self):
        """Your Plex watchlist, each matched to the copy on your server when there is one."""
        out = []
        for w in self.plex.watchlist():
            guid, m = w.get("guid") or "", None
            if guid:
                try:
                    m = self.plex.find_on_server(guid)
                except Exception:
                    m = None
            got = self.plex_items({"Metadata": [m]}) if m else []
            if got:
                out.append(got[0])
                continue
            thumb = w.get("thumb") or ""
            out.append(dict(item("plexwant:" + (guid or w.get("title", "")), w.get("title", ""),
                                 "plexwant", "", sub=str(w.get("year") or "")),
                            thumb=thumb if thumb.startswith("http") else None, ptype="want"))
        return out

    def plex_live_items(self, path):
        when, chans = self.plex_live
        if not chans or time.time() - when > 6 * 3600:
            chans = self.plex.live_channels()
            self.plex_live = (time.time(), chans)
        if path == "livetv":                          # genres, biggest first after "All"
            counts = {}
            for c in chans:
                counts[c["genre"]] = counts.get(c["genre"], 0) + 1
            items = [dict(item("plexlivesearch", "Search channels", "plexsearch", "livesearch",
                               sub="By name"), thumb=None, ptype="search", icon="find"),
                     dict(item("plexlive:all", "All channels", "plexdir", "livetv:*",
                               sub=f"{len(chans)} channels"), thumb=None, ptype="genre", icon="live")]
            for g in sorted(counts, key=lambda g: (-counts[g], g.lower())):
                items.append(dict(item("plexlive:g:" + g, g, "plexdir", "livetv:" + g,
                                       sub=f"{counts[g]} channels"), thumb=None, ptype="genre",
                                  icon="live"))
            return items
        genre = path.split(":", 1)[1]

        def wanted(c):
            if genre.startswith("~"):                 # any genre containing the word
                return genre[1:] in c["genre"].lower()
            return genre == "*" or c["genre"] == genre
        return [dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"],
                          sub=c["genre"]), thumb=c["thumb"] or None, ptype="channel")
                for c in chans if wanted(c)]

    def plex_search(self, query, library=True):
        """Live TV channels whose name (or kind) has every word you typed, then, for a
        search from the top, your server's movies, shows and episodes."""
        words = query.lower().split()
        when, chans = self.plex_live
        out = []
        if self.plex.signed_in:
            try:
                if not chans or time.time() - when > 6 * 3600:
                    chans = self.plex.live_channels()
                    self.plex_live = (time.time(), chans)
            except Exception:
                chans = []
            hits = [c for c in chans if all(w in (c["title"] + " " + c["genre"]).lower() for w in words)]
            hits.sort(key=lambda c: (not c["title"].lower().startswith(words[0]) if words else 0,
                                     c["title"].lower()))
            out += [dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"],
                              sub=c["genre"]), thumb=c["thumb"] or None, ptype="channel") for c in hits[:60]]
        if library:
            try:
                mc = self.plex.get("/hubs/search?" + urllib.parse.urlencode({"query": query, "limit": 20}))
                found = []
                for hub in mc.get("Hub") or []:
                    if hub.get("type") in ("movie", "show", "episode"):
                        found += hub.get("Metadata") or []
                out += self.plex_items({"Metadata": found})
            except Exception:
                pass
        return out

    def plex_back(self):
        pi = self.tab_index("plex")
        if len(self.plex_stack) > 1 and self.status.get(pi) != "loading":
            self.plex_stack.pop()
            lvl = self.plex_stack[-1]
            self.items[pi], self.sels[pi], self.tops[pi] = lvl["items"], lvl["sel"], lvl["top"]
            self.dirty = True
            return True
        return False

    def plex_sign_in(self):
        pi = self.tab_index("plex")
        self.status[pi] = "code"
        self.dirty = True
        threading.Thread(target=self.plex_login_loop, daemon=True).start()

    def plex_login_loop(self):
        pi = self.tab_index("plex")
        if not self.plex.signed_in:
            try:
                self.plex.start_pin()
            except Exception:
                self.status[pi] = "offline"
                self.dirty = True
                return
            self.status.pop(pi, None)
            self.dirty = True
            while self.plex.pin and time.monotonic() < self.plex.pin["until"]:
                time.sleep(2)
                try:
                    if self.plex.check_pin():
                        break
                except Exception:
                    pass
            if not self.plex.signed_in:
                self.plex.pin = None
                self.toast("That code expired. Press A for a new one")
                return
        self.status[pi] = "finding"
        self.dirty = True
        try:
            found = self.plex.find_server()
        except Exception:
            found = False
        if not found:
            self.status[pi] = "noserver"
            self.dirty = True
            return
        self.status.pop(pi, None)
        self.plex_open("root", "Plex")

    @staticmethod
    def plex_size(it):
        return {"episode": (56, 32), "channel": (48, 32)}.get(it.get("ptype"), (30, 44))

    def plex_thumb(self, it, size):
        key = f"plex:{it.get('thumb')}:{size}"
        im = self.thumbs.get(key)
        if im is not None:
            return im
        fn = os.path.join(CACHE_DIR, "plex", hashlib.md5(
            f"{self.plex.cfg.get('server')}{key}".encode()).hexdigest() + ".jpg")
        if os.path.exists(fn):
            from PIL import Image
            try:
                im = Image.open(fn)
                im.load()
                self.keep_thumb(key, im)
                return im
            except OSError:
                pass
        return None

    def start_plex_thumbs(self):
        if self.active and not (self.plexthumber and self.plexthumber.is_alive()):
            self.plexthumber = threading.Thread(target=self.plex_thumb_loop, daemon=True)
            self.plexthumber.start()

    def plex_thumb_loop(self):
        """Fetch poster thumbnails for the rows on screen (and the next page)."""
        import io
        from PIL import Image, ImageOps
        os.makedirs(os.path.join(CACHE_DIR, "plex"), exist_ok=True)
        failed = set()
        pi = self.tab_index("plex")
        while self.active and self.tab == pi and self.plex.ready:
            if self.proc_owns_screen():
                time.sleep(0.5)
                continue
            items = self.tab_items(pi)
            top, rows = self.tops.get(pi, 0), self.visible_rows()
            todo = None
            for it in items[top:top + rows * 2]:
                size = self.plex_size(it)
                if it.get("thumb") and (it["thumb"], size) not in failed \
                        and self.plex_thumb(it, size) is None:
                    todo = (it, size)
                    break
            if not todo:
                time.sleep(0.5)
                continue
            it, (w, h) = todo
            key = f"plex:{it['thumb']}:{(w, h)}"
            try:
                if it["thumb"].startswith("http"):     # a channel logo: fetched as is, fitted whole
                    req = urllib.request.Request(it["thumb"], headers=UA)
                    with urllib.request.urlopen(req, timeout=10) as r:
                        logo = Image.open(io.BytesIO(r.read())).convert("RGBA")
                    logo = ImageOps.contain(logo, (w - 4, h - 4), Image.BILINEAR)
                    im = Image.new("RGB", (w, h), LINE)
                    im.paste(logo, ((w - logo.width) // 2, (h - logo.height) // 2), logo)
                else:
                    data = self.plex.call(self.plex.thumb_url(it["thumb"], w * 2, h * 2),
                                          token=self.plex.cfg["server_token"], raw=True)
                    im = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (w, h),
                                      Image.BILINEAR)
                im.save(os.path.join(CACHE_DIR, "plex", hashlib.md5(
                    f"{self.plex.cfg.get('server')}{key}".encode()).hexdigest() + ".jpg"))
                self.keep_thumb(key, im)
                self.dirty = True
            except Exception:
                failed.add((it["thumb"], (w, h)))

    def probe_loop(self):
        while self.active:
            if self.proc_owns_screen():
                time.sleep(1)
                continue
            todo = None
            for i, tab in enumerate(LIBRARY):
                if tab["type"] == "files":
                    todo = next((it for it in self.tab_items(i)
                                 if self.length(it) is None), None)
                    if todo:
                        break
            if todo is None:
                break
            n = probe_length(todo["src"])
            try:
                mtime = os.path.getmtime(todo["src"])
            except OSError:
                continue
            with self.lock:
                self.state["dur"][todo["key"]] = [mtime, n]
            self.dirty = True
        self.save_state()

    # -- photo thumbnails ----------------------------------------------------
    THUMB = (144, 108)

    def thumb(self, path):
        """Thumbnail from memory or disk cache, or None if not made yet."""
        im = self.thumbs.get(path)
        if im is not None:
            return im
        fn = os.path.join(CACHE_DIR, "thumbs", cache_name(path, ".jpg"))
        if os.path.exists(fn):
            from PIL import Image
            try:
                im = Image.open(fn)
                im.load()
                self.keep_thumb(path, im)
                return im
            except OSError:
                pass
        return None

    def has_thumb(self, path):
        return path in self.thumbs or os.path.exists(
            os.path.join(CACHE_DIR, "thumbs", cache_name(path, ".jpg")))

    def keep_thumb(self, path, im):
        self.thumbs[path] = im
        if len(self.thumbs) > 300:
            self.thumbs.pop(next(iter(self.thumbs)))

    def thumb_loop(self):
        from PIL import Image, ImageOps
        os.makedirs(os.path.join(CACHE_DIR, "thumbs"), exist_ok=True)
        failed = set()
        pi = self.tab_index("photos")
        while self.active:
            if self.proc_owns_screen() or self.view not in ("list", "help"):
                time.sleep(0.5)
                continue
            items = self.tab_items(pi)
            start = self.tops.get(pi, 0) * self.GRID_COLS
            order = list(range(start, len(items))) + list(range(0, start))
            todo = next((items[k]["src"] for k in order
                         if items[k]["src"] not in failed and not self.has_thumb(items[k]["src"])),
                        None)
            if todo is None:
                time.sleep(1)
                continue
            try:
                im = Image.open(todo)
                im.draft("RGB", (self.THUMB[0] * 2, self.THUMB[1] * 2))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im = ImageOps.fit(im, self.THUMB, Image.BILINEAR)
                im.save(os.path.join(CACHE_DIR, "thumbs", cache_name(todo, ".jpg")), quality=85)
                self.keep_thumb(todo, im)
                if self.tab == pi:
                    self.dirty = True
            except Exception:
                failed.add(todo)

    # -- mode ----------------------------------------------------------------
    def proc_owns_screen(self):
        return bool(self.proc) and self.kind in SCREEN_KINDS

    def enter(self):
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401
            import numpy  # noqa: F401
            self.load_fonts()
            self.fb = Framebuffer()
        except Exception as ex:      # missing package or no framebuffer
            print(f"media mode unavailable: {ex}", flush=True)
            self.fb = None
            return
        self.active = True
        self.camera.listen()                           # PiE-inks say they're there: asked first for what they have
        if self.view not in ("photo", "pdf", "text"):
            self.view = "home"
            apps = self.home_apps()
            self.home_sel = next((k for k, a in enumerate(apps) if a[1] == self.strip_tab()), 0)
        for i, tab in enumerate(LIBRARY):
            if tab["type"] not in ("channels", "camera", "system", "plex") or i == self.tab:
                self.load_tab(i)
        try:
            vt = subprocess.run(["fgconsole"], capture_output=True, text=True)
            self.prev_vt = vt.stdout.strip() or "1"
        except OSError:
            pass
        subprocess.run(["chvt", str(MEDIA_VT)])
        try:
            self.ttyfd = os.open(f"/dev/tty{MEDIA_VT}", os.O_RDWR | os.O_NOCTTY)
            fcntl.ioctl(self.ttyfd, 0x4B3A, 1)   # KDSETMODE KD_GRAPHICS: no text/cursor
        except OSError:
            pass
        self.dirty = True
        if not (self.prober and self.prober.is_alive()):
            self.prober = threading.Thread(target=self.probe_loop, daemon=True)
            self.prober.start()

    def leave(self):
        """Back to the terminal. Music and radio keep playing; video stops."""
        if not self.active:
            return
        if self.learn:                                 # the controller's buttons go back to keys
            self.cancel_learn("")
        self.picking = None                            # (nothing left half-open for next time)
        self.friend_more = None
        self.confirm = (None, 0.0)
        self.camera.stop()
        self.voice.stop(unload=True)
        self.crypto.stop()
        self.hass.stop()
        self.remote_more = None
        if self.remote_pad is not None:
            self.close_pad()
        if self.view == "keys":
            self.close_keyboard(False)
        if self.kind not in LISTEN_KINDS:
            self.stop()
        self.active = False
        self.save_state()
        if self.ttyfd is not None:
            try:
                fcntl.ioctl(self.ttyfd, 0x4B3A, 0)   # KD_TEXT
                os.close(self.ttyfd)
            except OSError:
                pass
            self.ttyfd = None
        if self.fb:
            self.fb.close()
            self.fb = None
        subprocess.run(["chvt", self.prev_vt])

    def shutdown(self):
        self.stop()
        self.close_viewer()
        self.camera.stop()
        if self.active and self.fb is not None and system_stopping():
            self.goodbye()                 # the Pi is going off (the power switch, say): say so
            return
        self.leave()

    def power_off(self):
        """The case's power switch is off: the Pi shuts down, as with Shut down in the menu. In
        media mode the screen says so; in the terminal the Pi's own shutdown lines show there."""
        if time.monotonic() < self.halting:
            return                                     # on its way already
        print("power switch: off, shutting down", flush=True)
        self.halting, self.halt_note = time.monotonic() + HALT_WAIT, "The Pi didn't shut down"
        try:
            if self.active and self.fb is not None:
                if self.learn:
                    self.cancel_learn("")
                self.stop()                            # (a video would draw over it)
                self.close_viewer()
                self.camera.stop()
                self.voice.stop(unload=True)
                self.goodbye()
            else:
                show_shutdown_lines()                  # first: systemd may be on its way already
                self.save_state()                      # (music stops as the service does)
        finally:
            if not system_stopping():                  # (unless systemd-logind saw it first)
                try:
                    subprocess.Popen(["systemctl", "poweroff"], stdin=subprocess.DEVNULL)
                except OSError as ex:
                    print(f"power switch: couldn't shut down ({ex})", flush=True)

    def goodbye(self):
        """'Shutting down' on the screen, left there until the power goes."""
        try:
            self.save_state()
            img, d = self.canvas()
            W, H = self.fb.w, self.fb.h
            d.text((W / 2, H / 2), "Shutting down", font=self.fonts["big"], fill=TEXT, anchor="mm")
            self.fb.show(img)
        except Exception:
            self.leave()

    # -- opening things ------------------------------------------------------
    def open_item(self, items, i):
        it = items[i]
        kind = it["kind"]
        if (self.web_guard and kind in FILE_KINDS and str(it.get("src", "")).startswith("/")
                and not self.web_may_see(it["src"])):
            self.toast("The web page can't open that", 3)
            return
        if kind in ("dir", "up"):
            self.browse(it["src"], select=self.cwd if kind == "up" else None)
        elif kind == "child":
            self.tab = int(it["src"])
            self.load_tab(self.tab)
        elif kind == "radiodir":
            self.radio_open(it["src"], it["title"])
        elif kind == "chdir":
            self.open_dir(self.tab, it)
        elif kind == "chplex":                          # off to Plex to sign in
            self.chan_stack[self.tab] = []
            self.tab = self.tab_index("plex")
            self.load_tab(self.tab)
        elif kind == "chretry":
            self.live_wait.pop(self.tab, None)
            self.load_tab(self.tab)
        elif kind == "chwait":
            pass
        elif kind == "chsearch":
            self.open_keyboard("Search channels", "", self.chan_search)
        elif kind == "plexsearch":
            live = it["src"] == "livesearch"
            self.open_keyboard("Search channels" if live else "Search Plex", "",
                               lambda q, live=live: self.plex_open(("livesearch:" if live else "search:") + q,
                                                                   f"“{q}”"))
        elif kind == "radiosearch":
            self.open_keyboard("Station name", "", lambda text: self.radio_open("search:" + text, f"“{text}”"))
        elif kind == "plexwant":
            self.toast("That one isn't on your Plex server")
        elif kind == "plexdir":
            self.plex_open(it["src"], it["title"], context=it.get("ptype", ""))
        elif kind in ("video", "audio", "live", "radio", "plexvideo"):
            same = [x for x in items if x["kind"] == kind]
            self.play(same, same.index(it))
        elif kind == "image":
            pics = [x["src"] for x in items if x["kind"] == "image"]
            self.open_photo(pics, pics.index(it["src"]))
        elif kind == "pdf":
            self.open_pdf(it["src"])
        elif kind == "doc":
            self.open_doc(it["src"])
        elif kind == "action":
            self.system_action(it)
        elif kind == "info":
            pass
        elif kind == "text" or looks_like_text(it["src"]):
            self.open_text(it["src"])
        else:
            self.toast("Can't open this kind of file")

    def system_action(self, it):
        act = it["src"]
        waiting, until = self.confirm
        if waiting != act or time.monotonic() > until:
            self.confirm = (act, time.monotonic() + 4)
            self.dirty = True
            return
        self.confirm = (None, 0.0)
        if act == "plex_signout":
            self.plex.sign_out()
            self.plex_stack = []
            self.items[self.tab_index("plex")] = []
            self.toast("Signed out of Plex")
            return
        self.halting = time.monotonic() + HALT_WAIT       # nothing draws over it
        self.halt_note = {"reboot": "The Pi didn't restart", "poweroff": "The Pi didn't shut down",
                          "restart": "Media mode didn't restart"}[act]
        self.render_wait({"reboot": "Rebooting", "poweroff": "Shutting down",
                          "restart": "Restarting media mode"}[act], "One moment")
        self.save_state()
        cmd = {"reboot": ["systemctl", "reboot"], "poweroff": ["systemctl", "poweroff"],
               "restart": ["systemctl", "restart", "gpi-keys"]}[act]
        subprocess.Popen(cmd)

    def close_viewer(self):
        tmp = self.v.get("tmp")
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        self.v = {}
        self.view = "list"
        self.dirty = True

    # photos
    def open_photo(self, paths, i):
        self.close_viewer()
        self.v = {"type": "photo", "items": paths, "i": i, "zoom": 1, "rot": 0,
                  "img": None, "img_for": None, "cx": 0, "cy": 0,
                  "slideshow": False, "next_t": 0,
                  "edit": False, "fi": 0, "prev": {}, "confirm": False, "busy": None,
                  "changed": False}
        self.view = "photo"
        self.dirty = True

    def photo_image(self):
        from PIL import Image, ImageOps
        v = self.v
        key = (v["items"][v["i"]], v["rot"])
        if v["img_for"] != key:
            v["img_for"] = key
            try:
                im = Image.open(key[0])
                im.draft("RGB", (1280, 960))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1600, 1200))
                if v["rot"]:
                    im = im.rotate(-90 * v["rot"], expand=True)
            except Exception:
                im = None
            v["img"] = im
            if im:
                v["cx"], v["cy"] = im.width / 2, im.height / 2
        return v["img"]

    def photo_step(self, d):
        v = self.v
        v["i"] = (v["i"] + d) % len(v["items"])
        v["zoom"], v["rot"] = 1, 0
        self.dirty = True

    PREVIEW_STRIP = 52                  # the filter names under the picture while editing

    def photo_preview(self, size):
        """The picture as it's shown, with the chosen filter on (kept per filter).
        Worked out on a thread — the drawn filters take a moment on a Pi Zero —
        showing the last one meanwhile."""
        from PIL import Image
        v = self.v
        im = self.photo_image()
        if im is None:
            return None
        fid = FILTERS[v["fi"]][0]
        key = (v["img_for"], fid, size)
        if key in v["prev"]:
            v["shown"] = v["prev"][key]
            return v["shown"]
        if v.get("working") != key:
            v["working"] = key
            base = im.copy()
            base.thumbnail(size)

            def job():
                try:
                    if fid in FILTER_CSS:
                        out = apply_filter(base, fid)
                    else:                              # drawn: a smaller one, scaled up
                        small = base.copy()
                        small.thumbnail((400, 400))
                        out = apply_filter(small, fid).resize(base.size, Image.BILINEAR)
                except Exception:
                    out = base
                v["prev"][key] = out
                if v.get("working") == key:
                    v["working"] = None
                self.dirty = True
            threading.Thread(target=job, daemon=True, name="photo-preview").start()
        shown = v.get("shown")
        if shown is None or v.get("shown_for") != v["img_for"]:
            shown = im.copy()
            shown.thumbnail(size)
        v["shown_for"] = v["img_for"]
        return shown

    def photo_save_copy(self):
        """A: the filter (and the turn) onto the full-size picture, kept as a copy
        next to it — or in ~/Pictures for one outside your home folder."""
        v = self.v
        fid, label = FILTERS[v["fi"]]
        rot = v["rot"]
        if fid == "none" and not rot:
            self.toast("Pick a filter with ◀ ▶ first", 2)
            return
        src = v["items"][v["i"]]
        v["busy"] = "Saving…"

        def job():
            from PIL import Image, ImageOps
            import io
            try:
                im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
                if rot:
                    im = im.rotate(-90 * rot, expand=True)
                im = apply_filter(im, fid)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=92, optimize=True)
                folder = os.path.dirname(src) if in_home(src) else pictures_dir()
                stem = os.path.splitext(os.path.basename(src))[0]
                path = write_new(folder, f"{stem}-{fid if fid != 'none' else 'turned'}", ".jpg",
                                 buf.getvalue())
                if self.v is v:
                    v["items"].insert(v["i"], path)
                    v.update(edit=False, fi=0, rot=0, zoom=1, changed=True)
                self.last_shot = path
                self.toast(f"Saved {os.path.basename(path)}", 3)
            except Exception as ex:
                self.toast(f"Couldn't save it ({getattr(ex, 'strerror', None) or ex})"[:70], 4)
            finally:
                v["busy"] = None
                self.dirty = True
        threading.Thread(target=job, daemon=True, name="photo-save").start()

    def photo_delete(self):
        v = self.v
        v["confirm"] = False
        path = v["items"][v["i"]]
        try:
            os.remove(path)
        except OSError as ex:
            self.toast(f"Couldn't delete it ({ex.strerror or ex})", 4)
            return
        v["items"].pop(v["i"])
        v["changed"] = True
        self.toast("Deleted", 2)
        if not v["items"]:
            self.photo_back()
            return
        v["i"] %= len(v["items"])
        v["zoom"], v["rot"] = 1, 0

    # pdfs
    def open_pdf(self, path, title=None):
        self.close_viewer()
        try:
            r = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=20)
            pages = int(re.search(r"^Pages:\s+(\d+)", r.stdout, re.M).group(1))
        except Exception:
            self.toast("Can't open this PDF (is poppler-utils installed?)")
            return
        self.v = {"type": "pdf", "path": path, "title": title or os.path.basename(path),
                  "page": 1, "pages": pages, "fit": "width", "scroll": 0,
                  "zoom": 1.0, "sx": 0,
                  "cache": {}, "tmp": tempfile.mkdtemp(prefix="gpi-pdf-")}
        self.view = "pdf"
        self.dirty = True

    def pdf_image(self, page=None):
        from PIL import Image
        v = self.v
        page = page or v["page"]
        key = (page, v["fit"], v["zoom"])
        if key not in v["cache"]:
            W, H = self.fb.w, self.fb.h - self.FOOTER
            size = (["-scale-to-x", str(int(W * v["zoom"])), "-scale-to-y", "-1"]
                    if v["fit"] == "width" else ["-scale-to-x", "-1", "-scale-to-y", str(H)])
            out = os.path.join(v["tmp"], f"p{page}{v['fit'][0]}{int(v['zoom'] * 100)}")
            try:
                subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
                                "-png", "-aa", "yes", "-aaVector", "yes"] + size
                               + [v["path"], out], timeout=60, check=True,
                               capture_output=True)
                im = Image.open(out + ".png").convert("RGB")
                os.remove(out + ".png")
            except Exception:
                im = None
            v["cache"][key] = im
            if len(v["cache"]) > 6:
                v["cache"].pop(next(iter(v["cache"])))
        return v["cache"][key]

    def pdf_goto(self, page, at_bottom=False):
        v = self.v
        page = max(1, min(page, v["pages"]))
        if page == v["page"]:
            return
        self.render_wait(v["title"], f"Page {page}")
        v["page"] = page
        v["scroll"] = 0
        if at_bottom:
            im = self.pdf_image()
            v["scroll"] = max(im.height - (self.fb.h - self.FOOTER), 0) if im else 0
        self.dirty = True

    # documents
    def open_doc(self, path):
        if shutil.which("soffice"):
            pdf = os.path.join(CACHE_DIR, "docs", cache_name(path, ".pdf"))
            if os.path.exists(pdf):
                self.open_pdf(pdf, os.path.basename(path))
                return
            self.close_viewer()
            self.v = {"type": "wait", "title": os.path.basename(path), "src": path,
                      "status": "Converting (the first time takes a while)", "result": None}
            self.view = "wait"
            self.dirty = True
            threading.Thread(target=self.convert_doc, args=(self.v, path, pdf),
                             daemon=True).start()
            return
        try:
            self.open_text(path, text=doc_text(path))
        except Exception:
            ext = os.path.splitext(path)[1].lower()
            self.toast("Install LibreOffice to open " + ext + " files" if ext in (".doc", ".xls", ".ppt")
                       else "Couldn't read this document")

    def convert_doc(self, v, path, pdf):
        out = tempfile.mkdtemp(prefix="gpi-doc-")
        try:
            os.makedirs(os.path.join(CACHE_DIR, "lo-home"), exist_ok=True)
            subprocess.run(["nice", "-n", "5", "soffice", "--headless", "--norestore",
                            "--convert-to", "pdf", "--outdir", out, path],
                           timeout=600, capture_output=True,
                           env=dict(os.environ, HOME=os.path.join(CACHE_DIR, "lo-home")))
            made = glob.glob(os.path.join(out, "*.pdf"))
            if made:
                os.makedirs(os.path.dirname(pdf), exist_ok=True)
                shutil.move(made[0], pdf)
                v["result"] = pdf
            else:
                v["result"] = "fail"
        except Exception:
            v["result"] = "fail"
        finally:
            shutil.rmtree(out, ignore_errors=True)

    # text
    def open_text(self, path, text=None):
        if text is None:
            try:
                with open(path, "rb") as f:
                    raw = f.read(TEXT_LIMIT)
                text = raw.decode("utf-8", errors="replace")
                if len(raw) == TEXT_LIMIT:
                    text += "\n\n[ file continues; only the first 2 MB is shown ]"
            except OSError:
                self.toast("Can't read that file")
                return
        self.close_viewer()
        self.v = {"type": "text", "title": os.path.basename(path), "text": text,
                  "size": 0, "lines": None, "top": 0}
        self.view = "text"
        self.dirty = True

    def text_lines(self):
        v = self.v
        if v["lines"] is None:
            font = self.fonts["mono_s" if v["size"] == 0 else "mono_l"]
            cols = max(int((self.fb.w - 40) / font.getlength("M")), 10)
            lines = []
            for raw in v["text"].expandtabs(4).splitlines():
                lines += textwrap.wrap(raw, cols, drop_whitespace=False,
                                       replace_whitespace=False) or [""]
                if len(lines) > 40000:
                    lines.append("[ too long to show the rest ]")
                    break
            v["lines"] = lines
        return v["lines"]

    def text_rows(self):
        lh = 20 if self.v.get("size", 0) == 0 else 26
        return max((self.fb.h - self.FOOTER - self.LIST_TOP) // lh, 1), lh

    # -- player --------------------------------------------------------------
    def cmd(self, c):
        try:
            self.proc.stdin.write(c + "\n")
            self.proc.stdin.flush()
        except (OSError, AttributeError, ValueError):
            pass

    def next_screen(self):
        """Y while a video plays: full screen on or off, kept for the next videos too (Settings >
        Video size picks zoomed or stretched). The player starts again where it was: mplayer
        can't change its scaling as it plays."""
        cur = self.setting("screen")
        if cur == "Fit":
            mode = self.state["settings"].get("full")
            mode = mode if mode in SCREEN_MODES[1:] else "Full screen"
        else:
            mode = "Fit"
            self.state["settings"]["full"] = cur              # the next Y brings this one back
        self.state["settings"]["screen"] = mode
        self.save_state()
        self.screen_note = (mode, time.monotonic() + 4)
        if self.kind == "plex":
            self.plex_restart(self.plex_now())
        elif self.kind == "live":
            self.play(self.queue, self.qi, start=0)
        else:
            self.play(self.queue, self.qi, start=max(self.pos or 0, 0) + 3)

    def osd(self, text, ms=1500):
        self.cmd(f'osd_show_text "{text}" {ms}')

    def reader(self, p):
        for line in p.stdout:
            if p is not self.proc:
                continue
            if "StreamTitle='" in line:            # song name from internet radio
                m = re.search(r"StreamTitle='(.*?)';", line)
                if m and m.group(1).strip():
                    self.meta["song"] = m.group(1).strip()
                    self.dirty = True
                continue
            if not line.startswith("ANS_"):
                continue
            k, _, v = line.strip().partition("=")
            v = v.strip("'")
            if k == "ANS_VIDEO_RESOLUTION":
                m = re.search(r"(\d+)\s*x\s*(\d+)", v)
                if m and int(m.group(2)):
                    self.vsize = (int(m.group(1)), int(m.group(2)))
                continue
            if k in ("ANS_TIME_POSITION", "ANS_LENGTH"):
                try:
                    if k == "ANS_TIME_POSITION":
                        self.pos = float(v)
                    else:
                        self.meta["length"] = float(v)
                except ValueError:
                    pass
            elif k in ("ANS_META_TITLE", "ANS_META_ARTIST") and v:
                self.meta[k[9:].lower()] = v
                self.dirty = True

    def spawn(self, args, target):
        self.started = time.monotonic()
        self.voice.stop(unload=True)                   # (the player has the sound, and the memory)
        args = list(args)
        if "-ao" in args:                              # Settings > Sound
            args[args.index("-ao") + 1] = sound_device(self.setting("sound"))
        if self.fb and self.kind in SCREEN_KINDS and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()                       # the picture covers the menus' black edges
        self.proc = subprocess.Popen(
            args + [target], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            preexec_fn=lambda: os.nice(PLAYER_NICE))
        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()

    def screen_dims(self):
        """The real screen's size (the menus are drawn at 640x480 and scaled to it)."""
        return getattr(self.fb, "real_w", 640), getattr(self.fb, "real_h", 480)

    def video_args(self):
        w, h = self.screen_dims()
        args = VIDEO_PLAYER + video_scale(self.setting("screen"), self.vsize, w, h)
        if (w, h) != (640, 480) and slow_pi():
            args += ["-sws", "0"]              # the quicker way up to a big screen
        return args

    def play(self, queue, i, start=None):
        if queue[i]["kind"] == "plexvideo":
            return self.play_plex(queue, i)
        self.stop()
        it = queue[i]
        self.queue, self.qi = queue, i
        kind = it["kind"]
        if start is None:
            start = self.resume_at(it)
            self.vsize = None
        if kind in LISTEN_KINDS:
            self.close_viewer()
            self.view, self.now_from = "now", "list"
        elif self.active:
            status = (f"Resuming at {clock(start)}" if start else
                      "Connecting" if kind == "live" or it["src"].startswith("ia:")
                      else "Starting")
            self.render_wait(it["title"], status, playing=True)
        plexlive = it["src"].startswith("plexlive:")
        try:
            target = (self.plex.live_url(it["src"][len("plexlive:"):]) if plexlive
                      else resolve(it))
        except Exception:
            self.view = "list"
            self.toast("Couldn't load that. Check the WiFi connection.")
            return
        if kind == "live" and not plexlive and is_hls(target):     # the version that suits the Pi
            target = hls_pick(target)
        net = "://" in target
        args = list(AUDIO_PLAYER if kind in LISTEN_KINDS else self.video_args())
        if kind == "radio":
            args += RADIO_CACHE
        elif plexlive:
            args += PLEX_CACHE
        else:
            args += NET_CACHE if net else ([] if kind == "audio" else LOCAL_CACHE)
        args += ["-volume", str(self.volume)]
        if start:
            args += ["-ss", str(int(max(start - 3, 0)))]
        self.retry = None
        if kind == "radio":
            if target.startswith("https://"):
                # plain http lets mplayer show the song name; fall back to https if refused
                self.retry = (args, "ffmpeg://" + target)
                target = "http://" + target[len("https://"):]
        elif net:
            target = "ffmpeg://" + target        # lets mplayer open https and HLS
        self.kind, self.cur, self.pos, self.meta, self.paused = kind, it, start, {}, False
        self.next_query = time.monotonic() + 1
        if kind == "radio" and it.get("uuid"):          # Radio Browser counts what people play
            threading.Thread(target=lambda u=it["uuid"]: rb_get(f"/json/url/{u}"), daemon=True).start()
        self.spawn(args, target)
        if kind == "audio":
            for c in ("get_meta_title", "get_meta_artist", "get_time_length"):
                self.cmd(c)
        elif kind not in LISTEN_KINDS:
            self.cmd("get_video_resolution")
            if kind == "video":
                self.cmd("get_time_length")
        self.dirty = True

    def play_plex(self, queue, i, start=None):
        it = queue[i]
        self.stop()
        self.queue, self.qi = queue, i
        if start is None:
            near_end = it["dur"] and it["off"] > it["dur"] - 30
            start = it["off"] if it["off"] > 10 and not near_end else 0
        if self.active:
            self.render_wait(it["title"], f"Resuming at {clock(start)}" if start
                             else "Getting it ready on your Plex server", playing=True)
        self.plex_start(it, start)

    def plex_start(self, it, start):
        session = uuid.uuid4().hex
        url = self.plex.stream_url(it["src"], start, session)
        args = self.video_args() + PLEX_CACHE + ["-volume", str(self.volume)]
        self.kind, self.cur, self.meta, self.paused = "plex", it, {}, False
        self.plex_session, self.plex_base, self.plex_mode = session, start, None
        self.next_vsize = True
        self.plex_last, self.pos, self.retry = start, -1.0, None
        self.next_query = time.monotonic() + 3
        self.next_timeline = time.monotonic() + 5
        self.spawn(args, "ffmpeg://" + url)

    def plex_now(self):
        """Where you are in the Plex video, in seconds from its start."""
        if self.plex_mode is None or self.pos < 0:
            return self.plex_last
        return self.pos if self.plex_mode == "abs" else self.plex_base + self.pos

    def plex_seek(self, delta, absolute=None):
        """Plex seeks restart the stream, so quick presses are added up first."""
        cur = self.plex_pending if self.plex_pending is not None else self.plex_now()
        target = absolute if absolute is not None else cur + delta
        length = self.cur.get("dur") or 0
        target = max(0, min(target, length - 5) if length else target)
        self.plex_pending, self.plex_pending_t = target, time.monotonic() + 0.8
        self.osd(f"Go to {clock(target)}" + (f" of {clock(length)}" if length else ""), 1500)

    def plex_restart(self, target):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.kill()
        threading.Thread(target=self.plex.stop_transcode, args=(self.plex_session,),
                         daemon=True).start()
        self.plex_start(self.cur, target)

    def plex_finish(self, it, pos, session, done):
        """Tell Plex where you stopped (or that you finished) and end the conversion."""
        if not it:
            return
        it["off"] = 0 if done else pos
        it["watched"] = it.get("watched") or done

        def report():
            self.plex.timeline(it["src"], "stopped", pos, it.get("dur"))
            if done:
                self.plex.scrobble(it["src"])
            self.plex.stop_transcode(session)
        threading.Thread(target=report, daemon=True).start()

    def remember(self, finished=False):
        it, self.cur = self.cur, None
        if not it or it["kind"] != "video":
            return
        with self.lock:
            if finished:
                self.state["pos"][it["key"]] = -1
            elif self.pos > 5:
                self.state["pos"][it["key"]] = round(self.pos, 1)
        self.save_state()

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.write("quit\n")
                p.stdin.flush()
                p.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                p.kill()
        if self.kind == "plex" and self.cur:
            pos, length = self.plex_now(), self.cur.get("dur") or 0
            self.plex_finish(self.cur, pos, self.plex_session, bool(length) and pos > length * 0.9)
            self.cur = None
            self.plex_pending = None
        self.remember()
        self.kind = None
        self.retry = None

    def next_index(self, d):
        n = len(self.queue)
        if not n:
            return None
        if self.kind in ("radio", "live"):          # channel up/down wraps around
            return (self.qi + d) % n
        if self.kind == "audio" and self.shuffle and d > 0 and n > 1:
            return random.choice([i for i in range(n) if i != self.qi])
        i = self.qi + d
        return i if 0 <= i < n else None

    def skip(self, d):
        i = self.next_index(d)
        if i is not None:
            self.play(self.queue, i)
        else:
            self.stop()
            self.view = "list"
            self.dirty = True

    def tick(self):
        """Called every loop: track position, move on when something ends."""
        now = time.monotonic()
        if self.learn:
            self.learn_tick(now)
        note = getattr(self, "screen_note", None)
        if note and self.proc and self.kind not in LISTEN_KINDS and now - self.started > 1.5:
            self.screen_note = None
            if now < note[1]:
                self.osd(SCREEN_SAY.get(note[0], note[0]), 1500)
            if not self.vsize:
                self.cmd("get_video_resolution")
        if self.proc and self.active and self.fb and self.proc_owns_screen() and self.vsize \
                and now - self.started > 1 and self.proc.poll() is None:
            bars = (id(self.proc), self.vsize, self.setting("screen"))
            if bars != self.bars_for:
                self.bars_for = bars
                sw, sh = self.screen_dims()
                whole = fit_box(self.vsize, sw, sh, inset=0) if bars[2] == "Fit" else None
                if whole and whole != (0, 0, sw, sh) and hasattr(self.fb, "blank_outside"):
                    try:                                  # black bars, not the menu, round the picture
                        self.fb.blank_outside(fit_box(self.vsize, sw, sh))
                    except (OSError, ValueError, ZeroDivisionError):
                        pass
        if getattr(self, "next_vsize", False) and self.proc and now - self.started > 2:
            self.next_vsize = False
            self.cmd("get_video_resolution")
        if self.msg and now > self.msg_until:
            self.msg = None
            self.dirty = True
        if self.confirm[0] and now > self.confirm[1]:
            self.confirm = (None, 0.0)
            self.dirty = True
        if self.halting and now >= self.halting:       # still here: it didn't go
            self.halting = 0.0
            self.toast(self.halt_note, 4)
        if self.active and self.view == "list" and self.tab_type() == "remote" \
                and 0.25 <= now - self.remote_hit[1] < 0.6:
            self.dirty = True                         # let the pressed button go dark again
        if self.active and (self.view == "home" or (self.view == "list" and self.tab_type() == "weather")):
            self.weather.refresh(full=self.view == "list")   # only does anything when it's due
        if self.voice_arrived:
            self.voice_use(self.voice_arrived)
        if self.voice.error and self.voice.error != self.voice_told:
            self.voice_told = self.voice.error
            if self.on_friend_page() or (self.view == "list" and self.tab_type() == "settings"
                                         and self.set_page in FRIEND_PAGES):
                self.toast(self.voice.error, 5)
        elif not self.voice.error:
            self.voice_told = ""
        if self.on_friend_page():
            fr = self.friend
            gap = fr.chatter() * 60
            if gap and fr.ready() and not fr.busy and \
                    time.time() - max(fr.last_said(), self.friend_opened_at) >= gap * self.friend_jitter:
                fr.remark(self.friend_topic())
                self.friend_jitter = random.uniform(0.7, 1.3)
        if self.on_camera_page():
            if self.camera.check_hold():
                self.dirty = True
            told = self.cam_bot
            if told and not told["busy"]:
                if told["spoken"] and self.voice.speaking:
                    told["until"] = max(told["until"], now + 3)
                elif told["until"] <= now < told["until"] + 1:
                    self.dirty = True                 # what the bot said has had its turn
            shot = self.camera.shot
            if shot and shot[2] + CAM_SHOT_SHOW <= now < shot[2] + CAM_SHOT_SHOW + 1:
                self.dirty = True                     # time to take the little picture away
            if self.camera.action and 3 <= now - self.cam_said[1] < 7:
                self.dirty = True                     # and a message that has had its turn
        if (self.crypto_auto and self.active and self.view == "list"
                and self.tab_type() == "crypto" and now >= self.crypto_next):
            self.press_crypto("right", False)
        if self.plex.pin and self.active and self.tab_type() == "plex" and now >= self.next_status:
            self.dirty = True
        if self.active and now >= self.next_status and self.view in self.STATUS_VIEWS:
            self.next_status = now + 2
            sig = self.status_signature()
            if sig != self.status_sig:
                self.status_sig = sig
                self.dirty = True
        v = self.v
        if self.view == "photo" and v.get("slideshow") and now >= v["next_t"]:
            self.photo_step(1)
            v["next_t"] = now + SLIDESHOW_SECS
        if self.view == "wait" and v.get("result"):
            if v["result"] == "fail":
                src = v["src"]
                self.close_viewer()
                try:
                    self.open_text(src, text=doc_text(src))
                except Exception:
                    self.toast("Couldn't open this document")
            else:
                self.open_pdf(v["result"], v["title"])
        if not self.proc:
            return
        if self.kind == "plex" and self.proc.poll() is None:
            if self.plex_mode is None and self.pos >= 0:
                base = self.plex_base
                self.plex_mode = "abs" if base > 30 and self.pos >= base - 10 else "rel"
            if self.plex_mode:
                self.plex_last = self.plex_now()
            if self.plex_pending is not None and now >= self.plex_pending_t:
                target, self.plex_pending = self.plex_pending, None
                self.plex_restart(target)
                return
            if now >= self.next_timeline:
                self.next_timeline = now + PLEX_TIMELINE_SECS
                threading.Thread(target=self.plex.timeline, daemon=True,
                                 args=(self.cur["src"], "paused" if self.paused else "playing",
                                       self.plex_now(), self.cur.get("dur"))).start()
        if self.proc.poll() is not None and self.kind == "plex":
            it, quick = self.cur, now - self.started < 8
            pos, length = self.plex_now(), (self.cur or {}).get("dur") or 0
            done = bool(length) and pos > length * 0.9
            self.proc = None
            self.plex_finish(it, pos, self.plex_session, done)
            self.kind, self.cur = None, None
            if quick:
                self.toast("Plex couldn't play this one", 5)
            elif not done:
                self.toast("Playback stopped. Press A to pick up where you left off", 5)
            nxt = self.qi + 1
            if done and it and it.get("ptype") == "episode" and nxt < len(self.queue):
                self.play_plex(self.queue, nxt, start=0)       # on to the next episode
            else:
                self.view = "list"
                self.dirty = True
            return
        if self.proc.poll() is not None:
            was = self.kind
            quick = now - self.started < 8
            self.proc = None
            if quick and self.retry:              # try the backup way once
                args, target = self.retry
                self.retry = None
                self.spawn(args, target)
                return
            online = bool(self.cur) and self.cur["src"].startswith("ia:")
            self.remember(finished=not quick)
            i = None if was in ("live", "radio") or (quick and online) else self.next_index(1)
            if was in ("live", "radio") and quick:
                self.toast("Couldn't play that stream")
            elif quick and online:                      # not on to the next: it'd likely fail too
                self.toast("Couldn't play that one. Check the WiFi, or try another", 5)
            if i is not None:
                self.play(self.queue, i)
            else:
                self.kind = None
                self.view = "list"
                self.dirty = True
        elif now >= self.next_query and self.kind in ("audio", "video", "plex"):
            self.cmd("pausing_keep_force get_time_pos")
            self.next_query = now + (1 if self.kind == "audio" else 2)
            if self.kind == "audio" and self.view == "now":
                self.dirty = True

    def set_volume(self, d):
        self.volume = max(0, min(100, self.volume + d))
        self.cmd(f"pausing_keep volume {self.volume} 1")
        self.dirty = True

    # -- buttons -------------------------------------------------------------
    def crypto_focus(self):
        cards = self.crypto.cards()
        self.crypto.focus = cards[self.crypto_card % len(cards)] if cards else None

    def crypto_changed(self):
        if self.active and self.view == "list" and self.tab_type() == "crypto":
            self.dirty = True

    def press_crypto(self, name, repeat):
        cards = self.crypto.cards()
        if name in ("left", "right") and cards:
            self.crypto_card = (self.crypto_card + (1 if name == "right" else -1)) % len(cards)
            self.crypto_focus()
            self.crypto_next = time.monotonic() + CRYPTO_ROTATE
        elif name in ("up", "down") and not repeat:
            days = [d for d, _ in CRYPTO_WINDOWS]
            i = days.index(self.crypto.days) if self.crypto.days in days else 0
            self.crypto.days = days[(i + (1 if name == "up" else -1)) % len(days)]
        elif name == "a" and not repeat:
            self.crypto_auto = not self.crypto_auto
            self.crypto_next = time.monotonic() + CRYPTO_ROTATE
            self.toast("Auto: a new card every 20 seconds" if self.crypto_auto else "Auto off", 2)
        elif name == "x" and not repeat:
            self.crypto.force = True
            self.toast("Refreshing", 2)
        self.dirty = True
        return None

    # TV Remote
    def remote_changed(self):
        if self.active and self.view == "list" and self.tab_type() == "remote":
            self.dirty = True

    def remote_options(self):
        st = self.hass.tvstate
        off = st.get("state") in ("off", "standby", "unavailable", "", None)
        opts = [("Number pad", ("pad",)),
                ("Turn on" if off else "Turn off", ("power",)),
                ("Unmute" if st.get("muted") else "Mute", ("mute",)),
                ("Play / pause", ("play",))]
        for src in st.get("sources") or []:
            opts.append((src, ("source", src)))
        return opts

    REMOTE_KEYS = {"up": ("key", "up"), "down": ("key", "down"), "left": ("key", "left"),
                   "right": ("key", "right"), "a": ("key", "ok"), "y": ("key", "back"),
                   "x": ("key", "home"), "l": ("volume", -1), "r": ("volume", 1),
                   "start": ("play",)}

    def press_remote(self, name, repeat):
        """The case's buttons as the TV's remote. 'pass' lets B go back to the TV menu."""
        now = time.monotonic()
        if self.remote_pad is not None:                # the number pad
            return self.press_pad(name, repeat)
        if self.remote_more is not None:               # the More menu
            opts = self.remote_options()
            m = self.remote_more
            if name in ("up", "down"):
                m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % len(opts)
            elif name == "a" and not repeat:
                self.remote_more = None
                job = opts[m["sel"] % len(opts)][1]
                if job == ("pad",):
                    self.open_pad()
                else:
                    self.hass.send(*job)
            elif name in ("b", "select") and not repeat:
                self.remote_more = None
            self.dirty = True
            return None
        if name == "b":
            return "pass"
        if not self.hass.configured:
            return None
        if name == "select" and not repeat:
            self.remote_more = {"sel": 0}
        elif name in self.REMOTE_KEYS:
            if repeat and now - self.remote_hit[1] < HA_HELD:
                return None                            # held: gently, the TV keeps up
            self.hass.send(*self.REMOTE_KEYS[name])
            self.remote_hit = (name, now)
        self.dirty = True
        return None

    # the number pad, for channels
    def open_pad(self):
        self.remote_pad = {"text": "", "r": 0, "c": 1}
        self.keyreader.on_key = self.pad_key            # the BBQ20's numbers work too
        self.keyreader.start()
        self.dirty = True

    def close_pad(self):
        self.remote_pad = None
        self.keyreader.stop()
        self.dirty = True

    def pad_key(self, kind, ch=""):
        """A real keyboard while the number pad is up."""
        pad = self.remote_pad
        if pad is None:
            return
        if kind == "char" and (ch.isdigit() or ch in "-."):
            pad["text"] = (pad["text"] + ("-" if ch in "-." else ch))[:7]
        elif kind == "back":
            pad["text"] = pad["text"][:-1]
        elif kind == "done":
            self.pad_go()
        elif kind == "cancel":
            self.close_pad()
        self.dirty = True

    def pad_go(self):
        pad = self.remote_pad
        if pad and pad["text"].strip("-"):
            self.hass.send("channel", pad["text"].strip("-"))
            self.remote_hit = ("go", time.monotonic())
            self.close_pad()
        else:
            self.toast("Type a channel number first", 2)

    def press_pad(self, name, repeat):
        pad = self.remote_pad
        rows = TV_PAD
        if name in ("up", "down"):
            pad["r"] = (pad["r"] + (1 if name == "down" else -1)) % len(rows)
            pad["c"] = min(pad["c"], len(rows[pad["r"]]) - 1)
        elif name in ("left", "right"):
            n = len(rows[pad["r"]])
            pad["c"] = (pad["c"] + (1 if name == "right" else -1)) % n
        elif name == "a" and not repeat:
            label, what = rows[pad["r"]][pad["c"]]
            if what.isdigit() or what == "dash":
                pad["text"] = (pad["text"] + ("-" if what == "dash" else what))[:7]
            elif what == "del":
                pad["text"] = pad["text"][:-1]
            elif what == "go":
                self.pad_go()
                return None
            else:                                      # channel up/down, last, guide: straight away
                self.hass.send("key", what)
            self.remote_hit = ("pad", time.monotonic())
        elif name in ("l", "r") and not repeat:        # the shoulders change channel here
            self.hass.send("key", "chdown" if name == "l" else "chup")
        elif name == "x" and not repeat:
            pad["text"] = pad["text"][:-1]
        elif name == "start" and not repeat:
            self.pad_go()
            return None
        elif name in ("b", "select") and not repeat:
            self.close_pad()
        self.dirty = True
        return None

    def camera_changed(self):
        """A new picture or camera state arrived (from the camera's threads)."""
        if self.on_camera_page() or self.on_camera_list():
            self.dirty = True
        if self.on_camera_list() and not self.camera.scanning and self.camera.unseen():
            self.camera.scan()                       # one just heard on the network, say

    # -- PiE-ink on another Pi -------------------------------------------------
    def pie_cameras(self):
        """(cameras that answered as PiE-ink, the addresses in camera.txt: a PiE-ink's camera is at the
        Pi's address, so one of them may be a PiE-ink)."""
        cam = self.camera
        sure = [v["url"] for v in list(cam.known.values()) if v.get("kind") == "pie" and v.get("server") == "PiE-ink"]
        return sure, [c["addr"] for c in cam.cams or read_cameras(LIBRARY[self.tab_index("camera")]["files"])]

    # -- the bot ---------------------------------------------------------------
    def friend_files(self):
        return LIBRARY[self.tab_index("friend")]["files"]

    def on_friend_page(self):
        return self.active and self.view == "list" and self.tab_type() == "friend"

    def friend_changed(self):
        """It said something, or started or stopped thinking (from its thread)."""
        if len(self.friend.log) != self.friend_seen:
            self.friend_seen = len(self.friend.log)
            self.friend_scroll = 0                    # back to the newest
        if self.on_friend_page() or (self.active and self.view == "list" and self.tab_type() == "settings"
                                     and self.set_page in FRIEND_PAGES):
            self.dirty = True

    def friend_opened(self):
        fr = self.friend
        self.friend_opened_at = time.time()
        self.friend_scroll = 0
        if fr.ready() and self.bot_voice() and self.bot_speaks() and not self.proc:
            self.voice.warm(self.bot_voice())          # (a voice takes a few seconds to load)
        if fr.ready():
            fr.check_vision()                          # (can it see? for what it says by itself)
        if fr.ready() and not fr.busy and time.time() - fr.last_said() > FRIEND_HELLO_AFTER:
            fr.remark("hello")

    # its voice
    def bot_voice(self):
        """The voice picked in Settings > Bot ("" for none)."""
        return clean_name(self.friend.conf.get("voice"), 80)

    def bot_speaks(self):
        """Its replies said out loud (when it has a voice)."""
        return (self.friend.conf.get("speak") or "on").strip().lower() not in ("off", "no", "0", "false")

    def say_aloud(self, text=None):
        """A reply said out loud: the last one when none is given (not over something playing, which
        has the sound, and the memory). (True, "") or (False, why not)."""
        if self.proc:
            return False, "Not while something's playing"
        if text is None:
            last = next((x for x in reversed(self.friend.log)
                         if x["who"] == "friend" and x.get("kind") != "error"), None)
            if not last:
                return False, "It hasn't said anything yet"
            text = last["text"]
        self.dirty = True
        return self.voice.say(text, self.bot_voice(), aplay_device(self.setting("sound")), self.volume)

    def bot_replied(self, text):
        """It answered (on its own thread): out loud too, when that's set and nothing is playing."""
        if self.bot_voice() and self.bot_speaks() and not self.proc:
            self.say_aloud(text)

    def voice_ready(self, vid):
        """A voice arrived (on its download's thread): the main loop puts it to use."""
        self.voice_arrived = vid
        self.dirty = True

    def voice_use(self, vid):
        """The voice in bot.txt, and a word in it, so you hear how it sounds."""
        self.voice_arrived = None
        if vid != self.voice_want:
            return
        self.voice_want = None
        if self.friend_set(voice=vid):
            self.toast(f"{voice_name(vid)} is ready", 3)
            self.say_aloud(VOICE_SAMPLE)

    def voice_pick(self, vid):
        """A voice chosen (in Settings, or on the web page): used at once if it's on the Pi, fetched
        first if it isn't. (True, what's happening) or (False, why not)."""
        if not vid:
            self.voice_want = None
            self.voice.stop(unload=True)
            return (True, "No voice") if self.friend_set(voice="") else (False, "Couldn't save static/bot.txt")
        if vid in voices_here() and self.voice.have_piper():
            self.voice_want = None
            if not self.friend_set(voice=vid):
                return False, "Couldn't save static/bot.txt"
            self.say_aloud(VOICE_SAMPLE)
            return True, f"Using {voice_name(vid)}"
        if vid not in [i for i, _, _ in BOT_VOICES] and vid not in voices_here():
            return False, "There's no such voice"
        if not self.voice.supported():
            return False, "Piper doesn't run on this Pi"
        job = self.voice.job
        if job:
            return False, f"Still getting {job['what']}"
        self.voice_want = vid
        self.voice.get(vid)
        return True, f"Getting {voice_name(vid)}…"

    def friend_topic(self):
        """Something to talk about: mostly the weather and the time, the coins now and then, and what
        it sees, when it has a camera and a model that can see."""
        fr = self.friend
        fr.check_vision()
        topic = random.choice(FRIEND_TOPICS + (["sight"] * FRIEND_SIGHT if fr.sees() and self.friend_camera() else []))
        if topic == "weather" and not self.weather.data:
            topic = "time"
        if topic == "coins" and not any((self.crypto.quotes.get(c["id"]) or {}).get("d") for c in self.crypto.coins):
            topic = "anything"
        if topic == "playing" and not (self.proc and self.cur):
            topic = "anything"
        return topic

    def friend_facts(self):
        """What's true right now, for it to talk about."""
        t = time.localtime()
        lines = [f"Time: {time.strftime('%A', t)} {self.clock_text(t)}"]
        loc = self.setting("location")
        if loc:
            lines.append(f"Where you are: {place_text(loc)}")
        w = self.weather.data
        try:
            if w and w.get("temp") is not None:
                u = w.get("units") or "F"
                lines.append(f"Weather now: {round(w['temp'])}°{u}, {wx_words(w.get('code'))[0].lower()}, "
                             f"feels like {round(w.get('feels') if w.get('feels') is not None else w['temp'])}°, "
                             f"humidity {w.get('humidity')}%, wind {round(w.get('wind') or 0)}")
                days = w.get("days") or []
                if days and days[0].get("hi") is not None:
                    d0 = days[0]
                    lines.append(f"Today: high {round(d0['hi'])}°, low {round(d0['lo'])}°, {d0.get('rain') or 0}% "
                                 f"chance of rain, sunrise {d0.get('sunrise')}, sunset {d0.get('sunset')}")
                    ahead = [f"{time.strftime('%a', time.strptime(x['date'], '%Y-%m-%d'))} {round(x['hi'])}/"
                             f"{round(x['lo'])}° {wx_words(x.get('code'))[0].lower()}" for x in days[1:4]]
                    if ahead:
                        lines.append("Next few days: " + "; ".join(ahead))
        except (KeyError, TypeError, ValueError):
            pass
        coins = []
        for c in self.crypto.coins[:3]:
            q = (self.crypto.quotes.get(c["id"]) or {}).get("d") or {}
            if q.get("price") is not None:
                ch = q.get("change_24h")
                coins.append(f"{q.get('symbol') or c['symbol']} ${q['price']:,.2f}"
                             + (f" ({ch:+.1f}% in a day)" if ch is not None else ""))
        if coins:
            lines.append("Coins: " + ", ".join(coins))
        if self.proc and self.cur:
            title = self.cur.get("title") or ""
            song = self.meta.get("song") if self.kind == "radio" else ""
            lines.append(f"Playing now: {title}" + (f" ({song})" if song else ""))
        return lines

    def friend_camera(self, text=""):
        """The camera the bot looks through: one named in what you said ("take a picture with the
        garage camera"), the one on the Camera tab, or the first of yours. "" when there's none."""
        cam = self.camera
        cams = cam.cams or read_cameras(LIBRARY[self.tab_index("camera")]["files"])
        low = (text or "").lower()
        if low:
            for c in cams:
                name = (c.get("name") or cam.name_of(c["addr"])).lower()
                if len(name) >= 3 and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", low):
                    return c["addr"]
        return cam.addr or (cams[0]["addr"] if cams else "")

    def friend_look(self, text=""):
        """A picture from your camera, for a model that can see: (its JPEG, the camera) or (None, why not)."""
        cam = self.camera
        addr = self.friend_camera(text)
        if not addr:
            return None, "there's no camera set up"
        got = cam.snapshot(addr, max_age=2)
        if not got:
            return None, f"the camera {cam.name_of(addr)} didn't answer"
        return got[0], cam.name_of(addr)

    def friend_snap(self, text=""):
        """A picture taken with your camera because you asked the bot: kept in ~/Pictures, as one taken
        on the Camera tab is. (Where it is, its bytes, the camera); ValueError: why not."""
        from PIL import Image
        addr = self.friend_camera(text)
        if not addr:
            raise ValueError("there's no camera. Add one on the Camera tab")
        data = self.camera.photo_of(addr)
        try:
            fmt = (Image.open(io.BytesIO(data)).format or "").lower()
        except Exception:
            raise ValueError("that wasn't a picture")
        try:
            if shutil.disk_usage(pictures_dir()).free < len(data) + FRIEND_PIC_ROOM:
                raise ValueError("there's no room left for it on the Pi")
            path = save_picture(data, ".png" if fmt == "png" else ".jpg")
        except OSError as e:
            raise ValueError(f"couldn't save it ({e.strerror or e})")
        self.last_shot = path
        return path, data, self.camera.name_of(addr)

    def friend_options(self):
        """The Bot page's X menu: (what it says, what it does)."""
        opts = [("Send a picture from Photos", "send")]
        if self.friend_camera():
            opts.append(("Take a picture", "snap"))
        opts.append(("Press A again to clear it" if self.confirm[0] == "friendclear" else "Clear the conversation",
                     "clear"))
        return opts

    def friend_pick(self):
        """Photos, to pick a picture for the bot: A sends it, B goes back."""
        if self.friend.busy:
            self.toast("Still thinking about the last one", 2)
            return
        pi = self.tab_index("photos")
        self.load_tab(pi)
        if not self.tab_items(pi):
            self.toast("No pictures in Photos yet", 3)
            return
        self.picking, self.tab = "bot", pi
        self.toast("Pick a picture for your bot", 3)

    def friend_pic(self, pid):
        """A picture in the conversation, as the Bot page shows it: (it, its rounded corners), kept."""
        if not pid:
            return None
        have = self.friend_pics.get(pid)
        if have is None:
            have = False
            data = Friend.picture_bytes(pid)
            if data:
                try:
                    from PIL import Image, ImageDraw
                    im = Image.open(io.BytesIO(data))
                    im.draft("RGB", FRIEND_BUBBLE)
                    im = im.convert("RGB")
                    im.thumbnail(FRIEND_BUBBLE)
                    mask = Image.new("L", im.size, 0)
                    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=9, fill=255)
                    have = (im, mask)
                except Exception:
                    have = False
            if len(self.friend_pics) > FRIEND_KEEP + 10:     # only those still in the conversation
                live = {x.get("pic") for x in list(self.friend.log)}
                self.friend_pics = {k: v for k, v in self.friend_pics.items() if k in live}
            self.friend_pics[pid] = have
        return have or None

    def press_friend(self, name, repeat):
        fr = self.friend
        if self.friend_more is not None:               # the X menu
            opts = self.friend_options()
            menu = self.friend_more
            if name in ("up", "down"):
                menu["sel"] = (menu["sel"] + (1 if name == "down" else -1)) % len(opts)
                self.confirm = (None, 0.0)
            elif name == "a" and not repeat:
                what = opts[menu["sel"] % len(opts)][1]
                if what == "clear" and self.confirm[0] != "friendclear":
                    self.confirm = ("friendclear", time.monotonic() + 4)      # A again to clear it
                else:
                    self.friend_more = None
                    self.confirm = (None, 0.0)
                    if what == "clear":
                        fr.clear()
                        self.toast("Conversation cleared", 2)
                    elif what == "send":
                        self.friend_pick()
                    elif what == "snap":
                        self.friend_send("Take a picture")
            elif name in ("b", "x") and not repeat:
                self.friend_more = None
                self.confirm = (None, 0.0)
            self.dirty = True
            return None
        if name in ("l", "r", "b"):
            return "pass"
        if repeat and name not in ("up", "down"):
            return None
        if name == "start" or (name == "a" and not fr.ready()):
            self.friend_setup()
        elif not fr.ready():
            pass
        elif name == "select":
            if self.voice.speaking:
                self.voice.stop()
            else:
                ok, why = self.say_aloud()
                if not ok:
                    self.toast(why, 3)
        elif name == "a":
            if fr.busy:
                self.toast("Still thinking about the last one", 2)
            else:
                self.open_keyboard("Say something to your bot", "", self.friend_send, limit=200)
        elif name == "y":
            if not fr.remark(self.friend_topic()):
                self.toast("Still thinking about the last one", 2)
        elif name == "x" and not repeat:
            self.friend_more = {"sel": 0}
            self.confirm = (None, 0.0)
        elif name in ("up", "down"):
            self.friend_scroll = max(0, self.friend_scroll + (72 if name == "up" else -72))
        self.dirty = True
        return None

    def friend_send(self, text, picture=None):
        if not self.friend.say(text, picture=picture):
            self.toast("Still thinking about the last one", 2)
        self.friend_scroll = 0

    def friend_setup(self):
        """Settings > Bot."""
        self.tab = self.tab_index("settings")
        self.load_tab(self.tab)
        self.set_page, self.set_sel = "friend", 0
        self.friend.load(self.friend_files())
        if self.friend.server and self.friend.models_at != self.friend.server:
            self.friend.fetch_models()
        self.dirty = True

    def friend_set(self, **updates):
        """Settings > Bot into bot.txt (which starts from friend.txt, its earlier name)."""
        try:
            edit_config("bot.txt", {k: " ".join(str(v).split()) for k, v in updates.items()}, head=FRIEND_HEAD,
                        was="friend.txt")
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return False
        self.friend.load(self.friend_files())
        self.dirty = True
        return True

    def friend_set_server(self, text):
        text = text.strip()
        if text and not cam_address(text):
            self.toast("That isn't an address. Try 192.168.1.20", 4)
            return
        if self.friend_set(server=text) and text:
            self.friend.fetch_models()

    def friend_summary(self):
        fr = self.friend
        fr.load(self.friend_files())
        return fr.model if fr.ready() else ("Pick a model" if fr.server else "Not set up")

    def friend_value(self, key):
        fr = self.friend
        if key == "f_voice":
            job = self.voice.job
            if job and job["id"] == self.voice_want:
                return f"Getting it… {job['pct']}%"
            if not self.voice.supported():
                return "Not on this Pi"
            return voice_name(self.bot_voice()) if self.bot_voice() else "None"
        if key == "f_speak":
            return "On" if self.bot_speaks() else "Off"
        return {"f_server": fr.server or "Not set", "f_model": fr.model or "Pick one", "f_eyes": fr.eyes or "None",
                "f_name": fr.name or "Not set", "f_chatter": fr.chatter_text()}.get(key, "")

    def press_friend_settings(self, name, repeat, key, extra):
        fr = self.friend
        if repeat:
            return None
        page = self.set_page
        if name == "b":
            if page == "friend":
                self.set_page, self.set_sel = "root", [k for k, _, _ in SETTINGS].index("friend")
            else:
                self.set_page, self.set_sel = "friend", {"f_models": 1, "f_eyes": 2, "f_voices": 5}[page]
            self.confirm = (None, 0.0)
        elif page == "f_voices":
            self.press_voices(name, key, extra)
        elif name == "x":
            fr.fetch_models()
        elif page == "friend":
            if name == "a" and key == "f_server":
                self.open_keyboard("Computer with Ollama (its address)", fr.server, self.friend_set_server,
                                   row=0, limit=120, empty=True)
            elif name == "a" and key == "f_name":
                self.open_keyboard("What should it call you?", fr.name,
                                   lambda t: self.friend_set(name=t), limit=40, empty=True)
            elif name == "a" and key in ("f_model", "f_eyes"):
                if not fr.server:
                    self.toast("Set the computer with Ollama first", 3)
                else:
                    self.set_page = "f_models" if key == "f_model" else "f_eyes"
                    want = fr.model if key == "f_model" else fr.eyes
                    rows = self.settings_rows()
                    self.set_sel = next((i for i, r in enumerate(rows) if r[2] == want), 0)
                    if fr.models_at != fr.server or not fr.models:
                        fr.fetch_models()
            elif key == "f_chatter" and name in ("left", "right", "a"):
                labels = [t for t, _ in FRIEND_CHATTER]
                cur = fr.chatter_text()
                i = labels.index(cur) if cur in labels else 0
                new = FRIEND_CHATTER[(i + (-1 if name == "left" else 1)) % len(FRIEND_CHATTER)]
                self.friend_set(chatter=new[1])
            elif name == "a" and key == "f_voice":
                if not self.voice.supported():
                    self.toast("Piper doesn't run on this Pi", 3)
                else:
                    self.set_page = "f_voices"
                    rows = self.settings_rows()
                    want = self.voice_want or self.bot_voice()
                    self.set_sel = next((i for i, r in enumerate(rows) if r[2] == want), 0)
            elif key == "f_speak" and name in ("left", "right", "a"):
                if not self.bot_voice():
                    self.toast("Pick a voice first", 3)
                else:
                    self.friend_set(speak="off" if self.bot_speaks() else "on")
                    if not self.bot_speaks():
                        self.voice.stop()
        elif name == "a" and key == "f_pick":
            if page == "f_models":
                self.friend_set(model=extra)
                self.toast(f"Using {extra}", 2)
            else:
                self.friend_set(eyes=extra)
                self.toast(f"Looking with {extra}" if extra else "No model for seeing", 2)
            self.set_page, self.set_sel = "friend", 1 if page == "f_models" else 2
        self.dirty = True
        return None

    def press_voices(self, name, key, extra):
        """Settings > Bot > Voice: A uses one (fetching it the first time), X twice takes one off."""
        if name == "a":
            ok, what = self.voice_pick(extra if key == "v_pick" else "")
            self.toast(what, 3)
            self.confirm = (None, 0.0)
        elif name == "x" and key == "v_pick" and extra in voices_here():
            if self.confirm[0] == "voicerm:" + extra:
                self.confirm = (None, 0.0)
                if extra == self.bot_voice():
                    self.friend_set(voice="")
                self.voice.remove(extra)
                self.toast(f"Took {voice_name(extra)} off the Pi", 3)
            else:
                self.confirm = ("voicerm:" + extra, time.monotonic() + 4)
                self.toast(f"Press X again to take {voice_name(extra)} off the Pi", 4)

    def render_friend(self):
        from PIL import Image, ImageDraw
        F = self.fonts
        fr = self.friend
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.LIST_TOP + 4, H - self.FOOTER - 10
        # its face, in a card on the left
        cx0, cx1 = 16, 196
        d.rounded_rectangle((cx0, top, cx1, bottom), radius=18, fill=ROW)
        face, mood = fr.face() if fr.ready() else (FRIEND_FACES["sleepy"], "sleepy")
        mid = (top + bottom) / 2 - 16
        d.text(((cx0 + cx1) / 2, mid), face, font=F["face"], fill=TEXT, anchor="mm")
        speaking = self.voice.speaking
        status = (fr.doing or "Thinking…") if fr.busy else "Speaking…" if speaking else \
            self.fit(d, fr.model, F["small"], cx1 - cx0 - 24) if fr.ready() else "Not set up"
        d.text(((cx0 + cx1) / 2, mid + 50), status, font=F["small"], fill=ACCENT if fr.busy or speaking else MUTED,
               anchor="mm")

        # the conversation on the right, the newest at the bottom (above a notice while one is up)
        x0, x1 = cx1 + 14, W - 16
        pw, ph = x1 - x0, bottom - top - (44 if self.msg else 0)
        if not fr.ready():
            lines = [("Set up your bot", F["big"], TEXT), ("", F["small"], MUTED),
                     ("It talks through Ollama on another", F["small"], BODY),
                     ("computer on your network.", F["small"], BODY), ("", F["small"], MUTED),
                     ("Press A to set it up.", F["small"], MUTED)]
            y = top + ph / 2 - 60
            for text, font, colour in lines:
                d.text((x0 + pw / 2, y), text, font=font, fill=colour, anchor="mm")
                y += 26 if font is F["big"] else 22
        else:
            panel = Image.new("RGB", (pw, ph), BG)
            pd = ImageDraw.Draw(panel)
            font = F["chat"]
            lh = 24
            maxw = int(pw * 0.86)
            mine = tuple(int(a * 0.32 + b * 0.68) for a, b in zip(ACCENT, ROW))
            bubbles = []
            for x in list(fr.log):
                pic = self.friend_pic(x.get("pic"))
                lines = self.wrap(pd, x["text"], font, maxw - 28, lines=40) if x.get("text") else []
                w = max([pd.textlength(ln, font=font) + 28 for ln in lines] + ([pic[0].width + 16] if pic else [40]))
                h = 16 + len(lines) * lh + ((pic[0].height + (8 if lines else 0)) if pic else 0)
                bubbles.append((x["who"], x.get("kind"), lines, int(w), h, pic))
            if fr.busy:
                bubbles.append(("friend", "typing", [], 70, 40, None))
            total = sum(b[4] + 10 for b in bubbles)
            self.friend_scroll = max(0, min(self.friend_scroll, total - ph))
            y = ph + self.friend_scroll
            for who, kind, lines, w, h, pic in reversed(bubbles):
                y -= h
                if y + h < 0:
                    break
                if y < ph:
                    bx0 = pw - w if who == "you" else 0
                    pd.rounded_rectangle((bx0, y, bx0 + w, y + h), radius=14,
                                         fill=mine if who == "you" else ROW)
                    if kind == "typing":
                        for k in range(3):
                            pd.ellipse((bx0 + 18 + k * 14, y + h / 2 - 4, bx0 + 26 + k * 14, y + h / 2 + 4),
                                       fill=MUTED)
                    ty = y + 8
                    if pic:                            # a picture: sent, taken, or what it looked at
                        panel.paste(pic[0], (bx0 + 8, y + 8), pic[1])
                        ty += pic[0].height + 8
                    for k, ln in enumerate(lines):
                        pd.text((bx0 + 14, ty + k * lh + lh / 2), ln, font=font,
                                fill=WARN if kind == "error" else TEXT, anchor="lm")
                y -= 10
            if not bubbles:
                pd.text((pw / 2, ph / 2 - 14), "Say hello", font=F["big"], fill=TEXT, anchor="mm")
                pd.text((pw / 2, ph / 2 + 18), "A to talk, or Y and it says something", font=F["small"],
                        fill=MUTED, anchor="mm")
            img.paste(panel, (x0, top))
            if self.friend_scroll:
                d.text((x0 + pw / 2, top + ph - 4), "▼", font=F["small"], fill=MUTED, anchor="mb")
        if fr.ready() and self.friend_more is not None:   # the X menu, over the conversation
            opts = self.friend_options()
            sel = self.friend_more["sel"] % len(opts)
            mw, rh = 320, 44
            mx0, my0 = x0 + (pw - mw) / 2, top + 30
            d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + 44 + len(opts) * rh + 12), radius=14, fill=LINE)
            d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + 42 + len(opts) * rh + 10), radius=13, fill=BG)
            d.text((mx0 + 20, my0 + 22), "Your bot", font=F["small"], fill=MUTED, anchor="lm")
            for k, (label, what) in enumerate(opts):
                ry = my0 + 42 + k * rh
                if k == sel:
                    d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                colour = (WARN if what == "clear" and self.confirm[0] == "friendclear" else TEXT) if k == sel else BODY
                d.text((mx0 + 22, ry + (rh - 4) / 2), self.fit(d, label, F["row"], mw - 44), font=F["row"],
                       fill=colour, anchor="lm")
            hints = [("▲▼", "Choose"), ("A", "OK"), ("B", "Close")]
        elif fr.ready():
            hints = [("A", "Talk"), ("Y", "Say something"), ("X", "More")]
            hints += [("SELECT", "Stop" if speaking else "Speak")] if self.bot_voice() else [("▲▼", "Scroll")]
            hints += [("START", "Set up")]
        else:
            hints = [("A", "Set up"), ("L R", "Tabs"), ("B", "Home")]
        self.footer(d, hints)
        self.fb.show(img)

    def press_cameras(self, name, repeat):
        """The Camera tab: the live picture (B for your cameras, L R between them), or the list."""
        cam = self.camera
        if not self.cam_list:
            if name == "b":
                if not repeat:
                    self.camera_list()
                return None
            place = cam.place()
            if name in ("l", "r") and place and place[1] > 1:
                if not repeat:
                    self.camera_step(1 if name == "r" else -1)
                return None
            if name in ("l", "r"):
                return "pass"
            if name == "select" and not cam.steers:   # (one that turns: when SELECT is let go)
                if cam.addr and not repeat:
                    self.camera_select()
                return None
            if cam.addr and not repeat:
                cam.press(name)
                self.dirty = True
            return None
        rows = self.cam_rows()
        n = len(rows)
        sel = max(0, min(self.cam_sel, n - 1))
        if name in ("up", "down"):
            step = 1 if name == "down" else -1
            sel = (sel + step) % n
            if rows[sel][0] == "label":
                sel = (sel + step) % n
            self.cam_sel = sel
            self.confirm = (None, 0.0)
        elif name == "a" and not repeat:
            kind, entry = rows[sel]
            if kind == "add":
                self.open_keyboard("Camera address (192.168.1.50, or a link)", "", self.camera_typed,
                                   row=0, limit=120)
            elif kind == "found":
                self.camera_add(entry["addr"], entry["name"])
            elif kind == "cam":
                self.camera_open(entry["addr"])
        elif name == "x" and not repeat and rows[sel][0] == "cam":
            entry = rows[sel][1]
            key = "camdel:" + cam_key(entry["addr"])
            if self.confirm[0] == key:
                self.confirm = (None, 0.0)
                self.camera_remove(entry["addr"])
            else:
                self.confirm = (key, time.monotonic() + 4)
                self.toast(f"Press X again to remove {cam.name_of(entry['addr'])}", 4)
        elif name in ("l", "r", "b"):
            return "pass"
        self.dirty = True
        return None

    def camera_select(self):
        """SELECT on a camera's picture (let go quickly, on one that turns): the bot says what it
        sees, or stops talking. With no bot, what it did before: the next speed."""
        cam = self.camera
        if not self.friend.ready():
            if cam.steers:
                cam.next_speed()
            else:
                cam.press("select")
        elif self.voice.speaking:
            self.voice.stop()
        elif self.friend.busy:
            self.toast("Still looking" if (self.cam_bot or {}).get("busy")
                       else "Still thinking about the last one", 2)
        else:
            ok, why = self.camera_describe(cam.addr)
            if not ok:
                self.toast(why, 3)
        self.dirty = True

    def camera_describe(self, addr):
        """The bot looks through one of your cameras and says what it sees: out loud with a voice, and
        over the picture when that camera is on screen. (True, "") or (False, why not)."""
        fr = self.friend
        if not fr.ready():
            return False, "Set up your bot first: Settings > Bot"
        if not addr:
            return False, "Pick a camera first"
        was, token = self.cam_bot, object()
        self.cam_bot = {"addr": addr, "busy": True, "text": "", "note": "", "error": False, "spoken": False,
                        "until": 0.0, "token": token}
        if not fr.describe(lambda: self.camera_look(addr),
                           lambda text, error: self.camera_described(token, text, error)):
            self.cam_bot = was
            return False, "Still thinking about the last one"
        self.dirty = True
        return True, ""

    def camera_look(self, addr):
        """A picture from a camera for the bot: (its JPEG, the camera) or (None, why not). The one on
        screen: just what's on screen."""
        cam = self.camera
        name = cam.name_of(addr)
        jpeg = cam.jpeg
        if cam_key(addr) == cam_key(cam.addr) and jpeg is not None and time.monotonic() - cam.frame_at < 5:
            return jpeg, name
        got = cam.snapshot(addr, max_age=2)
        return (got[0], name) if got else (None, f"the camera {name} didn't answer")

    def camera_described(self, token, text, error):
        """It said what it sees (on its own thread): out loud too, and over the picture for a while."""
        told = self.cam_bot
        if not told or told["token"] is not token:
            return
        note, spoken = "", False
        if text and not error:
            spoken, why = self.say_aloud(text)
            note = "" if spoken else why
        said = error or text or ""
        self.cam_bot = dict(told, busy=False, text=said, error=bool(error), note=note, spoken=spoken,
                            until=time.monotonic() + max(8.0, 4 + len(said) / 12))
        self.dirty = True

    def camera_list(self):
        """Your cameras, with a small picture of each."""
        cam = self.camera
        cam.stop()
        self.cam_list = True
        rows = self.cam_rows()
        self.cam_sel = next((i for i, (k, e) in enumerate(rows)
                             if k == "cam" and cam_key(e["addr"]) == cam_key(cam.addr)), 0)
        cam.scan()
        self.dirty = True

    def camera_open(self, addr):
        """One camera's live picture."""
        cam = self.camera
        cam.select(addr)
        self.state["camera"] = addr
        self.save_state()
        self.cam_list = False
        if self.on_camera_page():
            cam.start()
        self.dirty = True

    def camera_step(self, d):
        cam = self.camera
        place = cam.place()
        if not place:
            return
        nxt = cam.cams[(place[0] - 1 + d) % place[1]]["addr"]
        cam.stop()
        self.camera_open(nxt)

    def camera_typed(self, text):
        addr = cam_address(text)
        if not addr:
            self.toast("That isn't an address. Try 192.168.1.50, or a link", 4)
            return
        self.camera_add(addr, "")

    def camera_add(self, addr, name=""):
        """A camera into camera.txt (for good), and on screen."""
        cam = self.camera
        if not cam.mine(addr):
            try:
                edit_cameras(add=addr, name=name)
            except OSError as ex:
                self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
                return
            cam.load(cam.patterns or LIBRARY[self.tab_index("camera")]["files"], last=addr)
            self.toast(f"Added {name or addr}", 3)
        self.camera_open(addr)

    def camera_remove(self, addr):
        cam = self.camera
        name = cam.name_of(addr)
        try:
            edit_cameras(remove=addr)
        except OSError as ex:
            self.toast(f"Couldn't change static/camera.txt ({ex.strerror or ex})", 4)
            return
        was = cam_key(addr) == cam_key(cam.addr)
        cam.cams = read_cameras(cam.patterns or LIBRARY[self.tab_index("camera")]["files"])
        if was:
            cam.select(cam.cams[0]["addr"] if cam.cams else "")
            if self.state.get("camera") and cam_key(self.state["camera"]) == cam_key(addr):
                self.state.pop("camera", None)
                self.save_state()
        self.toast(f"Removed {name}", 3)
        self.dirty = True

    def picture_saved(self, path):
        """A picture from the Camera tab landed in ~/Pictures (None: it didn't)."""
        if path is None:
            if self.msg == "Saved to Pictures":
                self.msg = None
            return
        self.last_shot = path
        if self.on_camera_page():
            self.toast("Saved to Pictures", 3)

    def release(self, name):
        """Button let go: stops the camera turning or zooming."""
        if self.on_camera_page():
            self.camera.release(name)
            self.dirty = True

    def press(self, name, repeat=False):
        """Returns 'exit' when media mode should close."""
        if self.view == "learn":                       # (controllers come in through learn_event)
            if name == "b" and not repeat:
                self.cancel_learn()
            return None
        if self.proc and self.kind == "plex":
            length = (self.cur or {}).get("dur") or 0
            if name == "a":
                self.cmd("pause")
                self.paused = not self.paused
                self.osd(("Paused  " if self.paused else "")
                         + f"{clock(self.plex_now())} of {clock(length)}", 1500)
                threading.Thread(target=self.plex.timeline, daemon=True,
                                 args=(self.cur["src"], "paused" if self.paused else "playing",
                                       self.plex_now(), length)).start()
            elif name == "b":
                self.stop()
                self.dirty = True
            elif name in ("left", "right", "l", "r"):
                self.plex_seek({"left": -10, "right": 10, "l": -60, "r": 60}[name])
            elif name == "y":
                self.next_screen()
            elif name == "x":
                left = f",  {clock(length - self.plex_now())} left" if length else ""
                self.osd(f"{clock(self.plex_now())} of {clock(length)}{left}", 2500)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "start":
                self.skip(1)
            elif name == "select":
                self.skip(-1)
            return None

        if self.proc and self.kind in ("video", "live"):
            if name == "a":
                self.cmd("pause")
                self.cmd("pausing_keep_force osd_show_progression")
                self.paused = not self.paused
            elif name == "b":
                self.stop()
                self.dirty = True
            elif name == "start":
                self.skip(1)
            elif name == "select":
                self.skip(-1)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "y" and not repeat:
                self.next_screen()
            elif name in PLAYING:
                self.cmd("pausing_keep " + PLAYING[name])
            return None

        if self.view == "home":
            return self.press_home(name, repeat)
        if self.view == "keys":
            return self.press_keys(name, repeat)
        if self.view == "help":
            if not repeat:
                back = self.help_from
                self.view = back if back != "now" or self.kind in LISTEN_KINDS else "list"
                self.dirty = True
            return None
        if self.view == "wait":
            if name == "b":
                self.close_viewer()
            return None
        if self.view == "photo":
            return self.press_photo(name, repeat)
        if self.view == "pdf":
            return self.press_pdf(name, repeat)
        if self.view == "text":
            return self.press_text(name, repeat)

        if self.view == "now" and self.kind in LISTEN_KINDS:
            if repeat:
                return None
            radio = self.kind == "radio"
            if name == "a":
                self.cmd("pause")
                self.paused = not self.paused
            elif name in ("left", "right") and not radio:
                self.cmd(f"seek {10 if name == 'right' else -10} 0")
                self.paused = False
            elif name in ("l", "select") or (radio and name == "left"):
                self.skip(-1)
            elif name in ("r", "start") or (radio and name == "right"):
                self.skip(1)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "y" and not radio:
                self.shuffle = not self.shuffle
            elif name == "x":
                self.view, self.help_from = "help", "now"
            elif name == "b":
                self.view = "home" if self.now_from == "home" else "list"
            self.dirty = True
            return None

        return self.press_list(name, repeat)

    # -- Settings --------------------------------------------------------------
    def current_ssid(self):
        w = self.wifi
        if time.monotonic() - w["ssid_t"] > 5:
            w["ssid_t"] = time.monotonic()
            link = run_out(["iw", "dev", "wlan0", "link"])
            m = re.search(r"SSID: (.+)", link)
            w["ssid"] = m.group(1).strip() if m else ""
        return w["ssid"]

    def settings_rows(self):
        if self.set_page == "wifi":
            w = self.wifi
            rows = [("radio", "WiFi", ["On", "Off"])]
            if w["radio"]:
                rows += [("net", n["ssid"], n) for n in w["nets"]]
                rows.append(("other", "Other network…", "A hidden network, by name"))
            return rows
        if self.set_page == "location":
            rows = [("find", "Find me", "From your internet address"),
                    ("type", "Type a town…", "With the d-pad or your keyboard")]
            rows += [("place", place_text(r) + (f", {r['country']}" if r.get("country") else ""), r)
                     for r in self.loc_results]
            return rows
        if self.set_page == "friend":
            return [("f_server", "Computer with Ollama", None), ("f_model", "Model", None),
                    ("f_eyes", "Model that can see", None), ("f_name", "What it calls you", None),
                    ("f_chatter", "Says something by itself", [t for t, _ in FRIEND_CHATTER]),
                    ("f_voice", "Voice", None), ("f_speak", "Says its replies out loud", ["On", "Off"])]
        if self.set_page == "f_voices":
            ours = [i for i, _, _ in BOT_VOICES]
            return [("v_none", "None", "")] + [("v_pick", n, i) for i, n, _ in BOT_VOICES] + \
                [("v_pick", v, v) for v in sorted(voices_here()) if v not in ours]
        if self.set_page in ("f_models", "f_eyes"):
            fr = self.friend
            rows = [("f_pick", m, m) for m in fr.models]
            if self.set_page == "f_eyes" and rows:
                rows.insert(0, ("f_pick", "None", ""))
            return rows or [("f_wait", fr.models_status or "Asking for its models…", None)]
        return [(key, label, (["Auto"] + [n for _, n in sound_cards()]) if key == "sound" else choices)
                for key, label, choices in SETTINGS]

    def press_settings(self, name, repeat):
        if name in ("l", "r"):
            return "pass"                              # tabs, as everywhere
        rows = self.settings_rows()
        self.set_sel %= len(rows)
        key, label, extra = rows[self.set_sel]
        if name in ("up", "down"):
            self.set_sel = (self.set_sel + (1 if name == "down" else -1)) % len(rows)
        elif self.set_page == "wifi":
            return self.press_wifi(name, repeat, key, extra)
        elif self.set_page in FRIEND_PAGES:
            return self.press_friend_settings(name, repeat, key, extra)
        elif self.set_page == "location":
            if name == "b" and not repeat:
                self.set_page, self.set_sel = "root", [k for k, _, _ in SETTINGS].index("location")
            elif name == "a" and not repeat:
                if key == "find":
                    self.loc_status = "Finding you…"
                    threading.Thread(target=self.locate_job, args=(None,), daemon=True).start()
                elif key == "type":
                    self.open_keyboard("Town or city", "", lambda text: (
                        setattr(self, "loc_status", "Looking…"),
                        threading.Thread(target=self.locate_job, args=(text,), daemon=True).start()))
                elif key == "place":
                    self.set_setting("location", extra)
                    self.toast(f"Location: {place_text(extra)}", 2)
                    self.weather_changed()
                    self.set_page, self.set_sel = "root", [k for k, _, _ in SETTINGS].index("location")
        elif name == "b":
            return "pass"
        elif name in ("left", "right") and extra and not repeat:
            cur = self.setting(key)
            i = extra.index(cur) if cur in extra else 0
            value = extra[(i + (1 if name == "right" else -1)) % len(extra)]
            self.set_setting(key, value)
            if key == "units":
                self.weather_changed()
        elif name == "a" and not repeat:
            if key == "wifi":
                self.set_page, self.set_sel = "wifi", 1
                self.wifi_rescan()
            elif key == "location":
                self.set_page, self.set_sel, self.loc_status = "location", 0, None
            elif key == "friend":
                self.set_page, self.set_sel = "friend", 0
                self.friend.load(self.friend_files())
                if self.friend.server and self.friend.models_at != self.friend.server:
                    self.friend.fetch_models()
            elif key == "wallpaper" and self.setting("wallpaper") == "Picture":
                pi = self.tab_index("photos")
                self.load_tab(pi)
                if not self.tab_items(pi):
                    self.toast("No pictures in ~/Pictures yet", 3)
                else:
                    self.picking, self.tab = "wallpaper", pi
                    self.toast("Pick a picture for the background", 3)
            elif key == "pad":
                self.start_learn()
            elif extra:
                cur = self.setting(key)
                i = extra.index(cur) if cur in extra else 0
                self.set_setting(key, extra[(i + 1) % len(extra)])
                if key == "units":
                    self.weather_changed()
        elif name == "x" and not repeat and key == "pad" and self.pads:
            self.pads.forget()
            self.toast("Back to each controller's standard buttons", 3)
        self.dirty = True
        return None

    # -- Settings > Controller: setting up a controller's buttons --------------------
    def pad_summary(self):
        pads = list(self.pads.by_path.values()) if self.pads else []
        if not pads:
            return "None plugged in"
        first = pads[0].dev.name
        return first if len(pads) == 1 else f"{first} + {len(pads) - 1}"

    @property
    def learning(self):
        return bool(self.learn) and not self.learn.get("done")

    def start_learn(self):
        self.learn = {"step": 0, "pad": None, "keys": {}, "axes": {}, "base": {}, "armed": {},
                      "t": time.monotonic(), "quiet": 0.0, "said": "", "skipped": [], "done": None,
                      "shown": -1}
        self.view = "learn"
        self.dirty = True

    def cancel_learn(self, why="Controller set-up stopped"):
        if not self.learn:
            return
        self.learn = None
        self.tab = self.tab_index("settings")
        self.view = "list"
        self.set_page = "root"
        self.load_tab(self.tab)
        if why:
            self.toast(why, 3)
        self.dirty = True

    def learn_next(self):
        L = self.learn
        L["step"] += 1
        L["t"] = time.monotonic()
        L["quiet"] = L["t"] + 0.25         # the same press can show up twice (d-pad and stick)
        L["said"] = ""
        if L["step"] >= len(LEARN_STEPS):
            if self.pads and L["pad"] is not None:
                self.pads.save(L["pad"].ident, L["keys"], L["axes"])
            L["done"] = time.monotonic() + 2.5
        self.dirty = True

    def learn_event(self, pad, ev):
        """A raw event from a controller while its buttons are being set up."""
        L = self.learn
        if not L or L.get("done"):
            return
        if L["pad"] is not None and pad is not L["pad"]:
            if any(down and name in ("b", "home") for name, down in pad.translate(ev)):
                self.cancel_learn()                    # another controller stops it
            return
        name = LEARN_STEPS[L["step"]][0]
        if ev.type == e.EV_KEY:
            if ev.value != 1:
                return
            if L["pad"] is None:                       # A on the controller to set up
                L["pad"] = pad
                for code in pad.axis_codes():
                    try:
                        L["base"][code] = pad.direction(code, pad.dev.absinfo(code).value)
                    except OSError:
                        L["base"][code] = 0
            if time.monotonic() < L["quiet"]:
                return
            if ev.code in L["keys"]:
                L["said"] = f"That one is {L['keys'][ev.code].upper()} already"
                self.dirty = True
                return
            L["keys"][ev.code] = name
            self.learn_next()
        elif ev.type == e.EV_ABS and L["pad"] is not None:
            d = pad.direction(ev.code, ev.value)
            base = L["base"].get(ev.code, 0)
            if d == base:
                L["armed"][ev.code] = True             # back at rest: ready again
                return
            if d == 0 or not L["armed"].get(ev.code, True) or time.monotonic() < L["quiet"]:
                return
            L["armed"][ev.code] = False
            used = L["axes"].get(ev.code, {}).get(d)
            if used:
                L["said"] = f"That one is {used.upper()} already"
                self.dirty = True
                return
            L["axes"].setdefault(ev.code, {})[d] = name
            self.learn_next()

    def learn_tick(self, now):
        L = self.learn
        if L.get("done"):
            if now > L["done"]:
                self.cancel_learn("")
            return
        idle = now - L["t"]
        _, _, optional = LEARN_STEPS[L["step"]]
        if L["pad"] is None and idle > 30:
            self.cancel_learn("No controller pressed A")
        elif optional and L["pad"] is not None and idle > LEARN_SKIP:
            L["skipped"].append(LEARN_STEPS[L["step"]][0])
            self.learn_next()
        elif not optional and idle > 60:
            self.cancel_learn()
        elif optional and L["pad"] is not None and int(idle) != L["shown"]:
            L["shown"] = int(idle)                     # the countdown
            self.dirty = True

    def learn_status(self):
        L = self.learn
        if not L:
            return None
        if L.get("done") or L["step"] >= len(LEARN_STEPS):
            return {"done": True, "text": "Saved", "n": len(LEARN_STEPS), "of": len(LEARN_STEPS)}
        what = LEARN_STEPS[L["step"]][1]
        text = (f"Press {what} on the controller to set up" if L["pad"] is None else f"Press {what}")
        return {"done": False, "text": text, "n": L["step"] + 1, "of": len(LEARN_STEPS),
                "pad": L["pad"].dev.name if L["pad"] is not None else None, "said": L["said"]}

    def render_learn(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        L = self.learn or {}
        pad = L.get("pad")
        self.title_row(d, "Set up a controller", pad.dev.name[:28] if pad is not None else None)
        done = set(L.get("keys", {}).values()) | {n for dirs in L.get("axes", {}).values() for n in dirs.values()}
        skipped = set(L.get("skipped", []))
        now_name = None if L.get("done") else LEARN_STEPS[L.get("step", 0)][0]

        def fill(name):
            if name == now_name:
                return ACCENT
            if name in done:
                return DONE
            return ROW if name in skipped else LINE

        # a controller: shoulders, body, d-pad, face buttons, SELECT / START / HOME
        cx, top = W // 2, 104
        d.rounded_rectangle((cx - 150, top - 18, cx - 70, top + 2), radius=8, fill=fill("l"))
        d.rounded_rectangle((cx + 70, top - 18, cx + 150, top + 2), radius=8, fill=fill("r"))
        d.rounded_rectangle((cx - 190, top, cx + 190, top + 170), radius=70, fill=PHOTO_BG,
                            outline=LINE, width=2)
        px, py = cx - 105, top + 85
        for name, box in (("up", (px - 13, py - 45, px + 13, py - 13)), ("down", (px - 13, py + 13, px + 13, py + 45)),
                          ("left", (px - 45, py - 13, px - 13, py + 13)), ("right", (px + 13, py - 13, px + 45, py + 13))):
            d.rounded_rectangle(box, radius=5, fill=fill(name))
        d.rectangle((px - 13, py - 13, px + 13, py + 13), fill=LINE)
        fx, fy = cx + 105, top + 85
        for name, (bx, by) in (("x", (fx, fy - 32)), ("a", (fx + 32, fy)), ("b", (fx, fy + 32)), ("y", (fx - 32, fy))):
            d.ellipse((bx - 16, by - 16, bx + 16, by + 16), fill=fill(name))
            d.text((bx, by), name.upper(), font=F["key"], fill=PHOTO_BG if fill(name) in (ACCENT, DONE) else TEXT,
                   anchor="mm")
        for name, box in (("select", (cx - 42, top + 112, cx - 6, top + 124)),
                          ("start", (cx + 6, top + 112, cx + 42, top + 124))):
            d.rounded_rectangle(box, radius=6, fill=fill(name))
        d.ellipse((cx - 13, top + 64, cx + 13, top + 90), fill=fill("home"))

        if L.get("done"):
            big, small = "All set", "These buttons are saved for this controller"
        else:
            st = self.learn_status() or {}
            big = st.get("text", "")
            _, _, optional = LEARN_STEPS[L.get("step", 0)]
            if L.get("said"):
                small = L["said"]
            elif pad is None:
                small = "It stops by itself if you wait"
            elif optional:
                small = f"Not on yours? It's skipped in {max(0, LEARN_SKIP - int(time.monotonic() - L['t']))} s"
            else:
                small = "B or HOME on another controller stops"
        d.text((W / 2, 318), self.fit(d, big, F["big"], W - 40), font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, 352), self.fit(d, small, F["small"], W - 40), font=F["small"], fill=MUTED, anchor="mm")
        n = min(L.get("step", 0) + 1, len(LEARN_STEPS))
        self.footer(d, [], right="" if L.get("done") else f"{n} of {len(LEARN_STEPS)}")
        self.fb.show(img)

    # -- the web page: what's on the screen, and putting things there -----------------
    def where_text(self):
        if not self.active:
            return "Terminal"
        if self.view == "home":
            return "Home"
        if self.view == "learn":
            return "Settings › Controller"
        names = []
        p = self.parent_of(self.tab)
        if p is not None:
            names.append(LIBRARY[p]["name"])
        names.append(LIBRARY[self.tab]["name"])
        stack = self.chan_stack.get(self.tab)
        if stack:
            names.append(stack[-1]["title"])
        elif self.tab_type() == "radio" and self.radio_stack:
            names.append(self.radio_stack[-1]["title"])
        elif self.tab_type() == "plex" and len(self.plex_stack) > 1:
            names += [lvl["title"] for lvl in self.plex_stack[1:]]
        if self.view in ("photo", "pdf", "text") and self.v.get("title"):
            names.append(self.v["title"])
        return " › ".join(names)

    def web_state(self):
        """(This runs on the web page's thread: it only reads, and tries again if the main loop
        changed something under it.)"""
        for _ in range(3):
            try:
                return self.web_state_now()
            except (RuntimeError, IndexError, KeyError, AttributeError, TypeError):
                time.sleep(0.02)
        return self.web_state_now()

    def web_state_now(self):
        playing = None
        cur, meta, kind = self.cur, self.meta, self.kind
        if self.proc and cur:
            length = meta.get("length") or cur.get("dur") or 0
            pos = self.plex_now() if kind == "plex" else self.pos
            playing = {"title": cur.get("title", ""), "sub": cur.get("sub", ""),
                       "src": cur.get("src", ""), "kind": kind,
                       "pos": round(max(pos or 0, 0), 1), "length": round(length or 0, 1),
                       "paused": self.paused, "song": meta.get("song") or meta.get("title") or ""}
        pads = list(self.pads.by_path.values()) if self.pads else []
        return {"mode": "media" if self.active else "terminal", "view": self.view,
                "where": self.where_text(), "playing": playing, "volume": self.volume,
                "screen": self.setting("screen"), "video": self.proc_owns_screen(),
                "frame": getattr(self.fb, "frames", 0) if self.active else -1,
                "controllers": [{"name": p.dev.name, "kind": p.kind, "learned": p.learned} for p in pads],
                "learning": self.learn_status(),
                "size": list(self.screen_dims() if self.fb else screen_size()),
                "plex": self.plex.signed_in, "msg": self.msg}

    def web_screen(self):
        """(bytes, type): the menus exactly as drawn, or a snapshot of the real screen while a
        video plays. Never the terminal: that stays on the Pi."""
        fb = self.fb
        if not self.active:
            return None
        if self.active and fb is not None and not self.proc_owns_screen() and getattr(fb, "last", None):
            key = ("menus", getattr(fb, "frames", 0))
            if self.shot[0] == key:
                return self.shot[1], self.shot[2]
            buf = io.BytesIO()
            fb.last.save(buf, "PNG", compress_level=1)    # quick to make on a Pi Zero
            out = (buf.getvalue(), "image/png")
        else:
            key = None
            img = grab_screen(640)
            buf = io.BytesIO()
            if self.proc_owns_screen():
                img.save(buf, "JPEG", quality=82)
                out = (buf.getvalue(), "image/jpeg")
            else:
                img.save(buf, "PNG")
                out = (buf.getvalue(), "image/png")
        self.shot = (key, out[0], out[1])
        return out

    def web_icon(self, name, size=96):
        """The home screen's icon for an app, for the web page (None: no such app)."""
        if name not in HOME_ICONS:
            return None
        size = min((48, 64, 96, 112, 128, 192), key=lambda x: abs(x - int(size)))
        if (name, size) not in self.web_icons:
            buf = io.BytesIO()
            draw_icon(name, size).save(buf, "PNG")
            self.web_icons[(name, size)] = buf.getvalue()
        return self.web_icons[(name, size)]

    def web_catalog(self):
        """Everything the web page can put on the screen without asking the internet."""
        apps = []
        for name, _ in self.home_apps():
            col, about = HOME_ICONS.get(name, ((76, 114, 154), ""))
            apps.append({"name": name, "color": "#%02x%02x%02x" % col, "about": about})
        group = LIBRARY[self.tab_index("group")]
        tv = [{"name": n, "about": next((t.get("about", "") for t in LIBRARY if t["name"] == n), "")}
              for n in group.get("children", [])]

        def shelf(lists, badges):
            return [{"folder": f, "badge": badges.get(f, ""),
                     "items": [[t, y, f"ia:{i}/{n}"] for t, y, i, n in rows]} for f, rows in lists.items()]
        radio = LIBRARY[self.tab_index("radio")]
        streams = LIBRARY[self.tab_index("streams")]
        return {"apps": apps, "tv": tv,
                "cartoons": shelf(CLASSIC, TOON_BADGES), "films": shelf(FILMS, FILM_BADGES),
                "radio": {"mine": [[it["title"], it.get("sub", ""), it["src"]]
                                   for it in read_streams(radio["files"], kind="radio")],
                          "stations": [list(x) for x in RADIO_STATIONS],
                          "genres": [g[0] for g in RADIO_GENRES]},
                "streams": [[it["title"], it.get("sub", ""), it["src"]] for it in read_streams(streams["files"])],
                "plex": self.plex.signed_in}

    def web_channels(self, what):
        """Plex's free Live TV channels of a kind (anime, toons, movies, news, sports)."""
        if what not in ("anime", "toons", "movies", "news", "sports"):
            return {"error": "No such list"}
        if not self.plex.signed_in:
            return {"error": "plex"}
        try:
            chans = self.live_list()
        except Exception:
            return {"error": "Plex didn't answer"}
        return {"channels": [[c["title"], c["genre"], "plexlive:" + c["key"]]
                             for c in chans if live_pick(what, c)]}

    def web_radio(self, genre=None, query=None):
        """Stations from Radio Browser: a genre's busiest, or a search by name."""
        tags = next((t for g, _, t in RADIO_GENRES if g == genre), None)
        if genre and tags is None:
            return {"error": "No such genre"}
        key = genre or "search:" + (query or "").strip().lower()
        hit = self.web_radio_cache.get(key)
        if not (hit and time.time() - hit[0] < RADIO_TTL):
            try:
                found = rb_stations(tags=tags or (), name=(query or "").strip())
            except Exception:
                return {"error": "Radio Browser didn't answer"}
            hit = (time.time(), [[it["title"], it.get("sub", ""), it["src"], it.get("uuid", ""), it.get("logo", "")]
                                 for it in found])
            self.web_radio_cache[key] = hit
        return {"stations": hit[1]}

    def web_item(self, r):
        """A row the web page sent, as something to play (only kinds that can be played)."""
        if not isinstance(r, dict):
            return None
        src, title, sub = str(r.get("src") or ""), str(r.get("title") or "")[:160], str(r.get("sub") or "")[:80]
        if src.startswith("ia:") and "/" in src[3:]:
            return item(src, title or src, "video", src, sub=sub)
        if src.startswith("plexlive:"):
            return dict(item(src, title or "Channel", "live", src, sub=sub), thumb=None, ptype="channel")
        if re.match(r"https?://", src):
            if r.get("kind") == "radio":
                it = item("url:" + src, title or src, "radio", src, sub=sub)
                if r.get("uuid"):
                    it["uuid"] = str(r["uuid"])[:64]
                return it
            return item("stream:" + src, title or src, "live", src, sub=sub)
        if src.startswith("/") and self.web_may_see(src) and os.path.isfile(src):
            kind = classify(src)
            if kind in ("video", "audio"):
                return item(src, title_of(src), kind, src)
        return None

    def web_ready(self):
        """Media mode on, with nothing half-open in the way."""
        if not self.active:
            self.enter()
        if not self.active:
            return False
        if self.learn:
            self.cancel_learn("")
        if self.view == "keys":
            self.close_keyboard(False)
        if self.view in ("photo", "pdf", "text", "wait"):
            self.close_viewer()
        if self.proc_owns_screen():
            self.stop()
        return True

    def web_tab(self, name):
        i = next((k for k, t in enumerate(LIBRARY) if t["name"] == name), None)
        if i is not None:
            self.go_home()
            self.tab, self.view = i, "list"
            self.load_tab(i)
            self.dirty = True
        return i

    def web_command(self, cmd):
        """What the web page asked for, done between button presses."""
        c = cmd.get("cmd")
        if c == "open":
            app = str(cmd.get("app") or "")
            if app == "Terminal":
                self.leave()
                return {"ok": True}
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            if app == "Home":
                self.go_home()
                return {"ok": True}
            if self.web_tab(app) is None:
                return {"error": "No such app"}
            return {"ok": True}
        if c == "play":
            rows = cmd.get("items")
            rows = rows[:600] if isinstance(rows, list) else []
            try:
                want = int(cmd.get("index") or 0)
            except (TypeError, ValueError):
                want = 0
            todo, i = [], None
            for k, r in enumerate(rows):             # (the one asked for, wherever it lands)
                it = self.web_item(r)
                if it:
                    if k == want:
                        i = len(todo)
                    todo.append(it)
            if not todo or i is None:
                return {"error": "That can't be played"}
            if not self.web_ready():
                return {"error": "There's no screen to play it on"}
            if self.web_tab(str(cmd.get("where") or "")) is None and self.view == "home":
                self.view = "list"
            self.play(todo, i)
            return {"ok": True, "title": todo[i]["title"]}
        if c == "show":
            return self.web_show(str(cmd.get("path") or ""))
        if c == "player":
            return self.web_player(str(cmd.get("do") or ""))
        if c == "learn":
            if cmd.get("stop"):
                self.cancel_learn()
                return {"ok": True}
            if not self.web_ready():
                return {"error": "There's no screen"}
            self.web_tab("Settings")
            self.start_learn()
            return {"ok": True}
        if c == "reset_pads":
            if self.pads:
                self.pads.forget()
            return {"ok": True}
        if c == "camera":
            return self.web_camera(cmd)
        if c == "friend":
            return self.web_friend_do(cmd)
        return {"error": "Unknown request"}

    # -- the web page's cameras and bot -------------------------------------------
    def web_cameras(self):
        """Your cameras and the ones heard on the network. (On the web page's thread: it reads, and
        asks no camera anything.)"""
        cam = self.camera
        cam.listen()
        cams = read_cameras(LIBRARY[self.tab_index("camera")]["files"])
        hosts = {cam_host(c["addr"]) for c in cams}

        def row(addr, name):
            k = cam_key(addr)
            got = cam.known.get(k) or cam.found.get(k) or {}
            th, miss = cam.thumbs.get(k), cam.missing.get(k, 0)
            return {"addr": addr, "name": name or got.get("name") or cam_host(addr) or addr,
                    "kind": got.get("server", ""),
                    "reach": "no" if miss and (not th or miss > th[2]) else "yes" if th else ""}
        found = [row(f["addr"], f["name"]) for f in list(cam.found.values())
                 if time.time() - f["seen"] <= CAM_FOUND_FOR and cam_host(f["addr"]) not in hosts]
        return {"cameras": [row(c["addr"], c["name"]) for c in cams],
                "found": sorted(found, key=lambda f: f["name"].lower()),
                "showing": cam.addr if self.on_camera_page() else "",
                "bot": self.friend.ready(), "voice": bool(self.bot_voice())}

    def web_camframe(self, addr):
        """A picture from one of your cameras, or one heard on the network (no other address)."""
        cam = self.camera
        k = cam_key(addr)
        cams = read_cameras(LIBRARY[self.tab_index("camera")]["files"])
        if not addr or (k not in {cam_key(c["addr"]) for c in cams} and k not in cam.found):
            return None
        got = cam.snapshot(addr, max_age=1.5)
        return got[0] if got else None

    def web_camera(self, cmd):
        cam = self.camera
        do = str(cmd.get("do") or "")
        addr = cam_address(str(cmd.get("addr") or ""))
        if not addr:
            return {"error": "That isn't an address. Try 192.168.1.50, or a link"}
        files = LIBRARY[self.tab_index("camera")]["files"]
        cam.cams = read_cameras(files)
        cam.patterns = cam.patterns or files
        if do == "add":
            if cam.mine(addr):
                return {"error": "That camera is already in your list"}
            if cam_is_local(addr):                    # (the Pi's own services stay its own)
                return {"error": "Add a camera by its address on your network, like 192.168.1.50"}
            try:
                edit_cameras(add=addr, name=clean_name(cmd.get("name")))
            except OSError as ex:
                return {"error": f"Couldn't save it ({ex.strerror or ex})"}
            cam.cams = read_cameras(files)
            self.dirty = True
            return {"ok": True}
        if do == "remove":
            if not cam.mine(addr):
                return {"error": "That camera isn't in your list"}
            self.camera_remove(addr)
            return {"ok": True}
        if do == "show":
            if not cam.mine(addr) and cam_key(addr) not in cam.found:
                return {"error": "That camera isn't in your list"}
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            self.web_tab("Camera")
            self.camera_open(addr)
            return {"ok": True}
        if do == "describe":                          # the bot says what it sees (on the Pi, out loud)
            if not cam.mine(addr):
                return {"error": "That camera isn't in your list"}
            self.friend.load(self.friend_files())
            if not self.friend.ready():
                return {"error": "Set up your bot first, on the Bot tab"}
            since = time.time()
            ok, why = self.camera_describe(addr)
            return {"ok": True, "since": since} if ok else {"error": "It's still thinking about the last one"
                                                             if why.startswith("Still") else why}
        return {"error": "Unknown request"}

    def web_friend(self):
        """The bot: its settings, the conversation, whether it's thinking or speaking, its voice."""
        fr = self.friend
        fr.load(self.friend_files())
        face, mood = fr.face() if fr.ready() else (FRIEND_FACES["sleepy"], "sleepy")
        addr = self.friend_camera()
        pics = os.path.realpath(os.path.join(home_dir(), "Pictures"))

        def photo(path):                               # where a picture is among your Pictures
            real = os.path.realpath(path) if isinstance(path, str) and path else ""
            return {"folder": "pictures", "path": os.path.relpath(real, pics)} \
                if real.startswith(pics + os.sep) else None
        return {"ready": fr.ready(), "server": fr.server, "model": fr.model, "eyes": fr.eyes, "name": fr.name,
                "chatter": fr.chatter(), "busy": fr.busy, "doing": fr.doing, "face": face, "mood": mood,
                "camera": self.camera.name_of(addr) if addr else "", "sees": fr.sees(),
                "log": [{"who": x["who"], "text": x["text"], "t": x["t"], "kind": x.get("kind", ""),
                         "pic": x.get("pic", ""), "photo": photo(x.get("photo"))}
                        for x in list(fr.log)],
                "models": list(fr.models) if fr.server and fr.models_at == fr.server else [],
                "modelsStatus": fr.models_status, "showing": self.on_friend_page(), "voice": self.web_voice()}

    def web_voice(self):
        here = voices_here()
        ours = [i for i, _, _ in BOT_VOICES]
        job = self.voice.job
        return {"id": self.bot_voice(), "speak": self.bot_speaks(), "speaking": self.voice.speaking,
                "status": self.voice.status(), "getting": job["id"] if job else "", "can": self.voice.supported(),
                "piper": self.voice.have_piper(), "mb": VOICE_MB,
                "list": [{"id": i, "name": n, "note": note, "here": i in here} for i, n, note in BOT_VOICES]
                + [{"id": v, "name": v, "note": "", "here": True} for v in sorted(here) if v not in ours]}

    def web_friend_do(self, cmd):
        fr = self.friend
        fr.load(self.friend_files())
        do = str(cmd.get("do") or "")
        if do in ("say", "remark", "aloud", "photo") and not fr.ready():
            return {"error": "Set up your bot first"}
        if do == "say":
            text = " ".join(str(cmd.get("text") or "").split())[:400]
            pic = cmd.get("picture")                   # one of your pictures (webui.py says where)
            if pic is not None and not (isinstance(pic, str) and pic.startswith("/") and self.web_may_see(pic)
                                        and os.path.splitext(pic)[1].lower() in IMAGE_EXTS and os.path.isfile(pic)):
                return {"error": "That picture can't be sent"}
            if not text and pic is None:
                return {"error": "Say something first"}
            if not fr.say(text, picture=pic):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True}
        if do == "photo":
            if not self.friend_camera():
                return {"error": "There's no camera. Add one on the Camera tab"}
            if not fr.say("Take a picture"):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True}
        if do == "remark":
            if not fr.remark(self.friend_topic()):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True}
        if do == "clear":
            fr.clear()
            return {"ok": True}
        if do == "aloud":
            ok, why = self.say_aloud()
            return {"ok": True} if ok else {"error": why}
        if do == "hush":
            self.voice.stop()
            return {"ok": True}
        if do == "models":
            fr.fetch_models()
            return {"ok": True}
        if do == "open":
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            self.web_tab("Bot")
            return {"ok": True}
        if do == "set":
            if "voice" in cmd:
                ok, what = self.voice_pick(clean_name(cmd.get("voice"), 80))
                return {"ok": True, "said": what} if ok else {"error": what}
            updates = {k: " ".join(str(cmd.get(k) or "").split())[:120]
                       for k in ("server", "model", "eyes", "name") if k in cmd}
            if "speak" in cmd:
                updates["speak"] = "on" if cmd.get("speak") in (True, "on", "yes", 1, "1") else "off"
            if "chatter" in cmd:
                try:
                    updates["chatter"] = str(max(0, min(1440, int(cmd["chatter"]))))
                except (TypeError, ValueError):
                    return {"error": "Bad request"}
            if not updates:
                return {"error": "Nothing to change"}
            if updates.get("server") and not cam_address(updates["server"]):
                return {"error": "That isn't an address. Try 192.168.1.20"}
            if not self.friend_set(**updates):
                return {"error": "Couldn't save static/bot.txt"}
            if updates.get("speak") == "off":
                self.voice.stop()
            if updates.get("server"):
                fr.fetch_models()
            return {"ok": True}
        return {"error": "Unknown request"}

    def web_show(self, path):
        """A file from the web page's list, opened on the screen the way Files opens it."""
        if not (path.startswith("/") and self.web_may_see(path) and os.path.exists(path)):
            return {"error": "That file isn't there"}
        if not self.web_ready():
            return {"error": "There's no screen to show it on"}
        kind = classify(path)
        folder = path if kind == "dir" else os.path.dirname(path)
        self.web_tab("Files")
        self.browse(folder, select=None if kind == "dir" else path)
        if kind == "dir":
            return {"ok": True}
        items = self.tab_items()
        i = next((k for k, it in enumerate(items) if it["src"] == path), None)
        if i is None:
            return {"error": "That file isn't there"}
        self.sels[self.tab] = i
        self.open_item(items, i)
        return {"ok": True}

    def web_player(self, do):
        if do in ("louder", "quieter"):
            self.set_volume(VOLUME_STEP if do == "louder" else -VOLUME_STEP)
            return {"ok": True, "volume": self.volume}
        if not self.proc:
            return {"error": "Nothing is playing"}
        if do == "pause":
            if self.kind == "plex":
                self.press("a")
            else:
                self.cmd("pause")
                self.paused = not self.paused
                if self.kind in SCREEN_KINDS:
                    self.cmd("pausing_keep_force osd_show_progression")
        elif do == "stop":
            self.stop()
            if self.view == "now":
                self.view = "home" if self.now_from == "home" else "list"
        elif do in ("next", "prev"):
            self.skip(1 if do == "next" else -1)
        elif do in ("back", "forward"):
            step = -10 if do == "back" else 10
            if self.kind == "plex":
                self.plex_seek(step)
            elif self.kind not in ("radio", "live"):
                self.cmd(f"seek {step} 0")
                self.paused = False
        elif do == "screen" and self.kind in SCREEN_KINDS:
            self.next_screen()
        else:
            return {"error": "Unknown request"}
        self.dirty = True
        return {"ok": True}

    # -- WiFi --------------------------------------------------------------------
    def press_wifi(self, name, repeat, key, extra):
        w = self.wifi
        if name == "b" and not repeat:
            self.set_page, self.set_sel = "root", [k for k, _, _ in SETTINGS].index("wifi")
            self.confirm = (None, 0.0)
        elif w["busy"]:
            pass                                       # one thing at a time
        elif key == "radio" and name in ("left", "right", "a") and not repeat:
            on = not w["radio"]
            w["busy"], w["status"] = True, "Turning WiFi on…" if on else "Turning WiFi off…"
            threading.Thread(target=self.wifi_job, args=("radio", on), daemon=True).start()
        elif name == "x" and not repeat:
            self.wifi_rescan()
        elif key == "net" and name == "a" and not repeat:
            net = extra
            if net["active"]:
                self.toast(f"Connected to {net['ssid']}", 2)
            elif net["ssid"] in w["saved"] or not net["secure"]:
                self.wifi_connect(net["ssid"], None)
            else:
                self.open_keyboard(f"Password for {net['ssid']}", "",
                                   lambda pw, ssid=net["ssid"]: self.wifi_connect(ssid, pw), strip=False)
        elif key == "net" and name == "y" and not repeat:
            ssid = extra["ssid"]
            if ssid not in w["saved"]:
                self.toast("That network isn't saved", 2)
            elif self.confirm[0] == "forget:" + ssid and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                w["busy"], w["status"] = True, f"Forgetting {ssid}…"
                threading.Thread(target=self.wifi_job, args=("forget", ssid), daemon=True).start()
            else:
                self.confirm = ("forget:" + ssid, time.monotonic() + 4)
                self.toast("Press Y again to forget it" + (" (you'll be disconnected)" if extra["active"] else ""), 4)
        elif key == "other" and name == "a" and not repeat:
            self.open_keyboard("Network name", "", lambda ssid: self.open_keyboard(
                f"Password for {ssid} (empty if open)", "",
                lambda pw, ssid=ssid: self.wifi_connect(ssid, pw or "", hidden=True), strip=False, empty=True))
        self.dirty = True
        return None

    def wifi_rescan(self):
        w = self.wifi
        if w["busy"]:
            return
        w["busy"], w["status"] = True, "Looking for networks…"
        threading.Thread(target=self.wifi_job, args=("scan",), daemon=True).start()

    def wifi_connect(self, ssid, password, hidden=False):
        w = self.wifi
        w["busy"], w["status"] = True, f"Connecting to {ssid}…"
        threading.Thread(target=self.wifi_job, args=("connect", ssid, password, hidden), daemon=True).start()
        self.dirty = True

    def wifi_job(self, what, *args):
        w = self.wifi
        try:
            if what == "radio":
                ok, _, err = nm(["radio", "wifi", "on" if args[0] else "off"], 15)
                if not ok:
                    raise ValueError(err or "Couldn't switch WiFi")
                w["radio"] = args[0]
                if args[0]:
                    time.sleep(3)                      # give it a moment to find networks
            elif what == "forget":
                profile = w["saved"].get(args[0], args[0])
                ok, _, err = nm(["connection", "delete", "id", profile], 15)
                self.toast(f"Forgot {args[0]}" if ok else nm_why(err), 3)
            elif what == "connect":
                ssid, password, hidden = args
                before = w["saved"] = wifi_saved()
                if ssid in before and password is None:
                    ok, _, err = nm(["connection", "up", "id", before[ssid]], 60)
                else:
                    cmd = ["device", "wifi", "connect", ssid]
                    if password:
                        cmd += ["password", password]
                    if hidden:
                        cmd += ["hidden", "yes"]
                    ok, _, err = nm(cmd, 60)
                    if not ok and ssid not in before:  # a wrong password leaves a broken profile behind
                        nm(["connection", "delete", "id", ssid], 15)
                if ok:
                    w["ssid_t"] = 0.0
                    self.toast(f"Connected to {ssid}", 3)
                else:
                    self.toast(f"{ssid}: {nm_why(err)}", 5)
            if what != "radio" or w["radio"]:
                ok, out, _ = nm(["radio", "wifi"], 10)
                w["radio"] = not ok or out.strip() != "disabled"
                w["saved"] = wifi_saved()
                w["nets"] = wifi_scan() if w["radio"] else []
            else:
                w["nets"] = []
            w["status"] = None if (w["nets"] or not w["radio"]) else "No networks found. X looks again"
        except ValueError as ex:
            w["status"] = str(ex)
        except Exception as ex:
            w["status"] = f"Something went wrong ({ex})"[:70]
        finally:
            w["busy"] = False
            w["ssid_t"] = 0.0
            self.dirty = True

    def locate_job(self, text):
        try:
            if text is None:
                try:
                    loc = self.pie.place()               # PiE-ink's place first: the same as its weather's
                except Exception:
                    loc = None
                loc = loc or find_me()
                if not loc:
                    raise ValueError("Couldn't tell from the internet address")
                self.set_setting("location", loc)
                self.loc_status = None
                self.toast(f"Location: {place_text(loc)}", 3)
                self.weather_changed()
                self.set_page, self.set_sel = "root", [k for k, _, _ in SETTINGS].index("location")
            else:
                self.loc_results = geocode(text)
                self.loc_status = None if self.loc_results else f"Nothing found for “{text}”"
                self.set_sel = 2 if self.loc_results else 1
        except Exception as ex:
            self.loc_status = (str(ex) if isinstance(ex, ValueError) else "Can't reach the internet")
        self.dirty = True

    def weather_changed(self):
        """Location or units changed: the weather starts over."""
        w = getattr(self, "weather", None)
        if w is not None:
            w.reset()

    # -- Cartoons, Free Movies, News, Sports ----------------------------------------
    def live_list(self):
        """Plex's Live TV channels, fetched again every few hours."""
        when, chans = self.plex_live
        if not chans or time.time() - when > CHANNEL_REFRESH:
            chans = self.plex.live_channels()
            self.plex_live = (time.time(), chans)
        return chans

    def live_fresh(self):
        when, chans = self.plex_live
        return chans if chans and time.time() - when < CHANNEL_REFRESH else None

    def load_channels(self, i):
        """The list shows at once; Plex's channels follow when they come."""
        self.items[i] = self.channel_root(i)
        if self.status.get(i) != "loading":
            self.status.pop(i, None)
        if (LIBRARY[i].get("pick") in ("news", "sports") and self.plex.signed_in
                and self.live_fresh() is None and self.live_wait.get(i) not in ("loading", "error")):
            self.live_wait[i] = "loading"           # only now, so its answer can't be overwritten
            threading.Thread(target=self.fetch_inline, args=(i,), daemon=True).start()

    def channel_root(self, i):
        """Search; Plex folders and the old cartoons or films by kind (Cartoons, Free Movies);
        Plex's channels (News, Sports: with Search once you're signed in to Plex)."""
        tab = LIBRARY[i]
        pick = tab.get("pick")
        noun = {"toons": "a cartoon", "movies": "a film"}.get(pick, "a channel")
        rows = []
        if pick in SHELVES or self.plex.signed_in:
            rows.append(dict(item("chsearch:" + tab["name"], "Search", "chsearch", "",
                                  sub=f"Find {noun} by name"), icon="find"))
        for title, badge, what in PLEX_FOLDERS.get(pick, []):
            rows.append(dict(item("chdir:live:" + what, title, "chdir", "live:" + what,
                                  sub="Live channels on Plex"), icon=badge))
        if pick in SHELVES:
            shelves, badges, kind = SHELVES[pick]
            for folder, entries in shelves.items():
                rows.append(dict(item(f"chdir:shelf:{folder}", folder, "chdir", "shelf:" + folder,
                                      sub=f"{len(entries)} {kind}"), icon=badges.get(folder, "FILM")))
        if pick in ("news", "sports"):
            rows += self.inline_live(i, pick)
        return rows

    def inline_live(self, i, what):
        """Plex's news or sports channels, or a row saying why they aren't here."""
        name = f"{what.title()} channels"
        if not self.plex.signed_in:
            return [dict(item("chplex", name, "chplex", "", sub="Sign in to Plex"), icon="PLEX")]
        chans = self.live_fresh()
        if chans is not None:
            return [channel_row(c) for c in chans if live_pick(what, c)]
        if self.live_wait.get(i) == "error":
            return [dict(item("chretry", name, "chretry", "", sub="Plex didn't answer"), icon="PLEX")]
        return [dict(item("chwait", name, "chwait", "", sub="Getting them from Plex…"), icon="PLEX")]

    def fetch_inline(self, i):
        try:
            self.live_list()
            self.live_wait.pop(i, None)
        except Exception:
            self.live_wait[i] = "error"
        if not self.chan_stack.get(i):
            self.items[i] = self.channel_root(i)
        self.dirty = True

    def picked(self, tab, chans):
        """Every Plex channel a tab shows (for its search)."""
        pick = tab.get("pick")
        whats = [w for _, _, w in PLEX_FOLDERS.get(pick, [])] or [pick]
        return [c for c in chans if any(live_pick(w, c) for w in whats)]

    def open_dir(self, i, it):
        """A on a folder: old cartoons or films (built in), or Plex's channels of a kind."""
        src = it["src"]
        if src.startswith("shelf:"):
            folder = src[len("shelf:"):]
            shelves = SHELVES.get(LIBRARY[i].get("pick"), ({}, {}, ""))[0]
            self.chan_open(i, it["title"], [ia_row(folder, *t) for t in shelves.get(folder, [])], src=src)
            return
        what = src.split(":", 1)[1]
        if not self.plex.signed_in:
            self.chan_open(i, it["title"], [], src=src, status="noplex")
            return
        chans = self.live_fresh()
        if chans is not None:
            self.chan_open(i, it["title"], [channel_row(c) for c in chans if live_pick(what, c)], src=src)
            return
        folder = self.chan_open(i, it["title"], [], src=src, status="loading")

        def job():
            try:
                rows = [channel_row(c) for c in self.live_list() if live_pick(what, c)]
                failed = None
            except Exception:
                rows, failed = [], "error"
            folder["items"][:] = rows
            if self.chan_stack.get(i) and self.chan_stack[i][-1] is folder:
                self.status[i] = failed or (None if rows else "empty")
            self.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def chan_open(self, i, title, rows, src=None, status=None):
        folder = {"title": title, "items": rows, "src": src}
        self.chan_stack.setdefault(i, []).append(folder)
        self.items[i], self.sels[i], self.tops[i] = rows, 0, 0
        self.status[i] = status or (None if rows else "empty")
        self.dirty = True
        return folder

    def chan_search(self, text):
        """Every word you typed in the name: the old cartoons or films first, then Plex's channels."""
        i = self.tab
        tab = LIBRARY[i]
        pick = tab.get("pick")
        words = text.lower().split()

        def hit(s):
            return all(w in s.lower() for w in words)
        rows = []
        if pick in SHELVES:
            rows = [ia_row(folder, *t) for folder, entries in SHELVES[pick][0].items() for t in entries
                    if hit(f"{folder} {t[0]} {t[1]}")]
        hits = [c for c in self.picked(tab, self.plex_live[1]) if hit(channel_text(c))]
        hits.sort(key=lambda c: (not c["title"].lower().startswith(words[0]) if words else 0,
                                 c["title"].lower()))
        self.chan_open(i, f"“{text}”", rows + [channel_row(c) for c in hits])

    def channels_note(self):
        """Top right of Cartoons, Free Movies, News and Sports: where the list comes from."""
        stack = self.chan_stack.get(self.tab)
        src = (stack[-1].get("src") or "") if stack else ""
        pick = LIBRARY[self.tab].get("pick")
        n = len(self.tab_items())
        if src.startswith("shelf:"):
            return f"{n} {SHELVES[pick][2]} · archive.org"
        if stack and not src:
            return f"{n} found"
        if stack:
            return "from Plex Live TV"
        if pick in SHELVES:
            total = sum(len(t) for t in SHELVES[pick][0].values())
            return f"{total} old {SHELVES[pick][2]}"
        return "Live channels"

    def chan_back(self, i):
        stack = self.chan_stack.get(i)
        if not stack:
            return False
        gone = stack.pop()
        self.status.pop(i, None)
        self.load_tab(i)
        self.sels[i] = next((k for k, it in enumerate(self.items[i]) if it["title"] == gone["title"]), 0)
        self.dirty = True
        return True

    # -- Radio -----------------------------------------------------------------
    def radio_root(self, tab):
        mine = [dict(it, icon="MINE") for it in read_streams(tab["files"], kind="radio")]
        loc = self.setting("location") or {}
        cc = (loc.get("country") or "").upper()
        rows = mine + [
            dict(item("rsearch:", "Search stations", "radiosearch", "", sub="By name"), icon="FIND"),
            dict(item("rdir:top:" + cc, f"Popular in {cc}" if cc else "Popular worldwide", "radiodir",
                      "top:" + cc, sub="The most played"), icon="TOP"),
        ]
        for name, badge, tags in RADIO_GENRES:
            rows.append(dict(item("rdir:" + name, name, "radiodir", "genre:" + name), icon=badge))
        rp = next(st for st in RADIO_STATIONS if st[0] == "Radio Paradise")
        rows.append(dict(item("url:" + rp[2], rp[0], "radio", rp[2], sub=rp[1]), icon="RP"))
        return rows

    def radio_open(self, key, title):
        """Open a folder of stations: a genre, the most played, or a search."""
        ti = self.tab_index("radio")
        folder = {"key": key, "title": title, "items": []}
        self.radio_stack.append(folder)
        self.items[ti] = folder["items"]
        self.sels[ti] = 0
        self.tops[ti] = 0
        cached = self.state["radio"].get(key)
        if cached and time.time() - cached["t"] < RADIO_TTL and not key.startswith("search:"):
            folder["items"][:] = cached["items"]
        else:
            self.status[ti] = "loading"
            threading.Thread(target=self.radio_fetch, args=(folder,), daemon=True).start()
        self.dirty = True

    def radio_fetch(self, folder):
        ti = self.tab_index("radio")
        key = folder["key"]
        try:
            if key.startswith("genre:"):
                tags = next(t for n, _, t in RADIO_GENRES if n == key[6:])
                found = rb_stations(tags=tags)
            elif key.startswith("top:"):
                found = rb_stations(country=key[4:], limit=50)
            else:
                found = rb_stations(name=key[7:], limit=50)
            folder["items"][:] = found
            if not key.startswith("search:"):
                self.state["radio"][key] = {"t": time.time(), "items": found}
                self.save_state()
            self.status[ti] = None if found else "empty"
        except Exception:
            self.status[ti] = "error"
        self.dirty = True

    def radio_back(self):
        if not self.radio_stack:
            return False
        ti = self.tab_index("radio")
        gone = self.radio_stack.pop()
        self.status[ti] = None
        self.load_tab(ti)
        self.sels[ti] = next((k for k, it in enumerate(self.items[ti]) if it.get("src") == gone["key"]), 0)
        self.dirty = True
        return True

    def radio_save(self, it):
        """Y: a station into radio.txt, so it's in your list for good."""
        try:
            try:
                have = read_own_text(settings_file("radio.txt"))
            except FileNotFoundError:
                have = ""
            src = str(it["src"]).strip()
            if not src or re.search(r"\s", src):
                self.toast("Can't save that one", 2)
                return
            if src in have:
                self.toast("Already in your stations", 2)
                return
            line = f"{' '.join(str(it['title']).replace('|', '/').split()) or src} | {src}\n"
            if not have:
                have = "# Your stations for the Radio tab. One per line:   Name | URL\n"
            elif not have.endswith("\n"):
                have += "\n"
            write_setting("radio.txt", have + line)
            self.toast(f"Saved {it['title']} to your stations", 3)
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 3)

    # -- Weather ---------------------------------------------------------------
    def weather_drawn(self):
        if self.active and (self.view == "home" or (self.view == "list" and self.tab_type() == "weather")):
            self.dirty = True

    def wx_pages(self):
        return ["Now", "Week"] + (["Forecast"] if self.weather.nws else [])

    def press_weather(self, name, repeat):
        if name in ("left", "right") and not repeat:
            n = len(self.wx_pages())
            self.wx_page = (self.wx_page + (1 if name == "right" else -1)) % n
        elif name == "x" and not repeat:
            self.weather.refresh(force=True, full=True)
            self.toast("Refreshing", 2)
        elif name == "a" and not repeat and not self.setting("location"):
            self.loc_status = None
            self.toast("Finding you…", 3)
            threading.Thread(target=self.locate_job, args=(None,), daemon=True).start()
        self.dirty = True
        return None

    def wx_icon(self, name, size):
        key = (name, size)
        if key not in self.wx_icons:
            self.wx_icons[key] = draw_wx(name, size)
        return self.wx_icons[key]

    def deg(self, v):
        try:
            return f"{round(float(v))}°"
        except (TypeError, ValueError, OverflowError):
            return "—"

    def hour_label(self, stamp):
        try:
            t = time.strptime(stamp, "%Y-%m-%dT%H:%M")
        except ValueError:
            return ""
        if self.setting("clock") == "24-hour":
            return time.strftime("%H:00", t)
        return time.strftime("%-I %p", t)

    # -- the on-screen keyboard (and a real one, while it's up) ----------------
    def open_keyboard(self, title, text, done, strip=True, empty=False, row=1, limit=60):
        back = self.kb["back_to"] if self.kb else self.view       # one box straight after another
        self.kb = {"title": title, "text": text, "done": done, "r": row, "c": 0, "shift": False, "sym": False,
                   "back_to": back, "strip": strip, "empty": empty, "limit": limit}
        self.view = "keys"
        self.keyreader.on_key = self.keyboard_key
        self.keyreader.start()
        self.dirty = True

    def close_keyboard(self, ok):
        kb = self.kb
        self.keyreader.stop()
        self.kb = None
        if kb:
            self.view = kb["back_to"] if kb["back_to"] != "keys" else "list"
            text = kb["text"].strip() if kb.get("strip", True) else kb["text"]
            if ok and (text.strip() or kb.get("empty")):
                kb["done"](text)                        # may open another box (a password, say)
        self.dirty = True

    def keyboard_key(self, kind, ch=""):
        kb = self.kb
        if not kb:
            return
        if kind == "char":
            kb["text"] = (kb["text"] + ch)[:kb.get("limit", 60)]
        elif kind == "back":
            kb["text"] = kb["text"][:-1]
        elif kind in ("done", "cancel"):
            self.close_keyboard(kind == "done")
        self.dirty = True

    def press_keys(self, name, repeat):
        kb = self.kb
        if kb is None:
            self.view = "list"
            return None
        rows = len(KEY_ROWS) + 1
        if name in ("up", "down"):
            kb["r"] = (kb["r"] + (1 if name == "down" else -1)) % rows
            if kb["r"] == len(KEY_ROWS):
                kb["c"] = min(kb["c"] * len(KEY_BOTTOM) // 10, len(KEY_BOTTOM) - 1)
        elif name in ("left", "right"):
            n = len(KEY_BOTTOM) if kb["r"] == len(KEY_ROWS) else 10
            kb["c"] = (kb["c"] + (1 if name == "right" else -1)) % n
        elif name == "a":
            if kb["r"] < len(KEY_ROWS):
                ch = (KEY_SYMBOLS if kb["sym"] else KEY_ROWS)[kb["r"]][kb["c"] % 10]
                self.keyboard_key("char", ch.upper() if kb["shift"] else ch)
                kb["shift"] = False
            else:
                what = KEY_BOTTOM[kb["c"]][0]
                if what == "shift":
                    kb["shift"] = not kb["shift"]
                elif what == "sym":
                    kb["sym"] = not kb["sym"]
                elif what == "space":
                    self.keyboard_key("char", " ")
                elif what == "back":
                    self.keyboard_key("back")
                else:
                    self.keyboard_key("done")
        elif name == "x":
            self.keyboard_key("back")
        elif name == "y":
            self.keyboard_key("char", " ")
        elif name == "select" and not repeat:
            kb["shift"] = not kb["shift"]
        elif name == "start" and not repeat:
            self.keyboard_key("done")
        elif name == "b" and not repeat:
            self.close_keyboard(False)
        if self.kb is not None and kb["r"] == len(KEY_ROWS):
            kb["c"] = min(kb["c"], len(KEY_BOTTOM) - 1)
        self.dirty = True
        return None

    # -- the home screen ------------------------------------------------------
    def home_apps(self):
        """(name, tab) for each icon; the Terminal icon has no tab."""
        return [(LIBRARY[i]["name"], i) for i in self.visible_tabs()] + [("Terminal", None)]

    def playing_now(self):
        return bool(self.proc and self.kind in LISTEN_KINDS and self.cur)

    def press_home(self, name, repeat):
        apps = self.home_apps()
        n = len(apps)
        cols = home_cols(n)
        sel = self.home_sel
        if name in ("left", "right"):
            sel = (sel + (1 if name == "right" else -1)) % n
        elif name in ("up", "down"):                   # the nearest icon in the row above or below
            slots = home_layout(n, cols)
            r, c = slots[sel]
            row = [k for k, (rr, _) in enumerate(slots) if rr == r + (1 if name == "down" else -1)]
            if row:
                sel = min(row, key=lambda k: abs(slots[k][1] - c))
        elif name == "a" and not repeat:
            return self.open_app(apps[sel][1])
        elif name == "start" and not repeat and self.playing_now():
            self.view, self.now_from = "now", "home"
        elif name == "b" and not repeat:
            return "exit"
        self.home_sel = sel
        self.dirty = True
        return None

    def open_app(self, i):
        if i is None:                                  # Terminal
            return "exit"
        self.tab = i
        self.view = "list"
        self.load_tab(i)
        self.dirty = True
        return None

    def go_home(self):
        """B from an app: back to the icons, with that app picked."""
        ttype = self.tab_type()
        if ttype == "camera":
            self.camera.stop()
        elif ttype == "crypto":
            self.crypto.stop()
        elif ttype == "remote":
            self.hass.stop()
            self.remote_more = None
        self.confirm = (None, 0.0)
        self.picking = None
        self.friend_more = None
        self.set_page = "root"
        if ttype == "radio" and self.radio_stack:
            self.radio_stack = []
            self.status[self.tab] = None
        for k in list(self.chan_stack):                # home: the Cartoons folders close
            self.chan_stack[k] = []
        apps = self.home_apps()
        self.home_sel = next((k for k, a in enumerate(apps) if a[1] == self.strip_tab()), self.home_sel)
        self.view = "home"
        self.dirty = True

    def press_list(self, name, repeat):
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        ttype = self.tab_type()
        grid = ttype == "photos"
        cols = self.GRID_COLS if grid else 1
        page = self.grid_rows() * cols if grid else self.visible_rows()

        if ttype == "remote":
            r = self.press_remote(name, repeat)
            if r != "pass":
                return r
        if ttype == "settings":
            r = self.press_settings(name, repeat)
            if r != "pass":
                return r
        if ttype == "camera":
            r = self.press_cameras(name, repeat)
            if r != "pass":
                return r
        if ttype == "friend":
            r = self.press_friend(name, repeat)
            if r != "pass":
                return r
        if ttype == "photos" and self.picking == "bot" and name in ("a", "b") and not repeat:
            path = items[sel]["src"] if name == "a" and n else None
            self.picking = None
            self.tab = self.tab_index("friend")         # (back as it was: no hello in the way)
            self.friend.load(self.friend_files())
            if path:                                   # a word with it, or none: it's sent either way
                self.open_keyboard("Ask about this picture, or just send it", "",
                                   lambda text, path=path: self.friend_send(text, path), empty=True, limit=200)
            self.dirty = True
            return None
        if ttype == "photos" and self.picking == "wallpaper" and name in ("a", "b") and not repeat:
            if name == "a" and n:
                self.set_setting("picture", items[sel]["src"])
                self.set_setting("wallpaper", "Picture")
                self.toast("Background set", 2)
            self.picking = None
            self.tab = self.tab_index("settings")
            self.load_tab(self.tab)
            self.dirty = True
            return None
        if ttype == "radio" and not repeat:
            if name == "y" and self.radio_stack and n and items[sel]["kind"] == "radio":
                self.radio_save(items[sel])
                return None
            if name == "a" and self.radio_stack and not n and self.status.get(self.tab) in ("error", None):
                folder = self.radio_stack.pop()
                self.radio_open(folder["key"], folder["title"])
                return None
        if ttype == "channels" and not n and name == "a" and not repeat:
            stack = self.chan_stack.get(self.tab)
            if self.status.get(self.tab) == "error" and stack and stack[-1].get("src"):
                gone = stack.pop()                              # try that folder again
                self.open_dir(self.tab, {"title": gone["title"], "src": gone["src"]})
            elif self.status.get(self.tab) == "error":         # try again
                self.status.pop(self.tab, None)
                self.load_tab(self.tab)
            elif self.status.get(self.tab) == "noplex":        # off to Plex to sign in
                self.chan_stack[self.tab] = []
                self.tab = self.tab_index("plex")
                self.load_tab(self.tab)
            self.dirty = True
            return None
        if name == "b":
            if ttype == "plex" and self.plex_back():
                return None
            if ttype == "radio" and self.radio_back():
                return None
            if ttype == "channels" and self.chan_back(self.tab):
                return None
            if ttype == "browser" and self.cwd.rstrip("/") != home_dir() and self.cwd != "/":
                self.browse(os.path.dirname(self.cwd.rstrip("/")) or "/", select=self.cwd)
                return None
            parent = self.parent_of(self.tab)
            if parent is not None:                    # back out to the TV menu
                if ttype == "remote":
                    self.hass.stop()
                    if self.remote_pad is not None:
                        self.close_pad()
                self.chan_stack[self.tab] = []
                child = LIBRARY[self.tab]["name"]
                self.tab = parent
                self.load_tab(parent)
                self.sels[parent] = next((k for k, it in enumerate(self.items[parent])
                                          if it["title"] == child), 0)
                self.dirty = True
                return None
            self.go_home()
            return None
        if name in ("l", "r"):
            if not repeat:
                self.switch_tab(1 if name == "r" else -1)
                self.dirty = True
            return None
        if ttype == "plex":
            st = self.status.get(self.tab)
            if not self.plex.ready:
                if name == "a" and not repeat and st not in ("code", "finding") and not self.plex.pin:
                    self.plex_sign_in()
                return None
            if st == "loading":
                return None
            if not n and name == "a" and not repeat:
                self.plex_open("root", "Plex")
                return None
        if ttype == "crypto":
            return self.press_crypto(name, repeat)
        if ttype == "weather":
            return self.press_weather(name, repeat)
        if name == "x":
            self.view, self.help_from = "help", "list"
        elif name == "y" and ttype == "browser" and self.web_guard:
            self.toast("Hidden files stay hidden from the web page", 3)
        elif name == "y" and ttype == "browser":
            self.show_hidden = not self.show_hidden
            self.browse(self.cwd)
            self.toast("Showing hidden files" if self.show_hidden else "Hiding hidden files", 2)
        elif name == "start" and self.kind in LISTEN_KINDS:
            self.view, self.now_from = "now", "list"
        elif name == "start" and grid and n:
            self.open_photo([x["src"] for x in items], sel)
            self.v["slideshow"], self.v["next_t"] = True, time.monotonic() + SLIDESHOW_SECS
        elif n:
            step = {"up": -cols, "down": cols,
                    "left": -1 if grid else -page, "right": 1 if grid else page}.get(name)
            if step is not None:
                if grid or repeat or name in ("left", "right"):
                    sel = max(0, min(sel + step, n - 1))
                else:
                    sel = (sel + step) % n
                self.confirm = (None, 0.0)
            elif name == "a":
                self.open_item(items, sel)
                self.dirty = True
                return None
            self.sels[self.tab] = sel
        self.dirty = True
        return None

    def press_photo(self, name, repeat):
        v = self.v
        if v["slideshow"]:
            v["slideshow"] = False
            self.dirty = True
            return None
        if v["busy"]:                                  # saving a copy: wait for it
            return None
        if v["confirm"]:                               # "Delete this picture?"
            if name == "a" and not repeat:
                self.photo_delete()
            elif name in ("b", "select") and not repeat:
                v["confirm"] = False
            self.dirty = True
            return None
        if v["edit"]:                                  # picking a filter
            if name in ("left", "right") and not repeat:
                v["fi"] = (v["fi"] + (1 if name == "right" else -1)) % len(FILTERS)
            elif name == "y" and not repeat:
                v["rot"] = (v["rot"] + 1) % 4
            elif name == "a" and not repeat:
                self.photo_save_copy()
            elif name in ("b", "x") and not repeat:
                v.update(edit=False, fi=0)
            self.dirty = True
            return None
        if name == "x" and not repeat:
            v.update(edit=True, fi=0, zoom=1)
            self.dirty = True
            return None
        if name == "select" and not repeat:
            if in_home(v["items"][v["i"]]):
                v["confirm"] = True
            else:
                self.toast("Only pictures in your home folder can be deleted here", 3)
            self.dirty = True
            return None
        im = self.photo_image()
        zoomed = v["zoom"] > 1 and im is not None
        if name == "b":
            self.photo_back()
        elif name in ("l", "r") or (name in ("left", "right") and not zoomed):
            self.photo_step(-1 if name in ("l", "left") else 1)
        elif name in ("left", "right", "up", "down") and zoomed:
            AW, AH = self.fb.w, self.fb.h - self.FOOTER
            s = min(AW / im.width, AH / im.height) * v["zoom"]
            dx = {"left": -1, "right": 1}.get(name, 0) * AW * 0.25 / s
            dy = {"up": -1, "down": 1}.get(name, 0) * AH * 0.25 / s
            v["cx"], v["cy"] = v["cx"] + dx, v["cy"] + dy
        elif name == "a" and not repeat:
            v["zoom"] = {1: 2, 2: 4}.get(v["zoom"], 1)
            if v["zoom"] == 1 and im:
                v["cx"], v["cy"] = im.width / 2, im.height / 2
        elif name == "y" and not repeat:
            v["rot"] = (v["rot"] + 1) % 4
            v["zoom"] = 1
        elif name == "start":
            v["slideshow"], v["zoom"] = True, 1
            v["next_t"] = time.monotonic() + SLIDESHOW_SECS
        self.dirty = True
        return None

    def photo_back(self):
        v = self.v
        path = v["items"][v["i"]] if v.get("items") else None
        ttype = self.tab_type()
        if v.get("changed"):                           # deleted or added: the list again
            if ttype == "photos":
                self.load_tab(self.tab)
            elif ttype == "browser":
                self.browse(self.cwd, select=path)
        if ttype == "photos" and path:
            items = self.tab_items()
            self.sels[self.tab] = next((k for k, x in enumerate(items) if x["src"] == path),
                                       min(self.sels.get(self.tab, 0), max(len(items) - 1, 0)))
        self.last_shot = None
        self.close_viewer()

    PDF_ZOOMS = (1.0, 1.5, 2.0, 3.0)      # times the screen width

    def pdf_zoom(self, step):
        """X/Y: whole page, fit width, then closer — keeping the middle of the view."""
        v = self.v
        W, AH = self.fb.w, self.fb.h - self.FOOTER
        if v["fit"] == "page":
            if step > 0:
                v.update(fit="width", zoom=1.0, scroll=0, sx=0)
            return
        zs = self.PDF_ZOOMS
        i = zs.index(v["zoom"]) if v["zoom"] in zs else 0
        if step < 0 and i == 0:
            v.update(fit="page", zoom=1.0, scroll=0, sx=0)
            return
        j = max(0, min(i + step, len(zs) - 1))
        if j == i:
            self.toast("That's as close as it goes" if step > 0 else "", 2)
            return
        old = self.pdf_image()
        cx = v["sx"] + min(W, old.width) / 2 if old else W / 2
        cy = v["scroll"] + AH / 2
        r = zs[j] / zs[i]
        if (v["page"], "width", zs[j]) not in v["cache"]:
            self.render_wait(v["title"], f"Zoom {int(zs[j] * 100)}%")
        v["zoom"] = zs[j]
        v["sx"] = max(0, cx * r - W / 2)
        v["scroll"] = max(0, cy * r - AH / 2)

    def press_pdf(self, name, repeat):
        v = self.v
        W, AH = self.fb.w, self.fb.h - self.FOOTER
        if name == "b":
            self.close_viewer()
            return None
        im = self.pdf_image()
        wide = v["fit"] == "width" and im is not None and im.width > W
        if name in ("x", "y"):
            if not repeat:
                self.pdf_zoom(1 if name == "x" else -1)
        elif name in ("left", "right"):
            if wide:                                   # zoomed in: slide across the page
                v["sx"] = max(0, min(v["sx"] + (W // 3) * (1 if name == "right" else -1),
                                     im.width - W))
            elif not repeat:
                self.pdf_goto(v["page"] + (1 if name == "right" else -1))
        elif name in ("l", "r"):
            if not repeat:
                self.pdf_goto(v["page"] + (1 if name == "r" else -1))
        elif name in ("start", "select"):
            if not repeat:
                self.pdf_goto(v["page"] + (10 if name == "start" else -10))
        elif name == "a" and not repeat:
            if v["fit"] == "width":
                v.update(fit="page", zoom=1.0, scroll=0, sx=0)
            else:
                v.update(fit="width", zoom=1.0, scroll=0, sx=0)
        elif name in ("up", "down"):
            limit = max((im.height if im else AH) - AH, 0)
            step = AH // 4 * (1 if name == "down" else -1)
            if v["fit"] == "page" or limit == 0:
                if not repeat:
                    self.pdf_goto(v["page"] + (1 if name == "down" else -1))
            elif name == "down" and v["scroll"] >= limit:
                if not repeat:
                    self.pdf_goto(v["page"] + 1)
            elif name == "up" and v["scroll"] <= 0:
                if not repeat and v["page"] > 1:
                    self.pdf_goto(v["page"] - 1, at_bottom=True)
            else:
                v["scroll"] = max(0, min(v["scroll"] + step, limit))
        self.dirty = True
        return None

    def press_text(self, name, repeat):
        v = self.v
        rows, _ = self.text_rows()
        n = len(self.text_lines())
        if name == "b":
            self.close_viewer()
            return None
        if name in ("up", "down"):
            v["top"] += 1 if name == "down" else -1
        elif name in ("left", "right"):
            v["top"] += (rows - 1) * (1 if name == "right" else -1)
        elif name in ("l", "r") and not repeat:
            v["top"] = 0 if name == "l" else n
        elif name == "a" and not repeat:
            first = v["lines"][v["top"]] if v["lines"] and v["top"] < len(v["lines"]) else ""
            v["size"] = 1 - v["size"]
            v["lines"] = None
            lines = self.text_lines()
            v["top"] = next((k for k, l in enumerate(lines) if first and l.startswith(first[:20])), 0)
            rows, _ = self.text_rows()
            n = len(lines)
        v["top"] = max(0, min(v["top"], max(n - rows, 0)))
        self.dirty = True
        return None

    def flush(self):
        """Redraw the screen if something changed (never over a video, or 'Shutting down')."""
        if not (self.active and self.dirty and self.fb) or time.monotonic() < self.halting:
            return
        if self.proc_owns_screen():
            return
        self.dirty = False
        draw = {"home": self.render_home, "keys": self.render_keys, "help": self.render_help,
                "learn": self.render_learn,
                "photo": self.render_photo,
                "pdf": self.render_pdf,
                "text": self.render_text, "wait": lambda: self.render_wait(
                    self.v.get("title", ""), self.v.get("status", ""))}.get(self.view)
        if draw:
            draw()
        elif self.view == "now" and self.kind in LISTEN_KINDS:
            self.render_now()
        else:
            self.render_list()

    # -- drawing -------------------------------------------------------------
    STATUS_H, HEADER, LIST_TOP = 26, 68, 76   # status bar, tab line, first row
    ROW_H, FOOTER = 48, 48
    GRID_COLS, CELL_H = 4, 116

    def load_fonts(self):
        if self.fonts:
            return
        from PIL import ImageFont

        def f(path, size):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                return ImageFont.load_default()
        self.fonts = {
            "tab": f(FONT, 17), "tab_b": f(FONT_BOLD, 17),
            "row": f(FONT, 20), "row_b": f(FONT_BOLD, 20), "small": f(FONT, 15),
            "key": f(FONT_BOLD, 13), "badge": f(FONT_BOLD, 11), "big": f(FONT_BOLD, 24),
            "note": f(FONT, 72), "mono_s": f(FONT_MONO, 15), "mono_l": f(FONT_MONO, 20),
            "head": f(FONT_BOLD, 18), "status": f(FONT, 13), "status_b": f(FONT_BOLD, 13),
            "code": f(FONT_MONO, 44), "price": f(FONT_BOLD, 46), "mid": f(FONT_BOLD, 24),
            "clock": f(FONT_BOLD, 52), "small_b": f(FONT_BOLD, 15), "label": f(FONT, 14), "temp": f(FONT_BOLD, 72),
            "keycap": f(FONT, 20), "face": f(FONT, 40), "chat": f(FONT, 18),
        }

    def list_top(self):
        crumbs = (self.tab_type() in ("browser", "plex") or self.parent_of(self.tab) is not None
                  or (self.tab_type() == "radio" and self.radio_stack))
        return self.LIST_TOP + (28 if crumbs else 0)

    def visible_rows(self):
        h = self.fb.h if self.fb else 480
        return max((h - self.FOOTER - self.list_top()) // self.ROW_H, 1)

    def grid_rows(self):
        h = self.fb.h if self.fb else 480
        return max((h - self.FOOTER - self.LIST_TOP) // self.CELL_H, 1)

    def canvas(self, bg=BG):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (self.fb.w, self.fb.h), bg)
        return img, ImageDraw.Draw(img)

    @staticmethod
    def fit(d, text, font, width):
        if d.textlength(text, font=font) <= width:
            return text
        while text and d.textlength(text + "…", font=font) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, d, text, font, width, lines=2):
        words, out, cur = text.split(), [], ""
        for w in words:
            if d.textlength((cur + " " + w).strip(), font=font) <= width:
                cur = (cur + " " + w).strip()
            else:
                out.append(cur)
                cur = w
        out.append(cur)
        out = [l for l in out if l]
        if len(out) > lines:
            out = out[:lines - 1] + [self.fit(d, " ".join(out[lines - 1:]), font, width)]
        return [self.fit(d, l, font, width) for l in out]

    def key_w(self, d, label):
        return max(d.textlength(label, font=self.fonts["key"]) + 14, 24)

    def key(self, d, x, y, label, on=False):
        """Button icon (pill with label), vertically centred on y, lit when what it turns on is
        on. Returns end x."""
        F = self.fonts
        w = self.key_w(d, label)
        d.rounded_rectangle((x, y - 11, x + w, y + 11), radius=11, fill=ACCENT if on else LINE)
        d.text((x + w / 2, y), label, font=F["key"], fill=BG if on else TEXT, anchor="mm")
        return x + w

    def footer(self, d, items, right=None, credit=None):
        """Button hints along the bottom (key, label[, lit]) and a note on the right. A credit
        (where the numbers come from) is always shown, as clearly as the hints: any hint that
        would run into it is left out instead."""
        F, W, H = self.fonts, self.fb.w, self.fb.h
        y = H - self.FOOTER // 2
        d.rectangle((0, H - self.FOOTER, W, H), fill=BG)
        d.line((0, H - self.FOOTER, W, H - self.FOOTER), fill=LINE)
        room = W - 20 - (d.textlength(credit, font=F["small"]) + 18 if credit else 0)
        x = 20
        for it in items:
            k, label, on = it[0], it[1], len(it) > 2 and bool(it[2])
            if credit and x + self.key_w(d, k) + 7 + d.textlength(label, font=F["small"]) > room:
                break
            x = self.key(d, x, y, k, on) + 7
            d.text((x, y), label, font=F["small"], fill=BODY, anchor="lm")
            x += d.textlength(label, font=F["small"]) + 18
        if credit:
            d.text((W - 20, y), credit, font=F["small"], fill=BODY, anchor="rm")
        elif right and x + d.textlength(right, font=F["small"]) < W - 20:
            d.text((W - 20, y), right, font=F["small"], fill=MUTED, anchor="rm")
        if self.msg:                      # short notice above the footer
            msg = self.fit(d, self.msg, F["small"], W - 72)
            mw = d.textlength(msg, font=F["small"]) + 32
            y0 = H - self.FOOTER - 46
            d.rounded_rectangle(((W - mw) / 2, y0, (W + mw) / 2, y0 + 34), radius=17, fill=ROW)
            d.text((W / 2, y0 + 17), msg, font=F["small"], fill=TEXT, anchor="mm")

    # status bar and headers -----------------------------------------------------
    def status_signature(self):
        t = cpu_temp()
        return (time.strftime("%H:%M"), wifi_bars(wifi_quality()),
                None if t is None else round(t), self.kind, self.meta.get("song"))

    def status_bar(self, d, clock=True):
        F, W = self.fonts, self.fb.w
        y = self.STATUS_H // 2 + 1
        if clock:
            d.text((20, y), self.clock_text(), font=F["status_b"], fill=BODY, anchor="lm")
        x = W - 20
        bars = wifi_bars(wifi_quality())
        for k in range(4):                       # signal bars, weakest on the left
            bx = x - (3 - k) * 6 - 4
            h = 4 + k * 3
            d.rectangle((bx, y + 6 - h, bx + 3, y + 6), fill=TEXT if k < bars else LINE)
        x -= 34
        if bars == 0:
            d.text((x, y), "No WiFi", font=F["status"], fill=WARN, anchor="rm")
            x -= d.textlength("No WiFi", font=F["status"]) + 14
        t = cpu_temp()
        if t is not None:
            txt = f"{t:.0f}°C"
            d.text((x, y), txt, font=F["status"], fill=WARN if t >= HOT_C else MUTED, anchor="rm")
            x -= d.textlength(txt, font=F["status"]) + 14
        if self.proc and self.kind in LISTEN_KINDS and self.cur:
            what = self.meta.get("song") or self.meta.get("title") or self.cur["title"]
            txt = self.fit(d, "♪ " + what, F["status"], max(x - 120, 40))
            d.text((x, y), txt, font=F["status"], fill=ACCENT, anchor="rm")

    def header(self, img, d):
        """Status bar plus the tab strip, scrolled so the current tab shows."""
        from PIL import Image, ImageDraw
        self.status_bar(d)
        F, W = self.fonts, self.fb.w
        vis = self.visible_tabs()
        cur = vis.index(self.strip_tab())
        names = []
        for i in vis:
            tab = LIBRARY[i]
            name = tab["name"]
            if self.proc and ((self.kind == "audio" and tab.get("kind") == "audio")
                              or (self.kind == "radio" and tab["type"] == "radio")):
                name = "♪ " + name
            names.append(name)
        fonts = [F["tab_b"] if i == cur else F["tab"] for i in range(len(names))]
        widths = [d.textlength(n, font=f) for n, f in zip(names, fonts)]
        gap, xs, x = 20, [], 0
        for w in widths:
            xs.append(x)
            x += w + gap
        total, avail = x - gap, W - 40
        off = self.tab_off
        if total <= avail:
            off = 0
        else:
            left, right = xs[cur], xs[cur] + widths[cur]
            if left - off < 0:
                off = left
            if right - off > avail:
                off = right - avail
            # keep the neighbours in view too, so you can see where L/R go next
            if cur > 0 and xs[cur - 1] < off:
                off = max(off - (off - xs[cur - 1]), right - avail, 0)
            if cur + 1 < len(xs) and xs[cur + 1] + widths[cur + 1] - off > avail:
                off = min(xs[cur + 1] + widths[cur + 1] - avail, left)
            off = max(0, min(off, total - avail))
        self.tab_off = off
        strip_h = self.HEADER - self.STATUS_H
        strip = Image.new("RGB", (avail, strip_h), BG)
        sd = ImageDraw.Draw(strip)
        y = strip_h // 2 - 2
        for i, (n, f, w) in enumerate(zip(names, fonts, widths)):
            tx = xs[i] - off
            if tx < 0 or tx + w > avail:      # only whole tabs; arrows show the rest
                continue
            sd.text((tx, y), n, font=f, fill=TEXT if i == cur else MUTED, anchor="lm")
            if i == cur:
                sd.rounded_rectangle((tx, strip_h - 7, tx + w, strip_h - 4), radius=1, fill=ACCENT)
        img.paste(strip, (20, self.STATUS_H))
        cy = self.STATUS_H + y
        if off > 0:
            d.text((10, cy), "‹", font=F["tab_b"], fill=MUTED, anchor="mm")
        if off < total - avail:
            d.text((W - 10, cy), "›", font=F["tab_b"], fill=MUTED, anchor="mm")
        d.line((0, self.HEADER, W, self.HEADER), fill=LINE)

    def title_row(self, d, title, right=None, right_fill=MUTED):
        """Status bar plus a plain title, for screens that aren't tabs."""
        self.status_bar(d)
        F, W = self.fonts, self.fb.w
        y = (self.STATUS_H + self.HEADER) // 2
        rw = d.textlength(right, font=F["small"]) + 24 if right else 0
        d.text((20, y), self.fit(d, title, F["head"], W - 40 - rw), font=F["head"],
               fill=TEXT, anchor="lm")
        if right:
            d.text((W - 20, y), right, font=F["small"], fill=right_fill, anchor="rm")
        d.line((0, self.HEADER, W, self.HEADER), fill=LINE)

    def scrollbar(self, d, top, rows, n, t0, t1):
        if n <= rows:
            return
        sx = self.fb.w - 10
        d.rounded_rectangle((sx, t0, sx + 4, t1), radius=2, fill=LINE)
        th = max((t1 - t0) * rows / n, 24)
        ty = t0 + (t1 - t0 - th) * top / max(n - rows, 1)
        d.rounded_rectangle((sx, ty, sx + 4, ty + th), radius=2, fill=BODY)

    def row_right(self, it):
        """Text and colour on the right of a list row, plus resume fraction."""
        kind = it["kind"]
        if kind == "info":
            return it["sub"], WARN if it.get("warn") else TEXT, None
        if kind == "action":
            if self.confirm[0] == it["src"]:
                return "press A again", ACCENT, None
            return "", MUTED, None
        if kind in ("radio", "radiodir", "radiosearch", "plexsearch", "chdir", "chsearch", "chplex",
                    "chretry", "chwait"):
            return it.get("sub", ""), MUTED, None
        if kind == "plexvideo":
            length, off = it.get("dur") or 0, it.get("off") or 0
            year = f"{it['sub']}  " if it.get("ptype") == "movie" and it.get("sub") else ""
            if off > 10 and length and off < length - 30:
                return f"{clock(length - off)} left", ACCENT, off / length
            if it.get("watched"):
                return "✓ " + year + clock(length), DONE, None
            return year + (clock(length) if length else ""), MUTED, None
        if kind == "child":
            return it.get("sub", ""), MUTED, None
        if kind == "plexwant":
            return "not on your server", MUTED, None
        if kind == "plexdir":
            if it.get("unwatched"):
                return f"{it['unwatched']} unwatched", ACCENT, None
            return it.get("sub", ""), MUTED, None
        if kind == "live":
            return it.get("sub") or "live", MUTED, None
        if self.tab_type() == "browser":
            if kind == "up":
                return "", MUTED, None
            if kind == "dir":
                try:
                    n = len([x for x in os.listdir(it["src"])
                             if self.show_hidden or not x.startswith(".")])
                    return f"{n} item{'s' if n != 1 else ''}", MUTED, None
                except OSError:
                    return "", MUTED, None
            try:
                return human_size(os.path.getsize(it["src"])), MUTED, None
            except OSError:
                return "", MUTED, None
        length = self.length(it)
        saved = self.state["pos"].get(it["key"], 0)
        resume = self.resume_at(it)
        if saved == -1:
            return "✓ " + (clock(length) if length else "watched"), DONE, None
        if resume:
            if length:
                return f"{clock(length - resume)} left", ACCENT, resume / length
            return f"at {clock(resume)}", ACCENT, None
        if "://" in it["src"]:
            return (clock(length) if length else ""), MUTED, None
        if it["src"].startswith("ia:"):                # an old cartoon: its year
            return (clock(length) if length else it.get("sub", "")), MUTED, None
        return (clock(length) if length else "…"), MUTED, None

    def badge(self, d, x, mid, it):
        F = self.fonts
        kind = it["kind"]
        if kind == "up":
            label, colour = "UP", MUTED
        elif kind == "dir":
            label, colour = "DIR", BADGE["dir"]
        else:
            ext = os.path.splitext(it["src"])[1][1:].upper()[:4] or "FILE"
            label, colour = ext, BADGE.get(kind, MUTED)
        d.rounded_rectangle((x, mid - 10, x + 40, mid + 10), radius=5, outline=colour, width=1)
        d.text((x + 20, mid), label, font=F["badge"], fill=colour, anchor="mm")
        return x + 52

    def list_hints(self):
        ttype = self.tab_type()
        items = self.tab_items()
        sel = self.sels.get(self.tab, 0)
        first = ("A", "Play")
        if ttype == "browser":
            first = ("A", "Open")
        elif ttype == "photos":
            first = ("A", "View")
        elif ttype == "radio":
            it = items[sel] if items and sel < len(items) else {}
            first = ("A", "Open" if it.get("kind") in ("radiodir", "radiosearch") else "Listen")
        elif ttype == "system":
            first = ("A", "Select")
        elif ttype == "plex":
            it = items[sel] if items and sel < len(items) else {}
            first = ("A", "Watch" if it.get("kind") == "live" else
                     "Open" if it.get("kind") != "plexvideo" else
                     "Resume" if it.get("off", 0) > 10 else "Play")
        elif items and sel < len(items) and self.resume_at(items[sel]):
            first = ("A", "Resume")
        hints = [first, ("L R", "Tabs")]
        if ttype == "browser":
            hints += [("B", "Up" if self.cwd.rstrip("/") != home_dir() and self.cwd != "/" else "Home"),
                      ("Y", "Hidden")]
        elif ttype == "photos":
            hints += [("START", "Slideshow"), ("B", "Home")]
            if self.picking == "wallpaper":
                hints = [("A", "Use as background"), ("B", "Cancel")]
            elif self.picking == "bot":
                hints = [("A", "Send to your bot"), ("B", "Cancel")]
        elif ttype == "system":
            hints += [("B", "Home")]
        elif ttype == "plex":
            hints += [("B", "Back" if len(self.plex_stack) > 1 else "Home")]
        else:
            hints += [("X", "Controls"), ("B", "Home")]
        if self.kind in LISTEN_KINDS and ttype != "photos":
            hints.append(("START", "Now playing"))
        if not items:
            hints = [h for h in hints if h[0] not in ("A", "START")]
        if self.parent_of(self.tab) is not None:
            hints = [("B", "Back") if h[0] == "B" else h for h in hints]
        if ttype == "group":
            hints = [("A", "Open"), ("L R", "Tabs"), ("B", "Home")] + hints[4:]
        if ttype == "channels" and items and sel < len(items):
            it = items[sel]
            first = {"chdir": "Open", "chsearch": "Open", "chplex": "Sign in", "chretry": "Try again"}.get(
                it["kind"], "Resume" if self.resume_at(it) else "Watch")
            hints = ([] if it["kind"] == "chwait" else [("A", first)]) + hints[1:]
        if ttype == "channels" and not items and self.status.get(self.tab) in ("error", "noplex"):
            hints = [("A", "Try again" if self.status.get(self.tab) == "error" else "Sign in"),
                     ("L R", "Tabs"), ("B", "Back")]
        if ttype == "radio" and self.radio_stack:
            hints = [first, ("Y", "Save"), ("L R", "Tabs"), ("B", "Back")]
            if self.kind in LISTEN_KINDS:
                hints.append(("START", "Now playing"))
            if not items:
                hints = [("A", "Try again") if self.status.get(self.tab) == "error" else ("L R", "Tabs"),
                         ("B", "Back")]
        return hints

    def empty_state(self, d, big, small):
        F, W, H = self.fonts, self.fb.w, self.fb.h
        mid = (self.HEADER + H - self.FOOTER) / 2
        d.text((W / 2, mid - 16), big, font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, mid + 18), small, font=F["small"], fill=MUTED, anchor="mm")

    def render_list(self):
        ttype = self.tab_type()
        if ttype == "photos":
            return self.render_grid()
        if ttype == "camera":
            return self.render_cameras() if self.cam_list else self.render_camera()
        if ttype == "friend":
            return self.render_friend()
        if ttype == "crypto":
            return self.render_crypto()
        if ttype == "remote":
            return self.render_remote()
        if ttype == "settings":
            return self.render_settings()
        if ttype == "weather":
            return self.render_weather()
        if ttype == "plex" and not self.plex.ready:
            return self.render_plex_signin()
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        self.header(img, d)
        top_y = self.list_top()
        if ttype == "browser":
            d.text((20, self.LIST_TOP + 10), self.fit(d, short_path(self.cwd), F["small"], W - 40),
                   font=F["small"], fill=MUTED, anchor="lm")
        elif self.parent_of(self.tab) is not None and ttype != "plex":
            crumbs = LIBRARY[self.parent_of(self.tab)]["name"] + "  ›  " + LIBRARY[self.tab]["name"]
            if self.chan_stack.get(self.tab):
                crumbs += "  ›  " + self.chan_stack[self.tab][-1]["title"]
            if ttype == "channels":
                d.text((W - 20, self.LIST_TOP + 10), self.channels_note(), font=F["small"],
                       fill=MUTED, anchor="rm")
            d.text((20, self.LIST_TOP + 10), crumbs, font=F["small"], fill=MUTED, anchor="lm")
        elif ttype == "radio" and self.radio_stack:
            crumbs = "Radio  ›  " + self.radio_stack[-1]["title"]
            d.text((20, self.LIST_TOP + 10), self.fit(d, crumbs, F["small"], W - 200), font=F["small"],
                   fill=MUTED, anchor="lm")
            d.text((W - 20, self.LIST_TOP + 10), "from radio-browser.info", font=F["small"],
                   fill=MUTED, anchor="rm")
        if ttype == "plex":
            loading = self.status.get(self.tab) == "loading" and n
            right = "Loading…" if loading else self.plex.server_name
            rw = d.textlength(right, font=F["small"])
            d.text((W - 20, self.LIST_TOP + 10), right, font=F["small"],
                   fill=ACCENT if loading else MUTED, anchor="rm")
            crumbs = "  ›  ".join(["TV"] + [l["title"] for l in self.plex_stack] or ["Plex"])
            d.text((20, self.LIST_TOP + 10), self.fit(d, crumbs, F["small"], W - 60 - rw),
                   font=F["small"], fill=MUTED, anchor="lm")

        if not n:
            status = self.status.get(self.tab)
            big, small = {
                "loading": ("Loading", "Getting the channels from Plex"
                            if ttype == "channels" else "Finding stations" if ttype == "radio" else "One moment"),
                "error": ("Can't connect", "Check the WiFi, then press L or R to retry"
                          if ttype not in ("plex", "radio", "channels")
                          else "Check the WiFi, then press A to try again"),
                "empty": ("No stations found" if ttype == "radio" else "Nothing found",
                          "Try another name" if ttype != "channels" else
                          LIBRARY[self.tab]["empty"] if not self.chan_stack.get(self.tab) else
                          "Nothing on Plex Live TV right now"
                          if (self.chan_stack[self.tab][-1].get("src") or "").startswith("live:")
                          else "Try another name"),
                "noplex": ("Sign in to Plex first", "These channels come from Plex's free Live TV. "
                           "Press A to sign in"),
            }.get(status, ("Nothing here yet", LIBRARY[self.tab]["empty"]))
            self.empty_state(d, big, small)
            self.footer(d, self.list_hints())
            self.fb.show(img)
            return

        rows = self.visible_rows()
        top = self.tops.get(self.tab, 0)
        if sel < top:
            top = sel
        elif sel >= top + rows:
            top = sel - rows + 1
        top = max(min(top, n - rows), 0)
        self.tops[self.tab] = top

        x0, x1 = 12, W - 22
        # one column width for the artwork, so titles line up when posters and stills mix
        slot = max([self.plex_size(it)[0] for it in items[top:top + rows]
                    if not it.get("icon")] or [0])
        for r, i in enumerate(range(top, min(top + rows, n))):
            it = items[i]
            kind = it["kind"]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            selected = i == sel
            if selected:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            tx = x0 + 18
            if ttype == "browser":
                tx = self.badge(d, tx, mid, it)
            elif (ttype in ("plex", "group") or (ttype == "radio" and not self.radio_stack)
                  or kind in ("chdir", "chsearch", "chplex", "chretry", "chwait")) and kind != "action":
                tx = self.plex_art(img, d, tx, mid, it, slot)
            right, colour, frac = self.row_right(it)
            if (self.proc and self.kind in LISTEN_KINDS and self.cur
                    and self.cur["key"] == it["key"]):
                right, colour = ("paused" if self.paused else "playing"), ACCENT

            if kind == "info":            # label on the left, reading on the right
                d.text((tx, mid), it["title"], font=F["small"],
                       fill=BODY if selected else MUTED, anchor="lm")
                vfont = F["row_b"] if selected else F["row"]
                d.text((x1 - 14, mid), self.fit(d, right, vfont, x1 - 14 - tx - 170),
                       font=vfont, fill=colour, anchor="rm")
                continue

            rw = d.textlength(right, font=F["small"]) if right else 0
            if right:
                d.text((x1 - 14, mid), right, font=F["small"], fill=colour, anchor="rm")
            font = F["row_b"] if selected or kind == "action" else F["row"]
            name = self.fit(d, it["title"], font, x1 - 14 - rw - 16 - tx)
            fill = TEXT if selected else BODY
            if kind == "plexwant":
                fill = BODY if selected else MUTED
            if kind == "action" and it["src"] == "poweroff":
                fill = WARN
            d.text((tx, mid - 3 if frac else mid), name, font=font, fill=fill, anchor="lm")

            if frac:                   # how far into the video you are
                by, bx1 = y + self.ROW_H - 12, x1 - 14
                d.rounded_rectangle((tx, by, bx1, by + 3), radius=1, fill=LINE)
                d.rounded_rectangle((tx, by, tx + (bx1 - tx) * min(frac, 1), by + 3),
                                    radius=1, fill=ACCENT)

        self.scrollbar(d, top, rows, n, top_y + 4, top_y + rows * self.ROW_H - 4)
        self.footer(d, self.list_hints(),
                    right=f"{sel + 1} of {n}" if ttype not in ("browser", "system", "group") else None)
        self.fb.show(img)

    def plex_art(self, img, d, x, mid, it, slot=0):
        """Poster (or episode still) at the start of a Plex row."""
        F = self.fonts
        icon = it.get("icon")
        if icon:
            label = {"deck": "NEXT", "movie": "FILM", "show": "TV", "live": "LIVE", "find": "FIND",
                     "list": "LIST"}.get(icon, icon)
            d.rounded_rectangle((x, mid - 10, x + 40, mid + 10), radius=5, outline=ACCENT, width=1)
            d.text((x + 20, mid), label, font=F["badge"], fill=ACCENT, anchor="mm")
            return x + 52
        w, h = self.plex_size(it)
        y = int(mid - h / 2)
        t = self.plex_thumb(it, (w, h)) if it.get("thumb") else None
        if t is not None:
            img.paste(t, (int(x), y))
        else:
            d.rounded_rectangle((x, y, x + w, y + h), radius=3, fill=LINE)
        return x + max(w, slot) + 12

    def render_plex_signin(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        mid = (self.HEADER + H - self.FOOTER) / 2
        st = self.status.get(self.tab)
        pin = self.plex.pin
        hints = [("A", "Sign in"), ("L R", "Tabs"), ("B", "Back")]
        if pin:
            d.text((W / 2, mid - 78), "On your phone or computer, go to",
                   font=F["small"], fill=MUTED, anchor="mm")
            d.text((W / 2, mid - 52), "plex.tv/link", font=F["big"], fill=TEXT, anchor="mm")
            code = "  ".join(pin["code"])
            cw = d.textlength(code, font=F["code"]) + 56
            d.rounded_rectangle(((W - cw) / 2, mid - 26, (W + cw) / 2, mid + 50), radius=16, fill=ROW)
            d.text((W / 2, mid + 12), code, font=F["code"], fill=ACCENT, anchor="mm")
            mins = max(int((pin["until"] - time.monotonic()) // 60), 0)
            d.text((W / 2, mid + 78), f"and type this code. Waiting…  (good for {mins} min)",
                   font=F["small"], fill=MUTED, anchor="mm")
            hints = [("L R", "Tabs"), ("B", "Back")]
        else:
            big, small = {
                "code": ("Getting a code", "One moment"),
                "finding": ("Signed in", "Looking for your Plex server"),
                "noserver": ("No Plex server found", "Make sure your server is on, then press A"),
                "offline": ("Can't reach plex.tv", "Check the WiFi, then press A to try again"),
            }.get(st, ("Watch your Plex library", "Press A to sign in with a code"))
            # a simple chevron, Plex-style
            cx, cy = W / 2, mid - 62
            d.polygon([(cx - 14, cy - 26), (cx + 2, cy - 26), (cx + 22, cy), (cx + 2, cy + 26),
                       (cx - 14, cy + 26), (cx + 6, cy)], fill=ACCENT)
            d.text((W / 2, mid + 2), big, font=F["big"], fill=TEXT, anchor="mm")
            d.text((W / 2, mid + 34), small, font=F["small"], fill=MUTED, anchor="mm")
            if st in ("code", "finding"):
                hints = [("L R", "Tabs"), ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)

    def render_grid(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        self.header(img, d)
        if not n:
            self.empty_state(d, "Nothing here yet", LIBRARY[self.tab]["empty"])
            self.footer(d, self.list_hints())
            self.fb.show(img)
            return
        cols, rows = self.GRID_COLS, self.grid_rows()
        top = self.tops.get(self.tab, 0)          # in rows
        srow = sel // cols
        if srow < top:
            top = srow
        elif srow >= top + rows:
            top = srow - rows + 1
        total_rows = (n + cols - 1) // cols
        top = max(min(top, total_rows - rows), 0)
        self.tops[self.tab] = top
        cw = (W - 32) // cols
        tw, th = self.THUMB
        for r in range(rows):
            for c in range(cols):
                i = (top + r) * cols + c
                if i >= n:
                    break
                x = 12 + c * cw + (cw - tw) // 2
                y = self.LIST_TOP + 2 + r * self.CELL_H + (self.CELL_H - th) // 2
                if i == sel:
                    d.rounded_rectangle((x - 5, y - 5, x + tw + 5, y + th + 5), radius=10,
                                        outline=ACCENT, width=3)
                t = self.thumb(items[i]["src"])
                if t is not None:
                    img.paste(t, (x, y))
                else:
                    d.rounded_rectangle((x, y, x + tw, y + th), radius=6, fill=ROW)
        self.scrollbar(d, top, rows, total_rows, self.LIST_TOP + 6,
                       self.LIST_TOP + rows * self.CELL_H)
        self.footer(d, self.list_hints(),
                    right=self.fit(d, items[sel]["title"], F["small"], 150))
        self.fb.show(img)

    def render_crypto(self):
        cr = self.crypto
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.HEADER + 1, H - self.FOOTER
        d.rectangle((0, top, W, bottom), fill=PI_BG)          # PiE-ink's black card
        cards = cr.cards()
        card = cards[self.crypto_card % len(cards)] if cards else None
        window = dict(CRYPTO_WINDOWS).get(cr.days, "1D")
        self.draw_coin(d, card[1] if card else None, top, bottom, window)
        # (A lights up while Auto is on; CoinGecko asks for a credit next to its numbers)
        hints = [("◀▶", "Coin"), ("▲▼", window), ("A", "Auto", self.crypto_auto), ("X", "Refresh"), ("B", "Home")]
        if len(cards) > 1:                                     # which card this is
            gap = 14
            x = W / 2 - (len(cards) - 1) * gap / 2
            for k in range(len(cards)):
                on = k == self.crypto_card % len(cards)
                r = 4 if on else 3
                d.ellipse((x - r, bottom - 16 - r, x + r, bottom - 16 + r), fill=PI_FG if on else (70, 70, 70))
                x += gap
        self.footer(d, hints, credit="Source: CoinGecko")  # (the dots above say which card)
        self.fb.show(img)

    def draw_coin(self, d, cid, top, bottom, window):
        """PiE-ink's coin card: name, price and change, high/low, the chart,
        then market cap, supply and the all-time high, and the community mood."""
        F = self.fonts
        cr = self.crypto
        W = self.fb.w
        pad = 24
        y0 = top + 14
        coin = cr.coin(cid) if cid else {"name": "", "symbol": ""}
        qe = cr.quotes.get(cid) or {}
        q = qe.get("d") or {}
        he = cr.hist.get(f"{cid}:{cr.days}") or {}
        name = (q.get("name") or coin["name"]).upper()
        d.text((pad, y0), name, font=F["small"], fill=PI_DIM)
        if q.get("rank"):
            d.text((pad + d.textlength(name, font=F["small"]) + 10, y0), f"#{q['rank']}",
                   font=F["small"], fill=(90, 90, 90))
        price = q.get("price")
        if price is None:
            d.text((W / 2, (top + bottom) / 2), "Waiting for prices…" if cr.running else "No prices yet",
                   font=F["row"], fill=PI_DIM, anchor="mm")
            return
        values = he.get("v") or []
        change = pct = None
        lo, hi = q.get("low_24h"), q.get("high_24h")
        ct, cb = top + 118, bottom - 92                    # the chart's box
        if len(values) < 2:
            d.text((W / 2, (ct + cb) / 2), "Loading the chart…" if cr.running else "No chart yet",
                   font=F["small"], fill=(90, 90, 90), anchor="mm")
        if len(values) >= 2:
            step = max(1, len(values) // (W - pad * 2))
            vals = values[::step]
            lo, hi = min(vals), max(vals)
            start = vals[0]
            change = vals[-1] - start
            pct = change / start * 100 if start else 0
            colour = PI_UP if change >= 0 else PI_DOWN
            span = (hi - lo) or 1
            pts = [(pad + i * (W - pad * 2) / (len(vals) - 1), cb - (v - lo) / span * (cb - ct))
                   for i, v in enumerate(vals)]
            shade = tuple(int(c * 0.16) for c in colour)
            d.polygon(pts + [(W - pad, cb), (pad, cb)], fill=shade)
            d.line(pts, fill=colour, width=3, joint="curve")
        elif q.get("change_24h") is not None and window == "1D" and q["change_24h"] > -100:
            pct = q["change_24h"]
            change = price * pct / (100 + pct)

        d.text((pad, y0 + 22), price_text(price), font=F["price"], fill=PI_FG)
        if change is not None and pct is not None:
            colour = PI_UP if change >= 0 else PI_DOWN
            dec = 0 if price >= 1000 else (2 if price >= 1 else 4)
            d.text((pad, y0 + 78), f"{change:+,.{dec}f} ({pct:+.2f}%)", font=F["row"], fill=colour)
            d.text((pad + d.textlength(f"{change:+,.{dec}f} ({pct:+.2f}%)", font=F["row"]) + 12,
                    y0 + 81), window, font=F["small"], fill=PI_DIM)
        if hi and lo:
            d.text((W - pad, y0), f"H: {price_text(hi)}", font=F["small"], fill=PI_DIM, anchor="ra")
            d.text((W - pad, y0 + 22), f"L: {price_text(lo)}", font=F["small"], fill=PI_DIM, anchor="ra")
        age = time.time() - qe.get("t", time.time())
        if age > 600:                                      # PiE-ink keeps old numbers, and says so
            mins = int(age // 60)
            d.text((W - pad, y0 + 44), f"{mins // 60} h old" if mins >= 120 else f"{mins} min old",
                   font=F["small"], fill=PI_DOWN, anchor="ra")

        y = bottom - 80
        for k, text in enumerate((f"MC: ${big_number(q.get('market_cap'))}",
                                  f"SUPPLY: {big_number(q.get('circulating_supply'))}",
                                  f"ATH: {price_text(q.get('ath'))}")):
            d.text((pad, y + k * 20), text, font=F["small"], fill=PI_DIM)
        vote = q.get("sentiment_up")
        if vote is not None:
            up = int(round(float(vote)))
            label, colour = (("BULLISH", PI_UP) if up > 55 else ("BEARISH", PI_DOWN) if up < 45
                             else ("NEUTRAL", PI_DIM))
            d.text((W - pad, y), label, font=F["small"], fill=colour, anchor="ra")
            d.text((W - pad, y + 22), f"+{up}% / -{100 - up}%", font=F["row"], fill=PI_DIM, anchor="ra")
        else:
            d.text((W - pad, y), "SENTIMENT", font=F["small"], fill=PI_DIM, anchor="ra")
            d.text((W - pad, y + 22), "no vote yet", font=F["row"], fill=PI_DIM, anchor="ra")

    def render_remote(self):
        F = self.fonts
        ha = self.hass
        img, d = self.canvas()
        W = self.fb.w
        self.header(img, d)
        d.text((20, self.LIST_TOP + 10), "TV  ›  TV Remote", font=F["small"], fill=MUTED, anchor="lm")
        if not ha.configured:
            self.empty_state(d, "Connect Home Assistant",
                             "Put your url and long-lived token in static/homeassistant.txt")
            self.footer(d, [("B", "Back")])
            self.fb.show(img)
            return
        st = ha.tvstate
        top = self.list_top() + 4

        # the TV, how it is
        d.rounded_rectangle((12, top, W - 12, top + 72), radius=12, fill=ROW)
        name = st.get("name") or ("Looking for your TV…" if not ha.error else "Home Assistant")
        d.text((30, top + 24), self.fit(d, name, F["row_b"], W - 260), font=F["row_b"], fill=TEXT, anchor="lm")
        if ha.error:
            line, colour = self.fit(d, ha.error, F["small"], W - 60), WARN
        elif st:
            state = st.get("state", "")
            words = {"on": "On", "off": "Off", "playing": "Playing", "paused": "Paused",
                     "idle": "On", "standby": "Off", "unavailable": "Not answering"}
            bits = [words.get(state, state.capitalize())]
            if state not in ("off", "standby", "unavailable"):
                bits += [b for b in (st.get("app"), st.get("source"), st.get("title")) if b][:2]
            line, colour = "  ·  ".join(bits), (DONE if state not in ("off", "standby", "unavailable")
                                                 else MUTED)
        else:
            line, colour = ha.where, MUTED
        d.text((30, top + 52), self.fit(d, line, F["small"], W - 250 if not ha.error else W - 60),
               font=F["small"], fill=colour, anchor="lm")
        vol = st.get("volume")
        if vol is not None and not ha.error:
            x1, x0 = W - 32, W - 32 - 150
            label = "Muted" if st.get("muted") else f"Volume {round(vol * 100)}"
            d.text((x1, top + 26), label, font=F["small"], fill=WARN if st.get("muted") else BODY, anchor="rm")
            d.rounded_rectangle((x0, top + 46, x1, top + 54), radius=4, fill=LINE)
            if vol > 0:
                d.rounded_rectangle((x0, top + 46, x0 + max(8, (x1 - x0) * vol), top + 54), radius=4,
                                    fill=MUTED if st.get("muted") else ACCENT)

        # the case's buttons, and what each one does to the TV
        hit = self.remote_hit[0] if time.monotonic() - self.remote_hit[1] < 0.25 else ""
        y0 = top + 96
        for k, (lab, txt) in enumerate((("L", "Vol −"), ("R", "Vol +"))):
            x = 24 if k == 0 else W - 24 - 150
            on = hit == lab.lower()
            d.rounded_rectangle((x, y0, x + 150, y0 + 32), radius=16, fill=ACCENT if on else ROW)
            d.text((x + 22, y0 + 16), lab, font=F["key"], fill=BG if on else MUTED, anchor="mm")
            d.text((x + 86, y0 + 16), txt, font=F["small"], fill=BG if on else TEXT, anchor="mm")

        cx, cy, arm, half = 150, y0 + 128, 54, 19          # d-pad
        d.rounded_rectangle((cx - arm, cy - half, cx + arm, cy + half), radius=8, fill=ROW)
        d.rounded_rectangle((cx - half, cy - arm, cx + half, cy + arm), radius=8, fill=ROW)
        for k, (dx, dy, glyph) in {"up": (0, -1, "▲"), "down": (0, 1, "▼"),
                                   "left": (-1, 0, "◀"), "right": (1, 0, "▶")}.items():
            gx, gy = cx + dx * (arm - 18), cy + dy * (arm - 18)
            if hit == k:
                d.rounded_rectangle((gx - 17, gy - 17, gx + 17, gy + 17), radius=8, fill=ACCENT)
            d.text((gx, gy), glyph, font=F["small"], fill=BG if hit == k else BODY, anchor="mm")
        d.text((cx, cy + arm + 18), "TV arrows", font=F["small"], fill=MUTED, anchor="mm")

        fx, fy, gap, r = W - 150, y0 + 128, 44, 19          # A B X Y
        faces = {"x": (0, -1, "Home", "ma"), "a": (1, 0, "OK", "lm"),
                 "b": (0, 1, "Leave", "mt"), "y": (-1, 0, "Back", "rm")}
        for k, (dx, dy, txt, anchor) in faces.items():
            bx, by = fx + dx * gap, fy + dy * gap
            on = hit == k
            d.ellipse((bx - r, by - r, bx + r, by + r), fill=ACCENT if on else ROW)
            d.text((bx, by), k.upper(), font=F["key"], fill=BG if on else BODY, anchor="mm")
            tx, ty = bx + dx * (r + 8), by + dy * (r + 4)
            if k == "x":
                ty = by - r - 22
            elif k == "b":
                ty = by + r + 4
            d.text((tx, ty), txt, font=F["small"], fill=MUTED if k == "b" else TEXT, anchor=anchor)

        for k, (key, txt) in enumerate((("START", "Play / pause"), ("SELECT", "More · 123"))):
            mx, my = W / 2, y0 + 96 + k * 62
            on = hit == key.lower()
            w = d.textlength(key, font=F["key"]) + 22
            d.rounded_rectangle((mx - w / 2, my - 12, mx + w / 2, my + 12), radius=12,
                                fill=ACCENT if on else LINE)
            d.text((mx, my), key, font=F["key"], fill=BG if on else TEXT, anchor="mm")
            d.text((mx, my + 26), txt, font=F["small"], fill=TEXT, anchor="mm")

        if self.remote_pad is not None:                    # the number pad, over the remote
            pad = self.remote_pad
            pw, kh, gap = 360, 42, 8
            px0, py0 = (W - pw) / 2, top - 4
            ph = 64 + len(TV_PAD) * (kh + gap) + 8
            d.rounded_rectangle((px0 - 2, py0 - 2, px0 + pw + 2, py0 + ph + 2), radius=16, fill=LINE)
            d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph), radius=15, fill=BG)
            d.text((px0 + 20, py0 + 28), "Channel", font=F["small"], fill=MUTED, anchor="lm")
            shown = pad["text"] or ""
            d.text((px0 + pw - 20, py0 + 28), shown + ("_" if len(shown) < 7 else ""), font=F["big"],
                   fill=TEXT, anchor="rm")
            y = py0 + 58
            hit = time.monotonic() - self.remote_hit[1] < 0.2
            for r, row in enumerate(TV_PAD):
                kw = (pw - 40 - gap * (len(row) - 1)) / len(row) if len(row) > 1 else pw - 40
                x = px0 + 20
                for c, (label, what) in enumerate(row):
                    on = pad["r"] == r and pad["c"] == c
                    side = not (what.isdigit() or what in ("dash", "del", "go"))
                    fill = ACCENT if on else (LINE if side else ROW)
                    if on and hit:
                        fill = TEXT
                    d.rounded_rectangle((x, y, x + kw, y + kh), radius=10, fill=fill)
                    font = F["keycap"] if len(label) <= 2 else F["small"]
                    d.text((x + kw / 2, y + kh / 2), label, font=font, fill=BG if on else TEXT, anchor="mm")
                    x += kw + gap
                y += kh + gap
            self.footer(d, [("A", "Press"), ("START", "Go"), ("L R", "CH − +"), ("X", "Delete"), ("B", "Close")])
        elif self.remote_more is not None:                 # the More menu, over the remote
            opts = self.remote_options()
            sel = self.remote_more["sel"] % len(opts)
            rows = min(len(opts), 6)
            first = max(0, min(sel - rows // 2, len(opts) - rows))
            mw, rh = 300, 40
            mx0, my0 = (W - mw) / 2, top + 40
            d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + 44 + rows * rh + 12),
                                radius=14, fill=LINE)
            d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + 42 + rows * rh + 10), radius=13, fill=BG)
            d.text((mx0 + 20, my0 + 22), "TV", font=F["small"], fill=MUTED, anchor="lm")
            for n, k in enumerate(range(first, first + rows)):
                label, job = opts[k]
                ry = my0 + 42 + n * rh
                if k == sel:
                    d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                text = ("Input  " + label) if job[0] == "source" else label
                d.text((mx0 + 22, ry + (rh - 4) / 2), self.fit(d, text, F["row"], mw - 60), font=F["row"],
                       fill=TEXT if k == sel else BODY, anchor="lm")
                if job[0] == "source" and label == st.get("source"):
                    d.ellipse((mx0 + mw - 30, ry + 14, mx0 + mw - 22, ry + 22), fill=ACCENT)
            self.footer(d, [("▲▼", "Choose"), ("A", "OK"), ("B", "Close")])
        else:
            self.footer(d, [("SEL", "More"), ("B", "Back")], right=ha.where)
        self.fb.show(img)

    def render_camera(self):
        from PIL import Image
        F = self.fonts
        cam = self.camera
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.HEADER + 1, H - self.FOOTER
        AW, AH = W, bottom - top
        if not cam.addr:
            self.empty_state(d, "No camera chosen", "Press B to pick one or add one")
            self.footer(d, [("B", "Cameras")])
            self.fb.show(img)
            return

        frame = cam.frame
        if frame is not None:                       # the live picture, as big as it fits
            s = min(AW / frame.width, AH / frame.height)
            size = (max(int(frame.width * s), 1), max(int(frame.height * s), 1))
            pic = frame if size == frame.size else frame.resize(size, Image.BILINEAR)
            img.paste(pic, ((AW - size[0]) // 2, top + (AH - size[1]) // 2))
        else:
            mid = top + AH / 2
            cx, cy = W / 2, mid - 40
            d.rounded_rectangle((cx - 44, cy - 40, cx + 44, cy + 40), radius=16, fill=ROW)
            d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), fill=BG, outline=ACCENT, width=3)
            d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=ACCENT)
            if cam.reached is False:
                big, small = "Can't reach this camera", f"Is it on? Nothing answered at {cam.where}"
            elif cam.kind == "pie" and cam.info and not cam.available:
                big, small = "No picture from that Pi", "Is its camera plugged in?"
            else:
                big, small = "Connecting", cam.where
            d.text((W / 2, mid + 30), big, font=F["big"], fill=TEXT, anchor="mm")
            d.text((W / 2, mid + 60), self.fit(d, small, F["small"], W - 40), font=F["small"],
                   fill=MUTED, anchor="mm")

        told = self.cam_bot                         # what the bot says it sees (SELECT)
        if told and cam_key(told["addr"]) == cam_key(cam.addr) and (told["busy"]
                                                                  or time.monotonic() < told["until"]):
            self.camera_told(d, told, bottom)

        # arrows on the picture's edges light up while it turns
        if cam.steers:
            arrows = {"up": (W / 2, top + 22, "▲"), "down": (W / 2, bottom - 22, "▼"),
                      "left": (22, top + AH / 2, "◀"), "right": (W - 22, top + AH / 2, "▶")}
            for k, (ax, ay, glyph) in arrows.items():
                on = k in cam.held
                if on or frame is None:
                    d.ellipse((ax - 15, ay - 15, ax + 15, ay + 15), fill=ACCENT if on else ROW)
                    d.text((ax, ay), glyph, font=F["small"], fill=BG if on else MUTED, anchor="mm")

        # a little status card over the corner of the picture
        bits = []
        if cam.zoom is not None and cam.available:
            bits.append(f"Zoom {round(cam.zoom * 100)}%")
        if cam.speed != "normal" and cam.steers:
            bits.append(cam.speed.capitalize())
        if cam.following:
            bits.append("Following you")
        if cam.asleep:
            bits.append("Asleep")
        now = time.monotonic()
        if cam.action != self.cam_said[0]:
            self.cam_said = (cam.action, now)
        busy = cam.held or cam.zoom_dir or cam.shooting
        keep = 6 if cam.action.startswith("No picture") else 3
        action = cam.action if busy or now - self.cam_said[1] < keep else ""
        text = action or "   ".join(bits)
        if text:
            tw = d.textlength(text, font=F["small"]) + 28
            d.rounded_rectangle((12, top + 10, 12 + tw, top + 40), radius=15, fill=BG)
            d.text((26, top + 25), text, font=F["small"], fill=ACCENT if action else BODY,
                   anchor="lm")
        shot = cam.shot                             # the picture just taken, in the corner
        if shot and time.monotonic() - shot[2] < CAM_SHOT_SHOW:
            small = shot[0]
            x1, y0 = W - 14, top + 12
            x0 = x1 - small.width
            d.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y0 + small.height + 5), radius=8, fill=TEXT)
            img.paste(small, (int(x0), int(y0)))

        # which camera this is, bottom left, with L R between yours when there are more
        # (out of the way while a notice is up there)
        place = cam.place()
        tag = f"{place[0]} of {place[1]}" if place and place[1] > 1 else ""
        if not self.msg:
            name = self.fit(d, cam.title, F["small_b"], W // 2)
            y = bottom - 26
            w = d.textlength(name, font=F["small_b"]) + (d.textlength(tag, font=F["small"]) + 76 if tag else 0)
            d.rounded_rectangle((12, y - 15, 12 + w + 28, y + 15), radius=15, fill=BG)
            x = 26
            if tag:
                x = self.key(d, x, y, "L") + 8
            d.text((x, y), name, font=F["small_b"], fill=TEXT, anchor="lm")
            x += d.textlength(name, font=F["small_b"]) + 12
            if tag:
                d.text((x, y), tag, font=F["small"], fill=MUTED, anchor="lm")
                x += d.textlength(tag, font=F["small"]) + 8
                self.key(d, x, y, "R")

        # SELECT: the bot says what it sees, when there's one (on one that turns, holding START
        # then sets the speed, which SELECT did before); a lit key: on
        bot = ("SEL", "Stop" if self.voice.speaking else "Describe") if self.friend.ready() else None
        if cam.steers:
            hints = [("X Y", "Zoom"), ("A", "Taking…" if cam.shooting else "Photo"),
                     ("START", "Home"), bot or ("SEL", "Speed")]
            if cam.can_follow:
                hints.append(("Hold SEL", "Follow", cam.following))
            else:
                hints.append(("B", "Cameras"))
        else:
            hints = [("A", "Taking…" if cam.shooting else "Photo")] + ([bot] if bot else []) + [("B", "Cameras")]
            if not tag:
                hints.append(("L R", "Tabs"))
        self.footer(d, hints)
        self.fb.show(img)

    def camera_told(self, d, told, bottom):
        """What the bot said it sees, across the foot of the picture, with its face; or that it's
        looking. (Above which camera this is.)"""
        F, W = self.fonts, self.fb.w
        busy = told["busy"]
        face = friend_face(told["text"], "error" if told["error"] else "", busy)[0]
        fw = d.textlength(face, font=F["small"])
        tw = W - 24 - 28 - fw - 12
        lines = ["Looking…"] if busy else self.wrap(d, told["text"], F["small"], tw, 4)
        note = "" if busy else self.fit(d, told["note"], F["small"], tw)
        y1 = bottom - 52
        y0 = y1 - (20 + 21 * len(lines) + (21 if note else 0))
        d.rounded_rectangle((12, y0, W - 12, y1), radius=14, fill=BG)
        d.text((26, y0 + 10), face, font=F["small"], fill=ACCENT, anchor="la")
        x, y = 26 + fw + 12, y0 + 10
        for line in lines:
            d.text((x, y), line, font=F["small"], fill=BODY if busy else TEXT, anchor="la")
            y += 21
        if note:
            d.text((x, y), note, font=F["small"], fill=MUTED, anchor="la")

    def cam_rows(self):
        """The Camera tab's list: your cameras, a row to add one, then the ones on the network."""
        cam = self.camera
        rows = [("cam", c) for c in cam.cams] + [("add", None)]
        found = cam.found_list()
        if found:
            rows.append(("label", "On your network"))
            rows += [("found", f) for f in found]
        return rows

    def render_cameras(self):
        F = self.fonts
        cam = self.camera
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.cam_rows()
        n = len(rows)
        if rows[min(self.cam_sel, n - 1)][0] == "label":
            self.cam_sel += 1
        sel = self.cam_sel = max(0, min(self.cam_sel, n - 1))
        d.text((20, self.LIST_TOP + 10), "Your cameras" if cam.cams else "No cameras yet",
               font=F["small"], fill=MUTED, anchor="lm")
        if cam.scanning:
            d.text((W - 20, self.LIST_TOP + 10), "Looking at them…", font=F["small"], fill=MUTED, anchor="rm")
        top_y = self.LIST_TOP + 28
        shown = max(1, (H - self.FOOTER - top_y) // self.ROW_H)
        top = self.tops.get("cameras", 0)
        top = sel if sel < top else (sel - shown + 1 if sel >= top + shown else top)
        top = max(0, min(top, n - shown))
        self.tops["cameras"] = top
        x0, x1 = 12, W - 22
        for r, i in enumerate(range(top, min(top + shown, n))):
            kind, entry = rows[i]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            if kind == "label":
                d.text((x0 + 18, mid + 8), entry, font=F["small_b"], fill=MUTED, anchor="lm")
                continue
            selected = i == sel
            if selected:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            bx0, by0, bx1, by1 = x0 + 18, y + 6, x0 + 18 + 48, y + self.ROW_H - 6
            if kind == "add":
                d.rounded_rectangle((bx0, by0, bx1, by1), radius=8, outline=ACCENT, width=2)
                cxm, cym = (bx0 + bx1) / 2, (by0 + by1) / 2
                d.line((cxm - 8, cym, cxm + 8, cym), fill=ACCENT, width=3)
                d.line((cxm, cym - 8, cxm, cym + 8), fill=ACCENT, width=3)
                title, right, colour = "Add a camera…", "", MUTED
            else:
                k = cam_key(entry["addr"])
                th = cam.thumbs.get(k)
                if th:
                    pic = th[1]
                    s = min(48 / pic.width, 36 / pic.height)
                    pic = pic.resize((max(1, int(pic.width * s)), max(1, int(pic.height * s))))
                    d.rounded_rectangle((bx0, by0, bx1, by1), radius=6, fill=BG)
                    img.paste(pic, (int(bx0 + (48 - pic.width) / 2), int(by0 + (36 - pic.height) / 2)))
                else:
                    d.rounded_rectangle((bx0, by0, bx1, by1), radius=6, fill=BG if selected else ROW)
                    d.ellipse(((bx0 + bx1) / 2 - 9, (by0 + by1) / 2 - 9, (bx0 + bx1) / 2 + 9,
                               (by0 + by1) / 2 + 9), outline=MUTED, width=2)
                title = cam.name_of(entry["addr"]) if kind == "cam" else entry["name"]
                gone = k in cam.missing and k not in cam.thumbs
                right = "Can't reach" if gone else cam_host(entry["addr"])
                colour = WARN if gone else MUTED
            tx = bx1 + 14
            rw = d.textlength(right, font=F["small"]) if right else 0
            if right:
                d.text((x1 - 14, mid), right, font=F["small"], fill=colour, anchor="rm")
            font = F["row_b"] if selected else F["row"]
            d.text((tx, mid), self.fit(d, title, font, x1 - 14 - rw - 16 - tx), font=font,
                   fill=TEXT if selected else BODY, anchor="lm")
        if n == 1:                                    # nothing yet but the row to add one
            y = top_y + self.ROW_H + 18
            for line in ("A Pi running PiE-ink, or gpi-media's camera server",
                         "(sudo bash setup.sh --camera on that Pi),", "or any MJPEG or JPEG camera link."):
                d.text((W / 2, y), line, font=F["small"], fill=MUTED, anchor="mm")
                y += 22
        kind, entry = rows[sel]
        if kind == "cam":
            hints = [("A", "Watch"), ("X", "Remove" if self.confirm[0] != "camdel:" + cam_key(entry["addr"])
                                      else "Remove it"), ("L R", "Tabs"), ("B", "Home")]
        else:
            hints = [("A", "Add"), ("L R", "Tabs"), ("B", "Home")]
        about = ""
        if entry:
            about = entry["addr"].split("://", 1)[-1]
            what = cam.kind_of(entry["addr"]) or entry.get("server", "")
            about += f" · {what}" if what else ""
        self.footer(d, hints, right=about)
        self.fb.show(img)

    def render_photo(self):
        from PIL import Image
        F = self.fonts
        v = self.v
        img, d = self.canvas(PHOTO_BG)
        W, H = self.fb.w, self.fb.h
        full = v["slideshow"]
        AW, AH = W, (H if full else H - self.FOOTER)
        im = self.photo_image()
        if v["edit"]:
            AH -= self.PREVIEW_STRIP
        if im is None:
            d.text((W / 2, AH / 2), "Can't show this picture", font=F["big"], fill=TEXT, anchor="mm")
        elif v["edit"]:
            pv = self.photo_preview((AW, AH))
            img.paste(pv, ((AW - pv.width) // 2, (AH - pv.height) // 2))
        else:
            s = min(AW / im.width, AH / im.height) * v["zoom"]
            vw, vh = AW / s, AH / s
            hw, hh = min(vw, im.width) / 2, min(vh, im.height) / 2
            v["cx"] = max(hw, min(v["cx"], im.width - hw))
            v["cy"] = max(hh, min(v["cy"], im.height - hh))
            box = (int(v["cx"] - hw), int(v["cy"] - hh), int(v["cx"] + hw), int(v["cy"] + hh))
            part = im.crop(box)
            size = (max(int(part.width * s), 1), max(int(part.height * s), 1))
            part = part.resize(size, Image.BILINEAR)
            img.paste(part, ((AW - size[0]) // 2, (AH - size[1]) // 2))
        if not full:
            pos = f"{v['i'] + 1} of {len(v['items'])}"
            name = os.path.basename(v["items"][v["i"]])
            if v["edit"]:                              # the filters, the chosen one in the middle
                y0 = AH
                d.rectangle((0, y0, W, y0 + self.PREVIEW_STRIP), fill=BG)
                widths = [d.textlength(lab, font=F["small"]) + 28 for _, lab in FILTERS]
                x = W / 2 - widths[v["fi"]] / 2 - sum(widths[:v["fi"]]) - 8 * v["fi"]
                for k, (_, lab) in enumerate(FILTERS):
                    on = k == v["fi"]
                    if x + widths[k] > 0 and x < W:
                        d.rounded_rectangle((x, y0 + 11, x + widths[k], y0 + 41), radius=15,
                                            fill=ACCENT if on else ROW)
                        d.text((x + widths[k] / 2, y0 + 26), lab + ("…" if on and v.get("working") else ""),
                               font=F["small"], fill=BG if on else BODY, anchor="mm")
                    x += widths[k] + 8
                hints = [("◀▶", "Filter"), ("Y", "Turn"), ("A", v["busy"] or "Save copy"),
                         ("B", "Cancel")]
            elif v["zoom"] > 1:
                hints = [("A", f"Zoom {v['zoom']}x"), ("PAD", "Move"), ("L R", "Prev/next"),
                         ("B", "Back")]
            else:
                hints = [("◀▶", "Next"), ("A", "Zoom"), ("X", "Filters"), ("SEL", "Delete"),
                         ("START", "Show"), ("B", "Back")]
            self.footer(d, hints, right=pos if not v["edit"] else None)
            if v["confirm"]:                           # are you sure?
                cw, ch = 420, 150
                cx0, cy0 = (W - cw) / 2, (AH - ch) / 2
                d.rounded_rectangle((cx0 - 2, cy0 - 2, cx0 + cw + 2, cy0 + ch + 2), radius=16, fill=LINE)
                d.rounded_rectangle((cx0, cy0, cx0 + cw, cy0 + ch), radius=15, fill=BG)
                d.text((W / 2, cy0 + 40), "Delete this picture?", font=F["big"], fill=TEXT, anchor="mm")
                d.text((W / 2, cy0 + 76), self.fit(d, name, F["small"], cw - 40), font=F["small"],
                       fill=BODY, anchor="mm")
                d.text((W / 2, cy0 + 102), "It can't be undone.", font=F["small"], fill=MUTED, anchor="mm")
                self.footer(d, [("A", "Delete"), ("B", "Keep")])
            label = self.fit(d, name, F["small"], W - 80)
            lw = d.textlength(label, font=F["small"]) + 24
            d.rounded_rectangle((12, 12, 12 + lw, 40), radius=14, fill=BG)
            d.text((24, 26), label, font=F["small"], fill=BODY, anchor="lm")
        self.fb.show(img)

    def render_pdf(self):
        F = self.fonts
        v = self.v
        img, d = self.canvas(PHOTO_BG)
        W, H = self.fb.w, self.fb.h
        AH = H - self.FOOTER
        im = self.pdf_image()
        wide = False
        if im is None:
            d.text((W / 2, AH / 2), "Can't show this page", font=F["big"], fill=TEXT, anchor="mm")
        elif v["fit"] == "width":
            limit = max(im.height - AH, 0)
            v["scroll"] = int(max(0, min(v["scroll"], limit)))
            wide = im.width > W
            v["sx"] = int(max(0, min(v["sx"], im.width - W))) if wide else 0
            x0 = v["sx"] if wide else 0
            part = im.crop((x0, v["scroll"], x0 + min(W, im.width), v["scroll"] + min(AH, im.height)))
            img.paste(part, ((W - part.width) // 2, 0))
            if limit:      # thin position bar on the right
                th = max(AH * AH / im.height, 20)
                ty = (AH - th) * v["scroll"] / limit
                d.rounded_rectangle((W - 6, ty, W - 2, ty + th), radius=2, fill=MUTED)
            if wide:       # and one along the bottom when the page is wider than the screen
                tw = max(W * W / im.width, 20)
                tx = (W - tw) * v["sx"] / (im.width - W)
                d.rounded_rectangle((tx, AH - 6, tx + tw, AH - 2), radius=2, fill=MUTED)
        else:
            img.paste(im, ((W - im.width) // 2, (AH - im.height) // 2))
        pg = f"{v['page']} / {v['pages']}"
        if v["fit"] == "width" and v["zoom"] != 1.0:
            pg += f"   {int(v['zoom'] * 100)}%"
        pw = d.textlength(pg, font=F["small"]) + 24
        d.rounded_rectangle((W - 12 - pw, 12, W - 12, 40), radius=14, fill=BG)
        d.text((W - 12 - pw / 2, 26), pg, font=F["small"], fill=BODY, anchor="mm")
        page_fit = ("A", "Whole page" if v["fit"] == "width" else "Fit width")
        if wide:
            hints = [("PAD", "Move"), ("X Y", "Zoom"), ("L R", "Page"), page_fit, ("B", "Back")]
        else:
            hints = [("▲▼", "Scroll"), ("◀▶", "Page"), ("X Y", "Zoom"), page_fit, ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)

    def render_text(self):
        F = self.fonts
        v = self.v
        img, d = self.canvas()
        lines = self.text_lines()
        rows, lh = self.text_rows()
        n = len(lines)
        v["top"] = max(0, min(v["top"], max(n - rows, 0)))
        pct = 100 if n <= rows else int(100 * (v["top"] + rows) / n)
        self.title_row(d, v["title"], f"{pct}%")
        font = F["mono_s" if v["size"] == 0 else "mono_l"]
        for r in range(rows):
            k = v["top"] + r
            if k >= n:
                break
            d.text((20, self.LIST_TOP + 2 + r * lh), lines[k], font=font, fill=BODY)
        self.scrollbar(d, v["top"], rows, n, self.LIST_TOP + 4, self.LIST_TOP + rows * lh)
        self.footer(d, [("▲▼", "Scroll"), ("◀▶", "Page"),
                        ("A", "Bigger text" if v["size"] == 0 else "Smaller text"),
                        ("L R", "Start/end"), ("B", "Back")])
        self.fb.show(img)

    def render_now(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        it = self.cur or {"title": "", "src": "", "sub": ""}
        radio = self.kind == "radio"
        self.title_row(d, "Now playing", "Shuffle" if self.shuffle and not radio else
                       ("LIVE" if radio else None), ACCENT)

        cx, cy, cs = 24, self.LIST_TOP + 20, 160
        d.rounded_rectangle((cx, cy, cx + cs, cy + cs), radius=16, fill=ROW)
        if radio:   # a little broadcast symbol
            ox, oy = cx + cs / 2, cy + cs / 2 + 18
            d.ellipse((ox - 9, oy - 9, ox + 9, oy + 9), fill=ACCENT)
            for r in (26, 44, 62):
                d.arc((ox - r, oy - r, ox + r, oy + r), 225, 315, fill=ACCENT, width=5)
        else:
            d.text((cx + cs / 2, cy + cs / 2), "♪", font=F["note"], fill=ACCENT, anchor="mm")

        tx, tw = cx + cs + 28, W - (cx + cs + 28) - 24
        if radio:
            title = it["title"]
            sub = self.meta.get("song") or it.get("sub") or ""
        else:
            title = self.meta.get("title") or it["title"]
            sub = self.meta.get("artist") or os.path.basename(os.path.dirname(it["src"]))
        y = cy + 18
        for l in self.wrap(d, title, F["big"], tw, 2):
            d.text((tx, y), l, font=F["big"], fill=TEXT, anchor="lm")
            y += 32
        if sub:
            for l in self.wrap(d, sub, F["row"], tw, 2 if radio else 1):
                d.text((tx, y + 2), l, font=F["row"], fill=BODY, anchor="lm")
                y += 28
        what = "Station" if radio else "Track"
        d.text((tx, y + 10), f"{what} {self.qi + 1} of {len(self.queue)}",
               font=F["small"], fill=MUTED, anchor="lm")
        d.text((tx, cy + cs - 10), ("Paused" if self.paused else f"Volume {self.volume}"),
               font=F["small"], fill=ACCENT if self.paused else MUTED, anchor="lm")

        by = cy + cs + 44
        if not radio:
            length = self.meta.get("length") or self.length(it) or 0
            d.rounded_rectangle((24, by, W - 24, by + 5), radius=2, fill=LINE)
            if length:
                frac = min(self.pos / length, 1)
                d.rounded_rectangle((24, by, 24 + (W - 48) * frac, by + 5), radius=2, fill=ACCENT)
            d.text((24, by + 22), clock(self.pos), font=F["small"], fill=BODY, anchor="lm")
            if length:
                d.text((W - 24, by + 22), clock(length), font=F["small"], fill=MUTED, anchor="rm")
            if not self.shuffle and self.qi + 1 < len(self.queue):
                nxt = self.fit(d, "Next: " + self.queue[self.qi + 1]["title"], F["small"], W - 48)
                d.text((24, by + 58), nxt, font=F["small"], fill=MUTED, anchor="lm")
            hints = [("A", "Play/pause" if not self.paused else "Play"), ("◀▶", "Seek"),
                     ("L R", "Prev/next"), ("Y", "Shuffle"), ("B", "List")]
        else:
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Station"),
                     ("▲▼", "Volume"), ("B", "List")]
        self.footer(d, hints)
        self.fb.show(img)

    def render_settings(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.settings_rows()
        sel = self.set_sel % len(rows)
        crumb = {"location": "Settings  ›  Location", "wifi": "Settings  ›  WiFi",
                 "friend": "Settings  ›  Bot", "f_models": "Bot  ›  Model",
                 "f_eyes": "Bot  ›  Model that can see", "f_voices": "Bot  ›  Voice"}.get(self.set_page, "Settings")
        d.text((20, self.LIST_TOP + 10), crumb, font=F["small"], fill=MUTED, anchor="lm")
        if self.set_page in FRIEND_PAGES:
            voicey = self.set_page == "f_voices" or (self.set_page == "friend" and self.voice.job)
            note = (self.voice.status() or ("Voices from Piper, made on the Pi" if self.voice.supported()
                                            else "Piper doesn't run on this Pi")) if voicey \
                else self.friend.models_status
            if note:
                d.text((W - 20, self.LIST_TOP + 10), self.fit(d, note, F["small"], 330), font=F["small"],
                       fill=ACCENT if voicey and self.voice.job else MUTED, anchor="rm")
        if self.set_page == "location":
            here = place_text(self.setting("location"))
            d.text((W - 20, self.LIST_TOP + 10), self.fit(d, "Now: " + here, F["small"], 300),
                   font=F["small"], fill=MUTED, anchor="rm")
        top, rh = self.LIST_TOP + 26, 46
        rows_fit = (H - self.FOOTER - top) // rh
        first = max(0, min(sel - rows_fit + 1, len(rows) - rows_fit))
        if self.set_page == "wifi":
            here = self.current_ssid()
            d.text((W - 20, self.LIST_TOP + 10), self.fit(d, f"Connected to {here}" if here else "Not connected",
                                                          F["small"], 320),
                   font=F["small"], fill=DONE if here else WARN, anchor="rm")
        for r, k in enumerate(range(first, min(first + rows_fit, len(rows)))):
            key, label, extra = rows[k]
            y = top + r * rh
            on = k == sel
            if on:
                d.rounded_rectangle((12, y + 2, W - 12, y + rh - 4), radius=10, fill=ROW)
                d.rectangle((12, y + 10, 15, y + rh - 12), fill=ACCENT)
            mid = y + rh / 2 - 1
            if self.set_page == "wifi":
                self.wifi_row(d, key, label, extra, mid, on)
                continue
            if self.set_page == "location":
                d.text((30, mid), self.fit(d, label, F["row"], W - 300), font=F["row"],
                       fill=TEXT if on else BODY, anchor="lm")
                if key != "place":
                    d.text((W - 28, mid), extra, font=F["small"], fill=MUTED, anchor="rm")
                continue
            if self.set_page == "f_voices":
                d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
                note = next((x for i, _, x in BOT_VOICES if i == extra), "")
                if note:
                    d.text((30 + d.textlength(label, font=F["row"]) + 12, mid + 1),
                           self.fit(d, note, F["small"], 250), font=F["small"], fill=MUTED, anchor="lm")
                job = self.voice.job
                state = ("Using", ACCENT) if extra == self.bot_voice() and (extra or not self.voice_want) else \
                    (f"{job['pct']}%", ACCENT) if job and job["id"] == extra else \
                    ("On the Pi", MUTED) if extra in voices_here() else \
                    ("", MUTED) if not extra else (f"{VOICE_MB} MB", MUTED)
                d.text((W - 28, mid), state[0], font=F["small"], fill=state[1], anchor="rm")
                continue
            if self.set_page in ("f_models", "f_eyes"):
                fr = self.friend
                d.text((30, mid), self.fit(d, label, F["row"], W - 200), font=F["row"],
                       fill=(TEXT if on else BODY) if key == "f_pick" else MUTED, anchor="lm")
                using = fr.model if self.set_page == "f_models" else fr.eyes
                if key == "f_pick" and extra == using:
                    d.text((W - 28, mid), "Using", font=F["small"], fill=ACCENT, anchor="rm")
                continue
            if self.set_page == "friend":
                d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
                value = self.friend_value(key)
                x1 = W - 28
                if extra and on:
                    d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                    x1 -= 22
                shown = self.fit(d, value, F["row"], 250)
                d.text((x1, mid), shown, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
                if extra and on:
                    d.text((x1 - d.textlength(shown, font=F["row"]) - 10, mid), "◀", font=F["small"],
                           fill=ACCENT, anchor="rm")
                continue
            d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
            value = (place_text(self.setting("location")) if key == "location" else
                     (self.current_ssid() or "Not connected") if key == "wifi" else
                     self.pad_summary() if key == "pad" else
                     self.friend_summary() if key == "friend" else self.setting(key))
            x1 = W - 28
            if extra and on:                          # ◀ value ▶
                d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                x1 -= 22
            vw = d.textlength(value, font=F["row"])
            d.text((x1, mid), self.fit(d, value, F["row"], 260), font=F["row"],
                   fill=ACCENT if on else MUTED, anchor="rm")
            x0 = x1 - min(vw, 260)
            if extra and on:
                d.text((x0 - 10, mid), "◀", font=F["small"], fill=ACCENT, anchor="rm")
                x0 -= 28
            if key == "wallpaper":                     # a little preview
                thumb = self.wall_thumb()
                d.rounded_rectangle((x0 - 70, mid - 15, x0 - 14, mid + 17), radius=5, fill=LINE)
                img.paste(thumb, (int(x0 - 68), int(mid - 13)))
            elif key == "accent":
                d.ellipse((x0 - 34, mid - 9, x0 - 16, mid + 9), fill=ACCENT)
        if self.loc_status and self.set_page == "location":
            d.text((W / 2, H - self.FOOTER - 22), self.loc_status, font=F["small"], fill=ACCENT, anchor="mm")
        if self.set_page == "wifi":
            if self.wifi["status"]:
                d.text((W / 2, H - self.FOOTER - 22), self.wifi["status"], font=F["small"], fill=ACCENT,
                       anchor="mm")
            k = rows[sel][0]
            hints = ([("◀▶", "On / off")] if k == "radio" else
                     [("A", "Connect")] + ([("Y", "Forget")] if k == "net" and rows[sel][1] in self.wifi["saved"]
                                           else []) if k == "net" else [("A", "Add")])
            hints += [("X", "Scan"), ("B", "Back")]
        elif self.set_page == "location":
            hints = [("A", "Choose"), ("B", "Back")]
        elif self.set_page == "friend":
            k = rows[sel][0]
            hints = ([("◀▶", "Change")] if k in ("f_chatter", "f_speak") else
                     [("A", "Choose")] if k in ("f_model", "f_eyes", "f_voice") else [("A", "Type")])
            hints += [("X", "Check"), ("B", "Back")]
        elif self.set_page == "f_voices":
            k, _, vid = rows[sel]
            here = vid in voices_here()
            hints = [("A", "No voice" if k == "v_none" else "Use this" if here else "Get it")]
            if k == "v_pick" and here:
                hints.append(("X", "Take it off?" if self.confirm[0] == "voicerm:" + vid else "Take it off"))
            hints.append(("B", "Back"))
        elif self.set_page in ("f_models", "f_eyes"):
            hints = ([("A", "Use this")] if rows[sel][0] == "f_pick" else []) + [("X", "Ask again"), ("B", "Back")]
        else:
            key = rows[sel][0]
            hints = [("◀▶", "Change"), ("L R", "Tabs"), ("B", "Home")]
            if key in ("location", "wifi", "friend"):
                hints = [("A", "Set" if key == "location" else "Set up" if key == "friend" else "Networks"),
                         ("L R", "Tabs"), ("B", "Home")]
            elif key == "pad":
                hints = [("A", "Set up buttons"), ("X", "Reset"), ("L R", "Tabs"), ("B", "Home")]
            elif key == "wallpaper" and self.setting("wallpaper") == "Picture":
                hints.insert(1, ("A", "Pick picture"))
        self.footer(d, hints)
        self.fb.show(img)

    def wifi_row(self, d, key, label, extra, mid, on):
        """One row of the WiFi page: the switch, a network, or "Other network…"."""
        F, W = self.fonts, self.fb.w
        w = self.wifi
        d.text((30, mid), self.fit(d, label, F["row"], W - 260), font=F["row"], fill=TEXT if on else BODY,
               anchor="lm")
        if key == "radio":
            value = "On" if w["radio"] else "Off"
            d.text((W - 28, mid), value, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
            return
        if key == "other":
            d.text((W - 28, mid), extra, font=F["small"], fill=MUTED, anchor="rm")
            return
        net = extra
        x = W - 28                                     # signal bars, then a lock for a password
        bars = 4 if net["signal"] >= 75 else 3 if net["signal"] >= 50 else 2 if net["signal"] >= 25 else 1
        for b in range(4):
            bx = x - (3 - b) * 7 - 5
            h = 5 + b * 4
            d.rectangle((bx, mid + 8 - h, bx + 4, mid + 8), fill=(TEXT if on else BODY) if b < bars else LINE)
        x -= 38
        if net["secure"]:
            d.rounded_rectangle((x - 12, mid - 1, x, mid + 9), radius=2, fill=MUTED)
            d.arc((x - 10, mid - 9, x - 2, mid + 3), 180, 360, fill=MUTED, width=2)
            x -= 22
        tag = "Connected" if net["active"] else "Saved" if net["ssid"] in w["saved"] else ""
        if tag:
            d.text((x, mid), tag, font=F["small"], fill=DONE if net["active"] else MUTED, anchor="rm")

    def wall_thumb(self):
        from PIL import Image
        key = ("thumb", self.setting("wallpaper"), self.setting("picture"))
        if getattr(self, "_wall_thumb", (None,))[0] != key:
            im = wallpaper(self.setting("wallpaper"), (224, 128), self.setting("picture"))
            self._wall_thumb = (key, im.resize((54, 30), Image.LANCZOS))
        return self._wall_thumb[1]

    def render_keys(self):
        F = self.fonts
        kb = self.kb or {"title": "", "text": "", "r": 0, "c": 0, "shift": False}
        img, d = self.canvas()
        W = self.fb.w
        self.title_row(d, kb["title"])
        d.rounded_rectangle((24, 84, W - 24, 132), radius=12, fill=ROW, outline=ACCENT, width=2)
        text = kb["text"]
        shown = text
        while d.textlength(shown, font=F["big"]) > W - 90 and shown:
            shown = shown[1:]
        d.text((42, 108), shown, font=F["big"], fill=TEXT, anchor="lm")
        cx = 42 + d.textlength(shown, font=F["big"]) + 3
        d.rectangle((cx, 94, cx + 2, 122), fill=ACCENT)
        kw, kh, gap = 54, 46, 6
        x0 = (W - (10 * kw + 9 * gap)) / 2
        y0 = 150
        for r, row in enumerate(KEY_SYMBOLS if kb.get("sym") else KEY_ROWS):
            for c, ch in enumerate(row):
                x, y = x0 + c * (kw + gap), y0 + r * (kh + gap)
                on = kb["r"] == r and kb["c"] == c
                d.rounded_rectangle((x, y, x + kw, y + kh), radius=9, fill=ACCENT if on else ROW)
                label = ch.upper() if kb["shift"] else ch
                d.text((x + kw / 2, y + kh / 2), label, font=F["keycap"], fill=BG if on else TEXT, anchor="mm")
        y = y0 + len(KEY_ROWS) * (kh + gap)
        x = x0
        unit = (10 * kw + 9 * gap - (len(KEY_BOTTOM) - 1) * gap) / 10
        for c, (what, label, span) in enumerate(KEY_BOTTOM):
            w = unit * span
            on = kb["r"] == len(KEY_ROWS) and kb["c"] == c
            lit = (what == "shift" and kb["shift"]) or (what == "sym" and kb.get("sym"))
            d.rounded_rectangle((x, y, x + w, y + kh), radius=9,
                                fill=ACCENT if on else (LINE if not lit else MUTED))
            if what == "sym" and kb.get("sym"):
                label = "abc"
            d.text((x + w / 2, y + kh / 2), label, font=F["keycap"] if len(label) < 3 else F["small"],
                   fill=BG if on else TEXT, anchor="mm")
            x += w + gap
        self.footer(d, [("A", "Type"), ("X", "Delete"), ("Y", "Space"), ("START", "Done"), ("B", "Cancel")])
        self.fb.show(img)

    def home_icon(self, name):
        if name not in self.icons:
            self.icons[name] = draw_icon(name, self.HOME_ICON)
        return self.icons[name]

    HOME_ICON, HOME_ROW, HOME_GRID = 72, 104, 124   # icon size, row height, first row's top

    def home_canvas(self):
        """A fresh copy of the home screen's background."""
        from PIL import ImageDraw
        key = (self.setting("wallpaper"), self.setting("picture"), self.fb.w, self.fb.h)
        if self.wall[0] != key:
            self.wall = (key, wallpaper(key[0], (self.fb.w, self.fb.h), key[1]))
        img = self.wall[1].copy()
        return img, ImageDraw.Draw(img)

    def home_widget(self, img, d):
        """The top-right corner of the home screen when nothing is playing: the weather."""
        F, W = self.fonts, self.fb.w
        wx = self.weather.data
        if not wx or not self.setting("location"):
            return
        icon = self.wx_icon(wx_icon_name(wx.get("code"), wx.get("is_day", True)), 64)
        img.paste(icon, (W - 24 - 64, 32), icon)
        x = W - 24 - 64 - 10
        d.text((x, 30), self.deg(wx.get("temp")), font=F["clock"], fill=TEXT, anchor="ra")
        words = wx_words(wx.get("code"))[0]
        today = (wx.get("days") or [{}])[0]
        line = f"{words}  ·  {self.deg(today.get('hi'))} / {self.deg(today.get('lo'))}"
        d.text((W - 24, 92), self.fit(d, line, F["row"], 300), font=F["row"], fill=BODY, anchor="ra")

    def render_weather(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        wx, loc = self.weather.data, self.setting("location")
        top = self.LIST_TOP
        if not loc:
            self.empty_state(d, "Where are you?", "A finds you from your internet address, or set a town in Settings")
            self.footer(d, [("A", "Find me"), ("L R", "Tabs"), ("B", "Home")])
            self.fb.show(img)
            return
        if not wx:
            if self.weather.error:
                self.empty_state(d, "Can't reach the weather service", "Check the WiFi; X tries again")
            else:
                self.empty_state(d, "Getting the weather", place_text(loc))
            self.footer(d, [("X", "Refresh"), ("L R", "Tabs"), ("B", "Home")])
            self.fb.show(img)
            return
        pages = self.wx_pages()
        self.wx_page %= len(pages)
        page = pages[self.wx_page]
        d.text((24, top + 12), place_text(loc).upper(), font=F["small"], fill=MUTED, anchor="lm")
        age = time.time() - self.weather.t
        when = ("Updated just now" if age < 90 else f"Updated {int(age // 60)} min ago" if age < 3600
                else f"Updated {int(age // 3600)} h ago")
        d.text((W - 24, top + 12), when, font=F["small"], fill=WARN if age > 3 * 3600 else MUTED, anchor="rm")
        today = (wx.get("days") or [{}])[0]

        if page == "Now":
            name = wx_icon_name(wx.get("code"), wx.get("is_day", True))
            icon = self.wx_icon(name, 128)
            img.paste(icon, (W - 32 - 128, top + 22), icon)
            d.text((22, top + 18), self.deg(wx.get("temp")), font=F["temp"], fill=TEXT, anchor="la")
            d.text((26, top + 100), wx_words(wx.get("code"))[0], font=F["big"], fill=TEXT, anchor="la")
            d.text((26, top + 130), f"Feels like {self.deg(wx.get('feels'))}   ·   "
                   f"High {self.deg(today.get('hi'))}   Low {self.deg(today.get('lo'))}",
                   font=F["small"], fill=BODY, anchor="la")
            row = []
            if wx.get("humidity") is not None:
                row.append(("humidity", f"{round(float(wx['humidity']))}%"))
            if wx.get("wind") is not None:
                unit = "mph" if wx.get("units") == "F" else "km/h"
                row.append(("wind", f"{round(float(wx['wind']))} {unit} {compass(wx.get('wind_dir'))}".strip()))
            if today.get("rain") is not None:
                row.append(("rain", f"{today['rain']}% rain"))
            if today.get("sunrise"):
                row.append(("sunrise", self.hour_min(today["sunrise"])))
            if today.get("sunset"):
                row.append(("sunset", self.hour_min(today["sunset"])))
            x, y = 26, top + 162
            for ic, text in row:
                pic = self.wx_icon(ic, 20)
                img.paste(pic, (int(x), int(y) - 10), pic)
                x += 26
                d.text((x, y), text, font=F["small"], fill=BODY, anchor="lm")
                x += d.textlength(text, font=F["small"]) + 20
            # the next hours
            y0 = top + 178
            d.line((20, y0, W - 20, y0), fill=LINE)
            hours = (wx.get("hours") or [])[:8]
            if not hours and self.weather.busy:            # (PiE-ink's forecast has none: on their way)
                d.text((W / 2, y0 + 41), "Getting the next hours…", font=F["small"], fill=MUTED, anchor="mm")
            if hours:
                cw = (W - 40) / len(hours)
                for i, h in enumerate(hours):
                    cx = 20 + cw * i + cw / 2
                    d.text((cx, y0 + 14), self.hour_label(h["time"]), font=F["label"], fill=MUTED, anchor="mm")
                    pic = self.wx_icon(wx_icon_name(h.get("code"), h.get("is_day", True)), 32)
                    img.paste(pic, (int(cx - 16), int(y0 + 24)), pic)
                    d.text((cx, y0 + 68), self.deg(h.get("temp")), font=F["small_b"], fill=TEXT, anchor="mm")
            # the coming days
            y1 = y0 + 82
            d.line((20, y1, W - 20, y1), fill=LINE)
            days = (wx.get("days") or [])[1:7]
            if days:
                cw = (W - 40) / len(days)
                for i, day in enumerate(days):
                    cx = 20 + cw * i + cw / 2
                    try:
                        label = time.strftime("%a", time.strptime(day["date"], "%Y-%m-%d"))
                    except (ValueError, KeyError):
                        label = "—"
                    d.text((cx, y1 + 13), label, font=F["label"], fill=MUTED, anchor="mm")
                    pic = self.wx_icon(wx_icon_name(day.get("code"), True), 28)
                    img.paste(pic, (int(cx - 14), int(y1 + 22)), pic)
                    hi, lo = self.deg(day.get("hi")), self.deg(day.get("lo"))
                    tw = d.textlength(hi, font=F["small_b"]) + 6 + d.textlength(lo, font=F["label"])
                    d.text((cx - tw / 2, y1 + 60), hi, font=F["small_b"], fill=TEXT, anchor="lm")
                    d.text((cx - tw / 2 + d.textlength(hi, font=F["small_b"]) + 6, y1 + 60), lo,
                           font=F["label"], fill=MUTED, anchor="lm")
        elif page == "Week":
            rh = 44
            for i, day in enumerate((wx.get("days") or [])[:7]):
                y = top + 30 + i * rh
                if y + rh > H - self.FOOTER:
                    break
                try:
                    label = "Today" if i == 0 else time.strftime("%A", time.strptime(day["date"], "%Y-%m-%d"))
                except (ValueError, KeyError):
                    label = "—"
                if i % 2 == 0:
                    d.rounded_rectangle((12, y + 2, W - 12, y + rh - 2), radius=8, fill=ROW)
                mid = y + rh / 2
                d.text((26, mid), label, font=F["row"], fill=TEXT, anchor="lm")
                pic = self.wx_icon(wx_icon_name(day.get("code"), True), 30)
                img.paste(pic, (150, int(mid - 15)), pic)
                d.text((194, mid), wx_words(day.get("code"))[0], font=F["small"], fill=BODY, anchor="lm")
                if day.get("rain"):
                    d.text((W - 150, mid), f"{day['rain']}%", font=F["small"], fill=WX_TINT["rain"], anchor="rm")
                d.text((W - 80, mid), self.deg(day.get("hi")), font=F["row_b"], fill=TEXT, anchor="rm")
                d.text((W - 26, mid), self.deg(day.get("lo")), font=F["row"], fill=MUTED, anchor="rm")
        else:                                          # the NWS in its own words
            y = top + 30
            for name, text in self.weather.nws:
                if y > H - self.FOOTER - 40:
                    break
                d.text((24, y), name, font=F["small_b"], fill=ACCENT, anchor="la")
                y += 22
                for line in textwrap.wrap(text, 70)[:3]:
                    d.text((24, y), line, font=F["small"], fill=BODY, anchor="la")
                    y += 20
                y += 8
        # which page
        gap = 14
        x = W / 2 - (len(pages) - 1) * gap / 2
        for k in range(len(pages)):
            on = k == self.wx_page
            r = 4 if on else 3
            d.ellipse((x - r, H - self.FOOTER - 10 - r, x + r, H - self.FOOTER - 10 + r),
                      fill=TEXT if on else LINE)
            x += gap
        nxt = pages[(self.wx_page + 1) % len(pages)]
        self.footer(d, [("◀▶", nxt), ("X", "Refresh"), ("L R", "Tabs"), ("B", "Home")],
                    right="from Open-Meteo" + (" + NWS" if page == "Forecast" else ""))
        self.fb.show(img)

    def hour_min(self, hhmm):
        try:
            t = time.strptime(hhmm, "%H:%M")
        except ValueError:
            return hhmm
        return time.strftime("%H:%M" if self.setting("clock") == "24-hour" else "%-I:%M %p", t)

    def render_home(self):
        F = self.fonts
        img, d = self.home_canvas()
        W, H = self.fb.w, self.fb.h
        self.status_bar(d, clock=False)

        # the time and date, big, like a phone's lock screen
        t = time.localtime()
        hm = self.clock_text(t, ampm=False)
        d.text((24, 30), hm, font=F["clock"], fill=TEXT, anchor="la")
        if self.setting("clock") != "24-hour":
            x = 24 + d.textlength(hm, font=F["clock"]) + 8
            d.text((x, 42), time.strftime("%p", t), font=F["head"], fill=BODY, anchor="la")
        d.text((26, 92), time.strftime("%A, %B ", t) + str(t.tm_mday), font=F["row"], fill=BODY, anchor="la")

        if self.playing_now():                         # what's playing, top right
            it = self.cur
            radio = self.kind == "radio"
            title = it["title"] if radio else (self.meta.get("title") or it["title"])
            sub = (self.meta.get("song") or it.get("sub") or "") if radio else (it.get("sub") or "")
            cx0, cx1, cy0 = W - 296, W - 20, 34
            d.rounded_rectangle((cx0, cy0, cx1, cy0 + 78), radius=14, fill=ROW)
            head = ("PAUSED" if self.paused else "ON THE RADIO" if radio else "NOW PLAYING")
            d.text((cx0 + 18, cy0 + 17), head, font=F["key"], fill=ACCENT, anchor="lm")
            d.text((cx0 + 18, cy0 + 42), self.fit(d, title, F["row_b"], cx1 - cx0 - 36), font=F["row_b"],
                   fill=TEXT, anchor="lm")
            if sub:
                d.text((cx0 + 18, cy0 + 63), self.fit(d, sub, F["small"], cx1 - cx0 - 36), font=F["small"],
                       fill=BODY, anchor="lm")
        elif self.setting("widget") == "Weather":
            self.home_widget(img, d)

        # the icons
        apps = self.home_apps()
        n = len(apps)
        cols = home_cols(n)
        sel = self.home_sel % n
        rows_fit = max(1, (H - self.FOOTER - self.HOME_GRID - self.HOME_ICON - 24) // self.HOME_ROW + 1)
        first = max(0, min(sel // cols - rows_fit + 1, (n - 1) // cols - rows_fit + 1))
        cw = (W - 20) / cols
        size = self.HOME_ICON
        playing = {"audio": "Music", "radio": "Radio"}.get(self.kind) if self.playing_now() else None
        slots = home_layout(n, cols)
        for k, (name, _) in enumerate(apps):
            r, c = slots[k]
            if not first <= r < first + rows_fit:
                continue
            x = 10 + c * cw + (cw - size) / 2
            y = self.HOME_GRID + (r - first) * self.HOME_ROW
            if k == sel:
                d.rounded_rectangle((x - 6, y - 6, x + size + 6, y + size + 6), radius=24,
                                    outline=ACCENT, width=3)
            icon = self.home_icon(name)
            img.paste(icon, (int(x), int(y)), icon)
            if name == playing:                       # a dot on what's playing
                d.ellipse((x + size - 13, y - 3, x + size + 5, y + 15), fill=BG)
                d.ellipse((x + size - 10, y, x + size + 2, y + 12), fill=ACCENT)
            label = self.fit(d, name, F["small_b"], cw - 8)
            lf = F["small_b"] if k == sel else F["label"]
            d.text((x + size / 2 + 1, y + size + 15), label, font=lf, fill=(0, 0, 0), anchor="mm")
            d.text((x + size / 2, y + size + 14), label, font=lf, fill=TEXT if k == sel else BODY,
                   anchor="mm")
        if (n - 1) // cols >= first + rows_fit:       # more below
            d.text((W / 2, H - self.FOOTER - 10), "▼", font=F["small"], fill=MUTED, anchor="mm")

        hints = [("A", "Open")]
        if self.playing_now():
            hints.append(("START", "Now playing"))
        hints.append(("B", "Terminal"))
        name_sel, tab_sel = apps[sel]
        about = HOME_ICONS.get(name_sel, (None, ""))[1]
        if not about and tab_sel is not None:
            about = LIBRARY[tab_sel].get("about", "")
        self.footer(d, hints, right=about)
        self.fb.show(img)

    def render_help(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        self.title_row(d, "Controls")
        if self.help_from == "now":
            cols = [
                ("Music & radio", [("A", "Pause / play"), ("◀▶", "Seek / station"),
                                   ("L R", "Prev / next"), ("▲▼", "Volume"), ("Y", "Shuffle")]),
                ("", [("B", "Back to the list"), ("HOME", "Terminal"),
                      ("", "Music keeps playing in"), ("", "the terminal")]),
            ]
        else:
            cols = [
                ("In the lists", [("L R", "Switch tab"), ("▲▼", "Move (hold)"),
                                  ("◀▶", "Page"), ("A", "Open / play"),
                                  ("START", "Now playing"), ("B", "Back / home"),
                                  ("HOME", "Terminal")]),
                ("While a video plays", [("A", "Pause / play"), ("◀▶", "10 seconds"),
                                         ("L R", "1 minute"), ("▲▼", "Volume"),
                                         ("X", "Time left"), ("Y", "Full screen"),
                                         ("SEL ST", "Prev / next"), ("B", "Back to list")]),
            ]
        for c, (head, rows) in enumerate(cols):
            x = 24 + c * (W // 2)
            if head:
                d.text((x, self.LIST_TOP + 12), head.upper(), font=F["key"], fill=MUTED, anchor="lm")
            for r, (k, label) in enumerate(rows):
                y = self.LIST_TOP + 44 + r * 36
                end = self.key(d, x, y, k) if k else x
                d.text((max(end, x + 64) + 10, y), label, font=F["small"],
                       fill=BODY if k else MUTED, anchor="lm")
        self.footer(d, [("ANY", "Close")])
        self.fb.show(img)

    def render_wait(self, title, status, playing=False, camera=False):
        if not (self.active and self.fb):
            return
        if playing:
            return self.render_curtain(title, status)
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        d.text((W / 2, H / 2 - 18), self.fit(d, title, F["big"], W - 60),
               font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, H / 2 + 18), status, font=F["small"], fill=MUTED, anchor="mm")
        if camera:
            hints = [("PAD", "Move"), ("X Y", "Zoom"), ("START", "Center"), ("B", "Back")]
        else:
            hints = [("B", "Cancel")]
        self.footer(d, hints)
        self.fb.show(img)


    def render_curtain(self, title, status):
        """Before a video: black, with the words in the middle where the picture will cover
        them. (mplayer only draws the picture: anything round it would stay on the screen.)"""
        F = self.fonts
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        d.text((W / 2, H / 2 - 30), self.fit(d, title, F["big"], W - 60),
               font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, H / 2 + 4), status, font=F["small"], fill=MUTED, anchor="mm")
        full = self.setting("screen") != "Fit"
        hints = [("A", "Pause"), ("▲▼", "Volume"), ("Y", "Whole picture" if full else "Full screen"),
                 ("B", "Back")]
        widths = [max(d.textlength(k, font=F["key"]) + 14, 24) + 7 + d.textlength(t, font=F["small"])
                  for k, t in hints]
        x, y = (W - sum(widths) - 18 * (len(hints) - 1)) / 2, H / 2 + 44
        for (k, t), w in zip(hints, widths):
            end = self.key(d, x, y, k) + 7
            d.text((end, y), t, font=F["small"], fill=BODY, anchor="lm")
            x += w + 18
        self.fb.show(img)


# ---- input: controllers ---------------------------------------------------------
CHORD_WAIT = 0.25   # no HOME button: how long SELECT or START waits to see if the other comes
SCAN_EVERY = 2.0    # seconds between looks for controllers plugged in


def pad_kind(dev):
    """'gamepad' for the standard layout (Xbox, PlayStation, 8BitDo, the GPi Case...),
    'joystick' for a plain USB pad that numbers its buttons, None for keyboards, mice and the rest."""
    name = (dev.name or "").lower()
    if dev.name == NAME or any(w in name for w in NOT_PADS):
        return None
    keys = set(dev.capabilities().get(e.EV_KEY, []))
    if keys & {e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_DPAD_UP}:
        return "gamepad"
    if any(e.BTN_TRIGGER <= k <= e.BTN_TRIGGER + 15 for k in keys):
        return "joystick"
    return None


def pad_ident(dev):
    """The controller's model: every one of the same model gets the same buttons."""
    try:
        return f"{dev.info.vendor:04x}:{dev.info.product:04x}:{dev.name}"
    except AttributeError:
        return dev.name


class Pad:
    """One controller: its raw events in, button names out."""

    def __init__(self, dev, kind, learned=None):
        self.dev, self.kind, self.path = dev, kind, dev.path
        self.ident = pad_ident(dev)
        self.has = set(dev.capabilities().get(e.EV_KEY, []))
        self.info = {}                                 # axis -> its range
        self.apply(learned)

    def apply(self, learned=None):
        """Its buttons: the standard ones for its kind, with those set up in Settings > Controller
        in their place (one that wasn't set up keeps its standard code)."""
        if self.kind == "joystick":
            keys = dict(JOY_CODES)
            keys.update({c: n for c, n in CODES.items() if c in self.has})
        else:
            keys = dict(CODES)
        axes = {c: dict(d) for c, d in AXES.items()}
        names = set()
        if isinstance(learned, dict):
            try:
                lk = {int(c): n for c, n in (learned.get("keys") or {}).items() if n in BUTTONS}
                la = {int(c): {int(d): n for d, n in dirs.items() if n in BUTTONS and int(d) in (-1, 1)}
                      for c, dirs in (learned.get("axes") or {}).items()}
            except (TypeError, ValueError, AttributeError):
                lk, la = {}, {}
            names = set(lk.values()) | {n for dirs in la.values() for n in dirs.values()}
            keys = {c: n for c, n in keys.items() if n not in names}
            keys.update(lk)
            axes.update(la)
        self.learned = bool(names)
        self.keys, self.axes = keys, axes
        self.home = (any(n == "home" and c in self.has for c, n in keys.items())
                     or any("home" in dirs.values() for dirs in axes.values()))
        self.now = {}                                  # axis -> the way it's pushed: -1, 0, 1
        self.down = set()                              # buttons held down

    def axis_codes(self):
        try:
            return list(self.dev.capabilities(absinfo=False).get(e.EV_ABS, []))
        except OSError:
            return []

    def direction(self, code, value):
        """-1, 0 or 1: an axis pushed past halfway one way or the other."""
        info = self.info.get(code)
        if info is None:
            try:
                info = self.info[code] = self.dev.absinfo(code)
            except OSError:
                return 0
        center = (info.min + info.max) / 2
        span = (info.max - info.min) / 2 or 1
        n = (value - center) / span
        return -1 if n < -0.5 else 1 if n > 0.5 else 0

    def translate(self, ev):
        """[(button, pressed)] for one raw event."""
        out = []
        if ev.type == e.EV_KEY and ev.value in (0, 1):
            name = self.keys.get(ev.code)
            if name:
                out.append((name, ev.value == 1))
        elif ev.type == e.EV_ABS and ev.code in self.axes:
            d = self.direction(ev.code, ev.value)
            old = self.now.get(ev.code, 0)
            if d != old:
                self.now[ev.code] = d
                dirs = self.axes[ev.code]
                if old and dirs.get(old):
                    out.append((dirs[old], False))
                if d and dirs.get(d):
                    out.append((dirs[d], True))
        for name, down in out:
            if down:
                self.down.add(name)
            else:
                self.down.discard(name)
        return out


class Pads:
    """The controllers plugged in, looked for again every couple of seconds."""

    def __init__(self, sel):
        self.sel = sel
        self.by_path = {}
        self.skip = {}               # path -> its device node: looked at, not a controller
        self.power = {}              # path -> PowerKey: the case's power switch
        self.gpi = gpi_case_set_up()
        self.power_told = False
        self.next_scan = 0.0
        self.saved = self.load()     # model -> the buttons set up for it

    @staticmethod
    def load():
        try:
            with open(PADS_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def write(self):
        try:
            os.makedirs(os.path.dirname(PADS_FILE), exist_ok=True)
            tmp = PADS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.saved, f, indent=1)
            os.replace(tmp, PADS_FILE)
        except OSError as ex:
            print(f"couldn't save the controller's buttons: {ex}", flush=True)

    def save(self, ident, keys, axes):
        self.saved[ident] = {"keys": {str(c): n for c, n in keys.items()},
                             "axes": {str(c): {str(d): n for d, n in dirs.items()} for c, dirs in axes.items()}}
        self.write()
        for pad in self.by_path.values():
            if pad.ident == ident:
                pad.apply(self.saved[ident])

    def forget(self):
        """Every controller back to its standard buttons."""
        self.saved = {}
        self.write()
        for pad in self.by_path.values():
            pad.apply(None)

    def scan(self, now, force=False):
        """Controllers plugged in since the last look: [Pad]."""
        if now < self.next_scan and not force:
            return []
        self.next_scan = now + SCAN_EVERY
        try:
            paths = set(list_devices())
        except OSError:
            return []
        for path in list(self.skip):
            if path not in paths:
                del self.skip[path]
        new = []
        for path in sorted(paths):
            if path in self.by_path or path in self.power:
                continue
            try:
                node = os.stat(path).st_ino
                if self.skip.get(path) == node:
                    continue
                dev = InputDevice(path)
            except OSError:
                continue
            try:
                kind = pad_kind(dev)
                if not kind:
                    if is_power_switch(dev, self.gpi):
                        switch = PowerKey(dev)
                        self.sel.register(dev, selectors.EVENT_READ, switch)
                        self.power[path] = switch
                        print(f"power switch: {dev.name} ({path})", flush=True)
                        continue
                    dev.close()
                    self.skip[path] = node
                    continue
                pad = Pad(dev, kind, self.saved.get(pad_ident(dev)))
                self.sel.register(dev, selectors.EVENT_READ, pad)
            except (OSError, ValueError, KeyError):
                try:
                    dev.close()
                except OSError:
                    pass
                continue
            self.by_path[path] = pad
            print(f"controller: {dev.name} ({path})", flush=True)
            new.append(pad)
        if self.gpi and not self.power and not self.power_told:
            self.power_told = True
            print("power switch: not found (setup.sh's GPi Case settings work once the Pi has "
                  "restarted)", flush=True)
        return new

    def drop(self, pad):
        if isinstance(pad, PowerKey):
            self.power.pop(pad.path, None)
        else:
            self.by_path.pop(pad.path, None)
        try:
            self.sel.unregister(pad.dev)
        except (KeyError, ValueError, OSError):
            pass
        try:
            pad.dev.close()
        except OSError:
            pass


# ---- input: the case's power switch ---------------------------------------------------
BUS_HOST = 0x19                  # a device on the Pi's own pins, rather than USB or Bluetooth
HALT_WAIT = 30.0                 # how long 'Shutting down' waits for the Pi to go before giving up
CONFIG_TXT = ("/boot/firmware/config.txt", "/boot/config.txt")


def gpi_case_set_up():
    """True when setup.sh set this Pi up for the GPi Case 2W (its part of config.txt is there)."""
    for path in CONFIG_TXT:
        try:
            with open(path, errors="ignore") as f:
                if "# >>> gpi-case setup >>>" in f.read():
                    return True
        except OSError:
            pass
    return False


def input_driver(dev):
    """The kernel driver behind an input device ('gpio-keys'...), from sysfs: '' when unknown."""
    try:
        path = f"/sys/class/input/{os.path.basename(dev.path)}/device/device/driver"
        return os.path.basename(os.readlink(path))
    except (OSError, AttributeError, TypeError):
        return ""


def is_power_switch(dev, gpi=False):
    """A power switch on the Pi's own pins (the gpio-keys driver's): the one the gpio-shutdown
    line in config.txt makes (setup.sh adds it for the GPi Case 2W), or on the GPi Case, any.
    Not a remote's power button, or a keyboard's."""
    try:
        if dev.info.bustype != BUS_HOST or e.KEY_POWER not in dev.capabilities().get(e.EV_KEY, []):
            return False
        where = os.path.realpath(f"/sys/class/input/{os.path.basename(dev.path)}/device")
    except (OSError, AttributeError, TypeError):
        return False
    if input_driver(dev) != "gpio-keys":
        return False
    return gpi or "shutdown" in (dev.name or "").lower() or "shutdown" in where.lower()


class PowerKey:
    """The power switch. Switched off, the Pi shuts down: systemd-logind does that too when it
    can, and this makes sure of it, whichever mode the screen is in."""

    def __init__(self, dev):
        self.dev, self.path = dev, dev.path

    @staticmethod
    def switched_off(events):
        return any(ev.type == e.EV_KEY and ev.code == e.KEY_POWER and ev.value == 1 for ev in events)


def show_shutdown_lines():
    """The Pi's own lines as it shuts down ("Stopped ...") on the console, even with 'quiet' on
    its command line: systemd shows them from then on when it's sent SIGRTMIN+20."""
    try:
        with open("/proc/1/comm") as f:
            if f.read().strip() != "systemd":
                return
        os.kill(1, signal.SIGRTMIN + 20)
    except (OSError, AttributeError, ValueError):
        pass


# ---- the web page's requests ----------------------------------------------------------
class Control:
    """Requests from the web page, handed to the main loop (it owns the screen and the player)
    and answered once done."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = []
        self.r, self.w = os.pipe()
        os.set_blocking(self.r, False)
        os.set_blocking(self.w, False)

    def ask(self, cmd, timeout=25):
        job = {"cmd": cmd, "done": threading.Event(), "out": None}
        with self.lock:
            self.jobs.append(job)
        try:
            os.write(self.w, b".")                     # wake the main loop
        except OSError:
            pass                                       # (the pipe is full: it's awake already)
        if job["done"].wait(timeout):
            return job["out"]
        with self.lock:
            if any(j is job for j in self.jobs):       # never started: forget it
                self.jobs = [j for j in self.jobs if j is not job]
                return {"error": "Media mode is busy. Try again in a moment"}
        job["done"].wait(timeout)                      # started: let it finish
        return job["out"] or {"error": "Media mode is busy. Try again in a moment"}

    def take(self):
        try:
            while os.read(self.r, 4096):
                pass
        except OSError:
            pass
        with self.lock:
            jobs, self.jobs = self.jobs, []
        return jobs

    @staticmethod
    def done(job, out):
        job["out"] = out
        job["done"].set()


def control_key():
    """A new key for the control server, in a file only root and you (the web page) can read."""
    key = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(CONTROL_KEY), mode=0o755, exist_ok=True)
        tmp = CONTROL_KEY + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        st = os.stat(home_dir())
        os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, CONTROL_KEY)
    except OSError as ex:
        print(f"couldn't save the web page's key: {ex}", flush=True)
    return key


def serve_control(media, control, port=CONTROL_PORT, key=None):
    """A small web server on this Pi only (127.0.0.1) for the web page (webui.py): what's on
    the screen, the lists, and requests to put things there. With a key, every request needs it."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            if not key or hmac.compare_digest((self.headers.get("X-Gpi-Key") or "").encode(), key.encode()):
                return True
            self.reply(401, {"error": "The web page's key doesn't match. Restart gpi-webui."})
            return False

        def reply(self, code, body, ctype="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return
            u = urllib.parse.urlsplit(self.path)
            q = dict(urllib.parse.parse_qsl(u.query))
            try:
                if u.path == "/state":
                    return self.reply(200, media.web_state())
                if u.path == "/screen":
                    shot = media.web_screen()
                    if not shot:
                        return self.reply(403, {"error": "The terminal stays on the Pi's screen"})
                    return self.reply(200, shot[0], shot[1])
                if u.path == "/catalog":
                    return self.reply(200, media.web_catalog())
                if u.path == "/channels":
                    return self.reply(200, media.web_channels(q.get("what", "")))
                if u.path == "/radio":
                    return self.reply(200, media.web_radio(q.get("genre") or None, q.get("q") or None))
                if u.path == "/cameras":
                    return self.reply(200, media.web_cameras())
                if u.path == "/camframe":
                    jpeg = media.web_camframe(q.get("addr", ""))
                    return self.reply(200, jpeg, "image/jpeg") if jpeg else \
                        self.reply(404, {"error": "That camera isn't answering"})
                if u.path == "/friend":
                    return self.reply(200, media.web_friend())
                if u.path == "/friendpic":
                    pic = Friend.picture_bytes(q.get("id", ""))
                    return self.reply(200, pic, "image/jpeg") if pic else self.reply(404, {"error": "No such picture"})
                if u.path == "/icon":
                    icon = media.web_icon(q.get("name", ""), q.get("size") or 96)
                    return self.reply(200, icon, "image/png") if icon else self.reply(404, {"error": "No such app"})
            except Exception as ex:
                print(f"web page asked for {u.path}: {ex!r}", flush=True)
                return self.reply(500, {"error": "Something went wrong on the Pi"})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.allowed():
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if not 0 <= n <= 1 << 20:
                return self.reply(413, {"error": "Too big"})
            if "json" not in (self.headers.get("Content-Type") or ""):
                return self.reply(415, {"error": "JSON only"})
            try:
                cmd = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                cmd = None
            if not isinstance(cmd, dict):
                return self.reply(400, {"error": "Bad request"})
            cmd["cmd"] = urllib.parse.urlsplit(self.path).path.strip("/")
            self.reply(200, control.ask(cmd))

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as ex:
        print(f"the web page can't work the screen: {ex}", flush=True)
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="control").start()
    return server


# ---- the main loop ----------------------------------------------------------------------
def run(ui, media, control=None, stop=None):
    """Controllers (plugged in or out at any time), the web page's requests and media mode's
    clock. stop() returning True ends it (the tests use that)."""
    held = {}        # button name -> [keys, next_repeat_time]  (terminal mode)
    menu_held = {}   # button name -> next_repeat_time            (media screens)
    pending = {}     # (pad, "select" or "start") -> when it goes out, unless the other comes first
    chorded = set()  # (pad, button) pressed as SELECT + START: its release goes nowhere
    was = {"learning": False}

    def key_down(name):
        keys = TERMINAL[name]
        for k in keys:
            ui.write(e.EV_KEY, k, 1)
        ui.syn()
        t = time.monotonic() + REPEAT_DELAY if keys[-1] in REPEAT else NEVER
        held[name] = [keys, t]

    def key_up(name):
        item = held.pop(name, None)
        if item:
            for k in reversed(item[0]):
                ui.write(e.EV_KEY, k, 0)
            ui.syn()

    def can_repeat():
        return (media.active and media.view in Media.REPEAT_VIEWS
                and media.kind not in SCREEN_KINDS and not media.holds_buttons())

    def toggle(to=None):
        """Media mode on or off (HOME)."""
        for n in list(held):
            key_up(n)
        menu_held.clear()
        to = to or ("terminal" if media.active else "media")
        if to == "media" and not media.active:
            media.enter()
        elif to == "terminal" and media.active:
            media.leave()

    def button(name, down):
        if name == MEDIA_TOGGLE:
            if down:
                toggle()
            return
        if media.active:
            if down:
                if media.press(name) == "exit":
                    menu_held.clear()
                    media.leave()
                elif name in MENU_REPEAT and can_repeat():
                    menu_held[name] = time.monotonic() + REPEAT_DELAY
            else:
                menu_held.pop(name, None)
                media.release(name)
            return
        if name in TERMINAL:
            key_down(name) if down else key_up(name)

    def pad_button(pad, name, down):
        """A controller without HOME: SELECT and START together stand in for it."""
        other = {"select": "start", "start": "select"}.get(name)
        if other is None or pad.home:
            button(name, down)
            return
        k, ko = (pad.path, name), (pad.path, other)
        if not down:
            if k in chorded:
                chorded.discard(k)
                return
            if pending.pop(k, None) is not None:       # a quick press: it goes out now
                button(name, True)
            button(name, False)
            return
        if other in pad.down and ko not in chorded:    # both down: HOME
            if pending.pop(ko, None) is None:
                button(other, False)                   # it went out already: let it go
            chorded.update((k, ko))
            toggle()
            return
        pending[k] = time.monotonic() + CHORD_WAIT

    def learn_check():
        """Settings > Controller takes every press while it runs: each controller starts afresh
        when it begins and ends, with nothing waiting to go out."""
        now_learning = media.learning
        if was["learning"] != now_learning:
            pending.clear()
            chorded.clear()
            if not now_learning:
                for p in pads.by_path.values():
                    p.now, p.down = {}, set()
        was["learning"] = now_learning

    def pad_event(pad, ev):
        media.web_guard = False                        # someone at the Pi has it
        learn_check()
        if media.learning:                             # Settings > Controller has it
            media.learn_event(pad, ev)
            return
        for name, down in pad.translate(ev):
            if down and time.monotonic() < media.halting:
                continue                               # shutting down: let go of things, no more
            pad_button(pad, name, down)

    def found(new, quiet=False):
        media.keyreader.exclude = set(pads.by_path)
        if new:
            media.dirty = True
            if not quiet and media.active and not media.proc_owns_screen():
                media.toast(f"{new[-1].dev.name} connected", 2)

    def lost(pad):
        pads.drop(pad)
        print(f"controller gone: {pad.dev.name}", flush=True)
        mine = {k for k in list(pending) + list(chorded) if k[0] == pad.path}
        for name in list(pad.down):
            if (pad.path, name) not in mine:
                button(name, False)                    # nothing stays held down
        pad.down.clear()
        for k in mine:
            pending.pop(k, None)
            chorded.discard(k)
        if media.learn and media.learn.get("pad") is pad:
            media.cancel_learn("The controller was unplugged")
        found([])
        media.dirty = True

    def handle(cmd):
        """One request from the web page. It works media mode, never the terminal."""
        if time.monotonic() < media.halting:
            return {"error": "The Pi is shutting down"}
        media.web_guard = True
        c = cmd.get("cmd")
        if c == "press":
            name = cmd.get("button")
            if name not in BUTTONS:
                return {"error": "No such button"}
            if not media.active and name != MEDIA_TOGGLE:
                return {"error": "The remote works in media mode. Press Home to open it."}
            if cmd.get("repeat"):                      # held down on the page
                if name not in MENU_REPEAT:
                    return {"ok": True}
                if media.active:
                    if can_repeat():
                        media.press(name, repeat=True)
                    return {"ok": True}
            button(name, True)
            button(name, False)
            return {"ok": True}
        if c == "mode":
            to = cmd.get("to")
            if to not in ("media", "terminal"):
                return {"error": "No such mode"}
            toggle(to)
            if to == "media" and not media.active:
                return {"error": "There's no screen for media mode"}
            return {"ok": True}
        if not media.active:
            for n in list(held):
                key_up(n)
        return media.web_command(cmd)

    sel = selectors.DefaultSelector()
    pads = Pads(sel)
    media.pads = pads
    if control is not None:
        sel.register(control.r, selectors.EVENT_READ, "control")
    found(pads.scan(time.monotonic(), force=True), quiet=True)
    if media.boot_media:                          # Settings: open on the home screen
        media.boot_media = False
        media.enter()

    try:
        while not (stop and stop()):
            nxt = min([t for _, t in held.values()] + list(menu_held.values()) + list(pending.values())
                      + [pads.next_scan])
            timeout = max(0.0, nxt - time.monotonic())
            if media.active or media.proc or media.learn:
                timeout = min(timeout, media.tick_limit())

            for key, _ in sel.select(timeout):
                if key.data == "control":
                    for job in control.take():
                        out = {"error": "Something went wrong on the Pi"}
                        try:
                            out = handle(job["cmd"])
                            learn_check()
                            media.flush()             # so the next picture of the screen shows it
                        except Exception as ex:
                            print(f"web page request {job['cmd'].get('cmd')}: {ex!r}", flush=True)
                        finally:
                            control.done(job, out)
                    continue
                if isinstance(key.data, PowerKey):
                    switch = key.data
                    if pads.power.get(switch.path) is not switch:
                        continue
                    try:
                        events = list(switch.dev.read())
                    except BlockingIOError:
                        continue
                    except OSError:
                        pads.drop(switch)
                        continue
                    if switch.switched_off(events):
                        media.power_off()
                    continue
                pad = key.data
                if pads.by_path.get(pad.path) is not pad:
                    continue                           # unplugged a moment ago
                try:
                    events = list(pad.dev.read())
                except BlockingIOError:
                    continue
                except OSError:
                    lost(pad)
                    continue
                for ev in events:
                    pad_event(pad, ev)

            found(pads.scan(time.monotonic()))
            media.tick()
            learn_check()

            now = time.monotonic()
            for k, t in list(pending.items()):
                if now >= t:                          # SELECT or START alone: out it goes
                    del pending[k]
                    button(k[1], True)
            for item in held.values():
                if now >= item[1]:
                    ui.write(e.EV_KEY, item[0][-1], 2)
                    ui.syn()
                    item[1] = now + REPEAT_RATE
            for name, t in list(menu_held.items()):
                if now >= t:
                    if not can_repeat():
                        menu_held.pop(name, None)
                    else:
                        media.press(name, repeat=True)
                        menu_held[name] = now + MENU_RATE

            media.flush()
    finally:
        for pad in list(pads.by_path.values()) + list(pads.power.values()):
            pads.drop(pad)
        sel.close()


def main():
    keys = sorted({k for combo in TERMINAL.values() for k in combo})
    ui = UInput({e.EV_KEY: keys}, name=NAME)
    media = Media()
    control = Control()
    serve_control(media, control, key=control_key())

    def on_term(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, on_term)

    try:
        while True:
            try:
                run(ui, media, control)
            except OSError as ex:
                print(f"input trouble ({ex}), starting again", flush=True)
                time.sleep(1)
    finally:
        media.shutdown()       # never leave the screen stuck in media mode


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
