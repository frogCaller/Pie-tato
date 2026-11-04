"""Attract mode (Settings > Attract mode): when Pietato's left idle, plugged in (the battery saver off), a game plays
by itself, as an arcade cabinet's does. The AI player plays it (the decision model you last picked for it, on your
bot's computer), from where you were in it; or, without one, the game's own demo plays, from its start. Its saves are
kept apart (your own never change), its sound's off, the Bot's face watches from a corner, and every few minutes it's
another game. START or A: that game, yours, from your own save; any other button: back where you were."""
import os
import random
import shutil
import time

from ..config import CACHE_DIR
from ..games import FAST_PI_ONLY, find_core, find_games, GameRun, games_dir, save_name, SAVES_FOLDER
from ..gameai import GameAI
from ..screen import aplay_device, screen_turn, sound_place
from ..theme import MUTED, TEXT

ATTRACT_AFTER = 300.0         # seconds with nothing happening before a game plays by itself
ATTRACT_GAME = 180.0          # seconds each game plays, then another
ATTRACT_START = 20.0          # seconds a game has to start (one that doesn't: another, and not that one again)
ATTRACT_FACE = 1.5            # seconds between the Bot's face's looks (it blinks, it glances about)
ATTRACT_AGAIN = 600.0         # seconds before it looks again for games to play, when there were none
ATTRACT_RECENT = 3            # the games played last aren't played again straight away
BADGE = (128, 112)            # the badge in the corner: the Bot's face, and what START does
SAVE_EXTS = (".srm", ".rtc", ".state.auto", ".disc")   # (yours, copied: where the AI player carries on from)


class AttractScreen:
    """Attract mode: a game playing by itself while Pietato's left idle."""

    def attract_on(self):
        return getattr(self, "attract", None) is not None

    def attract_ai(self):
        """The AI player to play with: (your bot's computer, the decision model last picked for games), or None."""
        server, model = self.snake_server(), self.setting("game_ai_model")
        return (server, model) if server and model and model != "Off" else None

    def attract_ready(self, now):
        """Time for a game to play by itself: Settings > Attract mode on; media mode up and left idle long enough, on
        the home screen or a list, with nothing playing, and running on mains power (the battery saver off)."""
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

    def attract_tick(self, now):
        a = getattr(self, "attract", None)
        if a is None:
            if self.attract_ready(now):
                self.attract_start(now)
            return
        run = a["run"]
        if self.game is not run:                       # (something else took the screen: a song from the web page)
            self.attract = None
            return
        if (self.stirs != a["stirs"] or self.setting("attract") == "Off" or not self.active or self.saver_on()):
            self.attract_stop()                        # (someone's here, or it's to stop)
            return
        if run.ended or (run.state == "starting" and now - a["since"] > ATTRACT_START):
            a["bad"].add(a["game"]["path"])            # (one that won't play: not again)
            self.attract_next(now)
            return
        if now - a["since"] >= ATTRACT_GAME:
            self.attract_next(now)
            return
        if run.state == "on" and now >= a["face_at"]:
            a["face_at"] = now + ATTRACT_FACE
            self.attract_badge(run)

    def attract_start(self, now, bad=None, recent=None, view=None):
        bad = set(bad or ())
        recent = list(recent or ())
        games = self.attract_games(bad)
        if not games:
            self.attract_wait = now + ATTRACT_AGAIN
            return
        fresh = [g for g in games if g["path"] not in recent] or games
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
            self.attract_wait = now + ATTRACT_AGAIN
            return
        recent = (recent + [g["path"]])[-ATTRACT_RECENT:]
        self.attract = {"run": run, "game": g, "since": now, "stirs": self.stirs, "view": view or self.view,
                        "face_at": now + 2.0, "bad": bad, "recent": recent, "badge": os.path.join(folder, "badge.png")}
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

    def attract_next(self, now):
        """Another game (the one playing ends first)."""
        a = self.attract
        self.attract_end()
        self.attract_start(now, a["bad"], a["recent"], a["view"])
        if self.attract is None:                        # (none to play: back where it was)
            self.view = a["view"]
            self.dirty = True

    def attract_end(self):
        """The game playing by itself ends (its saves were never yours: nothing's kept or told)."""
        a, self.attract = self.attract, None
        if a is None:
            return
        if self.game is a["run"]:
            self.game_end()

    def attract_stop(self):
        """Back where you were: the game playing by itself ends, and the wait for the next one starts again."""
        a = self.attract
        if a is None:
            return
        self.attract_end()
        self.view = a["view"] if a["view"] in ("home", "list") else "home"
        self.stirred = time.monotonic()
        if self.fb is not None and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()
        self.dirty = True

    def attract_press(self, name, repeat):
        """A button while a game plays by itself: START or A, that game's yours (from your own save); any other,
        back where you were."""
        a = self.attract
        if repeat or a is None:
            return None
        g = a["game"]
        self.attract_stop()
        if name in ("start", "a"):
            self.game_open({"src": g["path"], "title": g["title"], "system": g["system"]})
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
