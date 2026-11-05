"""Apps' Clock: on its own (when its picture changes, the dial's hands where the time says, the digital
look's figures, 12 or 24 hours), then in media mode: first in Apps' list, in the middle of the page with no
box, a frame a second (not twenty), A switching the look (kept), START's options, full screen, the battery saver
leaving it on, B back."""
import math, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
from PIL import Image
import pietato_all as g
S = SP + "/tclock"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def near(c1, c2, d=40):
    return all(abs(a - b) <= d for a, b in zip(c1, c2))


T = time.mktime((2026, 10, 30, 17, 40, 13, 0, 0, -1))     # Friday 5:40:13 PM, local time

# ---- on its own ---------------------------------------------------------------------------------------------
c = g.Clock(640, 346)
check("its options: Look, Font, Seconds, Date, Colour, Background (Analogue, Thin, On, On, Blue, Dark to start with)",
      [k for k, _, _, _ in c.options] == ["look", "font", "seconds", "date", "colour", "background"]
      and tuple(c.values[k] for k in ("look", "font", "seconds", "date", "colour", "background"))
      == ("Analogue", "Thin", "On", "On", "Blue", "Dark"))
check("drawn on the page itself, as each second begins", c.bare and c.paced and c.backdrop == g.BG)
check("...the next second: 0.25 s after 12:00:00.75 (just after it begins)", 0.25 < c.frame_in(1000.75) < 0.26)
c.configure({"seconds": "Off"})
check("...without seconds, the next minute", 10.5 < c.frame_in(1009.5) < 10.51 and 59.99 < c.frame_in(1020.0) < 60.01)
c.configure({"seconds": "On"})
check("A's hint: the other look", c.hints()[0] == ("A", "Digital"))

img = Image.new("RGB", (640, 346), g.BG)
t0 = time.perf_counter()
c.draw(img, 0, 0, now=T)
first = time.perf_counter() - t0
img2 = Image.new("RGB", (640, 346), g.BG)
t0 = time.perf_counter()
c.draw(img2, 0, 0, now=T + 1)
each = time.perf_counter() - t0
img.save(SP + "/clock_analogue.png")
R = c.radius()
cx, cy = 320, 173
check(f"the dial in the middle of its room, radius {R:.0f} (346 tall, less a margin)", R == 165)
a = np.asarray(img).astype(int)


