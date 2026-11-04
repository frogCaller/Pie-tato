"""The Bot's Character, as a game's character creator: its face as it always looked until you change it (every look,
with lashes or not, the same as before to the pixel); each of its eyes' and its mouth's steps changing it as it says
(bigger, taller, squarer, further apart; a bigger mouth, kept under tall eyes), always inside the box its frames are
drawn in; the page itself (Settings > Bot > Character, first; the Bot's X menu), its parts (L R, and ▲▼ running from
one into the next), its sliders (◀▶, held: on and on, never past 0 or 10), lashes, colours, its voice (the ones on the
Pi, heard; A: all of them, B back), how it talks; X: one made up (its face always clear on its background, its voice
as it was); Y twice: its look as it started; SELECT: how it looks, happy, sorry...; its face's frames there (only in
its panel); B back to where it was opened from; bot.txt typed by hand (a step too big, not a number); the web page's
Bot's character (sliders, swatches) and its setters; a tap on the web page's copy of it. Pictures saved."""
import os, shutil, subprocess, sys, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tchar2"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.makedirs(S + "/pics")
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
from PIL import Image, ImageChops, ImageDraw
from pitato import face as F
from pitato.screens import bot as B
import pitato.screens.character as C

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h, same = 640, 480, True
    frames = 0

    def __init__(self):
        self.last, self.parts = None, []

    def show(self, img):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()

    def show_part(self, img, box):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()
        self.parts.append(tuple(box))

    def invalidate(self):
        pass

    def close(self):
        pass


def bot_txt():
    for root, _, files in os.walk(S):
        if "bot.txt" in files:
            return open(os.path.join(root, "bot.txt")).read()
    return ""


def face_pic(look="idle", t=0.0, lashes=False, shape=None, size=200, mod=F):
    im = Image.new("RGB", (600, 600), (0, 0, 0))
    mod.draw_face(ImageDraw.Draw(im), 300, 300, size, look, t, (236, 239, 243), (0, 0, 0), lashes=lashes,
                  **({"shape": shape} if shape is not None else {}))
    return im


def lit(im):
    return int((np.asarray(im.convert("L")) > 128).sum())


# ---- its face, as it always looked ---------------------------------------------------------------------------------
old_src = open(SP + "/face_before_character.py").read()   # (pitato/face.py as it was before its Character)
old = types.ModuleType("old_face")
exec(compile(old_src.replace("from .theme import BG", "from pitato.theme import BG"), "old_face", "exec"), old.__dict__)
same, n = [], 0
for look in F.LOOKS:
    for lashes in (False, True):
        for t in (0.0, 1.3, 2.71, 5.5, 9.02):
            n += 1
            a, b = face_pic(look, t, lashes, mod=old), face_pic(look, t, lashes)
            c = face_pic(look, t, lashes, shape=F.face_shape(dict(F.SHAPE_DEFAULTS)))
            if ImageChops.difference(a, b).getbbox() is None and ImageChops.difference(a, c).getbbox() is None:
                same.append(look)
check(f"its face as it's always looked: every look, with lashes or not, the same to the pixel ({len(same)} of {n})",
      len(same) == n and "draw_face" in old_src and "shape" not in old_src.split("def draw_face")[1][:80])

# ---- each step, doing what it says ---------------------------------------------------------------------------------
def bbox(im):
    return im.getbbox()


def eyes_box(im):
    """Its eyes' box: what's lit above its middle (its mouth is below it)."""
    a = np.asarray(im.convert("L"))[:300] > 128
    ys, xs = np.nonzero(a)
    return xs.min(), ys.min(), xs.max(), ys.max()


base = face_pic()
big = face_pic(shape=F.face_shape({"eye_size": 10}))
small = face_pic(shape=F.face_shape({"eye_size": 0}))
check(f"Eye size: bigger eyes at 10, smaller at 0 ({lit(small)} < {lit(base)} < {lit(big)})",
      lit(small) < lit(base) * 0.7 < lit(base) < lit(big) * 0.75)
