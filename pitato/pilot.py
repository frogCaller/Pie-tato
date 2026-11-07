"""One of your Pietatos controlling another: its buttons as a controller plugged into the other one
(screens/pilot.py: Home > Control another Pietato; app.py: the buttons).

The one in your hand asks the other's web page (POST /api/pilot: from your network, both with Settings > Share with
other Pietatos on, and with the page's password if it has one: the page's remote can't do more), and the other answers
with a UDP port and a key. From then on, each time a button goes down or up,
the one in hand sends a packet: what's held now, and how many times each button has gone down, numbered. It sends the
same again a moment later (WiFi can lose one), and now and then while nothing changes, to say it's still there. The
other takes the newest and presses and lets go of what's changed; a press lost on the way is made up from the count. It
answers each packet with its number, so the one in hand can say it's in touch.

A packet: {"k": key, "n": number, "d": [held], "c": {button: times down}}, as JSON (or {"k": key, "bye": 1}). Its
answer: {"n": number}, or {"gone": 1} from one that doesn't know the key (it's been restarted, say: ask again).

The other one, hearing nothing for a second while something's held, lets go of it (so nothing's left held down when
the WiFi goes); after PILOT_GONE seconds of nothing, the one in hand's taken to have gone."""
import base64
import hmac
import json
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .inputs import BUTTONS, MEDIA_TOGGLE

PILOT_MOST = 4            # Pietatos controlling one at once (a player each, in a game)
PILOT_PACKET = 1024       # bytes: a packet, at most
PILOT_AGAIN = (0.03, 0.1)  # seconds after a change it's sent again (one lost on the way, made up)
PILOT_BEAT_HELD = 0.25    # seconds between packets while something's held, nothing changing
PILOT_BEAT = 1.0          # ...and while nothing is
PILOT_HOLD_LOST = 1.0     # seconds of nothing from it while something's held: let go of there
PILOT_GONE = 12.0         # seconds of nothing from it: it's gone
PILOT_QUIET = 3.0         # seconds without an answer before the one in hand says it isn't answering
PILOT_ASK_AGAIN = 3.0     # seconds between asks, to get in touch again
PILOT_ASK_WAIT = 6.0      # seconds the other's web page has to answer an ask
PILOT_LET_GO = 2.0        # seconds HOME is held on its own, on the one in hand, to let go of the other one
TAPS_MOST = 3             # presses lost on the way, made up for: at most this many at once
PILOT_KEY = re.compile(r"[A-Za-z0-9_-]{16,64}")


# ---- packets ---------------------------------------------------------------------------------------------------------
def packet(key, n, held, counts):
    """What's held now, and how many times each button's gone down: a packet's bytes."""
    return json.dumps({"k": key, "n": n, "d": sorted(held), "c": {b: c for b, c in sorted(counts.items()) if c}},
                      separators=(",", ":")).encode()


def bye_packet(key):
    return json.dumps({"k": key, "bye": 1}, separators=(",", ":")).encode()


def read_packet(data):
    """A packet, checked: {"k", "bye": True}, or {"k", "n", "d": a set, "c": a dict, "bye": False}; None when it
    isn't one (names it doesn't know are left out)."""
    if not data or len(data) > PILOT_PACKET:
        return None
    try:
        p = json.loads(data)
    except ValueError:
        return None
    if not isinstance(p, dict):
        return None
    key = p.get("k")
    if not isinstance(key, str) or not PILOT_KEY.fullmatch(key):
        return None
    if p.get("bye") == 1:
        return {"k": key, "bye": True}
    n, held, counts = p.get("n"), p.get("d", []), p.get("c", {})
    if (isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < 1 << 53 or not isinstance(held, list)
            or not isinstance(counts, dict) or len(held) > len(BUTTONS) or len(counts) > len(BUTTONS)):
        return None
    return {"k": key, "bye": False, "n": n, "d": {b for b in held if b in BUTTONS},
            "c": {b: c for b, c in counts.items()
                  if b in BUTTONS and isinstance(c, int) and not isinstance(c, bool) and 0 <= c < 1 << 31}}


