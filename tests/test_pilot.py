"""Home > Control another Pietato (pilot.py, screens/pilot.py): one of your Pietatos' buttons working another, as a
controller plugged into it would.

First the parts on their own: a packet (and what isn't one); what's pressed and let go of over there, in order, from
what was held and how many times each button went down (a press lost on the way made up, HOME before what's pressed
with it); the other one's side, on a real UDP port (an old or repeated packet left alone, one with another key or from
another address not taken, what's held let go of after a second of nothing and pressed again when it's heard from,
gone after a while, no more than four at once); and this one's sender (HOME let go of quickly: a press of it there;
held with another button: it first; held on its own: nothing sent, and how long it's been held; not answering, said;
its key gone over there, asked again; let go of, said so).

Then two of them: this one is the handheld ("gpi": its own main loop, a pretend GPi Case with no HOME, so SELECT and
START together are its HOME), and the TV's ("tv": peer_pietato.py, with its web page and its main loop, in a process
of its own). Home > Control another Pietato lists the TV; A asks it, and from then on the case's buttons are the TV's:
a controller of its own there, held as long as they're held here, and lit on this one's screen. HOME pressed quickly
is the TV's; its terminal is never typed in (only HOME brings its menus back). WiFi gone for a moment: what's held is
let go of there, then pressed again; gone for long: the TV says it's lost touch, and this one gets back in touch by
itself. SELECT and START held two seconds let go of it, the TV never seeing that HOME. The TV's web page has a
password: typed here once (a wrong one said), then kept. Not for one that isn't one of yours, or with the TV's sharing
off; the web page's part from your network only. Over there, it's a player of its own in a game, Swap A and B is kept
for it, and it's on the web page's list of controllers; its WiFi isn't left saving power while it's controlled; and
like the web page's remote, it can't answer your coding agent."""
import json, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.pilot as P
from evdev import ecodes as e, AbsInfo

S = SP + "/t_pilot"
shutil.rmtree(S, ignore_errors=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0, step=0.02):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return bool(cond())


KEY = "k" * 24

# ---- a packet---------------------------------------------------------------------------------------------------------
got = P.read_packet(P.packet(KEY, 7, {"a", "right"}, {"a": 3, "right": 1, "b": 0}))
check(f"a packet: what's held, how many times each went down (none for 0), numbered ({got})",
      got == {"k": KEY, "bye": False, "n": 7, "d": {"a", "right"}, "c": {"a": 3, "right": 1}})
check("...and a goodbye", P.read_packet(P.bye_packet(KEY)) == {"k": KEY, "bye": True})
bad = [b"", b"x" * 2000, b"[1]", b"\xff\xfe", json.dumps({"k": "short", "n": 1}).encode(),
       json.dumps({"k": KEY, "n": True}).encode(), json.dumps({"k": KEY, "n": -1}).encode(),
       json.dumps({"k": KEY, "n": 1, "d": "a"}).encode(), json.dumps({"k": KEY, "n": 1, "c": [1]}).encode()]
check("...not one: nothing", all(P.read_packet(b) is None for b in bad))
odd = P.read_packet(json.dumps({"k": KEY, "n": 2, "d": ["a", "jump"], "c": {"a": 1, "jump": 4, "b": -2,
                                                                          "x": True}}).encode())
check(f"...names it doesn't know, and odd counts, left out ({odd})", odd["d"] == {"a"} and odd["c"] == {"a": 1})

# ---- what's pressed over there, in order------------------------------------------------------------------------------
C = P.changes
check("pressed, then let go of", C(set(), {}, {"a"}, {"a": 1}) == [("a", True)]
      and C({"a"}, {"a": 1}, set(), {"a": 1}) == [("a", False)])
check("a quick press it never heard of (its packets lost): pressed and let go of",
      C(set(), {"b": 2}, set(), {"b": 3}) == [("b", True), ("b", False)])
check("let go of and pressed again between two packets: let go of, then pressed",
      C({"a"}, {"a": 1}, {"a"}, {"a": 2}) == [("a", False), ("a", True)])