tall, short = face_pic(shape=F.face_shape({"eye_height": 10})), face_pic(shape=F.face_shape({"eye_height": 0}))
hb, ht, hs = [eyes_box(x)[3] - eyes_box(x)[1] for x in (base, tall, short)]
wb, wt = [eyes_box(x)[2] - eyes_box(x)[0] for x in (base, tall)]
check(f"Eye height: taller at 10, shorter at 0, as wide ({hs} < {hb} < {ht}; {wb}, {wt})", hs < hb < ht and abs(wb - wt) <= 2)
square = face_pic(shape=F.face_shape({"eye_corners": 0}))
x0, y0, x1, y1 = eyes_box(base)
corner = lambda im: im.convert("L").getpixel((x0 + 1, y0 + 1))   # noqa: E731  (an eye's top left corner)
check(f"Eye corners: square at 0 (its corner lit {corner(square)}), round as before at 10 ({corner(base)})",
      corner(square) > 128 and corner(base) < 60)
wide, near = face_pic(shape=F.face_shape({"eye_gap": 10})), face_pic(shape=F.face_shape({"eye_gap": 0}))
check(f"Spacing: further apart at 10, nearer at 0 ({eyes_box(near)[2] - eyes_box(near)[0]} < {wb} < "
      f"{eyes_box(wide)[2] - eyes_box(wide)[0]})", eyes_box(near)[2] - eyes_box(near)[0] < wb
      < eyes_box(wide)[2] - eyes_box(wide)[0])
apart = lambda im: eyes_box(im)[2] - eyes_box(im)[0] - 0.25 * 200   # noqa: E731  (between their middles)
check(f"...as it's always been at 3 (its start), and far apart at 10: its eyes' middles {apart(wide):.0f} px apart "
      f"of a 200 px face (at 3: {apart(base):.0f})", F.SHAPE_DEFAULTS["eye_gap"] == 3 and abs(apart(base) - 92) <= 2
      and apart(wide) >= 140)
tight = face_pic("alert", 0.0, shape=F.face_shape({"eye_size": 10, "eye_gap": 0}))
row = np.asarray(tight.convert("L"))[300 - 40] > 128
runs = int(np.sum(row[1:] & ~row[:-1]))
check(f"...big eyes close together, surprised (bigger still): still two eyes, never touching ({runs} apart)", runs == 2)


def mouth_w(im):
    a = np.asarray(im.convert("L"))[330:] > 128
    xs = np.nonzero(a)[1]
    return xs.max() - xs.min() if len(xs) else 0


bm, sm = face_pic(shape=F.face_shape({"mouth_size": 10})), face_pic(shape=F.face_shape({"mouth_size": 0}))
check(f"Mouth size: wider at 10, narrower at 0 ({mouth_w(sm)} < {mouth_w(base)} < {mouth_w(bm)})",
      mouth_w(sm) < mouth_w(base) < mouth_w(bm))
towers = F.face_shape({"eye_size": 10, "eye_height": 10})
tw = face_pic("talking", 0.11, shape=towers)
a = np.asarray(tw.convert("L")) > 128
rows = np.nonzero(a.any(axis=1))[0]
gaps = [y for y in range(rows.min(), rows.max()) if not a[y].any()]
check(f"...its mouth kept under big, tall eyes, apart from them (a gap from {gaps[:1]} on)", len(gaps) >= 4)
outside = []
extremes = [{}, {k: 0 for k in F.SHAPE_DEFAULTS}, {k: 10 for k in F.SHAPE_DEFAULTS},
            {"eye_size": 10, "eye_height": 10, "eye_gap": 0, "mouth_size": 10},
            {"eye_size": 10, "eye_gap": 10, "eye_corners": 0}, {"eye_height": 0, "eye_size": 0, "mouth_size": 10},
            {"eye_size": 10, "eye_height": 10, "eye_gap": 10}, {"eye_gap": 10}]
