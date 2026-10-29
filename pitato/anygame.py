"""Any game, played by a decision model that looks at its screen (pitato/gameai.py runs this for a game with no
player of its own, as Pokémon Emerald has), coached by your Bot's model if there is one (pitato/coach.py): that knows
a lot of games, says what kind of game this is, what its buttons do and how it's played well, and now and then looks
at the screen and works out what to aim for and how; the decision model follows it. Until it's said, the kind of game
is guessed from its name (pitato/instincts.py).

An action game (racing, a platformer, fighting, a shooter) is played by instinct (pitato/instincts.py): many times a
second it looks at the screen and holds what a player would (the gas, steering to keep on the road; running and
jumping; attacks and blocks; firing and weaving), and the decision model's asked on a thread of its own, as often as
it answers, whether that's what to do now (a race on, a level going) and which way, or which button gets past a title
screen, a menu or some text. The game never waits for the model. If the model's not answering, it plays by instinct
while the screen's moving, and presses A or Start when it's been still a while (a menu, most likely).

Any other game is played a move at a time: the decision model's shown the game's picture as it is now and picks the
next thing to press (a button, a direction for a moment or held a while, a direction with a button, or nothing for a
moment) and this presses it; the game runs on meanwhile, at its own speed, and nothing's pressed while the model
thinks. It's told the game's name and system, what's known of the game, the coach's goal and plan (and your tips),
and what it did last and what came of each: something new on the screen, nothing new (it changed, but only to how it's
looked before, as with a jump on the spot), or nothing at all. When its moves have brought nothing new for a while,
it's stuck: it's told so, and which buttons it hasn't tried there; what it's mostly been doing comes off its list for a
few picks (or till something new comes of another move); and the coach looks again. A model that can't look at
pictures is told it can't see the screen, and plays on from the rest."""
import collections
import threading
import time

import numpy as np

from .games import plain_title, system as system_info
from .instincts import INSTINCTS, KINDS, LIVE, guess_kind, roles_for

STEP, HELD, TOGETHER, WAIT = 0.2, 1.0, 0.6, 1.0   # seconds: a direction for a moment, held, with a button; nothing
MISSED_WAIT = 2.0            # seconds before it asks again when the model didn't pick (it isn't answering)
RECENT = 8                   # moves it's told about, the last ones
SEEN_MOST = 300              # looks kept, to tell what's new: several minutes of them
CELL_DIFF = 16               # a look's cell (pitato/gameai.py's Look.cells: 64 x 48 of them) this much lighter or
                             # darker than another look's (of 255) is different there
NEW_SHARE = 0.02             # a look's new when this share of its cells is different from each look kept: a step or
                             # two, a new page of words or a new menu are more; a jump on the spot, an enemy going
                             # by, words blinking or a cursor moving, less
SAME_SHARE = 0.003           # less than this share of them different from just before the move: nothing changed
SAME_NOTE = 3                # ...after this many such moves in a row, it's told so
STUCK_AFTER = 8              # moves in a row that brought nothing new: it's stuck (and again after as many more)
OFF_FOR = 8                  # picks that what it was mostly doing then is off its list for (till something new)...
MOSTLY = 0.5                 # ...when that was at least this share of those moves
LEFT_ON = 4                  # (moves left on its list, at least)
TIPS_FOR_PICKS = 500         # characters of your tips the decision model's told (the coach reads them all)
PUSH = 127                   # a stick pushed all the way (an N64 game's directions)
CAME = {"new": "something new", "same": "nothing new", "nothing": "nothing changed", None: "not known"}

