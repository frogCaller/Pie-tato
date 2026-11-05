"""setup.sh's own screen (pitato/wizard.py): its questions, and the screen while it works.

What each machine can have and how long it all takes (a Pi Zero 2, a Pi 4 on 64 and 32 bits, a Pi 5, a PC, the first
Pis), as setup.sh has its parts. The questions, keys in and the screen out, on a pretend terminal: Default; Custom (the
PlayStation in already, the PSP left out); as it was before; Esc back (what was answered after it gone from the
screen); Change something; Not now and Ctrl+C; the GPi Case; a PC's desktop; --login's; a short terminal. Your
services, each against a pretend one, the ways they go wrong too: Home Assistant (a wrong token; Esc while it's
checked), Pi-hole (a wrong password, signed out after; something else there), Ollama (not an address; nothing there;
its models), Plex (a code; Esc while it waits), Jellyfin (found on the network; typed; Quick Connect off),
RetroAchievements (a wrong password), the web page's password (not the same twice; none): each kept as Settings keeps
it, yours only, and none of it on the screen. Python's own library only (it runs before setup.sh has put anything
in). wizard.py ask on a real terminal (a pty), and Ctrl+C there, plain letters on the Pi's console; the screen while
setup.sh works, from its lines, and wizard.py show on a pipe. setup.sh: what's left out (setup.conf, --default,
--without, an image) and its options. Then the real setup.sh on a pretend terminal (setupspin/full/inner.sh): Custom
without the PlayStation, Home Assistant and the web page's password connected (its own screen and no build output on
it, no PCSX ReARMed and no ps1 folder, kept in setup.conf, the files yours); Not now (nothing changed); Ctrl+C
mid-build; --update after (what was left out stays out); --plain (the old way, on a terminal too)."""
import fcntl, importlib, json, os, pty, re, select, shutil, signal, stat, struct, subprocess, sys, termios
import threading, time, types, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT  # noqa: E402  (this test's folder of work; the Pietato folder)

ROOT = os.environ.get("PITATO_ROOT", ROOT)
S = SP + "/twizard"
shutil.rmtree(S, ignore_errors=True)
HOME, STATIC, CORES, PROGS = S + "/home/sam", S + "/pietato/static", S + "/cores", S + "/progs"
for d in (HOME, STATIC, CORES, PROGS, S + "/var1", S + "/var2", S + "/static2", S + "/cores-ps1"):
    os.makedirs(d)
open(S + "/cores-ps1/pcsx_rearmed_libretro.so", "w").close()     # (the PlayStation's emulator built before)
os.environ["PITATO_STATIC"] = STATIC               # (nothing of the Pietato folder's own static folder touched)
os.environ.pop("PITATO_RA_HOST", None)
os.environ["COLUMNS"], os.environ["LINES"] = "100", "40"
sys.path.insert(0, ROOT)
from pitato import wizard as W  # noqa: E402

ok_all = []
ONLY = sys.argv[1:]


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


def screen(text):
    """What a terminal shows at the end of text: just enough of one (lines, \\r, up, clear to the end and the line),
    as tall as it needs to be."""
    lines, row, col, i = [""], 0, 0, 0
    while i < len(text):
        m = CSI.match(text, i)
        if m:
            arg, c = m.group(1), m.group(2)
            if c == "A":
                row = max(0, row - int(arg or 1))
            elif c == "J":
                lines[row] = lines[row][:col]
                del lines[row + 1:]
            elif c == "K":
                lines[row] = lines[row][:col]
            i = m.end()
            continue
        if text[i] == "\x1b":                      # (another escape: \x1b7 and the like)
            i += 2
            continue
        ch = text[i]
        if ch == "\n":
            row, col = row + 1, 0
            while row >= len(lines):
                lines.append("")
        elif ch == "\r":
            col = 0
        elif ch >= " ":
            line = lines[row].ljust(col)
            lines[row] = line[:col] + ch + line[col + 1:]
            col += 1
        i += 1
    return "\n".join(x.rstrip() for x in lines).rstrip("\n")


def sq(text):
    """text with each run of spaces as one (what's lined up in columns, read as words)."""
    return re.sub(r" {2,}", " ", text)


class ScriptTerm:
    """A pretend terminal: keys from a list, what's written kept. ("snap", key): the screen noted, then key.
    ("~", key, words): a key typed while something's being waited for, once words are on the screen ("snap" for
    the key: the screen noted)."""

    def __init__(self, keys, cols=100, rows=40):
        self.keys, self.cols, self.rows, self.out, self.snaps = list(keys), cols, rows, [], []

    def size(self):
        return self.cols, self.rows

    def write(self, text):
        self.out.append(text)

    def text(self):
        return "".join(self.out)

    def key(self, timeout=None):
        k = self.keys[0] if self.keys else None
        if timeout is not None:
            if isinstance(k, tuple) and k[0] == "~" and k[2] in screen(self.text()[-6000:]):
                self.keys.pop(0)
                if k[1] == "snap":
                    self.snaps.append(screen(self.text()))
                    return None
                return k[1]
            time.sleep(min(timeout, 0.02))
            return None
        if k is None:
            raise RuntimeError("out of keys at:\n" + screen(self.text())[-1500:])
        if isinstance(k, tuple) and k[0] == "~":
            raise RuntimeError(f"{k} came when nothing was being waited for:\n" + screen(self.text())[-1500:])
        self.keys.pop(0)
        if isinstance(k, tuple):
            self.snaps.append(screen(self.text()))
            k = k[1]
        return k


def typed(text):
    return ["space" if c == " " else c for c in text]


def machine(env):
    return W.Machine({"PIETATO_W_" + k: v for k, v in env.items()})


def wizard(env, keys, cols=100, rows=40):
    """The questions, with these keys: (the answers, or "cancelled"; the screen at the end; the terminal)."""
    t = ScriptTerm(keys, cols, rows)
    try:
        got = W.Wizard(W.Screen(t, W.Look(fancy=True, colour=False)), machine(env)).run()
    except W.Cancelled:
        got = "cancelled"
    return got, screen(t.text()), t


def order(env, case=None):
    m = machine(env)
    return (W.available(m, case) + (["autologin"] if m.user not in ("", "root") else [])
            + (["desktop"] if m.pc and m.desktop else []))


def moves(items, *values):
    """The keys to each of values in a list of items, Space on each."""
    keys, at = [], 0
    for v in values:
        k = items.index(v)
        keys += ["down"] * (k - at) if k >= at else ["up"] * (at - k)
        keys.append("space")
        at = k
    return keys


SERVICE_KEYS = [s[0] for s in W.SERVICES]
WHICH = {}                                         # (the programs this machine has, as the wizard sees it)
GLOB = []
W.shutil = types.SimpleNamespace(which=lambda name, *a, **k: WHICH.get(name),
                                 get_terminal_size=shutil.get_terminal_size)
W.glob = types.SimpleNamespace(glob=lambda pattern: [g for g in GLOB if "mgba" in pattern])

BASE_ENV = {"OS": "Debian GNU/Linux 12 (bookworm)", "USER": "sam", "HOME": HOME, "STATIC": STATIC, "CORES": CORES,
            "PROGS": PROGS, "MACHINE": "Pi", "MEM": "3796", "FREE": "24000"}
PI4 = dict(BASE_ENV, MODEL="Raspberry Pi 4 Model B Rev 1.5", BIG="yes", ARCH="arm64")
PI4_32 = dict(PI4, ARCH="armhf")
PI5 = dict(BASE_ENV, MODEL="Raspberry Pi 5 Model B Rev 1.0", BIG="yes", ARCH="arm64", MEM="8052")
ZERO2 = dict(BASE_ENV, MODEL="Raspberry Pi Zero 2 W Rev 1.0", BIG="no", ARCH="arm64", MEM="427", FREE="12000")
PI1 = dict(BASE_ENV, MODEL="Raspberry Pi Model B Rev 2", BIG="no", ARCH="armhf", NEO_OLD="yes", MEM="430")
CM4 = dict(BASE_ENV, MODEL="Raspberry Pi Compute Module 4 Rev 1.1", BIG="yes", ARCH="arm64")
PC = dict(BASE_ENV, MODEL="", PC="yes", BIG="yes", ARCH="amd64", MACHINE="computer", OS="Ubuntu 24.04.1 LTS",
          MEM="15890", FREE="204800", DESKTOP="yes")
PI4_PARTS = ["classic", "ps1", "n64", "psp", "nds", "dc", "neogeo", "ngp", "link", "cheevos", "chromium", "office",
             "toys", "computers"]
SMALL_PARTS = ["classic", "ps1", "neogeo", "ngp", "link", "cheevos", "office", "toys", "computers"]

