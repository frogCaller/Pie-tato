"""Attract mode (Settings > Attract mode): when Pietato's left idle, plugged in (the battery saver off), the Bot gets
bored and finds something to do, something else every minute or so: it plays one of your games (as an arcade
cabinet's does), looks through your camera and says what it sees (turning it to look around, when it's one that turns:
an OBSBOT on a Pi), puts up the weather, your stocks and coins, one of Apps' (the Game of Life, Forest Fire, the
Mandelbrot set, Rock Paper Scissors, a new fortune from the Fortune Cookie), a slideshow of your photos, or how the Pi's
doing. Each time, it says something about it: its model's words when it has one (Settings > Bot), else a line of its
own; on the screen, and out loud in the day (with a voice, and Talks out loud on). Games only: just games, as it was.

A game: the AI player plays it (the decision model you last picked for it, on your bot's computer), from where you were
in it; or, without one, the game's own demo plays, from its start. Its saves are kept apart (your own never change), its
sound's off, the Bot's face watches from a corner, and what it says goes over the top of the game.

START or A: what it's showing is yours (that game, from your own save; the app, as it is); any other button: back where
you were."""
import os
import random
import re
import shutil
import time

from ..bot import friend_face, FRIEND_TIMEOUT
from ..config import CACHE_DIR
from ..games import FAST_PI_ONLY, find_core, find_games, GameRun, games_dir, plain_title, save_name, SAVES_FOLDER
from ..gameai import GameAI
from ..library import LIBRARY, SLIDESHOW_SECS
from ..net import cam_key
from ..screen import aplay_device, screen_turn, sound_place
from ..stocks import money
from ..system import cpu_temp
from ..theme import ACCENT, BG, LINE, MUTED, TEXT

ATTRACT_AFTER = 300.0         # seconds with nothing happening before the Bot gets bored
ATTRACT_GAME = 180.0          # seconds each game plays, then something else
ATTRACT_START = 20.0          # seconds a game has to start (one that doesn't: another, and not that one again)
ATTRACT_FACE = 1.5            # seconds between the Bot's face's looks (it blinks, it glances about)
ATTRACT_AGAIN = 600.0         # seconds before it looks again for something to do, when there was nothing
ATTRACT_RECENT = 3            # the games played last aren't played again straight away
BADGE = (128, 112)            # the badge in the corner: the Bot's face, and what START does
SAVE_EXTS = (".srm", ".rtc", ".state.auto", ".disc")   # (yours, copied: where the AI player carries on from)
BORED_FOR = {"camera": 80.0, "weather": 40.0, "finance": 40.0, "app": 75.0, "photos": 60.0, "system": 30.0}
BORED_STILL = 45.0            # ...a camera that doesn't turn: this long (it looks once)
BORED_APPS = ("Game of Life", "Forest Fire", "Mandelbrot Set", "Rock Paper Scissors",   # Apps' it watches
              "Fortune Cookie")                                                     # (...or opens)
BORED_TALK = (8, 22)          # hours it says things out loud between (the rest of the time: just on the screen, so
                              # nobody's woken)
BORED_SAY = (8.0, 30.0)       # seconds what it said stays up: at least, at most (longer while it's still saying it)
BORED_NOTICE = 80             # characters of it that go over a game, at most
BORED_LOOK = ((4.0, "look"), (24.0, "left"), (29.0, "look"), (48.0, "right"), (55.0, "look"), (72.0, "home"))
STEER_FOR = 1.2               # seconds it turns the camera to look around (back the other way: twice as long)
BORED_PICTURE = 15.0          # seconds it waits for the camera's first picture before it says what it sees

# what it says as it starts something, without a model: a line (and what's what, where it knows)
BORED_LINES = {
    "game": ("I'm bored. Time for some {title}!", "My turn on {title}.", "Let's see how far I get in {title}."),
    "camera": ("Let me have a look around.", "I wonder what's going on.", "Just keeping an eye on things."),
    "weather": ("Let's see what the weather's doing.", "Weather check!", "What's it like out there?"),
    "finance": ("Let's see how your stocks and coins are doing.", "Checking on the markets.", "Number time!"),
    "photos": ("Let's look at some of your photos.", "I love looking through your pictures.", "Photo time!"),
    "system": ("Let me check how I'm doing.", "Time for a quick check-up.", "How am I doing? Let's see."),
}
BORED_APP_LINES = {"Game of Life": "I could watch the Game of Life all day.",
                   "Forest Fire": "Forest fires, from a safe distance.",
                   "Mandelbrot Set": "Let's take a dive into the Mandelbrot set.",
                   "Rock Paper Scissors": "Rock, paper or scissors? Let's find out."}
