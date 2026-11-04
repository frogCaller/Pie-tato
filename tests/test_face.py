"""The bot's face (pitato/face.py): each look drawn, inside the box the Bot page draws it again in (its dots, its z's
and its look of alarm too), at the GPi's size and twice it; blinking every few seconds and glancing about, never the
same on the dot each time; and face_wait honest: the face doesn't change before it says it will (so drawing it only
then misses nothing), and it isn't drawn when nothing's changed."""
import os, random, sys
from PIL import Image, ImageDraw, ImageFont
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, os.environ.get("PITATO_REPO") or ROOT)
from pitato import face as F
from pitato.screens.bot import BotScreen, FACE_SIZE

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


BG, FG = (30, 34, 44), (235, 238, 245)
font = ImageFont.load_default()


def draw(look, t, size=FACE_SIZE, scale=1):
    s = size * scale
    im = Image.new("RGB", (int(s * 2.2), int(s * 1.8)), BG)
    F.draw_face(ImageDraw.Draw(im), im.width / 2, im.height / 2, s, look, t, FG, BG, font=font)
    return im


for look in F.LOOKS:
    for scale in (1, 2):
        s = FACE_SIZE * scale
        im = draw(look, 1.0 + 0.37 * scale, scale=scale)
        cx, cy = im.width / 2, im.height / 2
        x0, y0, x1, y1 = BotScreen.face_box((cx, cy, s))
        inside = Image.new("RGB", im.size, BG)
        inside.paste(im.crop((x0, y0, x1, y1)), (x0, y0))
        diff = sum(1 for a, b in zip(im.getdata(), inside.getdata()) if a != b)
        check(f"{look} at {s}px: all of it in its box ({diff} pixels out)", diff == 0)

# blinks: every few seconds, not on the dot
shut = []
t = 0.0
while t < 60:
    if F.face_state("idle", t)[0] < 0.3:
        if not shut or t - shut[-1] > 0.5:
            shut.append(t)
    t += 0.01
gaps = [b - a for a, b in zip(shut, shut[1:])]
check(f"a blink every few seconds, never quite the same gap ({len(shut)} in a minute, {min(gaps):.2f}..{max(gaps):.2f} s)",
      10 <= len(shut) <= 30 and max(gaps) - min(gaps) > 1.0 and min(gaps) > 0.25)
check("asleep: eyes nearly shut, all the time", all(F.face_state("sleepy", x / 7)[0] < 0.3 for x in range(100)))
looks_at = {F.face_state("idle", x * 0.5)[1] for x in range(120)}
check(f"it glances about ({len(looks_at)} places in a minute)", len(looks_at) >= 4)
check("thinking: it looks up and away", F.face_state("thinking", 3.3)[1] == (0.75, -0.75))
mouths = {round(F.face_state("talking", x / 12)[2], 2) for x in range(48)}
check(f"talking: its mouth moves ({len(mouths)} ways in 4 seconds)", len(mouths) >= 12)

# face_wait: nothing changes before it says (between a blink and a glance), a frame every twentieth of a second
# through one, and few frames a minute all told
random.seed(5)
bad, frames = [], {}
for look in ("idle", "happy", "sad", "curious", "cool", "alert"):
    t = random.uniform(0, 10)
    start, n = t, 0
    while t < start + 60:
        w = F.face_wait(look, t)
        if w > 0.051:
            a = draw(look, t)
            mid = draw(look, t + w * random.uniform(0.2, 0.97))
            if a.tobytes() != mid.tobytes():
                bad.append((look, round(t, 2), round(w, 3)))
        t += w
        n += 1
    frames[look] = n
check(f"face_wait: the face is the same until then ({bad[:3]})", not bad)
check(f"...a few frames a second at most, all told, not a steady twenty ({frames} a minute)", all(n <= 300 for n in frames.values())
      and frames["alert"] < frames["idle"])
check("busy looks: a dozen frames a second; dozing, five", all(abs(F.face_wait(k, 1.234) - 1 / 12) < 1e-9
      for k in ("talking", "thinking", "listening")) and abs(F.face_wait("sleepy", 1.234) - 0.2) < 1e-9)

sheet = Image.new("RGB", (len(F.LOOKS) * 250, 210), BG)
for k, look in enumerate(F.LOOKS):
    sheet.paste(draw(look, 2.2), (k * 250, 0))
sheet.save(SP + "/out/faces_test.png")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