for steps in extremes:
    for look in F.LOOKS:
        for lashes in (False, True):
            for k in range(0, 40):
                t = k * 0.41
                im = Image.new("RGB", (600, 600), (0, 0, 0))
                F.draw_face(ImageDraw.Draw(im), 300, 300, 200, look, t, (255, 226, 102), (0, 0, 0), lashes=lashes,
                            font=None, shape=F.face_shape(steps))
                bb = im.getbbox()
                box = B.BotScreen.face_box((300, 300, 200))
                if bb and not (bb[0] >= box[0] and bb[1] >= box[1] and bb[2] <= box[2] and bb[3] <= box[3]):
                    outside.append((steps, look, lashes, round(t, 2), bb, box))
check(f"every shape, at its extremes, every look, lashes or not: inside its frames' box ({outside[:1]})", not outside)
check("bot.txt's steps read as typed: 12 is 10, -3 is 0, '7 # mine' is 7, 'big' its default",
      F.face_shape({"eye_size": 12})["size"] == F.face_shape({"eye_size": 10})["size"]
      and F.face_shape({"eye_size": -3})["size"] == F.face_shape({"eye_size": 0})["size"]
      and F.shape_step("7 # mine", 5) == 7 and F.shape_step("big", 5) == 5 and F.shape_step(None, 10) == 10)

# ---- the page -------------------------------------------------------------------------------------------------------
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
real_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), real_toast(text, secs))
m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Bot")
m.press("a")
m.press("start")
keys = [r[0] for r in m.settings_rows()]
check(f"START on the Bot (not set up): its settings, on what sets it up ({keys[m.set_sel]})",
      m.bot_settings and m.set_page == "friend" and keys[m.set_sel] == "f_server")
check(f"...Character, first of them ({keys[:2]}), its value: its name ({m.friend_value('f_char')})",
      keys[0] == "f_char" and m.friend_value("f_char") == "Potato")
check(f"...who it is there no more (all in its Character): just its computer, model, listening, face ({keys})",
      not any(k in keys for k in ("f_voice", "f_style", "f_colour", "f_back", "f_lashes", "f_name", "f_chatter",
                                  "f_speak")))
m.set_sel = 0
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/settings.png")
m.press("a")
check(f"A: its Character ({m.set_page}, {m.on_char_page()})", m.set_page == "f_char" and m.on_char_page()
      and m.bot_settings and not m.on_face_page())
m.dirty = True; m.flush()
page = m.fb.last
page.save(S + "/pics/character.png")
check("...its face, white on the menus' dark, in its panel on the left", int((np.abs(np.asarray(page.crop((16, 102, 284, 420)))
                                                                                .astype(int) - (236, 239, 243)).max(axis=2) < 10).sum()) > 2000)
check(f"...on Eyes the first time: Size, Height, Corners, Spacing, Eyelashes ({m.char_keys()})",
      m.char_keys() == ("eye_size", "eye_height", "eye_corners", "eye_gap", "lashes") and m.char_key() == "eye_size"
      and [p for p, _ in C.CHAR_PARTS] == ["Name", "Eyes", "Mouth", "Colours", "Voice"])
check("...its name over its face", int((np.asarray(page.crop((100, 106, 200, 136)).convert("L")) > 200).sum()) > 40)

# its sliders
m.press("right")
check(f"▶ on Size: a step up, kept ({m.bot_steps()['eye_size']}, {'eye_size = 6' in bot_txt()})",
      m.bot_steps()["eye_size"] == 6 and "eye_size = 6" in bot_txt())
for _ in range(8):
    m.press("right", True)
check(f"...held: on and on, but never past 10 ({m.bot_steps()['eye_size']})", m.bot_steps()["eye_size"] == 10)
m.dirty = True; m.flush(); bigger = m.fb.last
check("...its face bigger for it", lit(bigger.crop((16, 102, 284, 420))) > lit(page.crop((16, 102, 284, 420))))
for _ in range(14):
    m.press("left")
