"""What the web page asks for: what's on the screen, and putting things there."""
import io
import math
import os
import re
import time
import urllib.parse

from ..config import clean_name, home_dir
from ..util import classify, IMAGE_EXTS, item, title_of
from ..net import cam_address, cam_host, cam_is_local, cam_key
from ..screen import grab_screen, screen_size, slow_pi, web_sound, WEB_SOUND
from ..radio import RADIO_GENRES, RADIO_STATIONS, RADIO_TTL, rb_stations
from ..tv import CLASSIC, FILM_BADGES, FILMS, live_pick, TOON_BADGES
from ..library import LIBRARY, LISTEN_KINDS, read_streams, SCREEN_KINDS, VOLUME_STEP
from ..home import draw_icon, HOME_ICONS
from ..cameras import CAM_FOUND_FOR, edit_cameras, read_cameras
from ..voice import BOT_VOICES, VOICE_MB, voices_here
from ..bot import FRIEND_FACES
from ..www import clean_title
from ..games import BIOS_FOLDER, games_dir, save_name, SAVES_FOLDER
from .bluetooth import BT_PICKABLE
from .chromium import CHROME_MENU
from .games import GAME_MENU

SWIPE_MOST = 12              # presses a swipe (or a mouse's wheel, at once) stands for, at most
HERE_VIDEO = (".mp4", ".m4v", ".webm", ".mov", ".mkv")                          # Play here: what a browser plays
HERE_AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav")
HERE_GAMES = {"nes": "fceumm", "snes": "snes9x", "gb": "gambatte", "gbc": "gambatte", "gba": "mgba",   # ...a game's
              "genesis": "segaMD", "sms": "smsplus", "gg": "segaGG", "n64": "mupen64plus_next",   # system, as
              "ps1": "pcsx_rearmed", "nds": "melonds"}                                          # EmulatorJS has it
HERE_ONE_FILE = (".cue", ".m3u", ".gdi")    # games in more than one file: they stay on the Pi
HERE_BIOS = ("scph5501.bin", "scph5500.bin", "scph5502.bin", "scph1001.bin", "scph7001.bin")   # a PS1's, if it's there
HERE_MOST = 300              # songs handed over with the one picked, at most
WEB_HOLD = 15.0              # seconds Sound here and Mic here stay on after webui.py last says so (it does every 5)
FRAME_WAIT = 20.0            # seconds the web page's request for the next picture waits for one, at most
VIDEO_LOOK = (2.0, 4.0)      # ...while a video plays (no pictures drawn: a look at the screen), seconds between looks
                             # (a Pi Zero's: longer)


