"""Drawing: the fonts, the status bar and tabs, lists and grids, and the buttons along the bottom."""
import os
import time

from ..theme import (
    ACCENT, BADGE, BG, BODY, DONE, FONT, FONT_BOLD, FONT_MONO, FONT_MONO_BOLD, FONT_THIN, FONT_UI, FONT_UI_BOLD, LINE,
    MUTED, ROW, TEXT, WARN)
from ..config import home_dir
from ..util import clock, human_size, short_path
from ..system import cpu_temp, HOT_C, on_pc, wifi_bars, wifi_quality
from ..library import LIBRARY, LISTEN_KINDS
from ..screen import slow_pi
from ..home import mix
from .chromium import CHROME_HELP, CHROME_NOTES


KEY_FILL = (62, 68, 79)      # a button, in the hints along the bottom
FOOT_NOTE = (206, 211, 218)  # the home screen's line about the app picked
BASE_ROOM = 480 - 48 - 76    # the GPi Case's screen between its bars: what a page with a set layout is drawn for
FULL_VIEWS = ("list", "now", "photo", "pdf", "text")   # what Full screen apps puts on the whole screen
UPDATE_DOTS = 3              # the dots under Updating Pie-tato, lit one after another
TAP_KEYS = {"A": "a", "B": "b", "X": "x", "Y": "y", "L": "l", "R": "r", "L2": "l2", "R2": "r2", "START": "start",
            "ST": "start", "SELECT": "select", "SEL": "select", "HOME": "home", "ANY": "a",
            "▲": "up", "▼": "down", "◀": "left", "▶": "right"}   # a hint's button, as a tap on the web page presses it


def tap_buttons(label):
    """The buttons a hint along the bottom stands for, left to right: A's a, L R's l and r, ▲▼'s up and down. (PAD's:
    none, it's any way at all.)"""
    parts = label.split() if " " in label else list(label) if label and set(label) <= set("▲▼◀▶") else [label]
    out = [TAP_KEYS.get(p) for p in parts]
    return out if out and all(out) else []


class Bar:
    """How tall a bar is (or where a list starts, under them): its own size, or, while Settings > Full screen apps
    has an app on the whole screen, what's left without the bars. Asked of the class itself: its own size."""

    def __init__(self, shown, full):
        self.shown, self.full = shown, full

    def __get__(self, screen, owner=None):
        return self.shown if screen is None or not screen.full_app() else self.full