check(f"◀: down, never under 0 ({m.bot_steps()['eye_size']})", m.bot_steps()["eye_size"] == 0)
m.friend_set(eye_size=5)
m.press("down"); m.press("right"); m.press("right")
m.press("down"); m.press("left"); m.press("left"); m.press("left")
m.press("down"); m.press("right")
m.press("down"); m.press("right")
st = m.bot_steps()
check(f"Height ▶▶, Corners ◀◀◀, Spacing ▶, Eyelashes ▶ ({st}, {m.bot_lashes()})",
      st == {"eye_size": 5, "eye_height": 7, "eye_corners": 7, "eye_gap": 4, "mouth_size": 5} and m.bot_lashes())
m.press("right", True)
check("...Eyelashes held: not flipping on and off", m.bot_lashes())
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/eyes.png")
m.press("down")
check(f"▼ from the last of Eyes: Mouth's Size ({m.char_keys()})",
      m.char_keys() == ("mouth_size",) and m.char_sec == 2)
m.press("right"); m.press("right")
check(f"...▶▶: a bigger mouth ({m.bot_steps()['mouth_size']})", m.bot_steps()["mouth_size"] == 7)
m.press("up")
check(f"▲ from Mouth: back to Eyelashes, the last of Eyes ({m.char_sec}, {m.char_key()})",
      m.char_sec == 1 and m.char_key() == "lashes")
m.press("r"); m.press("r")
check(f"R R: Colours, its first row ({m.char_keys()}, {m.char_key()})", m.char_keys() == ("colour", "background")
      and m.char_key() == "colour")
m.press("right")
check(f"▶ on Face: the next colour ({m.bot_colour()})", m.bot_colour() == "Sky" and "colour = Sky" in bot_txt())
m.press("right", True)
check(f"...held: not spinning on ({m.bot_colour()})", m.bot_colour() == "Sky")
m.press("down"); m.press("left")
check(f"◀ on Background: round to the last ({m.bot_back()})", m.bot_back() == "White")
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/colours.png")
check("...its panel, its background", m.fb.last.getpixel((30, 140)) == F.face_colours("Sky", "White")[1])
m.press("r")
check(f"R: Voice ({m.char_keys()})", m.char_keys() == ("voice", "speak", "pause_music", "style", "chatter"))
toasts.clear()
m.press("right")
check(f"◀▶ on Voice, none on the Pi: A gets one ({toasts[-1:]})", toasts and toasts[-1] == "A gets it a voice")
picked = []
m.char_voices_here = lambda: ["en_US-amy-low", "en_GB-alan-low"]
m.voice_pick = lambda vid: (picked.append(vid), (True, f"Using {vid}" if vid else "No voice"))[1]
m.voice.supported = lambda: True
m.press("right")
check(f"...two on the Pi: ▶ uses the first, heard ({picked})", picked == ["en_US-amy-low"])
m.friend_set(voice="en_US-amy-low")
m.press("left")
check(f"...◀ from it: none ({picked})", picked[-1] == "")
m.press("a")
check(f"A on Voice: all the voices, to get one ({m.set_page})", m.set_page == "f_voices")
m.press("b")
check(f"...B: back to its Character, on Voice ({m.set_page}, {m.char_key()})", m.set_page == "f_char"
      and m.char_key() == "voice")
m.press("down")
m.friend_set(voice="")
toasts.clear()
m.press("right")
check(f"Talks out loud, with no voice: asks for one ({toasts[-1:]})", toasts and "Pick a voice" in toasts[-1]
      and m.char_value("speak") == "On")
m.friend_set(voice="en_US-amy-low")
m.voice.stop = lambda unload=False: None
m.press("right")
check(f"...with one: off, kept ({m.char_value('speak')})", m.char_value("speak") == "Off" and "speak = off" in bot_txt())
m.press("left")
check("...and on again", m.char_value("speak") == "On")
m.press("down")
check(f"Pauses music: off, as it comes ({m.char_key()}, {m.char_value('pause_music')})",
      m.char_key() == "pause_music" and m.char_value("pause_music") == "Off")
toasts.clear()
m.press("right")
check(f"...▶: on, kept, and what that means ({toasts[-1:]})", m.char_value("pause_music") == "On"
      and "pause_music = on" in bot_txt() and toasts and "pauses your music" in toasts[-1])
