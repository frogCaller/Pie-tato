"""What you're playing, sent to another of your Pietatos, and what one of them sends, taken (pitato/handoff.py): a
game's menu has Play on another Pietato (◀▶ picks which, A sends it: it carries on there from the same moment, and
its menu there sends it back), and so does HOME's menu on a video or Now playing, for a video, a song or a station
(it carries on there at the same place; X twice sends it too). HOME on a picture, a PDF or a document, or some text
has View on another Pietato (it opens there where you were in it, and HOME there sends it back). Settings > Share
with other Pietatos on, on both."""
import json
import os
import secrets
import shutil
import threading
import time
import urllib.error

from ..config import CACHE_DIR, web_private
from ..fine import detail, made_fine, scale
from ..games import find_games, games_dir, GAME_SYSTEMS, playable, save_name, SAVES_FOLDER
from ..handoff import (clean_file, clean_ident, clean_media, copy_file, copy_game, copy_place, file_place, FILE_MOST,
                       FILE_VIEWS, FIRST_MOST, GAME_COPY_MOST, game_ident, HANDOFF_ASK, HANDOFF_GO, local_game,
                       MEDIA_KINDS, TOKEN, Tokens)
from ..library import LISTEN_KINDS, SCREEN_KINDS
from ..screen import grab_screen
from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT
from ..util import clock, in_home
from .. import savesync
from .games import PEER_DOT

SEND_AGAIN = 4.0              # seconds X has to be pressed again in, to send what's playing
ONE_FILE = (".cue", ".gdi", ".m3u")   # a game in more than one file (its tracks, its discs): not copied over
FILE_BACK = {"photo": "Back to the picture", "pdf": "Back to the page", "text": "Back to the text"}
FILES_IN = "handoff-files"    # (in the cache folder) what you were looking at on another of yours, come here
FILES_OUT = "handoff-out"     # ...and a copy of what you're looking at here, for another to take (some text, say)
FILES_KEPT = 6                # files come from another Pietato kept (the newest): the rest go
OUT_SECS = 3600.0             # a file sent from here: its key good, and a copy of it kept, this long


def all_can_read(path):
    """Anyone can read the file (and get to it): the web page, which hands it over as your user, can."""
    try:
        if not os.stat(path).st_mode & 0o004:
            return False
        d = os.path.dirname(os.path.abspath(path))
        while True:
            if not os.stat(d).st_mode & 0o001:
                return False
            if d == os.path.dirname(d):
                return True
            d = os.path.dirname(d)
    except OSError:
        return False


def handoff_post(url, body, timeout):
    """Another Pietato's answer to a handoff (a dict), or None when it doesn't answer. (It answered no, with why: that,
    and its status.)"""
    try:
        got = savesync.post_json(url + "/api/handoff", body, timeout=timeout)
    except urllib.error.HTTPError as ex:
        try:
            got = json.loads(ex.read(1 << 16))
        except (OSError, ValueError):
            return None
        got = dict(got, ok=False, status=ex.code) if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


