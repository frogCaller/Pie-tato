"""Two Pietatos keeping one game in step (pitato/netplay.py), its messages on their own: the host's game open to the
other (only from the address it's told), the two saying hello, the host's game as it is sent over; then frame by
frame each one's buttons for both, the same on both, each sent a few frames ahead (nobody's for the first few), and
neither waiting on your network; a pause on one stops both (at once, not a wait for the other); the host's game
again when the other asks; a sum for checking both games are the same; and one leaving, said to the other at once
(and one that's stopped answering, after a while)."""
import socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from pitato import netplay as N

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def taken(lis, secs=3.0):
    end = time.time() + secs
    while time.time() < end:
        conn = lis.take()
        if conn is not None:
            return conn
        time.sleep(0.01)
    return None


# ---- open to the other, from its address only -------------------------------------------------------------------------
lis = N.Listener(0, "k" * 22, allow="10.11.12.13")
cli = N.join("127.0.0.1", lis.port)
check("from an address it wasn't told: not let in", taken(lis, 0.5) is None)
cli.settimeout(2)
try:
    shut = cli.recv(1) == b""
except OSError:
    shut = True
check("...and its connection closed", shut)
cli.close()
lis.close()
lis = N.Listener(0, "k" * 22, allow="127.0.0.1")
check("the host's game polls for the other without waiting (nobody yet)", lis.take() is None)
cli = N.join("127.0.0.1", lis.port)
conn = taken(lis)
check("from the address it was told: let in", conn is not None)
lis.close()
host, guest = N.Link(conn, host=True), N.Link(cli, host=False)

# ---- hello, and the host's game as it is -------------------------------------------------------------------------------
host.say_hello({"v": 1, "core": "Genesis Plus GX 1.7.4", "game": "ab" * 20, "who": "tv"})
said = guest.other()
guest.say_hello({"v": 1, "core": "Genesis Plus GX 1.7.4", "game": "ab" * 20, "who": "gpi", "key": "k" * 22})
check(f"each says what it is: its emulator, its game, who it is ({said['who']}, {host.other()['who']})",
      said["core"] == "Genesis Plus GX 1.7.4" and host.other()["key"] == "k" * 22)
STATE = bytes(range(256)) * 4000                       # (a megabyte: a big game's)
host.send_state(500, STATE)
frame, state = guest.first_state()
check(f"the host's game, as it is, to the other: frame {frame}, {len(state)} bytes", frame == 500 and state == STATE)
host.begin(500)
guest.begin(500)

# ---- frame by frame: the same buttons on both --------------------------------------------------------------------------
FRAMES = 600
mine = {"host": lambda f: (f * 7) & 0xFFF, "guest": lambda f: (f * 13 + 5) & 0xFFF}
got = {"host": [], "guest": []}
waits = {"host": 0.0, "guest": 0.0}


def play(link, who):
    for f in range(500, 500 + FRAMES):
        t = time.perf_counter()
        both = link.buttons(f, mine[who](f))
        waits[who] = max(waits[who], time.perf_counter() - t)
        got[who].append(both)
        time.sleep(1 / 240)                            # (quicker than a game: the two needn't keep the same time)


ths = [threading.Thread(target=play, args=(host, "host")), threading.Thread(target=play, args=(guest, "guest"))]
for t in ths:
    t.start()
for t in ths:
    t.join(30)
want = [(0, 0)] * N.NET_DELAY + [(mine["host"](f - N.NET_DELAY), mine["guest"](f - N.NET_DELAY))
                                 for f in range(500 + N.NET_DELAY, 500 + FRAMES)]
check(f"{FRAMES} frames: both see the same buttons for each, player 1's the host's", got["host"] == got["guest"]
      == want)
check(f"...each frame's buttons the ones pressed {N.NET_DELAY} frames before, nobody's for the first {N.NET_DELAY}",
      got["host"][:N.NET_DELAY] == [(0, 0)] * N.NET_DELAY and got["host"][N.NET_DELAY][0] == mine["host"](500))
check(f"...neither waiting long for the other (at most {max(waits.values()) * 1000:.0f} ms)",
      max(waits.values()) < 0.5)
check("...the old ones not kept for ever", len(host.mine) <= N.NET_KEEP + 70 and len(guest.theirs) <= N.NET_KEEP + 70)

# ---- a pause on one stops both, at once --------------------------------------------------------------------------------
f = 500 + FRAMES
host.pause(True)
time.sleep(0.1)                                        # (as long as it takes to come: a moment)
t = time.perf_counter()
paused = guest.buttons(f, 0)
check(f"the host's menu up: the other's frame waits, at once, though the host's buttons for it are there "
      f"({(time.perf_counter() - t) * 1000:.0f} ms, {paused})", paused is None and time.perf_counter() - t < 0.2
      and f in guest.theirs)
host.pause(False)
time.sleep(0.2)
check("...back to the game: on they go", guest.paused is False)

# ---- the host's game again, a sum, ---------------------------------------------------------------------------------------
guest.ask_again(f)
time.sleep(0.2)
check("the other asks for the host's game again (out of step)", host.asked_again() == f and host.asked_again() is None)
host.send_state(f, b"again")
time.sleep(0.2)
check("...and it comes", guest.new_state() == (f, b"again") and guest.new_state() is None)
host.send_sum(720, N.game_sum(b"abc"))
time.sleep(0.2)
check("a sum of the host's game, for checking", guest.their_sum(720) == N.game_sum(b"abc") and N.game_sum(b"abc")
      != N.game_sum(b"abd") and guest.their_sum(720) is None)

# ---- one leaves ----------------------------------------------------------------------------------------------------------
host.bye()
time.sleep(0.1)
t = time.perf_counter()
try:
    guest.buttons(f + 1, 0)
    why = None
except N.Gone as ex:
    why = str(ex)
check(f"the host leaves: the other knows at once ({why}, {(time.perf_counter() - t) * 1000:.0f} ms)",
      why == "it left" and time.perf_counter() - t < 1.0)
guest.close()

# ---- one that stops answering ------------------------------------------------------------------------------------------
a, b = socket.socketpair()
quiet, talker = N.Link(a, host=True, delay=1), N.Link(b, host=False, delay=1)
quiet.begin(0)
talker.begin(0)
t = time.perf_counter()
try:
    talker.buttons(1, 0, timeout=0.5)
    why = None
except N.Gone as ex:
    why = str(ex)
check(f"one that stops answering: the other's told, after a while ({why})", why == "it stopped answering"
      and 0.4 < time.perf_counter() - t < 2.0)
quiet.close()
talker.close()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
