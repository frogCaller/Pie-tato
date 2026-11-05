"""Apps' Fortune Cookie (pitato/fortune.py draws it): its buttons. A shows a new fortune; the d-pad picks its colours (up
and down the words', left and right the background's), L and R its font, Y an effect (each kept, as START's card keeps
them, and said); X reads it out loud in your Bot's voice (X again stops)."""

FORTUNE_KEYS = {"up": "ink", "down": "ink", "left": "paper", "right": "paper", "l": "font", "r": "font",
                "y": "effect"}


class FortuneScreen:
    """The Fortune Cookie: its buttons, and whether it's being read out loud."""

    def fortune_shown(self):
        """The Fortune Cookie is on the screen (its START card shut)."""
        return bool(self.active and self.view == "list" and self.tab_type() == "sim"
                    and self.sim_game().key == "fortune" and self.sim_opts is None)

    def press_fortune(self, s, name, repeat):
        """A: a new fortune (fading up); up and down the words' colour, left and right the
        background's, L and R the font, Y the effect (each kept, as START's card keeps it, and said); X reads it out
        loud (X again stops). B: back to the list ("pass"). False: as for any of Apps' (SELECT, START)."""
        if name == "b":
            return "pass"
        if repeat:
            return None if name in FORTUNE_KEYS or name in ("a", "x") else False
        if name == "a":
            if getattr(self, "fortune_aloud", False) and self.voice.speaking:
                self.voice.stop()                      # (the last one's fortune: not read on over the new one)
            self.fortune_aloud = False
            s.new()
            self.sim_next = 0.0                        # (it fades up now, frame by frame)
        elif name in FORTUNE_KEYS:
            key = FORTUNE_KEYS[name]
            label, ways = next((label, list(ways)) for k, label, ways, _ in s.options if k == key)
            cur = s.values.get(key)
            new = ways[((ways.index(cur) if cur in ways else 0) + (-1 if name in ("up", "left", "l") else 1))
                       % len(ways)]
            self.set_setting(f"sim_fortune_{key}", new)
            s.configure({key: new})
            self.toast(f"{label}: {new}", 2)
        elif name == "x":
            self.fortune_read(s)
        else:
            return False
        self.dirty = True
        return None

    def fortune_read(self, s):
        """X: the fortune and its lucky numbers read out loud in your Bot's voice (Settings > Bot), or that stopped."""
        if getattr(self, "fortune_aloud", False) and self.voice.speaking:
            self.voice.stop()
            self.fortune_aloud = False
            return
        ok, why = self.say_aloud(s.said())
        if ok:
            self.fortune_aloud = True
        else:
            self.toast(why, 3)

    def fortune_tick(self, now):
        """While it's up: whether it's being read out loud, as its X says."""
        if not self.fortune_shown():
            return
        s = self.sims.get("fortune")
        aloud = getattr(self, "fortune_aloud", False) and bool(self.voice.speaking)
        self.fortune_aloud = aloud
        if s is not None and s.reading != aloud:
            s.reading = aloud
            self.dirty = True
