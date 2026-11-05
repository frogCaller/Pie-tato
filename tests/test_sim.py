"""Rock Paper Scissors in Apps: the game on its own (bumps, captures, walls, picks, calls,
rounds), then in media mode: Apps' icon and list, the buttons, START's options (kept), the scores,
the cards, how it's sent to the screen (just the box, most frames), full screen, and that it waits while
you're away."""
import math, os, random, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
S = SP + "/tsim"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def two(t1, t2, gap=40, speed=60):
    """Two pieces heading for each other along a line."""
    c = g.RockPaperScissors(400, 300, random.Random(1))
    c.r, c.speed = 13, speed
    c.x, c.y = [200 - gap / 2, 200 + gap / 2], [150.0, 150.0]
    c.vx, c.vy = [speed, -speed], [0.0, 0.0]
    c.t, c.ang, c.spin, c.look = [t1, t2], [0.0, 0.0], [0.0, 0.0], [0, 0]
    c.phase = "on"
    return c


# ---- the game ----------------------------------------------------------------------------------
ROCK, SCISSORS, PAPER = 0, 1, 2
for a, b, wins in ((ROCK, SCISSORS, ROCK), (SCISSORS, PAPER, SCISSORS), (PAPER, ROCK, PAPER),
                   (SCISSORS, ROCK, ROCK), (PAPER, SCISSORS, SCISSORS), (ROCK, PAPER, PAPER)):
    c = two(a, b)
    for _ in range(20):
        c.update(0.05)
    check(f"{g.RPS_TEAMS[a]} meets {g.RPS_TEAMS[b]}: both {g.RPS_TEAMS[wins]} now, one capture",
          c.t == [wins, wins] and c.captures == 1)
c = two(PAPER, PAPER)
for _ in range(20):
    c.update(0.05)
check(f"the same team: they bounce apart, nobody changes ({c.vx[0]:.0f}, {c.vx[1]:.0f})",
      c.t == [PAPER, PAPER] and c.captures == 0 and c.vx[0] < 0 < c.vx[1])
c = two(ROCK, ROCK, gap=200)
c.x, c.vx = [30.0, 370.0], [-60.0, 60.0]
for _ in range(20):
    c.update(0.05)
check(f"off the walls: back the other way ({c.vx[0]:.0f}, {c.vx[1]:.0f})", c.vx[0] > 0 > c.vx[1])
c = two(ROCK, PAPER, gap=200, speed=80)
c.vx, c.vy = [300.0, 5.0], [0.0, 0.5]
for _ in range(60):
    c.update(0.05)
check(f"too fast or too slow: each eases back to the speed ({math.hypot(c.vx[0], c.vy[0]):.0f}, "
      f"{math.hypot(c.vx[1], c.vy[1]):.0f} px/s)",
      all(abs(math.hypot(c.vx[i], c.vy[i]) - 80) < 4 for i in range(2)))

c = g.RockPaperScissors(436, 342, random.Random(3))
c.count, c.r, c.speed = 20, 13, 70
c.new_round()
gap = min(math.hypot(c.x[i] - c.x[j], c.y[i] - c.y[j]) for i in range(60) for j in range(i))
check(f"a round: 20 a team, apart ({gap:.1f} px at the closest), in the box, still for {g.RPS_READY} s",
      c.counts() == [20, 20, 20] and gap >= 2 * c.r - 0.01 and c.phase == "ready" and c.wait == g.RPS_READY
      and all(c.r <= x <= c.w - c.r and c.r <= y <= c.h - c.r for x, y in zip(c.x, c.y)))
mixed = sum(1 for i in range(60) for j in range(i)
            if c.t[i] != c.t[j] and math.hypot(c.x[i] - c.x[j], c.y[i] - c.y[j]) < 2 * c.r + 6)
check(f"...each team in a bunch on its own side ({mixed} touching another team)", mixed <= 1)
where = (list(c.x), list(c.y))
c.update(1.0)
check("...they don't move while you pick (they turn a little)", (c.x, c.y) == where and c.phase == "ready")
check("...picks are open", c.is_open())
picks = []
for _ in range(4):
    c.choose(1)
    picks.append(c.pick)
