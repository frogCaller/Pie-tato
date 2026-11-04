"""The Finance tab (was Crypto): stocks from Yahoo Finance beside the coins (a pretend Yahoo and CoinGecko,
finance/fakenet.py): finance.txt's stocks = and coins = lines (no line: the defaults; an empty one: none; crypto.txt,
its earlier name, read till there's a finance.txt), a stock's price and day (one call: its quote and its 1D chart),
the other charts' ranges, before the market opens, the market closed, a ticker Yahoo hasn't got, Yahoo's second
address, no internet, Yahoo saying slow down; the card (on the GPi and a TV), the list (Y): looking up stocks and
coins at once, adding (finance.txt made from crypto.txt), removing, none left of a kind; the bot; the home screen;
and setup.sh moving crypto.txt across."""
import json, os, random, re, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/finance")
sys.path.insert(0, SP)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import fakenet, fakeyahoo as Y
fakenet.install()
import pietato_all as g
import gk_static

S = SP + "/tfinance"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"
g.home_dir = lambda: HOME
g.settings_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
gk_static.use_home(g, HOME)
g.STOCK_GAP = 0.01; g.CRYPTO_GAP = 0.01
FIN, OLD = HOME + "/finance.txt", HOME + "/crypto.txt"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def wait_for(c, t=10):
    e = time.time() + t
    while time.time() < e:
        if c():
            return True
        time.sleep(0.03)
    return bool(c())


def asked(path_part=""):
    return [(h, p, q) for h, p, q, _ in fakenet.ASKED if path_part in p]


def reset_net():
    fakenet.ASKED.clear()
    fakenet.STATE.update(offline=False, yahoo_down=False, search_down=None, gecko=True)
    Y.MARKET.update(open=True, premarket=False, now=None)


# ---- finance.txt ---------------------------------------------------------------------------------------------
st, cr = g.Stocks(), g.Crypto()
st.load([FIN]); cr.load([FIN])
check(f"no finance.txt: Apple, Amazon and Tesla, and Bitcoin, Ethereum and Dogecoin ({st.symbols()}, {cr.ids()})",
      st.symbols() == ["AAPL", "AMZN", "TSLA"] and cr.ids() == ["bitcoin", "ethereum", "dogecoin"]
      and st.stock("AAPL")["name"] == "Apple Inc.")
open(FIN, "w").write("stocks = aapl, brk-b, ^gspc, no/way, AAPL\ncoins =\n")
st.load([FIN]); cr.load([FIN])
check(f"its lines: tickers as Yahoo writes them (not twice, not a broken one); an empty line: none "
      f"({st.symbols()}, {cr.ids()})", st.symbols() == ["AAPL", "BRK-B", "^GSPC"] and cr.ids() == [])
os.remove(FIN)

# ---- a stock's numbers -----------------------------------------------------------------------------------------
reset_net()
st = g.Stocks()
st.fetch_quote("AAPL")
q = st.quotes["AAPL"]["d"]
calls = fakenet.ASKED[:]
check(f"a stock's price: one call, its quote and its day's chart ({[(h, p, a) for h, p, a, _ in calls]})",
      len(calls) == 1 and calls[0][0] == "query1.finance.yahoo.com" and calls[0][1] == "/v8/finance/chart/AAPL"
      and calls[0][2] == {"range": "1d", "interval": "5m", "includePrePost": "false"}
      and len(st.hist["AAPL:1"]["v"]) >= 2)
check(f"...asked as a browser asks ({calls[0][3].get('User-agent')!r})", calls[0][3].get("User-agent", "").startswith("Mozilla/5.0"))
check(f"...its numbers: {q['name']}, {q['price']} from {q['prev_close']} ({q['change_1d']:+.3f}%), "
      f"{q['currency']}, {q['exchange']}, vol {q['volume']}, 52w {q['low_52w']}-{q['high_52w']}",
      q["name"] == "Apple Inc." and q["price"] == 235.86 and q["prev_close"] == 233.42
      and abs(q["change_1d"] - (235.86 - 233.42) / 233.42 * 100) < 1e-9 and q["currency"] == "USD"
      and q["exchange"] == "NasdaqGS" and q["kind"] == "EQUITY" and q["volume"] == 38846578
      and q["high_52w"] == 237.49 and q["low_52w"] == 164.08 and q["high_1d"] and q["low_1d"]
      and q["tz"] == "EDT" and q["gmtoffset"] == -14400)
