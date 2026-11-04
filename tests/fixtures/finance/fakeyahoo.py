"""A pretend Yahoo Finance for the tests: its chart and search answers, made up but shaped as Yahoo's, for a
few stocks and an index, in a market that's open or closed (MARKET["open"]), at a made-up time."""
import math
import random
import time

ET = -4 * 3600                                     # (New York in October: EDT)
MARKET = {"open": True, "premarket": False, "now": None}   # (premarket: today's session not started yet)
INFO = {
    "AAPL": dict(name="Apple Inc.", ex="NasdaqGS", disp="NASDAQ", kind="EQUITY", price=235.86, prev=233.42,
                 hi52=237.49, lo52=164.08, vol=38_846_578, seed=1),
    "AMZN": dict(name="Amazon.com, Inc.", ex="NasdaqGS", disp="NASDAQ", kind="EQUITY", price=187.43, prev=189.07,
                 hi52=201.20, lo52=118.35, vol=29_412_300, seed=2),
    "TSLA": dict(name="Tesla, Inc.", ex="NasdaqGS", disp="NASDAQ", kind="EQUITY", price=217.97, prev=213.65,
                 hi52=278.98, lo52=138.80, vol=80_441_224, seed=3),
    "MSFT": dict(name="Microsoft Corporation", ex="NasdaqGS", disp="NASDAQ", kind="EQUITY", price=427.51, prev=424.60,
                 hi52=468.35, lo52=324.39, vol=15_002_100, seed=4),
    "^GSPC": dict(name="S&P 500", ex="SNP", disp="SNP", kind="INDEX", price=5851.20, prev=5853.98,
                  hi52=5878.46, lo52=4103.78, vol=0, seed=5),
    "SPY": dict(name="SPDR S&P 500 ETF Trust", ex="NYSEArca", disp="NYSEArca", kind="ETF", price=583.32,
                prev=583.63, hi52=586.12, lo52=409.21, vol=34_000_000, seed=6),
    "7203.T": dict(name="Toyota Motor Corporation", ex="Tokyo", disp="Tokyo", kind="EQUITY", price=2617.0,
                   prev=2590.5, hi52=3891.0, lo52=2183.0, vol=21_500_000, seed=7, cur="JPY", gmt=9 * 3600, tz="JST"),
}


def now():
    return MARKET["now"] or time.time()


def session(day_offset=0):
    """(open, close) of a weekday's regular session, day_offset days back (ignoring weekends: made up)."""
    t = now()
    if MARKET["open"]:                                 # (open now: the session started 3 hours ago)
        start = t - 3 * 3600 - day_offset * 86400
    else:                                              # (closed: it ended 2 hours ago)
        start = t - 8.5 * 3600 - day_offset * 86400
    return int(start), int(start + 6.5 * 3600)


def series(sym, start, end, step, last):
    rnd = random.Random(INFO[sym]["seed"] * 1000 + int(start) // 86400)
    n = max(1, int((end - start) // step) + 1)
    vals, v = [], last
    for _ in range(n):
        vals.append(v)
        v -= rnd.gauss(0, last * 0.002) + math.sin(len(vals) / 7) * last * 0.0008
    vals.reverse()
    vals[-1] = last
    return [int(start + k * step) for k in range(n)], [round(x, 2) for x in vals]


def chart(sym, rng, interval):
    """Yahoo's /v8/finance/chart answer for sym."""
    info = INFO.get(sym)
    if info is None:
        return 404, {"chart": {"result": None, "error": {"code": "Not Found",
                                                         "description": "No data found, symbol may be delisted"}}}
    step = {"5m": 300, "15m": 900, "60m": 3600, "1d": 86400}[interval]
    days = {"1d": 1, "5d": 5, "1mo": 22, "1y": 252}[rng]
    t = now()
    times, closes = [], []
    if interval == "1d":
        times, closes = series(sym, t - days * 86400 * 1.45, t, 86400, info["price"])
    elif rng == "1d" and MARKET["premarket"]:
        pass                                            # (nothing yet today)
    else:
        first = 1 if MARKET["premarket"] else 0
        for back in range(days - 1 + first, first - 1, -1):
            a, b = session(back)
            if back == 0 and MARKET["open"]:
                b = min(b, t)                           # (today's: so far)
            tt, cc = series(sym, a, b, step, info["price"] if back == 0 else info["prev"] * (1 + 0.004 * back))
            times += tt
            closes += cc
    a, b = session(0)
    meta = {"currency": info.get("cur", "USD"), "symbol": sym, "exchangeName": info["ex"][:3].upper(),
            "fullExchangeName": info["ex"], "instrumentType": info["kind"], "firstTradeDate": 345479400,
            "regularMarketTime": int(min(t, b) if MARKET["open"] else b), "hasPrePostMarketData": True,
            "gmtoffset": info.get("gmt", ET), "timezone": info.get("tz", "EDT"),
            "exchangeTimezoneName": "America/New_York",
            "regularMarketPrice": info["price"], "fiftyTwoWeekHigh": info["hi52"], "fiftyTwoWeekLow": info["lo52"],
            "regularMarketDayHigh": round(max(info["price"], info["prev"]) * 1.006, 2),
            "regularMarketDayLow": round(min(info["price"], info["prev"]) * 0.994, 2),
            "regularMarketVolume": info["vol"], "longName": info["name"], "shortName": info["name"][:20],
            "chartPreviousClose": info["prev"] if rng == "1d" else round(info["prev"] * 0.97, 2),
            "priceHint": 2, "scale": 3, "dataGranularity": interval, "range": rng,
            "currentTradingPeriod": {"pre": {"timezone": "EDT", "start": a - 19800, "end": a, "gmtoffset": ET},
                                     "regular": {"timezone": "EDT", "start": a, "end": b, "gmtoffset": ET},
                                     "post": {"timezone": "EDT", "start": b, "end": b + 14400, "gmtoffset": ET}},
            "validRanges": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]}
    if rng == "1d":
        meta["previousClose"] = info["prev"]
    return 200, {"chart": {"result": [{"meta": meta, "timestamp": times,
                                       "indicators": {"quote": [{"close": closes, "open": closes, "high": closes,
                                                                 "low": closes, "volume": [1000] * len(times)}]}}],
                           "error": None}}


def search(q):
    ql = q.lower()
    hits = [dict(exchange=i["ex"][:3].upper(), shortname=i["name"][:20], quoteType=i["kind"], symbol=s,
                 index="quotes", score=1000, typeDisp=i["kind"].title(), longname=i["name"], exchDisp=i["disp"],
                 isYahooFinance=True)
            for s, i in INFO.items() if ql in i["name"].lower() or ql == s.lower() or ql in s.lower()]
    if ql == "bitcoin":                                # (Yahoo has coins too: they're left to CoinGecko)
        hits = [dict(symbol="BTC-USD", shortname="Bitcoin USD", quoteType="CRYPTOCURRENCY", exchDisp="CCC",
                     isYahooFinance=True),
                dict(symbol="IBIT", longname="iShares Bitcoin Trust ETF", quoteType="ETF", exchDisp="NASDAQ",
                     isYahooFinance=True),
                dict(symbol="news-thing", name="Not Yahoo's", isYahooFinance=False)] + hits
    return 200, {"explains": [], "count": len(hits), "quotes": hits, "news": [], "nav": [], "lists": []}
