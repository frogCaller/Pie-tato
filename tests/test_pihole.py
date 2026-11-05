"""The Pi-hole page (in the Home Assistant tab), straight to the Pi-hole: against a real Pi-hole 6 (its engine,
pihole-FTL, running here on port 80 with the password testpass: ftl/run_ftl.sh) and stand-ins for Pi-hole 5, a
Pi-hole 6 without a password, one with two-factor sign-in, and something that isn't a Pi-hole. A on Add your
Pi-hole: its address (started with where this Pi asks for names; with no port, on 8080 or else 80, typed or in
pihole.txt), then its password (a wrong one: asked again),
once: saved, private; then its dashboard: its numbers as its own dashboard has them, its last 24 hours and its
top lists (◀▶) from Pi-hole 6 and 5, blocking off (in the warning colour), a session that's run out signed in
again by itself, a password changed since (A: sign in again), a Pi-hole gone (A: try again), and Forget (Y
twice)."""
import json, os, stat, sys, threading, time, shutil, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_pihole"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.JELLYFIN_FILE = S + "/jellyfin.json"; g.SHRINK_FILE = S + "/shrink.json"
g.home_dir = lambda: HOME
g.PIHOLE_POLL = 0.5
import gk_static; gk_static.use_home(g, HOME)
g.STATIC = HOME                                    # (where write_setting puts it: the stand-in static folder)
g.settings_file = lambda name: os.path.join(HOME, name)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


# ---- the real Pi-hole 6, here: password testpass ----
REAL = "http://127.0.0.1"
for port in ("", ":8080"):                         # (on 80, or 8080 when 80 was taken as it started)
    try:
        urllib.request.urlopen("http://127.0.0.1" + port + "/api/auth", timeout=3)
    except urllib.error.HTTPError as e:
        try:
            if "session" in json.loads(e.read() or b"null"):
                REAL = "http://127.0.0.1" + port
                break
        except (ValueError, TypeError):
            pass                                   # (something else on 80)
    except OSError:
        continue
REAL_AT = REAL if REAL.endswith(":8080") else REAL + ":80"     # (where it's found with no port typed)