check("...its market open now", g.market_open(q))
for days, want in ((7, ("5d", "15m")), (30, ("1mo", "60m")), (365, ("1y", "1d")), (1, ("5d", "5m"))):
    fakenet.ASKED.clear()
    st.fetch_hist("AAPL", days)
    got = asked("/chart/")
    check(f"...its {days}-day chart: {got[0][2]['range']} of {got[0][2]['interval']} ({len(st.hist[f'AAPL:{days}']['v'])} points)",
          (got[0][2]["range"], got[0][2]["interval"]) == want and len(st.hist[f"AAPL:{days}"]["v"]) >= 2)
Y.MARKET["premarket"] = True
st2 = g.Stocks()
st2.fetch_quote("TSLA")
check("before the market opens: the price, and no day's chart from it yet", st2.quotes["TSLA"]["d"]["price"] == 217.97
      and "TSLA:1" not in st2.hist)
st2.fetch_hist("TSLA", 1)
meta, pts = st2.chart("TSLA", "5d", "5m")
day = g.last_day(pts, meta["gmtoffset"])
check(f"...the 1D chart: the day before's, out of five ({len(st2.hist['TSLA:1']['v'])} points of {len(pts)})",
      st2.hist["TSLA:1"]["v"] == [p for _, p in day] and 2 <= len(day) < len(pts))
# a day's trading, out of several days' prices (times in UTC, from a midnight)
D0, HR = 20000 * 86400, 3600
def sess(day, a, b, step=300):                     # (a session from a o'clock to b on that day, a price every step)
    return [(D0 + day * 86400 + int(a * HR) + k * step, 1.0) for k in range(int((b - a) * HR) // step + 1)]
two = sess(-1, 13.5, 20) + sess(0, 13.5, 20)
check("last_day: of two days, the second's", g.last_day(two) == sess(0, 13.5, 20))
seldom = sess(-1, 13.5, 20) + [(D0 + int(t * HR), 1.0) for t in (13.6, 14, 17, 19.5)]
check("...a stock seldom traded (hours without a price): all of its day", g.last_day(seldom) == seldom[-4:])
late = sess(-2, 20, 26.5) + sess(-1, 20, 26.5)
check("...a session past midnight: all of it, not the one before", g.last_day(late) == sess(-1, 20, 26.5))
lunch = sess(-1, 0, 2.5) + sess(-1, 3.5, 6) + sess(0, 0, 2.5) + sess(0, 3.5, 6)
check("...a lunch break: both halves", g.last_day(lunch) == sess(0, 0, 2.5) + sess(0, 3.5, 6))
always = [(D0 - 3 * 86400 + k * 300, 1.0) for k in range(3 * 288 + 1)]
check("...a market that never closes: the last 24 hours", g.last_day(always) == always[-289:])
syd = [(D0 - HR, 1.0), (D0 + 2 * HR, 1.0), (D0 + int(4.5 * HR), 1.0)]   # (Sydney: 10 till 4 there, 11 hours ahead)
check("...by the market's own clock (seldom traded, in Sydney)", g.last_day(syd, 11 * HR) == syd
      and g.last_day(syd) == syd[1:])
Y.MARKET.update(premarket=False, open=False)
st2.fetch_quote("TSLA")
check("the market closed: said so", not g.market_open(st2.quotes["TSLA"]["d"]))
check(f"...and asked less often then (quote every {st2.ttl(('quote', 'TSLA'))} s, open: {st.ttl(('quote', 'AAPL'))} s)",
      st2.ttl(("quote", "TSLA")) == 600 and st.ttl(("quote", "AAPL")) == 60)
Y.MARKET["open"] = True
try:
    st.fetch_quote("ZZZZ")
    nope = None
except g.StockError as ex:
    nope = str(ex)
check(f"a ticker Yahoo hasn't got: it says so ({nope!r})", nope == "Yahoo Finance has no prices for ZZZZ")
fakenet.ASKED.clear()
fakenet.STATE["yahoo_down"] = "query1"
st.fetch_quote("TSLA")
check(f"its first address down: the second ({[h for h, *_ in fakenet.ASKED]})",
      [h for h, *_ in fakenet.ASKED] == ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
      and st.quotes["TSLA"]["d"]["price"] == 217.97)
reset_net()

# Yahoo saying slow down
import io, urllib.error
real = fakenet.urlopen


def busy(req, timeout=None):
    if "finance.yahoo.com" in req.full_url:
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))
    return real(req, timeout)


