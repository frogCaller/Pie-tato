"""The Finance tab's coins (Y): the search bar, looking a coin up on CoinGecko (a stand-in; Yahoo finding no
stocks), adding it (into finance.txt, the rest of the file kept; its card next), what's yours already, removing one (X twice,
not the last), as many as there's room for, nothing found, no internet, CoinGecko saying slow down, a
search that's no longer wanted, and leaving (B, Y, L R). Screenshots for a look."""
import json, math, os, shutil, sys, threading, time, urllib.error, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/tcoins"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/static"); os.makedirs(S + "/home/u")
g.PLEX_FILE = S + "/plex.json"; g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.FRIEND_LOG = S + "/friend.json"
g.CRYPTO_GAP = 0.02
g.STATIC = S + "/static"
g.home_dir = lambda: S + "/home/u"
g.settings_dir = lambda: S + "/static"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
TXT = S + "/static/finance.txt"
with open(TXT, "w") as f:
    f.write("# my coins\ncoins = bitcoin, ethereum\n# (a note of mine)\nstocks =\n")
ci = next(i for i, t in enumerate(g.LIBRARY) if t["type"] == "finance")
g.LIBRARY[ci]["files"] = [g.settings_glob("finance.txt")]
g.Stocks.search = lambda self, text: []          # (Yahoo finds no stocks: the coins are what's looked at here)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