# ---- what each machine can have, and how long it all takes ----
if not ONLY or "logic" in ONLY:
    setup = open(ROOT + "/setup.sh").read()
    check("setup.sh's parts are the wizard's, in its order",
          re.search(r'^PARTS="([^"]*)"', setup, re.M).group(1).split() == W.PART_IDS)
    av = {name: W.available(machine(env)) for name, env in (("Pi 4", PI4), ("Pi 4, 32-bit", PI4_32), ("Pi 5", PI5),
                                                             ("Zero 2", ZERO2), ("Pi 1", PI1), ("PC", PC))}
    check(f"a Pi 4 or 5: every emulator but the PC's, Chromium too ({av['Pi 4']})",
          av["Pi 4"] == PI4_PARTS and av["Pi 5"] == PI4_PARTS)
    check(f"...a Pi 4 on 32 bits: no DS ({av['Pi 4, 32-bit']})",
          av["Pi 4, 32-bit"] == [p for p in PI4_PARTS if p != "nds"])
    check(f"a Pi Zero 2: no N64, PSP, DS, Dreamcast or Chromium ({av['Zero 2']})", av["Zero 2"] == SMALL_PARTS)
    check(f"the first Pis: no Neo Geo either ({av['Pi 1']})", av["Pi 1"] == [p for p in SMALL_PARTS if p != "neogeo"])
    check(f"a PC: all of them, the PlayStation 2, GameCube and Wii too ({av['PC']})", av["PC"] == W.PART_IDS)
    check("a GPi Case 2W: no Chromium; the GPi Case 2 (a CM4): Chromium",
          not W.can_have("chromium", machine(PI4), "2w") and W.can_have("chromium", machine(CM4), "2"))
    gates = ['if [ "$BIG" = yes ] && ! wanted n64; then', 'if [ "$BIG" = yes ] && ! wanted psp; then',
             'if [ "$BIG" = yes ] && ! wanted dc; then',
             'if [ "$BIG" = yes ] && [ "$CASE" != 2w ] && ! wanted chromium; then',
             'arm64|aarch64|amd64|x86_64)\n      if ! wanted nds; then', 'if [ "$PC" = yes ]; then\n  if ! wanted gc; then',
             'if [ "${NEO_OLD:-no}" = yes ] && [ "$IMAGE" != yes ]; then',
             '  echo "(Neo Geo games need a Pi 2 or newer: no Neo Geo emulator on this one.)"\nelif ! wanted neogeo; then']
    check(f"...as setup.sh puts them in ({[g for g in gates if g not in setup]})", all(g in setup for g in gates))
    est = {name: W.how_long(W.estimate(W.available(machine(env)), machine(env)))
           for name, env in (("Pi 4", PI4), ("Pi 4, 32-bit", PI4_32), ("Pi 5", PI5), ("Zero 2", ZERO2), ("Pi 1", PI1),
                             ("PC", PC), ("CM4", CM4))}
    check(f"everything, as long as it takes ({est})",
          est == {"Pi 4": "about 2 h 30 min", "Pi 4, 32-bit": "about 2 h 20 min", "Pi 5": "about 1 h 10 min",
                  "Zero 2": "about 1 h 30 min", "Pi 1": "about 1 h", "PC": "about 1 h 15 min",
                  "CM4": "about 2 h 30 min"})
    m4 = machine(PI4)
    check(f"...the PSP's build the most of it on a Pi 4, the PlayStation's {W.minutes('ps1', m4)} min",
          max(PI4_PARTS, key=lambda p: W.minutes(p, m4)) == "psp" and W.minutes("ps1", m4) == 5
          and W.estimate([], m4) == 6)
    m_in = machine(dict(PI4, CORES=S + "/cores-ps1"))
    seen = [p for p in W.PART_IDS if W.already(p, m_in)]
    WHICH.update(soffice="/usr/bin/soffice", chromium="/usr/bin/chromium")
    GLOB.append("/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so")
    seen2 = [p for p in W.PART_IDS if W.already(p, m_in)]
    open(PROGS + "/cacafire", "w").close()
    WHICH.update(cmatrix="/usr/bin/cmatrix", sshfs="/usr/bin/sshfs")
    seen3 = [p for p in W.PART_IDS if W.already(p, m_in)]
    WHICH["mount.cifs"] = "/sbin/mount.cifs"
    open(PROGS + "/librcheevos.so", "w").close()
    seen4 = [p for p in W.PART_IDS if W.already(p, m_in)]
    check(f"what's in already takes no time: the PlayStation's emulator built before ({seen}), LibreOffice, Chromium "
          f"and the ready-made ones installed ({seen2}), the toys ({seen3}), the rest ({seen4})",
          seen == ["ps1"] and seen2 == ["classic", "ps1", "chromium", "office"]
          and seen3 == ["classic", "ps1", "chromium", "office", "toys"]
          and seen4 == ["classic", "ps1", "cheevos", "chromium", "office", "toys", "computers"]
          and W.minutes("ps1", m_in) == 0)
    WHICH.clear()
    GLOB.clear()
    for f in ("cacafire", "librcheevos.so"):
        os.remove(PROGS + "/" + f)
    words = [W.how_long(n) for n in (0, 1, 59, 60, 62, 88, 118, 152)] + [W.how_long(20, about=False),
                                                                          W.how_long(75, about=False)]
    check(f"how long, in words ({words})",
          words == ["about 1 min", "about 1 min", "about 59 min", "about 1 h", "about 1 h", "about 1 h 30 min",
                    "about 2 h", "about 2 h 30 min", "20 min", "1 h 15 min"])
    check(f"...and a step's time ({[W.clock(n) for n in (5, 185, 3725)]})",
          [W.clock(n) for n in (5, 185, 3725)] == ["0:05", "3:05", "1:02:05"])
    green = W.Look(fancy=True, colour=True).green("x" * 10)
    check(f"colours: kept as it's cut to fit ({W.cut(green, 5)!r}), and not counted ({W.visible(green)})",
          W.visible(green) == 10 and W.visible(W.cut(green, 5)) == 5 and W.cut(green, 5).endswith("\x1b[0m")
          and W.cut("abcdef", 4) == "abc…" and W.cut("abc", 4) == "abc" and W.wrap("aa bb cc", 5) == ["aa bb", "cc"])
    check("...and on the Pi's console, cut with dots it has",
          W.Look(fancy=False, colour=False).fit("x" * 30, 10) == "xxxxxxx..."
          and W.Look(fancy=False, colour=False).fit("Checking…", 20) == "Checking..."
          and W.Look(fancy=True, colour=False).fit("x" * 30, 10) == "xxxxxxxxx…")

    class Stream:
        def __init__(self, encoding):
            self.encoding = encoding

    looks, was_term = {}, os.environ.get("TERM")
    for term, enc, no_colour in (("xterm-256color", "utf-8", ""), ("linux", "utf-8", ""), ("xterm", "ascii", ""),
                                 ("xterm", "utf-8", "1")):
        os.environ["TERM"], os.environ["NO_COLOR"] = term, no_colour
        if not no_colour:
            os.environ.pop("NO_COLOR")
        lk = W.Look(stream=Stream(enc))
        looks[(term, enc, no_colour)] = (lk.fancy, lk.colour)
    os.environ.pop("NO_COLOR", None)
    if was_term is None:
        os.environ.pop("TERM", None)
    else:
        os.environ["TERM"] = was_term
    plain = W.Look(fancy=False, colour=False)
    check(f"its shapes on a terminal that has them, plain letters on the Pi's console and in ASCII, no colours with "
          f"NO_COLOR ({looks})", list(looks.values()) == [(True, True), (False, True), (False, True), (True, False)]
          and (plain.radio, plain.box, plain.arrows, plain.on, plain.done) == (("(*)", "( )"), ("[x]", "[ ]"),
                                                                                  "Up/Down", "*", "o"))
    ans = S + "/answers"
    W.write_answers(ans, {"GO": "yes", "LEAVE_OUT": "ps1; rm -rf /", "X": "a=b$(c)`d`"})
    back = W.read_answers(ans)
    check(f"the answers for setup.sh: letters, numbers and a few marks only ({back})",
          back == {"GO": "yes", "LEAVE_OUT": "ps1 rm -rf /", "X": "ab(c)d"} and not os.path.exists(ans + ".tmp"))

