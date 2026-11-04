"""Settings > Random song at start-up: off to start with; on, a song from ~/Music picked at random plays a moment after
the app starts (on the home screen or in the terminal), the rest after it in a random order, and you stay where you
are as one song follows another."""
import io, json, os, random, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_start_song"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music/Album"); os.makedirs(HOME + "/Pictures")
SONGS = [HOME + f"/Music/song {k:02d}.mp3" for k in range(1, 9)] + [HOME + "/Music/Album/deep cut.ogg"]
for p in SONGS:
    open(p, "wb").write(b"ID3")
open(HOME + "/Music/notes.txt", "w").write("not a song")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
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
    spawned.append((args, target))
    self.started = time.monotonic()
    self.proc = FakeProc()


g.Media.spawn = fake_spawn


prev = None


def fresh(settings=None):
    """A new start of the app with these settings (the last one's done saving first: its file-length thread saves
    the state as it stops)."""
    global prev
    if prev is not None:
        prev.active = False
        if prev.prober is not None:
            prev.prober.join(10)
    json.dump({"settings": settings or {}}, open(g.STATE_FILE, "w"))
    spawned.clear()
    prev = g.Media()
    return prev


def due(m):
    """Its moment has come (the input loop ticks every couple of seconds at most)."""
    m.boot_song = time.monotonic() - 0.01
    m.tick()


# ---- the setting
m = fresh()
rows = [r[0] for r in m.settings_rows()]
at = rows.index("start")
check(f"Settings has it, just after At start-up ({rows[at:at + 2]})", rows[at:at + 2] == ["start", "start_song"])
row = m.settings_rows()[rows.index("start_song")]
check(f"...called Random song at start-up, off or on ({row[1]}: {row[2]})", row[1] == "Random song at start-up"
      and row[2] == ["Off", "On"] and m.setting("start_song") == "Off")
check("off to start with: nothing waiting to play", not m.boot_song)
m.enter()
m.tick(); m.tick()
check("...and nothing plays", not spawned and m.proc is None)
m.view, m.tab = "list", next(i for i, t in enumerate(g.LIBRARY) if t["type"] == "settings")
m.set_sel = rows.index("start_song")
m.press("right")
saved = json.load(open(g.STATE_FILE))["settings"]
check(f"right turns it on, and it's kept ({saved.get('start_song')})", m.setting("start_song") == "On"
      and saved.get("start_song") == "On")
check("...not playing anything now (only when the app starts)", not spawned and m.proc is None)
m.dirty = True; m.flush()
shot = FB.last
m.press("left")
check("left turns it off again", m.setting("start_song") == "Off")
m.press("a")
check("A switches it too", m.setting("start_song") == "On")
os.makedirs(S + "/shots", exist_ok=True)
m.press("a"); m.dirty = True; m.flush(); FB.last.save(S + "/shots/settings_off.png")
shot.save(S + "/shots/settings_on.png")
m.leave()

# ---- on: the app starts on the home screen
m = fresh({"start_song": "On"})
check("on: a song's due a moment after the app starts", m.boot_song and 1 <= m.boot_song - time.monotonic() <= 3)
m.enter()
m.tick()
check("...not straight away (the home screen first)", not spawned and m.proc is None)
due(m)
check(f"then one plays: {os.path.basename(spawned[-1][1]) if spawned else None}", len(spawned) == 1
      and spawned[0][1] in SONGS and m.kind == "audio" and m.cur and m.cur["src"] == spawned[0][1])
check("...with mplayer's music settings, at your volume", spawned[0][0][:4] == ["mplayer", "-slave", "-quiet", "-novideo"]
      and "-volume" in spawned[0][0] and spawned[0][0][spawned[0][0].index("-volume") + 1] == str(m.volume))
check(f"...and every song after it, in some order ({len(m.queue)})", sorted(it["src"] for it in m.queue) == sorted(SONGS)
      and m.qi == 0 and not m.shuffle)
check("you stay on the home screen, its card saying what's playing", m.view == "home" and m.playing_now())
m.dirty = True; m.flush(); FB.last.save(S + "/shots/home_playing.png")
m.tick(); m.tick()
check("only the once", len(spawned) == 1 and not m.boot_song)
mi = next(i for i, t in enumerate(g.LIBRARY) if t.get("kind") == "audio")
check("the Music list is as it was (A-Z), the song marked there", [it["src"] for it in m.tab_items(mi)]
      == sorted(SONGS, key=lambda p: os.path.basename(p).lower()) and any(it["key"] == m.cur["key"] for it in m.tab_items(mi)))

