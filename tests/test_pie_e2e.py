"""gpi-media against a real PiE-ink (mock panel, port 5062) with /api/shared: the contract between them."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t71"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
sys.path.insert(0, TESTS)
import pietato_all as g
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
ok_all = []
def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)

open(HOME + "/pieink.txt", "w").write("# the PiE-ink\npieink = 127.0.0.1:5062\n")
p = g.PieInk()
a = p.ask()
check(f"asked: {a and sorted(a)} (its miners aren't read)", a and a["weather"] and a["coins"] and "mining" not in a
      and not hasattr(p, "miner"))
w = p.weather({"lat": 45.52, "lon": -122.68}, "F")
check(f"its weather for here: {w and w['data']['temp']}°, {w and len(w['data']['days'])} days, age {w and round(w['age'])}",
      w and w["data"]["temp"] == 61.2 and len(w["data"]["days"]) == 5 and w["age"] < 30 and w["nws"][0][0] == "Tonight"
      and w["data"]["days"][1]["hi"] == 65 and w["data"]["days"][2]["rain"] == 20)
wc = p.weather({"lat": 45.52, "lon": -122.68}, "C")
check(f"...in °C: {wc and wc['data']['temp']}", wc and wc["data"]["temp"] == 16.2 and wc["data"]["units"] == "C")
check("...not for somewhere 200 km off", p.weather({"lat": 44.06, "lon": -121.32}, "F") is None)
pl = p.place()
check(f"Find me: {pl}", pl == {"name": "Portland", "admin": "Oregon", "country": "US", "lat": 45.5152, "lon": -122.6784})
q = p.quote("bitcoin")
check(f"bitcoin: {q and q[0]['symbol']} {q and q[0]['price']} age {q and round(q[1])}",
      q and q[0]["symbol"] == "BTC" and q[0]["name"] == "Bitcoin" and q[0]["change_24h"] == 1.5 and q[1] < 30)
c = p.chart("bitcoin", 7)
check(f"...its week: {c and len(c[0])} prices", c and len(c[0]) == 169 and c[1] < 30)
check("...not a day's (it keeps a week)", p.chart("bitcoin", 1) is None)
v = p.quote("verus-coin")
check(f"a coin it has, though not on its watchlist: {v and v[0]['price']}", v and v[0]["price"] == 2.5)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
