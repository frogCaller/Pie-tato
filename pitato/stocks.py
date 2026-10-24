"""Stock prices and charts from Yahoo Finance: its public chart and search addresses (no sign-up), fetched by
this Pi itself, a little at a time."""
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import CACHE_DIR, clean_name, read_config
from .util import _num

YAHOO = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")   # (the other if one won't answer)
YAHOO_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) pitato/1.0", "Accept": "application/json"}
STOCKS = [("AAPL", "Apple Inc."), ("AMZN", "Amazon.com, Inc."), ("TSLA", "Tesla, Inc.")]   # when finance.txt
STOCK_CHARTS = {1: ("5d", "5m"), 7: ("5d", "15m"), 30: ("1mo", "60m"), 365: ("1y", "1d")}  # hasn't a stocks = line
STOCK_GAP = 0.6           # seconds between calls to Yahoo
STOCKS_MOST = 20          # stocks on the tab, at most
STOCKS_FOUND = 8          # ...and that a search shows
STOCKS_LINE = 400         # characters in finance.txt's stocks = line
SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9.^=_-]{0,19}")    # a ticker as Yahoo writes it: AAPL, BRK-B, ^GSPC, 7203.T
STOCK_KINDS = {"EQUITY": "", "ETF": "ETF", "INDEX": "Index", "MUTUALFUND": "Fund"}   # (what a search may add)
CURRENCY = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "INR": "₹", "KRW": "₩", "CAD": "CA$",
            "AUD": "A$", "HKD": "HK$", "NZD": "NZ$", "SGD": "S$", "BRL": "R$", "MXN": "MX$", "TWD": "NT$"}


def money(v, currency="USD", kind=""):
    """A price as it's written where it's traded: $235.86, €41.20, ¥2,861, 512.40p (pence); an index's
    points without a currency."""
    v = _num(v, None)
    if v is None:
        return "—"
    dec = 0 if currency in ("JPY", "KRW") else (2 if abs(v) >= 1 else 4)
    num = f"{v:,.{dec}f}"
    if kind == "INDEX" or not currency:
        return num
    if currency in ("GBp", "GBX"):
        return num + "p"
    sign = CURRENCY.get(currency)
    return sign + num if sign else f"{num} {currency}"


def market_open(q, now=None):
    """Whether its market's open (its regular hours), as of when its price came."""
    now = time.time() if now is None else now
    a, b = _num(q.get("open_at"), None), _num(q.get("close_at"), None)
    return a is not None and b is not None and a <= now < b