# ---- the questions ----
if not ONLY or "questions" in ONLY:
    got, sc, t = wizard(PI4, [("snap", "enter"), "enter", "enter", ("snap", "enter")])
    check(f"Default: everything, and restart when it's done ({got})", got != "cancelled" and got == {
        "GPI": "no", "CASE": "", "MODE": "default", "LEAVE_OUT": "", "AUTOLOGIN": "yes", "DESKTOP": "pietato",
        "REBOOT": "yes", "CONNECTED": "", "MINUTES": "152", "GO": "yes"} and not t.keys)
    check("...it starts with what this Pi is",
          sc.startswith("┌  Pietato setup\n│\n◇  This Pi ─") and "│  Raspberry Pi 4 Model B · Debian GNU/Linux 12 "
          "(bookworm)" in sc and "│  4 GB of memory · 23 GB free on its card" in sc)
    first = t.snaps[0]
    check("...Default or Custom: what each is, and how long Default takes",
          "◆  How do you want to set it up?\n│  ● Default  everything this Pi can run, about 2 h 30 min\n│  ○ Custom\n"
          "└  ↑↓ pick · Enter: go on · Esc: back" in first)
    check("...answered, a question's just its answer",
          "◇  How do you want to set it up?\n│  Default\n│\n◇  Connect any of your services now?\n│  None\n│\n"
          "◇  When it's done\n│  Restart it\n│\n◇  Ready" in sc)
    check("...ready: what it'll do, before it does it",
          all(x in t.snaps[1] for x in ("│  Default: everything, about 2 h 30 min", "│  Restarts when it's done",
                                         "│  Leave the Pi on until it says All set", "◆  Start setting it up?",
                                         "│  ● Yes, start", "│  ○ Change something", "│  ○ Not now"))
          and "Left out" not in t.snaps[1] and sc.endswith("◇  Start setting it up?\n│  Yes, start\n│"))

    env = dict(PI4, CORES=S + "/cores-ps1")
    items = order(env)
    got, sc, t = wizard(env, ["down", "enter", *moves(items, "psp"), ("snap", "enter"), "enter", "down", "enter",
                              "enter"])
    rest = W.estimate([p for p in PI4_PARTS if p != "psp"], machine(env))
    check(f"Custom: the PSP left out ({got['LEAVE_OUT']}, {got['MINUTES']} min), and no restart",
          got["MODE"] == "custom" and got["LEAVE_OUT"] == "psp" and got["REBOOT"] == "no"
          and got["MINUTES"] == str(rest) == "87")
    lst = sq(t.snaps[0])
    check("...what goes in: each part, how long it takes (the PlayStation's emulator in already), in groups",
          all(x in lst for x in ("◆ What goes in?", "│ Games\n", "│ ◼ Game Boy, NES, SNES, Genesis 1 min ready-made, "
                                 "no build\n", "│ ◼ PlayStation in already built here\n",
                                 "│ > ◻ PSP 1 h built here\n", "│ Extras\n",
                                 "│ ◼ Chromium 6 min the whole web in Web: 300 MB\n", "│ Start-up\n",
                                 "│ ◼ Sign in by itself no password at the console\n",
                                 "│ All in all: about 1 h 25 min\n", "Space: in or out")))
    check("...not what a Pi can't run", "PlayStation 2" not in lst and "GameCube" not in lst)
    check("...answered: what's left out and how long the rest takes",
          "◇  What goes in?\n│  All but PSP, about 1 h 25 min\n" in sc and "│  Custom, about 1 h 25 min" in sc
          and "│  Left out: PSP" in sc and "│  Doesn't restart when it's done" in sc)

    saved = dict(PI4, SAVED="yes", LEAVE_OUT="ps1 n64")
    got, sc, t = wizard(saved, [("snap", "enter"), "enter", "enter", "enter"])
    check(f"set up before: as it was, to start with ({got['MODE']}, {got['LEAVE_OUT']})",
          got["MODE"] == "keep" and got["LEAVE_OUT"] == "ps1 n64"
          and "│  ● Keep it as it is  left out: PlayStation, N64\n│  ○ Default\n│  ○ Custom" in t.snaps[0]
          and "│  As it is, about " in sc and "│  Left out: PlayStation, N64" in sc)
    items = order(saved)
    got, sc, t = wizard(saved, ["down", "down", "enter", *moves(items, "n64"), ("snap", "enter"), "enter", "enter",
                                "enter"])
    check(f"...Custom: what was left out, out to start with; the N64 back in ({got['LEAVE_OUT']})",
          got["MODE"] == "custom" and got["LEAVE_OUT"] == "ps1" and "│    ◻ PlayStation" in t.snaps[0]
          and "│  > ◼ N64" in t.snaps[0])

    got, sc, t = wizard(PI4, ["down", "enter", ("snap", "esc"), ("snap", "up"), "enter", "enter", "enter", "enter"])
    check(f"Esc: back a question, what was answered since gone from the screen ({got['MODE']})",
          got["MODE"] == "default" and "◆  What goes in?" in t.snaps[0] and "◇  What goes in?" not in t.snaps[1]
          and "│  Custom" not in t.snaps[1] and "◆  How do you want to set it up?\n│  ○ Default\n│  ● Custom" in t.snaps[1]
          and sc.count("How do you want to set it up?") == 1 and "What goes in?" not in sc and not t.keys)
    got, sc, t = wizard(PI4, ["enter", "esc", "down", "enter", "enter", "enter", "esc", "enter", "enter", "esc",
                              "down", "enter", "enter"])
    check(f"...from each of them, back and forth ({got['MODE']}, {got['REBOOT']})",
          got["MODE"] == "custom" and got["REBOOT"] == "no" and not t.keys
          and [sc.count(q) for q in ("How do you want to set it up?", "What goes in?", "Connect any of your services",
                                     "When it's done", "◇  Ready", "Start setting it up?")] == [1] * 6)
    got, sc, t = wizard(PI4, ["esc", "enter", "enter", "enter", "enter"])
    check(f"...Esc at the first question: it stays there ({got['MODE']})",
          got["MODE"] == "default" and sc.count("How do you want to set it up?") == 1)

    items = order(PI4)
    got, sc, t = wizard(PI4, ["enter", "enter", "enter", "down", ("snap", "enter"), "down", "enter",
                              *moves(items, "ngp"), "enter", "enter", "enter", "enter"])
    check(f"Change something: the questions again from the top, what was answered taken off ({got['MODE']}, "
          f"{got['LEAVE_OUT']})", got["MODE"] == "custom" and got["LEAVE_OUT"] == "ngp" and not t.keys
          and "◇  Ready" in t.snaps[0] and sc.count("◇  Ready") == 1 and sc.count("How do you want to set it up?") == 1
          and sc.count("◇  This Pi") == 1)
    got, sc, t = wizard(dict(PI4, WITHOUT="ps1"), ["enter", "enter", ("snap", "down"), "enter", ("snap", "enter"),
                                                   ("snap", "enter"), "enter", "enter", "enter"])
    check(f"--without: no question about what goes in, until Change something ({got['LEAVE_OUT']})",
          got["MODE"] == "custom" and got["LEAVE_OUT"] == "ps1" and "How do you want" not in t.snaps[0]
          and "What goes in" not in t.snaps[0] and "│  Left out: PlayStation" in t.snaps[0]
          and "│  ○ Default\n│  ● Custom" in t.snaps[1] and "│  > ◼ Game Boy" in t.snaps[2]
          and "│    ◻ PlayStation" in t.snaps[2])
    got, sc, t = wizard(dict(PI4, MODE="custom", SAVED="yes", LEAVE_OUT="dc"), [("snap", "enter"), "enter", "enter",
                                                                              "enter"])
    check(f"--custom: straight to what goes in, as it was ({got['LEAVE_OUT']})",
          got["LEAVE_OUT"] == "dc" and "How do you want" not in sc and "│    ◻ Dreamcast" in t.snaps[0])
    got, sc, t = wizard(dict(PI4, MODE="default"), ["enter", "enter", "enter"])
    check(f"--default: no question about it ({got['MODE']}, {got['LEAVE_OUT']!r})",
          got["MODE"] == "default" and got["LEAVE_OUT"] == "" and "How do you want" not in sc)

    got, sc, t = wizard(PI4, ["enter", "enter", "enter", "down", "down", "enter"])
    check(f"Not now: nothing's changed ({got})", got == "cancelled" and not t.keys)
    got, sc, t = wizard(PI4, ["down", "ctrl-c"])
    check(f"...Ctrl+C at a question, the same ({got})", got == "cancelled")
    got, sc, t = wizard(PI4, ["enter", "enter", "enter", "n"])
    check(f"...or N for Not now ({got})", got == "cancelled")

    zero = dict(ZERO2, ASK_CASE="2w")
    got, sc, t = wizard(zero, [("snap", "enter"), "enter", "enter", ("snap", "enter"), "enter"])
    check(f"a Pi Zero 2: in a GPi Case 2W? Yes to start with ({got['GPI']}, {got['CASE']})",
          got["GPI"] == "yes" and got["CASE"] == "2w" and "◆  Is this Pi in a RetroFlag GPi Case 2W?\n│  ● Yes  its "
          "screen, sound and power switch\n│  ○ No" in t.snaps[0])
    check("...restarting: the case's screen and sound need it; ready: in the case",
          "│  ● Restart it  Pietato starts by itself (the case's screen and sound need it)" in t.snaps[1]
          and "│  In a GPi Case 2W: its screen, sound and power switch" in sc
          and "about 1 h 30 min" in sc and got["MINUTES"] == "90")
    cm4 = dict(CM4, ASK_CASE="2", ASK_YES="no")
    got, sc, t = wizard(cm4, ["enter", "esc", ("snap", "up"), "enter", "enter", "enter", "enter", "enter"])
    check(f"a Compute Module 4: in a GPi Case 2? No to start with; back to it, as answered; then yes ({got['GPI']}, "
          f"{got['CASE']}, {got['LEAVE_OUT']!r})", got["GPI"] == "yes" and got["CASE"] == "2"
          and "│  ○ Yes\n│  ● No" in t.snaps[0] and sc.count("Is this Pi in a RetroFlag GPi Case 2?") == 1
          and got["LEAVE_OUT"] == "" and "In a GPi Case 2: its screen" in sc)
    got, sc, t = wizard(dict(PI4, GPI="no", ASK_CASE="2w"), ["enter", "enter", "enter", "enter"])
    check(f"--no-gpi: no question about it ({got['GPI']})", got["GPI"] == "no" and "GPi Case" not in sc)
    got, sc, t = wizard(dict(ZERO2, GPI="yes"), ["enter", "enter", "enter", "enter"])
    got2, sc2, t2 = wizard(dict(CM4, GPI="yes"), ["enter", "enter", "enter", "enter"])
    check(f"--gpi: no question, the case as setup.sh works it out ({got['CASE']}, {got2['CASE']})",
          (got["GPI"], got["CASE"], got2["GPI"], got2["CASE"]) == ("yes", "2w", "yes", "2")
          and "In a GPi Case 2W:" in sc and "In a GPi Case 2:" in sc2 and "Is this Pi" not in sc + sc2)

    items = order(PC)
    got, sc, t = wizard(PC, ["down", "enter", *moves(items, "desktop"), ("snap", "enter"), "enter", "enter", "enter"])
    check(f"a PC: This computer; Start in Pietato, or its desktop ({got['DESKTOP']}, {got['AUTOLOGIN']})",
          got["DESKTOP"] == "keep" and got["AUTOLOGIN"] == "yes" and got["LEAVE_OUT"] == ""
          and "◇  This computer ─" in sc and "│  Ubuntu 24.04.1 LTS" in sc and "│  16 GB of memory · 200 GB free  " in sc
          and all(x in t.snaps[0] for x in ("│    ◼ PlayStation 2", "│    ◼ GameCube and Wii", "│  > ◻ Start in Pietato",
                                            "not the desktop (System > Desktop opens it)")))
    got, sc, t = wizard(PC, ["down", "enter", ("snap", "enter"), "enter", "enter", "enter"], rows=16)
    tall = t.snaps[0]
    got2, sc2, t2 = wizard(PC, ["down", "enter", *["down"] * 17, ("snap", "enter"), "enter", "enter", "enter"],
                           rows=16)
    check("...a short terminal: as much of the list as fits, and where the rest is",
          "│  ↓ more" in tall and "↑ more" not in tall and "│  > ◼ Game Boy" in tall and "Start in Pietato" not in tall
          and "│  ↑ more" in t2.snaps[0] and "│  > ◼ Start in Pietato" in t2.snaps[0] and "↓ more" not in t2.snaps[0])
    login = dict(PI4, KEEP_LOGIN="yes")
    got, sc, t = wizard(login, ["down", "enter", ("snap", "enter"), "enter", "enter", "enter"])
    got2, _, _ = wizard(login, ["down", "enter", *moves(order(login), "autologin"), "enter", "enter", "enter",
                                "enter"])
    check(f"--login before: it doesn't sign in by itself, unless you tick it ({got['AUTOLOGIN']}, "
          f"{got2['AUTOLOGIN']})", got["AUTOLOGIN"] == "no" and "│    ◻ Sign in by itself" in t.snaps[0]
          and got2["AUTOLOGIN"] == "yes")
    got, sc, t = wizard(dict(PI4, USER="root"), ["down", "enter", ("snap", "enter"), "enter", "enter", "enter"])
    check("...set up as root: nobody to sign in", "Sign in by itself" not in t.snaps[0] and got["MODE"] == "custom")