check("ten presses lost: three made up, at most", C(set(), {}, set(), {"a": 10}) == [("a", True), ("a", False)] * 3)
check("let go of first, then HOME, then the rest (HOME before what's pressed with it, for a Konami code)",
      C({"b"}, {"b": 1}, {"home", "up"}, {"b": 1, "home": 1, "up": 1}) == [("b", False), ("home", True), ("up", True)])
check("...and let go of together: the other, then HOME",
      C({"home", "up"}, {"home": 1, "up": 1}, set(), {"home": 1, "up": 1}) == [("up", False), ("home", False)])

# ---- over there: one controlling it, on a real port-------------------------------------------------------------------
tv = P.Pilots()
check("no port till one's controlling it", tv.sock is None and tv.next_due() == float("inf"))
s1 = tv.add("127.0.0.1", "gpi", ["a", "b", "up", "home", "jump"], time.monotonic())
tv.open()
check(f"one controlling it: a key, a port ({tv.port}), and a controller here named for it, with its buttons and HOME",
      s1 is not None and P.PILOT_KEY.fullmatch(s1.key) and tv.port > 0 and s1.pad.dev.name == "gpi"
      and s1.pad.kind == "pilot" and s1.pad.has_button("a") and not s1.pad.has_button("l2") and s1.pad.home
      and not s1.pad.has_stick() and s1.pad.sticks_now() == [])
c1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
c1.bind(("127.0.0.1", 0))
c1.settimeout(0.5)


def send(n, held, counts, key=None, sock=c1):
    sock.sendto(P.packet(key or s1.key, n, held, counts), ("127.0.0.1", tv.port))
    time.sleep(0.03)


def take(pilots=tv):
    return [(w[0],) + tuple(w[2:]) for w in pilots.take(time.monotonic())]


def answers(sock=c1):
    out = []
    sock.settimeout(0.05)
    try:
        while True:
            out.append(json.loads(sock.recv(256)))
    except OSError:
        pass
    return out


send(1, {"a"}, {"a": 1})
check("A pressed there: pressed here, and answered with its number", take() == [("press", "a", True)]
      and answers() == [{"n": 1}])
send(1, {"a"}, {"a": 1})
send(0, set(), {})
check("...the same packet again (it's sent twice), or an older one: nothing", take() == [] and len(answers()) == 2)
send(2, set(), {"a": 1})
check("...let go of", take() == [("press", "a", False)] and answers() == [{"n": 2}])
send(3, {"b"}, {"a": 1, "b": 1}, key="z" * 24)
check("another key: nothing, and told its key's gone (to ask again)", take() == [] and answers() == [{"gone": 1}])
c2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
c2.bind(("127.0.0.2", 0))
send(3, {"b"}, {"a": 1, "b": 1}, sock=c2)
check("its key from another address: nothing", take() == [] and answers(c2) == [{"gone": 1}])
send(3, {"b"}, {"a": 1, "b": 1})
take()
now = time.monotonic()
check("B held, and nothing for a second: let go of here (WiFi gone, or its battery)",
      tv.next_due() <= now + P.PILOT_HOLD_LOST + 0.01
      and [(w[0], w[2], w[3]) for w in tv.check(now + 1.1)] == [("press", "b", False)] and s1.lost
      and s1.holding() == set())
check("...not again", tv.check(now + 1.2) == [] and tv.next_due() >= now + P.PILOT_GONE - 1)
send(3, {"b"}, {"a": 1, "b": 1})
check("...heard from again, still held: pressed again", take() == [("press", "b", True)] and not s1.lost)
check("nothing at all for a while: it's gone", [(w[0],) for w in tv.check(time.monotonic() + P.PILOT_GONE + 1)]
      == [("gone",)])
