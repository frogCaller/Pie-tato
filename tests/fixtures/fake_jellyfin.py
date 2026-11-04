"""A small fake Jellyfin server for the tests: the routes gpi-media uses, answering as Jellyfin 10.11 does (or, with
legacy=True, as 10.8 does: the newer routes missing), and a UDP discovery responder."""
import io
import json
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw


def hid(n):
    return f"{n:032x}"


SERVER_ID = "f3a1c2d4e5b6a7980a1b2c3d4e5f6a7b"
UID = hid(0xA11CE)
MOVIES, SHOWS, MUSIC, HOME = hid(1), hid(2), hid(3), hid(4)


def ud(pos=0, played=False, unplayed=None):
    d = {"PlaybackPositionTicks": int(pos * 1e7), "PlayCount": 1 if played else 0, "IsFavorite": False,
         "Played": played, "Key": "k"}
    if unplayed is not None:
        d["UnplayedItemCount"] = unplayed
    return d


def movie(n, name, year, mins, pos=0, played=False, tag=True):
    return {"Name": name, "ServerId": SERVER_ID, "Id": hid(n), "Type": "Movie", "IsFolder": False,
            "ProductionYear": year, "RunTimeTicks": int(mins * 60 * 1e7), "MediaType": "Video",
            "UserData": ud(pos, played), "ImageTags": {"Primary": f"tag{n}"} if tag else {}}


def series(n, name, eps, unplayed, tag=True):
    return {"Name": name, "ServerId": SERVER_ID, "Id": hid(n), "Type": "Series", "IsFolder": True,
            "RecursiveItemCount": eps, "ChildCount": 2, "UserData": ud(unplayed=unplayed),
            "ImageTags": {"Primary": f"tag{n}"} if tag else {}}


def season(n, sid, sname, idx, eps, unplayed):
    return {"Name": f"Season {idx}", "ServerId": SERVER_ID, "Id": hid(n), "Type": "Season", "IsFolder": True,
            "IndexNumber": idx, "SeriesId": hid(sid), "SeriesName": sname, "ChildCount": eps,
            "SeriesPrimaryImageTag": f"tag{sid}", "UserData": ud(unplayed=unplayed), "ImageTags": {}}