class HandoffScreen:
    """Sending what's playing to another of your Pietatos, and taking what one sends."""

    def handoff_target(self):
        """The one it goes to (◀▶ in a game's menu picks it): (its web page's address, its name), or None."""
        peers = self.saves_peers()
        if not peers:
            return None
        want = getattr(self, "handoff_to", None)        # (by its address: two can have the same name)
        got = next((p for p in peers if p[0] == want), None)
        if got is None:
            got = peers[0]
            self.handoff_to = got[0]                   # (kept: another of yours coming on doesn't change it)
        return got

    def handoff_cycle(self, d):
        peers = self.saves_peers()
        if not peers:
            return
        urls = [u for u, _ in peers]
        now = self.handoff_target()[0]
        self.handoff_to = urls[(urls.index(now) + d) % len(urls)] if now in urls else urls[0]

    def peer_colour(self, url):
        """Another of your Pietatos' colour (its accent colour, as it says), for a dot beside its name; None when it
        doesn't say (an older one)."""
        pie = getattr(self, "pie", None)
        return pie.peer_accent(url) if pie is not None and url else None

    def peer_dot(self, d, x, y, url, r=4.5):
        """A dot in another Pietato's colour, centred at x, y (nothing for one that doesn't say its colour). True if
        it's drawn."""
        colour = self.peer_colour(url)
        if colour is None:
            return False
        d.ellipse((x - r, y - r, x + r, y + r), fill=colour)
        return True

    def handoff_keys(self):
        keys = getattr(self, "handoff_tokens", None)
        if keys is None:
            keys = self.handoff_tokens = Tokens()
        return keys

    def web_handoff_file(self, key):
        """The file a key opens, for another of your Pietatos (webui.py serves it): its path, or None."""
        return self.handoff_keys().path(key)

    # -- sending a game ------------------------------------------------------------------------------------
    def game_send(self):
        """The game, to the one picked: asked whether it can, then ended here (its saves kept) and picked up there
        from the same moment. A cartridge it hasn't got goes too."""
        run, target = self.game, self.handoff_target()
        if run is None:
            return
        if target is None:
            self.toast("None of your other Pietatos is on", 3)
            return
        url, host = target
        g = run.game
        try:
            ident = game_ident(g["path"], games_dir(), g.get("system", ""), g["title"], save_name(g["path"]))
        except OSError:
            self.toast("Couldn't read the game", 3)
            return
        self.toast(f"Asking {host}…", 4)
        self.flush()                                   # (said before it waits for the answer)
        said = handoff_post(url, dict(ident, kind="game", check=True), HANDOFF_ASK)
        if said is None:
            self.toast(f"{host} isn't answering", 4)
            return
        if not said.get("ok"):
            self.toast(f"{host}: {said.get('error') or 'it can’t play it'}", 5)
            return
        copy = not said.get("have")
        if copy and (ident["size"] > GAME_COPY_MOST or g["path"].lower().endswith(ONE_FILE)):
            self.toast(f"{host} doesn't have this game. Put it in its Games folder too", 5)
            return
        key = self.handoff_keys().issue(g["path"]) if copy else ""
        self.game_end()                                # (where you are, kept: it's what it picks up)
        said = handoff_post(url, dict(ident, kind="game", file=key), HANDOFF_GO)
        if said is not None and said.get("ok"):
            self.toast(f"Playing on {host} now. Its menu there sends it back", 5)
        else:
            why = (said or {}).get("error") or "it isn't answering"
            self.toast(f"{host} didn't take it ({why}). It picks up here next time", 6)

    # -- sending a video, a song or a station --------------------------------------------------------------------
    def media_sendable(self):
        """What's playing can go to another of your Pietatos (and one's on)."""
        return (self.proc is not None and self.kind in MEDIA_KINDS and bool(self.cur)
                and self.handoff_target() is not None and self.media_source() is not None)

    def media_source(self):
        """(where the other one plays it from, a key to this one's file) for what's playing, or None: it can't go
        (Plex's and Jellyfin's stay with the sign-in here, a live channel through Plex too)."""
        it = self.cur or {}
        src = it.get("src") or ""
        if self.kind in ("video", "audio") and os.path.isfile(src):
            return "", src                             # (a file of yours: the other one takes it from here)
        if src.startswith(("http://", "https://")) or (src.startswith("ia:") and "/" in src):
            return src, None
        return None

    def media_x(self):
        """X while a video or a station plays, or on Now playing's Controls: once says X again sends it to another
        of your Pietatos (as long as one's on); twice in a few seconds sends it. False: X is as it always was."""
        if not self.media_sendable():
            return False
        now = time.monotonic()
        if now < getattr(self, "send_due", 0.0):
            self.send_due = 0.0
            self.media_send()
            return True
        self.send_due = now + SEND_AGAIN
        return False

    def media_send(self):
        target, it, kind = self.handoff_target(), self.cur, self.kind
        source = self.media_source()
        if target is None or not it or source is None:
            return
        url, host = target
        src, path = source
        key = self.handoff_keys().issue(path) if path else ""
        pos = float(self.pos or 0) if kind in ("video", "audio") else 0.0
        if kind not in LISTEN_KINDS:
            self.osd(f"Sending it to {host}…", 2000)
        else:
            self.toast(f"Sending it to {host}…", 3)
            self.flush()
        said = handoff_post(url, {"kind": "media", "media": kind, "title": it.get("title") or "", "src": src,
                                  "file": key, "pos": round(pos, 1)}, HANDOFF_GO)
        if said is None or not said.get("ok"):
            why = (said or {}).get("error") or "it isn't answering"
            if kind not in LISTEN_KINDS:
                self.osd(f"{host} didn't take it ({why})", 3000)
            else:
                self.toast(f"{host} didn't take it ({why})", 4)
            return
        self.stop()
        if self.view in ("now", "help"):
            self.view = "list"
        self.toast(f"Playing on {host} now", 4)
        self.dirty = True

    def media_send_hint(self):
        """What X again does, for the one it'd go to (said on a video's picture, and on Now playing's Controls)."""
        target = self.handoff_target()
        return f"X again: play it on {target[1]}" if target else ""

    # -- sending what's playing, from HOME's menu: a video, a song or a station -------------------------------------
    def media_home(self):
        """HOME on a video's picture, or on Now playing, while another of yours is on: its menu (Play on another
        Pietato, ◀▶ for which one), as a picture's has; from the menu, back to it. False: HOME as ever."""
        if self.view == "mediamenu":
            self.media_menu_close()
            return True
        video = self.kind in SCREEN_KINDS and self.proc_owns_screen()
        if not (video or (self.view == "now" and self.kind in LISTEN_KINDS)) or not self.media_sendable():
            return False
        self.media_menu_open(video)
        return True

    def media_menu_items(self):
        m = getattr(self, "media_menu", None) or {}
        back = ("Back to the video" if m.get("video") else "Back to the station" if self.kind == "radio"
                else "Back to the music")
        return [("back", back), ("send", "Play on another Pietato")]

    def media_menu_open(self, video):
        """The menu, over what's playing: a video paused under it (its picture, dimmed, behind it), music playing on."""
        was_paused = bool(self.paused)
        if video and not was_paused:
            self.cmd("pause")
            self.paused = True
        bg = None
        try:
            from PIL import ImageEnhance
            s = scale()
            if video:                                  # (the video's picture, as it's on the screen now)
                from PIL import Image
                pic = grab_screen(max(640, self.fb.w * s)).convert("RGB").resize((self.fb.w * s, self.fb.h * s),
                                                                                Image.BILINEAR)
            else:
                last = getattr(self.fb, "last", None)
                ok = last is not None and detail(last) == s and last.size == (self.fb.w, self.fb.h)
                pic = (last.pic if detail(last) > 1 else last).convert("RGB") if ok else None
            if pic is not None:
                bg = made_fine(ImageEnhance.Brightness(pic).enhance(0.3), s)
        except (OSError, ValueError, AttributeError, ImportError):
            bg = None
        self.media_menu = {"sel": 0, "view": self.view, "bg": bg, "video": video, "was_paused": was_paused}
        self.view = "mediamenu"
        self.dirty = True

    def media_menu_close(self, play_on=True):
        """Back to it: the video's picture, playing again if it was (play_on), or Now playing."""
        m = getattr(self, "media_menu", None) or {}
        self.media_menu = None
        if self.view == "mediamenu":
            self.view = m.get("view") or "list"
        if self.proc and m.get("video"):
            if play_on and not m.get("was_paused") and self.paused:
                self.cmd("pause")
                self.paused = False
            else:                                      # (still paused: its picture put back over the menu)
                self.cmd("pausing_keep_force osd_show_progression")
        self.dirty = True

    def press_media_menu(self, name, repeat):
        m = getattr(self, "media_menu", None)
        if m is None or not self.proc:                 # (what was playing is over)
            self.media_menu_close()
            return None
        menu = self.media_menu_items()
        job = menu[m["sel"] % len(menu)][0]
        if name in ("up", "down"):
            m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % len(menu)
        elif repeat:
            return None
        elif name in ("left", "right") and job == "send":
            self.handoff_cycle(1 if name == "right" else -1)
        elif name == "b" or (name == "a" and job == "back"):
            self.media_menu_close()
        elif name == "a":
            self.media_menu_close(play_on=False)       # (sent, it stops here; if it can't go, it plays on)
            self.media_send()
            if self.proc and m.get("video") and not m.get("was_paused") and self.paused:
                self.cmd("pause")
                self.paused = False
        self.dirty = True
        return None

    def media_where(self):
        """How far through what's playing it is, in words (in HOME's menu, under its name)."""
        if self.kind == "radio":
            return self.meta.get("song") or "A station"
        length = self.meta.get("length") or self.length(self.cur or {}) or 0
        return f"{clock(self.pos or 0)} of {clock(length)}" if length else clock(self.pos or 0)

    # -- sending what you're looking at: a picture, a PDF or a document, some text ----------------------------------
    def file_home(self):
        """HOME on a picture, a PDF or a document, or some text, while another of yours is on: its menu (View on
        another Pietato), or from the menu, back to it. False: HOME as ever."""
        if self.view == "filemenu":
            self.file_menu_close()
            return True
        if self.view not in FILE_VIEWS or self.v.get("type") != self.view or self.handoff_target() is None:
            return False
        self.file_menu_open()
        return True

    def file_menu_items(self):
        m = getattr(self, "file_menu", None) or {}
        return [("back", FILE_BACK.get(m.get("view") or self.v.get("type"), "Back to it")),
                ("send", "View on another Pietato")]

    def file_menu_open(self):
        bg, last = None, getattr(self.fb, "last", None)
        if last is not None and detail(last) == scale() and last.size == (self.fb.w, self.fb.h):
            try:
                from PIL import ImageEnhance            # (what's on the screen, dimmed, behind the menu)
                pic = last.pic if detail(last) > 1 else last
                bg = made_fine(ImageEnhance.Brightness(pic.convert("RGB")).enhance(0.3), scale())
            except (OSError, ValueError, AttributeError):
                bg = None
        self.file_menu = {"sel": 0, "view": self.view, "bg": bg}
        self.view = "filemenu"
        self.dirty = True

    def file_menu_close(self):
        """Back to what you're looking at (or, if it's gone, the list)."""
        m = getattr(self, "file_menu", None)
        self.file_menu = None
        self.view = m["view"] if m and self.v.get("type") == m["view"] else "list"
        self.dirty = True

    def press_file_menu(self, name, repeat):
        m = getattr(self, "file_menu", None)
        if m is None or self.v.get("type") != m["view"]:
            self.file_menu_close()
            return None
        menu = self.file_menu_items()
        job = menu[m["sel"] % len(menu)][0]
        if name in ("up", "down"):
            m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % len(menu)
        elif repeat:
            return None
        elif name in ("left", "right") and job == "send":
            self.handoff_cycle(1 if name == "right" else -1)
        elif name == "b" or (name == "a" and job == "back"):
            self.file_menu_close()
        elif name == "a":
            self.file_send()
        self.dirty = True
        return None

    def file_title(self):
        v = self.v
        if v.get("type") == "photo" and v.get("items"):
            return os.path.basename(v["items"][v["i"] % len(v["items"])])
        return v.get("title") or ""

    def file_where(self):
        """Where you are in what you're looking at, in words (under its name, in its menu)."""
        v = self.v
        if v.get("type") == "pdf":
            return f"Page {v['page']} of {v['pages']}"
        if v.get("type") == "text":
            return f"Line {v.get('top', 0) + 1} of {len(self.text_lines())}"
        if v.get("type") == "photo" and len(v.get("items") or ()) > 1:
            return f"Picture {v['i'] + 1} of {len(v['items'])}"
        return "A picture" if v.get("type") == "photo" else ""

    def file_what(self):
        """What you're looking at, as another of your Pietatos is told of it: (the file it takes, what it's told),
        or why it can't go, in words."""
        v = self.v
        kind = v.get("type")
        try:
            if kind == "photo":
                path = v["items"][v["i"]]
                title, place = os.path.basename(path), {"rot": v.get("rot", 0)}
            elif kind == "pdf":
                path, title = v["path"], v.get("title") or os.path.basename(v["path"])
                im = self.pdf_image() if v["fit"] == "width" else None
                place = {"page": v["page"], "fit": v["fit"], "zoom": v["zoom"],
                         "at": round(v["scroll"] / im.height, 4) if im is not None and im.height else 0.0,
                         "sx": round(v["sx"] / im.width, 4) if im is not None and im.width else 0.0}
            elif kind == "text":
                path, title = v.get("path") or "", v.get("title") or "Text"
                lines, top = self.text_lines(), v.get("top", 0)
                place = {"first": lines[top][:FIRST_MOST] if 0 <= top < len(lines) else "",
                         "frac": round(top / len(lines), 4) if lines else 0.0, "big": v.get("size", 0)}
            else:
                return "It can't go to another Pietato"
            if web_private(os.path.basename(path)) or web_private(title):
                return "That one stays on this Pi"      # (a password's or a token's file)
            if kind == "text":
                path = self.file_out(text=v["text"])    # (as it's shown: a document's words, say)
            elif not (in_home(path) or all_can_read(path)):
                path = self.file_out(path=path)         # (the web page, which hands it over, couldn't read it)
            size = os.path.getsize(path)
        except (OSError, KeyError, IndexError, TypeError, ValueError):
            return "Couldn't read it"
        if size > FILE_MOST:
            return "It's too big to send"
        return path, dict(place, view=kind, title=title, size=size)

    def file_out(self, text=None, path=None):
        """A copy of what you're looking at (some text, or a file the web page can't read), for another of your
        Pietatos to take: kept a while (the ones from before go)."""
        folder = os.path.join(CACHE_DIR, FILES_OUT)
        os.makedirs(folder, exist_ok=True)
        os.chmod(folder, 0o755)
        now = time.time()
        for name in os.listdir(folder):
            old = os.path.join(folder, name)
            try:
                if now - os.path.getmtime(old) > OUT_SECS:
                    os.remove(old)
            except OSError:
                pass
        out = os.path.join(folder, secrets.token_hex(8) + (".txt" if text is not None else
                                                           os.path.splitext(path)[1][:12]))
        if text is not None:
            with open(out, "w", encoding="utf-8", errors="replace") as f:
                f.write(text)
        else:
            shutil.copyfile(path, out)
        os.chmod(out, 0o644)
        return out

    def file_send(self):
        """What you're looking at, to the one picked: asked whether it can, then opened there where you were in it,
        and closed here."""
        target = self.handoff_target()
        if target is None:
            self.toast("None of your other Pietatos is on", 3)
            return
        url, host = target
        got = self.file_what()
        if isinstance(got, str):
            self.toast(got, 4)
            return
        path, body = got
        self.toast(f"Asking {host}…", 4)
        self.flush()                                   # (said before it waits for the answer)
        said = handoff_post(url, dict(body, kind="file", check=True), HANDOFF_ASK)
        if said is None:
            self.toast(f"{host} isn't answering", 4)
            return
        if said.get("status") == 400:                  # (one from before this: it doesn't know what it's asked)
            self.toast(f"{host} needs updating first (System > Update software there)", 6)
            return
        if not said.get("ok"):
            self.toast(f"{host}: {said.get('error') or 'it can’t show it'}", 5)
            return
        key = self.handoff_keys().issue(path, secs=OUT_SECS)
        said = handoff_post(url, dict(body, kind="file", file=key), HANDOFF_GO)
        if said is None or not said.get("ok"):
            self.toast(f"{host} didn't take it ({(said or {}).get('error') or 'it isn’t answering'})", 5)
            return
        self.file_menu = None
        if self.v.get("type") == "photo":
            self.photo_back()
        else:
            self.close_viewer()
        self.toast(f"Showing on {host} now. HOME there sends it back", 5)

    def render_file_menu(self):
        """HOME on what you're looking at: its menu, over it (Back to it; View on another Pietato ◀ ● name ▶)."""
        self.render_send_menu(getattr(self, "file_menu", None) or {"sel": 0, "bg": None}, self.file_menu_items(),
                              self.file_title(), self.file_where(), "file_menu")

    def render_media_menu(self):
        """HOME on a video's picture or Now playing: its menu, over it (Back to it; Play on another Pietato ◀ ● name
        ▶). What was playing over: back to where you were."""
        m = getattr(self, "media_menu", None)
        if m is None or not self.proc:
            self.media_menu_close()
            return
        title = (self.cur or {}).get("title") or "" if m.get("video") else self.lofi_words()[0]
        self.render_send_menu(m, self.media_menu_items(), title, self.media_where(), "media_menu")

    def render_send_menu(self, m, menu, title, where, owner):
        """A menu for sending what's on the screen to another of yours, over it (dimmed): its name, where you are in
        it, then its rows (the one that sends it with the one it'd go to, ◀ ● name ▶). owner: where it's kept (a
        tap on a row, on the web page's copy of the screen, picks it)."""
        F = self.fonts
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        if m.get("bg") is not None:
            img.paste(m["bg"])
        n, mw, rh = len(menu), self.game_menu_width(d, menu, title), 38
        mh = 64 + n * rh + 10
        mx0, my0 = (W - mw) / 2, max(12, (H - self.FOOTER - 50 - mh) / 2)   # (room below for a toast)
        d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + mh + 2), radius=14, fill=LINE)
        d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + mh), radius=13, fill=BG)
        d.text((mx0 + 22, my0 + 24), self.fit(d, title, F["row_b"], mw - 44), font=F["row_b"], fill=TEXT,
               anchor="lm")
        d.text((mx0 + 22, my0 + 46), self.fit(d, where, F["small"], mw - 44), font=F["small"],
               fill=MUTED, anchor="lm")
        peer = self.handoff_target()
        for k, (job, label) in enumerate(menu):
            ry = my0 + 64 + k * rh
            sel = k == m["sel"] % n
            font = F["row_b"] if sel else F["row"]
            self.tappable((mx0, ry - 2, mx0 + mw, ry + rh - 2), "sel", "dict", owner, k)
            if sel:
                d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                d.rounded_rectangle((mx0 + 8, ry + 10, mx0 + 12, ry + rh - 14), radius=2, fill=ACCENT)
            mid = ry + (rh - 4) / 2
            d.text((mx0 + 24, mid), label, font=font, fill=TEXT if sel else BODY, anchor="lm")
            if job != "send" or peer is None:
                continue
            gap = PEER_DOT if self.peer_colour(peer[0]) is not None else 0
            room = mw - 24 - d.textlength(label, font=font) - 28 - 22
            arrows = d.textlength("◀    ▶", font=F["small"]) if sel else 0
            name = self.fit(d, peer[1], F["small"], max(20, room - arrows - gap))
            head, tail = ("◀  ", f"{name}  ▶") if sel else ("", name)
            rx, colour = mx0 + mw - 22, TEXT if sel else MUTED
            tw = d.textlength(tail, font=F["small"])
            d.text((rx, mid), tail, font=F["small"], fill=colour, anchor="rm")
            if gap:                                    # (its colour's dot before its name)
                self.peer_dot(d, rx - tw - 6 - 4.5, mid, peer[0])
            if head:
                d.text((rx - tw - gap, mid), head, font=F["small"], fill=colour, anchor="rm")
                vx = rx - max(128, tw + gap + d.textlength(head, font=F["small"]))
                half = (vx + rx) / 2                   # ◀ name ▶: each end, a way to change it
                self.tappable((vx - 22, ry - 2, half, ry + rh - 2), "keys", "left")
                self.tappable((half, ry - 2, mx0 + mw, ry + rh - 2), "keys", "right")
        hints = [("A", "Choose")] + ([("◀▶", "Change")] if menu[m["sel"] % n][0] == "send" else []) \
            + [("B", menu[0][1])]
        self.footer(d, hints)
        self.fb.show(img)

    # -- taking what another one sends -----------------------------------------------------------------------
    def web_peer_handoff(self, cmd):
        """POST /api/handoff (another of your Pietatos, through webui.py): whether this one can take a game, or what
        you're looking at (check), or a game, a video, a song, a station, a picture, a PDF or some text, taken. (The
        main loop's thread.)"""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        url, host = peers[0]
        if cmd.get("kind") == "game":
            return self.handoff_take_game(cmd, url, host)
        if cmd.get("kind") == "media":
            return self.handoff_take_media(cmd, url, host)
        if cmd.get("kind") == "file":
            return self.handoff_take_file(cmd, url, host)
        return {"ok": False, "error": "What's that?"}

    def handoff_game_cant(self, key):
        """Why this Pietato can't play a console's games, in words, or None."""
        if not any(s[0] == key for s in GAME_SYSTEMS):
            return "It doesn't know that kind of game"
        name = next(s for s in GAME_SYSTEMS if s[0] == key)[2]
        if not playable(key):
            return f"{name} games don't play on this Pi"
        why = self.game_cant({"path": "", "system": key})
        return why[0] if why else None

    def handoff_take_game(self, cmd, url, host):
        ident = clean_ident(cmd)
        if ident is None:
            return {"ok": False, "error": "Which game?"}
        why = self.handoff_game_cant(ident["system"])
        games = games_dir()
        mine = None if why else local_game(games, ident, [g["path"] for g in find_games()
                                                          if g["system"] == ident["system"]], save_name)
        if cmd.get("check") is True:
            return {"ok": True, "have": bool(mine)} if why is None else {"ok": False, "error": why}
        if why:
            return {"ok": False, "error": why}
        if not self.web_ready():
            return {"ok": False, "error": "There's no screen to show it on"}
        if mine:
            self.soon_jobs.append(lambda: self.handoff_open(mine, ident, url, host))
            return {"ok": True}
        key = cmd.get("file")
        if not isinstance(key, str) or not TOKEN.fullmatch(key) or ident["size"] > GAME_COPY_MOST:
            return {"ok": False, "error": "It doesn't have that game"}
        dest = copy_place(games, ident)
        if dest is None:
            return {"ok": False, "error": "It has another game by that name"}
        owner = self.saves_owner()
        self.toast(f"Copying {ident['title']} from {host}…", 5)

        def copy():
            try:
                copy_game(f"{url}/api/handoff/file?token={key}", dest, ident, owner)
            except OSError as ex:
                print(f"handoff: {ident['title']} from {host}: {ex}", flush=True)
                self.soon_jobs.append(lambda: self.toast(f"Couldn't copy {ident['title']} from {host}", 5))
            else:
                self.soon_jobs.append(lambda: self.handoff_open(dest, ident, url, host))
            self.wake()
        threading.Thread(target=copy, daemon=True, name="handoff-game").start()
        return {"ok": True}

    def handoff_open(self, path, ident, url, host):
        """A game sent from another of your Pietatos, opened: its saves first, from that one (where you were there,
        even if this one's played it since: what's playing here ends first, its own saves kept as ever)."""
        if not self.web_ready():
            return
        self.stir()
        self.stop()
        saves, owner = os.path.join(games_dir(), SAVES_FOLDER), self.saves_owner()
        try:
            os.makedirs(saves, exist_ok=True)
            with self.saves_lock:
                savesync.pull(saves, ident["name"], [(url, host)], owner=owner, force=True)
        except Exception as ex:                        # (it starts all the same: from here's)
            print(f"handoff: {ident['title']}'s saves from {host}: {ex!r}", flush=True)
        self.game_open({"src": path, "title": ident["title"], "system": ident["system"]})
        self.handoff_to = url                          # (its menu here sends it back: that one's picked)

    def handoff_take_media(self, cmd, url, host):
        key = cmd.get("file")
        src = cmd.get("src")
        if isinstance(key, str) and key:
            if not TOKEN.fullmatch(key):
                return {"ok": False, "error": "What's that?"}
            src = f"{url}/api/handoff/file?token={key}"
        got = clean_media(dict(cmd, src=src))
        if got is None:
            return {"ok": False, "error": "What's that?"}
        kind, title, src, pos = got
        if not self.web_ready():
            return {"ok": False, "error": "There's no screen to show it on"}
        it = {"kind": kind, "src": src, "title": title, "key": "handoff:" + title, "label": f"{title} (from {host})"}
        self.soon_jobs.append(lambda: self.handoff_play(it, pos, url))
        return {"ok": True}

    def handoff_play(self, it, pos, url=None):
        """A video, a song or a station sent from another of your Pietatos, played from where it was there (a video
        says so as it starts: Resuming at ...)."""
        if not self.web_ready():
            return
        self.stir()
        self.play([it], 0, start=pos if pos >= 1 else 0)
        if url:
            self.handoff_to = url                      # (X twice here sends it back: that one's picked)

    def handoff_file_cant(self, view, size):
        """Why this Pietato can't show a file sent from another of yours, in words, or None."""
        if view == "pdf" and not (shutil.which("pdfinfo") and shutil.which("pdftoppm")):
            return "It can't show PDFs (is poppler-utils installed?)"
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            room = shutil.disk_usage(CACHE_DIR).free
        except OSError:
            room = 0
        if room < size + (64 << 20):
            return "It hasn't the room for it"
        return None

    def handoff_take_file(self, cmd, url, host):
        got = clean_file(cmd)
        if got is None:
            return {"ok": False, "error": "What's that?"}
        view, title, size, place = got
        why = self.handoff_file_cant(view, size)
        if cmd.get("check") is True:
            return {"ok": True} if why is None else {"ok": False, "error": why}
        if why:
            return {"ok": False, "error": why}
        key = cmd.get("file")
        if not isinstance(key, str) or not TOKEN.fullmatch(key):
            return {"ok": False, "error": "What's that?"}
        if not self.web_ready():
            return {"ok": False, "error": "There's no screen to show it on"}
        dest = os.path.join(CACHE_DIR, FILES_IN, secrets.token_hex(6), file_place(title))
        self.toast(f"Getting {title} from {host}…", 5)

        def copy():
            try:
                copy_file(f"{url}/api/handoff/file?token={key}", dest, size)
            except Exception as ex:                    # (a lost connection, too: said, not left unsaid)
                print(f"handoff: {title} from {host}: {ex!r}", flush=True)
                shutil.rmtree(os.path.dirname(dest), ignore_errors=True)
                self.soon_jobs.append(lambda: self.toast(f"Couldn't get {title} from {host}", 5))
            else:
                self.soon_jobs.append(lambda: self.handoff_show(dest, view, title, place, url, host))
            self.wake()
        threading.Thread(target=copy, daemon=True, name="handoff-file").start()
        return {"ok": True}

    def handoff_show(self, path, view, title, place, url, host):
        """What you were looking at on another of your Pietatos, opened here where you were in it there (HOME here
        sends it back: that one's picked)."""
        if not self.web_ready():
            return
        self.stir()
        if view == "photo":
            self.open_photo([path], 0)
            self.v["rot"] = place["rot"]
        elif view == "pdf":
            self.open_pdf(path, title)
            if self.view != "pdf":
                return                                 # (it said why)
            self.pdf_place(place)
        else:
            try:
                with open(path, "rb") as f:
                    text = f.read().decode("utf-8", errors="replace")
            except OSError:
                self.toast(f"Couldn't read {title}", 4)
                return
            self.open_text(path, text=text)
            self.v["title"] = title
            self.text_place(place)
        self.handoff_to = url
        self.files_in_tidy(path)
        self.toast(f"{title} (from {host})", 4)

    def pdf_place(self, place):
        """A PDF just opened: at the page, the fit and how close it was, as far down and across it."""
        v = self.v
        v["page"] = max(1, min(place["page"], v["pages"]))
        v["fit"] = place["fit"]
        v["zoom"] = place["zoom"] if v["fit"] == "width" and place["zoom"] in self.PDF_ZOOMS else 1.0
        if v["fit"] == "width" and (place["at"] or place["sx"]):
            im = self.pdf_image()
            if im is not None:
                v["scroll"], v["sx"] = int(place["at"] * im.height), int(place["sx"] * im.width)
        self.dirty = True

    def text_place(self, place):
        """Some text just opened: its letters' size, and the line that was at the top (the one starting the same way
        nearest as far down it; none: as far down)."""
        v = self.v
        v["size"], v["lines"] = place["big"], None
        lines = self.text_lines()
        rows, _ = self.text_rows()
        want, start = place["frac"] * len(lines), place["first"][:20]
        near = [k for k, line in enumerate(lines) if line.startswith(start)] if start.strip() else []
        top = min(near, key=lambda k: abs(k - want)) if near else int(round(want))
        v["top"] = max(0, min(top, max(len(lines) - rows, 0)))
        self.dirty = True

    def files_in_tidy(self, keep):
        """Files come from your other Pietatos: the newest few kept (the one open now among them), the rest go."""
        root = os.path.join(CACHE_DIR, FILES_IN)
        try:
            folders = sorted((os.path.join(root, d) for d in os.listdir(root)), key=os.path.getmtime, reverse=True)
        except OSError:
            return
        for d in folders[FILES_KEPT:]:
            if d != os.path.dirname(keep):
                shutil.rmtree(d, ignore_errors=True)
