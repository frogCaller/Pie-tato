"""The Bot's colours and eyelashes, and its buttons: as it was to start with (white, on the menus' own dark, no
eyelashes); SELECT switching between its chat page and just its face; on just its face, up and down going through its
face's colours and left and right its backgrounds, each on its own (kept in bot.txt), set up or not, a held press not
spinning them; on its chat page up and down still scroll and left and right go to its pages; its face there in a
rounded panel of its colours under its pages' names (which it doesn't cover), a little smaller; eyelashes; Settings >
Bot > Character's rows (a swatch beside each colour); the web page's; START: its settings on the Bot (not in X's menu
now), B back to it, tabs and Home closing them, no face drawn over them. Pictures saved, to look at."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_botcolours"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
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

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
os.makedirs(S + "/pics", exist_ok=True)
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

    def close(self):
        pass


def bot_txt():
    path = os.path.join(HOME, "bot.txt")
    for root, _, files in os.walk(S):
        if "bot.txt" in files:
            path = os.path.join(root, "bot.txt")
    return open(path).read() if os.path.exists(path) else ""


def count(img, colour, tol=12, box=None):
    """Pixels of a colour (within tol) in img (or box of it)."""
    a = np.asarray((img.crop(box) if box else img).convert("RGB")).astype(int)
    return int((np.abs(a - np.array(colour)).max(axis=2) <= tol).sum())


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
COL = dict(F.FACE_COLOURS)

# ---- as it was to start with --------------------------------------------------------------------------------------
BACKS = dict(F.FACE_BACKS)
check(f"to start with: white, on the menus' own dark, no eyelashes ({m.bot_colour()}, {m.bot_back()}, "
      f"{m.bot_lashes()})", (m.bot_colour(), m.bot_back(), m.bot_lashes()) == ("White", "Dark", False)
      and m.bot_palette() == (COL["White"], g.BG))

m.set_setting("bot_mode", "chat")
m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
m.press("select")
check(f"SELECT on its chat page: just its face ({m.bot_face_only()}, kept: {'face_only = on' in bot_txt()})",
      m.bot_face_only() and "face_only = on" in bot_txt())
real_look = m.face_look
m.face_look = lambda: "alert"                      # (eyes straight ahead, the same each time)
m.msg = None
m.dirty = True; m.flush()
first = m.fb.last
check(f"just its face, as before: on the menus' dark ({first.getpixel((5, 5))}), in white "
      f"({count(first, COL['White'])} px)", first.getpixel((5, 5)) == g.BG and count(first, COL["White"]) > 2000)

# ---- up and down: its colours -------------------------------------------------------------------------------------
m.press("down")
m.dirty = True; m.flush()
sky = m.fb.last
sky.save(S + "/pics/sky.png")
check(f"down: Sky, kept in bot.txt ({m.bot_colour()}, {'colour = Sky' in bot_txt()})",
      m.bot_colour() == "Sky" and "colour = Sky" in bot_txt())
page = sky.getpixel((5, 5))
check(f"...its face sky blue ({count(sky, COL['Sky'])} px), its background as it was: its own ({page})",
      count(sky, COL["Sky"]) > 2000 and count(sky, COL["White"]) < 50 and page == g.BG and m.bot_back() == "Dark")
m.press("down", repeat=True)
check("...a held press: not spinning through them", m.bot_colour() == "Sky")
m.press("up")
check("up: White again", m.bot_colour() == "White")
m.press("up")
check(f"up from the first: the last ({m.bot_colour()})", m.bot_colour() == F.FACE_COLOURS[-1][0])
seen = set()
for _ in range(len(F.FACE_COLOURS)):
    m.press("down")
    seen.add(m.bot_colour())
check(f"down through them all: {len(seen)} colours", len(seen) == len(F.FACE_COLOURS))
m.friend_set(colour="Pink")
check(f"not set up (no computer for it): still its colours ({m.friend.ready()})", not m.friend.ready()
      and m.bot_colour() == "Pink")
mode = m.bot_mode()
m.press("right")
m.dirty = True; m.flush()
navy = m.fb.last
check(f"right: its next background, Black, kept, its face still pink, its page as it was "
      f"({m.bot_back()}, {navy.getpixel((5, 5))}, {m.bot_mode()})",
      m.bot_back() == "Black" and "background = Black" in bot_txt() and navy.getpixel((5, 5)) == (0, 0, 0)
      and m.bot_colour() == "Pink" and count(navy, COL["Pink"]) > 2000 and m.bot_mode() == mode == "chat")
m.press("right"); m.press("right", repeat=True)
check(f"...right again: Navy (a held press: no further) ({m.bot_back()})", m.bot_back() == "Navy")
m.press("left"); m.press("left")
check(f"left twice: back to the first, Dark ({m.bot_back()})", m.bot_back() == "Dark")
m.press("left")
check(f"...and left from the first: the last ({m.bot_back()})", m.bot_back() == F.FACE_BACKS[-1][0])
m.press("down")
check("...its face's colour on its own: the background stays", m.bot_back() == F.FACE_BACKS[-1][0]
      and m.bot_colour() == "Lilac")
m.friend_set(colour="Pink", background="Navy")
m.dirty = True; m.flush()
m.fb.last.save(S + "/pics/face-only-pink-navy.png")
check(f"Pink on Navy: both as picked ({m.fb.last.getpixel((5, 5))})", m.fb.last.getpixel((5, 5)) == BACKS["Navy"])
m.press("select")
check(f"SELECT: its chat page again ({m.bot_face_only()})", not m.bot_face_only() and "face_only = off" in bot_txt())
m.press("select")
check("...SELECT again: just its face", m.bot_face_only())

# its chat page (not just its face): up and down still scroll
m.friend_set(face_only="off")
m.friend.log.extend({"who": "friend", "text": f"Line {i} " * 9, "t": time.time(), "kind": "remark"} for i in range(12))
m.friend_set(server="127.0.0.1:1", model="x")      # (set up, as far as it knows: kept in bot.txt)
m.dirty = True; m.flush()
m.press("up")
check(f"its chat page: up scrolls the conversation, its colour as it was ({m.friend_scroll}, {m.bot_colour()})",
      m.friend_scroll > 0 and m.bot_colour() == "Pink")
m.friend_scroll = 0
m.press("right")
check(f"...right: its next page, Work, as ever; its background as it was ({m.bot_mode()}, {m.bot_back()})",
      m.bot_mode() == "work" and m.bot_back() == "Navy")
m.press("left")
m.dirty = True; m.flush()
chat = m.fb.last
chat.save(S + "/pics/chat-pink.png")
face, back = m.bot_palette()
a = np.asarray(chat.convert("RGB")).astype(int)
navy_px = np.argwhere((np.abs(a - np.array(back)).max(axis=2) <= 2))
ny0, nx0 = navy_px.min(axis=0)
ny1, nx1 = navy_px.max(axis=0)
check(f"...its face in a panel of its background on its card ({nx0},{ny0} to {nx1},{ny1}): under its pages' names, "
      f"the card round it as ever ({chat.getpixel((22, 100))})", 20 < nx0 < 40 and 170 < nx1 < 192 and ny0 > 120
      and ny1 < 400 and chat.getpixel((22, 100)) == g.ROW and chat.getpixel((24, 380)) == g.ROW)
check(f"...the panel's corners round ({chat.getpixel((nx0, ny0))} at its corner, {back} inside)",
      chat.getpixel((nx0 + 1, ny0 + 1)) != back and chat.getpixel((nx0 + 20, ny0 + 20)) == back)
check(f"...its face in it, pink, a little smaller than before ({B.FACE_SIZE})", B.FACE_SIZE < 112
      and count(chat, face, box=(nx0, ny0, nx1, ny1)) > 200)

# ---- Settings > Bot ------------------------------------------------------------------------------------------------
m.friend_set(background="Dark")
m.tab = m.tab_index("settings"); m.load_tab(m.tab)
m.set_page = "friend"
keys = [r[0] for r in m.settings_rows()]
m.set_sel = keys.index("f_char")
m.press("a")
m.char_sec, m.char_row = 3, 1                           # (Character > Colours > Background)
m.press("right")
check(f"Settings > Bot > Character > Background ▶: Black ({m.bot_back()}, kept: {'background = Black' in bot_txt()})",
      m.bot_back() == "Black" and "background = Black" in bot_txt() and m.bot_palette()[1] == (0, 0, 0))
m.dirty = True; m.flush()
m.fb.last.save(S + "/pics/settings-colours.png")
shot = m.fb.last
check("...a swatch of it beside its name: black", count(shot, (0, 0, 0), tol=2, box=(300, 140, 620, 432)) > 100)
m.char_row = 0
m.dirty = True; m.flush()
check(f"Face's row: pink beside its name ({count(m.fb.last, COL['Pink'], box=(400, 140, 620, 200))} px)",
      count(m.fb.last, COL["Pink"], box=(400, 140, 620, 200)) > 100)
m.char_sec, m.char_row = 1, 4                           # (Character > Eyes > Eyelashes)
m.press("right")
check(f"Eyelashes ▶: On ({'lashes = on' in bot_txt()})", m.bot_lashes() and "lashes = on" in bot_txt())
m.press("b")

# just its face, black, with eyelashes
m.friend_set(face_only="on")
real_draw_face = B.draw_face      # (both drawn at the same moment of its blinking and glancing about: only the
B.draw_face = lambda d, x, y, size, look, t, *a, **k: real_draw_face(d, x, y, size, look, 0.5, *a, **k)  # lashes differ)
m.tab = m.tab_index("friend"); m.load_tab(m.tab)
m.dirty = True; m.flush()
lashed = m.fb.last
lashed.save(S + "/pics/face-only-black-lashes.png")
check(f"just its face: on black ({lashed.getpixel((5, 5))})", lashed.getpixel((5, 5)) == (0, 0, 0))
m.friend_set(lashes="off")
m.dirty = True; m.flush()
plain = m.fb.last
x, y, size = m.face_only_at()
diff = ImageChops.difference(lashed.convert("RGB"), plain.convert("RGB")).getbbox()
eye_top = y - size * 0.08 - size * 0.36 * 1.14 / 2
check(f"...its eyelashes: more of it at its eyes' top outer corners ({diff}; its eyes' tops at {eye_top:.0f})",
      diff is not None and diff[1] < eye_top and diff[3] < y and diff[0] < x - size * 0.3 and diff[2] > x + size * 0.3)
B.draw_face = real_draw_face
m.friend_set(lashes="on")

# every look, both ways, at all sorts of moments (glancing about, blinking): inside the box it's drawn again in
outside = []
for look in F.LOOKS:
    for lashes in (False, True):
        for k in range(0, 120):
            t = k * 0.37
            im = Image.new("RGB", (600, 600), (0, 0, 0))
            F.draw_face(ImageDraw.Draw(im), 300, 300, 200, look, t, COL["Lemon"], (0, 0, 0),
                        font=m.fonts["small"], lashes=lashes)
            bb = im.getbbox()
            box = B.BotScreen.face_box((300, 300, 200))
            if bb and not (bb[0] >= box[0] and bb[1] >= box[1] and bb[2] <= box[2] and bb[3] <= box[3]):
                outside.append((look, lashes, round(t, 2), bb, box))
check(f"every look, with eyelashes or not, glancing and blinking: inside its box ({outside[:2]})", not outside)
m.face_look = real_look

# ---- its settings, on the Bot itself: START -----------------------------------------------------------------------
m.friend_set(face_only="off", background="Dark")
m.dirty = True; m.flush()
m.press("x")
opts = [label for label, _ in m.friend_options()]
check(f"X on the Bot: no Settings in its menu now (START has them) ({opts})", "Settings" not in opts
      and "Set up your bot" not in opts)
m.press("b")
m.press("start")
check(f"START: its settings, on the Bot (still the Bot's tab: {m.tab_type()}, {m.set_page})",
      m.tab_type() == "friend" and m.bot_settings and m.set_page == "friend" and m.friend_more is None)
m.dirty = True; m.flush()
there = m.fb.last
there.save(S + "/pics/bot-settings.png")
check(f"...its rows on the screen, not its face ({m.on_face_page()}, {m.on_bot_settings()})",
      not m.on_face_page() and m.on_bot_settings() and not m.on_friend_page())
parts = len(m.fb.parts)
m.face_next = 0
m.face_tick(time.monotonic())
m.flush()
check(f"...no face drawn over them ({len(m.fb.parts) - parts} of its frames)", len(m.fb.parts) == parts
      and not m.face_step)
m.set_sel = [r[0] for r in m.settings_rows()].index("f_char")
m.press("a")
m.press("r"); m.press("r")                              # (Character > Colours)
m.press("right")
check(f"...they work there too: Character > Colours, ▶ on Face ({m.bot_colour()})", m.bot_colour() != "Pink")
m.press("down")
check("...▲▼ choose rows there, not colours", m.char_key() == "background")
m.press("b")
check(f"B: its settings again ({m.bot_settings}, {m.set_page})", m.bot_settings and m.set_page == "friend")
m.press("b")
check(f"B: back to the Bot ({m.bot_settings}, {m.set_page})", not m.bot_settings and m.set_page == "root"
      and m.tab_type() == "friend" and m.on_friend_page())
m.friend_set(face_only="on")
m.press("start")
check("START on just its face: its settings too", m.bot_settings and m.set_page == "friend")
m.press("b")
m.friend_set(face_only="off")
m.press("start")
m.set_sel = [r[0] for r in m.settings_rows()].index("f_char")
m.press("a")
m.char_sec, m.char_row = 4, 0                           # (Character > Voice > Voice)
m.press("a")
check(f"...a page of them (Voice) ({m.set_page})", m.set_page in ("f_voices", "f_char"))
if m.set_page == "f_voices":
    m.press("b")
    check("...B: back to its Character", m.set_page == "f_char" and m.bot_settings)
m.press("b")
m.press("r")
check(f"R, another tab: its settings closed ({m.bot_settings}, {m.set_page})", not m.bot_settings
      and m.set_page == "root" and m.tab_type() != "friend")
m.tab = m.tab_index("friend"); m.load_tab(m.tab)
check("...back on the Bot: the Bot", m.on_friend_page())
m.press("start")
m.go_home()
check(f"Home: closed too ({m.bot_settings})", not m.bot_settings)
m.view = "list"; m.tab = m.tab_index("friend")
m.press("start")
m.bot_open("chat")
check("the web page's Show on the Pi: the Bot, not its settings", not m.bot_settings and m.on_friend_page())
m.tab = m.tab_index("settings"); m.load_tab(m.tab)
m.set_page, m.set_sel = "root", 0
keys = [r[0] for r in m.settings_rows()]
m.set_sel = keys.index("friend")
m.press("a")
check("Settings > Bot: still there, as before", m.tab_type() == "settings" and m.set_page == "friend"
      and not m.bot_settings)
m.press("b")
check("...B: Settings, on Bot", m.set_page == "root" and m.settings_rows()[m.set_sel][0] == "friend")

# ---- the web page's Settings ---------------------------------------------------------------------------------------
sec = next(s for s in m.web_settings_now()["sections"] if s["id"] == "character")
rows = {r["key"]: r for r in sec["rows"]}
check(f"the web page: Face colour, Background, Eyelashes ({[rows[k]['value'] for k in ('f_colour', 'f_back', 'f_lashes') if k in rows]})",
      all(k in rows for k in ("f_colour", "f_back", "f_lashes")) and rows["f_colour"]["value"] == m.bot_colour()
      and rows["f_colour"]["choices"] == [n for n, _ in F.FACE_COLOURS]
      and rows["f_back"]["choices"] == [n for n, _ in F.FACE_BACKS] and rows["f_lashes"]["value"] == "on")
check("...Mint", m.web_settings_do({"key": "f_colour", "value": "Mint"}) == {"ok": True} and m.bot_colour() == "Mint")
check("...Navy", m.web_settings_do({"key": "f_back", "value": "Navy"}) == {"ok": True} and m.bot_back() == "Navy")
check("...no eyelashes", m.web_settings_do({"key": "f_lashes", "value": "off"}) == {"ok": True} and not m.bot_lashes())
check("...nothing else taken", all("error" in m.web_settings_do({"key": k, "value": v}) for k, v in
                                  (("f_colour", "Tartan"), ("f_back", "Matching"), ("f_lashes", "maybe"))))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