# each system's buttons: what the model's told each is, and the button as the emulator takes it (libretro's names:
# a PlayStation's go by where they are, so Cross is libretro's B; an N64's A and B are libretro's B and Y, Z its L2;
# a Genesis's A B C are libretro's Y B A, and a Master System's 1 and 2 its B and A). The first two go with a
# direction too (a jump or an attack on the move).
NINTENDO = (("A", "a"), ("B", "b"), ("Start", "start"), ("Select", "select"))
BUTTONS = {
    "gb": NINTENDO, "gbc": NINTENDO, "nes": NINTENDO,
    "gba": (("A", "a"), ("B", "b"), ("L", "l"), ("R", "r"), ("Start", "start"), ("Select", "select")),
    "snes": (("A", "a"), ("B", "b"), ("X", "x"), ("Y", "y"), ("L", "l"), ("R", "r"), ("Start", "start"),
             ("Select", "select")),
    "nds": (("A", "a"), ("B", "b"), ("X", "x"), ("Y", "y"), ("L", "l"), ("R", "r"), ("Start", "start"),
            ("Select", "select")),
    "genesis": (("B", "b"), ("C", "a"), ("A", "y"), ("Start", "start")),
    "sms": (("1", "b"), ("2", "a"), ("Pause", "start")),
    "gg": (("1", "b"), ("2", "a"), ("Start", "start")),
    "n64": (("A", "b"), ("B", "y"), ("Z", "l2"), ("L", "l"), ("R", "r"), ("Start", "start")),
    "ps1": (("Cross", "b"), ("Square", "y"), ("Circle", "a"), ("Triangle", "x"), ("L1", "l"), ("R1", "r"),
            ("L2", "l2"), ("R2", "r2"), ("Start", "start"), ("Select", "select")),
    "psp": (("Cross", "b"), ("Square", "y"), ("Circle", "a"), ("Triangle", "x"), ("L", "l"), ("R", "r"),
            ("Start", "start"), ("Select", "select")),
}
PAUSES = ("Start", "Pause")  # (the button that pauses: not one to suggest trying, as a person would)
STICK_SYSTEMS = ("n64",)     # its games move with the stick, not the d-pad
DIRECTIONS = (("up", "Up", ("ly", -PUSH)), ("down", "Down", ("ly", PUSH)), ("left", "Left", ("lx", -PUSH)),
              ("right", "Right", ("lx", PUSH)))
SAYS = ("You are playing {game} on the {system}, looking at its screen. Pick the next thing to press to make "
        "progress in the game: from its title screen, start the game; get through menus and text; then play it "
        "the way a good player would. When you're given a goal and a plan, follow them, a move at a time. What "
        "came of your last moves says whether they got you anywhere: when they keep bringing nothing new, do "
        "something else.")
LIVE_SAYS = ("You are playing {game}, {a_kind} game, on the {system}, looking at its screen. While the game's being "
             "played ({playing}), pick {play}: it then plays by itself, many times a second, till you pick something "
             "else. On title screens, menus, maps and text, pick the button that gets the game going (Start or A, "
             "usually) or moves a menu's cursor. When you're given a goal and a plan, follow them.")
# each kind of action game: what playing by instinct is called (its choices: the way it's going), what's on then, and
# which choice to pick then
PLAYS = {
    "racing": ({"drive": "Drive: race on (the gas held, steering to keep on the road, by itself)"}, "a race on",
               "Drive"),
    "platformer": ({"go_right": "Play: run right through the level, jumping gaps, enemies and what's in the way (by "
                                "itself)",
                    "go_left": "Play: run left through the level, jumping gaps, enemies and what's in the way (by "
                               "itself)"}, "a level going", "the Play that goes the way the level goes"),
    "fighting": ({"fight_right": "Fight: the other fighter's on your right (moving in, attacking, blocking and "
                                 "jumping by itself)",
                  "fight_left": "Fight: the other fighter's on your left (moving in, attacking, blocking and jumping "
                                "by itself)"}, "a fight on", "the Fight for the side the other fighter's on"),
    "shooter": ({"shoot": "Shoot: keep firing and dodging (by itself)"}, "a stage going", "Shoot"),
}
PLAY_WAY = {"go_right": "right", "go_left": "left", "fight_right": "right", "fight_left": "left"}
TICK = 0.1                   # seconds between the instincts' looks, at least
ASK_GAP = 1.0                # seconds between the decision model's picks, at least, while it plays by instinct
CHECK_EVERY = 1.0            # seconds between looks at what's come of it (new, or not), for the coach and when stuck
LIVE_STUCK = 10              # of those in a row with nothing new: it's stuck (and again after as many more)
STILL_POKE = 3               # ...and of those with the screen still, when the model's not answering: A or Start
STILL_SHARE = 0.02           # (still: less than this share of it changed since the last check, as a title screen
                             # with PRESS START blinking)
A_KIND = {"racing": "a racing", "platformer": "a platform", "fighting": "a fighting", "shooter": "a shooting",
          "sports": "a sports", "puzzle": "a puzzle", "rpg": "an RPG", "adventure": "an adventure", "other": "a"}


def button_key(label):
    return "button_" + label if label.isdigit() else label.lower()


