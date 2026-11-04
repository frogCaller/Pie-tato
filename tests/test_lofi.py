"""Lofi art on Now playing: the three scenes on their own (each the screen's size, a wide screen's and a turned one's
too, what moves moving, the window's rain the same again every 6 seconds, quick enough for a Pi Zero), each song its
own scene; then in media mode: SELECT puts it on (kept for next time), the whole screen the scene with what's playing
in its corner and how far through it is, a frame now and then (not twenty a second), the loop waiting meanwhile,
Paused when it is, radio too, SELECT again back to the usual page (its buttons fit, SELECT Art among them), L still the
one before, and the battery saver leaving it on while a song plays."""
import io, os, shutil, sys, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from pitato import lofi as L

S = SP + "/tlofi"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the scenes ---------------------------------------------------------------------------------------------
art = L.LofiArt()
for scene in L.LOFI_SCENES:
    sizes = {}
    for W, H in ((640, 480), (853, 480), (480, 640)):
        img = art.frame(scene, W, H, 3.0)
        sizes[(W, H)] = img.size
    a = np.asarray(art.frame(scene, 640, 480, 3.0)).astype(int)
    b = np.asarray(art.frame(scene, 640, 480, 3.0 + (6.0 if scene != "rooftop" else 20.0) + 0.5)).astype(int)
    blocks = (a.reshape(120, 4, 160, 4, 3) == a[::4, ::4][:, None, :, None, :]).all()
    colours = len(np.unique(a.reshape(-1, 3), axis=0))
    check(f"{scene}: the screen's size each time {sorted(set(sizes.values())) == sorted(set(sizes)) and 'ok'}, "
          f"big square pixels ({blocks}), {colours} colours, something moving ({int((a != b).any(axis=2).sum())} px)",
          all(sizes[k] == k for k in sizes) and blocks and 12 < colours < 400 and (a != b).any(axis=2).sum() > 30)
w0 = np.asarray(art.frame("window", 640, 480, 1.0))
w4 = np.asarray(art.frame("window", 640, 480, 7.0))
check("the window's rain and steam: the same again every 6 seconds", (w0 == w4).all())
times = {}
for scene in L.LOFI_SCENES:
    art.frame(scene, 640, 480, 0.0)
    t0 = time.perf_counter()
    for k in range(20):
        art.frame(scene, 640, 480, k / 6)
    times[scene] = (time.perf_counter() - t0) / 20 * 1000
check(f"a frame is quick ({', '.join(f'{k} {v:.1f} ms' for k, v in times.items())})", max(times.values()) < 8)
check(f"how often each draws a frame: {[(k, s.fps) for k, s in L.SCENES.items()]}",
      L.SCENES["rooftop"].fps < L.SCENES["window"].fps <= 6 and L.SCENES["train"].fps <= 6)
picks = [L.lofi_scene(f"/music/song {i}.mp3") for i in range(60)]
check(f"each song its own scene, the same each time ({[picks.count(s) for s in L.LOFI_SCENES]} of 60)",
      all(picks.count(s) > 8 for s in L.LOFI_SCENES) and L.lofi_scene("/music/song 3.mp3") == picks[3])

# ---- in media mode ------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last, self.shows = None, 0

    def show(self, img):
        self.last = img.copy(); self.shows += 1; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
music = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
items = [{"title": f"Song {k}", "src": f"{S}/home/u/Music/song{k}.mp3", "sub": "", "kind": "audio"} for k in range(3)]
said = []
m.to_player = lambda line: said.append(line)
m.queue, m.qi, m.cur, m.kind = items, 0, items[0], "audio"
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
m.meta = {"title": "Song 0", "artist": "Someone", "length": 200}
m.pos = 50
m.tab, m.view, m.now_from = music, "now", "list"
m.dirty = True
m.flush()
plain = m.fb.last
hints = [k for k, *_ in m.now_hints()] if hasattr(m, "now_hints") else None
taps = [t for t in getattr(m, "taps", [])] if hasattr(m, "taps") else []
check("Now playing as it was, its buttons along the bottom (SELECT Art among them)",
      not m.now_art() and plain.getpixel((320, 470)) == g.BG)