m.press("left")
check("...◀: off again", m.char_value("pause_music") == "Off" and "pause_music = off" in bot_txt())
m.press("down")
toasts.clear()
m.press("right")
check(f"How it talks ▶: Big brother, and a taste of it ({m.char_value('style')}, {toasts[-1:]})",
      m.char_value("style") == "Big brother" and toasts and "Timer set" in toasts[-1])
m.press("down")
m.press("right")
check(f"Chats ▶: every hour ({m.char_value('chatter')}, {m.friend.chatter()})", m.friend.chatter() == 60
      and m.char_value("chatter") == "Every hour")
m.press("left")
m.press("up")
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/voice.png")

# SELECT: how it looks; talking while it talks
looks = []
for _ in range(len(C.CHAR_LOOKS)):
    looks.append(m.char_look)
    m.press("select")
check(f"SELECT: how it looks, one after another and round again ({looks})", looks == [k for k, _ in C.CHAR_LOOKS]
      and m.char_look == "idle")
m.press("select"); m.press("select"); m.press("select")
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/sorry.png")
check(f"...its name under its face ({m.char_look})", m.char_look == "sad")
m.voice.speaking, m.voice.sounding = True, time.monotonic() + 30
check("...talking while it talks (heard)", m.char_preview_look() == "talking")
m.voice.speaking, m.voice.sounding = False, 0.0

# its frames: only in its panel
m.fb.parts.clear()
for _ in range(30):
    m.face_next = 0
    m.face_tick(time.monotonic())
    m.flush()
check(f"its face's frames there ({len(m.fb.parts)}), only in its panel ({set(m.fb.parts)})", m.fb.parts
      and all(b[0] >= 18 and b[1] >= 104 and b[2] <= 284 and b[3] <= 421 for b in m.fb.parts))

# X: one made up
before_voice = bot_txt().count("voice")
made = []
for _ in range(25):
    m.press("x")
    st, fc, bc = m.bot_steps(), *m.bot_palette()
    made.append((tuple(st.values()), m.bot_colour(), m.bot_back()))
    if abs(C.lightness(fc) - C.lightness(bc)) < C.CHAR_CONTRAST or any(
            not C.CHAR_RANDOM[k][0] <= v <= C.CHAR_RANDOM[k][1] for k, v in st.items()):
        made.append("bad")
check(f"X, 25 times: a new look each time, each clear on its background, none too odd ({len(set(made))})",
      "bad" not in made and len(set(made)) >= 20)
check("...its voice and how it talks: as they were", m.char_value("style") == "Big brother"
      and bot_txt().count("voice") == before_voice)
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/random.png")

# Y twice: as it started
m.press("y")
check(f"Y: asks first ({toasts[-1:]})", toasts and "Y again" in toasts[-1] and m.bot_steps() != C.CHAR_RESET)
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/reset-ask.png")
m.press("down")
m.press("y")
check("...another button between: it asks again", toasts and "Y again" in toasts[-1])
m.press("y")
check(f"Y again: its look as it started ({m.bot_steps()}, {m.bot_colour()} on {m.bot_back()}, {m.bot_lashes()})",
      m.bot_steps() == F.SHAPE_DEFAULTS and m.bot_colour() == "White" and m.bot_back() == "Dark"
      and not m.bot_lashes() and m.char_value("style") == "Big brother")

# B: back where it came from
m.press("b")
check(f"B: its settings again, on Character ({m.set_page}, {m.settings_rows()[m.set_sel][0]})",
      m.set_page == "friend" and m.settings_rows()[m.set_sel][0] == "f_char" and m.bot_settings)
m.press("b")
check("...B: the Bot", not m.bot_settings and m.on_bot_page())
m.char_open(from_menu=True)
check("from the Bot's X menu: its Character, on the Bot", m.on_char_page() and m.bot_settings)
m.press("b")
check("...B: straight back to the Bot", not m.bot_settings and m.on_bot_page())
opts = m.friend_options()
check(f"...the X menu: Send a photo, Edit Character before Clear ({[o for o, _ in opts]})",
      ("Edit Character", "character") in opts and ("Send a photo", "send") in opts and opts[-1][1] == "clear")