class WebScreen:
    """What the web page asks for: what's on the screen, and putting things there."""

    # -- the web page: what's on the screen, and putting things there -----------------
    def where_text(self):
        if not self.active:
            return "Terminal"
        if self.view == "home":
            return "Home screen"                   # (Home alone is the tab of that name)
        if self.view == "learn":
            return "Settings › Controller"
        if self.view == "sketch":
            return "Your drawing"
        names = []
        p = self.parent_of(self.tab)
        if p is not None:
            names.append(LIBRARY[p]["name"])
        names.append(LIBRARY[self.tab]["name"])
        if self.prog is not None:
            names.append(self.prog_name)
        stack = self.chan_stack.get(self.tab)
        if stack:
            names.append(stack[-1]["title"])
        elif self.tab_type() == "radio" and self.radio_stack:
            names.append(self.radio_stack[-1]["title"])
        elif self.tab_type() == "plex" and len(self.plex_stack) > 1:
            names += [lvl["title"] for lvl in self.plex_stack[1:]]
        elif self.tab_type() == "jellyfin" and len(self.jf_stack) > 1:
            names += [lvl["title"] for lvl in self.jf_stack[1:]]
        elif self.tab_type() == "lights" and self.lights_scenes:
            names.append("Scenes")
        elif self.tab_type() == "www" and self.view in ("chromium", "chromenu", "chromehow"):
            names.append("Chromium")
        elif self.tab_type() == "www" and self.www_on_page():
            names.append(clean_title(self.www["page"]))
        if self.view in ("photo", "pdf", "text") and self.v.get("title"):
            names.append(self.v["title"])
        elif self.view in ("game", "gamemenu") and self.game is not None:
            names.append(self.game.game["title"])
        return " › ".join(names)

    def web_state(self):
        """(This runs on the web page's thread: it only reads, and tries again if the main loop
        changed something under it.)"""
        for _ in range(3):
            try:
                return self.web_state_now()
            except (RuntimeError, IndexError, KeyError, AttributeError, TypeError):
                time.sleep(0.02)
        return self.web_state_now()

    def web_state_now(self):
        playing = None
        cur, meta, kind = self.cur, self.meta, self.kind
        if self.proc and cur:
            length = meta.get("length") or cur.get("dur") or 0
            pos = self.plex_now() if kind == "plex" else self.pos
            playing = {"title": cur.get("title", ""), "sub": cur.get("sub", ""),
                       "src": cur.get("src", ""), "kind": kind,
                       "pos": round(max(pos or 0, 0), 1), "length": round(length or 0, 1),
                       "paused": self.paused, "song": meta.get("song") or meta.get("title") or ""}
        pads = list(self.pads.by_path.values()) if self.pads else []
        return {"mode": "media" if self.active else "terminal", "view": self.view,
                "where": self.where_text(), "playing": playing, "volume": self.volume,
                "screen": self.setting("screen"), "video": self.proc_owns_screen(),
                "frame": getattr(self.fb, "frames", 0) if self.active else -1,
                "controllers": [{"name": p.dev.name, "kind": p.kind, "learned": p.learned, "swap": p.swapped,
                                 "path": p.path} for p in pads],
                "learning": self.learn_status(),
                "size": list(self.screen_dims() if self.fb else screen_size()),
                "canvas": [self.fb.w, self.fb.h] if self.fb else None,   # (what the menus, and drawings, are drawn at)
                "plex": self.plex.signed_in, "msg": self.msg, "kb": self.web_kb()}

    def web_kb(self):
        """The box to type in that's on the screen (its title, and what's in it so far), for the web page to type
        in too; None when there isn't one."""
        kb = self.kb if self.active and self.view == "keys" else None
        if not kb:
            return None
        return {"title": kb.get("title", ""), "text": kb.get("text", ""), "limit": kb.get("limit", 60)}

    def web_screen(self, after=None, wait=0.0):
        """(bytes, type): the menus exactly as drawn, or a snapshot of the real screen while a
        video plays. Never the terminal: that stays on the Pi. after: the picture the web page has already (its
        number): this waits for the next (wait: seconds, at most)."""
        shot = self.web_shot(after, wait)
        return shot and shot[:2]

    def web_shot(self, after=None, wait=0.0):
        """(bytes, type, the number of the menus' last picture): web_screen's, and which picture it is (a video's: a
        look at the screen as it is, a JPEG, with the number of the menus' last picture still)."""
        if after is not None:
            self.web_frame_wait(after, wait)
        fb = self.fb
        if not self.active:
            return None
        frame = getattr(fb, "frames", 0) if fb is not None else 0
        if self.active and fb is not None and not self.proc_owns_screen() and getattr(fb, "last", None):
            key = ("menus", frame)
            if self.shot[0] == key:
                return self.shot[1], self.shot[2], frame
            buf = io.BytesIO()
            fb.last.save(buf, "PNG", compress_level=1)    # quick to make on a Pi Zero
            out = (buf.getvalue(), "image/png")
        else:
            key = None
            img = grab_screen(640)
            buf = io.BytesIO()
            if self.proc_owns_screen():
                img.save(buf, "JPEG", quality=82)
                out = (buf.getvalue(), "image/jpeg")
            else:
                img.save(buf, "PNG")
                out = (buf.getvalue(), "image/png")
        self.shot = (key, out[0], out[1])
        return out[0], out[1], frame

    def web_frame_wait(self, after, wait):
        """(The control server's thread.) Till the screen's picture isn't the one numbered after (the web page's
        already), or wait seconds: a video's plays meanwhile, so it's looked at every few seconds instead."""
        try:
            after, wait = int(after), max(0.0, min(float(wait), FRAME_WAIT))
        except (TypeError, ValueError, OverflowError):
            return
        start = time.monotonic()
        while time.monotonic() - start < wait:
            fb = self.fb
            if not self.active or fb is None or getattr(fb, "frames", None) != after:
                return
            if self.proc_owns_screen() and time.monotonic() - start >= VIDEO_LOOK[1 if slow_pi() else 0]:
                return
            time.sleep(0.03)

    # -- the web page's copy of the screen: tapped, swiped, scrolled, and typed under ----------------------------
    def web_touch(self, cmd):
        """A tap, a swipe or a mouse's wheel on the web page's copy of the screen, or what's typed under it:
        ([the buttons it stands for, to be pressed as the remote's are], the answer). Some it does itself: a row
        picked, a list scrolled, words typed."""
        c = cmd.get("cmd")
        if self.view == "update":
            return [], {"error": "The Pi is updating. It restarts when it's done"}
        if c == "type":
            return [], self.web_type(cmd.get("text"), cmd.get("enter") is True)
        if self.fb is None:
            return [], {"error": "There's no screen"}
        try:
            x, y = float(cmd.get("x") or 0), float(cmd.get("y") or 0)   # (shares of the picture, 0 to 1; a wheel's:
        except (TypeError, ValueError):                                 # y, its notches)
            return [], {"error": "Bad request"}
        if not (math.isfinite(x) and math.isfinite(y)):
            return [], {"error": "Bad request"}
        W, H = self.fb.w, self.fb.h
        if c == "tap":
            return (self.web_tap(x * W, y * H) if 0 <= x <= 1 and 0 <= y <= 1 else []), {"ok": True}
        if c == "swipe":
            return self.web_swipe(max(-1.0, min(1.0, x)) * W, max(-1.0, min(1.0, y)) * H), {"ok": True}
        if c == "scroll":
            return self.web_scroll(max(-SWIPE_MOST, min(SWIPE_MOST, round(y)))), {"ok": True}
        return [], {"error": "Unknown request"}

    def taps_now(self):
        """Where a tap does what on the screen's picture now ([] if that picture wasn't drawn as the menus are: a
        video's on, or one was put up some other way)."""
        if self.proc_owns_screen() or self.taps_at is None or self.taps_at != getattr(self.fb, "frames", None):
            return []
        return self.taps

    def web_tap(self, x, y):
        """A tap at x, y (the menus' pixels): what's there does what it does (draw.py put down where things are, as
        it drew them); anywhere else, what a tap does on that page, if anything."""
        for (x0, y0, x1, y1), what in reversed(self.taps_now()):
            if x0 <= x < x1 and y0 <= y < y1:
                return self.tap_do(what)
        return self.tap_elsewhere(x, y)

    def tap_do(self, what):
        """What a place on the screen does when it's tapped (draw.py's tappable put it down): [buttons to press], or
        [] when it's done here."""
        kind, args = what[0], what[1:]
        if kind == "keys":                             # a button along the bottom, or ◀ ▶ by a value
            return list(args)
        if kind == "sel":                              # a row, a tile, an app: picked, or opened if it was
            return self.tap_pick(*args)
        if kind in ("tab", "tabs") and self.view == "list":
            vis = self.visible_tabs()
            here = vis.index(self.strip_tab())
            step = args[0] if kind == "tabs" else vis.index(args[0]) - here if args[0] in vis else 0
            if step:
                self.switch_tab(step)
                self.dirty = True
            return []
        if kind == "kb" and self.view == "keys" and self.kb:   # a key on the keyboard on the screen
            self.kb["r"], self.kb["c"] = args
            return ["a"]
        if kind == "www" and self.view == "list" and self.tab_type() == "www" and self.www_on_page():
            if args[0] < len(self.www["targets"]):     # a link, a box or a button on a page: opened
                self.www["focus"] = args[0]
                return ["a"]
            return []
        if kind == "bt" and self.view == "list" and self.tab_type() == "settings" and self.set_page == "bluetooth":
            rows = self.bt_rows()
            k = args[0]
            if k < len(rows) and rows[k][0] in BT_PICKABLE:
                if self.bt_sel(rows) == k:
                    return ["a"]
                self.bt_choose(rows, k)
                self.dirty = True
            return []
        return []

    def tap_pick(self, owner, key, k):
        """A row tapped (a tile, an app...): picked, as ▲▼ would; tapped again once it's picked: A. owner: where
        what's picked is kept: 'sels' (key: a tab's list), 'attr' (key: one of these, a number), 'dict' (key: one
        of these, a menu with its 'sel')."""
        n = self.sel_rows(owner, key)
        if n is None or not 0 <= k < n:
            return []
        if owner == "sels":
            if key != self.tab or self.view != "list":
                return []
            if self.sels.get(key, 0) == k:
                return ["a"]
            self.sels[key] = k
            self.confirm = (None, 0.0)
        elif owner == "attr":
            if (getattr(self, key, 0) or 0) % n == k:
                return ["a"]
            setattr(self, key, k)
        else:
            m = getattr(self, key)
            if m.get("sel", 0) % n == k:
                return ["a"]
            m["sel"] = k
            if "confirm" in m:
                m["confirm"] = (None, 0.0)
        self.dirty = True
        return []

    def sel_rows(self, owner, key):
        """How many rows the list a row was tapped in has now (None: it isn't up)."""
        try:
            if owner == "sels":
                return len(self.tab_items(key))
            if owner == "attr":
                rows = {"set_sel": self.settings_rows, "wx_sel": self.wx_rows, "home_sel": self.home_apps,
                        "cam_sel": self.cam_rows, "fin_sel": self.fin_rows}[key]
            elif isinstance(getattr(self, key, None), dict):
                rows = {"game_menu": lambda: self.game_menu_items() if self.game is not None else GAME_MENU,
                        "chrome_menu": lambda: CHROME_MENU, "ha_menu": self.ha_rows,
                        "cam_menu": self.cam_menu_rows}[key]
            else:
                return None
            return len(rows())
        except (KeyError, AttributeError, TypeError, IndexError, ValueError):
            return None

    def tap_elsewhere(self, x, y):
        """A tap where nothing's put down: on a video, pause or play; on a picture or a document, its left third
        back and its right third on; on a help page, closed (any button closes it)."""
        if self.proc_owns_screen():
            return ["a"] if self.proc and self.kind in SCREEN_KINDS and not self.chromium_shown() else []
        if self.view == "help":
            return ["a"]
        if self.view in ("photo", "pdf", "text"):
            third = self.fb.w / 3
            return ["left"] if x < third else ["right"] if x >= 2 * third else []
        return []

    def media_on(self):
        """A video on the screen, or Now playing: ▲▼ are the volume, ◀▶ go back and on."""
        return ((self.proc_owns_screen() and bool(self.proc) and self.kind in SCREEN_KINDS)
                or (self.view == "now" and self.kind in LISTEN_KINDS))

    def web_swipe(self, dx, dy):
        """A finger (or a mouse, held down) moved dx, dy across the web page's copy of the screen (the menus'
        pixels): the page moves with it. Up and down: a list scrolls; a video's (or Now playing's) volume, up
        louder. Across: ◀▶, the way the finger went for a video (on further), the other way for the rest (the next
        picture, page, or a screenful on comes in from the right)."""
        if self.proc_owns_screen() and not self.media_on():
            return []                                  # (a game: its buttons are the remote's)
        if abs(dx) > abs(dy):
            if self.media_on():
                return ["right" if dx > 0 else "left"]
            return ["right" if dx < 0 else "left"]
        if self.media_on():
            return ["up" if dy < 0 else "down"] * min(4, max(1, round(abs(dy) / 60)))
        rows = max(1, round(abs(dy) / self.ROW_H))
        if self.view == "list" and self.tab_type() == "www" and self.www_on_page():
            self.www_scroll(-dy)                       # (a page: as far as the finger went)
            return []
        return self.web_scroll(rows if dy < 0 else -rows)

    def web_scroll(self, n):
        """The wheel turned n notches (more than 0: down, on), or a swipe n rows' worth: a list scrolls that far,
        its row picked staying where it is on the screen; elsewhere, ▲ or ▼ that many times."""
        n = max(-SWIPE_MOST, min(SWIPE_MOST, int(n)))
        if not n or (self.proc_owns_screen() and not self.media_on()):
            return []
        if self.view == "list" and self.tab_type() == "www" and self.www_on_page():
            self.www_scroll(n * self.ROW_H)
            return []
        taps = self.taps_now()
        if (self.view == "list" and self.tab_type() != "photos"
                and any(w[:3] == ("sel", "sels", self.tab) for _, w in taps)):
            self.list_scroll(n)
            return []
        if self.view == "list" or self.view in ("gamemenu", "chromenu"):
            picked = next((w[1:3] for _, w in reversed(taps) if w[0] == "sel" and w[1] in ("attr", "dict")), None)
            if picked and picked != ("attr", "home_sel"):
                self.list_move(*picked, n)
                return []
        return ["down" if n > 0 else "up"] * abs(n)

    def list_scroll(self, n):
        """A tab's list moved n rows on (back, less than 0), the row picked going with it, so it stays where it is on
        the screen (at an end, or if the whole list fits: the pick goes on by itself)."""
        count = len(self.tab_items())
        if not count:
            return
        rows = self.visible_rows()
        top = self.tops.get(self.tab, 0)
        new_top = max(0, min(top + n, max(count - rows, 0)))
        sel = self.sels.get(self.tab, 0) + n
        self.sels[self.tab] = max(new_top, min(sel, min(new_top + rows, count) - 1))
        self.tops[self.tab] = new_top
        self.confirm = (None, 0.0)
        self.dirty = True

    def list_move(self, owner, key, n):
        """A page of settings (a menu) moved n rows on: the pick, never round past the end."""
        count = self.sel_rows(owner, key)
        if not count:
            return
        if owner == "attr":
            setattr(self, key, max(0, min((getattr(self, key, 0) or 0) % count + n, count - 1)))
        else:
            m = getattr(self, key)
            m["sel"] = max(0, min(m.get("sel", 0) % count + n, count - 1))
            if "confirm" in m:
                m["confirm"] = (None, 0.0)
        self.dirty = True

    def web_type(self, text, enter):
        """Typed on the web page, into the box on the screen: what's in it now (and Done, with enter). It's the web
        page's typing, as the remote's would be (a prompt for your coding agent isn't sent from it)."""
        kb = self.kb
        if not (self.active and self.view == "keys" and kb):
            return {"error": "There's no box to type in on the screen"}
        if not isinstance(text, str):
            return {"error": "Bad request"}
        kb["text"] = "".join(ch for ch in text if ch.isprintable())[:kb.get("limit", 60)]
        if kb.get("local"):
            kb["remote"] = True                        # (the web page had a hand in it)
        self.dirty = True
        if enter:
            self.keyboard_key("done")
        return {"ok": True}

    # -- Play here: what's picked on the web page's copy of the screen, played on the phone or computer instead ----
    def here_begin(self, here):
        """A request from the web page, with Play here on (or off): what's played meanwhile goes to it."""
        self.web_here, self.web_handoff, self.web_said = bool(here), None, ""

    def here_end(self, out):
        """The request done: the answer, with what's to play on the phone or computer ("play"), or why it played on the
        Pi after all ("note")."""
        handoff, said = self.web_handoff, self.web_said
        self.web_here, self.web_handoff, self.web_said = False, None, ""
        if isinstance(out, dict) and "error" not in out:
            if handoff:
                out = dict(out, play=handoff)
            elif said:
                out = dict(out, note=said)
        return out

    @staticmethod
    def home_rel(path):
        """A file's place in your home folder ("Videos/a.mp4"), as the web page hands files out; None outside it (or in
        a hidden folder, which the web page never hands out)."""
        try:
            real, home = os.path.realpath(path), os.path.realpath(home_dir())
        except (OSError, ValueError, TypeError):
            return None
        if not real.startswith(home + os.sep):
            return None
        rel = os.path.relpath(real, home)
        return rel if not any(p.startswith(".") for p in rel.split(os.sep)) else None

    def here_url(self, it):
        """Where the phone or computer gets a video, a song or a station to play it itself: a file of yours (the web page
        hands it out), a cartoon or a film from archive.org, a station's stream. None: it plays on the Pi."""
        src, kind = str(it.get("src") or ""), it.get("kind")
        if kind == "video" and src.startswith("ia:") and "/" in src[3:]:
            ident, name = src[3:].split("/", 1)
            return "https://archive.org/download/" + urllib.parse.quote(ident) + "/" + urllib.parse.quote(name)
        if kind == "radio" and re.match(r"https?://", src):
            return src
        if kind in ("video", "audio") and src.startswith("/") and not self.is_net(src) and self.web_may_see(src):
            rel = self.home_rel(src)
            if rel and os.path.splitext(src)[1].lower() in (HERE_VIDEO if kind == "video" else HERE_AUDIO):
                return "/api/home/" + urllib.parse.quote(rel)
        return None

    def here_take(self, queue, i):
        """Play here: queue[i] (and the rest of its kind with it, a song's album) handed to the phone or computer the web
        page's on, to play there: True. False: it plays on the Pi (one a browser can't play, or Plex's: why's noted)."""
        if not getattr(self, "web_here", False):
            return False
        it = queue[i]
        kind = it.get("kind")
        url = self.here_url(it)
        if url is None:
            src = str(it.get("src") or "")
            self.web_said = ("Plex and Jellyfin play on the Pi" if kind in ("plexvideo", "jfvideo") else
                             "Live channels play on the Pi" if kind == "live" else
                             "That one plays on the Pi: a browser can't play it"
                             if src.startswith("/") and self.home_rel(src) else "That one plays on the Pi")
            return False
        rows, at = [], 0
        for x in queue:
            if x is not it and x.get("kind") != kind:
                continue
            u = url if x is it else self.here_url(x)
            if u:
                if x is it:
                    at = len(rows)
                rows.append({"title": x.get("title", ""), "sub": x.get("sub", ""), "url": u})
        first = max(0, min(at - HERE_MOST // 2, len(rows) - HERE_MOST))
        rows = rows[first:first + HERE_MOST]
        self.web_handoff = {"kind": kind, "items": rows, "index": at - first,
                            "start": round(self.resume_at(it) or 0, 1) if kind == "video" else 0}
        return True

    def here_take_game(self, it):
        """Play here: a game, handed to the phone or computer the web page's on to play in its browser (EmulatorJS, with
        your save from here, which it sends back as you play): True. False: it plays on the Pi (why's noted)."""
        if not getattr(self, "web_here", False):
            return False
        src = str(it.get("src") or "")
        core = HERE_GAMES.get(it.get("system"))
        rel = self.home_rel(src) if src.startswith("/") and not self.is_net(src) else None
        if not core:
            self.web_said = "That kind of game plays on the Pi"
            return False
        if not rel or os.path.splitext(src)[1].lower() in HERE_ONE_FILE:
            self.web_said = "That game plays on the Pi" + (": it's in more than one file" if rel else "")
            return False
        bios = ""
        if it.get("system") == "ps1":
            folder = os.path.join(games_dir(), BIOS_FOLDER)
            found = next((n for n in HERE_BIOS if os.path.isfile(os.path.join(folder, n))), None)
            bios = (self.home_rel(os.path.join(folder, found)) or "") if found else ""
        self.web_handoff = {"kind": "game", "title": it.get("title", ""), "core": core, "rom": rel, "bios": bios,
                            "save": SAVES_FOLDER + "/" + save_name(src) + ".srm"}
        return True

    def web_icon(self, name, size=96):
        """The home screen's icon for an app, for the web page (None: no such app)."""
        if name not in HOME_ICONS:
            return None
        size = min((48, 64, 96, 112, 128, 192), key=lambda x: abs(x - int(size)))
        if (name, size) not in self.web_icons:
            buf = io.BytesIO()
            draw_icon(name, size, card=True).save(buf, "PNG")
            self.web_icons[(name, size)] = buf.getvalue()
        return self.web_icons[(name, size)]

    def web_catalog(self):
        """Everything the web page can put on the screen without asking the internet."""
        apps = []
        for name, _ in self.home_apps():
            col, about = HOME_ICONS.get(name, ((76, 114, 154), ""))
            apps.append({"name": name, "color": "#%02x%02x%02x" % col, "about": about})
        group = next((t for t in LIBRARY if t["name"] == "TV"), {})
        tv = [{"name": n, "about": next((t.get("about", "") for t in LIBRARY if t["name"] == n), "")}
              for n in group.get("children", [])]

        def shelf(lists, badges):
            return [{"folder": f, "badge": badges.get(f, ""),
                     "items": [[t, y, f"ia:{i}/{n}"] for t, y, i, n in rows]} for f, rows in lists.items()]
        radio = LIBRARY[self.tab_index("radio")]
        streams = LIBRARY[self.tab_index("streams")]
        return {"apps": apps, "tv": tv,
                "cartoons": shelf(CLASSIC, TOON_BADGES), "films": shelf(FILMS, FILM_BADGES),
                "radio": {"mine": [[it["title"], it.get("sub", ""), it["src"]]
                                   for it in read_streams(radio["files"], kind="radio")],
                          "stations": [list(x) for x in RADIO_STATIONS],
                          "genres": [g[0] for g in RADIO_GENRES]},
                "streams": [[it["title"], it.get("sub", ""), it["src"]] for it in read_streams(streams["files"])],
                "plex": self.plex.signed_in}

    def web_channels(self, what):
        """Plex's free Live TV channels of a kind (anime, toons, movies, news, sports)."""
        if what not in ("anime", "toons", "movies", "news", "sports"):
            return {"error": "No such list"}
        if not self.plex.signed_in:
            return {"error": "plex"}
        try:
            chans = self.live_list()
        except Exception:
            return {"error": "Plex didn't answer"}
        return {"channels": [[c["title"], c["genre"], "plexlive:" + c["key"]]
                             for c in chans if live_pick(what, c)]}

    def web_radio(self, genre=None, query=None):
        """Stations from Radio Browser: a genre's busiest, or a search by name."""
        tags = next((t for g, _, t in RADIO_GENRES if g == genre), None)
        if genre and tags is None:
            return {"error": "No such genre"}
        key = genre or "search:" + (query or "").strip().lower()
        hit = self.web_radio_cache.get(key)
        if not (hit and time.time() - hit[0] < RADIO_TTL):
            try:
                found = rb_stations(tags=tags or (), name=(query or "").strip())
            except Exception:
                return {"error": "Radio Browser didn't answer"}
            hit = (time.time(), [[it["title"], it.get("sub", ""), it["src"], it.get("uuid", ""), it.get("logo", "")]
                                 for it in found])
            self.web_radio_cache[key] = hit
        return {"stations": hit[1]}

    def web_item(self, r):
        """A row the web page sent, as something to play (only kinds that can be played)."""
        if not isinstance(r, dict):
            return None
        src, title, sub = str(r.get("src") or ""), str(r.get("title") or "")[:160], str(r.get("sub") or "")[:80]
        if src.startswith("ia:") and "/" in src[3:]:
            return item(src, title or src, "video", src, sub=sub)
        if src.startswith("plexlive:"):
            return dict(item(src, title or "Channel", "live", src, sub=sub), thumb=None, ptype="channel")
        if re.match(r"https?://", src):
            if r.get("kind") == "radio":
                it = item("url:" + src, title or src, "radio", src, sub=sub)
                if r.get("uuid"):
                    it["uuid"] = str(r["uuid"])[:64]
                return it
            return item("stream:" + src, title or src, "live", src, sub=sub)
        if src.startswith("/") and self.web_may_see(src) and os.path.isfile(src):
            kind = classify(src)
            if kind in ("video", "audio"):
                return item(src, title_of(src), kind, src)
        return None

    def web_ready(self):
        """Media mode on, with nothing half-open in the way."""
        if not self.active:
            self.enter()
        if not self.active:
            return False
        if self.learn:
            self.cancel_learn("")
        if self.view == "keys":
            self.close_keyboard(False)
        if self.view in ("photo", "pdf", "text", "wait"):
            self.close_viewer()
        self.prog_stop()                               # (the Simulator's cmatrix and the rest: it stops)
        if self.proc_owns_screen() or self.game is not None:
            self.stop()                                # (a video, or a game: kept for next time)
        return True

    def web_tab(self, name):
        i = next((k for k, t in enumerate(LIBRARY) if t["name"] == name), None)
        if i is not None and LIBRARY[i]["type"] == "prog":        # (no page of its own: the Simulator, and it)
            self.web_tab(LIBRARY[i]["parent"])
            self.prog_start(LIBRARY[i]["prog"])
            return i
        if i is not None:
            self.go_home()
            self.tab, self.view = i, "list"
            self.load_tab(i)
            self.dirty = True
        return i

    def web_command(self, cmd):
        """What the web page asked for, done between button presses."""
        c = cmd.get("cmd")
        if self.view == "update":                      # (nothing goes on the screen over the update)
            return {"error": "The Pi is updating. It restarts when it's done"}
        if c == "open":
            app = str(cmd.get("app") or "")
            if app == "Terminal":
                self.leave()
                return {"ok": True}
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            if cmd.get("home") is True:                 # the home screen (the app called Home is a tab)
                self.go_home()
                return {"ok": True}
            if app == "Coder":                         # (the Bot at work had its own app once)
                self.bot_open("work")
                return {"ok": True}
            if self.web_tab(app) is None:
                return {"error": "No such app"}
            return {"ok": True}
        if c == "play":
            rows = cmd.get("items")
            rows = rows[:600] if isinstance(rows, list) else []
            try:
                want = int(cmd.get("index") or 0)
            except (TypeError, ValueError):
                want = 0
            todo, i = [], None
            for k, r in enumerate(rows):             # (the one asked for, wherever it lands)
                it = self.web_item(r)
                if it:
                    if k == want:
                        i = len(todo)
                    todo.append(it)
            if not todo or i is None:
                return {"error": "That can't be played"}
            if not self.web_ready():
                return {"error": "There's no screen to play it on"}
            if self.web_tab(str(cmd.get("where") or "")) is None and self.view == "home":
                self.view = "list"
            self.play(todo, i)
            return {"ok": True, "title": todo[i]["title"]}
        if c == "show":
            return self.web_show(str(cmd.get("path") or ""))
        if c == "player":
            return self.web_player(str(cmd.get("do") or ""))
        if c == "learn":
            if cmd.get("stop"):
                self.cancel_learn()
                return {"ok": True}
            if not self.web_ready():
                return {"error": "There's no screen"}
            self.web_tab("Settings")
            self.start_learn()
            return {"ok": True}
        if c == "reset_pads":
            if self.pads:
                self.pads.forget()
            return {"ok": True}
        if c == "pad_swap":                            # A and B swapped on one of them (on), or back
            pad = self.pads.by_path.get(str(cmd.get("path") or "")) if self.pads else None
            if pad is None:
                return {"error": "That controller isn't plugged in"}
            self.pads.swap(pad.ident, bool(cmd.get("on")))
            self.dirty = True                          # (Settings shows it, if it's open)
            return {"ok": True}
        if c == "camera":
            return self.web_camera(cmd)
        if c == "friend":
            return self.web_friend_do(cmd)
        if c == "settings":                            # (Settings on the web page: one changed)
            return self.web_settings_do(cmd)
        if c == "sketch":                              # (opened already, by the control server)
            return self.web_sketch(cmd.get("image"))
        if c == "websound":                            # (webui.py: a page plays the Pi's sound, still; or stopped)
            return self.web_sound_set(cmd.get("on") is True)
        if c == "webmic":                              # (...a page's microphone is coming in, still; or stopped)
            return self.web_mic_set(cmd.get("on") is True)
        return {"error": "Unknown request"}

    # -- Sound here and Mic here: a web page's speaker and microphone, the Pi's (webui.py keeps saying so) ------------
    def web_sound_set(self, on):
        """Sound here, on for a while more (or off): the Pi's sound goes to the web page, through the Loopback card. What's
        playing moves there, and back, as it does to Bluetooth headphones (sound_tick)."""
        was = web_sound()
        WEB_SOUND["until"] = time.monotonic() + WEB_HOLD if on else 0.0
        if was != on:
            self.sound_look = 0.0                      # (sound_tick: now)
            if self.active and not self.proc_owns_screen():
                self.toast("Sound through the web page" if on else "Sound through the Pi again", 3)
        return {"ok": True}

    def web_mic_set(self, on):
        """Mic here, on for a while more (or off): the bot hears the web page's microphone instead of the Pi's."""
        self.web_mic_until = time.monotonic() + WEB_HOLD if on else 0.0
        self.web_mic_tick()
        return {"ok": True, "listens": self.bot_listens()}

    def web_mic_tick(self):
        """Mic here, come or gone (or not said for a while: webui.py stopped): the bot listens with that microphone."""
        on = time.monotonic() < self.web_mic_until
        if on == getattr(self, "web_mic_was", False):
            return
        self.web_mic_was = on
        self.listen_now()                              # (bot_mic says which)
        if self.active and self.bot_listens() and not self.proc_owns_screen():
            self.toast("The bot hears you through the web page" if on else "The bot hears the Pi's microphone again", 3)

    # -- the web page's Bluetooth: looked at while it asks (its own threads; not the screen's) -------
    def web_bluetooth(self):
        self.bt.watch("web")
        return self.bt.snapshot()

    def web_bluetooth_do(self, cmd):
        self.bt.watch("web")
        return self.bt.do(cmd.get("do"), cmd.get("addr"))

    # -- the web page's cameras and bot -------------------------------------------
    def web_cameras(self):
        """Your cameras and the ones heard on the network. (On the web page's thread: it reads, and
        asks no camera anything.)"""
        cam = self.camera
        cam.listen()
        cams = cam.listed(LIBRARY[self.tab_index("camera")]["files"])
        hosts = {cam_host(c["addr"]) for c in cams}

        def row(addr, name):
            k = cam_key(addr)
            got = cam.known.get(k) or cam.found.get(k) or {}
            th, miss = cam.thumbs.get(k), cam.missing.get(k, 0)
            return {"addr": addr, "name": name or got.get("name") or cam_host(addr) or addr, "usb": cam.is_usb(addr),
                    "kind": cam.kind_shown(addr, got.get("server", "")), "turn": cam.turn_of(addr),
                    "steers": cam.may_steer(addr), "flip": cam.flipped(addr), "flipv": cam.flipped(addr, "y"),
                    "reach": "no" if miss and (not th or miss > th[2]) else "yes" if th else ""}
        found = [row(f["addr"], f["name"]) for f in list(cam.found.values())
                 if time.time() - f["seen"] <= CAM_FOUND_FOR and cam_host(f["addr"]) not in hosts]
        return {"cameras": [row(c["addr"], c["name"]) for c in cams],
                "found": sorted(found, key=lambda f: f["name"].lower()),
                "showing": cam.addr if self.on_camera_page() else "",
                "bot": self.friend.ready(), "voice": bool(self.bot_voice())}

    def web_camframe(self, addr):
        """A picture from one of your cameras, or one heard on the network (no other address)."""
        cam = self.camera
        k = cam_key(addr)
        cams = cam.listed(LIBRARY[self.tab_index("camera")]["files"])
        if not addr or (k not in {cam_key(c["addr"]) for c in cams} and k not in cam.found):
            return None
        got = cam.snapshot(addr, max_age=1.5)
        return cam.turned_file(addr, got[0], got[2]) if got else None

    def web_camera(self, cmd):
        cam = self.camera
        do = str(cmd.get("do") or "")
        addr = cam_address(str(cmd.get("addr") or ""))
        if not addr:
            return {"error": "That isn't an address. Try 192.168.1.50, or a link"}
        files = LIBRARY[self.tab_index("camera")]["files"]
        cam.cams = cam.listed(files)
        cam.patterns = cam.patterns or files
        if do == "add":
            if cam.mine(addr):
                return {"error": "That camera is already in your list"}
            if cam_is_local(addr):                    # (the Pi's own services stay its own)
                return {"error": "Add a camera by its address on your network, like 192.168.1.50"}
            try:
                edit_cameras(add=addr, name=clean_name(cmd.get("name")))
            except OSError as ex:
                return {"error": f"Couldn't save it ({ex.strerror or ex})"}
            cam.cams = cam.listed(files)
            self.dirty = True
            return {"ok": True}
        if do == "remove":
            if not cam.mine(addr):
                return {"error": "That camera isn't in your list"}
            if cam.is_usb(addr) and not any(cam_key(c["addr"]) == cam_key(addr) for c in read_cameras(files)):
                return {"error": "It's plugged into the Pi: unplug it to take it off"}
            self.camera_remove(addr)
            return {"ok": True}
        if do == "rotate":                            # its picture a quarter turn clockwise (one on its side)
            if not cam.mine(addr):
                return {"error": "That camera isn't in your list"}
            return {"ok": True, "turn": self.camera_turn(addr)}
        if do == "flip":                              # one that turns the wrong way: left and right swapped, or back
            if not cam.mine(addr):                    # (axis "y": up and down)
                return {"error": "That camera isn't in your list"}
            on = self.camera_flip(addr, "y" if cmd.get("axis") == "y" else "x")
            return {"error": "This camera doesn't turn"} if on is None else {"ok": True, "flip": on}
        if do == "show":
            if not cam.mine(addr) and cam_key(addr) not in cam.found:
                return {"error": "That camera isn't in your list"}
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            self.web_tab("Camera")
            self.camera_open(addr)
            return {"ok": True}
        if do == "describe":                          # the bot says what it sees (on the Pi, out loud)
            if not cam.mine(addr):
                return {"error": "That camera isn't in your list"}
            self.friend.load(self.friend_files())
            if not self.friend.ready():
                return {"error": "Set up your bot first, on the Bot tab"}
            since = time.time()
            ok, why = self.camera_describe(addr)
            return {"ok": True, "since": since} if ok else {"error": "It's still thinking about the last one"
                                                             if why.startswith("Still") else why}
        return {"error": "Unknown request"}

    def web_friend(self):
        """The bot: its settings, the conversation, whether it's thinking or speaking, its voice."""
        fr = self.friend
        fr.load(self.friend_files())
        face, mood = fr.face() if fr.ready() else (FRIEND_FACES["sleepy"], "sleepy")
        addr = self.friend_camera()
        pics = os.path.realpath(os.path.join(home_dir(), "Pictures"))

        def photo(path):                               # where a picture is among your Pictures
            real = os.path.realpath(path) if isinstance(path, str) and path else ""
            return {"folder": "pictures", "path": os.path.relpath(real, pics)} \
                if real.startswith(pics + os.sep) else None
        return {"ready": fr.ready(), "server": fr.server, "model": fr.model, "name": fr.name,
                "chatter": fr.chatter(), "busy": fr.busy, "doing": fr.doing, "face": face, "mood": mood,
                "camera": self.camera.name_of(addr) if addr else "", "sees": fr.sees(),
                "log": [{"who": x["who"], "text": x["text"], "t": x["t"], "kind": x.get("kind", ""),
                         "pic": x.get("pic", ""), "photo": photo(x.get("photo"))}
                        for x in list(fr.log)],
                "models": list(fr.models) if fr.server and fr.models_at == fr.server else [],
                "modelsStatus": fr.models_status, "showing": self.on_friend_page(), "voice": self.web_voice(),
                "work": self.web_work()}

    def web_work(self):
        """Your coding agent, as the Bot at work sees it."""
        s = self.coder.snapshot(time.monotonic())
        title, sub = self.coder_status(s)
        return {"heard": bool(s["heard"]), "pose": s["anim"], "title": title, "sub": sub,
                "showing": self.on_coder_page()}

    def web_voice(self):
        here = voices_here()
        ours = [i for i, _, _ in BOT_VOICES]
        job = self.voice.job
        return {"id": self.bot_voice(), "speak": self.bot_speaks(), "speaking": self.voice.speaking,
                "status": self.voice.status(), "getting": job["id"] if job else "", "can": self.voice.supported(),
                "piper": self.voice.have_piper(), "mb": VOICE_MB,
                "list": [{"id": i, "name": n, "note": note, "here": i in here} for i, n, note in BOT_VOICES]
                + [{"id": v, "name": v, "note": "", "here": True} for v in sorted(here) if v not in ours]}

    def web_friend_do(self, cmd):
        fr = self.friend
        fr.load(self.friend_files())
        do = str(cmd.get("do") or "")
        if do in ("say", "remark", "aloud", "photo") and not fr.ready():
            return {"error": "Set up your bot first"}
        if do == "say":
            text = " ".join(str(cmd.get("text") or "").split())[:400]
            pic = cmd.get("picture")                   # one of your pictures (webui.py says where)
            if pic is not None and not (isinstance(pic, str) and pic.startswith("/") and self.web_may_see(pic)
                                        and os.path.splitext(pic)[1].lower() in IMAGE_EXTS and os.path.isfile(pic)):
                return {"error": "That picture can't be sent"}
            if not text and pic is None:
                return {"error": "Say something first"}
            since = time.time()                        # (its answer comes after this: the Draw tab waits for it)
            if not fr.say(text, picture=pic):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True, "since": since}
        if do == "photo":
            if not self.friend_camera():
                return {"error": "There's no camera. Add one on the Camera tab"}
            if not fr.say("Take a picture"):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True}
        if do == "remark":
            if not fr.remark(self.friend_topic()):
                return {"error": "It's still thinking about the last one"}
            return {"ok": True}
        if do == "clear":
            fr.clear()
            return {"ok": True}
        if do == "aloud":
            ok, why = self.say_aloud()
            return {"ok": True} if ok else {"error": why}
        if do == "hush":
            self.voice.stop()
            return {"ok": True}
        if do == "models":
            fr.fetch_models()
            return {"ok": True}
        if do in ("open", "work"):
            if not self.web_ready():
                return {"error": "There's no screen to show it on"}
            self.bot_open("work" if do == "work" else "chat")
            return {"ok": True}
        if do == "set":
            if "voice" in cmd:
                ok, what = self.voice_pick(clean_name(cmd.get("voice"), 80))
                return {"ok": True, "said": what} if ok else {"error": what}
            updates = {k: " ".join(str(cmd.get(k) or "").split())[:120]
                       for k in ("server", "model", "name") if k in cmd}
            if "speak" in cmd:
                updates["speak"] = "on" if cmd.get("speak") in (True, "on", "yes", 1, "1") else "off"
            if "chatter" in cmd:
                try:
                    updates["chatter"] = str(max(0, min(1440, int(cmd["chatter"]))))
                except (TypeError, ValueError):
                    return {"error": "Bad request"}
            if not updates:
                return {"error": "Nothing to change"}
            if updates.get("server") and not cam_address(updates["server"]):
                return {"error": "That isn't an address. Try 192.168.1.20"}
            if not self.friend_set(**updates):
                return {"error": "Couldn't save static/bot.txt"}
            if updates.get("speak") == "off":
                self.voice.stop()
            if updates.get("server"):
                fr.fetch_models()
            return {"ok": True}
        return {"error": "Unknown request"}

    def web_show(self, path):
        """A file from the web page's list, opened on the screen the way Files opens it. (One on another computer
        was looked at already, on the web page's thread: web_show_look. Nothing here asks that computer.)"""
        net = self.is_net(path)
        if not (path.startswith("/") and self.web_may_see(path)):
            return {"error": "That file isn't there"}
        kind = self.net_shown.pop(path, None) if net else ("" if os.path.exists(path) else None)
        if kind is None:
            return {"error": "That file isn't there"}
        if not self.web_ready():
            return {"error": "There's no screen to show it on"}
        kind = kind or classify(path)
        folder = path if kind == "dir" else os.path.dirname(path)
        self.web_tab("Files")
        self.browse(folder, select=None if kind == "dir" else path)
        if kind == "dir":
            return {"ok": True}
        items = self.tab_items()
        i = next((k for k, it in enumerate(items) if it["src"] == path), None)
        if i is None:
            return {"error": "That file isn't there"}
        self.sels[self.tab] = i
        self.open_item(items, i)
        return {"ok": True}

    def web_player(self, do):
        if do in ("louder", "quieter"):
            self.set_volume(VOLUME_STEP if do == "louder" else -VOLUME_STEP)
            return {"ok": True, "volume": self.volume}
        if not self.proc:
            return {"error": "Nothing is playing"}
        if do == "pause":
            if self.kind == "plex":
                self.press("a")
            else:
                self.cmd("pause")
                self.paused = not self.paused
                if self.kind in SCREEN_KINDS:
                    self.cmd("pausing_keep_force osd_show_progression")
        elif do == "stop":
            self.stop()
            self.resume_later = None                   # (stopped on purpose: it stays stopped)
            if self.view == "now":
                self.view = "home" if self.now_from == "home" else "list"
        elif do in ("next", "prev"):
            self.skip(1 if do == "next" else -1)
        elif do in ("back", "forward"):
            step = -10 if do == "back" else 10
            if self.kind == "plex":
                self.plex_seek(step)
            elif self.kind not in ("radio", "live"):
                self.cmd(f"seek {step} 0")
                self.paused = False
        elif do == "screen" and self.kind in SCREEN_KINDS:
            self.next_screen()
        else:
            return {"error": "Unknown request"}
        self.dirty = True
        return {"ok": True}
