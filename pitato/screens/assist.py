"""The bot as an assistant, in media mode. What you ask it to do (pitato/assist.py says what that is) is done here at
once: its answer kept in the conversation, said out loud when it has a voice (not over music), and shown as a notice
when its page isn't up. Timers, the focus timer and reminders speak up as they come due, wherever you are, and the
next one to end shows in the status bar. The Bot's Today page: your list, reminders, timers and notes."""
import random
import re
import threading
import time

from ..theme import ACCENT, BG, BODY, MUTED, ROW, TEXT
from ..assist import best_match, BREAK_MINS, FOCUS_MINS, parse, say_clock, say_duration, say_list, words_of
from ..util import item
from ..net import cam_key
from ..library import LIBRARY, read_streams
from ..radio import RADIO_GENRES, rb_stations
from ..weather import wx_words
from ..games import bios_missing, built_for_other_pi, find_core, find_games, neogeo_unknown, plain_title, system
from ..tv import channel_row, ia_row, live_pick, SHELVES
from .games import fold, game_matches

MUSIC_WORDS = ("music", "song", "songs", "album", "albums", "playlist", "tunes", "track", "tracks", "artist", "band",
               "radio", "station", "stations", "fm")
ALL_MUSIC = ("music", "my music", "some music", "songs", "my songs", "some songs", "something", "anything",
             "some tunes", "tunes", "a song", "my playlist", "everything", "all my music", "all my songs")
RADIO_ASK = ("the radio", "radio", "some radio", "a radio station", "a station", "the station", "my radio")
TODAY_ROWS = 7              # things on your list shown on the Today page at once
ANNOUNCE_SECS = 8           # how long a timer's or a reminder's notice stays up
ALARM_LOOK = 6              # ...and the bot's face looks up, for this long
ASKED_FOR = 20              # a question it asked (shut down? a game?): yes or no to it, till then
STEER_SECS = 0.7            # a camera told to turn (left, up...): it turns this long
WATCH_TOONS = ("cartoon", "cartoons", "toons", "toon", "anime")
WATCH_FILMS = ("movie", "movies", "film", "films", "old movie", "old movies", "old film", "old films",
               "classic film", "classic films", "classic movie")
WATCH_ANY = ("tv", "television", "channel", "channels", "tv channel", "any channel", "show", "shows", "something",
             "something to watch", "something on tv")
WATCH_FILLER = ("my", "the", "some", "a", "an", "on", "channel", "show", "live", "stream", "tv")   # (said with a name)
QUIET = ("play", "pause", "resume", "next", "previous", "louder", "quieter", "volume", "mute", "unmute", "open",
         "home", "shuffle", "game", "watch")  # (what it says to these is shown, not said out loud: the music, the
                                               # game or what you watch says it)
INFO = ("time", "date", "weather", "help", "playing")   # (asked of a bot that's set up, its model answers these, in
                                                        # its own way: it knows them too)


def radio_genre(w):
    """The radio's kind of music named ("rock", "classic rock", "jazz"), or None."""
    words = set(words_of(w))
    return next((g for g in RADIO_GENRES if words and words <= set(words_of(" ".join([g[0]] + g[2])))), None)


def said_game(games, what, whole=False):
    """The game of yours named in what you said: each word said a word of its name ("mario": Super Mario World), or
    run together, the start of it ("pacman": Pac-Man); whole: its name, all of it ("tetris"). The likeliest first: one
    whose name starts so, then the shortest. None for none."""
    small = ("the", "a", "an", "of", "game")
    words = [x for x in fold(what).split() if x not in small]
    if not words:
        return None
    joined = "".join(words)
    hits = []
    for g in games:
        for n in dict.fromkeys((fold(g.get("label") or ""), fold(plain_title(g["title"])), fold(g["title"]))):
            nw = n.split()
            if not nw:
                continue
            if whole:
                ok = [x for x in nw if x not in small] == words or n.replace(" ", "") == joined
            else:
                ok = all(x in nw for x in words) or (len(joined) >= 4 and n.replace(" ", "").startswith(joined))
            if ok:
                hits.append(((not n.startswith(words[0]), len(nw), g["title"].lower()), g))
                break
    hits.sort(key=lambda h: h[0])
    return hits[0][1] if hits else None


