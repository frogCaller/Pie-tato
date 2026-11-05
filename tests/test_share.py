"""Your Pietatos sharing what they fetch (nearby.py, media.py's share_loop and web_shared, webui.py's /api/shared): one
says it's there on the network every few seconds, as PiE-ink does, and shares its coins' and stocks' prices and charts
and the weather (its hours too); another hears it (not itself), asks it, and takes what's newer than its own; when
what it has is no newer, the one that's due fetches it (the others a little later: by then they find it there), and a
PiE-ink is still waited for, as it keeps its own fresh. Settings > Share with other Pietatos: Off stops it both ways.
/api/shared answers your network only, with no password."""
import json, os, shutil, socket, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tshare"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
sys.path.insert(0, TESTS)
import pietato_all as g
import importlib

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
N = importlib.import_module("pitato.nearby")
MEDIA = importlib.import_module("pitato.media")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


a, b = g.Media(), g.Media()
now = time.time()
check(f"each its own name for itself ({a.share_id}, {b.share_id})", a.share_id != b.share_id and len(a.share_id) == 12
      and a.pie.own == a.share_id and a.setting("share") == "On")

# ---- what one has fetched ------------------------------------------------------------------------------------------
a.crypto.quotes = {"bitcoin": {"t": now - 40, "d": {"symbol": "BTC", "name": "Bitcoin", "price": 101234.5, "ath": 126000,
                                                     "market_cap": 2.0e12, "rank": 1, "circulating_supply": 1.98e7,
                                                     "sentiment_up": 77.0, "high_24h": 102000, "low_24h": 99000,
                                                     "change_24h": 2.3}},
                   "dogecoin": {"t": now - 3 * 3600, "d": {"symbol": "DOGE", "name": "Dogecoin", "price": 0.2}}}
a.crypto.hist = {"bitcoin:1": {"t": now - 50, "v": [100000.0, 100500.0, 101234.5]},
                 "bitcoin:7": {"t": now - 400, "v": [95000.0, 98000.0, 101000.0]}}
a.stocks.quotes = {"AAPL": {"t": now - 20, "d": {"symbol": "AAPL", "name": "Apple Inc.", "price": 231.5, "prev_close": 229.0,
                                                  "change_1d": 1.09, "currency": "USD", "kind": "EQUITY", "gmtoffset": -14400,
                                                  "open_at": now - 3600, "close_at": now + 3600, "time": now - 30}}}
a.stocks.hist = {"AAPL:1": {"t": now - 25, "v": [229.0, 230.0, 231.5]}}
LOC = {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.52, "lon": -122.68}
a.set_setting("location", LOC)
a.weather.data = {"temp": 61.0, "feels": 60.0, "humidity": 70, "wind": 5.0, "wind_dir": 180, "code": 3, "is_day": True,
                  "units": "F", "hours": [{"time": "2026-10-31T15:00", "temp": 62.0, "code": 3, "rain": 10, "is_day": True}],
                  "days": [{"date": "2026-10-31", "code": 3, "hi": 64.0, "lo": 50.0, "rain": 20, "sunrise": "07:45",
                            "sunset": "18:05"}]}
a.weather.t = now - 100
out = a.web_shared()
body = json.dumps(out).encode()
check(f"what it shares: its coins (not one fetched long ago), stocks, the weather ({[c['id'] for c in out['coins']]}, "
      f"{[s['symbol'] for s in out['stocks']]})", out["ok"] and out["from"] == "pietato" and out["id"] == a.share_id
      and [c["id"] for c in out["coins"]] == ["bitcoin"] and [s["symbol"] for s in out["stocks"]] == ["AAPL"]
      and out["weather"]["place"] == "Portland, Oregon" and out["weather"]["data"]["hours"])
btc = out["coins"][0]
check("...a coin as PiE-ink shares one (its newest chart), and each of its charts",
      btc["graph_days"] == 1 and btc["graph"] == [100000.0, 100500.0, 101234.5] and btc["data"]["change"]["24h"] == 2.3
      and sorted(x["days"] for x in btc["graphs"]) == [1, 7] and 39 <= btc["age"] <= 45)

# ---- heard, and asked ------------------------------------------------------------------------------------------------
A_URL = "http://192.168.1.77:5432"
asks = []


def get(url):
    asks.append(url)
    if url == A_URL + "/api/shared":
        return 200, body
    raise OSError("nobody there")


