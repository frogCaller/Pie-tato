"""What's in each tab of media mode, and what plays things."""
from .theme import FONT
from .config import read_lines, settings_glob
from .util import AUDIO_EXTS, item, VIDEO_EXTS
from .tv import ia_best


# ---- media mode: what's in each tab -----------------------------------------
LIBRARY = [
    {"name": "Home Assistant", "type": "group", "empty": "", "children": ["TV Remote", "Lights", "Pi-hole"]},
    {"name": "TV", "type": "group", "empty": "",
     "children": ["Plex", "Jellyfin", "Cartoons", "Free Movies", "News", "Sports", "Streams"]},
    {"name": "Music", "type": "files", "dirs": ["/home/*/Music"],
     "exts": AUDIO_EXTS, "kind": "audio", "empty": "Copy music into ~/Music"},
    {"name": "Radio", "type": "radio", "files": [settings_glob("radio.txt")],
     "empty": "Add stations to static/radio.txt  as  Name | URL"},
    {"name": "Camera", "type": "camera", "files": [settings_glob("camera.txt")], "empty": ""},
    {"name": "Photos", "type": "photos", "dirs": ["/home/*/Pictures"],
     "empty": "Copy pictures into ~/Pictures"},
    {"name": "Videos", "type": "files", "dirs": ["/home/*/Videos"],
     "exts": VIDEO_EXTS, "kind": "video", "empty": "Copy video files into ~/Videos"},
    {"name": "Games", "type": "games", "empty": ""},
    {"name": "Weather", "type": "weather", "empty": ""},
    {"name": "Finance", "type": "finance", "files": [settings_glob("finance.txt")], "empty": ""},
    {"name": "Bot", "type": "friend", "files": [settings_glob("bot.txt")], "empty": ""},
    {"name": "Simulator", "type": "group", "empty": "",
     "children": ["Rock Paper Scissors", "Game of Life", "Forest Fire", "Mandelbrot Set", "cmatrix", "hollywood",
                  "nyancat", "cacafire", "htop"]},
    {"name": "Files", "type": "browser", "empty": "This folder is empty"},
    {"name": "System", "type": "system", "empty": ""},
    {"name": "Settings", "type": "settings", "empty": ""},
    # inside the TV tab (no tab of their own along the top)
    {"name": "Plex", "type": "plex", "parent": "TV", "badge": "PLEX",
     "about": "Your movies and shows, Live TV", "empty": "This library is empty"},
    {"name": "Jellyfin", "type": "jellyfin", "parent": "TV", "badge": "JELLY",
     "about": "Your movies and shows", "empty": "This library is empty"},
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
    # inside the Home Assistant tab
    {"name": "TV Remote", "type": "remote", "parent": "Home Assistant", "badge": "TV",
     "about": "Your TVs through Home Assistant", "files": [settings_glob("homeassistant.txt")],
     "empty": ""},
    {"name": "Lights", "type": "lights", "parent": "Home Assistant", "badge": "LIGHT",
     "about": "Your lights through Home Assistant", "files": [settings_glob("homeassistant.txt")],
     "empty": ""},
    {"name": "Pi-hole", "type": "pihole", "parent": "Home Assistant", "badge": "DNS",   # (from Pi-hole itself)
     "about": "Your Pi-hole's numbers", "files": [settings_glob("pihole.txt")], "empty": ""},
    # inside the Games tab
    {"name": "Snake", "type": "sim", "sim": "snake", "parent": "Games", "badge": "EAT", "title": "Snake",
     "about": "Eat the apples, don't crash", "empty": ""},
    # inside the Simulator tab
    {"name": "Rock Paper Scissors", "type": "sim", "sim": "rps", "parent": "Simulator", "badge": "RPS",
     "about": "Last team standing", "empty": ""},
    {"name": "Game of Life", "type": "sim", "sim": "life", "parent": "Simulator", "badge": "LIFE",
     "about": "Cells live, die and are born", "empty": ""},
    {"name": "Forest Fire", "type": "sim", "sim": "fire", "parent": "Simulator", "badge": "FIRE",
     "about": "Trees grow, fires spread", "empty": ""},
    {"name": "Mandelbrot Set", "type": "sim", "sim": "mandel", "parent": "Simulator", "badge": "ZOOM",
     "about": "Dives into the famous fractal", "empty": ""},
    # (Linux's own cmatrix, hollywood, nyancat, cacafire and htop: A starts one, on the whole screen)
    {"name": "cmatrix", "type": "prog", "prog": "cmatrix", "parent": "Simulator", "badge": "CODE",
     "about": "Linux's falling code. B stops it", "empty": ""},
    {"name": "hollywood", "type": "prog", "prog": "hollywood", "parent": "Simulator", "badge": "HACK",
     "about": "Movie hacker screens. B stops it", "empty": ""},
    {"name": "nyancat", "type": "prog", "prog": "nyancat", "parent": "Simulator", "badge": "NYAN",
     "about": "The rainbow cat. B stops it", "empty": ""},
    {"name": "cacafire", "type": "prog", "prog": "cacafire", "parent": "Simulator", "badge": "HEAT",
     "about": "Flames made of letters. B stops it", "empty": ""},
    {"name": "htop", "type": "prog", "prog": "htop", "parent": "Simulator", "badge": "PROC",
     "about": "What's running on the Pi. B stops it", "empty": ""},
]

MEDIA_VT = 7          # spare console the menu and player draw on


MENU_REPEAT = {"up", "down", "left", "right"}  # hold to keep scrolling
MENU_RATE = 0.11
SLIDESHOW_SECS = 5
TEXT_LIMIT = 2_000_000                         # bytes of a text file to show


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


def video_scale(mode, size, w=640, h=480, turn=0):
    """mplayer's scaling for the screen: Fit keeps the whole picture, Fill zooms it to cover the
    screen (cutting the edges, so letterboxed or 16:9 shows fill it), Stretch pulls it to fit. A screen on its
    side (turn: degrees, clockwise; w and h its size as it's seen): scaled for that, then turned, with what mplayer
    writes over it (where you are in it, subtitles) put on first, so they're turned too."""
    if turn in (90, 180, 270):
        vf = video_scale(mode, size, w, h)
        if vf[0] != "-vf":                               # (the GPi Case's own way: as for any other screen)
            vf = ["-vf", f"dsize={w}:{h}:0,scale=0:0"]
        return vf[:-1] + [vf[-1] + ",expand=::::1," + {90: "rotate=1", 180: "flip,mirror", 270: "rotate=2"}[turn]]
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


LISTEN_KINDS = ("audio", "radio")          # keep playing in the terminal
BOOT_SONG_WAIT = 2.0                       # Settings > Random song at start-up: seconds in, once the screen's up
NOW_POP_SECS = 5.0                         # the home screen's card of what's playing: up this long when a song starts
SCREEN_KINDS = ("video", "live", "plex")  # the player owns the screen


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


def resolve(it):
    """Turn an item into something mplayer can open."""
    if it["src"].startswith("ia:"):
        ident, name = it["src"][3:].split("/", 1)
        return ia_best(ident, name)
    return it["src"]