m.tab = m.tab_index("settings"); m.load_tab(m.tab)
m.set_page = "friend"; m.set_sel = 0
m.press("a")
check("Settings > Bot > Character, in Settings too", m.on_char_page() and not m.bot_settings)
m.press("b")
check("...B: Settings > Bot", m.set_page == "friend" and m.tab_type() == "settings")
m.press("a")
m.go_home()
check("Home: closed", m.set_page == "root" and not m.on_char_page())

# its shape on the Bot itself, and just its face
m.friend_set(eye_size=9, eye_height=8, eye_corners=4, eye_gap=7, mouth_size=8, lashes="on", colour="Mint",
             background="Plum")
m.view = "list"; m.tab = m.tab_index("friend"); m.load_tab(m.tab)
m.bot_set_mode("chat")
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/bot-chat.png")
m.friend_set(face_only="on")
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/bot-face-only.png")
x, y, size = m.face_only_at()
check("...just its face, in its shape: square-ish mint eyes on plum",
      m.fb.last.getpixel((5, 5)) == F.face_colours("Mint", "Plum")[1]
      and lit(m.fb.last) > 0)
m.friend_set(face_only="off")

# taps on the web page's copy of it
m.tab = m.tab_index("friend"); m.load_tab(m.tab)
m.char_open(from_menu=True)
m.dirty = True; m.flush()
taps = [(b, w) for b, w in m.taps_new] if getattr(m, "taps_new", None) else []
btns, _ = m.web_touch({"cmd": "tap", "x": 595 / 640, "y": 116 / 480})
check(f"a tap on Voice, on the web page: that part ({m.char_sec}, {btns})", m.char_sec == 4 and btns == [])
m.dirty = True; m.flush()
btns, _ = m.web_touch({"cmd": "tap", "x": 400 / 640, "y": (102 + 42 + 48 + 24) / 480})
check(f"...a tap on its second row: picked ({m.char_key()})", m.char_key() == "speak")
m.press("b")

# ---- its name ------------------------------------------------------------------------------------------------------
m.tab = m.tab_index("friend"); m.load_tab(m.tab)
m.char_open(from_menu=True)
m.char_sec, m.char_row = 0, 0
check(f"Name: its first part, Potato to start with ({m.char_keys()}, {m.char_value('name')})",
      m.char_keys() == ("name", "you") and m.char_value("name") == "Potato")
m.press("right")
check("...◀▶ on it: nothing (A types it)", m.bot_name() == "Potato" and m.view == "list")
m.press("a")
check(f"A: the keyboard, its name in it ({m.view}, {m.kb and m.kb['text']!r})", m.view == "keys"
      and m.kb["text"] == "Potato")
for _ in range(8):
    m.keyboard_key("back")
for ch in "Sparky":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check(f"Sparky: its name, and what you call it ({m.bot_name()}, {m.bot_wake()!r})", m.bot_name() == "Sparky"
      and m.bot_wake() == "hey sparky" and "wake = hey sparky" in bot_txt() and m.on_char_page())
check(f"...its model's told ({m.friend.system()[-40:]!r})", m.friend.system().endswith("Your name is Sparky.")
      and m.bot_calls() == ("hey sparky", "sparky"))
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/name.png")
check("...over its face", int((np.asarray(m.fb.last.crop((90, 106, 210, 136)).convert("L")) > 200).sum()) > 40)
m.press("a")
for _ in range(8):
    m.keyboard_key("back")
m.keyboard_key("char", "Q")
m.keyboard_key("done")
check(f"...one letter: not a name (still Sparky; {m.msg!r})", m.bot_name() == "Sparky" and "two letters" in (m.msg or ""))
m.friend_set(wake="ok computer")
check("a wake phrase of your own (ok computer): its name Computer", m.bot_name() == "Computer")
m.press("a")
for _ in range(10):
    m.keyboard_key("back")
