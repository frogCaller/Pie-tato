"""Two players on two Pietatos, one game: the emulators keep in step, frame by frame (lockstep). One (the host, player 1)
is already playing; the other (player 2) joins it over your network, starts from the host's game as it is at that
moment (its save state), and from then on each frame runs on both only once both players' buttons for it are there.
Each sends its buttons a few frames ahead (the delay), so on your network neither waits. The same start and the same
buttons make the same game on both; now and then they check (a sum of the game's own memory), and one that's got out
of step takes the host's state again. Pausing on one pauses both; one leaving says so to the other.

A message: its kind (a byte), its length (4 bytes), then what it says. pitato/emulator.py runs it (--net, nethost)."""
import json
import socket
import struct
import threading
import time
import zlib

NET_PORT = 5442              # the host's game listens for the other one here
NET_DELAY = 3                # frames each side's buttons are sent ahead (50 ms: your network's well within that)
NET_WAIT = 6.0               # seconds without the other's buttons before it's taken to have gone
NET_CHECK = 120              # frames between checks that both games are the same (every two seconds)
NET_KEEP = 900               # frames of buttons kept (to play again from a state taken a moment ago)
NET_STATE_MOST = 64 << 20    # bytes: a game's state, at most
NET_HELLO_WAIT = 10.0        # seconds the two have to say hello
HEADER = struct.Struct(">cI")
MSG_HELLO, MSG_STATE, MSG_BUTTONS, MSG_CHECK = b"H", b"S", b"I", b"C"   # (a message's kind)
MSG_AGAIN, MSG_PAUSE, MSG_RESUME, MSG_BYE = b"X", b"P", b"R", b"B"


class Gone(Exception):
    """The other Pietato's game has gone (it said so, or it stopped answering)."""


def game_sum(data):
    """A sum of a game's state, to tell whether two are the same."""
    return zlib.crc32(data) & 0xFFFFFFFF if data else 0


