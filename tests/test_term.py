"""The Pi's terminal on the web page (pitato/term.py), on its own: the console read as it has it (vcsa: its colours and
cursor; vcsu: its letters; without vcsu, plain ASCII), each look numbered and only what changed sent to a page that
has the one before; your Pi password checked as the Pi checks it (a SHA-512 and a yescrypt hash, as /etc/shadow has
them), wrong ones waited on and counted (for each address: five, then a minute's wait, doubling with each after that;
twenty from anywhere in an hour: none from anywhere; kept on disk; ones libcrypt can't check whole: wrong), none set
or a locked account said so (no name said); keys good while they're used (half an hour), twelve hours at most, none
once your password's changed, given back, never more than eight; what's typed put into a terminal as if typed
there (a pty here, TIOCSTI as on the Pi's console); then media mode's side of it (web_term): locked without a key, the
terminal only while media mode isn't on."""
import ctypes, ctypes.util, json, os, pty, select, shutil, struct, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_term"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
sys.path.insert(0, os.environ.get("PITATO_REPO") or ROOT)
from pitato import term as T
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


T.VCS = S + "/vcs{}{}"
T.TTY = S + "/tty{}"
T.ACTIVE = S + "/active"
T.TERM_WRONG_WAIT = 0.05
T.TRIES_FILE = S + "/tries.json"


def console(rows, cols, cx, cy, text, attrs=None, unicode=True, vt=1):
    """A pretend console: text (rows of it), every letter light grey on black unless attrs says ({(row, col): attr})."""
    cells, letters = bytearray(), []
    for r in range(rows):
        line = (text[r] if r < len(text) else "").ljust(cols)[:cols]
        for c, ch in enumerate(line):
            a = (attrs or {}).get((r, c), 0x07)
            cells += bytes([ord(ch) if ord(ch) < 256 else 0x3F, a])
            letters.append(ord(ch))
    open(S + f"/vcsa{vt}", "wb").write(bytes([rows, cols, cx, cy]) + bytes(cells))
    if unicode:
        open(S + f"/vcsu{vt}", "wb").write(struct.pack(f"<{rows * cols}I", *letters))
    elif os.path.exists(S + f"/vcsu{vt}"):
        os.remove(S + f"/vcsu{vt}")


# ---- the console, read ------------------------------------------------------------------------------------------------
open(T.ACTIVE, "w").write("tty1\n")
check(f"the console in front: tty1 ({T.console_vt()})", T.console_vt() == 1)
open(T.ACTIVE, "w").write("tty7\n")
check("...tty7 (media mode's)", T.console_vt() == 7)
open(T.ACTIVE, "w").write("garbage\n")
check("...nonsense: no telling", T.console_vt() is None)
open(T.ACTIVE, "w").write("tty1\n")

red, on_blue = 0x0C, 0x1F                     # (bright red on black; white on blue)
console(4, 20, 6, 1, ["pi@pi:~ $ ls", "Music  Pictures", "", "€ ünïcode ☺"], {(1, 0): red, (1, 1): red, (1, 2): red,
                                                                           (1, 3): red, (1, 4): red, (2, 3): on_blue})
rows, cols, cursor, lines = T.read_console(1)
check(f"its size and its cursor (4 x 20, at 6, 1): {rows} x {cols}, at {cursor}", (rows, cols, cursor) == (4, 20, (6, 1)))
check(f"a row's letters, plain ones as one run, blanks at its end not sent: {lines[0]}", lines[0] == [["pi@pi:~ $ ls", 7, 0]])
check(f"...colours as runs (Music in bright red, the rest plain): {lines[1]}",
      lines[1] == [["Music", 12, 0], ["  Pictures", 7, 0]])
check(f"...a coloured background kept, even a blank one: {lines[2]}", lines[2] == [["   ", 7, 0], [" ", 15, 1]])
check(f"...its letters as the console has them (vcsu): {lines[3]}", lines[3] == [["€ ünïcode ☺", 7, 0]])
console(4, 20, 0, 0, ["plain ASCII", "", "", "€ ü"], unicode=False)
_, _, _, lines = T.read_console(1)
check(f"no vcsu (an older kernel): its own letters, as plain ASCII (the rest blank): {lines[0]}, {lines[3]}",
      lines[0] == [["plain ASCII", 7, 0]] and lines[3] in ([["? \xfc", 7, 0]], [["?", 7, 0]], [["?  ", 7, 0]])
      or lines[3][0][0].startswith("?"))
