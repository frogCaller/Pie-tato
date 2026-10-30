"""Instincts: how a person plays a kind of game without stopping to think, for the AI player (pitato/anygame.py) in
games where waiting a second or two for each press would lose: a race, a platformer's level, a fight, a shoot-'em-up.
Each looks at the game's screen many times a second and holds the buttons a player would. A racer holds the gas and
steers to keep on the road (the road's colour just ahead of the car, and where the road goes further on), and backs
up and turns when it's hit something. A platformer runs on and jumps when it's blocked, when the floor ahead drops
away, and now and then anyway, backing off for a run-up when a jump wasn't enough. A fighter goes at the other
fighter with a mix of attacks, blocks, jumps and special moves. A shooter keeps firing and weaves about. The decision
model (pitato/anygame.py) says when to play like that (not on title screens and menus) and which way: where the level
goes, which side the other fighter's on.

What kind of game it is, and what its buttons do, come from what your Bot's model knows of the game (pitato/coach.py);
until it's said, from the game's name; and the buttons from how most games on that console go."""
import random
import re

import numpy as np

KINDS = ("racing", "platformer", "fighting", "shooter", "sports", "puzzle", "rpg", "adventure", "other")
LIVE = ("racing", "platformer", "fighting", "shooter")   # played by instinct, many times a second
SMALL = 96                   # pixels across the picture the instincts look at

# the kind of game, from its name: (a pattern in its name, lower case, the kind), the first that matches
TITLE_KINDS = (
    (r"mario kart|kart\b|racing|racer\b|\brace\b|rally|f-?zero|grand prix|\bgp\b|gran turismo|need for speed|"
     r"ridge racer|out ?run|road rash|rad racer|excitebike|motocross|\bmoto|top gear|wipe ?out|wave race|cruis.n|"
     r"micro machines|pro-am|pole position|burnout|nascar|\bindy|formula|\bf-?1\b|daytona|test drive|speed|drift|"
     r"\bcart\b|\btoca\b", "racing"),
    (r"dr\.? ?mario|tetris|puyo|columns|picross|puzzle|panel de pon|yoshi'?s cookie|wario'?s woods|klax|lemmings|"
     r"bust-a-move|zoop|mean bean|bejeweled|lumines|minesweeper|solitaire|chess|sudoku", "puzzle"),
    (r"mario (tennis|golf|strikers)|tennis|golf|fifa|\bnba|\bnhl|\bnfl|madden|soccer|football|"
     r"baseball|basketball|hockey|bowling|\bhawk'?s (pro|under|american|downhill|project|proving)|skate|\bpga\b|olympic|track (&|and) field|tecmo bowl|"
     r"blades of steel|world cup|volleyball", "sports"),
    (r"street fighter|mortal kombat|tekken|king of fighters|\bkof\b|fatal fury|samurai shodown|killer instinct|"
     r"smash bros|darkstalkers|soul ?(calibur|blade)|bloody roar|guilty gear|marvel vs|x-men vs|primal rage|"
     r"clay ?fighter|art of fighting|virtua fighter|dead or alive|toshinden|punch-out|dragon ball z|"
     r"power instinct|world heroes|eternal champions|bushido blade|rival schools", "fighting"),
    (r"pok[eé]mon (pinball|snap|stadium|puzzle)|mario (party|paint)|party", "other"),
    (r"pok[eé]mon|final fantasy|dragon (quest|warrior)|chrono|earthbound|mother\b|secret of mana|seiken|"
     r"breath of fire|lufia|phantasy star|golden sun|fire emblem|suikoden|star ocean|tales of|persona|"
     r"megami|paper mario|mario (&|and) luigi|mario rpg|xenogears|wild arms|kingdom hearts|legend of dragoon|"
     r"\bys\b|terranigma|illusion of gaia|shining force|advance wars|tactics|dragon slayer", "rpg"),
    (r"gradius|r-type|\b194[2-5]\b|galaga|galaxian|space invaders|xevious|life force|salamander|parodius|"
     r"thunder ?force|star ?fox|raiden|tyrian|ikaruga|contra|probotector|metal slug|zanac|gun\.?smoke|twinbee|"
     r"darius|axelay|u\.?n\.? squadron|phalanx|asteroids|defender|robotron|smash tv|einhander|gunbird|"
     r"strikers 1945|b-wings|1943|sky ?shark|tiger-heli|shmup|shoot", "shooter"),
    (r"zelda|link'?s awakening|resident evil|silent hill|tomb raider|metal gear|monkey island|myst\b|"
     r"secret of evermore|alundra|beyond oasis|landstalker|okami|shadow of", "adventure"),
    (r"mario|sonic|mega ?man|rockman|kirby|castlevania|metroid|donkey kong|yoshi|wario ?land|adventure island|"
     r"bonk|crash bandicoot|spyro|banjo|rayman|jazz jackrabbit|earthworm jim|aladdin|lion king|ninja gaiden|"
     r"shinobi|kid icarus|ducktales|chip .?n.? dale|prince of persia|commander keen|pitfall|bubsy|gex\b|croc\b|"
     r"ghouls|ghosts|wonder boy|alex kidd|bubble bobble|mega man|cave story|shovel knight|celeste|vectorman|"
     r"rocket knight|kid chameleon|ristar|toejam|cool spot|kid kool|super meat boy|klonoa|tail concerto|"
     r"ape escape|pandemonium|jumping flash|blinx|mischief makers|conker", "platformer"),
)

