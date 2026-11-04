"""What you're playing, sent to another of your Pietatos (Settings > Share with other Pietatos): a game carries on
there from the same moment (its saves go with it, savesync.py), and a video, a song or a station carries on at the
same place. This one asks the other whether it can, then sends it; the other picks it up. A file of yours it hasn't
got (a game, or the video or song itself) it takes from this one's web page, with a key that opens just that file,
for a while. (Media mode's part: pitato/screens/handoff.py; the web page's: /api/handoff and /api/handoff/file.)"""
import os
import re
import secrets
import threading
import time

from .savesync import fetch_file, file_sum, game_name

HANDOFF_ASK = 4.0             # seconds the other one has to say whether it can
HANDOFF_GO = 10.0             # ...and to say it's taking it
GAME_COPY_MOST = 64 << 20     # bytes: a game it hasn't got is copied over if it's no bigger (a cartridge's, not a disc's)
GAME_COPY_TIME = 300.0        # seconds a game's copy may take
TOKEN_SECS = 6 * 3600         # a file's key opens it for this long (a film, and then some)
TOKEN = re.compile(r"[A-Za-z0-9_-]{20,64}")
SYSTEM = re.compile(r"[a-z0-9]{1,12}")
SUM = re.compile(r"[0-9a-f]{40}")
MEDIA_KINDS = ("video", "audio", "radio", "live")
TITLE_MOST = 200
REL_MOST = 300
POS_MOST = 7 * 24 * 3600


class Tokens:
    """Keys to this Pi's files, for another of your Pietatos: each opens one file, for a while."""

    def __init__(self):
        self.lock = threading.Lock()
        self.keys = {}

    def issue(self, path, secs=TOKEN_SECS):
        key = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self.lock:
            self.keys = {k: v for k, v in self.keys.items() if v[1] > now}   # (the old ones go)
            self.keys[key] = (os.path.abspath(path), now + secs)
        return key

    def path(self, key):
        """The file a key opens (while it's good, and the file's there), or None."""
        if not isinstance(key, str) or not TOKEN.fullmatch(key):
            return None
        with self.lock:
            got = self.keys.get(key)
        if got is None or got[1] < time.monotonic() or not os.path.isfile(got[0]):
            return None
        return got[0]


def game_ident(path, games, system, title, name):
    """A game, as another Pietato is told of it: its console, where it is in the Games folder, its saves' name, its
    title, and its size (and its sum, for one small enough to be copied over)."""
    games, path = os.path.abspath(games), os.path.abspath(path)
    rel = os.path.relpath(path, games) if path.startswith(games + os.sep) else os.path.basename(path)
    size = os.path.getsize(path)
    return {"system": system, "rel": rel, "name": name, "title": title, "size": size,
            "sum": file_sum(path) if size <= GAME_COPY_MOST else ""}


def clean_rel(rel):
    """A place in the Games folder, from another machine: a plain relative path, or None."""
    if not isinstance(rel, str) or not 0 < len(rel) <= REL_MOST or "\0" in rel or "\\" in rel:
        return None
    parts = rel.split("/")
    if rel.startswith("/") or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    return rel


def clean_ident(d):
    """Another Pietato's word for a game: only as much of it as makes sense, or None."""
    if not isinstance(d, dict):
        return None
    system, rel, name = d.get("system"), clean_rel(d.get("rel")), game_name(d.get("name"))
    title, size, sm = d.get("title"), d.get("size"), d.get("sum") or ""
    if (not isinstance(system, str) or not SYSTEM.fullmatch(system) or rel is None or name is None
            or not isinstance(title, str) or not title.strip() or isinstance(size, bool) or not isinstance(size, int)
            or not 0 <= size < 1 << 40 or not isinstance(sm, str) or (sm and not SUM.fullmatch(sm))):
        return None
    return {"system": system, "rel": rel, "name": name, "title": title.strip()[:TITLE_MOST], "size": size, "sum": sm}


def same_game(path, ident):
    """This file is that game: the same size (and sum, when it's said)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) != ident["size"]:
            return False
        return not ident["sum"] or file_sum(path) == ident["sum"]
    except OSError:
        return False


def local_game(games, ident, others=(), name_of=None):
    """This Pi's copy of the game: at the same place in its Games folder, or among others (its games' paths) by the
    same name for its saves, the same size and sum. Its path, or None."""
    here = os.path.join(games, ident["rel"])
    if same_game(here, ident):
        return here
    for path in others:
        if name_of is not None and name_of(path) != ident["name"]:
            continue
        if same_game(path, ident):
            return path
    return None


def copy_place(games, ident):
    """Where a game copied over goes: the same place as on the other one (its saves' name goes with the file's), or
    None when a different game is there already."""
    dest = os.path.join(games, ident["rel"])
    if os.path.lexists(dest):
        return None
    return dest


def copy_game(url, dest, ident, owner=None):
    """A game, from another of your Pietatos' web page, into dest (whole, its sum checked, or not at all)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + ".part")
    try:
        if not fetch_file(url, part, ident["size"], timeout=GAME_COPY_TIME):
            raise OSError("it didn't come whole")
        if ident["sum"] and file_sum(part) != ident["sum"]:
            raise OSError("it didn't come whole")
        os.replace(part, dest)
        if owner:
            os.chown(dest, *owner)
            os.chown(os.path.dirname(dest), *owner)
    finally:
        try:
            os.remove(part)
        except OSError:
            pass


def clean_media(d):
    """Another Pietato's word for what it's playing: (kind, title, src, pos) or None. src: an address it plays from
    (the internet's, or its own web page's for a file of its own)."""
    if not isinstance(d, dict):
        return None
    kind, title, src, pos = d.get("media"), d.get("title"), d.get("src"), d.get("pos", 0)
    if (kind not in MEDIA_KINDS or not isinstance(title, str) or not title.strip() or not isinstance(src, str)
            or not 0 < len(src) <= 4000 or "\n" in src or "\0" in src
            or not (src.startswith(("http://", "https://")) or (src.startswith("ia:") and "/" in src))
            or isinstance(pos, bool) or not isinstance(pos, (int, float)) or not 0 <= pos <= POS_MOST):
        return None
    return kind, title.strip()[:TITLE_MOST], src, float(pos)
