"""The home screen: its grid of apps, and opening one."""
import time

from ..theme import ACCENT, BG, BODY, co_mix, LINE, MUTED, ROW, TEXT
from ..library import LIBRARY, LISTEN_KINDS, NOW_POP_SECS
from ..home import (CARD, CARD_LINE, draw_bright_icon, draw_glyph, draw_icon, draw_line_icon, draw_line_weather,
                    home_cols, HOME_ICONS, HOME_LABELS, home_layout, LINE_EDGE, LINE_INK_LIT, LINE_TILE, mix,
                    tile_tint, TILE_BOTTOM, TILE_TOP, wallpaper)
from ..weather import wx_icon_name, wx_words

LABEL = (214, 219, 226)      # Glass: an app's name under its tile
DATE = (222, 226, 232)       # ...the date, and the weather in words
LINE_LABEL = (206, 211, 218)  # Minimal: an app's name
LINE_SOFT = (196, 201, 209)  # ...the date, the weather in words, the buttons' names
LINE_DIM = (150, 156, 166)   # ...what's playing's heading
LINE_NOTE = (186, 192, 201)  # ...the app's line, bottom right
LINE_RULE = (34, 39, 48)     # ...the line under the time
CARD_PICKED = (36, 42, 52)   # Cards: the picked card
KEY_RING = (150, 158, 170)   # ...a button's ring, along the bottom


