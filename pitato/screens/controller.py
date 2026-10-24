"""Settings > Controller: setting up a controller's buttons."""
import math
import time
from evdev import ecodes as e

from ..theme import ACCENT, DONE, LINE, MUTED, PHOTO_BG, ROW, TEXT
from ..inputs import LEARN_SKIP, LEARN_STEPS, STAR, learn_steps


class ControllerScreen:
    """Settings > Controller: setting up a controller's buttons."""

    # -- Settings > Controller: setting up a controller's buttons --------------------
    def pad_summary(self):
        pads = list(self.pads.by_path.values()) if self.pads else []
        if not pads:
            return "None plugged in"
        first = pads[0].dev.name
        return first if len(pads) == 1 else f"{first} + {len(pads) - 1}"

    # -- Settings > Swap A and B: on the controller in hand ------------------------------
    def pad_in_hand(self):
        """The controller last pressed, or else the first one plugged in (None: there are none)."""
        pads = list(self.pads.by_path.values()) if self.pads else []
        used = getattr(self, "pad_used", None)
        if used is not None and any(p is used for p in pads):
            return used
        return pads[0] if pads else None

    def pad_swap_value(self):
        pad = self.pad_in_hand()
        return "No controller" if pad is None else "On" if pad.swapped else "Off"

    def pad_swap(self):
        """A and B the other way round on the controller in hand, or back as they were. (Every one of its
        model, kept for next time.)"""
        pad = self.pad_in_hand()
        if pad is None:
            self.toast("No controller plugged in", 3)
            return
        on = not pad.swapped
        self.pads.swap(pad.ident, on)
        name = pad.dev.name.strip() or "this controller"
        self.toast(f"A and B swapped on {name}" if on else f"A and B back to normal on {name}", 3)

    @property
    def learning(self):
        return bool(self.learn) and not self.learn.get("done")

    def learn_list(self):
        """This set-up's steps: on the GPi Case, its star button last."""
        return (self.learn or {}).get("steps") or LEARN_STEPS

    def start_learn(self):
        self.learn = {"step": 0, "pad": None, "keys": {}, "axes": {}, "base": {}, "armed": {},
                      "t": time.monotonic(), "quiet": 0.0, "said": "", "skipped": [], "done": None,
                      "shown": -1, "steps": learn_steps(bool(getattr(self.pads, "gpi", False)))}
        self.view = "learn"
        self.dirty = True

    def cancel_learn(self, why="Controller set-up stopped"):
        if not self.learn:
            return
        self.learn = None
        self.tab = self.tab_index("settings")
        self.view = "list"
        self.set_page = "root"
        self.load_tab(self.tab)
        if why:
            self.toast(why, 3)
        self.dirty = True

    def learn_next(self):
        L = self.learn
        L["step"] += 1
        L["t"] = time.monotonic()
        L["quiet"] = L["t"] + 0.25         # the same press can show up twice (d-pad and stick)
        L["said"] = ""
        if L["step"] >= len(self.learn_list()):
            if self.pads and L["pad"] is not None:
                self.pads.save(L["pad"].ident, L["keys"], L["axes"])
            L["done"] = time.monotonic() + 2.5
        self.dirty = True

    def learn_event(self, pad, ev):
        """A raw event from a controller while its buttons are being set up."""
        L = self.learn
        if not L or L.get("done"):
            return
        if L["pad"] is not None and pad is not L["pad"]:
            if any(down and name in ("b", "home") for name, down in pad.translate(ev)):
                self.cancel_learn()                    # another controller stops it
            return
        name = self.learn_list()[L["step"]][0]
        if ev.type == e.EV_KEY:
            if ev.value != 1:
                return
            if L["pad"] is None:                       # A on the controller to set up
                L["pad"] = pad
                for code in pad.axis_codes():
                    try:
                        L["base"][code] = pad.direction(code, pad.dev.absinfo(code).value)
                    except OSError:
                        L["base"][code] = 0
            if time.monotonic() < L["quiet"]:
                return
            if ev.code in L["keys"]:
                L["said"] = f"That one is {L['keys'][ev.code].upper()} already"
                self.dirty = True
                return
            L["keys"][ev.code] = name
            self.learn_next()
        elif ev.type == e.EV_ABS and L["pad"] is not None:
            d = pad.direction(ev.code, ev.value)
            base = L["base"].get(ev.code, 0)
            if d == base:
                L["armed"][ev.code] = True             # back at rest: ready again
                return
            if d == 0 or not L["armed"].get(ev.code, True) or time.monotonic() < L["quiet"]:
                return
            L["armed"][ev.code] = False
            used = L["axes"].get(ev.code, {}).get(d)
            if used:
                L["said"] = f"That one is {used.upper()} already"
                self.dirty = True
                return
            L["axes"].setdefault(ev.code, {})[d] = name
            self.learn_next()

    def learn_tick(self, now):
        L = self.learn
        if L.get("done"):
            if now > L["done"]:
                self.cancel_learn("")
            return
        idle = now - L["t"]
        steps = self.learn_list()
        _, _, optional = steps[L["step"]]
        if L["pad"] is None and idle > 30:
            self.cancel_learn("No controller pressed A")
        elif optional and L["pad"] is not None and idle > LEARN_SKIP:
            L["skipped"].append(steps[L["step"]][0])
            self.learn_next()
        elif not optional and idle > 60:
            self.cancel_learn()
        elif optional and L["pad"] is not None and int(idle) != L["shown"]:
            L["shown"] = int(idle)                     # the countdown
            self.dirty = True

    def learn_status(self):
        L = self.learn
        if not L:
            return None
        steps = self.learn_list()
        if L.get("done") or L["step"] >= len(steps):
            return {"done": True, "text": "Saved", "n": len(steps), "of": len(steps)}
        what = steps[L["step"]][1]
        text = (f"Press {what} on the controller to set up" if L["pad"] is None else f"Press {what}")
        return {"done": False, "text": text, "n": L["step"] + 1, "of": len(steps),
                "pad": L["pad"].dev.name if L["pad"] is not None else None, "said": L["said"]}

    def render_learn(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        L = self.learn or {}
        pad = L.get("pad")
        self.title_row(d, "Set up a controller", pad.dev.name[:28] if pad is not None else None)
        done = set(L.get("keys", {}).values()) | {n for dirs in L.get("axes", {}).values() for n in dirs.values()}
        skipped = set(L.get("skipped", []))
        steps = self.learn_list()
        now_name = None if L.get("done") else steps[L.get("step", 0)][0]

        def fill(name):
            if name == now_name:
                return ACCENT
            if name in done:
                return DONE
            return ROW if name in skipped else LINE

        # a controller: shoulders, body, d-pad, face buttons, SELECT / START / HOME
        cx, top = W // 2, 104
        d.rounded_rectangle((cx - 150, top - 18, cx - 70, top + 2), radius=8, fill=fill("l"))
        d.rounded_rectangle((cx + 70, top - 18, cx + 150, top + 2), radius=8, fill=fill("r"))
        d.rounded_rectangle((cx - 190, top, cx + 190, top + 170), radius=70, fill=PHOTO_BG,
                            outline=LINE, width=2)
        px, py = cx - 105, top + 85
        for name, box in (("up", (px - 13, py - 45, px + 13, py - 13)), ("down", (px - 13, py + 13, px + 13, py + 45)),
                          ("left", (px - 45, py - 13, px - 13, py + 13)), ("right", (px + 13, py - 13, px + 45, py + 13))):
            d.rounded_rectangle(box, radius=5, fill=fill(name))
        d.rectangle((px - 13, py - 13, px + 13, py + 13), fill=LINE)
        fx, fy = cx + 105, top + 85
        for name, (bx, by) in (("x", (fx, fy - 32)), ("a", (fx + 32, fy)), ("b", (fx, fy + 32)), ("y", (fx - 32, fy))):
            d.ellipse((bx - 16, by - 16, bx + 16, by + 16), fill=fill(name))
            d.text((bx, by), name.upper(), font=F["key"], fill=PHOTO_BG if fill(name) in (ACCENT, DONE) else TEXT,
                   anchor="mm")
        for name, box in (("select", (cx - 42, top + 112, cx - 6, top + 124)),
                          ("start", (cx + 6, top + 112, cx + 42, top + 124))):
            d.rounded_rectangle(box, radius=6, fill=fill(name))
        d.ellipse((cx - 13, top + 64, cx + 13, top + 90), fill=fill("home"))
        if any(s[0] == STAR for s in steps):          # the GPi Case's star, above HOME
            sx, sy = cx, top + 38
            d.polygon([(sx + (15 if k % 2 == 0 else 6) * math.sin(k * math.pi / 5),
                        sy - (15 if k % 2 == 0 else 6) * math.cos(k * math.pi / 5)) for k in range(10)],
                      fill=fill(STAR))

        if L.get("done"):
            big, small = "All set", "These buttons are saved for this controller"
            if STAR in skipped:
                small = "Saved. Nothing came through from the star"
        else:
            st = self.learn_status() or {}
            big = st.get("text", "")
            _, _, optional = steps[L.get("step", 0)]
            if L.get("said"):
                small = L["said"]
            elif pad is None:
                small = "It stops by itself if you wait"
            elif optional:
                small = f"Not on yours? It's skipped in {max(0, LEARN_SKIP - int(time.monotonic() - L['t']))} s"
            else:
                small = "B or HOME on another controller stops"
        d.text((W / 2, 318), self.fit(d, big, F["big"], W - 40), font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, 352), self.fit(d, small, F["small"], W - 40), font=F["small"], fill=MUTED, anchor="mm")
        n = min(L.get("step", 0) + 1, len(steps))
        self.footer(d, [], right="" if L.get("done") else f"{n} of {len(steps)}")
        self.fb.show(img)
