"""The Fortune Cookie, in Apps (pitato/fortune.py, screens/fortune.py): a fortune on the page, a fortune cookie over it
and six lucky numbers under it. A cracks a new cookie open: a new fortune (every one of them before any comes again),
its cookie cracking frame by frame, its words coming in as it opens, then still. The d-pad picks its colours (up and
down the words', left and right the background's), L and R its font, Y an effect, each kept and said; X reads it out
loud in your Bot's voice, its lucky numbers too (X again stops, and so does A: not over the next one). Its buttons fit
along the GPi Case's screen; START has its options; B goes back to the list."""
import json, os, shutil, subprocess, sys, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np

S = SP + "/t_fortune"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
apps = next(t for t in g.LIBRARY if t["name"] == "Apps")
check(f"Apps has the Fortune Cookie, after Notes ({apps['children'][:4]})",
      apps["children"][:3] == ["Clock", "Notes", "Fortune Cookie"])
fi = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Fortune Cookie")


def flush():
    m.dirty = True
    m.flush()
    return np.asarray(FB.last.convert("RGB")).astype(int)


def cookie_px(a):
    """How much of the top of the page is the cookie's colour."""
    return int((np.abs(a[70:190] - np.array(g.COOKIE[0])).max(axis=2) < 30).sum())


m.open_app(fi)
s = m.sim_game()
s.cracked = 0.0                                       # (opened: its cookie open already)
page = flush()
ink = np.array(dict(g.NOTE_INKS)[s.values["ink"]])
words = int((np.abs(page[180:400] - ink).max(axis=2) < 40).sum())
check(f"opened: a fortune ({s.text!r}), and six lucky numbers, 1 to 49, none twice, in order ({s.numbers})",
      s.text in g.FORTUNES and len(s.numbers) == 6 and all(1 <= n <= 49 for n in s.numbers)
      and list(s.numbers) == sorted(set(s.numbers)))
check(f"...on the page: the cookie over it ({cookie_px(page)} px), its words ({words} px)", cookie_px(page) > 800
      and words > 300)
check(f"...its buttons: {s.hints()}", s.hints() == [("A", "New one"), ("▲▼", "Colour"), ("◀▶", "Background"),
                                                  ("L R", "Font"), ("X", "Read it")])
foot = page[480 - 48 + 3:]
right = np.argwhere(np.abs(foot - np.array(g.BG)).sum(axis=2) > 60)[:, 1].max()
check(f"...all of them along the GPi Case's screen, the last ending before its edge ({right})", right < 630)
check(f"...nothing changing on it: drawn again only now and then ({s.frame_in(time.time()):.0f} s)",
      s.frame_in(time.time()) >= 10)

first = s.text
m.press("a")
t0 = s.cracked
check(f"A: a new fortune ({s.text!r}), its cookie cracking open now, frame by frame ({s.frame_in(t0 + 0.1):.2f} s)",
      s.text != first and s.text in g.FORTUNES and abs(t0 - time.time()) < 1 and s.frame_in(t0 + 0.1) < 0.1)
looks = []
for t in (0.0, 0.3, 0.6, 1.0):
    s.cracked = time.time() - t * g.FORTUNE_CRACK
    looks.append(flush())
moved = [int((np.abs(looks[k] - looks[k + 1]).sum(axis=2) > 60).sum()) for k in range(3)]
w0, w1 = (int((np.abs(x[180:400] - ink).max(axis=2) < 40).sum()) for x in (looks[0], looks[-1]))
check(f"...each frame of it its own ({moved} px changed), its words coming in as it opens ({w0} then {w1} px)",
      all(n > 100 for n in moved) and w0 < 50 < w1)
check(f"...then still ({s.frame_in(time.time()):.0f} s)", s.frame_in(time.time()) >= 10)
seen = {first, s.text}                                # (the one it opened on, and the one A cracked)
for _ in range(len(g.FORTUNES) - 2):
    m.press("a")
    seen.add(s.text)
check(f"A on and on: every fortune before any comes again ({len(seen)} of {len(g.FORTUNES)})",
      len(seen) == len(g.FORTUNES))
m.press("a")
check("...and then round again, not the last one straight after itself", s.text in g.FORTUNES)

for name, key, want in (("up", "ink", "Ink"), ("down", "ink", "White"), ("down", "ink", "Amber"),
                        ("right", "paper", "Black"), ("left", "paper", "Night"), ("left", "paper", "Paper"),
                        ("r", "font", "Handwriting"), ("r", "font", "Typewriter"), ("l", "font", "Handwriting"),
                        ("y", "effect", "Glow")):
    m.press(name)
    if s.values.get(key) != want or m.setting(f"sim_fortune_{key}") != want:
        break
check(f"up and down its colour, left and right its background, L and R its font, Y its effect: each kept, and said "
      f"({toasts[-1:]}, {s.values})", s.values == {"ink": "Amber", "paper": "Paper", "font": "Handwriting",
                                                   "size": "Normal", "effect": "Glow"}
      and toasts[-1] == "Effect: Glow" and m.setting("sim_fortune_paper") == "Paper")
s.cracked = 0.0
page = flush()
check(f"...its page in them (the background: the paper's) ({tuple(page[300, 20])})",
      tuple(page[300, 20]) == (246, 240, 226))

aloud, stopped = [], []
m.say_aloud = lambda text=None: (aloud.append(text), (True, ""))[1]
m.voice.stop = lambda *a, **k: (stopped.append(1), setattr(m.voice, "speaking", False))[0]
m.press("x")
m.voice.speaking = True
m.tick()
check(f"X: read out loud, its lucky numbers too ({aloud[-1:]}); its button says Stop while it is ({s.hints()[-1]})",
      aloud == [s.said()] and s.said().startswith(s.text) and "lucky numbers are" in s.said()
      and s.said().endswith(f"and {s.numbers[-1]}.") and s.hints()[-1] == ("X", "Stop"))
m.press("x")
m.tick()
check(f"...X again: stopped ({stopped})", stopped == [1] and s.hints()[-1] == ("X", "Read it"))
m.press("x")
m.voice.speaking = True
m.tick()
m.press("a")
m.tick()
check(f"...A while it's reading: stopped, not read on over the new one ({stopped})", stopped == [1, 1]
      and s.hints()[-1] == ("X", "Read it"))

m.press("start")
rows = [k for k, _, _, _ in m.sim_rows(type(s))]
check(f"START: its options {rows}", m.sim_opts == 0 and rows == ["ink", "paper", "font", "size", "effect", "full"])
m.press("b")
m.press("b")
check("B: back to the list, the Fortune Cookie picked", m.view == "list" and g.LIBRARY[m.tab]["name"] == "Apps"
      and m.tab_items()[m.sels[m.tab]]["title"] == "Fortune Cookie")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
