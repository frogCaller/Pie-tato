"""PiE-ink first: gpi-media asks a PiE-ink on the network for the weather, coin prices and charts it
has already fetched, and the internet only for the rest (PiE-ink's miners, which it also shares, aren't
gpi-media's). A pretend PiE-ink (new and old), a pretend internet that counts what it's asked."""
import io, json, os, shutil, sys, threading, time, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t70"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Pictures")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("dirs"):
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
import gk_static; gk_static.use_home(g, HOME)
g.CAM_PORTS = (5061,)
g.CAM_LINKS = []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- a pretend PiE-ink ----------------------------------------------------------------------------------
PORTLAND = (45.5152, -122.6784)
today = time.strftime("%Y-%m-%d")
days5 = [{"date": time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * i)), "code": [2, 61, 3, 0, 1][i],
          "hi": [66, 60, 62, 70, 71][i], "lo": [50, 48, 49, 52, 53][i], "rain": [10, 80, 30, 0, 5][i],
          "sunrise": "07:19", "sunset": "18:23"} for i in range(5)]
PIE = {"mode": "new", "slow": 0, "asked": []}


def shared(weather_age=120, at=PORTLAND, units="F", coin_age=100, graph_age=300, duco_age=20, who="someone"):
    return {"ok": True, "version": "3.0.0",
            "weather": {"lat": at[0], "lon": at[1], "units": units, "place": "Portland, Oregon", "country": "US",
                        "age": weather_age,
                        "data": {"temp": 61.2 if units == "F" else 16.2, "feels": 60.0, "humidity": 70, "wind": 5.0,
                                 "wind_dir": 250, "code": 2, "is_day": True, "precip": 0, "units": units,
                                 "days": days5, "tz": "America/Los_Angeles"},
                        "nws": [["Tonight", "Partly cloudy, with a low around 50."],
                                ["Thursday", "Rain likely. Cloudy, with a high near 60."]], "nws_age": 600},
            "coins": [{"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "age": coin_age,
                       "data": {"price": 64000.5, "ath": 73000, "ath_date": "2024-03-14", "from_ath": -12.3,
                                "market_cap": 1.26e12, "rank": 1, "total_supply": 21e6, "circulating_supply": 19.7e6,
                                "sentiment_up": 81.5, "high_24h": 65000, "low_24h": 63000,
                                "change": {"24h": 1.5, "7d": 3.0, "30d": None, "200d": None, "1y": 40.0}},
                       "graph_days": 7, "graph": [63000.0 + i * 5 for i in range(169)], "graph_age": graph_age}],
            "mining": {"duco": {"enabled": True, "who": who, "kind": "duco", "symbol": "DUCO", "running": True,
                                "error": None, "fetched_ago": duco_age, "line": 0.0, "alert": None,
                                "data": {"balance": 12.5, "paid": None, "trust_score": 5,
                                         "miners": [{"identifier": "esp32-a", "hashrate": 160.0, "pool": "magi"},
                                                    {"identifier": "pi-zero", "hashrate": 90.0, "pool": "magi"}],
                                         "pools": ["magi"], "hashrate": 250.0, "price": 0.00012,
                                         "net_hashrate": "1.2 GH/s", "luck": "", "per_day": 1.234, "age": duco_age,
                                         "kind": "duco", "symbol": "DUCO", "decimals": 3}}}}


PIE["shared"] = shared()