FOUND = {
    "sol": [{"id": "solana", "name": "Solana", "api_symbol": "solana", "symbol": "SOL", "market_cap_rank": 5,
             "thumb": "x", "large": "x"},
            {"id": "solv-protocol", "name": "Solv Protocol", "api_symbol": "solv-protocol", "symbol": "SOLV",
             "market_cap_rank": 312, "thumb": "x", "large": "x"},
            {"id": "Bad Id, with a comma", "name": "Broken", "symbol": "BAD", "market_cap_rank": 9},
            {"id": "solar-dao", "name": "Solar\nDAO", "symbol": "sdao", "market_cap_rank": None},
            ] + [{"id": f"sol-{k}", "name": f"Sol thing {k}", "symbol": f"S{k}", "market_cap_rank": 900 + k}
                 for k in range(20)],
    "bit": [{"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "market_cap_rank": 1},
            {"id": "bittorrent", "name": "BitTorrent", "symbol": "BTT", "market_cap_rank": 140}],
    "duino": [{"id": "duino-coin", "name": "Duino-Coin", "symbol": "DUCO", "market_cap_rank": 2400}],
}
fake = {"fail": None, "slow": 0.0}
import http.client
searches = []


class Resp:
    def __init__(self, obj): self.b = json.dumps(obj).encode()
    def read(self, n=-1): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(req, timeout=10):
    url = req.full_url if hasattr(req, "full_url") else req
    u = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(u.query)
    parts = u.path.split("/")
    if u.netloc == "api.coingecko.com" and u.path.endswith("/search"):
        searches.append(q["query"][0])
        time.sleep(fake["slow"])
        if fake["fail"] == "offline":
            raise urllib.error.URLError("no wifi")
        if fake["fail"] == "busy":
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        if fake["fail"] == "cut":
            raise http.client.IncompleteRead(b'{"coins": [')
        if fake["fail"] == "odd":
            return Resp({"coins": 5})
        return Resp({"coins": FOUND.get(q["query"][0].lower(), []), "exchanges": [], "icos": [], "categories": [],
                     "nfts": []})
    if fake["fail"] == "offline":
        raise urllib.error.URLError("no wifi")
    if u.netloc == "api.coingecko.com" and u.path.endswith("/market_chart"):
        return Resp({"prices": [[i, 100 + math.sin(i / 7) * 3 + i * 0.05] for i in range(120)]})
    if u.netloc == "api.coingecko.com" and "/coins/" in u.path:
        cid = parts[-1]
        price = {"bitcoin": 62890.0, "ethereum": 2435.12, "solana": 141.2, "solv-protocol": 0.0412}.get(cid, 1.5)
        return Resp({"name": cid.replace("-", " ").title(), "symbol": cid[:3], "market_cap_rank": 9,
                     "market_data": {"current_price": {"usd": price}, "price_change_percentage_24h":
                                     {"bitcoin": 1.84, "ethereum": -2.31}.get(cid, 0.4)}})
    raise urllib.error.URLError("unexpected " + url)


g.urllib.request.urlopen = fake_urlopen


class FB:
    w, h, same = 640, 480, True
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def close(self): pass


foot = {}
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
_footer = m.footer


def spy_footer(d, items, right=None, credit=None):
    foot.clear(); foot.update(items=[(it[0], it[1]) for it in items], credit=credit)
    return _footer(d, items, right=right, credit=credit)


m.footer = spy_footer
shots = {}


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def wait_for(c, t=5):
    e = time.time() + t
    while time.time() < e:
        if c():
            return True
        time.sleep(0.03)
    return bool(c())


def kinds():
    return [k for k, _ in m.fin_rows()]


def picked():
    return m.fin_rows()[m.fin_sel]


def type_in(text):
    for ch in text:
        m.keyboard_key("char", ch)
    m.keyboard_key("done")


def saved():
    with open(TXT) as f:
        return f.read()


while g.LIBRARY[m.tab]["name"] != "Finance":
    m.press("r")
cr = m.crypto
wait_for(lambda: "ethereum" in cr.quotes and "bitcoin" in cr.quotes)
snap("cards")
check(f"the coin cards: Y to add coins, beside the credit ({foot['items']})", ("Y", "Add") in foot["items"]
      and foot["credit"] == "Source: CoinGecko")

# Y: the search bar and your coins
m.press("y")
snap("list")
check(f"Y: the search bar, then your coins ({kinds()})", m.fin_list and kinds() == ["search", "label", "coin", "coin"]
      and picked()[0] == "search")
check(f"...its buttons: {foot['items']}", foot["items"] == [("A", "Look up"), ("B", "Back")]
      and foot["credit"] == "Yahoo Finance, CoinGecko")
m.press("a")
check(f"A: a box to type in ({m.view}, {m.kb and m.kb['title']!r})", m.view == "keys" and "Look up a stock or a coin" in m.kb["title"])
type_in("sol")
check(f"...typed, and it looks ({m.fin_status!r}, back on {m.view})", m.view == "list" and m.fin_list
      and m.fin_query == "sol")
wait_for(lambda: m.fin_found is not None)
rows = m.fin_rows()
found = [e for k, e in rows if k == "found"]
check(f"what it found, the first picked: {[(c['id'], c['symbol'], c['rank']) for c in found[:4]]}",
      [c["id"] for c in found[:3]] == ["solana", "solv-protocol", "solar-dao"] and found[0]["symbol"] == "SOL"
      and found[0]["rank"] == 5 and found[2]["rank"] is None and found[2]["name"] == "Solar DAO"
      and found[2]["symbol"] == "SDAO" and picked() == ("found", found[0]) and m.fin_status is None)
check(f"...not ones whose id can't go in finance.txt, and {g.FOUND_COINS} at most beside the stocks ({len(found)})",
      all(" " not in c["id"] and "," not in c["id"] for c in found) and len(found) == g.FOUND_COINS)
check(f"...under the search bar, your coins after: {kinds()[:3]}, {kinds()[-3:]}",
      kinds()[:3] == ["search", "label", "found"] and kinds()[-3:] == ["label", "coin", "coin"]
      and rows[1][1] == "Found for “sol”")
snap("found")
check(f"...its buttons: {foot['items']}", foot["items"] == [("A", "Add"), ("B", "Back")])

# A: added
m.press("a")
check(f"A: added ({m.msg!r}), and kept in finance.txt with the rest of it:\n{saved()}",
      cr.ids() == ["bitcoin", "ethereum", "solana"] and m.msg == "Added Solana"
      and "coins = bitcoin, ethereum, solana" in saved() and "# my coins" in saved() and "# (a note of mine)" in saved())
check(f"...its name and symbol, till its prices come; its card's next ({m.fin_card}, {cr.focus})",
      cr.coin("solana")["name"] == "Solana" and cr.coin("solana")["symbol"] == "SOL" and m.fin_card == 2
      and cr.focus == ("coin", "solana"))
snap("added")
check(f"...it says it's yours now, A shows it ({foot['items']})", foot["items"] == [("A", "Show"), ("B", "Back")]
      and kinds().count("coin") == 3)
m.press("down")
m.press("a")
check(f"another ({cr.ids()})", cr.ids() == ["bitcoin", "ethereum", "solana", "solv-protocol"]
      and m.msg == "Added Solv Protocol")
wait_for(lambda: "solana" in cr.quotes)
snap("prices")

# removing one: X twice
while picked()[0] != "coin" or picked()[1]["id"] != "ethereum":
    m.press("down")
m.press("x")
snap("remove")
check(f"X on one of yours: press it again to remove it ({m.msg!r}, {foot['items']})",
      m.msg == "Press X again to remove Ethereum" and ("X", "Remove it") in foot["items"] and "ethereum" in cr.ids())
m.press("x")
check(f"...X again: removed ({cr.ids()}, {m.msg!r})", cr.ids() == ["bitcoin", "solana", "solv-protocol"]
      and m.msg == "Removed Ethereum" and "coins = bitcoin, solana, solv-protocol" in saved())
check(f"...the picked row's still a coin ({picked()[0]}, {picked()[1]['id']})", picked()[0] == "coin")
m.press("x")
m.press("down")
m.press("x")
check("...moving off it in between: it asks again", m.msg.startswith("Press X again") and len(cr.ids()) == 3)

# A on one of yours: its card
target = picked()[1]["id"]
m.press("a")
check(f"A on one of yours: its card ({cr.focus})", not m.fin_list and cr.focus == ("coin", target)
      and cr.ids()[m.fin_card] == target)

# the last one stays
m.press("y")
for cid in ("solana", "solv-protocol"):
    while not (picked()[0] == "coin" and picked()[1]["id"] == cid):
        m.press("down")
    m.press("x"); m.press("x")
check(f"down to one coin ({cr.ids()})", cr.ids() == ["bitcoin"])
while picked()[0] != "coin":
    m.press("down")
m.press("x")
check(f"...that one stays ({m.msg!r})", cr.ids() == ["bitcoin"] and "your last one" in m.msg)

# what's yours already, found again
m.press("up")
m.press("a"); type_in("bit")
wait_for(lambda: m.fin_found is not None and m.fin_query == "bit" and m.fin_status is None)
snap("yours")
check(f"found, one of them yours: A shows it ({foot['items']})", picked()[1]["id"] == "bitcoin"
      and foot["items"] == [("A", "Show"), ("B", "Back")])
m.press("down")
m.press("a")
check(f"...the other's added ({cr.ids()})", cr.ids() == ["bitcoin", "bittorrent"])

# nothing found; no internet; CoinGecko says slow down
m.press("up"); m.press("up")
while picked()[0] != "search":
    m.press("up")
m.press("a"); type_in("zzzz")
wait_for(lambda: m.fin_status != "Looking…")
snap("nothing")
check(f"nothing found: it says so ({m.fin_status!r}), the list as it was ({kinds()})",
      m.fin_status == "Nothing found for “zzzz”" and "found" not in kinds() and picked()[0] == "search")
fake["fail"] = "offline"
m.press("a"); m.kb["text"] = ""; type_in("eth")
wait_for(lambda: m.fin_status != "Looking…")
snap("offline")
check(f"no internet ({m.fin_status!r})", m.fin_status == "Can't reach CoinGecko. Is the WiFi on?")
fake["fail"] = "busy"
m.press("a"); m.kb["text"] = ""; type_in("eth")
wait_for(lambda: m.fin_status != "Looking…")
check(f"CoinGecko says slow down ({m.fin_status!r})", "minute" in m.fin_status)
cr.backoff_until = 0
fake["fail"] = "cut"
m.press("a"); m.kb["text"] = ""; type_in("eth")
wait_for(lambda: m.fin_status != "Looking…")
check(f"cut off halfway: it says so, not looking for good ({m.fin_status!r})", m.fin_status == "Can't reach CoinGecko. Is the WiFi on?")
fake["fail"] = "odd"
m.press("a"); m.kb["text"] = ""; type_in("eth")
wait_for(lambda: m.fin_status != "Looking…")
check(f"an answer it can't make sense of: nothing found ({m.fin_status!r})", m.fin_status == "Nothing found for “eth”")
fake["fail"] = None

# a new search: what the last one found goes; one from before the list opened again isn't used
m.press("a"); type_in("sol")
wait_for(lambda: m.fin_found is not None)
fake["slow"] = 0.5
while picked()[0] != "search":
    m.press("up")
m.press("a"); type_in("duino")
check(f"looking again: what it found for the last one goes ({m.fin_found}, {kinds()[:2]})", m.fin_found is None
      and kinds()[:2] == ["search", "label"] and m.fin_query == "duino")
m.fin_close(); m.fin_open()
time.sleep(0.8)
check(f"...the list closed and opened again before it came: not used ({m.fin_found}, {m.fin_status})",
      m.fin_found is None and m.fin_status is None and m.fin_query == "")
fake["slow"] = 0.0

# a search that's no longer wanted: you've gone back
fake["slow"] = 0.5
m.press("a"); m.kb["text"] = ""; type_in("duino")
snap("looking")
check(f"looking ({m.fin_status!r})", m.fin_status == "Looking…")
m.press("b")
time.sleep(0.8)
check(f"B: back to the cards, and what it found then isn't used ({m.fin_found}, {m.fin_status})",
      not m.fin_list and m.fin_found is None and m.fin_status is None)
fake["slow"] = 0.0

# as many as there's room for
many = [f"coin-{k}" for k in range(g.CRYPTO_MOST - 1)] + ["bitcoin"]
with open(TXT, "w") as f:
    f.write("coins = " + ", ".join(many) + "\n")
cr.load(g.LIBRARY[ci]["files"])
m.press("y")
m.press("a"); type_in("duino")
wait_for(lambda: m.fin_found is not None)
m.press("a")
check(f"{g.CRYPTO_MOST} coins: as many as there's room for ({m.msg!r})", len(cr.ids()) == g.CRYPTO_MOST
      and "Remove one first" in m.msg)

# the coins line holds 400 characters
long = [f"a-coin-with-a-very-long-id-for-the-line-number-{k}" for k in range(8)]
with open(TXT, "w") as f:
    f.write("coins = " + ", ".join(long) + "\n")
cr.load(g.LIBRARY[ci]["files"])
if not m.fin_list:
    m.press("y")
while picked()[0] != "search":
    m.press("up")
m.press("a"); type_in("duino")
wait_for(lambda: m.fin_found is not None)
m.press("a")
check(f"...or as many as finance.txt's line holds ({len(', '.join(long))} characters, {m.msg!r})", cr.ids() == long
      and "Remove one first" in m.msg and saved().count("duino") == 0)

# a coins line written by hand, longer than that: removing one keeps the rest whole
longer = long + [f"another-coin-with-a-long-long-id-{k}" for k in range(6)]
with open(TXT, "w") as f:
    f.write("coins = " + ", ".join(longer) + "\n")
cr.load(g.LIBRARY[ci]["files"])
if not m.fin_list:
    m.press("y")
while not (picked()[0] == "coin" and picked()[1]["id"] == longer[0]):
    m.press("down")
m.press("x"); m.press("x")
check(f"...one written by hand that's longer still ({len(', '.join(longer))} characters): one removed, the rest kept "
      f"whole ({len(cr.ids())} coins)", cr.ids() == longer[1:] and ("coins = " + ", ".join(longer[1:])) in saved())

# Y closes it too; L R: another tab, and it's closed when you come back
m.press("y")
check("Y again: back to the cards", not m.fin_list)
m.press("y")
m.press("r")
check(f"R: the next tab ({g.LIBRARY[m.tab]['name']})", g.LIBRARY[m.tab]["name"] != "Finance")
m.press("l")
check(f"...back on Finance: its cards ({m.fin_list})", g.LIBRARY[m.tab]["name"] == "Finance" and not m.fin_list)

# no finance.txt yet: the first coin added makes one, with a word about it at the top
os.remove(TXT)
cr.load(g.LIBRARY[ci]["files"])
m.press("y")
m.press("a"); type_in("duino")
wait_for(lambda: m.fin_found is not None)
m.press("a")
check(f"no finance.txt: one's made, the coins as they were plus the new one:\n{saved()}",
      saved().startswith("# Finance: stocks by their tickers") and "coins = bitcoin, ethereum, dogecoin, duino-coin" in saved()
      and cr.ids() == ["bitcoin", "ethereum", "dogecoin", "duino-coin"])
m.press("b")

W, H = 640, 480
order = ["cards", "list", "found", "added", "prices", "remove", "yours", "nothing", "offline", "looking"]
sheet = Image.new("RGB", (W * 2 + 10, (H + 10) * 5 - 10), (80, 80, 80))
for k, name in enumerate(order):
    sheet.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
sheet.save(SP + "/out/coins_tab.png")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
