"""Settings > Bot > Just its face: the Bot's chat page as only its face, big, in the middle of the screen, nothing
else on it (no words, no tabs, no buttons along the bottom); its frames as it changes, just its face again; A talks
to it when it can hear (else the keyboard, as ever); a tap on its face on the web page does what A does; its X menu
over it, with that menu's buttons, and back to the face after; Today as it was; the web page's setting. And the
thinking dots: well above its eyes now, on the page and in the face's own box. Pictures saved, to look at."""
import json, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_faceonly"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageChops
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


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
BG = g.BG if hasattr(g, "BG") else B.BG


def outside_blank(img, box):
    """Everything outside box is the screen's plain background."""
    blank = Image.new("RGB", img.size, B.BG)
    diff = ImageChops.difference(img.convert("RGB"), blank)
    mask = Image.new("L", img.size, 255)
    mask.paste(0, tuple(int(v) for v in box))
    return ImageChops.multiply(diff.convert("L"), mask).getbbox() is None


def drawn(img):
    """Where anything's drawn on the screen's background."""
    return ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, B.BG)).getbbox()


# ---- Settings > Bot: the row, off at first ------------------------------------------------------------------------
m.tab = m.tab_index("settings"); m.load_tab(m.tab)
m.set_page = "friend"
rows = m.settings_rows()
keys = [r[0] for r in rows]
check(f"Settings > Bot: Just its face, last (its colours and eyelashes: its Character, first), Off at first "
      f"({keys}, {m.friend_value('f_face')})", keys[-1] == "f_face" and keys[0] == "f_char"
      and rows[-1][1] == "Just its face" and m.friend_value("f_face") == "Off")
m.set_sel = keys.index("f_face")
m.press("right")
conf = open(os.path.join(m.static_dir() if hasattr(m, "static_dir") else HOME, "bot.txt")).read() \
    if os.path.exists(os.path.join(HOME, "bot.txt")) else ""
from pitato.config import read_config
check(f"...▶: On, kept in bot.txt ({m.friend.conf.get('face_only')}), said so ({m.msg!r})",
      m.bot_face_only() and m.friend.conf.get("face_only") == "on" and m.friend_value("f_face") == "On"
      and "just its face" in (m.msg or ""))
m.dirty = True; m.flush()
m.fb.last.save(S + "/pics/settings.png")
m.press("left")
check("...◀: Off again", not m.bot_face_only())
m.press("a")
check("...A: On again", m.bot_face_only())

# ---- the Bot, chatting: just its face ------------------------------------------------------------------------------
m.set_setting("bot_mode", "chat")
m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
m.msg = None
m.dirty = True; m.flush()
img = m.fb.last
img.save(S + "/pics/face-only.png")
x, y, size = m.face_only_at()
box = B.BotScreen.face_box((x, y, size))
bb = drawn(img)
check(f"just its face: big ({size:.0f} across), nothing outside it (drawn: {bb}, its box {box})",
      size >= 280 and outside_blank(img, box) and bb is not None)
real_look = m.face_look
m.face_look = lambda: "alert"                      # (a look that's the same both sides: its eyes straight ahead)
m.dirty = True; m.flush()
bb2 = drawn(m.fb.last)
m.face_look = real_look
mid = (bb2[0] + bb2[2]) / 2
check(f"...in the middle of the screen (its alert look spans {bb2}: its middle at {mid:.0f} of 640; its box's at "
      f"{(box[0] + box[2]) / 2:.0f})", abs(mid - 320) <= 2 and abs((box[0] + box[2]) / 2 - 320) <= 1
      and bb2[1] > 16 and bb2[3] < 464)
check(f"...its box on the screen ({box})", box[0] >= 0 and box[1] >= 0 and box[2] <= 640 and box[3] <= 480)
fr_taps = [t for t in m.taps if t[1] == ("keys", "a")]
check(f"...a tap on it, on the web page's copy: A ({fr_taps[:1]})", fr_taps and fr_taps[0][0] == tuple(box))

# its next frames: just its face
m.face_step = True
m.flush()
check(f"its next frame: just its face ({m.fb.parts[-1:]} of {box})", m.fb.parts and m.fb.parts[-1] == tuple(box))
m.fb.last.save(S + "/pics/face-only-2.png")
check("...the rest as it was: still nothing else", outside_blank(m.fb.last, box))

# thinking: its dots well above its eyes
m.friend.busy = True
m.dirty = True; m.flush()
think = m.fb.last
think.save(S + "/pics/face-only-thinking.png")
m.friend.busy = False
check("thinking: still nothing but its face", outside_blank(think, box))