# ---- your services, against pretend ones ----
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def go(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        u = urllib.parse.urlsplit(self.path)
        self.server.seen.append((method, u.path, self.headers.get("X-FTL-SID")))
        code, body = self.server.fn(method, u.path, urllib.parse.parse_qs(u.query), raw, self.headers)
        data = b"" if code == 204 else body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.go("GET")

    def do_POST(self):
        self.go("POST")

    def do_DELETE(self):
        self.go("DELETE")


def serve(fn):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    srv.fn, srv.seen = fn, []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"127.0.0.1:{srv.server_address[1]}"


def ha_fake(method, path, qs, raw, h):
    auth = h.get("Authorization", "")
    if auth == "Bearer slow-token":
        time.sleep(1.5)
    if auth not in ("Bearer good-token", "Bearer slow-token"):
        return 401, {"message": "Invalid authentication"}
    if path == "/api/":
        return 200, {"message": "API running."}
    if path == "/api/config":
        return 200, {"location_name": "Home", "version": "2026.10.2"}
    return 404, {"message": "Not found"}


SIDS, SIGNED_OUT = [], []


def pihole_fake(method, path, qs, raw, h):
    if path != "/api/auth":
        return 404, {"error": {"key": "not_found"}}
    no = {"session": {"valid": False, "totp": False, "sid": None, "validity": -1, "message": "password incorrect"}}
    if method == "GET":
        return (200, {"session": {"valid": True}}) if h.get("X-FTL-SID") in SIDS else (401, no)
    if method == "POST":
        if json.loads(raw or b"{}").get("password") != "pihole-pw":
            return 401, no
        SIDS.append(f"sid-{len(SIDS) + 1}")
        return 200, {"session": {"valid": True, "totp": False, "sid": SIDS[-1], "csrf": "c", "validity": 1800,
                                 "message": "password correct"}}
    if method == "DELETE":
        SIGNED_OUT.append(h.get("X-FTL-SID"))
        return 204, b""
    return 405, {}


def ollama_fake(method, path, qs, raw, h):
    if path == "/api/tags":
        return 200, {"models": [{"name": "llama3.2:3b"}, {"name": "gemma3:4b"}]}
    return 404, {"error": "not found"}


PLEX = {"polls": 0}


def plex_fake(method, path, qs, raw, h):
    if path == "/api/v2/pins" and method == "POST":
        return 201, {"id": 42, "code": "PIET", "expiresIn": 900}
    if path == "/api/v2/pins/42":
        PLEX["polls"] += 1
        return 200, {"id": 42, "code": "PIET", "authToken": "plex-token" if PLEX["polls"] >= 2 else None}
    if path == "/api/v2/resources":
        if h.get("X-Plex-Token") != "plex-token":
            return 401, {}
        return 200, [{"name": "Living Room", "provides": "server", "owned": True, "accessToken": "server-token",
                      "connections": [{"uri": f"http://{PLEX['at']}/srv", "local": True}]}]
    if path == "/srv/identity" and h.get("X-Plex-Token") == "server-token":
        return 200, {"MediaContainer": {"machineIdentifier": "lr"}}
    return 404, {}


JF = {"polls": 0, "quick": True}


def jellyfin_fake(method, path, qs, raw, h):
    if path == "/System/Info/Public":
        return 200, {"Id": "jf-server-1", "ServerName": "Den", "Version": "10.11.0"}
    if path == "/QuickConnect/Enabled":
        return 200, JF["quick"]
    if path == "/QuickConnect/Initiate" and method == "POST":
        return 200, {"Secret": "jf-secret", "Code": "123456"}
    if path == "/QuickConnect/Connect" and qs.get("secret") == ["jf-secret"]:
        JF["polls"] += 1
        return 200, {"Authenticated": JF["polls"] >= 2, "Secret": "jf-secret"}
    if path == "/Users/AuthenticateWithQuickConnect" and json.loads(raw or b"{}").get("Secret") == "jf-secret":
        return 200, {"AccessToken": "jf-token", "User": {"Id": "u1", "Name": "Sam"}}
    return 404, {}


def ra_fake(method, path, qs, raw, h):
    f = urllib.parse.parse_qs(raw.decode())
    if path == "/dorequest.php" and f.get("r") == ["login2"]:
        if f.get("u") == ["Sam"] and f.get("p") == ["ra-pw"]:
            return 200, {"Success": True, "User": "Sam", "Token": "ra-key", "Score": 0}
        return 401, {"Success": False, "Error": "Invalid User/Password combination. Please try again",
                     "Code": "invalid_credentials"}
    return 404, {}


def kept(folder, name):
    """A file of yours: (what's in it, its mode), or (None, None)."""
    path = os.path.join(folder, name)
    try:
        return open(path).read(), stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None, None


if not ONLY or "services" in ONLY:
    ha_srv, HA = serve(ha_fake)
    ph_srv, PH = serve(pihole_fake)
    ol_srv, OL = serve(ollama_fake)
    px_srv, PX = serve(plex_fake)
    PLEX["at"] = PX
    jf_srv, JFA = serve(jellyfin_fake)
    ra_srv, RA = serve(ra_fake)
    os.environ["PITATO_RA_HOST"] = "http://" + RA
    plex_mod, jf_mod = importlib.import_module("pitato.plex"), importlib.import_module("pitato.jellyfin")
    real_call = plex_mod.Plex.call
    plex_mod.Plex.call = lambda self, url, *a, **k: real_call(self, url.replace("https://plex.tv", "http://" + PX),
                                                             *a, **k)
    plex_mod.PLEX_FILE, jf_mod.JELLYFIN_FILE = S + "/var1/plex.json", S + "/var1/jellyfin.json"
    FOUND = [{"Id": "jf-server-1", "Name": "Den", "Address": "http://" + JFA, "From": "127.0.0.1"}]
    jf_mod.discover = lambda timeout=2.0: list(FOUND)
    keys = ["enter", *moves(SERVICE_KEYS, *SERVICE_KEYS), ("snap", "enter"),
            *typed(HA), "enter", *typed("wrong-token"), "enter", "enter",        # Home Assistant: a wrong token
            "enter", *typed("good-token"), "enter",
            "ctrl-u", *typed(PH), "enter", *typed("nope"), "enter", "enter",    # Pi-hole: a wrong password
            *typed("pihole-pw"), "enter",
            *typed("a b"), "enter", ("snap", "ctrl-u"), *typed(OL), "enter",     # Ollama: not an address; its models
            ("snap", "down"), "enter",
            ("~", "snap", "Sign in to Plex"),                                   # Plex: a code
            ("~", "snap", "Sign in to Den"),                                    # Jellyfin: Quick Connect's
            *typed("Sam"), "enter", *typed("bad"), "enter", "enter",             # RetroAchievements: a wrong password
            "enter", *typed("ra-pw"), "enter",
            *typed("hunter22"), "enter", *typed("hunter2"), "enter",            # the web page: not the same twice
            *typed("hunter22"), "enter", *typed("hunter22"), "enter",
            "enter", ("snap", "enter")]
    t0 = time.monotonic()
    got, sc, t = wizard(PI4, keys, cols=120)
    took = time.monotonic() - t0
    raw = t.text()
    check(f"your services, each connected as it's added ({got['CONNECTED'] if got != 'cancelled' else got}, "
          f"{took:.0f} s)", got != "cancelled" and not t.keys and got["CONNECTED"] == ", ".join(
              ["Home Assistant", "Pi-hole", "Ollama", "Plex", "Jellyfin", "RetroAchievements",
               "The web page's password"]))
    check("...the list: what each is for", all(x in t.snaps[0] for x in (
        "◆  Connect any of your services now?", "│  > ◼ The web page's password", "│    ◼ Home Assistant",
        "the TV Remote and Lights", "sign in with a code at plex.tv/link", "the Bot's brain, on another computer",
        "none: add them later in Settings, or on the web page")))
    text, mode = kept(STATIC, "homeassistant.txt")
    check(f"Home Assistant: a wrong token said so, tried again, then kept, yours only ({oct(mode or 0)})",
          "│  ▲ Home Assistant didn't accept the token" in sc and "│  ✓ Connected to Home (2026.10.2)" in sc
          and text and f"url = http://{HA}\n" in text and "token = good-token\n" in text and mode == 0o600)
    text, mode = kept(STATIC, "pihole.txt")
    check(f"Pi-hole: found (6), a wrong password said so, then signed in, and out again ({SIGNED_OUT}) "
          f"({oct(mode or 0)})", "│  ▲ Your Pi-hole didn't take that password" in sc
          and f"│  ✓ Pi-hole 6 at {PH}" in sc and text and f"address = http://{PH}\n" in text
          and "password = pihole-pw\n" in text and mode == 0o600 and SIGNED_OUT == SIDS == ["sid-1"])
    text, mode = kept(STATIC, "bot.txt")
    check(f"Ollama: not an address (said as it's typed), then its models to pick from ({oct(mode or 0)})",
          "│  ▲ That isn't an address. Try 192.168.1.20" in t.snaps[1]
          and "◆  Which model?\n│  ● gemma3:4b\n│  ○ llama3.2:3b" in t.snaps[2]
          and f"│  ✓ llama3.2:3b, on {OL}" in sc and text and text.startswith("# Bot: a computer on your network")
          and f"server = {OL}\n" in text and "model = llama3.2:3b\n" in text and mode == 0o644)
    px = json.load(open(S + "/var1/plex.json"))
    check(f"Plex: a code to type at plex.tv/link, waited for, then its server found ({px.get('server_name')}, "
          f"{oct(stat.S_IMODE(os.stat(S + '/var1/plex.json').st_mode))})",
          "│  Go to  plex.tv/link  and type  PIET" in t.snaps[3] and "Waiting for it (14:5" in t.snaps[3]
          and "Esc: skip it for now" in t.snaps[3] and "│  ✓ Signed in to Plex: Living Room" in sc
          and px.get("token") == "plex-token" and px.get("server") == f"http://{PX}/srv"
          and px.get("server_token") == "server-token"
          and stat.S_IMODE(os.stat(S + "/var1/plex.json").st_mode) == 0o600)
    jf = json.load(open(S + "/var1/jellyfin.json"))
    check(f"Jellyfin: found on the network, Quick Connect's code waited for ({jf.get('server_name')}, "
          f"{jf.get('user_name')})", "│  In Jellyfin on your phone or computer: your profile > Quick Connect,"
          in t.snaps[4] and "│  and type  123456" in t.snaps[4] and "│  ✓ Signed in to Den, as Sam" in sc
          and jf.get("token") == "jf-token" and jf.get("user") == "u1" and jf.get("server") == "http://" + JFA
          and stat.S_IMODE(os.stat(S + "/var1/jellyfin.json").st_mode) == 0o600)
    text, mode = kept(STATIC, "retroachievements.txt")
    check(f"RetroAchievements: a wrong password said so, then its key for this Pi kept, not the password "
          f"({oct(mode or 0)})", "│  ▲ Invalid User/Password combination. Please try again" in sc
          and "│  ✓ Signed in as Sam" in sc and text and "user = Sam\n" in text and "token = ra-key\n" in text
          and "ra-pw" not in text and mode == 0o600)
    text, mode = kept(STATIC, "webui.txt")
    check(f"the web page's password: not the same twice said so, then kept ({oct(mode or 0)})",
          "│  ▲ They're not the same" in sc and "│  ✓ The web page asks for it" in sc and text
          and "password = hunter22\n" in text and mode == 0o600)
    check("...none of the tokens or passwords on the screen at any time, each shown as dots",
          not [w for w in ("good-token", "wrong-token", "pihole-pw", "nope", "ra-pw", "hunter2") if w in raw]
          and "◇  A long-lived access token\n│  ••••••••••" in sc and "◇  Its password\n│  •••••\n" in sc)
    check("...ready: what's connected", "│  Connected: Home Assistant, Pi-hole, Ollama, Plex, Jellyfin, "
          "RetroAchievements, The web page's password" in t.snaps[5])

    got, sc, t = wizard(PI4, ["enter", ("snap", "enter"), "enter", "enter"], cols=120)
    check(f"set up already: the list says so ({t.snaps[0].count('set up already')} of 7)",
          t.snaps[0].count(", set up already") == 7)

    plex_mod.PLEX_FILE, jf_mod.JELLYFIN_FILE = S + "/var2/plex.json", S + "/var2/jellyfin.json"
    FOUND.clear()
    JF["quick"], PLEX["polls"] = False, 0
    SIDS.clear()
    env = dict(PI4, STATIC=S + "/static2")
    keys = ["enter", *moves(SERVICE_KEYS, *SERVICE_KEYS), "enter",
            *typed(HA), "enter", *typed("slow-token"), "enter", ("~", "esc", "Checking Home Assistant"),
            "ctrl-u", *typed(HA), "enter", "down", "enter",                     # Pi-hole: not one there
            *typed("127.0.0.1:1"), "enter", "down", "enter",                    # Ollama: nothing there
            ("~", "esc", "Waiting for it"),                                     # Plex: skipped for now
            *typed("127.0.0.1:1"), "enter", "ctrl-u", *typed(JFA), "enter",      # Jellyfin: typed; Quick Connect off
            *typed("Sam"), "enter", *typed("bad"), "enter", "down", "enter",     # RetroAchievements: skipped
            "enter",                                                             # the web page: no password
            "down", "enter", ("snap", "enter")]
    got, sc, t = wizard(env, keys, cols=120)
    files = sorted(os.listdir(S + "/static2"))
    check(f"...or not: Esc while it's checked, skipped, nothing there: nothing kept but the web page's no password "
          f"({got['CONNECTED'] if got != 'cancelled' else got!r}, {files})",
          got != "cancelled" and got["CONNECTED"] == "" and not t.keys and files == ["webui.txt"]
          and re.search(r"^password = $", kept(S + "/static2", "webui.txt")[0], re.M)
          and "│  · No password for the web page" in sc and "Connected" not in t.snaps[0])
    check("...Home Assistant: Esc while it's checked, and on to the next",
          "Connected to Home" not in sc and "◇  A long-lived access token\n│  ••••••••••\n│\n◇  Pi-hole's address" in sc)
    check("...Pi-hole: something else there, said so", f"│  ▲ {HA} doesn't answer as a Pi-hole" in sc)
    check("...Ollama: nothing there, said so",
          "│  ▲ Can't reach 127.0.0.1:1. Is Ollama on there, and listening on the network?" in sc)
    px = json.load(open(S + "/var2/plex.json"))
    check(f"...Plex: Esc while it waits for the code, not signed in ({sorted(px)})", "token" not in px
          and "Signed in to Plex" not in sc)
    jf = json.load(open(S + "/var2/jellyfin.json"))
    check(f"...Jellyfin: none on the network, typed (nothing there first), Quick Connect off there ({sorted(jf)})",
          "◇  Jellyfin's address\n│  127.0.0.1:1\n│\n│  ▲ No Jellyfin server answers there" in sc
          and "│  ▲ Quick Connect is off on Den: turn it on in its Dashboard (General), or sign in later on the Pi" in sc
          and "token" not in jf and jf.get("server") == "http://" + JFA)
    check("...RetroAchievements: skipped", "Signed in as" not in sc and "◇  RetroAchievements\n│  Skip it" in sc)

# ---- Python's own library only, and wizard.py on a real terminal ----
STOPPED = "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish."


def on_pty(argv, env, steps=(), timeout=900, interrupt=None, size=(40, 100)):
    """argv on a pretend terminal: each of steps' keys typed once its words are on it (after the last's); interrupt:
    (words, seconds): Ctrl+C that long after they're there. (what it showed, its exit status, how long it took,
    how many of steps it got to)."""
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0))
        os.execvpe(argv[0], argv, env)
    out, pos, asked, t0, hit = b"", 0, 0, time.monotonic(), None
    while time.monotonic() - t0 < timeout:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            out += chunk
            text = out.decode("utf-8", "replace")
            while asked < len(steps):
                k = text.find(steps[asked][0], pos)
                if k < 0:
                    break
                pos = k + len(steps[asked][0])
                time.sleep(0.3)
                os.write(fd, steps[asked][1])
                asked += 1
            if interrupt and hit is None and interrupt[0] in text:
                hit = time.monotonic()
        if interrupt and hit is not None and time.monotonic() - hit >= interrupt[1]:
            os.write(fd, b"\x03")
            interrupt = None
    took = time.monotonic() - t0
    done, st = os.waitpid(pid, os.WNOHANG)
    for _ in range(50):
        if done:
            break
        time.sleep(0.1)
        done, st = os.waitpid(pid, os.WNOHANG)
    if not done:
        print(f"(still going after {timeout} s: stopped)")
        os.killpg(pid, signal.SIGKILL)
        st = os.waitpid(pid, 0)[1]
    os.close(fd)
    return out.decode("utf-8", "replace"), os.waitstatus_to_exitcode(st), took, asked


