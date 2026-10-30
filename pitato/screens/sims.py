"""The Simulator (and Games) tab: a world in a box, its numbers beside it, and START's options."""
import math
import time

from ..theme import ACCENT, BG, BODY, co_mix, LINE, MUTED, ROW, TEXT
from ..library import LIBRARY
from ..sims import (
    ForestFire, Life, RockPaperScissors, RPS_COLOUR, RPS_TEAMS, SIM_BOX, sim_clock,
    SIM_FLOOR, SIM_FULL, SIM_IN, SIM_PANEL)
from ..mandelbrot import Mandelbrot
from ..snake import Snake


SIMS = {s.key: s for s in (RockPaperScissors, Life, ForestFire, Mandelbrot, Snake)}


class SimScreen:
    """The Simulator (and Games) tab: a world in a box, its numbers beside it, and START's options."""

    # -- the Simulator tab: little worlds to watch ------------------------------------------------------
    def on_sim_page(self):
        return self.active and self.view == "list" and self.tab_type() == "sim"

    @staticmethod
    def sim_rows(kind):
        """START's card: the sim's options, then Full screen."""
        return tuple(kind.options) + (SIM_FULL,)

    def sim_value(self, kind, key):
        """One of a sim's options as you left it (kept with your settings), or its usual one."""
        for k, _, ways, default in self.sim_rows(kind):
            if k == key:
                v = self.setting("sim_full" if k == "full" else f"sim_{kind.key}_{k}")
                return v if v in ways and not isinstance(v, bool) else default
        return None

    def sim_full(self):
        """Full screen: just the sim, on the whole screen (for every sim)."""
        return self.setting("sim_full") == "On"

    def sim_layout(self):
        """(the box, its numbers beside it, what changes from one frame to the next) on this screen: on a
        bigger one than the GPi Case's, the box is as much wider and taller, the numbers still at its right."""
        dx = (self.fb.w if self.fb else 640) - 640
        dy = (self.fb.h if self.fb else 480) - 480
        box = (SIM_BOX[0], SIM_BOX[1], SIM_BOX[2] + dx, SIM_BOX[3] + dy)
        panel = (SIM_PANEL[0] + dx, SIM_PANEL[1], SIM_PANEL[2] + dx, SIM_PANEL[3] + dy)
        return box, panel, (box[0], box[1], panel[2], panel[3])

    def sim_box(self):
        """The box on the screen, and how far in from its wall the sim keeps: beside its numbers, or
        the whole screen."""
        if self.sim_full():
            return ((0, 0, self.fb.w, self.fb.h) if self.fb else (0, 0, 640, 480)), 0
        return self.sim_layout()[0], SIM_IN

    def sim_game(self):
        """The sim on this page: made the first time it's opened, with your options, and kept while
        you're elsewhere; its box the size it is now."""
        kind = SIMS[LIBRARY[self.tab]["sim"]]
        (x0, y0, x1, y1), inset = self.sim_box()
        w, h = x1 - x0 - 2 * inset, y1 - y0 - 2 * inset
        s = self.sims.get(kind.key)
        if s is None:
            s = self.sims[kind.key] = kind(w, h, values={k: self.sim_value(kind, k) for k, _, _, _ in kind.options})
            if kind is Snake:
                s.best = self.snake_best()
            calls = self.setting("sim_rps_calls")
            if (kind is RockPaperScissors and isinstance(calls, list) and len(calls) == 2
                    and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in calls)):
                s.calls = [min(calls), calls[1]]
        elif (s.w, s.h) != (w, h):
            s.refit(w, h)
        return s

    def sim_set_full(self, on):
        """SELECT: full screen (just the sim), or back. Kept for next time, for every sim."""
        self.set_setting("sim_full", "On" if on else "Off")
        if self.tab_type() == "sim":
            self.sim_game()                            # (the box grows or shrinks)
        if on:
            self.toast("Full screen. SELECT again to leave it", 3)

    def sim_close(self):
        """START's card closes: the sim starts again if an option it needs that for has changed."""
        if self.sim_opts is None:
            return
        self.sim_opts = None
        s = self.sims.get(LIBRARY[self.tab].get("sim")) if self.tab_type() == "sim" else None
        if s is not None and s.needs_restart():
            s.restart()
        self.dirty = True

    def press_sim(self, name, repeat):
        """A sim: A pauses (Rock Paper Scissors: starts, pauses, plays again), X pokes it, Y starts it
        again, SELECT is full screen, START has its options, B goes back to the list. In Rock Paper
        Scissors, left and right pick a winner (until the first capture)."""
        s = self.sim_game()
        if self.sim_opts is not None:
            return self.press_sim_opts(s, name, repeat)
        if name in ("b", "l", "r"):
            return "pass"
        if s.key == "mandel" and name in Mandelbrot.MOVES and self.press_mandel(s, name, repeat):
            self.dirty = True
            return None
        if s.key == "snake" and name in ("up", "down", "left", "right", "a", "x", "y", "start"):
            if not repeat:
                self.press_snake(s, name)
            self.dirty = True
            return None
        if repeat:
            return None
        full, rps = self.sim_full(), s.key == "rps"
        if name in ("left", "right") and rps:
            if s.is_open():
                s.choose(1 if name == "right" else -1)
                if full:                               # (nothing else on the screen says so)
                    self.toast("No pick" if s.pick is None else f"Your pick: {RPS_TEAMS[s.pick]}", 2)
            else:
                self.toast("Picks are locked until the next round", 2)
        elif name == "a":
            if rps and s.phase == "ready":
                s.start()
            elif rps and s.phase == "over":
                s.new_round()
            else:
                s.paused = not s.paused
                if full and s.paused:
                    self.toast("Paused", 2)
        elif name == "x" and s.poke_label and not (rps and s.phase == "ready"):
            s.poke()
        elif name == "y":
            s.restart()
            s.paused = False
        elif name == "select":
            self.sim_set_full(not full)
        elif name == "start":
            self.sim_opts = 0
        else:
            return None
        self.dirty = True
        return None

    def press_mandel(self, s, name, repeat):
        """The Mandelbrot Set: exploring, the d-pad moves round it and A zooms in, Y out, for as long as
        they're held; on the tour, the d-pad starts exploring from where it is. True if it took the press."""
        if s.phase != "explore":
            if name not in ("up", "down", "left", "right") or repeat:
                return False
            self.set_setting("sim_mandel_mode", "Explore")
            s.configure({"mode": "Explore"})
            self.toast("Exploring. START has the tour", 3)
        if repeat:                                     # (held down on the web page)
            s.nudge(name)
            return True
        if name == "a" and s.ex and s.ex["L"] >= s.DEEPEST:
            self.toast("As deep as it can go", 2)
        elif name == "y" and s.ex and s.ex["L"] <= 0:
            self.toast("That's the whole set", 2)
        s.hold(name)
        return True

    def on_mandel_page(self):
        """The Mandelbrot Set is on screen (its options closed)."""
        return self.on_sim_page() and self.sim_opts is None and LIBRARY[self.tab].get("sim") == "mandel"

    def takes_repeats(self, name):
        """A press held down on the web page goes on and on here (beyond the usual arrows in lists): Chromium's
        pointer and its scrolling too."""
        if self.chromium_shown():
            return name in ("up", "down", "left", "right", "l", "r")
        s = self.sims.get("mandel")
        return (self.on_mandel_page() and s is not None and s.phase == "explore" and name in Mandelbrot.MOVES)

    def press_sim_opts(self, s, name, repeat):
        """START's card: up and down pick a row, left and right change it, A or B closes it."""
        rows = self.sim_rows(type(s))
        if name in ("l", "r"):
            return "pass"                                  # (switching apps closes it)
        if name in ("up", "down"):
            self.sim_opts = (self.sim_opts + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and not repeat:
            key, _, ways, _ = rows[self.sim_opts]
            ways = list(ways)
            new = ways[(ways.index(self.sim_value(type(s), key)) + (1 if name == "right" else -1)) % len(ways)]
            if key == "full":
                self.set_setting("sim_full", new)
                self.sim_game()                            # (the box grows or shrinks)
            else:
                self.set_setting(f"sim_{s.key}_{key}", new)
                s.configure({key: new})
        elif name in ("a", "b", "start") and not repeat:
            self.sim_close()
        else:
            return None
        self.dirty = True
        return None

    def sim_hints(self, s):
        if self.sim_opts is not None:
            return [("▲▼", "Choose"), ("◀▶", "Change"), ("B", "Done")]
        own = s.hints()
        if own is not None:
            return own
        if s.key == "rps":
            first = (("A", "Start") if s.phase == "ready" else ("A", "Play again") if s.phase == "over"
                     else ("A", "Play") if s.paused else ("A", "Pause"))
            hints = [first] + ([("X", "Shake")] if s.phase != "ready" else []) + [("Y", "New round")]
            if s.is_open():
                hints.append(("◀▶", "Pick"))
            return hints + [("START", "Options")]
        hints = [("A", "Play" if s.paused else "Pause")]
        if s.poke_label:
            hints.append(("X", s.poke_label))
        return hints + [("Y", "New start"), ("START", "Options")]

    def sim_tile(self, text, font, fill, bg):
        """A picture of some words on a plain background, kept: a sim's words and numbers come back again
        and again, and drawing text is slow on a Pi Zero."""
        tiles = self.sim_tiles
        key = (text, font, fill, bg)
        tile = tiles.get(key)
        if tile is None:
            from PIL import Image, ImageDraw
            f = self.fonts[font]
            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            w, h = int(math.ceil(probe.textlength(text, font=f))) + 2, int(getattr(f, "size", 12) * 1.6)
            tile = Image.new("RGB", (max(w, 3), h), bg)
            ImageDraw.Draw(tile).text((1, h / 2), text, font=f, fill=fill, anchor="lm")
            if len(tiles) > 600:
                tiles.clear()
            tiles[key] = tile
        return tile

    def sim_text(self, img, xy, text, font, fill, bg, anchor="l"):
        """Words at xy (their middle, at the height), from the left, the right or the middle: kept
        pictures of them. Returns how wide they are."""
        tile = self.sim_tile(text, font, fill, bg)
        x, y = xy
        w = tile.width - 2
        x = x - w if anchor == "r" else x - w / 2 if anchor == "m" else x
        img.paste(tile, (int(round(x)) - 1, int(round(y)) - tile.height // 2))
        return w

    def sim_digits(self, img, xy, s):
        """A number, right-aligned at xy: each figure's picture is kept (the font has even widths)."""
        x, y = xy
        for ch in reversed(s):
            x -= self.sim_text(img, (x, y), ch, "mono_s", TEXT, BG, anchor="r")

    @staticmethod
    def sim_chart(d, history, colours, top, box):
        """A run so far: each count, over time."""
        if len(history) < 2:
            return
        x0, y0, x1, y1 = box
        top = max(1, top)
        t_max = max(10.0, history[-1][0])
        for k, colour in enumerate(colours):
            pts = [(x0 + 4 + t / t_max * (x1 - x0 - 8), y1 - 5 - min(c[k], top) / top * (y1 - y0 - 10))
                   for t, c in history]
            d.line(pts, fill=colour, width=2)
            x, y = pts[-1]
            d.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5), fill=colour)

    def rps_scores(self, s, sig):
        """Beside Rock Paper Scissors' box: each team's pieces, the time and captures, a chart of the
        round, your pick. What changes only now and then (the names, your pick) is kept, drawn again
        when sig changes."""
        from PIL import Image, ImageDraw
        _, panel, _ = self.sim_layout()
        W, H = panel[2] - panel[0], panel[3] - panel[1]
        chart = (0, 186, W - 1, 252)
        if self.sim_still[0] != sig:
            img = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(img)
            for k, name in enumerate(RPS_TEAMS):
                y, c, mine = k * 42, RPS_COLOUR[k], s.pick == k
                d.rounded_rectangle((0, y + 4, 10, y + 14), radius=3, fill=c)
                self.sim_text(img, (18, y + 9), name, "small_b" if mine else "small", c if mine else BODY, BG)
            for k, label in enumerate(("Time", "Captures")):
                self.sim_text(img, (0, 140 + k * 24), label, "label", MUTED, BG)
            y = 272
            self.sim_text(img, (0, y), "Your pick", "label", MUTED, BG)
            if s.is_open():
                state, fill = "Open", MUTED
            else:
                state, fill = ("Locked in", TEXT) if s.pick is not None else ("Closed", MUTED)
            self.sim_text(img, (W, y), state, "status", fill, BG, anchor="r")
            if s.pick is not None:
                self.sim_text(img, (0, y + 24), RPS_TEAMS[s.pick], "small_b", RPS_COLOUR[s.pick], BG)
            else:
                self.sim_text(img, (0, y + 24), "◀ ▶ to pick" if s.is_open() else "None this round",
                              "small", BODY, BG)
            hits, made = s.calls
            d.text((0, y + 48), f"Called {hits} of {made}" if made else "No calls yet",
                   font=self.fonts["status"], fill=MUTED, anchor="lm")
            self.sim_still = (sig, img)
        img = self.sim_still[1].copy()
        d = ImageDraw.Draw(img)
        counts, total = s.counts(), max(1, len(s.t))
        for k in range(3):
            y = k * 42
            self.sim_digits(img, (W, y + 9), str(counts[k]))
            d.rounded_rectangle((0, y + 22, W - 1, y + 28), radius=3, fill=ROW)
            if counts[k]:
                d.rounded_rectangle((0, y + 22, max(6, round((W - 1) * counts[k] / total)), y + 28), radius=3,
                                    fill=RPS_COLOUR[k])
        self.sim_digits(img, (W, 140), sim_clock(s.clock))
        self.sim_digits(img, (W, 164), str(s.captures))
        d.rounded_rectangle(chart, radius=6, fill=SIM_FLOOR, outline=LINE)
        self.sim_chart(d, s.history, RPS_COLOUR, total, chart)
        return img

    def sim_numbers(self, s, sig):
        """Beside a sim's box: its name, what it is, its numbers and (for some) a chart. The words that
        don't change are kept, drawn again when sig changes."""
        from PIL import Image, ImageDraw
        world, panel, _ = self.sim_layout()
        W, H = panel[2] - panel[0], panel[3] - panel[1]
        stats = s.stats()
        top = 10
        if self.sim_still[0] != sig:
            img = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(img)
            self.sim_text(img, (0, top + 2), LIBRARY[self.tab].get("title") or LIBRARY[self.tab]["name"], "head",
                          TEXT, BG)
            y = top + 28
            for line in self.wrap(d, s.blurb, self.fonts["status"], W, lines=6):
                self.sim_text(img, (0, y), line, "status", MUTED, BG)
                y += 17
            for k, (label, _) in enumerate(stats):
                self.sim_text(img, (0, 154 + k * 24), label, "label", MUTED, BG)
            self.sim_still = (sig, img)
        img = self.sim_still[1].copy()
        for k, (_, value) in enumerate(stats):
            y = 154 + k * 24
            if value.isdigit():
                self.sim_digits(img, (W, y), value)
            else:
                self.sim_text(img, (W, y), value, "small", TEXT, BG, anchor="r")
        chart = s.chart()
        if chart:
            d = ImageDraw.Draw(img)
            box = (0, 154 + len(stats) * 24, W - 1, 154 + len(stats) * 24 + 66)
            d.rounded_rectangle(box, radius=6, fill=SIM_FLOOR, outline=LINE)
            self.sim_chart(d, *chart, box)
            return img
        pw, ph = W - 10, round((W - 10) * (world[3] - world[1]) / (world[2] - world[0]))
        got = s.inset(pw, ph)
        if got:                                        # (the Mandelbrot Set: where the dive is)
            pic, words = got
            x, y = 5, 154 + len(stats) * 24 - 4
            if self.sim_mask is None or self.sim_mask.size != (pw, ph):     # (its round corners)
                self.sim_mask = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(self.sim_mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=6, fill=255)
            img.paste(pic, (x, y), self.sim_mask)
            ImageDraw.Draw(img).rounded_rectangle((x - 1, y - 1, x + pw, y + ph), radius=7, outline=LINE)
            self.sim_text(img, (W / 2, y + ph + 15), words, "status", MUTED, BG, anchor="m")
        return img

    def sim_overlay(self, s):
        """The card over the box, if there's one, as (picture, where): START's options; Paused; a sim's
        note (Life when it settles); in Rock Paper Scissors the moment to pick a winner, and who won.
        Full screen: just START's options."""
        if self.sim_opts is not None:
            key = ("opts", s.key, self.sim_opts, tuple(self.sim_value(type(s), k) for k, _, _, _ in self.sim_rows(type(s))),
                   self.sim_box(), ACCENT)
        elif self.sim_full():
            return None
        elif s.key == "rps" and s.phase == "ready":
            key = ("ready", s.pick, math.ceil(s.wait))
        elif s.key == "rps" and s.phase == "over":
            key = ("over", s.winner, s.pick, int(s.clock), s.captures, math.ceil(s.wait))
        elif s.paused:
            key = ("paused",)
        elif s.note():
            key = ("note",) + tuple(s.note()) + (s.note_top(),)
        else:
            return None
        if key != self.sim_card[0]:
            self.sim_card = (key, self.sim_opts_card(s) if key[0] == "opts" else self.sim_note(s, key))
        return self.sim_card[1]

    def sim_note(self, s, key):
        """A card of a few lines: in the middle of the box (the moment to pick, Paused), or at its foot
        (who won, a sim's note). Its words are kept pictures: they come back again and again."""
        from PIL import Image, ImageDraw
        bx0, by0, bx1, by1 = self.sim_layout()[0]
        rows = []                                      # ([(text, font, colour)...], height)
        middle = key[0] in ("ready", "paused")
        if key[0] == "ready":
            if s.pick is None:
                rows += [([("Pick a winner", "head", TEXT)], 30),
                         ([(f"◀ ▶ to choose. Starts in {key[2]}", "small", BODY)], 24)]
            else:
                rows += [([("Your pick: ", "head", TEXT), (RPS_TEAMS[s.pick], "head", RPS_COLOUR[s.pick])], 30),
                         ([(f"Starts in {key[2]}", "small", BODY)], 24)]
        elif key[0] == "paused":
            rows.append(([("Paused", "head", TEXT)], 30))
        elif key[0] == "note":
            rows += [([(key[1], "head", TEXT)], 30), ([(key[2], "small", BODY)], 24)]
        else:
            w = s.winner
            meta = f"After {sim_clock(s.clock)} and {s.captures} captures."
            if s.pick is not None:
                meta = ("You called it. " if s.pick == w else f"Your pick, {RPS_TEAMS[s.pick]}, didn't make it. ") + meta
            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            rows += [([("Last team standing", "label", MUTED)], 23),
                     ([(f"{RPS_TEAMS[w]} wins", "big", RPS_COLOUR[w])], 39)]
            rows += [([(line, "small", BODY)], 24) for line in self.wrap(probe, meta, self.fonts["small"], bx1 - bx0 - 80)]
            rows.append(([(f"Next round in {key[5]} s", "status", MUTED)], 24))
        tiles = [[self.sim_tile(t, f, colour, ROW) for t, f, colour in segs] for segs, _ in rows]
        widths = [sum(t.width - 2 for t in ts) for ts in tiles]
        px, py = (26, 12) if middle else (22, 10)
        W = int(max(widths) + 2 * px)
        H = int(sum(h for _, h in rows) + 2 * py)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle((0, 0, W - 1, H - 1), radius=12, fill=ROW + (255,),
                                              outline=LINE + (255,))
        y = py
        for (segs, h), ts, rw in zip(rows, tiles, widths):
            x = (W - rw) / 2 if middle else px
            for tile in ts:
                img.paste(tile, (int(round(x)) - 1, int(round(y + h / 2)) - tile.height // 2))
                x += tile.width - 2
            y += h
        x0 = (bx0 + bx1 - W) // 2
        y0 = (by0 + by1 - H) // 2 if middle else by0 + 14 if key[0] == "note" and key[3] else by1 - 14 - H
        return img, (x0, y0)

    def sim_opts_card(self, s):
        """START: the sim's options, and full screen."""
        from PIL import Image, ImageDraw
        F = self.fonts
        rows = self.sim_rows(type(s))
        W = 404
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lede = self.wrap(probe, s.blurb, F["small"], W - 44, lines=3)
        top = 56 + 20 * len(lede) + 6
        H = top + 40 * len(rows) + 10
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=12, fill=ROW + (255,), outline=LINE + (255,))
        d.text((22, 30), LIBRARY[self.tab].get("title") or LIBRARY[self.tab]["name"], font=F["head"], fill=TEXT,
               anchor="lm")
        y = 56
        for line in lede:
            d.text((22, y), line, font=F["small"], fill=MUTED, anchor="lm")
            y += 20
        y = top
        for i, (key, label, _, _) in enumerate(rows):
            on, mid = i == self.sim_opts, y + 18
            if on:
                d.rounded_rectangle((10, y, W - 11, y + 36), radius=8, fill=co_mix(ROW, TEXT, 0.07))
                d.rectangle((10, y + 9, 13, y + 27), fill=ACCENT)
            d.text((26, mid), label, font=F["small"], fill=TEXT if on else BODY, anchor="lm")
            value, font, x1 = str(self.sim_value(type(s), key)), F["small_b"] if on else F["small"], W - 24
            if value.endswith(":latest"):              # (a model's usual name: Ollama's own word for it)
                value = value[:-7]
            if on:
                d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                x1 -= 22
            d.text((x1, mid), value, font=font, fill=ACCENT if on else MUTED, anchor="rm")
            if on:
                d.text((x1 - d.textlength(value, font=font) - 10, mid), "◀", font=F["small"], fill=ACCENT,
                       anchor="rm")
            y += 40
        (bx0, by0, bx1, by1), _ = self.sim_box()
        if self.sim_full():
            by1 -= self.FOOTER                         # (the buttons show along the bottom meanwhile)
        return img, ((bx0 + bx1 - W) // 2, max(by0, (by0 + by1 - H) // 2))

    def sim_corners(self, base):
        """The box's round corners and its edge, as they are on the picture without the sim: put back on
        each frame over a sim that fills the box right up to its corners."""
        from PIL import Image, ImageDraw
        x0, y0, x1, y1 = self.sim_layout()[0]
        mask = Image.new("L", (x1 - x0 + 1, y1 - y0 + 1), 255)
        ImageDraw.Draw(mask).rounded_rectangle((1, 1, x1 - x0 - 1, y1 - y0 - 1), radius=9, fill=0)
        out = []
        for cx, cy in ((x0, y0), (x1 - 11, y0), (x0, y1 - 11), (x1 - 11, y1 - 11)):
            box = (cx, cy, cx + 12, cy + 12)
            out.append((base.crop(box), mask.crop((cx - x0, cy - y0, cx - x0 + 12, cy - y0 + 12)), (cx, cy)))
        return out

    def render_sim(self):
        """The box with the sim in it, and its numbers beside it. What doesn't move is drawn when it
        changes; each frame draws the sim on it and sends just the box (and the numbers, when they've
        changed) to the screen. Full screen: just the sim, the whole screen each frame."""
        from PIL import Image
        fb = self.fb
        now = time.monotonic()
        s = self.sim_game()
        if self.sim_opts is None:                      # (it waits while its options are open)
            dt = 0.0 if self.sim_t is None else min(now - self.sim_t, 0.1)
            if s.key == "snake" and s.phase == "on" and not s.ai and (self.sim_t is None or now - self.sim_t > 0.5):
                s.paused = True                        # (back to a game: it waits for you)
            if s.key == "snake":
                if dt > 0:
                    self.brain_frame = self.brain_frame * 0.9 + dt * 0.1
                self.snake_ai_take(s)
            news = s.update(dt)
            if news == "won" and s.key == "rps" and s.pick is not None:
                self.set_setting("sim_rps_calls", list(s.calls))
            elif news == "over" and s.key == "snake":
                self.snake_over(s)
            if s.key == "snake":
                self.snake_ai_ask(s)
        self.sim_t = now
        full, card_open = self.sim_full(), self.sim_opts is not None
        hints = (tuple(self.sim_hints(s)), ACCENT)
        if (card_open or not full) and hints not in self.sim_feet:   # the buttons: each set kept
            img, d = self.canvas()
            msg, self.msg = self.msg, None            # (a notice is put on each frame instead)
            mark = self.tap_mark()
            try:
                self.footer(d, list(hints[0]))
            finally:
                self.msg = msg
            self.sim_feet[hints] = img.crop((0, fb.h - self.FOOTER, fb.w, fb.h))
            if getattr(self, "sim_feet_taps", None) is None:
                self.sim_feet_taps = {}
            self.sim_feet_taps[hints] = self.taps_cut(mark)
        if card_open or not full:                      # (each frame: where they are, for the web page's taps)
            self.tap_again(getattr(self, "sim_feet_taps", {}).get(hints))
        fresh = False
        if full:
            key = ("full", fb.w, fb.h)
            if key != self.sim_base[0]:
                self.sim_base = (key, Image.new("RGB", (fb.w, fb.h), SIM_FLOOR), None)
        else:
            if (self.status_sig, ACCENT, self.tab_off) != self.sim_head[0]:     # the clock, the tabs
                img, d = self.canvas()
                mark = self.tap_mark()
                self.header(img, d)
                self.sim_head = ((self.status_sig, ACCENT, self.tab_off), img.crop((0, 0, fb.w, self.HEADER + 1)))
                self.sim_head_taps = self.taps_cut(mark)
            self.tap_again(getattr(self, "sim_head_taps", None))
            key = (self.sim_head[0], hints)
            if key != self.sim_base[0]:
                img, d = self.canvas()
                img.paste(self.sim_head[1], (0, 0))
                img.paste(self.sim_feet[hints], (0, fb.h - self.FOOTER))
                d.rounded_rectangle(self.sim_layout()[0], radius=10, fill=SIM_FLOOR, outline=LINE)
                self.sim_base = (key, img, self.sim_corners(img))
            if s.key == "rps":
                sig = ("rps", s.phase, s.pick, s.is_open(), tuple(s.calls), s.round, ACCENT)   # drawn at once
                pkey = (sig, tuple(s.counts()), int(s.clock), s.captures, len(s.history))     # ...or every 0.25 s
            else:
                sig = (s.key, self.tab, tuple(label for label, _ in s.stats()), ACCENT)
                pkey = (sig, tuple(s.stats()), len(s.history), s.look())
            old = self.sim_panel[0]
            fresh = old is None or old[0] != sig or (pkey != old and now - self.sim_panel[2] >= 0.25)
            if fresh:
                self.sim_panel = (pkey, self.rps_scores(s, sig) if s.key == "rps" else self.sim_numbers(s, sig), now)
        img = self.sim_base[1].copy()
        (bx, by, _, _), inset = self.sim_box()
        if not full:
            img.paste(self.sim_panel[1], self.sim_layout()[1][:2])
        s.draw(img, bx + inset, by + inset)
        if not full:
            for tile, mask, at in self.sim_base[2]:
                img.paste(tile, at, mask)
        card = self.sim_overlay(s)
        if card:
            img.paste(card[0], card[1], card[0])
        if full and card_open:                         # (its buttons, while the card is open)
            img.paste(self.sim_feet[hints], (0, fb.h - self.FOOTER))
        self.sim_msg(img, low=full and not card_open)  # (a notice stays over the sim)
        last_key, last_count, last_t, whole_t = self.sim_shown
        key = (key, self.msg, card_open and hints)
        if (full or key != last_key or getattr(fb, "frames", None) != last_count or now - last_t > 0.5
                or now - whole_t > 3 or not hasattr(fb, "show_part")):
            fb.show(img)                               # the whole picture: full screen, or something
            whole_t = now                              # else changed too
        else:
            box, _, dirty = self.sim_layout()
            fb.show_part(img, dirty if fresh else box)
        self.sim_shown = (key, getattr(fb, "frames", None), now, whole_t)

    def sim_msg(self, img, low=False):
        """A notice (toast) over the sim: as msg_pill draws it, from a kept picture of the words. Low: at
        the foot of the screen (full screen has no buttons along the bottom)."""
        if not self.msg:
            return
        from PIL import ImageDraw
        W, H = self.fb.w, self.fb.h
        tile = self.sim_tile(self.msg, "small", TEXT, ROW)
        if tile.width > W - 70:                        # (a long one: shortened, as usual)
            self.msg_pill(ImageDraw.Draw(img))
            return
        mw = tile.width - 2 + 32
        y0 = H - 48 if low else H - self.FOOTER - 46
        ImageDraw.Draw(img).rounded_rectangle(((W - mw) / 2, y0, (W + mw) / 2, y0 + 34), radius=17, fill=ROW)
        img.paste(tile, ((W - tile.width) // 2, y0 + 17 - tile.height // 2))
