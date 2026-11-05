"""The Games tab: Snake and your own games, with their pictures (Y finds them) and a box to find one by name
(START); with more than a few, a folder for each console (and the ones played last, your favourites, all of them), a
grid of their icons to pick from; a game while it plays (a process of its own draws it, pitato/emulator.py), and the
menu HOME brings up over it."""
import json
import os
import struct
import threading
import time
import unicodedata
import urllib.parse

from ..asyou import read_theirs, shm_path
from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT
from ..util import item
from ..screen import aplay_device, screen_turn, sound_place
from ..library import LIBRARY
from ..snake import snake_card
from ..consoles import draw_console
from ..games import (ANALOG_SYSTEMS, art_path, ArtFinder, bios_missing, built_for_other_pi, find_core, find_games,
                     game_kind, GAME_PACKAGES, GAME_PLAYERS, GAME_SYSTEMS, GameRun, games_dir, has_resume,
                     neogeo_unknown, plain_title, playable, save_name, SAVES_FOLDER, system)
from ..emulator import screen_picture
from ..fine import made_fine, scale
from ..gameai import GameAI
from .. import savesync

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
             ("cheevos", "Achievements"), ("together", "Play together"), ("send", "Play on another Pietato"),
             ("quit", "Quit game")]
DS_ONLY = ("screens", "touch")      # (a DS game's own)
GAME_CHANGE = ("disc", "volume", "picture", "screens", "touch", "ai", "together", "send")   # (◀▶ changes these)
DS_SCREENS = [("Left/Right", "Side by side"), ("Top/Bottom", "One above the other"),
              ("Hybrid Top", "Top one big"), ("Hybrid Bottom", "Touch screen big")]   # (melonDS's names, and ours)
DS_TOUCH = ["Right stick, R2", "D-pad, A"]   # what moves the pointer on the touch screen, and touches
DS_POINTER = 24                     # the d-pad's pointer: as a stick pushed this far (of 127: 3 pixels a frame)
DS_STICK_DPAD = 64                  # the left stick, as the d-pad: pushed this far (of 127), a direction
STICK_JOIN = 64                     # a controller not playing yet: its stick pushed this far (of 127) makes it a player
                                    # (a stick at rest reads a little off the middle: that doesn't)
GAME_CONFIRM = ("load", "reset")    # (these lose where you are: A twice)
GAME_MENU_W = 360                   # a game's menu: this wide at least, wider for its longest row (and the game's name)
GAME_MENU_EDGE = 16                 # ...as far as this from the screen's sides
GAME_MENU_TITLED = 480              # ...and for the game's name, no wider than this (a longer one's cut short)
PEER_JOBS = ("together", "send", "keep")   # (its rows that name another of your Pietatos: a dot in its colour
                                           #  before it)
PEER_DOT = 15                       # ...that dot's room, and the gap after it
GAME_PANEL_W = 212                  # the picked game's picture, beside the list
GAME_THUMB = 40                     # ...and each game's, on its row
GAME_PICS_KEPT = 80                 # pictures kept ready to draw
GAME_PICTURES = ("Fit", "Sharp", "Fill")   # a game's picture: as big as fits in its shape, whole pixels only, or the
                                           # whole screen (kept for each console)
WIDE_SCREEN = 1.5                   # a screen wider than this (a TV's 16:9, not 4:3): an N64 game in Fill is drawn wide
N64_WIDE = "mupen64plus-aspect=16:9 adjusted"   # (its own wide picture: more to each side, nothing stretched; it
                                                # takes it as it starts)
GAME_FIND_MOST = 40                 # letters in the box that finds a game
CHEEVO_PAGE = 5                     # ◀▶ in a game's list of achievements: this many at a time
GAMES_FLAT = 12                     # this many games or fewer: one list of them all (more: a folder for each console)
GAMES_RECENT = 20                   # the games played last, kept for Recently played
GAME_FOLDERS = {"recent": ("Recently played", "LAST"), "fav": ("Favourites", "★"), "all": ("All games", "ALL")}
GAMES_TILE = 96                     # the folders, as a grid: each one's icon (consoles.py) this big...
GAMES_CELL = (152, 172)             # ...in a cell this wide (at least) and tall: its name and how many under it
GAME_PANEL_ICON = 120               # a game with no picture of its own: its console's icon, beside the list


def fold(text):
    """A name as it's matched when you look for a game: lower case, no accents, its punctuation spaces."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def game_letter(row):
    """The letter a game goes under in a list in order of name: its name's first (# for a number or a sign)."""
    c = fold(row.get("label") or row.get("title", ""))[:1].upper()
    return c if c.isalpha() else "#"


def games_count(n):
    return f"{n} game{'' if n == 1 else 's'}"


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


def peer_labels(peers):
    """[(address, name)] of your other Pietatos, as their names are shown: one that has another's name, with the end of
    its address after it (raspberrypi (.54), raspberrypi (.62)), or the whole address when that's the same too."""
    names = [h for _, h in peers]
    ips = {u: urllib.parse.urlsplit(u).hostname or u for u, _ in peers}
    ends = {u: "." + ip.rsplit(".", 1)[-1] if ip.count(".") == 3 else ip for u, ip in ips.items()}
    out = []
    for u, h in peers:
        if names.count(h) > 1:
            same = [v for v, k in peers if k == h]
            end = ends[u] if [ends[v] for v in same].count(ends[u]) == 1 else ips[u]
            h = f"{h} ({end})"
        out.append((u, h))
    return out


