"""The Pi's terminal on the web page: its own console (the one the Pi's screen shows when media mode isn't on), its
words and colours as the console has them (/dev/vcsa and /dev/vcsu), and what's typed on the page put into it as if
it were typed there (TIOCSTI). Only once the page has been given your Pi password, the one you sign in with, checked
as the Pi checks it (its hash in /etc/shadow, through libcrypt): then a key for that page, good while it's used. Wrong
passwords are counted, for each address they come from and for all of them, and kept on disk: a restart doesn't forget
them."""
import ctypes
import ctypes.util
import fcntl
import hashlib
import hmac
import json
import math
import os
import secrets
import struct
import termios
import threading
import time

VCS = "/dev/vcs{}{}"            # the console's screen: vcsa (its letters' colours, and where the cursor is) and vcsu
TTY = "/dev/tty{}"              # (its letters), N for console N; and the console itself, to type into
ACTIVE = "/sys/class/tty/tty0/active"   # the console in front ("tty1")
SHADOW = "/etc/shadow"          # each user's password, as its hash
TRIES_FILE = "/var/lib/pitato/term-tries.json"   # the wrong passwords of the last day: when, and from where
TERM_KEY_IDLE = 30 * 60.0       # seconds a page's key is good for after it's last used (a page showing the terminal
                                # uses it every few seconds)
TERM_KEY_MOST = 12 * 3600.0     # ...and after it was given, at most: then your password again
TERM_HASH_LOOK = 5.0            # seconds between looks at whether your password has changed (then every key goes)
TERM_KEYS_MOST = 8              # pages with a key at once, at most (the oldest goes)
TERM_TRIES = (5, 60.0, 3600.0)  # this many wrong passwords from one address in a day: then a minute before its next
                                # try, twice as long after each wrong one after that, an hour at most
TERM_TRIES_ALL = (20, 3600.0)   # this many wrong ones from anywhere in an hour: no tries from anywhere till an hour
                                # after the first of them
TERM_TRIES_KEEP = 86400.0       # seconds a wrong password is counted for
TERM_TRIES_MOST = 500           # wrong passwords remembered, at most (the latest)
TERM_WRONG_WAIT = 1.5           # seconds before a wrong password is said to be wrong
PASSWORD_MOST = 511             # bytes a password can be, at most (libcrypt's own limit, less one)
TERM_WAIT = 20.0                # seconds a page's look waits for the console to change, at most
TERM_EVERY = 0.08               # ...looking at it this often meanwhile
TERM_KEEP = 24                  # the console's last this many looks, kept: a page that has one is sent what changed
TYPE_MOST = 4096                # characters typed at once, at most


def console_vt():
    """The number of the console in front (1 for tty1), or None."""
    try:
        with open(ACTIVE) as f:
            name = f.read().strip()
    except OSError:
        return None
    return int(name[3:]) if name.startswith("tty") and name[3:].isdigit() and int(name[3:]) > 0 else None