def episode(n, sid, sname, sea, idx, name, mins, pos=0, played=False, still=True):
    return {"Name": name, "ServerId": SERVER_ID, "Id": hid(n), "Type": "Episode", "IsFolder": False,
            "IndexNumber": idx, "ParentIndexNumber": sea, "SeriesId": hid(sid), "SeriesName": sname,
            "SeasonId": hid(n // 100 * 100), "RunTimeTicks": int(mins * 60 * 1e7), "MediaType": "Video",
            "SeriesPrimaryImageTag": f"tag{sid}", "UserData": ud(pos, played),
            "ImageTags": {"Primary": f"still{n}"} if still else {}}


ITEMS = {
    "movies": [movie(101, "Arrival", 2016, 116, pos=1800), movie(102, "Paddington 2", 2017, 104, played=True),
               movie(103, "Ponyo – 崖の上のポニョ", 2008, 101, tag=False)],
    "series": [series(200, "Bluey", 6, 4), series(300, "Planet Earth", 3, 3)],
    "seasons200": [season(210, 200, "Bluey", 1, 3, 1), season(220, 200, "Bluey", 2, 3, 3)],
    "seasons300": [season(310, 300, "Planet Earth", 1, 3, 3)],
    "eps210": [episode(211, 200, "Bluey", 1, 1, "Magic Xylophone", 7, played=True),
               episode(212, 200, "Bluey", 1, 2, "Hospital", 7, played=True),
               episode(213, 200, "Bluey", 1, 3, "Keepy Uppy", 7, pos=200)],
    "eps220": [episode(221, 200, "Bluey", 2, 1, "Dance Mode", 7), episode(222, 200, "Bluey", 2, 2, "Hammerbarn", 7),
               episode(223, 200, "Bluey", 2, 3, "Duck Cake", 7, still=False)],
    "eps310": [episode(311, 300, "Planet Earth", 1, 1, "From Pole to Pole", 49),
               episode(312, 300, "Planet Earth", 1, 2, "Mountains", 49),
               episode(313, 300, "Planet Earth", 1, 3, "Fresh Water", 49)],
    "home": [{"Name": "Holidays", "Id": hid(401), "Type": "Folder", "IsFolder": True, "ImageTags": {}},
             {"Name": "First steps", "Id": hid(402), "Type": "Video", "IsFolder": False, "MediaType": "Video",
              "RunTimeTicks": int(95 * 1e7), "UserData": ud(), "ImageTags": {"Primary": "t402"}}],
    "holidays": [{"Name": "Beach day", "Id": hid(411), "Type": "Video", "IsFolder": False, "MediaType": "Video",
                  "RunTimeTicks": int(300 * 1e7), "UserData": ud(), "ImageTags": {}}],
}
VIEWS = [{"Name": "Movies", "Id": MOVIES, "Type": "CollectionFolder", "CollectionType": "movies", "IsFolder": True},
         {"Name": "Shows", "Id": SHOWS, "Type": "CollectionFolder", "CollectionType": "tvshows", "IsFolder": True},
         {"Name": "Music", "Id": MUSIC, "Type": "CollectionFolder", "CollectionType": "music", "IsFolder": True},
         {"Name": "Home Videos", "Id": HOME, "Type": "CollectionFolder", "CollectionType": "homevideos",
          "IsFolder": True}]


def all_items():
    out = []
    for k, v in ITEMS.items():
        out += v
    return out


def jf_parts(header):
    """Jellyfin's own reading of its Authorization header (AuthorizationContext.GetParts), in Python."""
    name, _, rest = header.partition(" ")
    if name.lower() != "mediabrowser":
        return None
    result, escaped, start, key = {}, False, 0, ""
    for i, ch in enumerate(rest):
        if ch in '",':
            escaped = (not escaped) == (ch == '"')
            if ch == "," and not escaped:
                if start < i:
                    result[key] = urllib.parse.unquote_plus(rest[start:i].strip('"'))
                    key = ""
                start = i + 1
        elif not escaped and ch == "=":
            key = rest[start:i].strip()
            start = i + 1
    if start < len(rest):
        result[key] = urllib.parse.unquote_plus(rest[start:].strip('"'))
    return result


class FakeJellyfin:
    def __init__(self, legacy=False, quick=True, server_id=SERVER_ID, name="Den Server"):
        self.legacy, self.quick_enabled, self.server_id, self.name = legacy, quick, server_id, name
        self.requests = []
        self.tokens = {"TOKEN-QC": UID}
        self.users = {"sam": ("pw", "TOKEN-PW")}
        self.polls = 0
        self.authorize_after = 2
        self.lock = threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                fake.handle(self, "GET")

            def do_POST(self):
                fake.handle(self, "POST")

            def do_DELETE(self):
                fake.handle(self, "DELETE")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def find(self, method, path):
        return [r for r in self.requests if r["method"] == method and r["path"] == path]

    def paths(self):
        return [(r["method"], r["path"]) for r in self.requests]

    # -- the routes ------------------------------------------------------------------------------------------------
    def handle(self, h, method):
        u = urllib.parse.urlsplit(h.path)
        path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        n = int(h.headers.get("Content-Length") or 0)
        raw = h.rfile.read(n) if n else b""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = "BAD JSON"
        auth = jf_parts(h.headers.get("Authorization") or "") or {}
        rec = {"method": method, "path": path, "q": q, "auth": auth, "body": body,
               "content_length": h.headers.get("Content-Length")}
        with self.lock:
            self.requests.append(rec)
        token = auth.get("Token") or q.get("ApiKey")
        user = self.tokens.get(token)
        status, out, ctype = self.route(method, path, q, auth, body, user)
        if isinstance(out, (dict, list, bool)):
            data, ctype = json.dumps(out).encode(), "application/json; charset=utf-8"
        elif isinstance(out, str):
            data = out.encode()
        else:
            data = out or b""
        h.send_response(status)
        h.send_header("Content-Type", ctype or "text/plain")
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def route(self, method, path, q, auth, body, user):
        L = self.legacy
        if path == "/System/Info/Public" and method == "GET":
            return 200, {"LocalAddress": self.url, "ServerName": self.name, "Version": "10.11.9",
                         "ProductName": "Jellyfin Server", "Id": self.server_id, "StartupWizardCompleted": True}, None
        if path == "/QuickConnect/Enabled":
            return 200, self.quick_enabled, None
        if path == "/QuickConnect/Initiate":
            if L and method == "POST":
                return 405, "", None
            if not self.quick_enabled:
                return 401, "Quick connect is disabled", None
            if not all(auth.get(k) for k in ("DeviceId", "Device", "Client", "Version")):
                return 400, "missing device", None
            self.polls = 0
            return 200, {"Authenticated": False, "Secret": "SECRET-1", "Code": "482913",
                         "DeviceId": auth["DeviceId"], "DeviceName": auth["Device"], "AppName": auth["Client"],
                         "AppVersion": auth["Version"], "DateAdded": "2026-10-21T10:00:00Z"}, None
        if path == "/QuickConnect/Connect":
            if q.get("secret") != "SECRET-1":
                return 404, "Unknown secret", None
            self.polls += 1
            return 200, {"Authenticated": self.polls >= self.authorize_after, "Secret": "SECRET-1", "Code": "482913"}, None
        if path == "/Users/AuthenticateWithQuickConnect" and method == "POST":
            if (body or {}).get("Secret") != "SECRET-1" or self.polls < self.authorize_after:
                return 401, "", None
            self.tokens["TOKEN-QC"] = UID
            return 200, {"User": {"Name": "Sam\u0007", "Id": UID, "ServerId": self.server_id},
                         "AccessToken": "TOKEN-QC", "ServerId": self.server_id}, None
        if path == "/Users/AuthenticateByName" and method == "POST":
            name, pw = (body or {}).get("Username"), (body or {}).get("Pw")
            if name in self.users and self.users[name][0] == pw:
                tok = self.users[name][1]
                self.tokens[tok] = UID
                return 200, {"User": {"Name": name, "Id": UID}, "AccessToken": tok, "ServerId": self.server_id}, None
            return 401, "Error processing request.", None
        if path.startswith("/Items/") and path.endswith("/Images/Primary"):
            w, hgt = int(q.get("fillWidth", 60)), int(q.get("fillHeight", 88))
            im = Image.new("RGB", (w, hgt), (40 + hash(path) % 150, 90, 160))
            ImageDraw.Draw(im).ellipse((w * .2, hgt * .3, w * .8, hgt * .7), fill=(240, 220, 180))
            b = io.BytesIO()
            im.save(b, "JPEG")
            return 200, b.getvalue(), "image/jpeg"
        if user is None:
            return 401, "", None
        # -- signed in ----------------------------------------------------------------------------------------------
        if path == "/Sessions/Logout" and method == "POST":
            self.tokens.pop(auth.get("Token"), None)
            return 204, b"", None
        if path in ("/UserViews", f"/Users/{UID}/Views") and method == "GET":
            if L and path == "/UserViews":
                return 404, "", None
            return 200, {"Items": VIEWS, "TotalRecordCount": len(VIEWS), "StartIndex": 0}, None
        if path in ("/Items", f"/Users/{UID}/Items") and method == "GET":
            if L and path == "/Items":
                return 404, "", None
            return 200, self.items(q), None
        if path in ("/UserItems/Resume", f"/Users/{UID}/Items/Resume"):
            if L and path == "/UserItems/Resume":
                return 404, "", None
            got = [ITEMS["movies"][0], ITEMS["eps210"][2]]
            return 200, {"Items": got, "TotalRecordCount": 2, "StartIndex": 0}, None
        if path == "/Shows/NextUp":
            got = [ITEMS["eps210"][2], ITEMS["eps310"][0]]          # (Keepy Uppy again: once only, please)
            return 200, {"Items": got, "TotalRecordCount": 2, "StartIndex": 0}, None
        if path.startswith("/Shows/") and path.endswith("/Seasons"):
            sid = int(path.split("/")[2], 16)
            got = ITEMS.get(f"seasons{sid}", [])
            return 200, {"Items": got, "TotalRecordCount": len(got), "StartIndex": 0}, None
        if path.startswith("/Shows/") and path.endswith("/Episodes"):
            got = ITEMS.get(f"eps{int(q.get('seasonId', '0'), 16)}", [])
            return 200, {"Items": got, "TotalRecordCount": len(got), "StartIndex": 0}, None
        if path.startswith("/Videos/") and path.endswith("/stream.ts"):
            return 200, b"\x47" * 188 * 10, "video/mp2t"
        if path in ("/Sessions/Playing", "/Sessions/Playing/Progress", "/Sessions/Playing/Stopped"):
            return 204, b"", None
        if path.startswith("/UserPlayedItems/") or path.startswith(f"/Users/{UID}/PlayedItems/"):
            if L and path.startswith("/UserPlayedItems/"):
                return 404, "", None
            return 200, {"Played": True, "PlayCount": 1}, None
        if path == "/Videos/ActiveEncodings" and method == "DELETE":
            return 204, b"", None
        return 404, "no such route", None

    @staticmethod
    def items(q):
        parent, kinds = q.get("parentId"), (q.get("includeItemTypes") or "").split(",")
        if q.get("searchTerm"):
            words = q["searchTerm"].lower()
            got = [m for m in all_items() if words in m["Name"].lower() and m["Type"] in kinds]
        elif parent == MOVIES:
            got = ITEMS["movies"]
        elif parent == SHOWS:
            got = ITEMS["series"]
        elif parent == HOME:
            got = ITEMS["home"]
        elif parent == hid(401):
            got = ITEMS["holidays"]
        else:
            got = []
        return {"Items": got, "TotalRecordCount": len(got), "StartIndex": 0}


class Discovery:
    """Answers 'who is JellyfinServer?' with an address (any address: a server in Docker gives one it can't be
    reached at)."""

    def __init__(self, address, server_id=SERVER_ID, name="Den Server", extra=()):
        self.address, self.server_id, self.name, self.extra = address, server_id, name, list(extra)
        self.heard = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.quit = False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            self.sock.settimeout(0.2)
        except OSError:                                # (closed already)
            return
        while not self.quit:
            try:
                data, sender = self.sock.recvfrom(2048)
                if b"who is JellyfinServer?" in data:
                    self.heard += 1
                    for x in self.extra:
                        self.sock.sendto(x, sender)
                    self.sock.sendto(json.dumps({"Address": self.address, "Id": self.server_id, "Name": self.name,
                                                 "EndpointAddress": None}).encode(), sender)
            except OSError:
                continue

    def close(self):
        self.quit = True
        self.sock.close()