# what a button's for, in a game: its role, and the words that say it
ROLE_WORDS = {
    "gas": r"accelerat|\bgas\b|throttle|\bdrive|go faster|speed up",
    "brake": r"\bbrake|revers|slow down",
    "jump": r"\bjump",
    "run": r"\brun\b|\bruns\b|\bdash|sprint",
    "attack": r"attack|punch|kick|\bhit\b|slash|strike|sword|whip|\bfight",
    "fire": r"\bfire|shoot|\bshot|laser|blast|\bgun\b",
}
# ...and which button it is in most games on each console, until it's known for this one (the attacks: several)
NINTENDO_ROLES = {"gas": "A", "brake": "B", "jump": "A", "run": "B", "attack": ("B", "A"), "fire": "B"}
SONY_ROLES = {"gas": "Cross", "brake": "Square", "jump": "Cross", "run": "",
              "attack": ("Square", "Triangle", "Cross", "Circle"), "fire": "Square"}
SEGA8_ROLES = {"gas": "1", "brake": "2", "jump": "2", "run": "", "attack": ("1", "2"), "fire": "1"}
ROLES = {
    "nes": NINTENDO_ROLES, "gb": NINTENDO_ROLES, "gbc": NINTENDO_ROLES,
    "gba": dict(NINTENDO_ROLES, attack=("B", "A", "L", "R")),
    "snes": {"gas": "B", "brake": "Y", "jump": "B", "run": "Y", "attack": ("Y", "X", "B", "A", "L", "R"), "fire": "Y"},
    "nds": {"gas": "A", "brake": "B", "jump": "B", "run": "Y", "attack": ("Y", "X", "B", "A"), "fire": "Y"},
    "genesis": {"gas": "B", "brake": "A", "jump": "C", "run": "", "attack": ("A", "B", "C"), "fire": "B"},
    "sms": SEGA8_ROLES, "gg": SEGA8_ROLES,
    "n64": {"gas": "A", "brake": "B", "jump": "A", "run": "", "attack": ("B", "A"), "fire": "A"},
    "ps1": SONY_ROLES, "psp": SONY_ROLES,
    "dc": {"gas": "R", "brake": "L", "jump": "A", "run": "", "attack": ("X", "A", "B", "Y"), "fire": "A"},
}
OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up"}
PAD = {"Up": "up", "Down": "down", "Left": "left", "Right": "right"}   # (a role can be a direction: "Up: accelerate")


def guess_kind(title):
    """The kind of game, from its name (lower case, its tags gone): one of KINDS ("other" if nothing says)."""
    t = (title or "").lower()
    for pattern, kind in TITLE_KINDS:
        if re.search(pattern, t):
            return kind
    return "other"