class PieInk(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # (it gave up waiting)

    def do_GET(self):
        PIE["asked"].append(self.path)
        if PIE["slow"]:
            time.sleep(PIE["slow"])
        mode = PIE["mode"]
        if self.path == "/api/shared":
            if mode == "new":
                return self.reply(200, PIE["shared"])
            if mode == "garbage":
                return self.reply(200, PIE["garbage"])
            if mode == "huge":
                return self.reply(200, b'{"ok": true, "x": "' + b"a" * 4_000_000 + b'"}')
            if mode == "broken":
                return self.reply(500, {"ok": False, "error": "oops"})
            return self.reply(404, {"ok": False, "error": "not found"})
        if self.path == "/api/mining" and mode == "old":
            return self.reply(200, {"ok": True, "pools": PIE["shared"]["mining"]})
        if self.path == "/api/ptz":
            return self.reply(200, {"ok": True, "available": True, "position": {}, "follow": {}, "sleep": {}})
        self.reply(404, {"ok": False})


srv = ThreadingHTTPServer(("127.0.0.1", 5061), PieInk)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# ---- a pretend internet ----------------------------------------------------------------------------------
NET = []


def fake_json(url, timeout=15):
    NET.append(url)
    if "api.open-meteo.com" in url:
        base = time.strftime("%Y-%m-%dT%H")
        t0 = time.mktime(time.strptime(base, "%Y-%m-%dT%H"))
        times = [time.strftime("%Y-%m-%dT%H:%M", time.localtime(t0 + h * 3600)) for h in range(-2, 30)]
        return {"current": {"time": base + ":30", "temperature_2m": 58.0, "apparent_temperature": 57.0,
                            "relative_humidity_2m": 75, "weather_code": 3, "wind_speed_10m": 7.0,
                            "wind_direction_10m": 200, "is_day": 1, "precipitation": 0},
                "hourly": {"time": times, "temperature_2m": [58.0] * 32, "weather_code": [3] * 32,
                           "precipitation_probability": [20] * 32, "is_day": [1] * 32},
                "daily": {"time": [time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * i)) for i in range(7)],
                          "weather_code": [3] * 7, "temperature_2m_max": [63] * 7, "temperature_2m_min": [49] * 7,
                          "sunrise": ["2026-10-14T07:19"] * 7, "sunset": ["2026-10-14T18:23"] * 7,
                          "precipitation_probability_max": [20] * 7}}
    if "api.weather.gov/points" in url:
        return {"properties": {"forecast": "https://api.weather.gov/gridpoints/PQR/1,1/forecast"}}
    if "api.weather.gov/gridpoints" in url:
        return {"properties": {"periods": [{"name": "Tonight", "detailedForecast": "From the NWS itself."}]}}
    if "ipapi.co" in url:
        return {"latitude": 40.0, "longitude": -100.0, "city": "Internetville", "region": "Kansas", "country_code": "US"}
    raise OSError("offline: " + url)


g.fetch_json = fake_json


def fake_gecko(self, url, gecko=False):
    NET.append(url)
    if "/market_chart" in url:
        return {"prices": [[i, 100.0 + i] for i in range(50)]}
    if "/coins/" in url:
        cid = url.split("/coins/")[1].split("?")[0]
        return {"symbol": cid[:3], "name": cid.title(), "market_cap_rank": 9,
                "market_data": {"current_price": {"usd": 1.25}, "ath": {"usd": 2.0}, "market_cap": {"usd": 1e9},
                                "high_24h": {"usd": 1.3}, "low_24h": {"usd": 1.2}, "circulating_supply": 1e6,
                                "price_change_percentage_24h": 0.5}}
    raise OSError("offline: " + url)


g.Crypto.get_json = fake_gecko


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


shots = []


def since(n):
    return [u.split("?")[0] for u in NET[n:]]


def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


open(HOME + "/crypto.txt", "w").write("coins = bitcoin, ethereum\nduco = someone\nstocks =\n")   # (Finance's coins)
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("location", {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.52, "lon": -122.68})
pie, wx, cr = m.pie, m.weather, m.crypto

# ---- finding it -------------------------------------------------------------------------------------------
check(f"nobody to ask yet: {pie.candidates()}", pie.candidates() == ([], set()) and pie.ask() is None and not pie.known())
beacon = json.dumps({"pie": 1, "id": "abc", "host": "pie-shop", "port": 5061, "version": "3.0.0", "mode": "crypto",
                     "caps": {"camera": False}}).encode()