g.urllib.request.urlopen = busy
st3 = g.Stocks()
try:
    st3.fetch_quote("AAPL")
except Exception:
    pass
check(f"Yahoo says slow down: a minute's rest ({st3.backoff_until - time.time():.0f} s), nothing asked meanwhile",
      55 < st3.backoff_until - time.time() <= 60 and st3.next_job() is None)
try:
    st3.search("apple")
    said = None
except ValueError as ex:
    said = str(ex)
check(f"...a search then: it says so ({said!r})", said == "Yahoo Finance wants a minute's rest. Try again soon")
g.urllib.request.urlopen = fakenet.urlopen

# looking stocks up
reset_net()
found = st.search("apple")
check(f"looking up 'apple': {[(f['id'], f['name'], f['where']) for f in found]}",
      found and found[0]["id"] == "AAPL" and found[0]["name"] == "Apple Inc." and found[0]["where"] == "NASDAQ")
found = st.search("bitcoin")
check(f"...'bitcoin': funds, not Yahoo's coins (they're CoinGecko's) nor what isn't Yahoo's ({[f['id'] for f in found]})",
      [f["id"] for f in found] == ["IBIT"] and found[0]["where"] == "ETF")
found = st.search("s&p")
check(f"...an index: so marked ({[(f['id'], f['where']) for f in found]})", ("^GSPC", "Index") in [(f["id"], f["where"]) for f in found])
fakenet.STATE["search_down"] = 401
fakenet.ASKED.clear()
found = st.search("msft")
check(f"Yahoo's search turns you away: the ticker as typed, if Yahoo has prices for it ({[f['id'] for f in found]})",
      [f["id"] for f in found] == ["MSFT"] and found[0]["name"] == "Microsoft Corporation")
try:
    st.search("microsoft")
    said = None
except ValueError as ex:
    said = str(ex)
check(f"...a name: it says Yahoo couldn't look it up ({said!r})", said == "Yahoo Finance couldn't look it up (401)")
fakenet.STATE.update(search_down=None, offline=True)
fakenet.ASKED.clear()
try:
    st.search("msft")
    said = None
except ValueError as ex:
    said = str(ex)
check(f"no internet: it says so, and doesn't try the ticker too ({said!r}, {len(fakenet.ASKED)} asked)",
      said == "Can't reach Yahoo Finance. Is the WiFi on?" and len(fakenet.ASKED) == 2)
reset_net()

# kept on disk
st.save_cache()
st4 = g.Stocks()
check(f"kept on disk, read back by the next ({sorted(st4.quotes)})", st4.quotes["AAPL"]["d"]["price"] == 235.86
      and "AAPL:1" in st4.hist)

# how they're written
check(f"prices as they're written where they're traded: {[g.money(*a) for a in ((235.86,), (2617, 'JPY'), (512.4, 'GBp'), (5851.2, 'USD', 'INDEX'), (0.1234,), (41.2, 'EUR'), (10.5, 'SEK'))]}",
      [g.money(*a) for a in ((235.86,), (2617, "JPY"), (512.4, "GBp"), (5851.2, "USD", "INDEX"), (0.1234,),
                             (41.2, "EUR"), (10.5, "SEK"))] == ["$235.86", "¥2,617", "512.40p", "5,851.20", "$0.1234",
                                                                "€41.20", "10.50 SEK"])
close = 1760990400                                        # (a Monday, 4:00 PM in New York: 20:00 UTC)
clocks = [g.clock_at(close, -14400, "EDT", now=close + 3600), g.clock_at(close, -14400, "EDT", now=close + 2 * 86400),
          g.clock_at(close, -14400, "EDT", now=close + 10 * 86400)]