def moves_for(system):
    """{key: (what the model's told, how it's done)}: how is ("tap", button), ("hold", buttons, sticks, seconds) or
    ("wait", seconds)."""
    buttons = BUTTONS.get(system, NINTENDO)
    stick = system in STICK_SYSTEMS
    moves = {}
    for key, word, push in DIRECTIONS:
        how = ((), (push,)) if stick else ((key,), ())
        what = f"{word} on the stick" if stick else word
        moves[key] = (f"{what} for a moment (one step, or the cursor one place {key})", ("hold", *how, STEP))
        moves[key + "_held"] = (f"{what}, held a second (walk or run {key})", ("hold", *how, HELD))
    for label, b in buttons:
        moves[button_key(label)] = (f"Press {label}", ("tap", b))
    for label, b in buttons[:2]:
        for key, word, push in DIRECTIONS[2:]:
            how = ((b,), (push,)) if stick else ((key, b), ())
            moves[f"{key}_{button_key(label)}"] = (f"{word} and {label} together (on the move: a jump, an attack)",
                                                  ("hold", *how, TOGETHER))
    moves["wait"] = ("Nothing for a moment (let something finish, or wait for something to happen)", ("wait", WAIT))
    return moves


def kinds_for(system):
    """{move's key: what kind of move it is}: its button's key (on its own or on the move: a jump is a jump), its
    direction's (for a moment or held), or "wait"."""
    buttons = BUTTONS.get(system, NINTENDO)
    kinds = {"wait": "wait"}
    for key, _, _ in DIRECTIONS:
        kinds[key] = kinds[key + "_held"] = key
    for label, _ in buttons:
        kinds[button_key(label)] = button_key(label)
    for label, _ in buttons[:2]:
        for key, _, _ in DIRECTIONS[2:]:
            kinds[f"{key}_{button_key(label)}"] = button_key(label)
    return kinds


def changed(look, other):
    """The share of a look's cells different from another look's, 0 to 1."""
    return float((np.abs(look.cells.astype(np.int16) - other.cells.astype(np.int16)) > CELL_DIFF).mean())


class Seen:
    """What the screen's looked like lately: each look's cells, kept (the oldest go), to tell something new from what's
    been seen already."""

    def __init__(self, most=SEEN_MOST):
        self.most, self.rows, self.n, self.at = most, None, 0, 0

    def new(self, look):
        """How much of a look is unlike every look kept: the share of its cells different from the one it's most
        like, 0 to 1 (1 with none kept)."""
        cells = look.cells
        if not self.n or self.rows.shape[1] != cells.size:
            return 1.0
        kept = self.rows[:self.n].astype(np.int16)
        return float((np.abs(kept - cells.astype(np.int16)) > CELL_DIFF).mean(axis=1).min())

    def add(self, look):
        cells = look.cells
        if self.rows is None or self.rows.shape[1] != cells.size:
            self.rows, self.n, self.at = np.zeros((self.most, cells.size), np.uint8), 0, 0
        self.rows[self.at] = cells
        self.at = (self.at + 1) % self.most
        self.n = min(self.n + 1, self.most)


class Decider:
    """The decision model, asked on a thread of its own while the game's played by instinct (the game never waits
    for it): ask() a question (with the latest look), and take() its pick once it's come: (the pick, "model" or
    "own" (the model didn't say)). Only the main loop touches the game; this only asks."""

    def __init__(self, io):
        self.io = io
        self.job = self.got = None
        self.asked = self.forgotten = 0            # questions asked; and the last whose answer isn't wanted
        self.cv = threading.Condition()
        self.thread = threading.Thread(target=self.main, daemon=True, name="game-ai-decide")
        self.thread.start()

    def idle(self):
        with self.cv:
            return self.job is None

    def ask(self, says, state, choices, fallback, picture):
        with self.cv:
            self.asked += 1
            self.job = (self.asked, says, state, choices, fallback, picture)
            self.cv.notify()

    def take(self):
        with self.cv:
            got, self.got = self.got, None
            return got

    def forget(self):
        """Its pick, when it comes, isn't wanted (a new kind of game: its choices were another's)."""
        with self.cv:
            self.got = None
            self.forgotten = self.asked

    def main(self):
        stopping = self.io.ai.stopping
        while not stopping.is_set():
            with self.cv:
                while self.job is None and not stopping.is_set():
                    self.cv.wait(0.25)
                job = self.job
            if job is None:
                return
            n, says, state, choices, fallback, picture = job
            try:
                pick = self.io.decide("live", says, state, choices, fallback, picture=picture, quiet=True)
                by = self.io.last_by
            except Exception as ex:                # (it says why; the game goes on)
                self.io.log(event="The decision model's pick went wrong", error=repr(ex)[:300])
                pick, by = fallback, "own"
            with self.cv:
                self.got = (pick, by) if n > self.forgotten else None
                self.job = None


