"""Konami code (in Apps): button codes of your own that do things. Hold HOME and press ▶, and a
box asks for a code: put one of yours in (▲▲▼◀▼▶A, say) and it turns the TV on, the lights off, opens an app, plays a
song or your last game, or turns the screen off. The classic one's there to start with (▲▲▼▼◀▶◀▶BA: cmatrix). On its
page: A tries a code, X changes what it does, Y twice forgets it, and New code takes a new one (press it, then stop a
moment; HOME stops). (HOME on its own: in the menus it does its thing as you let go of it, to see if a button comes
with it: ▶ for a code, ◀ for the terminal; app.py.)"""
import random
import threading
import time

from ..games import find_games
from ..homeassistant import HA_WATCH
from ..library import LIBRARY, RENAMED
from ..theme import BODY, LINE, MUTED, ROW, TEXT, WARN
from ..util import item

CODE_KEYS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "start", "select")
GLYPHS = {"up": "▲", "down": "▼", "left": "◀", "right": "▶", "a": "A", "b": "B", "x": "X", "y": "Y", "l": "L",
          "r": "R", "start": "START", "select": "SELECT"}
CODE_LEAST = 3           # buttons in a code, at least
CODE_MOST = 16           # ...and at most
IN_FIRST = 5.0           # HOME and ▶, then this long to start putting a code in
IN_GAP = 3.0             # ...and this long at most between its buttons
REC_DONE = 2.0           # seconds without a button while a new one's put in: that's the code
REC_GIVE_UP = 12.0       # ...and with nothing pressed at all: not after all
KONAMI_CLASSIC = ["up", "up", "down", "down", "left", "right", "left", "right", "b", "a"]
HOTKEY_VIEWS = ("home", "list", "now")   # where HOME and ▶ are Konami code's, HOME and ◀ the terminal's (the menus)
DOES = [("tv:on", "Turn the TV on"), ("tv:off", "Turn the TV off"), ("lights:on", "Turn the lights on"),
        ("lights:off", "Turn the lights off"), ("open", "Open"), ("song", "Play a random song"),
        ("game", "Play your last game"), ("rest", "Turn the screen off"), ("home", "Go to the home screen")]
OPEN_FIRST = "Weather"   # (the app Open starts on)


def glyphs(keys):
    """A code as it's shown: ▲ ▲ ▼ ◀ ▼ ▶ A."""
    return " ".join(GLYPHS.get(k, k) for k in keys)


def code_trouble(keys):
    """Why these buttons can't be a code (in words), or None."""
    if len(keys) < CODE_LEAST:
        return f"A code has {CODE_LEAST} buttons at least. Again"
    return None


def open_names():
    """The apps a code can open: each of them, Apps' too (not this page)."""
    return [t["name"] for t in LIBRARY if t["type"] != "konami"]