check(f"...and when they're from: {clocks}", clocks == ["4:00 PM EDT", "Mon 4:00 PM EDT", "Oct 20"])

# ---- the tab ------------------------------------------------------------------------------------------------
reset_net()
open(OLD, "w").write("# Crypto tab. Coins are CoinGecko ids.\ncoins = bitcoin, solana\nduco = someone\n")


class FB:
    w, h, same = 640, 480, True
    last = None

    def show(self, img):
        FB.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


foot = {}
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
_footer = m.footer


def spy_footer(d, items, right=None, credit=None, plain=False):
    foot.clear(); foot.update(items=[(it[0], it[1]) for it in items], credit=credit)
    return _footer(d, items, right=right, credit=credit, plain=plain)


m.footer = spy_footer
shots = {}


def snap(name):
    m.msg = None
    m.dirty = True; m.flush(); shots[name] = FB.last
    return FB.last


apps = [a for a, _ in m.home_apps()]
check(f"Crypto's Finance now, on the home screen ({apps[10:]})", "Finance" in apps and "Crypto" not in apps)
check("...its icon, and the web page's", m.web_icon("Finance") and m.web_icon("Crypto") is None
      and all(len((f("Finance", 60).convert("RGBA").getcolors(1 << 16) or [])) > 30
              for f in (g.draw_icon, g.draw_glyph, g.draw_bright_icon)))   # (Minimal's outlines: gone)
m.view, m.home_sel = "home", apps.index("Finance")
m.press("a")
check(f"opened: {g.LIBRARY[m.tab]['name']}, crypto.txt read (no finance.txt yet): stocks, then coins ({m.fin_cards()})",
      g.LIBRARY[m.tab]["name"] == "Finance" and m.fin_cards() == [("stock", "AAPL"), ("stock", "AMZN"), ("stock", "TSLA"),
                                                                  ("coin", "bitcoin"), ("coin", "solana")])
check("...both fetching", m.stocks.running and m.crypto.running)
wait_for(lambda: all((m.stocks.quotes.get(s) or {}).get("d") for s in m.stocks.symbols())
         and all((m.crypto.quotes.get(c) or {}).get("d") for c in m.crypto.ids()), 20)
check("...their prices in", all((m.stocks.quotes.get(s) or {}).get("d") for s in m.stocks.symbols())
      and all((m.crypto.quotes.get(c) or {}).get("d") for c in m.crypto.ids()))
snap("stock")
check(f"a stock's card: Y Add fits beside the credit ({foot})", ("Y", "Add") in foot["items"] and ("◀▶", "Next") in foot["items"]
      and foot["credit"] == "Yahoo Finance")
m.press("up")
check(f"▲: 7D for stocks and coins ({m.stocks.days}, {m.crypto.days})", m.stocks.days == m.crypto.days == 7)
wait_for(lambda: m.stocks.hist.get("AAPL:7"), 10)
check(f"...the stock's week fetched ({len((m.stocks.hist.get('AAPL:7') or {}).get('v', []))} points)", m.stocks.hist.get("AAPL:7"))
snap("stock_7d")
m.press("down")
for _ in range(3):
    m.press("right")
check(f"▶ past the stocks: the coins ({m.fin_cards()[m.fin_card]}, focus {m.stocks.focus} / {m.crypto.focus})",
      m.fin_cards()[m.fin_card] == ("coin", "bitcoin") and m.crypto.focus == ("coin", "bitcoin") and m.stocks.focus is None)
snap("coin")
check(f"...a coin's card: CoinGecko's credit ({foot['credit']})", foot["credit"] == "Source: CoinGecko")
m.press("right"); m.press("right")
check(f"...and round again to the first stock ({m.fin_cards()[m.fin_card]})", m.fin_card == 0 and m.stocks.focus == ("stock", "AAPL"))
m.press("a")
m.fin_next = 0; m.tick()
check(f"Auto: on to the next card ({m.fin_cards()[m.fin_card]})", m.fin_auto and m.fin_card == 1)
m.press("a")
n = len(asked("/chart/AMZN"))
m.press("x")
wait_for(lambda: len(asked("/chart/AMZN")) > n, 5)
check("X: the card on screen fetched again at once", len(asked("/chart/AMZN")) > n)