# ...and what its model's asked to say
BORED_ASKS = {
    "game": "You're bored, so you just started playing {title}, one of their games, on the screen. Say something about "
            "it, in a sentence.",
    "camera": "You're bored, so you're looking through their camera ({cam}). The attached picture is what it sees right "
              "now. Say what you see, in a sentence or two, the way you'd say it out loud. No lists.",
    "turned": "You just turned the camera to the {way} to look around. The attached picture is what it sees now. Say "
              "what you see there, in a sentence, the way you'd say it out loud.",
    "weather": "You're bored, so you just put the weather on the screen. Say something about it, in a sentence or two.",
    "finance": "You're bored, so you just put their stocks and coins on the screen. Say something about how they're "
               "doing, in a sentence or two.",
    "app": "You're bored, so you just put {name} on the screen to watch ({about}). Say something about it, in a "
           "sentence.",
    "fortune": "You're bored, so you just cracked open a fortune cookie on the screen. Its fortune says: {text} Say "
               "something about it, in a sentence.",
    "photos": "You're bored, so you're looking through their photos. The attached picture is one of them{when}. Say "
              "something about it, in a sentence or two.",
    "system": "You're bored, so you just put your own numbers on the screen (you live on this Raspberry Pi): {facts}. "
              "Say something about how you're doing, in a sentence.",
}


