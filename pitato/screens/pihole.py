"""The Pi-hole page (in the Home Assistant tab): your Pi-hole's dashboard, from Pi-hole itself."""
import math
import threading
import time

from ..library import LIBRARY
from ..pihole import Busy, Denied, NotPihole, TwoFactor, dns_guess, forget_pihole, pihole_url, save_pihole
from ..theme import BG, BODY, DONE, LINE, MUTED, ROW, TEXT, WARN
from ..util import item

# the dashboard's colours (each the same thing wherever it's drawn): queries let through and blocked, in the
# chart and the top lists; the top clients; the kinds of query, in order, then the rest of them
PH_ALLOWED = (57, 135, 229)
PH_BLOCKED = (217, 89, 38)
PH_CLIENTS = (25, 158, 112)
PH_KINDS = [(25, 158, 112), (201, 133, 0), (213, 81, 129), (144, 133, 233)]
PH_REST = (78, 86, 98)
PH_AXIS = (58, 65, 76)
PH_PANELS = [("blocked", "Top blocked domains"), ("allowed", "Top allowed domains"), ("clients", "Top clients"),
             ("types", "Query types")]


def compact(n):
    """12,345 as 12.3K (for a number too wide for its place)."""
    try:
        n = float(str(n).replace(",", ""))
    except ValueError:
        return str(n)
    for size, word in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            v = n / size
            return (f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{v:.0f}") + word
    return f"{n:.0f}"


def nice_top(n):
    """The chart's top: n rounded up to 1, 2, 2.5 or 5 of its power of ten."""
    if n <= 1:
        return 1
    p = 10 ** math.floor(math.log10(n))
    for k in (1, 2, 2.5, 5, 10):
        if n <= k * p:
            return k * p
    return 10 * p


class PiholeScreen:
    """The Pi-hole page: Add your Pi-hole (A: its address, then its password, once). Then its dashboard: whether
    it's blocking, its queries today, blocked, the percentage and the domains on its lists, the last 24 hours an
    hour at a time (allowed and blocked), and below, ◀▶: its top blocked domains, top allowed domains, top
    clients, and kinds of query. Y (twice) forgets it. Asked for every few seconds while the page is open."""

    def pihole_rows(self):
        if not self.pihole.configured:
            return [item("pihole:add", "Add your Pi-hole", "action", "pihole:add")]
        return []                                      # (its dashboard: render_pihole)

    def pihole_files(self):
        return LIBRARY[self.tab_index("pihole")]["files"]

    def pihole_changed(self):
        """Pi-hole answered (on its page's thread): the page again."""
        pi = self.tab_index("pihole")
        if self.tab == pi:
            self.items[pi] = self.pihole_rows()
            if self.active and self.view == "list":
                self.dirty = True

    def pihole_close(self):
        self.pihole.stop()

    def press_pihole(self, name, repeat):
        """Not added yet: A adds it. Its dashboard: ◀▶ the lists below, Y forgets it (pressed twice), A signs in
        again or asks again when it says so. 'pass' leaves the rest to the list (L and R, X, B)."""
        ph = self.pihole
        if not ph.configured:
            if name == "a" and not repeat:
                self.open_keyboard("Your Pi-hole's address (like 192.168.1.2)", dns_guess(), self.pihole_typed,
                                   row=0, limit=120)
                return None
            return "pass" if name not in ("up", "down", "left", "right") else None
        if name in ("left", "right"):
            if not repeat:
                self.pihole_panel = (self.pihole_panel + (1 if name == "right" else -1)) % len(PH_PANELS)
                self.dirty = True
            return None
        if name in ("up", "down"):
            return None
        if name == "a":
            if not repeat and ph.error and ph.denied:
                self.pihole_ask_password(ph.url)
            elif not repeat and ph.error:
                ph.error, ph.poll_now = None, True     # try again
                ph.start()
                self.dirty = True
            return None
        if name == "y":
            if not repeat:
                if self.confirm[0] == "pihole:forget" and time.monotonic() < self.confirm[1]:
                    self.confirm = (None, 0.0)
                    self.pihole_forget()
                else:
                    self.confirm = ("pihole:forget", time.monotonic() + 4)
                    self.toast("Press Y again to forget your Pi-hole", 4)
                self.dirty = True
            return None
        return "pass"

    def pihole_hints(self, it=None):
        ph = self.pihole
        if not ph.configured:
            return [("A", "Add")] + [("L R", "Tabs"), ("B", "Back")]
        if ph.error and ph.denied:
            first = [("A", "Sign in")]
        elif ph.error:
            first = [("A", "Try again")]
        elif ph.found:
            first = [("◀▶", "Top lists")]
        else:
            first = []
        return first + [("Y", "Forget"), ("L R", "Tabs"), ("B", "Back")]

    # -- its dashboard --------------------------------------------------------------------------------------
    def render_pihole(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        ph = self.pihole
        y = self.LIST_TOP + 10
        d.text((20, y), "Home Assistant  ›  Pi-hole", font=F["small"], fill=MUTED, anchor="lm")
        right = W - 20
        where = self.fit(d, ph.where, F["small"], W // 3)
        d.text((right, y), where, font=F["small"], fill=MUTED, anchor="rm")
        right -= d.textlength(where, font=F["small"]) + 14
        values = {key: value for key, _, value, _ in ph.rows}
        if ph.found and not ph.error:                  # whether it's blocking: a word and a light, not the light alone
            on = values.get("blocking") == "On"
            word = "Blocking on" if on else "Blocking off"
            w = d.textlength(word, font=F["label"]) + 30
            d.rounded_rectangle((right - w, y - 11, right, y + 11), radius=11, fill=ROW)
            d.ellipse((right - w + 10, y - 4, right - w + 18, y + 4), fill=DONE if on else WARN)
            d.text((right - w + 24, y), word, font=F["label"], fill=TEXT if on else WARN, anchor="lm")
        top, bottom = self.LIST_TOP + 28, H - self.FOOTER - 6
        if ph.error or not ph.found:
            big, small = self.pihole_says()
            mid = (top + bottom) / 2
            d.text((W / 2, mid - 14), self.fit(d, big, F["big"], W - 40), font=F["big"], fill=TEXT, anchor="mm")
            d.text((W / 2, mid + 18), self.fit(d, small, F["small"], W - 40), font=F["small"], fill=MUTED, anchor="mm")
        else:
            rows = 5 if bottom - top >= 370 else 4
            tiles_h = 66
            panel_h = 24 + rows * 22
            chart_top = top + tiles_h + 14
            plot_h = max(48, bottom - chart_top - 14 - 22 - 12 - panel_h)
            self.pihole_tiles(d, values, top, tiles_h)
            self.pihole_chart(d, chart_top, plot_h)
            self.pihole_panel_draw(img, d, chart_top + 14 + plot_h + 22 + 12, rows)
        self.footer(d, self.pihole_hints())
        self.fb.show(img)

    def pihole_says(self):
        """What to say in place of its dashboard: (big, small)."""
        ph = self.pihole
        err = ph.error
        if not err:
            return "Asking your Pi-hole…", ph.where
        if err == "wants its password":
            return "Your Pi-hole wants its password", "A: sign in"
        if err == "wants a two-factor code":
            return "Your Pi-hole wants a two-factor code", "A: sign in with an app password instead"
        if err.startswith("too many signed in"):
            return "Your Pi-hole has too many signed in", "They run out after half an hour: try again then"
        if err == "isn't answering as a Pi-hole":
            return f"{ph.where} isn't answering as a Pi-hole", "A: try again"
        return "Your Pi-hole isn't answering", f"{ph.where}  ·  A: try again"

    def pihole_tiles(self, d, values, top, h):
        """Its four numbers, as its own dashboard has them (the percentage with a meter under it)."""
        F, W = self.fonts, self.fb.w
        tiles = [("total", "Total queries", "Queries"), ("blocked", "Queries blocked", "Blocked"),
                 ("percent", "Percentage blocked", "Percent blocked", "Blocked"),
                 ("lists", "Domains on lists", "On lists")]
        gap = 8
        tw = (W - 24 - gap * (len(tiles) - 1)) / len(tiles)
        for k, (key, *labels) in enumerate(tiles):
            x0 = 12 + k * (tw + gap)
            x1 = x0 + tw
            d.rounded_rectangle((x0, top, x1, top + h), radius=10, fill=ROW)
            label = next((t for t in labels if d.textlength(t, font=F["label"]) <= tw - 24), labels[-1])
            d.text((x0 + 12, top + 16), label, font=F["label"], fill=MUTED, anchor="lm")
            value = values.get(key, "—")
            try:
                float(value.replace(",", "").rstrip("%"))
            except ValueError:
                value = "—"                             # (one Pi-hole doesn't know: its gravity database gone)
            if d.textlength(value, font=F["big"]) > tw - 24:
                value = compact(value)
            d.text((x0 + 12, top + 39), value, font=F["big"], fill=TEXT, anchor="lm")
            if key == "percent":                        # (the meter: blocked's colour on a darker track)
                try:
                    pct = max(0.0, min(100.0, float(value.rstrip("%"))))
                except ValueError:
                    pct = 0.0
                y0 = top + h - 11
                d.rounded_rectangle((x0 + 12, y0, x1 - 12, y0 + 4), radius=2, fill=PH_AXIS)
                if pct > 0:
                    d.rounded_rectangle((x0 + 12, y0, x0 + 12 + max(4, (x1 - x0 - 24) * pct / 100), y0 + 4),
                                        radius=2, fill=PH_BLOCKED)

    def pihole_chart(self, d, top, plot_h):
        """The last 24 hours, an hour a column: allowed below, blocked on top, a gap between."""
        F, W = self.fonts, self.fb.w
        ph = self.pihole
        d.text((16, top), "Queries, last 24 hours", font=F["label"], fill=MUTED, anchor="lm")
        x = W - 16                                      # (the legend: a mark beside each word)
        for word, colour in (("Blocked", PH_BLOCKED), ("Allowed", PH_ALLOWED)):
            x -= d.textlength(word, font=F["label"])
            d.text((x, top), word, font=F["label"], fill=BODY, anchor="lm")
            d.rounded_rectangle((x - 16, top - 5, x - 6, top + 5), radius=2, fill=colour)
            x -= 30
        hours = ph.more.get("hours")
        y0, y1 = top + 14, top + 14 + plot_h            # (the plot)
        x0, x1 = 50, W - 16
        if not hours:
            d.text(((x0 + x1) / 2, (y0 + y1) / 2), "Pi-hole hasn't said yet", font=F["label"], fill=MUTED,
                   anchor="mm")
            return
        peak = nice_top(max(a + b for _, a, b in hours))
        d.line((x0, y0, x1, y0), fill=LINE)             # (its top, and its baseline: hairlines)
        d.line((x0, y1, x1, y1), fill=PH_AXIS)
        d.text((x0 - 8, y0), compact(peak), font=F["badge"], fill=MUTED, anchor="rm")
        d.text((x0 - 8, y1), "0", font=F["badge"], fill=MUTED, anchor="rm")
        slot = (x1 - x0) / len(hours)
        bw = max(2, min(24, slot - 4))
        twelve = self.setting("clock") != "24-hour"
        for i, (start, allowed, blocked) in enumerate(hours):
            cx = x0 + slot * (i + 0.5)
            ha, hb = plot_h * allowed / peak, plot_h * blocked / peak
            bx0, bx1 = cx - bw / 2, cx + bw / 2
            if ha >= 1:                                 # (rounded at its data end, square on the baseline)
                self.pihole_bar(d, (bx0, y1 - ha, bx1, y1), PH_ALLOWED, top_end=hb < 1)
            if hb >= 1:
                gap = 2 if ha >= 1 else 0
                self.pihole_bar(d, (bx0, y1 - ha - gap - hb, bx1, y1 - ha - gap), PH_BLOCKED, top_end=True)
            hour = time.localtime(start).tm_hour
            if hour % 6 == 0:
                label = (f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}" if twelve else f"{hour:02d}:00")
                d.text((cx, y1 + 11), label, font=F["badge"], fill=MUTED, anchor="mm")

    @staticmethod
    def pihole_bar(d, box, colour, top_end=True):
        """A column up from the baseline: square there, rounded at its end (whole pixels: rounding needs room)."""
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        r = min(4, (x1 - x0 - 1) // 2, (y1 - y0 - 1) // 2)
        if r >= 1 and top_end:                          # (rounded all round, then square again below its top)
            d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=colour)
            d.rectangle((x0, y0 + r, x1, y1), fill=colour)
        elif y1 >= y0:
            d.rectangle((x0, y0, x1, y1), fill=colour)

    def pihole_panel_draw(self, img, d, top, rows):
        """Below the chart, ◀▶: its top blocked and allowed domains, top clients (bars, the count at the end), or
        its kinds of query (a ring, with what each is beside it)."""
        F, W = self.fonts, self.fb.w
        key, title = PH_PANELS[self.pihole_panel % len(PH_PANELS)]
        d.text((16, top), title, font=F["label"], fill=MUTED, anchor="lm")
        for k in range(len(PH_PANELS)):                 # (which of them this is)
            cx = W - 16 - (len(PH_PANELS) - 1 - k) * 14
            on = k == self.pihole_panel % len(PH_PANELS)
            r = 4 if on else 3
            d.ellipse((cx - r, top - r, cx + r, top + r), fill=TEXT if on else PH_AXIS)
        got = self.pihole.more.get(key)
        y = top + 24
        if key == "types":
            return self.pihole_types(img, d, y, rows, got)
        items = [(str(name), v) for name, v in (got or []) if self.pihole_num(v) > 0][:rows]
        if not items:
            empty = {"blocked": "Nothing blocked yet today", "allowed": "No queries yet today",
                     "clients": "No clients yet today"}[key]
            d.text((16, y + 10), empty if got is not None else "Pi-hole hasn't said yet", font=F["label"],
                   fill=MUTED, anchor="lm")
            return
        colour = {"blocked": PH_BLOCKED, "allowed": PH_ALLOWED, "clients": PH_CLIENTS}[key]
        most = max(self.pihole_num(v) for _, v in items) or 1
        name_w = int(W * 0.44)
        bx0, bx1 = 16 + name_w + 12, W - 16 - 56
        for i, (name, v) in enumerate(items):
            cy = y + i * 22 + 8
            d.text((16, cy), self.fit(d, name, F["label"], name_w), font=F["label"], fill=BODY, anchor="lm")
            n = self.pihole_num(v)
            self.pihole_bar_h(d, (bx0, cy - 4, bx0 + max(3, (bx1 - bx0) * n / most), cy + 4), colour)
            d.text((W - 16, cy), compact(n) if n >= 100000 else f"{round(n):,}", font=F["label"], fill=TEXT,
                   anchor="rm")

    @staticmethod
    def pihole_num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def pihole_bar_h(d, box, colour):
        """A bar from the left: square there, rounded at its end."""
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        r = min(4, (x1 - x0 - 1) // 2, (y1 - y0 - 1) // 2)
        if r >= 1:                                      # (rounded all round, then square again but at its end)
            d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=colour)
            d.rectangle((x0, y0, x1 - r, y1), fill=colour)
        elif x1 >= x0:
            d.rectangle((x0, y0, x1, y1), fill=colour)

    def pihole_types(self, img, d, top, rows, got):
        """Its kinds of query: a ring (the four most, then the rest), and beside it each with its share."""
        F, W = self.fonts, self.fb.w
        kinds = sorted(((str(k), self.pihole_num(v)) for k, v in (got or [])), key=lambda kv: -kv[1])
        kinds = [kv for kv in kinds if kv[1] > 0]
        total = sum(v for _, v in kinds)
        if not total:
            d.text((16, top + 10), "No queries yet today" if got is not None else "Pi-hole hasn't said yet",
                   font=F["label"], fill=MUTED, anchor="lm")
            return
        shown = kinds[:min(4, rows - 1 if len(kinds) > rows else rows)]   # (all of them beside it: the rest
        rest = total - sum(v for _, v in shown)                             # as one, if there's no room)
        parts = [(k, v, PH_KINDS[i]) for i, (k, v) in enumerate(shown)] + ([("Other", rest, PH_REST)] if rest > 0
                                                                            else [])
        size = min(rows * 22 - 4, 112)
        cx, cy = 16 + size / 2, top - 4 + size / 2
        img.paste(*self.pihole_ring(parts, total, size, (int(cx - size / 2), int(cy - size / 2))))
        lx, lx1 = 16 + size + 24, min(W - 16, 16 + size + 24 + 260)
        for i, (name, v, colour) in enumerate(parts[:rows]):
            y = top + i * 22 + 8
            d.rounded_rectangle((lx, y - 5, lx + 10, y + 5), radius=2, fill=colour)
            d.text((lx + 18, y), name, font=F["label"], fill=BODY, anchor="lm")
            d.text((lx1, y), f"{100 * v / total:.1f}%", font=F["label"], fill=TEXT, anchor="rm")

    @staticmethod
    def pihole_ring(parts, total, size, at):
        """The ring, drawn four times bigger and made small (smooth edges), a sliver of the background between
        its parts: (image, where, mask) to paste."""
        from PIL import Image, ImageDraw
        k = 4
        big = int(size * k)
        ring = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        r = ImageDraw.Draw(ring)
        start = -90.0
        gap = math.degrees(2 * k / (big / 2)) if len(parts) > 1 else 0   # (2 pixels, at its edge)
        for _, v, colour in parts:
            sweep = 360.0 * v / total
            if sweep - gap > 0.2:
                r.pieslice((0, 0, big - 1, big - 1), start + gap / 2, start + sweep - gap / 2, fill=colour + (255,))
            start += sweep
        hole = big * 0.30
        r.ellipse((hole, hole, big - 1 - hole, big - 1 - hole), fill=(0, 0, 0, 0))
        small = ring.resize((int(size), int(size)), Image.LANCZOS)
        return small, at, small

    # -- adding it: its address, then (if it has one) its password, checked on a thread of their own --------
    def pihole_typed(self, text):
        url = pihole_url(text)
        if not url:
            self.toast("That isn't an address. Try 192.168.1.2", 4)
            return
        self.toast(f"Looking for your Pi-hole at {url.split('://', 1)[1]}…", 10)
        self.pihole_job("probe", url)

    def pihole_ask_password(self, url):
        self.open_keyboard("Your Pi-hole's password (or an app password)", "",
                           lambda pw: self.pihole_job("signin", url, pw), strip=False, limit=120)

    def pihole_job(self, what, url, password=""):
        def work():
            try:
                if what == "probe":
                    version, needs = self.pihole.probe(url)
                    out = ("needs" if needs else "ok", url, "", version, None)
                else:
                    version, sid = self.pihole.check(url, password)
                    out = ("ok", url, password, version, sid)
            except Denied:
                out = ("denied", url, "", None, None)
            except TwoFactor:
                out = ("twofactor", url, "", None, None)
            except Busy:
                out = ("busy", url, "", None, None)
            except NotPihole:
                out = ("notpihole", url, "", None, None)
            except Exception:
                out = ("away", url, "", None, None)
            self.pihole_done = out
            self.dirty = True
        if what == "signin":
            self.toast("Signing in to your Pi-hole…", 10)
        threading.Thread(target=work, daemon=True, name="pihole-add").start()

    def pihole_tick(self):
        """(media mode's own thread) what the Pi-hole said, as it's added: the next step."""
        (what, url, password, version, sid), self.pihole_done = self.pihole_done, None
        where = url.split("://", 1)[1]
        if self.tab != self.tab_index("pihole") or self.view not in ("list", "keys"):
            return                                     # (gone elsewhere meanwhile)
        if what == "ok":
            self.pihole_save(url, password, version, sid)
        elif what == "needs":
            self.msg = None
            self.pihole_ask_password(url)
        elif what == "denied":
            self.toast("Your Pi-hole didn't take that password", 4)
            self.pihole_ask_password(url)
        elif what == "twofactor":
            self.toast("Your Pi-hole wants a two-factor code too: use an app password", 5)
            self.pihole_ask_password(url)
        elif what == "busy":
            self.toast("Your Pi-hole has too many signed in: try again in a while", 5)
        elif what == "notpihole":
            self.toast(f"{where} doesn't answer as a Pi-hole", 4)
        else:
            self.toast(f"Can't reach {where}", 4)
        self.dirty = True

    def pihole_save(self, url, password, version=None, sid=None):
        try:
            save_pihole(url, password)
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return
        ph = self.pihole
        ph.loaded = None                               # (signed in afresh: whatever it had before, gone)
        ph.load(self.pihole_files())
        ph.version, ph.sid = version, sid              # (the session it signed in with, kept)
        ph.poll_now = True
        ph.start()
        pi = self.tab_index("pihole")
        self.items[pi] = self.pihole_rows()
        self.sels[pi] = 0
        self.toast("Signed in to your Pi-hole" if password else "Your Pi-hole's added", 3)

    def pihole_forget(self):
        ph = self.pihole
        url, sid = ph.url, ph.sid
        try:
            forget_pihole()
        except OSError as ex:
            self.toast(f"Couldn't change static/pihole.txt ({ex.strerror or ex})", 4)
            return
        ph.stop()
        if sid:                                        # (its session ended, rather than left to run out)
            threading.Thread(target=ph.sign_out, args=(url, sid), daemon=True).start()
        ph.load(self.pihole_files())
        pi = self.tab_index("pihole")
        self.items[pi] = self.pihole_rows()
        self.sels[pi] = 0
        self.toast(f"Forgot {url.split('://', 1)[1]}", 3)