def wenv(base, **more):
    env = {k: v for k, v in os.environ.items() if k not in ("COLUMNS", "LINES", "PIETATO_SETUP_UI", "NO_COLOR",
                                                              "PITATO_STATIC", "PITATO_RA_HOST")}
    env.update({"PIETATO_W_" + k: v for k, v in base.items()}, TERM="xterm-256color", LANG="C.UTF-8")
    env.update(more)
    return env


if not ONLY or "terminal" in ONLY:
    mods = ("wizard", "config", "homeassistant", "pihole", "bot", "net", "plex", "jellyfin", "cheevos")
    r = subprocess.run([sys.executable, "-I", "-S", "-c",       # (-S: none of what's been installed)
                        f"import sys; sys.path.insert(0, {ROOT!r}); import " + ", ".join("pitato." + m for m in mods)
                        + "; print('ok')"], capture_output=True, text=True, timeout=60)
    check(f"what it uses is Python's own library only: it runs before setup.sh has put anything in "
          f"({r.stdout.strip()}{r.stderr.strip()[-300:]})", r.returncode == 0 and r.stdout.strip() == "ok")
    r = subprocess.run([sys.executable, ROOT + "/pitato/wizard.py"], capture_output=True, text=True, timeout=30)
    check(f"wizard.py by itself: how it's used ({r.returncode})", r.returncode == 2 and "wizard.py ask ANSWERS"
          in r.stdout)

    ans = S + "/pty-answers"
    out, rc, took, asked = on_pty([sys.executable, ROOT + "/pitato/wizard.py", "ask", ans], wenv(PI4), [
        ("How do you want to set it up?", b"\x1b[B\r"), ("What goes in?", b"\x1b[B \r"),
        ("Connect any of your services now?", b"\r"), ("When it's done", b"\x1b[B\r"),
        ("Start setting it up?", b"\r")], timeout=60)
    a = W.read_answers(ans)
    check(f"wizard.py ask on a real terminal: the keys as a terminal sends them, the answers for setup.sh ({rc}, "
          f"{a})", rc == 0 and asked == 5 and a.get("MODE") == "custom" and a.get("LEAVE_OUT") == "ps1"
          and a.get("REBOOT") == "no" and a.get("GO") == "yes" and a.get("GPI") == "no")
    sc = screen(out)
    check("...drawn as it's answered, the cursor back at the end",
          "◇  What goes in?\n│  All but PlayStation, about " in sc and out.rstrip().endswith("\x1b[?25h")
          and out.startswith("\x1b[?25l"))
    out, rc, took, asked = on_pty([sys.executable, ROOT + "/pitato/wizard.py", "ask", ans], wenv(PI4, TERM="linux"),
                                  [("How do you want to set it up?", b"\x03")], timeout=60)
    sc = screen(out)
    check(f"...Ctrl+C: nothing's changed ({rc}, {W.read_answers(ans)}); on the Pi's console, plain letters",
          rc == 3 and W.read_answers(ans) == {"GO": "no"} and "\n|\nx  Not now: nothing's changed" in sc
          and sc.startswith("+  Pietato setup\n|\no  This Pi ---") and "(*) Default" in CSI.sub("", out)
          and "Up/Down pick" in CSI.sub("", out) and not re.search("[◆◇│●○↑↓·…]", out))

