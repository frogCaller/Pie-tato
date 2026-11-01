"""Achievements, from RetroAchievements (retroachievements.org): your account, signed in to on the web page (a key it
gives kept in static/retroachievements.txt, not your password), and which games can have them. The games' own,
while they play, are in the game's process (pitato/emulator.py, through rcheevos: pitato/rcheevos.py)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .config import edit_config, read_config, settings_glob

RA_HOST = "https://retroachievements.org"
RA_FILE = "retroachievements.txt"
RA_APP = "Pietato/1.1"               # how it introduces itself to RetroAchievements (rcheevos's own part after it)
CHEEVO_CONSOLES = {"gb": 4, "gbc": 6, "gba": 5, "nes": 7, "snes": 3, "genesis": 1, "sms": 11, "gg": 15,
                   "ngp": 14, "ngpc": 14, "neogeo": 27, "ps1": 12, "n64": 2, "psp": 41, "nds": 18, "dc": 40,
                   "ps2": 21, "gc": 16}   # each system's number at RetroAchievements (Neo Geo: its arcade games')


class LoginError(Exception):
    """RetroAchievements didn't take that user and password (its words)."""


def ra_host():
    return os.environ.get("PITATO_RA_HOST", "").rstrip("/") or RA_HOST   # (the tests: a pretend one)


def ra_account():
    """(user, token): signed in on the web page. None: not."""
    cfg = read_config([settings_glob(RA_FILE)])
    user, token = cfg.get("user", "").strip(), cfg.get("token", "").strip()
    return (user, token) if user and token else None


def ra_save(user, token):
    edit_config(RA_FILE, {"user": user, "token": token}, private=True,
                head="# RetroAchievements: your user, and the key it gave for this Pi (not your password). Keep it "
                     "private.\n")


def ra_forget():
    edit_config(RA_FILE, {"user": "", "token": ""}, private=True)


def ra_login(user, password, timeout=20):
    """Signs in to RetroAchievements: (your user as it has it, its key for this Pi). LoginError: it said no;
    OSError: it couldn't be reached."""
    body = urllib.parse.urlencode({"r": "login2", "u": user, "p": password}).encode()
    req = urllib.request.Request(ra_host() + "/dorequest.php", data=body, method="POST",
                                 headers={"User-Agent": RA_APP,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(1 << 16)
    except urllib.error.HTTPError as ex:              # (no, with its reason: 401 and the same JSON)
        data = ex.read(1 << 16)
    try:
        said = json.loads(data.decode("utf-8", "replace"))
    except ValueError as ex:
        raise OSError("RetroAchievements answered strangely") from ex
    if not isinstance(said, dict) or not said.get("Success") or not said.get("Token"):
        raise LoginError(str((said or {}).get("Error") or "It didn't take that user and password")
                         if isinstance(said, dict) else "It didn't take that user and password")
    return str(said.get("User") or user), str(said["Token"])
