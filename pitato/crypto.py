"""Coin prices and charts from CoinGecko, for the Finance tab."""
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
from .util import _num, UA


# the Finance tab's coins: the same sources PiE-ink uses, fetched by this Pi itself
COINGECKO = "https://api.coingecko.com/api/v3"
CRYPTO_COINS = [("bitcoin", "BTC", "Bitcoin"), ("ethereum", "ETH", "Ethereum"),
                ("dogecoin", "DOGE", "Dogecoin")]          # when finance.txt hasn't a coins = line
CRYPTO_WINDOWS = [(1, "1D"), (7, "7D"), (30, "30D"), (365, "1Y")]
CRYPTO_GAP = 2.5          # seconds between CoinGecko calls (its free tier is ~10 a minute)
CRYPTO_ROTATE = 20        # seconds per card when Auto is on
CRYPTO_MOST = 20          # coins on the tab, at most
CRYPTO_LINE = 400         # ...and characters in finance.txt's coins = line (what a settings line holds)
CRYPTO_FOUND = 12         # coins a search shows, at most


def price_text(p):
    p = _num(p, None)
    if p is None:
        return "—"
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    if p >= 0.01:
        return f"${p:,.4f}"
    return f"${p:.8f}"


def big_number(n):
    n = _num(n, None)
    if n is None:
        return "—"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= cut:
            return f"{n / cut:.1f}{suffix}"
    return str(int(n))