def kind_of(words):
    """One of KINDS, from what a model said ("a 2D platformer", "Racing game"...); None if it's none of them."""
    w = (words or "").lower()
    if not w:
        return None
    for kind, pattern in (("racing", r"rac(e|ing)|kart|driving"), ("platformer", r"platform|side.?scroll|jump.?n"),
                          ("fighting", r"fight|beat.?em|brawl"), ("shooter", r"shoot|shmup|shot|bullet"),
                          ("sports", r"sport|football|soccer|golf|tennis|basketball|baseball|hockey"),
                          ("puzzle", r"puzzle|block|match"), ("rpg", r"rpg|role.?play"),
                          ("adventure", r"adventure|action.?adv|explor"), ("other", r"other")):
        if re.search(pattern, w):
            return kind
    return None


def label_spots(text, labels):
    """Where each button's named in some text: [(where, label)]. One-letter names count only as capitals (not
    "a" the word); longer ones (Start, Cross) either way."""
    spots = []
    for label in labels:
        flags = 0 if len(label) == 1 else re.I
        for m in re.finditer(r"(?<![\w-])%s(?![\w-])" % re.escape(label), text, flags):
            spots.append((m.start(), label))
    return spots


def parse_roles(text, labels):
    """What each role's button is, from words like "B: accelerate; A: use an item; L or R: hop" or "Press A to jump
    and B to run": {role: label} (the attacks: a tuple). Each word that says a role goes with the button named
    nearest it, in its part of the text (an attack with every button named there: "B and A kick")."""
    found = {}
    for clause in re.split(r"[;\n]|\.(?:\s|$)", text or ""):
        spots = label_spots(clause, labels)
        if not spots:
            continue
        for role, pattern in ROLE_WORDS.items():
            for m in re.finditer(pattern, clause, re.I):
                if role == "attack":
                    found.setdefault("attack", [])
                    found["attack"] += [b for _, b in sorted(spots) if b not in found["attack"]]
                else:
                    found.setdefault(role, min(spots, key=lambda s: abs(s[0] - m.start()))[1])
    if "attack" in found:
        found["attack"] = tuple(found["attack"])
    return found


def roles_for(system, labels, buttons_said=""):
    """{role: label} for a game: what's been said of its buttons, over how most games on its console go (only
    buttons it has); and "told": the roles that were said. A button said to shoot, with nothing said of running,
    isn't held to run (it's the shooting button: Mega Man's B)."""
    roles = dict(ROLES.get(system, NINTENDO_ROLES))
    said = {r: v for r, v in parse_roles(buttons_said, list(labels) + list(PAD)).items()
            if r in ("gas", "brake") or v not in PAD}                 # (only the gas and the brake a direction)
    roles.update(said)
    if "run" not in said and roles.get("run") and roles["run"] in (said.get("fire"),) + tuple(said.get("attack", ())):
        roles["run"] = ""
    have = set(labels) | set(PAD)
    out = {}
    for role, v in roles.items():
        if role == "attack":
            v = tuple(b for b in (v if isinstance(v, (tuple, list)) else (v,)) if b in have)
            out[role] = v or tuple(b for b in labels[:2])
        else:
            out[role] = v if v in have else ""
    out["told"] = tuple(sorted(said))
    return out


# ---- looking ----------------------------------------------------------------------------------------------------
def small(look, width=SMALL):
    """A look's picture, small, as an (h, w, 3) int16 array (made once per look)."""
    got = getattr(look, "_small", None)
    if got is not None and got.shape[1] == width:
        return got
    from PIL import Image
    im = look.im
    h = max(2, round(im.height * width / im.width))
    got = np.asarray(im.resize((width, h), Image.BILINEAR), dtype=np.int16)
    look._small = got
    return got


def grey(a):
    return a.mean(axis=2)


def shift(prev, cur, most, axis=1):
    """How far the picture moved between two grey ones: (shift, how well it matched there, and with none). + when
    what's on it moved left (or up): the view moving right (or down). The middle rows only (not a score along the
    top)."""
    h = cur.shape[0]
    rows = slice(int(h * 0.15), int(h * 0.95))
    p, c = prev[rows], cur[rows]
    if axis == 0:
        p, c = p.T, c.T
    n = c.shape[1]
    best, best_err, zero_err = 0, None, None
    for s in range(-most, most + 1):
        if s >= 0:
            a, b = c[:, :n - s], p[:, s:]
        else:
            a, b = c[:, -s:], p[:, :n + s]
        err = float(np.abs(a - b).mean())
        if s == 0:
            zero_err = err
        if best_err is None or err < best_err - 1e-6 or (abs(err - best_err) <= 1e-6 and abs(s) < abs(best)):
            best, best_err = s, err
    return best, best_err, zero_err