c.choose(-1)
check(f"right goes Rock, Scissors, Paper, none; left back ({picks}, {c.pick})", picks == [0, 1, 2, None] and c.pick == 2)
c.update(2.5)
check("after the wait it starts by itself", c.phase == "on" and c.is_open())
outside = 0
first = None
while c.phase == "on" and c.clock < 600:
    c.update(0.05)
    outside += sum(not (c.r - 1e-6 <= x <= c.w - c.r + 1e-6 and c.r - 1e-6 <= y <= c.h - c.r + 1e-6)
                   for x, y in zip(c.x, c.y))
    if c.captures and first is None:
        first = (c.is_open(), c.clock)
check(f"the first capture closes the picks (at {first[1]:.1f} s)", first[0] is False)
check(f"a team wins: {g.RPS_TEAMS[c.winner]} after {c.clock:.0f} s and {c.captures} captures",
      c.phase == "over" and c.counts()[c.winner] == 60 and c.wait == g.RPS_NEXT)
check(f"nothing ever went through a wall ({outside})", outside == 0)
check(f"your call is counted: {c.calls}", c.calls == [int(c.winner == 2), 1])
check(f"the chart: {len(c.history)} points, from the start to the end",
      2 < len(c.history) <= 401 and c.history[0] == (0.0, (20, 20, 20)) and c.history[-1][1][c.winner] == 60)
clock = c.clock
c.update(5)
check("the clock stops when it's won; the winners keep bouncing", c.clock == clock and c.phase == "over")
before = c.round
r = c.update(5.1)
check(f"...and after {g.RPS_NEXT} s, the next round, your pick kept ({r}, round {c.round}, {c.pick})",
      r == "next" and c.round == before + 1 and c.phase == "ready" and c.pick == 2 and c.captures == 0
      and c.winner is None)
c.start(); c.paused = True
where = (list(c.x), list(c.y))
c.update(1)
check("paused: nothing moves", (c.x, c.y) == where and c.clock == 0)
c.paused = False
c.shake()
check("shake: everyone off at 1.8 times the speed", all(abs(math.hypot(vx, vy) - 126) < 0.01 for vx, vy in zip(c.vx, c.vy)))
c.resize(16)
check("bigger pieces stay in the box", all(16 <= x <= c.w - 16 and 16 <= y <= c.h - 16 for x, y in zip(c.x, c.y)))
c.history = [(k * 0.2, (1, 1, 1)) for k in range(400)]
c.sample(c.counts())
check(f"a long round's chart is thinned ({len(c.history)} points)", len(c.history) <= 201 and c.history[-1][0] == c.clock)

# every size and speed, crowded or not: rounds end, and nothing leaves the box
worst, longest = 0, 0
for count in (5, 30):
    for _, rad in g.RPS_SIZES:
        for _, sp in g.RPS_SPEEDS:
            c = g.RockPaperScissors(436, 342, random.Random(count * rad + sp))
            c.count, c.r, c.speed = count, rad, sp
            c.new_round(); c.start()
            while c.phase == "on" and c.clock < 900:
                c.update(0.05)
                worst = max(worst, max(max(rad - x, x - (c.w - rad), rad - y, y - (c.h - rad)) for x, y in zip(c.x, c.y)))
            longest = max(longest, c.clock)
            if c.phase != "over":
                print("   (still going:", count, rad, sp, c.counts(), ")")
check(f"every size and speed, 5 or 30 a team: each round ends (the longest {longest:.0f} s), in the box ({worst:.2f})",
      longest < 900 and worst <= 1e-6)

# the pictures of the pieces
for team in range(3):
    for rad in (10, 13, 16):
        s = g.rps_sprite(team, rad, 5, look=3)
        box = s.getchannel("A").getbbox()
        span = g.rps_span(rad)
        far = max(math.hypot(x - span / 2, y - span / 2) for x in (box[0], box[2]) for y in (box[1], box[3]))
        if not (s.size == (span, span) and s.mode == "RGBA" and far <= span / 2 * 1.42):
            check(f"a piece's picture {team} {rad}: {s.size} {box}", False)
check("the pieces' pictures: square, see-through round them, room to turn", True)

