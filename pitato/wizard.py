"""setup.sh's questions, and its screen while it works, on a terminal of its own: a few questions, then a line for
each step, as an app's own setup has it. Arrows move, Space ticks, Enter goes on and Esc goes back. Python's own
library only: it runs before setup.sh has put anything in.

  wizard.py ask ANSWERS   the questions: whether it's in a GPi Case; Default (everything this Pi can run) or Custom
                          (what goes in, each with how long it takes, so the big builds can wait); which of your
                          services to connect, each checked as it's added and kept as Settings keeps it (Home
                          Assistant, Pi-hole, Ollama, Plex, Jellyfin, RetroAchievements, the web page's password);
                          and whether to restart when it's done. What it knows of this machine comes from setup.sh
                          (PIETATO_W_*). The answers go in ANSWERS, a line each (GPI=yes, LEAVE_OUT=ps1 neogeo...)
  wizard.py show LOG      setup.sh's output as it works (on its stdin): a line for each step, a moving one for the
                          one under way, what didn't go in, and All set at the end. All of it goes in LOG

Without a terminal (Update software, an SD card image, answers piped in), setup.sh asks the old way instead."""
import glob
import os
import queue
import re
import select
import shutil
import signal
import sys
import termios
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if __name__ == "__main__":                      # (run as a script: the package beside it, not its files as modules)
    sys.path[0] = os.path.dirname(HERE)

CORES = "/usr/local/lib/libretro"
PROGS = "/usr/local/lib/pitato"
BACK = object()                                 # Esc: back a question
SKIP = object()                                 # a question that didn't need asking


class Cancelled(Exception):
    """Ctrl+C, or Not now: nothing's changed."""


# ---- this machine, as setup.sh says it is ------------------------------------------------------------------------------
class Machine:
    """What setup.sh worked out: the Pi (or PC), what it can run, and what it was set up with before."""

    def __init__(self, env=None):
        e = os.environ if env is None else env

        def get(key, default=""):
            return str(e.get("PIETATO_W_" + key, default)).strip()

        self.model = get("MODEL")
        self.pc = get("PC") == "yes"
        self.big = get("BIG") == "yes"
        self.arch = get("ARCH")
        self.neo_old = get("NEO_OLD") == "yes"
        self.ask_case = get("ASK_CASE")              # the GPi Case it asks about: 2w, 2, or none
        self.ask_yes = get("ASK_YES", "yes") == "yes"
        self.gpi = get("GPI")                        # yes or no already (--gpi, --no-gpi), or not yet
        self.case = get("CASE")
        self.machine = get("MACHINE", "Pi")
        self.static = get("STATIC")
        self.user = get("USER")
        self.home = get("HOME")
        self.os = get("OS")
        self.mem = int(get("MEM", "0") or 0)          # MB
        self.free = int(get("FREE", "0") or 0)        # MB on the card
        self.saved = get("SAVED") == "yes"           # set up before: what it left out (LEAVE_OUT), as it was
        self.left_out = set(get("LEAVE_OUT").split())
        self.keep_login = get("KEEP_LOGIN") == "yes"
        self.desktop = get("DESKTOP") == "yes"       # a PC that starts in its desktop now
        self.mode = get("MODE")                      # default or custom (--default, --custom), or ask
        self.without = get("WITHOUT")                # --without's: no question about what goes in
        self.cores = get("CORES") or CORES
        self.progs = get("PROGS") or PROGS

    @property
    def speed(self):
        """0: a Pi Zero 2 or 3 (or a board it doesn't know); 1: a Pi 4; 2: a Pi 5; 3: a PC."""
        if self.pc:
            return 3
        if "Pi 5" in self.model or "Compute Module 5" in self.model:
            return 2
        if "Pi 4" in self.model or "Pi 400" in self.model or "Compute Module 4" in self.model:
            return 1
        return 0

    def name(self):
        m = re.sub(r"\s+Rev\s+[\d.]+$", "", self.model.replace("\0", "")).strip()
        return m or ("This computer" if self.pc else "This Pi")


# ---- what goes in: setup.sh's optional parts ------------------------------------------------------------------------
# (id, group, words, what it is, minutes on a Pi Zero 2 or 3, a Pi 4, a Pi 5, a PC: None where it isn't put in)
PARTS = [
    ("classic", "Games", "Game Boy, NES, SNES, Genesis", "ready-made, no build", (2, 1, 1, 1)),
    ("ps1", "Games", "PlayStation", "built here", (15, 5, 3, 2)),
    ("n64", "Games", "N64", "built here", (None, 20, 10, 3)),
    ("psp", "Games", "PSP", "built here", (None, 60, 20, 15)),
    ("nds", "Games", "DS", "built here", (None, 10, 5, 3)),
    ("dc", "Games", "Dreamcast", "built here", (None, 20, 10, 3)),
    ("ps2", "Games", "PlayStation 2", "built here", (None, None, None, 15)),
    ("gc", "Games", "GameCube and Wii", "built here", (None, None, None, 15)),
    ("neogeo", "Games", "Neo Geo", "built here", (30, 10, 6, 3)),
    ("ngp", "Games", "Neo Geo Pocket", "built here", (6, 2, 1, 1)),
    ("link", "Games", "Game Boy link cable", "with your other Pietatos", (5, 2, 1, 1)),
    ("cheevos", "Games", "Achievements", "RetroAchievements", (3, 1, 1, 1)),
    ("chromium", "Extras", "Chromium", "the whole web in Web: 300 MB", (None, 6, 4, 4)),
    ("office", "Extras", "Documents in their own layout", "LibreOffice: 400 MB", (12, 6, 4, 3)),
    ("toys", "Extras", "Terminal toys in Apps", "cmatrix, hollywood, nyancat", (3, 2, 1, 1)),
    ("computers", "Extras", "Your other computers' files", "Windows, Mac and Linux", (2, 1, 1, 1)),
]
PART_IDS = [p[0] for p in PARTS]
BASE = (12, 6, 4, 3)                    # minutes for the rest (packages, media mode, the web page...), whatever's picked
SIXTY_FOUR = ("arm64", "aarch64", "amd64", "x86_64")
GAME_FILES = {"ps1": "pcsx_rearmed", "n64": "mupen64plus_next", "psp": "ppsspp", "nds": "melonds", "dc": "flycast",
              "ps2": "pcsx2", "gc": "dolphin", "neogeo": "fbneo_neogeo", "ngp": "mednafen_ngp", "link": "gambatte"}


def can_have(part, m, case=None):
    """Whether this machine can have the part (setup.sh would put it in)."""
    case = m.case if case is None else case
    if part in ("n64", "psp", "dc"):
        return m.big
    if part == "nds":
        return m.big and m.arch in SIXTY_FOUR
    if part in ("ps2", "gc"):
        return m.pc
    if part == "neogeo":
        return not m.neo_old
    if part == "chromium":
        return m.big and case != "2w"
    return part in PART_IDS