plain.save(SP + "/lofi_plain.png")
m.press("select")
check(f"SELECT: lofi art, kept for next time ({m.msg!r})", m.now_art() and m.setting("now_art") == "On"
      and g.Media().setting("now_art") == "On" and "Lofi art" in (m.msg or ""))
m.msg = None
m.dirty = True
m.flush()
shot = m.fb.last
shot.save(SP + "/lofi_window.png")
a = np.asarray(shot).astype(int)
corner = a[480 - 60:480 - 30, 40:200]
check("...the whole screen the scene: no status bar, no buttons", tuple(a[4, 320]) != g.BG and tuple(a[470, 600]) != g.BG
      and not (a[440:480, 300:640] == np.array(g.BG)).all(axis=2).any())
check("...what's playing in the corner, on a dark card", corner.mean() < 120 and (a[400:470, 30:200].max(axis=2) > 200).any())
bar = a[480 - 18 - 13: 480 - 18 - 10, 34:300]
check("...how far through it is: a quarter of a thin line in the colour", (np.abs(bar - np.array(g.ACCENT)).max(axis=2) < 30).any())
m.tick()
check(f"...the loop waits a little between frames ({m.tick_limit():.2f} s), not a twentieth", 0.05 < m.tick_limit() <= 0.25)
m.fb.shows = 0
for _ in range(40):
    fake[0] += 0.05
    m.tick()
    m.flush()
fps = L.SCENES[L.lofi_scene(items[0]["src"])].fps
check(f"...{m.fb.shows / 2:.1f} frames a second (its scene's {fps})", fps - 1 <= m.fb.shows / 2 <= fps + 1.5)
m.press("a")
m.dirty = True
m.flush()
check("A: paused, and it says so in the corner", m.paused and m.lofi_card[0][1] == "Paused")
m.press("a")
for k, scene in enumerate(L.LOFI_SCENES):
    it = next(x for x in ({"title": f"S{j}", "src": f"/m/s{j}.mp3", "sub": "", "kind": "audio"} for j in range(200))
              if L.lofi_scene(x["src"]) == scene)
    m.cur = it
    m.dirty = True
    m.flush()
    m.fb.last.save(f"{SP}/lofi_{scene}.png")
m.cur = items[0]
m.paused = False
check("the battery saver leaves the art on while a song plays (something to watch)", m.worth_watching(fake[0]))
m.paused = True
check("...but not once it's paused", not m.worth_watching(fake[0]))
m.paused = False
skipped = []
m.skip = lambda d: skipped.append(d)
m.press("r")
m.press("l")
m.press("select")
check(f"R and L: the next song, the one before ({skipped}); SELECT no longer the one before", skipped == [1, -1])
m.dirty = True
m.flush()
check("SELECT again: Now playing as it was", not m.now_art() and m.setting("now_art") == "Off"
      and m.fb.last.getpixel((320, 470)) == g.BG)
m.fb.last.save(SP + "/lofi_off.png")
k = m.fonts
from PIL import Image, ImageDraw
d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
x = 20
for key, label in (("A", "Pause"), ("◀▶", "Seek"), ("L R", "Prev/next"), ("Y", "Shuffle"), ("SELECT", "Art"), ("B", "List")):
    x += m.key_w(d, key) + 7 + d.textlength(label, font=k["small"]) + 18
check(f"...its buttons fit along the bottom ({x - 18:.0f} of 640)", x - 18 <= 632)
m.press("select")
m.press("b")
check("B: back to the list, the art still on for next time", m.view == "list" and m.setting("now_art") == "On")
m.view = "now"
m.kind, m.cur = "radio", {"title": "Night FM", "src": "http://radio.example/stream", "sub": "Lofi beats", "kind": "radio"}
m.meta = {"song": "Some Tune"}
m.dirty = True
m.flush()
m.fb.last.save(SP + "/lofi_radio.png")
check("radio too: the station and what's on, no line (it's live)", m.now_art() and m.lofi_card[0][:2] == ("Night FM", "Some Tune")
      and not m.lofi_card[0][4])
m.view = "list"
check("off Now playing: no frames, the usual wait", not m.now_art() and m.tick_limit() == 0.25)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