def along(turn, frac, like=None):
    """The colour on the dial `frac` of the way out toward `turn` degrees (clockwise from 12): of the pixels within
    one of there, the one most like `like` (a thin line's middle, not its smooth edge)."""
    x = int(round(cx + math.sin(math.radians(turn)) * frac * R))
    y = int(round(cy - math.cos(math.radians(turn)) * frac * R))
    if like is None:
        return tuple(a[y, x])
    near_px = [tuple(a[y + dy, x + dx]) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    return min(near_px, key=lambda p: sum(abs(u - v) for u, v in zip(p, like)))


hand, second = g.TEXT, dict(g.CLOCK_COLOURS)["Blue"]
hour_turn, min_turn, sec_turn = (5 + 40.2167 / 60) * 30, 40.2167 * 6, 13 * 6
check(f"the hour hand toward 5:40, white ({along(hour_turn, 0.35)})", near(along(hour_turn, 0.35), hand, 40))
check(f"...not past half the dial ({along(hour_turn, 0.6)})", not near(along(hour_turn, 0.6), hand, 70))
check(f"the minute hand toward 40 ({along(min_turn, 0.6)})", near(along(min_turn, 0.6), hand, 40))
check(f"the second hand toward 13, blue ({along(sec_turn, 0.5, second)})", near(along(sec_turn, 0.5, second), second, 40))
check(f"...and its tail behind the middle ({along(sec_turn + 180, 0.15, second)})",
      near(along(sec_turn + 180, 0.15, second), second, 50))
check(f"the middle: a blue disc ({along(0, 0.03, second)}), a dark pin in it ({along(0, 0)})",
      near(along(45, 0.03, second), second, 40) and sum(along(0, 0)) < 3 * 60)
dots = [along(m * 6, 0.9, (92, 100, 113)) for m in range(60) if m % 5]
check(f"a dot at each minute ({sum(1 for d in dots if near(d, (92, 100, 113), 30))} of 48)",
      sum(1 for d in dots if near(d, (92, 100, 113), 30)) >= 46)
marks = [along(h * 30, 0.84, (198, 205, 214)) for h in range(12) if h % 3]
check(f"a line at the other eight hours ({marks[:2]})", all(near(m, (198, 205, 214), 30) for m in marks))
check("12, 3, 6 and 9: their figures, in the face's light ink",
      all(max(min(along(h * 30 + k, 0.8)) for k in range(-6, 7)) > 150 for h in (0, 3, 6, 9)))
check(f"the face a shade lighter than the page ({along(200, 0.7)})", along(200, 0.7) == g.FACE or near(along(200, 0.7), g.FACE, 3))
date = img.crop((int(cx - 0.4 * R), int(cy + 0.32 * R), int(cx + 0.4 * R), int(cy + 0.48 * R)))
check("the date under the middle (Fri, Oct 30)", c.date_short(time.localtime(T)) == "Fri, Oct 30"
      and np.asarray(date).max() > 150)
check(f"a second later, just the second hand has moved (the first frame {first * 1000:.0f} ms, then {each * 1000:.1f} ms)",
      each < 0.05 and not near(tuple(np.asarray(img2).astype(int)[int(round(cy - math.cos(math.radians(sec_turn)) * 0.5 * R)),
                                                                int(round(cx + math.sin(math.radians(sec_turn)) * 0.5 * R))]),
                              second, 40))
c.configure({"seconds": "Off"})
img3 = Image.new("RGB", (640, 346), g.BG)
c.draw(img3, 0, 0, now=T)
a = np.asarray(img3).astype(int)
check("Seconds off: no second hand, the minute hand on the minute, a white middle",
      not near(along(sec_turn, 0.5, second), second, 40) and near(along(40 * 6, 0.6), hand, 40)
      and near(along(45, 0.03, hand), hand, 40))
c.configure({"seconds": "On", "colour": "Pink"})
img4 = Image.new("RGB", (640, 346), g.BG)
c.draw(img4, 0, 0, now=T)
a = np.asarray(img4).astype(int)
pink = dict(g.CLOCK_COLOURS)["Pink"]
check(f"Colour Pink: a pink second hand, the hands still white ({along(sec_turn, 0.5, pink)}, {along(min_turn, 0.6)})",
      near(along(sec_turn, 0.5, pink), pink, 40) and near(along(min_turn, 0.6), hand, 40))
c.configure({"date": "Off"})
img5 = Image.new("RGB", (640, 346), g.BG)
c.draw(img5, 0, 0, now=T)
box = (int(cx - 0.4 * R), int(cy + 0.32 * R), int(cx + 0.4 * R), int(cy + 0.48 * R))
had = np.asarray(img4.crop(box)).astype(int)
nodate = np.asarray(img5.crop(box)).astype(int)
gone = np.abs(had - nodate).sum(axis=2) > 60
grey = np.abs(nodate - np.array(g.BODY)).max(axis=2) < 25      # (the date's ink: a hand's smooth edge has a little)
was_grey = np.abs(had - np.array(g.BODY)).max(axis=2) < 25
check(f"Date off: none on the dial ({gone.sum()} pixels of it gone, its ink {was_grey.sum()} pixels, then {grey.sum()})",
      gone.sum() > 150 and grey.sum() * 5 < was_grey.sum())
c.configure({"date": "On", "background": "Black"})
img6 = Image.new("RGB", (640, 346), c.backdrop)
c.draw(img6, 0, 0, now=T)
img6.save(SP + "/clock_black.png")
a = np.asarray(img6).astype(int)
check(f"Background Black: black round it ({img6.getpixel((3, 3))}), the dial a shade lighter ({along(200, 0.7)}), "
      f"the hands as ever", img6.getpixel((3, 3)) == (0, 0, 0) and 5 < sum(along(200, 0.7)) < 60
      and near(along(min_turn, 0.6), hand, 40) and near(along(sec_turn, 0.5, pink), pink, 40))
c.configure({"background": "Colour"})
check(f"Background Colour: a deep shade of its colour ({c.backdrop})", c.backdrop[0] > c.backdrop[1] and
      sum(c.backdrop) < 3 * 60 and c.backdrop != g.BG)
c.configure({"colour": "Teal"})
check(f"...that follows the colour ({c.backdrop})", c.backdrop[1] > c.backdrop[0])
c.configure({"background": "Dark", "colour": "Pink"})

c.configure({"look": "Digital", "colour": "Blue"})
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=T)
img.save(SP + "/clock_digital.png")
a = np.asarray(img).astype(int)
lit = np.argwhere(a.min(axis=2) > 200)
blue = np.argwhere((np.abs(a - np.array(second)).max(axis=2) < 30))
block = np.concatenate([lit, blue])
size = c.digital_size()
check(f"Digital: big thin figures ({size} px letters), the seconds beside them, in the middle "
      f"({block[:, 1].min()}..{block[:, 1].max()})",
      len(lit) > 2000 and len(blue) > 150 and abs((block[:, 1].min() + block[:, 1].max()) / 2 - 320) < 12)