c1.sendto(P.bye_packet(s1.key), ("127.0.0.1", tv.port))
time.sleep(0.03)
check("a goodbye: it's let go of this one", take() == [("bye",)])
more = [tv.add(f"10.0.0.{k}", f"p{k}", None, time.monotonic()) for k in range(2, 6)]
check("four at once, and no more (a player each)", all(more[:3]) and more[3] is None and len(tv.sessions) == 4)
tv.close()

# ---- this one's side: the sender--------------------------------------------------------------------------------------
there = P.Pilots()
there.open()
asked = []


def post(url, body, timeout, password=None):
    asked.append((url, dict(body)))
    if body["kind"] == "end":
        return {"ok": True}
    s = there.add("127.0.0.1", "gpi", body.get("has"), time.monotonic())
    return {"ok": True, "port": there.port, "key": s.key}


got_there, hush, there_done = [], threading.Event(), threading.Event()


def answering():
    """Over there: each packet taken and answered, as the other one's main loop does (a goodbye: it's let go of)."""
    while not there_done.is_set():
        if not hush.is_set():
            for w in there.take(time.monotonic()):
                if w[1] not in there.sessions:         # (let go of a moment ago: its second goodbye, say)
                    continue
                got_there.append((w[2], w[3]) if w[0] == "press" else (w[0],))
                if w[0] == "bye":
                    there.remove(w[1])
        time.sleep(0.005)


threading.Thread(target=answering, daemon=True).start()


def listen(secs):
    """What it's pressed over there, these seconds."""
    time.sleep(secs)
    out = list(got_there)
    got_there.clear()
    return out


out = P.PilotOut("http://127.0.0.1:5432", "tv", ["a", "b", "up", "home", "jump"], post=post)
check("asks the other one first, saying which buttons it has", until(lambda: out.status(time.monotonic()) == "on")
      and asked == [("http://127.0.0.1:5432/api/pilot", {"kind": "ask", "has": ["a", "b", "home", "up"]})])
listen(0.2)
out.press("a", True)
out.press("a", False)
check("A pressed and let go of here: the same there (each sent twice; once's what counts)",
      listen(0.4) == [("a", True), ("a", False)])
out.press("home", True)
held_for = listen(0.3)
check(f"HOME down here: nothing sent yet, and how long it's been held ({out.home_held(time.monotonic()):.2f}s)",
      held_for == [] and 0.25 < out.home_held(time.monotonic()) < 1 and "home" in out.held_now())
out.press("home", False)
check("...let go of: a press of HOME there", listen(0.3) == [("home", True), ("home", False)])
out.press("home", True)
out.press("up", True)
check("HOME held and UP pressed: HOME first there (a Konami code)", listen(0.3) == [("home", True), ("up", True)]
      and out.home_held(time.monotonic()) == 0)
out.press("up", False)
out.press("home", False)
check("...let go of: UP, then HOME", listen(0.3) == [("up", False), ("home", False)])
out.press("b", True)
listen(0.1)
was_quiet = P.PILOT_QUIET
P.PILOT_QUIET = 0.4
hush.set()
time.sleep(0.6)
quiet = out.status(time.monotonic())
hush.clear()
listen(0.4)
check(f"no answers for a while: it says so ({quiet}); answered again, it's in touch",
      quiet == "quiet" and out.status(time.monotonic()) == "on")
P.PILOT_QUIET = was_quiet
there.remove(there.sessions[-1])
check("its key gone over there (restarted, say): asked again by itself, B still held pressed there afresh",
      until(lambda: len([a for a in asked if a[1]["kind"] == "ask"]) == 2, 3)
      and until(lambda: out.status(time.monotonic()) == "on", 3) and ("b", True) in listen(0.3))
out.press("b", False)
listen(0.2)
out.stop()
bye = listen(0.3)
check(f"let go of: it says goodbye there, and to its web page ({bye}, {asked[-1][1]}, {len(there.sessions)})",
      bye == [("bye",)] and until(lambda: asked[-1][1].get("kind") == "end", 3) and there.sessions == [])
there_done.set()
time.sleep(0.05)
there.close()

