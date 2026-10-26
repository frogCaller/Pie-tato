"""An AI player for the game that's playing: a decision model on your bot's computer (Ollama, as Snake's AI)
looks at the game's screen and picks what to do. Any game: the model picks the next button to press, from what it
sees (pitato/anygame.py). Pokémon Emerald has a player of its own (pitato/emerald.py): the model picks at each moment
that needs a decision, and it does the rest from the game's memory, a button at a time. The model is assumed to see
(the game's screen goes with each pick); one that turns out not to is asked without it from then on. It plays on a
thread of its own while the game runs (the game never waits for it: only the picking is slow), waits while the
game's menu is up, and stops when it's turned off there (pitato/screens/games.py) or the game ends. What it saw
and picked goes in a log beside the game's saves (Games/Saves/<game>.ai.log): send that when it gets stuck."""
import base64
import io as _io
import json
import os
import struct
import tempfile
import threading
import time
import traceback

from . import anygame, emerald
from .bot import CantSee, ollama_decide
from .emulator import game_data

FIRST_PICK = 120.0           # seconds the model's first pick may take (it wakes up on the other computer)
LOG_MOST = 1_000_000         # bytes of log kept (then it starts a new one, the old one as .1)
GIVE_UP_AFTER = 5            # picks the model missed in a row: then it plays on its own, asking it now and then
ASK_AGAIN_EVERY = 20         # ...every this many picks
TAP_DOWN, TAP_GAP = 0.05, 0.06   # seconds a tapped button's down, and before the next
SHOT_WAIT = 1.5              # seconds the game has to give its picture (it answers between frames, or paused)
SEE_SIZE = 512               # pixels across, at most, of the game's screen as the model's shown it
SAME_SIZE = (32, 24)         # ...and the small grey copy that tells whether the screen changed
SCREEN_SAYS = "The attached picture is the game's screen right now."


def cartridge(path, exts=(".gba",), head=None):
    """A game's bytes (out of its zip, if it's zipped), or None. head: only its first bytes (a file's)."""
    try:
        if head and not path.lower().endswith(".zip"):
            with open(path, "rb") as f:
                return f.read(head)
        buf, size, _ = game_data(path, list(exts))
        return bytes(buf[:size])
    except Exception:
        return None


def player_for(rom):
    """The module with a player of its own for this cartridge, or None: it's played from its screen
    (pitato/anygame.py)."""
    if rom and emerald.supported(rom):
        return emerald
    return None


_SUPPORTED = {}


def can_play(path):
    """True for a game with a player of its own (its cartridge looked at once, then remembered): Pokémon Emerald.
    (Any other game is played from its screen.)"""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return False
    if key not in _SUPPORTED:
        _SUPPORTED[key] = player_for(cartridge(path, head=0x200)) is not None
    return _SUPPORTED[key]


class Look:
    """The game's screen at one moment: its size, a small grey copy (to tell whether it changed), and data: the
    picture as the model's shown it (base64 PNG, or JPEG for a big one), made when it's wanted."""

    def __init__(self, im):
        from PIL import Image
        self.im = im.convert("RGB")
        self.size = self.im.size
        self.grey = self.im.convert("L").resize(SAME_SIZE, Image.BILINEAR).tobytes()
        self._data = None

    @property
    def data(self):
        if self._data is None:
            from PIL import Image
            im = self.im
            if im.width > SEE_SIZE:
                im = im.resize((SEE_SIZE, max(1, round(im.height * SEE_SIZE / im.width))), Image.BILINEAR)
            buf = _io.BytesIO()
            if im.width > 320:                     # (a 3D game's: a photo-like picture, smaller as a JPEG)
                im.save(buf, "JPEG", quality=85)
            else:                                  # (pixel art: crisp, and small, as a PNG)
                im.save(buf, "PNG")
            self._data = base64.b64encode(buf.getvalue()).decode()
        return self._data

    def differs(self, other):
        """How different another look is, 0 (the same) to 255."""
        if other is None or len(other.grey) != len(self.grey):
            return 255.0
        return sum(abs(a - b) for a, b in zip(self.grey, other.grey)) / len(self.grey)


