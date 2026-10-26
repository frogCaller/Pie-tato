"""Any game, played by a decision model that looks at its screen (pitato/gameai.py runs this for a game with no
player of its own, as Pokémon Emerald has). Each time, the model is shown the game's picture as it is now and picks
the next thing to press: a button, a direction for a moment or held a while, a direction with a button, or nothing
for a moment; and this presses it. The game runs on meanwhile, at its own speed: only the picking is slow, and
nothing's pressed while the model thinks. It's told the game's name and system, what it did last, and whether the
screen changed after each, so it doesn't keep doing what does nothing. A model that can't look at pictures is told
it can't see the screen, and plays on from the rest."""
import collections

from .games import plain_title, system as system_info

STEP, HELD, TOGETHER, WAIT = 0.2, 1.0, 0.6, 1.0   # seconds: a direction for a moment, held, with a button; nothing
MISSED_WAIT = 2.0            # seconds before it asks again when the model didn't pick (it isn't answering)
RECENT = 8                   # moves it's told about, the last ones
SAME_UNDER = 1.5             # a screen this little different (of 255, on average) looks the same as before
SAME_NOTE = 3                # ...after this many such moves in a row, it's told so
PUSH = 127                   # a stick pushed all the way (an N64 game's directions)

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
STICK_SYSTEMS = ("n64",)     # its games move with the stick, not the d-pad
DIRECTIONS = (("up", "Up", ("ly", -PUSH)), ("down", "Down", ("ly", PUSH)), ("left", "Left", ("lx", -PUSH)),
              ("right", "Right", ("lx", PUSH)))
SAYS = ("You are playing {game} on the {system}, looking at its screen. Pick the next thing to press to make "
        "progress in the game: from its title screen, start the game; get through menus and text; then play it "
        "the way a good player would. Something that didn't change the screen probably did nothing, so try "
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


class AnyGame:
    """Plays the game through io (pitato/gameai.py's GameIO: its screen, its buttons, the model)."""

    def __init__(self, game, io):
        self.io = io
        self.system = game.get("system") or ""
        try:
            self.system_name = system_info(self.system)[2]
        except StopIteration:
            self.system_name = self.system or "a games console"
        self.title = plain_title(game.get("title") or "") or "this game"
        self.moves = moves_for(self.system)
        self.choices = {k: words for k, (words, _) in self.moves.items()}
        self.says = SAYS.format(game=self.title, system=self.system_name)
        self.recent = collections.deque(maxlen=RECENT)   # [{"move": what it did, "changed": the screen did}]
        self.before = None                               # the screen just before the last move

    def play(self):
        self.io.status(f"Looking at {self.title}")
        while True:
            look = self.io.look()
            if self.recent and self.recent[-1]["changed"] is None and look is not None and self.before is not None:
                self.recent[-1]["changed"] = look.differs(self.before) >= SAME_UNDER
            key = self.io.decide("move", self.says, self.state(look), self.choices, "wait", picture=look or False)
            words, how = self.moves[key]
            if self.io.last_by != "model":
                self.io.status("Waiting for your bot's computer to answer")
                self.io.wait(MISSED_WAIT)
                continue
            self.io.status(words.split(" (")[0])
            self.before = self.io.look() if how[0] != "wait" else look   # (just before it: what changes is its doing)
            self.recent.append({"move": words.split(" (")[0], "changed": None})
            self.do(how)

    def state(self, look):
        """What the model's told, besides the screen (gameai.py says it's attached)."""
        state = {"game": self.title, "system": self.system_name}
        if self.io.blind:
            state["screen"] = "You can't see the screen (you can't look at pictures): go by the game and what you did."
        elif look is None:
            state["screen"] = "The game's screen couldn't be seen this time."
        done = [f"{m['move']}: " + ("the screen changed" if m["changed"] else "nothing changed"
                                    if m["changed"] is False else "not known") for m in self.recent]
        if done:
            state["you did last, oldest first"] = done
        same = 0
        for m in reversed(self.recent):
            if m["changed"] is not False:
                break
            same += 1
        if same >= SAME_NOTE:
            state["note"] = f"Your last {same} moves changed nothing on the screen: do something different."
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