def changes(held, counts, now_held, now_counts):
    """What to press and let go of, in order, to go from what's held there (and how many times each has gone down) to
    what the one in hand says now: [(button, down)]. A press it hasn't heard about (the count's gone up by more than it
    saw) is made up, as a quick press. What's let go of comes first, then HOME (pressed before what's pressed with it,
    for a Konami code), then the rest."""
    first, home, rest = [], [], []
    for b in BUTTONS:
        was, now = b in held, b in now_held
        more = min(max(0, now_counts.get(b, 0) - counts.get(b, 0)), TAPS_MOST)
        if not more:
            steps = [] if was == now else [(b, now)]
        else:
            steps = ([(b, False)] if was else []) + [(b, True), (b, False)] * (more - 1) + [(b, True)]
            if not now:
                steps.append((b, False))
        if b == MEDIA_TOGGLE:
            home = steps
        elif steps == [(b, False)]:
            first += steps
        else:
            rest += steps
    return first + home + rest


# ---- the one being controlled: a controller for each one controlling it ----------------------------------------------
class PilotDev:
    """A PilotPad's stand-in for an input device: its name (the other Pietato's), and nothing to read or close."""
    info = None

    def __init__(self, name, path):
        self.name, self.path = name, path

    def capabilities(self, *a, **k):
        return {}

    def close(self):
        pass


class PilotPad:
    """Another of your Pietatos controlling this one, as a controller plugged in here: Pads' by_path has it while it
    is (a player of its own in a game; Settings > Swap A and B, kept for it by its name; the web page's list of
    controllers). Its buttons come named already, HOME too (the one in hand's SELECT and START together, or its
    star)."""
    kind = "pilot"
    learned = False
    home = True
    own_dpad = False

    def __init__(self, path, name, has=None):
        self.path, self.dev = path, PilotDev(name, path)
        self.ident = "pilot:" + name
        self.names = {b for b in (has or ()) if b in BUTTONS} or set(BUTTONS)   # (the buttons the one in hand has)
        self.keys, self.axes, self.triggers, self.sticks, self.info = {}, {}, {}, {}, {}
        self.now, self.down = {}, set()
        self.swapped = False

    def apply(self, learned=None):
        """Settings > Swap A and B on it: A and B the other way round, here."""
        self.swapped = isinstance(learned, dict) and bool(learned.get("swap"))

    def has_stick(self):
        return False

    def dpad_apart(self):
        return False

    def has_button(self, name):
        return name in self.names

    def stick(self, ev):
        return None

    def sticks_now(self):
        return []

    def axis_codes(self):
        return []

    def translate(self, ev):
        return []


class PilotSession:
    """One of your Pietatos controlling this one: its key and address, its controller here, and what it's said."""

    def __init__(self, key, addr, name, pad, now):
        self.key, self.addr, self.name, self.pad = key, addr, name, pad
        self.held, self.counts, self.n = set(), {}, -1   # (what's been pressed here for it, as of packet n)
        self.seen = now                                  # when it was last heard from
        self.lost = False                                # quiet a while: what it held, let go of

    def holding(self):
        """What's held down here for it now."""
        return set() if self.lost else set(self.held)