class GameIO:
    """What a game's player does to the game, and asks the model."""

    def __init__(self, ai, rom):
        self.ai, self.rom = ai, rom
        self.run = ai.run
        base = "/dev/shm" if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK) else tempfile.gettempdir()
        self.mem_path = os.path.join(base, f"pitato-ai-{os.getpid()}-{id(self):x}.mem")
        self.shot_path = self.mem_path[:-4] + ".ppm"
        self.peeks = 0
        self.held, self.pushed = set(), set()
        self.misses, self.picks, self.asked_first = 0, 0, False
        self.blind = False                          # the model was shown the screen and can't look at pictures
        self.last_by = ""                           # who made the last pick: "model", or "own" (it couldn't say)
        self.shots_missed = 0                       # the game's picture asked for and not given, in a row
        self.logged_choices = None

    # -- the game -----------------------------------------------------------------------------------------
    def live(self):
        """Waits while the game's menu is up; Stop if the AI player's been turned off or the game's ended."""
        while True:
            if self.ai.stopping.is_set() or self.run.ended:
                raise emerald.Stop()
            if self.run.state != "paused":
                return
            self.ai.stopping.wait(0.2)

    def snapshot(self):
        """The game's memory now (its working RAM, and the cartridge)."""
        self.live()
        what, rest = self.run.ask("mem " + self.mem_path, ("mem",), 3.0)
        if what != "mem" or rest != "ok":
            self.live()
            raise emerald.Stop() if self.run.ended else RuntimeError("The game didn't let its memory be read")
        with open(self.mem_path, "rb") as f:
            data = f.read()
        return emerald.Mem(data[:emulator_iwram()], data[emulator_iwram():], self.rom)

    def peek(self, *ranges):
        """A quick look at a few places: [bytes, ...] (None for one it couldn't read), or None."""
        self.live()
        self.peeks += 1
        spec = " ".join(f"{a:x}:{n:x}" for a, n in ranges)
        what, rest = self.run.ask(f"peek {self.peeks} {spec}", ("peek",), 3.0)
        if what != "peek":
            return None
        words = rest.split()
        if not words or words[0] != str(self.peeks):
            return None
        out = []
        for w in words[1:]:
            try:
                out.append(None if w == "-" else bytes.fromhex(w))
            except ValueError:
                out.append(None)
        return out if len(out) == len(ranges) else None

    def look(self):
        """The game's screen now (a Look), or None: it didn't give its picture."""
        self.live()
        if self.shots_missed >= 3 and self.picks % 10:
            return None                             # (it hasn't been: asked again now and then)
        what, rest = self.run.ask("shot " + self.shot_path, ("shot",), SHOT_WAIT)
        if what != "shot" or rest != "ok":
            self.shots_missed += 1
            return None
        try:
            from PIL import Image
            with Image.open(self.shot_path) as im:
                got = Look(im)
        except (OSError, ValueError):
            self.shots_missed += 1
            return None
        self.shots_missed = 0
        return got

    def peek_u8(self, addr):
        got = self.peek((addr, 1))
        return got[0][0] if got and got[0] else None

    def peek_s8(self, addr):
        v = self.peek_u8(addr)
        return None if v is None else (v - 256 if v > 127 else v)

    def peek_u32(self, addr, code=False):
        got = self.peek((addr, 4))
        if not got or not got[0]:
            return None
        v = struct.unpack("<I", got[0])[0]
        return v & ~1 if code else v

    def tap(self, button):
        self.live()
        self.run.press(button)
        self.wait(TAP_DOWN)
        self.run.release(button)
        self.wait(TAP_GAP)

    def hold(self, button):
        self.live()
        self.held.add(button)
        self.run.press(button)

    def release(self, button):
        self.held.discard(button)
        self.run.release(button)

    def stick(self, axis, value):
        """A stick pushed (lx ly: the left one; -127 to 127, up and left minus), or let go (0)."""
        self.live()
        (self.pushed.add if value else self.pushed.discard)(axis)
        self.run.stick(axis, int(value))

    def let_go(self):
        for b in list(self.held):
            self.release(b)
        for axis in list(self.pushed):
            self.pushed.discard(axis)
            self.run.stick(axis, 0)

    def wait(self, secs):
        if self.ai.stopping.wait(secs) or self.run.ended:
            raise emerald.Stop()

    # -- the model ----------------------------------------------------------------------------------------
    def decide(self, kind, says, state, choices, fallback, picture=None):
        """The model's pick of choices ({key: words}), or fallback if it can't say (it's logged either way). The
        game's screen goes with it, as the model's assumed to see: picture, a Look taken already (False: none),
        or one taken now. A model that can't look at pictures is asked without, from then on."""
        if fallback not in choices:
            fallback = next(iter(choices))
        self.picks += 1
        pick, by, error, t0, seen = fallback, "own", "", time.monotonic(), None
        ask = len(choices) > 1 and self.ai.model and (self.misses < GIVE_UP_AFTER
                                                      or self.picks % ASK_AGAIN_EVERY == 0)
        if ask:
            if not self.blind:
                seen = (picture if picture is not None else self.look()) or None
            self.status("Thinking (the first time, it wakes up)…" if not self.asked_first else "Thinking…")
            try:
                got, seen = self.ask_model(says, state, choices, seen)
                self.asked_first = True
                if got in choices:
                    pick, by, self.misses = got, "model", 0
            except Exception as ex:                # (it says why; the game goes on)
                error = str(ex) or repr(ex)
                self.misses += 1
        self.ai.offline = self.misses >= GIVE_UP_AFTER
        self.last_by = by
        same = choices == self.logged_choices                # (the same as last time: not written out again)
        self.logged_choices = choices
        self.log(kind=kind, state=state, choices="as before" if same else choices, pick=pick, by=by,
                 saw="x".join(map(str, seen.size)) if seen is not None else None,
                 ms=round((time.monotonic() - t0) * 1000), error=error or None)
        return pick

    def ask_model(self, says, state, choices, seen):
        """(the model's pick, the Look it was shown or None): with the screen, or without it once the model
        turns out not to see (that pick's asked again, without)."""
        timeout = FIRST_PICK if not self.asked_first else emerald.PICK_TIMEOUT
        if seen is not None:
            shown = state
            if isinstance(state, dict) and "screen" not in state:
                shown = dict(state, screen=SCREEN_SAYS)
            elif isinstance(state, str):
                shown = state + "\n" + SCREEN_SAYS
            try:
                return ollama_decide(self.ai.server, self.ai.model, shown, says, choices, timeout, [seen.data])[0], seen
            except CantSee:
                self.blind = True
                self.log(event=f"{self.ai.model} can't look at pictures: it plays on without seeing the screen")
        return ollama_decide(self.ai.server, self.ai.model, state, says, choices, timeout)[0], None

    # -- what it's doing ------------------------------------------------------------------------------------
    def status(self, words):
        self.ai.set_status(words)

    def log(self, **entry):
        self.ai.log(entry)

    def close(self):
        try:
            self.let_go()
        except Exception:
            pass
        for p in (self.mem_path, self.mem_path + ".tmp", self.shot_path, self.shot_path + ".tmp"):
            try:
                os.remove(p)
            except OSError:
                pass