# ---- two of them: this one (the handheld) controlling the TV's--------------------------------------------------------
GPI, TVH, LOG = S + "/gpi", S + "/tv", S + "/tv.log"
for h in (GPI, TVH):
    for d in ("Music", "Videos", "Pictures", "Documents"):
        os.makedirs(f"{h}/{d}")
tvp = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TVH, LOG, "tv", "http://127.0.0.1:9", "gpi",
                        "presses"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                       env=dict(os.environ, PITATO_PILOT_GONE="3"))
ready = tvp.stdout.readline().split()
TV_URL = ready[1] if ready[:1] == ["READY"] else ""
check(f"the TV's Pietato is up ({TV_URL})", TV_URL.startswith("http://127.0.0.1:"))


def tv_say(cmd):
    tvp.stdin.write(cmd + "\n")
    tvp.stdin.flush()
    return tvp.stdout.readline()


def tv_pilots():
    return json.loads(tv_say("pilots"))


def tv_log(since=0):
    try:
        lines = open(LOG).read().splitlines()
    except OSError:
        return []
    return [json.loads(x) for x in lines[since:] if x.strip()]


def tv_mark():
    return len(tv_log())


def tv_presses(since):
    return [(x["pressed"], x["pad"] and x["pad"].startswith("pilot:")) if "pressed" in x
            else ("-" + x["released"], x["pad"] and x["pad"].startswith("pilot:"))
            for x in tv_log(since) if ("pressed" in x and not x["repeat"]) or "released" in x]


os.environ["HOME"] = GPI
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"; g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {"start": "Terminal"}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: GPI
import gk_static; gk_static.use_home(g, GPI)  # noqa: E401
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.wifi_power_save = lambda dev, on=None: None
g.SCAN_EVERY = 0.05


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    vendor, product, bustype = 0x45e, 0x28e, 3


class FakeDev:
    """A pretend GPi Case: the d-pad as a hat, A B X Y, L R, SELECT and START; no HOME (SELECT and START are)."""
    path = "/dev/input/event7"
    name = "GPi Case 2 pad"
    info = Info()

    def __init__(self):
        self.r, self.w = os.pipe()
        self.q = []
        self.keys = [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START]
        self.absaxes = {c: AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
                        for c in (e.ABS_HAT0X, e.ABS_HAT0Y)}

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys), e.EV_ABS: [(c, a) if absinfo else c for c, a in self.absaxes.items()]}

    def absinfo(self, code):
        return self.absaxes[code]

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        pass


case = FakeDev()
g.list_devices = lambda: [case.path]
g.InputDevice = lambda path: case
real_stat = os.stat
g.os.stat = lambda p, *a, **k: (type("St", (), {"st_ino": 7})() if str(p).startswith("/dev/input/")
                                else real_stat(p, *a, **k))
BTN = {"a": e.BTN_SOUTH, "b": e.BTN_EAST, "select": e.BTN_SELECT, "start": e.BTN_START}
HAT = {"right": (e.ABS_HAT0X, 1), "left": (e.ABS_HAT0X, -1), "up": (e.ABS_HAT0Y, -1), "down": (e.ABS_HAT0Y, 1)}


def down(name):
    case.send((e.EV_ABS, HAT[name][0], HAT[name][1]) if name in HAT else (e.EV_KEY, BTN[name], 1))


def up(name):
    case.send((e.EV_ABS, HAT[name][0], 0) if name in HAT else (e.EV_KEY, BTN[name], 0))


def tap(name, hold=0.06):
    down(name)
    time.sleep(hold)
    up(name)
    time.sleep(0.15)


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def show_part(self, img, box):
        FB.last = img.copy()

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
m.pie.heard[TV_URL] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
done, errors = threading.Event(), []


def loop():
    try:
        g.run(type("UI", (), {"write": lambda *a: None, "syn": lambda *a: None})(), m, None, stop=done.is_set)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        errors.append(ex)


threading.Thread(target=loop, daemon=True).start()


