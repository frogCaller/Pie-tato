"""The Games tab: Snake and your own games, with their pictures (Y finds them) and a box to find one by name
(START); a game while it plays (a process of its own draws it, pitato/emulator.py), and the menu HOME brings up
over it."""
import os
import struct
import time
import unicodedata

from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT
from ..util import item
from ..screen import aplay_device, screen_turn, sound_place
from ..library import LIBRARY
from ..snake import snake_card
from ..games import (ANALOG_SYSTEMS, art_path, ArtFinder, bios_missing, built_for_other_pi, find_core, find_games,
                     game_kind, GAME_PACKAGES, GAME_PLAYERS, GameRun, games_dir, has_resume, plain_title, playable,
                     save_name, SAVES_FOLDER, system)
from ..emulator import screen_picture
from ..gameai import GameAI

GAME_BUTTONS = ("a", "b", "x", "y", "l", "r", "l2", "r2", "start", "select", "up", "down", "left", "right")
BY_PLACE = {"a": "b", "b": "a", "x": "y", "y": "x"}   # PlayStation buttons go by where they are, not their letters
N64_BUTTONS = {"a": "b", "b": "y", "y": "a"}          # an N64's A and B are libretro's B and Y (X and Y: C buttons
                                                      # with R2 held, pitato/emulator.py)
DS_BUTTONS = {"r2": "r3"}                             # a DS game: R2 touches the touch screen (libretro's R3, to
                                                      # melonDS); L2 blows on its microphone
DC_BUTTONS = dict(BY_PLACE, l="l2", r="r2")           # a Dreamcast's go by place too (A at the bottom, as on an Xbox
                                                      # controller), and L and R are its triggers, as L2 and R2 are
GAME_BUTTON_MAPS = {"ps1": BY_PLACE, "psp": BY_PLACE, "n64": N64_BUTTONS, "nds": DS_BUTTONS, "dc": DC_BUTTONS}
DPAD = ("up", "down", "left", "right")
GAME_MENU = [("resume", "Back to the game"), ("save", "Save state"), ("load", "Load state"),
             ("reset", "Start over"), ("disc", "Disc"), ("screens", "Screens"), ("touch", "Touch screen"),
             ("volume", "Volume"), ("picture", "Picture"), ("players", "Players"), ("ai", "AI player"),
             ("quit", "Quit game")]
DS_ONLY = ("screens", "touch")      # (a DS game's own)
GAME_CHANGE = ("disc", "volume", "picture", "screens", "touch", "ai")   # (◀▶ changes these)
DS_SCREENS = [("Left/Right", "Side by side"), ("Top/Bottom", "One above the other"),
              ("Hybrid Top", "Top one big"), ("Hybrid Bottom", "Touch screen big")]   # (melonDS's names, and ours)
DS_TOUCH = ["Right stick, R2", "D-pad, A"]   # what moves the pointer on the touch screen, and touches
DS_POINTER = 24                     # the d-pad's pointer: as a stick pushed this far (of 127: 3 pixels a frame)
DS_STICK_DPAD = 64                  # the left stick, as the d-pad: pushed this far (of 127), a direction
STICK_JOIN = 64                     # a controller not playing yet: its stick pushed this far (of 127) makes it a player
                                    # (a stick at rest reads a little off the middle: that doesn't)
GAME_CONFIRM = ("load", "reset")    # (these lose where you are: A twice)
GAME_PANEL_W = 212                  # the picked game's picture, beside the list
GAME_THUMB = 40                     # ...and each game's, on its row
GAME_PICS_KEPT = 80                 # pictures kept ready to draw
GAME_PICTURES = ("Fit", "Sharp", "Fill")   # a game's picture: as big as fits in its shape, whole pixels only, or the
                                           # whole screen (kept for each console)
WIDE_SCREEN = 1.5                   # a screen wider than this (a TV's 16:9, not 4:3): an N64 game in Fill is drawn wide
N64_WIDE = "mupen64plus-aspect=16:9 adjusted"   # (its own wide picture: more to each side, nothing stretched; it
                                                # takes it as it starts)
GAME_FIND_MOST = 40                 # letters in the box that finds a game