class AttractScreen:
    """Attract mode: the Bot, bored, finding something to do while Pietato's left idle."""

    def attract_on(self):
        return getattr(self, "attract", None) is not None

    def attract_ai(self):
        """The AI player to play with: (your bot's computer, the decision model last picked for games), or None."""
        server, model = self.snake_server(), self.setting("game_ai_model")
        return (server, model) if server and model and model != "Off" else None

    def attract_ready(self, now):
        """Time for the Bot to get bored: Settings > Attract mode on; media mode up and left idle long enough, on the
        home screen or a list, with nothing playing, and running on mains power (the battery saver off)."""
        return (self.setting("attract") != "Off" and self.active and self.fb is not None and not self.resting
                and self.view in ("home", "list") and self.proc is None and self.game is None and self.prog is None
                and not self.chromium_up() and not self.learn and now - self.stirred >= ATTRACT_AFTER
                and now >= getattr(self, "attract_wait", 0.0) and not self.worth_watching(now)
                and not self.saver_on())

    def attract_games(self, bad=()):
        """The games it can play by itself here: your own, drawn in 2D (a 3D one's too much for a game nobody's
        playing), with their emulator here."""
        return [g for g in find_games() if g["system"] not in FAST_PI_ONLY and g["path"] not in bad
                and find_core(g["system"]) and not self.game_cant(g)]

    # -- what there is to do --------------------------------------------------------------------------------------
    def bored_choices(self):
        """What it can do here, now: your games, your camera, the weather (once it knows where you are), your stocks and
        coins, Apps', your photos and the Pi's own numbers. Games only: just games."""
        a = self.attract
        games = bool(self.attract_games(a["bad"]))
        if self.setting("attract") == "Games only":
            return ["game"] if games else []
        out = ["game"] if games else []
        if self.friend_camera():
            out.append("camera")
        if self.setting("location"):
            out.append("weather")
        if self.stocks.symbols() or self.crypto.coins:
            out.append("finance")
        if self.bored_apps():
            out.append("app")
        if self.bored_photo_list():
            out.append("photos")
        if self.tab_index("system") is not None:
            out.append("system")
        return out

    def bored_apps(self):
        """Apps' it watches: those here (the Mandelbrot set only while it tours: exploring, it'd stand still)."""
        names = {t["name"] for t in LIBRARY}
        return [n for n in BORED_APPS if n in names
                and not (n == "Mandelbrot Set" and self.setting("sim_mandel_mode") == "Explore")]

    def bored_photo_list(self):
        """Your photos (Photos' pictures), looked for once while it's bored."""
        a = self.attract
        if a.get("photos") is None:
            pi = self.tab_index("photos")
            paths = []
            if pi is not None:
                try:
                    self.load_tab(pi)
                    paths = [it["src"] for it in self.tab_items(pi) if it.get("kind") == "image"]
                except Exception as ex:                # (no photos to look at, then)
                    print(f"attract: your photos: {ex!r}", flush=True)
            a["photos"] = paths
        return a["photos"]

    # -- starting, and going on to the next thing ---------------------------------------------------------------------
    def attract_start(self, now):
        """Bored: where you were noted (to go back to), and the first thing to do."""
        self.attract = {"kind": None, "since": now, "stirs": self.stirs, "view": self.view, "tab": self.tab,
                        "sel": self.sels.get(self.tab), "home_sel": getattr(self, "home_sel", 0), "bad": set(),
                        "recent": [], "done": [], "gen": 0, "say": None, "moved": False, "spoke": False}
        if not self.bored_next(now):
            self.attract = None
            self.attract_wait = now + ATTRACT_AGAIN

    def bored_next(self, now):
        """The next thing to do (not what it did last, nor the one before, when there's something else), started, with
        a word about it. False: there's nothing it can do."""
        a = self.attract
        self.bored_end_one()
        tried = set()
        while True:
            kinds = [k for k in self.bored_choices() if k not in tried]
            if not kinds:
                return False
            fresh = [k for k in kinds if k not in a["done"][-2:]] or kinds
            kind = self.bored_pick(fresh)
            a.update(kind=kind, since=now, say=None, gen=a["gen"] + 1)
            if self.bored_begin(kind, now):
                a["done"] = (a["done"] + [kind])[-4:]
                self.dirty = True
                print(f"attract: {kind}", flush=True)
                return True
            tried.add(kind)

    @staticmethod
    def bored_pick(kinds):
        """One of them, at random."""
        return kinds[random.randrange(len(kinds))]

    def attract_next(self, now):
        """Something else (what it's doing ends first). Nothing else: back where you were."""
        if self.attract is not None and not self.bored_next(now):
            self.attract_stop()

    def bored_begin(self, kind, now):
        """One thing to do, put on the screen: True when it's on."""
        a = self.attract
        if kind == "game":
            return self.bored_game(now)
        a["moved"] = True                              # (the screen's its: put back as it was, after)
        if kind == "camera":
            addr = self.friend_camera()
            if not addr:
                return False
            self.web_tab("Camera")
            self.camera_open(addr)
            a.update(cam=addr, plan=list(BORED_LOOK), turned=False, turned_last=False, homed=False, looks=0, way="")
            a["shown"] = self.tab
            return True
        if kind == "photos":
            paths = list(self.bored_photo_list())
            if not paths:
                return False
            paths.sort(key=lambda _: random.random())  # (some of them, in no order)
            self.web_tab("Photos")
            self.open_photo(paths, 0)
            self.v["slideshow"], self.v["next_t"] = True, now + SLIDESHOW_SECS
            first = paths[0]
            try:
                when = time.strftime(", from %B %Y", time.localtime(os.path.getmtime(first)))
            except OSError:
                when = ""
            self.bored_remark(self.bored_line("photos"), BORED_ASKS["photos"].format(when=when),
                              look=lambda: (first, os.path.basename(first)))
            return True
        if kind == "app":
            names = self.bored_apps()
            if not names:
                return False
            fresh = [n for n in names if n != a.get("app")] or names
            name = fresh[random.randrange(len(fresh))]
            if self.web_tab(name) is None:
                return False
            a["app"], a["shown"] = name, self.tab
            if name == "Fortune Cookie":               # (a new fortune, and what it says read out)
                cookie = self.sim_game()
                cookie.new()
                self.sim_next = 0.0
                self.bored_remark(f"Fortune cookie time! It says: {cookie.text}",
                                  BORED_ASKS["fortune"].format(text=cookie.text))
                return True
            about = next((t.get("about", "") for t in LIBRARY if t["name"] == name), "")
            self.bored_remark(BORED_APP_LINES.get(name) or f"Here's {name}.",
                              BORED_ASKS["app"].format(name=name, about=about[:1].lower() + about[1:] or name))
            return True
        name = {"weather": "Weather", "finance": "Finance", "system": "System"}[kind]
        if kind == "weather" and not self.setting("location"):
            return False
        if self.web_tab(name) is None:
            return False
        a["shown"] = self.tab
        if kind == "system":
            n = getattr(self, "sys_now", None) or {}
            facts = self.bored_system(n)
            self.bored_remark(self.bored_line("system") + (" " + facts[0] if facts[0] else ""),
                              BORED_ASKS["system"].format(facts=facts[1] or "the numbers aren't in yet"))
        else:
            extra = self.bored_weather() if kind == "weather" else self.bored_finance()
            self.bored_remark(self.bored_line(kind) + (" " + extra if extra else ""), BORED_ASKS[kind])
        return True

    def bored_game(self, now):
        """One of your games, playing by itself. False: none would start."""
        a = self.attract
        games = self.attract_games(a["bad"])
        if not games:
            return False
        fresh = [g for g in games if g["path"] not in a["recent"]] or games
        g = random.choice(fresh)
        folder = os.path.join(CACHE_DIR, "attract")
        saves = os.path.join(folder, SAVES_FOLDER)
        shutil.rmtree(saves, ignore_errors=True)
        os.makedirs(saves, exist_ok=True)
        ai = self.attract_ai()
        name = save_name(g["path"])
        mine = os.path.join(games_dir(), SAVES_FOLDER, name)
        resume = bool(ai) and os.path.isfile(mine + ".state.auto")   # (the AI carries on from where you were;
        if resume:                                                     #  the game's own demo plays from its start)
            for ext in SAVE_EXTS:
                if os.path.isfile(mine + ext):
                    shutil.copy2(mine + ext, os.path.join(saves, name + ext))
        run = GameRun(g, on_change=self.game_changed)
        run.attract = True
        place = sound_place(self.setting("sound"))
        try:
            turn = screen_turn()
            run.start(find_core(g["system"]), sound=aplay_device(None, place[0]), volume=0,
                      picture=self.game_picture(g["system"]), resume=resume, cheevos=False, saves=saves,
                      **({"turn": turn} if turn else {}))
        except OSError as ex:
            print(f"attract: couldn't start {g['path']}: {ex}", flush=True)
            a["bad"].add(g["path"])
            return False
        a["recent"] = (a["recent"] + [g["path"]])[-ATTRACT_RECENT:]
        a.update(run=run, game=g, face_at=now + 2.0, badge=os.path.join(folder, "badge.png"))
        self.game, self.game_menu, self.game_sound = run, None, place
        self.game_since = now
        self.game_players = {}
        self.view = "game"
        if ai:
            self.game_ai = GameAI(run, ai[0], ai[1], os.path.join(saves, name + ".ai.log"),
                                  on_change=self.game_ai_changed, coach=self.friend.model,
                                  notes_path=mine + ".ai-notes.txt")   # (what it learns: kept, for next time)
            self.game_ai.start()
        print(f"attract: {g['title']}" + (f", the AI playing ({ai[1]})" if ai else ", its own demo"), flush=True)
        title = plain_title(g["title"]) or g["title"]
        self.bored_remark(self.bored_line("game").format(title=title), BORED_ASKS["game"].format(title=title))
        return True

    # -- each tick ------------------------------------------------------------------------------------------------
    def attract_tick(self, now):
        a = getattr(self, "attract", None)
        if a is None:
            if self.attract_ready(now):
                self.attract_start(now)
            return
        kind = a["kind"]
        gone = (self.game is not a.get("run")) if kind == "game" else not self.bored_shown()
        if gone:                                       # (something else took the screen, a song from the web page,
            self.attract = None                        #  say: it's left as it is)
            return
        if self.stirs != a["stirs"] or self.setting("attract") == "Off" or not self.active or self.saver_on():
            self.attract_stop()                        # (someone's here, or it's to stop)
            return
        if kind == "game":
            run = a["run"]
            if run.ended or (run.state == "starting" and now - a["since"] > ATTRACT_START):
                a["bad"].add(a["game"]["path"])        # (one that won't play: not again)
                self.attract_next(now)
                return
            if now - a["since"] >= ATTRACT_GAME:
                self.attract_next(now)
                return
            if run.state == "on" and now >= a["face_at"]:
                a["face_at"] = now + ATTRACT_FACE
                self.attract_badge(run)
            return
        say = a.get("say")
        if say and now >= say["until"] and not (a["spoke"] and self.voice.speaking):
            a["say"] = None                            # (what it said has had its turn)
            self.dirty = True
        if kind == "camera":
            self.bored_camera_tick(now)
            done = now - a["since"] >= (BORED_FOR["camera"] if a["turned"] else BORED_STILL)
        else:
            done = now - a["since"] >= BORED_FOR[kind]
        if done and not (a["spoke"] and self.voice.speaking):   # (it finishes what it's saying first)
            self.attract_next(now)

    def bored_shown(self):
        """What it put on the screen is still on it."""
        a = self.attract
        if a["kind"] == "camera":
            return self.on_camera_page() and cam_key(self.camera.addr or "") == cam_key(a.get("cam") or "")
        if a["kind"] == "photos":
            return self.view == "photo"
        return self.view == "list" and self.tab == a.get("shown")

    def bored_camera_tick(self, now):
        """Looking through the camera: it says what it sees, and (one that turns) turns to the left and looks, then to
        the right and looks, then back to where it was."""
        a, cam = self.attract, self.camera
        plan = a["plan"]
        while plan and now - a["since"] >= plan[0][0]:
            step = plan[0][1]
            if step == "look" and a["looks"] == 0 and cam.frame is None and now - a["since"] < BORED_PICTURE:
                break                                  # (its first picture first: a camera can take a while)
            plan.pop(0)
            if step == "look":
                if a["looks"] == 0 or a["turned_last"]:
                    self.bored_look()
            elif step in ("left", "right"):
                a["turned_last"] = False
                if cam.steers and not cam.following and not cam.held:   # (following you: that's left as it is)
                    secs = STEER_FOR * (2 if a["turned"] else 1)
                    cam.press(step)
                    a.update(turned=True, turned_last=True, way=step)
                    self.later(secs, lambda w=step: self.bored_unsteer(w))
                    self.dirty = True
            elif step == "home" and a["turned"]:
                cam.go_home()
                a["homed"] = True

    def bored_unsteer(self, way):
        self.camera.release(way)
        self.dirty = True

    def bored_look(self):
        """It says what the camera sees: its model looks (it says it's looking meanwhile); without one that sees, the
        first time, a line of its own."""
        a, fr = self.attract, self.friend
        addr, first = a["cam"], a["looks"] == 0
        a["looks"] += 1
        if fr.ready() and fr.sees():
            ask = (BORED_ASKS["camera"].format(cam=self.cam_called(addr)) if first
                   else BORED_ASKS["turned"].format(way=a["way"] or "side"))
            a["gen"] += 1
            gen = a["gen"]
            self.cam_bot = {"addr": addr, "busy": True, "text": "", "note": "", "error": False, "spoken": False,
                            "until": 0.0, "token": object()}
            if self.bored_ask(ask, lambda: self.camera_look(addr), self.bored_done("camera", gen)):
                self.dirty = True
                return
            self.cam_bot = None
        if first:
            self.bored_show(self.bored_line("camera"), talk=True)

    # -- what it says -----------------------------------------------------------------------------------------------
    @staticmethod
    def bored_line(kind):
        lines = BORED_LINES[kind]
        return lines[random.randrange(len(lines))]

    def bored_weather(self):
        """The weather in a few words, when it's in."""
        w = self.weather.data
        return self.weather_words() if w and w.get("temp") is not None else ""

    def bored_finance(self):
        """How the first of your coins (or stocks) is doing, in a few words, when it's in."""
        for c in self.crypto.coins[:1]:
            q = (self.crypto.quotes.get(c["id"]) or {}).get("d") or {}
            if q.get("price") is not None:
                ch = q.get("change_24h")
                name = c.get("name") or q.get("symbol") or c.get("symbol") or "It"
                return f"{name}'s at ${q['price']:,.2f}" + (f", {'up' if ch >= 0 else 'down'} {abs(ch):.1f}% today."
                                                            if ch is not None else ".")
        for sym in self.stocks.symbols()[:1]:
            q = (self.stocks.quotes.get(sym) or {}).get("d") or {}
            if q.get("price") is not None:
                ch = q.get("change_1d")
                price = money(q["price"], q.get("currency") or "USD", q.get("kind") or "")
                return f"{q.get('name') or sym}'s at {price}" + (f", {'up' if ch >= 0 else 'down'} {abs(ch):.1f}% "
                                                                 "today." if ch is not None else ".")
        return ""

    @staticmethod
    def bored_system(n):
        """(a few words of how the Pi's doing, the numbers for its model)."""
        t = n.get("temp")
        if t is None:
            t = cpu_temp()
        mem, disk, busy = n.get("mem"), n.get("disk"), n.get("busy")
        facts = []
        if t is not None:
            facts.append(f"{t:.0f}°C")
        if busy is not None:
            facts.append(f"the CPU {busy:.0f}% busy")
        if mem:
            facts.append(f"{100 * mem[0] / mem[1]:.0f}% of its memory in use")
        if disk:
            facts.append(f"its storage {100 * disk[0] / disk[2]:.0f}% full")
        said = f"I'm at {t:.0f}°C" + (f", with {100 * mem[0] / mem[1]:.0f}% of my memory in use." if mem else ".") \
            if t is not None else ""
        return said, ", ".join(facts)

    def bored_remark(self, line, ask, look=None):
        """What it says as it starts something: its line on the screen at once; then its model's words, when it has a
        model (said out loud), else the line (said out loud)."""
        a = self.attract
        a["gen"] += 1
        asked = self.bored_ask(ask, look, self.bored_done(a["kind"], a["gen"]))
        self.bored_show(line, talk=not asked)

    def bored_ask(self, ask, look, done):
        """Its model asked for a word of its own: False when it isn't set up, or the last one asked hasn't answered yet
        (its computer asleep, say: they aren't let pile up)."""
        if time.monotonic() < getattr(self, "bored_waiting", 0.0):
            return False
        if not self.friend.comment(ask, look=look, done=done):
            return False
        self.bored_waiting = time.monotonic() + FRIEND_TIMEOUT
        return True

    def bored_done(self, kind, gen):
        """What's called with its model's words (on its own thread): they're put up on media mode's."""
        def done(text):
            self.soon(lambda: self.bored_heard(kind, gen, text))
            self.wake()
        return done

    def bored_heard(self, kind, gen, text):
        """Its model's words, for what it's doing still (not something it's gone on from): up, and said."""
        self.bored_waiting = 0.0                       # (it answered: it can be asked again)
        a = self.attract
        if a is None or a["kind"] != kind or a["gen"] != gen:
            return
        if not text:
            if kind == "camera" and (self.cam_bot or {}).get("busy"):
                self.cam_bot = None                    # (it didn't say: nothing over the picture)
                self.dirty = True
            return
        self.bored_show(" ".join(text.split()), talk=True)

    def bored_show(self, text, talk=False):
        """What it says: over the game (a game's sound is its: just there), over the camera's picture, or along the
        foot of the page; and out loud too (talk), in the day."""
        a = self.attract
        now = time.monotonic()
        secs = max(BORED_SAY[0], min(BORED_SAY[1], 4 + len(text) / 12))
        if a["kind"] == "game":
            run = a.get("run")
            first = text if len(text) <= BORED_NOTICE else re.split(r"(?<=[.!?])\s+", text)[0]
            if len(first) > BORED_NOTICE:              # (as much of it as goes over a game)
                first = first[:BORED_NOTICE - 1].rsplit(" ", 1)[0] + "…"
            if run is not None:
                run.send("notice " + first)
            return
        spoke = self.bored_talk(text) if talk else False
        if a["kind"] == "camera":
            self.cam_bot = {"addr": a["cam"], "busy": False, "text": text, "note": "", "error": False,
                            "spoken": spoke, "until": now + secs, "token": object()}
        else:
            a["say"] = {"text": text, "until": now + secs}
        self.dirty = True

    def bored_talk(self, text):
        """Said out loud: with a voice and Talks out loud on, in the day (BORED_TALK). True when it's saying it."""
        hour = time.localtime().tm_hour
        if not (self.bot_voice() and self.bot_speaks() and BORED_TALK[0] <= hour < BORED_TALK[1]):
            return False
        ok, _ = self.say_aloud(text)
        if ok:
            self.attract["spoke"] = True
        return ok

    def bored_said(self):
        """What it said that's up along the foot of the page now ("" for nothing)."""
        a = getattr(self, "attract", None)
        say = a and a.get("say")
        return say["text"] if say and a["kind"] not in ("game", "camera") else ""

    def bored_bubble(self, d, low=False):
        """What it said, along the foot of the page with its face (over a notice's place: low, at the foot of the
        screen, when there are no buttons along it). True when it's drawn."""
        text = self.bored_said()
        if not text:
            return False
        F, W, H = self.fonts, self.fb.w, self.fb.h
        face = friend_face(text)[0]
        fw = d.textlength(face, font=F["small"])
        lines = self.wrap(d, text, F["small"], W - 24 - 28 - fw - 12, 4)
        y1 = H - 10 if low or self.full_app() else H - self.FOOTER - 10
        y0 = y1 - (20 + 21 * len(lines))
        d.rounded_rectangle((12, y0, W - 12, y1), radius=14, fill=BG, outline=LINE)
        d.text((26, y0 + 10), face, font=F["small"], fill=ACCENT, anchor="la")
        x, y = 26 + fw + 12, y0 + 10
        for line in lines:
            d.text((x, y), line, font=F["small"], fill=TEXT, anchor="la")
            y += 21
        return True

    # -- ending -----------------------------------------------------------------------------------------------------
    def bored_end_one(self):
        """What it's doing, over: the game ends (its saves were never yours: nothing's kept or told), the camera stops
        turning (back to where it was, if it turned), the slideshow closes."""
        a = self.attract
        kind = a["kind"] if a else None
        if kind == "game":
            run = a.get("run")
            a["run"] = None
            if run is not None and self.game is run:
                self.game_end()
        elif kind == "camera":
            cam = self.camera
            for way in list(cam.held):
                cam.release(way)
            if a.get("turned") and not a.get("homed"):
                cam.go_home()
            if (self.cam_bot or {}).get("addr") == a.get("cam"):
                self.cam_bot = None
        elif kind == "photos" and self.view == "photo":
            self.close_viewer()
        if a is not None:
            a["say"] = None

    def attract_end(self):
        """What it's doing ends, and with it the Bot's being bored (what's on the screen stays)."""
        if self.attract is not None:
            self.bored_end_one()
        self.attract = None

    def attract_stop(self):
        """Back where you were: what it's doing ends, and the wait for it to get bored again starts again."""
        a = self.attract
        if a is None:
            return
        self.attract_end()
        if a["spoke"] and self.voice.speaking:
            self.voice.stop()
        if a["moved"]:                                 # (it put up apps of its own: let go, and yours back)
            self.go_home()
            if a["view"] == "list" and a["tab"] is not None:
                self.tab, self.view = a["tab"], "list"
                self.load_tab(a["tab"])
                if a["sel"] is not None:
                    self.sels[a["tab"]] = a["sel"]
            else:
                if a["tab"] is not None:
                    self.tab = a["tab"]
                self.home_sel = a["home_sel"]
        else:
            self.view = a["view"] if a["view"] in ("home", "list") else "home"
        self.stirred = time.monotonic()
        if self.fb is not None and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()
        self.dirty = True

    def attract_press(self, name, repeat):
        """A button while it's bored: START or A, what it's showing is yours (a game, from your own save; an app, as it
        is); any other, back where you were."""
        a = self.attract
        if repeat or a is None:
            return None
        if name not in ("start", "a"):
            self.attract_stop()
            return None
        if a["kind"] == "game":
            g = a["game"]
            self.attract_stop()
            self.game_open({"src": g["path"], "title": g["title"], "system": g["system"]})
            return None
        self.attract = None                            # (as it is: the camera, the slideshow, the app...)
        cam = self.camera
        for way in list(cam.held):
            cam.release(way)
        self.stirred = time.monotonic()
        self.dirty = True
        return None

    def attract_badge(self, run):
        """The Bot's face in the corner, as it looks now (it blinks, it glances about), and what START does."""
        a = self.attract
        try:
            from PIL import Image, ImageDraw           # (a plain picture: the emulator sizes it for the screen)
            w, h = BADGE
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            own = tuple(self.bot_palette()[1])[:3]
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=own + (255,), outline=MUTED, width=2)
            self.draw_bot_face(d, (w // 2, 42, 52), look="idle", back=own)
            font = self.fonts["small"]
            for text, y, colour in (("Playing by itself", 74, TEXT), ("START to play", 92, MUTED)):
                tw = d.textlength(text, font=font)
                d.text(((w - tw) / 2, y), text, font=font, fill=colour)
            tmp = a["badge"] + ".tmp.png"
            img.save(tmp)
            os.replace(tmp, a["badge"])
        except Exception as ex:                        # (never the game's end: it plays on without it)
            print(f"attract: its badge: {ex!r}", flush=True)
            return
        run.send("badge " + a["badge"])