class KonamiScreen:
    """Your button codes: the box they're put in (HOME and ▶), and their page in Apps."""

    # -- your codes -----------------------------------------------------------------------------------------------
    def konami_codes(self):
        """Your codes ([{"keys", "do"}]): the classic one, until you've changed them."""
        v = self.setting("konami")
        if not isinstance(v, list):
            return [{"keys": list(KONAMI_CLASSIC), "do": "open:cmatrix"}]
        names = open_names()
        out = []
        for c in v:
            keys, do = (c.get("keys"), c.get("do")) if isinstance(c, dict) else (None, None)
            if isinstance(do, str) and do.startswith("open:") and do[5:] in RENAMED:
                do = "open:" + RENAMED[do[5:]]
            if (isinstance(keys, list) and all(k in CODE_KEYS for k in keys) and len(keys) <= CODE_MOST
                    and code_trouble(keys) is None and isinstance(do, str)
                    and (do in dict(DOES) and do != "open" or (do.startswith("open:") and do[5:] in names))):
                out.append({"keys": list(keys), "do": do})
        return out

    def konami_keep(self, codes):
        self.set_setting("konami", [{"keys": list(c["keys"]), "do": c["do"]} for c in codes])
        ki = self.tab_index("konami")
        if ki is not None:
            self.items[ki] = self.konami_rows()
        self.dirty = True

    @staticmethod
    def konami_label(do):
        if do.startswith("open:"):
            return f"Open {do[5:]}"
        return dict(DOES).get(do, do)

    def konami_clash(self, keys, besides=None):
        """Why a new code can't be one of yours (it's one already, or one starts like the other), or None."""
        for k, c in enumerate(self.konami_codes()):
            if k == besides:
                continue
            other, label = c["keys"], self.konami_label(c["do"])
            if other == keys:
                return f"That's your code for {label} already. Again"
            if other[:len(keys)] == keys or keys[:len(other)] == other:
                return f"It starts like your code for {label}: make it different. Again"
        return None

    # -- the box they're put in: HOME and ▶ ----------------------------------------------------------------------
    def konami_hotkey_ok(self):
        """HOME and ▶ are Konami code's here, and HOME and ◀ the terminal's (so HOME waits till you let go of it, to
        see): the menus; not a game, a video, cmatrix and the others or Chromium; not while a code's put in or
        picked."""
        return (self.active and not self.resting and not self.attract_on() and self.game is None
                and self.view in HOTKEY_VIEWS and not self.proc_owns_screen()
                and self.konami_rec is None and self.konami_pick is None and self.konami_in is None)

    def konami_listen(self):
        """HOME and ▶: the box for one of your codes (True; none yet: said). False: not here after all
        (that button goes as itself)."""
        if not (self.active and self.view in HOTKEY_VIEWS and self.konami_in is None and not self.proc_owns_screen()):
            return False
        if not self.konami_codes():
            self.toast("No codes yet: make one in Apps > Konami code", 4)
            return True
        self.konami_in = {"keys": [], "at": time.monotonic(), "from": self.view}
        self.view = "konami"
        self.dirty = True
        return True

    def press_konami_in(self, name, repeat):
        """The box for a code: each button's part of it. One of yours, all in: done. The start of none of them: said,
        and back."""
        k_in = self.konami_in
        if k_in is None:                               # (never: the box without its code)
            self.view = "home"
            self.dirty = True
            return None
        if repeat or name not in CODE_KEYS:
            return None
        k_in["keys"].append(name)
        k_in["at"] = time.monotonic()
        keys = k_in["keys"]
        codes = self.konami_codes()
        done = next((c for c in codes if c["keys"] == keys), None)
        if done is not None:
            self.konami_in_back()
            self.konami_run(done)
        elif not any(c["keys"][:len(keys)] == keys for c in codes):
            self.konami_in_back()
            self.toast("That's not one of your codes", 3)
        else:
            self.dirty = True
        return None

    def konami_in_back(self):
        """The box for a code, gone: back to what was on the screen."""
        k_in, self.konami_in = self.konami_in, None
        if k_in is not None and self.view == "konami":
            self.view = k_in["from"]
        self.dirty = True

    def konami_run(self, c):
        """A code: what it does, done (and said)."""
        do = c["do"]
        self.toast(f"Konami code: {self.konami_label(do)}", 3)
        print(f"konami: {glyphs(c['keys'])}: {self.konami_label(do)}", flush=True)
        try:
            self.konami_do(do)
        except Exception as ex:                        # (never the menus' end)
            print(f"konami: {do}: {ex!r}", flush=True)
            self.toast("That code's thing didn't work", 3)

    def konami_do(self, do):
        if do in ("tv:on", "tv:off"):
            self.konami_tv(do[3:])
        elif do in ("lights:on", "lights:off"):
            self.konami_lights(do == "lights:on")
        elif do.startswith("open:"):
            if self.web_tab(do[5:]) is None:
                self.toast(f"There's no {do[5:]} here", 3)
        elif do == "song":
            self.konami_song()
        elif do == "game":
            self.konami_game()
        elif do == "rest":
            self.rest_start()
        elif do == "home":
            self.go_home()
            self.dirty = True

    def konami_tv(self, want):
        """The TV on or off, through Home Assistant (asked till it's seen to happen, as the TV Remote does)."""
        ri = self.tab_index("remote")
        ha = self.hass
        ha.load(LIBRARY[ri]["files"], pick=self.setting("ha_tv") or "")
        if not ha.configured:
            self.toast("Set up Home Assistant first: Settings > Home", 4)
            return
        ha.on_change = self.remote_changed
        ha.on_note = lambda text, secs=3: self.toast(text, secs)
        ha.on_pick = lambda entity: self.set_setting("ha_tv", entity)
        ha.send("power", want)
        ha.start()
        self.konami_ha = (time.monotonic(), time.monotonic() + HA_WATCH + 5)

    def konami_lights(self, on):
        """All your lights on or off, through Home Assistant (on a thread: it asks how they are first)."""
        li = self.tab_index("lights")
        lt = self.lights
        lt.load(LIBRARY[li]["files"])
        if not lt.configured:
            self.toast("Set up Home Assistant first: Settings > Home", 4)
            return
        lt.on_change = self.lights_changed
        lt.on_note = lambda text: self.toast(text, 3)

        def job():
            if not lt.found:
                lt.refresh()
            if lt.error:
                self.toast(lt.error, 4)
                return
            if on:
                off = [r for r in lt.lights() if r["kind"] == "light" and not r["on"]]
                for r in off:
                    lt.toggle(r)
                n = len(off)
            else:
                n = lt.all_off()
            lt.start()                                 # (what's waiting, sent: then it stops by itself, unless the
            if not (self.view == "list" and self.tab_type() == "lights"):   # Lights page is up)
                lt.stop()
            self.toast(f"{n} light{'s' if n != 1 else ''} {'on' if on else 'off'}" if n
                       else f"Your lights are {'on' if on else 'off'} already", 3)
            self.wake()
        threading.Thread(target=job, daemon=True, name="konami-lights").start()

    def konami_song(self):
        """One of your songs, then the rest in a random order (whatever's playing makes way)."""
        mi = next((k for k, t in enumerate(LIBRARY) if t["type"] == "files" and t.get("kind") == "audio"), None)
        if mi is None:
            return
        if mi not in self.items:
            self.load_tab(mi)
        songs = [it for it in self.tab_items(mi) if it.get("kind") == "audio"]
        if not songs:
            self.toast("No songs in ~/Music yet", 3)
            return
        random.shuffle(songs)
        self.play(songs, 0, show=False)
        self.queue_random = True                       # (shuffled again each time round, as at start-up)

    def konami_game(self):
        """The game you played last, from where you were."""
        games = {g["path"]: g for g in find_games()}
        g = next((games[p] for p in self.games_recent() if p in games), None)
        if g is None:
            self.toast("Play a game first: this plays the one you played last", 4)
            return
        self.game_open({"src": g["path"], "title": g["title"], "system": g["system"]})

    def konami_tick(self, now):
        """The box for a code: given up on a while after its last button (or with none). A code being put in on its
        page: done once you stop a moment (or given up on). The TV a code turned on or off: Home Assistant asked no
        more once it's done (unless the TV Remote's up)."""
        k_in = self.konami_in
        if k_in is not None:
            if self.view != "konami":
                self.konami_in = None                  # (something else on the screen now)
            elif now - k_in["at"] >= (IN_GAP if k_in["keys"] else IN_FIRST):
                self.konami_in_back()
                if k_in["keys"]:
                    self.toast("That's not one of your codes", 3)
        rec = self.konami_rec
        if rec is not None:
            if not (self.view == "list" and self.tab_type() == "konami"):
                self.konami_rec = None                 # (somewhere else now)
            elif rec["keys"] and now - rec["at"] >= REC_DONE:
                self.konami_recorded()
            elif not rec["keys"] and now - rec["at"] >= REC_GIVE_UP:
                self.konami_rec = None
                self.dirty = True
        if self.konami_pick is not None and not (self.view == "list" and self.tab_type() == "konami"):
            self.konami_pick = None
        if self.konami_ha:
            sent, until = self.konami_ha
            done = now > sent + 3 and not self.hass.busy() and not self.hass.watch
            if done or now > until:
                self.konami_ha = None
                if not (self.view == "list" and self.tab_type() == "remote"):
                    self.hass.stop()

    def konami_home(self):
        """HOME while the box for a code is up, or while one's being put in on its page: not after all (True).
        False: HOME as ever."""
        if self.konami_in is not None:
            self.konami_in_back()
            return True
        if self.konami_rec is None:
            return False
        self.konami_rec = None
        self.dirty = True
        return True

    def render_konami_in(self):
        """The box for a code: its buttons so far, or that it's waiting for them."""
        k_in = self.konami_in or {"keys": []}
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.status_bar(d)
        cw = min(W - 40, 560)
        keys = k_in["keys"]
        text = glyphs(keys) if keys else "Put in your code"
        font = F["big"] if d.textlength(text, font=F["big"]) <= cw - 40 else F["row_b"]
        rows = [("Konami code", F["small"], MUTED), (text, font, TEXT),
                ("It's done as soon as it's all in", F["small"], BODY)]
        gaps = {id(F["big"]): 44, id(F["row_b"]): 34}
        total = sum(gaps.get(id(f), 26) for _, f, _ in rows)
        x0, y0 = (W - cw) / 2, max(self.LIST_TOP, (H - self.FOOTER - total - 36) / 2)
        d.rounded_rectangle((x0 - 1, y0 - 1, x0 + cw + 1, y0 + total + 37), radius=17, fill=LINE)
        d.rounded_rectangle((x0, y0, x0 + cw, y0 + total + 36), radius=16, fill=ROW)
        y = y0 + 18
        for line, f, colour in rows:
            h = gaps.get(id(f), 26)
            d.text((W / 2, y + h / 2), self.fit(d, line, f, cw - 40), font=f, fill=colour, anchor="mm")
            y += h
        self.footer(d, [("HOME", "Never mind")], always=True)
        self.fb.show(img)

    # -- its page --------------------------------------------------------------------------------------------------
    def konami_rows(self):
        """Your codes (and what each does), then New code; or, picking what one does, what it can do."""
        p = self.konami_pick
        if p is not None:
            ki = self.tab_index("konami")
            sel = self.sels.get(ki, 0)
            names = open_names()
            rows = []
            for k, (do, label) in enumerate(DOES):
                sub = ""
                if do == "open":
                    name = names[p["open"] % len(names)]
                    sub = f"◀  {name}  ▶" if k == sel else name
                rows.append(dict(item("konami:do:" + do, label, "konamido", do, sub=sub),
                                 lit=do == "open" and k == sel))
            return rows
        rows = [item(f"konami:{k}", glyphs(c["keys"]), "konami", str(k), sub=self.konami_label(c["do"]))
                for k, c in enumerate(self.konami_codes())]
        rows.append(item("konami:new", "New code", "konaminew", "", sub="Press it, then pick what it does"))
        return rows

    def konami_refresh(self):
        ki = self.tab_index("konami")
        self.items[ki] = self.konami_rows()
        self.dirty = True

    def press_konami(self, name, repeat):
        """Putting a new code in: every button's part of it. Picking what one does: ▲▼ which, ◀▶ which app (for
        Open), A picks it, B goes back. Your codes: A tries one, X changes what it does, Y twice forgets it; A on New
        code puts a new one in. 'pass' leaves the rest to the list (▲▼, L and R, B)."""
        ki = self.tab_index("konami")
        rec = self.konami_rec
        if rec is not None:
            if not repeat and name in CODE_KEYS and len(rec["keys"]) < CODE_MOST:
                rec["keys"].append(name)
                rec["at"], rec["said"] = time.monotonic(), ""
                if len(rec["keys"]) >= CODE_MOST:
                    self.konami_recorded()
                self.dirty = True
            return None
        items = self.tab_items()
        sel = min(self.sels.get(ki, 0), max(len(items) - 1, 0))
        it = items[sel] if items else None
        p = self.konami_pick
        if p is not None:
            if name in ("up", "down"):
                self.sels[ki] = (sel + (1 if name == "down" else -1)) % len(DOES)
                self.konami_refresh()
                return None
            if name in ("left", "right"):
                if it is not None and it["src"] == "open":
                    p["open"] = (p["open"] + (1 if name == "right" else -1)) % len(open_names())
                    self.konami_refresh()
                return None
            if repeat:
                return None
            if name == "a" and it is not None:
                self.konami_picked(it["src"])
            elif name == "b":
                self.konami_pick = None
                self.sels[ki] = p["back"]
                self.konami_refresh()
            return None
        if repeat:
            return "pass"
        if name == "a" and it is not None:
            if it["kind"] == "konaminew":
                self.konami_rec = {"keys": [], "at": time.monotonic(), "said": ""}
                self.dirty = True
            elif it["kind"] == "konami":
                self.konami_run(self.konami_codes()[int(it["src"])])
            return None
        if name == "x" and it is not None and it["kind"] == "konami":
            k = int(it["src"])
            self.konami_pick_for(self.konami_codes()[k]["keys"], k)
            return None
        if name == "y" and it is not None and it["kind"] == "konami":
            k = int(it["src"])
            if self.confirm[0] == f"konami:forget:{k}" and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                codes = self.konami_codes()
                gone = codes.pop(k)
                self.konami_keep(codes)
                self.sels[ki] = min(sel, len(codes))
                self.toast(f"Forgot {glyphs(gone['keys'])}", 3)
            else:
                self.confirm = (f"konami:forget:{k}", time.monotonic() + 4)
                self.toast("Press Y again to forget that code", 4)
            self.dirty = True
            return None
        if name == "x":
            return None                                # (no Controls here)
        return "pass"

    def konami_recorded(self):
        """The new code's buttons, put in: on to what it does, or (it can't be a code) put it in again."""
        rec = self.konami_rec
        keys = list(rec["keys"])
        why = code_trouble(keys) or self.konami_clash(keys)
        if why:
            self.konami_rec = {"keys": [], "at": time.monotonic(), "said": why}
            self.dirty = True
            return
        self.konami_rec = None
        self.konami_pick_for(keys, None)

    def konami_pick_for(self, keys, edit):
        """What a code does, to pick (edit: which of yours it is, or None: a new one)."""
        ki = self.tab_index("konami")
        names = open_names()
        do = self.konami_codes()[edit]["do"] if edit is not None else "tv:on"
        opening = names.index(do[5:]) if do.startswith("open:") and do[5:] in names else \
            names.index(OPEN_FIRST) if OPEN_FIRST in names else 0
        self.konami_pick = {"keys": keys, "edit": edit, "open": opening, "back": self.sels.get(ki, 0)}
        self.sels[ki] = [d for d, _ in DOES].index("open" if do.startswith("open:") else do)
        self.konami_refresh()

    def konami_picked(self, do):
        ki = self.tab_index("konami")
        p, self.konami_pick = self.konami_pick, None
        if do == "open":
            do = "open:" + open_names()[p["open"] % len(open_names())]
        codes = self.konami_codes()
        if p["edit"] is not None and p["edit"] < len(codes):
            codes[p["edit"]]["do"] = do
            at = p["edit"]
        else:
            codes.append({"keys": p["keys"], "do": do})
            at = len(codes) - 1
        self.konami_keep(codes)
        self.sels[ki] = at
        self.toast(f"{glyphs(p['keys'])}: {self.konami_label(do)}", 4)

    def konami_hints(self, it=None):
        if self.konami_rec is not None:
            return [("HOME", "Stop")]
        if self.konami_pick is not None:
            return [("A", "Pick")] + ([("◀▶", "Which app")] if it and it.get("src") == "open" else []) \
                + [("B", "Back")]
        if it is not None and it.get("kind") == "konami":
            return [("A", "Try it"), ("X", "Change"), ("Y", "Forget"), ("B", "Back")]
        return [("A", "New code"), ("L R", "Tabs"), ("B", "Back")]

    def konami_crumb(self):
        """What the page's line at the top adds: the code what it does is being picked for."""
        p = self.konami_pick
        return "  ›  " + glyphs(p["keys"]) if p is not None else ""

    def konami_note(self):
        """The right of the page's line at the top: how a code's put in (not while picking what one does)."""
        return "" if self.konami_pick is not None else "HOME and ▶, then a code"

    def render_konami_rec(self):
        """A new code, being put in: its buttons so far, big; and what to do (or why it can't be that one)."""
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        d.text((20, self.LIST_TOP + 10), "Apps  ›  Konami code  ›  New code", font=F["small"], fill=MUTED,
               anchor="lm")
        rec = self.konami_rec
        mid = (self.LIST_TOP + 26 + H - self.FOOTER) / 2
        if rec["keys"]:
            text = glyphs(rec["keys"])
            font = F["big"] if d.textlength(text, font=F["big"]) <= W - 60 else F["row_b"]
            d.text((W / 2, mid - 16), self.fit(d, text, font, W - 40), font=font, fill=TEXT, anchor="mm")
            note = "Stop a moment when that's all of it"
        else:
            d.text((W / 2, mid - 16), "Press your code", font=F["big"], fill=TEXT, anchor="mm")
            note = f"Any buttons, {CODE_LEAST} at least"
        said = rec.get("said")
        d.text((W / 2, mid + 26), self.fit(d, said or note, F["small"], W - 40), font=F["small"],
               fill=WARN if said else MUTED, anchor="mm")
        self.footer(d, self.konami_hints())
        self.fb.show(img)