def real(method, path, body=None, sid=None):
    req = urllib.request.Request(REAL + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-FTL-SID": sid} if sid else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


st, out = real("GET", "/api/auth")
check(st == 401, f"(the real Pi-hole 6 here wants its password: {st})")
admin = real("POST", "/api/auth", {"password": "testpass"})[1]["session"]["sid"]
real("POST", "/api/dns/blocking", {"blocking": True, "timer": None}, admin)
import random, socket, struct


def lookup(name, kind=1):
    """a DNS question for the real Pi-hole (so it has numbers to show)"""
    q = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0) + b"".join(
        bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0" + struct.pack(">HH", kind, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.settimeout(1)
        sk.sendto(q, ("127.0.0.1", 53))
        try:
            sk.recv(512)
        except socket.timeout:
            pass


for name in ["example.org", "example.org", "github.com"]:
    lookup(name)
lookup("example.org", 28)
real_numbers = real("GET", "/api/stats/summary", sid=admin)[1]


# ---- stand-ins: Pi-hole 5, a Pi-hole 6 without a password, one with two-factor sign-in, a web server ----
TOKEN5 = __import__("hashlib").sha256(__import__("hashlib").sha256(b"five").hexdigest().encode()).hexdigest()
SUMMARY5 = {"domains_being_blocked": 98765, "dns_queries_today": 4321, "ads_blocked_today": 432,
            "ads_percentage_today": 9.99, "unique_domains": 321, "queries_forwarded": 2000, "queries_cached": 1500,
            "clients_ever_seen": 12, "unique_clients": 6, "status": "enabled"}


def stand_in(kind, at=("127.0.0.1", 0)):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, obj, code=200, raw=None):
            body = raw if raw is not None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html" if raw is not None else "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def answer(self):
            path = self.path
            if kind == "web":
                return self.reply(None, 404, raw=b"<html>Not here</html>")
            if kind == "five":
                if path.startswith("/api/"):
                    return self.reply(None, 404, raw=b"<html>404 Not Found</html>")
                if path.startswith("/admin/api.php?summaryRaw"):
                    return self.reply(SUMMARY5 if path.endswith("&auth=" + TOKEN5) else [])
                if not path.endswith("&auth=" + TOKEN5):
                    return self.reply([])
                if path.startswith("/admin/api.php?overTimeData10mins"):
                    t0 = int(time.time()) // 600 * 600
                    return self.reply({"domains_over_time": {str(t0 - 600 * k): 30 + k % 7 for k in range(144)},
                                       "ads_over_time": {str(t0 - 600 * k): 3 + k % 3 for k in range(144)}})
                if path.startswith("/admin/api.php?topItems"):
                    return self.reply({"top_queries": {"github.com": 300, "plex.tv": 120},
                                       "top_ads": {"ads.example.com": 90, "tracker.example.net": 40}})
                if path.startswith("/admin/api.php?topClients"):
                    return self.reply({"top_sources": {"laptop|192.168.1.20": 2000, "|192.168.1.31": 900}})
                if path.startswith("/admin/api.php?getQueryTypes"):
                    return self.reply({"querytypes": {"A (IPv4)": 70.5, "AAAA (IPv6)": 25.0, "PTR": 4.5}})
            if kind == "open6":
                if path == "/api/auth":
                    return self.reply({"session": {"valid": True, "totp": False, "sid": None, "validity": -1,
                                                   "message": "no password set"}})
                if path == "/api/stats/summary":
                    return self.reply({"queries": {"total": 50, "blocked": 5, "percent_blocked": 10.0,
                                                   "unique_domains": 7, "forwarded": 30, "cached": 15},
                                       "clients": {"active": 2, "total": 3},
                                       "gravity": {"domains_being_blocked": 1000, "last_update": 0}})
                if path == "/api/dns/blocking":
                    return self.reply({"blocking": "enabled", "timer": None})
                if path == "/api/history":
                    t0 = int(time.time()) // 600 * 600
                    return self.reply({"history": [{"timestamp": t0 - 600 * k, "total": 10, "blocked": 1}
                                                   for k in range(145)]})
                if path.startswith("/api/stats/top_domains"):
                    return self.reply({"domains": [{"domain": "blocked.example.com" if "blocked=true" in path
                                                    else "allowed.example.com", "count": 5}]})
                if path.startswith("/api/stats/top_clients"):
                    return self.reply({"clients": [{"name": "", "ip": "192.168.1.9", "count": 50}]})
                if path == "/api/stats/query_types":
                    return self.reply({"types": {"A": 40, "AAAA": 10}})
            if kind == "busy6" and path == "/api/auth":
                if self.command == "GET":
                    return self.reply({"session": {"valid": False, "totp": False, "sid": None, "validity": -1,
                                                   "message": "no SID provided"}}, 401)
                return self.reply({"error": {"key": "api_seats_exceeded", "message": "API seats exceeded",
                                             "hint": "increase webserver.api.max_sessions"}}, 429)
            if kind == "totp6" and path == "/api/auth":
                return self.reply({"session": {"valid": False, "totp": True, "sid": None, "validity": -1,
                                               "message": "no 2FA token found"}}, 401)
            self.reply({"error": {"key": "not_found"}}, 404)

        do_GET = do_POST = do_DELETE = answer

    srv = ThreadingHTTPServer(at, H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"{at[0]}:{srv.server_address[1]}"


FIVE, OPEN6, TOTP6, BUSY6, WEB = (stand_in("five"), stand_in("open6"), stand_in("totp6"), stand_in("busy6"),
                                  stand_in("web"))


def sessions():
    return [x for x in (real("GET", "/api/auth/sessions", sid=admin)[1] or {}).get("sessions", []) if x.get("valid")]


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


def snap(name):
    m.dirty = True; m.flush()
    FB.last.save(f"{S}/{name}.png")


def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        m.tick()
        if c():
            return True
        time.sleep(0.05)
    return False


def rows():
    return [(x["title"], m.row_right(x)[0]) for x in m.tab_items()]


def vals():
    return [(label, value) for _, label, value, _ in m.pihole.rows]


def go(title):
    m.sels[m.tab] = [x["title"] for x in m.tab_items()].index(title)


def typed(text):
    """typed into the box that's up, and done"""
    m.kb["text"] = text
    m.close_keyboard(True)


def saved():
    return g.read_config([HOME + "/pihole.txt"]) if os.path.exists(HOME + "/pihole.txt") else None


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
hai = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab, m.view = hai, "list"
m.load_tab(hai)
menu = [(x["title"], x.get("icon")) for x in m.tab_items()]
check([t for t, _ in menu] == ["TV Remote", "Lights", "Pi-hole", "Web", "Control another Pietato"],
      f"Pi-hole is in the Home Assistant menu ({menu})")
go("Pi-hole")
m.press("a")
pi = m.tab
check(g.LIBRARY[pi]["type"] == "pihole" and rows() == [("Add your Pi-hole", "")]
      and m.list_hints()[0] == ("A", "Add"), f"no Home Assistant needed: Add your Pi-hole ({rows()}, {m.list_hints()})")
snap("0_add")

# A: its address, started with where this Pi asks for names
real_guess = g.dns_guess
g.dns_guess = lambda: "192.168.1.1"
m.press("a")
check(m.view == "keys" and m.kb["text"] == "192.168.1.1" and "address" in m.kb["title"],
      f"A: a box for its address, started with this Pi's name server ({m.kb and m.kb['text']!r})")
check("like 192.168.1.2:8080" in m.kb["title"], f"...its example has a port ({m.kb['title']!r})")
g.dns_guess = real_guess
snap("1_address")
typed("not an address!")
check(m.msg == "That isn't an address. Try one like 192.168.1.2:8080" and saved() is None,
      f"not an address: says so ({m.msg!r})")
m.press("a"); typed("127.0.0.1:9")
check(wait_for(lambda: m.msg == "Can't reach 127.0.0.1:9") and m.view == "list", f"nothing there: says so ({m.msg!r})")
m.press("a"); typed(WEB)
check(wait_for(lambda: m.msg == f"{WEB} doesn't answer as a Pi-hole"), f"a web server, not a Pi-hole: says so ({m.msg!r})")

# with no port typed: on 8080, or else 80
check(g.pihole_tries("http://192.168.1.2") == ["http://192.168.1.2:8080", "http://192.168.1.2:80"]
      and g.pihole_tries(g.pihole_url("pi.hole/admin/")) == ["http://pi.hole:8080", "http://pi.hole:80"]
      and g.pihole_tries(g.pihole_url("[fd00::2]")) == ["http://[fd00::2]:8080", "http://[fd00::2]:80"]
      and g.pihole_tries(g.pihole_url("192.168.1.2:8081")) == ["http://192.168.1.2:8081"]
      and g.pihole_tries(g.pihole_url("http://192.168.1.2:80")) == ["http://192.168.1.2:80"]
      and g.pihole_tries(g.pihole_url("https://192.168.1.2")) == ["https://192.168.1.2"],
      "no port: 8080, then 80; a port: just there; https: its own")
tried = []


def nothing_there(url):
    tried.append(url)
    raise OSError("refused")


m.pihole.probe = nothing_there
m.press("a"); typed("192.168.1.50")
check(wait_for(lambda: m.msg == "Can't reach 192.168.1.50 on port 8080 or 80")
      and tried == ["http://192.168.1.50:8080", "http://192.168.1.50:80"],
      f"nothing on either: it looked on 8080, then 80, and says so ({tried}, {m.msg!r})")
del m.pihole.probe
if REAL_AT.endswith(":80"):                         # (the real one on 80, everywhere: 127.0.0.2's and 3's too)
    ON_8080 = stand_in("open6", ("127.0.0.2", 8080))
    WEB_8080 = stand_in("web", ("127.0.0.3", 8080))
    m.press("a"); typed("127.0.0.2")
    check(wait_for(lambda: saved() == {"address": "http://127.0.0.2:8080", "password": ""} and len(vals()) == 9)
          and m.pihole.where == "127.0.0.2:8080",
          f"a Pi-hole on 8080 and one on 80: 8080's, saved with its port ({saved()}, {m.pihole.where})")
    m.press("y"); m.press("y")
    m.press("a"); typed("127.0.0.3")
    check(wait_for(lambda: m.view == "keys" and "password" in m.kb["title"]),
          "something else on 8080: the Pi-hole on 80, which wants its password")
    typed("testpass")
    check(wait_for(lambda: saved() == {"address": "http://127.0.0.3:80", "password": "testpass"}
                   and len(vals()) == 9 and m.pihole.sid),
          f"...signed in, saved with its port ({saved()})")
    m.press("y"); m.press("y")                      # (and its session ended)
else:
    print("(the real Pi-hole here is on 8080: no stand-ins on 8080 beside it)")

# the real Pi-hole 6: its password, once (typed with no port)
time.sleep(0.5)
before = len(sessions())
m.press("a"); typed("127.0.0.1")
check(wait_for(lambda: m.view == "keys" and "password" in m.kb["title"]),
      f"the real Pi-hole 6: it wants its password, so a box for it ({m.kb and m.kb['title']!r})")
snap("2_password")
typed("wrong")
check(wait_for(lambda: m.msg == "Your Pi-hole didn't take that password" and m.view == "keys"),
      f"a wrong one: says so, and asks again ({m.msg!r})")
typed("testpass")
check(wait_for(lambda: m.pihole.found and len(m.pihole.rows) == 9 and m.pihole.more.get("types")),
      f"the right one: signed in ({m.msg!r})")
cfg = saved()
mode = stat.S_IMODE(os.stat(HOME + "/pihole.txt").st_mode)
check(cfg == {"address": REAL_AT, "password": "testpass"} and mode == 0o600,
      f"...once: saved in static/pihole.txt, yours only ({cfg}, {oct(mode)})")
check(g.web_private("pihole.txt") and "pihole.txt" in __import__("pitato.webui", fromlist=["x"]).PRIVATE,
      "...which the web page never shows")
real_numbers = real("GET", "/api/stats/summary", sid=admin)[1]
want = [("Blocking", "On"), ("Total queries", f"{real_numbers['queries']['total']:,}"),
        ("Queries blocked", f"{real_numbers['queries']['blocked']:,}"),
        ("Percentage blocked", f"{float(real_numbers['queries']['percent_blocked']):.1f}%"),
        ("Domains on lists", "not known"), ("Clients", f"{real_numbers['clients']['active']:,}"),
        ("Unique domains", f"{real_numbers['queries']['unique_domains']:,}"),
        ("Answered from cache", f"{real_numbers['queries']['cached']:,}"),
        ("Forwarded", f"{real_numbers['queries']['forwarded']:,}")]
print("numbers:", vals())
check(vals() == want, "its numbers, as its dashboard has them (this one's gravity isn't there: not known)")
more = m.pihole.more
hours = more.get("hours") or []
print("more:", {k: (v if k != "hours" else f"{len(v)} hours, {sum(a + b for _, a, b in v)} queries")
                for k, v in more.items()})
check(len(hours) == 24 and sum(a + b for _, a, b in hours) == real_numbers["queries"]["total"]
      and hours[-1][0] <= time.time() < hours[-1][0] + 3600,
      "...its last 24 hours, an hour at a time, the last the one under way (every query in them)")
check(dict(more.get("allowed", [])).get("example.org", 0) >= 3 and more.get("blocked") == []
      and [c for c, _ in more.get("clients", [])] in (["localhost"], ["127.0.0.1"])
      and dict(more.get("types", [])).get("A", 0) >= 3 and dict(more["types"]).get("AAAA", 0) >= 1,
      "...its top allowed (example.org), top blocked (none here), clients (this Pi, by name), query types")
time.sleep(1.5)
check(len(sessions()) == before + 1, f"...one sign-in for it all, kept: Pi-hole 6 only has so many ({before} before, "
      f"{len(sessions())} now)")
check(m.list_hints() == [("◀▶", "Top lists"), ("Y", "Forget"), ("L R", "Tabs"), ("B", "Back")],
      f"its dashboard's buttons: {m.list_hints()}")
snap("3_dashboard")
panels = []
for k in range(4):
    panels.append(m.pihole_panel)
    m.press("right")
check(panels == [0, 1, 2, 3] and m.pihole_panel == 0, f"▶: its lists below, round and round ({panels})")
m.press("left")
check(m.pihole_panel == 3, "◀: back the other way")
for k in range(4):
    m.pihole_panel = k
    snap(f"3_panel{k}")
m.pihole_panel = 0
m.press("x")
check(m.view == "help", "X: its controls")
snap("3_help")
m.press("b")

# blocking off, and a session that's run out
real("POST", "/api/dns/blocking", {"blocking": False, "timer": None}, admin)
check(wait_for(lambda: dict(vals()).get("Blocking") == "Off"), f"blocking turned off: Off, picked up ({vals()[0]})")
snap("4_off")
pill = FB.last.crop((300, 76, 640, 96))
check(g.WARN in [c for _, c in pill.getcolors(100000)], "...said in the warning colour, beside its light")
real("POST", "/api/dns/blocking", {"blocking": True, "timer": None}, admin)
sid = m.pihole.sid
real("DELETE", "/api/auth", sid=sid)
check(wait_for(lambda: m.pihole.sid not in (None, sid) and dict(vals()).get("Blocking") == "On"),
      "its session ended (or run out): signed in again by itself")

# a password changed since: A signs in again
m.pihole.password = "changed-since"
m.pihole.sid = None
check(wait_for(lambda: m.pihole.error == "wants its password"), f"a password that's changed since: says so "
      f"({m.pihole_says()})")
check(m.list_hints()[0] == ("A", "Sign in"), f"...A: sign in ({m.list_hints()})")
snap("5_password")
m.press("a")
check(m.view == "keys" and "password" in m.kb["title"], "...a box for it")
typed("testpass")
check(wait_for(lambda: not m.pihole.error and dict(vals()).get("Blocking") == "On"), "...and its dashboard again")

# pihole.txt with no port: found on 8080, or else 80, as it's first asked
m.pihole.stop(); time.sleep(0.8)
real("DELETE", "/api/auth", sid=m.pihole.sid)
g.write_setting("pihole.txt", "address = 127.0.0.1\npassword = testpass\n")
m.load_tab(pi)
check(wait_for(lambda: len(vals()) == 9 and m.pihole.sid) and m.pihole.url == REAL_AT
      and m.pihole.where == REAL_AT.split("://")[1] and m.pihole.address == "http://127.0.0.1",
      f"pihole.txt with no port: found ({m.pihole.url})")
real("DELETE", "/api/auth", sid=m.pihole.sid)

# a Pi-hole gone: A tries again
g.write_setting("pihole.txt", "address = 127.0.0.1:9\n")
m.load_tab(pi)
check(wait_for(lambda: m.pihole.error == "not answering"), f"a Pi-hole that's gone: says so ({m.pihole_says()})")
check(m.list_hints()[0] == ("A", "Try again"), f"...A: try again ({m.list_hints()})")
snap("6_gone")
m.press("a")
check(m.pihole.error is None or wait_for(lambda: m.pihole.error == "not answering"), "...asked again")

# Forget, with Y twice
m.press("y")
check(m.msg == "Press Y again to forget your Pi-hole" and saved() is not None, f"Y: press it again ({m.msg!r})")
m.press("y")
check(saved() is None and rows() == [("Add your Pi-hole", "")] and not m.pihole.running,
      f"...forgotten: static/pihole.txt gone, Add your Pi-hole again ({rows()})")

# Pi-hole 5, a Pi-hole 6 without a password, one with two-factor sign-in
m.press("a"); typed(FIVE)
check(wait_for(lambda: m.view == "keys" and "password" in m.kb["title"]), "Pi-hole 5: its password")
typed("five")
check(wait_for(lambda: len(vals()) == 9 and m.pihole.more.get("types")), "...signed in")
check(vals()[:4] == [("Blocking", "On"), ("Total queries", "4,321"), ("Queries blocked", "432"),
                     ("Percentage blocked", "10.0%")] and dict(vals())["Domains on lists"] == "98,765"
      and dict(vals())["Clients"] == "6", f"...its numbers ({vals()})")
more = m.pihole.more
check(len(more["hours"]) == 24 and sum(b for _, _, b in more["hours"]) > 0
      and more["blocked"] == [("ads.example.com", 90), ("tracker.example.net", 40)]
      and more["allowed"][0] == ("github.com", 300)
      and more["clients"] == [("laptop", 2000), ("192.168.1.31", 900)]
      and [k for k, _ in more["types"]] == ["A", "AAAA", "PTR"],
      f"...its last 24 hours and top lists, Pi-hole 5's way ({ {k: v for k, v in more.items() if k != 'hours'} })")
snap("7_five")
blocked_drawn = [c for _, c in FB.last.crop((40, 190, 640, 290)).getcolors(100000)]
check(g.PH_BLOCKED in blocked_drawn and g.PH_ALLOWED in blocked_drawn, "...drawn: allowed and blocked, in the chart")
m.press("y"); m.press("y")
m.press("a"); typed(OPEN6)
check(wait_for(lambda: len(vals()) == 9 and m.pihole.more.get("types")) and m.msg == "Your Pi-hole's added"
      and saved() == {"address": f"http://{OPEN6}", "password": ""},
      f"a Pi-hole 6 without a password: no box for one, straight to its dashboard ({vals()[:2]}, {m.msg!r})")
check(m.pihole.more["blocked"] == [("blocked.example.com", 5)] and m.pihole.more["clients"] == [("192.168.1.9", 50)]
      and sum(a + b for _, a, b in m.pihole.more["hours"]) > 0, "...its dashboard's lists too")
m.press("y"); m.press("y")
m.press("a"); typed(TOTP6)
check(wait_for(lambda: m.view == "keys"), "a Pi-hole with two-factor sign-in: its password...")
typed("anything")
check(wait_for(lambda: m.msg == "Your Pi-hole wants a two-factor code too: use an app password"),
      f"...a two-factor code wanted: an app password, it says ({m.msg!r})")
m.close_keyboard(False)
m.press("a"); typed(BUSY6)
check(wait_for(lambda: m.view == "keys"), "a Pi-hole with as many signed in as it allows: its password...")
typed("anything")
check(wait_for(lambda: m.msg == "Your Pi-hole has too many signed in: try again in a while"),
      f"...says so ({m.msg!r})")

# B: back, and it stops asking
m.press("b")
time.sleep(1.2)
check(m.tab == hai and not m.pihole.running, "B: back to the Home Assistant menu, and it stops asking")
real("DELETE", "/api/auth", sid=admin)                 # (the test's own sign-in, ended)
print("ALL OK" if not fails else f"FAILED {len(fails)}", flush=True)
os._exit(0)
