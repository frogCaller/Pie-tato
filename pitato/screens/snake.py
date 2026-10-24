"""Snake's buttons, and its AI: asking the decision model on your bot's computer, and
using its answers."""
import math
import time

from ..snake import (
    Snake, SNAKE_AI_AHEAD, SNAKE_AI_BEHIND, SNAKE_AI_FRESH, SNAKE_AI_GUESS, SNAKE_AI_SPARE, SNAKE_AI_TRIES,
    SNAKE_AI_WAIT, SNAKE_AI_WAKE, SNAKE_DIRS, SNAKE_OPTIONS, SNAKE_SPEEDS)


class SnakeScreen:
    """Snake's buttons, and its AI: asking the decision model on your bot's computer, and
    using its answers."""

    def press_snake(self, s, name):
        """Snake: the d-pad steers, A starts, pauses or plays again, Y starts a new game, START has its
        options (and the game waits meanwhile)."""
        full = self.sim_full()
        if name in SNAKE_DIRS:
            if s.ai:
                self.toast("The AI's playing. X to take over", 2)
            s.steer(name)
        elif name == "x":
            self.snake_ai_toggle(s)
        elif name == "a":
            s.press_a()
            if full and s.paused:
                self.toast("Paused", 2)
        elif name == "y":
            self.snake_keep(s)
            s.restart()
        else:
            if s.phase == "on":
                s.paused = True
            self.sim_opts = 0

    def snake_keep(self, s):
        """Your best (and the AI's), kept for next time."""
        if s.best > self.snake_best():
            self.set_setting("snake_best", s.best)
        if s.ai_best > self.snake_best("snake_ai_best"):
            self.set_setting("snake_ai_best", s.ai_best)

    def snake_best(self, key="snake_best"):
        v = self.setting(key)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0

    # Snake's AI: a decision model on your bot's computer plays (X)
    def snake_server(self):
        self.friend.load(self.friend_files())
        return self.friend.server

    def snake_models(self, force=False):
        """Ask for the decision models on your bot's computer, unless the list is fresh."""
        server = self.snake_server()
        b = self.brain
        if server and (force or b.models_for != server or time.monotonic() - b.models_at > SNAKE_AI_FRESH):
            if b.ask(("models", server)):
                self.brain_looking = True

    def snake_ai_model(self):
        """The decision model chosen in START's card (or the first one found)."""
        return self.sim_value(Snake, "ai") if len(Snake.options) > len(SNAKE_OPTIONS) else ""

    def snake_found(self, models):
        """The decision models found: a row on START's card to pick one."""
        Snake.options = SNAKE_OPTIONS + ((("ai", "AI", tuple(models), models[0]),) if models else ())

    def snake_ai_toggle(self, s):
        """X: the AI takes over (once it's found a decision model on your bot's computer), or you do."""
        if s.ai:
            s.ai, s.ai_waking, s.plan = False, False, {}
            if s.phase == "on":
                s.paused = True                        # (yours now: A, or the d-pad, and on it goes)
            self.toast("Your turn. A or the d-pad to carry on" if s.phase == "on" else "Your turn", 3)
            return
        server = self.snake_server()
        if not server:
            self.toast("The AI plays on your bot's computer. Set up the Bot first", 4)
            return
        models = self.brain.models if self.brain.models_for == server else []
        if not models:
            self.snake_models(force=True)
            s.ai_want = True                           # (it takes over once they're found)
            self.toast("Looking for decision models on your bot's computer…", 3)
            return
        self.snake_ai_start(s)

    def snake_ai_start(self, s):
        s.ai_want = False
        self.brain_server = self.snake_server()
        s.ai, s.ai_model, s.ai_ms = True, self.snake_ai_model(), None
        s.ai_used = True
        if s.phase == "over":
            s.restart()
        self.snake_ai_wake(s)

    def snake_ai_wake(self, s):
        """The game waits for the AI's first move (its model wakes up on the other computer), and it
        decides from where the snake is: any turns still to come are dropped."""
        s.ai_waking, s.ai_ms, s.turns, s.plan = True, None, [], {}
        if s.phase == "on":
            s.paused = True
        self.brain_round += 1
        self.brain_asked = None

    def snake_ai_take(self, s):
        """Each frame, before the game moves on: what came back from the AI, put to use."""
        for kind, tag, answer, ms, error in self.brain.take():
            if kind == "models":
                self.brain_looking = False
                if not error:
                    self.snake_found(answer)
                if s.ai_want:
                    s.ai_want = False
                    if error:
                        self.toast(error, 5)
                    elif not answer:
                        self.toast("No decision models on your bot's computer. Try: ollama pull nimble", 5)
                    else:
                        self.snake_ai_start(s)
                continue
            if not s.ai or tag is None or tag[0] != s.games or tag[2] != self.brain_round:
                continue                               # (for a game that's over, from before it woke, or it's off)
            if error:
                s.ai_lost += 1
                if s.ai_waking or s.ai_lost >= SNAKE_AI_TRIES:
                    s.ai, s.ai_waking, s.ai_lost, s.plan = False, False, 0, {}
                    if s.phase == "on":
                        s.paused = True
                    self.toast(f"The AI stopped: {error}", 5)
                elif self.brain_asked == tag:          # (that move's asked for again, while there's time)
                    self.brain_asked = (tag[0], tag[1] - 1, tag[2])
                continue
            s.ai_lost = 0
            if not s.ai_waking:                        # (how long it takes, awake)
                s.ai_ms = ms if s.ai_ms is None else s.ai_ms * 0.8 + ms * 0.2
            if s.ai_waking:                            # awake: off it goes
                s.ai_waking = False
                s.paused = False
                if s.phase == "ready":
                    s.phase = "on"
                    s.ai_used = True
            if tag[1] >= s.steps:
                s.plan[tag[1]] = answer                # (made when the snake gets there)
            # (else it came too late for where it was asked about: the snake went straight on)

    def snake_ai_ask(self, s):
        """...and after: its next question, as soon as it's free. It's asked about where the snake will
        be by the time its answer comes (how long its moves take is timed), so its move is made right
        there, and the game never waits for it. One that comes later than that isn't used: the snake
        goes straight on (that's the model's own fault). When it's quick, it's a move ahead at most."""
        if s.ai_want and not self.brain_looking and not self.brain.busy():
            self.snake_models(force=True)              # (X, while it was still busy with the last move)
        if not s.ai or self.brain.busy() or s.phase != "on" and not s.ai_waking:
            return
        model = self.snake_ai_model()
        if model and model != s.ai_model:              # (another one picked: it wakes up first)
            s.ai_model = model
            self.snake_ai_wake(s)
        if not s.ai_model or s.paused and not s.ai_waking:
            return
        if s.ai_waking:
            lead, gap = 0, 1                           # (the game waits for this one)
        else:
            per = 1.0 / s.rate()                       # (seconds a move)
            ms = SNAKE_AI_GUESS if s.ai_ms is None else s.ai_ms / 1000
            took = ms * SNAKE_AI_SPARE + self.brain_frame
            lead = min(SNAKE_AI_AHEAD, int((took + s.acc) / per))   # (moves made before its answer's here)
            gap = max(1, math.ceil((ms + self.brain_frame / 2) / per))   # (moves made for each it decides)
            self.snake_keeping_up(s)
        last = self.brain_asked
        mine = last is not None and last[0] == s.games and last[2] == self.brain_round
        if mine and last[1] >= s.steps + max(lead, 1):
            return                                     # (it's far enough ahead)
        first = max(s.steps + lead, last[1] + 1) if mine else s.steps + lead
        c, got = s.later(first - s.steps)
        at = s.steps + got
        if mine and at <= last[1]:
            return                                     # (it runs into something before then, as decided)
        state, choices = c.situation(gap)
        tag = (s.games, at, self.brain_round)
        if self.brain.ask(("move", self.brain_server, s.ai_model, state, choices, tag,
                           SNAKE_AI_WAKE if s.ai_waking else SNAKE_AI_WAIT)):
            self.brain_asked = tag

    def snake_keeping_up(self, s):
        """It can't keep up with the game (after a while): said once, for each model."""
        share = s.keeps_up()
        if share is None or share >= SNAKE_AI_BEHIND or s.ai_model in self.brain_warned:
            return
        self.brain_warned.add(s.ai_model)
        name = s.ai_model[:-7] if s.ai_model.endswith(":latest") else s.ai_model
        took = f" ({s.ai_ms:,.0f} ms a move)" if s.ai_ms else ""
        if s.values["speed"] == SNAKE_SPEEDS[0][0]:
            self.toast(f"{name} can't keep up{took}", 5)
        else:
            self.toast(f"{name} can't keep up at this speed{took}. Try {SNAKE_SPEEDS[0][0]} in START", 5)

    def snake_over(self, s):
        """The end of a game: your best kept; full screen, a word about it (the card's not shown there)."""
        self.snake_keep(s)
        if self.sim_full():
            title, words = s.note()
            self.toast(f"{title} {words}" if title.endswith("!") else f"{title}: {words}", 4)
