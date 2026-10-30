"""Settings > Bluetooth: your devices (connect, disconnect, forget) and the ones nearby (pair), Bluetooth on or off,
and a keyboard's code to type in, big, while it pairs. pitato/bluetooth.py does the work, on threads of its own."""
import time

from ..theme import ACCENT, BODY, DONE, MUTED, ROW, TEXT

BT_BUSY = {"pair": "Pairing…", "connect": "Connecting…", "disconnect": "Disconnecting…", "forget": "Forgetting…"}
BT_PICKABLE = ("bt_power", "bt_dev", "bt_new")


class BluetoothScreen:
    """Settings > Bluetooth."""

    # -- its rows ---------------------------------------------------------------------
    def bt_rows(self):
        """(key, label, extra): the switch; your devices; the ones nearby; with a heading over each."""
        s = self.bt.snapshot()
        if s["there"] is False:
            return [("bt_none", s["why"] or "This Pi has no Bluetooth", None)]
        rows = [("bt_power", "Bluetooth", ["On", "Off"])]
        if not s["on"]:
            return rows
        mine = [d for d in s["devices"] if d["paired"] or d["connected"]]
        near = [d for d in s["devices"] if not (d["paired"] or d["connected"])]
        if mine:
            rows.append(("bt_head", "Your devices", None))
            rows += [("bt_dev", d["name"], d) for d in mine]
        if near:
            rows.append(("bt_head", "Nearby", None))
            rows += [("bt_new", d["name"], d) for d in near]
        return rows

    def bt_sel(self, rows):
        """The row picked: the device picked before, wherever it's moved to; or else the nearest one to where
        it was (one forgotten, gone from the list)."""
        for k, (key, _, extra) in enumerate(rows):
            if key in ("bt_dev", "bt_new") and extra["addr"] == self.bt_pick:
                return k
        pick = [k for k, r in enumerate(rows) if r[0] in BT_PICKABLE] or [0]
        if self.bt_pick is None:
            return pick[0]
        return min(pick, key=lambda k: (abs(k - self.bt_at), k))

    def bt_choose(self, rows, k):
        key, _, extra = rows[k]
        self.bt_pick = extra["addr"] if key in ("bt_dev", "bt_new") else None
        self.bt_at = k

    def on_bt_page(self):
        return self.active and self.view == "list" and self.tab_type() == "settings" and self.set_page == "bluetooth"

    def bt_changed(self):
        """(On Bluetooth's threads) something's changed: Settings drawn again, if it's showing."""
        if self.active and self.view == "list" and self.tab_type() == "settings":
            self.dirty = True

    def bt_sound_note(self):
        """(On Bluetooth's thread) headphones just connected: where the sound goes, by Settings > Sound."""
        return ("Sound plays through it" if self.setting("sound") == "Auto"
                else "For sound through it, set Settings > Sound to Auto")

    def bt_value(self):
        """Settings' first page: Bluetooth's row."""
        s = self.bt.summary()
        if s["there"] is None:
            return "…"
        if s["there"] is False:
            return "Not on this Pi"
        if not s["on"]:
            return "Off"
        n = sum(1 for d in s["devices"] if d["connected"])
        return f"{n} connected" if n else "On"

    # -- its buttons --------------------------------------------------------------------
    def bt_open(self):
        self.set_page, self.bt_pick, self.bt_at = "bluetooth", None, 0
        self.confirm = (None, 0.0)
        self.bt.watch("screen", True)
        self.bt.look()                                 # (if it's on: the ones in pairing mode come up)

    def bt_close(self):
        self.set_page, self.set_sel = "root", self.settings_root_index("bluetooth")
        self.confirm = (None, 0.0)
        self.bt.watch("screen", False)

    def bt_said(self, err):
        if err:
            self.toast(err, 3)

    def bt_sure(self, what, ask):
        """A second press within a few seconds does it: True then; the first says so."""
        if self.confirm[0] == what and time.monotonic() < self.confirm[1]:
            self.confirm = (None, 0.0)
            return True
        self.confirm = (what, time.monotonic() + 4)
        self.toast(ask, 4)
        return False

    def press_bluetooth(self, name, repeat):
        rows = self.bt_rows()
        k = self.bt_sel(rows)
        key, _, extra = rows[k]
        bt = self.bt
        if name == "b":
            if not repeat:
                self.bt_close()
        elif name in ("up", "down"):
            pick = [j for j, r in enumerate(rows) if r[0] in BT_PICKABLE]
            if pick:
                pos = pick.index(k) if k in pick else 0
                self.bt_choose(rows, pick[(pos + (1 if name == "down" else -1)) % len(pick)])
        elif repeat:
            pass
        elif name == "x":
            self.bt_said(bt.look())
        elif key == "bt_power" and name in ("a", "left", "right"):
            if not bt.snapshot()["on"]:
                self.bt_said(bt.power(True))
            elif self.bt_sure("bt_off", "Press again to turn Bluetooth off. Its devices disconnect"):
                self.bt_said(bt.power(False))
        elif key == "bt_new" and name == "a":
            self.bt_choose(rows, k)
            self.bt_said(bt.pair(extra["addr"]))
        elif key == "bt_dev" and name == "a":
            self.bt_choose(rows, k)
            if not extra["connected"]:
                self.bt_said(bt.connect(extra["addr"]))
            elif self.bt_sure("bt_dis:" + extra["addr"], "Press A again to disconnect it"):
                self.bt_said(bt.disconnect(extra["addr"]))
        elif key == "bt_dev" and name == "y":
            self.bt_choose(rows, k)
            if self.bt_sure("bt_forget:" + extra["addr"], "Press Y again to forget it"):
                self.bt_said(bt.forget(extra["addr"]))
        self.dirty = True
        return None

    # -- drawing ------------------------------------------------------------------------
    @staticmethod
    def bt_glyph(d, kind, x, y, fill):
        """What a device is, drawn small (24 across) at x, y."""
        if kind == "controller":
            d.rounded_rectangle((x + 1, y + 6, x + 23, y + 19), radius=6, outline=fill, width=2)
            d.line((x + 5, y + 12.5, x + 10, y + 12.5), fill=fill, width=2)
            d.line((x + 7.5, y + 10, x + 7.5, y + 15), fill=fill, width=2)
            d.ellipse((x + 15, y + 9.5, x + 17.5, y + 12), fill=fill)
            d.ellipse((x + 17.5, y + 12.5, x + 20, y + 15), fill=fill)
        elif kind == "keyboard":
            d.rounded_rectangle((x + 1, y + 5, x + 23, y + 19), radius=2, outline=fill, width=2)
            for i in range(4):
                d.rectangle((x + 5 + i * 4.5, y + 9, x + 6.5 + i * 4.5, y + 10.5), fill=fill)
            d.line((x + 7, y + 14.5, x + 17, y + 14.5), fill=fill, width=2)
        elif kind == "mouse":
            d.rounded_rectangle((x + 6, y + 2, x + 18, y + 22), radius=6, outline=fill, width=2)
            d.line((x + 12, y + 3, x + 12, y + 9), fill=fill, width=2)
        elif kind == "headphones":
            d.arc((x + 3, y + 3, x + 21, y + 21), 180, 360, fill=fill, width=2)
            d.line((x + 3, y + 12, x + 3, y + 16), fill=fill, width=2)
            d.line((x + 21, y + 12, x + 21, y + 16), fill=fill, width=2)
            d.rounded_rectangle((x + 1, y + 13, x + 7, y + 22), radius=2, fill=fill)
            d.rounded_rectangle((x + 17, y + 13, x + 23, y + 22), radius=2, fill=fill)
        elif kind == "speaker":
            d.rounded_rectangle((x + 5, y + 1, x + 19, y + 23), radius=3, outline=fill, width=2)
            d.ellipse((x + 8, y + 10, x + 16, y + 18), outline=fill, width=2)
            d.ellipse((x + 11, y + 4, x + 13, y + 6), fill=fill)
        elif kind == "phone":
            d.rounded_rectangle((x + 7, y + 1, x + 17, y + 23), radius=3, outline=fill, width=2)
            d.line((x + 10.5, y + 19, x + 13.5, y + 19), fill=fill, width=2)
        elif kind in ("computer", "tv"):
            d.rounded_rectangle((x + 1, y + 4, x + 23, y + 17), radius=2, outline=fill, width=2)
            if kind == "tv":
                d.line((x + 8, y + 21, x + 10, y + 17), fill=fill, width=2)
                d.line((x + 16, y + 21, x + 14, y + 17), fill=fill, width=2)
            else:
                d.line((x + 12, y + 17, x + 12, y + 21), fill=fill, width=2)
                d.line((x + 8, y + 21, x + 16, y + 21), fill=fill, width=2)
        else:                                           # Bluetooth's own mark
            d.line([(x + 7, y + 7), (x + 17, y + 16), (x + 12, y + 21), (x + 12, y + 3), (x + 17, y + 8),
                    (x + 7, y + 17)], fill=fill, width=2, joint="curve")

    def render_bluetooth(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        s = self.bt.snapshot()
        rows = self.bt_rows()
        sel = self.bt_sel(rows)
        top, bottom = self.LIST_TOP + 26, H - self.FOOTER - 40
        d.text((20, self.LIST_TOP + 10), "Settings  ›  Bluetooth", font=F["small"], fill=MUTED, anchor="lm")
        n = sum(1 for x in s["devices"] if x["connected"])
        note = ("Looking…", ACCENT) if s["looking"] else (f"{n} connected", DONE) if n else None
        if note:
            d.text((W - 20, self.LIST_TOP + 10), note[0], font=F["small"], fill=note[1], anchor="rm")
        heights = [30 if r[0] == "bt_head" else 46 for r in rows]
        ys, y = [], 0
        for h in heights:
            ys.append(y)
            y += h
        shift = max(0, min(ys[sel] + heights[sel] - (bottom - top), y - (bottom - top)))   # (the picked row in view)
        if sel > 0 and rows[sel - 1][0] == "bt_head":
            shift = min(shift, ys[sel - 1])                                                  # (its heading too)
        for k, (key, label, extra) in enumerate(rows):
            y0 = top + ys[k] - shift
            if y0 < top - 1 or y0 + heights[k] > bottom + 1:
                continue
            mid = y0 + heights[k] / 2 - 1
            if key == "bt_head":
                d.text((30, y0 + 19), label, font=F["small"], fill=MUTED, anchor="ls")
                continue
            on = k == sel and key in BT_PICKABLE
            if key in BT_PICKABLE:
                self.tappable((0, y0, W, y0 + heights[k]), "bt", k)
            if on:
                d.rounded_rectangle((12, y0 + 2, W - 12, y0 + heights[k] - 4), radius=10, fill=ROW)
                d.rectangle((12, y0 + 10, 15, y0 + heights[k] - 12), fill=ACCENT)
            if key == "bt_none":
                d.text((30, mid), self.fit(d, label, F["row"], W - 60), font=F["row"], fill=MUTED, anchor="lm")
                continue
            if key == "bt_power":
                d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
                value = "…" if s["there"] is None else "On" if s["on"] else "Off"
                d.text((W - 28, mid), value, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
                continue
            self.bt_glyph(d, extra["kind"], 30, mid - 12, TEXT if on else MUTED)
            busy = s["busy"] if s["busy_addr"] == extra["addr"] else None
            right, colour = ((BT_BUSY.get(busy, "…"), ACCENT) if busy else
                             (("Connected", DONE) if extra["connected"] else ("Not connected", MUTED)) if key == "bt_dev"
                             else (extra["what"], MUTED))
            rw = d.textlength(right, font=F["small"])
            d.text((W - 28, mid), right, font=F["small"], fill=colour, anchor="rm")
            d.text((66, mid), self.fit(d, label, F["row"], W - 66 - 28 - rw - 16), font=F["row"],
                   fill=TEXT if on else BODY, anchor="lm")
        if s["there"] is True and not s["on"]:
            d.text((30, top + 46 + 22), self.fit(d, "Turn it on to connect your controllers, keyboards and headphones",
                                                 F["small"], W - 60), font=F["small"], fill=MUTED, anchor="lm")
        near = any(not (x["paired"] or x["connected"]) for x in s["devices"])
        line = (None if s["code"] else s["status"] or
                ("Looking for devices. Put yours in pairing mode" if s["looking"] else
                 "Press X to look for devices" if s["on"] and not near and s["there"] else None))
        if line:
            d.text((W / 2, H - self.FOOTER - 22), self.fit(d, line, F["small"], W - 40), font=F["small"],
                   fill=ACCENT if (s["status"] or s["looking"]) else MUTED, anchor="mm")
        key = rows[sel][0]
        hints = []
        if key == "bt_power":
            hints.append(("◀▶", "On / off"))
        elif key == "bt_dev":
            hints += [("A", "Disconnect" if rows[sel][2]["connected"] else "Connect"), ("Y", "Forget")]
        elif key == "bt_new":
            hints.append(("A", "Pair"))
        if s["there"] and s["on"]:
            hints.append(("X", "Look again" if s["looking"] else "Look"))
        hints.append(("B", "Back"))
        self.footer(d, hints)
        if s["code"]:
            self.bt_code_card(d, s)
        self.fb.show(img)

    def bt_code_card(self, d, s):
        """While a keyboard pairs: the code to type on it, big."""
        F, W, H = self.fonts, self.fb.w, self.fb.h
        dev = next((x for x in s["devices"] if x["addr"] == s["busy_addr"]), None)
        keyboard = dev is None or dev["kind"] in ("keyboard", "")
        cw, ch = min(W - 80, 470), 168
        x0, y0 = (W - cw) / 2, (self.LIST_TOP + H - self.FOOTER) / 2 - ch / 2
        d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), radius=16, fill=ROW, outline=ACCENT, width=2)
        say = "Type this on the keyboard" if keyboard else "Its code"
        d.text((W / 2, y0 + 32), self.fit(d, say, F["row"], cw - 40), font=F["row"], fill=TEXT, anchor="mm")
        code, font = s["code"], F["code"]
        gap = 8
        widths = [d.textlength(c, font=font) for c in code]
        x = W / 2 - (sum(widths) + gap * (len(code) - 1)) / 2
        for c, w in zip(code, widths):
            d.text((x, y0 + 86), c, font=font, fill=ACCENT, anchor="lm")
            x += w + gap
        if keyboard:
            d.text((W / 2, y0 + 136), "then press Enter on it", font=F["small"], fill=MUTED, anchor="mm")