class Crypto:
    """Coin prices and charts from CoinGecko, fetched on a thread of its own and kept on
    disk — so the tab shows the last numbers it had, with their age, when there's no WiFi."""

    def __init__(self, pie=None):
        self.cfg = {}
        self.pie = pie                # PiE-ink on another Pi: asked first for what it has
        self.coins = [{"id": i, "symbol": s, "name": n} for i, s, n in CRYPTO_COINS]
        self.quotes, self.hist = {}, {}
        self.days = 1
        self.focus = None             # the card on screen: ("coin", id)
        self.force = False
        self.running = False
        self.last_call = 0.0
        self.backoff_until = 0.0
        self.on_change = lambda: None
        self.lock = threading.Lock()
        self.gecko = threading.Lock()  # (CoinGecko is asked one thing at a time, the time between kept)
        self.load_cache()

    # settings
    def ids(self):
        return [c["id"] for c in self.coins]

    def load(self, patterns):
        """The coins = line (CoinGecko ids). No such line: Bitcoin, Ethereum and Dogecoin; an empty one: none."""
        self.cfg = read_config(patterns)
        ids = []
        for c in re.split(r"[,\s]+", self.cfg.get("coins", "").lower()):
            if c.strip() and c.strip() not in ids:
                ids.append(c.strip())
        known = {i: (s, n) for i, s, n in CRYPTO_COINS}
        coins = []
        for cid in ids if "coins" in self.cfg else [c[0] for c in CRYPTO_COINS]:
            q = (self.quotes.get(cid) or {}).get("d") or {}
            sym, name = known.get(cid, (cid[:5].upper(), cid.replace("-", " ").title()))
            coins.append({"id": cid, "symbol": q.get("symbol") or sym, "name": q.get("name") or name})
        self.coins = coins

    def cards(self):
        return [("coin", c["id"]) for c in self.coins]

    def coin(self, cid):
        return next((c for c in self.coins if c["id"] == cid), {"id": cid, "symbol": cid, "name": cid})

    # the disk copy
    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "crypto.json")

    def load_cache(self):
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            self.quotes, self.hist = c.get("quotes", {}), c.get("hist", {})
        except (OSError, ValueError):
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

    # fetching
    def get_json(self, url, gecko=False):
        if not gecko:
            return self.ask(url)
        with self.gecko:
            wait = self.last_call + CRYPTO_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.time()
            return self.ask(url)

    def ask(self, url):
        req = urllib.request.Request(url, headers=dict(UA, Accept="application/json"))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                          # too many calls: wait a minute
                self.backoff_until = time.time() + 60
            raise

    def search(self, text):
        """Coins whose name or symbol fits what you typed, the biggest first (CoinGecko's order):
        [{"id", "symbol", "name", "rank"}]. ValueError: why it couldn't look."""
        if time.time() < self.backoff_until:
            raise ValueError("CoinGecko wants a minute's rest. Try again soon")
        try:
            got = self.get_json(f"{COINGECKO}/search?" + urllib.parse.urlencode({"query": text}), gecko=True)
        except urllib.error.HTTPError as e:
            raise ValueError("CoinGecko wants a minute's rest. Try again soon" if e.code == 429
                             else f"CoinGecko couldn't look it up ({e.code})")
        except (OSError, ValueError, http.client.HTTPException):
            raise ValueError("Can't reach CoinGecko. Is the WiFi on?")
        coins = got.get("coins") if isinstance(got, dict) else None
        found = []
        for c in coins if isinstance(coins, list) else []:
            cid = c.get("id") if isinstance(c, dict) else None
            if isinstance(cid, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", cid.strip().lower()):
                rank = c.get("market_cap_rank")
                found.append({"id": cid.strip().lower(), "symbol": clean_name(c.get("symbol") or "", 12).upper(),
                              "name": clean_name(c.get("name") or cid, 40),
                              "rank": rank if isinstance(rank, int) and not isinstance(rank, bool) else None})
            if len(found) >= CRYPTO_FOUND:
                break
        return found

    def fetch_quote(self, cid):
        q = urllib.parse.urlencode({"localization": "false", "tickers": "false",
                                    "community_data": "false", "developer_data": "false"})
        d = self.get_json(f"{COINGECKO}/coins/{urllib.parse.quote(cid)}?{q}", gecko=True)
        m = d.get("market_data", {})

        def usd(k):
            return (m.get(k) or {}).get("usd")
        price, ath = usd("current_price"), usd("ath")
        out = {"symbol": (d.get("symbol") or "").upper(), "name": d.get("name") or cid,
               "price": price, "ath": ath, "market_cap": usd("market_cap"),
               "rank": d.get("market_cap_rank"), "circulating_supply": m.get("circulating_supply"),
               "sentiment_up": d.get("sentiment_votes_up_percentage"),
               "high_24h": usd("high_24h"), "low_24h": usd("low_24h"),
               "change_24h": m.get("price_change_percentage_24h")}
        with self.lock:
            self.quotes[cid] = {"t": time.time(), "d": out}
        c = self.coin(cid)
        if c in self.coins:
            c["symbol"], c["name"] = out["symbol"] or c["symbol"], out["name"]

    def fetch_hist(self, cid, days):
        d = self.get_json(f"{COINGECKO}/coins/{urllib.parse.quote(cid)}/market_chart?"
                          + urllib.parse.urlencode({"vs_currency": "usd", "days": days}), gecko=True)
        with self.lock:
            self.hist[f"{cid}:{days}"] = {"t": time.time(), "v": [p[1] for p in d.get("prices", [])]}

    # what to fetch next: the card on screen first
    def stale(self, key, ttl):
        if time.time() < self.backoff_until:
            return False                               # CoinGecko said slow down
        e = self.quotes.get(key[1]) if key[0] == "quote" else self.hist.get(f"{key[1]}:{key[2]}")
        if ttl and e and time.time() - e.get("tried", 0) < 60:
            return False                               # failed a moment ago: give it a minute
        return not e or time.time() - e.get("t", 0) > ttl

    def next_job(self):
        jobs = []
        kind, what = self.focus or ("coin", self.coins[0]["id"] if self.coins else "")
        hist_ttl = 300 if self.days == 1 else 900
        if kind == "coin" and what:
            jobs += [(("quote", what), 0 if self.force else 300),
                     (("hist", what, self.days), 0 if self.force else hist_ttl)]
        self.force = False
        for c in self.coins:
            jobs += [(("quote", c["id"]), 300), (("hist", c["id"], self.days), hist_ttl)]
        return next(((key, ttl) for key, ttl in jobs if self.stale(key, ttl)), None)

    def from_pie(self, job, ttl):
        """PiE-ink's numbers for a job when it has them and they aren't too old (a little past their
        time is fine: it's asked again in a minute): taken when newer than what's here, or else its
        next ones are waited for, as PiE-ink is keeping them fresh. False: the internet is asked."""
        if self.pie is None:
            return False
        try:
            if job[0] == "quote":
                got, store, key = self.pie.quote(job[1]), self.quotes, job[1]
            else:
                got, store, key = self.pie.chart(job[1], job[2]), self.hist, f"{job[1]}:{job[2]}"
        except Exception:
            return False
        if not got:
            return False
        value, age = got
        now = time.time()
        if age >= (ttl * 1.5 if ttl else 60):
            return False                               # too old: the internet is asked
        held = store.get(key) or {}
        if now - age <= held.get("t", 0) + 1:          # what's here is as new as its: its next is coming
            if ttl:
                with self.lock:
                    store[key] = dict(held, tried=now)   # (asked again in a minute)
            return True
        entry = {"t": now - age, "pie": True}
        if job[0] == "quote":
            q = dict(value)
            c = self.coin(job[1])
            q["symbol"], q["name"] = q["symbol"] or c["symbol"], q["name"] or c["name"]
            entry["d"] = q
            if c in self.coins:
                c["symbol"], c["name"] = q["symbol"], q["name"]
        else:
            entry["v"] = value
        if age >= ttl:
            entry["tried"] = now                      # already due: PiE-ink is asked again in a minute
        with self.lock:
            store[key] = entry
        return True

    def start(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self.loop, daemon=True, name="crypto").start()

    def stop(self):
        self.running = False

    def loop(self):
        while self.running:
            got = self.next_job()
            if not got:
                time.sleep(1)
                continue
            job, ttl = got
            try:
                if self.from_pie(job, ttl):
                    pass                               # PiE-ink had it: the internet isn't asked
                elif job[0] == "quote":
                    self.fetch_quote(job[1])
                else:
                    self.fetch_hist(job[1], job[2])
                self.save_cache()
            except Exception:
                # keep the old numbers (and their age); try again in a minute
                with self.lock:
                    store = self.quotes if job[0] == "quote" else self.hist
                    key = job[1] if job[0] == "quote" else f"{job[1]}:{job[2]}"
                    store[key] = dict(store.get(key) or {}, tried=time.time())
                time.sleep(2)
            self.on_change()