check("a console that isn't there: none", T.read_console(9) is None)
open(S + "/vcsa5", "wb").write(b"\x02")
check("...or one too short to read: none", T.read_console(5) is None)

# ---- looks, numbered: what changed ------------------------------------------------------------------------------------
t = T.Terminal(shadow=S + "/shadow")
console(4, 20, 2, 0, ["$ ", "", "", ""])
a = t.look(1)
check(f"a page's first look: all of it ({a['v']}, {len(a['lines'])} rows, cursor {a['cursor']})",
      a["ok"] and "lines" in a and len(a["lines"]) == 4 and a["cursor"] == [2, 0])
b = t.look(1, a["v"], 0)
check(f"...again, nothing changed: the same look, nothing in it ({b['v']}, {b.get('changed')})",
      b["v"] == a["v"] and b.get("changed") == {})
console(4, 20, 4, 1, ["$ ls", "Music", "", ""])
c = t.look(1, a["v"], 0)
check(f"...typed, and answered: a new look, just the rows that changed ({c['v']}, {sorted(c['changed'])})",
      c["v"] == a["v"] + 1 and sorted(c["changed"]) == ["0", "1"] and c["changed"]["1"] == [["Music", 7, 0]]
      and c["cursor"] == [4, 1])
d = t.look(1, 12345, 0)
check("...a page with a look that's gone: all of it", "lines" in d and "changed" not in d)
t0 = time.monotonic()
e = t.look(1, c["v"], 0.4)
check(f"...waiting for a change that doesn't come: as long as asked ({time.monotonic() - t0:.2f} s)",
      0.35 <= time.monotonic() - t0 < 1.0 and e["v"] == c["v"])
import threading
threading.Timer(0.2, lambda: console(4, 20, 0, 2, ["$ ls", "Music", "$ ", ""])).start()
t0 = time.monotonic()
f = t.look(1, c["v"], 5)
check(f"...one that does: as it does ({time.monotonic() - t0:.2f} s, row {sorted(f['changed'])})",
      time.monotonic() - t0 < 1.0 and sorted(f["changed"]) == ["2"])
stop = [False]
t0 = time.monotonic()
g = t.look(1, f["v"], 5, still=lambda: not stop[0] and time.monotonic() - t0 < 0.3)
check(f"...stops waiting when told to (media mode on: {time.monotonic() - t0:.2f} s)", time.monotonic() - t0 < 1.0)
console(6, 30, 0, 0, ["bigger", "", "", "", "", ""])
h = t.look(1, f["v"], 0)
check("...the console a new size: all of it", "lines" in h and h["rows"] == 6 and h["cols"] == 30)
check("a console that can't be read: said so", "error" in t.look(9))

# ---- passwords ------------------------------------------------------------------------------------------------------
lib = ctypes.CDLL(ctypes.util.find_library("crypt") or "libcrypt.so.1")
lib.crypt.restype, lib.crypt.argtypes = ctypes.c_char_p, (ctypes.c_char_p, ctypes.c_char_p)
sha = lib.crypt(b"right one", b"$6$saltsaltsalt$").decode()
try:
    lib.crypt_gensalt.restype = ctypes.c_char_p
    lib.crypt_gensalt.argtypes = (ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_int)
    ys = lib.crypt(b"another", lib.crypt_gensalt(b"$y$", 0, None, 0)).decode()
except AttributeError:
    ys = None
open(S + "/shadow", "w").write(
    f"root:*:19000:0:99999:7:::\n"
    f"pi:{sha}:19000:0:99999:7:::\n"
    + (f"yes:{ys}:19000:0:99999:7:::\n" if ys else "")
    + "locked:!$6$x$y:19000:0:99999:7:::\nnone::19000:0:99999:7:::\n")
check("the right password (a SHA-512 hash): yes", T.password_ok("pi", "right one", S + "/shadow") is True)
check("...a wrong one: no", T.password_ok("pi", "wrong one", S + "/shadow") is False)
if ys:
    check(f"...yescrypt's (Raspberry Pi OS's own): yes, and no ({ys[:4]})",
          T.password_ok("yes", "another", S + "/shadow") is True and T.password_ok("yes", "nope", S + "/shadow") is False)
check("...a locked account, one with none, root's starred one, someone not there: no telling",
      T.password_ok("locked", "x", S + "/shadow") is None and T.password_ok("none", "", S + "/shadow") is None
      and T.password_ok("root", "x", S + "/shadow") is None and T.password_ok("nobody", "x", S + "/shadow") is None)