def read_console(vt):
    """Console vt as it is: (rows, columns, (the cursor's column, its row), [each row's letters, each with its colours,
    as runs: [letters, colour, background], the colours the console's own 0 to 15]), or None."""
    try:
        with open(VCS.format("a", vt), "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if len(raw) < 4:
        return None
    rows, cols, cx, cy = raw[0], raw[1], raw[2], raw[3]
    cells = raw[4:4 + rows * cols * 2]
    if not rows or not cols or len(cells) < rows * cols * 2:
        return None
    letters = None
    try:
        with open(VCS.format("u", vt), "rb") as f:
            u = f.read(rows * cols * 4)
        if len(u) == rows * cols * 4:
            letters = struct.unpack(f"<{rows * cols}I", u)
    except OSError:
        pass
    lines = []
    for r in range(rows):
        runs, text, at = [], [], None
        for c in range(cols):
            k = r * cols + c
            ch, attr = cells[2 * k], cells[2 * k + 1]
            if letters is not None:
                code = letters[k]
                ch = chr(code) if 32 <= code < 0x110000 and not 0xD800 <= code < 0xE000 else " "
            else:                                      # (no vcsu: the console's own letters, as far as plain ASCII)
                ch = chr(ch) if 32 <= ch < 127 else " "
            colours = (attr & 15, attr >> 4 & 7)
            if colours != at:
                if text:
                    runs.append(["".join(text), at[0], at[1]])
                text, at = [], colours
            text.append(ch)
        if text:
            runs.append(["".join(text), at[0], at[1]])
        while runs and runs[-1][2] == 0 and not runs[-1][0].strip():   # (plain blanks at a row's end: not sent)
            runs.pop()
        if runs and runs[-1][2] == 0:
            runs[-1][0] = runs[-1][0].rstrip(" ") or runs[-1][0]
        lines.append(runs)
    return rows, cols, (min(cx, cols - 1), min(cy, rows - 1)), lines


def type_into(vt, text):
    """text put into console vt, as if it had been typed on its keyboard (root: TIOCSTI). True if it went in."""
    try:
        fd = os.open(TTY.format(vt), os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return False
    try:
        for b in text.encode("utf-8"):
            fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


_crypt = None
_crypt_lock = threading.Lock()


def crypt(word, setting):
    """libcrypt's crypt(): word hashed as setting says (a hash from /etc/shadow: its kind and its salt), or None."""
    global _crypt
    with _crypt_lock:
        if _crypt is None:
            try:
                fn = ctypes.CDLL(ctypes.util.find_library("crypt") or "libcrypt.so.1").crypt
                fn.restype, fn.argtypes = ctypes.c_char_p, (ctypes.c_char_p, ctypes.c_char_p)
                _crypt = fn
            except (OSError, AttributeError):
                _crypt = False
        if not _crypt:
            return None
        out = _crypt(word.encode("utf-8"), setting.encode("utf-8"))
    return out.decode("utf-8", "replace") if out else None


def stored_hash(user, shadow=SHADOW):
    """user's password as /etc/shadow has it (its hash), or None (no such user, or it can't be read)."""
    try:
        with open(shadow, errors="replace") as f:
            for line in f:
                name, _, rest = line.partition(":")
                if name == user:
                    return rest.split(":", 1)[0].strip()
    except OSError:
        pass
    return None


def hash_digest(user, shadow=SHADOW):
    """A digest of user's password's hash (it changes when the password does), or None."""
    stored = stored_hash(user, shadow)
    return hashlib.sha256(stored.encode("utf-8", "replace")).hexdigest() if stored is not None else None


def password_ok(user, password, shadow=SHADOW):
    """Whether password is user's (as the Pi checks it when you sign in): True or False; None when there's no telling
    (no such user, no password set for them, or nothing here to check it with)."""
    stored = stored_hash(user, shadow)
    if not stored or stored[0] in "!*" or stored == "x":
        return None
    out = crypt(password, stored)
    if not out or out.startswith("*"):
        return None
    return hmac.compare_digest(out.encode(), stored.encode())


class Terminal:
    """The terminal on the web page: the keys given to pages, wrong passwords counted, and the console's last looks
    (numbered: a page that has one of them is sent just the rows that changed since)."""

    def __init__(self, shadow=None, tries_file=None):
        self.shadow = shadow           # (SHADOW's, unless it's given another)
        self.tries_file = tries_file   # (TRIES_FILE, unless it's given another)
        self.lock = threading.Lock()
        self.trying = threading.Lock() # one password checked at a time: many sent at once still count, one by one
        self.keys = {}                 # a page's key -> {"used", "made" (monotonic), "user", "hash": a digest of their
                                       # password's hash then, "seen": when that was last compared}
        self.wrong = None              # [[when (the clock's), from where]]: the last day's wrong passwords (from disk)
        self.v = 0                     # the console's look's number (a new one each time it changes)
        self.looks = []                # [(number, vt, rows, columns, cursor, rows' runs)], the last TERM_KEEP

    # -- wrong passwords ----------------------------------------------------------------------------------------
    def tries(self, now):
        """(Under self.lock.) The wrong passwords still counted: [[when, from where]], oldest first (read from disk the
        first time; none from the future either, the clock having gone back)."""
        if self.wrong is None:
            self.wrong = []
            try:
                with open(self.tries_file or TRIES_FILE) as f:
                    got = json.load(f)
                self.wrong = [[float(t), str(a)] for t, a in got if isinstance(t, (int, float))][-TERM_TRIES_MOST:]
            except (OSError, ValueError, TypeError):
                pass
        self.wrong = [x for x in self.wrong if 0 <= now - x[0] < TERM_TRIES_KEEP or 0 < x[0] - now < 60]
        return self.wrong

    def keep_tries(self):
        """(Under self.lock.) The wrong passwords, on disk (only root can read them)."""
        path = self.tries_file or TRIES_FILE
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".part"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.wrong[-TERM_TRIES_MOST:], f)
            os.replace(tmp, path)
        except OSError:
            pass

    def blocked(self, addr, now):
        """(Under self.lock.) Seconds until a password from addr is checked again (0: now)."""
        tries = self.tries(now)
        most, first, longest = TERM_TRIES
        mine = [t for t, a in tries if a == addr]
        wait = 0.0
        if len(mine) >= most:
            wait = mine[-1] + min(longest, first * 2 ** min(len(mine) - most, 16)) - now
        many, hour = TERM_TRIES_ALL
        recent = [t for t, a in tries if now - t < hour]
        if len(recent) >= many:
            wait = max(wait, recent[-many] + hour - now)
        return max(0.0, wait)

    # -- keys ---------------------------------------------------------------------------------------------------
    def unlock(self, user, password, addr=""):
        """Your Pi password, from a page (at addr): {"key": its key} or {"error": why not}."""
        if not user or not isinstance(password, str) or not password:
            return {"error": "Type your Pi password"}
        addr = str(addr or "")[:64]
        with self.trying:
            with self.lock:
                wait = self.blocked(addr, time.time())
            if wait > 0:
                minutes = math.ceil(wait / 60)
                return {"error": "Too many wrong passwords. Try again in "
                        + ("a minute" if minutes <= 1 else f"{minutes} minutes")}
            try:
                raw = password.encode("utf-8")
            except UnicodeEncodeError:                     # (half a letter: not one anyone could type)
                raw = b"\0"
            if b"\0" in raw or len(raw) > PASSWORD_MOST:          # (not one libcrypt could check whole: wrong)
                ok = False
            else:
                ok = password_ok(user, password, self.shadow or SHADOW)
            if ok is None:
                print(f"terminal: the Pi can't check {user}'s password (none set, or locked)", flush=True)
                return {"error": "The Pi can't check your password. Set one on the Pi first: passwd"}
            if not ok:
                with self.lock:
                    self.tries(time.time()).append([time.time(), addr])
                    self.keep_tries()
                print(f"terminal: a wrong password from {addr or 'here'}", flush=True)
                time.sleep(TERM_WRONG_WAIT)                # (still checking: the next one waits too)
                return {"error": "That isn't your Pi password", "kind": "wrong"}
        key = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self.lock:
            tries = self.tries(time.time())
            if any(a == addr for _, a in tries):           # (this address's wrong ones forgotten; not others')
                self.wrong = [x for x in tries if x[1] != addr]
                self.keep_tries()
            self.keys[key] = {"used": now, "made": now, "user": user, "seen": now,
                              "hash": hash_digest(user, self.shadow or SHADOW)}
            while len(self.keys) > TERM_KEYS_MOST:
                del self.keys[min(self.keys, key=lambda k: self.keys[k]["used"])]
        print(f"terminal: opened on the web page from {addr or 'here'}", flush=True)
        return {"ok": True, "key": key}

    def check(self, key):
        """A page's key, still good: True (and good for longer now). Not if it's gone unused a while, or it was given
        long ago, or your password's changed since."""
        if not isinstance(key, str) or not key or len(key) > 128:
            return False
        now = time.monotonic()
        with self.lock:
            for k, v in list(self.keys.items()):
                if now - v["used"] > TERM_KEY_IDLE or now - v["made"] > TERM_KEY_MOST:
                    del self.keys[k]
            want = key.encode("utf-8", "replace")
            got = next((k for k in self.keys if hmac.compare_digest(k.encode(), want)), None)
            if got is None:
                return False
            entry = self.keys[got]
            if now - entry["seen"] >= TERM_HASH_LOOK:
                entry["seen"] = now
                if hash_digest(entry["user"], self.shadow or SHADOW) != entry["hash"]:   # (a new password: every
                    for k in [k for k, v in self.keys.items() if v["user"] == entry["user"]]:   # page asked for it)
                        del self.keys[k]
                    return False
            entry["used"] = now
            return True

    def forget(self, key):
        """A page's key, given back (Lock)."""
        if not isinstance(key, str):
            return
        want = key.encode("utf-8", "replace")
        with self.lock:
            for k in list(self.keys):
                if hmac.compare_digest(k.encode(), want):
                    del self.keys[k]

    # -- the console ---------------------------------------------------------------------------------------------
    def current(self, vt):
        """The console's look now, numbered: (number, vt, rows, columns, cursor, rows' runs), or None."""
        got = read_console(vt)
        if got is None:
            return None
        with self.lock:
            last = self.looks[-1] if self.looks else None
            if last is not None and last[1:] == (vt,) + got:
                return last
            self.v += 1
            look = (self.v, vt) + got
            self.looks = (self.looks + [look])[-TERM_KEEP:]
            return look

    def look(self, vt, after=None, wait=0.0, still=lambda: True):
        """The console as a page sees it: its number, its size, where the cursor is, and its rows (all of them, or
        just those that changed since the look the page has: after), once it's changed from that one (waiting up to
        wait seconds, while still() says the page may)."""
        try:
            after = int(after) if after is not None else None
        except (TypeError, ValueError):
            after = None
        try:
            wait = max(0.0, min(float(wait or 0), TERM_WAIT))
        except (TypeError, ValueError):
            wait = 0.0
        end = time.monotonic() + wait
        look = self.current(vt)
        while look is not None and look[0] == after and time.monotonic() < end and still():
            time.sleep(TERM_EVERY)
            look = self.current(vt)
        if look is None:
            return {"error": "The Pi's terminal can't be read"}
        v, _, rows, cols, cursor, lines = look
        out = {"ok": True, "v": v, "rows": rows, "cols": cols, "cursor": list(cursor)}
        with self.lock:
            had = next((x for x in self.looks if x[0] == after), None)
        if had is not None and had[1:4] == (vt, rows, cols):
            out["changed"] = {str(r): lines[r] for r in range(rows) if lines[r] != had[5][r]}
        else:
            out["lines"] = lines
        return out

    def type(self, vt, text):
        """What's typed on a page, into the console: {"ok": True} or {"error": why not}."""
        if not isinstance(text, str) or not text:
            return {"ok": True}
        if len(text) > TYPE_MOST:
            return {"error": "That's too much to type at once"}
        if not type_into(vt, text):
            return {"error": "The Pi's terminal didn't take it"}
        return {"ok": True}
