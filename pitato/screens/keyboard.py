"""The on-screen keyboard (and a real one, while it's up)."""
from ..theme import ACCENT, BG, LINE, MUTED, ROW, TEXT
from ..inputs import KEY_BOTTOM, KEY_ROWS, KEY_SYMBOLS


class KeyboardScreen:
    """The on-screen keyboard (and a real one, while it's up)."""

    # -- the on-screen keyboard (and a real one, while it's up) ----------------
    def open_keyboard(self, title, text, done, strip=True, empty=False, row=1, limit=60, local=False, cancel=None):
        """A box to type in: done(text) when you're done. local: it notes whether the web page's remote typed
        in it (kb["remote"]). cancel(text): what you typed, when you back out."""
        back = self.kb["back_to"] if self.kb else self.view       # one box straight after another
        self.kb = {"title": title, "text": text, "done": done, "r": row, "c": 0, "shift": False, "sym": False,
                   "back_to": back, "strip": strip, "empty": empty, "limit": limit, "local": local,
                   "cancel": cancel, "remote": False}
        self.view = "keys"
        self.keyreader.on_key = self.keyboard_key
        self.keyreader.start()
        self.dirty = True
        return self.kb

    def close_keyboard(self, ok):
        kb = self.kb
        self.keyreader.stop()
        self.kb = None
        if kb:
            self.view = kb["back_to"] if kb["back_to"] != "keys" else "list"
            text = kb["text"].strip() if kb.get("strip", True) else kb["text"]
            if ok and (text.strip() or kb.get("empty")):
                kb["done"](text)                        # may open another box (a password, say)
            elif not ok and kb.get("cancel"):
                kb["cancel"](text)
        self.dirty = True

    def keyboard_key(self, kind, ch=""):
        kb = self.kb
        if not kb:
            return
        if kind == "char":
            kb["text"] = (kb["text"] + ch)[:kb.get("limit", 60)]
        elif kind == "back":
            kb["text"] = kb["text"][:-1]
        elif kind in ("done", "cancel"):
            self.close_keyboard(kind == "done")
        self.dirty = True

    def press_keys(self, name, repeat):
        kb = self.kb
        if kb is None:
            self.view = "list"
            return None
        if kb.get("local") and self.web_guard:
            kb["remote"] = True                        # (the web page's remote had a hand in it)
        rows = len(KEY_ROWS) + 1
        if name in ("up", "down"):
            kb["r"] = (kb["r"] + (1 if name == "down" else -1)) % rows
            if kb["r"] == len(KEY_ROWS):
                kb["c"] = min(kb["c"] * len(KEY_BOTTOM) // 10, len(KEY_BOTTOM) - 1)
        elif name in ("left", "right"):
            n = len(KEY_BOTTOM) if kb["r"] == len(KEY_ROWS) else 10
            kb["c"] = (kb["c"] + (1 if name == "right" else -1)) % n
        elif name == "a":
            if kb["r"] < len(KEY_ROWS):
                ch = (KEY_SYMBOLS if kb["sym"] else KEY_ROWS)[kb["r"]][kb["c"] % 10]
                self.keyboard_key("char", ch.upper() if kb["shift"] else ch)
                kb["shift"] = False
            else:
                what = KEY_BOTTOM[kb["c"]][0]
                if what == "shift":
                    kb["shift"] = not kb["shift"]
                elif what == "sym":
                    kb["sym"] = not kb["sym"]
                elif what == "space":
                    self.keyboard_key("char", " ")
                elif what == "back":
                    self.keyboard_key("back")
                else:
                    self.keyboard_key("done")
        elif name == "x":
            self.keyboard_key("back")
        elif name == "y":
            self.keyboard_key("char", " ")
        elif name == "select" and not repeat:
            kb["shift"] = not kb["shift"]
        elif name == "start" and not repeat:
            self.keyboard_key("done")
        elif name == "b" and not repeat:
            self.close_keyboard(False)
        if self.kb is not None and kb["r"] == len(KEY_ROWS):
            kb["c"] = min(kb["c"], len(KEY_BOTTOM) - 1)
        self.dirty = True
        return None

    def render_keys(self):
        F = self.fonts
        kb = self.kb or {"title": "", "text": "", "r": 0, "c": 0, "shift": False}
        img, d = self.canvas()
        W = self.fb.w
        self.title_row(d, kb["title"])
        d.rounded_rectangle((24, 84, W - 24, 132), radius=12, fill=ROW, outline=ACCENT, width=2)
        text = kb["text"]
        shown = text
        while d.textlength(shown, font=F["big"]) > W - 90 and shown:
            shown = shown[1:]
        d.text((42, 108), shown, font=F["big"], fill=TEXT, anchor="lm")
        cx = 42 + d.textlength(shown, font=F["big"]) + 3
        d.rectangle((cx, 94, cx + 2, 122), fill=ACCENT)
        kw, kh, gap = 54, 46, 6
        x0 = (W - (10 * kw + 9 * gap)) / 2
        y0 = 150
        for r, row in enumerate(KEY_SYMBOLS if kb.get("sym") else KEY_ROWS):
            for c, ch in enumerate(row):
                x, y = x0 + c * (kw + gap), y0 + r * (kh + gap)
                on = kb["r"] == r and kb["c"] == c
                d.rounded_rectangle((x, y, x + kw, y + kh), radius=9, fill=ACCENT if on else ROW)
                label = ch.upper() if kb["shift"] else ch
                d.text((x + kw / 2, y + kh / 2), label, font=F["keycap"], fill=BG if on else TEXT, anchor="mm")
        y = y0 + len(KEY_ROWS) * (kh + gap)
        x = x0
        unit = (10 * kw + 9 * gap - (len(KEY_BOTTOM) - 1) * gap) / 10
        for c, (what, label, span) in enumerate(KEY_BOTTOM):
            w = unit * span
            on = kb["r"] == len(KEY_ROWS) and kb["c"] == c
            lit = (what == "shift" and kb["shift"]) or (what == "sym" and kb.get("sym"))
            d.rounded_rectangle((x, y, x + w, y + kh), radius=9,
                                fill=ACCENT if on else (LINE if not lit else MUTED))
            if what == "sym" and kb.get("sym"):
                label = "abc"
            d.text((x + w / 2, y + kh / 2), label, font=F["keycap"] if len(label) < 3 else F["small"],
                   fill=BG if on else TEXT, anchor="mm")
            x += w + gap
        self.footer(d, [("A", "Type"), ("X", "Delete"), ("Y", "Space"), ("START", "Done"), ("B", "Cancel")])
        self.fb.show(img)
