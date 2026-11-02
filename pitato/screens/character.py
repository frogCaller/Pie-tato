"""The Bot's Character: everything about who it is, made your own, as a game's character creator does. Its name (and
what it calls you), its eyes (how big, how tall, how round their corners, how far apart, eyelashes), its mouth (how
big), its colours (its face's, its background's) and its voice (which one, out loud or not, how it talks, how often it
says something by itself): ▲▼ go from one to the next, ◀▶ change it (A types a name), and its face beside them shows
it at once, its name over it. L and R go from one part to the next, SELECT shows it happy, sorry, cool..., X makes up
a look at random, and Y twice puts its look back as it started. Kept in bot.txt as you go. From the Bot (X > Edit
Character), or its settings (Settings > Bot > Character)."""
import random
import time

from ..theme import ACCENT, BODY, LINE, MUTED, ROW, TEXT
from ..bot import FRIEND_CHATTER, FRIEND_STYLES
from ..face import FACE_BACKS, FACE_COLOURS, SHAPE_DEFAULTS, SHAPE_MOST
from ..voice import BOT_VOICES, voice_name, voices_here

CHAR_PARTS = (("Name", ("name", "you")),
              ("Eyes", ("eye_size", "eye_height", "eye_corners", "eye_gap", "lashes")),
              ("Mouth", ("mouth_size",)),
              ("Colours", ("colour", "background")),
              ("Voice", ("voice", "speak", "style", "chatter")))
CHAR_FIRST = 1                         # (the part it opens on, the first time: Eyes)
CHAR_LABELS = {"name": "Name", "you": "What it calls you", "eye_size": "Size", "eye_height": "Height",
               "eye_corners": "Corners", "eye_gap": "Spacing", "lashes": "Eyelashes", "mouth_size": "Size",
               "colour": "Face", "background": "Background", "voice": "Voice", "speak": "Talks out loud",
               "style": "How it talks", "chatter": "Chats"}
CHAR_TYPED = ("name", "you")           # (A types these: no ◀▶)
CHAR_CHATTER = {"30": "Every 30 min", "60": "Every hour", "0": "Never"}
CHAR_LOOKS = (("idle", "Calm"), ("happy", "Happy"), ("curious", "Curious"), ("sad", "Sorry"), ("cool", "Cool"),
              ("sleepy", "Sleepy"), ("talking", "Talking"), ("listening", "Listening"), ("thinking", "Thinking"),
              ("alert", "Surprised"))
CHAR_RANDOM = {"eye_size": (2, 9), "eye_height": (2, 9), "eye_corners": (3, 10), "eye_gap": (1, 8),
               "mouth_size": (2, 8)}   # X: a look made up, each step from this to that (none of them too odd)
CHAR_CONTRAST = 90                     # ...its face and its background this far apart in lightness, at least
CHAR_RESET = dict(SHAPE_DEFAULTS, colour="White", background="Dark", lashes="off")   # Y, twice: its look as it
                                                                                      # started (its voice as it is)
CHAR_ROW = 48                          # a row's height
CHAR_SLIDER = 112                      # a step's slider: this wide