b.pie.get = get
b.pie.cameras = lambda: ([], [])
check("before it's heard: no other Pietato", not b.pie.peers() and b.pie.have("coin", "bitcoin") is None)
b.camera.heard("192.168.1.50", json.dumps({"pietato": 1, "id": b.share_id, "port": 5432, "host": "me"}).encode())
check("its own beacon: not another's", not b.pie.peers())
b.camera.heard("192.168.1.77", json.dumps({"pietato": 1, "id": a.share_id, "port": 5432, "host": "kitchen"}).encode())
check(f"another's: heard (by the Camera tab's listener), not taken for a camera ({list(b.pie.heard)}, "
      f"{b.camera.found_list()})", b.pie.peers() and A_URL in b.pie.heard and b.pie.heard[A_URL]["peer"]
      and b.camera.found_list() == [])
check("...one that doesn't say its colour (an older one): none", b.pie.peer_accent(A_URL) is None)
said = a.share_beacon("kitchen")
check(f"a beacon says its colour, Settings > Accent colour ({said})", said == {"pietato": 1, "id": a.share_id,
      "port": 5432, "host": "kitchen", "accent": "Blue"})
a.set_setting("accent", "Purple")
b.camera.heard("192.168.1.77", json.dumps(a.share_beacon("kitchen")).encode())
check(f"...heard: its colour, for a dot beside its name ({b.pie.peer_accent(A_URL)})",
      b.pie.peer_accent(A_URL) == dict(g.ACCENTS)["Purple"])
a.set_setting("accent", "Blue")
b.camera.heard("192.168.1.78", json.dumps({"pietato": 1, "id": "other1", "port": 5432, "host": "kitchen",
                                           "accent": "Chartreuse"}).encode())
check("...not one of the colours: none", b.pie.peer_accent("http://192.168.1.78:5432") is None)
b.camera.heard("192.168.1.78", json.dumps({"pietato": 1, "id": "other1", "port": 5432, "host": "kitchen",
                                           "accent": ["Gold"]}).encode())
check("...nor anything else", b.pie.peer_accent("http://192.168.1.78:5432") is None)
check(f"two of the same name: the end of their addresses after it, by name ({b.saves_peers()})",
      b.saves_peers() == [(A_URL, "kitchen (.77)"), ("http://192.168.1.78:5432", "kitchen (.78)")])
del b.pie.heard["http://192.168.1.78:5432"]
check(f"...one: its name alone ({b.saves_peers()})", b.saves_peers() == [(A_URL, "kitchen")])
b.pie.answer = (0.0, None)
got = b.pie.have("coin", "bitcoin")
check(f"asked: its coin, how old, that it's another Pietato's ({got and (got[0]['price'], round(got[1]), got[2])})",
      got and got[0]["price"] == 101234.5 and got[0]["symbol"] == "BTC" and 39 <= got[1] <= 46 and got[2] is True
      and asks == [A_URL + "/api/shared"])
check("...its charts, each window", b.pie.have("coin_chart", "bitcoin", 7)[0] == [95000.0, 98000.0, 101000.0]
      and b.pie.have("coin_chart", "bitcoin", 1)[0][-1] == 101234.5 and b.pie.have("coin_chart", "bitcoin", 30) is None)
check("...the old way still (PiE-ink's): quote and chart", b.pie.quote("bitcoin")[0]["price"] == 101234.5
      and b.pie.chart("bitcoin", 1)[0][-1] == 101234.5)
st = b.pie.have("stock", "AAPL")
check(f"...its stocks ({st and (st[0]['price'], st[0]['name'])})", st and st[0]["price"] == 231.5 and st[2]
      and b.pie.have("stock_chart", "AAPL", 1)[0] == [229.0, 230.0, 231.5])

# ---- taken, or fetched -------------------------------------------------------------------------------------------------
b.crypto.quotes, b.crypto.hist = {}, {}
check("a coin: taken from it (newer than what's here)", b.crypto.from_pie(("quote", "bitcoin"), 300)
      and b.crypto.quotes["bitcoin"]["d"]["price"] == 101234.5 and abs(b.crypto.quotes["bitcoin"]["t"] - (now - 40)) < 3)
check("...its chart", b.crypto.from_pie(("hist", "bitcoin", 7), 900) and b.crypto.hist["bitcoin:7"]["v"][0] == 95000.0)
check("...no newer than what's here: this one fetches it (for both), it isn't waited for",
      b.crypto.from_pie(("quote", "bitcoin"), 300) is False)
b.crypto.quotes["bitcoin"]["t"] = now - 1000
check("...a newer one there again: taken", b.crypto.from_pie(("quote", "bitcoin"), 300))
b.crypto.late = 30
b.crypto.quotes["bitcoin"]["t"] = time.time() - 310
check("with another about: due a little later than its time (whichever's due first fetches)",
      not b.crypto.stale(("quote", "bitcoin"), 300))