def on_loop(fn):
    """fn, on this one's main loop (as a button would be)."""
    did = threading.Event()

    def job():
        try:
            fn()
        finally:
            did.set()
    m.soon_jobs.append(job)
    m.wake()
    did.wait(5)


check("the pretend case found", until(lambda: m.pads is not None and list(m.pads.by_path) == [case.path]))
pi = m.tab_index("pilot")
home_i = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Home")
check("Home has Control another Pietato, after Web", g.LIBRARY[home_i]["children"][-2:] == ["Web",
                                                                                          "Control another Pietato"])


def open_pilot():
    m.enter()
    m.tab, m.view = pi, "list"
    m.load_tab(pi)
    m.dirty = True


on_loop(open_pilot)
rows = m.tab_items()
check(f"Home > Control another Pietato lists the TV's ({[r['title'] for r in rows]})",
      [(r["title"], r["src"], r["sub"]) for r in rows] == [("tv", TV_URL, "127.0.0.1")]
      and m.list_hints() == [("A", "Control it"), ("B", "Back")])
mark = tv_mark()
tap("a")
check("A: it asks the TV, and it's in touch", until(lambda: m.pilot_on() and m.pilot_out.status(time.monotonic())
                                                     == "on"))
check("...the TV says so", until(lambda: "gpi is controlling this Pietato" in [x.get("toast") for x in tv_log(mark)]))
tp = tv_pilots()
check(f"...and has a controller of its own for it ({tp['pads']})", [(p["name"], p["kind"]) for p in tp["pads"]]
      == [("gpi", "pilot")])
check(f"...this one's screen says which it's controlling, and HOME held lets go ({m.list_hints()})",
      m.list_hints() == [("HOME", "Hold it to let go")] and not m.resting and m.worth_watching(time.monotonic()))
mark = tv_mark()
sel = tp["home_sel"]
tap("right")
check(f"RIGHT here: RIGHT there, from its controller ({tv_presses(mark)})",
      until(lambda: tv_presses(mark) == [("right", True), ("-right", True)]) and tv_pilots()["home_sel"] != sel)
check("...nothing pressed here (the screen here's just the same)", m.view == "list" and m.tab == pi)
mark = tv_mark()


def accent_px():
    if FB.last is None:
        return 0
    import numpy as np
    a = np.asarray(FB.last.convert("RGB")).astype(int)
    return int((abs(a - np.array(g.ACCENT)).sum(axis=2) < 30).sum())


lit_before = accent_px()
down("down")
time.sleep(0.8)
lit_held = accent_px()
up("down")
time.sleep(0.3)
pr = [x for x in tv_log(mark) if x.get("pressed") == "down" or x.get("released") == "down"]
held_secs = pr[-1]["t"] - pr[0]["t"] if pr and "released" in pr[-1] else 0
check(f"DOWN held here 0.8s: held there as long ({held_secs:.2f}s, its menus going on down as it is: "
      f"{sum(1 for x in pr if x.get('repeat'))} more)", 0.6 < held_secs < 1.2
      and sum(1 for x in pr if x.get("repeat")) >= 2)
check(f"...lit on this one's screen while it's held ({lit_before} then {lit_held} px)", lit_held > lit_before + 50)

# HOME: SELECT and START together, let go of quickly: a press of HOME there (on its home screen: its terminal)
mark = tv_mark()
down("select")
down("start")
time.sleep(0.15)
up("start")
up("select")
check("SELECT and START together, quickly: HOME there (its home screen: off to its terminal)",
      until(lambda: tv_pilots()["active"] is False, 3) and m.pilot_on())
tap("a")
tap("up")
time.sleep(0.3)
check(f"...its terminal's never typed in from here ({[x for x in tv_log(mark) if 'key' in x][:3]})",
      not [x for x in tv_log(mark) if "key" in x] and not [x for x in tv_log(mark) if "pressed" in x])
down("select")
down("start")
time.sleep(0.15)
up("start")
up("select")
check("...HOME again: its menus back", until(lambda: tv_pilots()["active"] is True, 3))

