"""The TV Remote (through Home Assistant), and its number pad."""
import time

from ..library import LIBRARY
from ..theme import ACCENT, BG, BODY, DONE, LINE, MUTED, ROW, TEXT, WARN
from ..homeassistant import HA_HELD, TV_PAD


class RemoteScreen:
    """The TV Remote (through Home Assistant), and its number pad."""

    # TV Remote
    def remote_changed(self):
        if self.active and self.view == "list" and self.tab_type() == "remote":
            self.dirty = True

    def remote_options(self):
        st = self.hass.tvstate
        opts = [(f"Switch to {name}", ("tv", entity)) for entity, name in self.hass.tv_names()
                if entity != self.hass.tv]                 # (your other TVs first)
        opts += [("Number pad", ("pad",)),
                 ("Turn on", ("power", "on")), ("Turn off", ("power", "off")),    # (both: it does what you pick)
                 ("Unmute", ("mute", False)) if st.get("muted") else ("Mute", ("mute", True)),
                 ("Play / pause", ("play",))]
        for src in st.get("sources") or []:
            opts.append((src, ("source", src)))
        return opts

    REMOTE_KEYS = {"up": ("key", "up"), "down": ("key", "down"), "left": ("key", "left"),
                   "right": ("key", "right"), "a": ("key", "ok"), "y": ("key", "back"),
                   "x": ("key", "home"), "l": ("volume", -1), "r": ("volume", 1),
                   "start": ("play",)}

    def press_remote(self, name, repeat):
        """The case's buttons as the TV's remote. 'pass' lets B go back to the Home menu."""
        now = time.monotonic()
        if self.remote_pad is not None:                # the number pad
            return self.press_pad(name, repeat)
        if self.remote_more is not None:               # the More menu
            opts = self.remote_options()
            m = self.remote_more
            if name in ("up", "down"):
                m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % len(opts)
            elif name == "a" and not repeat:
                self.remote_more = None
                label, job = opts[m["sel"] % len(opts)]
                if job == ("pad",):
                    self.open_pad()
                elif job[0] == "tv":
                    if self.hass.choose(job[1]):
                        self.toast(label[len("Switch to "):], 2)
                else:
                    self.hass.send(*job)
            elif name in ("b", "select") and not repeat:
                self.remote_more = None
            self.dirty = True
            return None
        if name == "b":
            return "pass"
        if not self.hass.configured:
            if name == "a" and not repeat:
                self.ha_open()                         # (its address and token)
            return None
        if name == "select" and not repeat:
            self.remote_more = {"sel": 0}
        elif name in self.REMOTE_KEYS:
            if repeat and (now - self.remote_hit[1] < HA_HELD or self.hass.busy()):
                return None                            # held: gently, never ahead of the TV
            self.hass.send(*self.REMOTE_KEYS[name])
            self.remote_hit = (name, now)
        self.dirty = True
        return None

    # the number pad, for channels
    def open_pad(self):
        self.remote_pad = {"text": "", "r": 0, "c": 1}
        self.keyreader.on_key = self.pad_key            # the BBQ20's numbers work too
        self.keyreader.start()
        self.dirty = True

    def close_pad(self):
        self.remote_pad = None
        self.keyreader.stop()
        self.dirty = True

    def pad_key(self, kind, ch=""):
        """A real keyboard while the number pad is up."""
        pad = self.remote_pad
        if pad is None:
            return
        if kind == "char" and (ch.isdigit() or ch in "-."):
            pad["text"] = (pad["text"] + ("-" if ch in "-." else ch))[:7]
        elif kind == "back":
            pad["text"] = pad["text"][:-1]
        elif kind == "done":
            self.pad_go()
        elif kind == "cancel":
            self.close_pad()
        self.dirty = True

    def pad_go(self):
        pad = self.remote_pad
        if pad and pad["text"].strip("-"):
            self.hass.send("channel", pad["text"].strip("-"))
            self.remote_hit = ("go", time.monotonic())
            self.close_pad()
        else:
            self.toast("Type a channel number first", 2)

    def press_pad(self, name, repeat):
        pad = self.remote_pad
        rows = TV_PAD
        if name in ("up", "down"):
            pad["r"] = (pad["r"] + (1 if name == "down" else -1)) % len(rows)
            pad["c"] = min(pad["c"], len(rows[pad["r"]]) - 1)
        elif name in ("left", "right"):
            n = len(rows[pad["r"]])
            pad["c"] = (pad["c"] + (1 if name == "right" else -1)) % n
        elif name == "a" and not repeat:
            label, what = rows[pad["r"]][pad["c"]]
            if what.isdigit() or what == "dash":
                pad["text"] = (pad["text"] + ("-" if what == "dash" else what))[:7]
            elif what == "del":
                pad["text"] = pad["text"][:-1]
            elif what == "go":
                self.pad_go()
                return None
            else:                                      # channel up/down, last, guide: straight away
                self.hass.send("key", what)
            self.remote_hit = ("pad", time.monotonic())
        elif name in ("l", "r") and not repeat:        # the shoulders change channel here
            self.hass.send("key", "chdown" if name == "l" else "chup")
        elif name == "x" and not repeat:
            pad["text"] = pad["text"][:-1]
        elif name == "start" and not repeat:
            self.pad_go()
            return None
        elif name in ("b", "select") and not repeat:
            self.close_pad()
        self.dirty = True
        return None

    def render_remote(self):
        F = self.fonts
        ha = self.hass
        img, d = self.canvas()
        W = self.fb.w
        self.header(img, d)
        p = self.parent_of(self.tab)
        crumbs = (LIBRARY[p]["name"] + "  ›  " if p is not None else "") + LIBRARY[self.tab]["name"]
        d.text((20, self.LIST_TOP + 10), crumbs, font=F["small"], fill=MUTED, anchor="lm")
        if not ha.configured:
            self.empty_state(d, "Connect Home Assistant", "Press A to put in its address and token")
            self.footer(d, [("A", "Set up"), ("B", "Back")])
            self.fb.show(img)
            return
        st = ha.tvstate
        top = self.list_top() + 4

        # the TV, how it is
        d.rounded_rectangle((12, top, W - 12, top + 72), radius=12, fill=ROW)
        name = st.get("name") or ("Looking for your TV…" if not ha.error else "Home Assistant")
        d.text((30, top + 24), self.fit(d, name, F["row_b"], W - 260), font=F["row_b"], fill=TEXT, anchor="lm")
        if ha.error:
            line, colour = self.fit(d, ha.error, F["small"], W - 60), WARN
        elif st:
            state = st.get("state", "")
            words = {"on": "On", "off": "Off", "playing": "Playing", "paused": "Paused",
                     "idle": "On", "standby": "Off", "unavailable": "Not answering"}
            bits = [words.get(state, state.capitalize())]
            if state not in ("off", "standby", "unavailable"):
                bits += [b for b in (st.get("app"), st.get("source"), st.get("title")) if b][:2]
            line, colour = "  ·  ".join(bits), (DONE if state not in ("off", "standby", "unavailable")
                                                 else MUTED)
        else:
            line, colour = ha.where, MUTED
        d.text((30, top + 52), self.fit(d, line, F["small"], W - 250 if not ha.error else W - 60),
               font=F["small"], fill=colour, anchor="lm")
        vol = st.get("volume")
        if vol is not None and not ha.error:
            x1, x0 = W - 32, W - 32 - 150
            label = "Muted" if st.get("muted") else f"Volume {round(vol * 100)}"
            d.text((x1, top + 26), label, font=F["small"], fill=WARN if st.get("muted") else BODY, anchor="rm")
            d.rounded_rectangle((x0, top + 46, x1, top + 54), radius=4, fill=LINE)
            if vol > 0:
                d.rounded_rectangle((x0, top + 46, x0 + max(8, (x1 - x0) * vol), top + 54), radius=4,
                                    fill=MUTED if st.get("muted") else ACCENT)

        # the case's buttons, and what each one does to the TV
        hit = self.remote_hit[0] if time.monotonic() - self.remote_hit[1] < 0.25 else ""
        y0 = top + 96
        for k, (lab, txt) in enumerate((("L", "Vol −"), ("R", "Vol +"))):
            x = 24 if k == 0 else W - 24 - 150
            on = hit == lab.lower()
            d.rounded_rectangle((x, y0, x + 150, y0 + 32), radius=16, fill=ACCENT if on else ROW)
            d.text((x + 22, y0 + 16), lab, font=F["key"], fill=BG if on else MUTED, anchor="mm")
            d.text((x + 86, y0 + 16), txt, font=F["small"], fill=BG if on else TEXT, anchor="mm")

        cx, cy, arm, half = 150, y0 + 128, 54, 19          # d-pad
        d.rounded_rectangle((cx - arm, cy - half, cx + arm, cy + half), radius=8, fill=ROW)
        d.rounded_rectangle((cx - half, cy - arm, cx + half, cy + arm), radius=8, fill=ROW)
        for k, (dx, dy, glyph) in {"up": (0, -1, "▲"), "down": (0, 1, "▼"),
                                   "left": (-1, 0, "◀"), "right": (1, 0, "▶")}.items():
            gx, gy = cx + dx * (arm - 18), cy + dy * (arm - 18)
            if hit == k:
                d.rounded_rectangle((gx - 17, gy - 17, gx + 17, gy + 17), radius=8, fill=ACCENT)
            d.text((gx, gy), glyph, font=F["small"], fill=BG if hit == k else BODY, anchor="mm")
        d.text((cx, cy + arm + 18), "TV arrows", font=F["small"], fill=MUTED, anchor="mm")

        fx, fy, gap, r = W - 150, y0 + 128, 44, 19          # A B X Y
        faces = {"x": (0, -1, "Home", "ma"), "a": (1, 0, "OK", "lm"),
                 "b": (0, 1, "Leave", "mt"), "y": (-1, 0, "Back", "rm")}
        for k, (dx, dy, txt, anchor) in faces.items():
            bx, by = fx + dx * gap, fy + dy * gap
            on = hit == k
            d.ellipse((bx - r, by - r, bx + r, by + r), fill=ACCENT if on else ROW)
            d.text((bx, by), k.upper(), font=F["key"], fill=BG if on else BODY, anchor="mm")
            tx, ty = bx + dx * (r + 8), by + dy * (r + 4)
            if k == "x":
                ty = by - r - 22
            elif k == "b":
                ty = by + r + 4
            d.text((tx, ty), txt, font=F["small"], fill=MUTED if k == "b" else TEXT, anchor=anchor)

        more = "TVs · More · 123" if len(ha.tvs) > 1 else "More · 123"
        for k, (key, txt) in enumerate((("START", "Play / pause"), ("SELECT", more))):
            mx, my = W / 2, y0 + 96 + k * 62
            on = hit == key.lower()
            w = d.textlength(key, font=F["key"]) + 22
            d.rounded_rectangle((mx - w / 2, my - 12, mx + w / 2, my + 12), radius=12,
                                fill=ACCENT if on else LINE)
            d.text((mx, my), key, font=F["key"], fill=BG if on else TEXT, anchor="mm")
            d.text((mx, my + 26), txt, font=F["small"], fill=TEXT, anchor="mm")

        if self.remote_pad is not None:                    # the number pad, over the remote
            pad = self.remote_pad
            pw, kh, gap = 360, 42, 8
            px0, py0 = (W - pw) / 2, top - 4
            ph = 64 + len(TV_PAD) * (kh + gap) + 8
            d.rounded_rectangle((px0 - 2, py0 - 2, px0 + pw + 2, py0 + ph + 2), radius=16, fill=LINE)
            d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph), radius=15, fill=BG)
            d.text((px0 + 20, py0 + 28), "Channel", font=F["small"], fill=MUTED, anchor="lm")
            shown = pad["text"] or ""
            d.text((px0 + pw - 20, py0 + 28), shown + ("_" if len(shown) < 7 else ""), font=F["big"],
                   fill=TEXT, anchor="rm")
            y = py0 + 58
            hit = time.monotonic() - self.remote_hit[1] < 0.2
            for r, row in enumerate(TV_PAD):
                kw = (pw - 40 - gap * (len(row) - 1)) / len(row) if len(row) > 1 else pw - 40
                x = px0 + 20
                for c, (label, what) in enumerate(row):
                    on = pad["r"] == r and pad["c"] == c
                    side = not (what.isdigit() or what in ("dash", "del", "go"))
                    fill = ACCENT if on else (LINE if side else ROW)
                    if on and hit:
                        fill = TEXT
                    d.rounded_rectangle((x, y, x + kw, y + kh), radius=10, fill=fill)
                    font = F["keycap"] if len(label) <= 2 else F["small"]
                    d.text((x + kw / 2, y + kh / 2), label, font=font, fill=BG if on else TEXT, anchor="mm")
                    x += kw + gap
                y += kh + gap
            self.footer(d, [("A", "Press"), ("START", "Go"), ("L R", "CH − +"), ("X", "Delete"), ("B", "Close")])
        elif self.remote_more is not None:                 # the More menu, over the remote
            opts = self.remote_options()
            sel = self.remote_more["sel"] % len(opts)
            rows = min(len(opts), 6)
            first = max(0, min(sel - rows // 2, len(opts) - rows))
            longest = max(d.textlength(("Input  " + label) if job[0] == "source" else label, font=F["row"])
                          for label, job in opts)
            mw, rh = int(min(max(300, longest + 60), W - 80)), 40    # (wide enough for a TV's name)
            mx0, my0 = (W - mw) / 2, top + 40
            d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + 44 + rows * rh + 12),
                                radius=14, fill=LINE)
            d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + 42 + rows * rh + 10), radius=13, fill=BG)
            d.text((mx0 + 20, my0 + 22), "TV", font=F["small"], fill=MUTED, anchor="lm")
            for n, k in enumerate(range(first, first + rows)):
                label, job = opts[k]
                ry = my0 + 42 + n * rh
                if k == sel:
                    d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                text = ("Input  " + label) if job[0] == "source" else label
                d.text((mx0 + 22, ry + (rh - 4) / 2), self.fit(d, text, F["row"], mw - 60), font=F["row"],
                       fill=TEXT if k == sel else BODY, anchor="lm")
                if job[0] == "source" and label == st.get("source"):
                    d.ellipse((mx0 + mw - 30, ry + 14, mx0 + mw - 22, ry + 22), fill=ACCENT)
            self.footer(d, [("▲▼", "Choose"), ("A", "OK"), ("B", "Close")])
        else:
            self.footer(d, [("SEL", "More"), ("B", "Back")], right=ha.where)
        self.fb.show(img)
