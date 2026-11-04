"""Settings > Random song at start-up keeps your music going: the songs go round and round (the random ones in a
new order each time), and music a game or a video stopped comes back a moment after it's over, from where it was;
not if it was paused or stopped on purpose, nor with the setting off."""
import io, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
S = SP + "/t_music_back"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music"); os.makedirs(HOME + "/Videos")
SONGS = [HOME + f"/Music/song {k}.mp3" for k in range(1, 6)]
for p in SONGS + [HOME + "/Videos/clip.mp4"]:
    open(p, "wb").write(b"x")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
spawned = []


class FakeProc:
    def __init__(self):
        self.stdin = io.StringIO(); self.dead = False
    def poll(self): return 0 if self.dead else None
    def wait(self, timeout=None): return 0
    def kill(self): self.dead = True


def fake_spawn(self, args, target):
    spawned.append((list(args), target))
    self.started = time.monotonic()
    self.proc = FakeProc()


g.Media.spawn = fake_spawn


class Game:
    """A game running (as far as the music's concerned)."""
    ended, state, noted = False, "on", True
    game = {"path": "/home/u/Games/nes/Tetris.nes", "label": "Tetris"}
    def quit(self): pass
    def poll(self): return None


def fresh(on=True):
    json.dump({"settings": {"start_song": "On" if on else "Off"}}, open(g.STATE_FILE, "w"))
    spawned.clear()
    m = g.Media(); m.enter()
    m.boot_song = 0.0
    return m


def ends(m):
    """The song playing comes to its end."""
    m.started = time.monotonic() - 300
    m.proc.dead = True
    m.tick()


def later(m, secs=2.1):
    """A moment passes (the clock the music watches, moved on)."""
    if m.resume_at_t is not None:
        m.resume_at_t -= secs
    m.tick()


def start_at(args):
    return float(args[args.index("-ss") + 1]) if "-ss" in args else 0.0


# ---- round and round: the start-up's random songs
m = fresh()
m.random_song()
first_round = [it["src"] for it in m.queue]
check("the start-up's songs: random", m.queue_random and sorted(first_round) == sorted(SONGS))
for _ in range(len(SONGS) - 1):
    ends(m)
check("...to the last of them", m.qi == len(SONGS) - 1)
last = m.cur["src"]
ends(m)
check(f"the last ends: round again, in a new order, from the first ({m.qi})", m.qi == 0 and m.proc is not None
      and sorted(it["src"] for it in m.queue) == sorted(SONGS) and m.queue[0]["src"] != last)
m.press("r") if m.view == "now" else None
m.stop()

# a list you picked: round again too, in its own order
m = fresh()
mi = next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == "audio")
m.load_tab(mi); m.tab = mi; m.view = "list"; m.sels[mi] = len(SONGS) - 1
m.press("a")
order = [it["src"] for it in m.queue]
ends(m)
check(f"a list you picked: after its last, its first ({m.qi})", m.qi == 0 and [it["src"] for it in m.queue] == order)
m.qi = 0
m.skip(-1)
check(f"...and back from its first: its last ({m.qi})", m.qi == len(SONGS) - 1)
m.stop()

# the setting off: as before, it ends
m = fresh(on=False)
m.random_song() if False else None
m.load_tab(mi); m.tab = mi; m.view = "list"; m.sels[mi] = len(SONGS) - 1
m.press("a")
ends(m)
check("the setting off: the list ends, and that's that", m.proc is None)
m.tick(); later(m); later(m)
check("...nothing comes back", m.proc is None)

# ---- a game stops it: back after the game, from where it was
m = fresh()
m.random_song()
m.view = "home"
playing = m.cur["src"]; m.pos = 61.0
m.stop()                                            # (as starting a game does)
m.game = Game()
m.tick(); later(m); later(m)
check("a game on: no music", m.proc is None)
m.game = None; m.view = "list"
m.tick()
check("the game over: not straight away", m.proc is None)
later(m)
args, target = spawned[-1]
check(f"...a moment later the same song, from where it was ({os.path.basename(target)} at {start_at(args)})",
      m.proc is not None and m.cur["src"] == playing and target == playing and 55 <= start_at(args) <= 61)
check("...you stay where you are", m.view == "list")
m.tick(); later(m)
check("...once", len([s for s in spawned if s[1] == playing]) == 2)

# a video stops it: back after the video
m.pos = 30.0
vi = next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == "video")
m.load_tab(vi)
m.play(m.tab_items(vi), 0)
check("a video: the music stops for it", m.kind == "video")
ends(m)
m.tick(); later(m)
check("the video over: the song back", m.kind == "audio" and m.cur["src"] == playing and 24 <= start_at(spawned[-1][0]) <= 30)

# the radio comes back too
radio = {"key": "r1", "title": "Jazz Radio", "kind": "radio", "src": "http://192.168.1.20:8000/jazz", "sub": ""}
m.play([radio], 0, show=False)
m.stop()
m.game = Game(); m.tick(); m.game = None
m.tick(); later(m)
check("the radio, stopped by a game: back after it", m.kind == "radio" and m.cur["title"] == "Jazz Radio")

# ---- not when...
m.stop(); m.game = Game(); m.game = None
m.resume_later = None
m.random_song()
m.paused = True
m.stop()
m.tick(); later(m); later(m)
check("it was paused: it stays stopped", m.proc is None)

m.random_song()
m.web_player("stop")
m.tick(); later(m); later(m)
check("stopped on purpose (the web page's Stop): it stays stopped", m.proc is None)

m.random_song()
m.stop()
m.leave()
m.tick(); later(m); later(m)
check("in the terminal: not there", m.proc is None)
m.enter()
m.tick(); later(m)
check("...back in media mode: it comes back", m.proc is not None and m.kind == "audio")

m.stop()
m.voice.speaking = True
m.tick(); later(m); later(m)
check("the bot talking: it waits", m.proc is None)
m.voice.speaking = False
m.tick(); later(m)
check("...till it's done", m.proc is not None)

m.stop()
m.set_setting("start_song", "Off")
m.tick(); later(m); later(m)
check("the setting turned off: nothing comes back", m.proc is None)
m.leave()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