class AssistScreen:
    # -- what you ask -------------------------------------------------------------------------------------------
    def assist_heard(self, text):
        """text asked of the bot (said after its wake phrase, typed on its page, or sent from the web page): done here
        if it's something done here (True: its answer kept and said), else False (its model answers)."""
        ask = parse(text, call=self.bot_calls())
        if ask is None or (ask.kind in INFO and self.friend.ready()):
            return False
        asked = self.assist_asking()
        if ask.kind in ("yes", "no") and not asked:
            return False                               # (not an answer to a question of its own: its model's)
        quiet = ask.kind in QUIET or (ask.kind == "yes" and asked.get("quiet"))
        try:
            reply = self.assist_do(ask)
        except Exception as ex:                        # (whatever it was, the bot says so rather than falling over)
            print(f"the bot couldn't do that ({ask!r}): {ex!r}", flush=True)
            reply = "That didn't work"
        if reply is None:
            return False
        fr = self.friend
        fr.add("you", " ".join(str(text).split())[:400], "chat")
        if reply:
            fr.add("friend", reply, "done")
            self.assist_tell(reply, speak=not quiet)
        self.friend_scroll = 0
        self.dirty = True
        return True

    def assist_tell(self, text, speak=True, secs=4):
        """An answer or a notice: on the screen (a notice, unless the Bot's page is up) and out loud (when it has a
        voice, and nothing's playing)."""
        if not self.on_friend_page() and self.active and text:
            self.toast(text, secs)
        if speak and text and self.bot_voice() and self.bot_speaks() and not self.proc:
            self.say_aloud(text)

    def ack(self):
        """A word of its style before what it did ("Okay.", "Aye!", "Very good.")."""
        words = self.friend.style()["ok"]
        return random.choice(words) + " " if words else ""

    def bot_calls(self):
        """What you call it, before or after what you ask: its wake phrase and its name ("hey potato", "potato")."""
        wake = self.bot_wake()
        return tuple(dict.fromkeys(c for c in (wake, wake.split()[-1] if wake else "") if c))

    def assist_do(self, ask):
        """Does what was asked: its answer ("" for none to give), or None if it's for the model after all."""
        k, a, A = ask.kind, ask.args, self.assist
        h24 = self.setting("clock") == "24-hour"
        asked, self.assist_pending = self.assist_asking(), None   # (anything else said: its question's gone)
        if k == "yes":
            return asked["do"]()
        if k == "no":
            return f"Okay, no {asked['what']} then." if asked.get("what") else "Okay."
        if k == "bored":
            return self.assist_bored()
        if k == "game":
            return self.assist_game(a["name"])
        if k == "watch":
            return self.assist_watch(a["what"])
        if k in ("update", "shutdown", "reboot"):
            return self.assist_power_ask(k, a.get("app"))
        if k == "cam_turn":
            return self.assist_cam_turn(a["step"], a["which"])
        if k == "cam_steer":
            return self.assist_steer(a["way"], a["which"])
        if k == "timer":
            A.add_timer(a["secs"], a["label"])
            what = f"{a['label'].capitalize()} timer" if a["label"] else "Timer"
            return f"{self.ack()}{what} set for {say_duration(a['secs'])}."
        if k == "timer_stop":
            gone = A.drop_timers(a["label"])
            if not gone:
                return "There's no timer running."
            return f"{self.ack()}{'Timer' if len(gone) == 1 else str(len(gone)) + ' timers'} cancelled."
        if k == "timer_left":
            now = time.time()
            mine = A.own_timers() + ([A.focus()] if A.focus() else [])
            if not mine:
                return "There's no timer running."
            return " ".join(f"{self.timer_name(x).capitalize()} has {say_duration(max(1, x['until'] - now))} left."
                            for x in mine[:3])
        if k == "focus":
            A.add_timer(a["secs"], kind="focus")
            return (f"{self.ack()}Focus timer on for {say_duration(a['secs'])}. I'll tell you when it's time for a "
                    f"break.")
        if k == "focus_stop":
            gone = A.drop_timers(kinds=("focus", "break"))
            return f"{self.ack()}Focus timer off." if gone else "The focus timer isn't on."
        if k == "break":
            A.add_timer(a["secs"], kind="break")
            return f"{self.ack()}Enjoy your break. I'll tell you when {say_duration(a['secs'])} is up."
        if k == "task_add":
            text = a["text"]
            if not A.add_task(text):
                return f"{text[:1].upper() + text[1:]} is on your list already."
            return f"{self.ack()}Added {text} to your list."
        if k == "tasks":
            todo = [x["text"] for x in A.open_tasks()]
            if not todo:
                return "Your list is empty."
            n = len(todo)
            return f"You have {n} thing{'s' if n != 1 else ''} on your list: {say_list(todo[:8])}" + (
                f", and {n - 8} more." if n > 8 else ".")
        if k == "task_done":
            it = best_match(A.open_tasks(), a["text"])
            if it is None:
                if "list" in ask.said or ask.said.startswith(("check off", "cross off", "tick off", "mark")):
                    return f"I couldn't find {a['text']} on your list."
                return None                            # ("check the weather": not one of yours, so the model's)
            A.tick_task(it)
            left = len(A.open_tasks())
            return f"{self.ack()}Checked off {it['text']}." + (" That's everything!" if not left else "")
        if k == "task_remove":
            it = best_match(A.tasks, a["text"])
            if it is None:
                return f"I couldn't find {a['text']} on your list."
            A.drop_task(it)
            return f"{self.ack()}Took {it['text']} off your list."
        if k == "tasks_clear":
            n = A.clear_tasks(a["done_only"])
            if a["done_only"]:
                return f"{self.ack()}Cleared {n} done thing{'s' if n != 1 else ''}." if n else "Nothing's done yet."
            return f"{self.ack()}Your list is clear." if n else "Your list was empty already."
        if k == "note_add":
            A.add_note(a["text"])
            return f"{self.ack()}Noted."
        if k == "notes":
            notes = [x["text"] for x in A.notes]
            if not notes:
                return "You haven't asked me to note anything yet."
            n = len(notes)
            return (f"You have {n} note{'s' if n != 1 else ''}." if n > 3 else "") + " " + " ".join(
                f"{x.rstrip('.')}." for x in notes[-3:])
        if k == "notes_clear":
            n = A.clear_notes(a["last_only"])
            if not n:
                return "There aren't any notes to forget."
            return f"{self.ack()}Forgot that." if a["last_only"] else f"{self.ack()}Your notes are gone."
        if k == "remind":
            A.add_reminder(a["at"], a["text"])
            return f"{self.ack()}I'll remind you to {a['text']} {self.when_text(a['at'], h24)}."
        if k == "alarm":
            A.add_reminder(a["at"], "Alarm", alarm=True)
            return f"{self.ack()}Alarm set for {say_clock(a['at'], h24=h24)}."
        if k == "alarm_stop":
            gone = A.drop_alarms()
            return f"{self.ack()}{'Alarm' if len(gone) == 1 else str(len(gone)) + ' alarms'} off." if gone else \
                "You don't have an alarm set."
        if k == "timer_how":
            return 'For how long? Say "set a timer for 10 minutes".'
        if k == "reminders":
            rs = A.reminders
            if not rs:
                return "You don't have any reminders."
            return f"You have {len(rs)} reminder{'s' if len(rs) != 1 else ''}: " + say_list(
                [f"{'your alarm' if r.get('alarm') else r['text']} {self.when_text(r['at'], h24)}"
                 for r in rs[:5]]) + "."
        if k == "reminders_stop":
            gone = A.drop_reminders(a["text"])
            if not gone:
                return "There's no reminder like that." if a["text"] else "You don't have any reminders."
            return f"{self.ack()}Cancelled {len(gone)} reminder{'s' if len(gone) != 1 else ''}."
        if k == "time":
            return f"It's {self.clock_text(time.localtime())}."
        if k == "date":
            t = time.localtime()
            return f"It's {time.strftime('%A, %B', t)} {t.tm_mday}."
        if k == "weather":
            return self.weather_words()
        if k == "help":
            return ("I can play your music, the radio and your games, put on cartoons, a film or a channel, set "
                    "timers and a focus timer, keep your list, notes and reminders, open apps, turn your lights on and "
                    "off, turn the camera, and update, restart or shut down the Pi. Or we can just chat.")
        if k == "open":
            return self.assist_open(a["app"])
        if k == "home":
            self.go_home()
            self.view = "home"
            return ""
        if k == "lights":
            return self.assist_lights(a["on"], a["which"])
        return self.assist_media(ask)

    # -- a question of its own: yes does it ----------------------------------------------------------------------------
    def assist_ask(self, question, do, what="", quiet=False):
        """Asked before it does something (shuts down, starts a game it thought of): yes does it, said or typed (said
        straight after: no wake phrase needed), for a little while. do() gives what it says as it does it (quiet: shown,
        not said, as the game or what you watch has the speaker)."""
        self.assist_pending = {"do": do, "what": what, "quiet": quiet, "until": time.monotonic() + ASKED_FOR}
        if self.ears.on:
            self.ears.wake_now()                       # (your answer: no wake phrase needed)
        return question

    def assist_asking(self):
        """The question it's waiting on an answer to, or None."""
        p = getattr(self, "assist_pending", None)
        return p if p and time.monotonic() < p["until"] else None

    # -- bored: something to do -------------------------------------------------------------------------------------
    def assist_bored(self):
        """A game of yours to play, or cartoons to watch: yes starts it."""
        games = self.game_choices()
        if games:
            g = random.choice(games)
            name = plain_title(g["title"]) or g["title"]
            q = random.choice([f"How about a game of {name}? Say yes, or ask me to put on some cartoons.",
                               f"Want to play {name}? Say yes, or I can put on some cartoons.",
                               f"We could play {name}, or watch some cartoons. Say yes for the game."])
            return self.assist_ask(q, lambda: self.game_start(g), "game", quiet=True)
        q = random.choice(["How about some cartoons? Say yes, or ask me to play Snake.",
                           "Want to watch some cartoons? Say yes, or say \"play a game\" for Snake."])
        return self.assist_ask(q, lambda: self.watch_shelf("toons"), "cartoons", quiet=True)

    # -- games ----------------------------------------------------------------------------------------------------
    def game_choices(self):
        """Your games that start here (their emulator's here, with what they need), as the Games list has them."""
        out = []
        for g in find_games():
            core = find_core(g["system"])
            if not core or bios_missing(core, g["path"]) or built_for_other_pi(core) \
                    or (g["system"] == "neogeo" and neogeo_unknown(g["path"])):
                continue
            _, badge, name = system(g["system"])[:3]
            out.append(dict(item(g["path"], g["title"], "game", g["path"], sub=name), system=g["system"],
                            icon=badge, label=plain_title(g["title"])))
        return out

    def game_start(self, g):
        self.game_open(g)
        return f"Starting {g.get('label') or g['title']}." if self.game is not None else ""

    def assist_game(self, name=""):
        """A game of yours by name, or any of them; Snake when you have none of your own."""
        games = self.game_choices()
        if name:
            words = fold(name).split()
            hit = said_game(games, name) or next((g for g in games if words and game_matches(g, words)), None)
            if hit is None:
                return f"I couldn't find {name} in your games."
            return self.game_start(hit)
        if not games:
            self.web_tab("Snake")
            return "You haven't any games of your own yet, so here's Snake."
        return self.game_start(random.choice(games))

    # -- something to watch -------------------------------------------------------------------------------------------
    def watch_shelf(self, pick, folder=None, title=None):
        """A cartoon or an old film (the TV menu's own, from the Internet Archive): one of a folder's, or any."""
        shelves = SHELVES[pick][0]
        folder = folder or random.choice(sorted(shelves))
        rows = [ia_row(folder, *t) for t in shelves[folder]]
        i = next((k for k, r in enumerate(rows) if r["title"] == title), None) if title else None
        i = random.randrange(len(rows)) if i is None else i
        self.play(rows, i)
        return f"Here's {rows[i]['title']}."

    def stream_rows(self):
        """Your streams (TV > Streams)."""
        si = self.tab_index("streams")
        return read_streams(LIBRARY[si]["files"]) if si is not None else []

    def assist_watch(self, what):
        """Something to watch: cartoons or an old film (the TV menu's own), the news or sports (Plex's live channels, or
        your streams), anything (a channel), or one by name."""
        w = fold(what)
        if w in WATCH_TOONS:
            return self.watch_shelf("toons")
        if w in WATCH_FILMS:
            return self.watch_shelf("movies")
        if w in ("news", "sports", "sport"):
            return self.watch_live("sports" if w.startswith("sport") else "news")
        if w in ("video", "videos", "my videos", "my video", "a video"):
            self.web_tab("Videos")
            return "Here are your videos."
        if w in WATCH_ANY:
            if self.plex.signed_in:
                return self.watch_live("any")
            streams = self.stream_rows()
            if streams:
                i = random.randrange(len(streams))
                self.play(streams, i)
                return f"Here's {streams[i]['title']}."
            return self.watch_shelf(random.choice(["toons", "toons", "movies"]))
        words = [x for x in w.split() if x not in WATCH_FILLER] or w.split()   # one by name: a stream, a Plex channel,
        streams = self.stream_rows()                                       # a cartoon or a film, or a video of yours
        hit = next((k for k, r in enumerate(streams) if all(x in fold(r["title"]) for x in words)), None)
        if hit is not None:
            self.play(streams, hit)
            return f"Here's {streams[hit]['title']}."
        chans = self.live_fresh() or []
        rows = [channel_row(c) for c in chans]
        hit = next((k for k, r in enumerate(rows) if all(x in fold(r["title"]) for x in words)), None)
        if hit is not None:
            self.play(rows, hit)
            return f"Here's {rows[hit]['title']}."
        for pick, (shelves, _, _) in SHELVES.items():
            for folder, entries in shelves.items():
                if all(x in fold(folder) for x in words):
                    return self.watch_shelf(pick, folder)
                t = next((e for e in entries if all(x in fold(e[0]) for x in words)), None)
                if t is not None:
                    return self.watch_shelf(pick, folder, t[0])
        vi = next((k for k, t in enumerate(LIBRARY) if t.get("kind") == "video"), None)
        if vi is not None:                             # (one of your videos)
            if vi not in self.items:
                self.load_tab(vi)
            vids = [it for it in self.tab_items(vi) if it.get("kind") == "video"]
            hit = next((k for k, r in enumerate(vids) if all(x in fold(r["title"]) for x in words)), None)
            if hit is not None:
                self.play(vids, hit)
                return f"Here's {vids[hit]['title']}."
        return f"I couldn't find {what} to watch."

    def watch_live(self, pick):
        """Plex's live channels of a kind (news, sports; "any": all of them), or your streams of it."""
        label = {"news": "news", "sports": "sports"}.get(pick, "TV")
        if not self.plex.signed_in:
            return self.watch_streams(pick) or f"Live {label} channels come from Plex. Sign in on TV > Plex first."
        if self.live_fresh() is not None:
            return self.watch_live_now(pick, label)

        def job():                                     # (Plex asked on a thread, then played on the main one)
            try:
                self.live_list()
                self.soon(lambda: self.assist_said(self.watch_live_now(pick, label)))
            except Exception:
                self.soon(lambda: self.assist_said("Plex didn't answer. Try again in a minute."))
            self.wake()
        threading.Thread(target=job, daemon=True, name="bot-live").start()
        return f"Finding some {label}…"

    def watch_streams(self, pick):
        """One of your streams of a kind (its name says news or sports; "any": the first): playing it, its answer; or
        None when there's none."""
        streams = [r for r in self.stream_rows() if pick == "any" or pick.rstrip("s") in fold(r["title"])]
        if not streams:
            return None
        self.play(streams, 0)
        return f"Here's {streams[0]['title']}."

    def watch_live_now(self, pick, label):
        rows = [channel_row(c) for c in self.live_fresh() or [] if pick == "any" or live_pick(pick, c)]
        if not rows:                                   # (none on Plex just now: one of yours, or cartoons)
            return self.watch_streams(pick) or (self.watch_shelf("toons") if pick == "any" else
                                                f"There are no {label} channels on Plex right now.")
        i = random.randrange(len(rows)) if pick == "any" else 0
        self.play(rows, i)
        return f"Here's {rows[i]['title']}."

    def later(self, secs, job):
        """job() on the main thread in a while (a camera let go, say)."""
        def go():
            self.soon(job)
            self.wake()
        t = threading.Timer(secs, go)
        t.daemon = True
        t.start()

    def assist_said(self, text):
        """What it says when something it set off finishes (on the main thread): kept in the conversation, shown."""
        if text:
            self.friend.add("friend", text, "done")
            self.assist_tell(text, speak=False)

    # -- the Pi itself: update, restart, shut down -------------------------------------------------------------------
    def assist_power_ask(self, kind, app=False):
        if kind == "update":
            if self.updater.going():
                return "It's updating already."
            q = ("There's a new version. Update now? The Pi restarts when it's done. Say yes."
                 if self.updater.available()
                 else "Look for a new version, and update if there is one? The Pi restarts if it does. Say yes.")
            return self.assist_ask(q, lambda: self.assist_power("update"), "update")
        if kind == "shutdown":
            return self.assist_ask("Shut down the Pi? Say yes.", lambda: self.assist_power("poweroff"), "shutting down")
        act = "restart" if app else "reboot"
        return self.assist_ask("Restart media mode? Say yes." if app else "Restart the Pi? Say yes.",
                               lambda: self.assist_power(act), "restart")

    def assist_power(self, act):
        """Said yes to: as System's rows do it."""
        if act == "update":
            err = self.updater.begin()
            if err:
                return err
            self.show_update()
            return ""
        self.system_do(act)
        return ""

    # -- the camera: its picture turned, or it turned ---------------------------------------------------------------
    def cam_called(self, addr):
        """What a camera's called: its name in camera.txt (before the Camera tab's been opened, too), or name_of's."""
        cam, k = self.camera, cam_key(addr)
        for c in cam.cams or cam.listed(LIBRARY[self.tab_index("camera")]["files"]):
            if cam_key(c["addr"]) == k and c.get("name"):
                return c["name"]
        return cam.name_of(addr)

    def assist_cam_turn(self, step, which=""):
        cam = self.camera
        addr = self.friend_camera(which)
        if not addr:
            return "There's no camera. Add one on the Camera tab."
        deg = self.camera_turn(addr, step if step else -cam.turn_of(addr), quiet=True)
        name = self.cam_called(addr)
        return f"{self.ack()}{name}'s picture is turned {deg}°." if deg else \
            f"{self.ack()}{name}'s picture is the right way up."

    def assist_steer(self, way, which=""):
        """A camera that turns (an OBSBOT on a Pi), turned a little that way; its picture on the screen first."""
        cam = self.camera
        addr = self.friend_camera(which)
        if not addr:
            return "There's no camera. Add one on the Camera tab."
        if not cam.may_steer(addr):
            return f"{self.cam_called(addr)} can't turn. Say \"rotate the camera\" to turn its picture."
        wait = 0.0
        if not (self.on_camera_page() and cam_key(cam.addr or "") == cam_key(addr)):
            self.web_tab("Camera")
            self.camera_open(addr)
            wait = 2.5                                 # (a moment to reach it first)

        def go():
            if not self.on_camera_page():
                return
            if not cam.steers:
                self.assist_said(f"{self.cam_called(addr)} can't turn.")
                return
            cam.press(way)
            self.dirty = True

            def stop():
                cam.release(way)
                self.dirty = True
            self.later(STEER_SECS, stop)
        if wait:
            self.later(wait, go)
        else:
            go()
        return f"{self.ack()}Turning {way}."

    def timer_name(self, x):
        return {"focus": "the focus timer", "break": "your break"}.get(x.get("kind"), (
            f"the {x['label']} timer" if x.get("label") else "your timer"))

    @staticmethod
    def when_text(at, h24=False):
        """"at 5:00 PM", "tomorrow at 9:00 AM", "in 20 minutes" (soon: how soon)."""
        left = at - time.time()
        if left < 3600:
            return f"in {say_duration(max(60, round(left / 60) * 60))}"
        said = say_clock(at, h24=h24)
        return said if said.startswith(("tomorrow", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")) else f"at {said}"

    def weather_words(self):
        w = self.weather.data
        if not w or w.get("temp") is None:
            return "I don't have the weather yet. Set where you are on the Weather page."
        out = f"It's {round(w['temp'])} degrees and {wx_words(w.get('code'))[0].lower()}."
        days = w.get("days") or []
        if days and days[0].get("hi") is not None:
            out += f" Today's high is {round(days[0]['hi'])}, the low {round(days[0]['lo'])}."
            if (days[0].get("rain") or 0) >= 40:
                out += f" There's a {days[0]['rain']}% chance of rain."
        return out

    def assist_open(self, app):
        if app == "Today":                             # (the Bot's own page of your list and timers)
            self.set_setting("bot_mode", "today")
            self.web_tab("Bot")
            return ""
        if self.web_tab(app) is None:
            return None
        return ""

    # -- music, the radio, the sound ------------------------------------------------------------------------------
    def music_tab(self):
        return next((k for k, t in enumerate(LIBRARY) if t["type"] == "files" and t.get("kind") == "audio"), None)

    def assist_media(self, ask):
        k, a = ask.kind, ask.args
        if k == "pause":
            if self.voice.speaking:
                self.voice.stop()
                return ""
            if not self.proc:
                return "Nothing's playing."
            if not self.paused:
                self.cmd("pause")
                self.paused = True
            return "Paused."
        if k == "resume":
            if self.proc and self.paused:
                self.cmd("pause")
                self.paused = False
                return "Playing again."
            if self.proc:
                return "It's playing."
            return self.assist_play("music")
        if k in ("next", "previous"):
            if not self.proc:
                return "Nothing's playing."
            self.skip(1 if k == "next" else -1)
            return ""
        if k in ("louder", "quieter"):
            self.set_volume(10 if k == "louder" else -10)
            return f"Volume {self.volume}."
        if k == "volume":
            self.set_volume(a["pct"] - self.volume)
            return f"Volume {self.volume}."
        if k in ("mute", "unmute"):
            if not self.proc:
                return "Nothing's playing."
            self.cmd("pausing_keep mute " + ("1" if k == "mute" else "0"))
            return "Muted." if k == "mute" else "Sound back on."
        if k == "shuffle":
            self.shuffle = not self.shuffle
            return f"Shuffle {'on' if self.shuffle else 'off'}."
        if k == "playing":
            if not self.proc or not self.cur:
                return "Nothing's playing."
            if self.kind == "radio":
                song = self.meta.get("song")
                return f"This is {self.cur['title']}" + (f", playing {song}." if song else ".")
            title = self.meta.get("title") or self.cur.get("title")
            who = self.meta.get("artist")
            return f"This is {title}" + (f" by {who}." if who else ".")
        if k == "play":
            return self.assist_play(a["what"])
        return None

    def assist_play(self, what):
        """A game of yours by its name, your music (a song, an artist's or a folder's, or all of it, shuffled), else a
        station: its answer, or None when it doesn't sound like music at all (the model's, then)."""
        w = " ".join(what.lower().split())
        radio = w in RADIO_ASK or bool(set(words_of(w)) & {"radio", "station", "fm"})
        musical = radio or w in ALL_MUSIC or bool(set(words_of(w)) & set(MUSIC_WORDS)) or radio_genre(w) is not None
        games = [] if musical else self.game_choices()
        whole = said_game(games, w, whole=True)        # ("play tetris", "play super mario world": the game)
        if whole is not None:
            return self.game_start(whole)
        mi = self.music_tab()
        if not radio and mi is not None:
            if mi not in self.items:
                self.load_tab(mi)
            songs = [it for it in self.tab_items(mi) if it.get("kind") == "audio"]
            if w in ALL_MUSIC:
                if not songs:
                    return "There's no music in your Music folder yet."
                songs = list(songs)
                random.shuffle(songs)
                self.play(songs, 0, show=False)
                self.queue_random = True
                return f"{self.ack()}Playing your music, shuffled."
            found = self.music_like(songs, w)
            if found:
                self.play(found, 0, show=False)
                one = found[0].get("title") or "it"
                return f"{self.ack()}Playing {one}" + (f" and {len(found) - 1} more." if len(found) > 1 else ".")
        part = said_game(games, w)                     # ("play mario": a game with it in its name, after your music)
        if part is not None:
            return self.game_start(part)
        station = self.station_like(w, radio)
        if station is not None:
            return station
        if radio or len(w.split()) <= 3 or set(words_of(w)) & set(MUSIC_WORDS):
            return f"I couldn't find {what} in your music."
        return None

    @staticmethod
    def music_like(songs, w):
        """The songs whose names or folders have every word asked for ("so what", "miles davis", "jazz"), best first."""
        want = [x for x in words_of(w) if x not in ("song", "songs", "music", "by", "album", "the", "some")]
        if not want:
            return []
        scored = []
        for k, it in enumerate(songs):
            title = set(words_of(it.get("title") or ""))
            where = set(words_of(it.get("src") or ""))
            if all(x in title or x in where for x in want):
                scored.append((0 if all(x in title for x in want) else 1, k, it))
        scored.sort(key=lambda s: (s[0], s[1]))
        return [it for _, _, it in scored]

    def station_like(self, w, radio):
        """A station for what was asked (one of yours, Radio Paradise, or a genre's busiest): playing it, its answer;
        None if there's none like it."""
        ri = self.tab_index("radio")
        if ri is None:
            return None
        tab = LIBRARY[ri]
        mine = [it for it in self.radio_root(tab) if it.get("kind") == "radio"]
        bare = re.sub(r"\b(?:the|radio|station|fm|some|on|a|my|play)\b", " ", w) if radio else w
        bare = " ".join(bare.split())
        if not bare:                                   # "the radio": the first of yours (Radio Paradise, if none)
            it = mine[0] if mine else None
            if it is None:
                return None
            self.play([it], 0, show=False)
            return f"{self.ack()}Playing {it['title']}."
        hit = next((it for it in mine if bare and all(x in words_of(it["title"]) for x in words_of(bare))), None)
        if hit is not None:
            self.play([hit], 0, show=False)
            return f"{self.ack()}Playing {hit['title']}."
        genre = next((g for g in RADIO_GENRES if set(words_of(bare)) & set(words_of(" ".join([g[0]] + g[2])))), None)
        if genre is None:
            return None
        self.assist_genre(genre)
        return f"{self.ack()}Finding {genre[0]} radio…"

    def assist_genre(self, genre):
        """A genre's busiest station, played (fetched on a thread, or as the Radio tab kept them)."""
        key = "genre:" + genre[0]
        cached = (self.state.get("radio") or {}).get(key)

        def go(items):
            if items:
                self.play(list(items), 0, show=False)
            else:
                self.toast(f"Couldn't find {genre[0]} radio", 4)
        if cached and cached.get("items") and time.time() - cached["t"] < 86400:
            return go(cached["items"])

        def job():
            try:
                found = rb_stations(tags=genre[2])
            except Exception:
                found = []
            self.soon(lambda: go(found))
        threading.Thread(target=job, daemon=True, name="bot-radio").start()

    # -- the lights ----------------------------------------------------------------------------------------------
    def assist_lights(self, on, which):
        li = next((k for k, t in enumerate(LIBRARY) if t["type"] == "lights"), None)
        if li is None:
            return None
        lt = self.lights
        lt.load(LIBRARY[li]["files"])
        if not lt.configured:
            return "Your lights come through Home Assistant: set it up on the Lights page first."

        def job():
            try:
                lt.refresh()
                rows = [r for r in lt.lights() if r["kind"] in ("light", "plug")]
                if which:
                    rows = [r for r in rows if all(x in words_of(r["name"]) for x in words_of(which))]
                rows = [r for r in rows if r["on"] != on]
                for r in rows:
                    domain = "light" if r["kind"] == "light" else r["entity"].split(".", 1)[0]
                    lt.service(domain, "turn_on" if on else "turn_off", entity_id=r["entity"])
                text = (f"Turned {'on' if on else 'off'} {say_list([r['name'] for r in rows[:4]])}." if rows
                        else f"The {which + ' ' if which else ''}lights are {'on' if on else 'off'} already."
                        if not which or any(which in r["name"].lower() for r in lt.lights())
                        else f"I couldn't find the {which} lights.")
            except Exception as ex:
                text = f"Couldn't reach Home Assistant ({lt.why(ex)})"
            self.soon(lambda: (self.friend.add("friend", text, "done"), self.assist_tell(text)))
        threading.Thread(target=job, daemon=True, name="bot-lights").start()
        return f"{self.ack()}Turning {'on' if on else 'off'} the {which + ' ' if which else ''}lights."

    # -- timers and reminders coming due --------------------------------------------------------------------------
    def assist_tick(self, now):
        """The main loop: timers and reminders said as they come due (twice a second, at most), and the Today page's
        timers counting down each second while it's up."""
        if now < self.assist_next:
            return
        self.assist_next = now + 0.5
        A = self.assist
        if A.timers or A.reminders:
            for kind, it in A.due(time.time()):
                self.assist_announce(kind, it)
        if A.timers and self.on_today_page() and not self.resting:
            sec = int(time.time())
            if sec != self.assist_shown:
                self.assist_shown = sec
                self.dirty = True

    def assist_announce(self, kind, it):
        """A timer or a reminder come due: said out loud (or a chime), kept in the conversation, and on the screen
        (over a video, too)."""
        if kind == "reminder" and it.get("alarm"):
            body = f"It's {self.clock_text(time.localtime())}. Here's your alarm!"
        elif kind == "reminder":
            body = f"Reminder: {it['text'].rstrip('.')}."
        elif kind == "focus":
            n = self.assist.focus_count()
            body = f"Focus time's up. Take {BREAK_MINS} minutes." + (f" That's {n} today." if n > 1 else "")
        elif kind == "break":
            body = "Break's over. Ready to focus again?"
        else:
            body = f"The {it['label']} timer's up!" if it.get("label") else "Time's up!"
        hey = self.friend.style()["hey"]
        text = f"{hey} {body}" if hey else body
        self.friend.add("friend", text, "alarm")
        self.alarm_until = time.monotonic() + ALARM_LOOK
        self.stir()                                    # (the screen awake to show it)
        if self.proc and self.proc_owns_screen():
            self.osd(text, ANNOUNCE_SECS * 1000)       # (a video: over it)
        elif self.active:
            self.toast(text, ANNOUNCE_SECS)
        if self.bot_voice() and self.bot_speaks() and not self.proc:
            self.say_aloud(text)
        else:
            self.voice.chime(self.chime_device(), self.volume)

    def chime_device(self):
        from ..screen import aplay_device
        return aplay_device(self.setting("sound"))

    def assist_status(self):
        """The status bar's word on the next timer to end ("4 min", "Focus 18 min"), or "" (by the minute: it isn't
        drawn again each second)."""
        A = self.assist
        if not A.timers:
            return ""
        x = A.timers[0]
        mins = max(1, int((x["until"] - time.time() + 59.999) // 60))
        when = f"{mins // 60}h {mins % 60:02d}" if mins >= 60 else f"{mins} min"
        return {"focus": "Focus ", "break": "Break "}.get(x.get("kind"), "") + when

    @staticmethod
    def countdown(left):
        """"4:05", "1:02:03"."""
        left = max(0, int(left + 0.999))
        return f"{left // 3600}:{left % 3600 // 60:02d}:{left % 60:02d}" if left >= 3600 else \
            f"{left // 60}:{left % 60:02d}"

    # -- the Bot's Today page --------------------------------------------------------------------------------------
    def today_rows(self):
        """The things on your list, open ones first (the ticked-off ones after, most recent first)."""
        A = self.assist
        done = sorted([x for x in A.tasks if x.get("done")], key=lambda x: -(x.get("done_t") or 0))
        return A.open_tasks() + done

    def press_today(self, name, repeat):
        rows = self.today_rows()
        n = len(rows)
        self.today_sel = max(0, min(self.today_sel, n - 1)) if n else 0
        if name in ("l", "r", "b"):
            return "pass"
        if name in ("up", "down"):
            if n:
                self.today_sel = (self.today_sel + (1 if name == "down" else -1)) % n
            self.confirm = (None, 0.0)
        elif repeat:
            return None
        elif name == "a":
            self.open_keyboard("Add to your list, or ask: \"remind me at 5 to…\"", "", self.today_typed, limit=160)
        elif name == "x" and n:
            it = rows[self.today_sel]
            self.assist.tick_task(it, not it.get("done"))
            self.toast("Done" if it.get("done") else "Back on your list", 2)
        elif name == "select" and n:
            it = rows[self.today_sel]
            if self.confirm[0] == "taskdrop":
                self.confirm = (None, 0.0)
                self.assist.drop_task(it)
                self.toast(f"Took {it['text']} off your list", 2)
            else:
                self.confirm = ("taskdrop", time.monotonic() + 4)
                self.toast("Press SELECT again to take it off your list", 3)
        elif name == "y":
            fr = self.friend
            if not fr.ready():
                self.toast("Set up your bot to plan your day: Settings > Bot", 4)
            elif fr.say("Plan my day: what should I do when, with what's on my list, my reminders and the weather?"):
                self.set_setting("bot_mode", "chat")
                self.friend_opened()
            else:
                self.toast("Still thinking about the last one", 2)
        elif name == "start":                          # the focus timer: on, or off
            if self.assist.focus():
                self.assist.drop_timers(kinds=("focus", "break"))
                self.toast("Focus timer off", 2)
            else:
                self.assist.add_timer(FOCUS_MINS * 60, kind="focus")
                self.toast(f"Focus for {FOCUS_MINS} minutes. I'll tell you when it's time for a break", 4)
        self.dirty = True
        return None

    def today_typed(self, text):
        """Typed on the Today page: something it does (a reminder, a timer...), else a thing for your list."""
        if not text.strip():
            return
        if not self.assist_heard(text):
            if self.assist.add_task(text):
                self.toast(f"Added {text.strip()} to your list", 2)

    def render_today(self, d, x0, x1, top, bottom):
        """Your timers, your list, your reminders and your notes, on the right of the Bot's page."""
        F, A = self.fonts, self.assist
        now = time.time()
        h24 = self.setting("clock") == "24-hour"
        y = top + 6
        timers = list(A.timers)
        for x in timers[:2]:                           # timers: how long's left, a bar going down
            left = max(0, x["until"] - now)
            clock = self.countdown(left)
            d.rounded_rectangle((x0, y, x1, y + 52), radius=14, fill=ROW)
            d.text((x0 + 16, y + 18), self.timer_name(x).capitalize(), font=F["small"], fill=BODY, anchor="lm")
            d.text((x1 - 16, y + 26), clock, font=F["big"], fill=ACCENT if x.get("kind") != "break" else TEXT,
                   anchor="rm")
            frac = max(0.0, min(1.0, left / max(1, x["secs"])))
            d.rounded_rectangle((x0 + 16, y + 36, x0 + 16 + (x1 - x0 - 140) * frac, y + 40), radius=2, fill=ACCENT)
            y += 60
        rows = self.today_rows()
        n_open = len(A.open_tasks())
        d.text((x0 + 4, y + 12), "To do" + (f"  ·  {n_open}" if n_open else ""), font=F["small_b"], fill=MUTED,
               anchor="lm")
        y += 26
        room = max(2, int((bottom - y - 70) // 34))
        shown = min(TODAY_ROWS, room)
        sel = max(0, min(self.today_sel, len(rows) - 1)) if rows else 0
        first = max(0, min(sel - shown + 1, len(rows) - shown)) if len(rows) > shown else 0
        if not rows:
            d.text((x0 + 4, y + 16), "Nothing yet. Say \"add milk to my list\", or press A", font=F["small"],
                   fill=MUTED, anchor="lm")
            y += 34
        for k, it in enumerate(rows[first:first + shown]):
            i = first + k
            picked = i == sel and self.friend_more is None
            if picked:
                d.rounded_rectangle((x0, y, x1, y + 32), radius=10, fill=ROW)
            done = bool(it.get("done"))
            cx, cy = x0 + 18, y + 16
            if done:
                d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=ACCENT)
                d.line((cx - 4, cy, cx - 1, cy + 3, cx + 4, cy - 3), fill=BG, width=2)
            else:
                d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), outline=MUTED if not picked else TEXT, width=2)
            label = self.fit(d, it["text"], F["row"], x1 - x0 - 50)
            d.text((x0 + 36, cy), label, font=F["row"], fill=MUTED if done else TEXT if picked else BODY,
                   anchor="lm")
            if done:
                lw = d.textlength(label, font=F["row"])
                d.line((x0 + 36, cy + 1, x0 + 36 + lw, cy + 1), fill=MUTED, width=1)
            y += 34
        if A.reminders and y < bottom - 40:            # reminders, then notes, as room allows
            d.text((x0 + 4, y + 14), "Reminders", font=F["small_b"], fill=MUTED, anchor="lm")
            y += 30
            for r in A.reminders[:3]:
                if y > bottom - 24:
                    break
                when = say_clock(r["at"], now, h24)
                d.text((x0 + 4, y + 10), when, font=F["small"], fill=ACCENT, anchor="lm")
                tw = d.textlength(when, font=F["small"]) + 12
                d.text((x0 + 4 + tw, y + 10), self.fit(d, r["text"], F["small"], x1 - x0 - tw - 8), font=F["small"],
                       fill=BODY, anchor="lm")
                y += 24
        if A.notes and y < bottom - 40:
            d.text((x0 + 4, y + 14), "Notes", font=F["small_b"], fill=MUTED, anchor="lm")
            y += 30
            for x in reversed(A.notes[-3:]):
                if y > bottom - 24:
                    break
                d.text((x0 + 4, y + 10), self.fit(d, x["text"], F["small"], x1 - x0 - 8), font=F["small"], fill=BODY,
                       anchor="lm")
                y += 24

