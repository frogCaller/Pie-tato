import io, os, sys, time, json, shutil, math, urllib.parse, urllib.error
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t11"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
g.PLEX_FILE = S + "/plex.json"; g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.CRYPTO_GAP = 0.05
WALLET = "RTestWallet1234"
with open(S + "/crypto.txt", "w") as f:
    f.write(f"# coins from coingecko.com\ncoins = bitcoin, ethereum, verus-coin\nduco = someone\nverus = {WALLET}\n"
            "stocks =\n")                          # (the Finance tab's coins only, here)
# (an older crypto.txt had miners in it: they're left alone now, and no pool is asked)
os.makedirs(S + "/cache", exist_ok=True)
with open(S + "/cache/crypto.json", "w") as f:
    json.dump({"quotes": {}, "hist": {}, "mines": {"duco": {"t": 1, "d": {}}}, "samples": {"duco": [[1, 2]]}}, f)
ci = next(i for i, t in enumerate(g.LIBRARY) if t["type"] == "finance")
g.LIBRARY[ci]["files"] = [S + "/crypto.txt"]

COINS = {
    "bitcoin": dict(name="Bitcoin", symbol="btc", rank=1, price=62890.0, ath=73738.0, mc=1.24e12,
                    supply=19.75e6, vote=68.0, hi=63350.0, lo=61420.0, ch=1.84),
    "ethereum": dict(name="Ethereum", symbol="eth", rank=2, price=2435.12, ath=4878.26, mc=2.93e11,
                     supply=120.3e6, vote=41.0, hi=2510.0, lo=2401.0, ch=-2.31),
    "verus-coin": dict(name="Verus", symbol="vrsc", rank=742, price=0.3812, ath=17.5, mc=29.4e6,
                       supply=77.1e6, vote=None, hi=0.39, lo=0.37, ch=0.4),
}
calls = []
pools = []
fail = {"on": False}


class Resp:
    def __init__(self, obj): self.b = json.dumps(obj).encode()
    def read(self, n=-1): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def series(cid, days):
    c = COINS[cid]
    n = {1: 288, 7: 168, 30: 720, 365: 366}[days]
    end = c["price"]
    start = end / (1 + c["ch"] / 100) if days == 1 else end * (0.9 if days == 7 else 0.8 if days == 30 else 1.6)
    out = []
    for i in range(n):
        f = i / (n - 1)
        wob = math.sin(i / 9.0) * 0.006 + math.sin(i / 31.0 + days) * 0.012
        out.append([1700000000000 + i * 60000, (start + (end - start) * f) * (1 + wob * (1 - f))])
    out[-1][1] = end
    return out


def fake_urlopen(req, timeout=10):
    url = req.full_url if hasattr(req, "full_url") else req
    calls.append(url)
    if fail["on"]:
        raise OSError("no wifi")
    u = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(u.query)
    parts = u.path.split("/")
    if u.netloc == "api.coingecko.com" and u.path.endswith("/market_chart"):
        return Resp({"prices": series(parts[-2], int(q["days"][0]))})
    if u.netloc == "api.coingecko.com" and "/coins/" in u.path:
        c = COINS[parts[-1]]
        return Resp({"name": c["name"], "symbol": c["symbol"], "market_cap_rank": c["rank"],
                     "sentiment_votes_up_percentage": c["vote"],
                     "market_data": {"current_price": {"usd": c["price"]}, "ath": {"usd": c["ath"]},
                                     "market_cap": {"usd": c["mc"]}, "circulating_supply": c["supply"],
                                     "high_24h": {"usd": c["hi"]}, "low_24h": {"usd": c["lo"]},
                                     "price_change_percentage_24h": c["ch"]}})
    if u.netloc != "api.coingecko.com":           # (a mining pool, or anywhere else: never asked now)
        pools.append(url)
    raise OSError("unexpected " + url)


g.urllib.request.urlopen = fake_urlopen
shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


feet = {}
foot = {}


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last
    feet[name] = dict(foot)


def wait_for(c, t=10):
    e = time.time() + t
    while time.time() < e:
        if c(): return True
        time.sleep(0.05)
    return False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
_footer, _key = m.footer, m.key


def spy_footer(d, items, right=None, credit=None):          # what the footer was asked to show
    foot.clear(); foot.update(n=len(items), credit=credit, right=right, drawn=0, lit=[])
    return _footer(d, items, right=right, credit=credit)


def spy_key(d, x, y, label, on=False):                        # and what it drew
    foot["drawn"] = foot.get("drawn", 0) + 1
    if on:
        foot.setdefault("lit", []).append(label)
    return _key(d, x, y, label, on)