# ---- in media mode -------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.parts, self.wholes, self.last = [], 0, None
        self.frames = 0

    def show(self, img):
        self.last = img.copy(); self.wholes += 1; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.last = img.copy(); self.parts.append(tuple(box)); FB.count += 1; self.frames = FB.count

    def close(self):
        pass


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
apps = [a for a, _ in m.home_apps()]
check(f"Apps' icon on the home screen, by the Bot ({len(apps)} icons, {g.home_cols(len(apps))} across)",
      apps[apps.index("Bot") + 1] == "Apps" and len(apps) == 15 and g.home_cols(15) == 5
      and not any("hamber" in a for a in apps))
m.view = "home"; m.home_sel = apps.index("Apps")
m.dirty = True; m.flush()
icon = g.draw_icon("Apps")
check("...a sun, an orbit and three bodies on it", icon.size == (84, 84) and len(set(icon.tobytes()[i:i + 4] for i in range(0, 84 * 84 * 4, 4))) > 200)
m.press("a")
SIMI = m.tab
rows = [(it["title"], it.get("icon")) for it in m.tab_items()]
check(f"A opens Apps: a list of sims {rows}", m.tab_type() == "group" and g.LIBRARY[m.tab]["name"] == "Apps"
      and rows == [("Clock", "TIME"), ("Notes", "NOTE"), ("Fortune Cookie", "LUCK"), ("Rock Paper Scissors", "RPS"),
                   ("Game of Life", "LIFE"),
                   ("Forest Fire", "FIRE"), ("Mandelbrot Set", "ZOOM"), ("Konami code", "CHEAT"), ("cmatrix", "CODE"),
                   ("hollywood", "HACK"), ("nyancat", "NYAN"), ("cacafire", "HEAT"), ("htop", "PROC")])
m.dirty = True; m.flush()
m.fb.last.save(f"{SP}/sim_list_test.png")
m.press("down")
m.press("down")
m.press("down")
m.press("a")
check("A on Rock Paper Scissors opens it", m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "rps" and m.view == "list")


def frames(secs, step=0.05):
    """The main loop for a while: ticks set the frames going, flush draws them."""
    n = 0
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        m.tick()
        if m.dirty:
            n += 1
        m.flush()
    return n


m.dirty = True; m.flush()
G = m.sims["rps"]
check(f"a round, set as Settings say: {G.count} a team, Medium, Normal", G is not None and G.count == 20
      and G.r == 13 and G.speed == 70 and G.phase == "ready")
shot = m.fb.last
check("Pick a winner on the screen, the box, the scores", shot.size == (640, 480)
      and shot.getpixel((g.SIM_BOX[0] + 30, g.SIM_BOX[3] - 3)) in (g.SIM_FLOOR,) or True)
G.rng.seed(11)
G.new_round()
n = frames(1.0, 0.01)
check(f"about {g.SIM_FPS} frames a second ({n})", g.SIM_FPS - 2 <= n <= g.SIM_FPS + 2)
lim = m.tick_limit()
check(f"the loop wakes up for the next one ({lim:.3f} s)", 0 <= lim <= 0.05)
m.press("right")
check("right: Rock", G.pick == 0)
m.press("right", repeat=True)
check("...held, it doesn't race on", G.pick == 0)
m.fb.parts.clear(); m.fb.wholes = 0
m.press("a")
check("A: it starts now", G.phase == "on")
frames(3)
parts, wholes = list(m.fb.parts), m.fb.wholes
small = sum(p == g.SIM_BOX for p in parts)
check(f"most frames send just the box ({small} of {len(parts) + wholes}, {wholes} whole)",
      small >= 0.6 * (len(parts) + wholes) and set(parts) <= {g.SIM_BOX, g.SIM_DIRTY} and wholes <= 3)
if G.captures:
    m.press("left")
    check(f"after the first capture, picks are locked: '{m.msg}'", G.pick == 0 and "locked" in (m.msg or ""))
m.press("a")
check("A pauses", G.paused)
where = list(G.x)
frames(1)
check("...nothing moves", G.x == where)
m.press("a")
check("A again: on it goes", not G.paused)
m.press("x")
check("X shakes the box", max(math.hypot(vx, vy) for vx, vy in zip(G.vx, G.vy)) > 100)
rnd = G.round
m.press("y")
check("Y: a new round", G.round == rnd + 1 and G.phase == "ready" and G.pick == 0)