# on a TV: the card, and Yahoo's full credit
TV = type("TV", (FB,), {"w": 960, "h": 540, "same": False})
m.fb = TV()
m.fin_card = 0
snap("tv")
check(f"on a TV: Source: Yahoo Finance, Y Add too ({foot})", foot["credit"] == "Source: Yahoo Finance" and ("Y", "Add") in foot["items"])
m.fb = FB()

# ---- Y: your stocks and coins, and looking up more -----------------------------------------------------------
m.press("y")
kinds = [k for k, _ in m.fin_rows()]
check(f"Y: the search bar, your stocks, your coins ({kinds})", kinds == ["search", "label", "stock", "stock", "stock",
                                                                         "label", "coin", "coin"])
snap("list")
m.press("a")
check(f"A: a box to type in ({m.kb and m.kb['title']!r})", m.view == "keys" and "stock or a coin" in m.kb["title"])
for ch in "msft":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
wait_for(lambda: m.fin_status != "Looking…")
rows = m.fin_rows()
found = [e for k, e in rows if k == "found"]
check(f"'msft': Microsoft found and picked ({[(f['kind'], f['id']) for f in found]}, {m.fin_status})",
      found and found[0]["id"] == "MSFT" and found[0]["kind"] == "stock" and rows[m.fin_sel][1] is found[0]
      and m.fin_status is None)
snap("found")
m.press("a")
txt = open(FIN).read() if os.path.exists(FIN) else ""
check(f"A: added, into a new finance.txt made from crypto.txt (its coins and the rest kept, its own header):\n{txt}",
      m.msg == "Added Microsoft Corporation" and txt.startswith("# Finance: stocks by their tickers")
      and "coins = bitcoin, solana" in txt and "duco = someone" in txt and "stocks = AAPL, AMZN, TSLA, MSFT" in txt
      and "# Crypto tab" not in txt and os.path.exists(OLD))
check(f"...its card next, fetched first ({m.fin_cards()[m.fin_card]}, {m.stocks.focus})",
      m.fin_cards()[m.fin_card] == ("stock", "MSFT") and m.stocks.focus == ("stock", "MSFT"))
wait_for(lambda: (m.stocks.quotes.get("MSFT") or {}).get("d"), 10)
check("...its price in", (m.stocks.quotes.get("MSFT") or {}).get("d", {}).get("price") == 427.51)

while m.fin_rows()[m.fin_sel][0] != "search":
    m.press("up")
m.press("a"); m.kb["text"] = ""
for ch in "bitcoin":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
wait_for(lambda: m.fin_status != "Looking…")
found = [e for k, e in m.fin_rows() if k == "found"]
check(f"'bitcoin': the coin you typed first, then a fund, then other coins ({[(f['kind'], f['id']) for f in found]})",
      [(f["kind"], f["id"]) for f in found] == [("coin", "bitcoin"), ("stock", "IBIT"), ("coin", "bitcoin-cash")])
snap("found_both")
check(f"...Bitcoin's yours: A shows it ({foot['items']})", foot["items"][0] == ("A", "Show"))
fakenet.STATE["gecko"] = False
while m.fin_rows()[m.fin_sel][0] != "search":
    m.press("up")
m.press("a"); m.kb["text"] = ""
for ch in "apple":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
wait_for(lambda: m.fin_status != "Looking…")
found = [e for k, e in m.fin_rows() if k == "found"]
check(f"CoinGecko down: the stocks found, and a word about it ({[f['id'] for f in found]}, {m.fin_status!r})",
      found and found[0]["id"] == "AAPL" and m.fin_status == "Can't reach CoinGecko. Is the WiFi on?")
snap("half")
fakenet.STATE["offline"] = True
while m.fin_rows()[m.fin_sel][0] != "search":
    m.press("up")