# the song ends: the next, and you stay where you are
m.home_sel = 3; m.dirty = True; m.flush()
first = m.cur["src"]
m.started = time.monotonic() - 200
m.proc.dead = True
m.tick()
check(f"it ends: the next one plays ({os.path.basename(m.cur['src']) if m.cur else None})", len(spawned) == 2
      and m.qi == 1 and m.cur["src"] == m.queue[1]["src"] != first)
check("...and you're still on the home screen, where you were", m.view == "home" and m.home_sel == 3)

# a photo open as the song changes: still open
pi = next(i for i, t in enumerate(g.LIBRARY) if t["type"] == "photos")
from PIL import Image
Image.new("RGB", (40, 30), (200, 10, 10)).save(HOME + "/Pictures/red.png")
m.load_tab(pi); m.tab = pi; m.view = "list"
m.sels[pi] = 0
m.press("a")
was_view = m.view
m.started = time.monotonic() - 200; m.proc.dead = True; m.tick()
check(f"a picture you're looking at stays open as the next song starts ({was_view} -> {m.view})",
      was_view == "photo" and m.view == "photo" and m.qi == 2)
m.press("b")

# Now playing, as before
m.tab = mi; m.view = "list"
m.sels[mi] = 4
m.press("a")
check("picking a song in Music still opens Now playing, the list in its own order",
      m.view == "now" and m.cur["src"] == m.tab_items(mi)[4]["src"] and m.queue == m.tab_items(mi) and m.qi == 4)
m.started = time.monotonic() - 200; m.proc.dead = True; m.tick()
check("...and the next one shows there", m.view == "now" and m.qi == 5)
m.press("b")
check("B: the list; the next song after that keeps you there", m.view == "list")
m.started = time.monotonic() - 200; m.proc.dead = True; m.tick()
check(f"...(playing {m.qi + 1} of {len(m.queue)})", m.view == "list" and m.qi == 6)
# the last one ends (the setting on, it goes round again: test_music_back.py; off, the list ends)
m.set_setting("start_song", "Off")
m.qi = len(m.queue) - 1; m.cur = m.queue[-1]
m.go_home()
m.started = time.monotonic() - 200; m.proc.dead = True; m.tick()
check("the last one ends while you're on the home screen: you stay there", m.view == "home" and m.proc is None
      and m.kind is None and not m.playing_now())
m.play(m.tab_items(mi), len(m.tab_items(mi)) - 1)
m.started = time.monotonic() - 200; m.proc.dead = True; m.tick()
check("...on Now playing: back to the list, as before", m.view == "list" and m.proc is None)
m.leave()

# ---- random: not always the same song
firsts = set()
for k in range(12):
    random.seed(k)
    m = fresh({"start_song": "On"})
    due(m)
    firsts.add(m.cur["src"] if m.cur else None)
    m.stop()
check(f"a different song from one start to another ({len(firsts)} different in 12)", len(firsts) >= 4 and None not in firsts)

# ---- the app starts in the terminal
m = fresh({"start_song": "On", "start": "Terminal"})
check("starting in the terminal", not m.boot_media and not m.active)
due(m)
check("...the song plays there too (music keeps playing in the terminal)", len(spawned) == 1 and m.kind == "audio"
      and not m.active and m.view != "now")
m.enter()
check("Home: the home screen, with the song on its card", m.view == "home" and m.playing_now())
m.press("start")
check("...START: Now playing, B back home", m.view == "now" and (m.press("b"), m.view)[1] == "home")
m.stop(); m.leave()

# ---- nothing in ~/Music
shutil.move(HOME + "/Music", S + "/Music.away"); os.makedirs(HOME + "/Music")
m = fresh({"start_song": "On"})
m.enter()
due(m)
check(f"no songs: nothing plays, and it says why ({m.msg})", not spawned and m.proc is None
      and m.msg == "No songs in ~/Music to play at start-up" and m.view == "home")
m.leave()
m = fresh({"start_song": "On", "start": "Terminal"})
due(m)
check("...(quietly, in the terminal)", not spawned and m.proc is None)
shutil.rmtree(HOME + "/Music"); shutil.move(S + "/Music.away", HOME + "/Music")

# ---- something playing already: left alone
m = fresh({"start_song": "On"})
m.enter()
radio = {"key": "r1", "title": "Jazz Radio", "kind": "radio", "src": "http://192.168.1.20:8000/jazz", "sub": ""}
m.play([radio], 0)
due(m)
check("something already playing (the web page put on the radio): it's left playing", len(spawned) == 1
      and m.kind == "radio" and m.cur["title"] == "Jazz Radio" and not m.boot_song)
m.stop(); m.leave()

# ---- a fresh app with it on, then off again: nothing
m = fresh({"start_song": "Off"})
check("off: nothing due", not m.boot_song)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
