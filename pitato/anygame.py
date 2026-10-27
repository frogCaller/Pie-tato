"""Any game, played by a decision model that looks at its screen (pitato/gameai.py runs this for a game with no
player of its own, as Pokémon Emerald has), coached by your Bot's model if there is one (pitato/coach.py): now and
then that looks at the screen too and works out what to aim for and how, and the decision model follows it. Each
time, the decision model is shown the game's picture as it is now and picks the next thing to press: a button, a
direction for a moment or held a while, a direction with a button, or nothing for a moment; and this presses it. The
game runs on meanwhile, at its own speed: only the picking is slow, and nothing's pressed while the model thinks.
It's told the game's name and system, the coach's goal and plan (and your tips), and what it did last and what came
of each: something new on the screen, nothing new (it changed, but only to how it's looked before, as with a jump on
the spot), or nothing at all. When its moves have brought nothing new for a while, it's stuck: it's told so, and
which buttons it hasn't tried there; what it's mostly been doing comes off its list for a few picks (or till
something new comes of another move); and the coach looks again. A model that can't look at pictures is told it
can't see the screen, and plays on from the rest."""
import collections

import numpy as np

from .games import plain_title, system as system_info

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

    def play(self):
        self.io.status(f"Looking at {self.title}")
        if self.coach is not None:
            self.coach.start(self.title, self.system_name, self.controls())
        while True:
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
                continue
            if self.off_left > 0:
                self.off_left -= 1
            self.io.status(self.doing(words))
            self.before = self.io.look() if how[0] != "wait" else look   # (just before it: what changes is its doing)
            self.recent.append({"move": words.split(" (")[0], "key": key, "came": None})
            self.do(how)

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
        mostly, what's off its list, and the buttons it hasn't tried there."""
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
