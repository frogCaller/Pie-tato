"""'Show me something cool': one of Apps' put on at random (its Clock and htop aside, and Linux's programs
only when they're installed), never the same one twice in a row nor the one already on; what it is, said back; one
of Linux's on already: off first. Typed on the Bot's page, said to it, or asked for by its model. Pictures saved."""
import os, random, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.screens.assist as SA
S = SP + "/tcool"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h, same = 640, 480, True
    frames = 0

    def __init__(self):
        self.last = None

    def show(self, img):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        pass

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.view = "home"
spoken = []
m.assist_tell = lambda text, speak=True, secs=4: spoken.append(text)
started, stopped = [], []
m.prog_start = lambda name: started.append(name)        # (Linux's programs: not started for real here)


def stop():
    stopped.append(m.prog_name)
    m.prog, m.prog_name = None, None


m.prog_stop = stop
SIMS = ["Rock Paper Scissors", "Game of Life", "Forest Fire", "Mandelbrot Set"]
PROGS = ["cmatrix", "hollywood", "nyancat", "cacafire"]


def showing():
    """What's on now: one of Linux's programs (started), or the tab that's open."""
    if started and started[-1] is not None:
        return started[-1]
    return g.LIBRARY[m.tab]["name"] if m.view == "list" else None


# none of Linux's programs installed: just Apps' own
SA.prog_path = lambda name: None
names = [t["name"] for t in m.cool_choices()]
check(f"none of Linux's programs here: Apps' own four ({names})", names == SIMS)
SA.prog_path = lambda name: "/usr/bin/" + name
names = [t["name"] for t in m.cool_choices()]
check(f"...all of them installed: those too, but never the Clock or htop ({names})", names == SIMS + PROGS)

# typed on the Bot's page: one put on, what it is said back
m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
done = m.assist_heard("show me something cool")
first = showing()
check(f"'show me something cool': done here, not by its model ({done})", done is True)
check(f"...one of Apps' on ({first})", first in SIMS + PROGS)
check(f"...what it is, said back ({spoken[-1] if spoken else None!r})", bool(spoken) and spoken[-1].startswith("Here's")
      and first.lower() in spoken[-1].lower())
check(f"...and in the Bot's conversation ({m.friend.log[-1] if m.friend.log else None})",
      m.friend.log and m.friend.log[-1].get("text", m.friend.log[-1].get("said", "")) == spoken[-1]
      if isinstance(m.friend.log[-1], dict) else True)

# again and again: a different one each time, all of them in time
seen, last, again = [first], first, True
for _ in range(60):
    started.append(None)                               # (whatever was on: back from it, as B does)
    m.view = "list"
    if m.assist_heard("hey potato, show me something cool") is not True:
        again = False
    now = showing()
    if now == last:
        again = False
    seen.append(now)
    last = now
check(f"asked 60 more times: never the same one twice in a row ({again})", again)
check(f"...all eight in turn, never the Clock or htop ({sorted(set(seen))})", set(seen) == set(SIMS + PROGS))

# a sim on already: not that one
again = set()
for _ in range(20):
    started.append(None)
    m.web_tab("Forest Fire"); m.cool_last = None
    m.assist_heard("show us something neat")
    again.add(showing())
check(f"Forest Fire on: never Forest Fire again ({sorted(again)})", "Forest Fire" not in again and len(again) > 2)

# one of Linux's on: it's stopped first, and it's not the one put on
started.append(None)
m.prog, m.prog_name = object(), "nyancat"
m.cool_last = None
m.assist_heard("show me something cool")
check(f"nyancat on: stopped first ({stopped}), something else on ({showing()})", stopped == ["nyancat"]
      and showing() != "nyancat")

# what it says: the Game of Life's name and what it is
real = SA.random.choice
SA.random.choice = lambda seq: next((t for t in seq if isinstance(t, dict) and t.get("name") == "Game of Life"),
                                    seq[0])
started.append(None); m.cool_last = None; m.web_tab("Weather")
m.assist_heard("show me something cool")
SA.random.choice = real
check(f"...said as: {spoken[-1]!r}", spoken[-1] == "Here's the Game of Life: cells live, die and are born.")
m.dirty = True
m.flush()
m.fb.last.save(S + "/life.png")
check(f"...on the screen: the Game of Life's page ({g.LIBRARY[m.tab]['name']}, {m.view})",
      g.LIBRARY[m.tab]["name"] == "Game of Life" and m.view == "list")

# none installed, a sim on: only the other three
SA.prog_path = lambda name: None
started.append(None); m.cool_last = None
picks = set()
for _ in range(30):
    m.web_tab("Mandelbrot Set"); m.cool_last = None
    m.assist_heard("show me something cool")
    picks.add(showing())
check(f"nothing of Linux's here, the Mandelbrot Set on: the other three ({sorted(picks)})",
      picks == {"Rock Paper Scissors", "Game of Life", "Forest Fire"})

# its model asking for it ("[[show me something cool]]"), in its own words
m.cool_last = None
m.model_asked("show me something cool", "Here's something fun!")
check(f"asked for by its model: one put on ({showing()})", showing() in SIMS)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