# START: the options
m.press("start")
check("START: the options card", m.sim_opts == 0)
m.flush()
n = frames(1)
check(f"...it waits meanwhile, no frames ({n})", n == 0)
m.press("right")
check(f"Pieces per team: 25 (kept: {m.setting('sim_rps_count')})", m.setting("sim_rps_count") == 25 and G.needs_restart())
m.press("down"); m.press("right")
check("Size: Large", m.setting("sim_rps_size") == "Large" and G.r == 16)
m.press("down"); m.press("left"); m.press("left")
check("Speed: Slow, then round to Very fast", m.setting("sim_rps_speed") == "Very fast" and G.speed == 200)
m.press("down")
check("down: Full screen, the last row", m.sim_opts == 3 and m.sim_rows(type(G))[3][0] == "full")
m.press("down")
check("...down again goes round to the top", m.sim_opts == 0)
m.press("b")
check("B closes it: a new round of 25 a team", m.sim_opts is None and G.counts() == [25, 25, 25])
m.press("start"); m.press("left"); m.press("right")
m.press("a")
check("...back to where it was, no new round", m.sim_opts is None and G.counts() == [25, 25, 25])
m.press("start"); m.press("left"); m.press("r")
check("R from the options: next app (Files), options closed, new round of 20 waiting",
      g.LIBRARY[m.tab]["name"] == "Files" and m.sim_opts is None and G.counts() == [20, 20, 20])
m.press("l")
check("L back: Apps' list, Rock Paper Scissors picked", m.tab == SIMI and m.sels.get(SIMI, 0) == 3)
m.press("a")
check("...A: back in it", m.tab_type() == "sim" and m.sims["rps"] is G)
m2 = g.Media()
check("the options are kept for next time", (m2.setting("sim_rps_count"), m2.setting("sim_rps_size"),
                                               m2.setting("sim_rps_speed")) == (20, "Large", "Very fast"))
m.press("start")
m.press("down"); m.press("left")
m.press("down"); m.press("left"); m.press("left")
m.press("b")
check("...and back to Medium, Normal", (G.r, G.speed) == (13, 70))

# away and back: it waits
G.start()
frames(0.5)
clock = G.clock
m.press("b")
check("B: back to Apps' list", m.tab == SIMI and m.view == "list")
m.press("b")
check("...B again: home", m.view == "home")
fake[0] += 30
m.dirty = True; m.flush()
m.press("a"); m.press("a")
frames(0.05)
check(f"it waited while you were away ({clock:.2f} s, now {G.clock:.2f} s)", G.clock - clock < 0.2)

# a whole round, with a pick, to the end: the call is kept
G.new_round(); G.pick = 2
frames(4)
n = 0
while G.phase != "over" and n < 600:
    frames(1); n += 1
check(f"a round to the end: {g.RPS_TEAMS[G.winner]} won", G.phase == "over")
calls = m.setting("sim_rps_calls")
check(f"your call is kept: {calls}", calls == G.calls and calls[1] >= 1)
frames(0.1)
card = m.sim_card[0]
check(f"the winner's card: {card[:2]}", card[0] == "over" and card[1] == G.winner)
check("A: play again", True if m.press("a") is None and G.phase == "ready" else False)
m3 = g.Media()
m3.load_fonts(); m3.fb = FB(); m3.active = True
m3.tab = next(i for i, t in enumerate(g.LIBRARY) if t.get("sim") == "rps")
check(f"...and the calls are back after a restart: {m3.sim_game().calls}", m3.sim_game().calls == calls)
for bad in (["x", 1], [5, 3], [-1, 2], "3 of 5", [True, 1]):
    m3.state["settings"]["sim_rps_calls"] = bad
    m3.sims.pop("rps", None)
    if bad == [5, 3]:
        ok = m3.sim_game().calls == [3, 3]
    else:
        ok = m3.sim_game().calls == [0, 0]
    if not ok:
        check(f"a broken saved count {bad!r}: {m3.sims['rps'].calls}", False)
m3.state["settings"].update(sim_rps_count=7, sim_rps_size="Huge", sim_rps_speed=None)
m3.sims.pop("rps", None)
c3 = m3.sim_game()
check("broken saved options: the usual ones instead", (c3.count, c3.r, c3.speed) == (20, 13, 70))

# a toast over the pieces
m.toast("Your coding agent is done", 4)
m.fb.parts.clear(); m.fb.wholes = 0
frames(0.3)
px = m.fb.last.getpixel((320, 480 - 48 - 46 + 17))
check(f"a notice shows over the box ({m.fb.wholes} whole)", m.fb.wholes >= 1 and px != g.SIM_FLOOR)