class GameScreen:
    """The Games tab: Snake and your own games; a game while it plays, and its menu (HOME)."""

    def games_rows(self):
        """Snake, then the games in your Games folder (a word on where they go, if there are none). More than a
        dozen: a folder for each console instead (and the ones played last, your favourites, all of them), and in a
        folder, its games. While you're finding one (START): just the ones with what you typed in their names (of
        all of them), those starting with it first."""
        snake = next(k for k, t in enumerate(LIBRARY) if t.get("sim") == "snake")
        rows = [dict(item("grp:Snake", "Snake", "child", str(snake), sub=LIBRARY[snake].get("about", "")),
                     icon=LIBRARY[snake].get("badge", ""))]
        games = find_games()
        self.games_all = games
        words = fold(getattr(self, "games_q", None)).split()
        if words:
            hits = [r for r in rows + self.game_rows(games) if game_matches(r, words)]
            hits.sort(key=lambda r: not fold(r.get("label") or r["title"]).startswith(words[0]))
            return hits or [dict(item("games:none", f"No game has “{self.games_q}” in its name", "info", ""),
                                 sub="")]
        if len(games) <= GAMES_FLAT:
            self.games_dir = None
            rows += self.game_rows(games)
            if len(rows) == 1:
                rows.append(dict(item("games:where", "Your own games go in", "info", ""),
                                 sub="the Games folder"))
            return rows
        if self.games_dir:
            inside = self.game_rows(self.games_in(self.games_dir, games))
            return inside or [dict(item("games:empty", "No favourites yet: SELECT on a game adds it"
                                        if self.games_dir == "fav" else "No games here now", "info", ""), sub="")]
        return rows + self.games_folders(games)

    def game_rows(self, games):
        """A row for each game: its name without its tags (unless two have it), its console's badge, its picture's
        key, and whether it's one of your favourites."""
        rows = []
        plain = [plain_title(g["title"]) for g in games]
        titles = [g["title"] for g in games]
        favs = set(self.games_favs())
        for g, short in zip(games, plain):
            _, badge, name = system(g["system"])[:3]
            label = (short if plain.count(short) == 1 else g["title"] if titles.count(g["title"]) == 1
                     else f"{g['title']} ({badge})")      # (two of a name: their tags, or their kinds, tell them apart)
            rows.append(dict(item(g["path"], g["title"], "game", g["path"], sub=name), icon=badge,
                             system=g["system"], label=label, fav=g["path"] in favs))
        return rows

    # -- folders: each console's, the ones played last, your favourites, all of them -----------------------------------
    def games_recent(self):
        v = self.setting("games_recent")
        return [p for p in v if isinstance(p, str)] if isinstance(v, list) else []

    def games_favs(self):
        v = self.setting("games_favourites")
        return [p for p in v if isinstance(p, str)] if isinstance(v, list) else []

    def games_in(self, folder, games):
        """A folder's games: a console's, the ones played last (the last first), your favourites, or all of them."""
        if folder == "recent":
            by_path = {g["path"]: g for g in games}
            return [by_path[p] for p in self.games_recent() if p in by_path]
        if folder == "fav":
            favs = set(self.games_favs())
            return [g for g in games if g["path"] in favs]
        if folder.startswith("sys:"):
            return [g for g in games if g["system"] == folder[4:]]
        return list(games)

    def games_folders(self, games):
        """The top of a long list: the games played last, your favourites, a folder for each console (in the order
        the consoles came out, near enough), then all of them. Each with a picture of one of its games, if one has
        one."""
        rows = []

        def folder(key, title, sub, icon, inside, **more):
            cover = next((g["path"] for g in inside if art_path(g["path"])), None)
            rows.append(dict(item("games:" + key, title, "gamedir", key, sub=sub), icon=icon, cover=cover, **more))
        recent = self.games_in("recent", games)
        if recent:
            folder("recent", GAME_FOLDERS["recent"][0], plain_title(recent[0]["title"]), GAME_FOLDERS["recent"][1],
                   recent)
        favs = self.games_in("fav", games)
        if favs:
            folder("fav", GAME_FOLDERS["fav"][0], games_count(len(favs)), GAME_FOLDERS["fav"][1], favs)
        keys = [s[0] for s in GAME_SYSTEMS if any(g["system"] == s[0] for g in games)]
        for key in keys:
            inside = [g for g in games if g["system"] == key]
            _, badge, name = system(key)[:3]
            folder("sys:" + key, name, games_count(len(inside)), badge, inside, system=key)
        if len(keys) > 1:
            folder("all", GAME_FOLDERS["all"][0], games_count(len(games)), GAME_FOLDERS["all"][1], games)
        return rows

    # -- the folders, as a grid of icons to pick from ------------------------------------------------------------
    def games_grid(self):
        """The Games tab's top, with a folder for each console: a grid of their icons (not a list)."""
        return (self.tab_type() == "games" and not getattr(self, "games_q", None)
                and not getattr(self, "games_dir", None)
                and any(it.get("kind") == "gamedir" for it in self.tab_items()))

    def games_cols(self):
        """The grid's columns: four on the GPi Case's screen, more on a wider one."""
        w = self.fb.w if self.fb else 640
        return max(4, (w - 32) // GAMES_CELL[0])

    def games_grid_rows(self):
        h = self.fb.h if self.fb else 480
        return max(1, (h - self.FOOTER - self.LIST_TOP - 6) // GAMES_CELL[1])

    def console_pic(self, key, label, size):
        """A console's icon (consoles.py: a folder's too), size across, kept: as finely as the screen's drawn."""
        s = scale()
        k = ("console", key, label, size, s)
        hit = self.game_pics.get(k)
        if hit is None:
            hit = made_fine(draw_console(key, label, size * s, fine=s), s)
            if len(self.game_pics) >= GAME_PICS_KEPT:
                self.game_pics.pop(next(iter(self.game_pics)))
            self.game_pics[k] = hit
        return hit

    def games_tile(self, it):
        """A tile in the grid: Snake's card, a console's icon (its short name on it), or a folder's (Recently played,
        Favourites, All games: just its picture)."""
        if it.get("kind") == "child":
            return self.game_pic(it, "tile")
        src = it.get("src", "")
        if src.startswith("sys:"):
            return self.console_pic(src[4:], it.get("icon", ""), GAMES_TILE)
        return self.console_pic(src, "", GAMES_TILE)

    def render_games_grid(self):
        """The Games tab's top: a tile for Snake and each folder (the ones played last, your favourites, each
        console's, all of them), its name and how many games under it, in a grid: the picked one lit. Up, down, left
        and right go from one to the next; A opens it."""
        F = self.fonts
        W = self.fb.w
        img, d = self.canvas()
        self.header(img, d)
        items = self.tab_items()
        n = len(items)
        sel = min(self.sels.get(self.tab, 0), max(n - 1, 0))
        cols, rows = self.games_cols(), self.games_grid_rows()
        top = self.tops.get(self.tab, 0)               # (in rows)
        if sel // cols < top:
            top = sel // cols
        elif sel // cols >= top + rows:
            top = sel // cols - rows + 1
        total = (n + cols - 1) // cols
        top = max(min(top, total - rows), 0)
        self.tops[self.tab] = top
        cw, ch = (W - 32) / cols, GAMES_CELL[1]
        y_top = self.LIST_TOP + 6
        for r in range(rows):
            for c in range(cols):
                i = (top + r) * cols + c
                if i >= n:
                    break
                it = items[i]
                x0, y0 = 16 + c * cw, y_top + r * ch
                ix, iy = int(x0 + (cw - GAMES_TILE) / 2), int(y0 + 8)
                if i == sel:                           # (picked: a ring round it, its name bright)
                    d.rounded_rectangle((ix - 6, iy - 6, ix + GAMES_TILE + 5, iy + GAMES_TILE + 5), radius=27,
                                        outline=ACCENT, width=3)
                pic = self.games_tile(it)
                if pic is not None:
                    img.paste(pic, (ix, iy), pic)
                font = F["small"]
                name = self.fit(d, it.get("label") or it["title"], font, cw - 8)
                d.text((x0 + cw / 2, iy + GAMES_TILE + 20), name, font=font, fill=TEXT if i == sel else BODY,
                       anchor="mm")
                d.text((x0 + cw / 2, iy + GAMES_TILE + 40), self.fit(d, it.get("sub", ""), F["label"], cw - 10),
                       font=F["label"], fill=MUTED, anchor="mm")
                self.tappable((x0, y0, x0 + cw, y0 + ch), "sel", "sels", self.tab, i)
        if total > rows:                               # (where you are, when there are more)
            t0, t1 = y_top + 6, y_top + rows * ch - 6
            d.rounded_rectangle((W - 10, t0, W - 7, t1), radius=2, fill=LINE)
            th = max((t1 - t0) * rows / total, 20)
            ty = t0 + (t1 - t0 - th) * top / max(total - rows, 1)
            d.rounded_rectangle((W - 10, ty, W - 7, ty + th), radius=2, fill=BODY)
        f = self.art_finder
        right = f"Finding pictures {f.done} of {f.total}" if f is not None and f.busy else None
        self.footer(d, self.list_hints(), right=right)
        self.fb.show(img)

    def games_dir_title(self, folder):
        if folder in GAME_FOLDERS:
            return GAME_FOLDERS[folder][0]
        return system(folder[4:])[2] if folder.startswith("sys:") else ""

    def games_open_dir(self, it):
        """A on a folder: its games, the first picked."""
        i = self.tab_index("games")
        if i is None:
            return
        self.games_dir = it["src"]
        self.items[i] = self.games_rows()
        self.sels[i], self.tops[i] = 0, 0
        self.dirty = True

    def games_back(self):
        """B in a folder: back to the folders, that one picked. False: not in one."""
        i = self.tab_index("games")
        if i is None or not self.games_dir:
            return False
        was, self.games_dir = self.games_dir, None
        self.items[i] = self.games_rows()
        self.sels[i] = next((k for k, r in enumerate(self.items[i]) if r.get("kind") == "gamedir" and r["src"] == was),
                            0)
        self.tops[i] = 0
        self.dirty = True
        return True

    def games_by_letter(self):
        """◀▶ go by letter here: a folder of games in order of name (not the ones played last, nor what's found)."""
        return bool(self.tab_type() == "games" and self.games_dir and self.games_dir != "recent"
                    and not self.games_q)

    def games_letter_step(self, items, sel, d):
        """The row ◀ (d -1) or ▶ (d 1) goes to: the first game of the letter before, or after (round to the other
        end). ◀ in a letter's games, past its first: its first."""
        n = len(items)
        if not n:
            return 0
        sel = max(0, min(sel, n - 1))
        here = game_letter(items[sel])
        if d > 0:
            k = next((k for k in range(sel + 1, n) if game_letter(items[k]) != here), None)
            return 0 if k is None else k
        start = sel
        while start > 0 and game_letter(items[start - 1]) == here:
            start -= 1
        if start < sel:
            return start
        k = (start - 1) % n                            # (the letter before: its first game)
        there = game_letter(items[k])
        while k > 0 and game_letter(items[k - 1]) == there:
            k -= 1
        return k

    def games_fav_toggle(self, it):
        """SELECT on a game: one of your favourites, or not any more."""
        if not it or it.get("kind") != "game":
            return
        favs = self.games_favs()
        if it["src"] in favs:
            favs.remove(it["src"])
            self.toast("Taken out of Favourites", 2)
        else:
            favs.append(it["src"])
            self.toast("★ Added to Favourites", 2)
        self.set_setting("games_favourites", favs)
        i = self.tab_index("games")
        if i is not None:
            sel = self.sels.get(i, 0)
            self.items[i] = self.games_rows()
            self.sels[i] = max(0, min(sel, len(self.items[i]) - 1))
        self.dirty = True

    def games_played(self, path):
        """A game started: first of the ones played last."""
        self.set_setting("games_recent", ([path] + [p for p in self.games_recent() if p != path])[:GAMES_RECENT])

    def games_systems(self):
        """The consoles you have games for, in the order they're listed."""
        have = {g["system"] for g in getattr(self, "games_all", None) or []}
        return [s[0] for s in GAME_SYSTEMS if s[0] in have]

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
        if self.here_take_game(it):                    # (picked on the web page, with Play here on: played there)
            return
        g = {"path": it["src"], "title": it["title"], "system": it.get("system", "")}
        why = self.game_cant(g)
        if why:
            self.toast(*why)
            return
        core = find_core(g["system"])
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
        hints = [("HOME", "Its menu")] + ([("SELECT", "Coin")] if g["system"] == "neogeo" else [])
        self.render_curtain(g["title"], "Starting…", hints=hints)   # (the game draws over it)
        came = self.saves_follow(g, lambda words: self.render_curtain(g["title"], words, hints=hints))
        if came:
            self.render_curtain(g["title"], f"Carrying on from {came}", hints=hints)
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

    def game_boot(self):
        """Settings > At start-up's Game, as the Pi starts: the game you played last, from where you were (saved as
        you left it, or by the power switch, or a minute before the battery ran out). None played yet, or it's gone:
        the home screen."""
        games = {g["path"]: g for g in find_games()}
        g = next((games[p] for p in self.games_recent() if p in games), None)
        if g is None:
            self.toast("Play a game first: the Pi starts in the one you played last", 4)
            return
        print(f"start-up: {g['title']}, the game played last", flush=True)
        self.game_open({"src": g["path"], "title": g["title"], "system": g["system"]})

    @staticmethod
    def game_cant(g):
        """Why a game won't start here, and for how long to say so: (words, seconds), or None. (Its path "": its
        console's games.)"""
        name = system(g["system"])[2]
        core = find_core(g["system"])
        if not core:
            pkg = GAME_PACKAGES.get(system(g["system"])[4][0], "")
            if g["system"] == "nds" and struct.calcsize("P") < 8:   # (a 32-bit system: setup.sh can't build it)
                return "DS games need the 64-bit Raspberry Pi OS", 5
            return (f"The {name} emulator isn't installed. Run setup.sh again to add it"
                    if pkg else f"There's no {name} emulator here", 5)
        missing = bios_missing(core, g["path"] or None)
        if missing:
            return f"{name} games need {missing} in Games/BIOS", 5
        if g["system"] == "neogeo" and g["path"] and neogeo_unknown(g["path"]):   # (it plays them only by the names
            return ("The Neo Geo emulator doesn't know this game by its name. Name it as in its list, like mslug.zip",
                    6)                                                              # it knows)
        if built_for_other_pi(core):                   # (the SD card moved from a Pi 4 to a Pi 5, say)
            return f"The {name} emulator was built on another kind of Pi. Run setup.sh again to build it here", 6
        return None

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
        if run is None or getattr(run, "attract", False):   # (a game playing by itself: attract_tick's)
            return
        if run.state in ("on", "paused") and not getattr(run, "noted", False):   # (it's started: one of the ones
            run.noted = True                                                    # played last now)
            self.games_played(run.game["path"])
        if self.together_of(run) is not None:          # (played together: the other joined, left...)
            self.together_tick(run, now)
        if run.ended or (run.state == "starting" and now - self.game_since > 15):
            why = run.error or ("The game didn't start" if run.state == "starting" else "The game stopped")
            self.game_end()
            self.toast(why, 5)

    # -- pictures -------------------------------------------------------------------------
    def games_find_art(self):
        """Y on the Games tab: pictures for the games without one, from libretro's thumbnails."""
        games = [{"path": it["src"], "title": it["title"], "system": it["system"]}
                 for it in self.tab_items() if it["kind"] == "game"]
        if not games and not self.games_dir and not self.games_q:   # (the folders: every game's)
            games = [dict(g) for g in getattr(self, "games_all", None) or []]
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
        from ..fine import Image
        from PIL import ImageFilter, ImageOps
        if it.get("kind") == "child":
            src, stamp = "icon", 0
        elif it.get("kind") in ("game", "gamedir"):
            if it["kind"] == "gamedir" and (kind == "thumb" or not it.get("cover")):
                return None                             # (on its row: its badge)
            src = art_path(it["src"] if it["kind"] == "game" else it["cover"])
            if src is None:
                return None
            try:
                stamp = os.path.getmtime(src)
            except OSError:
                return None
        else:
            return None
        s = scale()                                    # (as finely as the screen's drawn: a 4K TV's, twice)
        key = (it["src"], src, stamp, kind, s) + ((self.HEADER, self.FOOTER) if kind == "back" else ())   # (its size)
        hit = self.game_pics.get(key)
        if hit is not None:
            return hit
        W, H = self.fb.w, self.fb.h
        if src == "icon":
            if kind == "back":
                return None
            pic = made_fine(snake_card({"thumb": GAME_THUMB, "tile": GAMES_TILE}.get(kind, 132) * s, fine=s), s)
        else:
            try:
                art = Image.open(src)
                art.load()
                art = art.convert("RGBA")
            except (OSError, ValueError):
                return None
            if kind == "thumb":
                pic = made_fine(ImageOps.contain(art, (GAME_THUMB * s, GAME_THUMB * s), Image.BILINEAR), s)
            elif kind == "panel":
                pic = made_fine(ImageOps.contain(art, (GAME_PANEL_W * s, GAME_PANEL_W * s), Image.BILINEAR), s)
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
        the right, and softly behind it all. (Its top, with a folder for each console: a grid of their icons.)"""
        if self.games_grid():
            return self.render_games_grid()
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
        elif self.games_dir:                           # in a folder: which, and how many in it
            note = games_count(sum(it["kind"] == "game" for it in items))
            d.text((W - 20, self.LIST_TOP + 10), note, font=F["small"], fill=MUTED, anchor="rm")
            crumbs = f"{LIBRARY[self.tab]['name']}  ›  {self.games_dir_title(self.games_dir)}"
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
        self.tap_rows(0, x1 + 8, top_y, self.ROW_H, top, min(top + rows, n), "sel", "sels", self.tab)
        if cur and cur.get("kind") != "info":           # (the picked one's picture: a tap plays it)
            self.tappable((px0 - 6, top_y, W, self.fb.h - self.FOOTER), "keys", "a")
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
            if pic is None:                            # (no picture of its own: its console's icon, or its folder's)
                pic = self.console_pic(it.get("system") or (it["src"] if it["kind"] == "gamedir" else ""),
                                       it.get("icon", "") if it.get("system") else "", GAME_THUMB)
            img.paste(pic, (int(tx + (GAME_THUMB - pic.width) / 2), int(mid - pic.height / 2)), pic)
            tx += GAME_THUMB + 12
            font = F["row_b"] if i == sel else F["row"]
            name = it.get("label") or it["title"]
            star = d.textlength("  ★", font=font) if it.get("fav") else 0
            name = self.fit(d, name, font, x1 - 12 - tx - star)
            d.text((tx, mid), name, font=font, fill=TEXT if i == sel else BODY, anchor="lm")
            if star:                                   # (one of your favourites)
                d.text((tx + d.textlength(name + "  ", font=font), mid), "★", font=font, fill=ACCENT, anchor="lm")
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
            else:                                      # (no picture of its own: its console's icon, big)
                d.rounded_rectangle((px0, py, px0 + GAME_PANEL_W, py + 168), radius=12, fill=ROW)
                key = cur.get("system") or (cur["src"][4:] if str(cur["src"]).startswith("sys:") else cur["src"])
                icon = self.console_pic(key, cur.get("icon", "") if cur.get("system") or
                                        str(cur["src"]).startswith("sys:") else "", GAME_PANEL_ICON)
                img.paste(icon, (int(px0 + (GAME_PANEL_W - GAME_PANEL_ICON) / 2), py + 12), icon)
                if cur["kind"] == "game":
                    d.text((px0 + GAME_PANEL_W / 2, py + 150), "No picture yet: Y finds one", font=F["small"],
                           fill=MUTED, anchor="mm")
                py += 168 + 14
            if cur["kind"] == "game":
                full = os.path.splitext(os.path.basename(cur["src"]))[0]
                for line in self.wrap(d, full, F["small"], GAME_PANEL_W):
                    d.text((px0, py), line, font=F["small"], fill=BODY, anchor="lt")
                    py += 18
                d.text((px0, py + 2), cur.get("sub", ""), font=F["small"], fill=MUTED, anchor="lt")
                if has_resume(cur["src"]):
                    d.text((px0, py + 22), "Picks up where you left off", font=F["small"], fill=ACCENT, anchor="lt")
                    py += 20
                if cur.get("fav"):
                    d.text((px0, py + 22), "★ One of your favourites", font=F["small"], fill=ACCENT, anchor="lt")
            else:                                      # (a folder: its name, and how many in it)
                if cur["kind"] == "gamedir":
                    d.text((px0, py), self.fit(d, cur["title"], F["small"], GAME_PANEL_W), font=F["small"], fill=BODY,
                           anchor="lt")
                    py += 20
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
        if getattr(run, "attract", False):             # (a game playing by itself: its saves were never yours)
            if getattr(self, "attract", None) is not None and self.attract["run"] is run:
                self.attract = None
            self.dirty = True
            return
        t = self.together_of(run)
        if t is not None:
            self.together_end(run)                     # (a link cable's save, back with yours)
        if t is None or t.get("host") or t.get("link"):
            self.saves_tell(run)                       # (its saves written: your other Pietatos take them)
        gi = self.tab_index("games")
        if gi is not None:
            self.load_tab(gi)
            path = (getattr(run, "game", None) or {}).get("path")
            at = next((k for k, r in enumerate(self.items.get(gi) or []) if r.get("kind") == "game"
                       and r.get("src") == path), None)
            if at is not None:
                self.sels[gi] = at
        self.dirty = True

    # -- saves that follow you: your other Pietatos' (savesync.py) ------------------------------------------
    def saves_peers(self, addr=None):
        """Your other Pietatos heard lately ([(address, name)]), with Settings > Share with other Pietatos on, by name
        (a steady order, not who said they're there last): two of the same name with the end of their addresses
        after it, so they can be told apart ("raspberrypi (.54)"). The one at addr alone, if that's given."""
        pie = getattr(self, "pie", None)
        if pie is None or self.setting("share") == "Off":
            return []
        peers = sorted(peer_labels(pie.peer_list()), key=lambda p: (p[1].lower(), p[0]))
        if addr is not None:
            peers = [(u, h) for u, h in peers if urllib.parse.urlsplit(u).hostname == addr]
        return peers

    def saves_playing(self):
        """The game being played here now, by its saves' name (None: none)."""
        run = self.game
        if run is None or run.ended:
            return None
        return save_name(run.game["path"])

    def saves_owner(self):
        """Whose the Games folder is (the saves are theirs too): (uid, gid), or None."""
        try:
            st = os.stat(games_dir())
            return st.st_uid, st.st_gid
        except OSError:
            return None

    def saves_follow(self, g, say=None):
        """Before a game starts: its saves from whichever of your other Pietatos played it last, if that was later
        than here (asked quickly: a moment at most when none has it). The name of the one they came from, or None."""
        peers = self.saves_peers()
        if not peers:
            return None
        saves, owner = os.path.join(games_dir(), SAVES_FOLDER), self.saves_owner()
        try:
            os.makedirs(saves, exist_ok=True)
            if owner:
                os.chown(saves, *owner)
            with self.saves_lock:
                came = savesync.pull(saves, save_name(g["path"]), peers, owner=owner,
                                     on_fetch=(lambda host: say(f"Getting your save from {host}…")) if say else None)
        except Exception as ex:                        # (whatever happens, the game still starts)
            print(f"saves: {ex!r}", flush=True)
            return None
        if came:
            print(f"saves: {save_name(g['path'])} from {came}", flush=True)
        return came

    def saves_tell(self, run):
        """A game just played here: your other Pietatos told, so they take its saves (on a thread of its own)."""
        path = (getattr(run, "game", None) or {}).get("path")
        peers = self.saves_peers() if path else []
        if peers:
            threading.Thread(target=savesync.tell, args=(save_name(path), peers), daemon=True,
                             name="saves-tell").start()

    def web_saves(self, name):
        """GET /api/saves (another of your Pietatos asking, from your network: webui.py): a game's saves here, and
        whether it's being played here now (its saves still changing). (The control server's thread.)"""
        name = savesync.game_name(name)
        if name is None:
            return {"ok": False, "error": "Which game?"}
        if self.setting("share") == "Off":
            return {"ok": True, "on": False}
        files = savesync.save_files(os.path.join(games_dir(), SAVES_FOLDER), name)
        return {"ok": True, "on": True, "playing": self.saves_playing() == name, "files": files,
                "folder": os.path.join(games_dir(), SAVES_FOLDER)}

    def web_saves_news(self, cmd):
        """POST /api/saves/news: another of your Pietatos has just played a game: its saves, taken from it (on a
        thread of its own), unless the game's being played here now."""
        name = savesync.game_name(cmd.get("game"))
        if name is None:
            return {"ok": False, "error": "Which game?"}
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers or not os.path.isdir(games_dir()):
            return {"ok": False, "error": "Not one of your Pietatos"}

        def take():
            if self.saves_playing() == name:
                return
            saves, owner = os.path.join(games_dir(), SAVES_FOLDER), self.saves_owner()
            try:
                os.makedirs(saves, exist_ok=True)
                if owner:
                    os.chown(saves, *owner)
                with self.saves_lock:
                    if self.saves_playing() != name:
                        came = savesync.pull(saves, name, peers, owner=owner)
                        if came:
                            print(f"saves: {name} from {came}", flush=True)
            except Exception as ex:
                print(f"saves: {ex!r}", flush=True)
        threading.Thread(target=take, daemon=True, name="saves-take").start()
        return {"ok": True}

    # -- its menu (HOME) -------------------------------------------------------------------
    def game_home(self):
        """HOME in a game: its menu, or (from the menu) back to the game. False: not in a game."""
        if not self.on_game():
            return False
        if self.attract_on():                          # (a game playing by itself: back where you were)
            self.attract_stop()
            return True
        if self.view == "game":
            self.game_menu_open()
        else:
            self.game_menu_close()
        return True

    def game_menu_open(self):
        run = self.game
        if (run.state != "on" or not run.pause()) and not self.together_waiting(run):
            return                                     # (still starting, or busy: HOME again in a moment)
        bg = screen_picture()                          # the game, dimmed, behind the menu
        if bg is not None:
            from PIL import ImageEnhance, ImageOps
            s = scale()
            bg = made_fine(ImageEnhance.Brightness(ImageOps.pad(bg.convert("RGB"), (self.fb.w * s, self.fb.h * s),
                                                                color=(0, 0, 0))).enhance(0.3), s)
        self.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": bg}
        self.view = "gamemenu"
        if hasattr(self.fb, "invalidate"):
            self.fb.invalidate()
        self.dirty = True

    def game_menu_close(self):
        self.game_menu = None
        self.view = "game"
        t = self.together_of()
        if t is not None:
            t["waiting"] = False
        if self.game is not None:
            self.game.resume()
            self.game_sticks_now()

    def game_menu_items(self):
        """The game's menu: Disc only for a game on more than one; Players for one two (or more) can play;
        Screens and Touch screen for a DS game; Play on another Pietato while another of yours is on, and Play
        together for a game two can play on two of them (Link cable: a Game Boy's). (AI player: any game.) Playing
        together: not what'd put the two out of step (screens/together.py)."""
        many = self.game is not None and self.game.disc[1] > 1
        ds = self.game is not None and self.game.game.get("system") == "nds"
        together = self.game is not None and GAME_PLAYERS.get(self.game.game.get("system"), 1) > 1
        cheevos = self.game is not None and self.game.cheevos is not None
        send = self.game is not None and self.handoff_target() is not None
        two = self.together_can()                      # (Play together: Link cable, for a Game Boy game)
        return [(m[0], self.together_label()) if m[0] == "together" else m for m in GAME_MENU
                if (m[0] != "disc" or many) and (m[0] not in DS_ONLY or ds)
                and (m[0] != "players" or together) and (m[0] != "cheevos" or cheevos) and (m[0] != "send" or send)
                and (m[0] != "together" or two) and not self.together_apart(m[0])]

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
        if job == "cheevos" and self.game is not None and self.game.cheevos:
            return f"{self.game.cheevos[0]} of {self.game.cheevos[1]}"
        if job in ("send", "together"):
            target = self.handoff_target()
            return target[1] if target else ""
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
        elif job in ("send", "together"):              # (which of your other Pietatos)
            self.handoff_cycle(d)

    def press_game_menu(self, name, repeat):
        m, run = self.game_menu, self.game
        if m is None or run is None:
            self.view = "list" if run is None else "game"
            self.dirty = True
            return None
        if m.get("list"):                              # the achievements' list: up and down, then back to the menu
            lst = m["list"]
            if name in ("up", "down"):
                lst["sel"] = max(0, min(lst["sel"] + (1 if name == "down" else -1), len(lst["rows"]) - 1))
            elif name in ("left", "right"):
                lst["sel"] = max(0, min(lst["sel"] + (CHEEVO_PAGE if name == "right" else -CHEEVO_PAGE),
                                        len(lst["rows"]) - 1))
            elif name in ("a", "b") and not repeat:
                m["list"] = None
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
            twice = job in GAME_CONFIRM or (job == "together" and self.together_link())
            if twice and (waiting != job or time.monotonic() > until):
                m["confirm"] = (job, time.monotonic() + 4)
                if job == "together":                  # (where you are now isn't where it starts)
                    self.toast("The link cable starts from the game's own save, the last time you saved in it", 4)
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
        elif job == "send":
            self.game_send()
        elif job == "together":
            self.together_invite()
        elif job in GAME_CHANGE:
            self.game_change(job, 1)
        elif job == "cheevos":                         # the game's achievements, as a list over the menu
            path = shm_path(f"pitato-cheevos-{os.getpid()}.json")   # (where the game can leave it, as you)
            what, _ = run.ask(f"cheevolist {path}", ("cheevolist",), 5)
            try:
                got = json.loads(read_theirs(path, 4 << 20))
            except (OSError, ValueError):
                got = None
            try:
                os.remove(path)
            except OSError:
                pass
            if what != "cheevolist" or not isinstance(got, dict) or not got.get("list"):
                self.toast("Its achievements aren't here just now", 3)
                return
            self.game_menu["list"] = {"rows": got["list"], "sel": 0, "top": 0, "head": got.get("head", "")}
        elif job == "quit":
            t = self.together_of()
            self.game_end()
            if t is not None and not t.get("host") and not t.get("link"):
                self.toast(f"You've left {t['with']}'s game", 3)
            else:
                self.toast("Saved. It picks up there next time", 3)

    def render_game_menu(self):
        F = self.fonts
        m = self.game_menu or {"sel": 0, "confirm": (None, 0.0), "bg": None}
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        if m.get("bg") is not None:
            img.paste(m["bg"])
        g = self.game.game if self.game is not None else {"title": "", "system": ""}
        if m.get("list"):
            self.render_cheevos(img, d, m["list"], g)
            return
        menu = self.game_menu_items() if self.game is not None else GAME_MENU
        n, mw = len(menu), self.game_menu_width(d, menu, g["title"])
        rh = 38 if n <= 7 else 34                       # (a game on discs has a row more; a DS game, more again:
        rh = min(rh, max(28, (H - self.FOOTER - 98) // n))   # as many as fit)
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
        if self.game is not None and self.together_note():
            sysname = self.together_note()             # (playing together: who with)
        d.text((mx0 + 22, my0 + 46), self.fit(d, sysname, F["small"], mw - 44), font=F["small"], fill=MUTED,
               anchor="lm")
        waiting, until = m["confirm"]
        for k, (job, label) in enumerate(menu):
            ry = my0 + 64 + k * rh
            sel = k == m["sel"]
            font = F["row_b"] if sel else F["row"]
            room = mw - 24 - d.textlength(label, font=font) - 28 - 22   # (what's left of the row for its value)
            asking = waiting == job and time.monotonic() <= until
            peer = self.handoff_target() if job in PEER_JOBS and not asking else None
            gap = PEER_DOT if peer is not None and self.peer_colour(peer[0]) is not None else 0
            right, colour = self.game_value(job), MUTED
            if asking:
                right, colour = "press A again", ACCENT
            elif job in GAME_CHANGE and sel:
                arrows = d.textlength("◀    ▶", font=F["small"])
                right, colour = f"◀  {self.fit(d, right, F['small'], max(20, room - arrows - gap))}  ▶", TEXT
            elif right:
                right = self.fit(d, right, F["small"], max(20, room - gap))
            rw = (d.textlength(right, font=F["small"]) + gap) if right else 0
            self.tappable((mx0, ry - 2, mx0 + mw, ry + rh - 2), "sel", "dict", "game_menu", k)
            if sel and job in GAME_CHANGE:             # ◀ value ▶: each end, a way to change it
                vx = mx0 + mw - 22 - max(128, rw)
                half = (vx + mx0 + mw - 22) / 2
                self.tappable((vx - 22, ry - 2, half, ry + rh - 2), "keys", "left")
                self.tappable((half, ry - 2, mx0 + mw, ry + rh - 2), "keys", "right")
            if sel:
                d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                d.rounded_rectangle((mx0 + 8, ry + 10, mx0 + 12, ry + rh - 14), radius=2, fill=ACCENT)
            mid = ry + (rh - 4) / 2
            d.text((mx0 + 24, mid), label, font=font, fill=TEXT if sel else BODY, anchor="lm")
            rx = mx0 + mw - 22
            if right and gap:                          # (another Pietato: its colour's dot before its name)
                head = "◀  " if right.startswith("◀  ") else ""
                tail = right[len(head):]
                tw = d.textlength(tail, font=F["small"])
                d.text((rx, mid), tail, font=F["small"], fill=colour, anchor="rm")
                self.peer_dot(d, rx - tw - 6 - 4.5, mid, peer[0])
                if head:
                    d.text((rx - tw - gap, mid), head, font=F["small"], fill=colour, anchor="rm")
            elif right:
                d.text((rx, mid), right, font=F["small"], fill=colour, anchor="rm")
        job = menu[min(m["sel"], n - 1)][0]
        hints = [("A", "Pick again" if job == "players" else "Choose")]
        if job in GAME_CHANGE:
            hints.append(("◀▶", "Change"))
        hints.append(("B", "Back to the game"))
        self.footer(d, hints)
        self.fb.show(img)

    def game_menu_width(self, d, menu, title):
        """A game's menu: as wide as its longest row needs (its words in bold, as when it's picked, and its value as it
        shows then: ◀ value ▶, or press A again) and the game's name, GAME_MENU_W at least, and no wider than the
        screen leaves room for."""
        F = self.fonts
        need = min(d.textlength(title or "", font=F["row_b"]) + 44, GAME_MENU_TITLED)
        peers = [(name, PEER_DOT if self.peer_colour(url) is not None else 0) for url, name in self.saves_peers()]
        for job, label in menu:
            if job in PEER_JOBS:                       # (any of your other Pietatos: ◀▶ doesn't change its width)
                vw = max([d.textlength(f"◀  {name}  ▶", font=F["small"]) + dot for name, dot in peers]
                         + [d.textlength("press A again", font=F["small"])])
            else:
                value = self.game_value(job)
                shown = [value] + ([f"◀  {value}  ▶"] if job in GAME_CHANGE else []) \
                    + (["press A again"] if job in GAME_CONFIRM else [])
                vw = max((d.textlength(v, font=F["small"]) for v in shown if v), default=0)
            need = max(need, 24 + d.textlength(label, font=F["row_b"]) + (28 + vw if vw else 0) + 22)
        return int(max(GAME_MENU_W, min(need + 2, self.fb.w - 2 * GAME_MENU_EDGE)))   # (+2: never a pixel short)

    def render_cheevos(self, img, d, lst, g):
        """The game's achievements, over it: yours first (a tick), then the rest (how far along, or their points)."""
        F = self.fonts
        W, H = self.fb.w, self.fb.h
        rows = lst["rows"]
        mw = min(W - 32, 600)
        rh = 50
        fit = max(1, (H - self.FOOTER - 24 - 70) // rh)
        shown = min(fit, len(rows))
        mh = 70 + shown * rh + 8
        mx0, my0 = (W - mw) / 2, max(12, (H - self.FOOTER - mh) / 2)
        d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + mh + 2), radius=14, fill=LINE)
        d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + mh), radius=13, fill=BG)
        d.text((mx0 + 22, my0 + 24), self.fit(d, f"Achievements: {g.get('title', '')}", F["row_b"], mw - 44),
               font=F["row_b"], fill=TEXT, anchor="lm")
        d.text((mx0 + 22, my0 + 47), self.fit(d, lst.get("head", ""), F["small"], mw - 44), font=F["small"],
               fill=MUTED, anchor="lm")
        sel = max(0, min(lst["sel"], len(rows) - 1))
        top = lst["top"]
        if sel < top:
            top = sel
        elif sel >= top + shown:
            top = sel - shown + 1
        lst["top"] = top = max(0, min(top, len(rows) - shown))
        for k, i in enumerate(range(top, top + shown)):
            r = rows[i]
            ry = my0 + 66 + k * rh
            if i == sel:
                d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
            mine = bool(r.get("unlocked"))
            right = "✓" if mine else (r.get("progress") or f"{r.get('points', 0)} points")
            rw = d.textlength(right, font=F["small"])
            d.text((mx0 + 24, ry + 15), self.fit(d, str(r.get("title", "")), F["row_b"] if i == sel else F["row"],
                                               mw - 60 - rw), font=F["row_b"] if i == sel else F["row"],
                   fill=(TEXT if i == sel else BODY) if mine else MUTED, anchor="lm")
            d.text((mx0 + 24, ry + 35), self.fit(d, str(r.get("description", "")), F["small"], mw - 60 - rw),
                   font=F["small"], fill=MUTED, anchor="lm")
            d.text((mx0 + mw - 22, ry + 15), right, font=F["small"], fill=ACCENT if mine else MUTED, anchor="rm")
        if len(rows) > shown:                          # (where you are in a long list)
            t0, t1 = my0 + 70, my0 + 70 + shown * rh - 12
            d.rounded_rectangle((mx0 + mw - 7, t0, mx0 + mw - 4, t1), radius=2, fill=LINE)
            th = max((t1 - t0) * shown / len(rows), 16)
            ty = t0 + (t1 - t0 - th) * top / max(len(rows) - shown, 1)
            d.rounded_rectangle((mx0 + mw - 7, ty, mx0 + mw - 4, ty + th), radius=2, fill=BODY)
        self.footer(d, [("▲▼", "Scroll"), ("B", "Back to the menu")])
        self.fb.show(img)

    def game_hint(self, it):
        """A on a row of the Games tab."""
        if it.get("kind") == "game":
            return "Continue" if has_resume(it["src"]) else "Play"
        if it.get("kind") == "child":
            return "Play"
        if it.get("kind") == "gamedir":
            return "Open"
        return None