def motion(prev, cur, most, axis=1):
    """How far the view moved between two grey pictures (as shift()), if that's clear: the picture matches itself
    moved that far much better than not moved at all; else 0."""
    s, err, err0 = shift(prev, cur, most, axis)
    return s if err < 0.85 * err0 else 0


def common_colour(a):
    """The most common colour in a picture (rgb), roughly: its pixels' colours in coarse bins, the fullest bin's
    mean; and how much its pixels vary."""
    px = a.reshape(-1, 3)
    q = px // 32
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    top = np.bincount(keys, minlength=512).argmax()
    sel = px[keys == top]
    return sel.mean(axis=0), float(sel.std(axis=0).mean())


def runs(row):
    """The runs of True in a row of booleans: [(start, end)] (end not in it)."""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def close_gaps(row, most):
    """A row of booleans with short runs of False between Trues made True (a car, or a line, on the road)."""
    out = row.copy()
    rs = runs(row)
    for (s0, e0), (s1, e1) in zip(rs, rs[1:]):
        if s1 - e0 <= most:
            out[e0:s1] = True
    return out


# ---- the instincts -------------------------------------------------------------------------------------------------
class Instinct:
    """Plays a kind of game for a moment at a time: tick(look, now) says what to hold for the next moment, as a few
    steps: [(buttons, sticks, seconds)], buttons by the emulator's names (libretro's), sticks {axis: -127 to 127}.
    way: which way to go ("right", "left"; where the level goes, or the other fighter is). stuck(): it's been told
    it's got nowhere for a while (try something else)."""

    TICK = 0.1

    def __init__(self, system, labels, roles, stick=False):
        self.system, self.labels, self.roles, self.stick = system, dict(labels, **PAD), roles, stick
        self.way = "right"
        self.prev = None                           # the last look's grey picture
        self.said = ""                             # what it's doing, in a few words (for the game's menu)

    def button(self, role):
        """A role's button, as the emulator takes it (or None)."""
        label = self.roles.get(role)
        return self.labels.get(label) if isinstance(label, str) and label else None

    def attacks(self):
        return [self.labels[b] for b in self.roles.get("attack", ()) if b in self.labels and b not in PAD] or \
            [v for k, v in self.labels.items() if k not in ("Start", "Select", "Pause") and k not in PAD][:2]

    def dirs(self, *ds):
        """Directions held: d-pad buttons, or the left stick pushed (a stick console's): (buttons, sticks)."""
        if not self.stick:
            return set(d for d in ds if d), {}
        sticks = {}
        for d in ds:
            if d in ("left", "right"):
                sticks["lx"] = -127 if d == "left" else 127
            elif d in ("up", "down"):
                sticks["ly"] = -127 if d == "up" else 127
        return set(), sticks

    def step(self, buttons=(), dirs=(), secs=None, steer=None):
        """One step: buttons and directions held for secs (a tick, unless said); steer pushes the stick partway
        (-1 to 1) on a stick console."""
        b, s = self.dirs(*dirs)
        b |= set(x for x in buttons if x)
        if steer is not None and self.stick:
            s["lx"] = int(max(-1.0, min(1.0, steer)) * 127)
        return (b, s, self.TICK if secs is None else secs)

    def tick(self, look, now):
        return [self.step()]

    def stuck(self, now):
        pass

    def moved(self, g):
        """How much the picture changed since the last look (0 to 255), and remember this one."""
        changed = float(np.abs(g - self.prev).mean()) if self.prev is not None and self.prev.shape == g.shape else 255.0
        self.prev = g
        return changed