check("...no shadow file to read: no telling", T.password_ok("pi", "right one", S + "/nothing") is None)

A, B = "192.168.1.20", "192.168.1.30"
got = t.unlock("pi", "right one", A)
check(f"unlocked: a key for the page ({len(got.get('key') or '')} letters)", got.get("ok") and len(got["key"]) >= 30)
key = got["key"]
check("...good", t.check(key) and not t.check(key + "x") and not t.check("") and not t.check(None)
      and not t.check(["x"]) and not t.check("\ud800") and not t.check("k" * 5000))
t0 = time.monotonic()
w = t.unlock("pi", "wrong", A)
check(f"a wrong password: said so, after a moment ({w}, {time.monotonic() - t0:.2f} s)",
      w.get("kind") == "wrong" and "error" in w and time.monotonic() - t0 >= T.TERM_WRONG_WAIT)
check(f"...counted, and kept on disk, only root's to read ({open(S + '/tries.json').read()[:60]}, "
      f"{oct(os.stat(S + '/tries.json').st_mode & 0o777)})",
      len(t.wrong) == 1 and t.wrong[0][1] == A and json.load(open(S + "/tries.json"))[0][1] == A
      and os.stat(S + "/tries.json").st_mode & 0o077 == 0)
check(f"...none: said so ({t.unlock('pi', '', A)})", "error" in t.unlock("pi", "", A) and len(t.wrong) == 1)
none = t.unlock("none", "x", A)
check(f"...an account with no password: how to give one, its name not said ({none['error']})",
      "passwd" in none["error"] and "none" not in none["error"].replace("none set", ""))
for odd in ("right one\x00junk", "x" * 600, "\ud800abc"):
    w = t.unlock("pi", odd, B)
    check(f"...one libcrypt couldn't check whole ({odd[:12]!r}, {len(odd)} long): wrong, and counted ({w})",
          w.get("kind") == "wrong")
t.wrong = [x for x in t.wrong if x[1] != B]
for _ in range(4):
    t.unlock("pi", "wrong", A)
z = t.unlock("pi", "right one", A)
check(f"five wrong from one address: not even the right one from it for a minute ({z})",
      "error" in z and z["error"].endswith("in a minute"))
other = t.unlock("pi", "right one", B)
check(f"...but from another address: yes ({sorted(other)})", other.get("ok"))
check("...and that didn't forget the first one's wrong ones", "minute" in t.unlock("pi", "right one", A).get("error", ""))
t2 = T.Terminal(shadow=S + "/shadow")
check("...nor does a restart: they're on disk", "minute" in t2.unlock("pi", "right one", A).get("error", ""))
for x in t.wrong:
    x[0] -= 61
check("a minute on: the right one again, and that address's wrong ones forgotten",
      t.unlock("pi", "right one", A).get("ok") and not any(a == A for _, a in t.wrong))
now = time.time()
t.wrong = [[now - 3000 + i, A] for i in range(5)]
w = t.unlock("pi", "wrong", A)
z = t.unlock("pi", "right one", A)
check(f"a wrong one after the minute: two minutes' wait now ({z.get('error')})", z.get("error", "").endswith("2 minutes"))
t.wrong = [[now - 30000 + i * 10, A] for i in range(12)] + [[now - 5, A]]
z = t.unlock("pi", "right one", A)
check(f"...doubling, each time, an hour at most ({z.get('error')})",
      z.get("error", "").endswith(" minutes") and 55 <= int(z["error"].split()[-2]) <= 60)
t.wrong = [[now - 90000, A]] * 9
check("...a day on: forgotten", t.unlock("pi", "right one", A).get("ok") and t.wrong == [])
t.wrong = [[now - 600 + i, f"10.0.0.{i}"] for i in range(20)]
z = t.unlock("pi", "right one", "10.0.0.99")
check(f"twenty wrong in an hour, from all over: no tries from anywhere for the rest of it ({z.get('error')})",
      z.get("error", "").endswith(" minutes") and 49 <= int(z["error"].split()[-2]) <= 51)
t.wrong = [[now + 7200, A]] * 9
check("wrong ones from the future (the clock gone back): not counted", t.unlock("pi", "right one", A).get("ok"))
t.wrong = []
import threading
checked = []
real_ok = T.password_ok
T.password_ok = lambda *a: (checked.append(1), real_ok(*a))[1]
answers = []
tries = [threading.Thread(target=lambda: answers.append(t.unlock("pi", "wrong", A))) for _ in range(12)]
for th in tries:
    th.start()