# WiFi gone a moment, with UP held: let go of there, then pressed again
mark = tv_mark()
down("up")
until(lambda: [x for x in tv_log(mark) if x.get("pressed") == "up"], 2)
real_send = m.pilot_out.send
m.pilot_out.send = lambda data: None
time.sleep(1.4)
let_go = [x for x in tv_log(mark) if x.get("released") == "up"]
m.pilot_out.send = real_send
check("WiFi gone a moment with UP held: let go of there after a second (nothing left held)", len(let_go) == 1)
check("...back: still held here, so pressed there again",
      until(lambda: len([x for x in tv_log(mark) if x.get("pressed") == "up" and not x["repeat"]]) == 2, 2))
up("up")
check("...let go of", until(lambda: len([x for x in tv_log(mark) if x.get("released") == "up"]) == 2, 2))

# gone for long: the TV loses touch; this one gets back in touch by itself
mark = tv_mark()
m.pilot_out.send = lambda data: None
check("WiFi gone for long: the TV says it's lost touch, and its controller's gone",
      until(lambda: "Lost touch with gpi" in [x.get("toast") for x in tv_log(mark)], 6) and tv_pilots()["pads"] == [])
check("...this one says it isn't answering", until(lambda: m.pilot_out.status(time.monotonic()) == "quiet", 4))
del m.pilot_out.send
check("...back: in touch again by itself",
      until(lambda: m.pilot_out.status(time.monotonic()) == "on" and len(tv_pilots()["pads"]) == 1, 8)
      and "gpi is controlling this Pietato" in [x.get("toast") for x in tv_log(mark)])

# SELECT and START held two seconds: let go of it (the TV never sees that HOME)
mark = tv_mark()
toasts.clear()
down("select")
down("start")
check("SELECT and START held two seconds: let go of it", until(lambda: not m.pilot_on(), 4)
      and "Stopped controlling tv" in toasts)
up("start")
up("select")
check("...the TV's told (its controller gone), and saw no HOME (its menus still up, nothing pressed)",
      until(lambda: "gpi stopped controlling this Pietato" in [x.get("toast") for x in tv_log(mark)], 3)
      and tv_pilots()["pads"] == [] and tv_pilots()["active"] is True
      and not [x for x in tv_log(mark) if "pressed" in x or "key" in x])
time.sleep(0.3)
check("...and this one's buttons are its own again: the list, its row picked",
      m.view == "list" and m.tab == pi and m.list_hints() == [("A", "Control it"), ("B", "Back")])

# the TV's web page has a password: typed here once (a wrong one said), then kept
TV_PW = TVH + "/.pietato/static/webui.txt"
open(TV_PW, "w").write("password = sesame\n")
toasts.clear()
tap("a")
check("the TV's web page has a password: asked for here", until(lambda: m.view == "keys", 8) and not m.pilot_on()
      and m.kb["title"] == "tv's web page password")


def typed(text):
    def go():
        m.kb["text"] = text
        m.close_keyboard(True)
    on_loop(go)


typed("open")
check(f"...a wrong one: said, and asked for again ({toasts[-1:]})",
      until(lambda: m.view == "keys" and "That isn't its password" in toasts, 8))
typed("sesame")
check("...its password: in touch, and it's kept (here only)",
      until(lambda: m.pilot_on() and m.pilot_out.status(time.monotonic()) == "on", 8)
      and until(lambda: m.state["pilot"].get(TV_URL) == "sesame", 2)
      and json.load(open(g.STATE_FILE))["pilot"] == {TV_URL: "sesame"})
down("select")
down("start")
until(lambda: not m.pilot_on(), 4)
up("start")
up("select")
time.sleep(0.3)
tap("a")
check("...next time: the one kept, no asking", until(lambda: m.pilot_on() and m.pilot_out.status(time.monotonic())
                                                     == "on", 8) and m.view == "list")
down("select")
down("start")
until(lambda: not m.pilot_on(), 4)
up("start")
up("select")
os.remove(TV_PW)
time.sleep(0.3)