b.crypto.quotes["bitcoin"]["t"] = time.time() - 340
check("...then due", b.crypto.stale(("quote", "bitcoin"), 300))
b.stocks.quotes, b.stocks.hist = {}, {}
check("a stock: taken from it", b.stocks.from_peer(("quote", "AAPL"), 60) and b.stocks.quotes["AAPL"]["d"]["price"] == 231.5
      and b.stocks.from_peer(("hist", "AAPL", 1), 60) and b.stocks.hist["AAPL:1"]["v"][-1] == 231.5)
check("...no newer: Yahoo's asked", b.stocks.from_peer(("quote", "AAPL"), 60) is False)
b.set_setting("location", dict(LOC, lat=45.53))
b.weather.data, b.weather.t = None, 0.0
key = b.weather.key()
check("the weather, for somewhere close: taken, its hours too (so the Weather tab's as well)",
      b.weather.from_pie(key, b.setting("location"), "F", full=True) and b.weather.data["hours"][0]["temp"] == 62.0
      and b.weather.src == "Pietato" and abs(b.weather.t - (now - 100)) < 3)
check("...in your units", b.weather.from_pie(key, b.setting("location"), "C", full=True) is False
      or round(b.pie.weather(b.setting("location"), "C")["data"]["temp"], 1) == 16.1)

# a PiE-ink, as ever: its next is waited for
pie_body = json.dumps({"ok": True, "coins": [dict(btc, graphs=None)], "weather": None}).encode()
b.pie.get = lambda url: (200, pie_body)
b.pie.answer = (0.0, None)
b.crypto.quotes["bitcoin"]["t"] = now - 40
check("a PiE-ink's: no newer than what's here, its next is waited for (it keeps its own fresh)",
      b.crypto.from_pie(("quote", "bitcoin"), 300) is True and b.crypto.quotes["bitcoin"].get("tried"))
b.pie.get = get
b.pie.answer, b.pie.remembered = (0.0, None), None      # (that was a PiE-ink at that address, for a moment)
b.pie.have("coin", "bitcoin")
check("another Pietato remembered as one", b.pie.remembered == {"url": A_URL, "host": "kitchen", "peer": True})

# ---- off ---------------------------------------------------------------------------------------------------------------
a.set_setting("share", "Off")
check("Settings > Share with other Pietatos, Off: nothing shared", a.web_shared() == {"ok": False,
                                                                                     "error": "Sharing is off"})
b.set_setting("share", "Off")
check("...nor asked for", not b.pie.peers() and b.pie.candidates()[0] == [] and b.pie.have("coin", "bitcoin") is None)
b.pie.heard.clear()
b.camera.heard("192.168.1.77", json.dumps({"pietato": 1, "id": a.share_id, "port": 5432}).encode())
check("...nor heard", not b.pie.heard)
a.set_setting("share", "On"); b.set_setting("share", "On")

# ---- it says it's there ---------------------------------------------------------------------------------------------------
lis = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
lis.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
lis.bind(("", 0))
port = lis.getsockname()[1]
lis.settimeout(3)
MEDIA.CAM_BEACON, MEDIA.PEER_SAYS = port, 0.3
a.share_start()
heard = []
try:
    while len(heard) < 2:
        data, _ = lis.recvfrom(4096)
        heard.append(json.loads(data))
except OSError:
    pass
a.sharing = False
check(f"it says it's there, again and again ({heard[:1]})", len(heard) >= 2 and heard[0]["pietato"] == 1
      and heard[0]["id"] == a.share_id and heard[0]["port"] == 5432 and heard[0]["host"])

# ---- the web page: your network only, no password -----------------------------------------------------------------------
W = importlib.import_module("pitato.webui")
W.ask_pi = lambda method, path, **k: (200, json.dumps(a.web_shared()).encode(), "application/json") \
    if path == "/shared" else None
W.settings = lambda: {"password": "secret"}
c = W.app.test_client()
r = c.get("/api/shared", headers={"Host": "192.168.1.77:5432"}, environ_base={"REMOTE_ADDR": "192.168.1.20"})
check(f"/api/shared from your network: answered, no password asked ({r.status_code})", r.status_code == 200
      and r.get_json()["from"] == "pietato" and r.headers["Cache-Control"] == "no-store")
r = c.get("/api/shared", headers={"Host": "192.168.1.77:5432"}, environ_base={"REMOTE_ADDR": "8.8.8.8"})
check(f"...from outside it: no ({r.status_code})", r.status_code == 403)
r = c.get("/api/pi/state", headers={"Host": "192.168.1.77:5432", "X-Pitato-Page": "1"},
          environ_base={"REMOTE_ADDR": "192.168.1.20"})
check(f"...the rest of the page still asks for the password ({r.status_code})", r.status_code == 401)
check("...IPv6 on your network too", W.on_my_network("fe80::1") and W.on_my_network("::ffff:10.0.0.4")
      and not W.on_my_network("2001:4860::8888") and not W.on_my_network("nonsense"))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