m.press("a"); m.kb["text"] = ""
for ch in "apple":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
wait_for(lambda: m.fin_status != "Looking…")
check(f"no internet at all: it says so ({m.fin_status!r})",
      m.fin_found is None and m.fin_status == "Can't reach Yahoo Finance or CoinGecko. Is the WiFi on?")
reset_net()

# removing: X twice
while not (m.fin_rows()[m.fin_sel][0] == "stock" and m.fin_rows()[m.fin_sel][1]["id"] == "TSLA"):
    m.press("down")
m.press("x")
check(f"X on Tesla: press it again ({m.msg!r})", m.msg == "Press X again to remove Tesla, Inc.")
m.press("x")
txt = open(FIN).read()
check(f"...removed ({m.stocks.symbols()}, {m.msg!r})", m.stocks.symbols() == ["AAPL", "AMZN", "MSFT"]
      and m.msg == "Removed Tesla, Inc." and "stocks = AAPL, AMZN, MSFT" in txt)
for sym in ("AAPL", "AMZN", "MSFT"):
    while not (m.fin_rows()[m.fin_sel][0] == "stock" and m.fin_rows()[m.fin_sel][1]["id"] == sym):
        m.press("down")
    m.press("x"); m.press("x")
txt = open(FIN).read()
check(f"all the stocks removed: none, for good, not the defaults back ({m.stocks.symbols()}, {[k for k, _ in m.fin_rows()]})",
      m.stocks.symbols() == [] and re.search(r"^stocks =\s*$", txt, re.M) and "label" in [k for k, _ in m.fin_rows()]
      and "stock" not in [k for k, _ in m.fin_rows()])
m.stocks.load(m.fin_files())
check("...still none, read again", m.stocks.symbols() == [])
while not (m.fin_rows()[m.fin_sel][0] == "coin" and m.fin_rows()[m.fin_sel][1]["id"] == "solana"):
    m.press("down")
m.press("x"); m.press("x")
while m.fin_rows()[m.fin_sel][0] != "coin":
    m.press("down")
m.press("x")
check(f"the last one stays ({m.msg!r}, {m.fin_cards()})", m.msg == "That's your last one. Add another before removing it"
      and m.fin_cards() == [("coin", "bitcoin")])
m.press("b")
snap("coins_only")
check("B: the cards, coins only now", not m.fin_list and m.fin_cards() == [("coin", "bitcoin")])

# ---- the bot ------------------------------------------------------------------------------------------------
open(FIN, "w").write("stocks = AAPL\ncoins = bitcoin\n")
m.fin_load()
facts = "\n".join(m.friend_facts())
check(f"the bot knows your stocks and coins:\n{facts}", "Stocks: Apple Inc. (AAPL) $235.86 (+1.0% today)" in facts
      and "Coins: BTC $67,234.00" in facts)
pick = random.choice
random.choice = lambda seq: "markets"
mc = m.crypto.quotes.pop("bitcoin")
t1 = m.friend_topic()
ms = m.stocks.quotes.pop("AAPL")
t2 = m.friend_topic()
random.choice = pick
m.crypto.quotes["bitcoin"], m.stocks.quotes["AAPL"] = mc, ms
check(f"...talks about them now and then: with only stocks' prices too ({t1}), not with none ({t2})",
      t1 == "markets" and t2 == "anything")

# leaving stops both
m.press("r")
wait_for(lambda: not {"stocks", "crypto"} & {t.name for t in threading.enumerate()}, 6)
names = [t.name for t in threading.enumerate()]
check(f"R: another tab, both stopped ({g.LIBRARY[m.tab]['name']}, {'stocks' in names}, {'crypto' in names})",
      g.LIBRARY[m.tab]["name"] != "Finance" and not m.stocks.running and not m.crypto.running
      and "stocks" not in names and "crypto" not in names)

# ---- a card without prices: why --------------------------------------------------------------------------------
open(FIN, "w").write("stocks = ZZZZ, AAPL\ncoins =\n")
fakenet.ASKED.clear()
m.press("l")
wait_for(lambda: (m.stocks.quotes.get("ZZZZ") or {}).get("err"), 10)
m.fin_card = 0
snap("nothing")
check(f"a ticker Yahoo hasn't got: its card says so ({m.stocks.error_of('ZZZZ')!r})",
      m.stocks.error_of("ZZZZ") == "Yahoo Finance has no prices for ZZZZ")
