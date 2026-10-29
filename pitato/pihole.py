"""Your Pi-hole: its numbers from Pi-hole itself (its API: Pi-hole 6's, or 5's), signed in to once."""
import hashlib
import ipaddress
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import read_config, settings_file, write_setting

PIHOLE_POLL = 10         # seconds between asking Pi-hole for its numbers, while its page is open
PIHOLE_MORE = 30         # ...and for its last 24 hours and its top lists (they change more slowly)
PIHOLE_TOP = 5           # how many of each top list
PIHOLE_FILE = "pihole.txt"


class Denied(Exception):
    """Pi-hole didn't take the password (or wants one)."""


class TwoFactor(Exception):
    """Pi-hole wants a two-factor code as well (an app password goes without one)."""


class NotPihole(Exception):
    """Something answered, but not as a Pi-hole does."""


class Busy(Exception):
    """Pi-hole 6 has as many sign-ins open as it allows (they run out after half an hour unused)."""


def pihole_url(text):
    """Pi-hole's address as you might type it (192.168.1.2, pi.hole:8080, http://192.168.1.2/admin/) as the start
    of its API's addresses, or '' when it isn't one."""
    t = (text or "").strip()
    if not t:
        return ""
    if "://" not in t:
        t = "http://" + t
    try:
        u = urllib.parse.urlsplit(t)
        host, port = u.hostname, u.port
    except ValueError:
        return ""
    if u.scheme not in ("http", "https") or not host or not re.fullmatch(r"[A-Za-z0-9.-]+|[0-9A-Fa-f:]+", host):
        return ""
    return f"{u.scheme}://{'[' + host + ']' if ':' in host else host}" + (f":{port}" if port else "")


def pihole_tries(url):
    """Where to look for the Pi-hole at url: there, if it has a port; with none, on 8080 (where it is when something
    else has 80, as in Docker) and then on 80. (https with none: its own 443.)"""
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port
    except ValueError:
        return [url]
    if port or u.scheme != "http":
        return [url]
    return [url + ":8080", url + ":80"]


def dns_guess():
    """Where this Pi asks for names (your Pi-hole, as often as not): to start the address box with."""
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    try:
                        ip = ipaddress.ip_address(parts[1])
                    except ValueError:
                        continue
                    if ip.version == 4 and ip.is_private and str(ip) != "127.0.0.53":   # (on your network, or
                        return str(ip)                                                    # this Pi; not systemd's)
    except OSError:
        pass
    return ""


def v5_token(password):
    """Pi-hole 5's API token for a password (the token itself, from its Settings > API, as it is)."""
    if re.fullmatch(r"[0-9a-f]{64}", password or ""):
        return password
    return hashlib.sha256(hashlib.sha256(password.encode()).hexdigest().encode()).hexdigest()


def hourly(buckets, now=None):
    """Pi-hole's ten-minute counts [(start, total, blocked)] as the last 24 hours, an hour at a time (hours of your
    clock, the last the one under way): [(the hour's start, allowed, blocked)]."""
    now = time.time() if now is None else now

    def hour_of(t):
        lt = time.localtime(t)
        return int(t) - lt.tm_min * 60 - lt.tm_sec

    this = hour_of(now)
    hours = [this - 3600 * k for k in range(23, -1, -1)]
    sums = {h: [0, 0] for h in hours}
    for t, total, blocked in buckets:
        try:
            t, total, blocked = int(float(t)), max(0, int(float(total or 0))), max(0, int(float(blocked or 0)))
        except (TypeError, ValueError):
            continue
        h = hour_of(t)
        if h in sums:
            sums[h][0] += max(0, total - blocked)
            sums[h][1] += min(blocked, total) if total else blocked
    return [(h, sums[h][0], sums[h][1]) for h in hours]


def count(n):
    try:
        return f"{round(float(n)):,}"
    except (TypeError, ValueError):
        return "not known"