class HomeScreen:
    """The home screen: its grid of apps, and opening one."""

    # -- the home screen ------------------------------------------------------
    def home_apps(self):
        """(name, tab) for each icon. (Y goes to the terminal, so it has no icon.)"""
        return [(LIBRARY[i]["name"], i) for i in self.visible_tabs()]

    def playing_now(self):
        return bool(self.proc and self.kind in LISTEN_KINDS and self.cur)

    def pop_now(self):
        """What's playing pops up on the home screen for a few seconds (a song starts, the radio's song changes,
        you come back from the terminal); then the weather's back."""
        self.np_until = time.monotonic() + NOW_POP_SECS
        self.dirty = True

    def now_popped(self):
        return self.playing_now() and time.monotonic() < self.np_until

    def press_home(self, name, repeat):
        apps = self.home_apps()
        n = len(apps)
        cols = home_cols(n)
        sel = self.home_sel
        if name in ("left", "right"):
            sel = (sel + (1 if name == "right" else -1)) % n
        elif name in ("up", "down"):                   # the nearest icon in the row above or below
            slots = home_layout(n, cols)
            r, c = slots[sel]
            row = [k for k, (rr, _) in enumerate(slots) if rr == r + (1 if name == "down" else -1)]
            if row:
                sel = min(row, key=lambda k: abs(slots[k][1] - c))
        elif name == "a" and not repeat:
            return self.open_app(apps[sel][1])
        elif name == "start" and not repeat and self.playing_now():
            self.view, self.now_from = "now", "home"
        elif name == "y" and not repeat:               # (here only: B is back everywhere else)
            return "exit"
        self.home_sel = sel
        self.dirty = True
        return None

    def open_app(self, i):
        self.tab = i
        self.view = "list"
        self.load_tab(i)
        self.dirty = True
        return None

    def go_home(self):
        """B from an app: back to the icons, with that app picked."""
        ttype = self.tab_type()
        if ttype == "camera":
            self.camera.stop()
        elif ttype == "finance":
            self.fin_stop()
            self.fin_close()
        elif ttype == "remote":
            self.hass.stop()
            self.remote_more = None
        elif ttype == "lights":
            self.lights_close()
        self.confirm = (None, 0.0)
        self.picking = None
        self.friend_more = None
        self.coder_help = False
        self.sim_close()
        self.set_page = "root"
        if ttype == "radio" and self.radio_stack:
            self.radio_stack = []
            self.status[self.tab] = None
        for k in list(self.chan_stack):                # home: the Cartoons folders close
            self.chan_stack[k] = []
        apps = self.home_apps()
        self.home_sel = next((k for k, a in enumerate(apps) if a[1] == self.strip_tab()), self.home_sel)
        self.view = "home"
        self.dirty = True

    # -- its four looks (Settings > Home screen style) -------------------------
    #   Bright: bold, the time and the weather big, bright tiles with white glyphs, an accent ring round the app
    #           picked
    #   Glass: thin type, tiles of tinted glass with grey glyphs, the app picked lit and glowing
    #   Minimal: thinner still, a line under the time, big outline glyphs on nothing (a thin ring round the
    #            app picked), the buttons' names under them
    #   Cards: dark cards, each with a coloured glyph and its name, an accent line by the time, the weather
    #          between thin lines
    HOME_X = 36                                      # Glass's margins, left and right
    TILE = 74                                        # Glass's tile
    HOME_TOP = 14                                    # the time's top (no status bar here)
    LABEL_DY = 15                                    # Glass: an app's name, this far under its tile (its middle)
    HOME_GEOMETRY = {    # a tile; the first row's top; a row (a tile and its name); its name's middle under it
        "Bright": (72, 116, 104, 14),
        "Glass": (74, 116, 105, 15),
        "Minimal": (56, 112, 104, 18),
        "Cards": (92, 112, 104, -16),            # (a card 92 high, as wide as fits; its name inside it, at the foot)
    }
    CARD_X, CARD_GAP, CARD_R, GLYPH = 22, 14, 20, 52   # Cards: its margins, the gap between cards, their corners'
                                                      # roundness, a glyph's size
    MINIMAL_NAMES = {"Home Assistant": "Home"}

    def home_style(self):
        style = self.setting("home_style")
        return style if style in self.HOME_GEOMETRY else "Glass"

    def home_geometry(self):
        """(a tile, the first row's top, a row, its name's middle under it). On a taller screen than the GPi
        Case's (a monitor's 540 lines), the rows lower down and further apart: the room shared out."""
        tile, top, row, dy = self.HOME_GEOMETRY[self.home_style()]
        extra = max(0, (self.fb.h if self.fb else 480) - 480)
        return tile, top + extra // 3, row + extra // 4, dy

    def home_icon(self, name, lit=False):
        style = self.home_style()
        key = (style, name, lit)
        if key not in self.icons:
            size = self.home_geometry()[0]
            self.icons[key] = (draw_line_icon(name, size, lit) if style == "Minimal" else
                               draw_glyph(name, self.GLYPH) if style == "Cards" else
                               draw_bright_icon(name, size) if style == "Bright" else draw_icon(name, size, lit=lit))
        return self.icons[key]

    def home_wall(self):
        """The home screen's background, made again only when it changes."""
        key = (self.setting("wallpaper"), self.setting("picture"), self.fb.w, self.fb.h)
        if self.wall[0] != key:
            self.wall = (key, wallpaper(key[0], (self.fb.w, self.fb.h), key[1]))
        return self.wall[1]

    def home_canvas(self):
        """A fresh copy of the home screen's background."""
        from PIL import ImageDraw
        img = self.home_wall().copy()
        return img, ImageDraw.Draw(img)

    def home_pitch(self, cols):
        """How far apart the columns are."""
        W, style = self.fb.w, self.home_style()
        if style == "Bright":
            return (W - 20) / cols
        if style == "Minimal":
            return min(114, (W - 40) / cols)
        if style == "Cards":
            return (W - 2 * self.CARD_X + self.CARD_GAP) / cols
        return (W - 2 * self.HOME_X - self.TILE) / max(cols - 1, 1)   # (the first tile on the left margin, the last
                                                                        # on the right: the time and weather's)

    def card_box(self, k, slots, cols, first):
        """Where app k's tile is: (x0, y0, x1, y1)."""
        W, style = self.fb.w, self.home_style()
        tile, top, row, _ = self.home_geometry()
        r, c = slots[k]
        pitch = self.home_pitch(cols)
        if style == "Bright":
            cx = 10 + (c + 0.5) * pitch
        elif style == "Minimal":
            cx = W / 2 + (c - (cols - 1) / 2) * pitch
        else:
            cx = self.HOME_X + tile / 2 + c * pitch
        if style == "Cards":                          # (cards: as wide as fits)
            x0 = self.CARD_X + c * pitch
            return x0, top + (r - first) * row, x0 + pitch - self.CARD_GAP, top + (r - first) * row + tile
        x0, y0 = cx - tile / 2, top + (r - first) * row
        return x0, y0, x0 + tile, y0 + tile

    def home_rows_fit(self):
        tile, top, row, dy = self.home_geometry()
        return max(1, (self.fb.h - self.FOOTER - top - tile - 2 * max(dy, 0)) // row + 1)

    def home_glow(self, name, kind):
        """Glass: a soft light round a tile (the picked one: in its colour) or a shadow under it, made once."""
        from PIL import Image, ImageDraw, ImageFilter
        key = ("glow", name if kind == "glow" else None, kind, self.TILE)
        if key not in self.icons:
            pad = 14
            im = Image.new("RGBA", (self.TILE + 2 * pad, self.TILE + 2 * pad), (0, 0, 0, 0))
            colour = tile_tint(name) + (150,) if kind == "glow" else (0, 0, 0, 120)
            ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + self.TILE, pad + self.TILE),
                                                 radius=int(self.TILE * 0.23), fill=colour)
            self.icons[key] = (im.filter(ImageFilter.GaussianBlur(7 if kind == "glow" else 5)), pad)
        return self.icons[key]

    def home_ring(self, size):
        """Minimal: the ring round the app picked, drawn four times bigger so its corners come out smooth."""
        from PIL import Image, ImageDraw
        key = ("ring", size)
        if key not in self.icons:
            im = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((2, 2, size * 4 - 3, size * 4 - 3), radius=56,
                                                 outline=LINE_EDGE + (255,), width=7)
            self.icons[key] = im.resize((size, size), Image.LANCZOS)
        return self.icons[key]

    def home_card(self, d, img, name, box, picked, pitch):
        """One app: its tile, and its name under it, the picked one marked as its look has it."""
        F, style = self.fonts, self.home_style()
        x0, y0, x1, y1 = box
        dy = self.home_geometry()[3]
        room = pitch - 8
        if style == "Cards":                         # its glyph on the card, its name at the card's foot
            if picked:
                d.rounded_rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), radius=self.CARD_R + 1, fill=CARD_PICKED,
                                    outline=ACCENT, width=2)
            glyph = self.home_icon(name)
            img.paste(glyph, (int((x0 + x1 - self.GLYPH) / 2), int(y0 + 11)), glyph)
            label = self.fit(d, HOME_LABELS.get(name, name), F["home4_label"], x1 - x0 - 6)
            d.text(((x0 + x1) / 2, y1 + dy), label, font=F["home4_label"], fill=TEXT if picked else LABEL, anchor="mm")
            return
        if picked:                                     # (its name, as drawn on the grid unpicked: gone)
            cx, ly = (x0 + x1) / 2, y1 + dy
            strip = tuple(int(v) for v in (cx - pitch / 2, ly - 11, cx + pitch / 2, ly + 12))
            img.paste(self.wall[1].crop(strip), strip[:2])
        if style == "Bright":
            if picked:
                d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), radius=24, outline=ACCENT, width=3)
            tile = self.home_icon(name)
            img.paste(tile, (int(x0), int(y0)), tile)
            font = F["small_b"] if picked and d.textlength(name, font=F["small_b"]) <= room else F["label"]
            label = self.fit(d, name, font, room)
            d.text(((x0 + x1) / 2 + 1, y1 + dy + 1), label, font=font, fill=(0, 0, 0), anchor="mm")
            d.text(((x0 + x1) / 2, y1 + dy), label, font=font, fill=TEXT if picked else BODY, anchor="mm")
            return
        if picked and style == "Glass":
            glow, pad = self.home_glow(name, "glow")
            img.paste(glow, (int(x0) - pad, int(y0) - pad), glow)
        if picked and style == "Minimal":              # a thin ring round it, its glyph white
            spot = tuple(int(v) for v in (x0, y0, x1, y1))
            img.paste(self.wall[1].crop(spot), spot[:2])
            ring = self.home_ring(int(x1 - x0) + 14)
            img.paste(ring, (int(x0) - 7, int(y0) - 7), ring)
        tile = self.home_icon(name, picked)
        img.paste(tile, (int(x0), int(y0)), tile)
        if style == "Minimal":
            font, fill = F["home3_label"], (TEXT if picked else LINE_LABEL)
            name = self.MINIMAL_NAMES.get(name, name)
        else:
            font, fill = F["home_label"], (TEXT if picked else LABEL)
        label = name if d.textlength(name, font=font) <= room else HOME_LABELS.get(name, name)
        d.text(((x0 + x1) / 2, y1 + dy), self.fit(d, label, font, room), font=font, fill=fill, anchor="mm")

    def home_grid(self, apps, cols, first, rows_fit):
        """The background with every tile on it, unpicked: kept until something about it changes."""
        from PIL import ImageDraw
        style = self.home_style()
        key = (style, self.wall[0], tuple(a for a, _ in apps), cols, first, rows_fit, self.fb.w, self.fb.h)
        if self.home_base[0] != key:
            base = self.wall[1].copy()
            bd = ImageDraw.Draw(base)
            slots = home_layout(len(apps), cols)
            if style == "Glass":
                shade, pad = self.home_glow(None, "shadow")
            shown = [(name, self.card_box(k, slots, cols, first)) for k, (name, _) in enumerate(apps)
                     if first <= slots[k][0] < first + rows_fit]
            if style == "Cards":                     # the cards, a little see-through
                from PIL import Image
                layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                for _, box in shown:
                    ld.rounded_rectangle(box, radius=self.CARD_R, fill=CARD + (232,), outline=CARD_LINE + (255,))
                base = base.convert("RGBA")
                base.alpha_composite(layer)
                base = base.convert("RGB")
                bd = ImageDraw.Draw(base)
            for name, box in shown:
                if style == "Glass":
                    base.paste(shade, (int(box[0]) - pad, int(box[1]) - pad + 3), shade)
                self.home_card(bd, base, name, box, False, self.home_pitch(cols))
            if style == "Minimal":                     # a line under the time and the weather
                bd.line((20, 96, self.fb.w - 20, 96), fill=LINE_RULE)
            self.home_base = (key, base)
        img = self.home_base[1].copy()
        return img, ImageDraw.Draw(img)

    def home_widget(self, img, d):
        """The top right of the home screen when nothing is playing: the temperature and the sky, and under them
        the weather in words and today's high and low."""
        F, W, style = self.fonts, self.fb.w, self.home_style()
        wx = self.weather.data
        if not wx or not self.setting("location"):
            return
        today = (wx.get("days") or [{}])[0]
        hi, lo = self.deg(today.get("hi")), self.deg(today.get("lo"))
        temp, sky = self.deg(wx.get("temp")), wx_icon_name(wx.get("code"), wx.get("is_day", True))
        words = wx_words(wx.get("code"))[0]
        if style == "Cards":                         # between thin lines: the sky, now, today's high and low
            hilo = f"{hi} / {lo}"
            words = self.fit(d, words, F["small"], 150)
            x_hilo = W - 22 - d.textlength(hilo, font=F["home4_date"])
            line2 = x_hilo - 16
            x_tc = line2 - 16 - max(d.textlength(temp, font=F["home4_temp"]), d.textlength(words, font=F["small"]))
            x_icon = x_tc - 10 - 52
            line1 = x_icon - 16
            d.line((line1, 30, line1, 92), fill=CARD_LINE, width=1)
            icon = self.wx_icon(sky, 52)
            img.paste(icon, (int(x_icon), 34), icon)
            d.text((x_tc, 28), temp, font=F["home4_temp"], fill=TEXT, anchor="la")
            d.text((x_tc, 80), words, font=F["small"], fill=BODY, anchor="lm")
            d.line((line2, 30, line2, 92), fill=CARD_LINE, width=1)
            d.text((x_hilo, 80), hilo, font=F["home4_date"], fill=co_mix(ACCENT, TEXT, 0.35), anchor="lm")
        elif style == "Bright":
            icon = self.wx_icon(sky, 64)
            img.paste(icon, (W - 24 - 64, 16), icon)
            d.text((W - 24 - 64 - 10, 14), temp, font=F["clock"], fill=TEXT, anchor="ra")
            line = f"{words}  ·  {hi} / {lo}"
            d.text((W - 24, 76), self.fit(d, line, F["row"], 300), font=F["row"], fill=BODY, anchor="ra")
        elif style == "Minimal":
            key = ("line_wx", sky)
            if key not in self.icons:
                self.icons[key] = draw_line_weather(sky, 40)
            icon = self.icons[key]
            img.paste(icon, (W - 26 - 40, 17), icon)
            d.text((W - 26 - 40 - 10, 54), temp, font=F["home3_clock"], fill=TEXT, anchor="rs")
            tail = f"  ·  {hi}/{lo}"
            words = self.fit(d, words, F["home3_small"], 280 - d.textlength(tail, font=F["home3_small"]))
            d.text((W - 26, 78), words + tail, font=F["home3_small"], fill=LINE_SOFT, anchor="rs")
        else:
            x1 = W - self.HOME_X
            icon = self.wx_icon(sky, 52)
            img.paste(icon, (int(x1 - 52), 21), icon)
            d.text((x1 - 52 - 14, 66), temp, font=F["wx_temp"], fill=TEXT, anchor="rs")
            tail = f"  ·  {hi} / {lo}"
            words = self.fit(d, words, F["home_date"], 300 - d.textlength(tail, font=F["home_date"]))
            d.text((x1, 95), words + tail, font=F["home_date"], fill=DATE, anchor="rs")

    def hour_min(self, hhmm):
        try:
            t = time.strptime(hhmm, "%H:%M")
        except ValueError:
            return hhmm
        return time.strftime("%H:%M" if self.setting("clock") == "24-hour" else "%-I:%M %p", t)

    def home_clock(self, d):
        """The time, big, and the date under it."""
        F, style = self.fonts, self.home_style()
        t = time.localtime()
        hm = self.clock_text(t, ampm=False)
        twelve = self.setting("clock") != "24-hour"
        date = time.strftime("%A, %B ", t) + str(t.tm_mday)
        if style == "Cards":                         # an accent line beside it, a little calendar by the date
            top = self.HOME_TOP
            d.rounded_rectangle((16, top + 8, 20, top + 84), radius=2, fill=ACCENT)
            d.text((32, top), hm, font=F["home4_clock"], fill=TEXT, anchor="la")
            if twelve:
                l, tp, r, b = d.textbbox((32, top), hm, font=F["home4_clock"], anchor="la")
                d.text((r + 10, (tp + b) / 2), time.strftime("%p", t), font=F["home4_date"], fill=TEXT, anchor="lm")
            cy = top + 72
            d.rounded_rectangle((33, cy - 6, 47, cy + 8), radius=3, outline=BODY, width=2)
            d.line((33, cy - 1, 47, cy - 1), fill=BODY, width=2)
            for x in (37, 43):
                d.line((x, cy - 9, x, cy - 4), fill=BODY, width=2)
            d.text((57, cy + 1), date, font=F["home4_date"], fill=BODY, anchor="lm")
        elif style == "Bright":
            d.text((24, 14), hm, font=F["clock"], fill=TEXT, anchor="la")
            if twelve:
                d.text((24 + d.textlength(hm, font=F["clock"]) + 8, 26), time.strftime("%p", t), font=F["head"],
                       fill=BODY, anchor="la")
            d.text((26, 76), date, font=F["row"], fill=BODY, anchor="la")
        elif style == "Minimal":
            d.text((26, 54), hm + (time.strftime(" %p", t) if twelve else ""), font=F["home3_clock"], fill=TEXT,
                   anchor="ls")
            d.text((28, 78), date, font=F["home3_small"], fill=LINE_SOFT, anchor="ls")
        else:
            x = self.HOME_X - 2                        # (the figures' own margin)
            d.text((x, 66), hm, font=F["home_clock"], fill=TEXT, anchor="ls")
            if twelve:
                d.text((x + d.textlength(hm, font=F["home_clock"]) + 9, 47), time.strftime("%p", t),
                       font=F["home_ampm"], fill=TEXT, anchor="ls")
            d.text((self.HOME_X, 95), date, font=F["home_date"], fill=DATE, anchor="ls")

    def home_playing(self, img, d):
        """What's playing, top right, for a few seconds."""
        from PIL import Image, ImageDraw
        F, W, style = self.fonts, self.fb.w, self.home_style()
        it = self.cur
        radio = self.kind == "radio"
        title = it["title"] if radio else (self.meta.get("title") or it["title"])
        sub = (self.meta.get("song") or it.get("sub") or "") if radio else (it.get("sub") or "")
        head = "PAUSED" if self.paused else "ON THE RADIO" if radio else "NOW PLAYING"
        if style in ("Bright", "Cards"):           # a card
            x0, x1, y0 = W - 296, W - 20, 18 if style == "Bright" else self.HOME_TOP + 8
            if style == "Bright":
                d.rounded_rectangle((x0, y0, x1, y0 + 78), radius=14, fill=ROW)
            else:
                d.rounded_rectangle((x0, y0, x1, y0 + 78), radius=12, fill=CARD, outline=CARD_LINE)
            d.text((x0 + 18, y0 + 17), head, font=F["key"], fill=ACCENT, anchor="lm")
            d.text((x0 + 18, y0 + 42), self.fit(d, title, F["row_b"], x1 - x0 - 36), font=F["row_b"], fill=TEXT,
                   anchor="lm")
            if sub:
                d.text((x0 + 18, y0 + 63), self.fit(d, sub, F["small"], x1 - x0 - 36), font=F["small"], fill=BODY,
                       anchor="lm")
            return
        if style == "Minimal":                         # a quiet panel, like its tiles
            x0, y0, x1, y1 = W - 26 - 262, 12, W - 26, 86
            d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=LINE_TILE)
            room = x1 - x0 - 32
            d.text((x0 + 16, y0 + 16), head, font=F["home_pop_head"], fill=LINE_DIM, anchor="lm")
            d.text((x0 + 16, y0 + 38), self.fit(d, title, F["home3_title"], room), font=F["home3_title"], fill=TEXT,
                   anchor="lm")
            if sub:
                d.text((x0 + 16, y0 + 58), self.fit(d, sub, F["home3_small"], room), font=F["home3_small"],
                       fill=LINE_SOFT, anchor="lm")
            return
        x0, y0, x1, y1 = W - self.HOME_X - 280, 20, W - self.HOME_X, 98   # a panel like the tiles, in Music's or
        tint = tile_tint("Radio" if radio else "Music")                    # Radio's colour
        key = ("panel", tint, x1 - x0, y1 - y0)
        if key not in self.icons:
            w, h = int(x1 - x0), int(y1 - y0)
            grad = Image.linear_gradient("L").resize((w, h))
            panel = Image.composite(Image.new("RGBA", (w, h), mix(TILE_BOTTOM, tint, 0.2) + (255,)),
                                    Image.new("RGBA", (w, h), mix(TILE_TOP, tint, 0.32) + (255,)), grad)
            shape = Image.new("L", (w, h), 0)
            ImageDraw.Draw(shape).rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=255)
            ImageDraw.Draw(panel).rounded_rectangle((0, 0, w - 1, h - 1), radius=16,
                                                    outline=mix((66, 72, 84), tint, 0.5) + (255,), width=1)
            panel.putalpha(shape)
            self.icons[key] = panel
        panel = self.icons[key]
        img.paste(panel, (int(x0), int(y0)), panel)
        room = x1 - x0 - 36
        d.text((x0 + 18, y0 + 19), head, font=F["home_pop_head"], fill=mix(tint, (255, 255, 255), 0.45), anchor="lm")
        d.text((x0 + 18, y0 + 42), self.fit(d, title, F["home_pop_title"], room), font=F["home_pop_title"],
               fill=TEXT, anchor="lm")
        if sub:
            d.text((x0 + 18, y0 + 62), self.fit(d, sub, F["home_pop_sub"], room), font=F["home_pop_sub"],
                   fill=DATE, anchor="lm")

    def home_outline_key(self, w):
        """Minimal: a button's ring (a word's, a pill w wide), like Cards' but drawn four times bigger for smooth
        edges."""
        from PIL import Image, ImageDraw
        key = ("keyring", int(w))
        if key not in self.icons:
            w4, h4 = int(w) * 4, 24 * 4
            im = Image.new("RGBA", (w4, h4), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((3, 3, w4 - 4, h4 - 4), radius=h4 // 2 - 3,
                                                 outline=KEY_RING + (255,), width=8)
            self.icons[key] = im.resize((int(w), 24), Image.LANCZOS)
        return self.icons[key]

    def home_footer3(self, img, d, hints, note):
        """Minimal's buttons along the bottom: rings round their letters (as Cards has them), each with its name
        under it, and the app's line on the right, slanted."""
        from PIL import Image, ImageDraw
        F, W, H = self.fonts, self.fb.w, self.fb.h
        x, cy = 28, H - 40
        for k, label in hints:
            lw = d.textlength(label, font=F["home3_keylabel"])
            kw = 24 if len(k) == 1 else d.textlength(k, font=F["home3_key"]) + 16
            mid = x + max(lw, kw) / 2
            ring = self.home_outline_key(kw)
            img.paste(ring, (int(mid - ring.width / 2), cy - 12), ring)
            d.text((mid, cy), k, font=F["home3_key"], fill=TEXT, anchor="mm")
            d.text((mid, cy + 26), label, font=F["home3_keylabel"], fill=LINE_SOFT, anchor="mm")
            x += max(lw, kw) + 22
        if note:
            font = F["home3_note"]
            key = ("slant", note)
            if key not in self.icons:                  # (a typeface leaning right, made from the upright one)
                w, h = int(d.textlength(note, font=font)) + 4, font.size + 10
                m = Image.new("L", (w, h), 0)
                ImageDraw.Draw(m).text((2, h / 2), note, font=font, fill=255, anchor="lm")
                lean = 0.2
                self.icons[key] = m.transform((w + int(h * lean), h), Image.AFFINE, (1, lean, -h * lean, 0, 1, 0),
                                              Image.BICUBIC)
            m = self.icons[key]
            if x + 8 + m.width < W - 26:
                img.paste(LINE_NOTE, (int(W - 26 - m.width), int(cy + 10 - m.height / 2)), m)
        self.msg_pill(d)

    def home_footer4(self, d, hints, note):
        """Cards's buttons along the bottom: rings round the letters, thin lines between them, and the app's line on
        the right with three little slants before it."""
        F, W, H = self.fonts, self.fb.w, self.fb.h
        y, x = H - self.FOOTER // 2, 20
        for n, (k, label) in enumerate(hints):
            if n:
                d.line((x - 9, y - 9, x - 9, y + 9), fill=LINE, width=1)
            w = self.key_w(d, k)
            if len(k) == 1:
                d.ellipse((x, y - 11, x + w, y + 11), outline=KEY_RING, width=2)
            else:
                d.rounded_rectangle((x, y - 11, x + w, y + 11), radius=11, outline=KEY_RING, width=2)
            d.text((x + w / 2, y), k, font=F["key"], fill=TEXT, anchor="mm")
            x += w + 7
            d.text((x, y), label, font=F["small"], fill=BODY, anchor="lm")
            x += d.textlength(label, font=F["small"]) + 18
        if note and x + d.textlength(note, font=F["small"]) < W - 20:
            d.text((W - 20, y), note, font=F["small"], fill=MUTED, anchor="rm")
            if x + 34 + d.textlength(note, font=F["small"]) < W - 20:   # (a long line goes without them)
                mx = W - 20 - d.textlength(note, font=F["small"]) - 14
                for j in range(3):
                    sx = mx - (2 - j) * 9
                    d.polygon([(sx - 7, y + 4), (sx - 3, y - 4), (sx + 2, y - 4), (sx - 2, y + 4)], fill=ACCENT)
        self.msg_pill(d)

    def render_home(self):
        F = self.fonts
        W, H = self.fb.w, self.fb.h
        style = self.home_style()
        apps = self.home_apps()
        n = len(apps)
        cols = home_cols(n)
        sel = self.home_sel % n
        rows_fit = self.home_rows_fit()
        first = max(0, min(sel // cols - rows_fit + 1, (n - 1) // cols - rows_fit + 1))
        self.home_wall()
        img, d = self.home_grid(apps, cols, first, rows_fit)

        self.home_clock(d)
        if self.now_popped():                          # what's playing, top right, for a few seconds
            self.home_playing(img, d)
        elif self.setting("widget") == "Weather":
            self.home_widget(img, d)

        # the picked app, marked; a dot on what's playing
        slots = home_layout(n, cols)
        self.home_card(d, img, apps[sel][0], self.card_box(sel, slots, cols, first), True, self.home_pitch(cols))
        playing = {"audio": "Music", "radio": "Radio"}.get(self.kind) if self.playing_now() else None
        for k, (name, _) in enumerate(apps):
            if name == playing and first <= slots[k][0] < first + rows_fit:
                x0, y0, x1, y1 = self.card_box(k, slots, cols, first)
                if style == "Bright":
                    d.ellipse((x1 - 13, y0 - 3, x1 + 5, y0 + 15), fill=BG)
                    d.ellipse((x1 - 10, y0, x1 + 2, y0 + 12), fill=ACCENT)
                elif style == "Minimal":
                    d.ellipse((x1 - 1, y0 - 1, x1 + 5, y0 + 5), fill=LINE_INK_LIT)
                elif style == "Cards":
                    d.ellipse((x1 - 22, y0 + 10, x1 - 10, y0 + 22), fill=ACCENT)
                else:
                    d.ellipse((x1 - 10, y0 - 4, x1 + 4, y0 + 10), fill=ACCENT, outline=BG, width=2)
        if (n - 1) // cols >= first + rows_fit:       # more below
            d.text((W / 2, H - self.FOOTER - 2), "▼", font=F["small"], fill=MUTED, anchor="mm")

        hints = [("A", "Open")]
        if self.now_popped():                          # (START opens it any time; said while it's up)
            hints.append(("START", "Now playing"))
        hints.append(("Y", "Terminal"))
        name_sel, tab_sel = apps[sel]
        about = HOME_ICONS.get(name_sel, (None, ""))[1]
        if not about and tab_sel is not None:
            about = LIBRARY[tab_sel].get("about", "")
        if style == "Minimal":
            self.home_footer3(img, d, hints, about)
        elif style == "Cards":
            self.home_footer4(d, hints, about)
        else:
            self.footer(d, hints, right=about, plain=style == "Glass")
        self.fb.show(img)