# ---- the screen while setup.sh works ----
FEED = ["Setting up for a screen on HDMI (Raspberry Pi 4 Model B Rev 1.5). Plug in any USB or Bluetooth game "
        "controller.", "Leave the Pi on until it says All set.", "", "==> Installing packages",
        "Hit:1 http://deb.debian.org bookworm InRelease", "Reading package lists...",
        "(Couldn't install cmatrix: Apps' cmatrix won't start.)", "",
        "==> Building the PlayStation emulator (PCSX ReARMed): a few minutes, longer on a Pi Zero",
        "@@working Downloading|", "  Downloading: done (took 0:12)", "@@working Building|41", "gcc -c foo.c",
        "  Building: done (took 3:01)", "", "==> Bluetooth",
        "Pair Bluetooth controllers, keyboards, headphones and the rest in Settings > Bluetooth, or on the web page.",
        "", "All set.", "It starts on the home screen (Settings > At start-up can make it the terminal).",
        "On your phone or computer, open  http://raspberrypi.local:5432",
        "to see the screen, work it with a remote, and add files.", "Your settings files are in /home/sam/Pietato/static"]


class Out:
    def __init__(self):
        self.parts = []

    def write(self, t):
        self.parts.append(t)

    def flush(self):
        pass

    def text(self):
        return "".join(self.parts)