m.camera.heard("127.0.0.1", beacon)
check(f"its beacon: it's there (even with no camera): {pie.candidates()}",
      pie.candidates() == (["http://127.0.0.1:5061"], set()) and pie.known())
check("...and it isn't listed as a camera", not m.camera.found)
pie.heard.clear()
pie.answer = (0.0, None)
open(HOME + "/camera.txt", "w").write("camera = 127.0.0.1:5061   Garage\ncamera = http://127.0.0.1:5999/stream  Porch\n")
check(f"a camera in camera.txt may be one (not a link with a path), a guess: {pie.candidates()}",
      pie.candidates() == (["http://127.0.0.1:5061"], {"127.0.0.1:5061"}))
pie.remembered = {"url": "http://127.0.0.1:5062", "host": "other"}
check("...only when there's no PiE-ink it knows of", pie.candidates() == (["http://127.0.0.1:5062"], set()))
pie.remembered = None
os.remove(HOME + "/camera.txt")
open(HOME + "/pieink.txt", "w").write("pieink = 127.0.0.1:5061\n")
check(f"pieink.txt names it: {pie.candidates()}", pie.candidates() == (["http://127.0.0.1:5061"], set()))
for v, want in (("192.168.1.30", "http://192.168.1.30:5000"), ("http://pie.local:5001/", "http://pie.local:5001"),
                ("not an address!", None), ("http://192.168.1.30:5000/stream", None)):
    check(f"...an address: {v!r} -> {g.pie_addr(v)}", g.pie_addr(v) == want)

# ---- the weather: PiE-ink's, on the home screen --------------------------------------------------------------
n = len(NET)
wx.refresh()
check("home screen: asked, and taken", wait(lambda: not wx.busy and wx.src))
d = wx.data
check(f"PiE-ink's forecast, the internet not asked: {since(n)}", since(n) == [] and PIE["asked"][-1] == "/api/shared")
check(f"...as it was: {d['temp']}°{d['units']}, {len(d['days'])} days, no hours, age {time.time() - wx.t:.0f} s",
      d["temp"] == 61.2 and d["units"] == "F" and len(d["days"]) == 5 and d["hours"] == []
      and 115 < time.time() - wx.t < 130 and wx.nws[0][0] == "Tonight")
check(f"...remembered for next time: {pie.remembered}", pie.remembered["url"] == "http://127.0.0.1:5061"
      and g.PieInk().remembered == pie.remembered)
m.view = "home"; m.dirty = True; m.flush()
home_shot = shots[-1]
facts = "\n".join(m.friend_facts())
check("the bot knows it", "Weather now: 61°F, partly cloudy" in facts and "Next few days" in facts)

# the Weather tab wants the hours: it gets the whole forecast itself
n = len(NET)
wi = m.tab_index("weather")
m.tab, m.view = wi, "list"
m.tick()
check("Weather tab: the whole forecast, from the internet", wait(lambda: not wx.busy and wx.data.get("hours")))
check(f"...hours and the week: {since(n)}", since(n)[0].endswith("open-meteo.com/v1/forecast") and len(wx.data["days"]) == 7
      and wx.src == "" and wx.nws[0][1] == "From the NWS itself.")
m.dirty = True; m.flush()
tab_shot = shots[-1]
n = len(NET)
m.tick(); time.sleep(0.3); m.tick()
check("...and not again while it's fresh", since(n) == [] and not wx.busy)

# stale: PiE-ink's again, when it's newer
m.view = "home"
wx.t -= 700; wx.checked = 0
PIE["shared"] = shared(weather_age=30)
pie.answer = (0.0, None)
n = len(NET)
wx.refresh()
check("10 min later: PiE-ink's newer one", wait(lambda: not wx.busy) and wx.src == "PiE-ink" and since(n) == [])
# due, and PiE-ink's is what's here already, not too old: its next one is waited for, not the internet
held = wx.t
wx.checked = 0
PIE["shared"] = shared(weather_age=int(time.time() - held) + 600)
pie.answer = (0.0, None)
wx.t -= 600
PIE["shared"] = shared(weather_age=int(time.time() - wx.t))
n = len(NET)
wx.refresh()
okk = wait(lambda: not wx.busy)
check(f"due, and PiE-ink has nothing newer yet: its next one is waited for ({since(n)})", okk and since(n) == []
      and wx.src == "PiE-ink" and time.time() - wx.checked < 5)