class Pilots:
    """Your other Pietatos controlling this one (the main loop's, in app.py): their buttons come in on one UDP port,
    open while any is."""

    def __init__(self):
        self.sock, self.port, self.sessions, self.made = None, 0, [], 0

    def open(self):
        """The port, opened if it isn't: True when it's just been opened (for the main loop to watch it)."""
        if self.sock is not None:
            return False
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", 0))
            s.setblocking(False)
        except OSError:
            s.close()
            raise
        self.sock, self.port = s, s.getsockname()[1]
        return True

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock, self.port = None, 0

    def add(self, addr, name, has, now):
        """A new one controlling this one: its session (a new key, and a controller here), or None when PILOT_MOST
        already are."""
        if len(self.sessions) >= PILOT_MOST:
            return None
        self.made += 1
        sess = PilotSession(secrets.token_urlsafe(18), addr, name, PilotPad(f"pilot:{addr}:{self.made}", name, has),
                            now)
        self.sessions.append(sess)
        return sess

    def of(self, addr):
        """The one controlling this one from that address, or None."""
        return next((s for s in self.sessions if s.addr == addr), None)

    def find(self, key, addr):
        """The session with that key, from that address (None: there's none)."""
        if not isinstance(key, str):
            return None
        return next((s for s in self.sessions if s.addr == addr and hmac.compare_digest(s.key.encode(), key.encode())),
                    None)

    def remove(self, sess):
        self.sessions = [s for s in self.sessions if s is not sess]

    def take(self, now):
        """What's come in on the port, in order: ("press", session, button, down), and ("bye", session) for one
        letting go of this one. Each packet's answered with its number, or that its key's gone."""
        out = []
        for _ in range(64):                            # (at most this many at once: the screen gets its turn)
            try:
                data, frm = self.sock.recvfrom(PILOT_PACKET + 1)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:                            # (an error from the last answer sent, say: the next one)
                continue
            out += self.packet_in(data, frm, now)
        return out

    def packet_in(self, data, frm, now):
        p = read_packet(data)
        if p is None:
            return []
        sess = self.find(p["k"], frm[0])
        if sess is None:
            self.answer(frm, {"gone": 1})
            return []
        sess.seen = now
        if p["bye"]:
            return [("bye", sess)]
        self.answer(frm, {"n": p["n"]})
        if p["n"] < sess.n or (p["n"] == sess.n and not sess.lost):
            return []                                  # (an older one, or the same one again)
        steps = changes(set() if sess.lost else sess.held, sess.counts, p["d"], p["c"])
        sess.held, sess.counts, sess.n, sess.lost = set(p["d"]), dict(p["c"]), p["n"], False
        return [("press", sess, b, down) for b, down in steps]

    def answer(self, to, what):
        try:
            self.sock.sendto(json.dumps(what, separators=(",", ":")).encode(), to)
        except OSError:
            pass

    def check(self, now):
        """Each one's quiet: what it held let go of after PILOT_HOLD_LOST seconds (its WiFi lost, or its battery),
        and it's gone after PILOT_GONE: ("press", session, button, False) and ("gone", session)."""
        out = []
        for sess in list(self.sessions):
            quiet = now - sess.seen
            if quiet >= PILOT_GONE:
                out.append(("gone", sess))
            elif quiet >= PILOT_HOLD_LOST and sess.held and not sess.lost:
                out += [("press", sess, b, down) for b, down in changes(sess.held, sess.counts, set(), sess.counts)]
                sess.lost = True                       # (heard from again: what it holds then, pressed again)
        return out

    def next_due(self):
        """When check next has something to do (inf: never)."""
        return min((s.seen + (PILOT_HOLD_LOST if s.held and not s.lost else PILOT_GONE) for s in self.sessions),
                   default=float("inf"))


