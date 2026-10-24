"""Jellyfin: your own server's films and shows. The server is found on your network by itself (or its address is
in jellyfin.txt), you sign in with a Quick Connect code (or a user and password in jellyfin.txt), and a video is
streamed at a size the Pi plays smoothly, from where you left off."""
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import clean_name, read_config, settings_glob
from .screen import video_target


JELLYFIN_FILE = "/var/lib/pitato/jellyfin.json"   # the server and the sign-in (readable by root only)
JF_CLIENT, JF_VERSION = "Pitato", "1.0"     # what Jellyfin's list of devices calls it
JF_BROADCAST, JF_DISCOVERY = "255.255.255.255", 7359  # where Jellyfin servers answer "who is JellyfinServer?"
JF_PORT = 8096                  # a server's own port, when its address doesn't say
TICKS = 10_000_000              # Jellyfin counts time in ticks of 100 nanoseconds
JF_LIBRARIES = ("movies", "tvshows", "homevideos", "musicvideos", "boxsets", "folders", "")   # not music, books...
JF_FIELDS = "ChildCount,RecursiveItemCount"
JF_QUICK_SECS = 9 * 60          # how long a Quick Connect code is shown (the server keeps it 10 minutes)


def server_addresses(text):
    """Where a server may be, from its address as you'd type it or copy it from your browser: 192.168.1.20,
    jellyfin.local:8096, http://192.168.1.20:8096/web/#/home.html... Without a port, Jellyfin's own (8096) is
    tried as well as the usual one."""
    text = (text or "").strip()
    if not text:
        return []
    typed = "://" in text
    try:
        u = urllib.parse.urlsplit(text if typed else "http://" + text)
        port = u.port
    except ValueError:
        return []
    host = u.hostname or ""
    if u.scheme not in ("http", "https") or not host or any(c in host for c in " \"'<>\\"):
        return []
    host = f"[{host}]" if ":" in host else host
    path = re.split(r"/web(?:/|$)", u.path, maxsplit=1)[0].rstrip("/")     # (the web app's page: not the server)
    if port:
        out = [f"{u.scheme}://{host}:{port}{path}"]
    elif typed:
        out = [f"{u.scheme}://{host}{path}"] + ([f"http://{host}:{JF_PORT}{path}"] if u.scheme == "http" else [])
    else:
        out = [f"http://{host}:{JF_PORT}{path}", f"http://{host}{path}"]
    return list(dict.fromkeys(out))


def discover(timeout=2.0):
    """Jellyfin servers on your network, each once, in the order they answered: [{"Id", "Name", "Address",
    "From"}] ("From": where the answer came from, for a server that gives an address it can't be reached at)."""
    found, seen = [], set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return found
    with sock:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(b"who is JellyfinServer?", (JF_BROADCAST, JF_DISCOVERY))
        except OSError:
            return found
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                data, sender = sock.recvfrom(65535)
            except OSError:                            # (the time's up, or the network's gone)
                break
            try:
                info = json.loads(data)
            except ValueError:
                continue
            if (isinstance(info, dict) and isinstance(info.get("Id"), str) and isinstance(info.get("Address"), str)
                    and info["Id"] not in seen):
                seen.add(info["Id"])
                found.append({"Id": info["Id"], "Name": str(info.get("Name") or ""), "Address": info["Address"],
                              "From": sender[0]})
    return found


