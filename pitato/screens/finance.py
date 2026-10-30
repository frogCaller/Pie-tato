"""The Finance tab: a card for each of your stocks and coins, and looking more up to add (Y)."""
import glob
import os
import threading
import time

from ..theme import ACCENT, BG, BODY, DONE, LINE, MUTED, PI_BG, PI_DIM, PI_DOWN, PI_FG, PI_UP, ROW, TEXT, WARN
from ..config import edit_config
from ..util import _num
from ..library import LIBRARY
from ..crypto import big_number, CRYPTO_LINE, CRYPTO_MOST, CRYPTO_ROTATE, CRYPTO_WINDOWS, price_text
from ..stocks import market_open, money, STOCKS_LINE, STOCKS_MOST

FINANCE_HEAD = ("# Finance: stocks by their tickers, as on finance.yahoo.com (AAPL, AMZN, TSLA), and coins by their\n"
                "# CoinGecko ids, as in coingecko.com/en/coins/bitcoin. Y on the Finance tab looks them up and adds\n"
                "# them, or removes them.\n")
FADE_TOP = 0.34          # the chart's shading: this strong at its top, faded away by its bottom
FOUND_COINS = 8          # coins a search shows beside the stocks


def fade_under(img, pts, colour, x0, top, x1, bottom):
    """The area under a chart's line, in its colour: strongest at the top, faded away by the bottom."""
    from PIL import Image, ImageChops, ImageDraw
    box = (int(x0), int(top), int(x1) + 1, int(bottom) + 1)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 2 or h < 2:
        return
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(x - box[0], y - box[1]) for x, y in pts] + [(w - 1, h - 1), (0, h - 1)], fill=255)
    fade = Image.linear_gradient("L").resize((w, h)).point(lambda v: int((255 - v) * FADE_TOP))
    img.paste(colour, box, ImageChops.multiply(mask, fade))


def draw_chart(img, d, vals, colour, x0, top, x1, bottom, lo=None, hi=None):
    """A chart's line over the shaded area under it, from lo at the bottom to hi at the top."""
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    span = (hi - lo) or 1
    pts = [(x0 + i * (x1 - x0) / (len(vals) - 1), bottom - (v - lo) / span * (bottom - top))
           for i, v in enumerate(vals)]
    fade_under(img, pts, colour, x0, top, x1, bottom)
    d.line(pts, fill=colour, width=3, joint="curve")


