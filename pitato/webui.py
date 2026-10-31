#!/usr/bin/env python3
"""
webui.py - the Pi's screen and files, from any browser on your WiFi.

Screen: what's on the Pi's screen right now, tapped as the Pi's buttons would be (pitato.py says what's
where), and a remote for it. Library: cartoons, films, news, sports, radio and cameras to put on it
(through pitato.py, which listens on this Pi only). Its Draw tab draws a picture for the screen: PUT
/api/draw puts it there and keeps it in ~/Pictures/Drawings. Play here plays what's picked in the
browser instead (a game in EmulatorJS, fetched from npm the first time and handed out from here:
/play); Sound here plays the Pi's sound there, and Mic here gives the bot the browser's microphone
(both through the Loopback card setup.sh adds). A browser allows a microphone only on a secure page,
so the page is on https://<your Pi's name>.local:5443 too, with a certificate of the Pi's own.

Files: drag files or whole folders onto the page and they land in ~/Music, ~/Videos, ~/Pictures,
~/Documents or ~/Games (picked by file type), ready for media mode, and media mode's settings files
(radio.txt, bot.txt...) in the static folder. The page also lists what's there, shows it on the
screen, and downloads or deletes it. Its Computers tab does the same for your other computers'
files (pitato.py opens them, read-only: nothing on them can be changed or deleted from here).

setup.sh installs it as the pitato-web service, running as your user. Then open
    http://<your Pi's name>.local:5432

The page is templates/index.html, and its typeface is in static/fonts: the only part of the static
folder handed out as it is. Your settings files go in the static folder of the Pietato folder
(setup.sh tells the service where that is; run by hand, it's the one beside the folder this script
is in).

Optional, static/webui.txt:
    password = something       the page asks for it before showing anything
    hosts = tv.example.lan     other names you open the page by (its .local name and its
                               address always work; other names are turned away, so a web
                               site can't reach the page by pointing a name of its own at it)

The Bot hears from your coding agent here too, and acts it out at work: Claude Code's hooks
(coder_hooks.py sets them up, and is handed out at /coder_hooks.py), POST /coder?pose=typing from
anything else, and a WAV to POST /coder/say to have it said out loud. Prompts typed on the Pi go the
other way: coder_hooks.py --channel, which Claude Code runs, asks for them at POST /coder/prompts.
With a password, these send it as a token (Authorization: Bearer ...).
"""
import base64
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
import logging
import math
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

from flask import Flask, Response, abort, jsonify, request, send_file

PORT = 5432
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = HERE if os.path.isdir(os.path.join(HERE, "templates")) else os.path.dirname(HERE)   # installed: the page
HOME = os.path.expanduser("~")                            # beside this; in the Pietato folder: one folder up
TOLD = os.environ.get("PITATO_STATIC", "").strip()        # where setup.sh says the static folder is
STATIC = os.path.abspath(TOLD or os.path.join(TOP, "static"))
KNOWS = bool(TOLD) or os.path.isfile(os.path.join(TOP, "setup.sh"))   # told, or run from the folder
PAGE = os.path.join(TOP, "templates", "index.html")
FONTS_DIR = os.path.join(TOP, "static", "fonts")
STATE_FILE = "/var/lib/pitato/state.json"     # the handheld's settings (its accent colour)
SPARE = 64 << 20                                # room left on the card after an upload
CHUNK = 1 << 20

FOLDERS = {"music": "Music", "videos": "Videos", "pictures": "Pictures", "documents": "Documents",
           "games": "Games", "home": "", "computers": None, "settings": None}
# (settings: the static folder; computers: your other computers' folders, as media mode opened them)
LABELS = {"music": "Music", "videos": "Videos", "pictures": "Pictures", "documents": "Documents",
          "games": "Games", "home": "Home", "computers": "Computers", "settings": "Settings"}
NET_ROOT = "/run/pitato/computers"              # where media mode opens your other computers' folders (read-only)
KINDS = {   # what goes where when the page picks for you
    "music": [".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma"],
    "videos": [".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg"],
    "pictures": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"],
    "documents": [".pdf", ".epub", ".txt", ".md", ".docx", ".doc", ".odt", ".rtf", ".xlsx", ".xls",
                  ".ods", ".csv", ".pptx", ".ppt", ".odp"],
    "games": [".gb", ".gbc", ".gba", ".nes", ".sfc", ".smc", ".md", ".gen", ".smd", ".sms", ".gg", ".z64", ".n64",
              ".v64", ".cue", ".bin", ".chd", ".pbp", ".m3u", ".iso", ".cso", ".nds", ".gdi", ".cdi", ".raw"],
}
SETTINGS_FILES = ["radio.txt", "streams.txt", "streams.m3u", "finance.txt", "crypto.txt", "camera.txt", "bot.txt",
                  "homeassistant.txt", "plex.txt", "jellyfin.txt", "pihole.txt"]   # media mode's settings: in static/
PRIVATE = {"webui.txt", "homeassistant.txt", "plex.txt", "jellyfin.txt", "pihole.txt"}   # passwords: never shown
INLINE = set(KINDS["music"] + KINDS["videos"] + KINDS["pictures"] + [".pdf", ".txt", ".md"])
ACCENTS = {"Blue": "#60aae4", "Teal": "#40c4b4", "Green": "#6ec878", "Purple": "#a082e6",
           "Pink": "#e878aa", "Red": "#ec6464", "Gold": "#e6be50", "White": "#e4e8ee"}
BAD_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]")
CONTROL = ("127.0.0.1", 5480)                   # pitato.py's media mode, on this Pi only
CONTROL_KEY = "/run/pitato/control-key"       # ...and the key it asks for (made at its start)
PI_GET = {"state", "screen", "catalog", "channels", "radio", "icon", "cameras", "camframe", "friend", "friendpic",
          "computers", "bluetooth", "settings", "places"}
PI_POST = {"press", "open", "play", "show", "player", "learn", "mode", "reset_pads", "pad_swap", "camera", "friend",
           "computer", "bluetooth", "settings", "tap", "swipe", "scroll", "type"}
PI_ARGS = ("what", "genre", "q", "name", "size", "addr", "id", "after", "wait")
FRAME_WAIT = 20                                 # seconds the page's request for the screen's next picture waits, at most
CODER = ("rest", "typing", "reading", "thinking", "talking", "done", "hello", "attention", "error",
         "shrug", "wake", "sleep")                     # the Bot's poses at work
CODER_SAY_AS = ("talking", "typing", "reading", "thinking", "rest")   # the poses it says a clip in
CLIP_MAX = 8 << 20                                      # bytes of a clip to say
CLIP_TURN = threading.Lock()                            # clips take turns (the next waits, unread)
HOOK_MAX = 32 << 20                                     # bytes of a hook's report read (a big edit's is big)
HOOK_READS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead"}   # Claude Code's tools that read
HOOK_HELPERS = {"Task", "Agent"}                        # ...and that hand work to a helper
THUMBS = os.path.join(HOME, ".cache", "pitato", "thumbs")   # small copies of your pictures
DRAWINGS = "Drawings"                                   # the Draw tab's drawings: a folder in Pictures
DRAWING_MAX = 8 << 20                                   # bytes of one (a PNG of a 1080p screen is far less)
PNG = b"\x89PNG\r\n\x1a\n"

app = Flask(__name__, static_folder=None)     # static/ holds your settings: only its fonts go out