n = len(NET)
wx.refresh()
check("...and it isn't asked again for a minute", not wx.busy and since(n) == [])
# too old: the internet
wx.t -= 700; wx.checked = 0
PIE["shared"] = shared(weather_age=900)
pie.answer = (0.0, None)
n = len(NET)
wx.refresh()
okk = wait(lambda: not wx.busy)
check(f"PiE-ink's is 15 min old: from the internet ({since(n)[:1]})", okk and wx.src == "" and since(n)
      and "open-meteo" in since(n)[0])
# not here
wx.t -= 700; wx.checked = 0
PIE["shared"] = shared(at=(44.0582, -121.3153))           # Bend, 200 km away
pie.answer = (0.0, None)
n = len(NET)
wx.refresh()
check("PiE-ink's is for somewhere else: from the internet", wait(lambda: not wx.busy) and wx.src == ""
      and "open-meteo" in since(n)[0])
# in the other units
PIE["shared"] = shared()
pie.answer = (0.0, None)
m.set_setting("units", "°C"); m.weather_changed()
okk = wait(lambda: not wx.busy and wx.src == "PiE-ink")
check("°C here, °F there: changed over", okk
      and abs(wx.data["temp"] - 16.2) < 0.1 and wx.data["units"] == "C" and abs(wx.data["wind"] - 8.0) < 0.1
      and abs(wx.data["days"][0]["hi"] - 18.9) < 0.1)
m.set_setting("units", "°F"); m.weather_changed()
wait(lambda: not wx.busy)
# PiE-ink doesn't answer
wx.t -= 700; wx.checked = 0
PIE["slow"] = 6
pie.answer = (0.0, None)
n = len(NET)
t0 = time.time()
wx.refresh()
check("PiE-ink too slow: the internet, after a few seconds", wait(lambda: not wx.busy, 20) and "open-meteo" in since(n)[0]
      and time.time() - t0 < 9)
check(f"...and it's left alone for a while: {pie.bad}", pie.bad.get("127.0.0.1:5061", 0) > time.time() + 60)
PIE["slow"] = 0
time.sleep(3.5)                                            # (the slow answers finish)
pie.bad.clear()

# Find me: PiE-ink's place
m.set_setting("location", None); m.weather_changed()
pie.answer = (0.0, None)
m.locate_job(None)
loc = m.setting("location")
check(f"Find me: where PiE-ink is: {loc}", loc and loc["name"] == "Portland" and loc["admin"] == "Oregon"
      and loc["country"] == "US" and loc["lat"] == 45.5152)
wait(lambda: not wx.busy)

# ---- coins and miners -------------------------------------------------------------------------------------
m.fin_load()                                   # (no finance.txt: crypto.txt, its earlier name)
check(f"an old crypto.txt's miner (duco =) is left alone: {cr.cards()}",
      cr.cards() == [("coin", "bitcoin"), ("coin", "ethereum")])
cr.days = 7
PIE["shared"] = shared()
pie.answer = (0.0, None)
n = len(NET)
job = cr.next_job()
check(f"the first job: {job}", job == (("quote", "bitcoin"), 300))
check("bitcoin: PiE-ink's", cr.from_pie(*job) and cr.quotes["bitcoin"]["pie"] and since(n) == [])
q = cr.quotes["bitcoin"]["d"]
check(f"...as the card wants it: {q['symbol']} {q['price']} H {q['high_24h']} 24h {q['change_24h']}% #{q['rank']}",
      q["symbol"] == "BTC" and q["name"] == "Bitcoin" and q["price"] == 64000.5 and q["change_24h"] == 1.5
      and q["rank"] == 1 and q["sentiment_up"] == 81.5 and 95 < time.time() - cr.quotes["bitcoin"]["t"] < 110)