def save_pihole(url, password):
    """Your Pi-hole and its password, in static/pihole.txt (yours only: never shown on the web page)."""
    write_setting(PIHOLE_FILE, "# Your Pi-hole, for the Pi-hole page in the Home tab: Pietato writes this\n"
                               "# when you sign in there. Keep it private: it has your Pi-hole's password.\n"
                               f"address = {url}\npassword = {password}\n", private=True)


def forget_pihole():
    try:
        os.remove(settings_file(PIHOLE_FILE))
    except FileNotFoundError:
        pass


class Pihole:
    """Your Pi-hole's numbers, from Pi-hole itself: its queries today, how many it blocked and the percentage, the
    domains on its lists, its clients, and whether it's blocking; and for its dashboard, its last 24 hours, its top
    blocked and allowed domains, its top clients and its kinds of query. Asked for every few seconds while its page
    is open, on a thread of its own. pihole.txt (written when you sign in on its page):
        address = http://192.168.1.2:8080      (with no port: on 8080, or else 80)
        password = (its password, or an app password; none if it has none)
    """

    def __init__(self):
        self.address = self.url = self.password = ""   # (its address, as written; where it answers)
        self.loaded = None
        self.sid = None              # Pi-hole 6's session, while it lasts
        self.version = None          # 6 or 5, once it's answered
        self.rows = []               # [(key, label, value, worry)]
        self.more = {}               # the dashboard's: "hours" [(start, allowed, blocked)], "blocked", "allowed" and
        self.more_at = 0.0           # "clients" [(name, count)], "types" [(kind, count)]; when to ask for them again
        self.error = None            # what's wrong, in a few words
        self.denied = False          # ...the password, which signing in again puts right
        self.found = False
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.running = False
        self.thread = None
        self.poll_now = False
        self.on_change = lambda: None

    def load(self, patterns):
        cfg = read_config(patterns)
        key = (pihole_url(cfg.get("address", "")), cfg.get("password", ""))
        if key != self.loaded:                         # another Pi-hole, or another password: afresh
            self.loaded = key
            self.address, self.password = key
            self.url = self.address                    # (with no port: which, found when it's first asked)
            self.sid = self.version = None
            self.rows, self.error, self.denied, self.found = [], None, False, False
            self.more, self.more_at = {}, 0.0

    @property
    def configured(self):
        return bool(self.url)

    @property
    def where(self):
        return self.url.split("://", 1)[-1]

    # talking to Pi-hole
    def ask(self, method, path, body=None, url=None, sid=None, timeout=6):
        """(status, its JSON) from Pi-hole: its refusals are answers too (401: not signed in)."""
        url = url or self.url
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if sid:
            headers["X-FTL-SID"] = sid
        req = urllib.request.Request(url + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        ctx = None
        if url.startswith("https://"):                 # (Pi-hole's own certificate, made by itself)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                status, raw = r.status, r.read(2_000_000)
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read(200_000)
        try:
            return status, (json.loads(raw) if raw.strip() else None)
        except ValueError:
            return status, None

    def probe(self, url):
        """What's at url: (6 or 5, whether it wants a password). NotPihole for something else; OSError when
        nothing's there."""
        status, out = self.ask("GET", "/api/auth", url=url)
        if status in (200, 401) and isinstance(out, dict) and isinstance(out.get("session"), dict):
            return 6, not out["session"].get("valid")
        status, out = self.ask("GET", "/admin/api.php?summaryRaw", url=url)
        if status == 200 and isinstance(out, dict) and "dns_queries_today" in out:
            return 5, False
        if status == 200 and out == []:                # (Pi-hole 5 says nothing without its token)
            return 5, True
        raise NotPihole()

    def find(self, url):
        """Where the Pi-hole at url answers (with no port: on 8080, or else 80): (there, 6 or 5, whether it wants a
        password). NotPihole when something else answers there; OSError (or the like) when nothing does."""
        trouble = None
        for there in pihole_tries(url):
            try:
                return (there,) + self.probe(there)
            except NotPihole as ex:
                trouble = ex
            except Exception as ex:
                trouble = trouble if isinstance(trouble, NotPihole) else ex
        raise trouble

    def sign_in(self, url, password):
        """Pi-hole 6: a session (its sid; None when it has no password). Denied, TwoFactor or NotPihole if not."""
        status, out = self.ask("POST", "/api/auth", {"password": password}, url=url)
        if status == 429:
            raise Busy()
        s = out.get("session") if isinstance(out, dict) else None
        if not isinstance(s, dict):
            raise NotPihole()
        if s.get("valid"):
            return s.get("sid")
        words = str(s.get("message") or "").lower()
        if s.get("totp") or "2fa" in words or "totp" in words:
            raise TwoFactor()
        raise Denied()

    def check(self, url, password):
        """Signing in, as it's added: (Pi-hole's version, its session), or Denied, TwoFactor, Busy, NotPihole,
        OSError. (The session's kept for its numbers: Pi-hole 6 only has so many.)"""
        version, needs = self.probe(url)
        sid = None
        if version == 6:
            if needs or password:
                sid = self.sign_in(url, password)
        elif needs:
            _, out = self.ask("GET", f"/admin/api.php?summaryRaw&auth={v5_token(password)}", url=url)
            if not (isinstance(out, dict) and "dns_queries_today" in out):
                raise Denied()
        return version, sid

    def sign_out(self, url, sid):
        try:
            self.ask("DELETE", "/api/auth", url=url, sid=sid, timeout=3)
        except Exception:
            pass

    def get6(self, path):
        """Pi-hole 6's answer, signed in (again, if the session's run out)."""
        for again in (False, True):
            status, out = self.ask("GET", path, sid=self.sid)
            if status == 401 and not again:
                self.sid = self.sign_in(self.url, self.password)
                continue
            if status == 401:
                raise Denied()
            if status != 200 or not isinstance(out, dict):
                raise NotPihole()
            return out

    def numbers(self):
        """[(key, label, value, worry)], as Pi-hole's own dashboard has them."""
        if self.version is None:
            self.url, self.version, needs = self.find(self.address)
            if needs and not self.password:
                raise Denied()
        if self.version == 6:
            s, b = self.get6("/api/stats/summary"), self.get6("/api/dns/blocking")
            q, c, g = s.get("queries") or {}, s.get("clients") or {}, s.get("gravity") or {}
            blocking, total, blocked = b.get("blocking"), q.get("total"), q.get("blocked")
            pct, lists, clients = q.get("percent_blocked"), g.get("domains_being_blocked"), c.get("active")
            domains, cached, forwarded = q.get("unique_domains"), q.get("cached"), q.get("forwarded")
        else:
            auth = f"&auth={v5_token(self.password)}" if self.password else ""
            status, s = self.ask("GET", "/admin/api.php?summaryRaw" + auth)
            if s == []:
                raise Denied()
            if status != 200 or not isinstance(s, dict):
                raise NotPihole()
            blocking, total, blocked = s.get("status"), s.get("dns_queries_today"), s.get("ads_blocked_today")
            pct, lists, clients = s.get("ads_percentage_today"), s.get("domains_being_blocked"), s.get("unique_clients")
            domains, cached, forwarded = s.get("unique_domains"), s.get("queries_cached"), s.get("queries_forwarded")
        try:
            pct = f"{float(pct):.1f}%"
        except (TypeError, ValueError):
            pct = "not known"
        on = {"enabled": "On", "disabled": "Off"}.get(str(blocking))
        return [("blocking", "Blocking", on or str(blocking or "not known"), on != "On"),
                ("total", "Total queries", count(total), False),
                ("blocked", "Queries blocked", count(blocked), False),
                ("percent", "Percentage blocked", pct, False),
                ("lists", "Domains on lists", count(lists) if isinstance(lists, (int, float)) and lists >= 0
                 else "not known", False),
                ("clients", "Clients", count(clients), False),
                ("domains", "Unique domains", count(domains), False),
                ("cached", "Answered from cache", count(cached), False),
                ("forwarded", "Forwarded", count(forwarded), False)]

    def extras(self):
        """The dashboard's: the last 24 hours, an hour at a time, and the top lists. What Pi-hole won't say is left
        out (each on its own: the numbers above are what matter)."""
        more = {}

        def tried(what):
            try:
                return what()
            except (Denied, TwoFactor, Busy):
                raise
            except Exception:
                return None

        n = PIHOLE_TOP
        if self.version == 6:
            h = tried(lambda: self.get6("/api/history").get("history"))
            if isinstance(h, list):
                more["hours"] = hourly([(x.get("timestamp"), x.get("total"), x.get("blocked"))
                                        for x in h if isinstance(x, dict)])
            for key, path in (("blocked", f"/api/stats/top_domains?count={n}&blocked=true"),
                              ("allowed", f"/api/stats/top_domains?count={n}")):
                got = tried(lambda: self.get6(path).get("domains"))
                if isinstance(got, list):
                    more[key] = [(str(x.get("domain") or ""), x.get("count") or 0) for x in got if isinstance(x, dict)]
            got = tried(lambda: self.get6(f"/api/stats/top_clients?count={n}").get("clients"))
            if isinstance(got, list):
                more["clients"] = [(str(x.get("name") or x.get("ip") or ""), x.get("count") or 0)
                                   for x in got if isinstance(x, dict)]
            got = tried(lambda: self.get6("/api/stats/query_types").get("types"))
            if isinstance(got, dict):
                more["types"] = [(str(k), v) for k, v in got.items()]
        else:
            auth = f"&auth={v5_token(self.password)}" if self.password else ""

            def ask5(what):
                status, out = self.ask("GET", "/admin/api.php?" + what + auth)
                return out if status == 200 and isinstance(out, dict) else {}

            o = tried(lambda: ask5("overTimeData10mins"))
            if o:
                total, ads = o.get("domains_over_time") or {}, o.get("ads_over_time") or {}
                if isinstance(total, dict) and isinstance(ads, dict):
                    more["hours"] = hourly([(t, total.get(t), ads.get(t)) for t in total])
            t = tried(lambda: ask5(f"topItems={n}")) or {}
            for key, part in (("blocked", "top_ads"), ("allowed", "top_queries")):
                if isinstance(t.get(part), dict):
                    more[key] = list(t[part].items())[:n]
            c = tried(lambda: ask5(f"topClients={n}")) or {}
            if isinstance(c.get("top_sources"), dict):        # ("name|ip": count)
                more["clients"] = [(k.split("|")[0] or k.split("|")[-1], v) for k, v in c["top_sources"].items()][:n]
            q = tried(lambda: ask5("getQueryTypes")) or {}
            if isinstance(q.get("querytypes"), dict):         # ("A (IPv4)": its percentage)
                more["types"] = [(k.split(" ")[0], v) for k, v in q["querytypes"].items()]
        return more

    def refresh(self):
        try:
            rows = self.numbers()
            if time.monotonic() >= self.more_at:
                self.more = self.extras()
                self.more_at = time.monotonic() + PIHOLE_MORE
            self.rows, self.found, self.error, self.denied = rows, True, None, False
        except Denied:
            self.rows, self.error, self.denied = [], "wants its password", True
        except TwoFactor:
            self.rows, self.error, self.denied = [], "wants a two-factor code", True
        except Busy:
            self.rows, self.error, self.denied = [], "too many signed in: try again later", False
        except NotPihole:
            self.rows, self.error, self.denied, self.version = [], "isn't answering as a Pi-hole", False, None
        except Exception:
            self.rows, self.error, self.denied, self.version = [], "not answering", False, None
        self.on_change()

    # its thread: while the page is open
    def start(self):
        if not self.configured:
            return
        with self.lock:
            self.running = True
            if self.thread is None:
                self.thread = threading.Thread(target=self.loop, daemon=True, name="pihole")
                self.thread.start()
        self.wake.set()

    def stop(self):
        self.running = False
        self.wake.set()

    def loop(self):
        next_poll = 0.0
        while True:
            with self.lock:
                if not self.running:
                    self.thread = None
                    return
            if self.poll_now or time.monotonic() >= next_poll:
                self.poll_now = False
                self.refresh()
                next_poll = time.monotonic() + PIHOLE_POLL
            self.wake.wait(0.25)
            self.wake.clear()