# ---- settings and paths --------------------------------------------------------
class Unreadable(Exception):
    """webui.txt is there but can't be read, or the static folder is missing: the page won't open
    without its password."""


def settings():
    """static/webui.txt, read on every request so a change needs no restart (one still in your
    home folder, where it used to go, counts until setup.sh moves it). Unreadable when it can't
    tell whether there's a password."""
    if not KNOWS or not os.path.isdir(STATIC):
        raise Unreadable("Run sudo bash setup.sh again from the Pietato folder: the page can't "
                         "find its static folder")
    cfg = {}
    for path in (os.path.join(STATIC, "webui.txt"), os.path.join(HOME, "webui.txt")):
        if path != os.path.join(STATIC, "webui.txt") and not os.path.isfile(path):
            continue                                   # (only ever a file of yours, there)
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip().lower()] = v.strip()
            return cfg
        except FileNotFoundError:
            continue
        except OSError:
            raise Unreadable(f"The page can't read {path}")
    return cfg


PRIVATE_NAME = re.compile(r"[#.~]*(" + "|".join(map(re.escape, sorted(PRIVATE))) + ")")
PASSWORD_NAME = re.compile(r"[#.~]*webui\.txt")


def private(name):
    """A password or a token, or a copy of one an editor left (webui.txt.save, homeassistant.txt~,
    #plex.txt#), but not complex.txt."""
    return bool(PRIVATE_NAME.match((name or "").lower()))


def accent():
    try:
        with open(STATE_FILE) as f:
            name = (json.load(f).get("settings") or {}).get("accent")
    except (OSError, ValueError):
        name = None
    return ACCENTS.get(name, ACCENTS["Blue"])


def clean_name(name):
    """A file or folder name that's safe to write: no slashes, control characters or leading dots."""
    name = BAD_CHARS.sub("", name or "").strip().lstrip(".").strip()
    while len(name.encode()) > 240:                     # keep the extension when shortening
        stem, ext = os.path.splitext(name)
        name = (stem[:-1] + ext) if stem else name[:-1]
    return name


def clean_parts(path):
    parts = []
    for p in (path or "").replace("\\", "/").split("/"):
        p = clean_name(p)
        if p and p not in (".", ".."):
            parts.append(p)
    return parts


def root_of(key):
    if key not in FOLDERS:
        abort(404)
    if key == "settings":
        return os.path.realpath(STATIC)                # (setup.sh makes it; the page never does)
    if key == "computers":
        return os.path.realpath(NET_ROOT)              # (media mode makes it, as root)
    root = os.path.join(HOME, FOLDERS[key]) if FOLDERS[key] else HOME
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        pass
    return os.path.realpath(root)


def inside(root, path):
    return path == root or path.startswith(root + os.sep)


def in_app_folder(path):
    """True inside the Pietato folder (the static folder's), unless that's your home folder
    itself: the page leaves it as it is. setup.sh runs from there, and settings go in through
    Settings."""
    folder = os.path.realpath(os.path.dirname(STATIC))
    return folder != os.path.realpath(HOME) and inside(folder, os.path.realpath(path))


def holds_app_folder(path):
    """True for a folder with the Pietato folder in it, somewhere: it can't be deleted."""
    return inside(os.path.realpath(path), os.path.realpath(STATIC))


def shown_path(key):
    """A folder as the page shows it: ~/Music, ~/pietato/static..."""
    if key == "computers":
        return "Other computers"
    if key != "settings":
        return "~/" + FOLDERS[key] if FOLDERS[key] else "~"
    real, home = os.path.realpath(STATIC), os.path.realpath(HOME)
    return "~/" + os.path.relpath(real, home) if inside(home, real) and real != home else real


def locate(key, rel, must_exist=True):
    """(folder's root, full path, path parts) for a path inside one of the folders, never outside."""
    root = root_of(key)
    parts = clean_parts(rel)
    if key == "settings" and parts and (len(parts) != 1 or parts[0].lower() not in SETTINGS_FILES):
        abort(404)                                     # Settings: the settings files, nothing else
    full = os.path.realpath(os.path.join(root, *parts)) if parts else root
    if not inside(root, full):
        abort(403)
    if must_exist and not os.path.exists(full):
        abort(404)
    return root, full, parts


def protected():
    """The folders themselves can't be deleted from the page."""
    return {os.path.realpath(os.path.join(HOME, sub)) for sub in FOLDERS.values() if sub is not None} \
        | {os.path.realpath(STATIC)}


def free_name(path):
    """song.mp3 -> song (2).mp3 when the first is taken."""
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.lexists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def natural(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def count_files(root, limit=100000):
    n = 0
    for _, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        n += sum(1 for f in files if not f.startswith("."))
        if n >= limit:
            break
    return n


# ---- who may ask --------------------------------------------------------------------
def host_ok():
    """The page answers to this Pi's name (name.local...), an address, or a name in webui.txt."""
    try:
        host = (urllib.parse.urlsplit("//" + (request.host or "")).hostname or "").lower()
    except ValueError:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    name = socket.gethostname().lower()
    names = {"localhost", name} | {f"{name}.{d}" for d in ("local", "lan", "home", "home.arpa", "localdomain")}
    names |= {h.lower() for h in re.split(r"[,\s]+", settings().get("hosts", "")) if h}
    return host in names


PAGE_ONLY = {"state", "catalog", "channels", "radio", "cameras", "friend", "computers",
             "bluetooth", "settings", "places"}   # (pictures load without it)


def coder_path():
    """Where your coding agent talks to the Bot at work."""
    return request.path == "/coder" or request.path.startswith("/coder/")


@app.before_request
def check_password():
    try:
        settings()
    except Unreadable as ex:                           # no telling whether there's a password
        return Response(str(ex), 503)
    if not host_ok():
        return Response(pc_said("Open this page by the Pi's name or address"), 403)
    # Another website open in the same browser can't make this page do things: browsers say
    # where a request came from, and the page's own requests carry a header no site can add
    # without asking first.
    if request.path != "/" and request.headers.get("Sec-Fetch-Site") == "cross-site":
        return Response("Not from another site", 403)
    if (request.method in ("GET", "HEAD") and request.path.startswith("/api/pi/")
            and request.path[8:] in PAGE_ONLY and request.headers.get("X-Pitato-Page") != "1"):
        return Response("Only the page asks for that", 403)
    pw = settings().get("password")
    if not pw or request.path == "/coder_hooks.py":    # (that script has nothing private in it)
        return None
    if coder_path():                                   # your agent: the password, as a token
        scheme, _, token = (request.headers.get("Authorization") or "").strip().partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), pw.encode()):
            return None
    auth = request.authorization
    if auth and auth.password is not None and hmac.compare_digest(auth.password.encode(), pw.encode()):
        return None
    if coder_path():
        return jsonify(ok=False, error="The web page's password is needed"), 401
    return Response("Password needed", 401, {"WWW-Authenticate": 'Basic realm="Pietato"'})


