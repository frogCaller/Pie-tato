"""Where your settings are: the static folder and its settings files, the saved state's settings,
and reading and writing settings files."""
import glob
import os
import re
import stat
import tempfile

from .theme import ACCENTS


CONTROL_PORT = 5480        # the web page (webui.py) works media mode through this, on this Pi only
WEB_PORT = 5432            # ...which is itself on this port (the Bot at work gives its address to agents)
CONTROL_KEY = "/run/pitato/control-key"   # ...with this key, readable by you and root only
# passwords and tokens: never shown
WEB_PRIVATE = {"webui.txt", "homeassistant.txt", "plex.txt", "jellyfin.txt", "pihole.txt"}


# ---- your settings files: the static folder ---------------------------------
def settings_dir():
    """Where your settings files are (radio.txt, bot.txt...): the static folder in the pitato
    folder. The service is told where that is (setup.sh); run by hand, it's the one next to the
    code's own folder."""
    told = os.environ.get("PITATO_STATIC", "").strip()
    if told:
        return os.path.abspath(told)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


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


# ---- settings: saved with the rest of the state ---------------------------------------
WALLPAPERS = ["Midnight", "Dusk", "Ocean", "Forest", "Aurora", "Black", "Picture"]
SCREEN_MODES = ["Fit", "Full screen", "Stretch"]   # Settings > Video size; Y while a video plays
SETTINGS = [   # key, label, choices (None: opens a page of its own)
    ("wifi", "WiFi", None),
    ("bluetooth", "Bluetooth", None),     # your controllers, keyboards and the rest: find, pair, connect
    ("wallpaper", "Background", WALLPAPERS),
    ("home_style", "Home screen style", ["Bright", "Glass", "Minimal", "Cards"]),
    ("accent", "Accent colour", [a for a, _ in ACCENTS]),
    ("clock", "Clock", ["12-hour", "24-hour"]),
    ("widget", "On the home screen", ["Weather", "Just the time"]),
    ("location", "Location", None),
    ("units", "Temperature", ["°F", "°C"]),
    ("screen", "Video size", SCREEN_MODES),
    ("resolution", "Resolution", None),   # a TV or monitor's: the sizes it takes (not there on the GPi Case)
    ("sound", "Sound", None),
    ("pad", "Controller", None),
    ("pad_swap", "Swap A and B", ["Off", "On"]),   # on the controller in hand (kept with its buttons, not here)
    ("friend", "Bot", None),
    ("start", "At start-up", ["Home screen", "Terminal"]),
    ("start_song", "Random song at start-up", ["Off", "On"]),   # one of yours from ~/Music, as it starts
]
SETTINGS_DEFAULT = {"wallpaper": "Midnight", "picture": "", "accent": "Blue", "clock": "12-hour",
                    "widget": "Weather", "units": "°F", "start": "Home screen", "location": None,
                    "screen": "Fit", "sound": "Auto", "coder_sound": "On", "sim_full": "Off", "bot_mode": "chat",
                    "game_picture": "Fit", "start_song": "Off", "home_style": "Glass",
                    "ds_screens": "Left/Right", "ds_touch": "Right stick, R2"}
HOME_STYLE_WAS = {"Original": "Bright", "Style 2": "Glass", "Style 3": "Minimal", "Style 4": "Cards"}   # (earlier names)
SETTINGS_GONE = ("shrink",)   # settings there were once (Big videos: they're made smaller whenever they need it)


STATE_FILE = "/var/lib/pitato/state.json"   # resume points, lengths, lists
CACHE_DIR = "/var/cache/pitato"             # thumbnails, converted documents
OLD_PLACES = (("/var/lib/gpi-keys", "/var/lib/pitato"), ("/var/cache/gpi-keys", "/var/cache/pitato"))


def move_old_places():
    """What it kept by the name it had before (gpi-media), where it keeps it now. setup.sh moves them; this is
    for a setup.sh that didn't get that far."""
    for old, new in OLD_PLACES:
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                os.rename(old, new)
            except OSError:
                pass


def home_dir():
    homes = sorted(h for h in glob.glob("/home/*") if os.path.isdir(h))
    return homes[0] if homes else "/root"


def read_lines(patterns):
    for pattern in patterns:
        for fn in sorted(glob.glob(pattern)):
            try:
                yield from open(fn, errors="ignore").read().splitlines()
            except OSError:
                continue


def read_config(patterns):
    """'key = value' lines; lines starting with # are notes."""
    cfg = {}
    for line in read_lines(patterns):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip().lower()] = v.strip()
    return cfg


def clean_name(text, limit=40):
    """A name fit for a line of a settings file, and the screen: printable, on one line."""
    text = "".join(c if c.isprintable() else " " for c in str(text or ""))
    return " ".join(text.split())[:limit]


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


def write_setting(name, text, private=False):
    """A settings file in the static folder, written whole and owned by you: a new file swapped
    in, so a link left in its place is replaced rather than followed (this runs as root)."""
    st = os.stat(home_dir())
    if not os.path.isdir(STATIC):                     # not made yet: yours, like the rest (and only
        os.mkdir(STATIC)                              # in a pitato folder that's there)
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


def edit_config(name, updates, head="", was="", limit=400):
    """'key = value' lines in a settings file changed or added; the rest kept. A file that isn't
    there yet starts from `was` (its earlier name), if that one is. Values: a line each, `limit`
    characters at most."""
    path = settings_file(name)
    updates = {k: clean_name(v, limit) for k, v in updates.items()}
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