def fold(text):
    """A name as it's matched when you look for a game: lower case, no accents, its punctuation spaces."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def game_matches(row, words):
    """Every word you typed is in the game's name (anywhere in it, with its spaces or without: "pacman" finds
    Pac-Man), or starts a word of its console's ("gba", "game boy"; "nes" isn't the SNES). Snake: its name."""
    names = [fold(row.get("title", ""))]
    consoles = []
    if row.get("kind") == "game":
        names.append(fold(row.get("label") or ""))
        consoles = [c for c in (fold(row.get("sub", "")), fold(row.get("icon", ""))) if c]

    def found(w):
        return (any(w in n or w in n.replace(" ", "") for n in names)
                or any(c.replace(" ", "").startswith(w) or any(x.startswith(w) for x in c.split()) for c in consoles))
    return all(found(w) for w in words)


class GameScreen:
    """The Games tab: Snake and your own games; a game while it plays, and its menu (HOME)."""

    def games_rows(self):
        """Snake, then the games in your Games folder (a word on where they go, if there are none). While you're
        finding one (START): just the ones with what you typed in their names, those starting with it first."""
        snake = next(k for k, t in enumerate(LIBRARY) if t.get("sim") == "snake")
        rows = [dict(item("grp:Snake", "Snake", "child", str(snake), sub=LIBRARY[snake].get("about", "")),
                     icon=LIBRARY[snake].get("badge", ""))]
        games = find_games()
        plain = [plain_title(g["title"]) for g in games]
        titles = [g["title"] for g in games]
        for g, short in zip(games, plain):
            _, badge, name = system(g["system"])[:3]
            label = (short if plain.count(short) == 1 else g["title"] if titles.count(g["title"]) == 1
                     else f"{g['title']} ({badge})")      # (two of a name: their tags, or their kinds, tell them apart)
            rows.append(dict(item(g["path"], g["title"], "game", g["path"], sub=name), icon=badge,
                             system=g["system"], label=label))
        words = fold(getattr(self, "games_q", None)).split()
        if words:
            hits = [r for r in rows if game_matches(r, words)]
            hits.sort(key=lambda r: not fold(r.get("label") or r["title"]).startswith(words[0]))
            return hits or [dict(item("games:none", f"No game has “{self.games_q}” in its name", "info", ""),
                                 sub="")]
        if len(rows) == 1:
            rows.append(dict(item("games:where", "Your own games go in", "info", ""),
                             sub="the Games folder"))
        return rows

    def games_find(self):
        """START on the Games tab: a box to type a game's name in (what you typed last, if it's still finding it)."""
        self.open_keyboard("Find a game", self.games_q or "", self.games_search, empty=True, limit=GAME_FIND_MOST)

    def games_search(self, text):
        """The games with every word you typed in their names, the first of them picked. Nothing typed (or B): all
        of them again, the one you were on still picked."""
        i = self.tab_index("games")
        if i is None:
            return
        rows = self.tab_items(i)
        sel = self.sels.get(i, 0)
        was = rows[sel].get("key") if rows and 0 <= sel < len(rows) else None
        self.games_q = text.strip() if fold(text) else None
        self.items[i] = self.games_rows()
        keys = [r.get("key") for r in self.items[i]]
        self.sels[i] = 0 if self.games_q or was not in keys else keys.index(was)
        self.tops[i] = 0
        self.dirty = True

    @staticmethod
    def game_system(path):
        """A game's system (gb, gba, nes, ps1...) by its file, or None: it isn't one (or not one this Pi plays)."""
        kind = game_kind(path)
        return kind if kind and playable(kind) else None

    def on_game(self):
        return self.game is not None and self.view in ("game", "gamemenu")

    # -- playing ---------------------------------------------------------------------
    def game_open(self, it):
        g = {"path": it["src"], "title": it["title"], "system": it.get("system", "")}
        name = system(g["system"])[2]
        core = find_core(g["system"])
        if not core:
            pkg = GAME_PACKAGES.get(system(g["system"])[4][0], "")
            if g["system"] == "nds" and struct.calcsize("P") < 8:   # (a 32-bit system: setup.sh can't build it)
                self.toast("DS games need the 64-bit Raspberry Pi OS", 5)
                return
            self.toast(f"The {name} emulator isn't installed. Run setup.sh again to add it"
                       if pkg else f"There's no {name} emulator here", 5)
            return
        missing = bios_missing(core)
        if missing:
            self.toast(f"{name} games need {missing} in Games/BIOS", 5)
            return
        if built_for_other_pi(core):                   # (the SD card moved from a Pi 4 to a Pi 5, say)
            self.toast(f"The {name} emulator was built on another kind of Pi. Run setup.sh again to build it here", 6)
            return
        self.stop()                                    # (music, a video, another game: the game has the speaker)
        self.game_menu = None
        options = []
        picture = self.game_picture(g["system"])
        if self.game_wide(g["system"], picture):       # (an N64 game filling a TV: drawn wide, not stretched)
            options.append(N64_WIDE)
        if g["system"] == "nds":                       # (its screens, as you had them last)
            layout = self.setting("ds_screens")
            options.append("melonds_screen_layout=" + (layout if layout in dict(DS_SCREENS) else DS_SCREENS[0][0]))
        self.view = "game"
        self.render_curtain(g["title"], "Starting…", hints=[("HOME", "Its menu")])   # (the game draws over it)
        run = GameRun(g, on_change=self.game_changed)
        place = sound_place(self.setting("sound"))     # (Bluetooth headphones, if they're on: sound_tick moves it)
        try:
            turn = screen_turn()                       # (a screen on its side: the game's turned too)
            run.start(core, sound=aplay_device(None, place[0]), volume=self.volume, picture=picture, options=options,
                      **({"turn": turn} if turn else {}))
        except OSError as ex:
            print(f"game: couldn't start {g['path']}: {ex}", flush=True)
            self.view = "list"
            self.toast("Couldn't start the game", 4)
            return
        self.game = run
        self.game_sound = place
        self.game_since = time.monotonic()
        self.stick_sent = {}
        self.ds_dirs = set()
        used = getattr(self, "input_pad", None)       # the controller that started it: player 1 (from the web page or
        self.game_players = {used.path: 0} if used is not None and self.pads and \
            self.pads.by_path.get(used.path) is used else {}      # a keyboard: the first controller pressed)

    def game_picture(self, key):
        """A console's games' picture: Fit, Sharp or Fill, as it was last picked for that console (at first: as it
        was for every game, before it was each console's own)."""
        v = self.setting(f"game_picture_{key}") if key else None
        if v not in GAME_PICTURES:
            v = self.setting("game_picture")
        return v if v in GAME_PICTURES else GAME_PICTURES[0]

    def game_wide(self, key, picture):
        """An N64 game drawn wide: in Fill, on a screen wider than 4:3 (a TV)."""
        fb = self.fb
        w, h = (getattr(fb, "real_w", fb.w), getattr(fb, "real_h", fb.h)) if fb else (640, 480)
        return key == "n64" and picture == "Fill" and w > h * WIDE_SCREEN

    def game_restart(self):
        """The game started again where it was (an N64 game drawn wide, or not: it takes that as it starts)."""
        g = self.game.game
        it = {"src": g["path"], "title": g["title"], "system": g.get("system", "")}
        self.game_end()                                # (where you are, kept)
        self.game_open(it)                             # (...and picked up again)

    # -- its players: each controller its own (the one that started it player 1, the next to press player 2...) -----
    def game_port(self, pad, join=True):
        """The player a controller's buttons are for (0 is player 1), or None: no place for it (as many as the
        game has are playing already). The web page's remote is player 1."""
        if pad is None or self.game is None:
            return 0
        most = GAME_PLAYERS.get(self.game.game.get("system"), 1)
        if most < 2:
            return 0                                   # (a game for one: every controller works it)
        players = self.game_players
        if pad.path in players:
            return players[pad.path]
        if not join:
            return None
        here = self.pads.by_path if self.pads else {}
        taken = {p for path, p in players.items() if path in here}   # (one unplugged: its place is free again)
        free = [p for p in range(most) if p not in taken]
        if not free:
            return None
        for path in [k for k, p in players.items() if p == free[0]]:
            del players[path]                          # (the one unplugged from it: a newcomer, if it's back)
        players[pad.path] = free[0]
        return free[0]

    def game_player_names(self):
        """[(player number, its controller's name)] for the players playing, player 1 first."""
        here = self.pads.by_path if self.pads else {}
        return sorted((p + 1, here[path].dev.name.strip() or "Controller") for path, p in self.game_players.items()
                      if path in here)

    def game_changed(self):
        """The game said something (its thread)."""
        self.dirty = True

    def game_tick(self, now):
        """A game that stopped by itself, or never started; and pictures, found."""
        f = self.art_finder
        if f is not None and not f.busy and f.note:
            note, f.note = f.note, ""
            if not self.on_game():
                self.toast(note, 5)
        run = self.game
        if run is None:
            return
        if run.ended or (run.state == "starting" and now - self.game_since > 15):
            why = run.error or ("The game didn't start" if run.state == "starting" else "The game stopped")
            self.game_end()
            self.toast(why, 5)

    # -- pictures -------------------------------------------------------------------------
    def games_find_art(self):
        """Y on the Games tab: pictures for the games without one, from libretro's thumbnails."""
        games = [{"path": it["src"], "title": it["title"], "system": it["system"]}
                 for it in self.tab_items() if it["kind"] == "game"]
        if not games:
            self.toast("Put some games in the Games folder first", 3)
            return
        if self.art_finder is None:
            self.art_finder = ArtFinder()
            self.art_finder.on_change = self.game_changed
        f = self.art_finder
        if f.busy:
            self.toast("Finding pictures already", 2)
        elif not f.start(games):
            self.toast("Every game has a picture", 3)
        else:
            self.toast(f"Finding pictures for {f.total} game{'s' if f.total != 1 else ''}", 3)

    def game_pic(self, it, kind):
        """A row's picture, ready to draw: "thumb" (on its row), "panel" (beside the list) or "back" (soft,
        behind the list). Snake's is a little board from the game, the snake about to eat an apple. None:
        there isn't one."""
        from PIL import Image, ImageFilter, ImageOps
        if it.get("kind") == "child":
            src, stamp = "icon", 0
        elif it.get("kind") == "game":
            src = art_path(it["src"])
            if src is None:
                return None
            try:
                stamp = os.path.getmtime(src)
            except OSError:
                return None
        else:
            return None
        key = (it["src"], src, stamp, kind) + ((self.HEADER, self.FOOTER) if kind == "back" else ())   # (its size)
        hit = self.game_pics.get(key)
        if hit is not None:
            return hit
        W, H = self.fb.w, self.fb.h
        if src == "icon":
            if kind == "back":
                return None
            pic = snake_card(GAME_THUMB if kind == "thumb" else 132)
        else:
            try:
                art = Image.open(src)
                art.load()
                art = art.convert("RGBA")
            except (OSError, ValueError):
                return None
            if kind == "thumb":
                pic = ImageOps.contain(art, (GAME_THUMB, GAME_THUMB), Image.BILINEAR)
            elif kind == "panel":
                pic = ImageOps.contain(art, (GAME_PANEL_W, GAME_PANEL_W), Image.BILINEAR)
            else:                                      # a soft, dark wash of it, behind the list
                area = (W, H - self.HEADER - self.FOOTER - 1)
                small = ImageOps.fit(art.convert("RGB"), (40, max(1, 40 * area[1] // area[0])), Image.BILINEAR)
                small = small.filter(ImageFilter.GaussianBlur(1.6))
                wash = small.resize(area, Image.BILINEAR)
                pic = Image.blend(wash, Image.new("RGB", area, BG), 0.72)
        if len(self.game_pics) >= GAME_PICS_KEPT:
            self.game_pics.pop(next(iter(self.game_pics)))
        self.game_pics[key] = pic
        return pic

    def render_games(self):
        """The Games tab: the list on the left, each game with its picture; the picked one's picture big on
        the right, and softly behind it all."""
        F = self.fonts
        W = self.fb.w
        img, d = self.canvas()
        items = self.tab_items()
        n = len(items)
        sel = min(self.sels.get(self.tab, 0), max(n - 1, 0))
        cur = items[sel] if n else {}
        back = self.game_pic(cur, "back") if cur else None
        if back is not None:
            img.paste(back, (0, self.HEADER + 1))
        self.header(img, d)
        if self.games_q:                               # finding one: what you typed, and how many have it
            found = sum(it["kind"] != "info" for it in items)
            note = f"{found} found"
            d.text((W - 20, self.LIST_TOP + 10), note, font=F["small"], fill=MUTED, anchor="rm")
            crumbs = f"{LIBRARY[self.tab]['name']}  ›  “{self.games_q}”"
            room = W - 60 - d.textlength(note, font=F["small"])
            d.text((20, self.LIST_TOP + 10), self.fit(d, crumbs, F["small"], room), font=F["small"], fill=MUTED,
                   anchor="lm")
        top_y = self.list_top()
        rows = self.visible_rows()
        top = self.tops.get(self.tab, 0)
        if sel < top:
            top = sel
        elif sel >= top + rows:
            top = sel - rows + 1
        top = max(min(top, n - rows), 0)
        self.tops[self.tab] = top
        px0 = W - GAME_PANEL_W - 16                     # the picture beside the list
        x0, x1 = 12, px0 - 14
        for r, i in enumerate(range(top, min(top + rows, n))):
            it = items[i]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            if i == sel:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            tx = x0 + 16
            if it["kind"] == "info":
                d.text((tx, mid), self.fit(d, it["title"], F["small"], x1 - 12 - tx), font=F["small"],
                       fill=BODY if i == sel else MUTED, anchor="lm")
                continue
            pic = self.game_pic(it, "thumb")
            if pic is not None:
                img.paste(pic, (int(tx + (GAME_THUMB - pic.width) / 2), int(mid - pic.height / 2)), pic)
            else:
                d.rounded_rectangle((tx, mid - 10, tx + GAME_THUMB, mid + 10), radius=5, outline=ACCENT, width=1)
                d.text((tx + GAME_THUMB / 2, mid), it.get("icon", ""), font=F["badge"], fill=ACCENT, anchor="mm")
            tx += GAME_THUMB + 12
            font = F["row_b"] if i == sel else F["row"]
            name = it.get("label") or it["title"]
            d.text((tx, mid), self.fit(d, name, font, x1 - 12 - tx), font=font, fill=TEXT if i == sel else BODY,
                   anchor="lm")
        if n > rows:                                    # (where you are in a long list)
            t0, t1 = top_y + 6, top_y + rows * self.ROW_H - 6
            d.rounded_rectangle((x1 + 4, t0, x1 + 7, t1), radius=2, fill=LINE)
            th = max((t1 - t0) * rows / n, 20)
            ty = t0 + (t1 - t0 - th) * top / max(n - rows, 1)
            d.rounded_rectangle((x1 + 4, ty, x1 + 7, ty + th), radius=2, fill=BODY)
        if cur and cur.get("kind") != "info":           # the picked one, big
            pic = self.game_pic(cur, "panel")
            py = top_y + 4
            if pic is not None:
                img.paste(pic, (int(px0 + (GAME_PANEL_W - pic.width) / 2), py), pic)
                py += pic.height + 14
            else:
                d.rounded_rectangle((px0, py, px0 + GAME_PANEL_W, py + 150), radius=12, fill=ROW)
                d.text((px0 + GAME_PANEL_W / 2, py + 62), cur.get("icon", ""), font=F["big"], fill=ACCENT, anchor="mm")
                d.text((px0 + GAME_PANEL_W / 2, py + 104), "No picture yet: Y finds one", font=F["small"],
                       fill=MUTED, anchor="mm")
                py += 150 + 14
            if cur["kind"] == "game":
                full = os.path.splitext(os.path.basename(cur["src"]))[0]
                for line in self.wrap(d, full, F["small"], GAME_PANEL_W):
                    d.text((px0, py), line, font=F["small"], fill=BODY, anchor="lt")
                    py += 18
                d.text((px0, py + 2), cur.get("sub", ""), font=F["small"], fill=MUTED, anchor="lt")
                if has_resume(cur["src"]):
                    d.text((px0, py + 22), "Picks up where you left off", font=F["small"], fill=ACCENT, anchor="lt")
            else:
                d.text((px0, py), cur.get("sub", ""), font=F["small"], fill=MUTED, anchor="lt")
        f = self.art_finder
        right = f"Finding pictures {f.done} of {f.total}" if f is not None and f.busy else None
        self.footer(d, self.list_hints(), right=right)
        self.fb.show(img)

    def game_button(self, name):
        """A button as the game gets it: a PlayStation's and a PSP's go by place (bottom is Cross), an N64's by
        letter."""
        return GAME_BUTTON_MAPS.get(self.game.game.get("system"), {}).get(name, name)

    # -- the sticks (an N64 or a PSP game) ------------------------------------------------------
    def game_sticks(self):
        """A game on the screen that takes the sticks as they are: True. (Not while the AI player plays: it has
        the sticks, as it has the buttons.)"""
        return (self.game is not None and self.view == "game" and self.game.game.get("system") in ANALOG_SYSTEMS
                and not self.game_ai_on())

    def game_stick(self, axis, value, pad=None):
        """Where a stick is (axis lx ly rx ry, -127 to 127), to the game when it's moved: its controller's player's.
        A DS game's: the left one is its d-pad (it has no stick), the right one moves the pointer on its touch
        screen, half as fast (it's small: the stick all the way, 8 pixels a frame)."""
        if self.game.game.get("system") == "nds":
            if axis in ("lx", "ly"):
                self.ds_stick_dpad(axis, value)
                return
            value = int(value / 2)
        port = self.game_port(pad, join=abs(value) >= STICK_JOIN)   # (pushed, not just resting: a player)
        if port is not None:
            self.game_stick_send(axis, value, port)

    def game_stick_send(self, axis, value, port=0):
        if self.stick_sent.get((port, axis), 0) != value:
            self.stick_sent[(port, axis)] = value
            self.game.stick(axis, value, port)

    def ds_stick_dpad(self, axis, value):
        """A DS game's left stick, as its d-pad: a direction pressed while the stick's pushed that way."""
        self.stick_sent[(0, axis)] = value
        x, y = self.stick_sent.get((0, "lx"), 0), self.stick_sent.get((0, "ly"), 0)
        want = ({"right"} if x > DS_STICK_DPAD else {"left"} if x < -DS_STICK_DPAD else set()) | \
            ({"down"} if y > DS_STICK_DPAD else {"up"} if y < -DS_STICK_DPAD else set())
        held = getattr(self, "ds_dirs", set())
        for d in held - want:
            self.game.release(d)
        for d in want - held:
            self.game.press(d)
        self.ds_dirs = want

    def game_pad_button(self, pad, name):
        """A button from this controller, for an N64 game: on one with no stick the d-pad is the stick (None: it
        went that way); on one with no L2, L is the N64's Z (L2). (A PSP has a d-pad of its own.) For a DS game
        with its touch screen on the d-pad (its menu: Touch screen), the d-pad moves the pointer and A touches."""
        sysk = self.game.game.get("system")
        if sysk == "nds":
            if self.setting("ds_touch") != DS_TOUCH[1]:
                return name
            if name in DPAD:
                x = ("right" in pad.down) - ("left" in pad.down)
                y = ("down" in pad.down) - ("up" in pad.down)
                self.game_stick_send("rx", x * DS_POINTER)
                self.game_stick_send("ry", y * DS_POINTER)
                return None
            return "r2" if name == "a" else name       # (R2: touch, DS_BUTTONS)
        if sysk != "n64":
            return name
        if name in DPAD and not pad.has_stick():
            x = ("right" in pad.down) - ("left" in pad.down)
            y = ("down" in pad.down) - ("up" in pad.down)
            k = 90 if x and y else 127                 # (a diagonal as far as a stick goes)
            self.game_stick("lx", x * k, pad)
            self.game_stick("ly", y * k, pad)
            return None
        if name == "l" and not pad.has_button("l2"):
            return "l2"
        return name

    def game_sticks_now(self):
        """The sticks where they are now (the game let go of them while its menu was up)."""
        self.stick_sent = {}
        self.ds_dirs = set()
        if not self.game_sticks():
            return
        for pad in (self.pads.by_path.values() if self.pads else []):
            for axis, value in pad.sticks_now():
                port = self.game_port(pad, join=abs(value) >= STICK_JOIN)   # (one held: its player's, or a player now)
                if value and port is not None and not self.stick_sent.get((port, axis)):
                    self.game_stick(axis, value, pad)

    def press_game(self, name, repeat):
        if self.game is None:
            self.view = "list"
            self.dirty = True
        elif name in GAME_BUTTONS and not repeat and not self.game_ai_on():   # (the AI player's playing: it has the
            port = self.game_port(getattr(self, "input_pad", None))           # buttons till it's off)
            if port is not None:
                self.game.press(self.game_button(name), port)
        return None

    def release_game(self, name):
        if self.game is not None and name in GAME_BUTTONS and not self.game_ai_on():
            port = self.game_port(getattr(self, "input_pad", None), join=False)
            if port is not None:
                self.game.release(self.game_button(name), port)

    def game_end(self):
        """The game ends, its saves kept (where you are, too: it picks up there next time)."""
        run, self.game = self.game, None
        if run is None:
            return
        if getattr(self, "game_ai", None) is not None:
            self.game_ai.stop()
            self.game_ai = None
        self.game_menu, self.game_sound = None, None
        if self.view in ("game", "gamemenu"):
            self.view = "list"
        run.quit()
        if self.fb is not None and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()                       # (the game drew everywhere: all of it again)
        gi = self.tab_index("games")
        if gi is not None:
            self.load_tab(gi)
        self.dirty = True

    # -- its menu (HOME) -------------------------------------------------------------------
    def game_home(self):
        """HOME in a game: its menu, or (from the menu) back to the game. False: not in a game."""
        if not self.on_game():
            return False
        if self.view == "game":
            self.game_menu_open()
        else:
            self.game_menu_close()
        return True

    def game_menu_open(self):
        run = self.game
        if run.state != "on" or not run.pause():
            return                                     # (still starting, or busy: HOME again in a moment)
        bg = screen_picture()                          # the game, dimmed, behind the menu
        if bg is not None:
            from PIL import ImageEnhance, ImageOps
            bg = ImageEnhance.Brightness(ImageOps.pad(bg.convert("RGB"), (self.fb.w, self.fb.h),
                                                      color=(0, 0, 0))).enhance(0.3)
        self.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": bg}
        self.view = "gamemenu"
        if hasattr(self.fb, "invalidate"):
            self.fb.invalidate()
        self.dirty = True

    def game_menu_close(self):
        self.game_menu = None
        self.view = "game"
        if self.game is not None:
            self.game.resume()
            self.game_sticks_now()

    def game_menu_items(self):
        """The game's menu: Disc only for a game on more than one; Players for one two (or more) can play;
        Screens and Touch screen for a DS game. (AI player: any game.)"""
        many = self.game is not None and self.game.disc[1] > 1
        ds = self.game is not None and self.game.game.get("system") == "nds"
        together = self.game is not None and GAME_PLAYERS.get(self.game.game.get("system"), 1) > 1
        return [m for m in GAME_MENU if (m[0] != "disc" or many) and (m[0] not in DS_ONLY or ds)
                and (m[0] != "players" or together)]

    # -- the AI player (a decision model on your bot's computer plays, looking at the screen; your Bot's model
    #    coaches it) -----------------------------------------------------------------------------------------
    def game_ai_on(self):
        ai = getattr(self, "game_ai", None)
        return ai is not None and ai.alive()

    def game_ai_models(self):
        """["Off", and the decision models on your bot's computer] (asked for, if they're not known yet)."""
        server = self.snake_server()
        if not server:
            return ["Off"]
        self.snake_models()
        b = self.brain
        return ["Off"] + (list(b.models) if b.models_for == server else [])

    def game_ai_set(self, model):
        """The AI player on, with that model ("Off": off). It plays once the game's back on the screen."""
        ai = getattr(self, "game_ai", None)
        if ai is not None:
            ai.stop()
        self.game_ai = None
        if model == "Off" or self.game is None:
            return
        base = os.path.join(games_dir(), SAVES_FOLDER, save_name(self.game.game["path"]))
        server = self.snake_server()                  # (and your Bot's model, to coach it: pitato/coach.py)
        self.game_ai = GameAI(self.game, server, model, base + ".ai.log", on_change=self.game_ai_changed,
                              coach=self.friend.model, notes_path=base + ".ai-notes.txt")
        self.game_ai.start()
        self.set_setting("game_ai_model", model)

    def game_ai_changed(self):
        if self.view == "gamemenu":
            self.dirty = True

    def game_value(self, job):
        if job == "players" and self.game is not None:
            return f"{len(self.game_player_names())} of {GAME_PLAYERS.get(self.game.game.get('system'), 1)}"
        if job == "volume":
            return f"{self.volume}%"
        if job == "picture":
            return self.game_picture(self.game.game.get("system") if self.game is not None else "")
        if job == "disc" and self.game is not None:
            i, n = self.game.disc
            return f"{i + 1} of {n}"
        if job == "screens":
            return dict(DS_SCREENS).get(self.setting("ds_screens"), DS_SCREENS[0][1])
        if job == "touch":
            return self.setting("ds_touch") if self.setting("ds_touch") in DS_TOUCH else DS_TOUCH[0]
        if job == "ai":
            ai = getattr(self, "game_ai", None)
            return ai.model if ai is not None and ai.alive() else "Off"
        return ""

    def game_change(self, job, d):
        """◀▶ on Disc, Volume or Picture."""
        if job == "disc":
            i, n = self.game.disc
            want = (i + d) % n
            what, rest = self.game.ask(f"disc {want + 1}", ("disc",), 3)
            if what == "disc" and self.game.disc[0] == want:
                self.toast(f"Disc {want + 1} is in. Back to the game to play on", 3)
            else:
                self.toast("Couldn't change the disc", 3)
        elif job == "volume":
            self.volume = max(0, min(100, self.volume + 10 * d))
            self.game.send(f"volume {self.volume}")
        elif job == "picture":                         # (kept for this console's games)
            key = self.game.game.get("system", "")
            now = self.game_picture(key)
            mode = GAME_PICTURES[(GAME_PICTURES.index(now) + d) % len(GAME_PICTURES)]
            self.set_setting(f"game_picture_{key}", mode)
            if self.game_wide(key, mode) != self.game_wide(key, now):
                self.game_restart()                    # (an N64 game, wide or not: it starts again where it was)
            else:
                self.game.send(f"picture {mode}")
        elif job == "screens":                         # (melonDS lays them out afresh as the game goes on)
            keys = [k for k, _ in DS_SCREENS]
            now = self.setting("ds_screens")
            want = keys[((keys.index(now) if now in keys else 0) + d) % len(keys)]
            self.set_setting("ds_screens", want)
            self.game.send(f"option melonds_screen_layout {want}")
        elif job == "touch":
            now = self.setting("ds_touch")
            want = DS_TOUCH[((DS_TOUCH.index(now) if now in DS_TOUCH else 0) + d) % len(DS_TOUCH)]
            self.set_setting("ds_touch", want)
            self.game_stick_send("rx", 0)              # (the pointer, still)
            self.game_stick_send("ry", 0)
        elif job == "ai":
            if not self.snake_server():
                self.toast("The AI plays on your bot's computer. Set up the Bot first", 4)
                return
            options = self.game_ai_models()
            if len(options) == 1:
                self.snake_models(force=True)
                self.toast("Looking for decision models on your bot's computer…", 3)
                return
            now = self.game_value("ai")
            if now == "Off" and d > 0 and self.setting("game_ai_model") in options:
                want = self.setting("game_ai_model")   # (the one it had last time, first)
            else:
                want = options[((options.index(now) if now in options else 0) + d) % len(options)]
            self.game_ai_set(want)
            self.toast("The AI plays once you're back in the game. Your buttons wait while it does" if want != "Off"
                       else "Your turn", 3)

    def press_game_menu(self, name, repeat):
        m, run = self.game_menu, self.game
        if m is None or run is None:
            self.view = "list" if run is None else "game"
            self.dirty = True
            return None
        menu = self.game_menu_items()
        n = len(menu)
        m["sel"] = min(m["sel"], n - 1)
        job = menu[m["sel"]][0]
        if name in ("up", "down"):
            m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % n
            m["confirm"] = (None, 0.0)
        elif name in ("left", "right") and job in GAME_CHANGE:
            self.game_change(job, 1 if name == "right" else -1)
        elif name == "b" and not repeat:
            self.game_menu_close()
        elif name == "a" and not repeat:
            waiting, until = m["confirm"]
            if job in GAME_CONFIRM and (waiting != job or time.monotonic() > until):
                m["confirm"] = (job, time.monotonic() + 4)
            else:
                m["confirm"] = (None, 0.0)
                self.game_do(job)
        self.dirty = True
        return None

    def game_do(self, job):
        run = self.game
        if job == "resume":
            self.game_menu_close()
        elif job == "save":
            what, why = run.ask("save", ("saved", "error"), 8)
            self.toast("Saved" if what == "saved" else (why or "Couldn't save"), 3)
        elif job == "load":
            what, why = run.ask("load", ("loaded", "nostate", "error"), 8)
            if what == "loaded":
                self.game_menu_close()
            else:
                self.toast("There's no save state yet" if what == "nostate" else (why or "Couldn't load it"), 3)
        elif job == "reset":
            run.ask("reset", ("reset",), 3)
            self.game_menu_close()
        elif job == "players":                         # who's who, afresh: in the order they press a button
            self.game_players = {}
            self.toast("Back in the game, press a button on each controller: player 1 first", 4)
        elif job in GAME_CHANGE:
            self.game_change(job, 1)
        elif job == "quit":
            self.game_end()
            self.toast("Saved. It picks up there next time", 3)

    def render_game_menu(self):
        F = self.fonts
        m = self.game_menu or {"sel": 0, "confirm": (None, 0.0), "bg": None}
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        if m.get("bg") is not None:
            img.paste(m["bg"])
        g = self.game.game if self.game is not None else {"title": "", "system": ""}
        menu = self.game_menu_items() if self.game is not None else GAME_MENU
        n, mw = len(menu), 360
        rh = 38 if n <= 7 else 34                       # (a game on discs has a row more)
        mh = 64 + n * rh + 10
        mx0, my0 = (W - mw) / 2, max(12, (H - self.FOOTER - 50 - mh) / 2)   # (room below for a toast)
        d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + mh + 2), radius=14, fill=LINE)
        d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + mh), radius=13, fill=BG)
        d.text((mx0 + 22, my0 + 24), self.fit(d, g["title"], F["row_b"], mw - 44), font=F["row_b"],
               fill=TEXT, anchor="lm")
        sysname = system(g["system"])[2] if g.get("system") else ""
        if self.game is not None and self.game.slow:
            sysname += " (running slowly on this Pi)"
        ai = getattr(self, "game_ai", None)
        if ai is not None and self.game is not None:     # the AI player's doing (or why it stopped)
            sysname = ("AI (its model can't see the screen): " if ai.alive() and ai.blind else "AI: ") + \
                      (ai.status if ai.alive() or ai.status.startswith("Stopped") else "Off") + \
                      (" (on its own: your bot's computer isn't answering)" if ai.alive() and ai.offline else "")
        d.text((mx0 + 22, my0 + 46), self.fit(d, sysname, F["small"], mw - 44), font=F["small"], fill=MUTED,
               anchor="lm")
        waiting, until = m["confirm"]
        for k, (job, label) in enumerate(menu):
            ry = my0 + 64 + k * rh
            sel = k == m["sel"]
            if sel:
                d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                d.rounded_rectangle((mx0 + 8, ry + 10, mx0 + 12, ry + rh - 14), radius=2, fill=ACCENT)
            mid = ry + (rh - 4) / 2
            d.text((mx0 + 24, mid), label, font=F["row_b"] if sel else F["row"], fill=TEXT if sel else BODY,
                   anchor="lm")
            right, colour = self.game_value(job), MUTED
            if waiting == job and time.monotonic() <= until:
                right, colour = "press A again", ACCENT
            elif job in GAME_CHANGE and sel:
                right, colour = f"◀  {right}  ▶", TEXT
            if right:
                d.text((mx0 + mw - 22, mid), right, font=F["small"], fill=colour, anchor="rm")
        job = menu[min(m["sel"], n - 1)][0]
        hints = [("A", "Pick again" if job == "players" else "Choose")]
        if job in GAME_CHANGE:
            hints.append(("◀▶", "Change"))
        hints.append(("B", "Back to the game"))
        self.footer(d, hints)
        self.fb.show(img)

    def game_hint(self, it):
        """A on a row of the Games tab."""
        if it.get("kind") == "game":
            return "Continue" if has_resume(it["src"]) else "Play"
        if it.get("kind") == "child":
            return "Play"
        return None
