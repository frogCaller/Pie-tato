"""Two players on two of your Pietatos (Settings > Share with other Pietatos on, on both): a game's menu has Play together
(◀▶ picks which of them). A game two play at once (NES, SNES, Genesis, Master System, Neo Geo): the other joins it as
player 2, from this game as it is now, its emulator keeping in step with this one's frame by frame (pitato/netplay.py).
A Game Boy or Game Boy Color game: Link cable. Each plays its own game from its own save (Pokémon to trade or battle
with), the two emulators linked over your network (gambatte's own link), and each one's save is its own again after.
The other Pietato asks first: A to play (◀▶: which of its Game Boy games, for a link cable), B for no thanks."""
import glob
import ipaddress
import os
import secrets
import shutil
import threading
import time
import urllib.parse

from ..config import CACHE_DIR
from ..games import CORE_DIRS, find_core, find_games, GameRun, games_dir, save_name, SAVES_FOLDER
from ..handoff import (clean_ident, copy_game, copy_place, GAME_COPY_MOST, game_ident, HANDOFF_ASK, HANDOFF_GO,
                       local_game, TOKEN)
from ..netplay import NET_PORT
from ..screen import aplay_device, screen_turn, sound_place
from ..theme import BODY, LINE, MUTED, ROW, TEXT
from .handoff import ONE_FILE
from .. import savesync

NET_SYSTEMS = ("nes", "snes", "genesis", "sms", "neogeo")   # a game two play at once, kept in step
LINK_SYSTEMS = ("gb", "gbc")          # ...and a link cable's
LINK_CORE = "gambatte"                # (the Game Boy emulator with a link cable over the network: setup.sh builds it)
LINK_PORT = 56400                     # (gambatte's own)
INVITE_SECS = 60.0                    # seconds the other has to say yes
TOGETHER_WAIT = 90.0                  # seconds this one waits for the other to join (from when it was asked, or said yes)
APART = ("load", "reset", "disc", "ai", "send", "together")   # not in a game's menu while it's played together


def link_core():
    """gambatte's path (setup.sh builds it: the Game Boy's link cable), or None."""
    for pattern in CORE_DIRS:
        for path in sorted(glob.glob(os.path.join(pattern, LINK_CORE + "_libretro.so"))):
            if os.path.isfile(path):
                return path
    return None


def link_options(server, addr=""):
    """gambatte's settings for a link cable over your network: this one's the end the other joins (server), or it
    joins the other's at addr (as gambatte takes an address: 12 digits, 3 for each part). None: not an address it
    can take (only one like 192.168.1.20)."""
    out = ["gambatte_gb_link_mode=" + ("Network Server" if server else "Network Client"),
           f"gambatte_gb_link_network_port={LINK_PORT}"]
    if not server:
        try:
            digits = "".join(f"{int(o):03d}" for o in str(ipaddress.IPv4Address(addr)).split("."))
        except ValueError:
            return None
        out += [f"gambatte_gb_link_network_server_ip_{i + 1}={d}" for i, d in enumerate(digits)]
    return out


def together_post(url, body, timeout):
    """Another Pietato's answer (a dict), or None when it doesn't answer."""
    try:
        got = savesync.post_json(url + "/api/together", body, timeout=timeout)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def gone_words(who, why):
    """Why player 2's game ended, in words: the host's game ended, or it stopped answering."""
    if why in ("", "it left"):
        return f"{who} ended the game"
    return f"{who}{why[2:]}" if why.startswith("it ") else f"{who}: {why}"


def keep_tail(new, old):
    """A link cable's save, back with yours: what another emulator keeps after it (mGBA keeps a game's clock there,
    gambatte apart from it) kept as it was."""
    return new + old[len(new):] if old is not None and len(old) > len(new) else new


