"""Home > Control another Pietato (pitato/pilot.py has how): this one's buttons working another of yours, as a
controller plugged into it would. Pick which one (A): from then on every button goes there instead (held ones too,
so its games play as they should), this screen says which one it's controlling and that it's in touch, and HOME held
on its own for two seconds lets go of it. And the other side: another of yours asking to control this one (its web
page asks the main loop, app.py, which has the buttons), said on the screen as it begins and ends."""
import time
import urllib.parse

from ..inputs import BUTTONS, MEDIA_TOGGLE
from ..pilot import PILOT_LET_GO, PilotOut
from ..power import wifi_power_save
from ..system import wifi_dev
from ..theme import ACCENT, BG, BODY, DONE, LINE, MUTED, ROW, TEXT, WARN
from ..util import item

PILOT_LOOK = 3.0      # seconds between looks at which of your other Pietatos are on, while you pick one
PILOT_DRAW = 0.1      # seconds between drawings of what's held, at most (drawing never holds up the next press)


class PilotScreen:
    """Home > Control another Pietato; and another of yours controlling this one."""

    # -- this one controlling another -----------------------------------------------------------------------------
    def pilot_on(self):
        """This one's buttons are another's now."""
        return getattr(self, "pilot_out", None) is not None

    def pilot_page(self):
        """Home > Control another Pietato is on the screen."""
        return bool(self.active and self.view == "list" and self.tab_type() == "pilot")

    def pilot_rows(self):
        """Your other Pietatos that are on, to pick from (Settings > Share with other Pietatos on, here and there)."""
        return [item("pilot:" + url, name, "pilot", url, sub=urllib.parse.urlsplit(url).hostname or "")
                for url, name in self.saves_peers()]

    def pilot_empty(self):
        """(big, small): none to pick."""
        if self.setting("share") == "Off":
            return "Sharing is off", "Turn on Settings > Share with other Pietatos, here and on the other one"
        return "None of your other Pietatos is on", "It needs Settings > Share with other Pietatos on too"

    def pilot_hints(self):
        if self.pilot_on():
            return [("HOME", "Hold it to let go")]
        return [("A", "Control it"), ("B", "Back")] if self.tab_items() else [("B", "Back")]

    def pilot_has(self):
        """The buttons this one's controllers have (an N64 game there wants to know whether there's an L2, say)."""
        pads = [p for p in (self.pads.by_path.values() if self.pads else []) if getattr(p, "kind", "") != "pilot"]
        return sorted({b for p in pads for b in BUTTONS if p.has_button(b)} or set(BUTTONS))

    def pilot_start(self, it, password=None):
        """A on one of them: this one's buttons are its, once it's said yes. With its web page's password, if it's
        been given one (kept from last time, or just typed)."""
        if self.pilot_on():
            return
        url = it["src"]
        if password is None:
            password = self.state["pilot"].get(url)
        self.pilot_out = PilotOut(url, it["title"], self.pilot_has(), changed=self.pilot_changed, password=password)
        self.pilot_shown = None
        print(f"pilot: controlling {it['title']} ({url})", flush=True)
        self.dirty = True

    def pilot_password(self, out):
        """Its web page has a password (Settings on its web page): typed here, once (kept, for next time). The one
        kept, or typed, wasn't it: said, and asked for again."""
        it = {"src": out.url, "title": out.name}
        if out.password:
            self.toast("That isn't its password", 3)
            if self.state["pilot"].pop(out.url, None) is not None:
                self.save_state()
        self.open_keyboard(f"{out.name}'s web page password", "", lambda text: self.pilot_start(it, password=text),
                           strip=False)

    def pilot_changed(self):
        """(Its thread.) How it's going has changed: drawn again, now."""
        self.dirty = True
        self.wake()

    def pilot_press(self, name, down):
        """(The main loop: a controller or a keyboard here.) A button, down or up, for the other one."""
        out = getattr(self, "pilot_out", None)
        if out is not None:
            out.press(name, down)                      # (lit on the screen at its next tick: pilot_tick)

    def pilot_let_go(self):
        """A controller here unplugged: what it held, let go of there too."""
        out = getattr(self, "pilot_out", None)
        if out is not None:
            out.let_go()
            self.dirty = True

    def pilot_stop(self, words=None):
        """This one's buttons its own again (the other one's told so), and said."""
        out = getattr(self, "pilot_out", None)
        if out is None:
            return
        self.pilot_out = None
        out.stop()
        print(f"pilot: let go of {out.name}", flush=True)
        self.stir()
        self.toast(words or f"Stopped controlling {out.name}", 3)
        if self.pilot_page():
            self.pilot_look(time.monotonic())
        self.dirty = True

    def pilot_look(self, now):
        """Which of your other Pietatos are on: the list as it is now (the one picked kept picked)."""
        self.pilot_looked = now
        rows = self.pilot_rows()
        was = self.items.get(self.tab) or []
        if [(r["src"], r["title"]) for r in rows] == [(r["src"], r["title"]) for r in was]:
            return
        sel = self.sels.get(self.tab, 0)
        picked = was[sel]["src"] if sel < len(was) else None
        self.items[self.tab] = rows
        self.sels[self.tab] = next((k for k, r in enumerate(rows) if r["src"] == picked),
                                   min(sel, max(len(rows) - 1, 0)))
        self.dirty = True

    def press_pilot(self, name, repeat):
        """While it's controlling another one, only the web page's remote (or a touch) gets here: B lets go of it.
        Otherwise the list as any is ("pass")."""
        if not self.pilot_on():
            return "pass"
        if name == "b" and not repeat:
            self.pilot_stop()
        return None

    def pilot_tick(self, now):
        """Picking: the list kept up to date. Controlling: let go of it as HOME's been held long enough, as something
        else is on the screen here now, or as it won't (said)."""
        out = getattr(self, "pilot_out", None)
        if out is None:
            if self.pilot_page() and now - getattr(self, "pilot_looked", 0.0) >= PILOT_LOOK:
                self.pilot_look(now)
            return
        if not self.pilot_page():
            self.pilot_stop()
            return
        state = out.status(now)
        if state == "failed":
            self.pilot_out = None
            out.stop()
            if out.why == "password":                  # (its web page has a password: typed here)
                self.pilot_password(out)
            else:
                self.toast(out.why or f"{out.name} not responding", 4)
                self.pilot_look(now)
            self.dirty = True
            return
        if out.password and state == "on" and self.state["pilot"].get(out.url) != out.password:
            self.state["pilot"][out.url] = out.password   # (its password: it let this one in, so kept for next time)
            self.save_state()
        held = out.home_held(now)
        if held >= PILOT_LET_GO:
            self.pilot_stop()
            return
        if held or state != getattr(self, "pilot_shown", None):
            self.dirty = True                          # (HOME's ring filling up; or in touch, or not)
        elif (out.held_now() != getattr(self, "pilot_lit", None)
              and now - getattr(self, "pilot_drawn", 0.0) >= PILOT_DRAW):
            self.dirty = True                          # (what's held, lit: as often as PILOT_DRAW)

    def pilot_tick_limit(self):
        """While it's controlling another: often enough for HOME's ring as it's held, and what's held lit."""
        out = getattr(self, "pilot_out", None)
        return 0.05 if out is not None and out.home_at is not None else PILOT_DRAW

    def pilot_art(self, d, x, mid, it):
        """A row's dot: the other Pietato's colour (or a plain one, for one that doesn't say)."""
        if not self.peer_dot(d, x + 6, mid, it["src"], r=6):
            d.ellipse((x, mid - 6, x + 12, mid + 6), outline=MUTED, width=2)
        return x + 26

    def render_pilot(self):
        """Controlling another one: its name, with its colour's dot; in touch or not; what's held down, lit on a
        controller; and HOME's ring filling up as it's held."""
        out = self.pilot_out
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        now = time.monotonic()
        state = out.status(now)
        self.pilot_shown, self.pilot_lit, self.pilot_drawn = state, out.held_now(), now
        d.text((20, self.LIST_TOP + 10), "Home  ›  Control another Pietato", font=F["small"], fill=MUTED, anchor="lm")
        top, bottom = self.LIST_TOP + 28, H - self.FOOTER - 6
        y = top + max(10, (bottom - top - 330) // 2)
        d.text((W / 2, y + 10), "Controlling", font=F["small"], fill=MUTED, anchor="mm")
        name = self.fit(d, out.name, F["big"], W - 80)
        tw = d.textlength(name, font=F["big"])
        dot = self.peer_colour(out.url) is not None
        d.text((W / 2 + (9 if dot else 0), y + 42), name, font=F["big"], fill=TEXT, anchor="mm")
        if dot:
            self.peer_dot(d, W / 2 - tw / 2 - 5, y + 42, out.url, r=6)
        words, colour = {"on": ("In touch", DONE), "quiet": ("Not responding: is it on, and on your WiFi?", WARN),
                         "asking": ("Getting in touch…" if not out.was_on else "Getting in touch again…", ACCENT)
                         }.get(state, ("", MUTED))
        words = self.fit(d, words, F["small"], W - 100)
        pw = d.textlength(words, font=F["small"]) + 38
        py = y + 80
        d.rounded_rectangle((W / 2 - pw / 2, py - 14, W / 2 + pw / 2, py + 14), radius=14, fill=ROW)
        d.ellipse((W / 2 - pw / 2 + 12, py - 4, W / 2 - pw / 2 + 20, py + 4), fill=colour)
        d.text((W / 2 - pw / 2 + 28, py), words, font=F["small"], fill=TEXT if state == "on" else colour,
               anchor="lm")
        self.pilot_pad(d, W / 2, py + 40, self.pilot_lit, set(out.has))
        held = out.home_held(now)
        hints = [("HOME", "Keep holding it to let go", True)] if held else self.pilot_hints()
        self.footer(d, hints, always=True)
        if held:                                       # (its ring, filling up beside it)
            x = 20 + self.key_w(d, "HOME") + 7 + d.textlength(hints[0][1], font=F["small"]) + 22
            self.pilot_ring(d, x, H - type(self).FOOTER // 2, min(held / PILOT_LET_GO, 1.0))
        self.fb.show(img)

    def pilot_ring(self, d, x, cy, frac):
        """HOME held: a ring filling up, till it lets go of the other one."""
        r = 9
        d.ellipse((x - r, cy - r, x + r, cy + r), outline=LINE, width=3)
        if frac > 0:
            d.arc((x - r, cy - r, x + r, cy + r), -90, -90 + 360 * frac, fill=ACCENT, width=3)

    def pilot_pad(self, d, cx, top, held, has):
        """A controller, its buttons held down lit."""
        F = self.fonts

        def lit(name):
            return name in held

        def key(box, name, label="", radius=6, font="badge"):
            on = lit(name)
            d.rounded_rectangle(box, radius=radius, fill=ACCENT if on else ROW, outline=None if on else LINE,
                                width=1)
            if label:
                d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), label, font=F[font], fill=BG if on else BODY,
                       anchor="mm")

        w, h = 330, 150
        x0, y0 = cx - w / 2, top + 16
        for name, x, label in (("l", x0 + 22, "L"), ("r", x0 + w - 92, "R")):
            key((x, top, x + 70, top + 24), name, label, radius=10)
        if "l2" in has or "r2" in has:
            for name, x, label in (("l2", x0 + 98, "L2"), ("r2", x0 + w - 142, "R2")):
                key((x, top + 2, x + 44, top + 22), name, label, radius=9)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=44, fill=BG, outline=LINE, width=2)
        dx, dy, s = x0 + 70, y0 + h / 2, 21                  # the d-pad
        for name, (ax, ay) in (("up", (0, -1)), ("down", (0, 1)), ("left", (-1, 0)), ("right", (1, 0))):
            bx, by = dx + ax * s, dy + ay * s
            key((bx - s / 2, by - s / 2, bx + s / 2, by + s / 2), name, radius=4)
        d.rectangle((dx - s / 2, dy - s / 2, dx + s / 2, dy + s / 2), fill=ROW)
        fx, fy, r = x0 + w - 70, y0 + h / 2, 13              # A B X Y, as the GPi Case has them
        for name, (ax, ay) in (("x", (0, -1)), ("a", (1, 0)), ("b", (0, 1)), ("y", (-1, 0))):
            bx, by = fx + ax * 25, fy + ay * 25
            key((bx - r, by - r, bx + r, by + r), name, name.upper(), radius=r, font="key")
        mx = cx
        for name, x, label in (("select", mx - 52, "SELECT"), ("start", mx + 8, "START")):
            key((x, y0 + h - 46, x + 44, y0 + h - 30), name, "", radius=8)
            d.text((x + 22, y0 + h - 18), label, font=F["badge"], fill=ACCENT if lit(name) else MUTED, anchor="mm")
        key((mx - 13, y0 + 26, mx + 13, y0 + 52), MEDIA_TOGGLE, "", radius=13)
        d.text((mx, y0 + 64), "HOME", font=F["badge"], fill=ACCENT if lit(MEDIA_TOGGLE) else MUTED, anchor="mm")

    # -- another one controlling this one --------------------------------------------------------------------------
    def pilot_may(self, cmd):
        """POST /api/pilot (another of yours, through webui.py): whether it may (Settings > Share with other Pietatos
        on here, and it's one of yours): {"addr", "name"}, or why not."""
        if self.setting("share") == "Off":
            return {"ok": False, "error": "Its Settings > Share with other Pietatos is off"}
        addr = str(cmd.get("from") or "")
        peers = self.saves_peers(addr)
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        if cmd.get("kind") not in ("ask", "end"):
            return {"ok": False, "error": "What's that?"}
        return {"addr": addr, "name": peers[0][1]}

    def pilot_began(self, name, first):
        """Another of yours controlling this one now: said, the screen woken (and the WiFi kept quick while it is: no
        power saving, which would hold its buttons up)."""
        if first:
            dev = wifi_dev()
            self.pilot_wifi = dev if wifi_power_save(dev, False) else None   # (put back as it was, after)
        self.stir()
        if self.active and not self.proc_owns_screen():
            self.toast(f"{name} is controlling this Pietato", 4)
        print(f"pilot: {name} is controlling this one", flush=True)
        self.dirty = True

    def pilot_ended(self, name, why, last):
        """It's let go of this one (why: "bye"), or gone quiet ("gone"); or asked again ("again": not said)."""
        if last and getattr(self, "pilot_wifi", None):
            wifi_power_save(self.pilot_wifi, True)
            self.pilot_wifi = None
        if why in ("bye", "gone"):
            print(f"pilot: {name} " + ("let go of this one" if why == "bye" else "went quiet"), flush=True)
            if self.active and not self.proc_owns_screen():
                self.toast(f"{name} stopped controlling this Pietato" if why == "bye"
                           else f"Lost touch with {name}", 3)
        self.dirty = True