job = cr.next_job()
check(f"next: its 7-day chart: {job}", job == (("hist", "bitcoin", 7), 900) and cr.from_pie(*job)
      and len(cr.hist["bitcoin:7"]["v"]) == 169 and since(n) == [])
job = cr.next_job()
check(f"next: ethereum, which PiE-ink hasn't got: {job}", job == (("quote", "ethereum"), 300) and not cr.from_pie(*job))
cr.days = 1
check("a 1-day chart isn't what it keeps", not cr.from_pie(("hist", "bitcoin", 1), 300))
cr.days = 7
n = len(NET)
before = dict(cr.quotes["bitcoin"])
check("what's here is PiE-ink's newest: waited for (asked again in a minute), not the internet",
      cr.from_pie(("quote", "bitcoin"), 300) and cr.quotes["bitcoin"].get("tried") and since(n) == []
      and cr.quotes["bitcoin"]["t"] == before["t"] and not cr.stale(("quote", "bitcoin"), 300))
# too old, and a forced refresh
PIE["shared"] = shared(coin_age=500)
pie.answer = (0.0, None)
cr.quotes.pop("bitcoin")
check("a quote 8 min old: not taken", not cr.from_pie(("quote", "bitcoin"), 300))
PIE["shared"] = shared(coin_age=330)
pie.answer = (0.0, None)
check("5.5 min old: taken, and asked again in a minute", cr.from_pie(("quote", "bitcoin"), 300)
      and cr.quotes["bitcoin"].get("tried") and not cr.stale(("quote", "bitcoin"), 300))
cr.quotes.pop("bitcoin")
check("X (refresh now): only one from the last minute", not cr.from_pie(("quote", "bitcoin"), 0))
PIE["shared"] = shared(coin_age=20)
pie.answer = (0.0, None)
check("...like this", cr.from_pie(("quote", "bitcoin"), 0))

# the loop itself: bitcoin and its chart from PiE-ink, ethereum from the internet
cr.quotes.clear(); cr.hist.clear()
PIE["shared"] = shared()
pie.answer = (0.0, None)
n = len(NET)
cr.start()
wait(lambda: "ethereum" in cr.quotes and "ethereum:7" in cr.hist and "bitcoin:7" in cr.hist, 30)
cr.stop()
time.sleep(0.5)
got = since(n)
check(f"the Finance tab's coins: the internet asked only for what PiE-ink hasn't got: {got}",
      all("ethereum" in u for u in got) and len(got) == 2 and cr.quotes["bitcoin"].get("pie"))
check("...and never a mining pool", not any("pool" in u or "miner" in u for u in NET))
m.tab, m.view = m.tab_index("finance"), "list"
m.fin_card = 0
m.dirty = True; m.flush()
coin_shot = shots[-1]
m.fin_card = 1
m.dirty = True; m.flush()
eth_shot = shots[-1]

# ---- an older PiE-ink: nothing to share (its miners aren't asked for) ----------------------------------------
PIE["mode"] = "old"
pie.answer = (0.0, None)
pie.bad.clear()
check(f"an older PiE-ink: nothing to share, left alone for an hour ({PIE['asked'][-1]})", pie.ask() is None
      and PIE["asked"][-1] == "/api/shared" and "/api/mining" not in PIE["asked"]
      and pie.bad["127.0.0.1:5061"] > time.time() + 3000)
pie.bad.clear()
# not a PiE-ink at all
PIE["mode"] = "nothing"
pie.answer = (0.0, None)
check("not a PiE-ink: left alone for an hour", pie.ask() is None and pie.bad["127.0.0.1:5061"] > time.time() + 3000)
pie.bad.clear()
PIE["mode"] = "broken"
pie.answer = (0.0, None)
check("a PiE-ink with trouble: a couple of minutes", pie.ask() is None
      and time.time() + 60 < pie.bad["127.0.0.1:5061"] < time.time() + 200)