# ---- the one in hand ------------------------------------------------------------------------------------------------
def ask_post(url, body, timeout, password=None):
    """Another Pietato's web page's answer (a dict), or None when it doesn't answer. It answered no: what it said, with
    its status (401: it wants its password). With its password, if it's been given one."""
    headers = {"Content-Type": "application/json", "User-Agent": "Pietato"}
    if password:
        headers["Authorization"] = "Basic " + base64.b64encode(f"pietato:{password}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            got = json.loads(r.read(1 << 16))
    except urllib.error.HTTPError as ex:
        try:
            said = json.loads(ex.read(1 << 16))
        except (OSError, ValueError):
            said = {}
        return dict(said if isinstance(said, dict) else {}, ok=False, status=ex.code)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


class PilotOut:
    """This Pietato's buttons, sent to another of yours while it controls it. press() sends a change at once (the main
    loop's); a thread of its own asks the other one first, sends each change again a moment later and now and then
    while nothing changes, and hears its answers."""

    def __init__(self, url, name, has=(), changed=None, post=None, password=None):
        self.url, self.name, self.password = url, name, password   # (its web page's password, if it has one)
        self.host = urllib.parse.urlsplit(url).hostname or ""
        self.has = sorted(b for b in has if b in BUTTONS)
        self.changed = changed or (lambda: None)       # (how it's going has changed: drawn again)
        self.post = post or ask_post
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.sock, self.key = None, None
        self.held, self.counts, self.n = set(), {}, 0
        self.again = []                                # when the last change is to be sent again
        self.sent = 0.0                                # when a packet last went
        self.state, self.why = "asking", ""            # asking, on, or failed (why: what it said, or that it didn't)
        self.was_on = False
        self.heard = 0.0                               # when it last answered
        self.home_at = None                            # HOME down here, not sent yet (held long: let go of the other)
        self.home_sent = False                         # ...sent after all, as another button went down with it
        self.done = False
        threading.Thread(target=self.loop, daemon=True, name="pilot").start()

    # -- the main loop's ---------------------------------------------------------------------------------------------
    def press(self, name, down):
        """A button here, down or up, for the other one. HOME isn't sent as it goes down: let go of quickly, it's a
        press of HOME there; with another button pressed while it's held, it goes down first (a Konami code there);
        held on its own for PILOT_LET_GO seconds, it lets go of the other one (home_held says how long)."""
        with self.lock:
            if self.done:
                return
            now = time.monotonic()
            if name == MEDIA_TOGGLE:
                if down:
                    if self.home_at is None and not self.home_sent:
                        self.home_at = now
                    return
                if self.home_sent:
                    self.home_sent = False
                    self.set(name, False)
                elif self.home_at is not None:         # (let go of quickly: a press of it there)
                    self.home_at = None
                    self.counts[name] = self.counts.get(name, 0) + 1
                    self.n += 1
                else:
                    return                             # (held from before: nothing)
            else:
                changed = False
                if down and self.home_at is not None:  # (with HOME held: HOME first)
                    self.home_at, self.home_sent = None, True
                    changed = self.set(MEDIA_TOGGLE, True)
                if not self.set(name, down) and not changed:
                    return
            data = self.changed_now(now)
        self.send(data)
        self.wake.set()

    def set(self, name, down):
        """Held, or let go of (and counted, as it goes down): True if that's a change."""
        if down == (name in self.held):
            return False
        if down:
            self.held.add(name)
            self.counts[name] = self.counts.get(name, 0) + 1
        else:
            self.held.discard(name)
        self.n += 1
        return True

    def changed_now(self, now):
        """(The lock held.) A change: its packet, to go now (and again a moment later)."""
        self.again = [now + gap for gap in PILOT_AGAIN]
        self.sent = now
        return self.packet_now()

    def packet_now(self):
        return packet(self.key, self.n, self.held, self.counts) if self.key and self.state == "on" else None

    def let_go(self):
        """Everything held here let go of, there too (a controller unplugged)."""
        with self.lock:
            changed = False
            for b in list(self.held):
                changed = self.set(b, False) or changed
            self.home_at, self.home_sent = None, False
            if not changed:
                return
            data = self.changed_now(time.monotonic())
        self.send(data)
        self.wake.set()

    def home_held(self, now):
        """Seconds HOME has been held on its own (0: it isn't)."""
        at = self.home_at
        return now - at if at is not None else 0.0

    def held_now(self):
        with self.lock:
            return set(self.held) | ({MEDIA_TOGGLE} if self.home_at is not None else set())

    def status(self, now):
        """How it's going: "asking" (getting in touch), "on" (in touch), "quiet" (not answering lately), "failed"
        (it won't, or can't be reached: why says which)."""
        if self.state == "on" and now - self.heard > PILOT_QUIET:
            return "quiet"
        return self.state

    def stop(self):
        """Let go of the other one: it's told so (on a thread of its own: this returns at once)."""
        with self.lock:
            if self.done:
                return
            self.done = True
            key, sock = self.key if self.state == "on" else None, self.sock
        self.wake.set()
        threading.Thread(target=self.bye, args=(key, sock), daemon=True, name="pilot-bye").start()

    def bye(self, key, sock):
        if key and sock is not None:
            for _ in range(2):
                try:
                    sock.send(bye_packet(key))
                except OSError:
                    break
            self.post(self.url + "/api/pilot", {"kind": "end", "key": key}, 3.0, self.password)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def send(self, data):
        sock = self.sock
        if data and sock is not None:
            try:
                sock.send(data)
            except OSError:                            # (nothing there now: its answers say so, or don't come)
                pass

    # -- its thread --------------------------------------------------------------------------------------------------
    def loop(self):
        while not self.done:
            if self.state != "on":
                if self.ask():
                    continue
                if not self.was_on:                    # (the first ask: it won't, or isn't answering. That's said)
                    self.state = "failed"
                    self.changed()
                    return
                self.wake.wait(PILOT_ASK_AGAIN)        # (in touch before: asked again, now and then)
                self.wake.clear()
                continue
            now = time.monotonic()
            self.listen(now)
            if self.state != "on" or self.done:
                continue
            with self.lock:
                due = self.again[0] if self.again else self.sent + (PILOT_BEAT_HELD if self.held else PILOT_BEAT)
                data = None
                if now >= due:
                    if self.again:
                        self.again.pop(0)
                    self.sent = now
                    data = self.packet_now()
                    due = self.again[0] if self.again else now + (PILOT_BEAT_HELD if self.held else PILOT_BEAT)
            self.send(data)
            if now - self.heard > PILOT_GONE:          # (nothing back for long: it's gone, or been restarted)
                self.state = "asking"
                continue
            self.wake.wait(max(0.0, min(due - time.monotonic(), 0.25)))
            self.wake.clear()
        self.changed()

    def listen(self, now):
        """Its answers: in touch; or its key's gone (asked again)."""
        sock = self.sock
        while sock is not None:
            try:
                data = sock.recv(256)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:                            # (nothing listening there now: restarted, say)
                if now - self.heard > PILOT_QUIET:
                    self.state = "asking"
                return
            try:
                said = json.loads(data)
            except ValueError:
                continue
            if not isinstance(said, dict):
                continue
            if said.get("gone"):
                self.state = "asking"
                self.changed()
                return
            if "n" in said:
                quiet = now - self.heard > PILOT_QUIET
                self.heard = now
                if quiet:
                    self.changed()

    def ask(self):
        """The other one asked: True once it's said yes (its port and key, a socket for them). False otherwise, with
        why ("password": its web page wants its password, or that one wasn't it)."""
        if self.state != "asking":
            self.state = "asking"
            self.changed()
        got = self.post(self.url + "/api/pilot", {"kind": "ask", "has": self.has}, PILOT_ASK_WAIT, self.password)
        if self.done:
            return False
        if got and got.get("status") == 401:
            self.why = "password"
            return False
        if not got or not got.get("ok"):
            self.why = str((got or {}).get("error") or f"{self.name} not responding")[:120]
            return False
        port, key = got.get("port"), got.get("key")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536 or not isinstance(key, str) \
                or not PILOT_KEY.fullmatch(key):
            self.why = f"{self.name} said something this one doesn't understand"
            return False
        try:
            fam, kind, proto, _, addr = socket.getaddrinfo(self.host, port, type=socket.SOCK_DGRAM)[0]
            sock = socket.socket(fam, kind, proto)
            sock.connect(addr)
            sock.setblocking(False)
        except OSError:
            self.why = f"Couldn't reach {self.name}"
            return False
        with self.lock:
            done = self.done
            if not done:
                old, self.sock, self.key = self.sock, sock, key
                self.counts = {b: 1 for b in self.held}   # (a new start there: what's held here now, pressed there)
                self.n += 1
                self.state, self.was_on, self.heard = "on", True, time.monotonic()
                data = self.changed_now(time.monotonic())
        if done:                                       # (let go of while it was asking: it's told so)
            self.bye(key, sock)
            return False
        if old is not None:
            try:
                old.close()
            except OSError:
                pass
        self.send(data)
        self.changed()
        return True