def last_day(points, gmtoffset=0, gap=7200):
    """Of (time, price) points over several days: the last day's trading. That's all of the last one's day (by
    the market's own clock: a stock seldom traded can go hours without a price), and before it, back to a break
    of over two hours (a market open past midnight; a lunch break is shorter), 24 hours at most (one that never
    closes)."""
    if not points:
        return []
    end = points[-1][0]
    day = (end + gmtoffset) // 86400
    out = [points[-1]]
    for p in reversed(points[:-1]):
        if end - p[0] > 86400 or (out[-1][0] - p[0] > gap and (p[0] + gmtoffset) // 86400 != day):
            break
        out.append(p)
    return out[::-1]


class StockError(Exception):
    """Why Yahoo hasn't a stock's prices: what to say."""


class Stocks:
    """Stock prices and charts from Yahoo Finance, fetched on a thread of its own and kept on disk, so the
    Finance tab shows the last numbers it had, with their age, when there's no WiFi."""

    def __init__(self):
        self.stocks = [{"symbol": s, "name": n} for s, n in STOCKS]
        self.quotes, self.hist = {}, {}
        self.days = 1
        self.focus = None             # the card on screen: ("stock", symbol)
        self.force = False
        self.running = False
        self.last_call = 0.0
        self.backoff_until = 0.0
        self.on_change = lambda: None
        self.lock = threading.Lock()
        self.gate = threading.Lock()  # (Yahoo is asked one thing at a time, a moment apart)
        self.load_cache()

    # settings
    def symbols(self):
        return [s["symbol"] for s in self.stocks]

    def load(self, patterns):
        """The stocks = line of finance.txt: tickers, as Yahoo writes them. No such line: Apple, Amazon and
        Tesla; an empty one: none."""
        cfg = read_config(patterns)
        if "stocks" in cfg:
            syms = []
            for s in re.split(r"[,\s]+", cfg["stocks"].upper()):
                if SYMBOL.fullmatch(s) and s not in syms:
                    syms.append(s)
        else:
            syms = [s for s, _ in STOCKS]
        known = dict(STOCKS)
        self.stocks = [{"symbol": s, "name": ((self.quotes.get(s) or {}).get("d") or {}).get("name")
                        or known.get(s, s)} for s in syms]

    def cards(self):
        return [("stock", s["symbol"]) for s in self.stocks]

    def stock(self, sym):
        return next((s for s in self.stocks if s["symbol"] == sym), {"symbol": sym, "name": sym})

    # the disk copy
    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "stocks.json")

    def load_cache(self):
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            self.quotes, self.hist = c.get("quotes", {}), c.get("hist", {})
        except (OSError, ValueError, AttributeError):
            pass

    def save_cache(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with self.lock:
                data = json.dumps({"quotes": self.quotes, "hist": self.hist})
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    # asking Yahoo
    def get_json(self, path, query):
        """GET path?query from Yahoo (one call at a time, a moment apart; its second address if the first
        won't answer). HTTPError for an answer that isn't a yes; OSError and the like for no answer."""
        with self.gate:
            wait = self.last_call + STOCK_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.time()
            for k, base in enumerate(YAHOO):
                req = urllib.request.Request(f"{base}{path}?{urllib.parse.urlencode(query)}", headers=YAHOO_UA)
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        return json.load(r)
                except urllib.error.HTTPError as e:
                    if e.code == 429:                  # too many calls: a minute's rest
                        self.backoff_until = time.time() + 60
                    if e.code not in (401, 403, 429, 500, 502, 503) or k == len(YAHOO) - 1:
                        raise
                except (OSError, ValueError, http.client.HTTPException):
                    if k == len(YAHOO) - 1:
                        raise

    def chart(self, sym, rng, interval):
        """Yahoo's chart for a stock: (its meta: price, day's high and low, ..., [(time, price)]).
        StockError: Yahoo hasn't it."""
        try:
            got = self.get_json(f"/v8/finance/chart/{urllib.parse.quote(sym, safe='')}",
                                {"range": rng, "interval": interval, "includePrePost": "false"})
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise StockError(f"Yahoo Finance has no prices for {sym}")
            raise
        res = ((got or {}).get("chart") or {}).get("result") if isinstance(got, dict) else None
        if not isinstance(res, list) or not res or not isinstance(res[0], dict):
            raise StockError(f"Yahoo Finance has no prices for {sym}")
        r = res[0]
        meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        times = r.get("timestamp") or []
        quote = ((r.get("indicators") or {}).get("quote") or [{}])[0] or {}
        closes = quote.get("close") or []
        points = [(int(t), float(c)) for t, c in zip(times, closes)
                  if isinstance(t, (int, float)) and isinstance(c, (int, float)) and not isinstance(c, bool)]
        return meta, points

    def search(self, text):
        """Stocks, funds and indexes whose name or ticker fits what you typed (Yahoo's order):
        [{"id", "symbol", "name", "where"}]. If Yahoo's search won't answer, what you typed as a ticker, if it
        is one. ValueError: why it couldn't look."""
        if time.time() < self.backoff_until:
            raise ValueError("Yahoo Finance wants a minute's rest. Try again soon")
        try:
            got = self.get_json("/v1/finance/search", {"q": text, "quotesCount": 12, "newsCount": 0,
                                                       "listsCount": 0, "enableFuzzyQuery": "false"})
        except (OSError, ValueError, http.client.HTTPException) as ex:
            typed = text.strip().upper()
            if isinstance(ex, urllib.error.HTTPError) and ex.code != 429 and SYMBOL.fullmatch(typed):
                # (its search turned you away: the ticker as typed, if Yahoo has prices for it)
                try:
                    meta, _ = self.chart(typed, "1d", "1d")
                    if _num(meta.get("regularMarketPrice"), None) is not None:
                        return [self.found_row(meta.get("symbol") or typed, meta.get("longName")
                                               or meta.get("shortName"), meta.get("instrumentType"),
                                               meta.get("fullExchangeName") or meta.get("exchangeName"))]
                except (StockError, OSError, ValueError, http.client.HTTPException):
                    pass
            if isinstance(ex, urllib.error.HTTPError) and ex.code == 429:
                raise ValueError("Yahoo Finance wants a minute's rest. Try again soon")
            raise ValueError("Can't reach Yahoo Finance. Is the WiFi on?"
                             if not isinstance(ex, urllib.error.HTTPError)
                             else f"Yahoo Finance couldn't look it up ({ex.code})")
        quotes = got.get("quotes") if isinstance(got, dict) else None
        found = []
        for q in quotes if isinstance(quotes, list) else []:
            if not isinstance(q, dict) or q.get("isYahooFinance") is False:
                continue
            sym = str(q.get("symbol") or "").strip().upper()
            kind = q.get("quoteType")
            if kind not in STOCK_KINDS or not SYMBOL.fullmatch(sym) or sym in [f["id"] for f in found]:
                continue
            found.append(self.found_row(sym, q.get("longname") or q.get("shortname"), kind,
                                        q.get("exchDisp") or q.get("exchange")))
            if len(found) >= STOCKS_FOUND:
                break
        return found

    @staticmethod
    def found_row(sym, name, kind, where):
        kind_word = STOCK_KINDS.get(kind, "")
        return {"id": sym, "symbol": sym, "name": clean_name(name or sym, 40),
                "where": kind_word or clean_name(where or "", 16)}

    def fetch_quote(self, sym):
        """A stock's price, its day so far (and the chart of it, once the market's opened), and the rest."""
        meta, points = self.chart(sym, "1d", "5m")
        period = ((meta.get("currentTradingPeriod") or {}).get("regular") or {})
        price = _num(meta.get("regularMarketPrice"), None)
        prev = _num(meta.get("previousClose"), None)
        prev = prev if prev is not None else _num(meta.get("chartPreviousClose"), None)
        out = {"symbol": str(meta.get("symbol") or sym).upper(),
               "name": clean_name(meta.get("longName") or meta.get("shortName") or self.stock(sym)["name"], 60),
               "price": price, "prev_close": prev,
               "change_1d": (price - prev) / prev * 100 if price is not None and prev else None,
               "high_1d": _num(meta.get("regularMarketDayHigh"), None),
               "low_1d": _num(meta.get("regularMarketDayLow"), None),
               "volume": _num(meta.get("regularMarketVolume"), None),
               "high_52w": _num(meta.get("fiftyTwoWeekHigh"), None),
               "low_52w": _num(meta.get("fiftyTwoWeekLow"), None),
               "currency": clean_name(meta.get("currency") or "", 8), "kind": meta.get("instrumentType") or "",
               "exchange": clean_name(meta.get("fullExchangeName") or meta.get("exchangeName") or "", 24),
               "time": _num(meta.get("regularMarketTime"), None), "tz": clean_name(meta.get("timezone") or "", 8),
               "gmtoffset": int(_num(meta.get("gmtoffset"), 0)),
               "open_at": _num(period.get("start"), None), "close_at": _num(period.get("end"), None)}
        if price is None:
            raise StockError(f"Yahoo Finance has no price for {sym}")
        now = time.time()
        with self.lock:
            self.quotes[sym] = {"t": now, "d": out}
            day = last_day(points, out["gmtoffset"])
            if len(day) >= 2:                          # the day so far: its 1D chart too
                self.hist[f"{sym}:1"] = {"t": now, "v": [p for _, p in day]}
        s = self.stock(sym)
        if s in self.stocks:
            s["name"] = out["name"]

    def fetch_hist(self, sym, days):
        rng, interval = STOCK_CHARTS.get(days, STOCK_CHARTS[1])
        meta, points = self.chart(sym, rng, interval)
        if days == 1:                                  # (before the market opens: the day before)
            points = last_day(points, int(_num(meta.get("gmtoffset"), 0)))
        with self.lock:
            self.hist[f"{sym}:{days}"] = {"t": time.time(), "v": [p for _, p in points]}

    # what to fetch next: the card on screen first
    def ttl(self, key):
        e = self.quotes.get(key[1]) or {}
        q, now = e.get("d") or {}, time.time()
        end = _num(q.get("close_at"), None)            # (just closed: soon again, for the closing price)
        closing = end is not None and end <= now < end + 900 and e.get("t", 0) < end + 120
        live = market_open(q, now) or closing if q else True
        if key[0] == "quote" or key[2] == 1:
            return 60 if live else 600
        return (600 if live else 1800) if key[2] == 7 else (1800 if live else 3600)

    def stale(self, key, ttl):
        if time.time() < self.backoff_until:
            return False                               # Yahoo said slow down
        e = self.quotes.get(key[1]) if key[0] == "quote" else self.hist.get(f"{key[1]}:{key[2]}")
        if ttl and e and time.time() - e.get("tried", 0) < 60:
            return False                               # failed a moment ago: give it a minute
        return not e or time.time() - e.get("t", 0) > ttl

    def next_job(self):
        jobs = []
        kind, what = self.focus or ("stock", self.stocks[0]["symbol"] if self.stocks else "")
        if kind == "stock" and what:
            for key in (("quote", what), ("hist", what, self.days)):
                jobs.append((key, 0 if self.force else self.ttl(key)))
        self.force = False
        for s in self.stocks:
            for key in (("quote", s["symbol"]), ("hist", s["symbol"], self.days)):
                jobs.append((key, self.ttl(key)))

        def wanted(key):                           # (no chart asked for while its price can't be had)
            q = self.quotes.get(key[1]) or {}
            return key[0] == "quote" or q.get("d") or not q.get("err")
        return next(((key, ttl) for key, ttl in jobs if wanted(key) and self.stale(key, ttl)), None)

    def error_of(self, sym):
        """Why there are no prices for it, if the last try said why."""
        return (self.quotes.get(sym) or {}).get("err")

    def start(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self.loop, daemon=True, name="stocks").start()

    def stop(self):
        self.running = False

    def loop(self):
        while self.running:
            got = self.next_job()
            if not got:
                time.sleep(1)
                continue
            job, _ = got
            err = None
            try:
                if job[0] == "quote":
                    self.fetch_quote(job[1])
                else:
                    self.fetch_hist(job[1], job[2])
                self.save_cache()
            except StockError as ex:
                err = str(ex)
            except Exception:
                err = "Can't reach Yahoo Finance. Is the WiFi on?"
            if err:                                    # the old numbers kept (and their age); again in a minute
                with self.lock:
                    store = self.quotes if job[0] == "quote" else self.hist
                    key = job[1] if job[0] == "quote" else f"{job[1]}:{job[2]}"
                    store[key] = dict(store.get(key) or {}, tried=time.time(), err=err)
                time.sleep(2)
            self.on_change()