# not for one that isn't one of yours, or with the TV's sharing off
toasts.clear()
tv_say("set share Off")
tap("a")
check(f"the TV's sharing off: it says so here ({toasts[-1:]})",
      until(lambda: "Its Settings > Share with other Pietatos is off" in toasts, 8) and not m.pilot_on())
tv_say("set share On")
tv_say("peer http://10.0.0.9:5432 someone")
toasts.clear()
tap("a")
check(f"...not one the TV knows: it won't ({toasts[-1:]})",
      until(lambda: "Not one of your Pietatos" in toasts, 8) and not m.pilot_on())
tv_say("peer http://127.0.0.1:9 gpi")

# the web page's part: from your network only, and with its password if it has one
sys.path.append(os.path.dirname(TESTS) + "/pitato")
import webui  # noqa: E402
webui.HOME = GPI
webui.STATIC = S + "/gpistatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
client = webui.app.test_client()
far = client.post("/api/pilot", json={"kind": "ask"}, base_url="http://192.168.1.30:5432",
                  environ_base={"REMOTE_ADDR": "8.8.8.8"})
check(f"the web page's part: your network only ({far.status_code})", far.status_code == 403)
open(webui.STATIC + "/webui.txt", "w").write("password = sesame\n")
near = client.post("/api/pilot", json={"kind": "ask"}, base_url="http://192.168.1.30:5432",
                   environ_base={"REMOTE_ADDR": "192.168.1.31"})
check(f"...and with the page's password, when it has one ({near.status_code})", near.status_code == 401)
os.remove(webui.STATIC + "/webui.txt")

# another of yours as a controller plugged in here: a player of its own, Swap A and B kept for it, the page's list
pp = P.PilotPad("pilot:10.0.0.7:1", "den", ["a", "b", "up"])
ports = {}


def as_players():
    m.pads.by_path[pp.path] = pp
    m.game, m.game_players = type("Run", (), {"game": {"system": "nes"}})(), {}
    try:
        ports.update(case=m.game_port(m.pads.by_path[case.path]), den=m.game_port(pp))
    finally:
        m.game = None
    m.pads.swap(pp.ident, True)


on_loop(as_players)
pads_web = m.web_state_now()["controllers"]
check(f"another Pietato's controller here: a player of its own in a game ({ports})", ports == {"case": 0, "den": 1})
check("...Swap A and B on it, kept for it by its name", pp.swapped
      and json.load(open(g.PADS_FILE)).get("pilot:den") == {"swap": True})
check(f"...on the web page's list of controllers ({[p['name'] for p in pads_web]})",
      {"name": "den", "kind": "pilot", "learned": False, "swap": True, "path": pp.path} in pads_web)
on_loop(lambda: (m.pads.swap(pp.ident, False), m.pads.by_path.pop(pp.path, None)))

# being controlled: said, and the WiFi kept quick while it is (put back after)
wifi = []
g.wifi_power_save = lambda dev, on=None: (wifi.append(on), True)[1]
toasts.clear()
on_loop(lambda: m.pilot_began("den", True))
on_loop(lambda: m.pilot_ended("den", "bye", True))
check(f"another controlling this one: said as it begins and ends ({toasts}); its WiFi's power saving off while it "
      f"is, then as it was ({wifi})",
      toasts == ["den is controlling this Pietato", "den stopped controlling this Pietato"]
      and wifi == [False, True])
g.wifi_power_save = lambda dev, on=None: None

# like the web page's remote, it can't answer your coding agent
said = []
m.prompts.answer = lambda *a, **k: said.append(a) or True
m.web_guard = "pilot"
toasts.clear()
m.coder_answer({"id": 1, "tool": "Bash"}, "a")
check(f"your coding agent's asking, A from another Pietato: not answered ({toasts[-1:]})",
      said == [] and toasts[-1:] == ["Answer it on the Pi itself, not from another Pietato"])
m.web_guard = False

done.set()
tv_say("quit")
tvp.wait(10)
check("no trouble on this one's main loop", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