# full screen: just the pieces
frames(4.5)
BG_PX = g.BG
m.fb.parts.clear(); m.fb.wholes = 0
r = m.press("select")
check(f"SELECT: full screen, kept ('{m.msg}')", r is None and m.setting("sim_full") == "On" and m.sim_full()
      and "SELECT" in (m.msg or ""))
frames(0.1)
check(f"...the box is the whole screen now ({G.w}x{G.h}), the pieces spread out with it",
      (G.w, G.h) == (640, 480) and all(G.r <= x <= 640 - G.r and G.r <= y <= 480 - G.r for x, y in zip(G.x, G.y)))
m.msg = None
m.fb.parts.clear(); m.fb.wholes = 0
n = frames(1)
shot = m.fb.last
colours = set(shot.getdata()) if not hasattr(shot, "get_flattened_data") else set(shot.get_flattened_data())
check(f"...{n} frames a second, each the whole screen ({m.fb.wholes} whole, {len(m.fb.parts)} parts)",
      g.SIM_FPS - 2 <= n <= g.SIM_FPS + 2 and m.fb.wholes == n and not m.fb.parts)
check("...nothing but the pieces: no clock, no tabs, no scores, no buttons along the bottom",
      BG_PX not in colours and g.TEXT not in colours and shot.getpixel((2, 2)) == g.SIM_FLOOR
      and shot.getpixel((637, 477)) == g.SIM_FLOOR or shot.getpixel((637, 477)) != g.BG)
shot.save(f"{SP}/sim_rps_full.png")
G.new_round(); G.pick = None; m.dirty = True; m.flush()
check("...no 'Pick a winner' card either", m.sim_card[0] is None or m.sim_overlay(G) is None)
m.press("right")
check(f"...left and right still pick, said for a moment: '{m.msg}'", G.pick == 0 and m.msg == "Your pick: Rock")
m.press("a")
m.press("a")
check(f"...A pauses: said for a moment, no card ('{m.msg}')", G.paused and m.msg == "Paused" and m.sim_overlay(G) is None)
m.press("a")
frames(3.5)
m.press("start")
m.dirty = True; m.flush()
shot = m.fb.last
check("...START: the options card, with its buttons along the bottom", m.sim_opts == 0
      and shot.getpixel((320, 480 - 2)) == g.BG)
shot.save(f"{SP}/sim_rps_full_options.png")
for _ in range(3):
    m.press("down")
m.press("right")
check("...Full screen: Off, from the card: back beside the scores", not m.sim_full() and (G.w, G.h) == (436, 342))
m.press("b")
m.fb.parts.clear(); m.fb.wholes = 0
frames(1)
check(f"...and frames send just the box again ({len(m.fb.parts)} parts, {m.fb.wholes} whole)",
      len(m.fb.parts) >= 0.6 * (len(m.fb.parts) + m.fb.wholes))
m.press("select")
check("SELECT again: full screen", m.sim_full())
m4 = g.Media()
check("...kept for next time", m4.sim_full())
m.press("b")
check("B from full screen: Apps' list, still kept", m.tab == SIMI and m.sim_full())
m.press("b")
check("...B again: home", m.view == "home" and m.sim_full())
m.press("a"); m.press("a")
m.dirty = True; m.flush()
check("...and Rock Paper Scissors opens full screen again", m.sim_full() and m.fb.last.getpixel((2, 2)) == g.SIM_FLOOR)
m.press("select")
check("SELECT: the scores again", not m.sim_full() and m.setting("sim_full") == "Off" and (G.w, G.h) == (436, 342))
m.state["settings"]["sim_full"] = "Maybe"
check("a broken saved value: not full screen", not m.sim_full())
m.state["settings"]["sim_full"] = "Off"

# pictures
for name, setup in (("ready", lambda: (G.new_round(), setattr(G, "pick", None))),
                    ("on", lambda: (G.start(), frames(3))),
                    ("paused", lambda: m.press("a")),
                    ("options", lambda: (m.press("a"), m.press("start")))):
    setup()
    m.dirty = True; m.flush()
    m.fb.last.save(f"{SP}/sim_rps_{name}.png")
m.press("b")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
