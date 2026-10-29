"""Plex: your server's films and shows, and its live TV."""
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
import uuid

from .config import read_config, settings_glob
from .screen import video_target


PLEX_FILE = "/var/lib/pitato/plex.json"      # sign-in token (readable by root only)
PLEX_PRODUCT = "Pietato"


PLEX_CACHE = ["-cache", "4096", "-cache-min", "5"]
PLEX_TIMELINE_SECS = 10                        # how often progress goes back to Plex
PLEX_EPG = "https://epg.provider.plex.tv"      # Plex's free live TV channels


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

    def timeline(self, rating_key, state, pos, length, session=None):
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