m.footer, m.key = spy_footer, spy_key
print("strip:", [g.LIBRARY[i]["name"] for i in m.visible_tabs()])
while g.LIBRARY[m.tab]["name"] != "Finance":
    m.press("r")
cr = m.crypto
print("on:", g.LIBRARY[m.tab]["name"], "running:", cr.running, "cards:", cr.cards())
snap("waiting")
assert wait_for(lambda: "bitcoin:1" in cr.hist and "bitcoin" in cr.quotes)
snap("btc_1d")
m.press("up")                                   # 7D
assert wait_for(lambda: "bitcoin:7" in cr.hist)
snap("btc_7d")
m.press("down")                                 # back to 1D
m.press("right")
assert wait_for(lambda: "ethereum:1" in cr.hist and "ethereum" in cr.quotes)
snap("eth_1d")
m.press("right")
assert wait_for(lambda: "verus-coin:1" in cr.hist)
snap("vrsc")
print("the cards: coins only, with an old crypto.txt's miners left alone:", cr.cards())
assert cr.cards() == [("coin", "bitcoin"), ("coin", "ethereum"), ("coin", "verus-coin")], cr.cards()

# cache on disk, then offline with old numbers
assert wait_for(lambda: os.path.exists(g.CACHE_DIR + "/crypto.json"))
print("cache keys:", sorted(json.load(open(g.CACHE_DIR + "/crypto.json"))))
fail["on"] = True
m.press("right")                                # wraps to bitcoin
print("card after wrap:", cr.focus)
with cr.lock:
    cr.quotes["bitcoin"]["t"] -= 3600
    cr.hist["bitcoin:1"]["t"] -= 3600
n0 = len(calls)
m.press("x")
time.sleep(1.0)
print("calls while offline:", len(calls) - n0, "| tried set:", "tried" in cr.quotes["bitcoin"])
snap("offline")
age = time.time() - cr.quotes["bitcoin"]["t"]
print("bitcoin age kept: %d min" % (age // 60))
n1 = len(calls); time.sleep(1.5)
print("retries in the next 1.5s (should be 0 for bitcoin):",
      len([c for c in calls[n1:] if "bitcoin" in c]))

# auto rotate
fail["on"] = False
m.press("a"); print("auto:", m.fin_auto, m.msg)
snap("btc_auto")
# with a wider font (no DejaVu on the Pi, say) the credit stays and the last hints make way
from PIL import ImageFont
m.fonts["small"], keep_small = ImageFont.truetype(g.FONT, 20), m.fonts["small"]
snap("wide_font")
m.fonts["small"] = keep_small
m.fin_next = 0; m.tick(); print("auto moved to:", cr.focus)
m.press("a")

# a new Media reads the disk copy before any network
cr2 = g.Crypto()
print("fresh from disk:", sorted(cr2.quotes), "| no miners kept:", sorted(json.load(open(g.CACHE_DIR + "/crypto.json"))))
assert sorted(json.load(open(g.CACHE_DIR + "/crypto.json"))) == ["hist", "quotes"]
assert not pools and not hasattr(cr, "mines"), pools

# leaving the tab stops the thread
m.press("r"); print("R ->", g.LIBRARY[m.tab]["name"], "| crypto running:", cr.running)
time.sleep(1.2)
alive = [t.name for t in __import__("threading").enumerate() if t.name == "crypto"]
print("crypto thread alive after leaving:", bool(alive))

# not set up: the default coins
os.remove(S + "/crypto.txt")
cr3 = g.Crypto(); cr3.load([S + "/crypto.txt"]); print("defaults:", cr3.cards())

# the credit: CoinGecko's numbers say so, as clearly as the hints, with every hint still there
for name in ("btc_1d", "btc_7d", "eth_1d", "vrsc", "offline", "waiting", "btc_auto"):
    f = feet[name]
    print(f"footer {name:9s} credit={f['credit']!r:26s} hints {f['drawn']}/{f['n']} lit={f['lit']}")
    assert f["credit"] == "Source: CoinGecko" and f["drawn"] == f["n"], (name, f)
    assert f["lit"] == (["A"] if name == "btc_auto" else []), (name, f)
f = feet["wide_font"]
print("wide font:", f)
assert f["credit"] == "Source: CoinGecko" and 0 < f["drawn"] < f["n"], f

W, H = 640, 480
order = ["btc_1d", "btc_7d", "eth_1d", "vrsc", "offline", "waiting", "btc_auto", "wide_font"]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 4 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/crypto_tab.png")
print("saved")

print("ALL OK")   # (got here: every assert above held)