def lightness(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class CharacterScreen:
    """The Bot's Character: Settings' page "f_char", on the Bot (B: back to it) or in Settings > Bot."""

    def on_char_page(self):
        """The Bot's Character is on the screen."""
        return self.set_page == "f_char" and self.on_bot_settings()

    def char_open(self, from_menu=False):
        """The Character page: from the Bot's X menu (B goes back to the Bot), or its settings' Character row (B goes
        back to them)."""
        if from_menu and self.tab_type() == "friend":
            self.bot_settings = True
        self.char_from = "menu" if from_menu else "settings"
        self.set_page = "f_char"
        self.char_sec, self.char_row = getattr(self, "char_sec", CHAR_FIRST), getattr(self, "char_row", 0)
        self.char_look = "idle"
        self.confirm = (None, 0.0)
        self.face_next = 0.0
        self.dirty = True

    def char_close(self):
        """B: back to where it was opened from."""
        self.confirm = (None, 0.0)
        if getattr(self, "char_from", "settings") == "menu" and self.bot_settings:
            self.bot_settings_close()
        else:
            self.set_page = "friend"
            keys = [r[0] for r in self.settings_rows()]
            self.set_sel = keys.index("f_char") if "f_char" in keys else 0
        self.dirty = True

    # -- what it is now --------------------------------------------------------------------------------------------
    def char_keys(self):
        return CHAR_PARTS[self.char_sec % len(CHAR_PARTS)][1]

    def char_key(self):
        keys = self.char_keys()
        self.char_row = max(0, min(self.char_row, len(keys) - 1))
        return keys[self.char_row]

    def char_preview_look(self):
        """How its face looks beside them: talking while it talks (its voice, tried), else the look SELECT showed."""
        return "talking" if self.voice.speaking else getattr(self, "char_look", "idle")

    def char_value(self, key):
        """What a row shows: its step (0 to 10) for its shape, else its words."""
        if key in SHAPE_DEFAULTS:
            return self.bot_steps()[key]
        if key == "lashes":
            return "On" if self.bot_lashes() else "Off"
        if key == "colour":
            return self.bot_colour()
        if key == "background":
            return self.bot_back()
        if key == "voice":
            job = self.voice.job
            if job and job["id"] == self.voice_want:
                return f"Getting it… {job['pct']}%"
            if not self.voice.supported():
                return "Not on this Pi"
            return voice_name(self.bot_voice()) if self.bot_voice() else "None"
        if key == "style":
            return self.friend.style()["name"]
        if key == "name":
            return self.bot_name() or "Not set"
        if key == "you":
            return self.friend.name or "Not set"
        if key == "speak":
            return "On" if self.bot_speaks() else "Off"
        if key == "chatter":
            return CHAR_CHATTER.get(str(self.friend.chatter()), self.friend.chatter_text())
        return ""

    def char_summary(self):
        """Settings > Bot > Character's value: its name."""
        return self.bot_name() or "Your bot"

    # -- changing it -----------------------------------------------------------------------------------------------
    def char_change(self, key, d):
        """◀ (d -1) or ▶ (1) on a row: its next step, colour, voice..., kept in bot.txt."""
        if key in SHAPE_DEFAULTS:
            now = self.bot_steps()[key]
            new = max(0, min(SHAPE_MOST, now + d))
            if new != now:
                self.friend_set(**{key: new})
        elif key == "lashes":
            self.friend_set(lashes="off" if self.bot_lashes() else "on")
        elif key == "colour":
            self.bot_colour_step(d)
        elif key == "background":
            self.bot_back_step(d)
        elif key == "voice":
            self.char_voice_step(d)
        elif key == "style":
            keys = [k for k, *_ in FRIEND_STYLES]
            cur = self.friend.style()["key"]
            if self.friend_set(style=keys[(keys.index(cur) + d) % len(keys)]):
                self.toast(self.style_sample(), 3)
        elif key == "speak":
            self.bot_speak_step()
        elif key == "chatter":
            labels = [t for t, _ in FRIEND_CHATTER]
            cur = self.friend.chatter_text()
            i = labels.index(cur) if cur in labels else 0
            self.friend_set(chatter=FRIEND_CHATTER[(i + d) % len(FRIEND_CHATTER)][1])

    def char_type(self, key):
        """A on Name or What it calls you: the keyboard, to type it."""
        if key == "name":
            self.open_keyboard("Its name", self.bot_name(), self.bot_name_typed, limit=24)
        elif key == "you":
            self.open_keyboard("What should it call you?", self.friend.name, lambda t: self.friend_set(name=t),
                               limit=40, empty=True)

    def char_voices_here(self):
        """The voices on the Pi, in the order Settings lists them: ◀▶ go through these (none fetched by it)."""
        here = voices_here()
        ours = [i for i, _, _ in BOT_VOICES]
        return [i for i in ours if i in here] + sorted(v for v in here if v not in ours)

    def char_voice_step(self, d):
        """◀▶ on Voice: the next voice on the Pi (or none), heard at once. A: all of them, to get another."""
        if not self.voice.supported():
            self.toast("Piper doesn't run on this Pi", 3)
            return
        choices = [""] + self.char_voices_here()
        if len(choices) == 1:
            self.toast("A gets it a voice", 3)
            return
        cur = self.bot_voice() if self.bot_voice() in choices else ""
        ok, what = self.voice_pick(choices[(choices.index(cur) + d) % len(choices)])
        self.toast(what, 2)

    def char_voices(self):
        """A on Voice: the voices (Settings > Bot > Voice's list), to get one; B comes back here."""
        if not self.voice.supported():
            self.toast("Piper doesn't run on this Pi", 3)
            return
        self.voices_from = "f_char"
        self.set_page = "f_voices"
        rows = self.settings_rows()
        want = self.voice_want or self.bot_voice()
        self.set_sel = next((i for i, r in enumerate(rows) if r[2] == want), 0)

    def char_random(self):
        """X: a look made up: its eyes, its mouth, its colours (its face always clear on its background), lashes or
        not. Its voice stays as it is."""
        steps = {k: random.randint(*CHAR_RANDOM[k]) for k in SHAPE_DEFAULTS}
        pairs = [(c, b) for c, fc in FACE_COLOURS for b, bc in FACE_BACKS
                 if abs(lightness(fc) - lightness(bc)) >= CHAR_CONTRAST
                 and (c, b) != (self.bot_colour(), self.bot_back())]
        colour, back = random.choice(pairs)
        self.friend_set(colour=colour, background=back, lashes=random.choice(("on", "off")), **steps)

    def char_reset(self):
        """Y, twice: its look as it started (white on the menus' dark, its eyes and mouth as they were, no lashes)."""
        if self.confirm[0] != "charreset" or time.monotonic() > self.confirm[1]:
            self.confirm = ("charreset", time.monotonic() + 4)
            self.toast("Press Y again to put its look back as it started", 4)
            return
        self.confirm = (None, 0.0)
        if self.friend_set(**CHAR_RESET):
            self.toast("Its look, as it started", 2)

    def char_pick(self, sec, row):
        """A row (or a part's name) tapped on the web page's copy of the screen: picked."""
        self.char_sec = sec % len(CHAR_PARTS)
        self.char_row = max(0, min(row, len(self.char_keys()) - 1))
        self.dirty = True

    def press_character(self, name, repeat):
        key = self.char_key()
        if name in ("l", "r"):
            if not repeat:
                self.char_sec = (self.char_sec + (1 if name == "r" else -1)) % len(CHAR_PARTS)
                self.char_row = 0
        elif name in ("up", "down"):
            r = self.char_row + (1 if name == "down" else -1)
            if r < 0:                                  # (on up into the part before: its last)
                self.char_sec = (self.char_sec - 1) % len(CHAR_PARTS)
                self.char_row = len(self.char_keys()) - 1
            elif r >= len(self.char_keys()):           # (on down into the next: its first)
                self.char_sec = (self.char_sec + 1) % len(CHAR_PARTS)
                self.char_row = 0
            else:
                self.char_row = r
        elif name in ("left", "right"):
            if key in CHAR_TYPED:
                pass
            elif not repeat or key in SHAPE_DEFAULTS:  # (a step held: on and on, as a slider)
                self.char_change(key, -1 if name == "left" else 1)
        elif repeat:
            return None
        elif name == "a":
            if key == "voice":
                self.char_voices()
            elif key in CHAR_TYPED:
                self.char_type(key)
            elif key not in SHAPE_DEFAULTS:
                self.char_change(key, 1)
        elif name == "x":
            self.char_random()
        elif name == "y":
            self.char_reset()
            self.dirty = True
            return None
        elif name == "select":
            looks = [k for k, _ in CHAR_LOOKS]
            cur = getattr(self, "char_look", "idle")
            self.char_look = looks[(looks.index(cur) + 1) % len(looks)] if cur in looks else "idle"
            self.face_next = 0.0
        elif name in ("b", "start"):
            self.char_close()
            return None
        if name != "y" and self.confirm[0] == "charreset":
            self.confirm = (None, 0.0)
        self.dirty = True
        return None

    # -- drawing it ------------------------------------------------------------------------------------------------
    def render_character(self):
        """Its face, big, on its background, in a panel on the left, its name over it (how it looks under it: SELECT
        for another); its parts along the top on the right (L R), the picked part's rows under them, each with its
        slider, its colour or its words."""
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        d.text((20, self.LIST_TOP + 10), "Bot  ›  Character", font=F["small"], fill=MUTED, anchor="lm")
        top, bottom = self.LIST_TOP + 26, H - self.FOOTER - 10
        face, back = self.bot_palette()
        pw = int(min(300, W * 0.42))
        px0, px1 = 16, 16 + pw
        d.rounded_rectangle((px0, top, px1, bottom), radius=18, fill=back, outline=LINE)
        size = int(min(pw / 1.6, (bottom - top) * 0.58))   # (its widest look, eyes far apart: inside its panel)
        face_at = ((px0 + px1) / 2, top + (bottom - top) * 0.52, size)
        self.draw_bot_face(d, face_at, look=self.char_preview_look(), back=back)
        look = dict(CHAR_LOOKS).get(getattr(self, "char_look", "idle"), "Calm")
        ink = BODY if lightness(back) < 140 else (40, 44, 52)
        name = self.bot_name()
        if name:                                       # its name, over its face (clear of its frames)
            d.text(((px0 + px1) / 2, top + 22), self.fit(d, name, F["head"], pw - 40), font=F["head"],
                   fill=TEXT if lightness(back) < 140 else (26, 28, 34), anchor="mm")
        lw = self.key_w(d, "SELECT") + 8 + d.textlength(look, font=F["small"])
        lx, ly = (px0 + px1 - lw) / 2, bottom - 20
        x = self.key(d, lx, ly, "SELECT") + 8
        d.text((x, ly), look, font=F["small"], fill=ink, anchor="lm")
        self.tap_hint(lx - 6, x + d.textlength(look, font=F["small"]) + 6, ly - 14, ly + 14, "SELECT")
        # its parts, along the top: spread across the room there is (smaller, if they wouldn't fit)
        rx0, rx1 = px1 + 18, W - 16
        bold, plain = F["tab_b"], F["tab"]
        widths = [d.textlength(part, font=bold) for part, _ in CHAR_PARTS]
        if sum(widths) + 12 * (len(widths) - 1) > rx1 - rx0 - 12:
            bold, plain = F["small_b"], F["small"]
            widths = [d.textlength(part, font=bold) for part, _ in CHAR_PARTS]
        gap = max(8, min(24, (rx1 - rx0 - 12 - sum(widths)) / max(1, len(widths) - 1)))
        x = rx0 + 6
        for i, (part, _) in enumerate(CHAR_PARTS):
            on = i == self.char_sec % len(CHAR_PARTS)
            font = bold if on else plain
            tw = d.textlength(part, font=font)
            d.text((x, top + 14), part, font=font, fill=TEXT if on else MUTED, anchor="lm")
            if on:
                d.rounded_rectangle((x, top + 27, x + tw, top + 30), radius=2, fill=ACCENT)
            self.tappable((x - gap / 2, top, x + tw + gap / 2, top + 32), "char", i, 0)
            x += widths[i] + gap
        d.line((rx0, top + 34, rx1, top + 34), fill=LINE)
        # its rows
        keys = self.char_keys()
        sel = self.char_row
        steps = self.bot_steps()
        for r, key in enumerate(keys):
            y = top + 42 + r * CHAR_ROW
            on = r == sel
            mid = y + CHAR_ROW / 2 - 1
            if on:
                d.rounded_rectangle((rx0, y + 2, rx1, y + CHAR_ROW - 4), radius=10, fill=ROW)
                d.rectangle((rx0, y + 10, rx0 + 3, y + CHAR_ROW - 12), fill=ACCENT)
            self.tappable((rx0, y, rx1, y + CHAR_ROW), "char", self.char_sec, r)
            d.text((rx0 + 14, mid), CHAR_LABELS[key], font=F["row"], fill=TEXT if on else BODY, anchor="lm")
            x1 = rx1 - 12
            arrows = on and key not in CHAR_TYPED       # (◀ ▶ by what they change; A types a name)
            if arrows:
                d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                x1 -= 22
            if key in SHAPE_DEFAULTS:                  # a slider: its step, and where it started (a notch)
                x0 = x1 - CHAR_SLIDER
                k = steps[key] / SHAPE_MOST
                d.rounded_rectangle((x0, mid - 3, x1, mid + 3), radius=3, fill=LINE)
                d.rounded_rectangle((x0, mid - 3, x0 + (x1 - x0) * k, mid + 3), radius=3,
                                    fill=ACCENT if on else MUTED)
                nx = x0 + (x1 - x0) * SHAPE_DEFAULTS[key] / SHAPE_MOST
                d.rectangle((nx - 1, mid + 7, nx + 1, mid + 11), fill=MUTED)
                kx = x0 + (x1 - x0) * k
                d.ellipse((kx - 8, mid - 8, kx + 8, mid + 8), fill=TEXT if on else BODY)
            else:
                value = self.char_value(key)
                room = rx1 - rx0 - 42 - d.textlength(CHAR_LABELS[key], font=F["row"]) - (52 if arrows else 0)
                shown = self.fit(d, value, F["row"], max(40, min(150, room)))
                d.text((x1, mid), shown, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
                x0 = x1 - d.textlength(shown, font=F["row"])
                if key in ("colour", "background"):    # (the colour itself, beside its name)
                    sw = face if key == "colour" else back
                    d.ellipse((x0 - 30, mid - 9, x0 - 12, mid + 9), fill=sw, outline=LINE)
                    x0 -= 30
            if arrows:
                d.text((x0 - 10, mid), "◀", font=F["small"], fill=ACCENT, anchor="rm")
                self.tap_arrows(y, y + CHAR_ROW, x0 - 10, rx1 - 12)
        key = keys[sel % len(keys)]
        asking = self.confirm[0] == "charreset" and time.monotonic() < self.confirm[1]
        hints = ([("A", "Type")] if key in CHAR_TYPED else [("◀▶", "Change")]) + \
            ([("A", "More voices")] if key == "voice" else []) + \
            [("L R", "Parts"), ("X", "Random"), ("Y", "Reset?" if asking else "Reset", asking), ("B", "Done")]
        self.footer(d, self.hints_room(hints, keep=("◀▶", "A", "B")))
        self.fb.show(img)
        x0, y0, x1, y1 = self.face_box(face_at)                       # (its frames: inside its panel's edge)
        box = (max(x0, px0 + 2), max(y0, top + 2), min(x1, px1 - 1), min(y1, bottom - 1))
        self.face_shot = (img, box, getattr(self.fb, "frames", None), face_at, back)