for th in tries:
    th.join()
T.password_ok = real_ok
check(f"twelve wrong ones sent at once: only five checked, the rest turned away ({len(checked)} checked, "
      f"{sum('minute' in a.get('error', '') for a in answers)} turned away)",
      len(checked) == 5 and sum("minute" in a.get("error", "") for a in answers) == 7)
check("...and the right one waits its minute too", "minute" in t.unlock("pi", "right one", A).get("error", ""))
t.wrong = []
t.forget(key)
check("Lock: the page's key given back, no good now", not t.check(key))
keys = [t.unlock("pi", "right one", A)["key"] for _ in range(10)]
check(f"at most eight keys: the oldest go ({len(t.keys)})", len(t.keys) == 8 and not t.check(keys[0])
      and t.check(keys[-1]))
t.keys[keys[-1]]["used"] = time.monotonic() - T.TERM_KEY_IDLE - 1
check("a key not used for half an hour: no good", not t.check(keys[-1]))
t.keys[keys[-2]]["made"] = time.monotonic() - T.TERM_KEY_MOST - 1
check("...nor one given twelve hours ago, however much it's used", not t.check(keys[-2]))
check("...the others still good", t.check(keys[-3]) and t.check(keys[-4]))
old = open(S + "/shadow").read()
open(S + "/shadow", "w").write(old.replace(sha, lib.crypt(b"a new one", b"$6$othersalt$").decode()))
for k in t.keys.values():
    k["seen"] -= T.TERM_HASH_LOOK
check("your password changed: every page's key no good", not t.check(keys[-3]) and not t.check(keys[-4])
      and not t.keys)
open(S + "/shadow", "w").write(old)

# ---- typing --------------------------------------------------------------------------------------------------------
master, slave = pty.openpty()
os.symlink(os.ttyname(slave), S + "/tty3")
r = t.type(3, "ls -l\r")
typed = b""
for _ in range(20):
    if select.select([slave], [], [], 0.05)[0]:
        typed += os.read(slave, 1000)
    if b"ls -l" in typed:
        break
check(f"typed: into the terminal as if on its keyboard ({r}, it read {typed!r})", r == {"ok": True} and b"ls -l" in typed)
r = t.type(3, "é☺\r")                            # (a line at a time, as the terminal hands them on)
typed = b""
for _ in range(20):
    if select.select([slave], [], [], 0.05)[0]:
        typed += os.read(slave, 1000)
    if "☺".encode() in typed:
        break
check(f"...any letter, as UTF-8 ({typed!r})", typed == "é☺\n".encode())
check("...nothing: nothing", t.type(3, "") == {"ok": True})
check("...too much at once: said so", "error" in t.type(3, "x" * (T.TYPE_MOST + 1)))
check("...a console that isn't there: said so", "error" in t.type(8, "x"))
os.close(master); os.close(slave)

# ---- media mode's side: web_term ---------------------------------------------------------------------------------------
from pitato.screens import web as W


class M(W.WebScreen):
    def __init__(self):
        self.term, self.active, self.prev_vt = T.Terminal(shadow=S + "/shadow"), False, "1"

    def term_user(self):
        return "pi"


m = M()
console(4, 20, 2, 0, ["$ ", "", "", ""])
check(f"web_term without a key: locked ({m.web_term({'do': 'look'})})", m.web_term({"do": "look"}).get("kind") == "locked")
k = m.web_term({"do": "unlock", "password": "right one"})["key"]
look = m.web_term({"do": "look", "key": k})
check(f"...with one: the terminal ({look.get('rows')} x {look.get('cols')})", look.get("ok") and look["rows"] == 4)
m.active = True
check("...media mode on: it says so", m.web_term({"do": "look", "key": k}).get("kind") == "media"
      and m.web_term({"do": "type", "key": k, "text": "x"}).get("kind") == "media")
m.active = False
check("...Lock", m.web_term({"do": "lock", "key": k}) == {"ok": True}
      and m.web_term({"do": "look", "key": k}).get("kind") == "locked")
check("...nonsense asked for: said so", "error" in m.web_term({"do": "rm -rf", "key": m.web_term(
    {"do": "unlock", "password": "right one"})["key"]}))
os.remove(T.ACTIVE)
check(f"no telling which console's in front: the one media mode went back to ({m.term_vt()})", m.term_vt() == 1)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