def already(part, m):
    """It's in already (built here before, or installed): nothing much to do for it this time."""
    if part in GAME_FILES:
        return os.path.isfile(os.path.join(m.cores, GAME_FILES[part] + "_libretro.so"))
    if part == "cheevos":
        return os.path.isfile(os.path.join(m.progs, "librcheevos.so"))
    if part == "toys":
        return os.path.isfile(os.path.join(m.progs, "cacafire")) and bool(shutil.which("cmatrix"))
    if part == "office":
        return bool(shutil.which("soffice") or shutil.which("libreoffice"))
    if part == "chromium":
        return bool(shutil.which("chromium") or shutil.which("chromium-browser"))
    if part == "computers":
        return bool(shutil.which("sshfs") and shutil.which("mount.cifs"))
    if part == "classic":
        return bool(glob.glob("/usr/lib/*/libretro/mgba_libretro.so") or glob.glob("/usr/lib/libretro/mgba_libretro.so"))
    return False


def minutes(part, m):
    if already(part, m):
        return 0
    times = next(p[4] for p in PARTS if p[0] == part)
    return times[m.speed] or 0


def estimate(parts, m):
    """Minutes for the whole of it, with these parts in."""
    return BASE[m.speed] + sum(minutes(p, m) for p in parts)


def how_long(mins, about=True):
    """30 min, 1 h 20 min (about it, or not)."""
    if not about:
        return how_long(mins)[6:]
    mins = max(1, int(round(mins)))
    if mins < 60:
        return f"about {mins} min"
    h, rest = divmod(mins, 60)
    rest = int(round(rest / 5.0) * 5)
    if rest == 60:
        h, rest = h + 1, 0
    return f"about {h} h" + (f" {rest} min" if rest else "")


def available(m, case=None):
    return [p for p in PART_IDS if can_have(p, m, case)]


# ---- the look: the shapes and colours ------------------------------------------------------------------------------
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def visible(text):
    return len(ANSI.sub("", text))