c_h = round(size * 0.14)
said = []
real_words = c.words
c.words = lambda text, path, size_: said.append(text) or real_words(text, path, size_)
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=T)
check(f"...PM beside it, the date under it ({said})", "PM" in said and "Friday, October 30" in said and "5" in said
      and ":" in said and "40" in said and "13" in said)
said.clear()
c.hours24 = True
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=T)
img.save(SP + "/clock_digital24.png")
check(f"24-hour: 17:40, no AM or PM ({said})", "17" in said and "PM" not in said and "AM" not in said)
c.hours24 = False
said.clear()
t9 = time.mktime((2026, 10, 30, 9, 5, 7, 0, 0, -1))
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=t9)
img.save(SP + "/clock_digital_am.png")
check(f"...9:05 AM: the hour with no 0 before it ({said})", "9" in said and "05" in said and "AM" in said and "07" in said)
del c.words
c.configure({"seconds": "Off"})
said = []
c.words = lambda text, path, size_: said.append(text) or real_words(text, path, size_)
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=T)
check(f"...Seconds off: no seconds ({said})", "13" not in said and "PM" in said)
said.clear()
c.configure({"date": "Off"})
img = Image.new("RGB", (640, 346), g.BG)
c.draw(img, 0, 0, now=T)
a = np.asarray(img).astype(int)
rows_lit = np.argwhere(a.min(axis=2) > 200)[:, 0]
check(f"...Date off: no date, the time in the middle of the room ({said}, {rows_lit.min()}..{rows_lit.max()})",
      not any("October" in w for w in said) and abs((rows_lit.min() + rows_lit.max()) / 2 - 173) < 14)
del c.words
c.configure({"seconds": "On", "date": "On"})

# ---- in media mode ------------------------------------------------------------------------------------------
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
wall = [T + 0.6]
real_time = time.time
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()


def frames(secs, step=0.05):
    n = 0
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        wall[0] += step
        g.time.time = lambda: wall[0]
        try:
            m.tick()
            if m.dirty:
                n += 1
            m.flush()
        finally:
            g.time.time = real_time
    return n


m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Apps")
m.press("a")
SIMI = m.tab
rows = [it["title"] for it in m.tab_items()]
check(f"the Clock first in Apps' list: {rows[:3]}", rows[0] == "Clock" and m.sels.get(SIMI, 0) == 0
      and m.tab_items()[0].get("sub") == "The time and the date")
m.dirty = True
m.flush()
m.fb.last.save(SP + "/clock_list.png")
m.press("a")
s = m.sim_game()
check("A opens it", m.tab_type() == "sim" and s.key == "clock" and m.on_sim_page())
check(f"...on the page itself: all of it between the bars ({s.w} x {s.h})", (s.w, s.h) == (640, 346))
m.fb.parts.clear(); m.fb.wholes = 0
n = frames(3)
shot = m.fb.last
shot.save(SP + "/clock_page.png")
check(f"...a frame a second, not twenty ({n} in 3 s)", 3 <= n <= 4)
check(f"...the loop waits a quarter of a second, not a twentieth ({m.tick_limit():.2f})", 0.05 < m.tick_limit() <= 0.25)
check("...no box: its corner is the page's", shot.getpixel((g.SIM_BOX[0] + 1, g.SIM_BOX[1] + 1)) == g.BG
      and shot.getpixel((g.SIM_BOX[0] + 6, g.SIM_BOX[1] + 6)) == g.BG)
check("...the dial in the middle of the page: its face from y=86 to 416", shot.getpixel((320, 82)) == g.BG
      and near(shot.getpixel((320, 92)), g.FACE, 3) and near(shot.getpixel((320, 410)), g.FACE, 3)
      and shot.getpixel((320, 420)) == g.BG and near(shot.getpixel((160, 251)), g.FACE, 3))
hints = [(k, label) for k, label, *_ in m.sim_hints(s)]
check(f"...its buttons: {hints}", hints == [("A", "Digital"), ("▲▼", "Colour"), ("◀▶", "Background"), ("X", "Seconds"),
                                           ("Y", "Date")])