@app.after_request
def no_sniff(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ---- the page ----------------------------------------------------------------------
PI_MODEL = "/proc/device-tree/model"            # a Pi's model; a PC hasn't one...
DMI = "/sys/class/dmi/id"                      # ...but its firmware's description of itself (pitato/system.py's is_pc)
PC_WORDS = re.compile(r"\b([Tt]he|[Tt]his|[Yy]our|[Aa]) Pi\b(?![-\w]| \d| Zero| OS| Case)")


def is_pc():
    """A computer of your own (Intel or AMD, with Ubuntu) rather than a Pi."""
    try:
        with open(PI_MODEL, errors="replace") as f:
            if "Raspberry Pi" in f.read():
                return False
    except OSError:
        pass
    return os.path.isdir(DMI)


def pc_said(text):
    """What the server says, as it goes on a PC: "the PC", not "the Pi"."""
    return PC_WORDS.sub(lambda m: m.group(1) + " PC", text) if isinstance(text, str) and is_pc() else text


@app.after_request
def pc_errors(resp):
    """On a PC, an error's words say "the PC", not "the Pi" (the server's own, or media mode's passed on)."""
    if resp.mimetype != "application/json" or resp.direct_passthrough or resp.is_streamed or resp.status_code < 400 \
            and b'"error"' not in resp.get_data():
        return resp
    try:
        data = json.loads(resp.get_data(as_text=True))
    except ValueError:
        return resp
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        said = pc_said(data["error"])
        if said != data["error"]:
            data["error"] = said
            resp.set_data(json.dumps(data))
    return resp


def page_file(path, mimetype=None):
    """One of the page's own files, handed out: on a PC, what it says about the Pi says "the PC" instead (never a
    Pi-hole, a Pi 4 or a Pi Zero)."""
    if not is_pc():
        return send_file(path, mimetype=mimetype)
    with open(path, encoding="utf-8") as f:
        text = PC_WORDS.sub(lambda m: m.group(1) + " PC", f.read())
    return Response(text, mimetype=mimetype or "text/html")


@app.get("/")
def index():
    resp = page_file(PAGE)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


FONTS = {"next-latin.woff2", "next-latin-ext.woff2"}


@app.get("/static/fonts/<name>")
def font(name):
    """The page's typeface (Atkinson Hyperlegible, OFL), kept for a year: the only thing handed
    out from a static folder."""
    if name not in FONTS:
        abort(404)
    resp = send_file(os.path.join(FONTS_DIR, name), mimetype="font/woff2", conditional=True)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.get("/api/info")
def info():
    du = shutil.disk_usage(HOME)
    folders = []
    for key in FOLDERS:
        root = root_of(key)
        folders.append({"key": key, "label": LABELS[key], "path": shown_path(key),
                        "files": None if key in ("home", "settings", "computers") else count_files(root)})
    return jsonify(name=socket.gethostname(), accent=accent(), folders=folders, kinds=KINDS,
                   settingsFiles=SETTINGS_FILES, disk={"free": du.free, "total": du.total, "spare": SPARE})


@app.get("/api/list")
def list_folder():
    key = request.args.get("folder", "music")
    if key == "computers":
        parts = clean_parts(request.args.get("path", ""))
        listed = list_computers(parts)
        if listed is not None:
            return listed
    root, full, parts = locate(key, request.args.get("path", ""))
    if not os.path.isdir(full):
        abort(404)
    keep = protected()
    entries = []
    with os.scandir(full) as it:
        for e in it:
            if e.name.startswith(".") or private(e.name):
                continue
            if key == "settings" and e.name.lower() not in SETTINGS_FILES:
                continue
            try:
                is_dir = e.is_dir()
                st = e.stat()
            except OSError:
                continue
            entry = {"name": e.name, "dir": is_dir, "size": 0 if is_dir else st.st_size,
                     "mtime": int(st.st_mtime)}
            if key == "computers":
                entry["locked"] = True                   # (read-only: nothing on them changes from here)
                if is_dir:
                    entry["items"] = None                # (no counting: each would be a trip to the computer)
            elif is_dir:
                try:
                    with os.scandir(e.path) as sub:
                        entry["items"] = sum(1 for x in sub if not x.name.startswith("."))
                except OSError:
                    entry["items"] = 0
                # folders in your home folder (your projects) and the media folders stay put
                entry["locked"] = key == "home" or os.path.realpath(e.path) in keep
            elif key != "settings" and in_app_folder(e.path):
                entry["locked"] = True                   # the Pietato folder stays as it is
            entries.append(entry)
    entries.sort(key=lambda x: (not x["dir"], natural(x["name"])))
    return jsonify(folder=key, path="/".join(parts), entries=entries)


# ---- your other computers: media mode opens them (as root), the page reads them ------------------
def from_pi(method, path, body=None, timeout=60):
    """Media mode's answer as (JSON, None), or (None, an error response)."""
    got = ask_pi(method, path, body, timeout=timeout)
    if got is None or got[0] == 401:
        return None, (jsonify(error="The Pi's screen isn't answering. Is Pietato running?"), 503)
    try:
        data = json.loads(got[1] or b"{}")
    except ValueError:
        data = {}
    if got[0] != 200 or not isinstance(data, dict) or data.get("error"):
        return None, (jsonify(error=(data or {}).get("error") or "The Pi said no", kind=(data or {}).get("kind")), 502)
    return data, None


def open_computer(parts):
    """The folder a path on another computer is in, opened by media mode if it isn't (a restart closes them):
    None, or an error response."""
    if not parts:
        return None
    _, bad = from_pi("POST", "/computer", {"do": "open", "path": "/".join(parts)})
    return bad


def list_computers(parts):
    """The Computers tab's own lists: the computers, and a computer's shared folders. None: a folder on one,
    opened now, for the usual listing."""
    if not parts:
        data, bad = from_pi("GET", "/computers", timeout=15)
        if bad:
            return bad
        entries = [{"name": c["key"], "label": c["addr"], "dir": True, "computer": True, "how": c["how"],
                    "user": c.get("user", ""), "start": c.get("start") or c["key"], "items": None, "size": 0,
                    "mtime": 0, "locked": True} for c in data.get("computers", [])]
        return jsonify(folder="computers", path="", entries=entries)
    if len(parts) == 1:
        data, bad = from_pi("GET", "/computers?" + urllib.parse.urlencode({"addr": parts[0]}))
        if bad:
            return bad
        if data.get("how") == "smb":
            entries = [{"name": sh, "dir": True, "share": True, "items": None, "size": 0, "mtime": 0, "locked": True}
                       for sh in data.get("shares", [])]
            return jsonify(folder="computers", path=parts[0], entries=entries, label=data.get("addr"))
    bad = open_computer(parts)
    if bad:
        return bad
    return None


@app.get("/api/recent")
def recent():
    """Your newest pictures, in folders too: for sending one to the bot."""
    root = root_of("pictures")
    try:
        n = max(1, min(int(request.args.get("n") or 40), 200))
    except ValueError:
        n = 40
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith(".") or private(name) or os.path.splitext(name)[1].lower() not in KINDS["pictures"]:
                continue
            full = os.path.join(folder, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            found.append((st.st_mtime, os.path.relpath(full, root), st.st_size))
        if len(found) > 50000:
            break
    found.sort(reverse=True)
    return jsonify(folder="pictures", pictures=[{"path": p, "name": os.path.basename(p), "mtime": int(t), "size": z}
                                                 for t, p, z in found[:n]])


READ_ONLY = "Your other computers' files can't be changed from here"


@app.get("/api/exists")
def exists():
    key = request.args.get("folder", "")
    if key == "computers":
        return jsonify(error=READ_ONLY), 403
    root, full, parts = locate(key, request.args.get("path", ""), must_exist=False)
    return jsonify(exists=bool(parts) and os.path.lexists(full))


@app.put("/api/upload")
def upload():
    """The file is the request body, written straight to the card (no copy in /tmp)."""
    key = request.args.get("folder", "")
    if key == "computers":
        return jsonify(error=READ_ONLY), 403
    root = root_of(key)
    parts = clean_parts(request.args.get("path", ""))
    if not parts:
        return jsonify(error="No file name"), 400
    if any(PASSWORD_NAME.match(x.lower()) for x in parts):
        return jsonify(error="Change webui.txt on the Pi itself"), 403
    if key == "settings":
        if len(parts) != 1 or parts[0].lower() not in SETTINGS_FILES:
            return jsonify(error="Only media mode's settings files go in Settings, like radio.txt"), 403
        parts = [parts[0].lower()]                   # the name media mode looks for
    folder = os.path.realpath(os.path.join(root, *parts[:-1])) if len(parts) > 1 else root
    if not inside(root, folder):
        return jsonify(error="Not allowed there"), 403
    if key != "settings" and in_app_folder(os.path.join(folder, parts[-1])):
        return jsonify(error="The Pietato folder stays as it is. Settings files go in Settings."), 403
    size = request.content_length
    if size is not None and size > shutil.disk_usage(root).free - SPARE:
        return jsonify(error="Not enough space on the Pi"), 507
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return jsonify(error="Couldn't make that folder"), 500
    target = os.path.join(folder, parts[-1])
    mode = request.args.get("exists", "rename")
    if key == "settings" and mode == "rename":
        mode = "replace"                            # a second radio.txt would never be read
    if os.path.lexists(target):
        if os.path.isdir(target):
            return jsonify(error="There's a folder with that name"), 409
        if mode == "skip":
            return jsonify(ok=True, skipped=True, name=parts[-1])
        if mode != "replace":
            target = free_name(target)
    tmp = os.path.join(folder, f".{os.path.basename(target)}.{uuid.uuid4().hex[:8]}.part")
    got = 0
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = request.stream.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
        if size is not None and got != size:
            raise OSError("cut short")
        if private(os.path.basename(target)):
            os.chmod(tmp, 0o600)                    # a key or a token: only you can read it
        os.replace(tmp, target)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return jsonify(error="The upload didn't finish"), 400
    try:                                            # keep the file's own date (photos sort by it)
        mtime = int(request.args.get("mtime", "")) / 1000
        if 0 < mtime < time.time() + 86400:
            os.utime(target, (time.time(), mtime))
    except (ValueError, OSError):
        pass
    return jsonify(ok=True, name=os.path.basename(target), path=os.path.relpath(target, root), size=got)


@app.post("/api/delete")
def delete():
    if not request.is_json:                         # JSON only: another site's form can't post here
        abort(415)
    data = request.get_json(silent=True) or {}
    key = data.get("folder", "")
    if key == "computers":
        return jsonify(error=READ_ONLY), 403
    root, full, parts = locate(key, data.get("path", ""))
    if not parts or full == root or full in protected() or holds_app_folder(full) \
            or (key != "settings" and in_app_folder(full)):
        return jsonify(error="That one stays"), 403
    if PASSWORD_NAME.match(os.path.basename(full).lower()):
        return jsonify(error="Change webui.txt on the Pi itself"), 403
    try:
        if os.path.isdir(full):
            if key == "home":
                return jsonify(error="Folders in your home folder stay"), 403
            if key == "settings":
                return jsonify(error="That one stays"), 403
            shutil.rmtree(full)
        else:
            os.remove(full)
    except OSError as ex:
        return jsonify(error=ex.strerror or "Couldn't delete it"), 500
    return jsonify(ok=True)


@app.get("/api/file")
def get_file():
    key = request.args.get("folder", "")
    if key == "computers":
        bad = open_computer(clean_parts(request.args.get("path", "")))
        if bad:
            return bad
    root, full, parts = locate(key, request.args.get("path", ""))
    if not parts or os.path.isdir(full):
        abort(404)
    if private(os.path.basename(full)):
        abort(403)
    ext = os.path.splitext(full)[1].lower()
    download = request.args.get("download") == "1" or ext not in INLINE
    resp = send_file(full, as_attachment=download, download_name=os.path.basename(full),
                     conditional=True)
    if ext in (".txt", ".md"):
        resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@app.get("/api/home/<path:rel>")
def home_file(rel):
    """A file of yours by its place in your home folder, its name last: Play here's (a browser's player, and the game
    emulator, go by how the name ends). The same files as /api/file's home folder."""
    root, full, parts = locate("home", rel)
    if not parts or os.path.isdir(full):
        abort(404)
    if private(os.path.basename(full)):
        abort(403)
    resp = send_file(full, conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


# ---- Play here: a game on your phone or computer, in EmulatorJS (GPL-3.0, emulatorjs.org) -------------------------
# Its files come from npm (each checked against npm's own SHA-512 of it) the first time a game of that kind is played,
# into your home folder, and the page hands them out from there: nothing it runs comes from anywhere else.
EJS_VERSION = "4.2.3"
EJS_DIR = os.path.join(HOME, ".local", "share", "pitato", "emulatorjs", EJS_VERSION)
EJS_NPM = "https://registry.npmjs.org/@emulatorjs/{0}/-/{0}-" + EJS_VERSION + ".tgz"
EJS_SUMS = {    # npm's dist.integrity for each
    "emulatorjs": "7z3qaA4LwyurhuGvdMUDF9xJpEbxC3SNy9+E9tSaOsRo8FCS2QXam/0k/lc9kqHWRFIlLKWahNjPAStyL0rFnw==",
    "core-fceumm": "XX9Vv2N/hzp0TstNMCTSppEs+sg+1lpJpPdSDuRqIO/cwdt7dUcF+WjNX1yQJLRbP5+XwcNHZ6K4BKy8CJpndQ==",
    "core-snes9x": "JTe9Rv9eOuCkgkG4ILwuCZUqNcVI3m9ju1NHTTjridUlFgJSqL4DUqF/vLKN9olCpsqlJFfcCayAOoikJxefwA==",
    "core-gambatte": "Oq3AJL9SKnMsNAmtAP2eN934TQts3NHeaAe0z1BO9Lx/L3xDZKLpxL+XwgcSXIrl4Sx1oXxYEUwD7JjPEQ0DGg==",
    "core-mgba": "daiHzZQKEr+P9fra7j5YoEAXiyYUEtBhFQ8EAV/SeCtrkvqtayU7GQ9LYgoSgzkKSwsbNSskApqGuA9EGARYPA==",
    "core-genesis_plus_gx": "D1e2XA2CPRAjfr0JurpXJgR9dePxl/xHtaE8v1T9BqD9A3DLfobIFWsWU9jCFS4NfUxCvcLdTYdY/We3QzvcTw==",
    "core-smsplus": "93G2pY9HJVl5pImoIQbDhtswVkX9aIgrrihdGTFHqurhisYHl74XCpzmCoMzdB5UMx09nFW12S+n+bLTIuiLrA==",
    "core-pcsx_rearmed": "mMbl/NszCryFI15X5QniOqLNL7YGZ6tLP24gr5y1q2ekFOIbtc39BcVTMDEwRndNGovh2nPoCcMjB+W3fgQCog==",
    "core-mupen64plus_next": "HnnEXbOEpYxD7f2wUJQLxWUpEB0bT2kC56u5s7PLyj/xNI5ckQKka5+ay1QhU2fOv2BuPRwjjhlzmVJmk5e3hw==",
    "core-melonds": "IjsEBNLPPbqU2GSeWEoEkOgAonK3JEyzvoYR3ucgOXu6InzDNdfuA5kP/mMh3d6DwCUbOwfnqGZuZXMTyNE2wA==",
}
EJS_LOADS = ["emulator.js", "nipplejs.js", "shaders.js", "storage.js", "gamepad.js", "GameManager.js",
             "socket.io.min.js", "compression.js"]   # (its loader's order: put together as the emulator.min.js it asks for)
EJS_MOST = 40 << 20                             # bytes of a package, at most (a core's is about 4 MB)
EJS_TYPES = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".wasm": "application/wasm"}
EJS_ONE = threading.Lock()                      # (one fetched at a time)
PLAY_CSP = ("default-src 'self'; script-src 'self' blob: 'unsafe-eval' 'wasm-unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; "
            "connect-src 'self' data: blob:; worker-src 'self' blob:; font-src 'self' data:; "
            "frame-ancestors 'self'; base-uri 'none'; form-action 'none'")   # (the game's page: nothing from elsewhere)


def ejs_fetch(name):
    """One of EmulatorJS's packages from npm, checked: its bytes, or raises ValueError (why not)."""
    req = urllib.request.Request(EJS_NPM.format(name), headers={"User-Agent": "Pietato"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(EJS_MOST + 1)
    except (OSError, ValueError) as ex:
        raise ValueError(f"The Pi couldn't get the emulator ({getattr(ex, 'reason', ex)}). Check its WiFi") from ex
    if len(data) > EJS_MOST or base64.b64encode(hashlib.sha512(data).digest()).decode() != EJS_SUMS[name]:
        raise ValueError("The emulator the Pi got wasn't the one it should be. Try again later")
    return data


def ejs_unpack(data, into, keep):
    """A package's files (keep(name) says where each goes, under into; None: left out), never outside into."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            dest = keep(m.name)
            if dest is None or not m.isfile():
                continue
            parts = [p for p in dest.split("/") if p]
            if not parts or any(p in (".", "..") for p in parts):
                continue
            path = os.path.join(into, *parts)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with tar.extractfile(m) as src, open(path + ".part", "wb") as out:
                shutil.copyfileobj(src, out)
            os.replace(path + ".part", path)


def ejs_ready(core):
    """EmulatorJS and the core a game needs, on the Pi to hand out (fetched the first time): None, or why not."""
    name = "core-" + core
    if name not in EJS_SUMS:
        return "There's no emulator for that here"
    data_dir = os.path.join(EJS_DIR, "data")
    with EJS_ONE:
        try:
            if not os.path.isfile(os.path.join(EJS_DIR, ".emulatorjs")):
                ejs_unpack(ejs_fetch("emulatorjs"), EJS_DIR,
                           lambda n: n[len("package/"):] if n.startswith("package/data/") else None)
                with open(os.path.join(data_dir, "emulator.min.js") + ".part", "wb") as out:
                    for js in EJS_LOADS:              # (its loader asks for this, which npm's copy hasn't got)
                        with open(os.path.join(data_dir, "src", js), "rb") as f:
                            out.write(f.read() + b"\n;\n")
                os.replace(os.path.join(data_dir, "emulator.min.js") + ".part", os.path.join(data_dir, "emulator.min.js"))
                shutil.copyfile(os.path.join(data_dir, "emulator.css"), os.path.join(data_dir, "emulator.min.css"))
                open(os.path.join(EJS_DIR, ".emulatorjs"), "w").close()
            if not os.path.isfile(os.path.join(EJS_DIR, "." + name)):
                ejs_unpack(ejs_fetch(name), os.path.join(data_dir, "cores"),
                           lambda n: n[len("package/"):] if n.startswith("package/") and n.endswith((".data", ".json"))
                           and not n.endswith("package.json") else None)
                open(os.path.join(EJS_DIR, "." + name), "w").close()
        except ValueError as ex:
            return str(ex)
        except (OSError, tarfile.TarError) as ex:
            return f"The Pi couldn't keep the emulator ({getattr(ex, 'strerror', None) or ex})"
    return None


@app.post("/api/ejs")
def ejs_prepare():
    """The emulator for a game, ready to hand out (the game's page asks first)."""
    why = ejs_ready(request.args.get("core", ""))
    return (jsonify(error=why), 502) if why else jsonify(ok=True)


@app.get("/ejs/<path:rel>")
def ejs_file(rel):
    """EmulatorJS's files, as it fetched and checked them (its data folder: /ejs/data/...)."""
    root = os.path.realpath(EJS_DIR)
    parts = [p for p in rel.split("/") if p]
    full = os.path.realpath(os.path.join(root, *parts)) if parts else root
    if any(p.startswith(".") for p in parts) or not inside(root, full) or not os.path.isfile(full):
        abort(404)
    ext = os.path.splitext(full)[1].lower()
    resp = send_file(full, mimetype=EJS_TYPES.get(ext, "application/octet-stream"), conditional=True)
    resp.headers["Cache-Control"] = "public, max-age=604800"
    return resp


@app.get("/play")
def play_page():
    """A game's page (the Screen view puts it where the Pi's screen is): it says what to play in its address."""
    resp = page_file(os.path.join(TOP, "templates", "play.html"))
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Content-Security-Policy"] = PLAY_CSP
    return resp


@app.get("/play.js")
def play_script():
    resp = page_file(os.path.join(TOP, "templates", "play.js"), mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---- the screen: passed on to media mode ---------------------------------------------
def control_key():
    try:
        with open(CONTROL_KEY) as f:
            return f.read().strip()
    except OSError:
        return ""


def ask_pi(method, path, body=None, timeout=10, ctype="application/json", keep=()):
    """(status, bytes, content type) from media mode, or None when it isn't answering. body: JSON,
    or bytes sent as they are (of type ctype). keep: headers of its answer wanted too (then a fourth: them)."""
    conn = http.client.HTTPConnection(*CONTROL, timeout=timeout)
    try:
        data = body if body is None or isinstance(body, bytes) else json.dumps(body).encode()
        headers = {"X-Pitato-Key": control_key()}
        if data:
            headers["Content-Type"] = ctype
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        out = r.status, r.read(), r.getheader("Content-Type") or "application/json"
        return out + ({k: r.getheader(k) for k in keep if r.getheader(k)},) if keep else out
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def pi_reply(got, cache="no-store"):
    if got is None or got[0] == 401:
        return jsonify(error="The Pi's screen isn't answering. Is Pietato running?"), 503
    status, data, ctype = got
    resp = Response(data, status, content_type=ctype)
    resp.headers["Cache-Control"] = cache if status == 200 else "no-store"
    return resp


@app.get("/api/pi/<what>")
def pi_get(what):
    if what not in PI_GET:
        abort(404)
    args = {k: request.args[k][:200] for k in PI_ARGS if k in request.args}
    path = "/" + what + ("?" + urllib.parse.urlencode(args) if args else "")
    if what == "screen":                            # (after=: the next picture, when there is one; and its number)
        try:
            wait = min(max(float(args.get("wait") or 0), 0.0), FRAME_WAIT)
        except ValueError:
            wait = 0.0
        got = ask_pi("GET", path, timeout=(wait if math.isfinite(wait) else 0) + 15, keep=("X-Pitato-Frame",))
        resp = pi_reply(got and got[:3])
        if got and got[0] == 200 and got[3].get("X-Pitato-Frame"):
            resp.headers["X-Pitato-Frame"] = got[3]["X-Pitato-Frame"]
        return resp
    slow = what in ("channels", "radio", "camframe", "computers", "places")   # these ask the internet, a camera or
                                                                               # a computer
    cache = "private, max-age=86400" if what in ("icon", "friendpic") else "no-store"   # (these never change)
    return pi_reply(ask_pi("GET", path, timeout=40 if slow else 10), cache=cache)


@app.post("/api/pi/<what>")
def pi_post(what):
    if what not in PI_POST:
        abort(404)
    if not request.is_json:                         # JSON only: another site's form can't post here
        abort(415)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Bad request"), 400
    if what == "show":                              # a file from the Files list: where it really is
        if data.get("folder") == "computers":
            bad = open_computer(clean_parts(data.get("path", "")))
            if bad:
                return bad
        root, full, parts = locate(data.get("folder", ""), data.get("path", ""))
        if private(os.path.basename(full)):
            abort(403)
        data = {"path": full}
    if what == "settings" and data.get("key") == "picture":   # a picture of yours for the background: where it is
        pic = data.get("value")
        if not isinstance(pic, dict):
            return jsonify(error="Bad request"), 400
        root, full, parts = locate(pic.get("folder", ""), pic.get("path", ""))
        if (not parts or not os.path.isfile(full) or private(os.path.basename(full))
                or os.path.splitext(full)[1].lower() not in KINDS["pictures"]):
            return jsonify(error="That isn't a picture"), 400
        data = dict(data, value=full)
    if what == "friend" and "picture" in data:      # a picture of yours for the bot: where it really is
        pic = data.get("picture")
        if not isinstance(pic, dict):
            return jsonify(error="Bad request"), 400
        root, full, parts = locate(pic.get("folder", ""), pic.get("path", ""))
        if (not parts or not os.path.isfile(full) or private(os.path.basename(full))
                or os.path.splitext(full)[1].lower() not in KINDS["pictures"]):
            return jsonify(error="That isn't a picture"), 400
        data = dict(data, picture=full)
    return pi_reply(ask_pi("POST", "/" + what, data, timeout=60))


# ---- the Draw tab: a drawing for the screen ---------------------------------------------
def keep_drawing(data, name):
    """The drawing as ~/Pictures/Drawings/<name> (one already there: replaced, so a drawing sent again is
    still one picture), or under a new name when there's none: (its name, None) or (None, why not)."""
    root = root_of("pictures")
    folder = os.path.realpath(os.path.join(root, DRAWINGS))
    if not inside(root, folder):
        return None, "Not allowed there"
    name = name or ""
    if not (name == clean_name(name) and name.lower().endswith(".png") and len(name) > 4):
        name = time.strftime("drawing-%Y-%m-%d-%H%M%S.png")
        if os.path.lexists(os.path.join(folder, name)):
            name = os.path.basename(free_name(os.path.join(folder, name)))
    target = os.path.join(folder, name)
    if os.path.isdir(target):
        return None, "There's a folder with that name"
    if len(data) > shutil.disk_usage(root).free - SPARE:
        return None, "Not enough space on the Pi"
    tmp = os.path.join(folder, f".{name}.{uuid.uuid4().hex[:8]}.part")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None, "Couldn't keep it in Pictures"
    return name, None


@app.put("/api/draw")
def draw():
    """The Draw tab's drawing, a PNG (the request's body): ?show=1 puts it on the Pi's screen (media mode
    shows it till B), ?keep=1 keeps it in Pictures/Drawings (&name=: the one it went in last time)."""
    show, keep = request.args.get("show") == "1", request.args.get("keep") == "1"
    if not (show or keep):
        return jsonify(error="Nothing to do"), 400
    size = request.content_length
    if size is None or not 0 < size <= DRAWING_MAX:
        return jsonify(error="That drawing is too big"), 413
    parts, got = [], 0
    while got < size:
        part = request.stream.read(min(CHUNK, size - got))
        if not part:
            break
        parts.append(part)
        got += len(part)
    data = b"".join(parts)
    if len(data) != size or not data.startswith(PNG):
        return jsonify(error="That isn't a drawing"), 400
    out = {"ok": True}
    if keep:
        name, why = keep_drawing(data, request.args.get("name"))
        if not name:
            return jsonify(error=why), 507 if why.startswith("Not enough") else 500
        out.update(name=name, path=DRAWINGS + "/" + name)
    if show:
        answer = ask_pi("POST", "/sketch", data, timeout=30, ctype="image/png")
        if answer is None or answer[0] == 401:
            out.update(ok=False, error="The Pi's screen isn't answering. Is Pietato running?")
            return jsonify(out), 503
        try:
            said = json.loads(answer[1])
        except ValueError:
            said = None
        if answer[0] != 200 or not isinstance(said, dict) or said.get("error"):
            why = said.get("error") if isinstance(said, dict) else None
            out.update(ok=False, error=why or "The Pi couldn't show it")
            return jsonify(out), answer[0] if answer[0] != 200 else 409
    return jsonify(out)


# ---- the Bot at work: your coding agent, acted out --------------------------------------
def coder_reply(got):
    """Media mode's answer, passed on."""
    if got is None or got[0] == 401:
        return jsonify(ok=False, error="Pietato isn't answering"), 503
    status, data, _ = got
    return Response(data, status, content_type="application/json")


@app.route("/coder", methods=["GET", "POST"])
def coder():
    """What the Bot is doing at work (GET), or what it does now (POST ?pose=typing)."""
    if request.method == "GET":
        return coder_reply(ask_pi("GET", "/coder", timeout=5))
    pose = request.args.get("pose")
    if pose not in CODER:
        return jsonify(ok=False, error="pose is one of: " + ", ".join(CODER)), 400
    return coder_reply(ask_pi("POST", "/coder", {"pose": pose}, timeout=5))


@app.post("/coder/say")
def coder_say():
    """A WAV for the Bot to say at work (16-bit PCM), in a pose (?pose=thinking; talking if not
    given): answered once it has been said."""
    pose = request.args.get("pose") or "talking"
    if pose not in CODER_SAY_AS:
        return jsonify(ok=False, error="a clip is said " + ", ".join(CODER_SAY_AS)), 400
    if (request.content_length or 0) > CLIP_MAX:
        return jsonify(ok=False, error="clip too big (8 MB at most)"), 413
    if not CLIP_TURN.acquire(timeout=600):
        return jsonify(ok=False, error="still saying the clips before this one"), 503
    try:
        parts, got = [], 0
        while got <= CLIP_MAX:
            part = request.stream.read(min(CHUNK, CLIP_MAX + 1 - got))
            if not part:
                break
            parts.append(part)
            got += len(part)
        if got > CLIP_MAX:
            return jsonify(ok=False, error="clip too big (8 MB at most)"), 413
        data = b"".join(parts)
        # (a clip says how long it is; this is long enough for the slowest one there could be)
        return coder_reply(ask_pi("POST", "/coder/say?pose=" + pose, data, timeout=len(data) / 16000 + 30,
                                  ctype="audio/wav"))
    finally:
        CLIP_TURN.release()


def hook_report(raw, size):
    """What a Claude Code hook reported: all of it when it's small, or the few things needed, picked
    out of the start of a big one (a large file being written)."""
    if size <= 1 << 20:
        try:
            event = json.loads(raw)
            return event if isinstance(event, dict) else {}
        except ValueError:
            return {}
    event = {}
    for key in ("hook_event_name", "tool_name"):
        m = re.search(rb'"' + key.encode() + rb'"\s*:\s*"([A-Za-z0-9_.:-]{1,100})"', raw[:65536])
        if m:
            event[key] = m.group(1).decode()
    return event


def hook_pose(event):
    """The pose for what Claude Code says it's doing (None: nothing to show)."""
    what, tool = event.get("hook_event_name"), str(event.get("tool_name") or "")
    if what == "SessionStart":
        return "hello" if event.get("source") == "startup" else "wake"
    if what == "SessionEnd":
        return None if event.get("reason") in ("clear", "resume") else "sleep"   # (a new one starts at once)
    if what in ("UserPromptSubmit", "PostToolBatch", "PreCompact"):
        return "thinking"
    if what == "PreToolUse":
        return "reading" if tool in HOOK_READS else "thinking" if tool in HOOK_HELPERS else "typing"
    if what in ("PermissionRequest", "Notification"):
        return "attention"
    if what == "PermissionDenied":
        return "shrug"
    if what in ("PostToolUseFailure", "StopFailure"):
        return "error"
    if what == "Stop":
        return "done"
    return None


@app.post("/coder/hook")
def coder_hook():
    """Claude Code's hooks (coder_hooks.py sets them up): the report each one sends, turned into a
    pose. Answered with nothing at all, so Claude Code has nothing to read."""
    keep, size = [], 0
    while size <= HOOK_MAX:
        part = request.stream.read(CHUNK)
        if not part:
            break
        size += len(part)
        if size <= 1 << 20 or not keep:
            keep.append(part)
    pose = hook_pose(hook_report(b"".join(keep), size))
    if pose:
        got = ask_pi("POST", "/coder", {"pose": pose}, timeout=5)
        if got is None or got[0] != 200:
            return Response(status=503)
    return Response(status=204)


@app.post("/coder/prompts")
def coder_prompts():
    """Prompts typed on the Pi for your coding agent: coder_hooks.py --channel asks for them, and this
    waits a while for one (?wait=20, in seconds). ?got= is the last one it got, from ?run= (the Pi's
    run it came from), so one handed out that never got there goes out again."""
    try:
        wait, got = float(request.args.get("wait") or 0), int(request.args.get("got") or 0)
    except ValueError:
        return jsonify(ok=False, error="wait is seconds, got is a prompt's number"), 400
    wait = min(max(wait, 0.0), 20.0) if math.isfinite(wait) else 0.0
    run = re.sub(r"[^0-9a-f]", "", request.args.get("run") or "")[:16]
    query = urllib.parse.urlencode({"wait": wait, "got": got, "run": run})
    return coder_reply(ask_pi("POST", "/coder/prompts?" + query, b"", timeout=wait + 10))


@app.get("/coder_hooks.py")
def coder_hooks():
    """The script that connects Claude Code to the Bot at work, for the computer it runs on (setup.sh
    puts it next to this one)."""
    path = os.path.join(HERE, "coder_hooks.py")
    if not os.path.isfile(path):
        return Response("coder_hooks.py isn't here: run sudo bash setup.sh again", 404, content_type="text/plain")
    return send_file(path, mimetype="text/x-python", as_attachment=True, download_name="coder_hooks.py")


# ---- small pictures for the list ------------------------------------------------------
def prune_thumbs(keep=3000):
    """The cache keeps the newest few thousand."""
    try:
        with os.scandir(THUMBS) as it:
            found = [(e.stat().st_mtime, e.path) for e in it if e.name.endswith(".jpg")]
    except OSError:
        return
    for _, path in sorted(found)[:max(0, len(found) - keep)]:
        try:
            os.remove(path)
        except OSError:
            pass


THUMB_ONE = threading.Lock()
THUMB_PIXELS = 30_000_000       # bigger pictures (besides JPEGs, which shrink as they load) keep their icon
WEBP_PIXELS = 4_000_000         # WebP decodes with a lot more memory


def make_thumb(full, out):
    try:
        from PIL import Image, ImageOps
        with Image.open(full) as im:
            im.draft("RGB", (480, 480))                 # JPEGs decode at a fraction of the size
            if im.width * im.height > (WEBP_PIXELS if im.format == "WEBP" else THUMB_PIXELS):
                return False
            im.thumbnail((240, 240))
            small = ImageOps.exif_transpose(im).convert("RGB")
        os.makedirs(THUMBS, exist_ok=True)
        tmp = out + f".{uuid.uuid4().hex[:6]}.part"
        small.save(tmp, "JPEG", quality=82)
        os.replace(tmp, out)
        return True
    except Exception:
        return False


@app.get("/api/thumb")
def thumb():
    if request.args.get("folder") == "computers":
        bad = open_computer(clean_parts(request.args.get("path", "")))
        if bad:
            abort(404)
    root, full, parts = locate(request.args.get("folder", ""), request.args.get("path", ""))
    if (not parts or os.path.isdir(full) or private(os.path.basename(full))
            or os.path.splitext(full)[1].lower() not in KINDS["pictures"]):
        abort(404)
    st = os.stat(full)
    out = os.path.join(THUMBS, hashlib.sha1(f"{full}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest() + ".jpg")
    if not os.path.exists(out):
        with THUMB_ONE:                                 # one at a time: a Pi Zero has 512 MB
            if not os.path.exists(out) and not make_thumb(full, out):
                abort(404)
        prune_thumbs()
    resp = send_file(out, mimetype="image/jpeg", conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


# ---- Sound here and Mic here: the Pi's sound on your phone or computer, and its microphone the Pi's ---------------
# Both go through the Loopback card (snd-aloop: setup.sh adds it). Media mode plays into it while a page listens
# (pietato_web, mixed), and this hands each page what comes out; a page's microphone is played into it here, and the
# bot listens at its other side. Media mode is told every few seconds that a page is still there.
LOOPBACK = "/proc/asound/Loopback"
SOUND_FROM = "hw:Loopback,1,0"                  # the Pi's sound, out of the card
MIC_TO = "hw:Loopback,0,1"                      # a page's microphone, into it (the bot hears it at 1,1)
SOUND_RATE, SOUND_CHUNK = 48000, 3840           # two 16-bit channels at 48 kHz: 20 ms a chunk
MIC_RATE, MIC_MOST = 16000, 64 << 10            # one 16-bit channel at 16 kHz (the bot's ears' own); bytes a request
SAY_EVERY = 5.0                                 # seconds between telling media mode a page is still there
SOUND_HEARD = 6.0                               # seconds without a page saying it's playing the sound (a phone that
                                                # locked, say) before the Pi plays it itself again
MIC_QUIET = 3.0                                 # seconds without a page's microphone before it's let go
NO_LOOPBACK = "Run sudo bash setup.sh again on the Pi to add this"


def tell_pi(what, on):
    """Media mode told Sound here (or Mic here) is on or off: its answer, or {} when it isn't answering."""
    got = ask_pi("POST", "/" + what, {"on": on}, timeout=5)
    try:
        return json.loads(got[1]) if got and got[0] == 200 else {}
    except ValueError:
        return {}


class SoundOut:
    """arecord on the Loopback card while a page listens, every chunk to every page listening (one that falls behind
    loses the oldest)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.pages = set()
        self.proc = None
        self.heard = 0.0                             # when a page last said it's playing what it gets

    def playing(self):
        self.heard = time.monotonic()

    def join(self):
        q = queue.Queue(maxsize=50)                  # (a second)
        with self.lock:
            self.heard = time.monotonic()            # (a page that's only just come: a moment to start playing)
            self.pages.add(q)
            if self.proc is None:
                try:
                    self.proc = subprocess.Popen(["arecord", "-q", "-D", SOUND_FROM, "-f", "S16_LE", "-r", str(SOUND_RATE),
                                                  "-c", "2", "-t", "raw"], stdout=subprocess.PIPE,
                                                 stderr=subprocess.DEVNULL)
                except OSError:
                    self.pages.discard(q)
                    return None
                threading.Thread(target=self.read, args=(self.proc,), daemon=True, name="sound").start()
                threading.Thread(target=self.say, args=(self.proc,), daemon=True, name="sound-on").start()
        return q

    def leave(self, q):
        with self.lock:
            self.pages.discard(q)
            proc = self.proc if not self.pages else None
            if proc is not None:
                self.proc = None
        if proc is not None:
            proc.terminate()

    def read(self, proc):
        while True:
            chunk = proc.stdout.read(SOUND_CHUNK)
            with self.lock:
                pages = list(self.pages) if self.proc is proc else []
            for q in pages:
                while True:
                    try:
                        q.put_nowait(chunk or None)     # (None: it stopped)
                        break
                    except queue.Full:
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
            if not chunk:
                break
        with self.lock:
            if self.proc is proc:                      # (it stopped by itself: the next page starts another)
                self.proc = None
        proc.wait()

    def say(self, proc):
        told, at = None, 0.0
        while self.proc is proc and proc.poll() is None:
            on = time.monotonic() - self.heard < SOUND_HEARD
            if on != told or time.monotonic() - at >= SAY_EVERY:
                tell_pi("websound", on)                # (off while no page is playing it: the Pi plays it)
                told, at = on, time.monotonic()
            time.sleep(0.25)
        if self.proc is None:                          # (not if another page started listening meanwhile)
            tell_pi("websound", False)


class MicIn:
    """aplay into the Loopback card while a page sends its microphone; let go a few seconds after the last of it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.last = 0.0
        self.listens = True                            # (whether the bot's listening at all, as media mode last said)
        self.why = ""                                  # ...and if it isn't, why not

    def put(self, data):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                try:
                    self.proc = subprocess.Popen(["aplay", "-q", "-D", MIC_TO, "-f", "S16_LE", "-r", str(MIC_RATE), "-c",
                                                  "1", "-t", "raw"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                except OSError:
                    self.proc = None
                    return False
                self.listens, self.why = True, ""      # (a new one: what media mode says about it, not about the last)
                threading.Thread(target=self.watch, args=(self.proc,), daemon=True, name="mic").start()
            self.last = time.monotonic()
            proc = self.proc
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def watch(self, proc):
        said = 0.0
        while True:
            now = time.monotonic()
            with self.lock:
                gone = now - self.last > MIC_QUIET or proc.poll() is not None
                if gone and self.proc is proc:
                    self.proc = None
            if gone:
                break
            if now - said >= SAY_EVERY:
                said = now
                answer = tell_pi("webmic", True)
                self.listens, self.why = answer.get("listens", True), str(answer.get("why") or "")[:200]
            time.sleep(0.25)
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.terminate()
        tell_pi("webmic", False)


SOUND, MIC = SoundOut(), MicIn()


@app.get("/api/sound")
def sound_out():
    """The Pi's sound, as it plays (raw: two 16-bit channels at 48 kHz), while the page wants it."""
    if not os.path.isdir(LOOPBACK):
        return jsonify(error=NO_LOOPBACK), 503
    q = SOUND.join()
    if q is None:
        return jsonify(error="The Pi couldn't start sending its sound"), 503

    def chunks():
        try:
            while True:
                chunk = q.get(timeout=10)
                if chunk is None:
                    break
                yield chunk
        except queue.Empty:
            pass
        finally:
            SOUND.leave(q)
    return Response(chunks(), mimetype="application/octet-stream",
                    headers={"Cache-Control": "no-store", "X-Pitato-Rate": str(SOUND_RATE)})


@app.post("/api/sound")
def sound_playing():
    """A page playing the Pi's sound says so every couple of seconds (one that's stopped, a phone that locked, doesn't:
    then the Pi plays it again)."""
    SOUND.playing()
    return jsonify(ok=True)


@app.post("/api/mic")
def mic_in():
    """A moment of the page's microphone (raw: one 16-bit channel at 16 kHz), for the bot to hear."""
    if not os.path.isdir(LOOPBACK):
        return jsonify(error=NO_LOOPBACK), 503
    if (request.content_length or 0) > MIC_MOST:
        return jsonify(error="Too big"), 413
    data = request.get_data()
    if len(data) % 2:
        data = data[:-1]
    if not MIC.put(data):
        return jsonify(error="The Pi couldn't take the microphone"), 503
    return jsonify(ok=True, listens=MIC.listens, **({"why": MIC.why} if MIC.why and not MIC.listens else {}))


# ---- the secure page: the same page, over HTTPS, for what a browser only allows there (a microphone) ---------------
SECURE_PORT = 5443
SECURE_HELLO = 20.0                                    # seconds a browser has to begin a secure connection
CERT_DIR = os.path.join(HOME, ".local", "share", "pitato", "web-cert")


def addresses():
    """This Pi's addresses on your network."""
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        out = []
    good = []
    for a in out:
        try:
            if not ipaddress.ip_address(a).is_loopback:
                good.append(a)
        except ValueError:
            pass
    return good[:6]


def certificate():
    """The Pi's own certificate for the secure page, made once with openssl (good for ten years): (its file, its key's
    file), or None. Browsers warn about one a Pi made itself the first time: then they let you on."""
    cert, key = os.path.join(CERT_DIR, "cert.pem"), os.path.join(CERT_DIR, "key.pem")
    if os.path.isfile(cert) and os.path.isfile(key):
        return cert, key
    name = re.sub(r"[^A-Za-z0-9-]", "", socket.gethostname()) or "pietato"
    alt = ",".join([f"DNS:{name}.local", f"DNS:{name}", "DNS:localhost"] + [f"IP:{a}" for a in addresses()])
    try:
        os.makedirs(CERT_DIR, mode=0o700, exist_ok=True)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650", "-keyout",
                        key + ".part", "-out", cert + ".part", "-subj", f"/CN={name}.local", "-addext",
                        "subjectAltName=" + alt], capture_output=True, timeout=120, check=True)
        os.chmod(key + ".part", 0o600)
        os.replace(key + ".part", key)
        os.replace(cert + ".part", cert)
    except (OSError, subprocess.SubprocessError) as ex:
        print(f"the secure page: no certificate ({ex})", flush=True)
        return None
    return cert, key


def serve_secure():
    """The same page over HTTPS too (SECURE_PORT), alongside the usual one."""
    pair = certificate()
    if not pair:
        return
    from werkzeug.serving import make_server, WSGIRequestHandler

    class Handler(WSGIRequestHandler):
        def handle(self):
            # Each secure connection is begun on its own, here: a phone that went away halfway would otherwise hold
            # up everyone else's, for good. One that doesn't start in a while is let go.
            try:
                self.connection.settimeout(SECURE_HELLO)
                self.connection.do_handshake()
                self.connection.settimeout(None)
            except (OSError, ValueError):
                return
            super().handle()

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*pair)
        server = make_server("0.0.0.0", SECURE_PORT, app, threaded=True, request_handler=Handler)
        server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        server.ssl_context = ctx                       # (so its requests are https ones)
    except (OSError, ssl.SSLError) as ex:
        print(f"the secure page: {ex}", flush=True)
        return
    server.serve_forever()


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)    # keep the journal quiet
    threading.Thread(target=serve_secure, daemon=True, name="secure").start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