def cut(text, width, ell="…"):
    """text cut to width columns as they show (its colours kept, and ended), ell where it's cut."""
    if visible(text) <= width:
        return text
    out, n, i = [], 0, 0
    while i < len(text) and n < max(0, width - len(ell)):
        m = ANSI.match(text, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        out.append(text[i])
        n += 1
        i += 1
    return "".join(out) + ell + ("\x1b[0m" if "\x1b[" in text else "")


def wrap(text, width):
    """text as lines of width (or fewer) columns, broken between words."""
    rows, row = [], ""
    for w in text.split():
        if row and visible(row) + 1 + visible(w) > width:
            rows.append(row)
            row = w
        else:
            row = f"{row} {w}" if row else w
    return rows + [row] if row or not rows else rows


class Look:
    """Its shapes and colours: Unicode's on a terminal that has them, plain letters on the Pi's own console (whose font
    hasn't the shapes), and no colours with NO_COLOR."""

    def __init__(self, fancy=None, colour=None, stream=None):
        stream = stream or sys.stdout
        term = os.environ.get("TERM", "")
        if fancy is None:
            enc = (getattr(stream, "encoding", "") or "").lower()
            fancy = "utf" in enc and term not in ("linux", "dumb", "vt100", "vt220")
        if colour is None:
            colour = not os.environ.get("NO_COLOR") and term != "dumb"
        self.fancy, self.colour = fancy, colour
        u = fancy
        self.bar, self.top, self.end = ("│", "┌", "└") if u else ("|", "+", "+")
        self.on, self.done, self.stop = ("◆", "◇", "■") if u else ("*", "o", "x")
        self.radio = ("●", "○") if u else ("(*)", "( )")
        self.box = ("◼", "◻") if u else ("[x]", "[ ]")
        self.ok, self.warn = ("✓", "▲") if u else ("+", "!")
        self.rule = "─" if u else "-"
        self.corner = ("╮", "╯", "├") if u else ("+", "+", "+")
        self.spin = "◒◐◓◑" if u else "|/-\\"
        self.dot = "·" if u else "-"
        self.more = ("↑", "↓") if u else ("^", "v")
        self.arrows = "↑↓" if u else "Up/Down"
        self.cursor = "\x1b[7m \x1b[27m" if colour else "_"
        self.secret = "•" if u else "*"
        self.ell = "…" if u else "..."

    def fit(self, text, width):
        """text cut to width, in letters this terminal has (… as ... on the console)."""
        return cut(text if self.fancy else text.replace("…", "..."), width, self.ell)

    def c(self, code, text):
        return f"\x1b[{code}m{text}\x1b[0m" if self.colour and text else text

    def cyan(self, t):
        return self.c("36", t)

    def green(self, t):
        return self.c("32", t)

    def yellow(self, t):
        return self.c("33", t)

    def red(self, t):
        return self.c("31", t)

    def dim(self, t):
        return self.c("2", t)

    def bold(self, t):
        return self.c("1", t)


# ---- the terminal ------------------------------------------------------------------------------------------------
KEYS = {"\r": "enter", "\n": "enter", " ": "space", "\x7f": "backspace", "\x08": "backspace", "\x03": "ctrl-c",
        "\x04": "ctrl-d", "\x15": "ctrl-u", "\t": "tab", "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right",
        "\x1b[D": "left", "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left", "\x1b[3~": "delete",
        "\x1b[Z": "up"}


class Term:
    """The terminal: keys in one at a time (Ctrl+C as a key too), text out."""

    def __init__(self, fd=0, out=None):
        self.fd = fd
        self.out = out or sys.stdout
        self.saved = None

    def __enter__(self):
        try:
            self.saved = termios.tcgetattr(self.fd)
            mode = termios.tcgetattr(self.fd)
            mode[0] &= ~(termios.IXON | termios.ICRNL)
            mode[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG | termios.IEXTEN)
            mode[6][termios.VMIN], mode[6][termios.VTIME] = 1, 0
            termios.tcsetattr(self.fd, termios.TCSADRAIN, mode)
        except termios.error:
            self.saved = None
        self.write("\x1b[?25l")                  # (no cursor: the questions draw their own)
        return self

    def __exit__(self, *exc):
        self.write("\x1b[?25h")
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def size(self):
        s = shutil.get_terminal_size((80, 24))
        return max(30, s.columns), max(12, s.lines)

    def write(self, text):
        try:
            self.out.write(text)
            self.out.flush()
        except (OSError, ValueError):
            pass

    def key(self, timeout=None):
        """The next key ('up', 'enter', 'a'...), or None if none in timeout seconds."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        b = os.read(self.fd, 1)
        if not b:
            raise Cancelled()                        # (the terminal's gone)
        if b == b"\x1b":
            seq = b
            while select.select([self.fd], [], [], 0.05)[0]:
                seq += os.read(self.fd, 1)
                if len(seq) >= 3 and (seq[-1:].isalpha() or seq[-1:] == b"~"):
                    break
            s = seq.decode("latin-1")
            return KEYS.get(s, "esc" if s == "\x1b" else "")
        if b[0] >= 0x80:                             # (a letter in UTF-8: the rest of its bytes)
            need = 1 if b[0] < 0xe0 else 2 if b[0] < 0xf0 else 3
            b += os.read(self.fd, need)
        s = b.decode("utf-8", "replace")
        return KEYS.get(s, s)


class Screen:
    """Questions drawn below what's been answered: the one being answered drawn again at each key, then settled
    (just its answer kept)."""

    def __init__(self, term, look):
        self.t, self.l = term, look
        self.drawn = 0
        self.lines = 0                          # (the lines settled so far: going back takes some off again)

    def width(self):
        return self.t.size()[0] - 1

    def draw(self, lines):
        w = self.width()
        out = [f"\x1b[{self.drawn}A\r" if self.drawn else "\r", "\x1b[J"]
        out += [self.l.fit(x, w) + "\n" for x in lines]
        self.t.write("".join(out))
        self.drawn = len(lines)

    def settle(self, lines):
        self.draw(lines)
        self.drawn = 0
        self.lines += len(lines)

    def back_to(self, mark):
        """What's been settled since mark (self.lines then) taken off the screen: a question gone back to is asked
        afresh where it was."""
        n = self.lines - mark
        if n > 0:
            self.draw([])
            self.t.write(f"\x1b[{n}A\r\x1b[J")
            self.lines = mark

    def say(self, *lines):
        self.settle(list(lines))

    # the parts of a question
    def head(self, title):
        return f"{self.l.cyan(self.l.on)}  {self.l.bold(title)}"

    def rail(self, text=""):
        return f"{self.l.cyan(self.l.bar)}  {text}" if text else self.l.cyan(self.l.bar)

    def foot(self, text):
        return f"{self.l.cyan(self.l.end)}  {self.l.dim(text)}"

    def answered(self, title, answer):
        l = self.l
        return [f"{l.green(l.done)}  {title}", f"{l.dim(l.bar)}  {l.dim(answer)}", l.dim(l.bar)]

    def intro(self, title):
        self.say(f"{self.l.dim(self.l.top)}  {self.l.bold(title)}", self.l.dim(self.l.bar))

    def note(self, title, lines, mark=None):
        l = self.l
        w = min(max([visible(x) for x in lines] + [visible(title) + 2, 20]) + 2, self.width() - 6)
        top = f"{mark or l.green(l.done)}  {title} " + l.dim(l.rule * max(2, w + 1 - visible(title)) + l.corner[0])
        rows = [r for x in lines for r in (wrap(x, w) if x else [""])]
        body = [f"{l.dim(l.bar)}  {l.fit(x, w)}{' ' * max(0, w - visible(l.fit(x, w)))}  {l.dim(l.bar)}"
                for x in [""] + rows + [""]]
        bottom = l.dim(l.corner[2] + l.rule * (w + 4) + l.corner[1])
        self.say(top, *body, bottom, l.dim(l.bar))

    def told(self, text, kind="ok"):
        l = self.l
        mark = {"ok": l.green(l.ok), "warn": l.yellow(l.warn), "info": l.dim(l.dot)}[kind]
        words = l.yellow(text) if kind == "warn" else text
        self.say(f"{l.dim(l.bar)}  {mark} {words}")

    def gap(self):
        self.say(self.l.dim(self.l.bar))

    # questions
    def select(self, title, options, default=0, hint=""):
        """One of options [(value, words, what it is)], picked with the arrows (or the first letter of yes and no): its
        value, or BACK for Esc."""
        l, n = self.l, len(options)
        i = max(0, min(default, n - 1))
        letters = {o[1][:1].lower(): k for k, o in enumerate(options) if o[1][:1].lower() in ("y", "n")}
        while True:
            lines = [self.head(title)]
            for k, (_, words, what) in enumerate(options):
                if k == i:
                    lines.append(self.rail(f"{l.green(l.radio[0])} {words}" + (f"  {l.dim(what)}" if what else "")))
                else:
                    lines.append(self.rail(f"{l.dim(l.radio[1])} {l.dim(words)}"))
            lines.append(self.foot(hint or f"{l.arrows} pick {l.dot} Enter: go on {l.dot} Esc: back"))
            self.draw(lines)
            k = self.t.key()
            if k in ("up", "k"):
                i = (i - 1) % n
            elif k in ("down", "j", "tab"):
                i = (i + 1) % n
            elif k == "enter":
                break
            elif k in letters and k not in ("j", "k"):
                i = letters[k]
                break
            elif k == "esc":
                self.draw([])
                return BACK
            elif k in ("ctrl-c", "ctrl-d"):
                raise Cancelled()
        self.settle(self.answered(title, options[i][1]))
        return options[i][0]

    def multi(self, title, items, hint="", total=None, summary=None):
        """Ticks on items [(value, words, what it is, on, group)]: Space ticks or unticks, Enter goes on. The values
        ticked (a set), or BACK. total(ticked): a line under them (how long it all takes); summary(ticked): the
        answer, in a few words, once it's given."""
        l = self.l
        on = {it[0] for it in items if it[3]}
        rows = []                               # (None, group) or (index, None)
        group = None
        for k, it in enumerate(items):
            if it[4] and it[4] != group:
                group = it[4]
                rows.append((None, group))
            rows.append((k, None))
        picks = [r for r, (k, _) in enumerate(rows) if k is not None]
        cur = 0
        col = min(max(visible(it[1]) for it in items) + 2, 34, self.width() // 2)   # (what each is: a column)
        while True:
            room = max(4, self.t.size()[1] - 8)
            at = picks[cur]
            first = max(0, min(at - room // 2, len(rows) - room))
            shown = rows[first:first + room]
            lines = [self.head(title)]
            if first > 0:
                lines.append(self.rail(l.dim(l.more[0] + " more")))
            for k, g in shown:
                if k is None:
                    lines.append(self.rail(l.bold(g)))
                    continue
                value, words, what = items[k][0], items[k][1], items[k][2]
                ticked = value in on
                mark = l.green(l.box[0]) if ticked else l.dim(l.box[1])
                text = words if ticked else l.dim(words)
                pointer = l.cyan(">") if k == rows[at][0] else " "
                pad = " " * max(2, col - visible(words))
                lines.append(self.rail(f"{pointer} {mark} {text}" + (f"{pad}{l.dim(what)}" if what else "")))
            if first + room < len(rows):
                lines.append(self.rail(l.dim(l.more[1] + " more")))
            if total:
                lines.append(self.rail(l.dim(total(on))))
            lines.append(self.foot(hint or f"{l.arrows} move {l.dot} Space: in or out {l.dot} Enter: go on {l.dot} "
                                           "Esc: back"))
            self.draw(lines)
            k = self.t.key()
            if k in ("up", "k"):
                cur = (cur - 1) % len(picks)
            elif k in ("down", "j", "tab"):
                cur = (cur + 1) % len(picks)
            elif k == "space":
                value = items[rows[picks[cur]][0]][0]
                on ^= {value}
            elif k == "enter":
                break
            elif k == "esc":
                self.draw([])
                return BACK
            elif k in ("ctrl-c", "ctrl-d"):
                raise Cancelled()
        ticked = [it[1] for it in items if it[0] in on]
        self.settle(self.answered(title, summary(on) if summary else ", ".join(ticked) if ticked else "None"))
        return on

    def text(self, title, default="", placeholder="", secret=False, hint="", check=None):
        """Words typed in: what was typed (Enter), or BACK (Esc). check(text): None, or why it won't do."""
        l = self.l
        buf, why = default, ""
        while True:
            shown = l.secret * len(buf) if secret else buf
            line = shown + l.cursor + (l.dim(placeholder) if not buf and placeholder else "")
            lines = [self.head(title), self.rail(line)]
            if why:
                lines.append(self.rail(l.yellow(f"{l.warn} {why}")))
            lines.append(self.foot(hint or f"Enter: go on {l.dot} Esc: back"))
            self.draw(lines)
            k = self.t.key()
            if k == "enter":
                why = check(buf) if check else ""
                if not why:
                    break
            elif k == "backspace":
                buf = buf[:-1]
            elif k == "ctrl-u":
                buf = ""
            elif k == "space" and len(buf) < 400:
                buf += " "
                why = ""
            elif k == "esc":
                self.draw([])
                return BACK
            elif k in ("ctrl-c", "ctrl-d"):
                raise Cancelled()
            elif k and len(k) == 1 and k.isprintable() and len(buf) < 400:
                buf += k
                why = ""
        answer = (l.secret * min(len(buf), 12) if secret else buf) or "None"
        self.settle(self.answered(title, answer))
        return buf

    def busy(self, words, job):
        """job() on a thread of its own, with a line that moves meanwhile: what it gave back (what it raised, raised
        here). Esc stops waiting for it: BACK."""
        l, box = self.l, {}

        def run():
            try:
                box["out"] = job()
            except BaseException as ex:          # (raised on this side)
                box["ex"] = ex
        th = threading.Thread(target=run, daemon=True)
        th.start()
        i = 0
        while th.is_alive():
            self.draw([f"{l.cyan(l.spin[i % len(l.spin)])}  {words}  {l.dim('Esc: skip it')}"])
            i += 1
            k = self.t.key(0.12)
            if k == "esc":
                self.draw([])
                return BACK
            if k in ("ctrl-c", "ctrl-d"):
                raise Cancelled()
        self.draw([])
        if "ex" in box:
            raise box["ex"]
        return box.get("out")

    def wait_code(self, title, lines, poll, every, until):
        """A code to type somewhere else (Plex's, Jellyfin's): shown, and poll() asked every few seconds until it says
        yes (True), the code runs out (False), or Esc (None)."""
        l = self.l
        state = {"ok": False, "stop": False}

        def ask():
            while not state["stop"] and time.monotonic() < until:
                try:
                    if poll():
                        state["ok"] = True
                        return
                except Exception:
                    pass                          # (asked again in a moment)
                for _ in range(int(every * 10)):
                    if state["stop"]:
                        return
                    time.sleep(0.1)
        th = threading.Thread(target=ask, daemon=True)
        th.start()
        i = 0
        try:
            while th.is_alive():
                left = max(0, int(until - time.monotonic()))
                frame = [self.head(title)] + [self.rail(x) for x in lines] + [
                    self.rail(f"{l.cyan(l.spin[i % len(l.spin)])} {l.dim(f'Waiting for it ({left // 60}:{left % 60:02d} left)')}"),
                    self.foot("Esc: skip it for now")]
                self.draw(frame)
                i += 1
                k = self.t.key(0.25)
                if k == "esc":
                    self.draw([])
                    return None
                if k in ("ctrl-c", "ctrl-d"):
                    raise Cancelled()
        finally:
            state["stop"] = True
        self.draw([])
        return state["ok"]


# ---- your services: checked as they're added, kept as Settings keeps them ---------------------------------------
SERVICES = [
    ("ha", "Home Assistant", "the TV Remote and Lights"),
    ("pihole", "Pi-hole", "its numbers, in the Home tab"),
    ("ollama", "Ollama", "the Bot's brain, on another computer"),
    ("plex", "Plex", "sign in with a code at plex.tv/link"),
    ("jellyfin", "Jellyfin", "sign in with a Quick Connect code"),
    ("ra", "RetroAchievements", "achievements as you play"),
    ("web", "The web page's password", "it asks for one before it opens"),
]


class Wizard:
    """The questions, one after another (Esc goes back one), and the answers for setup.sh."""

    def __init__(self, screen, machine, mods=None):
        self.s, self.m = screen, machine
        self.mods = dict(mods or {})
        self.gpi, self.case = machine.gpi, machine.case
        if self.gpi == "yes" and not self.case:     # (--gpi: the case this Pi goes in, as setup.sh works it out)
            self.case = "2" if re.search(r"Compute Module 4( |$)", machine.model) else "2w"
        self.mode = ""
        self.parts = set()
        self.autologin = not machine.keep_login
        self.keep_desktop = False
        self.reboot = True
        self.connected = {}                     # {service: what it said}
        self.free = False                       # (Change something: every question asked, whatever the options said)

    # Pietato's own modules (the settings files' ways), with the static folder and you as setup.sh says
    def mod(self, name):
        if name not in self.mods:
            if self.m.static:
                os.environ["PITATO_STATIC"] = self.m.static
            import importlib
            module = importlib.import_module("pitato." + name)
            config = importlib.import_module("pitato.config")
            if self.m.static:
                config.STATIC = os.path.abspath(self.m.static)
            if self.m.home and os.path.isdir(self.m.home):
                config.home_dir = lambda: self.m.home           # (the files yours, as setup.sh's are)
            self.mods[name] = module
        return self.mods[name]

    def setting(self, name, key):
        try:
            cfg = self.mod("config")
            return cfg.read_config([cfg.settings_glob(name)]).get(key, "")
        except Exception:
            return ""

    # ---- the whole of it ----
    def run(self):
        s, l, m = self.s, self.s.l, self.m
        s.intro("Pietato setup")
        what = [x for x in (m.name() if m.model.replace("\0", "").strip() else "", m.os) if x]   # (its model, its OS)
        room = []
        if m.mem:
            room.append(f"{m.mem / 1024:.0f} GB of memory" if m.mem >= 1536 else f"{m.mem} MB of memory")
        if m.free:
            room.append(f"{m.free / 1024:.0f} GB free" + ("" if m.pc else " on its card"))
        s.note("This computer" if m.pc else "This Pi", [f" {l.dot} ".join(x) for x in (what, room) if x])
        steps = [self.ask_case, self.ask_mode, self.ask_parts, self.ask_services, self.ask_restart, self.ask_go]
        asked, i, marks, start = [], 0, {}, s.lines
        while i < len(steps):
            marks[i] = s.lines                   # (where its question went: back to it, and it's asked there again)
            got = steps[i]()
            if got is BACK:
                i = asked.pop() if asked else 0
                s.back_to(marks.get(i, s.lines))
                continue
            if got == "again":                   # (Change something: the questions again, from the top)
                s.back_to(start)
                asked, i, self.free = [], 0, True
                continue
            if got is not SKIP:
                asked.append(i)
            i += 1
        return self.answers()

    def answers(self):
        left_out = [p for p in available(self.m, self.case) if p not in self.parts]
        return {"GPI": self.gpi or "no", "CASE": self.case if self.gpi == "yes" else "", "MODE": self.mode,
                "LEAVE_OUT": " ".join(left_out), "AUTOLOGIN": "yes" if self.autologin else "no",
                "DESKTOP": "keep" if self.keep_desktop else "pietato", "REBOOT": "yes" if self.reboot else "no",
                "CONNECTED": ", ".join(self.connected),
                "MINUTES": str(estimate(self.parts, self.m)), "GO": "yes"}

    # ---- the questions ----
    def ask_case(self):
        m = self.m
        if self.m.gpi or not m.ask_case:
            if not self.gpi:
                self.gpi = "no"
            return SKIP
        name = "GPi Case 2W" if m.ask_case == "2w" else "GPi Case 2"
        opts = [("yes", "Yes", "its screen, sound and power switch"), ("no", "No", "a screen on HDMI")]
        yes = self.gpi == "yes" if self.gpi else m.ask_yes      # (asked again: as you answered it)
        got = self.s.select(f"Is this Pi in a RetroFlag {name}?", opts, default=0 if yes else 1)
        if got is BACK:
            return BACK
        self.gpi, self.case = got, m.ask_case if got == "yes" else ""
        return got

    def everything(self):
        return set(available(self.m, self.case))

    def ask_mode(self):
        m = self.m
        every = self.everything()
        if m.without and not self.free:
            self.mode = "custom"
            self.parts = every - set(m.without.replace(",", " ").split())
            return SKIP
        if m.mode in ("default", "custom") and not self.free:
            self.mode = m.mode
            self.parts = set(every) if m.mode == "default" else every - m.left_out
            return SKIP
        opts = []
        if m.saved:
            out = [p[2] for p in PARTS if p[0] in every and p[0] in m.left_out]
            opts.append(("keep", "Keep it as it is", "left out: " + ", ".join(out) if out else "everything in"))
        opts += [("default", "Default", f"everything this {m.machine} can run, {how_long(estimate(every, m))}"),
                 ("custom", "Custom", "pick what goes in: leave the big builds out to be done sooner")]
        was = [o[0] for o in opts].index(self.mode) if self.mode in [o[0] for o in opts] else 0
        got = self.s.select("How do you want to set it up?", opts, default=was)
        if got is BACK:
            return BACK
        if got == "default":
            self.parts = set(every)
        elif got == "keep" or self.mode != "custom":   # (Custom: as it was to start with; or as you'd picked it)
            self.parts = every - m.left_out
        self.mode = got
        return got

    def ask_parts(self):
        m = self.m
        if self.mode != "custom" or (m.without and not self.free):
            return SKIP
        items = []
        for pid, group, words, what, _ in PARTS:
            if not can_have(pid, m, self.case):
                continue
            mins = minutes(pid, m)
            when = "in already" if already(pid, m) else how_long(mins, about=False) if mins else ""
            items.append((pid, words, f"{when:<11} {what}", pid in self.parts, group))
        start = [("autologin", "Sign in by itself", f"{'':<11} no password at the console", self.autologin,
                  "Start-up")]
        if m.pc and m.desktop:
            start.append(("desktop", "Start in Pietato", f"{'':<11} not the desktop (System > Desktop opens it)",
                          not self.keep_desktop, "Start-up"))
        if m.user in ("", "root"):
            start = start[1:]
        def summary(on):
            out = [words for pid, words, _, _, _ in items if pid not in on]
            return ("Everything" if not out else "All but " + ", ".join(out)) \
                + f", {how_long(estimate(on & set(PART_IDS), m))}"
        got = self.s.multi("What goes in?", items + start, summary=summary,
                           total=lambda on: f"All in all: {how_long(estimate(on & set(PART_IDS), m))}")
        if got is BACK:
            return BACK
        self.parts = {p for p in got if p in PART_IDS}
        if m.user not in ("", "root"):
            self.autologin = "autologin" in got
        if m.pc and m.desktop:
            self.keep_desktop = "desktop" not in got
        return "custom"

    def ask_services(self):
        s, l = self.s, self.s.l
        items = [(key, name, what + (", set up already" if self.is_set(key) else ""), False, "")
                 for key, name, what in SERVICES]
        got = s.multi("Connect any of your services now?", items,
                      hint=f"Space: tick {l.dot} Enter: go on {l.dot} none: add them later in Settings, or on the "
                           "web page")
        if got is BACK:
            return BACK
        for key, name, _ in SERVICES:
            if key not in got:
                continue
            try:
                words = getattr(self, "connect_" + key)()
            except Cancelled:
                raise
            except Exception as ex:                # (a surprise: said, and on to the next)
                s.told(f"Couldn't set up {name}: {ex}", "warn")
                s.gap()
                words = None
            if words:
                self.connected[name] = words
        return "services"

    def ask_restart(self):
        need = " (the case's screen and sound need it)" if self.gpi == "yes" else ""
        opts = [("yes", "Restart it", f"Pietato starts by itself{need}"),
                ("no", "Don't restart", "restart it yourself later: sudo reboot")]
        got = self.s.select("When it's done", opts, default=0 if self.reboot else 1)
        if got is BACK:
            return BACK
        self.reboot = got == "yes"
        return got

    def ask_go(self):
        s, m = self.s, self.m
        every = self.everything()
        out = [p[2] for p in PARTS if p[0] in every and p[0] not in self.parts]
        lines = []
        if self.gpi == "yes":
            lines.append(f"In a GPi Case {'2W' if self.case == '2w' else '2'}: its screen, sound and power switch")
        lines.append({"keep": "As it is", "default": "Default: everything"}.get(self.mode, "Custom")
                     + f", {how_long(estimate(self.parts, m))}")
        if out:
            lines.append("Left out: " + ", ".join(out))
        if self.connected:
            lines.append("Connected: " + ", ".join(self.connected))
        lines.append("Restarts when it's done" if self.reboot else "Doesn't restart when it's done")
        lines.append(f"Leave the {m.machine} on until it says All set")
        s.note("Ready", lines)
        got = s.select("Start setting it up?", [("go", "Yes, start", ""), ("again", "Change something", ""),
                                                ("stop", "Not now", "nothing's changed")])
        if got is BACK:
            return BACK
        if got == "stop":
            raise Cancelled()
        return got

    # ---- the services ----
    def is_set(self, key):
        try:
            if key == "ha":
                return bool(self.setting("homeassistant.txt", "token"))
            if key == "pihole":
                return bool(self.setting("pihole.txt", "address"))
            if key == "ollama":
                return bool(self.setting("bot.txt", "server") and self.setting("bot.txt", "model"))
            if key == "ra":
                return bool(self.setting("retroachievements.txt", "token"))
            if key == "web":
                return bool(self.setting("webui.txt", "password"))
            if key in ("plex", "jellyfin"):
                import json
                mod = self.mod(key)
                with open(mod.PLEX_FILE if key == "plex" else mod.JELLYFIN_FILE) as f:
                    return bool(json.load(f).get("token"))
        except Exception:
            return False
        return False

    def again_or_skip(self, title):
        """After something didn't work: try again (True), or skip it (False)."""
        got = self.s.select(title, [("again", "Try again", ""), ("skip", "Skip it", "add it later in Settings")])
        return got == "again"

    def connect_ha(self):
        s, ha = self.s, self.mod("homeassistant")
        addr = re.sub(r"^https?://", "", self.setting("homeassistant.txt", "url"))
        token = ""
        while True:
            addr = s.text("Home Assistant's address", default=addr, placeholder="homeassistant.local:8123")
            if addr is BACK or not addr.strip():
                return None
            token = s.text("A long-lived access token", secret=True,
                           hint="Home Assistant: your profile > Security > Long-lived access tokens")
            if token is BACK or not token.strip():
                return None
            token, url = token.strip(), ha.ha_typed_url(addr)
            got = s.busy("Checking Home Assistant…", lambda: ha.ha_check(url, token))
            if got is BACK:
                return None
            ok, words = got
            if ok:
                ha.save_ha({"url": url, "token": token})
                s.told(words)
                s.gap()
                return words
            s.told(words, "warn")
            if not self.again_or_skip("Home Assistant"):
                return None

    def connect_pihole(self):
        s, ph = self.s, self.mod("pihole")
        addr = re.sub(r"^https?://", "", self.setting("pihole.txt", "address")) or ph.dns_guess()
        while True:
            addr = s.text("Pi-hole's address", default=addr, placeholder="192.168.1.2")
            if addr is BACK or not addr.strip():
                return None
            url = ph.pihole_url(addr)
            if not url:
                s.told("That isn't an address. Try one like 192.168.1.2:8080", "warn")
                continue
            where = url.split("://", 1)[1]
            tries = ph.pihole_tries(url)
            ports = f" on port {' or '.join(t.rsplit(':', 1)[1] for t in tries)}" if len(tries) > 1 else ""
            p = ph.Pihole()
            try:
                got = s.busy(f"Looking for your Pi-hole at {where}…", lambda: p.find(url))
            except ph.NotPihole:
                got = f"{where} doesn't answer as a Pi-hole{ports}"
            except Exception:
                got = f"Can't reach {where}{ports}"
            if got is BACK:
                return None
            if isinstance(got, str):
                s.told(got, "warn")
                if not self.again_or_skip("Pi-hole"):
                    return None
                continue
            there, version, needs = got
            password = ""
            while needs:
                password = s.text("Its password (or an app password)", secret=True)
                if password is BACK:
                    return None
                try:
                    out = s.busy("Signing in to your Pi-hole…", lambda: p.check(there, password))
                except ph.Denied:
                    out = "Your Pi-hole didn't take that password"
                except ph.TwoFactor:
                    out = "Your Pi-hole wants a two-factor code too: use an app password"
                except ph.Busy:
                    out = "Your Pi-hole has too many signed in: try again in a while"
                except Exception:
                    out = f"Can't reach {where}"
                if out is BACK:
                    return None
                if isinstance(out, str):
                    s.told(out, "warn")
                    if not self.again_or_skip("Pi-hole"):
                        return None
                    continue
                version, sid = out
                if sid:
                    p.sign_out(there, sid)               # (Pi-hole only has so many: Pietato signs in itself)
                break
            ph.save_pihole(there, password)
            words = f"Pi-hole {version} at {there.split('://', 1)[1]}"
            s.told(words)
            s.gap()
            return words

    def connect_ollama(self):
        s, bot, net, cfg = self.s, self.mod("bot"), self.mod("net"), self.mod("config")
        addr = self.setting("bot.txt", "server")
        while True:
            addr = s.text("The computer with Ollama", default=addr, placeholder="192.168.1.20",
                          hint="Ollama there listens on the network with OLLAMA_HOST=0.0.0.0",
                          check=lambda t: None if not t.strip() or net.cam_address(t)
                          else "That isn't an address. Try 192.168.1.20")
            if addr is BACK or not addr.strip():
                return None
            addr = " ".join(addr.split())
            try:
                models = s.busy("Asking Ollama for its models…", lambda: bot.ollama_models(addr))
            except Exception as ex:
                models = str(ex) or "Ollama didn't answer"
            if models is BACK:
                return None
            if isinstance(models, str):
                s.told(models, "warn")
                if not self.again_or_skip("Ollama"):
                    return None
                continue
            model = ""
            if models:
                had = self.setting("bot.txt", "model")
                model = s.select("Which model?", [(x, x, "") for x in models],
                                 default=models.index(had) if had in models else 0)
                if model is BACK:
                    continue
            cfg.edit_config("bot.txt", {"server": addr, "model": model}, head=bot.FRIEND_HEAD, was="friend.txt")
            if model:
                words = f"{model}, on {addr}"
                s.told(words)
            else:
                words = f"Ollama on {addr}"
                s.told(f"{words}: no models on it yet (ollama pull gemma3 there, say)", "warn")
            s.gap()
            return words

    def connect_plex(self):
        s = self.s
        plex = self.mod("plex").Plex()
        while True:
            try:
                got = s.busy("Asking Plex for a code…", plex.start_pin)
            except Exception:
                got = "Can't reach plex.tv"
            if got is BACK:
                return None
            if isinstance(got, str):
                s.told(got, "warn")
                if not self.again_or_skip("Plex"):
                    return None
                continue
            code = plex.pin["code"]
            ok = s.wait_code("Sign in to Plex", [f"Go to  {s.l.bold('plex.tv/link')}  and type  {s.l.bold(code)}"],
                             plex.check_pin, 2, plex.pin["until"])
            if ok is None:
                return None
            if not ok:
                s.told("The code ran out", "warn")
                if not self.again_or_skip("Plex"):
                    return None
                continue
            try:
                found = s.busy("Looking for your Plex server…", plex.find_server)
            except Exception:
                found = False
            words = f"Signed in to Plex: {plex.server_name}" if found is True else "Signed in to Plex"
            s.told(words if found is True else f"{words} (no server found yet: it looks again as it starts)",
                   "ok" if found is True else "info")
            s.gap()
            return words

    def connect_jellyfin(self):
        s = self.s
        jf = self.mod("jellyfin").Jellyfin()
        try:
            found = s.busy("Looking for your Jellyfin server…", jf.find_server)
        except Exception:
            found = False
        if found is BACK:
            return None
        addr = ""
        while not found:
            addr = s.text("Jellyfin's address", default=addr, placeholder="192.168.1.20:8096")
            if addr is BACK or not addr.strip():
                return None
            try:
                found = s.busy(f"Looking at {addr.strip()}…", lambda: jf.use_server(addr))
            except Exception:
                found = False
            if found is BACK:
                return None
            if not found:
                s.told("No Jellyfin server answers there", "warn")
        while True:
            try:
                quick = s.busy(f"Asking {jf.server_name} for a code…",
                               lambda: jf.quick_on() and (jf.start_quick() or True))
            except Exception:
                quick = f"Can't reach {jf.server_name}"
            if quick is BACK:
                return None
            if quick is not True:
                s.told(quick or f"Quick Connect is off on {jf.server_name}: turn it on in its Dashboard (General), "
                       "or sign in later on the Pi", "warn")
                if quick is False or not self.again_or_skip("Jellyfin"):
                    return None
                continue
            ok = s.wait_code(f"Sign in to {jf.server_name}",
                             ["In Jellyfin on your phone or computer: your profile > Quick Connect,",
                              f"and type  {s.l.bold(jf.quick['code'])}"], jf.check_quick, 3, jf.quick["until"])
            if ok is None:
                return None
            if not ok:
                s.told("The code ran out", "warn")
                if not self.again_or_skip("Jellyfin"):
                    return None
                continue
            who = jf.cfg.get("user_name")
            words = f"{jf.server_name}" + (f", as {who}" if who else "")
            s.told(f"Signed in to {words}")
            s.gap()
            return words

    def connect_ra(self):
        s, ra = self.s, self.mod("cheevos")
        user = self.setting("retroachievements.txt", "user")
        while True:
            user = s.text("Your RetroAchievements user name", default=user)
            if user is BACK or not user.strip():
                return None
            password = s.text("Its password", secret=True,
                              hint="Pietato keeps the key it gives for this Pi, not your password")
            if password is BACK or not password:
                return None
            try:
                got = s.busy("Signing in to RetroAchievements…", lambda: ra.ra_login(user.strip(), password))
            except ra.LoginError as ex:
                got = str(ex)
            except OSError:
                got = "Can't reach retroachievements.org"
            if got is BACK:
                return None
            if isinstance(got, str):
                s.told(got, "warn")
                if not self.again_or_skip("RetroAchievements"):
                    return None
                continue
            who, key = got
            ra.ra_save(who, key)
            s.told(f"Signed in as {who}")
            s.gap()
            return who

    def connect_web(self):
        s, cfg = self.s, self.mod("config")
        while True:
            pw = s.text("A password for the web page", secret=True, hint="Blank: none (anyone on your WiFi can open it)")
            if pw is BACK:
                return None
            pw = pw.strip()[:120]
            if pw:
                again = s.text("The same again", secret=True)
                if again is BACK:
                    continue
                if again.strip() != pw:
                    s.told("They're not the same", "warn")
                    continue
            cfg.edit_config("webui.txt", {"password": pw}, head="# The web page: a password if you want it to ask for "
                            "one, and other names you open it by. Keep it private.\n", limit=200, private=True)
            s.told("The web page asks for it" if pw else "No password for the web page", "ok" if pw else "info")
            s.gap()
            return "asks for one" if pw else None


def write_answers(path, answers):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for k, v in answers.items():
            f.write(f"{k}={re.sub(r'[^A-Za-z0-9 ,._:/()-]', '', str(v))}\n")
    os.replace(tmp, path)


def ask(path):
    look = Look()
    machine = Machine()
    with Term() as term:
        screen = Screen(term, look)
        try:
            answers = Wizard(screen, machine).run()
        except Cancelled:
            screen.say(f"{look.red(look.stop)}  Not now: nothing's changed", "")
            write_answers(path, {"GO": "no"})
            return 3
    write_answers(path, answers)
    return 0


# ---- the screen while setup.sh works ------------------------------------------------------------------------------
WARN = re.compile(r"^\((Couldn't|Couldn’t|No )")
SUB_DONE = re.compile(r"^  (\S[^:]*): done \(took ([\d:]+)\)$")


def read_answers(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                k, eq, v = line.rstrip("\n").partition("=")
                if eq:
                    out[k] = v
    except OSError:
        pass
    return out


def clock(secs):
    secs = int(secs)
    return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}" if secs >= 3600 else f"{secs // 60}:{secs % 60:02d}"


class Show:
    """setup.sh's output, as it works, drawn: a line for each step once it's done (and the one under way, moving, with
    how far its build has got), under it anything that didn't go in, and at the end All set (or where it stopped, and
    the last of what it said)."""

    def __init__(self, out, log, look, answers, now=time.monotonic):
        self.out, self.log, self.l, self.a, self.now = out, log, look, answers, now
        self.step = self.hint = ""
        self.t0 = self.start = now()
        self.sub = ""                            # what its build says: Building 41%
        self.spun = 0
        self.live = False                        # the moving line's on the screen
        self.notes = []                          # what didn't go in, said under its step once that's done
        self.tail = []                           # the last of what it said, for where it stopped
        self.final = None                        # All set's lines, once it's said it
        self.stopped = ""
        self.steps = 0

    def width(self):
        return max(30, shutil.get_terminal_size((80, 24)).columns) - 1

    def write(self, text):
        try:
            self.out.write(text)
            self.out.flush()
        except (OSError, ValueError):
            pass

    def line(self, text):                          # a line for good, above the moving one
        self.write(("\r\x1b[K" if self.live else "") + self.l.fit(text, self.width()) + "\n")
        self.live = False

    def wrapped(self, text, style, first=""):
        """text on lines of the screen's width, after the rail (first before its first line, and room for it before
        the rest)."""
        l = self.l
        rest = " " * visible(first)
        room = max(20, self.width() - 6 - visible(first))
        words, row = text.split(), ""
        rows = []
        for w in words:
            if row and len(row) + 1 + len(w) > room:
                rows.append(row)
                row = w
            else:
                row = f"{row} {w}" if row else w
        rows.append(row)
        for k, r in enumerate(rows):
            self.line(f"{l.dim(l.bar)}  {first if k == 0 else rest}{style(r)}")

    def timed(self, mark, label, secs, extra=""):
        """A step's line: its time at the right."""
        l = self.l
        t = clock(secs)
        right = min(self.width(), 76)
        room = right - 4 - len(t) - 2
        while visible(label) > room and label.endswith(")") and " (" in label:   # (its words in brackets go first)
            label = label[:label.rindex(" (")]
        head = l.fit(f"{label}{extra}", room)
        return f"{mark}  {head}{' ' * max(1, room - visible(head))}  {l.dim(t)}"

    def moving(self):
        if not self.step or self.final is not None or self.stopped:
            return
        l = self.l
        mark = l.cyan(l.spin[self.spun % len(l.spin)])
        self.spun += 1
        extra = f"  {l.dim(self.sub)}" if self.sub else (f"  {l.dim(self.hint)}" if self.hint else "")
        self.write("\r\x1b[K" + self.timed(mark, self.step, self.now() - self.t0, extra))
        self.live = True

    def end_step(self, mark=None):
        l = self.l
        if self.step:
            self.line(self.timed(mark or l.green(l.done), self.step, self.now() - self.t0))
        for note in self.notes:
            self.wrapped(note, l.yellow, first=l.yellow(l.warn) + " ")
        self.notes = []
        self.step = self.hint = self.sub = ""

    def take(self, raw):
        """A line of setup.sh's."""
        l = self.l
        text = raw.rstrip("\r")
        if text.startswith("@@"):                  # (setup.sh to this, not for the log: how far a build's got)
            if text.startswith("@@working "):
                what, _, pct = text[10:].partition("|")
                self.sub = what + (f" {pct}%" if pct.strip().isdigit() else "")
            return
        self.log_line(text)
        if self.final is not None:
            if text.strip():
                self.final.append(text.strip())
            return
        if text.startswith("==> "):
            self.end_step()
            if not self.steps:
                self.line(l.dim(l.bar))
            label = text[4:].strip()
            self.step, _, self.hint = label.partition(": ")
            self.t0 = self.now()
            self.tail = []                       # (where it stops: what this step said)
            self.steps += 1
            self.moving()
        elif text.startswith("All set"):
            self.end_step()
            self.final = [text.strip()]
        elif text.startswith("setup.sh stopped before it was done"):
            self.stopped = text.strip()
        elif SUB_DONE.match(text):
            self.sub = ""
        elif WARN.match(text):
            note = text.strip()[1:]
            self.notes.append(note[:-1] if note.endswith(")") else note)
            if not self.step:
                self.end_step()
        elif not self.steps and text.strip():   # (what it says before the first step: what it's setting up for)
            self.wrapped(text.strip(), l.dim)
        if text.strip() and not text.startswith("==> "):      # (its steps: drawn already)
            self.tail = (self.tail + [text.strip()])[-12:]

    def log_line(self, text):
        try:
            self.log.write(text + "\n")
            self.log.flush()
        except (OSError, ValueError):
            pass

    def finish(self, log_path):
        l = self.l
        took = clock(self.now() - self.start)
        if self.final is not None:
            self.end_step()
            title = self.final[0]
            lines = list(self.final[1:]) + ["", f"It took {took}. All it did is in {log_path}"]
            self.line(l.dim(l.bar))
            w = max(20, min(max([visible(x) for x in lines] + [visible(title) + 4]) + 2, self.width() - 6))
            self.line(f"{l.green(l.done)}  {title} " + l.dim(l.rule * max(2, w + 1 - visible(title)) + l.corner[0]))
            for x in [""] + [r for x in lines for r in (wrap(x, w) if x else [""])] + [""]:
                x = l.fit(x, w)
                self.line(f"{l.dim(l.bar)}  {x}{' ' * max(0, w - visible(x))}  {l.dim(l.bar)}")
            self.line(l.dim(l.corner[2] + l.rule * (w + 4) + l.corner[1]))
            if self.a.get("REBOOT") == "yes":
                self.line(f"{l.dim(l.end)}  Restarting now…")
            elif self.a.get("GPI") == "yes":
                self.line(f"{l.dim(l.end)}  Restart when you're ready (sudo reboot): the case's screen and sound need it")
            else:
                self.line(f"{l.dim(l.end)}  Pietato's starting. Restart when you're ready: sudo reboot")
            return
        self.end_step(l.red(l.stop))
        self.line(l.dim(l.bar))
        for x in self.tail[-10:]:
            if x != self.stopped:
                self.line(f"{l.dim(l.bar)}  {l.dim(x)}")
        self.line(l.dim(l.bar))
        self.line(f"{l.red(l.end)}  {self.stopped or 'setup.sh stopped before it was done.'}")
        self.line(f"   All it did is in {log_path}")


def drain(q):
    """Whatever else has come, at once."""
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def show(log_path, answers_path=""):
    signal.signal(signal.SIGINT, signal.SIG_IGN)   # (Ctrl+C stops setup.sh, which says so: this shows it)
    look = Look()
    answers = read_answers(answers_path) if answers_path else {}
    lines = queue.Queue()

    def read():
        buf = b""
        fd = sys.stdin.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"\r?\n|\r", buf)
            buf = parts.pop()
            for p in parts:
                lines.put(p.decode("utf-8", "replace"))
        if buf:
            lines.put(buf.decode("utf-8", "replace"))
        lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    try:
        log = open(log_path, "a", encoding="utf-8", errors="replace")
    except OSError:
        log = open(os.devnull, "w")
    s = Show(sys.stdout, log, look, answers)
    s.write("\x1b[?25l")
    try:
        while True:                               # (read to the end whatever happens: setup.sh writes to this)
            try:
                got = [lines.get(timeout=0.15)] + drain(lines)
            except queue.Empty:
                got = []
            ended = False
            for line in got:
                if line is None or line == "@@end":   # (setup.sh's done with it: what it's running may not be)
                    ended = True
                    break
                try:
                    s.take(line)
                except Exception:
                    s.log_line(line)
            if ended:
                break
            try:
                s.moving()
            except Exception:
                pass
        s.finish(log_path)
    finally:
        s.write("\x1b[?25h")
        log.close()
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "ask":
        return ask(argv[2])
    if len(argv) >= 3 and argv[1] == "show":
        return show(argv[2], argv[3] if len(argv) > 3 else "")
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.exit(130)