class Racing(Instinct):
    """Holds the gas and steers toward the middle of the road: the road's colour learnt from just ahead of the car
    (the most common colour low in the middle of the driver's view), the road found in rows from the car out to the
    distance (gaps the size of a car, or a line, closed), and steered toward where its middle is, more by the rows
    further on (a bend's seen coming). A view that's stopped changing with the gas held means it's hit something:
    it backs up (the brake held), steering the other way, then goes on. On a split screen (a map or another view
    below), the view is the top part."""

    STILL = 1.2               # how little the view changes (of 255) when the car's not moving
    STILL_FOR = 1.5           # seconds of that, the gas held, after it's been moving: it's stuck
    MOVED_WITHIN = 5.0        # (moving this lately: not a race that's yet to start)
    BACK_FOR = 1.2            # seconds it backs up for
    LEARN_EVERY = 4.0         # seconds between looks at what colour the road is
    DEAD = 0.05               # the road's middle this near the car's (of half the view across): no steering
    GAIN = 2.5

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.colour, self.spread, self.learnt_at = None, 30.0, -1e9
        self.still_since, self.back_until, self.back_way = None, 0.0, "left"
        self.offset, self.moving_at = 0.0, -1e9

    def view(self, a):
        """The driver's view: the screen above a band across it that's all one dark colour with things above and
        below it (a split screen), else all of it."""
        h = a.shape[0]
        lo, hi = int(h * 0.35), int(h * 0.75)
        band = a[lo:hi]
        spread = band.std(axis=1).mean(axis=1)
        dark = band.mean(axis=(1, 2))
        for i in np.where((spread < 4) & (dark < 60))[0]:
            y = lo + i
            below = a[min(h - 1, y + max(2, h // 12)):]
            if a[:y].std() > 12 and below.size and below.std() > 12:
                return a[:y]
        return a

    def learn(self, v):
        """The road's colour: the most common colour low in the middle of the view (just ahead of the car and
        round it), if that looks like a road (not most of the view, or a sliver of it)."""
        h, w = v.shape[:2]
        colour, spread = common_colour(v[int(h * 0.62):int(h * 0.92), int(w * 0.28):int(w * 0.72)])
        share = float((np.abs(v - colour).sum(axis=2) < max(45.0, spread * 4)).mean())
        if 0.08 < share < 0.85 or self.colour is None:
            self.colour, self.spread = colour, spread

    def road(self, v):
        """Where the road's middle is, ahead: (how far off the middle of the view, -1 to 1: + to the right; how
        much of the view low down is road)."""
        h, w = v.shape[:2]
        mask = np.abs(v - self.colour).sum(axis=2) < max(45.0, self.spread * 4)
        top, bottom = int(h * 0.5), int(h * 0.94)
        total = weight = 0.0
        mid = w / 2
        for y in range(top, bottom, 2):
            row = close_gaps(mask[y], max(2, w // 4))
            rs = [(s, e) for s, e in runs(row) if e - s >= max(2, w // 12)]
            if not rs:
                continue
            s, e = min(rs, key=lambda r: 0 if r[0] <= mid < r[1] else min(abs(r[0] - mid), abs(r[1] - mid)))
            far = 1.0 - (y - top) / max(1, bottom - top)            # (rows further on count for more)
            wgt = 1.0 + 2.0 * far
            total += wgt * ((s + e) / 2 - mid) / mid
            weight += wgt
        share = float(mask[int(h * 0.7):bottom, int(w * 0.3):int(w * 0.7)].mean())
        return (total / weight if weight else 0.0), share

    def tick(self, look, now):
        a = small(look)
        v = self.view(a)
        changed = self.moved(grey(v))
        gas, brake = self.button("gas"), self.button("brake")
        if now < self.back_until:                  # backing up, steering the other way
            self.said = "Backing up"
            return [self.step((brake,), ("down" if not brake else None, self.back_way))]
        if now - self.learnt_at > self.LEARN_EVERY or self.colour is None:
            self.learn(v)
            self.learnt_at = now
        self.offset, share = self.road(v)
        if changed < self.STILL:
            self.still_since = self.still_since or now
            if now - self.still_since > self.STILL_FOR and self.still_since - self.moving_at < self.MOVED_WITHIN:
                self.stuck(now)
                return [self.step((brake,), ("down" if not brake else None, self.back_way))]
        else:
            self.still_since, self.moving_at = None, now
        o = self.offset
        self.said = "Driving"
        if abs(o) < self.DEAD:
            return [self.step((gas,))]
        way = "right" if o > 0 else "left"
        if self.stick:
            return [self.step((gas,), steer=o * self.GAIN)]
        duty = min(1.0, abs(o) * self.GAIN)
        held = round(self.TICK * duty, 3)
        steps = [self.step((gas,), (way,), held)]
        if held < self.TICK:
            steps.append(self.step((gas,), secs=round(self.TICK - held, 3)))
        return steps

    def stuck(self, now):
        """Hit something: back up a while, steering away from where the road was."""
        self.back_way = "left" if self.offset > 0 else "right"
        self.back_until = now + self.BACK_FOR
        self.still_since = None
        self.colour = None                         # (and look at the road again after)


class Platformer(Instinct):
    """Runs the way it's going (the run button held, if the game has one) and jumps: when it's held that way and the
    view's stopped moving (a wall, a pipe), longer each time; when the floor ahead drops away (the background's
    colour showing at the bottom of the screen ahead, where there's floor under it); when something's moving just
    ahead of it, low down, on its own (not as the view moves: an enemy coming); and now and then anyway. When
    jumping hasn't got it past something, it backs off for a run-up. In a game with a button to shoot or attack (said
    of it: not just how most games go), it presses that every so often too."""

    BLOCKED = 3               # looks in a row not moving on, holding that way: blocked
    HOP = (1.4, 3.0)          # seconds between hops, at random
    JUMPS = (0.30, 0.45, 0.6, 0.6)   # how long jumps are held, try by try (a longer press jumps higher)
    BACK_FOR = 0.5

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.jump_until = self.rest_until = self.back_until = 0.0
        self.next_hop = None
        self.blocked = self.tries = 0
        self.going = 0                             # looks in a row moving on
        self.shots = 0

    def gap_ahead(self, a):
        """The floor ahead drops away: low down in front, the background's colour (from high up the screen), where
        there's floor underneath."""
        h, w = a.shape[:2]
        sky, spread = common_colour(a[int(h * 0.12):int(h * 0.4)])
        low = a[int(h * 0.88):]
        like_sky = np.abs(low - sky).sum(axis=2) < max(30.0, spread * 4)
        if self.way == "right":
            under, ahead = like_sky[:, int(w * 0.36):int(w * 0.5)], like_sky[:, int(w * 0.52):int(w * 0.66)]
        else:
            under, ahead = like_sky[:, int(w * 0.5):int(w * 0.64)], like_sky[:, int(w * 0.34):int(w * 0.48)]
        if under.mean() > 0.3:                     # (no floor under it: it's in the air, or this isn't that game)
            return False
        cols = ahead.mean(axis=0) > 0.8
        return any(e - s >= max(2, w // 30) for s, e in runs(cols))

    def coming(self, prev, g, s):
        """Something moving on its own just ahead, low down: what's there unlike the last look, the view's own
        move (s) taken out."""
        h, w = g.shape
        was = np.roll(prev, -s, axis=1)            # (what was at x + s is at x now)
        cols = slice(int(w * 0.52), int(w * 0.68)) if self.way == "right" else slice(int(w * 0.32), int(w * 0.48))
        box = np.abs(g - was)[int(h * 0.55):int(h * 0.88), cols]
        return float((box > 40).mean()) > 0.02

    def shooter(self, run, jump):
        """Its shooting button, if it's been said to have one (and it's not running or jumping too)."""
        told = self.roles.get("told", ())
        b = self.button("fire") if "fire" in told else self.attacks()[0] if "attack" in told else None
        return b if b not in (run, jump) else None

    def tick(self, look, now):
        a = small(look)
        g = grey(a)
        prev = self.prev
        self.moved(g)
        run, jump = self.button("run"), self.button("jump")
        shoot = self.shooter(run, jump)
        self.shots += 1
        shoot = shoot if shoot and self.shots % 4 == 0 else None   # (pressed one moment in four: a new press each)
        back = OPPOSITE[self.way]
        if self.next_hop is None:
            self.next_hop = now + random.uniform(*self.HOP)
        if now < self.back_until:
            self.said = "Backing off for a run-up"
            return [self.step((run,), (back,))]
        moving_on, s = False, None
        if prev is not None and prev.shape == g.shape:
            s = motion(prev, g, max(3, a.shape[1] // 10))
            moving_on = (s if self.way == "right" else -s) >= 1
        self.going = self.going + 1 if moving_on else 0
        jumping = now < self.jump_until
        if not jumping and now >= self.rest_until:
            self.blocked = 0 if moving_on else self.blocked + 1
            why = None
            if self.blocked >= self.BLOCKED:
                why = "blocked"
            elif self.gap_ahead(a):
                why = "gap"
            elif s is not None and self.coming(prev, g, s):
                why = "enemy"
            elif now >= self.next_hop:
                why = "hop"
            if why == "blocked" and self.tries >= len(self.JUMPS):
                self.tries, self.blocked = 1, 0     # (jumping hasn't done it: back off, for a run-up)
                self.back_until = now + self.BACK_FOR
                return [self.step((run,), (back,))]
            if why:
                held = self.JUMPS[min(self.tries, len(self.JUMPS) - 1)] if why == "blocked" else \
                    0.6 if why == "gap" else 0.35 if why == "enemy" else random.uniform(0.2, 0.45)
                self.tries += why == "blocked"
                self.jump_until, self.rest_until = now + held, now + held + self.TICK
                self.next_hop = now + random.uniform(*self.HOP)
                jumping = True
                self.blocked = 0
                self.said = {"blocked": "Jumping over something", "gap": "Jumping a gap",
                             "enemy": "Jumping something coming", "hop": "Running"}[why]
        if self.going >= 10:
            self.tries = 0
        if not jumping:
            self.said = "Running"
        return [self.step((run, jump if jumping else None, shoot), (self.way,))]

    def stuck(self, now):
        """Got nowhere for a while: the other way for a few seconds (the level may go that way)."""
        self.back_until = now + 3.0


class Fighter(Instinct):
    """Goes at the other fighter (on the side it's told: right to start with, as player 1 starts on the left) with
    a mix of moves: stepping in, quick attacks, blocking (holding away), jumping in with an attack, and special
    moves (a quarter circle forward and a punch; forward, down, down-forward and a punch)."""

    def tick(self, look, now):
        self.moved(grey(small(look)))
        toward, away = self.way, OPPOSITE[self.way]
        hits = self.attacks()
        hit = random.choice(hits)
        punch = hits[0]
        r = random.random()
        if r < 0.25:
            self.said = "Moving in"
            return [self.step((), (toward,), 0.25)]
        if r < 0.6:
            self.said = "Attacking"
            return [self.step((hit,), secs=0.08), self.step(secs=0.06)]
        if r < 0.7:
            self.said = "Blocking"
            return [self.step((), (away,), 0.45)]
        if r < 0.8:
            self.said = "Jumping in"
            return [self.step((), ("up", toward), 0.12), self.step((hit,), secs=0.3)]
        self.said = "A special move"
        if r < 0.92:
            return [self.step((), ("down",), 0.05), self.step((), ("down", toward), 0.05),
                    self.step((), (toward,), 0.05), self.step((punch,), (toward,), 0.08), self.step(secs=0.05)]
        return [self.step((), (toward,), 0.05), self.step((), ("down",), 0.05),
                self.step((), ("down", toward), 0.05), self.step((punch,), ("down", toward), 0.08), self.step(secs=0.05)]

    def stuck(self, now):
        self.way = OPPOSITE[self.way]              # (maybe they're the other side now)


class Shooter(Instinct):
    """Keeps firing (pressed and let go each moment: most games fire again only for a new press) and weaves about:
    up and down when the game scrolls sideways, left and right when it scrolls up; now and then it holds still."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.across = self.along = 0.0             # how much it's scrolled sideways, and up or down
        self.move, self.move_until = None, 0.0

    def tick(self, look, now):
        g = grey(small(look))
        prev = self.prev
        self.moved(g)
        if prev is not None and prev.shape == g.shape:
            sx = motion(prev, g, 4, axis=1)
            sy = motion(prev, g, 4, axis=0)
            self.across = 0.9 * self.across + abs(sx)
            self.along = 0.9 * self.along + abs(sy)
        if now >= self.move_until:
            ways = ("left", "right") if self.along > 1.5 * self.across else ("up", "down")
            self.move = random.choice(ways + (None,))
            self.move_until = now + random.uniform(0.3, 0.9)
        fire = self.button("fire") or self.attacks()[0]
        self.said = "Shooting"
        half = round(self.TICK / 2, 3)
        return [self.step((fire,), (self.move,), half), self.step((), (self.move,), half)]

    def stuck(self, now):
        self.move_until = 0.0


INSTINCTS = {"racing": Racing, "platformer": Platformer, "fighting": Fighter, "shooter": Shooter}