def emulator_iwram():
    from .emulator import MEM_REGIONS
    return MEM_REGIONS[0][1]


class GameAI:
    """The AI player, while it plays: start(), stop(); status is what it's doing, in a few words."""

    def __init__(self, run, server, model, log_path, on_change=lambda: None):
        self.run, self.server, self.model = run, server, model
        self.log_path, self.on_change = log_path, on_change
        self.stopping = threading.Event()
        self.status = "Starting"
        self.offline = False                       # the model hasn't answered of late: playing on its own
        self.thread = None
        self.io = None
        self.lock = threading.Lock()

    @property
    def blind(self):
        """Its model turned out not to see: it plays without the screen."""
        return self.io is not None and self.io.blind

    def start(self):
        self.thread = threading.Thread(target=self.main, daemon=True, name="game-ai")
        self.thread.start()

    def stop(self):
        self.stopping.set()

    def alive(self):
        return self.thread is not None and self.thread.is_alive() and not self.stopping.is_set()

    def set_status(self, words):
        if words != self.status:
            self.status = words
            self.on_change()

    def log(self, entry):
        entry = {"t": time.strftime("%Y-%m-%d %H:%M:%S")} | {k: v for k, v in entry.items() if v is not None}
        try:
            with self.lock:
                if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > LOG_MOST:
                    os.replace(self.log_path, self.log_path + ".1")
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def main(self):
        io = None
        try:
            game = self.run.game
            rom = None
            if game.get("system") == "gba" and can_play(game["path"]):
                rom = cartridge(game["path"])          # (a player of its own reads the cartridge too)
            mod = player_for(rom)
            io = self.io = GameIO(self, rom)
            self.log({"event": f"Started, with {self.model or 'no model (on its own)'}"
                               + ("" if mod else ", looking at the screen")})
            self.set_status("Playing")
            if mod is emerald:
                emerald.Emerald(rom, io).play()
            else:
                anygame.AnyGame(game, io).play()
        except emerald.Stop:
            self.log({"event": "Stopped"})
        except Exception as ex:                    # (it says why, here and in the log)
            self.log({"event": "Stopped by an error", "error": traceback.format_exc()[-2000:]})
            self.set_status(f"Stopped: {str(ex)[:60] or type(ex).__name__}")
            print(f"game ai: {ex!r}", flush=True)
            return
        finally:
            if io is not None:
                io.close()
            self.stopping.set()
        self.set_status("Off")