pie.bad.clear()

# ---- whatever comes back, nothing breaks ------------------------------------------------------------------------
PIE["mode"] = "garbage"
for junk in ([1, 2, 3], {"ok": True, "weather": "rain", "coins": {"a": 1}, "mining": [1]},
             {"ok": True, "weather": {"lat": "x", "data": {}}, "coins": [{"id": "../x", "data": {"price": 1}, "age": 1},
                                                                         {"id": "btc", "data": {"price": float("nan")}, "age": 1},
                                                                         {"id": "eth", "data": {"price": 5}, "age": None}],
              "mining": {"duco": {"who": "someone", "data": {"balance": "lots", "age": 1}}}},
             {"ok": True, "weather": {"lat": 45.5, "lon": -122.6, "units": "K", "age": 1, "data": {"temp": 1}}},
             {"ok": True, "weather": {"lat": 95, "lon": 0, "units": "F", "age": 1, "data": {"temp": 1, "units": "F"}}},
             {"ok": True, "coins": [{"id": "bitcoin", "age": 1, "data": {"price": 1, "rank": True},
                                     "graph": [1, "two", 3], "graph_days": 7, "graph_age": 1}]},
             {"ok": True, "weather": {"lat": 45.52, "lon": -122.68, "units": "C", "age": 0,
                                      "data": {"temp": 1e308, "units": "C", "days": []}}},
             {"ok": True, "weather": {"lat": 45.52, "lon": -122.68, "units": "F", "age": 10 ** 400,
                                      "data": {"temp": 50, "units": "F"}}},
             {"ok": True, "coins": [{"id": "bitcoin", "age": 1, "data": {"price": 1, "rank": 1},
                                     "graph": [1, 1e300, 3], "graph_days": 7, "graph_age": -1e9}]}):
    PIE["garbage"] = junk
    pie.answer = (0.0, None)
    pie.bad.clear()
    try:
        a = pie.ask()
        okay = a is None or (a["weather"] is None and set(a["coins"]) <= {"bitcoin"} and "mining" not in a)
        if a and a["coins"].get("bitcoin"):
            b = a["coins"]["bitcoin"]
            okay = okay and b["graph"] == [] and (b["q"]["rank"] is None or b["q"]["rank"] == 1) \
                and (b["graph_age"] is None or b["graph_age"] >= 0)
    except Exception as ex:
        okay = f"crashed: {ex!r}"
    check(f"junk is left out: {str(junk)[:70]}", okay is True)
PIE["mode"] = "huge"
pie.answer = (0.0, None)
pie.bad.clear()
check("too big an answer: not read", pie.ask() is None)

# ---- a PiE-ink that answers a byte at a time ------------------------------------------------------------------------
import socket as _socket


def drip(port):
    s = _socket.socket(); s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port)); s.listen(5)
    while True:
        c, _ = s.accept()

        def serve(c=c):
            try:
                c.recv(4096)
                c.sendall(b"HTTP/1.1 200 OK\r\n")
                for ch in b"X-Slow: " + b"a" * 1000:
                    c.sendall(bytes([ch])); time.sleep(1.0)
            except OSError:
                pass
        threading.Thread(target=serve, daemon=True).start()


threading.Thread(target=drip, args=(5063,), daemon=True).start()
time.sleep(0.2)
pd = g.PieInk()
pd.candidates = lambda: (["http://127.0.0.1:5063"], set())
t0 = time.time()
done = []
for _ in range(2):
    threading.Thread(target=lambda: done.append((pd.ask(), time.time() - t0)), daemon=True).start()
wait(lambda: len(done) == 2, 20)
check(f"a PiE-ink that answers a byte a second: given up in seconds ({[round(t, 1) for _, t in done]})",
      len(done) == 2 and all(a is None and t < 8 for a, t in done) and pd.bad)