for ch in "Mister Potato":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check(f"...renamed Mister Potato: ok kept ({m.bot_wake()!r})", m.bot_wake() == "ok mister potato"
      and m.bot_name() == "Mister Potato")
m.press("down"); m.press("a")
for ch in "Sam":
    m.keyboard_key("char", ch)
m.keyboard_key("done")
check(f"What it calls you: Sam ({m.friend.name})", m.friend.name == "Sam" and "name = Sam" in bot_txt()
      and m.friend.system().endswith("Your name is Mister Potato. The person you live with is called Sam."))
m.friend_set(wake="hey potato", name="")
m.press("b")
m.friend_more = {"sel": 0}
m.dirty = True; m.flush(); m.fb.last.save(S + "/pics/menu.png")
m.friend_more = None
m.friend_set(persona="You are a grumpy cat.")
check("a persona of yours: as it is (no name added to it)", m.friend.system() == "You are a grumpy cat.")
m.friend_set(persona="")

# ---- the web page ---------------------------------------------------------------------------------------------------
secs = {s["id"]: s for s in m.web_settings_now()["sections"]}
rows = {r["key"]: r for r in secs["character"]["rows"]}
order = [r["key"] for r in secs["character"]["rows"]]
check(f"the web page: Bot's character, after Bot ({order})", list(secs).index("character") == list(secs).index("bot") + 1
      and order[:10] == ["f_botname", "f_name", "f_eye_size", "f_eye_height", "f_eye_corners", "f_eye_gap",
                         "f_lashes", "f_mouth_size", "f_colour", "f_back"] and order[-2:] == ["f_style", "f_chatter"])
check(f"...its name, and what you say to it ({rows['f_botname']['value']}, {rows['f_botname']['note']})",
      rows["f_botname"]["value"] == "Potato" and "hey potato" in rows["f_botname"]["note"])
check(f"...its steps as sliders, from 0 to 10, where they started marked ({rows['f_eye_size']})",
      rows["f_eye_size"]["kind"] == "range" and rows["f_eye_size"]["value"] == 9 and rows["f_eye_size"]["max"] == 10
      and rows["f_eye_corners"]["start"] == 10 and rows["f_mouth_size"]["value"] == 8)
check("...its colours as swatches", rows["f_colour"]["colours"]["Mint"] == "#%02x%02x%02x" % dict(F.FACE_COLOURS)["Mint"]
      and rows["f_back"]["value"] == "Plum" and set(rows["f_back"]["colours"]) == {n for n, _ in F.FACE_BACKS})
check("...and not in the Bot's section now", not any(r["key"] in rows for r in secs["bot"]["rows"]))
check("f_eye_gap 2, from the web page: kept", m.web_settings_do({"key": "f_eye_gap", "value": 2}) == {"ok": True}
      and m.bot_steps()["eye_gap"] == 2 and "eye_gap = 2" in bot_txt())
check("...'3' too", m.web_settings_do({"key": "f_mouth_size", "value": "3"}) == {"ok": True}
      and m.bot_steps()["mouth_size"] == 3)
bad = [v for v in (11, -1, "x", None, True, 2.5e9) if "error" not in m.web_settings_do({"key": "f_eye_size", "value": v})]
check(f"...11, -1, words, nothing, true: refused ({bad})", not bad and m.bot_steps()["eye_size"] == 9)
check("its name from the web page: Sparky, and what you say to it", m.web_settings_do({"key": "f_botname", "value":
                                                                                      " Sparky "}).get("ok")
      and m.bot_name() == "Sparky" and "wake = hey sparky" in bot_txt())
check("...one letter: refused", "error" in m.web_settings_do({"key": "f_botname", "value": "x"}) and m.bot_name() == "Sparky")
m.friend_set(wake="hey potato")
html = open(ROOT + "/templates/index.html").read()
check("the page draws a slider row", "range(r) {" in html and 'inp.type = "range"' in html and ".range input" in html)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