def shown(feed, answers, end=True):
    clock = [0.0]
    out, log = Out(), Out()
    s = W.Show(out, log, W.Look(fancy=True, colour=False), answers, now=lambda: clock[0])
    for line in feed:
        clock[0] += 7
        s.take(line)
        s.moving()
    if end:
        s.finish("/var/log/pietato-setup.log")
    return screen(out.text()), out.text(), log.text()


if not ONLY or "show" in ONLY:
    sc, raw, log = shown(FEED, {"REBOOT": "yes"})
    rows = sc.split("\n")
    first = rows[:next(k for k, r in enumerate(rows) if r.startswith("◇"))]
    check(f"what it says first, under the questions, to the screen's width ({first})",
          first[-1] == "│" and all(r.startswith("│  ") and len(r) <= 99 for r in first[:-1])
          and " ".join(r[3:] for r in first[:-1]) == FEED[0] + " " + FEED[1] and len(first) == 4)
    steps = [r for r in rows if r.startswith(("◇  ", "│  ▲"))]
    check(f"a line for each step once it's done, its time at the right; under it what didn't go in ({steps[:4]})",
          [re.sub(r" {2,}", " | ", s) for s in steps[:4]] == [
              "◇ | Installing packages | 0:35", "│ | ▲ Couldn't install cmatrix: Apps' cmatrix won't start.",
              "◇ | Building the PlayStation emulator (PCSX ReARMed) | 0:49", "◇ | Bluetooth | 0:21"]
          and len(steps[0]) == len(steps[2]) == len(steps[3]) == 75)
    check("...the one under way moving, with what it's at (a few minutes; Building 41%)",
          re.search(r"[◒◐◓◑]  Building the PlayStation emulator \(PCSX ReARMed\)  a few minutes", raw) is not None
          and re.search(r"[◒◐◓◑]  Building the PlayStation emulator \(PCSX ReARMed\)  Building 41% +\d:\d\d", raw)
          is not None and "Downloading" in raw)
    check("...nothing else of what it says on the screen (the build's, apt's)",
          not [w for w in ("gcc", "Hit:1", "Reading package", "Pair Bluetooth", "@@", "done (took") if w in sc])
    check("All set: what's next, how long it took, and where the log is, and then it restarts",
          "◇  All set. ─" in sc and "│  It starts on the home screen (Settings > At start-up can make it the terminal)."
          in sc and "│  On your phone or computer, open http://raspberrypi.local:5432" in sc
          and "│  It took 2:41. All it did is in /var/log/pietato-setup.log" in sc and sc.endswith("└  Restarting now…"))
    check("...all it said in its log, as it said it (not what was for the screen)",
          log.split("\n")[:-1] == [x for x in FEED if not x.startswith("@@")])
    sc2 = shown(FEED, {"REBOOT": "no"})[0]
    sc3 = shown(FEED, {"REBOOT": "no", "GPI": "yes"})[0]
    check("...not restarting: Pietato's starting, restart when you're ready (in a GPi Case: its screen needs it)",
          sc2.endswith("└  Pietato's starting. Restart when you're ready: sudo reboot")
          and sc3.endswith("└  Restart when you're ready (sudo reboot): the case's screen and sound need it"))
    sc, raw, log = shown(["==> Installing packages", "Hit:1 http://deb.debian.org bookworm InRelease",
                          "E: no network (pretend)", "", STOPPED], {"REBOOT": "yes"})
    check("stopped: where, the last of what it said, and how to finish",
          re.search(r"\n■  Installing packages +0:28\n│\n│  Hit:1 http://deb.debian.org bookworm InRelease\n"
                    r"│  E: no network \(pretend\)\n│\n└  " + re.escape(STOPPED) +
                    r"\n   All it did is in /var/log/pietato-setup.log$", sc) is not None and sc.count(STOPPED) == 1)
    sc = shown(["==> Installing packages"], {})[0]
    check("...its output ended without a word: stopped all the same",
          sc.endswith("└  setup.sh stopped before it was done.\n   All it did is in /var/log/pietato-setup.log"))
    os.environ["COLUMNS"] = "60"
    sc = shown(["==> Installing LibreOffice (Word, Excel and PowerPoint files in their own layout)", "All set."],
               {})[0]
    os.environ["COLUMNS"] = "100"
    check(f"...a narrow screen: a step's words in brackets go first ({[r for r in sc.split(chr(10)) if 'Libre' in r]})",
          re.search(r"\n◇  Installing LibreOffice +0:07\n", sc) is not None)

    log_path = S + "/show.log"
    p = subprocess.Popen([sys.executable, ROOT + "/pitato/wizard.py", "show", log_path, S + "/none"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=dict(os.environ, LANG="C.UTF-8", TERM="xterm"))
    p.stdin.write(b"==> Installing packages\r\nHit:1 a\n\n@@working Building|5\nAll set.\nIt starts on the home screen.\n")
    p.stdin.flush()
    time.sleep(0.6)
    p.send_signal(signal.SIGINT)
    time.sleep(0.4)
    alive = p.poll() is None
    p.stdin.write(b"@@end\n")
    p.stdin.flush()
    try:
        rc = p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = "stuck"
    out = p.stdout.read().decode("utf-8", "replace")
    p.stdin.close()
    sc = screen(out)
    check(f"wizard.py show: setup.sh's output on a pipe, drawn; Ctrl+C left to setup.sh ({alive}); done at @@end, "
          f"though the pipe's still open ({rc})", alive and rc == 0 and "◇  Installing packages" in sc
          and "◇  All set. ─" in sc and f"All it did is in {log_path}" in sc and out.endswith("\x1b[?25h")
          and open(log_path).read() == "==> Installing packages\nHit:1 a\n\nAll set.\nIt starts on the home screen.\n")

# ---- setup.sh: what's left out, and its options ----
if not ONLY or "options" in ONLY:
    setup = open(ROOT + "/setup.sh").read()
    block = setup[setup.index("SETUP_CONF=/var/lib/pitato/setup.conf"):setup.index("# Until it's done, a shutdown")]
    parts = re.search(r'^PARTS="[^"]*"', setup, re.M).group(0)
    conf = S + "/setup.conf"

    def left(saved=None, **v):
        if saved is None:
            if os.path.exists(conf):
                os.remove(conf)
        else:
            open(conf, "w").write(f"# setup.sh's\nleave_out = {saved}\n")
        script = (f"{parts}\nIMAGE={v.get('IMAGE', 'no')} MODE={v.get('MODE', '')} WITHOUT={v.get('WITHOUT', '')!r}\n"
                  + block.replace("/var/lib/pitato/setup.conf", conf)
                  + '\necho "$SAVED|$LEAVE_OUT|$(wanted ps1 && echo in || echo out)|$(left_out ps1 "the PSX")"')
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() + r.stderr.strip()

    got = [left(), left("ps1 n64 bogus ps1"), left("ps1", MODE="default"), left("ps1", IMAGE="yes"),
           left("ps1", WITHOUT="neogeo,dc ps1"), left("", WITHOUT="classic")]
    check(f"setup.sh: what's left out ({got})", got == [
        "no||in|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)",
        "yes|ps1 n64|out|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)",
        "yes||in|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)",
        "yes||in|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)",
        "yes|ps1 dc neogeo|out|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)",
        "yes|classic|in|(Left out: the PSX. sudo bash setup.sh --default puts everything in.)"])
    args = setup[setup.index('next_is=""'):setup.index('HERE="$(cd')]
    parsed = []
    for a in (["--without", "ps1,neogeo", "--custom"], ["--without=dc", "--without", "n64", "--default", "--plain"]):
        r = subprocess.run(["bash", "-c", f'GPI="" CASE="" PLAIN=no MODE="" WITHOUT=""\n{args}\n'
                                          'echo "[$(echo $WITHOUT)] $MODE $PLAIN"', "_"] + a,
                           capture_output=True, text=True, timeout=30)
        parsed.append(" ".join(r.stdout.split()))
    check(f"...its options ({parsed})", parsed == ["[ps1 neogeo] custom no", "[dc n64] default yes"])
    errs = []
    for a in (["--without", "ps1,bogus"], ["--without"], ["--without=psx"], ["--frob"]):
        r = subprocess.run(["bash", ROOT + "/setup.sh"] + a, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        errs.append((r.returncode, r.stdout.strip()))
    check(f"...ones it doesn't know: said, and nothing done ({errs})", errs == [
        (1, "There's no part called bogus. The parts: classic, ps1, n64, psp, nds, dc, ps2, gc, neogeo, ngp, link, "
            "cheevos, chromium, office, toys, computers"),
        (1, "--without needs the parts after it: --without ps1,neogeo"),
        (1, "There's no part called psx. The parts: classic, ps1, n64, psp, nds, dc, ps2, gc, neogeo, ngp, link, "
            "cheevos, chromium, office, toys, computers"),
        (1, "Unknown option: --frob (use --gpi, --gpi2, --no-gpi, --login, --camera, --update, --image, --plain, "
            "--default, --custom or --without)")])

# ---- the real setup.sh, on a pretend terminal ----
F = SP + "/setupspin/full"


def report(out, key):
    m = re.search(r"^" + re.escape(key) + r": (.*?)\r?$", CSI.sub("", out), re.M)
    return m.group(1) if m else None


def setup_run(steps=(), timeout=1800, interrupt=None, **more):
    for f in ("hold.log", "stub.log", "setup.log", "setup.log.1"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = wenv({}, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", PIETATO_SETUP_LOG=F + "/setup.log", **more)
    env = {k: v for k, v in env.items() if not k.startswith("PIETATO_W_") and k != "GIT_TERMINAL_PROMPT"}
    return on_pty(["unshare", "-m", "bash", F + "/inner.sh"], env, steps, timeout, interrupt)


def setup_log():
    try:
        return open(F + "/setup.log", errors="replace").read()
    except OSError:
        return ""


if not ONLY or "setup" in ONLY:
    shutil.rmtree(F + "/repo", ignore_errors=True)
    shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    ha_srv2, HA2 = serve(ha_fake)
    out, rc, took, asked = setup_run([
        ("How do you want to set it up?", b"\x1b[B\r"), ("What goes in?", b"\x1b[B \r"),
        ("Connect any of your services now?", b" \x1b[A \r"), ("Home Assistant's address", HA2.encode() + b"\r"),
        ("A long-lived access token", b"good-token\r"), ("A password for the web page", b"s3cret-pw\r"),
        ("The same again", b"s3cret-pw\r"), ("When it's done", b"\x1b[B\r"), ("Start setting it up?", b"\r")])
    open(F + "/wizard.out", "w").write(out)
    sc, log = screen(out), setup_log()
    print(f"(Custom, without the PlayStation: {took:.0f} s)")
    check(f"setup.sh on a terminal: its questions first ({asked} of 9), then it works by itself, to the end "
          f"(exit {report(out, 'SETUP EXIT')})", asked == 9 and report(out, "SETUP EXIT") == "0"
          and "◇  How do you want to set it up?\n│  Custom\n" in sc and "◇  What goes in?\n│  All but PlayStation" in sc
          and "│  ✓ Connected to Home (2026.10.2)" in sc and "│  ✓ The web page asks for it" in sc
          and "│  Connected: Home Assistant, The web page's password" in sc and STOPPED not in sc)
    step_rows = [r for r in sc.split("\n") if re.match(r"◇  \S.* \d+:\d\d$", r)]
    check(f"...a line for each step ({len(step_rows)}: {[r.split('  ')[1] for r in step_rows][:4]}...), and no build "
          f"output, nor anything else it said, on the screen",
          len(step_rows) >= 8 and step_rows[0].startswith("◇  Installing packages")
          and "==> " not in out and not re.search(r"\bgcc\b|make\[\d|Hit:\d+ |Reading package lists|\.o\b", sc)
          and "Building the PlayStation emulator" not in sc)
    check("...All set: what's next, where the log is, and Pietato started (no restart, as asked)",
          "◇  All set. ─" in sc and "All it did is in" in sc and f"{F}/setup.log" in sc
          and "└  Pietato's starting. Restart when you're ready: sudo reboot" in sc
          and "systemctl restart pitato" in open(F + "/stub.log").read().splitlines()
          and not any(x.startswith("reboot") for x in open(F + "/stub.log").read().splitlines()))
    check(f"...the PlayStation left out: no PCSX ReARMed, no ps1 folder, and kept for next time "
          f"({report(out, 'CORES')}, {report(out, 'GAMES')}, {report(out, 'SETUP CONF')})",
          "pcsx" not in report(out, "CORES") and " ps1 " not in report(out, "GAMES") + " "
          and "gb " in report(out, "GAMES") and report(out, "SETUP CONF") == "[ps1]")
    check(f"...Home Assistant and the web page's password: kept by it as Settings keeps them, yours only "
          f"({report(out, 'PRIVATE')}, {report(out, 'HA FILE')})",
          report(out, "PRIVATE") == "[homeassistant.txt gpitest 600 webui.txt gpitest 600 ]"
          and report(out, "HA FILE") == f"[url = http://{HA2}|token = good-token|]"
          and "Keeping your existing /home/gpitest/pitato/static/homeassistant.txt" in log
          and "Home Assistant address" not in out)
    check("...all it did in its log, not the screen's own words; the answers' file gone",
          "==> Installing packages" in log and "All set." in log and "@@" not in log
          and report(out, "VARTMP") == "[]")
    h = open(F + "/hold.log").read().splitlines() if os.path.exists(F + "/hold.log") else []
    check(f"...held while it worked, let go before All set ({len(h)})", len(h) == 2 and h[1].startswith("let go "))

    out, rc, took, asked = setup_run([("How do you want to set it up?", b"\r"),
                                      ("Connect any of your services now?", b"\r"), ("When it's done", b"\r"),
                                      ("Start setting it up?", b"\x1b[B\x1b[B\r")], timeout=300)
    sc = screen(out)
    check(f"Not now: nothing's changed, and it says so ({report(out, 'SETUP EXIT')}, {report(out, 'SETUP CONF')}, "
          f"{report(out, 'UNITS')})", asked == 4 and report(out, "SETUP EXIT") == "0" and "■  Not now: nothing's "
          "changed" in sc and STOPPED not in sc and report(out, "SETUP CONF") == "[]" and report(out, "UNITS") == "[]"
          and report(out, "VARTMP") == "[]" and "==> " not in out and not setup_log())

    out, rc, took, asked = setup_run([("How do you want to set it up?", b"\r"),
                                      ("Connect any of your services now?", b"\r"), ("When it's done", b"\r"),
                                      ("Start setting it up?", b"\r")], timeout=600,
                                     interrupt=("Building the PlayStation emulator", 4))
    open(F + "/wizard-ctrlc.out", "w").write(out)
    sc = screen(out)
    print(f"(Ctrl+C: {took:.0f} s)")
    check(f"Ctrl+C mid-build: where it stopped, the last of what it said, how to finish ({report(out, 'SETUP EXIT')})",
          report(out, "SETUP EXIT") == "130" and re.search(r"\n■  Building the PlayStation emulator \(PCSX ReARMed\) +"
                                                           r"\d+:\d\d\n", sc) is not None
          and f"└  {STOPPED}\n   All it did is in {F}/setup.log" in sc and "◇  All set" not in sc
          and "Couldn't build cacafire" not in sc[sc.index("■  Building the PlayStation"):]
          and STOPPED in setup_log())
    check(f"...the half-built emulator's folder gone, the answers' too, nothing built ({report(out, 'VARTMP')}, "
          f"{report(out, 'CORES')})", report(out, "VARTMP") == "[]" and "pcsx" not in report(out, "CORES"))
    check("...the terminal as it was: the cursor back", "\x1b[?25h" in out[out.rfind(STOPPED):])

    out, rc, took, asked = setup_run(SETUP_ARGS="--update", SETUP_STDIN="/dev/null", SETUP_GIT="1",
                                     SETUP_CONF_INIT="ps1 neogeo")
    print(f"(--update: {took:.0f} s)")
    check(f"--update (Update software): no questions, what was left out stays out "
          f"({report(out, 'CORES')}, {report(out, 'GAMES')}, {report(out, 'SETUP CONF')})",
          report(out, "SETUP EXIT") == "0" and "How do you want" not in out and "pcsx" not in report(out, "CORES")
          and "fbneo" not in report(out, "CORES") and "==> Building the Neo Geo Pocket emulator" in out
          and " ps1 " not in report(out, "GAMES") and "neogeo" not in report(out, "GAMES")
          and report(out, "SETUP CONF") == "[ps1 neogeo]"
          and "(Left out: the PlayStation emulator (PCSX ReARMed). sudo bash setup.sh --default puts everything in.)"
          in out and "(Left out: the Neo Geo emulator (FinalBurn Neo). sudo bash setup.sh --default puts everything "
          "in.)" in out and "==> Installing packages" in out)

    out, rc, took, asked = setup_run(SETUP_ARGS="--no-gpi --plain", APT_FAIL="1", timeout=300)
    check(f"--plain on a terminal: the old way, its lines as they come ({report(out, 'SETUP EXIT')})",
          "How do you want" not in out and "==> Installing packages" in out and "E: no network (pretend)" in out
          and STOPPED in out and report(out, "SETUP EXIT") not in (None, "0") and "◇" not in out)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