n = len(asked("/chart/ZZZZ"))
time.sleep(2.5)
check(f"...and it's asked again in a minute, not straight away, nor its chart ({n} asked, {len(asked('/chart/ZZZZ')) - n} more)",
      n == 1 and len(asked("/chart/ZZZZ")) == n)
fakenet.STATE["offline"] = True
m.stocks.quotes.pop("AAPL", None)
m.stocks.force = True
m.fin_card = 1; m.fin_focus()
wait_for(lambda: (m.stocks.quotes.get("AAPL") or {}).get("err"), 10)
snap("offline")
check(f"no internet: the card says so ({m.stocks.error_of('AAPL')!r})",
      m.stocks.error_of("AAPL") == "Can't reach Yahoo Finance. Is the WiFi on?")
reset_net()
m.press("r")

# ---- setup.sh: the Finance tab's file, and crypto.txt moved across --------------------------------------------
src = open(os.environ.get("PITATO_ROOT", ROOT) + "/setup.sh").read()
at = src.index("# the Finance tab's stocks and coins to start with")
step = src[at:src.index("# ----", at)]
SB = S + "/setup"


def setup_run(files):
    shutil.rmtree(SB, ignore_errors=True)
    os.makedirs(SB)
    for name, text in files.items():
        open(f"{SB}/{name}", "w").write(text)
    script = ("set -e\nstep() { echo \"==> $*\"; }\nchown() { :; }\nSTATIC=" + SB + "\nUSER_NAME=pi\n" + step
              + "\necho DONE\n")
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return out.stdout + out.stderr, {n: open(f"{SB}/{n}").read() for n in sorted(os.listdir(SB))}


out, files = setup_run({})
check(f"setup.sh, nothing yet: finance.txt, stocks and coins, without a word ({out.strip()!r}):\n{files.get('finance.txt')}",
      out.strip() == "DONE" and list(files) == ["finance.txt"] and files["finance.txt"].startswith("# Finance: stocks by their tickers")
      and "stocks = AAPL, AMZN, TSLA\ncoins = bitcoin, ethereum, dogecoin\n" in files["finance.txt"])
out, files = setup_run({"crypto.txt": "# Crypto tab. Coins are CoinGecko ids\n# Y on the Crypto tab ...\n"
                                      "coins = bitcoin, solana\nduco = someone\n"})
check(f"...an old crypto.txt: moved across, its coins and the rest kept, stocks added:\n{files.get('finance.txt')}",
      out.strip() == "DONE" and list(files) == ["finance.txt"]
      and files["finance.txt"].startswith("# Finance: stocks by their tickers") and "# Crypto tab" not in files["finance.txt"]
      and files["finance.txt"].endswith("stocks = AAPL, AMZN, TSLA\ncoins = bitcoin, solana\nduco = someone\n"))
out, files = setup_run({"crypto.txt": "stocks = NVDA\ncoins = bitcoin\n"})
check(f"...one with its own stocks: not the defaults added ({files.get('finance.txt')!r})",
      "DONE" in out and files["finance.txt"].count("stocks =") == 1 and "stocks = NVDA" in files["finance.txt"])
out, files = setup_run({"crypto.txt": "# only notes\n"})
check(f"...one with only notes in it: no harm done ({out.strip().splitlines()[-1]}, {files.get('finance.txt')!r})",
      "DONE" in out and "stocks = AAPL, AMZN, TSLA" in files["finance.txt"] and list(files) == ["finance.txt"])
out, files = setup_run({"finance.txt": "stocks = AAPL\n", "crypto.txt": "coins = bitcoin\n"})
check(f"...finance.txt there already: kept as it is, without a word ({out.strip()!r})",
      out.strip() == "DONE" and files["finance.txt"] == "stocks = AAPL\n")

# pictures
from PIL import Image
order = ["stock", "stock_7d", "coin", "list", "found", "found_both", "half", "coins_only", "nothing", "offline"]
W, H = 640, 480
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 5 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/finance_tab.png")
shots["tv"].save(SP + "/out/finance_tv.png")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