class Jellyfin:
    """Your Jellyfin server: finding it, signing in, browsing and streaming. Its calls for playing a video are the
    ones the Plex player makes (stream_url, timeline, scrobble, stop_transcode), so a Jellyfin video plays as a
    Plex one does."""

    def __init__(self):
        self.cfg = {}
        self.manual = {}
        self.quick = None            # a Quick Connect code to type in Jellyfin: {"secret", "code", "until"}
        self.playing = {}            # item -> {"session", "started"}: what the server's been told is playing
        self.lock = threading.Lock()
        self.load()

    # -- kept -------------------------------------------------------------------------------------------------------
    def load(self):
        """The saved server and sign-in, and jellyfin.txt (read again each time you sign in)."""
        try:
            with open(JELLYFIN_FILE) as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        self.cfg = cfg if isinstance(cfg, dict) else {}
        changed = False
        if not self.cfg.get("device"):
            self.cfg["device"] = uuid.uuid4().hex
            changed = True
        self.manual = read_config([settings_glob("jellyfin.txt")])     # optional: server, user, password
        typed = self.manual.get("server", "")
        if typed and typed != self.cfg.get("typed"):    # another server named there: that one, signed in afresh
            self.cfg = {"device": self.cfg["device"], "typed": typed}
            changed = True
        user = self.manual.get("user", "")
        if user and self.cfg.get("login") and user != self.cfg["login"]:     # someone else named there
            self.drop_sign_in()
            changed = True
        if changed:
            self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(JELLYFIN_FILE), exist_ok=True)
            tmp = JELLYFIN_FILE + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.cfg, f)
            os.replace(tmp, JELLYFIN_FILE)
        except OSError:
            pass

    def drop_sign_in(self):
        for k in ("token", "user", "user_name", "login"):
            self.cfg.pop(k, None)
        self.quick = None

    def forget(self):
        """Signed out here (the server no longer takes the sign-in, say)."""
        self.drop_sign_in()
        self.save()

    @property
    def ready(self):
        return bool(self.cfg.get("server") and self.cfg.get("token") and self.cfg.get("user"))

    @property
    def server(self):
        return self.cfg.get("server", "")

    @property
    def server_name(self):
        return self.cfg.get("server_name") or "Jellyfin"

    @property
    def uid(self):
        return self.cfg.get("user", "")

    # -- talking to it ----------------------------------------------------------------------------------------------
    def headers(self, token=None):
        parts = [("Client", JF_CLIENT), ("Device", socket.gethostname() or "Raspberry Pi"),
                 ("DeviceId", self.cfg["device"]), ("Version", JF_VERSION)]
        token = token or self.cfg.get("token")
        if token:
            parts.append(("Token", token))
        auth = ", ".join(f'{k}="{urllib.parse.quote(v, safe=" ")}"' for k, v in parts)
        return {"Accept": "application/json", "Authorization": "MediaBrowser " + auth}

    def call(self, path, method="GET", body=None, timeout=10, raw=False, server=None, token=None, **params):
        url = (server or self.server) + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        h = self.headers(token)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        elif method == "POST":
            data = b""                                 # (a length of nothing: some proxies want one)
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read()
        if raw:
            return out
        return json.loads(out) if out.strip() else {}

    def get(self, paths, **params):
        """The first of these the server has: a newer server's way first, then an older one's."""
        for k, path in enumerate(paths):
            try:
                return self.call(path, **params)
            except urllib.error.HTTPError as ex:
                if ex.code != 404 or k == len(paths) - 1:
                    raise
        return {}

    def quiet(self, path, method="POST", body=None, **params):
        try:
            self.call(path, method=method, body=body, timeout=6, raw=True, **params)
            return True
        except Exception:
            return False

    # -- finding it -------------------------------------------------------------------------------------------------
    def use_server(self, text, same=False):
        """The first of a server's addresses that answers as a Jellyfin server, kept (with the sign-in, if it's the
        server signed in to; same: only that one). True if there's one."""
        for address in server_addresses(text):
            try:
                req = urllib.request.Request(address + "/System/Info/Public", headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    info = json.loads(r.read() or b"{}")
                    final = r.geturl()
            except (OSError, ValueError):
                continue
            if not (isinstance(info, dict) and isinstance(info.get("Id"), str) and info["Id"]):
                continue
            mine = info["Id"] == self.cfg.get("server_id")
            if same and not mine:
                continue
            if final.endswith("/System/Info/Public"):  # (sent on to https, say: that address from now on)
                address = final[:-len("/System/Info/Public")]
            base = self.cfg if mine else {"device": self.cfg["device"], "typed": self.cfg.get("typed", "")}
            self.cfg = dict(base, server=address, server_id=info["Id"],
                            server_name=clean_name(info.get("ServerName"), 30) or "Jellyfin")
            self.save()
            return True
        return False

    def find_server(self, same=False):
        """The server named in jellyfin.txt, or else the one used before, or the first that answers on your network
        (same: only the one signed in to, found again at a new address). True if there's one."""
        typed = self.manual.get("server", "")
        if typed:
            return self.use_server(typed, same)
        if self.server and self.use_server(self.server, same):
            return True
        found = discover()
        found.sort(key=lambda f: f["Id"] != self.cfg.get("server_id"))          # the one signed in to first
        for info in found:
            if self.use_server(info["Address"], same):
                return True
            try:
                port = urllib.parse.urlsplit(info["Address"]).port or JF_PORT
            except ValueError:
                port = JF_PORT
            if self.use_server(f"http://{info['From']}:{port}", same):     # (a server in Docker, say)
                return True
        return False

    # -- signing in -------------------------------------------------------------------------------------------------
    def can_use_password(self):
        """A user in jellyfin.txt, with the server it's for: a password only goes to a server you named."""
        return bool(self.manual.get("user") and self.manual.get("server"))

    def sign_in_with_password(self):
        user = self.manual.get("user", "")
        r = self.call("/Users/AuthenticateByName", method="POST",
                      body={"Username": user, "Pw": self.manual.get("password", "")})
        if not self.signed(r):
            return False
        self.cfg["login"] = user
        self.save()
        return True

    def quick_on(self):
        try:
            return self.call("/QuickConnect/Enabled", timeout=6) is True
        except urllib.error.HTTPError:
            return False

    def start_quick(self):
        try:
            r = self.call("/QuickConnect/Initiate", method="POST")
        except urllib.error.HTTPError as ex:
            if ex.code not in (404, 405):
                raise
            r = self.call("/QuickConnect/Initiate")    # (an older server's way)
        self.quick = {"secret": r["Secret"], "code": str(r["Code"]), "until": time.monotonic() + JF_QUICK_SECS}

    def check_quick(self):
        """True once you've typed the code in Jellyfin (and it's signed in)."""
        q = self.quick
        if not q:
            return False
        r = self.call("/QuickConnect/Connect", timeout=6, secret=q["secret"])
        if not r.get("Authenticated"):
            return False
        a = self.call("/Users/AuthenticateWithQuickConnect", method="POST", body={"Secret": q["secret"]})
        self.quick = None
        return self.signed(a)

    def signed(self, auth):
        user = auth.get("User") if isinstance(auth, dict) else None
        if not (isinstance(user, dict) and auth.get("AccessToken") and user.get("Id")):
            return False
        self.cfg.update(token=auth["AccessToken"], user=user["Id"], user_name=clean_name(user.get("Name"), 30))
        self.cfg.pop("login", None)
        self.save()
        return True

    def sign_out(self):
        """Signed out at once; the server's told after (it may not answer)."""
        server, token = self.server, self.cfg.get("token")
        self.forget()
        if server and token:
            threading.Thread(target=self.quiet_logout, args=(server, token), daemon=True).start()

    def quiet_logout(self, server, token):
        try:
            self.call("/Sessions/Logout", method="POST", timeout=6, raw=True, server=server, token=token)
        except Exception:
            pass

    # -- browsing ---------------------------------------------------------------------------------------------------
    @staticmethod
    def common(params):
        params.setdefault("fields", JF_FIELDS)
        params.setdefault("enableImageTypes", "Primary")
        params.setdefault("imageTypeLimit", 1)
        return params

    def views(self):
        """Your libraries of films, shows and videos (not music, books or photos)."""
        r = self.get(["/UserViews", f"/Users/{self.uid}/Views"], userId=self.uid)
        return [v for v in r.get("Items") or [] if isinstance(v, dict) and v.get("Id")
                and (v.get("CollectionType") or "") in JF_LIBRARIES]

    def items(self, **params):
        params.setdefault("sortBy", "SortName")
        params.setdefault("sortOrder", "Ascending")
        params.setdefault("limit", 2000)
        r = self.get(["/Items", f"/Users/{self.uid}/Items"], userId=self.uid, **self.common(params))
        return r.get("Items") or []

    def library(self, lib, kind):
        """A library's films (or shows) all together; any other library, folder by folder."""
        if kind == "movies":
            return self.items(parentId=lib, recursive="true", includeItemTypes="Movie")
        if kind == "tvshows":
            return self.items(parentId=lib, recursive="true", includeItemTypes="Series")
        return self.items(parentId=lib)

    def resume(self):
        r = self.get(["/UserItems/Resume", f"/Users/{self.uid}/Items/Resume"], userId=self.uid,
                     **self.common({"mediaTypes": "Video", "limit": 50}))
        return r.get("Items") or []

    def next_up(self):
        r = self.call("/Shows/NextUp", userId=self.uid, **self.common({"limit": 50}))
        return r.get("Items") or []

    def seasons(self, series):
        r = self.call(f"/Shows/{series}/Seasons", userId=self.uid, isMissing="false", **self.common({}))
        return r.get("Items") or []

    def episodes(self, series, season):
        r = self.call(f"/Shows/{series}/Episodes", userId=self.uid, seasonId=season, isMissing="false",
                      **self.common({}))
        return r.get("Items") or []

    def search(self, words):
        return self.items(searchTerm=words, recursive="true", includeItemTypes="Movie,Series,Episode,Video",
                          limit=60)

    def image(self, item, tag, w, h):
        """An item's picture, filling w x h: JPEG bytes."""
        return self.call(f"/Items/{item}/Images/Primary", raw=True, fillWidth=w, fillHeight=h, quality=85, tag=tag)

    # -- playing (as the Plex player asks) ---------------------------------------------------------------------------
    def stream_url(self, item, offset, session):
        """The video, made the size the Pi plays smoothly, from offset seconds in."""
        res, kbps, _ = video_target()
        w, h = (int(x) for x in res.split("x"))
        with self.lock:
            was = self.playing.get(item)               # (the same video again, from a new place: still playing)
            self.playing[item] = {"session": session, "started": bool(was and was["started"])}
        q = {"static": "false", "mediaSourceId": item, "deviceId": self.cfg["device"], "playSessionId": session,
             "videoCodec": "h264", "audioCodec": "aac", "maxWidth": w, "maxHeight": h, "videoBitRate": kbps * 1000,
             "maxFramerate": 30, "maxVideoBitDepth": 8, "audioBitRate": 128000, "audioChannels": 2,
             "startTimeTicks": int(max(offset, 0) * TICKS), "ApiKey": self.cfg.get("token", "")}
        return f"{self.server}/Videos/{item}/stream.ts?" + urllib.parse.urlencode(q)

    def timeline(self, item, state, pos, length, session=None):
        """Where you are (playing, paused or stopped), for the server to keep and show on its dashboard."""
        with self.lock:
            p = self.playing.get(item)
            session = session or (p and p["session"])
            if state == "stopped" and p and p["session"] == session:
                self.playing.pop(item, None)
        if not session:
            return
        body = {"ItemId": item, "MediaSourceId": item, "PlaySessionId": session,
                "PositionTicks": int(max(pos or 0, 0) * TICKS)}
        if state == "stopped":
            self.quiet("/Sessions/Playing/Stopped", body=body)
            return
        if p is None or p["session"] != session:      # (a report from before a seek, late)
            return
        body.update(IsPaused=state == "paused", CanSeek=True, PlayMethod="Transcode")
        if not p["started"]:
            p["started"] = self.quiet("/Sessions/Playing", body=body)
        else:
            self.quiet("/Sessions/Playing/Progress", body=body)

    def scrobble(self, item):
        """Watched."""
        if not self.quiet(f"/UserPlayedItems/{item}", userId=self.uid):
            self.quiet(f"/Users/{self.uid}/PlayedItems/{item}")

    def stop_transcode(self, session):
        self.quiet("/Videos/ActiveEncodings", method="DELETE", deviceId=self.cfg["device"], playSessionId=session)