# a real PiE-ink on a poor link: cut off, but asked again in a couple of minutes (not an hour)
def trickle(port):
    s = _socket.socket(); s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port)); s.listen(5)
    body = json.dumps({"ok": True, "coins": []}).encode() + b" " * 40
    while True:
        c, _ = s.accept()

        def serve(c=c):
            try:
                c.recv(4096)
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body))
                for ch in body:
                    c.sendall(bytes([ch])); time.sleep(0.4)
            except OSError:
                pass
        threading.Thread(target=serve, daemon=True).start()


threading.Thread(target=trickle, args=(5064,), daemon=True).start()
time.sleep(0.2)
pt = g.PieInk()
pt.candidates = lambda: (["http://127.0.0.1:5064"], set())
check("a slow PiE-ink: tried again in a couple of minutes, not an hour", pt.ask() is None
      and time.time() + 60 < pt.bad["127.0.0.1:5064"] < time.time() + 200)

PIE["mode"] = "new"
# the PiE-ink it remembers has moved (a new address from the router), and its beacon doesn't reach here:
# camera.txt's address for it is tried in the same question, and remembered instead
pm = g.PieInk(cameras=lambda: ([], ["127.0.0.1:5061"]))
pm.remembered = {"url": "http://127.0.0.1:5998", "host": "pie"}
a = pm.ask()
check(f"it moved: found where camera.txt says ({pm.remembered['url']})", a and pm.remembered["url"] == "http://127.0.0.1:5061"
      and pm.candidates()[0][0] == "http://127.0.0.1:5061")

# a coin down 100% in a day: not a change its card can draw, so it's left out (and the card draws)
PIE["shared"] = shared()
PIE["shared"]["coins"][0]["data"]["change"]["24h"] = -100
pie.answer = (0.0, None); pie.bad.clear()
cr.quotes.pop("bitcoin", None); cr.days = 1
okk = cr.from_pie(("quote", "bitcoin"), 300)
m.tab, m.view, m.fin_card = m.tab_index("finance"), "list", 0
m.dirty = True
try:
    m.flush()
    drew = True
except Exception as ex:
    drew = repr(ex)
check(f"down 100%: left out, and the card draws ({drew})", okk and cr.quotes["bitcoin"]["d"]["change_24h"] is None and drew is True)
cr.quotes["bitcoin"]["d"]["change_24h"] = -100.0                      # (as CoinGecko itself might say of a coin gone to nothing)
m.dirty = True
try:
    m.flush()
    drew = True
except Exception as ex:
    drew = repr(ex)
check(f"...or from the internet ({drew})", drew is True)
cr.days = 7
PIE["shared"] = shared()

# ---- off ----------------------------------------------------------------------------------------------------------
PIE["mode"] = "new"
open(HOME + "/pieink.txt", "w").write("pieink = off\n")
m.camera.heard("127.0.0.1", beacon)
pie.answer = (0.0, None)
pie.bad.clear()
k = len(PIE["asked"])
check("pieink = off: never asked", pie.candidates() == ([], set()) and pie.ask() is None and len(PIE["asked"]) == k
      and not pie.known())
os.remove(HOME + "/pieink.txt")

# ---- nobody known: nobody asked, and no waiting ---------------------------------------------------------------
p3 = g.PieInk()
p3.remembered = None
k = len(PIE["asked"])
t0 = time.time()
check("no PiE-ink known: nothing asked, no waiting", p3.ask() is None and time.time() - t0 < 0.3 and len(PIE["asked"]) == k)
p3.hear("127.0.0.1", json.loads(beacon))
check("...until one is heard", p3.ask() and p3.answer[1]["host"] == "pie-shop")

W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, shot in enumerate([home_shot, tab_shot, coin_shot, eth_shot]):
    sheet.paste(shot, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/pie_share_sheet.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
os._exit(0)
