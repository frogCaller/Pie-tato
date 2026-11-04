"""urllib.request.urlopen stood in for: Yahoo Finance (fakeyahoo) and CoinGecko (made-up coins), and what was asked."""
import io, json, math, time, urllib.error, urllib.parse, urllib.request
import fakeyahoo as Y

ASKED = []
STATE = {"offline": False, "yahoo_down": False, "search_down": None, "gecko": True}
COINS = {
    "bitcoin": dict(name="Bitcoin", symbol="btc", rank=1, price=67234.0, ath=73738.0, mc=1.33e12, supply=19.77e6,
                    vote=72.0, hi=67900.0, lo=66010.0, ch=1.12),
    "ethereum": dict(name="Ethereum", symbol="eth", rank=2, price=2641.5, ath=4878.26, mc=3.18e11, supply=120.4e6,
                     vote=58.0, hi=2690.0, lo=2588.0, ch=-0.84),
    "dogecoin": dict(name="Dogecoin", symbol="doge", rank=8, price=0.1412, ath=0.7316, mc=2.07e10, supply=146.3e9,
                     vote=81.0, hi=0.1450, lo=0.1371, ch=3.4),
    "solana": dict(name="Solana", symbol="sol", rank=5, price=166.2, ath=259.96, mc=7.8e10, supply=470e6,
                   vote=77.0, hi=170.0, lo=161.0, ch=2.1),
}
GECKO_FOUND = {
    "bitcoin": [{"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "market_cap_rank": 1},
                {"id": "bitcoin-cash", "name": "Bitcoin Cash", "symbol": "BCH", "market_cap_rank": 18}],
    "sol": [{"id": "solana", "name": "Solana", "symbol": "SOL", "market_cap_rank": 5}],
    "apple": [{"id": "apple-token", "name": "Apple Token", "symbol": "APT2", "market_cap_rank": None}],
}


class Resp:
    def __init__(self, obj):
        self.b = json.dumps(obj).encode()

    def read(self, n=-1):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def urlopen(req, timeout=None):
    url = req.full_url if hasattr(req, "full_url") else req
    u = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(u.query))
    ASKED.append((u.netloc, u.path, q, dict(req.headers) if hasattr(req, "headers") else {}))
    if STATE["offline"]:
        raise urllib.error.URLError("no network (pretend)")
    if u.netloc in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        yd = STATE["yahoo_down"]
        if yd is True or (yd == "query1" and u.netloc.startswith("query1")):
            raise urllib.error.URLError("down")
        if u.path.startswith("/v8/finance/chart/"):
            sym = urllib.parse.unquote(u.path.rsplit("/", 1)[1])
            code, body = Y.chart(sym, q.get("range"), q.get("interval"))
        elif u.path == "/v1/finance/search":
            if STATE["search_down"]:
                raise urllib.error.HTTPError(url, STATE["search_down"], "no", {}, io.BytesIO(b"{}"))
            code, body = Y.search(q.get("q", ""))
        else:
            code, body = 404, {}
        if code != 200:
            raise urllib.error.HTTPError(url, code, "no", {}, io.BytesIO(json.dumps(body).encode()))
        return Resp(body)
    if u.netloc == "api.coingecko.com":
        if not STATE["gecko"]:
            raise urllib.error.URLError("down")
        if u.path.endswith("/search"):
            return Resp({"coins": GECKO_FOUND.get(q.get("query", "").lower(), [])})
        cid = u.path.split("/coins/")[1].split("/")[0]
        c = COINS.get(cid)
        if c is None:
            raise urllib.error.HTTPError(url, 404, "no", {}, io.BytesIO(b"{}"))
        if u.path.endswith("/market_chart"):
            days = int(q.get("days", 1))
            n = 96 if days == 1 else 168
            return Resp({"prices": [[k, c["price"] * (1 + 0.02 * math.sin(k / 9 + len(cid)) - 0.01 * (n - k) / n)]
                                    for k in range(n)]})
        return Resp({"symbol": c["symbol"], "name": c["name"], "market_cap_rank": c["rank"],
                     "sentiment_votes_up_percentage": c["vote"],
                     "market_data": {"current_price": {"usd": c["price"]}, "ath": {"usd": c["ath"]},
                                     "market_cap": {"usd": c["mc"]}, "circulating_supply": c["supply"],
                                     "high_24h": {"usd": c["hi"]}, "low_24h": {"usd": c["lo"]},
                                     "price_change_percentage_24h": c["ch"]}})
    raise urllib.error.URLError(f"not here: {u.netloc}")


def install():
    urllib.request.urlopen = urlopen