class TogetherScreen:
    """Two players on two Pietatos: asking another to play (this one's game), and another's asking (taken, or not)."""

    def together_of(self, run=None):
        run = self.game if run is None else run
        return getattr(run, "together", None) if run is not None else None

    def together_link(self):
        """The game playing is a Game Boy's (playing together is a link cable)."""
        return self.game is not None and self.game.game.get("system") in LINK_SYSTEMS

    def together_can(self):
        """The game playing can be played together with another of yours (and one's on)."""
        run = self.game
        if run is None or getattr(run, "attract", False) or self.together_of() is not None:
            return False
        return run.game.get("system") in NET_SYSTEMS + LINK_SYSTEMS and self.handoff_target() is not None

    def together_label(self):
        return "Link cable" if self.together_link() else "Play together"

    def together_apart(self, job):
        """A job a game's menu hasn't while it's played together (the two would be out of step; player 2's game is
        the host's, its saves too; a link cable's saves come back with yours from the game's own)."""
        t = self.together_of()
        if t is None:
            return False
        return job in APART or (job == "save" and (t.get("link") or not t.get("host")))

    def together_note(self):
        """What the game's menu says about playing together (under its title), or ""."""
        t = self.together_of()
        if t is None:
            return ""
        if t.get("link"):
            return f"The link cable's waiting for {t['with']}" if t.get("waiting") else f"Link cable with {t['with']}"
        if t.get("host"):
            return f"Playing with {t['with']} (player 2)" if t.get("state") == "on" else f"Waiting for {t['with']}"
        return f"Playing {t['with']}'s game: you're player 2"

    def together_waiting(self, run):
        """HOME, and the game doesn't answer: a link cable's game stands still while it waits for the other Game Boy
        (one that's linked, but not where the link's used: the other player isn't at the link yet). Its menu, all the
        same (it pauses as soon as it can), so it can be left: True."""
        t = self.together_of(run)
        if t is None or not t.get("link") or run.state != "on" or run.ended:
            return False
        t["waiting"] = True
        return True

    # -- asking another to play ------------------------------------------------------------------------------------
    def together_invite(self):
        """Play together (A in a game's menu): the one picked is asked whether it can; then this game's opened to it
        (a link cable: this game again, linked) and it's asked to play."""
        run, target = self.game, self.handoff_target()
        if run is None:
            return
        if target is None:
            self.toast("None of your other Pietatos is on", 3)
            return
        url, host = target
        g = run.game
        link = g["system"] in LINK_SYSTEMS
        if link and not link_core():
            self.toast("The link cable needs setup.sh run again", 4)
            return
        if link and link_options(False, urllib.parse.urlsplit(url).hostname) is None:
            self.toast(f"The link cable can't reach {host}", 4)
            return
        try:
            ident = game_ident(g["path"], games_dir(), g["system"], g["title"], save_name(g["path"]))
        except OSError:
            self.toast("Couldn't read the game", 3)
            return
        self.toast(f"Asking {host}…", 4)
        self.flush()                                   # (said before it waits for the answer)
        said = together_post(url, dict(ident, kind="ask", link=link), HANDOFF_ASK)
        if said is None:
            self.toast(f"{host} isn't answering", 4)
            return
        if not said.get("ok"):
            self.toast(f"{host}: {said.get('error') or 'it can’t play it'}", 5)
            return
        if link:
            return self.together_link_host(url, host, ident)
        copy = not said.get("have")
        if copy and (ident["size"] > GAME_COPY_MOST or g["path"].lower().endswith(ONE_FILE)):
            self.toast(f"{host} doesn't have this game. Put it in its Games folder too", 5)
            return
        key = secrets.token_urlsafe(16)
        what, rest = run.ask(f"nethost {NET_PORT} {key} {urllib.parse.urlsplit(url).hostname}", ("nethost",), 3)
        words = rest.split()
        if what != "nethost" or words[:1] != ["ok"] or len(words) < 2 or not words[1].isdigit():
            print(f"together: couldn't open the game to {host} ({rest})", flush=True)
            self.toast(f"Couldn't open the game to {host}", 4)
            return
        file = self.handoff_keys().issue(g["path"]) if copy else ""
        said = together_post(url, dict(ident, kind="invite", port=int(words[1]), key=key, file=file), HANDOFF_GO)
        if said is None or not said.get("ok"):
            run.send("netstop")
            self.toast(f"{host}: {(said or {}).get('error') or 'it isn’t answering'}", 5)
            return
        run.together = {"with": host, "url": url, "host": True, "link": False, "state": "asked",
                        "since": time.monotonic()}
        self.game_menu_close()
        run.send(f"notice Asking {host} to play")

    def together_link_host(self, url, host, ident):
        """A link cable: this game again, linked (gambatte, the end the other joins), from its own save; then the
        other's asked to play."""
        g = dict(self.game.game)
        self.game_end()                                # (where you were, kept: there again after, if nothing changed)
        run = self.together_start(g, True, host, url, link=True)
        if run is None:
            return
        said = together_post(url, dict(ident, kind="invite", link=True, port=LINK_PORT), HANDOFF_GO)
        if said is None or not said.get("ok"):
            run.send(f"notice {host} didn't take it")
            self.toast(f"{host}: {(said or {}).get('error') or 'it isn’t answering'}", 5)
            return
        run.send(f"notice Asking {host} to link up")

    def together_start(self, g, host, who, url, link=False, net=""):
        """A game played together, opened: the host's (a link cable's: either end's) or player 2's."""
        name = save_name(g["path"])
        folder = os.path.join(CACHE_DIR, "link" if link else "together", SAVES_FOLDER)
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder, exist_ok=True)
        hints = [("HOME", "Its menu")] + ([("SELECT", "Coin")] if g["system"] == "neogeo" else [])
        self.stop()                                    # (music, a video: the game has the speaker)
        self.view = "game"
        self.render_curtain(g["title"], f"Linking up with {who}…" if link else f"Joining {who}'s game…", hints=hints)
        if link:                                       # its own save (a copy: back with yours after)
            if not host:
                came = self.saves_follow(g, lambda words: self.render_curtain(g["title"], words, hints=hints))
                if came:
                    self.render_curtain(g["title"], f"Your save from {came}. Linking up with {who}…", hints=hints)
            mine = os.path.join(games_dir(), SAVES_FOLDER, name)
            for ext in (".srm", ".rtc"):
                if os.path.isfile(mine + ext):
                    shutil.copy2(mine + ext, os.path.join(folder, name + ext))
        core = link_core() if link else find_core(g["system"])
        options = (link_options(host, urllib.parse.urlsplit(url).hostname) or []) if link else []
        run = GameRun(g, on_change=self.game_changed)
        run.together = {"with": who, "url": url, "host": host, "link": link, "folder": folder, "name": name,
                        "state": "on" if link or not host else "asked", "since": time.monotonic()}
        place = sound_place(self.setting("sound"))
        try:
            turn = screen_turn()
            run.start(core, sound=aplay_device(None, place[0]), volume=self.volume,
                      picture=self.game_picture(g["system"]), resume=False, cheevos=False, saves=folder,
                      options=options, net=net, **({"turn": turn} if turn else {}))
        except OSError as ex:
            print(f"together: couldn't start {g['path']}: {ex}", flush=True)
            self.view = "list"
            self.toast("Couldn't start the game", 4)
            return None
        self.game, self.game_menu, self.game_sound = run, None, place
        self.game_since = time.monotonic()
        self.stick_sent = {}
        self.ds_dirs = set()
        used = getattr(self, "input_pad", None)       # (the controller that said yes: its player, as ever)
        self.game_players = {used.path: 0} if used is not None and self.pads and \
            self.pads.by_path.get(used.path) is used else {}
        print(f"together: {g['title']}" + (", a link cable" if link else ", the host" if host else ", player 2")
              + f" with {who}", flush=True)
        return run

    def together_end(self, run):
        """A game played together, over. A link cable's: its save back with yours (if it changed: what was traded's
        in it), and where you were in it put aside (from before: it'd take the trade back), so it starts from that
        save next time. Player 2's: nothing of yours changed (it was the host's game)."""
        t = self.together_of(run)
        if not t or not t.get("link"):
            return
        saves = os.path.join(games_dir(), SAVES_FOLDER)
        mine = os.path.join(saves, t["name"])
        took = os.path.join(t["folder"], t["name"])
        changed = []
        for ext in (".srm", ".rtc"):                   # (the save; and the clock some games keep, which moves on
            try:                                       #  whenever they're played)
                with open(took + ext, "rb") as f:
                    new = f.read()
            except OSError:
                continue
            try:
                with open(mine + ext, "rb") as f:
                    old = f.read()
            except OSError:
                old = None
            new = keep_tail(new, old)
            if new != old:
                os.makedirs(saves, exist_ok=True)
                with open(mine + ext + ".part", "wb") as f:
                    f.write(new)
                os.replace(mine + ext + ".part", mine + ext)
                changed.append(mine + ext)
        if not changed:
            return
        if mine + ".srm" in changed and os.path.isfile(mine + ".state.auto"):   # (the save itself changed)
            keep = os.path.join(saves, savesync.REPLACED)
            os.makedirs(keep, exist_ok=True)
            os.replace(mine + ".state.auto", os.path.join(keep, t["name"] + ".state.auto"))
        owner = self.saves_owner()
        if owner:
            for path in changed:
                try:
                    os.chown(path, *owner)
                except OSError:
                    pass
        print(f"together: {t['name']}'s save, back from the link cable", flush=True)

    def together_tick(self, run, now):
        """What's happened, playing together: the other joined or left, or (player 2) the host's game ended; and the
        wait for the other to join, over."""
        t = run.together
        while run.net_news:
            what, why = run.net_news.pop(0)
            if what == "netjoined":
                t["state"] = "on"
            elif what == "netleft":                    # (player 1 plays on, alone)
                run.together = None
                self.toast(gone_words(t["with"], why).replace("ended the game", "left"), 4)
            elif what == "netgone":                    # (player 2: its game ends, and says why)
                run.error = gone_words(t["with"], why)
        if (run.together is t and t.get("host") and not t.get("link") and t.get("state") != "on"
                and now - t["since"] > TOGETHER_WAIT):
            run.send("netstop")
            run.send(f"notice {t['with']} didn't join")
            run.together = None

    # -- another's asking ----------------------------------------------------------------------------------------------
    def web_together(self, cmd):
        """POST /api/together (another of your Pietatos, through webui.py): whether this one can play a game with it
        (ask), its asking to play (invite: shown, for A or B), or (to the one that asked) the answer."""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        url, host = peers[0]
        kind = cmd.get("kind")
        if kind == "answer":
            return self.together_answered(url, host, cmd.get("yes") is True)
        ident = clean_ident(cmd)
        if ident is None or kind not in ("ask", "invite"):
            return {"ok": False, "error": "Which game?"}
        link = cmd.get("link") is True
        if self.game is not None and not getattr(self.game, "attract", False):
            return {"ok": False, "error": "It's playing a game"}
        if self.proc is not None and self.proc_owns_screen():
            return {"ok": False, "error": "It's playing a video"}
        if getattr(self, "invite", None) is not None:
            return {"ok": False, "error": "It's been asked already"}
        mine, games = None, []
        if link:
            if not link_core():
                return {"ok": False, "error": "It needs setup.sh run again for the link cable"}
            if link_options(False, urllib.parse.urlsplit(url).hostname) is None:
                return {"ok": False, "error": "Its link cable can't reach this one"}
            games = self.link_games()
            if not games:
                return {"ok": False, "error": "It has no Game Boy games"}
        else:
            why = self.handoff_game_cant(ident["system"])
            if why:
                return {"ok": False, "error": why}
            mine = local_game(games_dir(), ident, [g["path"] for g in find_games() if g["system"] == ident["system"]],
                              save_name)
            if mine is None and copy_place(games_dir(), ident) is None:
                return {"ok": False, "error": "It has another game by that name"}
        if kind == "ask":
            return {"ok": True, "have": bool(mine)} if not link else {"ok": True}
        port, key, file = cmd.get("port"), cmd.get("key") or "", cmd.get("file") or ""
        if (isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536 or not isinstance(key, str)
                or not (link or TOKEN.fullmatch(key)) or not isinstance(file, str) or (file and not TOKEN.fullmatch(file))
                or (not link and mine is None and not file)):
            return {"ok": False, "error": "What's that?"}
        if not self.web_ready():
            return {"ok": False, "error": "There's no screen to show it on"}
        if self.attract_on():
            self.attract_stop()
        pick = next((k for k, g in enumerate(games) if save_name(g["path"]) == ident["name"]), 0)
        self.invite = {"host": host, "url": url, "ident": ident, "link": link, "port": port, "key": key,
                       "file": file, "mine": mine, "games": games, "pick": pick,
                       "from": self.view if self.view in ("home", "list", "now") else "home",
                       "until": time.monotonic() + INVITE_SECS, "shown": None}
        self.view = "invite"
        self.dirty = True
        print(f"together: {host} asks to play {ident['title']}" + (" (a link cable)" if link else ""), flush=True)
        return {"ok": True}

    def together_answered(self, url, host, yes):
        """The other's answer (this one asked it to play): yes, it's coming; or no thanks."""
        run = self.game
        t = self.together_of(run)
        if t is None or t.get("url") != url or not t.get("host"):
            return {"ok": True}
        if yes:
            t["state"] = "coming" if t.get("state") != "on" else "on"
            t["since"] = time.monotonic()              # (the wait for it to join, from now)
            run.send(f"notice {host} said yes" if not t.get("link") else f"notice {host} is linking up")
        else:
            run.send(f"notice {host} said no thanks")
            if not t.get("link"):                      # (a link cable's game plays on, its save back with yours after)
                run.send("netstop")
                run.together = None
        return {"ok": True}

    def link_games(self):
        """Your Game Boy and Game Boy Color games (to link up with), the ones played last first."""
        recent = self.games_recent()
        games = [g for g in find_games() if g["system"] in LINK_SYSTEMS]
        return sorted(games, key=lambda g: (recent.index(g["path"]) if g["path"] in recent else len(recent),
                                            g["title"].lower()))

    def invite_tick(self, now):
        """Asked to play, and not answered in time (or something else is on the screen now): no thanks."""
        inv = getattr(self, "invite", None)
        if inv is None:
            return
        if now > inv["until"] or self.view != "invite":
            self.invite_answer(False, back=self.view == "invite")
            return
        left = int(inv["until"] - now)
        if left != inv["shown"]:                       # (how long's left, said each second)
            self.dirty = True

    def press_invite(self, name, repeat):
        inv = getattr(self, "invite", None)
        if inv is None:
            self.view = "home"
            self.dirty = True
            return None
        if name in ("left", "right") and inv["link"] and len(inv["games"]) > 1:
            inv["pick"] = (inv["pick"] + (1 if name == "right" else -1)) % len(inv["games"])
        elif name in ("a", "start") and not repeat:
            self.invite_answer(True)
        elif name == "b" and not repeat:
            self.invite_answer(False)
        self.dirty = True
        return None

    def invite_answer(self, yes, back=True):
        """The answer: told to the one that asked (on a thread of its own); yes, and its game's opened (copied from it
        first, if this one hasn't got it)."""
        inv, self.invite = self.invite, None
        if inv is None:
            return
        if back:
            self.view = inv["from"]
        self.dirty = True
        threading.Thread(target=together_post, args=(inv["url"], {"kind": "answer", "yes": yes}, HANDOFF_ASK),
                         daemon=True, name="together-answer").start()
        if not yes:
            return
        if inv["link"]:
            self.together_start(inv["games"][inv["pick"]], False, inv["host"], inv["url"], link=True)
            return
        ident, net = inv["ident"], f"{urllib.parse.urlsplit(inv['url']).hostname}:{inv['port']}:{inv['key']}"
        g = {"path": inv["mine"], "title": ident["title"], "system": ident["system"]}
        if g["path"] is not None:
            self.together_start(g, False, inv["host"], inv["url"], net=net)
            return
        dest = copy_place(games_dir(), ident)          # (it hasn't got it: from the other, first)
        if dest is None:
            self.toast("This Pietato has another game by that name", 4)
            return
        owner = self.saves_owner()
        self.toast(f"Copying {ident['title']} from {inv['host']}…", 5)

        def copy():
            try:
                copy_game(f"{inv['url']}/api/handoff/file?token={inv['file']}", dest, ident, owner)
            except OSError as ex:
                print(f"together: {ident['title']} from {inv['host']}: {ex}", flush=True)
                self.soon_jobs.append(lambda: self.toast(f"Couldn't copy {ident['title']} from {inv['host']}", 5))
            else:
                g["path"] = dest
                self.soon_jobs.append(lambda: self.together_start(g, False, inv["host"], inv["url"], net=net)
                                      if self.game is None else None)
            self.wake()
        threading.Thread(target=copy, daemon=True, name="together-game").start()

    def render_invite(self):
        """Another Pietato asks to play: its game (a link cable: and which of yours), and A or B."""
        inv = getattr(self, "invite", None) or {}
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.status_bar(d)
        ident = inv.get("ident") or {}
        host = inv.get("host", "")
        left = max(0, int(inv.get("until", 0) - time.monotonic()))
        inv["shown"] = left
        if inv.get("link"):
            games = inv.get("games") or []
            yours = games[inv.get("pick", 0)]["title"] if games else ""
            rows = [(f"{host} asks to link up, with", F["small"], MUTED),
                    (ident.get("title", ""), F["big"], TEXT),
                    ("and your", F["small"], MUTED),
                    (f"◀  {yours}  ▶" if len(games) > 1 else yours, F["row_b"], TEXT),
                    ("From your game's own save (the last time you saved in it)", F["small"], BODY)]
        else:
            rows = [(f"{host} asks you to play", F["small"], MUTED),
                    (ident.get("title", ""), F["big"], TEXT),
                    ("together, from its game as it is now: you're player 2", F["small"], BODY)]
        rows.append((f"No thanks in {left} s", F["small"], MUTED))
        gaps = {id(F["big"]): 44, id(F["row_b"]): 34}
        total = sum(gaps.get(id(f), 26) for _, f, _ in rows)
        cw = min(W - 40, 560)
        x0, y0 = (W - cw) / 2, max(self.LIST_TOP, (H - self.FOOTER - total - 36) / 2)
        d.rounded_rectangle((x0 - 1, y0 - 1, x0 + cw + 1, y0 + total + 37), radius=17, fill=LINE)
        d.rounded_rectangle((x0, y0, x0 + cw, y0 + total + 36), radius=16, fill=ROW)
        y = y0 + 18
        for text, font, colour in rows:
            h = gaps.get(id(font), 26)
            d.text((W / 2, y + h / 2), self.fit(d, text, font, cw - 40), font=font, fill=colour, anchor="mm")
            y += h
        hints = [("A", "Play")] + ([("◀▶", "Your game")] if inv.get("link") and len(inv.get("games") or []) > 1
                                   else []) + [("B", "No thanks")]
        self.footer(d, hints, always=True)
        self.fb.show(img)