class AnyGame:
    """Plays the game through io (pitato/gameai.py's GameIO: its screen, its buttons, the model), coached by coach
    (pitato/coach.py's Coach) or not (None)."""

    def __init__(self, game, io, coach=None):
        self.io, self.coach = io, coach
        self.system = game.get("system") or ""
        try:
            self.system_name = system_info(self.system)[2]
        except StopIteration:
            self.system_name = self.system or "a games console"
        self.title = plain_title(game.get("title") or "") or "this game"
        self.moves = moves_for(self.system)
        self.kinds = kinds_for(self.system)
        self.choices = {k: words for k, (words, _) in self.moves.items()}
        self.buttons = {button_key(label): label for label, _ in BUTTONS.get(self.system, NINTENDO)}
        self.says = SAYS.format(game=self.title, system=self.system_name)
        self.recent = collections.deque(maxlen=RECENT)   # [{"move": what it did, "key": which, "came": what of it}]
        self.before = None                               # the screen just before the last move
        self.seen = Seen()
        self.stale = []                                  # the moves since the screen last showed something new
        self.off, self.off_left = (), 0                  # moves off its list for now, and for how many more picks
        # what's known of the game: its kind (from its name, till the coach or your notes say), what its buttons do
        self.labels = [label for label, _ in BUTTONS.get(self.system, NINTENDO)]
        self.card = {"kind": guess_kind(self.title), "buttons": "", "how": ""}
        self.kind = self.card["kind"]
        self.instinct = None                             # (an action game's: pitato/instincts.py)
        self.decider = None                              # (the model asked on a thread of its own, meanwhile)
        self.mode = "menu"                               # play (by instinct), menu (a move picked: then nothing), auto
        self.way = "right"                               # (which way it's going, by instinct)
        self.ask_at = self.check_at = 0.0
        self.stale_checks = self.still_checks = 0        # checks in a row with nothing new, and with the screen still
        self.last_check = None
        self.poke = 0

    def play(self):
        self.io.status(f"Looking at {self.title}")
        if self.coach is not None:
            self.coach.start(self.title, self.system_name, self.controls())
        self.io.log(event=(f"It's {A_KIND[self.kind]} game, by its name: " + ("played by instinct" if self.kind in LIVE
                                                                              else "played a move at a time"))
                    if self.kind != "other" else "What kind of game it is isn't known yet: played a move at a time")
        while True:
            self.know()
            if self.kind in LIVE:
                self.live()
            else:
                self.turn()

    def know(self):
        """What's known of the game now: the coach's word on it (or your notes'), over the guess from its name. A
        new kind of game: played its way from now on."""
        said = self.coach.card() if self.coach is not None and hasattr(self.coach, "card") else None
        card = dict(self.card)
        for k, v in (said or {}).items():
            if v:
                card[k] = v
        if card == self.card:
            return
        was, self.card = self.kind, card
        self.kind = card["kind"] if card["kind"] in KINDS else self.kind
        if self.kind != was:
            self.io.log(event=f"It's {A_KIND[self.kind]} game ({self.kind}): "
                              + ("played by instinct" if self.kind in LIVE else "played a move at a time"))
            self.io.let_go()
            self.mode = "menu"
            if self.decider is not None:
                self.decider.forget()
        self.instinct = None                             # (made again: what its buttons do may be known now)

    def turn(self):
        """One move, picked by the model from the screen as it is now; then it's done. (Not while the model's still
        answering a question from playing by instinct: one at a time.)"""
        while self.decider is not None and not self.decider.idle():
            self.io.wait(0.1)
        look = self.io.look()
        self.came(look)
        if self.coach is not None:
            self.coach.see(look, self.story())
        choices = self.choices
        if self.off_left > 0:
            choices = {k: w for k, w in self.choices.items() if k not in self.off}
        key = self.io.decide("move", self.says, self.state(look), choices, "wait", picture=look or False)
        words, how = self.moves[key]
        if self.io.last_by != "model":
            self.io.status("Waiting for your bot's computer to answer")
            self.io.wait(MISSED_WAIT)
            return
        if self.off_left > 0:
            self.off_left -= 1
        self.io.status(self.doing(words))
        self.before = self.io.look() if how[0] != "wait" else look   # (just before it: what changes is its doing)
        self.recent.append({"move": words.split(" (")[0], "key": key, "came": None})
        self.do(how)

    # -- an action game: by instinct ------------------------------------------------------------------------------
    def plays(self):
        return PLAYS[self.kind][0]

    def make_instinct(self):
        roles = roles_for(self.system, self.labels, self.card.get("buttons", ""))
        lib = dict(BUTTONS.get(self.system, NINTENDO))
        self.instinct = INSTINCTS[self.kind](self.system, lib, roles, stick=self.system in STICK_SYSTEMS)
        self.instinct.way = self.way
        self.io.log(event="Its buttons, as it plays: " + ", ".join(f"{r} {v}" for r, v in roles.items()
                                                                  if v and r != "told"))

    def live(self):
        """A moment of an action game: a look; the model's pick, if one's come (play by instinct, or a move: a
        button for a menu); the model asked again (with this look) if it's free; what's come of it, once a second;
        then the instinct's next moment, or nothing (after a move, till the model says to play)."""
        if self.instinct is None:
            self.make_instinct()
        if self.decider is None:
            self.decider = Decider(self.io)
        t0 = time.monotonic()
        look = self.io.look()
        now = time.monotonic()
        got = self.decider.take()
        if got is not None and self.follow(got, look):
            return                                   # (a move made: what came of it's seen next time)
        if look is not None and now >= self.check_at:
            self.check(look, now)
        if now >= self.ask_at and self.decider.idle():
            plays = self.plays()
            fallback = next((k for k in plays if PLAY_WAY.get(k, self.instinct.way) == self.instinct.way), "wait") \
                if self.mode == "play" else "wait"
            self.decider.ask(self.live_says(), self.state(look) | {"now": self.now_words()}, dict(plays, **self.choices),
                             fallback, look or False)
            self.ask_at = now + ASK_GAP
        if look is None:                                 # (it can't see the game this moment: nothing held)
            steps = [(set(), {}, TICK)]
        elif self.mode == "play" or (self.mode == "auto" and self.still_checks < STILL_POKE):
            steps = self.instinct.tick(look, now)
            self.io.status(self.doing(self.instinct.said or "Playing"))
        elif self.mode == "auto":
            self.poke += 1
            steps = [({self.button("start" if self.poke % 2 else "a")}, {}, 0.08), (set(), {}, 1.0)]
            self.still_checks = STILL_POKE - 2              # (and again in a couple of seconds, if it's still still)
            self.io.status("Pressing on (the model's not answering)")
        else:
            steps = [(set(), {}, TICK)]
        for buttons, sticks, secs in steps:
            self.io.hold_only(buttons, sticks if sticks is not None else dict(self.io.sticks))
            self.io.wait(secs)
        took = time.monotonic() - t0 - sum(st[2] for st in steps)
        if took > TICK / 3:                              # (a slow Pi: it looks less often, so the game keeps up)
            self.io.wait(min(0.5, took * 2))

    def button(self, name):
        """A button by the emulator's name, if this console has it (else its first)."""
        lib = [b for _, b in BUTTONS.get(self.system, NINTENDO)]
        return name if name in lib else lib[0]

    def follow(self, got, look):
        """The model's pick, as it comes: play by instinct (which way), or a move (done now; then nothing's held till
        it picks again): True if it made a move. Not picked by the model (it's not answering): it plays on as best it
        can."""
        key, by = got
        plays = self.plays()
        if by != "model":
            if self.mode != "auto":
                self.io.log(event="The decision model isn't answering: it plays by instinct while the screen's "
                                  "moving, and presses on when it's still")
            self.mode = "auto"
            return False
        if key not in plays and key not in self.moves:  # (a pick from another kind of game's choices)
            return False
        words = plays.get(key) or self.moves[key][0]
        if not self.recent or self.recent[-1]["key"] != key:
            self.recent.append({"move": words.split(" (")[0].split(":")[0], "key": key, "came": None})
        if key in plays:
            self.mode = "play"
            self.way = self.instinct.way = PLAY_WAY.get(key, self.instinct.way)
            return False
        self.mode = "menu"
        self.io.hold_only(set(), {})
        self.io.status(self.doing(words))
        self.do(self.moves[key][1])
        self.ask_at = time.monotonic() + 0.3         # (asked again once it's seen what came of that, not before)
        return True

    def check(self, look, now):
        """Once a second: whether something new's on the screen (and what came of the last pick), whether the
        screen's still; stuck after LIVE_STUCK checks with nothing new (the instinct tries something else, the
        coach looks again). The coach is shown the screen."""
        self.check_at = now + CHECK_EVERY
        share = self.seen.new(look)
        self.seen.add(look)
        new = share >= NEW_SHARE
        still = self.last_check is not None and changed(look, self.last_check) < STILL_SHARE
        self.last_check = look
        self.still_checks = self.still_checks + 1 if still else 0
        last = self.recent[-1] if self.recent else None
        if last is not None and last["came"] is None:
            last["came"] = "new" if new else "nothing" if still else "same"
        self.stale_checks = 0 if new else self.stale_checks + 1
        if self.stale_checks and self.stale_checks % LIVE_STUCK == 0:
            self.io.log(event=f"Stuck: {self.stale_checks} seconds with nothing new")
            if self.mode in ("play", "auto"):
                self.instinct.stuck(now)
            if self.coach is not None:
                self.coach.nudge()
        if self.coach is not None:
            self.coach.see(look, self.story())

    def live_says(self):
        _, playing, play = PLAYS[self.kind]
        return LIVE_SAYS.format(game=self.title, system=self.system_name, a_kind=A_KIND[self.kind],
                                playing=playing, play=play)

    def now_words(self):
        """What it's doing now, for the model."""
        if self.mode == "play":
            return f"playing by itself: {self.instinct.said or 'playing'}, going {self.instinct.way}"
        if self.mode == "auto":
            return "playing as best it can (you weren't answering)"
        return "waiting for your pick"

    def came(self, look):
        """What came of the last move, now the screen's been looked at again: something new on it, nothing new (it
        changed, but only to how it's looked before), or nothing at all; the look's kept, and it's stuck when its
        moves keep bringing nothing new."""
        if look is None:
            return
        share = self.seen.new(look)
        self.seen.add(look)
        last = self.recent[-1] if self.recent else None
        if last is None or last["came"] is not None:
            return
        if self.before is not None and changed(look, self.before) < SAME_SHARE:
            last["came"] = "nothing"
        else:
            last["came"] = "new" if share >= NEW_SHARE else "same"
        if last["came"] == "new":                       # (it's got somewhere: all its moves are back on its list)
            self.stale, self.off, self.off_left = [], (), 0
            return
        self.stale.append(last["key"])
        if len(self.stale) % STUCK_AFTER == 0:
            self.stuck()

    def mostly(self):
        """What kind of move most of its last stuck ones were, if one kind was at least MOSTLY of them; else None."""
        last = self.stale[-STUCK_AFTER:]
        if not last:
            return None
        kind, n = collections.Counter(self.kinds.get(k, k) for k in last).most_common(1)[0]
        return kind if n >= MOSTLY * len(last) else None

    def stuck(self):
        """Its last STUCK_AFTER moves brought nothing new: what it's mostly been doing comes off its list for OFF_FOR
        picks (if it's mostly done one thing), and the coach looks again."""
        kind = self.mostly()
        off = tuple(k for k in self.moves if self.kinds.get(k) == kind) if kind else ()
        if off and self.off_left <= 0 and len(self.moves) - len(off) >= LEFT_ON:
            self.off, self.off_left = off, OFF_FOR
            self.io.log(event=f"Stuck: {len(self.stale)} moves with nothing new, mostly {self.kind_words(kind)}: "
                              f"that's off its list for {OFF_FOR} picks")
        else:
            self.io.log(event=f"Stuck: {len(self.stale)} moves with nothing new")
        if self.coach is not None:
            self.coach.nudge()

    def kind_words(self, kind):
        if kind == "wait":
            return "waiting"
        if kind in self.buttons:
            return f"{self.buttons[kind]} (on its own and on the move)"
        return next((word for key, word, _ in DIRECTIONS if key == kind), kind)

    def untried(self):
        """The buttons (but the one that pauses) not pressed since the screen last showed something new."""
        used = {self.kinds.get(k) for k in self.stale}
        return [label for key, label in self.buttons.items() if key not in used and label not in PAUSES]

    def off_words(self):
        return [self.moves[k][0].split(" (")[0] for k in self.off] if self.off_left > 0 else []

    def controls(self):
        """Its buttons, in words: for the coach."""
        pad = "the stick" if self.system in STICK_SYSTEMS else "the d-pad (Up, Down, Left, Right)"
        return ", ".join(label for label, _ in BUTTONS.get(self.system, NINTENDO)) + " and " + pad

    def story(self):
        """How it's going, for the coach: the last moves and what came of each; and whether it's stuck, doing what
        mostly, what's off its list, and the buttons it hasn't tried there (an action game: for how long, doing
        what)."""
        if self.kind in LIVE:
            stuck = self.stale_checks >= LIVE_STUCK
            return {"moves": [f"{m['move']}: {CAME[m['came']]}" for m in self.recent], "stale": self.stale_checks,
                    "stuck": stuck, "mostly": "", "off": [], "untried": [],
                    "stuck_words": f"It's stuck: {self.stale_checks} seconds with nothing new on the screen, "
                                   f"{self.now_words()}." if stuck else ""}
        kind = self.mostly() if len(self.stale) >= STUCK_AFTER else None
        return {"moves": [f"{m['move']}: {CAME[m['came']]}" for m in self.recent], "stale": len(self.stale),
                "stuck": len(self.stale) >= STUCK_AFTER, "mostly": self.kind_words(kind) if kind else "",
                "off": self.off_words(), "untried": self.untried()}

    def doing(self, words):
        """What it's doing, for the game's menu: the coach's goal, or the move."""
        advice = self.coach.advice if self.coach is not None else None
        return f"Goal: {advice['goal']}" if advice and advice.get("goal") else words.split(" (")[0]

    def state(self, look):
        """What the model's told, besides the screen (gameai.py says it's attached)."""
        state = {"game": self.title, "system": self.system_name}
        if self.card["kind"] != "other":
            state["kind of game"] = self.card["kind"]
        if self.card.get("buttons"):
            state["its buttons"] = self.card["buttons"]
        if self.card.get("how"):
            state["how it's played well"] = self.card["how"]
        if self.io.blind:
            state["screen"] = "You can't see the screen (you can't look at pictures): go by the game and what you did."
        elif look is None:
            state["screen"] = "The game's screen couldn't be seen this time."
        advice = self.coach.advice if self.coach is not None else None
        for key in ("goal", "plan"):
            if advice and advice.get(key):
                state[key] = advice[key]
        controls = self.coach.controls() if self.coach is not None else ""
        if controls:
            state["controls"] = controls
        tips = self.coach.tips if self.coach is not None else ""
        if tips:
            state["tips"] = tips[:TIPS_FOR_PICKS]
        done = [f"{m['move']}: {CAME[m['came']]}" for m in self.recent]
        if done:
            state["you did last, oldest first"] = done
        notes, nothing = [], 0
        for m in reversed(self.recent):
            if m["came"] != "nothing":
                break
            nothing += 1
        if nothing >= SAME_NOTE:
            notes.append(f"Your last {nothing} moves changed nothing on the screen: do something different.")
        elif len(self.stale) >= STUCK_AFTER:
            notes.append(f"Your last {len(self.stale)} moves got you nowhere (nothing new on the screen): do "
                         "something different.")
        if self.kind in LIVE and self.stale_checks >= LIVE_STUCK:
            notes.append(f"Nothing new on the screen for {self.stale_checks} seconds: try something else (the other "
                         "way, or a button).")
        if self.off_left > 0:
            notes.append("Off your list for now, as they got you nowhere: " + ", ".join(self.off_words()) + ".")
        untried = self.untried()
        if len(self.stale) >= STUCK_AFTER and untried:
            notes.append("Buttons you haven't tried here: " + ", ".join(untried) + ".")
        if notes:
            state["note"] = " ".join(notes)
        return state

    def do(self, how):
        """A move, carried out: it lets go of everything after (even if it's stopped meanwhile)."""
        if how[0] == "tap":
            self.io.tap(how[1])
        elif how[0] == "hold":
            _, buttons, sticks, secs = how
            try:
                for b in buttons:
                    self.io.hold(b)
                for axis, value in sticks:
                    self.io.stick(axis, value)
                self.io.wait(secs)
            finally:
                self.io.let_go()
        else:
            self.io.wait(how[1])
