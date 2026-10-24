"""Another Pi on your network that has already fetched the weather and prices: asked first, so the
same things aren't fetched twice."""
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.parse

from .config import CACHE_DIR, clean_name, read_config, settings_glob
from .util import UA
from .net import cam_address, cam_host, cam_key, CamHTTP, CamHTTPS, read_capped


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
    """One of PiE-ink's coins: (its id, {"q": the quote as the Finance tab keeps it, "age", "graph",
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