def clock_at(t, gmtoffset, tz, now=None):
    """When a price is from, in its market's own time: 4:00 PM EDT, Fri 4:00 PM EDT, or Oct 17."""
    now = time.time() if now is None else now
    at, today = time.gmtime(t + gmtoffset), time.gmtime(now + gmtoffset)
    clock = f"{(at.tm_hour % 12) or 12}:{at.tm_min:02d} {'AM' if at.tm_hour < 12 else 'PM'}" + (f" {tz}" if tz else "")
    days = (int(now + gmtoffset) // 86400) - (int(t + gmtoffset) // 86400)
    if days <= 0 and at.tm_yday == today.tm_yday:
        return clock
    if days < 6:
        return time.strftime("%a ", at) + clock
    return time.strftime("%b ", at) + str(at.tm_mday)


class FinanceScreen:
    """The Finance tab: a card for each of your stocks and coins, and looking more up to add (Y)."""

    def fin_cards(self):
        return self.stocks.cards() + self.crypto.cards()

    def fin_files(self):
        """finance.txt; crypto.txt (its earlier name) till there's one."""
        files = LIBRARY[self.tab_index("finance")]["files"]
        if not any(glob.glob(p) for p in files):
            return [os.path.join(os.path.dirname(p), "crypto.txt") for p in files]
        return files

    def fin_load(self):
        files = self.fin_files()
        self.stocks.load(files)
        self.crypto.load(files)

    def fin_focus(self):
        """The card on screen, fetched before the rest."""
        cards = self.fin_cards()
        card = cards[self.fin_card % len(cards)] if cards else None
        self.stocks.focus = card if card and card[0] == "stock" else None
        self.crypto.focus = card if card and card[0] == "coin" else None

    def fin_changed(self):
        if self.active and self.view == "list" and self.tab_type() == "finance":
            self.dirty = True

    def fin_start(self):
        self.stocks.start()
        self.crypto.start()

    def fin_stop(self):
        self.stocks.stop()
        self.crypto.stop()

    def press_finance(self, name, repeat):
        cards = self.fin_cards()
        if name in ("left", "right") and cards:
            self.fin_card = (self.fin_card + (1 if name == "right" else -1)) % len(cards)
            self.fin_focus()
            self.fin_next = time.monotonic() + CRYPTO_ROTATE
        elif name in ("up", "down") and not repeat:
            days = [d for d, _ in CRYPTO_WINDOWS]
            i = days.index(self.crypto.days) if self.crypto.days in days else 0
            self.crypto.days = self.stocks.days = days[(i + (1 if name == "up" else -1)) % len(days)]
        elif name == "a" and not repeat:
            self.fin_auto = not self.fin_auto
            self.fin_next = time.monotonic() + CRYPTO_ROTATE
            self.toast("Auto: a new card every 20 seconds" if self.fin_auto else "Auto off", 2)
        elif name == "x" and not repeat:
            self.crypto.force = self.stocks.force = True
            self.toast("Refreshing", 2)
        elif name == "y" and not repeat:
            self.fin_open()
        self.dirty = True
        return None

    # your stocks and coins: look them up, add them, remove them (Y)
    def fin_open(self):
        self.fin_list, self.fin_sel = True, 0
        self.fin_token += 1                            # (a search from before isn't wanted now)
        self.fin_query, self.fin_found, self.fin_status = "", None, None
        self.confirm = (None, 0.0)
        self.dirty = True

    def fin_close(self):
        self.fin_list = False
        self.fin_token += 1                            # (a search still out there isn't wanted now)
        self.fin_found, self.fin_status = None, None
        self.confirm = (None, 0.0)
        self.dirty = True

    def fin_rows(self):
        """The search bar, what it found (if you've looked), then your stocks and your coins."""
        rows = [("search", None)]
        if self.fin_found:
            rows.append(("label", f"Found for “{self.fin_query}”"))
            rows += [("found", f) for f in self.fin_found]
        if self.stocks.stocks:
            rows.append(("label", "Your stocks"))
            rows += [("stock", dict(s, id=s["symbol"])) for s in self.stocks.stocks]
        if self.crypto.coins:
            rows.append(("label", "Your coins"))
            rows += [("coin", c) for c in self.crypto.coins]
        return rows

    def fin_mine(self, kind, ident):
        return ident in (self.stocks.symbols() if kind == "stock" else self.crypto.ids())

    def press_fin_list(self, name, repeat):
        rows = self.fin_rows()
        n = len(rows)
        sel = max(0, min(self.fin_sel, n - 1))
        kind, entry = rows[sel]
        if name in ("up", "down"):
            step = 1 if name == "down" else -1
            sel = (sel + step) % n
            if rows[sel][0] == "label":
                sel = (sel + step) % n
            self.fin_sel = sel
            self.confirm = (None, 0.0)
        elif name == "a" and not repeat:
            if kind == "search":
                self.open_keyboard("Look up a stock or a coin (its name or ticker)", "", self.fin_search, limit=40)
            elif kind == "found" and not self.fin_mine(entry["kind"], entry["id"]):
                self.fin_add(entry)
            elif kind == "found":
                self.fin_show(entry["kind"], entry["id"])
            elif kind in ("stock", "coin"):
                self.fin_show(kind, entry["id"])
        elif name == "x" and not repeat and kind in ("stock", "coin"):
            key = f"findel:{kind}:{entry['id']}"
            if len(self.fin_cards()) < 2:
                self.toast("That's your last one. Add another before removing it", 4)
            elif self.confirm[0] == key:
                self.confirm = (None, 0.0)
                self.fin_remove(kind, entry["id"])
            else:
                self.confirm = (key, time.monotonic() + 4)
                self.toast(f"Press X again to remove {entry['name']}", 4)
        elif name in ("b", "y") and not repeat:
            self.fin_close()
        elif name in ("l", "r"):
            return "pass"                              # (tabs, as everywhere: it closes as you go)
        self.dirty = True
        return None

    @staticmethod
    def fin_order(text, stocks, coins):
        """What a search found: a ticker or coin you typed exactly first, then stocks, then coins."""
        typed = text.strip().lower()
        rows = [dict(s, kind="stock") for s in stocks] + [dict(c, kind="coin") for c in coins[:FOUND_COINS]]

        def exact(r):
            return (r.get("symbol") or "").lower() == typed or (r["kind"] == "coin" and r["id"] == typed)
        return [r for r in rows if exact(r)] + [r for r in rows if not exact(r)]

    def fin_search(self, text):
        """What you typed, looked up on Yahoo Finance and CoinGecko at once (on threads: the screen says it's
        looking). What one found is shown even if the other couldn't look."""
        text = " ".join(text.split())
        if not text:
            return
        self.fin_token += 1
        token = self.fin_token
        self.fin_query, self.fin_status, self.fin_sel, self.fin_found = text, "Looking…", 0, None

        def look(fn, got, key):
            try:
                got[key] = (fn(text), None)
            except ValueError as ex:
                got[key] = (None, str(ex))
            except Exception:
                got[key] = (None, "Couldn't look that up. Try again")

        def job():
            got = {}
            coins = threading.Thread(target=look, args=(self.crypto.search, got, "coin"), daemon=True,
                                     name="coin-search")
            coins.start()
            look(self.stocks.search, got, "stock")
            coins.join(45)
            stocks, s_err = got.get("stock", (None, "Couldn't look that up. Try again"))
            found_coins, c_err = got.get("coin", (None, "Couldn't look that up. Try again"))
            found = self.fin_order(text, stocks or [], found_coins or [])
            if s_err and c_err and s_err.startswith("Can't reach") and c_err.startswith("Can't reach"):
                status = "Can't reach Yahoo Finance or CoinGecko. Is the WiFi on?"
            else:
                status = s_err or c_err or (None if found else f"Nothing found for “{text}”")
            if token != self.fin_token:
                return                                 # (another search since, or the list's closed)
            self.fin_found, self.fin_status = found or None, status
            self.fin_sel = 2 if found else 0           # (the first thing it found)
            self.dirty = True
        threading.Thread(target=job, daemon=True, name="finance-search").start()
        self.dirty = True

    def fin_save(self, stocks=None, coins=None):
        """Your stocks or coins into finance.txt (for good: the rest of it kept), and on the tab. False: it
        couldn't."""
        updates = {}
        if stocks is not None:
            updates["stocks"] = ", ".join(stocks)
        if coins is not None:
            updates["coins"] = ", ".join(coins)
        try:
            edit_config("finance.txt", updates, head=FINANCE_HEAD, was="crypto.txt",
                        limit=max(STOCKS_LINE, CRYPTO_LINE, *(len(v) for v in updates.values())))
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return False
        self.fin_load()
        return True

    def fin_add(self, entry):
        if entry["kind"] == "stock":
            syms = self.stocks.symbols()
            if len(syms) >= STOCKS_MOST or len(", ".join(syms + [entry["id"]])) > STOCKS_LINE:
                self.toast("That's as many stocks as there's room for. Remove one first", 4)
                return
            if not self.fin_save(stocks=syms + [entry["id"]]):
                return
            s = self.stocks.stock(entry["id"])
            if s in self.stocks.stocks:                # (its name, till its prices come)
                s["name"] = entry["name"] or s["name"]
        else:
            ids = self.crypto.ids()
            if len(ids) >= CRYPTO_MOST or len(", ".join(ids + [entry["id"]])) > CRYPTO_LINE:
                self.toast("That's as many coins as there's room for. Remove one first", 4)
                return
            if not self.fin_save(coins=ids + [entry["id"]]):
                return
            c = self.crypto.coin(entry["id"])
            if c in self.crypto.coins:                 # (its name and symbol, till its prices come)
                c["symbol"], c["name"] = entry["symbol"] or c["symbol"], entry["name"] or c["name"]
        cards = self.fin_cards()
        card = (entry["kind"], entry["id"])
        self.fin_card = cards.index(card) if card in cards else self.fin_card   # (its card's next: fetched first)
        self.fin_focus()
        self.toast(f"Added {entry['name']}", 3)

    def fin_remove(self, kind, ident):
        if kind == "stock":
            name = self.stocks.stock(ident)["name"]
        else:
            name = self.crypto.coin(ident)["name"]
        cards = self.fin_cards()
        at = cards.index((kind, ident)) if (kind, ident) in cards else -1
        if kind == "stock":
            saved = self.fin_save(stocks=[s for s in self.stocks.symbols() if s != ident])
        else:
            saved = self.fin_save(coins=[i for i in self.crypto.ids() if i != ident])
        if not saved:
            return
        if 0 <= at < self.fin_card or self.fin_card >= len(self.fin_cards()):
            self.fin_card = max(0, self.fin_card - 1)
        self.fin_focus()
        rows = self.fin_rows()
        self.fin_sel = min(self.fin_sel, len(rows) - 1)
        if rows[self.fin_sel][0] == "label":
            self.fin_sel -= 1
        self.toast(f"Removed {name}", 3)

    def fin_show(self, kind, ident):
        """That stock's or coin's card."""
        cards = self.fin_cards()
        if (kind, ident) in cards:
            self.fin_card = cards.index((kind, ident))
            self.fin_focus()
            self.fin_next = time.monotonic() + CRYPTO_ROTATE
        self.fin_close()

    def render_finance(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.HEADER + 1, H if self.full_app() else H - self.FOOTER   # (no buttons: down to the bottom)
        d.rectangle((0, top, W, bottom), fill=PI_BG)          # PiE-ink's black card
        cards = self.fin_cards()
        card = cards[self.fin_card % len(cards)] if cards else None
        window = dict(CRYPTO_WINDOWS).get(self.crypto.days, "1D")
        if card is None:
            d.text((W / 2, (top + bottom) / 2), "Press Y to add stocks or coins", font=F["row"], fill=PI_DIM,
                   anchor="mm")
        elif card[0] == "stock":
            self.draw_stock(img, d, card[1], top, bottom, window)
        else:
            self.draw_coin(img, d, card[1], top, bottom, window)
        # (A lights up while Auto is on; the card's source is credited beside its numbers)
        hints = [("◀▶", "Next"), ("▲▼", window), ("A", "Auto", self.fin_auto), ("X", "Refresh"), ("Y", "Add")]
        if len(cards) > 1:                                     # which card this is
            gap = 14 if len(cards) * 14 < W - 40 else max(6, (W - 40) // len(cards))
            x = W / 2 - (len(cards) - 1) * gap / 2
            for k in range(len(cards)):
                on = k == self.fin_card % len(cards)
                r = 4 if on else 3
                d.ellipse((x - r, bottom - 16 - r, x + r, bottom - 16 + r), fill=PI_FG if on else (70, 70, 70))
                x += gap
        if card and card[0] == "stock":                        # (shorter on the GPi's screen: Y Add still fits)
            credit = "Source: Yahoo Finance" if W >= 800 else "Yahoo Finance"
        else:
            credit = "Source: CoinGecko" if card else ""
        self.footer(d, hints, credit=credit)                   # (the dots above say which card)
        self.fb.show(img)

    def render_fin_list(self):
        """Your stocks and coins (Y): the search bar, what it found, then yours with their prices."""
        F = self.fonts
        cr, st = self.crypto, self.stocks
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.fin_rows()
        n = len(rows)
        sel = self.fin_sel = max(0, min(self.fin_sel, n - 1))
        if rows[sel][0] == "label":
            sel = self.fin_sel = min(sel + 1, n - 1)
        d.text((20, self.LIST_TOP + 10), "Finance  ›  Yours", font=F["small"], fill=MUTED, anchor="lm")
        if self.fin_status:
            busy = self.fin_status == "Looking…"
            d.text((W - 20, self.LIST_TOP + 10), self.fit(d, self.fin_status, F["small"], max(200, W - 220)),
                   font=F["small"], fill=MUTED if busy else WARN, anchor="rm")
        top_y = self.LIST_TOP + 28
        shown = max(1, (H - self.FOOTER - top_y) // self.ROW_H)
        top = self.tops.get("finance", 0)
        top = sel if sel < top else (sel - shown + 1 if sel >= top + shown else top)
        top = max(0, min(top, n - shown))
        self.tops["finance"] = top
        x0, x1 = 12, W - 22
        for r, i in enumerate(range(top, min(top + shown, n))):
            kind, entry = rows[i]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            selected = i == sel
            if kind != "label":
                self.tappable((0, y, W, y + self.ROW_H), "sel", "attr", "fin_sel", i)
            if kind == "label":
                d.text((x0 + 18, mid + 8), entry, font=F["small_b"], fill=MUTED, anchor="lm")
                continue
            if kind == "search":                       # a search bar: what you looked up, or what it's for
                bx0, by0, bx1, by1 = x0 + 4, y + 5, x1, y + self.ROW_H - 5
                d.rounded_rectangle((bx0, by0, bx1, by1), radius=(by1 - by0) // 2, fill=ROW if selected else BG,
                                    outline=ACCENT if selected else LINE, width=2)
                ink = ACCENT if selected else MUTED
                cx, cy = bx0 + 26, mid - 2
                d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), outline=ink, width=2)
                d.line((cx + 5, cy + 5, cx + 10, cy + 10), fill=ink, width=3)
                words = self.fin_query or "Look up a stock or a coin to add: its name or ticker"
                d.text((bx0 + 48, mid), self.fit(d, words, F["row"], bx1 - bx0 - 66), font=F["row"],
                       fill=(TEXT if selected else BODY) if self.fin_query else MUTED, anchor="lm")
                continue
            if selected:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            what = entry.get("kind") or kind                # stock or coin
            cx, rad = x0 + 36, 15                       # a token with its symbol's first letter: round for a coin,
            box = (cx - rad, mid - rad, cx + rad, mid + rad)    # squarer for a stock
            if what == "stock":
                d.rounded_rectangle(box, radius=7, fill=BG if selected else ROW, outline=LINE)
            else:
                d.ellipse(box, fill=BG if selected else ROW, outline=LINE)
            d.text((cx, mid), (entry["symbol"] or entry["id"]).lstrip("^")[:1].upper(), font=F["small_b"], fill=ACCENT,
                   anchor="mm")
            rx = x1 - 14
            if kind in ("stock", "coin"):              # yours: its price, and how it's done today
                if kind == "stock":
                    q = (st.quotes.get(entry["id"]) or {}).get("d") or {}
                    pct, price = _num(q.get("change_1d"), None), q.get("price")
                    shown_price = money(price, q.get("currency") or "USD", q.get("kind") or "")
                else:
                    q = (cr.quotes.get(entry["id"]) or {}).get("d") or {}
                    pct, price = _num(q.get("change_24h"), None), q.get("price")
                    shown_price = price_text(price)
                if pct is not None:
                    d.text((rx, mid), f"{pct:+.1f}%", font=F["small"], fill=DONE if pct >= 0 else WARN, anchor="rm")
                    rx -= 64
                if price is not None:
                    d.text((rx, mid), shown_price, font=F["row"], fill=TEXT if selected else BODY, anchor="rm")
                    rx -= d.textlength(shown_price, font=F["row"]) + 16
            else:                                      # found: that it's yours already, or what it is
                if self.fin_mine(what, entry["id"]):
                    right, colour = "Yours", ACCENT
                elif what == "stock":
                    right, colour = entry.get("where") or "", MUTED
                else:
                    right, colour = (f"Coin #{entry['rank']}" if entry.get("rank") else "Coin"), MUTED
                if right:
                    d.text((rx, mid), right, font=F["small"], fill=colour, anchor="rm")
                    rx -= d.textlength(right, font=F["small"]) + 16
            tx = cx + rad + 14
            font = F["row_b"] if selected else F["row"]
            name = self.fit(d, entry["name"], font, max(40, rx - tx - 70))
            d.text((tx, mid), name, font=font, fill=TEXT if selected else BODY, anchor="lm")
            if entry["symbol"]:
                d.text((tx + d.textlength(name, font=font) + 10, mid + 1), self.fit(d, entry["symbol"], F["small"], 64),
                       font=F["small"], fill=MUTED, anchor="lm")
        kind, entry = rows[sel]
        if kind == "search":
            hints = [("A", "Look up"), ("B", "Back")]
        elif kind == "found":
            hints = [("A", "Show" if self.fin_mine(entry["kind"], entry["id"]) else "Add"), ("B", "Back")]
        else:
            gone = self.confirm[0] == f"findel:{kind}:{entry['id']}"
            hints = [("A", "Show"), ("X", "Remove it" if gone else "Remove"), ("B", "Back")]
        self.footer(d, hints, credit="Yahoo Finance, CoinGecko")
        self.fb.show(img)

    def draw_stock(self, img, d, sym, top, bottom, window):
        """A stock's card, like a coin's: its name and ticker, price and change, high and low, the chart (the
        day's with the last close dotted across it), then the day's volume, the year's high and low, and
        whether its market's open."""
        F = self.fonts
        st = self.stocks
        W = self.fb.w
        pad = 24
        y0 = top + 14
        qe = st.quotes.get(sym) or {}
        q = qe.get("d") or {}
        he = st.hist.get(f"{sym}:{st.days}") or {}
        cur, kind = q.get("currency") or "USD", q.get("kind") or ""
        name = (q.get("name") or st.stock(sym)["name"]).upper()
        name = self.fit(d, name, F["small"], W - pad * 2 - 230)
        d.text((pad, y0), name, font=F["small"], fill=PI_DIM)
        if name != sym:                                    # (its ticker beside its name, as a coin's rank is)
            d.text((pad + d.textlength(name, font=F["small"]) + 10, y0), sym, font=F["small"], fill=(90, 90, 90))
        price = q.get("price")
        if price is None:
            why = st.error_of(sym)
            d.text((W / 2, (top + bottom) / 2), why or ("Waiting for prices…" if st.running else "No prices yet"),
                   font=F["row"], fill=PI_DIM, anchor="mm")
            return
        values = he.get("v") or []
        prev = q.get("prev_close")
        change = pct = None
        lo, hi = (q.get("low_1d"), q.get("high_1d")) if window == "1D" else (None, None)
        ct, cb = top + 118, bottom - 92                    # the chart's box
        if window == "1D" and prev:                        # the day: from the last close, as it's counted
            change, pct = price - prev, (price - prev) / prev * 100
        if len(values) >= 2:
            step = max(1, len(values) // (W - pad * 2))
            vals = values[::step]
            if window == "1D":
                bottom_v, top_v = min(vals + ([prev] if prev else [])), max(vals + ([prev] if prev else []))
                colour = PI_UP if (change if change is not None else vals[-1] - vals[0]) >= 0 else PI_DOWN
            else:
                bottom_v, top_v = min(vals), max(vals)
                change = price - vals[0]
                pct = change / vals[0] * 100 if vals[0] else 0
                lo, hi = min(vals), max(vals)
                colour = PI_UP if change >= 0 else PI_DOWN
            draw_chart(img, d, vals, colour, pad, ct, W - pad, cb, bottom_v, top_v)
            if window == "1D" and prev:                    # the last close, dotted across
                yb = cb - (prev - bottom_v) / ((top_v - bottom_v) or 1) * (cb - ct)
                for x in range(pad, W - pad, 10):
                    d.line((x, yb, x + 3, yb), fill=(110, 110, 110), width=1)
        else:
            d.text((W / 2, (ct + cb) / 2), "Loading the chart…" if st.running else "No chart yet",
                   font=F["small"], fill=(90, 90, 90), anchor="mm")

        d.text((pad, y0 + 22), money(price, cur, kind), font=F["price"], fill=PI_FG)
        if change is not None and pct is not None:
            colour = PI_UP if change >= 0 else PI_DOWN
            dec = 0 if cur in ("JPY", "KRW") else (2 if abs(price) >= 1 else 4)
            words = f"{change:+,.{dec}f} ({pct:+.2f}%)"
            d.text((pad, y0 + 78), words, font=F["row"], fill=colour)
            d.text((pad + d.textlength(words, font=F["row"]) + 12, y0 + 81), window, font=F["small"], fill=PI_DIM)
        if hi and lo:
            d.text((W - pad, y0), f"H: {money(hi, cur, kind)}", font=F["small"], fill=PI_DIM, anchor="ra")
            d.text((W - pad, y0 + 22), f"L: {money(lo, cur, kind)}", font=F["small"], fill=PI_DIM, anchor="ra")
        age = time.time() - qe.get("t", time.time())
        if age > 600:                                      # old numbers are kept, and say so
            mins = int(age // 60)
            d.text((W - pad, y0 + 44), f"{mins // 60} h old" if mins >= 120 else f"{mins} min old",
                   font=F["small"], fill=PI_DOWN, anchor="ra")

        y = bottom - 80
        vol = q.get("volume")
        for k, text in enumerate((f"VOL: {big_number(vol) if vol else '—'}",
                                  f"52W HIGH: {money(q.get('high_52w'), cur, kind)}",
                                  f"52W LOW: {money(q.get('low_52w'), cur, kind)}")):
            d.text((pad, y + k * 20), text, font=F["small"], fill=PI_DIM)
        live = market_open(q)
        d.text((W - pad, y), "MARKET OPEN" if live else "MARKET CLOSED", font=F["small"],
               fill=PI_UP if live else PI_DIM, anchor="ra")
        if q.get("time"):
            d.text((W - pad, y + 22), clock_at(q["time"], q.get("gmtoffset") or 0, q.get("tz") or ""),
                   font=F["row"], fill=PI_DIM, anchor="ra")

    def draw_coin(self, img, d, cid, top, bottom, window):
        """PiE-ink's coin card: name, price and change, high/low, the chart,
        then market cap, supply and the all-time high, and the community mood."""
        F = self.fonts
        cr = self.crypto
        W = self.fb.w
        pad = 24
        y0 = top + 14
        coin = cr.coin(cid) if cid else {"name": "", "symbol": ""}
        qe = cr.quotes.get(cid) or {}
        q = qe.get("d") or {}
        he = cr.hist.get(f"{cid}:{cr.days}") or {}
        name = (q.get("name") or coin["name"]).upper()
        d.text((pad, y0), name, font=F["small"], fill=PI_DIM)
        if q.get("rank"):
            d.text((pad + d.textlength(name, font=F["small"]) + 10, y0), f"#{q['rank']}",
                   font=F["small"], fill=(90, 90, 90))
        price = q.get("price")
        if price is None:
            d.text((W / 2, (top + bottom) / 2), "Waiting for prices…" if cr.running else "No prices yet",
                   font=F["row"], fill=PI_DIM, anchor="mm")
            return
        values = he.get("v") or []
        change = pct = None
        lo, hi = q.get("low_24h"), q.get("high_24h")
        ct, cb = top + 118, bottom - 92                    # the chart's box
        if len(values) < 2:
            d.text((W / 2, (ct + cb) / 2), "Loading the chart…" if cr.running else "No chart yet",
                   font=F["small"], fill=(90, 90, 90), anchor="mm")
        if len(values) >= 2:
            step = max(1, len(values) // (W - pad * 2))
            vals = values[::step]
            lo, hi = min(vals), max(vals)
            start = vals[0]
            change = vals[-1] - start
            pct = change / start * 100 if start else 0
            draw_chart(img, d, vals, PI_UP if change >= 0 else PI_DOWN, pad, ct, W - pad, cb)
        elif q.get("change_24h") is not None and window == "1D" and q["change_24h"] > -100:
            pct = q["change_24h"]
            change = price * pct / (100 + pct)

        d.text((pad, y0 + 22), price_text(price), font=F["price"], fill=PI_FG)
        if change is not None and pct is not None:
            colour = PI_UP if change >= 0 else PI_DOWN
            dec = 0 if price >= 1000 else (2 if price >= 1 else 4)
            d.text((pad, y0 + 78), f"{change:+,.{dec}f} ({pct:+.2f}%)", font=F["row"], fill=colour)
            d.text((pad + d.textlength(f"{change:+,.{dec}f} ({pct:+.2f}%)", font=F["row"]) + 12,
                    y0 + 81), window, font=F["small"], fill=PI_DIM)
        if hi and lo:
            d.text((W - pad, y0), f"H: {price_text(hi)}", font=F["small"], fill=PI_DIM, anchor="ra")
            d.text((W - pad, y0 + 22), f"L: {price_text(lo)}", font=F["small"], fill=PI_DIM, anchor="ra")
        age = time.time() - qe.get("t", time.time())
        if age > 600:                                      # PiE-ink keeps old numbers, and says so
            mins = int(age // 60)
            d.text((W - pad, y0 + 44), f"{mins // 60} h old" if mins >= 120 else f"{mins} min old",
                   font=F["small"], fill=PI_DOWN, anchor="ra")

        y = bottom - 80
        for k, text in enumerate((f"MC: ${big_number(q.get('market_cap'))}",
                                  f"SUPPLY: {big_number(q.get('circulating_supply'))}",
                                  f"ATH: {price_text(q.get('ath'))}")):
            d.text((pad, y + k * 20), text, font=F["small"], fill=PI_DIM)
        vote = q.get("sentiment_up")
        if vote is not None:
            up = int(round(float(vote)))
            label, colour = (("BULLISH", PI_UP) if up > 55 else ("BEARISH", PI_DOWN) if up < 45
                             else ("NEUTRAL", PI_DIM))
            d.text((W - pad, y), label, font=F["small"], fill=colour, anchor="ra")
            d.text((W - pad, y + 22), f"+{up}% / -{100 - up}%", font=F["row"], fill=PI_DIM, anchor="ra")
        else:
            d.text((W - pad, y), "SENTIMENT", font=F["small"], fill=PI_DIM, anchor="ra")
            d.text((W - pad, y + 22), "no vote yet", font=F["row"], fill=PI_DIM, anchor="ra")