class DrawScreen:
    """Drawing: the fonts, the status bar and tabs, lists and grids, and the buttons along the bottom."""

    # -- drawing -------------------------------------------------------------
    STATUS_H, HEADER, LIST_TOP = Bar(26, 0), Bar(68, 40), Bar(76, 48)   # status bar, tab line (Full screen apps: the
    ROW_H, FOOTER = 48, Bar(48, 8)                                      # app's name), first row
    GRID_COLS, CELL_H = 4, 116

    def full_app(self):
        """Settings > Full screen apps: an app on the whole screen, no status bar, tabs or buttons along the
        bottom (its Controls, X, has the buttons): its page, Now playing, a picture or a document. Not the home
        screen, Controls, a box to type in or a game's menu; nor a sim, which has its own (SELECT)."""
        if getattr(self, "view", None) not in FULL_VIEWS or not getattr(self, "state", None):
            return False
        try:
            return self.setting("app_full") == "On" and self.tab_type() != "sim"
        except (AttributeError, IndexError, KeyError, TypeError):
            return False

    def spare(self):
        """Room beyond the GPi Case's screen between its bars, for a page with a set layout to spread into: a
        taller screen's, and the bars' while Full screen apps is on."""
        return max(0, (self.fb.h if self.fb else 480) - self.FOOTER - self.LIST_TOP - BASE_ROOM)

    def load_fonts(self):
        if self.fonts:
            return
        from PIL import ImageFont

        def f(path, size):
            try:
                if path in (FONT_THIN, FONT_UI, FONT_UI_BOLD) and path.endswith(".otf"):
                    basic = ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else ImageFont.LAYOUT_BASIC
                    return ImageFont.truetype(path, size, layout_engine=basic)   # (Inter: much quicker so)
                return ImageFont.truetype(path, size)
            except OSError:
                return ImageFont.load_default()
        self.fonts = {
            "tab": f(FONT, 17), "tab_b": f(FONT_BOLD, 17),
            "row": f(FONT, 20), "row_b": f(FONT_BOLD, 20), "small": f(FONT, 15),
            "key": f(FONT_BOLD, 13), "badge": f(FONT_BOLD, 11), "big": f(FONT_BOLD, 24),
            "note": f(FONT, 72), "mono_s": f(FONT_MONO, 15), "mono_l": f(FONT_MONO, 20),
            "head": f(FONT_BOLD, 18), "status": f(FONT, 13), "status_b": f(FONT_BOLD, 13),
            "code": f(FONT_MONO, 44), "price": f(FONT_BOLD, 46), "mid": f(FONT_BOLD, 24),
            "clock": f(FONT_BOLD, 52), "small_b": f(FONT_BOLD, 15), "label": f(FONT, 14), "temp": f(FONT_BOLD, 72),
            "home_clock": f(FONT_THIN, 52), "wx_temp": f(FONT_THIN, 52), "home_ampm": f(FONT_UI, 17),
            "home_date": f(FONT_UI, 17), "home_label": f(FONT_UI, 14), "home_foot": f(FONT_UI, 15),
            "home_pop_head": f(FONT_UI_BOLD, 11), "home_pop_title": f(FONT_UI_BOLD, 18), "home_pop_sub": f(FONT_UI, 14),
            "home4_clock": f(FONT_BOLD, 48), "home4_date": f(FONT, 18),
            "home4_temp": f(FONT_BOLD, 34), "home4_label": f(FONT, 13),
            "keycap": f(FONT, 20), "face": f(FONT, 40), "chat": f(FONT, 18),
            "co_code": f(FONT_MONO_BOLD if os.path.exists(FONT_MONO_BOLD) else FONT_MONO, 17),
            "co_mono_xs": f(FONT_MONO, 13), "co_z1": f(FONT_BOLD, 16), "co_z2": f(FONT_BOLD, 21),
            "co_z3": f(FONT_BOLD, 27),
            "www": f(FONT, 18), "www_b": f(FONT_BOLD, 18), "www_h1": f(FONT_BOLD, 25), "www_h2": f(FONT_BOLD, 21),
            "www_h3": f(FONT_BOLD, 19),
        }

    def list_top(self):
        crumbs = (self.tab_type() in ("browser", "plex") or self.parent_of(self.tab) is not None
                  or (self.tab_type() == "radio" and self.radio_stack)
                  or (self.tab_type() == "games" and getattr(self, "games_q", None)))
        return self.LIST_TOP + (28 if crumbs else 0)

    def visible_rows(self):
        h = self.fb.h if self.fb else 480
        return max((h - self.FOOTER - self.list_top()) // self.ROW_H, 1)

    def grid_rows(self):
        h = self.fb.h if self.fb else 480
        return max((h - self.FOOTER - self.LIST_TOP) // self.CELL_H, 1)

    def grid_cols(self):
        """Photos' columns: four on the GPi Case's screen, more on a wider one."""
        w = self.fb.w if self.fb else 640
        return max(self.GRID_COLS, (w - 32) // 152)

    def canvas(self, bg=BG):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (self.fb.w, self.fb.h), bg)
        return img, ImageDraw.Draw(img)

    # -- the web page's copy of the screen: what a tap on it does, where ----------------------------------------
    def tappable(self, box, *what):
        """A tap in box (x0, y0, x1, y1, in the menus' pixels) on the web page's copy of the screen does what (web.py's
        tap_do says how). Where two overlap, the one put down last wins, as what's drawn last is on top. (Put down
        while the screen's drawn: flush keeps them with the picture.)"""
        taps = getattr(self, "taps_new", None)
        if taps is not None:
            taps.append((tuple(box), what))

    def tap_mark(self):
        taps = getattr(self, "taps_new", None)
        return len(taps) if taps is not None else 0

    def taps_cut(self, mark):
        """The places put down since mark (tap_mark's), taken up: kept with a picture that's kept, and put down again
        each time it's used (tap_again)."""
        taps = getattr(self, "taps_new", None)
        if taps is None:
            return []
        cut = taps[mark:]
        del taps[mark:]
        return cut

    def tap_again(self, kept):
        taps = getattr(self, "taps_new", None)
        if taps is not None and kept:
            taps.extend(kept)

    def tap_hint(self, x0, x1, y0, y1, label):
        """A hint's button, tappable over the whole of it (the button and its words); one for two buttons (L R,
        ▲▼), each its half."""
        names = tap_buttons(label)
        if len(names) == 1:
            self.tappable((x0, y0, x1, y1), "keys", names[0])
        elif len(names) == 2:
            mid = (x0 + x1) / 2
            self.tappable((x0, y0, mid, y1), "keys", names[0])
            self.tappable((mid, y0, x1, y1), "keys", names[1])

    def tap_arrows(self, y0, y1, left, right):
        """A picked row's ◀ value ▶, its ◀ ending at left and its ▶ at right: each a way to change it."""
        self.tappable((left - 32, y0, left + 6, y1), "keys", "left")
        self.tappable((right - 26, y0, right + 18, y1), "keys", "right")

    def tap_rows(self, x0, x1, y, h, first, last, *what):
        """A list's rows on the screen, first to last (items), from y down, h apart: each tappable, as what + (its
        number,)."""
        for r, i in enumerate(range(first, last)):
            self.tappable((x0, y + r * h, x1, y + (r + 1) * h), *what, i)

    @staticmethod
    def fit(d, text, font, width):
        if d.textlength(text, font=font) <= width:
            return text
        while text and d.textlength(text + "…", font=font) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, d, text, font, width, lines=2):
        words, out, cur = text.split(), [], ""
        for w in words:
            if d.textlength((cur + " " + w).strip(), font=font) <= width:
                cur = (cur + " " + w).strip()
            else:
                out.append(cur)
                cur = w
        out.append(cur)
        out = [l for l in out if l]
        if len(out) > lines:
            out = out[:lines - 1] + [self.fit(d, " ".join(out[lines - 1:]), font, width)]
        return [self.fit(d, l, font, width) for l in out]

    def key_w(self, d, label):
        if len(label) == 1:
            return 22
        return max(d.textlength(label, font=self.fonts["key"]) + 14, 24)

    def key(self, d, x, y, label, on=False):
        """Button icon (a dot round a letter, a pill round a word), vertically centred on y, lit when what it
        turns on is on. Returns end x."""
        F = self.fonts
        w = self.key_w(d, label)
        box = (x, y - 11, x + w, y + 11)
        if len(label) == 1:
            d.ellipse(box, fill=ACCENT if on else KEY_FILL)
        else:
            d.rounded_rectangle(box, radius=11, fill=ACCENT if on else KEY_FILL)
        d.text((x + w / 2, y), label, font=F["key"], fill=BG if on else TEXT, anchor="mm")
        return x + w

    def footer(self, d, items, right=None, credit=None, plain=False, pill=True, always=False):
        """Button hints along the bottom (key, label[, lit]) and a note on the right. A credit (where the numbers
        come from) is always shown, as clearly as the hints: any hint that would run into it is left out instead.
        plain: the home screen's, straight onto what's behind it under a thin line, in its own typeface. pill:
        a notice above it, if there's one (False: it's put up later, over what's drawn after). always: even with
        Full screen apps on (an are-you-sure's buttons)."""
        F, W, H = self.fonts, self.fb.w, self.fb.h
        if self.full_app() and not plain and not always:   # Full screen apps: no buttons, a credit small in the corner
            if credit:
                d.text((W - 12, H - 6), credit, font=F["label"], fill=MUTED, anchor="rd")
            if pill:
                self.msg_pill(d)
            return
        fh = type(self).FOOTER if always else self.FOOTER   # (an are-you-sure's: as tall as ever, even so)
        y = H - fh // 2
        font = F["home_foot"] if plain else F["small"]
        if plain:
            d.line((28, H - fh + 4, W - 28, H - fh + 4), fill=LINE)
        else:
            d.rectangle((0, H - fh, W, H), fill=BG)
            d.line((0, H - fh, W, H - fh), fill=LINE)
        room = W - 20 - (d.textlength(credit, font=font) + 18 if credit else 0)
        x = 28 if plain else 20
        for it in items:
            k, label, on = it[0], it[1], len(it) > 2 and bool(it[2])
            if credit and x + self.key_w(d, k) + 7 + d.textlength(label, font=font) > room:
                break
            x0 = x
            x = self.key(d, x, y, k, on) + (9 if plain else 7)
            d.text((x, y), label, font=font, fill=TEXT if plain else BODY, anchor="lm")
            x += d.textlength(label, font=font) + (26 if plain else 18)
            self.tap_hint(x0 - 8, x - (17 if plain else 9), H - fh, H, k)   # (halfway to the next)
        if credit:
            d.text((W - 20, y), credit, font=font, fill=BODY, anchor="rm")
        elif right:
            end = W - 28 if plain else W - 20
            if x - (10 if plain else 0) + d.textlength(right, font=font) < end:   # (16 apart is enough, there)
                d.text((end, y), right, font=font, fill=FOOT_NOTE if plain else MUTED, anchor="rm")
        if pill:
            self.msg_pill(d)

    def msg_pill(self, d):
        """A short notice (toast) above the footer."""
        if not self.msg:
            return
        F, W, H = self.fonts, self.fb.w, self.fb.h
        msg = self.fit(d, self.msg, F["small"], W - 72)
        mw = d.textlength(msg, font=F["small"]) + 32
        y0 = H - self.FOOTER - 46
        d.rounded_rectangle(((W - mw) / 2, y0, (W + mw) / 2, y0 + 34), radius=17, fill=ROW)
        d.text((W / 2, y0 + 17), msg, font=F["small"], fill=TEXT, anchor="mm")

    # status bar and headers -----------------------------------------------------
    def status_signature(self):
        t = cpu_temp()
        return (time.strftime("%H:%M"), wifi_bars(wifi_quality()),
                None if t is None else round(t), self.kind, self.meta.get("song"))

    def status_bar(self, d, clock=True):
        F, W = self.fonts, self.fb.w
        y = self.STATUS_H // 2 + 1
        if clock:
            d.text((20, y), self.clock_text(), font=F["status_b"], fill=BODY, anchor="lm")
        x = W - 20
        bars = wifi_bars(wifi_quality())
        for k in range(4):                       # signal bars, weakest on the left
            bx = x - (3 - k) * 6 - 4
            h = 4 + k * 3
            d.rectangle((bx, y + 6 - h, bx + 3, y + 6), fill=TEXT if k < bars else LINE)
        x -= 34
        if bars == 0:
            d.text((x, y), "No WiFi", font=F["status"], fill=WARN, anchor="rm")
            x -= d.textlength("No WiFi", font=F["status"]) + 14
        t = cpu_temp()
        if t is not None:
            txt = f"{t:.0f}°C"
            d.text((x, y), txt, font=F["status"], fill=WARN if t >= HOT_C else MUTED, anchor="rm")
            x -= d.textlength(txt, font=F["status"]) + 14
        if self.proc and self.kind in LISTEN_KINDS and self.cur:
            what = self.meta.get("song") or self.meta.get("title") or self.cur["title"]
            txt = self.fit(d, "♪ " + what, F["status"], max(x - 120, 40))
            d.text((x, y), txt, font=F["status"], fill=ACCENT, anchor="rm")

    def header(self, img, d):
        """Status bar plus the tab strip, scrolled so the current tab shows (Full screen apps: just the app's name)."""
        from PIL import Image, ImageDraw
        if self.full_app():
            self.app_title(d, LIBRARY[self.strip_tab()]["name"])
            return
        self.status_bar(d)
        F, W = self.fonts, self.fb.w
        vis = self.visible_tabs()
        cur = vis.index(self.strip_tab())
        names = []
        for i in vis:
            tab = LIBRARY[i]
            name = tab["name"]
            if self.proc and ((self.kind == "audio" and tab.get("kind") == "audio")
                              or (self.kind == "radio" and tab["type"] == "radio")):
                name = "♪ " + name
            names.append(name)
        fonts = [F["tab_b"] if i == cur else F["tab"] for i in range(len(names))]
        widths = [d.textlength(n, font=f) for n, f in zip(names, fonts)]
        gap, xs, x = 20, [], 0
        for w in widths:
            xs.append(x)
            x += w + gap
        total, avail = x - gap, W - 40
        off = self.tab_off
        if total <= avail:
            off = 0
        else:
            left, right = xs[cur], xs[cur] + widths[cur]
            if left - off < 0:
                off = left
            if right - off > avail:
                off = right - avail
            # keep the neighbours in view too, so you can see where L/R go next
            if cur > 0 and xs[cur - 1] < off:
                off = max(off - (off - xs[cur - 1]), right - avail, 0)
            if cur + 1 < len(xs) and xs[cur + 1] + widths[cur + 1] - off > avail:
                off = min(xs[cur + 1] + widths[cur + 1] - avail, left)
            off = max(0, min(off, total - avail))
        self.tab_off = off
        strip_h = self.HEADER - self.STATUS_H
        strip = Image.new("RGB", (avail, strip_h), BG)
        sd = ImageDraw.Draw(strip)
        y = strip_h // 2 - 2
        for i, (n, f, w) in enumerate(zip(names, fonts, widths)):
            tx = xs[i] - off
            if tx < 0 or tx + w > avail:      # only whole tabs; arrows show the rest
                continue
            sd.text((tx, y), n, font=f, fill=TEXT if i == cur else MUTED, anchor="lm")
            if i == cur:
                sd.rounded_rectangle((tx, strip_h - 7, tx + w, strip_h - 4), radius=1, fill=ACCENT)
            self.tappable((20 + tx - gap / 2, self.STATUS_H, 20 + tx + w + gap / 2, self.HEADER), "tab", vis[i])
        img.paste(strip, (20, self.STATUS_H))
        cy = self.STATUS_H + y
        if off > 0:
            d.text((10, cy), "‹", font=F["tab_b"], fill=MUTED, anchor="mm")
            self.tappable((0, self.STATUS_H, 20, self.HEADER), "tabs", -1)
        if off < total - avail:
            d.text((W - 10, cy), "›", font=F["tab_b"], fill=MUTED, anchor="mm")
            self.tappable((W - 20, self.STATUS_H, W, self.HEADER), "tabs", 1)
        d.line((0, self.HEADER, W, self.HEADER), fill=LINE)

    def app_title(self, d, title, right=None, right_fill=MUTED):
        """Full screen apps' top: the app's name (or Now playing, a document's) and a note on the right, no status
        bar."""
        F, W = self.fonts, self.fb.w
        y = self.HEADER // 2
        rw = d.textlength(right, font=F["small"]) + 24 if right else 0
        d.text((20, y), self.fit(d, title, F["head"], W - 40 - rw), font=F["head"], fill=TEXT, anchor="lm")
        if right:
            d.text((W - 20, y), right, font=F["small"], fill=right_fill, anchor="rm")
        d.line((0, self.HEADER, W, self.HEADER), fill=LINE)

    def title_row(self, d, title, right=None, right_fill=MUTED):
        """Status bar plus a plain title, for screens that aren't tabs (Full screen apps: the title, no status bar)."""
        if self.full_app():
            self.app_title(d, title, right, right_fill)
            return
        self.status_bar(d)
        F, W = self.fonts, self.fb.w
        y = (self.STATUS_H + self.HEADER) // 2
        rw = d.textlength(right, font=F["small"]) + 24 if right else 0
        d.text((20, y), self.fit(d, title, F["head"], W - 40 - rw), font=F["head"],
               fill=TEXT, anchor="lm")
        if right:
            d.text((W - 20, y), right, font=F["small"], fill=right_fill, anchor="rm")
        d.line((0, self.HEADER, W, self.HEADER), fill=LINE)

    def scrollbar(self, d, top, rows, n, t0, t1):
        if n <= rows:
            return
        sx = self.fb.w - 10
        d.rounded_rectangle((sx, t0, sx + 4, t1), radius=2, fill=LINE)
        th = max((t1 - t0) * rows / n, 24)
        ty = t0 + (t1 - t0 - th) * top / max(n - rows, 1)
        d.rounded_rectangle((sx, ty, sx + 4, ty + th), radius=2, fill=BODY)

    def row_right(self, it):
        """Text and colour on the right of a list row, plus resume fraction."""
        kind = it["kind"]
        if kind in ("light", "scene", "lightsoff", "lightscenes"):
            return self.lights_right(it)
        if kind == "info":
            return it["sub"], WARN if it.get("warn") else TEXT, None
        if kind == "action":
            if self.confirm[0] == it["src"]:
                return "press A again", ACCENT, None
            if it["src"] == "update":                  # (New version, or Finish updating: lit; Up to date: not)
                sub = it.get("sub", "")
                return sub, MUTED if sub == "Up to date" else ACCENT, None
            return "", MUTED, None
        if kind in ("radio", "radiodir", "radiosearch", "plexsearch", "jfsearch", "chdir", "chsearch", "chplex",
                    "chretry", "chwait"):
            return it.get("sub", ""), MUTED, None
        if kind in ("plexvideo", "jfvideo"):
            length, off = it.get("dur") or 0, it.get("off") or 0
            year = f"{it['sub']}  " if it.get("ptype") == "movie" and it.get("sub") else ""
            if off > 10 and length and off < length - 30:
                return f"{clock(length - off)} left", ACCENT, off / length
            if it.get("watched"):
                return "✓ " + year + clock(length), DONE, None
            return year + (clock(length) if length else ""), MUTED, None
        if kind in ("child", "game", "wwwgo", "wwwsearch", "wwwtype", "wwwchromium", "wwwpage"):
            return it.get("sub", ""), MUTED, None
        if kind == "hasettings":                       # (the Home tab's: where it is, or set it up)
            return it.get("sub", ""), MUTED if self.hass.configured else ACCENT, None
        if kind == "plexwant":
            return "not on your server", MUTED, None
        if kind in ("plexdir", "jfdir"):
            if it.get("unwatched"):
                return f"{it['unwatched']} unwatched", ACCENT, None
            return it.get("sub", ""), MUTED, None
        if kind == "live":
            return it.get("sub") or "live", MUTED, None
        if self.tab_type() == "browser":
            if kind == "up":
                return "", MUTED, None
            if kind in ("netroot", "netpc", "netadd"):
                return it.get("sub", ""), MUTED, None
            if kind == "netshare" or (kind == "dir" and self.is_net(it["src"])):
                return "", MUTED, None                 # (no counting what's in it: a trip to the computer)
            if "size" in it:
                return human_size(it["size"]), MUTED, None
            if kind == "dir":
                try:
                    n = len([x for x in os.listdir(it["src"])
                             if self.show_hidden or not x.startswith(".")])
                    return f"{n} item{'s' if n != 1 else ''}", MUTED, None
                except OSError:
                    return "", MUTED, None
            try:
                return human_size(os.path.getsize(it["src"])), MUTED, None
            except OSError:
                return "", MUTED, None
        if kind == "video":
            st = self.shrinker.status(it["src"])
            if st:                                     # too big for this Pi: being made smaller
                return (f"converting {st[1]}%" if st[0] == "converting" else "to convert"), MUTED, None
        length = self.length(it)
        saved = self.state["pos"].get(it["key"], 0)
        resume = self.resume_at(it)
        if saved == -1:
            return "✓ " + (clock(length) if length else "watched"), DONE, None
        if resume:
            if length:
                return f"{clock(length - resume)} left", ACCENT, resume / length
            return f"at {clock(resume)}", ACCENT, None
        if "://" in it["src"]:
            return (clock(length) if length else ""), MUTED, None
        if it["src"].startswith("ia:"):                # an old cartoon: its year
            return (clock(length) if length else it.get("sub", "")), MUTED, None
        return (clock(length) if length else "…"), MUTED, None

    def badge(self, d, x, mid, it):
        F = self.fonts
        kind = it["kind"]
        if kind == "up":
            label, colour = "UP", MUTED
        elif kind in ("dir", "netshare"):
            label, colour = "DIR", BADGE["dir"]
        elif kind in ("netroot", "netpc", "netadd"):
            label, colour = {"netroot": "NET", "netpc": "PC", "netadd": "ADD"}[kind], BADGE["dir"]
        else:
            ext = os.path.splitext(it["src"])[1][1:].upper()[:4] or "FILE"
            label, colour = ext, BADGE.get(kind, MUTED)
        d.rounded_rectangle((x, mid - 10, x + 40, mid + 10), radius=5, outline=colour, width=1)
        d.text((x + 20, mid), label, font=F["badge"], fill=colour, anchor="mm")
        return x + 52

    def list_hints(self):
        ttype = self.tab_type()
        items = self.tab_items()
        sel = self.sels.get(self.tab, 0)
        if ttype == "lights":
            return self.lights_hints(items[sel] if items and sel < len(items) else None)
        if ttype == "pihole":
            return self.pihole_hints(items[sel] if items and sel < len(items) else None)
        if ttype == "www":
            it = items[sel] if items and sel < len(items) else {}
            kept = it.get("key", "").startswith(("www:mark:", "www:past:"))
            shut = it.get("key") == "www:chromium" and self.chromium_up()   # (Chromium, open: Y closes it)
            return ([("A", "Open"), ("START", "Search")] + ([("Y", "Remove")] if kept else [])
                    + ([("Y", "Close it")] if shut else []) + [("L R", "Tabs"), ("B", "Back")])
        first = ("A", "Play")
        if ttype == "browser":
            first = ("A", "Open")
        elif ttype == "photos":
            first = ("A", "View")
        elif ttype == "radio":
            it = items[sel] if items and sel < len(items) else {}
            first = ("A", "Open" if it.get("kind") in ("radiodir", "radiosearch") else "Listen")
        elif ttype == "system":
            first = ("A", "Select")
        elif ttype in ("plex", "jellyfin"):
            it = items[sel] if items and sel < len(items) else {}
            first = ("A", "Watch" if it.get("kind") == "live" else
                     "Open" if it.get("kind") not in ("plexvideo", "jfvideo") else
                     "Resume" if it.get("off", 0) > 10 else "Play")
        elif items and sel < len(items) and self.resume_at(items[sel]):
            first = ("A", "Resume")
        hints = [first, ("L R", "Tabs")]
        if ttype == "browser" and self.is_net(self.cwd):
            pc = items and sel < len(items) and items[sel]["kind"] == "netpc"
            hints += [("B", "Up")] + ([("Y", "Forget")] if pc else [] if self.cwd.startswith("net:") else
                                      [("Y", "Hidden")])
        elif ttype == "browser":
            hints += [("B", "Up" if self.cwd.rstrip("/") != home_dir() and self.cwd != "/" else "Home"),
                      ("Y", "Hidden")]
        elif ttype == "photos":
            hints += [("START", "Slideshow"), ("B", "Home")]
            if self.picking == "wallpaper":
                hints = [("A", "Use as background"), ("B", "Cancel")]
            elif self.picking == "bot":
                hints = [("A", "Send to your bot"), ("B", "Cancel")]
        elif ttype == "system":
            hints = [first, ("SELECT", "Dashboard"), ("L R", "Tabs"), ("B", "Home")]
        elif ttype in ("plex", "jellyfin"):
            stack = self.plex_stack if ttype == "plex" else self.jf_stack
            hints += [("B", "Back" if len(stack) > 1 else "Home")]
        else:
            hints += [("X", "Controls"), ("B", "Home")]
        if self.kind in LISTEN_KINDS and ttype != "photos":
            hints.append(("START", "Now playing"))
        if not items:
            hints = [h for h in hints if h[0] not in ("A", "START")]
        if self.parent_of(self.tab) is not None:
            hints = [("B", "Back") if h[0] == "B" else h for h in hints]
        if ttype == "group":
            hints = [("A", "Open"), ("L R", "Tabs"), ("B", "Home")] + hints[4:]
        if ttype == "games":                           # (START: a game found by name, not Now playing; L R
            act = self.game_hint(items[sel]) if items and sel < len(items) else None   # on its Controls, for room)
            finding = self.art_finder is not None and self.art_finder.busy
            some = any(it["kind"] == "game" for it in items)
            back = ("B", "All games") if self.games_q else None
            hints = (([("A", act)] if act else []) + ([("Y", "Find pictures")] if some and not finding else [])
                     + [back if back and h[0] == "B" else h for h in hints if h[0] not in ("A", "START", "L R")]
                     + [("START", "Search")])
        if ttype == "channels" and items and sel < len(items):
            it = items[sel]
            first = {"chdir": "Open", "chsearch": "Open", "chplex": "Sign in", "chretry": "Try again"}.get(
                it["kind"], "Resume" if self.resume_at(it) else "Watch")
            hints = ([] if it["kind"] == "chwait" else [("A", first)]) + hints[1:]
        if ttype == "channels" and not items and self.status.get(self.tab) in ("error", "noplex"):
            hints = [("A", "Try again" if self.status.get(self.tab) == "error" else "Sign in"),
                     ("L R", "Tabs"), ("B", "Back")]
        if ttype == "radio" and self.radio_stack:
            hints = [first, ("Y", "Save"), ("L R", "Tabs"), ("B", "Back")]
            if self.kind in LISTEN_KINDS:
                hints.append(("START", "Now playing"))
            if not items:
                hints = [("A", "Try again") if self.status.get(self.tab) == "error" else ("L R", "Tabs"),
                         ("B", "Back")]
        return hints

    def empty_state(self, d, big, small):
        F, W, H = self.fonts, self.fb.w, self.fb.h
        mid = (self.HEADER + H - self.FOOTER) / 2
        d.text((W / 2, mid - 16), big, font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, mid + 18), small, font=F["small"], fill=MUTED, anchor="mm")

    def render_list(self):
        if self.ha_menu is not None:                   # Home Assistant's settings, over the page
            return self.render_ha_menu()
        ttype = self.tab_type()
        if ttype == "photos":
            return self.render_grid()
        if ttype == "camera":
            return self.render_cameras() if self.cam_list else self.render_camera()
        if ttype == "friend":
            return self.render_coder() if self.bot_mode() == "work" else self.render_friend()
        if ttype == "sim":
            return self.render_sim()
        if ttype == "games":
            return self.render_games()
        if ttype == "finance":
            return self.render_fin_list() if self.fin_list else self.render_finance()
        if ttype == "remote":
            return self.render_remote()
        if ttype == "settings":
            return self.render_settings()
        if ttype == "weather":
            return self.render_weather()
        if ttype == "pihole" and self.pihole.configured:
            return self.render_pihole()
        if ttype == "system" and self.sys_dash():
            return self.render_sysdash()
        if ttype == "www" and self.www_on_page():
            return self.render_www()
        if ttype == "plex" and not self.plex.ready:
            return self.render_plex_signin()
        if ttype == "jellyfin" and not self.jellyfin.ready:
            return self.render_jf_signin()
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        self.header(img, d)
        top_y = self.list_top()
        if ttype == "browser":
            busy = self.net_busy
            right = busy["label"] if busy and busy["label"] and self.cwd in (busy["path"], busy["from"]) else ""
            rw = d.textlength(right, font=F["small"]) + 16 if right else 0
            if right:
                d.text((W - 20, self.LIST_TOP + 10), right, font=F["small"], fill=ACCENT, anchor="rm")
            where = self.net_place(self.cwd) if self.is_net(self.cwd) else short_path(self.cwd)
            d.text((20, self.LIST_TOP + 10), self.fit(d, where, F["small"], W - 40 - rw),
                   font=F["small"], fill=MUTED, anchor="lm")
        elif self.parent_of(self.tab) is not None and ttype not in ("plex", "jellyfin"):
            crumbs = LIBRARY[self.parent_of(self.tab)]["name"] + "  ›  " + LIBRARY[self.tab]["name"]
            if self.chan_stack.get(self.tab):
                crumbs += "  ›  " + self.chan_stack[self.tab][-1]["title"]
            elif ttype == "lights" and self.lights_scenes:
                crumbs += "  ›  Scenes"
            if ttype == "channels":
                d.text((W - 20, self.LIST_TOP + 10), self.channels_note(), font=F["small"],
                       fill=MUTED, anchor="rm")
            elif ttype == "www" and self.www_wait is not None:
                d.text((W - 20, self.LIST_TOP + 10), f"Loading {self.www_wait['host']}…", font=F["small"],
                       fill=ACCENT, anchor="rm")
            d.text((20, self.LIST_TOP + 10), crumbs, font=F["small"], fill=MUTED, anchor="lm")
        elif ttype == "radio" and self.radio_stack:
            crumbs = "Radio  ›  " + self.radio_stack[-1]["title"]
            d.text((20, self.LIST_TOP + 10), self.fit(d, crumbs, F["small"], W - 200), font=F["small"],
                   fill=MUTED, anchor="lm")
            d.text((W - 20, self.LIST_TOP + 10), "from radio-browser.info", font=F["small"],
                   fill=MUTED, anchor="rm")
        if ttype in ("plex", "jellyfin"):
            server, stack = (self.plex, self.plex_stack) if ttype == "plex" else (self.jellyfin, self.jf_stack)
            loading = self.status.get(self.tab) == "loading" and n
            right = "Loading…" if loading else server.server_name
            rw = d.textlength(right, font=F["small"])
            d.text((W - 20, self.LIST_TOP + 10), right, font=F["small"],
                   fill=ACCENT if loading else MUTED, anchor="rm")
            crumbs = "  ›  ".join(["TV"] + ([l["title"] for l in stack] or [LIBRARY[self.tab]["name"]]))
            d.text((20, self.LIST_TOP + 10), self.fit(d, crumbs, F["small"], W - 60 - rw),
                   font=F["small"], fill=MUTED, anchor="lm")

        if not n and ttype == "lights":
            self.empty_state(d, *self.lights_empty())
            self.footer(d, self.list_hints())
            self.fb.show(img)
            return
        if not n:
            status = self.status.get(self.tab)
            big, small = {
                "loading": ("Loading", "Getting the channels from Plex"
                            if ttype == "channels" else "Finding stations" if ttype == "radio" else "One moment"),
                "error": ("Can't connect", "Check the WiFi, then press L or R to retry"
                          if ttype not in ("plex", "jellyfin", "radio", "channels")
                          else "Check the WiFi, then press A to try again"),
                "empty": ("No stations found" if ttype == "radio" else "Nothing found",
                          "Try another name" if ttype != "channels" else
                          LIBRARY[self.tab]["empty"] if not self.chan_stack.get(self.tab) else
                          "Nothing on Plex Live TV right now"
                          if (self.chan_stack[self.tab][-1].get("src") or "").startswith("live:")
                          else "Try another name"),
                "noplex": ("Sign in to Plex first", "These channels come from Plex's free Live TV. "
                           "Press A to sign in"),
            }.get(status, ("Nothing here yet", LIBRARY[self.tab]["empty"]))
            self.empty_state(d, big, small)
            self.footer(d, self.list_hints())
            self.fb.show(img)
            return

        rows = self.visible_rows()
        top = self.tops.get(self.tab, 0)
        if sel < top:
            top = sel
        elif sel >= top + rows:
            top = sel - rows + 1
        top = max(min(top, n - rows), 0)
        self.tops[self.tab] = top

        x0, x1 = 12, W - 22
        self.tap_rows(0, W, top_y, self.ROW_H, top, min(top + rows, n), "sel", "sels", self.tab)
        # one column width for the artwork, so titles line up when posters and stills mix
        slot = max([self.plex_size(it)[0] for it in items[top:top + rows]
                    if not it.get("icon")] or [0])
        for r, i in enumerate(range(top, min(top + rows, n))):
            it = items[i]
            kind = it["kind"]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            selected = i == sel
            if selected:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            tx = x0 + 18
            if ttype == "browser":
                tx = self.badge(d, tx, mid, it)
            elif ttype == "lights":
                tx = self.lights_art(d, tx, mid, it)
            elif (ttype in ("plex", "jellyfin", "group", "games", "www") or (ttype == "radio" and not self.radio_stack)
                  or kind in ("chdir", "chsearch", "chplex", "chretry", "chwait")) and kind != "action":
                tx = self.plex_art(img, d, tx, mid, it, slot)
            right, colour, frac = self.row_right(it)
            if (self.proc and self.kind in LISTEN_KINDS and self.cur
                    and self.cur["key"] == it["key"]):
                right, colour = ("paused" if self.paused else "playing"), ACCENT

            if kind == "info":            # label on the left, reading on the right
                d.text((tx, mid), it["title"], font=F["small"],
                       fill=BODY if selected else MUTED, anchor="lm")
                vfont = F["row_b"] if selected else F["row"]
                d.text((x1 - 14, mid), self.fit(d, right, vfont, x1 - 14 - tx - 170),
                       font=vfont, fill=colour, anchor="rm")
                continue

            rw = d.textlength(right, font=F["small"]) if right else 0
            if right:
                d.text((x1 - 14, mid), right, font=F["small"], fill=colour, anchor="rm")
            font = F["row_b"] if selected or kind == "action" else F["row"]
            name = self.fit(d, it["title"], font, x1 - 14 - rw - 16 - tx)
            fill = TEXT if selected else BODY
            if kind == "plexwant":
                fill = BODY if selected else MUTED
            if kind == "action" and it["src"] == "poweroff":
                fill = WARN
            d.text((tx, mid - 3 if frac else mid), name, font=font, fill=fill, anchor="lm")

            if frac:                   # how far into the video you are
                by, bx1 = y + self.ROW_H - 12, x1 - 14
                d.rounded_rectangle((tx, by, bx1, by + 3), radius=1, fill=LINE)
                d.rounded_rectangle((tx, by, tx + (bx1 - tx) * min(frac, 1), by + 3),
                                    radius=1, fill=ACCENT)

        self.scrollbar(d, top, rows, n, top_y + 4, top_y + rows * self.ROW_H - 4)
        self.footer(d, self.list_hints(),
                    right=f"{sel + 1} of {n}" if ttype not in ("browser", "system", "group") else None)
        self.fb.show(img)

    def render_grid(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        self.header(img, d)
        if not n:
            self.empty_state(d, "Nothing here yet", LIBRARY[self.tab]["empty"])
            self.footer(d, self.list_hints())
            self.fb.show(img)
            return
        cols, rows = self.grid_cols(), self.grid_rows()
        top = self.tops.get(self.tab, 0)          # in rows
        srow = sel // cols
        if srow < top:
            top = srow
        elif srow >= top + rows:
            top = srow - rows + 1
        total_rows = (n + cols - 1) // cols
        top = max(min(top, total_rows - rows), 0)
        self.tops[self.tab] = top
        cw = (W - 32) // cols
        tw, th = self.THUMB
        for r in range(rows):
            for c in range(cols):
                i = (top + r) * cols + c
                if i >= n:
                    break
                x = 12 + c * cw + (cw - tw) // 2
                y = self.LIST_TOP + 2 + r * self.CELL_H + (self.CELL_H - th) // 2
                self.tappable((12 + c * cw, self.LIST_TOP + 2 + r * self.CELL_H, 12 + (c + 1) * cw,
                               self.LIST_TOP + 2 + (r + 1) * self.CELL_H), "sel", "sels", self.tab, i)
                if i == sel:
                    d.rounded_rectangle((x - 5, y - 5, x + tw + 5, y + th + 5), radius=10,
                                        outline=ACCENT, width=3)
                t = self.thumb(items[i]["src"])
                if t is not None:
                    img.paste(t, (x, y))
                else:
                    d.rounded_rectangle((x, y, x + tw, y + th), radius=6, fill=ROW)
        self.scrollbar(d, top, rows, total_rows, self.LIST_TOP + 6,
                       self.LIST_TOP + rows * self.CELL_H)
        self.footer(d, self.list_hints(),
                    right=self.fit(d, items[sel]["title"], F["small"], 150))
        self.fb.show(img)

    def render_help(self):
        img, d = self.canvas()
        self.title_row(d, "Controls")
        if self.help_from == "list" and self.tab_type() == "games":
            fast = not slow_pi()                       # (a Pi 4 or 5's: three more)
            folders = [("", "gb, gbc, gba, nes, snes,"), ("", "genesis, sms, gg, ps1" + ("," if fast else ""))] + \
                ([("", "n64, psp, nds and dc")] if fast else [])
            cols = [
                ("Games", [("A", "Play"), ("Y", "Find pictures"), ("START", "Search"), ("L R", "Switch tab"),
                           ("B", "Home"),
                           ("", "Your games go in the Games"), ("", "folder, a folder for each:")] + folders),
                ("In a game", [("HOME", "Its menu"), ("", "Save or load a state,"), ("", "start over, or quit"),
                               ("", "Quitting keeps your place"), ("", "Two players: one"),
                               ("", "controller each")]),
            ]
        elif self.help_from == "list" and self.tab_type() == "www":
            cols = [
                ("On a page", [("▲▼", "Link to link"), ("◀▶", "Page up / down"), ("A", "Open, type, send"),
                               ("B", "Back"), ("START", "Address or search"), ("Y", "Bookmark"),
                               ("SELECT", "Reader")]),
                ("In Chromium", CHROME_HELP) if self.chromium_here() else
                ("Web", [("", "Pages as words and pictures,"), ("", "no JavaScript: sites made"),
                         ("", "for that work best"), ("", "Reader: just the article"),
                         ("L R", "Switch tab")]),
            ]
        elif self.help_from == "chromenu":
            cols = [("In Chromium", CHROME_HELP), ("", CHROME_NOTES)]
        elif self.help_from == "list" and self.tab_type() == "lights":
            cols = [
                ("Lights", [("A", "On / off"), ("◀▶", "Dimmer"), ("▲▼", "Move"), ("L R", "Switch tab"),
                            ("B", "Back")]),
                ("", [("", "A plug: ◀▶ turns it"), ("", "off and on"), ("", "A scene: A sets it"),
                      ("", "All lights off: A")]),
            ]
        elif self.help_from == "list" and self.tab_type() == "pihole":
            cols = [
                ("Pi-hole", [("◀▶", "Top lists"), ("Y", "Forget (twice)"), ("A", "Sign in / try again"),
                             ("L R", "Switch tab"), ("B", "Back")]),
                ("The chart", [("", "The last 24 hours"), ("", "An hour a column"), ("", "Blue: allowed"),
                               ("", "Orange: blocked")]),
            ]
        elif self.help_from == "list" and self.tab_type() == "system":
            cols = [
                ("System", [("SELECT", "Dashboard / list"), ("◀▶", "More (dashboard)"), ("A", "Select (list)"),
                            ("", "or Update (a new version)"), ("L R", "Switch tab"), ("B", "Home")]),
                ("The dashboard", [("", "The CPU's last 5 minutes,"), ("", "a column every 10 seconds"),
                                   ("", "Below it, ◀▶: the network,"), ("", "temperature, this Pi, and"),
                                   ("", "what's in the background")]),
            ]
        elif self.help_from == "list" and LIBRARY[self.tab]["name"] == "Simulator":
            rows, sel = self.tab_items(), self.sels.get(self.tab, 0)
            on = rows[sel]["title"] if rows and 0 <= sel < len(rows) else ""
            cols = [
                ("In the lists", [("L R", "Switch tab"), ("▲▼", "Move (hold)"), ("A", "Open"),
                                  ("B", "Back / home"), ("HOME", "Terminal"), ("", ""),
                                  ("", "The others: B stops"), ("", "cacafire: A pauses")]),
                ("While htop is on", [("▲▼", "Move (hold)"), ("◀▶", "Scroll"), ("A", "Pause"), ("X", "Sort by CPU"),
                                      ("Y", "Sort by memory"), ("SELECT", "Tree"), ("B", "Stop")]) if on == "htop" else
                ("While cmatrix is on", [("◀▶", "Colour"), ("▲▼", "Speed"), ("A", "Pause"), ("X", "Bold"),
                                         ("Y", "Mixed speeds"), ("SELECT", "Rainbow"), ("B", "Stop")]),
            ]
        elif self.help_from == "now":
            cols = [
                ("Music & radio", [("A", "Pause / play"), ("◀▶", "Seek / station"),
                                   ("L R", "Prev / next"), ("▲▼", "Volume"), ("Y", "Shuffle")]),
                ("", [("B", "Back to the list"), ("HOME", "Terminal"),
                      ("", "Music keeps playing in"), ("", "the terminal")]),
            ]
        else:
            cols = [
                ("In the lists", [("L R", "Switch tab"), ("▲▼", "Move (hold)"),
                                  ("◀▶", "Page"), ("A", "Open / play"),
                                  ("START", "Now playing"), ("B", "Back / home"),
                                  ("HOME", "Terminal")]),
                ("While a video plays", [("A", "Pause / play"), ("◀▶", "10 seconds"),
                                         ("L R", "1 minute"), ("▲▼", "Volume"),
                                         ("X", "Time left"), ("Y", "Full screen"),
                                         ("SEL ST", "Prev / next"), ("B", "Back to list")]),
            ]
        self.help_columns(d, cols)
        self.footer(d, [("ANY", "Close")])
        self.fb.show(img)

    def help_columns(self, d, cols):
        """A help page's two columns: [(heading, [(button, what it does)])] (no button: a note)."""
        F = self.fonts
        W = self.fb.w
        most = max((len(rows) for _, rows in cols), default=1)
        room = self.fb.h - self.FOOTER - 16 - (self.LIST_TOP + 44)    # (down to the last row's middle)
        step = min(36, room / max(most - 1, 1))       # (a long column: its rows a little closer, all of them shown)
        for c, (head, rows) in enumerate(cols):
            x = 24 + c * (W // 2)
            if head:
                d.text((x, self.LIST_TOP + 12), head.upper(), font=F["key"], fill=MUTED, anchor="lm")
            for r, (k, label) in enumerate(rows):
                y = self.LIST_TOP + 44 + round(r * step)
                end = self.key(d, x, y, k) if k else x
                d.text((max(end, x + 64) + 10, y), label, font=F["small"],
                       fill=BODY if k else MUTED, anchor="lm")

    def render_wait(self, title, status, playing=False, camera=False):
        if not (self.active and self.fb):
            return
        if playing:
            return self.render_curtain(title, status)
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        title, status = on_pc(title), on_pc(status)    # (on a PC: "the PC", not "the Pi")
        d.text((W / 2, H / 2 - 18), self.fit(d, title, F["big"], W - 60),
               font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, H / 2 + 18), status, font=F["small"], fill=MUTED, anchor="mm")
        if camera:
            hints = [("PAD", "Move"), ("X Y", "Zoom"), ("START", "Center"), ("B", "Back")]
        else:
            hints = [("B", "Cancel")]
        self.footer(d, hints)
        self.fb.show(img)


    def render_update(self, dots_only=False):
        """While it updates (System > Update software), till the Pi restarts by itself: Updating Pie-tato, and dots
        under it, lit one after another (update_tick moves them on). dots_only: they're all that's changed."""
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.status_bar(d)                             # (the time and WiFi: no tabs, there's nowhere to go)
        d.text((W / 2, H / 2 - 22), self.fit(d, "Updating Pie-tato", F["big"], W - 60), font=F["big"], fill=TEXT,
               anchor="mm")
        box = self.update_dots(d, W / 2, H / 2 + 28)
        if dots_only and hasattr(self.fb, "show_part"):
            self.fb.show_part(img, box)
        else:
            self.fb.show(img)

    def update_dots(self, d, cx, cy):
        """The dots: the one lit, big, in the accent colour, the one before it fading, the rest dim. Their box."""
        n, gap = UPDATE_DOTS, 30
        lit = getattr(self, "update_frame", 0) % n
        for k in range(n):
            x = cx + (k - (n - 1) / 2) * gap
            age = (lit - k) % n                        # (0: lit now; 1: lit a step ago...)
            r = (9, 7, 6)[min(age, 2)]
            fill = ACCENT if age == 0 else mix(ACCENT, BG, 0.55) if age == 1 else LINE
            d.ellipse((x - r, cy - r, x + r, cy + r), fill=fill)
        half = (n - 1) / 2 * gap + 13
        return (int(cx - half), int(cy - 13), int(cx + half) + 1, int(cy + 13) + 1)

    def render_curtain(self, title, status, hints=None):
        """Before a video (or a game): black, with the words in the middle where the picture will cover
        them. (mplayer only draws the picture: anything round it would stay on the screen.)"""
        F = self.fonts
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        d.text((W / 2, H / 2 - 30), self.fit(d, title, F["big"], W - 60),
               font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, H / 2 + 4), status, font=F["small"], fill=MUTED, anchor="mm")
        full = self.setting("screen") != "Fit"
        hints = hints or [("A", "Pause"), ("▲▼", "Volume"), ("Y", "Whole picture" if full else "Full screen"),
                          ("B", "Back")]
        widths = [max(d.textlength(k, font=F["key"]) + 14, 24) + 7 + d.textlength(t, font=F["small"])
                  for k, t in hints]
        x, y = (W - sum(widths) - 18 * (len(hints) - 1)) / 2, H / 2 + 44
        for (k, t), w in zip(hints, widths):
            end = self.key(d, x, y, k) + 7
            d.text((end, y), t, font=F["small"], fill=BODY, anchor="lm")
            x += w + 18
        self.fb.show(img)