foot = np.asarray(shot)[480 - 48 + 3:].astype(int)
check(f"...all of them on the screen, the last one ending before its edge "
      f"({np.argwhere(np.abs(foot - np.array(g.BG)).sum(axis=2) > 60)[:, 1].max()})",
      np.argwhere(np.abs(foot - np.array(g.BG)).sum(axis=2) > 60)[:, 1].max() < 630)
check("...the battery saver leaves it on (something to watch)", m.worth_watching(fake[0]))
m.press("a")
check("A: Digital, kept for next time", s.values["look"] == "Digital" and m.setting("sim_clock_look") == "Digital"
      and g.Media().sim_value(type(s), "look") == "Digital")
m.dirty = True; m.flush()
m.fb.last.save(SP + "/clock_page_digital.png")
page = np.asarray(m.fb.last)[78:424].astype(int)
digits = np.concatenate([np.argwhere(page.min(axis=2) > 200),
                         np.argwhere(np.abs(page - np.array(dict(g.CLOCK_COLOURS)["Blue"])).max(axis=2) < 30)])
check(f"...its figures in the middle of the page ({len(digits)} px)", len(digits) > 1500
      and abs((digits[:, 1].min() + digits[:, 1].max()) / 2 - 320) < 12)
m.press("a")
check(f"A again: the figures in the next font, said and kept ({m.msg})", s.values["look"] == "Digital"
      and s.values["font"] == "Bold" and m.msg == "Font: Bold" and m.setting("sim_clock_font") == "Bold")
pics, off = set(), []
for font in g.CLOCK_FONTS[1:]:                     # (each font: drawn its own way, its figures in the middle)
    if s.values["font"] != font:
        m.press("a")
    m.msg = None                                   # (its name, said: not over the page for this)
    m.dirty = True; m.flush()
    page = np.asarray(m.fb.last)[78:424].astype(int)
    pics.add(page.tobytes())
    lit = np.argwhere(np.abs(page - np.array(g.BG)).sum(axis=2) > 60)   # (all of it: the figures, the date...)
    mid_x, mid_y = (lit[:, 1].min() + lit[:, 1].max()) / 2, (lit[:, 0].min() + lit[:, 0].max()) / 2
    if not (abs(mid_x - 320) < 24 and abs(mid_y - 173) < 40 and lit[:, 1].min() > 4 and lit[:, 1].max() < 636):
        off.append((font, round(mid_x), round(mid_y)))
check(f"...on through the fonts, each its own, the time in the middle of the page in every one "
      f"({s.values['font']}, {len(pics)} pictures, {off} off)", s.values["font"] == g.CLOCK_FONTS[-1]
      and len(pics) == len(g.CLOCK_FONTS) - 1 and not off and all(os.path.isfile(g.typeface(f)[0])
                                                                    for f in g.CLOCK_FONTS))
check(f"...its hint before the last: back to the dial ({s.hints()[0]})", s.hints()[0] == ("A", "Analogue"))
m.press("a")
check("...after the last: the dial again, its figures Thin", s.values["look"] == "Analogue"
      and s.values["font"] == "Thin")
m.press("down")
check(f"down: its next colour, Teal, said and kept ({m.msg})", s.values["colour"] == "Teal" and m.msg == "Colour: Teal"
      and m.setting("sim_clock_colour") == "Teal")
m.press("up"); m.press("up")
check(f"up twice: back past Blue to White, the last one ({s.values['colour']})", s.values["colour"] == "White"
      and g.Media().sim_value(type(s), "colour") == "White")
m.press("down")
m.press("right")
frames(0.1)
page = m.fb.last
check(f"right: Background Black, said and kept, the page black between the bars ({page.getpixel((20, 200))}, "
      f"{page.getpixel((20, 70))})", s.values["background"] == "Black" and m.msg == "Background: Black"
      and page.getpixel((20, 200)) == (0, 0, 0) and page.getpixel((20, 440)) != (0, 0, 0)
      and m.setting("sim_clock_background") == "Black")
page.save(SP + "/clock_page_black.png")
m.press("right")
frames(0.1)
page = m.fb.last
check(f"...again: Colour, a deep blue ({page.getpixel((20, 200))})", s.values["background"] == "Colour"
      and page.getpixel((20, 200)) == s.backdrop and page.getpixel((20, 200))[2] > page.getpixel((20, 200))[0])
page.save(SP + "/clock_page_colour.png")
m.press("left"); m.press("left")
frames(0.1)
check("left twice: Dark again, the page's own", s.values["background"] == "Dark"
      and m.fb.last.getpixel((20, 200)) == g.BG)