class Link:
    """This game's side of two keeping in step: what it sends, and what the other has sent (read on a thread of its
    own as it comes)."""

    def __init__(self, sock, host, delay=NET_DELAY):
        self.sock = sock
        self.host = host                              # player 1 (its game is the one they play), or player 2
        self.delay = delay
        self.sock.settimeout(None)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.cond = threading.Condition()
        self.mine, self.theirs = {}, {}               # frame -> buttons (this one's, the other's)
        self.sums = {}                                # frame -> the other's sum of its game then
        self.states = []                              # (frame, state) the host's sent (to start from, or again)
        self.again = None                             # (the host) the frame the other asked to start again from
        self.paused = False                           # the other's menu is up
        self.start = 0                                # the frame the two started together at
        self.gone = None                              # why the other's gone (None: it's there)
        self.hello = None                             # what the other said it is
        self.sending = threading.Lock()
        self.reader = threading.Thread(target=self.read, daemon=True, name="netplay")
        self.reader.start()

    # -- sending ------------------------------------------------------------------------------------------------
    def send(self, kind, data=b""):
        try:
            with self.sending:
                self.sock.sendall(HEADER.pack(kind, len(data)) + data)
            return True
        except OSError as ex:
            self.lost(f"it stopped answering ({ex.strerror or ex})")
            return False

    def say_hello(self, about):
        self.send(MSG_HELLO, json.dumps(about).encode())

    def send_state(self, frame, data):
        self.send(MSG_STATE, struct.pack(">I", frame) + data)

    def send_sum(self, frame, total):
        self.send(MSG_CHECK, struct.pack(">II", frame, total))

    def ask_again(self, frame):
        self.send(MSG_AGAIN, struct.pack(">I", frame))

    def pause(self, on):
        self.send(MSG_PAUSE if on else MSG_RESUME)

    def bye(self):
        self.send(MSG_BYE)
        self.close()

    # -- reading ------------------------------------------------------------------------------------------------
    def read_exactly(self, n):
        out = bytearray()
        while len(out) < n:
            chunk = self.sock.recv(min(1 << 20, n - len(out)))
            if not chunk:
                raise Gone("it's gone")
            out += chunk
        return bytes(out)

    def read(self):
        try:
            while True:
                kind, n = HEADER.unpack(self.read_exactly(HEADER.size))
                if n > NET_STATE_MOST + 16:
                    raise Gone("it said something too big")
                data = self.read_exactly(n)
                with self.cond:
                    if kind == MSG_BUTTONS and n == 8:
                        frame, held = struct.unpack(">II", data)
                        self.theirs[frame] = held
                    elif kind == MSG_HELLO:
                        self.hello = json.loads(data.decode())
                    elif kind == MSG_STATE and n >= 4:
                        self.states.append((struct.unpack(">I", data[:4])[0], data[4:]))
                    elif kind == MSG_CHECK and n == 8:
                        frame, total = struct.unpack(">II", data)
                        self.sums[frame] = total
                    elif kind == MSG_AGAIN and n == 4:
                        self.again = struct.unpack(">I", data)[0]
                    elif kind == MSG_PAUSE:
                        self.paused = True
                    elif kind == MSG_RESUME:
                        self.paused = False
                    elif kind == MSG_BYE:
                        raise Gone("it left")
                    self.cond.notify_all()
        except (Gone, OSError, ValueError, struct.error) as ex:
            self.lost(str(ex) if isinstance(ex, Gone) else "it stopped answering")

    def lost(self, why):
        with self.cond:
            if self.gone is None:
                self.gone = why
            self.cond.notify_all()

    def wait_for(self, what, timeout):
        """Waits (up to timeout seconds) till what() is true; it's what() then. Gone, if the other's gone."""
        end = time.monotonic() + timeout
        with self.cond:
            while True:
                got = what()
                if got or self.gone is not None:
                    break
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
            if not got and self.gone is not None:
                raise Gone(self.gone)
            return got

    def other(self, timeout=NET_HELLO_WAIT):
        """What the other said it is (its hello)."""
        got = self.wait_for(lambda: self.hello, timeout)
        if not got:
            raise Gone("it didn't say hello")
        return got

    def first_state(self, timeout=NET_HELLO_WAIT):
        """(the frame, the state) the host's game was at as this one joined it."""
        got = self.wait_for(lambda: self.states[:1], timeout)
        if not got:
            raise Gone("its game didn't come")
        with self.cond:
            return self.states.pop(0)

    def new_state(self):
        """A state the host's sent again (the two had got out of step): (frame, state), or None."""
        with self.cond:
            return self.states.pop(0) if self.states else None

    def asked_again(self):
        with self.cond:
            frame, self.again = self.again, None
            return frame

    # -- a frame ------------------------------------------------------------------------------------------------
    def begin(self, frame):
        """The two start together at this frame (nobody's pressed anything for the first few)."""
        self.start = frame

    def fill(self, frame, held):
        """This one's buttons for the frames from this one on that it hasn't sent yet (it's jumped ahead, to the
        host's state), so the other isn't left waiting for them."""
        for f in range(frame, frame + self.delay + 1):
            if f not in self.mine:
                self.mine[f] = held
                self.send(MSG_BUTTONS, struct.pack(">II", f, held))

    def buttons(self, frame, held, timeout=NET_WAIT):
        """This frame's buttons for both: this one's (held now) go to the other for frame + delay, and the other's
        for this frame are waited for. (player 1's, player 2's). Gone if the other's gone (at once, even with its
        buttons for the next few frames here) or never sent them. None: the other's menu is up (no frame now)."""
        with self.cond:
            if self.gone is not None:
                raise Gone(self.gone)
        ahead = frame + self.delay
        if ahead not in self.mine:
            self.mine[ahead] = held
            self.send(MSG_BUTTONS, struct.pack(">II", ahead, held))
        with self.cond:
            if self.paused:
                return None                             # (its menu's up: both wait, at once)
        if frame < self.start + self.delay:            # (the first few: nobody's pressed anything yet)
            theirs, mine = 0, 0
        else:
            got = self.wait_for(lambda: frame in self.theirs or self.paused, timeout)
            if not got:
                raise Gone("it stopped answering")
            with self.cond:
                if frame not in self.theirs:
                    return None                         # (paused there)
                theirs = self.theirs[frame]
            mine = self.mine.get(frame, 0)
        if frame % 64 == 0:                            # (the old ones go)
            for d in (self.mine, self.theirs):
                for f in [f for f in d if f < frame - NET_KEEP]:
                    del d[f]
        return (mine, theirs) if self.host else (theirs, mine)

    def their_sum(self, frame):
        with self.cond:
            return self.sums.pop(frame, None)

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class Listener:
    """The host's game, waiting for the other to join (polled between frames: it never holds a frame up)."""

    def __init__(self, port, key, allow=None):
        self.key, self.allow = key, allow
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen(1)
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]

    def take(self):
        """The other's connection, once it's come (from the address allowed, if one's said), or None."""
        try:
            conn, addr = self.sock.accept()
        except (BlockingIOError, OSError):
            return None
        if self.allow and addr[0] != self.allow:
            conn.close()
            return None
        conn.setblocking(True)
        return conn

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def join(addr, port, timeout=NET_HELLO_WAIT):
    """The host's game, joined: the connection."""
    return socket.create_connection((addr, port), timeout=timeout)