# the dots, on their own: where they are against its eyes, at any size
for sz in (112, 300):
    im = Image.new("RGB", (int(sz * 2), int(sz * 1.8)), (0, 0, 0))
    from PIL import ImageDraw
    cx, cy = im.width / 2, im.height * 0.6
    F.draw_face(ImageDraw.Draw(im), cx, cy, sz, "thinking", 0.1, (255, 255, 255), (0, 0, 0))
    a = im.convert("L")
    # the eyes: their tops (thinking, they look up and to the right); the dots: above them
    eye_top = cy - sz * 0.08 - sz * 0.06 * 0.75 - sz * 0.36 / 2
    dots_y = cy - sz * F.THINK_DOTS
    gap = eye_top - (dots_y + sz * 0.032)
    bx = B.BotScreen.face_box((cx, cy, sz))
    check(f"its dots at {sz}: a gap of {gap / sz:.2f} of its size above its eyes (was under 0.03), inside the "
          f"box it's drawn again in", gap >= sz * 0.12 and dots_y - sz * 0.032 >= bx[1])

# A: talks to it, when it can hear
woke = []
m.ears.want = "auto"                               # (it listens for you...)
m.ears.state = "waiting"
real_wake = m.ears.wake_now
m.ears.wake_now = lambda: woke.append(1) or True
m.friend.conf["server"], m.friend.conf["model"] = "127.0.0.1:1", "x"
check("(set up, as far as it knows)", m.friend.ready())
m.press("a")
check(f"A, with it listening for you: it hears you now, no keyboard ({woke}, {m.view})", woke and m.view == "list")
m.ears.want = None
m.press("a")
check(f"...without a microphone: the keyboard, as ever ({m.view})", m.view == "keys")
m.close_keyboard(False)
m.view = "list"
m.ears.wake_now = real_wake

# a tap on its face, on the web page: what A does
m.ears.want, m.ears.state = "auto", "waiting"
m.ears.wake_now = lambda: woke.append(2) or True
m.dirty = True; m.flush()
btns, out = m.web_touch({"cmd": "tap", "x": x / 640, "y": y / 480})
check(f"a tap on its face on the web page: A ({btns}, {out})", btns == ["a"] or 2 in woke)
m.ears.want = None
m.ears.wake_now = real_wake

# X: its menu over it, with that menu's buttons; B: just its face again
m.press("x")
m.flush()
menu = m.fb.last
menu.save(S + "/pics/face-only-menu.png")
above = drawn(menu.crop((0, 0, 640, 480 - m.FOOTER)))
below = drawn(menu.crop((0, 480 - m.FOOTER, 640, 480)))
check(f"X: its menu there instead, in the middle ({above}), its buttons along the bottom ({below})",
      m.friend_more is not None and m.face_shot is None and above is not None and below is not None
      and abs(above[0] - (640 - above[2])) <= 1 and above[2] - above[0] <= g.FRIEND_MENU[0] + 6
      if hasattr(g, "FRIEND_MENU") else abs(above[0] - (640 - above[2])) <= 1 and above[2] - above[0] <= 326)
was = m.fb.frames
m.face_next = 0
m.face_tick(time.monotonic())
m.flush()
check(f"...while it's open, no frames of its face (its menu stays as it is: {m.fb.frames - was} drawn)",
      m.fb.frames == was and not m.face_step)
m.press("b")
m.flush()
check("...B: just its face again", m.friend_more is None and outside_blank(m.fb.last, box))

# Today: as it was (its face in its card, your day beside it): SELECT for its chat page, then left
m.press("select")
m.press("left")
m.flush()
today = m.fb.last
today.save(S + "/pics/today.png")
check(f"Today: as it was, not just its face ({m.bot_mode()})", m.bot_mode() == "today" and not outside_blank(today, box))
m.press("right")
m.press("select")
m.flush()
check("...and back: just its face", m.bot_mode() == "chat" and outside_blank(m.fb.last, box))

# a bigger screen: still in the middle, still as big as fits
m.fb.w, m.fb.h = 960, 540
m.dirty = True; m.flush()
big = m.fb.last
big.save(S + "/pics/face-only-960.png")
x2, y2, size2 = m.face_only_at()
box2 = B.BotScreen.face_box((x2, y2, size2))
check(f"a 960x540 screen: bigger ({size2:.0f}), in the middle, nothing else ({drawn(big)})",
      size2 > size and outside_blank(big, box2) and box2[1] >= 0 and box2[3] <= 540)
m.fb.w, m.fb.h = 640, 480

# the web page's setting
sec = next(s for s in m.web_settings_now()["sections"] if s["id"] == "bot")
row = next((r for r in sec["rows"] if r["key"] == "f_face"), None)
check(f"the web page's Settings > Bot: Just its face, Yes now, said what it does ({row and row['value']})",
      row is not None and row["value"] == "on" and row["names"] == {"on": "Yes", "off": "No"} and row.get("note"))
said = m.web_settings_do({"key": "f_face", "value": "off"})
check(f"...No: its face and the conversation again ({said})", said == {"ok": True} and not m.bot_face_only())
m.dirty = True; m.flush()
m.fb.last.save(S + "/pics/chat-again.png")
check("...the page as it was", not outside_blank(m.fb.last, box) and m.face_shot
      and m.face_shot[4] == m.bot_palette()[1])
check(f"...nothing else taken: {m.web_settings_do({'key': 'f_face', 'value': 'maybe'})}",
      "error" in m.web_settings_do({"key": "f_face", "value": "maybe"}))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