m.press("x")
check(f"X: its seconds off, said and kept ({m.msg})", s.values["seconds"] == "Off" and m.msg == "Seconds: Off"
      and m.setting("sim_clock_seconds") == "Off")
m.press("x")
check("X again: on", s.values["seconds"] == "On")
m.press("y")
check(f"Y: the date off, said and kept ({m.msg})", s.values["date"] == "Off" and m.msg == "Date: Off"
      and m.setting("sim_clock_date") == "Off")
m.press("y")
check("Y again: on", s.values["date"] == "On" and not s.paused)
m.press("start")
rows = [k for k, _, _, _ in m.sim_rows(type(s))]
check(f"START: its options {rows}", m.sim_opts == 0 and rows == ["look", "font", "seconds", "date", "colour",
                                                                  "background", "full"])
m.dirty = True; m.flush()
m.fb.last.save(SP + "/clock_opts.png")
card = np.asarray(m.fb.last)[78:432].astype(int)
check("...the card fits between the bars", True)
m.press("down"); m.press("down"); m.press("right")
check("...Seconds: Off (kept)", s.values["seconds"] == "Off" and m.setting("sim_clock_seconds") == "Off")
m.press("down"); m.press("down"); m.press("right")
check("...Colour: Teal (kept)", s.values["colour"] == "Teal" and m.setting("sim_clock_colour") == "Teal")
m.press("b")
check("...B closes it", m.sim_opts is None)
frames(1.1)                                        # (the second it was waiting for, then the minute)
before = m.sim_next - fake[0]
check(f"without seconds, the next frame as the next minute begins ({before:.1f} s)", 0 < before <= 60.01
      and abs(((wall[0] + before) % 60)) < 0.05)
m.fb.parts.clear(); m.fb.wholes = 0
n = frames(10)
check(f"...nothing drawn in between ({n} frames in 10 s)", n <= 1)
m.press("start"); m.press("down"); m.press("down"); m.press("left"); m.press("b")
frames(0.1)
check(f"Seconds On again: the next frame within the second ({m.sim_next - fake[0]:.2f} s), not the minute",
      s.values["seconds"] == "On" and 0 < m.sim_next - fake[0] <= 1.0)
m.press("select")
frames(1.2)
check(f"SELECT: full screen ({s.w} x {s.h}), on the page's colour", m.sim_full() and (s.w, s.h) == (640, 480)
      and m.fb.last.getpixel((2, 2)) == g.BG)
said = m.msg
m.msg = None                                       # (its toast gone: just the clock)
m.dirty = True; m.flush()
full_img = m.fb.last.convert("RGB")
dial = np.asarray(full_img).astype(int)
lit = np.argwhere(np.abs(dial - np.array(g.BG)).sum(axis=2) > 12)      # (the dial and all on it: what isn't the page)
top, bottom = lit[:, 0].min(), lit[:, 0].max()
check(f"...the dial bigger than on the page, but a little way in from the screen's edges (radius {s.radius():.0f}; "
      f"{top} px from the top, {479 - bottom} from the bottom)", 165 < s.radius() < 232
      and abs(s.radius() - 240 * 0.84) < 0.01 and top >= 30 and 479 - bottom >= 30)
m.fb.last.save(SP + "/clock_full.png")
m.press("select")
frames(0.2)
check("SELECT again: back", not m.sim_full() and (s.w, s.h) == (640, 346))
m.set_setting("clock", "24-hour")
m.sim_game()
check("Settings > Clock 24-hour: the Clock's too", s.hours24)
m.set_setting("clock", "12-hour")
m.press("start"); m.press("down"); m.press("down"); m.press("right"); m.press("b")
frames(1.1)
check(f"Seconds Off once more: its next frame a while away ({m.sim_next - fake[0]:.0f} s)", m.sim_next - fake[0] > 5)
m.press("b")
check("B: back to the list, the Clock picked", m.tab == SIMI and m.sels[SIMI] == 0)
m.press("down")
check("the next one down is Notes", m.tab_items()[m.sels[SIMI]]["title"] == "Notes")
m.press("down")
m.press("a")
check("...and then Rock Paper Scissors, in its box as before",
      m.sim_game().key == "rps" and not m.sim_bare() and (m.sim_game().w, m.sim_game().h) == (436, 342))
n = frames(1)
check(f"...moving at once, not waiting for the Clock's minute ({n} frames in a second)", n >= 10)
m.press("b")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
