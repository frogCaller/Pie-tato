"""What you're playing, sent to another of your Pietatos, and what one of them sends, taken (pitato/handoff.py): a
game's menu has Play on another Pietato (◀▶ picks which, A sends it: it carries on there from the same moment, and
its menu there sends it back), and X twice sends a video, a song or a station (it carries on there at the same
place). Settings > Share with other Pietatos on, on both."""
import os
import threading
import time

from ..games import find_games, games_dir, GAME_SYSTEMS, playable, save_name, SAVES_FOLDER
from ..handoff import (clean_ident, clean_media, copy_game, copy_place, GAME_COPY_MOST, game_ident, HANDOFF_ASK,
                       HANDOFF_GO, local_game, MEDIA_KINDS, TOKEN, Tokens)
from ..library import LISTEN_KINDS
from .. import savesync

SEND_AGAIN = 4.0              # seconds X has to be pressed again in, to send what's playing
ONE_FILE = (".cue", ".gdi", ".m3u")   # a game in more than one file (its tracks, its discs): not copied over


def handoff_post(url, body, timeout):
    """Another Pietato's answer to a handoff (a dict), or None when it doesn't answer."""
    try:
        got = savesync.post_json(url + "/api/handoff", body, timeout=timeout)
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
        want = getattr(self, "handoff_to", None)
        return next((p for p in peers if p[1] == want), peers[0])

    def handoff_cycle(self, d):
        peers = self.saves_peers()
        if not peers:
            return
        names = [h for _, h in peers]
        now = self.handoff_target()[1]
        self.handoff_to = names[(names.index(now) + d) % len(names)] if now in names else names[0]

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

    # -- taking what another one sends -----------------------------------------------------------------------
    def web_peer_handoff(self, cmd):
        """POST /api/handoff (another of your Pietatos, through webui.py): whether this one can take a game (check), or
        a game, a video, a song or a station, taken. (The main loop's thread.)"""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        url, host = peers[0]
        if cmd.get("kind") == "game":
            return self.handoff_take_game(cmd, url, host)
        if cmd.get("kind") == "media":
            return self.handoff_take_media(cmd, url, host)
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
        self.soon_jobs.append(lambda: self.handoff_play(it, pos))
        return {"ok": True}

    def handoff_play(self, it, pos):
        """A video, a song or a station sent from another of your Pietatos, played from where it was there (a video
        says so as it starts: Resuming at ...)."""
        if not self.web_ready():
            return
        self.stir()
        self.play([it], 0, start=pos if pos >= 1 else 0)
